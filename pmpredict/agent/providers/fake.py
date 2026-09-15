"""Scripted provider for tests and UI smoke runs (no network)."""
from __future__ import annotations

import json
from typing import Callable, Iterator

from ..events import Done, Event, TextDelta, ToolCall, ToolResultEvent
from ..tools.registry import ToolResult, ToolSpec, result_for_llm
from .base import Provider


class FakeProvider(Provider):
    """script: list of turns; each turn is a list of ("text", str) | ("tool", name, input) steps. After the script runs out,
    every user message is answered with an echo plus a `list_models` call if the text contains '모델'."""
    name = "fake"
    model = "fake-1"

    def __init__(self, model: str | None = None, script: list[list[tuple]] | None = None):
        super().__init__(model)
        self.script = list(script or [])
        self.turn = 0

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return True, "always available (no LLM; echoes and runs scripted tools)"

    def iter_turn(self, *, system, messages, tools, execute: Callable[[ToolCall], ToolResult], provider_session_id=None,
                  on_tool_progress=None) -> Iterator[Event]:
        user_text = ""
        for b in messages[-1]["content"]:
            if b.get("type") == "text":
                user_text += b["text"]
        steps = self.script[self.turn] if self.turn < len(self.script) else self._default_steps(user_text)
        self.turn += 1
        n = 0
        for step in steps:
            if step[0] == "text":
                for chunk in _chunks(step[1]):
                    yield TextDelta(chunk)
            elif step[0] == "tool":
                n += 1
                call = ToolCall(id=f"fake_{self.turn}_{n}", name=step[1], input=step[2])
                yield call
                res = execute(call)
                yield ToolResultEvent(id=call.id, name=call.name, result=res, elapsed_s=0.0)
                yield TextDelta(f"\n[{call.name}] {res.summary or json.dumps(res.data, ensure_ascii=False)[:200]}\n")
        yield Done(usage=dict(input_tokens=0, output_tokens=0), provider_session_id=f"fake-{self.turn}")

    @staticmethod
    def _default_steps(text: str) -> list[tuple]:
        steps = [("text", f"(fake) 입력을 받았습니다: {text[:80]}")]
        low = text.lower()
        mix = dict(system_type="mortar", w_b=0.4, s_b=2.0, binder={"portland_cement": 1.0}, admixtures_pct={"superplasticiser_pce": 0.5},
                   conditions=dict(age_d=28, curing="moist", is_3dcp=False), name="fake_mix")
        if "모델" in text or "model" in low:
            steps.append(("tool", "list_models", {"variant": "general"}))
        elif "예측" in text or "predict" in low:
            steps.append(("tool", "predict_properties", {"mix": mix, "targets": ["compressive_strength", "flow_table_spread"]}))
        elif "판정" in text or "buildab" in low or "사이클" in text:
            steps.append(("tool", "assess_buildability", {"job": {"object_type": "wall", "target_height_mm": 600, "footprint_mm": 1500, "wall_filaments": 2,
                                                                  "nozzle_d_mm": 25, "print_speed_mm_s": 50, "open_time_min": 60},
                                                          "material": {"tau_s0_Pa": 3000, "athix_Pa_s": 1.0}}))
        elif "sql" in low or "논문" in text:
            steps.append(("tool", "sql_query", {"sql": "SELECT COUNT(*) AS n_papers FROM papers WHERE is_3dcp_study='1'"}))
        return steps

    def summarise(self, text: str, max_tokens: int = 800) -> str | None:
        return "(fake summary) " + text[-500:]


def _chunks(s: str, n: int = 24):
    for i in range(0, len(s), n):
        yield s[i:i + n]
