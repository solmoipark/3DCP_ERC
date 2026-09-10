"""Leakage-safe evaluation: GroupKFold by paper, metrics on the original scale,
interval calibration, slices, leakage check and feature importance."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold, KFold

from .models import (TRANSFORMS, Baseline, conformal_scale_from_oof, fit_with_early_stopping, make_lgbm,
                     model_defaults, prepare_X)

log = logging.getLogger("pmpredict.evaluate")


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    if len(y) < 3:
        return dict(n=int(len(y)), rmse=np.nan, mae=np.nan, r2=np.nan, medape=np.nan, spearman=np.nan)
    resid = y - p
    ss = np.sum((y - y.mean()) ** 2)
    return dict(
        n=int(len(y)),
        rmse=float(np.sqrt(np.mean(resid ** 2))),
        mae=float(np.mean(np.abs(resid))),
        r2=float(1 - np.sum(resid ** 2) / ss) if ss > 0 else np.nan,
        medape=float(np.median(np.abs(resid) / np.maximum(np.abs(y), 1e-9))),
        spearman=float(spearmanr(y, p).statistic) if len(y) > 5 else np.nan,
    )


def cross_validate_target(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, w: np.ndarray | None,
                          params: dict, transform: str, seed: int, feature_names: list[str],
                          cat_levels: dict, n_splits: int = 5, defaults: dict | None = None,
                          baselines: bool = True, random_kfold: bool = False) -> dict:
    """Return OOF predictions and summary metrics for one target."""
    d = defaults or model_defaults()
    qlo, qhi = d.get("quantiles", [0.10, 0.90])
    fwd, inv = TRANSFORMS[transform]
    yt = fwd(y)
    Xp = prepare_X(X, feature_names, cat_levels)
    n = len(y)
    mu = np.full(n, np.nan); lo = np.full(n, np.nan); hi = np.full(n, np.nan)
    ridge = np.full(n, np.nan); knn = np.full(n, np.nan)
    best_iters = []
    splitter = KFold(n_splits, shuffle=True, random_state=seed) if random_kfold else \
        GroupKFold(n_splits, shuffle=True, random_state=seed)
    for k, (tr, te) in enumerate(splitter.split(Xp, yt, groups)):
        wtr = None if w is None else w[tr]
        point, best = fit_with_early_stopping(params, Xp.iloc[tr], yt[tr], wtr, groups[tr], seed + k, defaults=d)
        best_iters.append(best)
        p = dict(params, n_estimators=best)
        ql = make_lgbm(p, seed + k + 1, "quantile", qlo).fit(Xp.iloc[tr], yt[tr], sample_weight=wtr)
        qh = make_lgbm(p, seed + k + 2, "quantile", qhi).fit(Xp.iloc[tr], yt[tr], sample_weight=wtr)
        mu[te] = point.predict(Xp.iloc[te]); lo[te] = ql.predict(Xp.iloc[te]); hi[te] = qh.predict(Xp.iloc[te])
        if baselines:
            ridge[te] = Baseline("ridge", feature_names, cat_levels, transform).fit(X.iloc[tr], y[tr], wtr).predict(X.iloc[te])
            knn[te] = Baseline("knn", feature_names, cat_levels, transform).fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
        log.info("fold %d done (best_iter=%d)", k, best)
    scale = conformal_scale_from_oof(yt, mu, lo, hi, d.get("interval_coverage", 0.80))
    lo_c = mu - np.maximum(mu - lo, 0) * scale
    hi_c = mu + np.maximum(hi - mu, 0) * scale
    pred = inv(mu)
    oof = pd.DataFrame(dict(y=y, pred=pred, q10=inv(np.minimum(lo_c, mu)), q90=inv(np.maximum(hi_c, mu)),
                            q10_raw=inv(np.minimum(lo, mu)), q90_raw=inv(np.maximum(hi, mu)),
                            ridge=ridge, knn=knn), index=X.index)
    m = metrics(y, pred)
    m.update(
        coverage_raw=float(np.mean((y >= oof.q10_raw) & (y <= oof.q90_raw))),
        coverage_conformal=float(np.mean((y >= oof.q10) & (y <= oof.q90))),
        rel_width=float(np.nanmedian((oof.q90 - oof.q10) / np.maximum(np.abs(pred), 1e-9))),
        conformal_scale=scale, best_iter_median=int(np.median(best_iters)),
        rmse_t=float(np.sqrt(np.nanmean((yt - mu) ** 2))), r2_t=metrics(yt, mu)["r2"],
    )
    if baselines:
        m["ridge_r2"] = metrics(y, ridge)["r2"]; m["ridge_rmse"] = metrics(y, ridge)["rmse"]
        m["knn_r2"] = metrics(y, knn)["r2"]
    return dict(oof=oof, metrics=m, best_iters=best_iters, conformal_scale=scale)


def slice_metrics(oof: pd.DataFrame, meta: pd.DataFrame, by: str, min_n: int = 20) -> pd.DataFrame:
    rows = []
    col = meta[by]
    for lvl, idx in meta.groupby(col, observed=True, dropna=False).groups.items():
        sub = oof.loc[idx]
        if len(sub) < min_n:
            continue
        mm = metrics(sub.y, sub.pred)
        mm.update(slice=by, level=str(lvl), coverage=float(np.mean((sub.y >= sub.q10) & (sub.y <= sub.q90))))
        rows.append(mm)
    return pd.DataFrame(rows)


def gain_importance(model, feature_names: list[str], top: int = 30) -> pd.DataFrame:
    imp = pd.Series(model.booster_.feature_importance(importance_type="gain"), index=feature_names)
    imp = imp / imp.sum() if imp.sum() > 0 else imp
    return imp.sort_values(ascending=False).head(top).rename("gain_share").reset_index().rename(columns={"index": "feature"})
