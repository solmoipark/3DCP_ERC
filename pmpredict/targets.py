"""Build the long target table from numeric measurements.

Per target (configs/targets.yaml): unit harmonisation, plausibility bounds,
geometry / basis filters, age binning, condition_note normalisation with a
conflict rule, and aggregation of replicate rows to one value per
(mix, target, age_bin, comparability_group, rest_time).
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy

import numpy as np
import pandas as pd

from .config import load_yaml

log = logging.getLogger("pmpredict.targets")


def load_target_rules() -> tuple[dict[str, dict], dict]:
    y = load_yaml("targets.yaml")
    defaults = y.get("defaults", {})
    rules = {}
    for name, r in y["targets"].items():
        rr = deepcopy(defaults)
        rr.update(r or {})
        rules[name] = rr
    meta = {k: v for k, v in y.items() if k not in {"targets", "defaults"}}
    return rules, meta


# ------------------------------------------------------------- helpers
def snap_age(age: float, grid: list[float], tol: float = 0.10) -> float:
    if age is None or not np.isfinite(age) or age <= 0:
        return np.nan
    la = np.log(age)
    g = np.asarray(grid, dtype=float)
    d = np.abs(np.log(g) - la)
    i = int(np.argmin(d))
    if d[i] <= np.log(1.0 + tol):
        return float(g[i])
    return float(f"{age:.3g}")


def normalize_condition(note, drop_re: re.Pattern, rep_re: re.Pattern) -> tuple[str, bool]:
    """Return (condition key, drop). '' = base/replicate condition."""
    if not isinstance(note, str) or not note.strip():
        return "", False
    s = note.strip().lower()
    if drop_re.search(s):
        return "", True
    if rep_re.search(s):
        return "", False
    return re.sub(r"[^a-z0-9]+", " ", s).strip(), False


# ------------------------------------------------------- test covariates
# rheometer / test protocol parameters attached per test_uid (numeric, SI) + two categoricals
TP_NUMERIC: dict[str, tuple[str, dict[str, float]]] = {
    # parameter -> (feature name, {accepted unit_si (lower): factor to the feature unit})
    "pre_shear_rate": ("tp_pre_shear_rate_1s", {"1/s": 1.0, "s-1": 1.0, "1/min": 1 / 60.0}),
    "pre_shear_duration": ("tp_pre_shear_s", {"s": 1.0, "min": 60.0}),
    "rest_time_before_measurement": ("tp_rest_s", {"s": 1.0, "min": 60.0}),
    "temperature": ("tp_temp_C", {"degc": 1.0, "c": 1.0, "°c": 1.0, "deg_c": 1.0}),
    "shear_rate_max": ("tp_shear_rate_max_1s", {"1/s": 1.0, "s-1": 1.0, "1/min": 1 / 60.0}),
    "ramp_duration": ("tp_ramp_s", {"s": 1.0, "min": 60.0}),
    "gap": ("tp_gap_mm", {"mm": 1.0, "um": 0.001}),
    "vane_diameter": ("tp_vane_d_mm", {"mm": 1.0}),
}
TP_GEOMETRY = ["vane", "coaxial", "parallel_plate", "cone_plate", "other", "unknown"]
TP_METHODS = ["flow_curve_bingham_fit", "flow_curve_herschel_bulkley_fit", "stress_growth_vane", "stress_growth_coaxial",
              "coaxial_cylinder_rheometer", "vane_rheometer", "plate_plate_rheometer", "oscillatory_amplitude_sweep",
              "other", "unknown"]


def classify_geometry(text) -> str:
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    s = text.lower()
    if "vane" in s or "paddle" in s or "t-bar" in s or "stirrer" in s:
        return "vane"
    if re.search(r"coaxial|concentric|couette|cylinder|bob|cup", s):
        return "coaxial"
    if re.search(r"parallel|plate[- ]plate|pp\d", s):
        return "parallel_plate"
    if "cone" in s:
        return "cone_plate"
    return "other"


def build_test_covariates(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per test_uid: numeric protocol parameters (SI) + geometry / method categoricals."""
    tests = tables["tests"][["test_uid", "method_name", "geometry"]].drop_duplicates("test_uid").copy()
    out = tests[["test_uid"]].copy()
    tp = tables.get("test_protocols")
    if tp is not None and len(tp):
        tp = tp.copy()
        tp["unit_l"] = tp["unit_si"].astype("string").str.lower().str.strip()
        for param, (feat, units) in TP_NUMERIC.items():
            s = tp[(tp["parameter"] == param) & tp["unit_l"].isin(units)]
            v = pd.to_numeric(s["value_si"], errors="coerce") * s["unit_l"].map(units).astype(float)
            med = v.groupby(s["test_uid"]).median()
            out[feat] = out["test_uid"].map(med)
        g = tp[tp["parameter"] == "geometry_type"].drop_duplicates("test_uid").set_index("test_uid")["value_reported"]
        geo = out["test_uid"].map(g)
    else:
        for feat, _ in TP_NUMERIC.values():
            out[feat] = np.nan
        geo = pd.Series([None] * len(out), index=out.index)
    # fall back to tests.geometry free text when no geometry_type parameter
    geo = geo.where(geo.notna(), out["test_uid"].map(tests.set_index("test_uid")["geometry"]))
    out["tp_geometry"] = pd.Categorical([classify_geometry(x) for x in geo], categories=TP_GEOMETRY)
    mn = out["test_uid"].map(tests.set_index("test_uid")["method_name"]).astype("object")
    mn = mn.where(mn.isin(TP_METHODS), mn.where(mn.isna(), "other")).fillna("unknown")
    out["tp_method"] = pd.Categorical(mn, categories=TP_METHODS)
    return out


# ------------------------------------------------------------- builder
def build_targets(tables: dict[str, pd.DataFrame], rules: dict[str, dict] | None = None,
                  meta: dict | None = None, only: list[str] | None = None
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (targets_long, qa) where targets_long has one row per
    (mix_uid, target, age_bin, comparability_group, rest_time_s)."""
    if rules is None:
        rules, meta = load_target_rules()
    meta = meta or {}
    grid = meta.get("age_grid", [1, 3, 7, 28, 90])
    drop_re = re.compile(meta.get("condition_drop_regex", "predict"), re.I)
    rep_re = re.compile(meta.get("condition_replicate_regex", "^replicate"), re.I)
    conflict_rel = float(meta.get("condition_conflict_rel", 0.15))

    ms = tables["measurements"]
    tests = tables["tests"][["test_uid", "comparability_group", "method_name"]]
    ms = ms.merge(tests, on="test_uid", how="left")
    ms["unit_canonical"] = ms["unit_canonical"].astype("string").str.strip()
    ms["basis"] = ms["basis"].astype("string").str.strip()

    out, qa = [], []
    for name, r in rules.items():
        if only and name not in only:
            continue
        q = {"target": name}
        m = ms[ms["quantity"].isin(r["quantities"])].copy()
        q["rows_in"] = len(m)
        m = m[m["value_kind"].isin(r.get("value_kinds", ["reported"]))]
        q["after_kind"] = len(m)
        # units
        umap = {str(k): float(v) for k, v in r["units"].items()}
        fac = m["unit_canonical"].map(umap)
        if len(umap) == 1:
            fac = fac.fillna(list(umap.values())[0]) if r.get("assume_unit_if_missing", True) else fac
        m = m.assign(value=m["value_canonical"] * fac.astype(float)).dropna(subset=["value"])
        q["after_unit"] = len(m)
        if r.get("abs_value"):
            m["value"] = m["value"].abs()
        lo, hi = r.get("bounds", [-np.inf, np.inf])
        m = m[(m["value"] >= lo) & (m["value"] <= hi)]
        q["after_bounds"] = len(m)
        # geometry
        excl = r.get("exclude_comparability") or []
        if excl:
            m = m[~m["comparability_group"].isin(excl)]
        q["after_geom"] = len(m)
        # basis (heat)
        if r.get("basis_in"):
            imp = r.get("unit_implies_basis") or {}
            unit_basis = m["unit_canonical"].map(imp)
            keep = m["basis"].isin(r["basis_in"]) | unit_basis.isin(r["basis_in"])
            m = m[keep]
        q["after_basis"] = len(m)
        # age
        m["age_d"] = pd.to_numeric(m["age_norm_d"], errors="coerce")
        if r.get("requires_age"):
            m = m[m["age_d"].notna() & (m["age_d"] > 0)]
        q["after_age"] = len(m)
        m["age_bin"] = [snap_age(a, grid) for a in m["age_d"]]
        m["rest_time_s"] = pd.to_numeric(m["rest_time_norm_s"], errors="coerce")
        # condition note
        keys = [normalize_condition(n, drop_re, rep_re) for n in m["condition_note"]]
        m["cond_key"] = [k for k, _ in keys]
        m = m[[not d for _, d in keys]]
        q["after_cond_drop"] = len(m)
        if m.empty:
            qa.append(q); continue
        # group replicates
        m["cg"] = m["comparability_group"].astype("string").fillna("unknown")
        m["rt"] = m["rest_time_s"].fillna(-1.0)
        m["ab"] = m["age_bin"].fillna(-1.0)
        gcols = ["mix_uid", "paper_uid", "ab", "cg", "rt", "cond_key"]
        g = m.groupby(gcols, sort=False).agg(
            value=("value", "median"), n_rows=("value", "size"), vmin=("value", "min"), vmax=("value", "max"),
            value_kind_mode=("value_kind", lambda s: s.mode().iat[0]),
            test_uid=("test_uid", lambda s: s.mode().iat[0]),
        ).reset_index()
        q["groups"] = len(g)
        # conflict rule across condition keys
        gcols2 = ["mix_uid", "paper_uid", "ab", "cg", "rt"]
        parts = []
        n_conflict_drop = 0
        n_multi = 0
        for _, grp in g.groupby(gcols2, sort=False):
            if len(grp) == 1:
                parts.append(grp); continue
            n_multi += 1
            med = grp["value"].median()
            spread = (grp["value"].max() - grp["value"].min()) / med if med else 0.0
            if spread <= conflict_rel:
                row = grp.iloc[[0]].copy()
                row["value"] = med
                row["n_rows"] = grp["n_rows"].sum()
                row["cond_key"] = ""
                parts.append(row)
            else:
                base = grp[grp["cond_key"] == ""]
                if len(base) == 1:
                    parts.append(base)
                else:
                    n_conflict_drop += 1
        g = pd.concat(parts, ignore_index=True) if parts else g.iloc[0:0]
        q["multi_condition_groups"] = n_multi
        q["conflict_dropped"] = n_conflict_drop
        g["target"] = name
        g["age_d"] = g["ab"].where(g["ab"] >= 0)
        g["comparability_group"] = g["cg"].where(g["cg"] != "unknown")
        g["rest_time_s"] = g["rt"].where(g["rt"] >= 0)
        g["rest_time_known"] = (g["rt"] >= 0).astype(int)
        g["spread_rel"] = ((g["vmax"] - g["vmin"]) / g["value"].abs().replace(0, np.nan)).fillna(0.0)
        g = g.drop(columns=["ab", "cg", "rt", "vmin", "vmax"])
        q["final_rows"] = len(g)
        q["n_mixes"] = g["mix_uid"].nunique()
        q["n_papers"] = g["paper_uid"].nunique()
        qa.append(q)
        out.append(g)
        log.info("target %s: %d rows / %d mixes / %d papers", name, len(g), q["n_mixes"], q["n_papers"])
    long = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    cols = ["mix_uid", "paper_uid", "target", "value", "age_d", "comparability_group", "rest_time_s",
            "rest_time_known", "n_rows", "spread_rel", "value_kind_mode", "cond_key", "test_uid"]
    long = long[cols] if len(long) else long
    return long, pd.DataFrame(qa)
