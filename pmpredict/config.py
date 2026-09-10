"""Pipeline configuration: paths, seed, and switches.

Configuration is read from ``configs/pipeline.yaml`` at the project root.
The database path can be overridden by the ``PMPREDICT_DB`` environment
variable or an explicit argument (CLI ``--db``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = ROOT / "configs"


@dataclass
class PipelineConfig:
    db_path: Path
    data_dir: Path
    artifacts_dir: Path
    seed: int = 42
    use_mixing_protocol: bool = False
    paper_weighting: str = "sqrt"
    configs_dir: Path = field(default=CONFIGS_DIR)

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def models_dir(self) -> Path:
        return self.artifacts_dir / "models"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    def ensure_dirs(self) -> None:
        for p in (self.raw_dir, self.models_dir, self.reports_dir):
            p.mkdir(parents=True, exist_ok=True)


def _resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def load_config(db_path: str | Path | None = None, path: Path | None = None) -> PipelineConfig:
    """Load ``configs/pipeline.yaml`` and apply overrides (argument > env > file)."""
    path = path or CONFIGS_DIR / "pipeline.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # The database is only needed to (re)build features/targets; the UI and predict/design run from the
    # parquet caches in data/ and the models in artifacts/, so a missing db_path must not stop them.
    db = db_path or os.environ.get("PMPREDICT_DB") or raw.get("db_path") or "master.db"
    return PipelineConfig(
        db_path=_resolve(db),
        data_dir=_resolve(raw.get("data_dir", "data")),
        artifacts_dir=_resolve(raw.get("artifacts_dir", "artifacts")),
        seed=int(raw.get("seed", 42)),
        use_mixing_protocol=bool(raw.get("use_mixing_protocol", False)),
        paper_weighting=str(raw.get("paper_weighting", "sqrt")),
    )


def load_yaml(name: str) -> dict:
    """Load a YAML file from the configs directory by file name."""
    return yaml.safe_load((CONFIGS_DIR / name).read_text(encoding="utf-8")) or {}
