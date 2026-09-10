"""Unit conversion for design requests (user unit -> canonical target unit)."""
from __future__ import annotations

from ..targets import load_target_rules

# canonical unit -> {alias (lower): factor}
_TABLE: dict[str, dict[str, float]] = {
    "MPa": {"mpa": 1.0, "n/mm2": 1.0, "kpa": 1e-3, "gpa": 1e3, "psi": 0.00689476},
    "GPa": {"gpa": 1.0, "mpa": 1e-3},
    "Pa": {"pa": 1.0, "kpa": 1e3, "mpa": 1e6},
    "Pa.s": {"pa.s": 1.0, "pa·s": 1.0, "pas": 1.0, "mpa.s": 1e-3, "cp": 1e-3},
    "Pa/s": {"pa/s": 1.0, "pa/min": 1 / 60.0, "kpa/s": 1e3},
    "mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
    "min": {"min": 1.0, "minute": 1.0, "minutes": 1.0, "h": 60.0, "hr": 60.0, "hour": 60.0, "hours": 60.0, "s": 1 / 60.0},
    "%": {"%": 1.0, "pct": 1.0, "percent": 1.0, "fraction": 100.0},
    "microstrain": {"microstrain": 1.0, "ue": 1.0, "um/m": 1.0, "µm/m": 1.0, "mm/m": 1000.0, "%": 10000.0, "‰": 1000.0},
    "J/g binder": {"j/g": 1.0, "j/g binder": 1.0, "kj/kg": 1.0},
    "kg/m3": {"kg/m3": 1.0, "g/cm3": 1000.0, "g/ml": 1000.0, "t/m3": 1000.0},
}


class UnitError(ValueError):
    pass


DERIVED_UNITS = {"shear_stress_at_rate": "Pa", "static_yield_stress_at_rest": "Pa"}


def canonical_unit(quantity: str) -> str:
    if quantity in DERIVED_UNITS:
        return DERIVED_UNITS[quantity]
    rules, _ = load_target_rules()
    if quantity not in rules:
        raise UnitError(f"unknown target quantity {quantity!r}; known: {sorted(rules) + sorted(DERIVED_UNITS)}")
    return rules[quantity].get("unit", "")


def to_canonical(quantity: str, value: float | None, unit: str | None) -> float | None:
    """Convert `value` given in `unit` to the canonical unit of `quantity`."""
    if value is None:
        return None
    cu = canonical_unit(quantity)
    if not unit or unit.strip().lower() == cu.lower():
        return float(value)
    table = _TABLE.get(cu, {})
    key = unit.strip().lower().replace("µ", "u") if "µ" in unit else unit.strip().lower()
    if key not in table:
        raise UnitError(f"cannot convert {unit!r} to {cu!r} for {quantity}; accepted: {sorted(table)}")
    return float(value) * table[key]
