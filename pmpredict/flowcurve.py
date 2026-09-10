"""Flow-curve (shear rate -> shear stress) prediction from Bingham parameters.

tau(gamma_dot) = tau0 + mu * gamma_dot, with tau0 from the dynamic_yield_stress model and mu from the
plastic_viscosity model. Uncertainty bands come from sampling both predictive distributions
(split-normal on the log scale, treated as independent). Real digitised curves of the nearest
published analogues can be overlaid for context.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .config import PipelineConfig
from .curves import load_flow_curves
from .design.uncertainty import Z80
from .predict import Assets, add_covariates, featurize_specs
from .schema import MixSpec

DEFAULT_RATES = np.concatenate([[0.0], np.geomspace(0.5, 150.0, 40)])


def _sample_lognormal_split(q10: float, q50: float, q90: float, n: int, rng) -> np.ndarray:
    """Samples from a split-normal on log10 scale defined by three quantiles (values > 0)."""
    l10, l50, l90 = np.log10(max(q10, 1e-9)), np.log10(max(q50, 1e-9)), np.log10(max(q90, 1e-9))
    s_lo = max((l50 - l10) / Z80, 1e-6)
    s_hi = max((l90 - l50) / Z80, 1e-6)
    z = rng.standard_normal(n)
    return 10 ** (l50 + np.where(z < 0, s_lo, s_hi) * z)


def predict_bingham(specs: list[MixSpec], cfg: PipelineConfig, assets: Assets | None = None) -> pd.DataFrame:
    """Per spec: q10/q50/q90 of tau0 [Pa] and mu [Pa.s] plus model metadata."""
    assets = assets or Assets(cfg)
    F, warns = featurize_specs(specs, assets)
    rows = []
    for si, spec in enumerate(specs):
        r = dict(spec=spec.name or f"mix{si}")
        for key, tgt in (("tau0", "dynamic_yield_stress"), ("mu", "plastic_viscosity")):
            m = assets.model(tgt)
            X = add_covariates(F.iloc[[si]], [spec], m.meta.get("covariates", []))
            q = m.predict_quantiles(X).iloc[0]
            r[f"{key}_q10"], r[f"{key}_q50"], r[f"{key}_q90"] = float(q.q10), float(q.q50), float(q.q90)
            r[f"{key}_weak"] = bool(assets.manifest["models"][tgt].get("weak_model", False))
        rows.append(r)
    return pd.DataFrame(rows)


def bingham_band(tau0_q: tuple[float, float, float], mu_q: tuple[float, float, float], rates=DEFAULT_RATES,
                 n: int = 4000, seed: int = 0) -> pd.DataFrame:
    """Predicted flow curve with q10/q50/q90 bands (independent sampling of tau0 and mu)."""
    rng = np.random.default_rng(seed)
    t = _sample_lognormal_split(*tau0_q, n, rng)
    m = _sample_lognormal_split(*mu_q, n, rng)
    rates = np.asarray(rates, float)
    tau = t[:, None] + m[:, None] * rates[None, :]
    return pd.DataFrame(dict(shear_rate=rates, q10=np.quantile(tau, 0.10, axis=0), q50=np.quantile(tau, 0.50, axis=0),
                             q90=np.quantile(tau, 0.90, axis=0),
                             median_line=np.median(t) + np.median(m) * rates))


def predict_flow_curves(specs: list[MixSpec], cfg: PipelineConfig, rates=DEFAULT_RATES, assets: Assets | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (bingham parameter table, long curve table with spec / shear_rate / q10 / q50 / q90)."""
    P = predict_bingham(specs, cfg, assets)
    parts = []
    for r in P.itertuples(index=False):
        b = bingham_band((r.tau0_q10, r.tau0_q50, r.tau0_q90), (r.mu_q10, r.mu_q50, r.mu_q90), rates)
        b.insert(0, "spec", r.spec)
        parts.append(b)
    return P, pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------- real curves
def real_flow_curves(cfg: PipelineConfig, mix_uids: list[str] | None = None) -> pd.DataFrame:
    """Digitised flow-curve points (shear_rate [1/s], shear_stress [Pa]) for the given mixes (or all)."""
    c, p = load_flow_curves(cfg.db_path)
    if mix_uids is not None:
        c = c[c.mix_uid.isin(set(mix_uids))]
    p = p[p.curve_uid.isin(c.curve_uid)].merge(c[["curve_uid", "mix_uid", "paper_uid", "y_quantity", "y_unit"]], on="curve_uid")
    vis = p.y_quantity == "apparent_viscosity"
    fac = np.where(p.y_unit.astype(str).str.lower().str.startswith("mpa"), 0.001, 1.0)
    p["shear_stress"] = np.where(vis, p.y * fac * p.x, p.y)
    p = p[(p.x >= 0) & (p.shear_stress > 0)]
    return p[["curve_uid", "mix_uid", "paper_uid", "x", "shear_stress"]].rename(columns={"x": "shear_rate"})


# ------------------------------------------------------------- analogues & plot
def analogue_curves(spec: MixSpec, cfg: PipelineConfig, k: int = 3, assets: Assets | None = None) -> pd.DataFrame:
    """Real flow curves of the k nearest published mixes (composition space) that have a digitised curve."""
    from .design.domain import DomainIndex
    assets = assets or Assets(cfg)
    real = real_flow_curves(cfg)
    feats = pd.read_parquet(cfg.data_dir / "features.parquet")
    feats = feats[feats.mix_uid.isin(set(real.mix_uid))].reset_index(drop=True)
    if feats.empty:
        return real.iloc[0:0]
    di = DomainIndex(k=min(10, len(feats))).fit(feats)
    F, _ = featurize_specs([spec], assets)
    d, idx = di.neighbors(F, k=min(k, len(feats)))
    picks = feats.iloc[idx[0]][["mix_uid", "paper_uid"]].assign(distance=d[0])
    out = real[real.mix_uid.isin(picks.mix_uid)].merge(picks[["mix_uid", "distance"]], on="mix_uid")
    return out.sort_values(["distance", "curve_uid", "shear_rate"])


def _korean_font() -> bool:
    """Select a CJK-capable font if one is installed; return True when Korean labels are safe."""
    import matplotlib
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "AppleGothic", "Gulim", "Batang"):
        if cand in names:
            matplotlib.rcParams["font.family"] = [cand, "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True
    return False


def plot_flow_curve(band: pd.DataFrame, analogues: pd.DataFrame | None = None, title: str = "", log_y: bool = False):
    import matplotlib
    matplotlib.use("Agg")
    ko = _korean_font()
    import matplotlib.pyplot as plt
    L = (dict(band="예측 80 % 밴드", med="예측 (중앙)", lit="문헌", x="전단속도 γ̇ (1/s)", y="전단응력 τ (Pa)", t="예측 flow curve (Bingham: τ = τ₀ + μ·γ̇)")
         if ko else dict(band="predicted 80 % band", med="prediction (median)", lit="published", x="shear rate (1/s)",
                         y="shear stress (Pa)", t="predicted flow curve (Bingham)"))
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=120)
    ax.fill_between(band.shear_rate, band.q10, band.q90, color="#2563eb", alpha=0.18, label=L["band"])
    ax.plot(band.shear_rate, band.q50, color="#2563eb", lw=2.2, label=L["med"])
    if analogues is not None and len(analogues):
        cmap = plt.get_cmap("Set2")
        seen_mix: dict[str, int] = {}
        for cu, g in analogues.groupby("curve_uid", sort=False):
            g = g.sort_values("shear_rate")
            mix = g.mix_uid.iloc[0]
            first = mix not in seen_mix
            seen_mix.setdefault(mix, len(seen_mix))
            i = seen_mix[mix]
            lbl = f"{L['lit']} {mix.split('::')[0]} · {mix.split('::')[-1]} (d={g.distance.iloc[0]:.2f})" if first and i < 6 else None
            ax.plot(g.shear_rate, g.shear_stress, "o--", ms=4, lw=1.2, color=cmap(i % 8), label=lbl)
    ax.set_xlabel(L["x"]); ax.set_ylabel(L["y"])
    if log_y:
        ax.set_yscale("log")
    ax.set_title(title or L["t"], fontsize=11)
    ax.grid(alpha=0.3); ax.legend(fontsize=7.5, loc="upper left")
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- validation
def validate_against_curves(cfg: PipelineConfig) -> dict:
    """Leakage-free check: out-of-fold (GroupKFold) tau0 / mu per mix -> predicted Bingham line vs the
    digitised points of that mix's real flow curve(s)."""
    oof_t = pd.read_parquet(cfg.reports_dir / "oof_dynamic_yield_stress.parquet")
    oof_m = pd.read_parquet(cfg.reports_dir / "oof_plastic_viscosity.parquet")
    t = oof_t.groupby("mix_uid")[["pred", "q10", "q90"]].median().rename(columns=lambda c: f"tau0_{c}")
    m = oof_m.groupby("mix_uid")[["pred", "q10", "q90"]].median().rename(columns=lambda c: f"mu_{c}")
    real = real_flow_curves(cfg)
    j = real.merge(t, left_on="mix_uid", right_index=True).merge(m, left_on="mix_uid", right_index=True)
    if j.empty:
        return dict(n_points=0)
    rng = np.random.default_rng(0)
    rows = []
    for uid, g in j.groupby("mix_uid"):
        r = g.iloc[0]
        b = bingham_band((r.tau0_q10, r.tau0_pred, r.tau0_q90), (r.mu_q10, r.mu_pred, r.mu_q90), g.shear_rate.to_numpy(), n=2000)
        pred50 = b.q50.to_numpy(); lo = b.q10.to_numpy(); hi = b.q90.to_numpy()
        y = g.shear_stress.to_numpy()
        ok = y > 0
        rows.append(dict(mix_uid=uid, paper_uid=r.paper_uid, n_pts=int(ok.sum()),
                         mean_abs_log10_err=float(np.mean(np.abs(np.log10(pred50[ok] / y[ok])))),
                         median_ratio=float(np.median(pred50[ok] / y[ok])),
                         coverage80=float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))),
                         spearman_shape=float(pd.Series(pred50[ok]).corr(pd.Series(y[ok]), method="spearman")) if ok.sum() > 3 else np.nan))
    R = pd.DataFrame(rows)
    # baseline: a single global median curve (no composition information)
    gt, gm = float(oof_t.y.median()), float(oof_m.y.median())
    base = np.mean(np.abs(np.log10((gt + gm * j.shear_rate) / j.shear_stress)))
    rep = dict(n_mixes=int(len(R)), n_papers=int(R.paper_uid.nunique()), n_points=int(R.n_pts.sum()),
               mean_abs_log10_err=float(R.mean_abs_log10_err.mean()), median_abs_log10_err=float(R.mean_abs_log10_err.median()),
               within_factor2_share=float((R.mean_abs_log10_err <= np.log10(2)).mean()),
               coverage80=float(np.average(R.coverage80, weights=R.n_pts)), median_ratio=float(R.median_ratio.median()),
               baseline_global_median_curve_abs_log10_err=float(base))
    R.to_csv(cfg.reports_dir / "flow_curve_validation.csv", index=False)
    return rep
