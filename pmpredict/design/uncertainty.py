"""Predictive distributions from (q10, q50, q90) and probabilistic constraint satisfaction."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

Z80 = float(norm.ppf(0.9))  # Phi^-1(0.9) = 1.28155...


@dataclass
class PredDist:
    """Split-normal distribution per candidate, parameterised by three quantiles."""
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray

    def __post_init__(self):
        self.q10, self.q50, self.q90 = (np.asarray(a, float) for a in (self.q10, self.q50, self.q90))
        self.s_lo = np.maximum((self.q50 - self.q10) / Z80, 1e-12)
        self.s_hi = np.maximum((self.q90 - self.q50) / Z80, 1e-12)

    def cdf(self, t) -> np.ndarray:
        t = np.asarray(t, float)
        s = np.where(t < self.q50, self.s_lo, self.s_hi)
        return norm.cdf((t - self.q50) / s)

    def prob_ge(self, t) -> np.ndarray:
        return 1.0 - self.cdf(t)

    def prob_le(self, t) -> np.ndarray:
        return self.cdf(t)

    def prob_in(self, lo, hi) -> np.ndarray:
        return np.clip(self.cdf(hi) - self.cdf(lo), 0.0, 1.0)

    def rel_width(self) -> np.ndarray:
        return (self.q90 - self.q10) / np.maximum(np.abs(self.q50), 1e-9)

    @classmethod
    def from_frame(cls, df) -> "PredDist":
        return cls(df["q10"].to_numpy(), df["q50"].to_numpy(), df["q90"].to_numpy())


def satisfaction(dist: PredDist, kind: str, lo: float | None, hi: float | None, goal: float | None = None) -> np.ndarray:
    """P(target satisfied) for kinds ge / le / range; 1.0 for objective-only kinds."""
    if kind == "ge":
        return dist.prob_ge(lo)
    if kind == "le":
        return dist.prob_le(hi)
    if kind == "range":
        return dist.prob_in(lo, hi)
    return np.ones_like(dist.q50)


def combine(probs: list[np.ndarray], how: str = "product") -> np.ndarray:
    if not probs:
        return np.ones(1)
    P = np.vstack(probs)
    return P.prod(axis=0) if how == "product" else P.min(axis=0)
