"""Applicability domain: kNN distance of a candidate to a model's training mixes in
standardised composition-feature space (score <= 1 means 'as close as 95 % of training points')."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

from ..composition import ACT_GROUPS, ADMIX_GROUPS, AGG_GROUPS, FIBRE_GROUPS, NANO_GROUPS, POWDER_GROUPS

COMP_FEATURES = ([f"pw_{g}" for g in POWDER_GROUPS] + ["water_b", "sand_b", "cement_share", "filler_frac", "sp_solid_pct",
                                                        "vma_solid_pct", "fibre_total_vol_pct", "act_total_b", "act_na2o_pct",
                                                        "act_sio2_pct", "nano_total_pct"]
                 + [f"agg_{g}" for g in AGG_GROUPS] + [f"adx_{g}_pct" for g in ADMIX_GROUPS])


class DomainIndex:
    def __init__(self, k: int = 10, ref_quantile: float = 0.95):
        self.k = k
        self.ref_quantile = ref_quantile
        self.cols: list[str] = []
        self.mu = None; self.sd = None; self.ref = 1.0
        self.nn: NearestNeighbors | None = None
        self.mins = None; self.maxs = None
        self.n_train = 0

    def _matrix(self, X: pd.DataFrame) -> np.ndarray:
        A = X.reindex(columns=self.cols).astype(float).to_numpy()
        A = np.where(np.isnan(A), self.mu, A)
        return (A - self.mu) / self.sd

    def fit(self, X: pd.DataFrame, cols: list[str] | None = None) -> "DomainIndex":
        self.cols = [c for c in (cols or COMP_FEATURES) if c in X.columns]
        A = X[self.cols].astype(float)
        self.mu = np.nan_to_num(A.mean().to_numpy(), nan=0.0)
        sd = A.std().to_numpy()
        self.sd = np.where(np.isfinite(sd) & (sd > 1e-9), sd, 1.0)
        self.mins = A.min().to_numpy(); self.maxs = A.max().to_numpy()
        Z = self._matrix(A)
        self.n_train = len(Z)
        k = min(self.k + 1, len(Z))
        self.nn = NearestNeighbors(n_neighbors=k).fit(Z)
        d, _ = self.nn.kneighbors(Z)
        d_loo = d[:, 1:].mean(axis=1) if k > 1 else d[:, 0]
        self.ref = float(max(np.quantile(d_loo, self.ref_quantile), 1e-6))
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        Z = self._matrix(X)
        k = min(self.k, self.n_train)
        d, _ = self.nn.kneighbors(Z, n_neighbors=k)
        return d.mean(axis=1) / self.ref

    def neighbors(self, X: pd.DataFrame, k: int = 3) -> tuple[np.ndarray, np.ndarray]:
        Z = self._matrix(X)
        d, idx = self.nn.kneighbors(Z, n_neighbors=min(k, self.n_train))
        return d / self.ref, idx

    def range_violation(self, X: pd.DataFrame) -> np.ndarray:
        A = X.reindex(columns=self.cols).astype(float).to_numpy()
        return ((A < self.mins - 1e-9) | (A > self.maxs + 1e-9)).sum(axis=1)

    def save(self, path: Path) -> None:
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> "DomainIndex":
        return joblib.load(path)


def domain_for_model(model_dir: Path, features: pd.DataFrame, rebuild: bool = False) -> DomainIndex:
    """Load (or build and cache) the applicability-domain index of one trained model."""
    p = Path(model_dir) / "domain.joblib"
    if p.exists() and not rebuild:
        return DomainIndex.load(p)
    uids = (Path(model_dir) / "train_mix_uids.txt").read_text(encoding="utf-8").split()
    sub = features[features["mix_uid"].isin(set(uids))]
    di = DomainIndex().fit(sub)
    di.save(p)
    return di
