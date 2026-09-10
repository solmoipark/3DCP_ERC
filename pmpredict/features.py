"""Feature construction shared by training (DB path) and prediction (MixSpec path).

``featurize_frame`` is the single entry point. Both paths feed it the same
inputs: a composition wide table (from ``composition``), the per-material long
table, per-material oxide / physical property tables, a mix-context table and
the class-median table used for imputation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import vocab as V
from .composition import ADMIX_GROUPS, AGG_GROUPS, FIBRE_GROUPS, ACT_GROUPS, NANO_GROUPS, POWDER_GROUPS

log = logging.getLogger("pmpredict.features")

FEATURIZER_VERSION = "1.0"
OX = ["SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3", "K2O", "Na2O", "TiO2", "P2O5", "LOI"]
PHYS_POWDER = ["blaine_m2kg", "d50_um", "sg", "bet_m2g"]
PHYS_AGG = ["agg_fm", "agg_dmax_mm", "agg_wabs_pct", "agg_sg"]
PHYS_FIB = ["fibre_length_mm", "fibre_diameter_um", "fibre_tensile_MPa", "fibre_emod_GPa"]
CURING_TYPES = ["water", "moist", "sealed", "ambient", "heat", "autoclave", "unknown"]
MIXER_TYPES = ["hobart", "planetary", "mortar_standard", "high_shear", "hand", "pan_drum", "other", "unknown"]


def classify_mixer(text) -> str:
    """Map the free-text mixer_type of mixing_protocols to a small vocabulary."""
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    s = text.lower()
    if re.search(r"not (stated|reported|specified)|unspecified|n/?a\b|unknown", s) and not re.search(r"hobart|planetary|mortar", s):
        return "unknown"
    if "hobart" in s:
        return "hobart"
    if re.search(r"high[- ]?shear|high[- ]?speed|dispers|blender|vortex|shear mixer|colloidal|ultrason", s):
        return "high_shear"
    if "planetary" in s:
        return "planetary"
    if re.search(r"mortar mixer|astm c305|en ?196|jgj|paddle|standard mixer|cement paste mixer|net slurry|jc/t ?729", s):
        return "mortar_standard"
    if re.search(r"hand|manual", s):
        return "hand"
    if re.search(r"pan|drum|concrete mixer|tilting|rotating", s):
        return "pan_drum"
    return "other"
BINDER_FAMILIES = ["opc", "blended", "lc3", "aam", "csa", "cac", "mgo", "sulfate", "other_binder"]
SYSTEM_TYPES = ["paste", "mortar", "unknown"]
CATEGORICALS = {"system_type": SYSTEM_TYPES, "curing_type": CURING_TYPES, "binder_family": BINDER_FAMILIES}
MIN_CLASS_N = 5


# --------------------------------------------------------- material tables
def build_material_oxides(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per material with canonical oxide mass-% columns and a validity flag."""
    ch = tables["material_chemistry"]
    ch = ch[ch["basis"].isna() | ch["basis"].isin(["oxide_mass_pct"])].copy()
    norm = [V.normalize_component(c) for c in ch["component"]]
    ch["ox"] = [n[0] if n else None for n in norm]
    ch["fac"] = [n[1] if n else np.nan for n in norm]
    ch = ch.dropna(subset=["ox"])
    ch["val"] = ch["value_reported_pct"] * ch["fac"]
    ch = ch[(ch["val"] >= 0) & (ch["val"] <= 100)]
    wide = ch.pivot_table(index="material_uid", columns="ox", values="val", aggfunc="median")
    for c in OX + ["na2o_eq", "MnO", "Cl"]:
        if c not in wide.columns:
            wide[c] = np.nan
    wide = wide.reset_index()
    mats = tables["materials"][["material_uid", "material_class", "chemistry_status"]]
    wide = wide.merge(mats, on="material_uid", how="left")
    major = wide[OX].sum(axis=1, min_count=1)
    wide["chem_ok"] = ((major >= 70) & (major <= 105)) | (wide["chemistry_status"] == "accepted")
    wide.loc[wide[["SiO2", "CaO", "Al2O3"]].isna().all(axis=1), "chem_ok"] = False
    return wide


def build_material_phys(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per material with harmonised physical properties."""
    ph = tables["material_physical"].copy()
    ph["val"] = [V.convert_phys(p, v, u) for p, v, u in zip(ph["property"], ph["value_reported"], ph["unit_reported"])]
    ph = ph.dropna(subset=["val"])
    wide = ph.pivot_table(index="material_uid", columns="property", values="val", aggfunc="median").reset_index()
    out = pd.DataFrame({"material_uid": wide["material_uid"]})
    g = lambda c: wide[c] if c in wide.columns else pd.Series(np.nan, index=wide.index)
    out["blaine_m2kg"] = g("blaine_fineness")
    out["d50_um"] = g("d50").fillna(g("mean_particle_size"))
    out["sg"] = g("specific_gravity").fillna(g("particle_density"))
    out["bet_m2g"] = g("bet_surface_area")
    out["agg_fm"] = g("fineness_modulus")
    out["agg_dmax_mm"] = g("dmax")
    out["agg_wabs_pct"] = g("water_absorption_aggregate")
    out["agg_sg"] = out["sg"]
    out["fibre_length_mm"] = g("fibre_length")
    out["fibre_diameter_um"] = g("fibre_diameter")
    out["fibre_tensile_MPa"] = g("tensile_strength_fibre")
    out["fibre_emod_GPa"] = g("elastic_modulus_fibre")
    out["solid_content_pct"] = g("solid_content")
    out["silica_modulus"] = g("silica_modulus")
    out["density_solution"] = g("density_solution")
    return out.merge(tables["materials"][["material_uid", "material_class"]], on="material_uid", how="left")


def build_class_medians(mat_ox: pd.DataFrame, mat_phys: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Per material_class medians of oxides and physical properties (>= MIN_CLASS_N materials)."""
    med: dict[str, dict[str, float]] = {}
    ox = mat_ox[mat_ox["chem_ok"]]
    for cls, grp in ox.groupby("material_class"):
        if len(grp) >= MIN_CLASS_N:
            d = grp[OX].median().dropna().to_dict()
            if d:
                med.setdefault(cls, {}).update({f"ox_{k}": float(v) for k, v in d.items()})
    for cls, grp in mat_phys.groupby("material_class"):
        for c in PHYS_POWDER + PHYS_AGG + PHYS_FIB:
            s = grp[c].dropna()
            if len(s) >= MIN_CLASS_N:
                med.setdefault(cls, {})[c] = float(s.median())
    return med


# -------------------------------------------------------------- curing parse
_TEMP_RE = re.compile(r"(-?\d{1,3}(?:\.\d)?)\s*(?:±\s*\d+(?:\.\d)?\s*)?(?:°|º|deg\.?|degrees?)?\s*C\b", re.I)
_RH_RE = re.compile(r"(?:RH|R\.H\.|relative humidity)\s*(?:of|=|:|≥|>=|>|~|≈|at)?\s*(\d{2,3})|(\d{2,3})\s*(?:±\s*\d+\s*)?%\s*(?:RH|R\.H\.|relative humidity)", re.I)


def parse_curing(regime: str | None, temp: float | None, rh: float | None) -> tuple[float, float, str]:
    """Return (curing_temp_C, curing_rh_pct, curing_type) with regex fallbacks on the regime text."""
    regime = regime if isinstance(regime, str) else ""
    txt = regime.lower()
    if temp is None or pd.isna(temp):
        temps = [float(m.group(1)) for m in _TEMP_RE.finditer(regime)]
        temps = [t for t in temps if -20 <= t <= 300]
        temp = max(temps) if temps else np.nan
    if rh is None or pd.isna(rh):
        m = _RH_RE.search(regime)
        rh = float(m.group(1) or m.group(2)) if m else np.nan
        if not (0 <= rh <= 100):
            rh = np.nan
    ctype = "unknown"
    if "autoclave" in txt:
        ctype = "autoclave"
    elif re.search(r"steam|oven|elevated temp|heat[- ]cur|thermal cur", txt) or (not pd.isna(temp) and temp >= 40):
        ctype = "heat"
    elif re.search(r"water[- ]?(cur|bath|tank|immers|storage)|immersed|submerged|lime[- ]saturated|saturated lime|in water|under water", txt):
        ctype = "water"
        if pd.isna(rh):
            rh = 100.0
    elif re.search(r"moist|fog|humid|curing (room|chamber|cabinet)|standard cur|rh\s*[≥>=]*\s*9\d|9\d\s*%\s*rh", txt):
        ctype = "moist"
    elif re.search(r"seal|foil|wrapped|plastic (bag|film|sheet)|cling|covered", txt):
        ctype = "sealed"
    elif re.search(r"ambient|air[- ]cur|room|laborator|lab\b|indoor|natural", txt):
        ctype = "ambient"
    elif not pd.isna(rh):
        ctype = "moist" if rh >= 90 else "ambient"
    return temp, rh, ctype


# ------------------------------------------------------------- binder family
def binder_family(row: pd.Series) -> str:
    cs = row.get("cement_share")
    cs = 0.0 if cs is None or pd.isna(cs) else float(cs)
    if row.get("act_total_b", 0) >= 0.02 and cs < 0.3:
        return "aam"
    if row.get("pw_csa", 0) >= 0.5:
        return "csa"
    if row.get("pw_cac", 0) >= 0.5:
        return "cac"
    if row.get("pw_magnesia", 0) >= 0.4:
        return "mgo"
    if row.get("pw_gypsum_sulfate", 0) >= 0.5:
        return "sulfate"
    if row.get("pw_opc", 0) + row.get("pw_cement_other", 0) < 0.05:
        return "aam" if row.get("act_total_b", 0) > 0 or row.get("naoh_molarity", 0) > 0 else "other_binder"
    if 1.0 - cs < 0.10:
        return "opc"
    if row.get("pw_calcined_clay", 0) + row.get("pw_metakaolin", 0) >= 0.15 and row.get("pw_limestone_powder", 0) >= 0.10:
        return "lc3"
    return "blended"


# --------------------------------------------------------------- weighting
def _weighted_props(long: pd.DataFrame, props: pd.DataFrame, cols: list[str], family: str,
                    class_medians: dict, prefix: str = "") -> pd.DataFrame:
    """Share-weighted material properties per mix with class-median imputation.

    Returns columns ``<prefix><col>`` plus ``<prefix>coverage`` (share with a measured value for
    the first col) and ``<prefix>imputed_frac``.
    """
    sub = long[long["family"] == family].merge(props[["material_uid"] + cols], on="material_uid", how="left")
    if sub.empty:
        return pd.DataFrame(columns=["mix_uid"] + [prefix + c for c in cols] + [prefix + "coverage", prefix + "imputed_frac"])
    med_rows = []
    for cls in sub["cls"].unique():
        m = class_medians.get(cls if isinstance(cls, str) else "", {})
        med_rows.append({"cls": cls, **{f"__med_{c}": m.get(c if not c.startswith("ox_") else c, np.nan) for c in cols}})
    sub = sub.merge(pd.DataFrame(med_rows), on="cls", how="left")
    out = {"mix_uid": sub["mix_uid"]}
    frac = pd.to_numeric(sub["frac"], errors="coerce").fillna(0.0)
    first = pd.to_numeric(sub[cols[0]], errors="coerce")
    first_med = pd.to_numeric(sub[f"__med_{cols[0]}"], errors="coerce")
    known_w = frac.where(first.notna(), 0.0)
    imput_w = frac.where(first.isna() & first_med.notna(), 0.0)
    for c in cols:
        v = pd.to_numeric(sub[c], errors="coerce").fillna(pd.to_numeric(sub[f"__med_{c}"], errors="coerce"))
        w = frac.where(v.notna(), 0.0)
        out[prefix + c + "__num"] = (v.fillna(0.0) * w).astype(float)
        out[prefix + c + "__den"] = w.astype(float)
    df = pd.DataFrame(out)
    df["__known"] = known_w
    df["__imput"] = imput_w
    g = df.groupby("mix_uid").sum(numeric_only=True)
    res = pd.DataFrame(index=g.index)
    for c in cols:
        den = g[prefix + c + "__den"]
        res[prefix + c] = (g[prefix + c + "__num"] / den).where(den > 0)
    res[prefix + "coverage"] = g["__known"]
    res[prefix + "imputed_frac"] = g["__imput"]
    return res.reset_index()


# --------------------------------------------------------- activator chemistry
MW = dict(NaOH=40.0, KOH=56.11, Na2O=61.98, K2O=94.2, SiO2=60.08, Na2CO3=105.99, Na2SO4=142.04)
K2O_TO_NA2O_EQ = 0.658


def _naoh_solution_solids_frac(M: float, koh: bool = False) -> float:
    """Mass fraction of hydroxide solids in an M mol/L solution (density fit 1.0 + 0.04 M)."""
    rho = 1.0 + (0.048 if koh else 0.0405) * M
    return (MW["KOH"] if koh else MW["NaOH"]) * M / (1000.0 * rho)


def activator_chemistry(long: pd.DataFrame, mat_phys: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    """Per-mix activator solids, Na2O-equivalent, SiO2, effective silica modulus and solution water,
    all as mass / powder. Uses material solid_content / silica_modulus when reported, else group defaults."""
    cols = ["act_solids_b", "act_na2o_pct", "act_sio2_pct", "act_ms_eff", "act_water_b", "act_solid_assumed"]
    act = long[long["family"] == "activator"]
    if act.empty:
        return pd.DataFrame(columns=["mix_uid"] + cols)
    mp = mat_phys[["material_uid", "solid_content_pct", "silica_modulus"]] if "silica_modulus" in mat_phys.columns \
        else mat_phys[["material_uid", "solid_content_pct"]].assign(silica_modulus=np.nan)
    a = act.merge(mp, on="material_uid", how="left").merge(comp[["mix_uid", "naoh_molarity"]], on="mix_uid", how="left")
    m = a["frac"].astype(float).to_numpy()
    grp = a["group"].to_numpy()
    M = a["naoh_molarity"].fillna(0.0).astype(float).to_numpy()
    sc = a["solid_content_pct"].astype(float).to_numpy()
    ms = a["silica_modulus"].astype(float).to_numpy()
    solids = np.zeros_like(m); na2o = np.zeros_like(m); sio2 = np.zeros_like(m); assumed = np.zeros_like(m)
    for i in range(len(a)):
        g = grp[i]
        if g in ("naoh", "koh"):
            koh = g == "koh"
            if M[i] > 0:
                s = m[i] * _naoh_solution_solids_frac(M[i], koh)
            elif np.isfinite(sc[i]):
                s = m[i] * sc[i] / 100.0
            else:
                s = m[i]; assumed[i] = 1          # dosed as solid pellets/flakes
            solids[i] = s
            na2o[i] = s * (MW["K2O"] / 2 / MW["KOH"] * K2O_TO_NA2O_EQ if koh else MW["Na2O"] / 2 / MW["NaOH"])
        elif g in ("sodium_silicate", "potassium_silicate"):
            frac_s = sc[i] / 100.0 if np.isfinite(sc[i]) else 0.40
            if not np.isfinite(sc[i]):
                assumed[i] = 1
            s = m[i] * frac_s
            Ms = ms[i] if np.isfinite(ms[i]) and ms[i] > 0 else 2.0
            if g == "sodium_silicate":
                share_alk = 1.0 / (1.0 + Ms * MW["SiO2"] / MW["Na2O"])
                na2o[i] = s * share_alk
            else:
                share_alk = 1.0 / (1.0 + Ms * MW["SiO2"] / MW["K2O"])
                na2o[i] = s * share_alk * K2O_TO_NA2O_EQ
            sio2[i] = s * (1.0 - share_alk)
            solids[i] = s
        elif g == "sodium_carbonate":
            solids[i] = m[i]; na2o[i] = m[i] * MW["Na2O"] / MW["Na2CO3"]
        elif g == "sodium_sulfate":
            solids[i] = m[i]; na2o[i] = m[i] * MW["Na2O"] / MW["Na2SO4"]
        else:
            solids[i] = m[i]; assumed[i] = 1
    a = a.assign(_s=solids, _n=na2o, _si=sio2, _w=np.maximum(m - solids, 0.0), _as=assumed)
    g = a.groupby("mix_uid")[["_s", "_n", "_si", "_w", "_as"]].sum()
    out = pd.DataFrame(index=g.index)
    out["act_solids_b"] = g["_s"]
    out["act_na2o_pct"] = 100.0 * g["_n"]
    out["act_sio2_pct"] = 100.0 * g["_si"]
    out["act_ms_eff"] = ((g["_si"] / MW["SiO2"]) / (g["_n"] / MW["Na2O"]).replace(0, np.nan)).fillna(0.0)
    out["act_water_b"] = g["_w"]
    out["act_solid_assumed"] = (g["_as"] > 0).astype(int)
    return out.reset_index()


# ----------------------------------------------------------------- featurize
def featurize_frame(comp: pd.DataFrame, long: pd.DataFrame, mat_ox: pd.DataFrame, mat_phys: pd.DataFrame,
                    ctx: pd.DataFrame, class_medians: dict) -> pd.DataFrame:
    """Build the feature table.

    comp: composition wide table (one row per mix); long: per-material shares;
    mat_ox/mat_phys: per-material property tables; ctx: per-mix context
    (mix_uid, system_type, is_3dcp, year, curing_regime, curing_temp_C, curing_rh_pct,
    mix_time_s, max_rpm); class_medians: from build_class_medians.
    """
    comp = comp.drop_duplicates("mix_uid").reset_index(drop=True)
    col: dict[str, pd.Series] = {"mix_uid": comp["mix_uid"]}
    if "paper_uid" in comp.columns:
        col["paper_uid"] = comp["paper_uid"]

    # ---- composition block
    f = lambda c: comp[c].astype(float)
    for g in POWDER_GROUPS:
        col[f"pw_{g}"] = f(f"pw_{g}")
    col["water_b"] = f("water_b")
    col["log_water_b"] = np.log(col["water_b"].clip(lower=0.02))
    col["sand_b"] = f("sand_b")
    col["filler_frac"] = f("filler_frac")
    col["cement_share"] = f("cement_share")
    col["scm_frac"] = 1.0 - col["cement_share"]
    for g in AGG_GROUPS:
        col[f"agg_{g}"] = f(f"agg_{g}")
    for g in ADMIX_GROUPS:
        col[f"adx_{g}_pct"] = f(f"adx_{g}_pct")
    col["sp_solid_pct"] = f("sp_solid_pct")
    col["vma_solid_pct"] = f("vma_solid_pct")
    for g in FIBRE_GROUPS:
        col[f"fib_{g}_vol"] = f(f"fib_{g}_vol")
    col["fibre_total_vol_pct"] = f("fibre_total_vol_pct")
    col["fibre_total_mass_b"] = f("fibre_total_mass_b")
    for g in ACT_GROUPS:
        col[f"act_{g}"] = f(f"act_{g}")
    col["act_total_b"] = f("act_total_b")
    col["naoh_molarity"] = f("naoh_molarity")
    for g in NANO_GROUPS:
        col[f"nano_{g}_pct"] = f(f"nano_{g}_pct")
    col["nano_total_pct"] = f("nano_total_pct")
    col["other_frac"] = f("other_frac")
    col["total_solids_b"] = 1.0 + col["sand_b"].fillna(0.0) + col["fibre_total_mass_b"] + col["act_total_b"]
    flags = comp["flags"].fillna("")
    col["wb_source_reported"] = (comp["water_b_source"] == "reported").astype(int)
    col["sb_source_reported"] = (comp["sand_b_source"] == "reported").astype(int)
    col["mode_parts"] = comp["mode"].isin(["parts", "solids"]).astype(int)
    col["binder_sum_deviates"] = flags.str.contains("binder_sum_deviates").astype(int)
    col["cement_share_proxy"] = flags.str.contains("cement_share_proxy").astype(int)
    F = pd.DataFrame(col)

    # ---- binder chemistry (share-weighted, class-median imputed)
    ox_cols = [f"ox_{o}" for o in OX]
    mo = mat_ox.rename(columns={o: f"ox_{o}" for o in OX})
    if "chem_ok" in mo.columns:
        mo = mo.loc[mo["chem_ok"].fillna(False).astype(bool).to_numpy()]   # .to_numpy(): an empty object Series would select columns
    chem = _weighted_props(long, mo, ox_cols, "powder", class_medians, prefix="")
    chem = chem.rename(columns={"coverage": "chem_coverage", "imputed_frac": "chem_imputed_frac"})
    F = F.merge(chem, on="mix_uid", how="left")
    for c in ox_cols:
        if c not in F.columns:
            F[c] = np.nan
    F["chem_coverage"] = F["chem_coverage"].fillna(0.0)
    F["chem_imputed_frac"] = F["chem_imputed_frac"].fillna(0.0)

    # ---- physical properties: powder, aggregate, fibre
    phys = _weighted_props(long, mat_phys, PHYS_POWDER, "powder", class_medians, prefix="")
    phys = phys.rename(columns={"coverage": "phys_coverage", "imputed_frac": "phys_imputed_frac", "sg": "sg_powder"})
    agg = _weighted_props(long, mat_phys, PHYS_AGG, "aggregate", class_medians, prefix="")
    agg = agg.drop(columns=["coverage", "imputed_frac"])
    fib = _weighted_props(long, mat_phys, PHYS_FIB, "fibre", class_medians, prefix="")
    fib = fib.drop(columns=["coverage", "imputed_frac"])
    F = F.merge(phys, on="mix_uid", how="left").merge(agg, on="mix_uid", how="left").merge(fib, on="mix_uid", how="left")
    for c in PHYS_POWDER + PHYS_AGG + PHYS_FIB + ["phys_coverage", "phys_imputed_frac"]:
        cc = "sg_powder" if c == "sg" else c
        if cc not in F.columns:
            F[cc] = np.nan
    F = F.copy()

    # ---- derived chemistry / physical
    si = F["ox_SiO2"].replace(0, np.nan)
    der = {
        "ca_si": F["ox_CaO"] / si,
        "al_si": F["ox_Al2O3"] / si,
        "hydraulic_modulus": (F["ox_CaO"] + F["ox_MgO"].fillna(0) + F["ox_Al2O3"].fillna(0)) / si,
        "alkali_eq": (F["ox_Na2O"].fillna(0) + 0.658 * F["ox_K2O"].fillna(0)).where(
            ~(F["ox_Na2O"].isna() & F["ox_K2O"].isna())),
        "log_d50_um": np.log(F["d50_um"].clip(lower=0.01)),
        "fibre_aspect": (F["fibre_length_mm"] * 1000.0 / F["fibre_diameter_um"]),
        "phys_coverage": F["phys_coverage"].fillna(0.0),
        "phys_imputed_frac": F["phys_imputed_frac"].fillna(0.0),
    }
    F = F.drop(columns=["phys_coverage", "phys_imputed_frac"])
    F = pd.concat([F, pd.DataFrame(der, index=F.index)], axis=1)
    F.loc[F["fibre_total_vol_pct"] <= 0, PHYS_FIB + ["fibre_aspect"]] = np.nan

    # ---- activator chemistry (alkali-activated systems)
    ac = activator_chemistry(long, mat_phys, comp)
    F = F.merge(ac, on="mix_uid", how="left")
    for c in ["act_solids_b", "act_na2o_pct", "act_sio2_pct", "act_ms_eff", "act_water_b"]:
        F[c] = F[c].fillna(0.0)
    F["act_solid_assumed"] = F["act_solid_assumed"].fillna(0).astype(int)
    F["water_total_b"] = F["water_b"] + F["act_water_b"]
    F["w_solids_total"] = F["water_total_b"] / (1.0 + F["act_solids_b"])
    F = F.copy()

    # ---- curing & context
    c = ctx.drop_duplicates("mix_uid").set_index("mix_uid").reindex(F["mix_uid"])
    parsed = [parse_curing(r, t, h) for r, t, h in zip(c["curing_regime"], c["curing_temp_C"], c["curing_rh_pct"])]
    st = c["system_type"].where(c["system_type"].isin(["paste", "mortar"]), "unknown")
    ctxcols = {
        "curing_temp_C": pd.Series([p[0] for p in parsed], index=F.index, dtype=float),
        "curing_rh_pct": pd.Series([p[1] for p in parsed], index=F.index, dtype=float),
        "curing_type": pd.Categorical([p[2] for p in parsed], categories=CURING_TYPES),
        "is_3dcp": pd.to_numeric(c["is_3dcp"], errors="coerce").fillna(0).astype(int).values,
        "year": pd.to_numeric(c["year"], errors="coerce").values,
        "system_type": pd.Categorical(st.values, categories=SYSTEM_TYPES),
    }
    if "mix_time_s" in c.columns:          # protocol features present in the context (use_mixing_protocol)
        mt = pd.to_numeric(c["mix_time_s"], errors="coerce").values
        ctxcols["mix_time_s"] = mt
        ctxcols["log_mix_time"] = np.log(np.clip(mt, 5.0, None))
        ctxcols["max_rpm"] = pd.to_numeric(c["max_rpm"], errors="coerce").values
        mixer = c["mixer_type"] if "mixer_type" in c.columns else pd.Series([None] * len(c), index=c.index)
        ctxcols["mixer_type"] = pd.Categorical([classify_mixer(x) for x in mixer], categories=MIXER_TYPES)
    F = pd.concat([F, pd.DataFrame(ctxcols, index=F.index)], axis=1)
    F["heat_cured"] = (F["curing_temp_C"] >= 40).astype(int)
    F["binder_family"] = pd.Categorical([binder_family(r) for _, r in F.iterrows()], categories=BINDER_FAMILIES)
    return F


def feature_columns(F: pd.DataFrame) -> list[str]:
    return [c for c in F.columns if c not in {"mix_uid", "paper_uid"}]


def schema_of(F: pd.DataFrame, material_groups_hash: str, class_medians_hash: str) -> dict:
    cols = feature_columns(F)
    dtypes = {c: ("category" if isinstance(F[c].dtype, pd.CategoricalDtype) else str(F[c].dtype)) for c in cols}
    levels = {c: list(F[c].cat.categories) for c in cols if dtypes[c] == "category"}
    payload = json.dumps({"columns": cols, "dtypes": dtypes, "levels": levels, "featurizer": FEATURIZER_VERSION,
                          "material_groups": material_groups_hash, "class_medians": class_medians_hash}, sort_keys=True)
    return {"columns": cols, "dtypes": dtypes, "categorical_levels": levels, "featurizer_version": FEATURIZER_VERSION,
            "material_groups_hash": material_groups_hash, "class_medians_hash": class_medians_hash,
            "hash": hashlib.sha256(payload.encode()).hexdigest()[:16]}


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def build_context(tables: dict[str, pd.DataFrame], use_mixing_protocol: bool = False) -> pd.DataFrame:
    mixes = tables["mixes"]
    papers = tables["papers"][["paper_uid", "year", "is_3dcp_study"]]
    ctx = mixes[["mix_uid", "paper_uid", "system_type", "curing_regime", "curing_temp_C", "curing_rh_pct", "protocol_uid"]]
    ctx = ctx.merge(papers, on="paper_uid", how="left").rename(columns={"is_3dcp_study": "is_3dcp"})
    if use_mixing_protocol and "mixing_protocols" in tables:
        mp = tables["mixing_protocols"][["protocol_uid", "total_mixing_time_s", "max_speed_rpm", "mixer_type"]]
        mp = mp.drop_duplicates("protocol_uid")
        ctx = ctx.merge(mp, on="protocol_uid", how="left").rename(
            columns={"total_mixing_time_s": "mix_time_s", "max_speed_rpm": "max_rpm"})
    return ctx.drop(columns=["protocol_uid"])
