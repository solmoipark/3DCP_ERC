"""Shared mix input contract (``MixSpec``) used by ``predict`` and produced by ``design``.

A MixSpec is converted to a ``MixComposition`` through the very same
``composition.normalize_mix`` that the training pipeline uses on DB rows, so
features computed for a hand-written mix are identical to those of an
equivalent DB mix (see tests/test_featurize_parity.py).

JSON shape::

    {"schema_version": "1.0", "name": "opc_mortar", "system_type": "mortar",
     "basis": "mass_frac_of_powder",
     "components": [
        {"material_class": "portland_cement", "amount": 0.70,
         "props": {"blaine_m2kg": 380, "sg": 3.15, "oxides": {"SiO2": 20.1, "CaO": 63.5}}},
        {"material_class": "ggbfs", "amount": 0.30},
        {"material_class": "natural_sand", "amount": 2.0},
        {"material_class": "superplasticiser_pce", "amount": 0.008, "solid_content_pct": 30},
        {"material_class": "steel_fibre", "vol_pct": 0.5, "length_mm": 13, "diameter_um": 200},
        {"material_class": "sodium_hydroxide", "amount": 0.08, "molarity": 10}],
     "water_binder": 0.40,
     "conditions": {"age_d": 28, "comparability_group": "comp_cube50", "rest_time_s": 0,
                    "curing_temp_C": 20, "curing_rh_pct": 95, "curing_regime": "water", "is_3dcp": 0}}

``amount`` is mass relative to total powder (fraction) for basis ``mass_frac_of_powder``
or kg/m3 for basis ``kg_m3``. Powder amounts must sum to 1 (mass-fraction basis).
"""
from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from . import vocab as V

SCHEMA_VERSION = "1.0"
SYSTEM_TYPES = {"paste", "mortar"}
COMPARABILITY_GROUPS = ["comp_cube50", "comp_cube_other", "comp_prism40", "comp_cyl_small",
                        "comp_prism_other", "comp_cube100", "comp_cube70", "comp_cyl_standard"]
FILLER_GROUPS = {"limestone_powder", "quartz_powder", "inert_filler_other"}


class SpecError(ValueError):
    pass


@dataclass
class Component:
    material_class: str
    amount: float | None = None          # mass rel. to powder (fraction) or kg/m3 (basis kg_m3)
    role: str | None = None              # optional override; inferred from material_class otherwise
    props: dict = field(default_factory=dict)   # blaine_m2kg, sg, d50_um, bet_m2g, oxides{...}
    solid_content_pct: float | None = None
    vol_pct: float | None = None         # fibres: volume % of mix
    molarity: float | None = None        # activators: mol/L
    length_mm: float | None = None
    diameter_um: float | None = None


@dataclass
class Conditions:
    age_d: float | None = None
    comparability_group: str | None = None
    rest_time_s: float | None = None
    curing_temp_C: float | None = None
    curing_rh_pct: float | None = None
    curing_regime: str | None = None
    is_3dcp: int = 0
    mix_time_s: float | None = None
    max_rpm: float | None = None
    mixer_type: str | None = None        # free text, e.g. "Hobart mixer"; classified by features.classify_mixer
    # rheometer protocol (only used by rheology targets): geometry text, method_name, numeric parameters
    rheometer_geometry: str | None = None      # e.g. "vane", "coaxial cylinder", "parallel plate"
    rheometer_method: str | None = None        # tests.method_name vocabulary, e.g. "stress_growth_vane"
    rheometer: dict = field(default_factory=dict)  # {pre_shear_rate_1s, pre_shear_s, rest_s, temp_C, shear_rate_max_1s, ramp_s, gap_mm, vane_d_mm}


@dataclass
class MixSpec:
    system_type: str
    components: list[Component]
    water_binder: float | None = None
    sand_binder: float | None = None     # optional: sand/powder mass ratio when aggregate identity is unknown
    conditions: Conditions = field(default_factory=Conditions)
    basis: str = "mass_frac_of_powder"
    name: str | None = None
    year: int | None = None
    schema_version: str = SCHEMA_VERSION

    # ------------------------------------------------------------ (de)serialisation
    @classmethod
    def from_dict(cls, d: dict) -> "MixSpec":
        comps = [Component(**c) if not isinstance(c, Component) else c for c in d.get("components", [])]
        cond = d.get("conditions") or {}
        cond = Conditions(**cond) if not isinstance(cond, Conditions) else cond
        return cls(system_type=d.get("system_type", "mortar"), components=comps,
                   water_binder=d.get("water_binder"), sand_binder=d.get("sand_binder"), conditions=cond,
                   basis=d.get("basis", "mass_frac_of_powder"), name=d.get("name"), year=d.get("year"),
                   schema_version=d.get("schema_version", SCHEMA_VERSION))

    @classmethod
    def from_json(cls, path: str | Path) -> "MixSpec | list[MixSpec]":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [cls.from_dict(x) for x in data]
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------ validation
    def infer_role(self, c: Component) -> str:
        if c.role:
            return c.role
        gi = V.resolve_group(c.material_class, None)
        if gi.family == "powder":
            if V.is_cement_class(c.material_class):
                return "binder"
            return "filler" if gi.group in FILLER_GROUPS else "scm"
        return {"aggregate": "fine_aggregate", "admixture": "admixture", "fibre": "fibre",
                "activator": "activator", "nano": "nanomaterial", "water": "water"}.get(gi.family, "other")

    def validate(self) -> list[str]:
        """Raise SpecError on hard errors; return a list of warnings."""
        warnings: list[str] = []
        if self.system_type not in SYSTEM_TYPES:
            raise SpecError(f"system_type must be one of {sorted(SYSTEM_TYPES)}, got {self.system_type!r}")
        if self.basis not in {"mass_frac_of_powder", "kg_m3"}:
            raise SpecError(f"basis must be 'mass_frac_of_powder' or 'kg_m3', got {self.basis!r}")
        known = set(V.class_to_group())
        if not self.components:
            raise SpecError("components is empty")
        for c in self.components:
            if c.material_class not in known:
                close = difflib.get_close_matches(c.material_class, sorted(known), n=5, cutoff=0.5)
                raise SpecError(f"unknown material_class {c.material_class!r}; did you mean {close}? "
                                f"({len(known)} accepted classes in configs/material_groups.yaml)")
            if c.amount is None and c.vol_pct is None and c.molarity is None:
                raise SpecError(f"component {c.material_class}: give amount (or vol_pct for fibres)")
            if c.amount is not None and c.amount < 0:
                raise SpecError(f"component {c.material_class}: negative amount")
        powder = [c for c in self.components if V.resolve_group(c.material_class, self.infer_role(c)).family == "powder"]
        if not powder:
            raise SpecError("no powder (binder/scm/filler) component")
        if self.basis == "mass_frac_of_powder":
            s = sum(c.amount or 0.0 for c in powder)
            if abs(s - 1.0) > 0.01:
                raise SpecError(f"powder amounts must sum to 1 (mass_frac_of_powder), got {s:.4f}")
            if abs(s - 1.0) > 1e-6:
                warnings.append(f"powder amounts sum to {s:.4f}; normalised to 1")
                for c in powder:
                    c.amount = (c.amount or 0.0) / s
        has_water = any(self.infer_role(c) == "water" for c in self.components)
        if self.water_binder is None and not has_water:
            raise SpecError("water_binder (or a water component) is required")
        if self.water_binder is not None and not (0.05 <= self.water_binder <= 3.0):
            warnings.append(f"water_binder {self.water_binder} is outside the usual range 0.05-3.0")
        cg = self.conditions.comparability_group
        if cg is not None and cg not in COMPARABILITY_GROUPS:
            warnings.append(f"comparability_group {cg!r} not in {COMPARABILITY_GROUPS}; treated as unknown")
        if self.conditions.age_d is not None and self.conditions.age_d <= 0:
            raise SpecError("conditions.age_d must be > 0")
        return warnings

    # -------------------------------------------------- bridge to composition path
    def to_component_rows(self) -> pd.DataFrame:
        """Rows shaped like mix_components (+material_class) for ``composition.normalize_mix``."""
        rows = []
        kg = self.basis == "kg_m3"
        for i, c in enumerate(self.components):
            role = self.infer_role(c)
            fam = V.resolve_group(c.material_class, role).family
            base = dict(material_uid=f"spec::{i}", role=role, material_class=c.material_class,
                        dosage_raw=None, solid_content=c.solid_content_pct, density_solution=None)
            if c.amount is not None:
                if kg:
                    rows.append({**base, "dosage_reported": c.amount, "unit_reported": "kg/m3", "basis_reported": "kg_m3"})
                elif fam == "powder" or fam in {"water", "aggregate", "activator", "other"}:
                    rows.append({**base, "dosage_reported": c.amount, "unit_reported": "ratio", "basis_reported": "ratio_to_binder"})
                else:  # admixture, fibre, nano: percent of powder
                    rows.append({**base, "dosage_reported": 100.0 * c.amount, "unit_reported": "%", "basis_reported": "pct_binder_mass"})
            if fam == "fibre" and c.vol_pct is not None:
                rows.append({**base, "material_uid": f"spec::{i}v", "dosage_reported": c.vol_pct, "unit_reported": "vol%",
                             "basis_reported": "pct_binder_volume"})
            if c.molarity is not None:
                rows.append({**base, "material_uid": f"spec::{i}m", "dosage_reported": c.molarity, "unit_reported": "mol/L",
                             "basis_reported": "molarity"})
        if self.water_binder is not None and not any(r["role"] == "water" for r in rows):
            rows.append(dict(material_uid="spec::water", role="water", material_class="water", dosage_raw=None,
                             solid_content=None, density_solution=None,
                             dosage_reported=self.water_binder, unit_reported="ratio", basis_reported="ratio_to_binder")
                        if not kg else
                        dict(material_uid="spec::water", role="water", material_class="water", dosage_raw=None,
                             solid_content=None, density_solution=None, dosage_reported=None,
                             unit_reported=None, basis_reported=None))
        return pd.DataFrame(rows)

    def to_mix_row(self) -> pd.Series:
        cd = self.conditions
        return pd.Series(dict(
            mix_uid=f"spec::{self.name or 'mix'}", paper_uid="spec", system_type=self.system_type,
            w_b_reported=self.water_binder, sand_binder_ratio=self.sand_binder,
            sand_binder_basis=("mass" if self.sand_binder is not None else None),
            fresh_density_kg_m3=None, binder_total_kg_m3=None, curing_regime=cd.curing_regime,
            curing_temp_C=cd.curing_temp_C, curing_rh_pct=cd.curing_rh_pct, is_control_mix=None,
        ))

    def material_props(self) -> dict[str, dict]:
        """Per-component user-supplied properties keyed by synthetic material_uid."""
        out = {}
        for i, c in enumerate(self.components):
            p = dict(c.props or {})
            if c.length_mm is not None:
                p["fibre_length_mm"] = c.length_mm
            if c.diameter_um is not None:
                p["fibre_diameter_um"] = c.diameter_um
            if c.solid_content_pct is not None:
                p["solid_content_pct"] = c.solid_content_pct
            if p:
                out[f"spec::{i}"] = p
        return out
