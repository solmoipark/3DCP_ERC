"""Anthropic Messages API provider: streaming text, client-side tool loop, prompt caching."""
from __future__ import annotations

import json
from typing import Callable, Iterator

from ..events import Done, Error, Event, TextDelta, ToolCall, ToolResultEvent
from ..secrets import get_secret, redact, secret_source
from ..tools.registry import ToolResult, ToolSpec, result_for_llm, to_anthropic_tools
from .base import Provider

DEFAULT_MODEL = "claude-sonnet-5"
SUMMARY_MODEL = "claude-haiku-4-5-20251001"
MAX_ITER = 12


def _to_api_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if m["role"] == "user":
            out.append(dict(role="user", content=[dict(type="text", text=b["text"]) for b in m["content"] if b["type"] == "text"] or
                            [dict(type="text", text="(빈 메시지)")]))
            continue
        # assistant record may interleave text / tool_use / tool_result: split into assistant + user(tool_result) messages
        cur: list[dict] = []
        pending_results: list[dict] = []

        def flush_assistant():
            nonlocal cur
            if cur:
                out.append(dict(role="assistant", content=cur)); cur = []

        def flush_results():
            nonlocal pending_results
            if pending_results:
                out.append(dict(role="user", content=pending_results)); pending_results = []
        for b in m["content"]:
            if b["type"] == "text":
                flush_results()
                if b["text"].strip():
                    cur.append(dict(type="text", text=b["text"]))
            elif b["type"] == "tool_use":
                flush_results()
                cur.append(dict(type="tool_use", id=b["id"], name=b["name"], input=b["input"]))
            elif b["type"] == "tool_result":
                flush_assistant()
                res = ToolResult.from_dict(b["result"])
                pending_results.append(dict(type="tool_result", tool_use_id=b["id"], content=result_for_llm(res), is_error=bool(res.is_error)))
        flush_assistant(); flush_results()
    # the API requires alternating roles; merge consecutive same-role messages
    merged: list[dict] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] = merged[-1]["content"] + m["content"]
        else:
            merged.append(m)
    return merged


class AnthropicProvider(Provider):
    name = "anthropic"
    model = DEFAULT_MODEL

    def __init__(self, model: str | None = None):
        super().__init__(model)
        import anthropic
        self._client = anthropic.Anthropic(api_key=get_secret("anthropic_api_key"))

    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "pip install anthropic"
        src = secret_source("anthropic_api_key")
        return (src != "none"), (f"API key from {src}" if src != "none" else "no ANTHROPIC_API_KEY / config.json anthropic_api_key")

    def iter_turn(self, *, system, messages, tools: list[ToolSpec], execute: Callable[[ToolCall], ToolResult], provider_session_id=None,
                  on_tool_progress=None) -> Iterator[Event]:
        api_msgs = _to_api_messages(messages)
        tool_defs = to_anthropic_tools([t.name for t in tools])
        if tool_defs:
            tool_defs[-1] = dict(tool_defs[-1], cache_control={"type": "ephemeral"})
        sys_blocks = [dict(type="text", text=system, cache_control={"type": "ephemeral"})]
        usage_tot: dict = {}
        for _ in range(MAX_ITER):
            try:
                with self._client.messages.stream(model=self.model, max_tokens=8000, system=sys_blocks, tools=tool_defs, messages=api_msgs) as stream:
                    for text in stream.text_stream:
                        yield TextDelta(text)
                    final = stream.get_final_message()
            except Exception as e:  # noqa: BLE001
                yield Error(message=redact(f"{type(e).__name__}: {e}"), recoverable=False)
                return
            u = final.usage
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                v = getattr(u, k, None)
                if v:
                    usage_tot[k] = usage_tot.get(k, 0) + int(v)
            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason != "tool_use" or not tool_uses:
                if final.stop_reason == "refusal":
                    yield Error(message="모델이 요청을 거부했습니다 (refusal).", recoverable=True)
                yield Done(usage=usage_tot, stop_reason=final.stop_reason or "end_turn")
                return
            api_msgs.append(dict(role="assistant", content=[b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b for b in final.content]))
            results = []
            for b in tool_uses:
                call = ToolCall(id=b.id, name=b.name, input=dict(b.input or {}))
                yield call
                import time
                t0 = time.time()
                res = execute(call)
                yield ToolResultEvent(id=call.id, name=call.name, result=res, elapsed_s=round(time.time() - t0, 2))
                results.append(dict(type="tool_result", tool_use_id=call.id, content=result_for_llm(res), is_error=bool(res.is_error)))
            api_msgs.append(dict(role="user", content=results))
        yield Error(message=f"한 턴에 도구 호출 {MAX_ITER}회 상한에 도달했습니다.", recoverable=True)
        yield Done(usage=usage_tot, stop_reason="max_iterations")

    def summarise(self, text: str, max_tokens: int = 800) -> str | None:
        try:
            r = self._client.messages.create(model=SUMMARY_MODEL, max_tokens=max_tokens, messages=[dict(
                role="user", content="다음 대화를 한국어로 요약해 주세요. 사용자의 목표, 확정된 배합/조건/수치, 미해결 질문을 항목으로:\n\n" + text)])
            return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        except Exception:  # noqa: BLE001
            return None
