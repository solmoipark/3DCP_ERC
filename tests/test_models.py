"""Unit tests for the model bundle utilities."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pmpredict.models import TRANSFORMS, conformal_scale_from_oof, param_tier, prepare_X


def test_param_tiers():
    assert param_tier(10000, 500)[0] == "large"
    assert param_tier(1500, 100)[0] == "medium"
    assert param_tier(500, 100)[0] == "small"
    assert param_tier(5000, 20)[0] == "small"        # few papers -> small regardless of rows


def test_prepare_X_pins_categories_and_orders_columns():
    X = pd.DataFrame({"b": [1, 2], "a": ["x", "zzz"], "extra": [0, 0]})
    out = prepare_X(X, ["a", "b", "missing"], {"a": ["x", "y"]})
    assert list(out.columns) == ["a", "b", "missing"]
    assert list(out["a"].cat.categories) == ["x", "y"]
    assert out["a"].isna().iloc[1]                    # unseen level -> NaN
    assert out["missing"].isna().all()


def test_conformal_scale():
    rng = np.random.default_rng(0)
    y = rng.normal(0, 1, 5000)
    mu = np.zeros_like(y)
    lo, hi = mu - 1.0, mu + 1.0                        # nominal +-1 sigma interval (~68 %)
    s = conformal_scale_from_oof(y, mu, lo, hi, coverage=0.80)
    assert 1.2 < s < 1.4                               # 80 % of N(0,1) lies within +-1.28
    cov = np.mean((y >= mu - s) & (y <= mu + s))
    assert abs(cov - 0.80) < 0.02


def test_transforms_roundtrip():
    y = np.array([0.5, 3.0, 40.0])
    for k, (f, inv) in TRANSFORMS.items():
        assert np.allclose(inv(f(y)), y)
