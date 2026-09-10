"""Unit tests for target-table rules on synthetic measurement rows."""
from __future__ import annotations

import pandas as pd
import pytest

from pmpredict.targets import build_targets, load_target_rules, snap_age


def _tables(meas_rows, tests_rows=None):
    cols = ["obs_uid", "mix_uid", "test_uid", "paper_uid", "quantity", "value_canonical", "unit_canonical",
            "value_kind", "age_norm_d", "rest_time_norm_s", "basis", "condition_note"]
    ms = pd.DataFrame([{c: r.get(c) for c in cols} for r in meas_rows])
    tests = pd.DataFrame(tests_rows or [{"test_uid": "T1", "comparability_group": "comp_cube50", "method_name": "x"}])
    return {"measurements": ms, "tests": tests}


def row(**kw):
    base = dict(obs_uid="o", mix_uid="P::M1", test_uid="T1", paper_uid="P", quantity="compressive_strength",
                value_canonical=40.0, unit_canonical="MPa", value_kind="reported", age_norm_d=28.0,
                rest_time_norm_s=None, basis=None, condition_note=None)
    base.update(kw)
    return base


def test_snap_age():
    grid = [1, 3, 7, 28, 90]
    assert snap_age(27.0, grid) == 28.0
    assert snap_age(3.2, grid) == 3.0
    assert snap_age(45.0, grid) == 45.0
    assert snap_age(None, grid) != snap_age(None, grid)  # NaN


def test_units_bounds_and_replicates():
    rules, meta = load_target_rules()
    T = _tables([
        row(obs_uid="a", value_canonical=40.0),
        row(obs_uid="b", value_canonical=42.0, condition_note="Replicate specimen 2 of 3"),
        row(obs_uid="c", value_canonical=400.0),                       # out of bounds -> dropped
        row(obs_uid="d", quantity="initial_setting_time", value_canonical=3.0, unit_canonical="h"),
        row(obs_uid="e", quantity="initial_setting_time", value_canonical=200.0, unit_canonical="furlongs"),
    ])
    long, qa = build_targets(T, rules, meta, only=["compressive_strength", "initial_setting_time"])
    cs = long[long.target == "compressive_strength"]
    assert len(cs) == 1 and cs.value.iloc[0] == 41.0 and cs.n_rows.iloc[0] == 2
    assert cs.comparability_group.iloc[0] == "comp_cube50" and cs.age_d.iloc[0] == 28.0
    st = long[long.target == "initial_setting_time"]
    assert len(st) == 1 and st.value.iloc[0] == pytest.approx(180.0)     # 3 h -> 180 min; unknown unit dropped


def test_condition_conflict_rule():
    rules, meta = load_target_rules()
    T = _tables([
        row(obs_uid="a", value_canonical=40.0),
        row(obs_uid="b", value_canonical=60.0, condition_note="NaOH 12 M"),        # divergent -> base kept
        row(obs_uid="c", mix_uid="P::M2", value_canonical=40.0, condition_note="8 M"),
        row(obs_uid="d", mix_uid="P::M2", value_canonical=60.0, condition_note="12 M"),   # no base -> dropped
        row(obs_uid="e", mix_uid="P::M3", value_canonical=40.0, condition_note="8 M"),
        row(obs_uid="f", mix_uid="P::M3", value_canonical=42.0, condition_note="12 M"),   # within 15 % -> merged
        row(obs_uid="g", mix_uid="P::M4", value_canonical=55.0, condition_note="RSM model-predicted value"),
    ])
    long, qa = build_targets(T, rules, meta, only=["compressive_strength"])
    m = long.set_index("mix_uid")
    assert m.loc["P::M1", "value"] == 40.0
    assert "P::M2" not in m.index
    assert m.loc["P::M3", "value"] == 41.0
    assert "P::M4" not in m.index
    q = qa.iloc[0]
    assert q["conflict_dropped"] == 1 and q["after_cond_drop"] == 6


def test_heat_basis_filter_and_abs_shrinkage():
    rules, meta = load_target_rules()
    T = _tables([
        row(obs_uid="a", quantity="cumulative_heat", value_canonical=250.0, unit_canonical="J/g", basis="per_g_binder", age_norm_d=3.0),
        row(obs_uid="b", quantity="cumulative_heat", value_canonical=300.0, unit_canonical="J/g", basis="per_g_cement", age_norm_d=3.0, mix_uid="P::M2"),
        row(obs_uid="c", quantity="cumulative_heat", value_canonical=200.0, unit_canonical="J/g binder", basis=None, age_norm_d=3.0, mix_uid="P::M3"),
        row(obs_uid="d", quantity="drying_shrinkage", value_canonical=-800.0, unit_canonical="microstrain", age_norm_d=28.0),
        row(obs_uid="e", quantity="drying_shrinkage", value_canonical=0.09, unit_canonical="%", age_norm_d=28.0, mix_uid="P::M2"),
    ])
    long, qa = build_targets(T, rules, meta, only=["cumulative_heat", "drying_shrinkage"])
    h = long[long.target == "cumulative_heat"].set_index("mix_uid")
    assert set(h.index) == {"P::M1", "P::M3"}
    d = long[long.target == "drying_shrinkage"].set_index("mix_uid")
    assert d.loc["P::M1", "value"] == 800.0 and d.loc["P::M2", "value"] == pytest.approx(900.0)
