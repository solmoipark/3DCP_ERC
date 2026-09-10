"""Rebuild a ``MixSpec`` from a normalised DB mix (used by parity / closed-loop tests
and by literature retrieval to present published mixes in the shared schema)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import vocab as V
from .composition import ACT_GROUPS, ADMIX_GROUPS, FIBRE_GROUPS, NANO_GROUPS
from .features import OX, PHYS_AGG, PHYS_FIB, PHYS_POWDER
from .schema import Component, Conditions, MixSpec

# representative material_class per group (first class listed for the group in material_groups.yaml)
_REP: dict[str, str] = {}
for cls, g in V.class_to_group().items():
    if g and g not in _REP:
        _REP[g] = cls


def representative_class(group: str) -> str:
    return _REP.get(group, "other")


def _props_for(material_uid: str, mat_ox: pd.DataFrame | None, mat_phys: pd.DataFrame | None) -> dict:
    props: dict = {}
    if mat_ox is not None:
        r = mat_ox[mat_ox["material_uid"] == material_uid]
        if len(r) and bool(r["chem_ok"].iloc[0]):
            ox = {o: float(r[o].iloc[0]) for o in OX if o in r.columns and pd.notna(r[o].iloc[0])}
            if ox:
                props["oxides"] = ox
    if mat_phys is not None:
        r = mat_phys[mat_phys["material_uid"] == material_uid]
        if len(r):
            for c in PHYS_POWDER + PHYS_AGG + PHYS_FIB + ["solid_content_pct"]:
                if c in r.columns and pd.notna(r[c].iloc[0]):
                    props[c] = float(r[c].iloc[0])
    return props


def spec_from_db(mix_uid: str, comp_wide: pd.DataFrame, comp_long: pd.DataFrame, ctx: pd.DataFrame,
                 mat_ox: pd.DataFrame | None = None, mat_phys: pd.DataFrame | None = None,
                 conditions: Conditions | None = None) -> MixSpec:
    """Material-level reconstruction; group-level dosages (admixtures, fibres, activators, nano)
    use a representative class per group."""
    w = comp_wide[comp_wide["mix_uid"] == mix_uid]
    if w.empty:
        raise KeyError(mix_uid)
    w = w.iloc[0]
    L = comp_long[comp_long["mix_uid"] == mix_uid]
    comps: list[Component] = []
    has_role = "role" in L.columns
    for r in L[L["family"] == "powder"].itertuples(index=False):
        cls = r.cls if isinstance(r.cls, str) else "other"
        if has_role and isinstance(r.role, str):
            role = r.role
        else:
            gi = V.resolve_group(cls, None)
            role = "binder" if V.is_cement_class(cls) or cls == "other" else (
                "filler" if gi.group in {"limestone_powder", "quartz_powder", "inert_filler_other"} else "scm")
        comps.append(Component(material_class=cls, amount=float(r.frac), role=role,
                               props=_props_for(r.material_uid, mat_ox, mat_phys)))
    sand_b = w["sand_b"]
    sand_binder = None
    if pd.notna(sand_b) and sand_b > 0:
        agg = L[L["family"] == "aggregate"]
        if len(agg):
            for r in agg.itertuples(index=False):
                cls = r.cls if isinstance(r.cls, str) else "other"
                role = r.role if has_role and isinstance(r.role, str) else "fine_aggregate"
                comps.append(Component(material_class=cls, amount=float(sand_b * r.frac), role=role,
                                       props=_props_for(r.material_uid, mat_ox, mat_phys)))
        else:
            sand_binder = float(sand_b)        # identity unknown: carry the ratio only
    for g in ADMIX_GROUPS:
        pct = w.get(f"adx_{g}_pct", 0.0)
        if pct and pct > 0:
            comps.append(Component(material_class=representative_class(g), amount=float(pct) / 100.0, role="admixture"))
    fib = L[L["family"] == "fibre"]
    for g in FIBRE_GROUPS:
        vol = w.get(f"fib_{g}_vol", 0.0)
        if vol and vol > 0:
            cls = representative_class(g)
            sub = fib[fib["group"] == g]
            props = _props_for(sub["material_uid"].iloc[0], mat_ox, mat_phys) if len(sub) else {}
            if len(sub) and isinstance(sub["cls"].iloc[0], str):
                cls = sub["cls"].iloc[0]
            comps.append(Component(material_class=cls, vol_pct=float(vol), role="fibre", props=props))
    mol_used = False
    for g in ACT_GROUPS:
        m = w.get(f"act_{g}", 0.0)
        if m and m > 0:
            mol = None
            if g in {"naoh", "koh"} and w.get("naoh_molarity", 0) > 0 and not mol_used:
                mol, mol_used = float(w["naoh_molarity"]), True
            comps.append(Component(material_class=representative_class(g), amount=float(m), role="activator", molarity=mol))
    if w.get("naoh_molarity", 0) > 0 and not mol_used:   # molarity-only activator row in the paper
        comps.append(Component(material_class="sodium_hydroxide", molarity=float(w["naoh_molarity"]), role="activator"))
    for g in NANO_GROUPS:
        pct = w.get(f"nano_{g}_pct", 0.0)
        if pct and pct > 0:
            comps.append(Component(material_class=representative_class(g), amount=float(pct) / 100.0, role="nanomaterial"))
    c = ctx[ctx["mix_uid"] == mix_uid].iloc[0] if (ctx["mix_uid"] == mix_uid).any() else None
    cond = conditions or Conditions()
    if c is not None:
        cond.curing_regime = c["curing_regime"] if isinstance(c["curing_regime"], str) else None
        cond.curing_temp_C = None if pd.isna(c["curing_temp_C"]) else float(c["curing_temp_C"])
        cond.curing_rh_pct = None if pd.isna(c["curing_rh_pct"]) else float(c["curing_rh_pct"])
        cond.is_3dcp = int(c["is_3dcp"]) if pd.notna(c["is_3dcp"]) else 0
    spec = MixSpec(system_type=str(w["system_type"]), components=comps,
                   water_binder=None if pd.isna(w["water_b"]) else float(w["water_b"]),
                   sand_binder=sand_binder, conditions=cond,
                   name=mix_uid, year=(None if c is None or pd.isna(c["year"]) else int(c["year"])))
    return spec


def composition_summary(w: pd.Series, max_items: int = 4) -> str:
    """Short human-readable string: 'OPC 0.70 / FA-F 0.30; w/b 0.35; s/b 1.5; sp_pce 0.8%'."""
    from .composition import POWDER_GROUPS
    parts = sorted(((g, w.get(f"pw_{g}", 0.0)) for g in POWDER_GROUPS), key=lambda x: -x[1])
    s = " / ".join(f"{g} {v:.2f}" for g, v in parts[:max_items] if v > 0.005)
    if pd.notna(w.get("water_b")):
        s += f"; w/b {w['water_b']:.2f}"
    if pd.notna(w.get("sand_b")) and w.get("sand_b", 0) > 0:
        s += f"; s/b {w['sand_b']:.2f}"
    adm = [(g, w.get(f"adx_{g}_pct", 0.0)) for g in ADMIX_GROUPS if w.get(f"adx_{g}_pct", 0.0) > 0]
    if adm:
        s += "; " + ", ".join(f"{g} {v:.2f}%" for g, v in adm[:3])
    if w.get("fibre_total_vol_pct", 0) > 0:
        s += f"; fibre {w['fibre_total_vol_pct']:.2f} vol%"
    if w.get("act_total_b", 0) > 0:
        s += f"; activator {w['act_total_b']:.2f}/b"
    return s
