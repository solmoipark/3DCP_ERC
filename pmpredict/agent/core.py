"""Agent: system prompt + session memory + tool execution around a provider."""
from __future__ import annotations

import time
from typing import Iterator

from .events import Done, Error, Event, TextDelta, ToolCall, ToolProgress, ToolResultEvent
from .memory import Session, tool_result_block
from .prompt import build_system_prompt
from .providers.base import Provider, ensure_done
from .tools import REGISTRY, call_tool
from .tools.registry import ToolContext, ToolResult, ToolSpec
from .tools.runtime import Runtime

MAX_TOOL_ITERATIONS = 12


class Agent:
    def __init__(self, provider: Provider, session: Session, runtime: Runtime, tools: list[ToolSpec] | None = None):
        self.provider = provider
        self.session = session
        self.runtime = runtime
        self.tools = tools or list(REGISTRY.values())
        self._progress_sink = None

    # ------------------------------------------------------------------ tool execution (API providers and SDK in-process tools)
    def execute(self, call: ToolCall, progress=None) -> ToolResult:
        ctx = ToolContext(runtime=self.runtime, session_id=self.session.id,
                          artifact_dir=self.runtime.session_artifact_dir(self.session.id),
                          progress=(progress or (lambda pct, msg: None)))
        return call_tool(call.name, call.input, ctx)

    # ------------------------------------------------------------------ one user turn
    def run(self, user_text: str) -> Iterator[Event]:
        self.session.append_user(user_text)
        system = build_system_prompt(self.runtime, self.session.summary)
        messages = self.session.messages_for_provider() if not self.provider.manages_history else \
            [dict(role="user", content=[dict(type="text", text=user_text)])]
        blocks: list[dict] = []
        text_buf: list[str] = []
        t_call: dict[str, float] = {}

        def flush_text():
            if text_buf:
                blocks.append(dict(type="text", text="".join(text_buf)))
                text_buf.clear()

        def execute(call: ToolCall) -> ToolResult:
            t_call[call.id] = time.time()
            return self.execute(call, progress=None)

        try:
            for ev in ensure_done(self.provider.iter_turn(system=system, messages=messages, tools=self.tools, execute=execute,
                                                          provider_session_id=self.session.meta.get("provider_session_id"))):
                if isinstance(ev, TextDelta):
                    text_buf.append(ev.text)
                elif isinstance(ev, ToolCall):
                    flush_text()
                    blocks.append(dict(type="tool_use", id=ev.id, name=ev.name, input=ev.input))
                    t_call.setdefault(ev.id, time.time())
                elif isinstance(ev, ToolResultEvent):
                    flush_text()
                    if not ev.elapsed_s and ev.id in t_call:
                        ev.elapsed_s = round(time.time() - t_call[ev.id], 2)
                    blocks.append(tool_result_block(ev.id, ev.name, ev.result, ev.elapsed_s))
                elif isinstance(ev, Done):
                    flush_text()
                    self._record_done(ev)
                elif isinstance(ev, Error):
                    flush_text()
                    blocks.append(dict(type="text", text=f"[오류] {ev.message}"))
                yield ev
        finally:
            flush_text()
            self.session.append_assistant(blocks)
            self.session.save_meta()
        self.maybe_summarise()

    def _record_done(self, ev: Done) -> None:
        m = self.session.meta
        if ev.provider_session_id:
            m["provider_session_id"] = ev.provider_session_id
        tot = m.setdefault("usage_total", {})
        for k, v in (ev.usage or {}).items():
            if isinstance(v, (int, float)):
                tot[k] = tot.get(k, 0) + v
        if ev.cost_usd:
            m["cost_usd"] = round(float(m.get("cost_usd") or 0.0) + float(ev.cost_usd), 4)
        m["provider"] = self.provider.name
        m["model"] = self.provider.model

    def maybe_summarise(self) -> None:
        if not self.session.needs_summary():
            return
        try:
            s = self.provider.summarise(self.session.plain_text())
        except Exception:  # noqa: BLE001
            s = None
        if not s:
            s = "최근 대화 (자동 요약 불가, 마지막 6턴):\n" + "\n".join(
                f"{t['role']}: " + " ".join(b.get("text", "") for b in t["content"] if b["type"] == "text")[:400] for t in self.session.turns[-6:])
        self.session.set_summary(s)


def event_to_text(ev: Event) -> str:
    """CLI rendering of one event."""
    if isinstance(ev, TextDelta):
        return ev.text
    if isinstance(ev, ToolCall):
        import json
        return f"\n[tool {ev.name}] {json.dumps(ev.input, ensure_ascii=False)[:300]}\n"
    if isinstance(ev, ToolProgress):
        return f"  … {ev.pct:.0f} % {ev.message}\n"
    if isinstance(ev, ToolResultEvent):
        arts = "".join(f"\n    - {a.kind}: {a.path}" for a in ev.result.artifacts)
        return f"[tool {ev.name} {ev.elapsed_s:.1f} s] {'ERROR ' if ev.result.is_error else ''}{ev.result.summary}{arts}\n"
    if isinstance(ev, Done):
        u = ev.usage or {}
        return f"\n(done; tokens in/out {u.get('input_tokens', '?')}/{u.get('output_tokens', '?')}" + (f", ${ev.cost_usd:.4f}" if ev.cost_usd else "") + ")\n"
    if isinstance(ev, Error):
        return f"\n[error] {ev.message}\n"
    return ""
