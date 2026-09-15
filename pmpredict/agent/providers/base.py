"""Provider interface: one synchronous event generator per turn, plus an async→sync bridge for SDK backends."""
from __future__ import annotations

import asyncio
import queue
import sys
import threading
from abc import ABC, abstractmethod
from typing import Callable, Iterator

from ..events import Done, Error, Event, ToolCall
from ..tools.registry import ToolResult, ToolSpec

_SENTINEL = object()


class Provider(ABC):
    name: str = "base"
    model: str = ""
    manages_history: bool = False          # True when the backend keeps the conversation itself (resume by session id)

    def __init__(self, model: str | None = None):
        if model:
            self.model = model

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return False, "not implemented"

    @abstractmethod
    def iter_turn(self, *, system: str, messages: list[dict], tools: list[ToolSpec], execute: Callable[[ToolCall], ToolResult],
                  provider_session_id: str | None = None, on_tool_progress=None) -> Iterator[Event]:
        """Yield events for one user turn. `messages` are provider-neutral records (see memory.Session.messages_for_provider);
        the last one is the new user message."""

    def summarise(self, text: str, max_tokens: int = 800) -> str | None:
        """Optional cheap summary call used for rolling session summaries."""
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} model={self.model}>"


def run_async_iter(agen_factory: Callable[[], "AsyncIterator[Event]"]) -> Iterator[Event]:  # noqa: F821
    """Run an async generator on a private loop in a daemon thread and yield its items synchronously."""
    q: queue.Queue = queue.Queue()

    def runner():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def pump():
            try:
                async for ev in agen_factory():
                    q.put(ev)
            except Exception as e:  # noqa: BLE001
                from ..secrets import redact
                q.put(Error(message=redact(f"{type(e).__name__}: {e}"), recoverable=False))
            finally:
                q.put(_SENTINEL)
        try:
            loop.run_until_complete(pump())
        finally:
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    while True:
        ev = q.get()
        if ev is _SENTINEL:
            break
        yield ev


def ensure_done(events: Iterator[Event]) -> Iterator[Event]:
    """Guarantee the stream ends with Done or Error."""
    last = None
    for ev in events:
        last = ev
        yield ev
    if not isinstance(last, (Done, Error)):
        yield Done()
