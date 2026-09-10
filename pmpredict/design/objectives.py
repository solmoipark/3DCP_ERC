"""Secondary objectives: cost, embodied CO2, clinker fraction (per kg powder and per m3)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .. import vocab as V
from ..config import CONFIGS_DIR
from ..composition import ACT_GROUPS, ADMIX_GROUPS, AGG_GROUPS, FIBRE_GROUPS, NANO_GROUPS, POWDER_GROUPS

DEFAULT_TABLES = {"cost": CONFIGS_DIR / "unit_cost_default.yaml", "co2": CONFIGS_DIR / "embodied_carbon_default.yaml"}


class FactorTable:
    def __init__(self, path: Path | str | None, kind: str):
        p = Path(path) if path else DEFAULT_TABLES[kind]
        self.path = p
        self.is_default = path is None
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        self.unit = d.get("unit", "")
        self.groups: dict[str, float] = {k: float(v) for k, v in d["groups"].items()}
        self.hash = hashlib.sha256(p.read_bytes()).hexdigest()[:12]

    def get(self, group: str) -> float:
        return self.groups.get(group, np.nan)

    def provenance(self) -> dict:
        return dict(path=str(self.path), hash=self.hash, default=self.is_default, unit=self.unit)


def per_kg_powder(F: pd.DataFrame, table: FactorTable) -> np.ndarray:
    """Sum over all constituents of (mass per kg powder) x factor."""
    tot = np.zeros(len(F))
    for g in POWDER_GROUPS:
        tot += F[f"pw_{g}"].to_numpy(float) * table.get(g)
    tot += F["water_b"].fillna(0).to_numpy(float) * table.get("water")
    sb = F["sand_b"].fillna(0).to_numpy(float)
    shares = np.column_stack([F[f"agg_{g}"].to_numpy(float) for g in AGG_GROUPS])
    known = shares.sum(axis=1)
    agg_factor = np.where(known > 0, sum(shares[:, i] * table.get(g) for i, g in enumerate(AGG_GROUPS)) / np.maximum(known, 1e-9),
                          table.get("natural_sand"))
    tot += sb * agg_factor
    for g in ADMIX_GROUPS:
        tot += F[f"adx_{g}_pct"].to_numpy(float) / 100.0 * table.get(g)
    tot += F["fibre_total_mass_b"].to_numpy(float) * np.nanmean([table.get(g) for g in FIBRE_GROUPS])
    for g in ACT_GROUPS:
        tot += F[f"act_{g}"].to_numpy(float) * table.get(g)
    for g in NANO_GROUPS:
        tot += F[f"nano_{g}_pct"].to_numpy(float) / 100.0 * table.get(g)
    return tot


def powder_kg_per_m3(F: pd.DataFrame, air_frac: float = 0.02) -> np.ndarray:
    """Absolute-volume estimate of powder content (kg/m3) from group specific gravities."""
    gd = V.group_defaults()
    vol = np.zeros(len(F))            # m3 per kg powder
    for g in POWDER_GROUPS:
        vol += F[f"pw_{g}"].to_numpy(float) / (gd[g].sg * 1000.0)
    vol += F["water_b"].fillna(0).to_numpy(float) / 1000.0
    sb = F["sand_b"].fillna(0).to_numpy(float)
    shares = np.column_stack([F[f"agg_{g}"].to_numpy(float) for g in AGG_GROUPS])
    known = shares.sum(axis=1)
    agg_sg = np.where(known > 0, sum(shares[:, i] * gd[g].sg for i, g in enumerate(AGG_GROUPS)) / np.maximum(known, 1e-9), 2.65)
    vol += sb / (agg_sg * 1000.0)
    for g in ADMIX_GROUPS:
        vol += F[f"adx_{g}_pct"].to_numpy(float) / 100.0 / (gd[g].sg * 1000.0)
    for g in ACT_GROUPS:
        vol += F[f"act_{g}"].to_numpy(float) / (gd[g].sg * 1000.0)
    vol += F["fibre_total_mass_b"].to_numpy(float) / (3.0 * 1000.0)
    return (1.0 - air_frac) / np.maximum(vol, 1e-9)


def clinker_fraction(F: pd.DataFrame) -> np.ndarray:
    w = V.clinker_weight()
    return sum(F[f"pw_{g}"].to_numpy(float) * float(wt) for g, wt in w.items() if f"pw_{g}" in F.columns)


def compute_objectives(F: pd.DataFrame, cost: FactorTable, co2: FactorTable,
                       strength_q10: np.ndarray | None = None) -> pd.DataFrame:
    kgm3 = powder_kg_per_m3(F)
    out = pd.DataFrame(index=F.index)
    out["powder_kg_m3"] = kgm3
    out["cost_per_kg_powder"] = per_kg_powder(F, cost)
    out["co2_per_kg_powder"] = per_kg_powder(F, co2)
    out["cost_per_m3"] = out["cost_per_kg_powder"] * kgm3
    out["co2_per_m3"] = out["co2_per_kg_powder"] * kgm3
    out["clinker_fraction"] = clinker_fraction(F)
    if strength_q10 is not None:
        s = np.maximum(np.asarray(strength_q10, float), 1e-6)
        out["co2_per_mpa"] = out["co2_per_m3"] / s
        out["cost_per_mpa"] = out["cost_per_m3"] / s
    return out


OBJECTIVE_COLUMN = {"cost": "cost_per_m3", "co2": "co2_per_m3", "clinker_fraction": "clinker_fraction",
                    "co2_per_mpa": "co2_per_mpa", "cost_per_mpa": "cost_per_mpa"}
