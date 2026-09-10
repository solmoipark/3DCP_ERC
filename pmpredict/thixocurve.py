"""Structuration (static yield stress vs rest time) curve prediction.

Two routes:
  physical : tau_s(t) = tau_s(0) + Athix * t (Roussel) with tau_s(0) from the static_yield_stress model at rest 0 and
             Athix from the structuration_rate_athix model (augmented with curve-fitted Athix). PRIMARY route: the
             real curves grow x7 (median) over 0-80 min and this route reproduces that order of growth.
  model    : sweep rest_time_s through the static_yield_stress model. Reference only: its rest-time dependence is far too
             flat (implied Athix ~1/12 of the fitted values) because 56 % of its training rows lack a rest time.
Digitised curves of the nearest published mixes are overlaid for context.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PipelineConfig
from .flowcurve import _korean_font, _sample_lognormal_split
from .predict import Assets, add_covariates, featurize_specs
from .schema import MixSpec

TIME_X = {"rest_time", "resting_time", "time_at_rest", "time", "time_after_mixing", "hydration_time", "time_since_extrusion"}
T_FAC = {"s": 1.0, "sec": 1.0, "min": 60.0, "h": 3600.0, "hr": 3600.0}
DEFAULT_REST_S = np.concatenate([[0.0], np.geomspace(30.0, 3600.0, 30)])


def load_static_curves(db_path: Path) -> pd.DataFrame:
    """Digitised static-yield-stress vs rest-time points: curve_uid, mix_uid, paper_uid, t_s, tau [Pa]."""
    from .curves import _cache_or_query

    def _q():
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        try:
            c = pd.read_sql_query("SELECT curve_uid, mix_uid, paper_uid, x_quantity, x_unit, y_unit FROM curves "
                                  "WHERE y_quantity='static_yield_stress'", con)
            p = pd.read_sql_query("SELECT curve_uid, x_canonical, y_canonical FROM curve_points", con)
        finally:
            con.close()
        c = c[c.x_quantity.isin(TIME_X) & c.x_unit.astype(str).str.lower().isin(T_FAC)]
        return p[p.curve_uid.isin(c.curve_uid)].merge(c, on="curve_uid")
    p = _cache_or_query(db_path, "curves_static_cache", _q)
    p["t_s"] = pd.to_numeric(p.x_canonical, errors="coerce") * p.x_unit.str.lower().map(T_FAC)
    p["tau"] = pd.to_numeric(p.y_canonical, errors="coerce") * np.where(p.y_unit.astype(str).str.lower() == "kpa", 1000.0, 1.0)
    p = p.dropna(subset=["t_s", "tau"])
    return p[(p.t_s >= 0) & (p.tau > 0)][["curve_uid", "mix_uid", "paper_uid", "t_s", "tau"]]


def fit_athix(points: pd.DataFrame) -> pd.DataFrame:
    """Per curve: linear fit tau = tau0 + Athix * t (Roussel), R2, duration."""
    rows = []
    for cu, g in points.groupby("curve_uid"):
        g = g.sort_values("t_s")
        if len(g) < 3:
            continue
        A = np.column_stack([np.ones(len(g)), g.t_s])
        (b, a), *_ = np.linalg.lstsq(A, g.tau, rcond=None)
        pred = b + a * g.t_s
        ss = float(((g.tau - g.tau.mean()) ** 2).sum())
        rows.append(dict(curve_uid=cu, mix_uid=g.mix_uid.iloc[0], paper_uid=g.paper_uid.iloc[0], n=len(g),
                         t_max_s=float(g.t_s.max()), tau0=float(b), athix=float(a),
                         r2=float(1 - ((g.tau - pred) ** 2).sum() / ss) if ss > 0 else np.nan))
    return pd.DataFrame(rows)


# ------------------------------------------------------------- prediction
def predict_static_curve(spec: MixSpec, cfg: PipelineConfig, rest_s=DEFAULT_REST_S, assets: Assets | None = None,
                         n_samples: int = 3000, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Returns (curve table with route 'model' and 'physical' bands, info dict)."""
    assets = assets or Assets(cfg)
    rest_s = np.asarray(rest_s, float)
    F, _ = featurize_specs([spec], assets)
    m = assets.model("static_yield_stress")
    # route A: sweep rest time through the model
    specs_t = []
    for t in rest_s:
        s = MixSpec.from_dict(spec.to_dict()); s.conditions.rest_time_s = float(t); specs_t.append(s)
    Ft = pd.concat([F] * len(rest_s), ignore_index=True)
    X = add_covariates(Ft, specs_t, m.meta.get("covariates", []))
    q = m.predict_quantiles(X)
    A = pd.DataFrame(dict(route="model", rest_s=rest_s, q10=q.q10.to_numpy(), q50=q.q50.to_numpy(), q90=q.q90.to_numpy()))
    info = dict(static_weak=bool(assets.manifest["models"]["static_yield_stress"].get("weak_model", False)),
                tau0_model=(float(A.q10.iloc[0]), float(A.q50.iloc[0]), float(A.q90.iloc[0])))
    # route B: tau_s(0) + Athix * t
    B = None
    if "structuration_rate_athix" in assets.manifest["models"]:
        ma = assets.model("structuration_rate_athix")
        Xa = add_covariates(F, [spec], ma.meta.get("covariates", []))
        qa = ma.predict_quantiles(Xa).iloc[0]
        rng = np.random.default_rng(seed)
        t0 = _sample_lognormal_split(*info["tau0_model"], n_samples, rng)
        ath = _sample_lognormal_split(float(qa.q10), float(qa.q50), float(qa.q90), n_samples, rng)
        tau = t0[:, None] + ath[:, None] * rest_s[None, :]
        B = pd.DataFrame(dict(route="physical", rest_s=rest_s, q10=np.quantile(tau, .1, axis=0), q50=np.quantile(tau, .5, axis=0),
                              q90=np.quantile(tau, .9, axis=0)))
        info["athix_model"] = (float(qa.q10), float(qa.q50), float(qa.q90))
        info["athix_weak"] = bool(assets.manifest["models"]["structuration_rate_athix"].get("weak_model", False))
    out = pd.concat([A] + ([B] if B is not None else []), ignore_index=True)
    # model-implied structuration rate over the window (median line slope, Pa/s)
    a = A.q50.to_numpy(); info["athix_implied_model"] = float((a[-1] - a[0]) / max(rest_s[-1] - rest_s[0], 1e-9))
    return out, info


def analogue_static_curves(spec: MixSpec, cfg: PipelineConfig, k: int = 3, assets: Assets | None = None) -> pd.DataFrame:
    from .design.domain import DomainIndex
    assets = assets or Assets(cfg)
    real = load_static_curves(cfg.db_path)
    feats = pd.read_parquet(cfg.data_dir / "features.parquet")
    feats = feats[feats.mix_uid.isin(set(real.mix_uid))].reset_index(drop=True)
    if feats.empty:
        return real.iloc[0:0]
    di = DomainIndex(k=min(10, len(feats))).fit(feats)
    F, _ = featurize_specs([spec], assets)
    d, idx = di.neighbors(F, k=min(k, len(feats)))
    picks = feats.iloc[idx[0]][["mix_uid"]].assign(distance=d[0])
    return real[real.mix_uid.isin(picks.mix_uid)].merge(picks, on="mix_uid").sort_values(["distance", "curve_uid", "t_s"])


def plot_static_curve(curve: pd.DataFrame, analogues: pd.DataFrame | None = None, title: str = "", log_y: bool = True,
                      show_physical: bool = True):
    import matplotlib
    matplotlib.use("Agg")
    ko = _korean_font()
    import matplotlib.pyplot as plt
    L = (dict(phys="예측 τ_s(0)+Athix·t, 80 % 밴드", model="참고: 정적항복 모델 스윕 (기울기 과소)", lit="문헌", x="휴지시간 (min)", y="정적항복응력 τ_s (Pa)",
              t="구조화 곡선 예측 (정적항복응력 – 휴지시간)")
         if ko else dict(phys="prediction tau0+Athix*t, 80 % band", model="reference: static-model sweep (slope too flat)", lit="published",
                         x="rest time (min)", y="static yield stress (Pa)", t="structuration curve prediction"))
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=120)
    B = curve[curve.route == "physical"]
    A = curve[curve.route == "model"]
    P = B if len(B) else A
    ax.fill_between(P.rest_s / 60, P.q10, P.q90, color="#2563eb", alpha=0.18, label=L["phys"] if len(B) else L["model"])
    ax.plot(P.rest_s / 60, P.q50, color="#2563eb", lw=2.2)
    if show_physical and len(B) and len(A):
        ax.plot(A.rest_s / 60, A.q50, color="#9333ea", lw=1.4, ls=":", label=L["model"])
    if analogues is not None and len(analogues):
        cmap = plt.get_cmap("Set2"); seen: dict[str, int] = {}
        for cu, g in analogues.groupby("curve_uid", sort=False):
            g = g.sort_values("t_s"); mix = g.mix_uid.iloc[0]; first = mix not in seen; seen.setdefault(mix, len(seen)); i = seen[mix]
            lbl = f"{L['lit']} {mix.split('::')[0]} · {mix.split('::')[-1]} (d={g.distance.iloc[0]:.2f})" if first and i < 6 else None
            ax.plot(g.t_s / 60, g.tau, "o--", ms=4, lw=1.2, color=cmap(i % 8), label=lbl)
    ax.set_xlabel(L["x"]); ax.set_ylabel(L["y"])
    if log_y:
        ax.set_yscale("log")
    ax.set_title(title or L["t"], fontsize=11); ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=7.5, loc="upper left")
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- validation
def validate_oof(cfg: PipelineConfig) -> dict:
    """Leakage-free check of the physical route: tau_s(t) = tau_s0 + Athix * t with OUT-OF-FOLD (GroupKFold) Athix per mix
    and the fitted intercept of the real curve (so the slope is what is being tested), compared with the digitised points."""
    real = load_static_curves(cfg.db_path)
    fits = fit_athix(real)
    oof = pd.read_parquet(cfg.reports_dir / "oof_structuration_rate_athix.parquet")
    a = oof.groupby("mix_uid")[["pred", "q10", "q90"]].median()
    j = fits.merge(a, left_on="mix_uid", right_index=True)
    j = j[(j.athix > 0) & (j.pred > 0)]
    if j.empty:
        return dict(n_mixes=0)
    rows = []
    for r in j.itertuples(index=False):
        g = real[real.curve_uid == r.curve_uid].sort_values("t_s")
        y = g.tau.to_numpy(); t = g.t_s.to_numpy()
        pred = r.tau0 + r.pred * t
        lo = r.tau0 + r.q10 * t; hi = r.tau0 + r.q90 * t
        ok = (y > 0) & (pred > 0)
        rows.append(dict(mix_uid=r.mix_uid, paper_uid=r.paper_uid, athix_fit=r.athix, athix_oof=r.pred,
                         abs_log10_err=float(np.mean(np.abs(np.log10(pred[ok] / y[ok])))) if ok.any() else np.nan,
                         coverage80=float(np.mean((y >= np.minimum(lo, hi)) & (y <= np.maximum(lo, hi))))))
    R = pd.DataFrame(rows)
    R.to_csv(cfg.reports_dir / "static_curve_validation_oof.csv", index=False)
    lr = np.log10(R.athix_oof / R.athix_fit)
    return dict(n_mixes=int(len(R)), n_papers=int(R.paper_uid.nunique()),
                athix_oof_vs_fit_spearman=float(R.athix_oof.corr(R.athix_fit, method="spearman")) if len(R) > 3 else None,
                athix_oof_log10_ratio_median=float(lr.median()), athix_oof_within_factor3=float((lr.abs() <= np.log10(3)).mean()),
                curve_abs_log10_err_median=float(R.abs_log10_err.median()), coverage80=float(R.coverage80.mean()))


def validate_against_curves(cfg: PipelineConfig, max_mixes: int | None = None) -> dict:
    """For mixes with a digitised static-yield/rest-time curve: rebuild the mix as a MixSpec, sweep the model over the
    curve's rest times and compare (a) the model-implied structuration rate with the fitted Athix and (b) point-wise error.
    The static model saw these mixes' *tabulated* values (in-sample for the level); the curve points themselves were
    never used for training."""
    from .db import load_tables
    from .features import build_context
    from .reconstruct import spec_from_db
    real = load_static_curves(cfg.db_path)
    fits = fit_athix(real)
    comp = pd.read_parquet(cfg.data_dir / "composition.parquet")
    long = pd.read_parquet(cfg.data_dir / "composition_long.parquet")
    ctx = build_context(load_tables(cfg, tables=["mixes", "papers"]))
    assets = Assets(cfg)
    rows = []
    uids = [u for u in fits.mix_uid.unique() if u in set(comp.mix_uid) and comp.set_index("mix_uid").loc[u, "water_b"] == comp.set_index("mix_uid").loc[u, "water_b"]]
    if max_mixes:
        uids = uids[:max_mixes]
    for uid in uids:
        g = real[real.mix_uid == uid].sort_values("t_s")
        f = fits[fits.mix_uid == uid].iloc[0]
        try:
            spec = spec_from_db(uid, comp, long, ctx)
            spec.validate()
            curve, info = predict_static_curve(spec, cfg, rest_s=g.t_s.to_numpy(), assets=assets)
        except Exception as e:  # pragma: no cover
            continue
        A = curve[curve.route == "model"]
        pred, lo, hi, y = A.q50.to_numpy(), A.q10.to_numpy(), A.q90.to_numpy(), g.tau.to_numpy()
        rows.append(dict(mix_uid=uid, paper_uid=f.paper_uid, n_pts=len(y), athix_fit=f.athix, athix_model_implied=info["athix_implied_model"],
                         athix_model_direct=(info.get("athix_model") or (np.nan,) * 3)[1],
                         abs_log10_err=float(np.mean(np.abs(np.log10(np.maximum(pred, 1e-9) / y)))),
                         coverage80=float(np.mean((y >= lo) & (y <= hi))), growth_real=float(y[-1] / max(y[0], 1e-9)),
                         growth_model=float(pred[-1] / max(pred[0], 1e-9))))
    R = pd.DataFrame(rows)
    R.to_csv(cfg.reports_dir / "static_curve_validation.csv", index=False)
    if R.empty:
        return dict(n_mixes=0)
    pos = R[(R.athix_fit > 0) & (R.athix_model_implied > 0)]
    posd = R[(R.athix_fit > 0) & (R.athix_model_direct > 0)]
    return dict(n_mixes=int(len(R)), n_papers=int(R.paper_uid.nunique()),
                abs_log10_err_median=float(R.abs_log10_err.median()), coverage80=float(R.coverage80.mean()),
                growth_real_median=float(R.growth_real.median()), growth_model_median=float(R.growth_model.median()),
                athix_model_implied_vs_fit_spearman=float(pos.athix_model_implied.corr(pos.athix_fit, method="spearman")) if len(pos) > 3 else None,
                athix_model_implied_log10_ratio_median=float(np.log10(pos.athix_model_implied / pos.athix_fit).median()) if len(pos) else None,
                athix_direct_model_vs_fit_spearman=float(posd.athix_model_direct.corr(posd.athix_fit, method="spearman")) if len(posd) > 3 else None,
                athix_direct_log10_ratio_median=float(np.log10(posd.athix_model_direct / posd.athix_fit).median()) if len(posd) else None)
