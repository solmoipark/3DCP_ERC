"""Rheology from digitised flow curves (curves / curve_points).

Bingham parameters fitted to shear_rate -> shear_stress curves (apparent-viscosity curves are
converted to stress) reproduce the tabulated values of the same mixes (Spearman 0.88 for yield
stress, 0.97 for plastic viscosity; median bias < 0.05 log10), so they are used to extend the
``dynamic_yield_stress`` and ``plastic_viscosity`` targets to mixes that only report a figure.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("pmpredict.curves")

REF_RATES = (10.0, 50.0, 100.0)
# strict fit filter (redig01 A/B, 2026-09-10): R2 >= 0.97, rate range reaching 50 1/s, >= 6 points. The loose
# filter (0.9, no range check) on the enlarged curve set lowered grouped-CV Spearman of both targets.
MIN_R2 = 0.97
MIN_XMAX = 50.0
MIN_N = 6


_CACHE_DIR = Path(__file__).resolve().parents[1] / "data"


def _cache_or_query(db_path: Path, name: str, query_fn):
    """Read `data/<name>.parquet` when master.db is not available (deployed UI); otherwise query the DB and
    refresh the cache so the repository can ship without the 170 MB database."""
    cache = _CACHE_DIR / f"{name}.parquet"
    if not Path(db_path).exists():
        if cache.exists():
            return pd.read_parquet(cache)
        raise FileNotFoundError(f"neither master.db ({db_path}) nor the cache {cache} is available")
    df = query_fn()
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    except Exception:  # cache is a convenience; never fail the caller
        pass
    return df


def load_flow_curves(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    def _q():
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        try:
            c = pd.read_sql_query(
                "SELECT curve_uid, mix_uid, test_uid, paper_uid, x_quantity, x_unit, y_quantity, y_unit, n_points, "
                "digitisation_uncertainty_pct FROM curves WHERE x_quantity='shear_rate' "
                "AND y_quantity IN ('shear_stress','apparent_viscosity')", con)
            p = pd.read_sql_query("SELECT curve_uid, x_canonical, y_canonical FROM curve_points", con)
        finally:
            con.close()
        p = p[p.curve_uid.isin(c.curve_uid)].copy()
        return pd.concat([c.assign(_kind="c"), p.assign(_kind="p")], ignore_index=True)
    both = _cache_or_query(db_path, "curves_flow_cache", _q)
    c = both[both._kind == "c"].dropna(axis=1, how="all").drop(columns="_kind").reset_index(drop=True)
    p = both[both._kind == "p"][["curve_uid", "x_canonical", "y_canonical"]].reset_index(drop=True)
    p = p[p.curve_uid.isin(c.curve_uid)].copy()
    p["x"] = pd.to_numeric(p.x_canonical, errors="coerce")
    p["y"] = pd.to_numeric(p.y_canonical, errors="coerce")
    # canonical values carry the printed unit (validator X-05): bring kPa -> Pa, 1/min -> 1/s here
    u = p.merge(c[["curve_uid", "x_unit", "y_unit"]], on="curve_uid", how="left")
    yfac = np.where(u.y_unit.astype(str).str.lower() == "kpa", 1000.0, 1.0)
    xfac = np.where(u.x_unit.astype(str).str.lower().isin(["1/min", "min-1"]), 1 / 60.0, 1.0)
    p["y"] = p["y"].to_numpy() * yfac
    p["x"] = p["x"].to_numpy() * xfac
    return c, p.dropna(subset=["x", "y"])


def fit_bingham(x, y, kind: str = "shear_stress", yunit: str | None = None) -> dict | None:
    """Least-squares Bingham fit on the upper 80 % of the shear-rate range; stress at reference rates."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if kind == "apparent_viscosity":
        y = y * (0.001 if str(yunit).lower().startswith("mpa") else 1.0) * x
    o = np.argsort(x); x, y = x[o], y[o]
    m = (x > 0) & np.isfinite(y) & (y > 0)
    x, y = x[m], y[m]
    if len(x) < 4:
        return None
    sel = x >= 0.2 * x.max()
    if sel.sum() < 3:
        sel = np.ones_like(x, bool)
    A = np.column_stack([np.ones(int(sel.sum())), x[sel]])
    (tau0, mu), *_ = np.linalg.lstsq(A, y[sel], rcond=None)
    pred = tau0 + mu * x[sel]
    ss = float(np.sum((y[sel] - y[sel].mean()) ** 2))
    r2 = 1 - float(np.sum((y[sel] - pred) ** 2)) / ss if ss > 0 else np.nan
    out = dict(tau0=float(tau0), mu=float(mu), r2=r2, n=int(len(x)), xmin=float(x.min()), xmax=float(x.max()))
    for r in REF_RATES:
        out[f"tau_{int(r)}"] = float(np.interp(r, x, y)) if x.min() <= r <= x.max() else np.nan
    return out


def fit_all(db_path: Path) -> pd.DataFrame:
    c, p = load_flow_curves(db_path)
    rows = []
    for cu in c.itertuples(index=False):
        pts = p[p.curve_uid == cu.curve_uid]
        f = fit_bingham(pts.x, pts.y, cu.y_quantity, cu.y_unit)
        if f:
            rows.append(dict(curve_uid=cu.curve_uid, mix_uid=cu.mix_uid, paper_uid=cu.paper_uid, test_uid=cu.test_uid,
                             kind=cu.y_quantity, **f))
    return pd.DataFrame(rows)


def good_fits(F: pd.DataFrame) -> pd.DataFrame:
    if F.empty:
        return F
    return F[(F.r2 >= MIN_R2) & (F.mu > 0) & (F.tau0 > -0.1 * F.tau0.abs().max()) & (F.xmax >= MIN_XMAX) & (F.n >= MIN_N)]


def augment_rheology_targets(T: pd.DataFrame, db_path: Path) -> tuple[pd.DataFrame, dict]:
    """Append curve-derived Bingham tau0 / mu rows (value_kind_mode='curve_derived') for mixes that
    have no tabulated dynamic_yield_stress / plastic_viscosity. Returns (targets, summary)."""
    F = fit_all(db_path)
    G = good_fits(F)
    summ = dict(curves=int(len(F)), good_fits=int(len(G)), added={})
    if G.empty:
        return T, summ
    per_mix = G.groupby("mix_uid").agg(tau0=("tau0", "median"), mu=("mu", "median"), paper_uid=("paper_uid", "first"),
                                       test_uid=("test_uid", "first")).reset_index()
    cols = list(T.columns)
    add_all = []
    for tgt, col, lo, hi in (("dynamic_yield_stress", "tau0", 0.1, 50000), ("plastic_viscosity", "mu", 0.01, 5000)):
        have = set(T.loc[T.target == tgt, "mix_uid"])
        add = per_mix[~per_mix.mix_uid.isin(have) & per_mix[col].between(lo, hi)]
        rows = pd.DataFrame(dict(mix_uid=add.mix_uid, paper_uid=add.paper_uid, target=tgt, value=add[col], age_d=np.nan,
                                 comparability_group=None, rest_time_s=np.nan, rest_time_known=0, n_rows=1, spread_rel=0.0,
                                 value_kind_mode="curve_derived", cond_key="", test_uid=add.test_uid))
        for c in cols:
            if c not in rows.columns:
                rows[c] = np.nan
        add_all.append(rows[cols])
        summ["added"][tgt] = dict(rows=int(len(rows)), papers=int(add.paper_uid.nunique()))
    out = pd.concat([T] + add_all, ignore_index=True)
    log.info("curve augmentation: %s", summ)
    return out, summ


def augment_athix_targets(T: pd.DataFrame, db_path: Path, min_r2: float = 0.7, min_duration_s: float = 600.0
                          ) -> tuple[pd.DataFrame, dict]:
    """Append structuration_rate_athix rows from linear fits of digitised static-yield-stress vs rest-time
    curves (Roussel model, Pa/s) for mixes without a tabulated Athix."""
    from .thixocurve import fit_athix, load_static_curves
    fits = fit_athix(load_static_curves(db_path))
    summ = dict(curves=int(len(fits)), added={})
    good = fits[(fits.r2 >= min_r2) & (fits.athix > 0) & (fits.t_max_s >= min_duration_s)]
    if good.empty:
        return T, summ
    per_mix = good.groupby("mix_uid").agg(athix=("athix", "median"), paper_uid=("paper_uid", "first")).reset_index()
    have = set(T.loc[T.target == "structuration_rate_athix", "mix_uid"])
    add = per_mix[~per_mix.mix_uid.isin(have) & per_mix.athix.between(0.0005, 200)]
    rows = pd.DataFrame(dict(mix_uid=add.mix_uid, paper_uid=add.paper_uid, target="structuration_rate_athix", value=add.athix,
                             age_d=np.nan, comparability_group=None, rest_time_s=np.nan, rest_time_known=0, n_rows=1, spread_rel=0.0,
                             value_kind_mode="curve_derived", cond_key="", test_uid=None))
    for c in T.columns:
        if c not in rows.columns:
            rows[c] = np.nan
    summ["added"]["structuration_rate_athix"] = dict(rows=int(len(rows)), papers=int(add.paper_uid.nunique()))
    log.info("athix curve augmentation: %s", summ)
    return pd.concat([T, rows[T.columns]], ignore_index=True), summ


# ----------------------------------------------------------------- age-series curves (redig03 wave)
AGE_X = ("age", "curing_age", "curing_time", "time")
X_TO_DAYS = {"d": 1.0, "day": 1.0, "days": 1.0, "h": 1 / 24, "hr": 1 / 24, "hours": 1 / 24, "min": 1 / 1440,
             "wk": 7.0, "week": 7.0, "weeks": 7.0, "month": 30.0, "months": 30.0}
# printed y-units seen in the curves table -> factor to microstrain (shrinkage) or MPa (strength)
STRAIN_TO_UE = {"microstrain": 1, "um/m": 1, "µm/m": 1, "µε": 1, "ue": 1, "ue ": 1, "us": 1, "1e-6": 1, "10e-6": 1,
                "×10^-6": 1, "x10^-6": 1, "1e-6_strain": 1, "mm/mm x1e-6": 1, "uepsilon": 1, "um_per_m": 1, "um": 1,
                "µm": 1, "1e-6 mm/mm": 1, "as_plotted_axis_label_microstrain": 1, "x10^6 um/m": 1, "με": 1,
                "mm/m": 1000, "1e-3": 1000, "permille": 1000, "1e-3 (microstrain)": 1000, "‰": 1000,
                "%": 10000, "pct": 10000, "percent": 10000, "%x10^-3": 10, "1e-5": 10, "x1e-5 dimensionless": 10,
                "fraction": 1e6, "unitless_strain": 1e6}
AGE_SERIES = {  # target -> (curve y_quantities, unit map, abs_value)
    "drying_shrinkage": (("drying_shrinkage",), STRAIN_TO_UE, True),
    "autogenous_shrinkage": (("autogenous_shrinkage",), STRAIN_TO_UE, True),
    "compressive_strength": (("compressive_strength",), {"mpa": 1.0, "n/mm2": 1.0, "n/mm²": 1.0}, False),
    "flexural_strength": (("flexural_strength",), {"mpa": 1.0, "n/mm2": 1.0, "n/mm²": 1.0}, False),
}


def load_age_curves(db_path: Path, y_quantities: tuple[str, ...],
                    exclude_curve_types: tuple[str, ...] = ()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`exclude_curve_types`: SQL LIKE patterns on curves.curve_type to leave out (e.g. '%_vs_age_bars' to drop
    the redig04 grouped-bar readings and keep only line/marker series)."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        sql = ("SELECT curve_uid, mix_uid, test_uid, paper_uid, x_quantity, x_unit, y_quantity, y_unit, n_points, curve_type "
               f"FROM curves WHERE x_quantity IN ({','.join('?' * len(AGE_X))}) AND y_quantity IN ({','.join('?' * len(y_quantities))})")
        params = list(AGE_X) + list(y_quantities)
        for pat in exclude_curve_types:
            sql += " AND COALESCE(curve_type,'') NOT LIKE ?"
            params.append(pat)
        c = pd.read_sql_query(sql, con, params=params)
        if c.empty:
            return c, pd.DataFrame(columns=["curve_uid", "x", "y"])
        p = pd.read_sql_query("SELECT curve_uid, x_value, y_value FROM curve_points", con)
    finally:
        con.close()
    p = p[p.curve_uid.isin(c.curve_uid)].copy()
    p["x"] = pd.to_numeric(p.x_value, errors="coerce")
    p["y"] = pd.to_numeric(p.y_value, errors="coerce")
    return c, p.dropna(subset=["x", "y"])


def augment_age_series_targets(T: pd.DataFrame, db_path: Path, grid: list[float] | None = None,
                               targets: tuple[str, ...] = tuple(AGE_SERIES), min_points: int = 3,
                               exclude_curve_types: tuple[str, ...] = ()) -> tuple[pd.DataFrame, dict]:
    """Append target rows read off digitised age/time curves (strength vs age, shrinkage vs time) at the
    standard age grid, for (mix, target, age_bin) combinations that have no tabulated value.
    Interpolation is linear between plotted points and never extrapolates beyond the plotted range."""
    from .targets import snap_age
    grid = list(grid or [1, 3, 7, 28, 90])
    summ = {"added": {}}
    add_all = []
    cols = list(T.columns)
    for tgt in targets:
        if tgt not in AGE_SERIES:
            continue
        yq, umap, use_abs = AGE_SERIES[tgt]
        c, p = load_age_curves(db_path, yq, tuple(exclude_curve_types or ()))
        if c.empty:
            continue
        xf = c.x_unit.astype(str).str.strip().str.lower().map(X_TO_DAYS)
        yf = c.y_unit.astype(str).str.strip().str.lower().map({k.lower(): v for k, v in umap.items()})
        c = c.assign(xf=xf, yf=yf).dropna(subset=["xf", "yf"])
        have = T[T.target == tgt]
        have_keys = set(zip(have.mix_uid, [snap_age(a, grid) for a in have.age_d]))
        rows = {}
        for cu in c.itertuples(index=False):
            pts = p[p.curve_uid == cu.curve_uid].sort_values("x")
            if len(pts) < min_points:
                continue
            x = pts.x.to_numpy() * cu.xf
            y = pts.y.to_numpy() * cu.yf
            if use_abs:
                y = np.abs(y)
            for a in grid:
                if not (x.min() <= a <= x.max()):
                    continue
                key = (cu.mix_uid, a)
                if key in have_keys:
                    continue
                v = float(np.interp(a, x, y))
                if not np.isfinite(v) or v <= 0:
                    continue
                rows.setdefault(key, []).append((v, cu.paper_uid, cu.test_uid))
        if not rows:
            continue
        recs = []
        for (mix, a), vals in rows.items():
            v = float(np.median([t[0] for t in vals]))
            recs.append(dict(mix_uid=mix, paper_uid=vals[0][1], target=tgt, value=v, age_d=float(a), comparability_group=None,
                             rest_time_s=np.nan, rest_time_known=0, n_rows=len(vals), spread_rel=0.0,
                             value_kind_mode="curve_derived", cond_key="", test_uid=vals[0][2] or None))
        df = pd.DataFrame(recs)
        for col in cols:
            if col not in df.columns:
                df[col] = np.nan
        add_all.append(df[cols])
        summ["added"][tgt] = dict(rows=len(df), papers=int(df.paper_uid.nunique()), mixes=int(df.mix_uid.nunique()))
    if not add_all:
        return T, summ
    log.info("age-series curve augmentation: %s", summ)
    return pd.concat([T] + add_all, ignore_index=True), summ


def agreement_report(T: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """Curve-derived vs tabulated values for mixes that have both."""
    G = good_fits(fit_all(db_path))
    per_mix = G.groupby("mix_uid").agg(tau0=("tau0", "median"), mu=("mu", "median")).reset_index()
    rows = []
    for tgt, col in (("dynamic_yield_stress", "tau0"), ("plastic_viscosity", "mu")):
        tab = T[(T.target == tgt) & (T.value_kind_mode != "curve_derived")].groupby("mix_uid")["value"].median()
        j = per_mix.merge(tab.rename("tab"), left_on="mix_uid", right_index=True)
        j = j[(j["tab"] > 0) & (j[col] > 0)]
        if len(j):
            lr = np.log10(j[col] / j["tab"])
            rows.append(dict(target=tgt, n_mixes=len(j), log10_ratio_median=lr.median(), log10_ratio_q25=lr.quantile(.25),
                             log10_ratio_q75=lr.quantile(.75), spearman=j[col].corr(j["tab"], method="spearman")))
    return pd.DataFrame(rows)
