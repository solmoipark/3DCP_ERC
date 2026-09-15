"""Claude subscription provider via claude-agent-sdk (bundled Claude Code CLI; uses the machine's Claude Code login or ANTHROPIC_API_KEY).

Tools run in *this* process through an in-process SDK MCP server, so artifacts and results are captured directly.
Headless use on a Pro/Max plan draws from a separate weekly pool; do not deploy this path publicly (personal local use only).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Iterator

from ..events import Done, Error, Event, TextDelta, ToolCall, ToolResultEvent
from ..secrets import redact
from ..tools.registry import ToolResult, ToolSpec, result_for_llm
from .base import Provider, run_async_iter

PREFIX = "mcp__pmpredict__"
MODEL_ALIAS = {"sonnet": "sonnet", "opus": "opus", "claude-sonnet-5": "sonnet", "claude-opus-5": "opus"}


def bundled_cli() -> Path | None:
    try:
        import claude_agent_sdk
    except ImportError:
        return None
    d = Path(claude_agent_sdk.__file__).parent / "_bundled"
    for n in ("claude.exe", "claude"):
        if (d / n).exists():
            return d / n
    return None


def _clean_env() -> dict:
    """The bundled CLI must not inherit a parent Claude Code session's proxy / session variables."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDECODE", "ANTHROPIC_BASE_URL")}
    return env


def auth_status() -> tuple[bool, str]:
    """Ask the bundled CLI whether it is logged in (subscription OAuth or API key)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True, "ANTHROPIC_API_KEY"
    cli = bundled_cli()
    if cli is None:
        return False, "bundled CLI not found"
    try:
        import subprocess
        out = subprocess.run([str(cli), "auth", "status"], capture_output=True, text=True, timeout=20, env=_clean_env())
        d = json.loads(out.stdout[out.stdout.find("{"):]) if "{" in out.stdout else {}
    except Exception as e:  # noqa: BLE001
        return False, f"auth status failed: {type(e).__name__}"
    if d.get("loggedIn"):
        return True, f"logged in ({d.get('authMethod')})"
    return False, f"not logged in — run: \"{cli}\" auth login"


def _logged_in() -> bool:
    return auth_status()[0]


class ClaudeSDKProvider(Provider):
    name = "claude_sdk"
    model = "sonnet"
    manages_history = True

    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            return False, "pip install claude-agent-sdk"
        ok, why = auth_status()
        if not ok:
            return False, f"Claude 구독 로그인 필요: {why}"
        return True, f"claude-agent-sdk (bundled CLI), {why}"

    def _server(self, tools: list[ToolSpec], execute: Callable[[ToolCall], ToolResult], sink: list):
        from claude_agent_sdk import create_sdk_mcp_server, tool
        sdk_tools = []
        for spec in tools:
            def make(spec=spec):
                @tool(spec.name, spec.description, spec.input_schema)
                async def handler(args: dict) -> dict:
                    import asyncio
                    call = ToolCall(id=f"sdk_{spec.name}_{int(time.time() * 1000)}", name=spec.name, input=dict(args or {}))
                    sink.append(call)
                    t0 = time.time()
                    res = await asyncio.get_running_loop().run_in_executor(None, execute, call)
                    sink.append(ToolResultEvent(id=call.id, name=spec.name, result=res, elapsed_s=round(time.time() - t0, 2)))
                    return {"content": [{"type": "text", "text": result_for_llm(res)}], "is_error": bool(res.is_error)}
                return handler
            sdk_tools.append(make())
        return create_sdk_mcp_server(name="pmpredict", version="1.0.0", tools=sdk_tools)

    def iter_turn(self, *, system, messages, tools: list[ToolSpec], execute, provider_session_id=None, on_tool_progress=None) -> Iterator[Event]:
        user_text = "".join(b["text"] for b in messages[-1]["content"] if b["type"] == "text")
        sink: list = []
        from ..tools.runtime import get_runtime
        cwd = get_runtime().reports_root

        async def agen():
            from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, StreamEvent, TextBlock, ToolUseBlock)
            server = self._server(tools, execute, sink)
            opts = ClaudeAgentOptions(
                env=_clean_env(),
                system_prompt=system, mcp_servers={"pmpredict": server}, allowed_tools=[PREFIX + t.name for t in tools], tools=[],
                disallowed_tools=["Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "WebSearch", "WebFetch", "Task", "NotebookEdit"],
                permission_mode="default", setting_sources=[], cwd=str(cwd), resume=provider_session_id, include_partial_messages=True,
                model=MODEL_ALIAS.get(self.model, self.model), max_turns=24)
            streamed = False
            async with ClaudeSDKClient(options=opts) as client:
                await client.query(user_text)
                async for m in client.receive_response():
                    while sink:
                        yield sink.pop(0)
                    if isinstance(m, StreamEvent):
                        ev = m.event or {}
                        if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                            streamed = True
                            yield TextDelta(ev["delta"].get("text", ""))
                    elif isinstance(m, AssistantMessage):
                        for b in m.content:
                            if isinstance(b, TextBlock) and not streamed:
                                yield TextDelta(b.text)
                            elif isinstance(b, ToolUseBlock) and not b.name.startswith(PREFIX):
                                yield TextDelta(f"\n[built-in tool blocked: {b.name}]\n")
                        streamed = False
                    elif isinstance(m, ResultMessage):
                        while sink:
                            yield sink.pop(0)
                        if m.is_error:
                            yield Error(message=redact(str(m.result or m.subtype)), recoverable=True)
                        u = m.usage or {}
                        yield Done(usage={k: v for k, v in u.items() if isinstance(v, (int, float))}, stop_reason=m.subtype or "success",
                                   provider_session_id=m.session_id, cost_usd=m.total_cost_usd)
            while sink:
                yield sink.pop(0)

        yield from run_async_iter(agen)

    def summarise(self, text: str, max_tokens: int = 800) -> str | None:
        out: list[str] = []

        async def agen():
            from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
            opts = ClaudeAgentOptions(tools=[], setting_sources=[], model="haiku", max_turns=1,
                                      system_prompt="대화를 한국어로 요약합니다. 사용자의 목표, 확정된 배합/조건/수치, 미해결 질문을 항목으로.")
            async for m in query(prompt=text[-20000:], options=opts):
                if isinstance(m, ResultMessage) and m.result:
                    out.append(m.result)
                    yield Done()
        try:
            for _ in run_async_iter(agen):
                pass
        except Exception:  # noqa: BLE001
            return None
        return out[0] if out else None
