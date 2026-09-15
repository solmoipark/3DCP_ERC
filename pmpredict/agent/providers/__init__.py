"""Provider detection: API keys first, then the subscriptions this machine is logged into."""
from __future__ import annotations

import os

ORDER = ["anthropic", "openai", "claude_sdk", "codex"]
LABELS = {"anthropic": "Anthropic API", "openai": "OpenAI API", "claude_sdk": "Claude 구독 (Agent SDK)", "codex": "ChatGPT 구독 (Codex CLI)", "fake": "테스트용 가짜 프로바이더"}


def _cls(name: str):
    if name == "anthropic":
        from .anthropic_api import AnthropicProvider as P
    elif name == "openai":
        from .openai_api import OpenAIProvider as P
    elif name == "claude_sdk":
        from .claude_sdk import ClaudeSDKProvider as P
    elif name == "codex":
        from .codex_cli import CodexProvider as P
    elif name == "fake":
        from .fake import FakeProvider as P
    else:
        raise KeyError(f"unknown provider {name!r}; choose from {ORDER + ['fake']}")
    return P


def provider_status() -> list[dict]:
    out = []
    for n in ORDER:
        try:
            ok, reason = _cls(n).available()
        except Exception as e:  # noqa: BLE001
            ok, reason = False, f"{type(e).__name__}: {e}"
        out.append(dict(name=n, label=LABELS[n], available=ok, reason=reason))
    return out


def detect_provider(override: str | None = None) -> tuple[str | None, list[dict]]:
    override = override or os.environ.get("PMPREDICT_PROVIDER")
    status = provider_status()
    if override and override != "auto":
        return override, status
    for s in status:
        if s["available"]:
            return s["name"], status
    return None, status


def make_provider(name: str, model: str | None = None):
    P = _cls(name)
    return P(model=model) if model else P()
