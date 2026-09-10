"""Normalise each mix's components into mass fractions relative to total powder.

Powder (the denominator) = every component whose effective family is
``powder`` (roles binder/scm/filler, or a powder-class material used as an
addition). The normaliser works on ``dosage_reported`` + ``basis_reported``
(the ``dosage_kg_m3`` / ``mass_frac_of_binder`` columns are too sparse to use).

Modes
  abs    powder rows share one absolute mass scale (kg/m3 or per-batch mass)
  rel    powder rows are fractions/percent of binder summing to ~1
  parts  powder rows are relative mass parts (any scale); everything is divided by their sum
  solids powder rows are percent of total solids
  failed cannot be normalised (reason in flags)
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import vocab as V

log = logging.getLogger("pmpredict.composition")

POWDER_GROUPS = V.groups_by_family("powder")
AGG_GROUPS = V.groups_by_family("aggregate")
ADMIX_GROUPS = V.groups_by_family("admixture")
FIBRE_GROUPS = V.groups_by_family("fibre")
ACT_GROUPS = V.groups_by_family("activator")
NANO_GROUPS = V.groups_by_family("nano")

PASTE_DENSITY, MORTAR_DENSITY = 1900.0, 2200.0
_RATIO_UNITS = {"ratio", "dimensionless", "-", "fraction", "ratio_to_binder", "mass_ratio_to_binder",
                "kg/kg binder", "w/b", "w/c", "mass ratio", "by mass ratio", "mass_ratio"}
LIQ_DENSITY = {"water": 1.0, "admixture": 1.05, "activator": 1.40, "sodium_silicate": 1.40, "naoh": 1.30}


@dataclass
class MixComposition:
    mix_uid: str
    mode: str = "failed"
    powder: dict[str, float] = field(default_factory=dict)          # group -> frac of powder
    powder_role_filler: float = 0.0                                 # frac of powder with role filler
    cement_share: float | None = None
    water_b: float | None = None
    water_b_source: str = "none"
    sand_b: float | None = None
    sand_b_source: str = "none"
    agg_share: dict[str, float] = field(default_factory=dict)       # group -> share of total aggregate
    admix_pct: dict[str, float] = field(default_factory=dict)       # group -> % of powder (as dosed)
    admix_solid_pct: dict[str, float] = field(default_factory=dict) # group -> % solids of powder
    fibre_mass_b: dict[str, float] = field(default_factory=dict)    # group -> mass / powder
    fibre_vol_pct: dict[str, float] = field(default_factory=dict)   # group -> vol% of mix
    activator_b: dict[str, float] = field(default_factory=dict)     # group -> mass / powder (as dosed)
    activator_molarity: dict[str, float] = field(default_factory=dict)
    nano_pct: dict[str, float] = field(default_factory=dict)        # group -> % of powder
    other_b: float = 0.0
    flags: list[str] = field(default_factory=list)
    # per-material rows for material-property weighting:
    # dict(material_uid, cls, group, family, frac) where frac = share within its family
    materials_long: list[dict] = field(default_factory=list)

    def flag(self, f: str) -> None:
        if f not in self.flags:
            self.flags.append(f)

    @property
    def ok(self) -> bool:
        return self.mode != "failed"


# ----------------------------------------------------------------- helpers
def _scale_of(basis: str, unit: str) -> tuple[str, float] | None:
    """Return (scale, factor) for an absolute-mass row: scale in {per_m3, batch}."""
    u = (unit or "").strip().lower()
    if basis == "kg_m3":
        if u in {"kg/dm3", "kg/l"}:
            return "per_m3", 1000.0
        if u in {"g/m3"}:
            return "per_m3", 0.001
        return "per_m3", 1.0           # kg/m3, g/L, g/dm3, L/m3(water), lt/m3 ...
    if basis == "L_per_m3":
        return "per_m3", 1.0           # density applied by caller
    if basis == "g_per_batch":
        if u in {"kg", "kg_per_batch", "l"}:
            return "batch", 1000.0
        if u == "mg":
            return "batch", 0.001
        return "batch", 1.0            # g, mL(as g), cm3
    if basis == "kg_per_batch":
        if u in {"lb"}:
            return "batch", 453.6
        if u in {"g", "ml", "ml/batch", "ml_per_batch"}:
            return "batch", 1.0
        return "batch", 1000.0         # kg -> g
    return None


def _num_or_none(x) -> float | None:
    """NaN/NA/None -> None, else float (so `x or default` never sees a truthy NaN)."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_dose(value, raw) -> float | None:
    if value is not None and not (isinstance(value, float) and math.isnan(value)):
        return float(value)
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    m = V.DOSE_RESCUE.match(str(raw))
    return float(m.group(1)) if m else None


def _mix_density(system_type: str | None, fresh_density: float | None) -> float:
    if fresh_density and 1000 < fresh_density < 3500:
        return fresh_density
    return PASTE_DENSITY if system_type == "paste" else MORTAR_DENSITY


# ------------------------------------------------------------ core routine
def normalize_mix(rows: pd.DataFrame, mix_row: pd.Series) -> MixComposition:
    """Normalise one mix. ``rows`` = its mix_components joined with material info."""
    mc = MixComposition(mix_uid=str(mix_row["mix_uid"]))
    if rows.empty:
        mc.flag("no_components")
        return mc

    # ---- 1. per-row preparation: basis inference, dose parse, group/family
    items = []
    for r in rows.itertuples(index=False):
        basis = r.basis_reported if isinstance(r.basis_reported, str) else None
        if basis is None:
            basis = V.infer_basis(r.unit_reported if isinstance(r.unit_reported, str) else None, r.role)
            if basis is None:
                basis = "unknown"
            else:
                mc.flag("basis_inferred")
        dose = _parse_dose(r.dosage_reported, r.dosage_raw)
        gi = V.resolve_group(r.material_class if isinstance(r.material_class, str) else None, r.role)
        fam = gi.family
        if fam == "powder" and r.role not in {"binder", "scm", "filler"}:
            mc.flag("powder_by_class_override")
        items.append(dict(
            material_uid=r.material_uid, role=r.role, cls=r.material_class, group=gi.group, family=fam,
            basis=basis, unit=(r.unit_reported if isinstance(r.unit_reported, str) else ""), dose=dose,
            sg=gi.sg, solid_default=gi.solid_content,
            solid_content=_num_or_none(getattr(r, "solid_content", None)),
            density_solution=_num_or_none(getattr(r, "density_solution", None)),
            is_cement=V.is_cement_class(r.material_class if isinstance(r.material_class, str) else None),
        ))

    # ---- 2. molarity rows -> separate feature; drop from mass processing
    mass_items = []
    for it in items:
        if it["basis"] in V.MOLARITY:
            if it["dose"] is not None:
                mc.activator_molarity[it["group"]] = max(mc.activator_molarity.get(it["group"], 0.0), it["dose"])
            continue
        if it["dose"] is None:
            if it["family"] == "powder":
                mc.flag("failed:unparsed_major_dose")
                return mc
            # a water/aggregate row without a printed dose: fall back to mixes.w_b_reported /
            # sand_binder_ratio downstream instead of failing the whole mix
            mc.flag(f"dropped_unparsed_{it['family']}" if it["family"] in {"water", "aggregate"}
                    else "dropped_unparsed_minor")
            continue
        if it["basis"] == "unknown":
            if it["family"] in {"powder", "water", "aggregate"}:
                mc.flag("failed:unknown_basis_major")
                return mc
            mc.flag("dropped_unknown_basis_minor")
            continue
        mass_items.append(it)

    # duplicate material rows: same basis -> sum; different bases -> keep the first in priority order
    by_mat: dict[str, list[dict]] = defaultdict(list)
    for it in mass_items:
        by_mat[it["material_uid"]].append(it)
    dedup = []
    prio = [V.ABS_MASS, V.PARTS, V.REL_B_PCT | V.REL_B_RAT, V.REL_C_PCT | V.REL_C_RAT]
    for mat, lst in by_mat.items():
        if len(lst) == 1:
            dedup.append(lst[0]); continue
        bases = {x["basis"] for x in lst}
        if len(bases) == 1:
            merged = dict(lst[0]); merged["dose"] = sum(x["dose"] for x in lst)
            dedup.append(merged); mc.flag("dup_material_summed")
        else:
            chosen = None
            for p in prio:
                cand = [x for x in lst if x["basis"] in p]
                if cand:
                    chosen = cand[0]; break
            dedup.append(chosen or lst[0]); mc.flag("dup_material_conflict")
    items = dedup

    P = [it for it in items if it["family"] == "powder"]
    if not P:
        mc.flag("failed:no_powder")
        return mc

    # ---- 3. resolve powder rows to one relative scale
    def cat(b):
        if b in V.ABS_MASS or b in V.LIQ_VOL: return "abs"
        if b in V.PARTS: return "parts"
        if b in V.REL_B_PCT or b in V.REL_B_RAT: return "relb"
        if b in V.REL_C_PCT or b in V.REL_C_RAT: return "relc"
        if b in V.REL_SOLIDS_PCT or b in V.REL_SOLIDS_RAT: return "solids"
        if b in V.VOLUME: return "vol"
        return "other"

    cats = [cat(it["basis"]) for it in P]
    for it, c in zip(P, cats):
        it["cat"] = c
    primary = None
    for c in ("abs", "parts", "relb", "solids", "vol", "relc"):
        if c in cats:
            primary = c; break
    if primary is None:
        mc.flag("failed:powder_basis_unusable")
        return mc
    if primary == "relc":
        # every powder row is expressed relative to cement (cement itself = 100 % / 1.0):
        # treat the values as relative mass parts
        mc.flag("relc_primary")

    # value of a powder row in "primary units"
    abs_scale = None
    prim_vals: dict[int, float] = {}
    for i, it in enumerate(P):
        if it["cat"] != primary:
            continue
        if primary == "abs":
            sc = _scale_of(it["basis"], it["unit"])
            if sc is None:
                mc.flag("failed:abs_unit"); return mc
            if abs_scale is None:
                abs_scale = sc[0]
            elif sc[0] != abs_scale:
                mc.flag("failed:mixed_abs_scale"); return mc
            v = it["dose"] * sc[1]
            if it["basis"] in V.LIQ_VOL:
                v *= it.get("density_solution") or 1.0
            prim_vals[i] = v
        elif primary == "relb":
            prim_vals[i] = it["dose"] / 100.0 if it["basis"] in V.REL_B_PCT else it["dose"]
        elif primary == "relc":
            prim_vals[i] = it["dose"] / 100.0 if it["basis"] in V.REL_C_PCT else it["dose"]
        elif primary == "vol":
            prim_vals[i] = it["dose"] * it["sg"]          # volume parts -> mass parts
            mc.flag("volume_converted")
        else:  # parts, solids
            prim_vals[i] = it["dose"]
    B0 = sum(prim_vals.values())
    C0 = sum(v for i, v in prim_vals.items() if P[i]["is_cement"])
    if B0 <= 0:
        mc.flag("failed:zero_powder"); return mc

    # secondary powder rows (relative to binder or cement)
    for i, it in enumerate(P):
        if i in prim_vals:
            continue
        c = it["cat"]
        frac = it["dose"] / 100.0 if it["basis"] in (V.REL_B_PCT | V.REL_C_PCT) else it["dose"]
        if c == "relb":
            prim_vals[i] = frac * B0; mc.flag("mixed_powder_basis_resolved")
        elif c == "relc":
            if C0 <= 0:
                mc.flag("failed:rel_to_cement_without_cement"); return mc
            prim_vals[i] = frac * C0; mc.flag("mixed_powder_basis_resolved")
        elif c == "vol" and primary in {"parts", "relb"}:
            prim_vals[i] = it["dose"] * it["sg"]; mc.flag("volume_converted")
        else:
            mc.flag("failed:mixed_powder_basis"); return mc
    B = sum(prim_vals.values())
    if primary == "relb":
        S = sum(v for i, v in prim_vals.items() if P[i]["cat"] == "relb")
        if abs(S - 1.0) <= 0.05 and len(prim_vals) == sum(1 for c in cats if c == "relb"):
            mc.mode = "rel"
        else:
            mc.mode = "parts"; mc.flag("binder_sum_deviates")
    elif primary == "abs":
        mc.mode = "abs"
    elif primary == "solids":
        mc.mode = "solids"
    else:
        mc.mode = "parts"

    # powder fractions
    for i, v in prim_vals.items():
        g = P[i]["group"]
        mc.powder[g] = mc.powder.get(g, 0.0) + v / B
        mc.materials_long.append(dict(material_uid=P[i]["material_uid"], cls=P[i]["cls"], group=g,
                                      family="powder", role=P[i]["role"], frac=v / B))
    mc.powder_role_filler = sum(v for i, v in prim_vals.items() if P[i]["role"] == "filler") / B
    mc.cement_share = C0 / B if C0 > 0 else None
    if mc.cement_share is None:
        # no cement class present: cement_share proxy = binder-role powder share
        cs = sum(v for i, v in prim_vals.items() if P[i]["role"] == "binder") / B
        mc.cement_share = cs
        mc.flag("cement_share_proxy")
    P_pct_sum = B if primary == "solids" else None

    # ---- 4. non-powder rows -> mass / powder
    def to_mass_b(it) -> float | None:
        b, u = it["basis"], it["unit"]
        if b in V.ABS_MASS or b in V.LIQ_VOL:
            if mc.mode != "abs":
                return None
            sc = _scale_of(b, u)
            if sc is None or sc[0] != abs_scale:
                return None
            v = it["dose"] * sc[1]
            if b in V.LIQ_VOL or (u or "").lower() in {"ml", "l", "l/m3", "lt/m3", "ml/batch", "ml_per_batch"}:
                dens = it.get("density_solution") or LIQ_DENSITY.get(it["group"], LIQ_DENSITY.get(it["family"], 1.0))
                v *= dens
                mc.flag("liquid_volume_to_mass")
            return v / B
        if b in V.REL_B_PCT:
            return it["dose"] / 100.0
        if b in V.REL_B_RAT:
            return it["dose"]
        if b in V.REL_C_PCT:
            return it["dose"] / 100.0 * mc.cement_share
        if b in V.REL_C_RAT:
            return it["dose"] * mc.cement_share
        if b in V.PARTS:
            if mc.mode not in {"parts", "rel", "solids"}:
                return None
            ul = (u or "").strip().lower()
            # 'mass_parts' rows printed as a ratio (w/b 0.5, s/b 3) next to percent-parts powder
            # (cement 100 pct): treat ratio-unit rows, or tiny values against a >=20-part powder
            # sum, as ratios to binder rather than parts.
            if ul in _RATIO_UNITS or (B >= 20 and it["dose"] < 5 and it["family"] in {"water", "aggregate"}):
                mc.flag("parts_ratio_reinterpreted")
                return it["dose"]
            return it["dose"] / B
        if b in V.REL_SOLIDS_PCT:
            return it["dose"] / P_pct_sum if P_pct_sum else None
        if b in V.REL_SOLIDS_RAT:
            # liquid / total solids; total solids = 100 % in solids mode
            return it["dose"] * 100.0 / P_pct_sum if P_pct_sum else None
        return None

    water_sum, water_ok = 0.0, False
    agg_mass: dict[str, float] = {}
    agg_pct: dict[str, float] = {}
    agg_items: list[tuple[dict, float]] = []     # (item, mass or share) for per-material weighting
    fib_items: list[tuple[dict, float]] = []
    for it in items:
        fam, g = it["family"], it["group"]
        if fam == "powder":
            continue
        b = it["basis"]
        if fam == "water":
            m = to_mass_b(it)
            if m is None:
                mc.flag("water_row_unconverted"); continue
            water_sum += m; water_ok = True
        elif fam == "aggregate":
            if b in V.REL_AGG:
                agg_pct[g] = agg_pct.get(g, 0.0) + it["dose"] / 100.0; mc.flag("agg_pct_rows")
                agg_items.append((it, it["dose"] / 100.0))
            elif b in V.VOLUME:
                mc.flag("agg_volume_row_unconverted")
            else:
                m = to_mass_b(it)
                if m is None:
                    mc.flag("agg_row_unconverted"); continue
                agg_mass[g] = agg_mass.get(g, 0.0) + m
                agg_items.append((it, m))
        elif fam == "admixture":
            if b in V.ADMIX_SOL:
                mc.admix_solid_pct[g] = mc.admix_solid_pct.get(g, 0.0) + it["dose"]
                mc.admix_pct[g] = mc.admix_pct.get(g, 0.0) + it["dose"]
            elif b in V.ADMIX_LIQ:
                mc.admix_pct[g] = mc.admix_pct.get(g, 0.0) + it["dose"]
                sc_ = it.get("solid_content") or it["solid_default"] or 100.0
                mc.admix_solid_pct[g] = mc.admix_solid_pct.get(g, 0.0) + it["dose"] * sc_ / 100.0
            elif b in V.VOLUME:
                mc.flag("admix_volume_row_dropped")
            else:
                m = to_mass_b(it)
                if m is None:
                    mc.flag("admix_row_unconverted"); continue
                pct = 100.0 * m
                mc.admix_pct[g] = mc.admix_pct.get(g, 0.0) + pct
                sc_ = it.get("solid_content")
                if sc_ is None:
                    sc_ = it["solid_default"] or 100.0
                    if it["solid_default"] is not None and it["solid_default"] < 100:
                        mc.flag("sp_solid_default")
                mc.admix_solid_pct[g] = mc.admix_solid_pct.get(g, 0.0) + pct * sc_ / 100.0
        elif fam == "fibre":
            if b in V.VOLUME:
                mc.fibre_vol_pct[g] = mc.fibre_vol_pct.get(g, 0.0) + it["dose"]
                fib_items.append((it, it["dose"] * it["sg"]))      # vol% * sg ~ relative mass
            else:
                m = to_mass_b(it)
                if m is None:
                    mc.flag("fibre_row_unconverted"); continue
                mc.fibre_mass_b[g] = mc.fibre_mass_b.get(g, 0.0) + m
                fib_items.append((it, m))
        elif fam == "activator":
            if b in V.VOLUME:
                mc.flag("activator_volume_row_dropped"); continue
            m = to_mass_b(it)
            if m is None:
                mc.flag("activator_row_unconverted"); continue
            mc.activator_b[g] = mc.activator_b.get(g, 0.0) + m
            # activators are stored with frac = mass / powder (not a share) for activator-chemistry features
            mc.materials_long.append(dict(material_uid=it["material_uid"], cls=it["cls"], group=g,
                                          family="activator", role=it["role"], frac=m))
        elif fam == "nano":
            m = to_mass_b(it)
            if m is None:
                mc.flag("nano_row_unconverted"); continue
            mc.nano_pct[g] = mc.nano_pct.get(g, 0.0) + 100.0 * m
        else:
            m = to_mass_b(it)
            if m is not None:
                mc.other_b += m
            else:
                mc.flag("other_row_unconverted")

    # ---- 5. water / sand with fallbacks
    wb_rep = mix_row.get("w_b_reported")
    wb_rep = float(wb_rep) if wb_rep is not None and not pd.isna(wb_rep) else None
    if water_ok and water_sum > 0:
        mc.water_b, mc.water_b_source = water_sum, "computed"
        if wb_rep is not None and abs(water_sum - wb_rep) > 0.05:
            mc.flag("wb_disagree")
    elif wb_rep is not None:
        mc.water_b, mc.water_b_source = wb_rep, "reported"
    else:
        mc.flag("no_water")

    sb_rep = mix_row.get("sand_binder_ratio")
    sb_rep = float(sb_rep) if sb_rep is not None and not pd.isna(sb_rep) else None
    sb_basis = mix_row.get("sand_binder_basis")
    if agg_mass:
        mc.sand_b, mc.sand_b_source = sum(agg_mass.values()), "computed"
        tot = mc.sand_b
        mc.agg_share = {g: m / tot for g, m in agg_mass.items()}
        if sb_rep is not None and sb_rep > 0 and abs(mc.sand_b - sb_rep) / sb_rep > 0.05:
            mc.flag("sb_disagree")
    elif sb_rep is not None and (sb_basis is None or pd.isna(sb_basis) or sb_basis == "mass"):
        mc.sand_b, mc.sand_b_source = sb_rep, "reported"
        if agg_pct:
            s = sum(agg_pct.values()) or 1.0
            mc.agg_share = {g: v / s for g, v in agg_pct.items()}
    elif agg_pct:
        s = sum(agg_pct.values()) or 1.0
        mc.agg_share = {g: v / s for g, v in agg_pct.items()}
        mc.flag("agg_share_only")
    if mix_row.get("system_type") == "mortar" and mc.sand_b is None:
        mc.flag("mortar_without_sand")

    # ---- 6. fibre mass <-> volume cross-conversion
    if mc.fibre_mass_b or mc.fibre_vol_pct:
        rho_mix = _mix_density(mix_row.get("system_type"), mix_row.get("fresh_density_kg_m3"))
        btot = mix_row.get("binder_total_kg_m3")
        if btot is None or pd.isna(btot) or not (100 < float(btot) < 2500):
            denom = 1.0 + (mc.water_b or 0.0) + (mc.sand_b or 0.0) + sum(mc.fibre_mass_b.values()) \
                + sum(mc.activator_b.values())
            btot = rho_mix / denom
            mc.flag("fibre_converted_default_density")
        btot = float(btot)
        for g, m in list(mc.fibre_mass_b.items()):
            if g not in mc.fibre_vol_pct:
                sg = V.group_defaults()[g].sg
                mc.fibre_vol_pct[g] = m * btot / (sg * 1000.0) * 100.0
        for g, v in list(mc.fibre_vol_pct.items()):
            if g not in mc.fibre_mass_b:
                sg = V.group_defaults()[g].sg
                mc.fibre_mass_b[g] = v / 100.0 * sg * 1000.0 / btot

    if mc.activator_molarity and not mc.activator_b:
        mc.flag("activator_solution_only")

    # per-material shares within aggregate / fibre families
    for lst, fam in ((agg_items, "aggregate"), (fib_items, "fibre")):
        tot = sum(m for _, m in lst)
        if tot > 0:
            for it, m in lst:
                mc.materials_long.append(dict(material_uid=it["material_uid"], cls=it["cls"], group=it["group"],
                                              family=fam, role=it["role"], frac=m / tot))
    return mc


# --------------------------------------------------------------- batch API
def _material_props(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per-material solid_content (%) and density_solution (g/cm3) from material_physical."""
    ph = tables["material_physical"]
    ph = ph[ph["property"].isin(["solid_content", "density_solution"])].copy()
    ph["val"] = [V.convert_phys(p, v, u) for p, v, u in zip(ph["property"], ph["value_reported"], ph["unit_reported"])]
    ph = ph.dropna(subset=["val"])
    wide = ph.pivot_table(index="material_uid", columns="property", values="val", aggfunc="median")
    return wide.reset_index()


def compose_all(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Normalise every mix. Returns (composition wide table, QA table, per-material long table)."""
    mixes = tables["mixes"].drop_duplicates("mix_uid")          # master.db carries a few duplicated mix rows
    mc = tables["mix_components"].drop_duplicates(
        ["mix_uid", "material_uid", "role", "dosage_reported", "unit_reported", "basis_reported"]).merge(
        tables["materials"][["material_uid", "material_class"]], on="material_uid", how="left")
    mc = mc.merge(_material_props(tables), on="material_uid", how="left")
    if "dosage_raw" not in mc.columns:
        mc["dosage_raw"] = pd.NA
    for c in ("solid_content", "density_solution"):
        if c not in mc.columns:
            mc[c] = np.nan
    groups = {k: g for k, g in mc.groupby("mix_uid", sort=False)}
    empty = mc.iloc[0:0]

    recs, qa, long = [], [], []
    for row in mixes.itertuples(index=False):
        r = row._asdict()
        comp = normalize_mix(groups.get(r["mix_uid"], empty), pd.Series(r))
        qa.append(dict(mix_uid=r["mix_uid"], paper_uid=r["paper_uid"], mode=comp.mode,
                       water_b_source=comp.water_b_source, sand_b_source=comp.sand_b_source,
                       n_flags=len(comp.flags), flags=";".join(comp.flags)))
        if not comp.ok:
            continue
        recs.append(_to_record(comp, r))
        for m in comp.materials_long:
            long.append({"mix_uid": comp.mix_uid, **m})
    wide = pd.DataFrame(recs)
    qa_df = pd.DataFrame(qa)
    long_df = pd.DataFrame(long)
    log.info("composition: %d / %d mixes normalised", len(wide), len(mixes))
    return wide, qa_df, long_df


def _to_record(c: MixComposition, r: dict) -> dict:
    rec = dict(mix_uid=c.mix_uid, paper_uid=r["paper_uid"], system_type=r.get("system_type"), mode=c.mode,
               cement_share=c.cement_share, filler_frac=c.powder_role_filler,
               water_b=c.water_b, water_b_source=c.water_b_source,
               sand_b=c.sand_b, sand_b_source=c.sand_b_source, other_frac=c.other_b,
               flags=";".join(c.flags))
    for g in POWDER_GROUPS:
        rec[f"pw_{g}"] = c.powder.get(g, 0.0)
    for g in AGG_GROUPS:
        rec[f"agg_{g}"] = c.agg_share.get(g, 0.0)
    for g in ADMIX_GROUPS:
        rec[f"adx_{g}_pct"] = c.admix_pct.get(g, 0.0)
    rec["sp_solid_pct"] = c.admix_solid_pct.get("sp_pce", 0.0) + c.admix_solid_pct.get("sp_other", 0.0)
    rec["vma_solid_pct"] = c.admix_solid_pct.get("vma", 0.0) + c.admix_solid_pct.get("clay_modifier", 0.0)
    for g in FIBRE_GROUPS:
        rec[f"fib_{g}_vol"] = c.fibre_vol_pct.get(g, 0.0)
    rec["fibre_total_vol_pct"] = sum(c.fibre_vol_pct.values())
    rec["fibre_total_mass_b"] = sum(c.fibre_mass_b.values())
    for g in ACT_GROUPS:
        rec[f"act_{g}"] = c.activator_b.get(g, 0.0)
    rec["act_total_b"] = sum(c.activator_b.values())
    rec["naoh_molarity"] = c.activator_molarity.get("naoh", c.activator_molarity.get("koh", 0.0))
    for g in NANO_GROUPS:
        rec[f"nano_{g}_pct"] = c.nano_pct.get(g, 0.0)
    rec["nano_total_pct"] = sum(c.nano_pct.values())
    return rec
