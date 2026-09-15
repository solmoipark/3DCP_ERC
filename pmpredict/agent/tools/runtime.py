"""Lazy singletons shared by all tools (and by the Streamlit app through set_runtime)."""
from __future__ import annotations

import json
import os
from functools import cached_property
from pathlib import Path

from ...config import PipelineConfig, load_config


class Runtime:
    def __init__(self, cfg: PipelineConfig | None = None):
        self.cfg = cfg or load_config()

    @cached_property
    def assets(self):
        from ...predict import Assets
        return Assets(self.cfg)

    @cached_property
    def store(self):
        from ...design.retrieve import LiteratureStore
        return LiteratureStore(self.cfg)

    @cached_property
    def cal(self) -> dict:
        from ...buildability import load_calibration
        return load_calibration(self.cfg)

    @cached_property
    def age_support(self) -> dict[str, dict]:
        ages = {}
        for k, m in self.assets.manifest["models"].items():
            if m.get("variant") == "general":
                p = self.cfg.artifacts_dir / m["path"] / "meta.json"
                if p.exists():
                    ages[m["target"]] = json.loads(p.read_text(encoding="utf-8")).get("age_support") or {}
        return ages

    @property
    def print_db_path(self) -> Path:
        return Path(os.environ.get("PMPREDICT_PRINT_DB") or (Path(self.cfg.db_path).parent / "print_process.db"))

    @property
    def master_db_path(self) -> Path:
        return Path(self.cfg.db_path)

    @property
    def agent_root(self) -> Path:
        p = Path(os.environ.get("PMPREDICT_HOME") or (Path.home() / ".pmpredict" / "agent"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_root(self) -> Path:
        p = self.cfg.reports_dir / "agent"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def session_artifact_dir(self, session_id: str) -> Path:
        p = self.reports_root / session_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def build_summary(self) -> dict:
        p = self.cfg.data_dir / "build_summary.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


_RUNTIME: Runtime | None = None


def get_runtime() -> Runtime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = Runtime()
    return _RUNTIME


def set_runtime(rt: Runtime) -> None:
    global _RUNTIME
    _RUNTIME = rt
