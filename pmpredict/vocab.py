"""Controlled vocabularies and unit tables shared by the whole pipeline.

Everything declarative about the source DB lives here or in
``configs/material_groups.yaml``: dosage-basis classes, NULL-basis inference,
material-class grouping, oxide alias normalisation and physical-property unit
factors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import load_yaml

# ---------------------------------------------------------------- dosage bases
ABS_MASS = {"kg_m3", "g_per_batch", "kg_per_batch"}
PARTS = {"mass_parts"}
REL_B_PCT = {"pct_binder_mass", "pct_binder_mass_basis_unstated", "pct_of_binder_mass"}
REL_B_RAT = {"ratio_to_binder"}
REL_C_PCT = {"pct_cement_mass"}
REL_C_RAT = {"ratio_to_cement"}
REL_SOLIDS_PCT = {"pct_total_solids"}
REL_SOLIDS_RAT = {"ratio_to_solids"}
REL_AGG = {"pct_aggregate_mass"}
VOLUME = {"pct_binder_volume", "volume_parts"}
LIQ_VOL = {"L_per_m3"}
ADMIX_SOL = {"pct_admixture_solid_content"}
ADMIX_LIQ = {"pct_admixture_solution_mass"}
MOLARITY = {"molarity"}
ALL_BASES = (ABS_MASS | PARTS | REL_B_PCT | REL_B_RAT | REL_C_PCT | REL_C_RAT | REL_SOLIDS_PCT
             | REL_SOLIDS_RAT | REL_AGG | VOLUME | LIQ_VOL | ADMIX_SOL | ADMIX_LIQ | MOLARITY)

ROLES = ["binder", "scm", "filler", "water", "fine_aggregate", "admixture", "activator",
         "fibre", "nanomaterial", "other"]
ROLE_FAMILY = {
    "binder": "powder", "scm": "powder", "filler": "powder", "water": "water",
    "fine_aggregate": "aggregate", "admixture": "admixture", "activator": "activator",
    "fibre": "fibre", "nanomaterial": "nano", "other": "other",
}
FAMILIES = ["powder", "aggregate", "admixture", "fibre", "activator", "nano", "water", "other"]

_UNIT_KG_M3 = {"kg/m3", "kg_m3", "kg_per_m3", "kg/m^3", "kg m-3"}
_UNIT_G = {"g", "g_per_batch", "gram", "grams"}
_UNIT_KG = {"kg", "kg_per_batch", "kg/batch"}
_UNIT_RATIO = {"ratio", "dimensionless", "kg/kg binder", "mass_ratio_to_binder", "-", "fraction"}
_UNIT_PCT = {"%", "pct", "wt%", "wt.%", "% wt", "mass%", "percent", "pct_of_binder_mass", "% by mass"}
_UNIT_VOLPCT = {"vol%", "vol.%", "% by volume", "%v/v", "vol_pct", "% volume", "%vol"}
_UNIT_MOLAR = {"mol/l", "m", "mol", "n", "molar"}
_UNIT_L_M3 = {"l/m3", "l_per_m3", "lt/m3"}


def infer_basis(unit: str | None, role: str | None) -> str | None:
    """Infer a dosage basis for rows where basis_reported is NULL (2,644 rows).

    Returns a basis label from ``ALL_BASES`` or None when it cannot be inferred.
    """
    u = (unit or "").strip().lower()
    if not u:
        return None
    if u in _UNIT_KG_M3:
        return "kg_m3"
    if u in _UNIT_G:
        return "g_per_batch"
    if u in _UNIT_KG:
        return "kg_per_batch"
    if u in _UNIT_MOLAR:
        return "molarity"
    if u in _UNIT_L_M3:
        return "L_per_m3"
    if u in _UNIT_RATIO:
        return "ratio_to_binder"
    if u in _UNIT_VOLPCT or "volume" in u or "vol" in u:
        return "pct_binder_volume"
    if u in _UNIT_PCT or u.startswith("%") or u.startswith("wt"):
        if role in {"admixture", "fibre", "nanomaterial", "scm", "filler", "other", "activator"}:
            return "pct_binder_mass"
        return "mass_parts"
    return None


# --------------------------------------------------------- material grouping
@dataclass(frozen=True)
class GroupInfo:
    group: str
    family: str
    sg: float
    solid_content: float | None


@lru_cache(maxsize=1)
def _groups_yaml() -> dict:
    return load_yaml("material_groups.yaml")


@lru_cache(maxsize=1)
def group_defaults() -> dict[str, GroupInfo]:
    out = {}
    for g, d in _groups_yaml()["group_defaults"].items():
        out[g] = GroupInfo(g, d["family"], float(d.get("sg", 2.7)), d.get("solid_content"))
    return out


@lru_cache(maxsize=1)
def class_to_group() -> dict[str, str | None]:
    return dict(_groups_yaml()["classes"])


def cement_groups() -> set[str]:
    return set(_groups_yaml()["cement_groups"])


def clinker_weight() -> dict[str, float]:
    return dict(_groups_yaml()["clinker_weight"])


def groups_by_family(family: str) -> list[str]:
    return [g for g, gi in group_defaults().items() if gi.family == family]


def resolve_group(material_class: str | None, role: str | None) -> GroupInfo:
    """Map (material_class, role) to a GroupInfo.

    The class decides the group; the class 'other' (or an unmapped class)
    falls back to ``other_<family-of-role>``.
    """
    c2g = class_to_group()
    g = c2g.get(material_class or "")
    if g is None:
        fam = ROLE_FAMILY.get(role or "other", "other")
        g = f"other_{fam}" if fam != "powder" else "other_powder"
        if g not in group_defaults():
            # e.g. other_aggregate -> other_agg, other_admixture -> other_admix, ...
            alias = {"other_aggregate": "other_agg", "other_admixture": "other_admix",
                     "other_activator": "other_activator", "other_fibre": "other_fibre",
                     "other_nano": "nano_other", "other_water": "water", "other_other": "other_other"}
            g = alias.get(g, "other_other")
    return group_defaults()[g]


def is_cement_class(material_class: str | None) -> bool:
    g = class_to_group().get(material_class or "")
    return g in cement_groups()


# --------------------------------------------------------- chemistry aliases
OXIDES = ["SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3", "K2O", "Na2O", "TiO2", "P2O5", "MnO", "LOI", "Cl"]
EXTRA_CHEM = ["na2o_eq"]

_OXIDE_ALIAS: dict[str, tuple[str, float]] = {
    # LOI spellings
    "loi": ("LOI", 1.0), "l.o.i": ("LOI", 1.0), "l.o.i.": ("LOI", 1.0), "loss": ("LOI", 1.0),
    "loss of ignition": ("LOI", 1.0), "loss on ignition": ("LOI", 1.0), "loss_on_ignition": ("LOI", 1.0),
    "ignition loss": ("LOI", 1.0), "loi_950c": ("LOI", 1.0), "loi_975c": ("LOI", 1.0),
    "loi_1050c": ("LOI", 1.0), "loi_reported": ("LOI", 1.0), "paf(loi)": ("LOI", 1.0), "p.a.f": ("LOI", 1.0),
    # chloride
    "cl-": ("Cl", 1.0), "chloride": ("Cl", 1.0), "chloride as cl-": ("Cl", 1.0), "cl_content_volhard": ("Cl", 1.0),
    # alkali equivalent
    "na2oeq": ("na2o_eq", 1.0), "na2o_eq": ("na2o_eq", 1.0), "na2o eq": ("na2o_eq", 1.0),
    "na2oequiv": ("na2o_eq", 1.0), "na2o_equivalent": ("na2o_eq", 1.0), "total_alkali_na2oeq": ("na2o_eq", 1.0),
    "na2o+0.658k2o": ("na2o_eq", 1.0), "na2o+0.658k2o_alkali_equivalent": ("na2o_eq", 1.0),
    "alkalies (0.658 k2o + na2o)": ("na2o_eq", 1.0), "r2o_alkali_equivalent": ("na2o_eq", 1.0),
    # manganese / iron / sulfur forms -> canonical oxide with stoichiometric factor
    "mn2o3": ("MnO", 0.899), "mno2": ("MnO", 0.816), "mn3o4": ("MnO", 0.930),
    "feo": ("Fe2O3", 1.111), "fe2o3t": ("Fe2O3", 1.0),
    "so4": ("SO3", 0.833), "sulphate": ("SO3", 1.0), "so3 (as sulphate)": ("SO3", 1.0),
}


def normalize_component(label: str | None) -> tuple[str, float] | None:
    """Return (canonical oxide, factor) or None for non-oxide / unrecognised labels."""
    if not isinstance(label, str) or not label:
        return None
    s = label.strip()
    if s in OXIDES:
        return s, 1.0
    key = s.lower()
    if key in _OXIDE_ALIAS:
        return _OXIDE_ALIAS[key]
    for ox in OXIDES:
        if key == ox.lower():
            return ox, 1.0
    return None


# ------------------------------------------------------ physical property units
# property -> (canonical unit, {unit_reported(lower): factor})
PHYS_UNITS: dict[str, tuple[str, dict[str, float]]] = {
    "blaine_fineness": ("m2/kg", {"m2/kg": 1.0, "cm2/g": 0.1, "cm2/gm": 0.1, "m2/g": 1000.0}),
    "bet_surface_area": ("m2/g", {"m2/g": 1.0, "m2/kg": 0.001, "cm2/g": 1e-4}),
    "d10": ("um", {"um": 1.0, "µm": 1.0, "mm": 1000.0, "nm": 0.001}),
    "d50": ("um", {"um": 1.0, "µm": 1.0, "mm": 1000.0, "nm": 0.001}),
    "d90": ("um", {"um": 1.0, "µm": 1.0, "mm": 1000.0, "nm": 0.001}),
    "mean_particle_size": ("um", {"um": 1.0, "µm": 1.0, "mm": 1000.0, "nm": 0.001}),
    "dmax": ("mm", {"mm": 1.0, "um": 0.001}),
    "specific_gravity": ("-", {"dimensionless": 1.0, "": 1.0, "g/cm3": 1.0, "g/cc": 1.0, "g/ml": 1.0,
                               "kg/l": 1.0, "kg/dm3": 1.0, "t/m3": 1.0, "mg/m3": 1.0, "kg/m3": 0.001}),
    "particle_density": ("-", {"dimensionless": 1.0, "g/cm3": 1.0, "g/cc": 1.0, "g/ml": 1.0, "kg/l": 1.0,
                               "kg/dm3": 1.0, "t/m3": 1.0, "mg/m3": 1.0, "kg/m3": 0.001}),
    "bulk_density_loose": ("kg/m3", {"kg/m3": 1.0, "g/cm3": 1000.0, "g/cc": 1000.0, "g/ml": 1000.0,
                                     "kg/l": 1000.0, "kg/lit": 1000.0, "kg/dm3": 1000.0, "t/m3": 1000.0,
                                     "mg/m3": 1000.0, "g/l": 1.0, "pcf": 16.018}),
    "bulk_density_compacted": ("kg/m3", {"kg/m3": 1.0, "g/cm3": 1000.0, "kg/l": 1000.0, "t/m3": 1000.0,
                                         "mg/m3": 1000.0}),
    "density_solution": ("g/cm3", {"g/cm3": 1.0, "g/ml": 1.0, "kg/l": 1.0, "kg/dm3": 1.0, "kg/m3": 0.001,
                                   "dimensionless": 1.0}),
    "fibre_length": ("mm", {"mm": 1.0, "um": 0.001, "cm": 10.0, "nm": 1e-6}),
    "fibre_diameter": ("um", {"um": 1.0, "mm": 1000.0, "nm": 0.001}),
    "tensile_strength_fibre": ("MPa", {"mpa": 1.0, "gpa": 1000.0, "n/mm2": 1.0, "kn/mm2": 1000.0}),
    "elastic_modulus_fibre": ("GPa", {"gpa": 1.0, "mpa": 0.001, "kn/mm2": 1.0}),
    "solid_content": ("%", {"%": 1.0, "pct": 1.0, "% mass": 1.0}),
    "purity": ("%", {"%": 1.0, "pct": 1.0, "% mass": 1.0}),
    "loi_material": ("%", {"%": 1.0, "pct": 1.0}),
    "moisture_content": ("%", {"%": 1.0, "pct": 1.0}),
    "water_absorption_aggregate": ("%", {"%": 1.0, "pct": 1.0}),
    "residue_45um": ("%", {"%": 1.0, "pct": 1.0}),
    "free_cao": ("%", {"%": 1.0}),
    "na2o_equivalent": ("%", {"%": 1.0}),
    "fineness_modulus": ("-", {"dimensionless": 1.0, "": 1.0}),
    "aspect_ratio": ("-", {"dimensionless": 1.0}),
    "silica_modulus": ("-", {"dimensionless": 1.0}),
    "ph_admixture": ("-", {"dimensionless": 1.0, "ph": 1.0, "": 1.0}),
}

# plausible range after conversion (drop values outside)
PHYS_RANGE: dict[str, tuple[float, float]] = {
    "blaine_fineness": (100, 3000), "bet_surface_area": (0.05, 800), "d10": (0.005, 5000), "d50": (0.01, 10000),
    "d90": (0.05, 20000), "mean_particle_size": (0.005, 10000), "dmax": (0.05, 40),
    "specific_gravity": (0.5, 8.0), "particle_density": (0.5, 8.0), "bulk_density_loose": (100, 4000),
    "bulk_density_compacted": (100, 4000), "density_solution": (0.8, 2.5), "fibre_length": (0.01, 100),
    "fibre_diameter": (0.01, 2000), "tensile_strength_fibre": (10, 8000), "elastic_modulus_fibre": (0.5, 600),
    "solid_content": (0.5, 100), "purity": (1, 100), "loi_material": (0, 60), "moisture_content": (0, 60),
    "water_absorption_aggregate": (0, 60), "residue_45um": (0, 100), "free_cao": (0, 40),
    "na2o_equivalent": (0, 30), "fineness_modulus": (0.3, 6), "aspect_ratio": (1, 5000),
    "silica_modulus": (0.2, 4), "ph_admixture": (0, 14),
}


def convert_phys(prop: str, value: float | None, unit: str | None) -> float | None:
    """Convert a material_physical row to its canonical unit; None if unknown/implausible."""
    if not isinstance(prop, str) or prop not in PHYS_UNITS or value is None or value != value:
        return None
    _, table = PHYS_UNITS[prop]
    u = (unit if isinstance(unit, str) else "").strip().lower().replace("µ", "u")
    if u not in table:
        return None
    v = float(value) * table[u]
    lo, hi = PHYS_RANGE.get(prop, (-1e300, 1e300))
    return v if lo <= v <= hi else None


# ------------------------------------------------------------- misc regexes
DOSE_RESCUE = re.compile(r"^\s*[~≈<>=≤≥]*\s*([0-9]*\.?[0-9]+)\s*$")
