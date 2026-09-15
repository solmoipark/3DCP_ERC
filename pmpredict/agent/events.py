"""Events streamed by providers and consumed by the Streamlit app / CLI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolProgress:
    id: str
    pct: float
    message: str


@dataclass
class ToolResultEvent:
    id: str
    name: str
    result: Any            # tools.registry.ToolResult
    elapsed_s: float


@dataclass
class Done:
    usage: dict = field(default_factory=dict)
    stop_reason: str = "end_turn"
    provider_session_id: str | None = None
    cost_usd: float | None = None


@dataclass
class Error:
    message: str
    recoverable: bool = True


Event = TextDelta | ToolCall | ToolProgress | ToolResultEvent | Done | Error
