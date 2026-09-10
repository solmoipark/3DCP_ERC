"""Model bundle per target: LightGBM point + quantile models, conformal scaling,
paper-bootstrap ensemble, and simple baselines.

The bundle exposes the contract consumed by ``predict`` and the inverse layer::

    predict_quantiles(X) -> DataFrame[q10, q50, q90]   (original units)
    predict_std(X)       -> ndarray                    (original units, epistemic)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import load_yaml

log = logging.getLogger("pmpredict.models")

TRANSFORMS = {
    "log": (lambda y: np.log(np.clip(y, 1e-6, None)), np.exp),
    "log1p": (np.log1p, np.expm1),
    "none": (lambda y: np.asarray(y, dtype=float), lambda y: np.asarray(y, dtype=float)),
}
Z80 = 1.2816  # normal quantile for 10 % / 90 %


def model_defaults() -> dict:
    return load_yaml("model_defaults.yaml")


def param_tier(n_rows: int, n_papers: int, defaults: dict | None = None) -> tuple[str, dict]:
    d = defaults or model_defaults()
    tiers = d["tiers"]
    if n_papers < d.get("small_paper_threshold", 30) or n_rows < tiers["medium"]["min_rows"]:
        return "small", dict(tiers["small"]["params"])
    if n_rows >= tiers["large"]["min_rows"]:
        return "large", dict(tiers["large"]["params"])
    return "medium", dict(tiers["medium"]["params"])


def make_lgbm(params: dict, seed: int, objective: str = "regression", alpha: float | None = None) -> lgb.LGBMRegressor:
    p = dict(params)
    p.update(objective=objective, random_state=seed, verbose=-1, deterministic=True, force_row_wise=True,
             n_jobs=0)
    if alpha is not None:
        p["alpha"] = alpha
    return lgb.LGBMRegressor(**p)


def prepare_X(X: pd.DataFrame, feature_names: list[str], cat_levels: dict[str, list[str]]) -> pd.DataFrame:
    """Select/order columns and pin categorical levels (unseen -> NaN)."""
    out = pd.DataFrame(index=X.index)
    for c in feature_names:
        if c in cat_levels:
            vals = X[c].astype("object") if c in X.columns else pd.Series([None] * len(X), index=X.index)
            out[c] = pd.Categorical(vals, categories=cat_levels[c])
        else:
            out[c] = pd.to_numeric(X[c], errors="coerce").astype(float) if c in X.columns else np.nan
    return out


# ------------------------------------------------------------- bundle
@dataclass
class TargetModel:
    target: str
    unit: str
    transform: str
    feature_names: list[str]
    cat_levels: dict[str, list[str]]
    point: lgb.LGBMRegressor
    q_lo: lgb.LGBMRegressor
    q_hi: lgb.LGBMRegressor
    ensemble: list = field(default_factory=list)
    conformal_scale: float = 1.0
    meta: dict = field(default_factory=dict)

    # ---- prediction
    def _X(self, X: pd.DataFrame) -> pd.DataFrame:
        return prepare_X(X, self.feature_names, self.cat_levels)

    def predict_transformed(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        Xp = self._X(X)
        mu = self.point.predict(Xp)
        lo = self.q_lo.predict(Xp)
        hi = self.q_hi.predict(Xp)
        # centre the interval on the point prediction, apply conformal scale, enforce ordering
        lo_w = np.maximum(mu - lo, 0.0) * self.conformal_scale
        hi_w = np.maximum(hi - mu, 0.0) * self.conformal_scale
        return mu - lo_w, mu, mu + hi_w

    def predict_quantiles(self, X: pd.DataFrame) -> pd.DataFrame:
        lo, mu, hi = self.predict_transformed(X)
        inv = TRANSFORMS[self.transform][1]
        q = np.sort(np.column_stack([inv(lo), inv(mu), inv(hi)]), axis=1)
        return pd.DataFrame(q, columns=["q10", "q50", "q90"], index=X.index)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.predict_quantiles(X)["q50"].to_numpy()

    def predict_std(self, X: pd.DataFrame) -> np.ndarray:
        """Epistemic std (original units) from the paper-bootstrap ensemble."""
        if not self.ensemble:
            return np.full(len(X), np.nan)
        Xp = self._X(X)
        P = np.column_stack([m.predict(Xp) for m in self.ensemble])
        inv = TRANSFORMS[self.transform][1]
        return inv(P).std(axis=1, ddof=1)

    # ---- persistence
    def save(self, d: Path) -> None:
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(dict(point=self.point, q_lo=self.q_lo, q_hi=self.q_hi, ensemble=self.ensemble), d / "model.joblib")
        meta = dict(self.meta)
        meta.update(target=self.target, unit=self.unit, transform=self.transform, feature_names=self.feature_names,
                    cat_levels=self.cat_levels, conformal_scale=self.conformal_scale)
        (d / "meta.json").write_text(json.dumps(meta, indent=1, default=_json_default), encoding="utf-8")

    @classmethod
    def load(cls, d: Path) -> "TargetModel":
        d = Path(d)
        parts = joblib.load(d / "model.joblib")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        return cls(target=meta["target"], unit=meta["unit"], transform=meta["transform"],
                   feature_names=meta["feature_names"], cat_levels=meta["cat_levels"],
                   point=parts["point"], q_lo=parts["q_lo"], q_hi=parts["q_hi"], ensemble=parts.get("ensemble", []),
                   conformal_scale=float(meta.get("conformal_scale", 1.0)), meta=meta)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ------------------------------------------------------------- fitting
def fit_with_early_stopping(params: dict, X: pd.DataFrame, y: np.ndarray, w: np.ndarray | None,
                            groups: np.ndarray, seed: int, objective: str = "regression",
                            alpha: float | None = None, defaults: dict | None = None) -> tuple[lgb.LGBMRegressor, int]:
    """Fit with an inner group-held-out validation split for early stopping; refit on all rows."""
    from sklearn.model_selection import GroupShuffleSplit
    d = defaults or model_defaults()
    gss = GroupShuffleSplit(n_splits=1, test_size=d.get("inner_val_fraction", 0.1), random_state=seed)
    tr, va = next(gss.split(X, y, groups))
    m = make_lgbm(params, seed, objective, alpha)
    m.fit(X.iloc[tr], y[tr], sample_weight=None if w is None else w[tr],
          eval_set=[(X.iloc[va], y[va])], eval_sample_weight=None if w is None else [w[va]],
          callbacks=[lgb.early_stopping(d.get("early_stopping_rounds", 50), verbose=False)])
    best = int(m.best_iteration_ or params.get("n_estimators", 500))
    best = max(best, 30)
    p = dict(params, n_estimators=best)
    final = make_lgbm(p, seed, objective, alpha)
    final.fit(X, y, sample_weight=w)
    return final, best


def fit_bundle(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, w: np.ndarray | None, params: dict,
               transform: str, seed: int, n_boot: int = 10, best_iter: int | None = None,
               defaults: dict | None = None) -> tuple[lgb.LGBMRegressor, lgb.LGBMRegressor, lgb.LGBMRegressor, list, int]:
    """Fit point, q10, q90 and a paper-bootstrap ensemble on transformed y."""
    d = defaults or model_defaults()
    qlo, qhi = d.get("quantiles", [0.10, 0.90])
    yt = TRANSFORMS[transform][0](y)
    if best_iter is None:
        point, best_iter = fit_with_early_stopping(params, X, yt, w, groups, seed, defaults=d)
    else:
        point = make_lgbm(dict(params, n_estimators=best_iter), seed)
        point.fit(X, yt, sample_weight=w)
    p = dict(params, n_estimators=best_iter)
    q_lo = make_lgbm(p, seed + 1, "quantile", qlo); q_lo.fit(X, yt, sample_weight=w)
    q_hi = make_lgbm(p, seed + 2, "quantile", qhi); q_hi.fit(X, yt, sample_weight=w)
    ens = []
    rng = np.random.default_rng(seed)
    upapers = np.unique(groups)
    for b in range(n_boot):
        samp = rng.choice(upapers, size=len(upapers), replace=True)
        idx = np.concatenate([np.flatnonzero(groups == pu) for pu in samp])
        m = make_lgbm(p, seed + 100 + b)
        m.fit(X.iloc[idx], yt[idx], sample_weight=None if w is None else w[idx])
        ens.append(m)
    return point, q_lo, q_hi, ens, best_iter


def conformal_scale_from_oof(y_t: np.ndarray, mu: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                             coverage: float = 0.80) -> float:
    """Smallest scale s such that [mu - s(mu-lo), mu + s(hi-mu)] covers `coverage` of y (transformed)."""
    lo_w = np.maximum(mu - lo, 1e-9)
    hi_w = np.maximum(hi - mu, 1e-9)
    r = np.where(y_t < mu, (mu - y_t) / lo_w, (y_t - mu) / hi_w)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return 1.0
    return float(max(np.quantile(r, coverage), 0.25))


# ------------------------------------------------------------- baselines
def _tabular_pipe(estimator, feature_names: list[str], cat_levels: dict[str, list[str]]):
    num = [c for c in feature_names if c not in cat_levels]
    cat = [c for c in feature_names if c in cat_levels]
    ct = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
    ])
    return Pipeline([("ct", ct), ("est", estimator)])


class Baseline:
    """Ridge / kNN baseline sharing the TargetModel feature contract."""

    def __init__(self, kind: str, feature_names: list[str], cat_levels: dict[str, list[str]], transform: str):
        self.kind, self.feature_names, self.cat_levels, self.transform = kind, feature_names, cat_levels, transform
        est = RidgeCV(alphas=np.logspace(-2, 3, 12)) if kind == "ridge" else KNeighborsRegressor(n_neighbors=10, weights="distance")
        self.pipe = _tabular_pipe(est, feature_names, cat_levels)

    def fit(self, X: pd.DataFrame, y: np.ndarray, w: np.ndarray | None = None):
        Xp = prepare_X(X, self.feature_names, self.cat_levels)
        for c in self.cat_levels:
            Xp[c] = Xp[c].astype("object").fillna("unknown")
        yt = TRANSFORMS[self.transform][0](y)
        # linear models extrapolate wildly on outlying standardised features: clip to the training range
        self._lo, self._hi = float(np.min(yt)), float(np.max(yt))
        if self.kind == "ridge" and w is not None:
            self.pipe.fit(Xp, yt, est__sample_weight=w)
        else:
            self.pipe.fit(Xp, yt)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        Xp = prepare_X(X, self.feature_names, self.cat_levels)
        for c in self.cat_levels:
            Xp[c] = Xp[c].astype("object").fillna("unknown")
        p = np.clip(self.pipe.predict(Xp), self._lo, self._hi)
        return TRANSFORMS[self.transform][1](p)
