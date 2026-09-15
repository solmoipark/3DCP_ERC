"""OpenAI Chat Completions provider with function calling (streaming)."""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Iterator

from ..events import Done, Error, Event, TextDelta, ToolCall, ToolResultEvent
from ..secrets import get_secret, redact, secret_source
from ..tools.registry import ToolResult, ToolSpec, result_for_llm, to_openai_tools
from .base import Provider

DEFAULT_MODEL = os.environ.get("PMPREDICT_OPENAI_MODEL", "gpt-5")
MAX_ITER = 12


def _to_api_messages(system: str, messages: list[dict]) -> list[dict]:
    out = [dict(role="system", content=system)]
    for m in messages:
        if m["role"] == "user":
            out.append(dict(role="user", content="".join(b["text"] for b in m["content"] if b["type"] == "text")))
            continue
        text, calls = [], []

        def flush():
            nonlocal text, calls
            if text or calls:
                msg = dict(role="assistant", content="".join(text) or None)
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg); text, calls = [], []
        for b in m["content"]:
            if b["type"] == "text":
                text.append(b["text"])
            elif b["type"] == "tool_use":
                calls.append(dict(id=b["id"], type="function", function=dict(name=b["name"], arguments=json.dumps(b["input"], ensure_ascii=False))))
            elif b["type"] == "tool_result":
                flush()
                out.append(dict(role="tool", tool_call_id=b["id"], content=result_for_llm(ToolResult.from_dict(b["result"]))))
        flush()
    return out


class OpenAIProvider(Provider):
    name = "openai"
    model = DEFAULT_MODEL

    def __init__(self, model: str | None = None):
        super().__init__(model)
        import openai
        self._client = openai.OpenAI(api_key=get_secret("openai_api_key"))

    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "pip install openai"
        src = secret_source("openai_api_key")
        return (src != "none"), (f"API key from {src}" if src != "none" else "no OPENAI_API_KEY / config.json openai_api_key")

    def iter_turn(self, *, system, messages, tools: list[ToolSpec], execute: Callable[[ToolCall], ToolResult], provider_session_id=None,
                  on_tool_progress=None) -> Iterator[Event]:
        api_msgs = _to_api_messages(system, messages)
        tool_defs = to_openai_tools([t.name for t in tools])
        usage_tot: dict = {}
        for _ in range(MAX_ITER):
            calls: dict[int, dict] = {}
            text_parts: list[str] = []
            finish = None
            try:
                stream = self._client.chat.completions.create(model=self.model, messages=api_msgs, tools=tool_defs, stream=True,
                                                              stream_options={"include_usage": True})
                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        u = chunk.usage
                        usage_tot["input_tokens"] = usage_tot.get("input_tokens", 0) + int(u.prompt_tokens or 0)
                        usage_tot["output_tokens"] = usage_tot.get("output_tokens", 0) + int(u.completion_tokens or 0)
                    if not chunk.choices:
                        continue
                    ch = chunk.choices[0]
                    d = ch.delta
                    if d and d.content:
                        text_parts.append(d.content); yield TextDelta(d.content)
                    for tc in (d.tool_calls or []) if d else []:
                        slot = calls.setdefault(tc.index, dict(id=None, name="", args=""))
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                slot["name"] += tc.function.name
                            if tc.function.arguments:
                                slot["args"] += tc.function.arguments
                    if ch.finish_reason:
                        finish = ch.finish_reason
            except Exception as e:  # noqa: BLE001
                yield Error(message=redact(f"{type(e).__name__}: {e}"), recoverable=False)
                return
            if not calls:
                yield Done(usage=usage_tot, stop_reason=finish or "stop")
                return
            assistant = dict(role="assistant", content="".join(text_parts) or None,
                             tool_calls=[dict(id=c["id"] or f"call_{i}", type="function", function=dict(name=c["name"], arguments=c["args"] or "{}"))
                                         for i, c in sorted(calls.items())])
            api_msgs.append(assistant)
            for i, c in sorted(calls.items()):
                try:
                    args = json.loads(c["args"] or "{}")
                except ValueError:
                    args = {"_raw": c["args"]}
                call = ToolCall(id=c["id"] or f"call_{i}", name=c["name"], input=args)
                yield call
                t0 = time.time()
                res = execute(call)
                yield ToolResultEvent(id=call.id, name=call.name, result=res, elapsed_s=round(time.time() - t0, 2))
                api_msgs.append(dict(role="tool", tool_call_id=call.id, content=result_for_llm(res)))
        yield Error(message=f"한 턴에 도구 호출 {MAX_ITER}회 상한에 도달했습니다.", recoverable=True)
        yield Done(usage=usage_tot, stop_reason="max_iterations")

    def summarise(self, text: str, max_tokens: int = 800) -> str | None:
        try:
            r = self._client.chat.completions.create(model=os.environ.get("PMPREDICT_OPENAI_SUMMARY_MODEL", "gpt-5-mini"), messages=[dict(
                role="user", content="다음 대화를 한국어로 요약해 주세요. 사용자의 목표, 확정된 배합/조건/수치, 미해결 질문을 항목으로:\n\n" + text)])
            return r.choices[0].message.content
        except Exception:  # noqa: BLE001
            return None
