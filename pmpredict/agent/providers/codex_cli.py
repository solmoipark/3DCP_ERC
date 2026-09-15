"""ChatGPT subscription provider via the OpenAI Codex CLI (`codex exec --json`) with our tools served over MCP (stdio).

Requires `npm i -g @openai/codex` and `codex login` (ChatGPT OAuth; token in ~/.codex/auth.json). Tools run in a separate
`python -m pmpredict.agent.mcp_server` process spawned by Codex; their results are read back from the JSONL event stream.
The event schema of `codex exec --json` is documented as evolving, so parsing is defensive and unknown events are logged.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterator

from ..events import Done, Error, Event, TextDelta, ToolCall, ToolResultEvent
from ..secrets import redact
from ..tools.registry import Artifact, ToolResult, ToolSpec
from .base import Provider

log = logging.getLogger(__name__)


def _codex() -> str | None:
    return shutil.which("codex") or shutil.which("codex.cmd")


class CodexProvider(Provider):
    name = "codex"
    model = os.environ.get("PMPREDICT_CODEX_MODEL", "")     # empty = Codex default
    manages_history = True

    @classmethod
    def available(cls) -> tuple[bool, str]:
        exe = _codex()
        if not exe:
            return False, "codex CLI 없음 (npm i -g @openai/codex)"
        if not (Path.home() / ".codex" / "auth.json").exists() and not os.environ.get("CODEX_API_KEY"):
            return False, "codex 로그인 없음 (codex login)"
        return True, f"codex CLI ({exe})"

    def _cmd(self, session_id: str, prompt: str, provider_session_id: str | None) -> list[str]:
        exe = _codex()
        py = sys.executable.replace("\\", "/")
        cfg = [f'mcp_servers.pmpredict.command="{py}"', 'mcp_servers.pmpredict.args=["-m","pmpredict.agent.mcp_server"]',
               f'mcp_servers.pmpredict.env={{PMPREDICT_SESSION="{session_id}"}}', 'mcp_servers.pmpredict.required=true']
        base = [exe, "exec"]
        if provider_session_id:
            base += ["resume", provider_session_id]
        base += ["--json", "--skip-git-repo-check", "--sandbox", "read-only"]
        for c in cfg:
            base += ["-c", c]
        if self.model:
            base += ["-m", self.model]
        return base + [prompt]

    def iter_turn(self, *, system, messages, tools: list[ToolSpec], execute: Callable[[ToolCall], ToolResult], provider_session_id=None,
                  on_tool_progress=None) -> Iterator[Event]:
        from ..tools.runtime import get_runtime
        rt = get_runtime()
        session_id = os.environ.get("PMPREDICT_SESSION") or "codex"
        user_text = "".join(b["text"] for b in messages[-1]["content"] if b["type"] == "text")
        cwd = rt.reports_root / f"codex_{session_id}"
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / "AGENTS.md").write_text(system + "\n\n도구는 MCP 서버 'pmpredict'의 도구만 사용합니다. 파일 시스템이나 셸은 쓰지 않습니다.\n", encoding="utf-8")
        cmd = self._cmd(session_id, user_text, provider_session_id)
        env = dict(os.environ)
        env["PMPREDICT_SESSION"] = session_id
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        except OSError as e:
            yield Error(message=redact(f"codex 실행 실패: {e}"), recoverable=False)
            return
        thread_id = provider_session_id
        usage: dict = {}
        pending: dict[str, tuple[ToolCall, float]] = {}
        log_path = cwd / "events.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                lf.write(line + "\n")
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                t = ev.get("type", "")
                if t == "thread.started":
                    thread_id = ev.get("thread_id") or thread_id
                elif t in ("item.started", "item.completed", "item.updated"):
                    item = ev.get("item") or {}
                    it = item.get("type") or item.get("item_type") or ""
                    if it in ("agent_message", "assistant_message") and t == "item.completed":
                        yield TextDelta((item.get("text") or item.get("content") or "") + "\n")
                    elif it == "mcp_tool_call":
                        name = (item.get("tool") or item.get("name") or "").split("__")[-1]
                        iid = item.get("id") or f"codex_{len(pending)}"
                        if t == "item.started" and iid not in pending:
                            call = ToolCall(id=iid, name=name, input=item.get("arguments") or item.get("input") or {})
                            pending[iid] = (call, time.time())
                            yield call
                        elif t == "item.completed":
                            if iid not in pending:
                                call = ToolCall(id=iid, name=name, input=item.get("arguments") or item.get("input") or {})
                                pending[iid] = (call, time.time()); yield call
                            call, t0 = pending.pop(iid)
                            yield ToolResultEvent(id=iid, name=call.name, result=_parse_result(item), elapsed_s=round(time.time() - t0, 2))
                elif t == "turn.completed":
                    u = ev.get("usage") or {}
                    usage = dict(input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
                                 cache_read_input_tokens=u.get("cached_input_tokens", 0))
                elif t in ("turn.failed", "error"):
                    msg = (ev.get("error") or {}).get("message") if isinstance(ev.get("error"), dict) else ev.get("message") or str(ev)
                    yield Error(message=redact(str(msg)), recoverable=True)
        rc = proc.wait()
        if rc != 0:
            err = (proc.stderr.read() or "")[-800:]
            yield Error(message=redact(f"codex exit {rc}: {err}"), recoverable=True)
        yield Done(usage=usage, stop_reason="success" if rc == 0 else "error", provider_session_id=thread_id)


def _parse_result(item: dict) -> ToolResult:
    """Tool output as Codex reports it: try to recover our JSON (with artifact list); otherwise wrap the text."""
    out = item.get("result") or item.get("output") or item.get("content")
    text = ""
    if isinstance(out, dict):
        parts = out.get("content") if isinstance(out.get("content"), list) else None
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)) if parts else json.dumps(out, ensure_ascii=False)
    elif isinstance(out, list):
        text = "".join(p.get("text", "") for p in out if isinstance(p, dict))
    elif out is not None:
        text = str(out)
    try:
        d = json.loads(text) if text.startswith("{") else {}
    except ValueError:
        d = {}
    arts = [Artifact(**a) for a in d.pop("artifacts", []) if isinstance(a, dict) and {"path", "kind", "title"} <= set(a)]
    is_err = bool(d.pop("is_error", False)) or bool(item.get("error")) or item.get("status") == "failed"
    return ToolResult(data=d or {"text": text[:4000]}, artifacts=arts, summary=(d.get("summary") or "")[:120] if isinstance(d, dict) else "", is_error=is_err)
