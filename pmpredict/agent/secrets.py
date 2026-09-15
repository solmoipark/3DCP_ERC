"""API keys: environment first, then the pastemortar config.json outside this (public) repository.

Values never enter tool results, transcripts, Streamlit state or logs; only "found (env)" / "found (config)" / "none".
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_SECRETS_FILE = Path(r"C:\Users\User\pastemortar_extraction_package_v1.2.2\config.json")
ENV_NAMES = {"anthropic_api_key": "ANTHROPIC_API_KEY", "openai_api_key": "OPENAI_API_KEY"}
_KEY_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|key-[A-Za-z0-9_\-]{12,})")


def secrets_file() -> Path:
    return Path(os.environ.get("PMPREDICT_SECRETS_FILE", str(DEFAULT_SECRETS_FILE)))


def get_secret(name: str) -> str | None:
    env = os.environ.get(ENV_NAMES.get(name, name.upper()))
    if env:
        return env.strip()
    p = secrets_file()
    if p.exists():
        try:
            v = json.loads(p.read_text(encoding="utf-8")).get(name)
        except (OSError, ValueError):
            return None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def secret_source(name: str) -> str:
    """Where a key would come from, without revealing it: 'env' | 'config' | 'none'."""
    if os.environ.get(ENV_NAMES.get(name, name.upper())):
        return "env"
    p = secrets_file()
    if p.exists():
        try:
            v = json.loads(p.read_text(encoding="utf-8")).get(name)
            if isinstance(v, str) and v.strip():
                return "config"
        except (OSError, ValueError):
            pass
    return "none"


def redact(text: str) -> str:
    """Mask anything that looks like an API key in log / error text."""
    if not text:
        return text
    out = _KEY_RE.sub(lambda m: m.group(0)[:3] + "-***", str(text))
    for name in ENV_NAMES:
        v = get_secret(name)
        if v and len(v) > 8:
            out = out.replace(v, v[:3] + "-***")
    return out
