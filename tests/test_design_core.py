"""Tests for design spec / search space / uncertainty / objectives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pmpredict.design.objectives import FactorTable, compute_objectives
from pmpredict.design.space import decode, encode, frame_to_composition, frame_to_specs, make_layout, project_bounded_simplex
from pmpredict.design.spec import TEMPLATES, DesignSpec, SpecValidationError
from pmpredict.design.uncertainty import PredDist, combine, satisfaction


def _spec(name="3dcp_printable_mortar"):
    s = DesignSpec.from_dict(TEMPLATES[name])
    s.validate(available_targets={"compressive_strength", "static_yield_stress", "flow_table_spread",
                                  "mini_slump_flow_diameter"})
    return s


def test_spec_units_and_validation():
    s = _spec()
    sy = next(t for t in s.targets if t.quantity == "static_yield_stress")
    assert sy.lo == 1000.0 and sy.hi == 4000.0 and sy.unit is None       # kPa -> Pa
    bad = DesignSpec.from_dict(dict(TEMPLATES["hpc_paste"]))
    bad.space.binder["portland_cement"].lo = 0.9
    bad.space.binder["silica_fume"].lo = 0.3
    bad.space.binder["silica_fume"].required = True
    with pytest.raises(SpecValidationError):
        bad.validate()
    with pytest.raises(SpecValidationError):
        DesignSpec.from_dict(dict(TEMPLATES["hpc_paste"], targets=[dict(quantity="compressive_strength", kind="ge")])).validate()


def test_projection_and_decode_constraints():
    rng = np.random.default_rng(0)
    lo = np.array([[0.5, 0.0, 0.0, 0.0]] * 5); hi = np.array([[1.0, 0.15, 0.3, 0.4]] * 5)
    x = project_bounded_simplex(rng.random((5, 4)), lo, hi)
    assert np.allclose(x.sum(axis=1), 1.0) and (x >= lo - 1e-12).all() and (x <= hi + 1e-12).all()

    s = _spec()
    L = make_layout(s)
    Z = rng.random((10000, L.D))
    M = decode(Z, s, L)
    B = M[[f"b:{c}" for c in L.binder]].to_numpy()
    assert np.allclose(B.sum(axis=1), 1.0, atol=1e-9)
    assert (B >= L.b_lo - 1e-9).all() and (B <= L.b_hi + 1e-9).all()
    assert ((B > 0).sum(axis=1) <= s.space.max_binder_components).all()
    present = B[B > 0]
    assert (present >= s.space.min_present_frac - 1e-12).all()
    assert (M["w_b"].between(*s.space.w_b)).all() and (M["s_b"].between(*s.space.s_b)).all()
    a = M["a:superplasticiser_pce"]
    assert a.between(0.2 - 1e-9, 1.5 + 1e-9).all()          # lo > 0 -> always present


def test_encode_decode_roundtrip_and_composition_bridge():
    s = _spec()
    L = make_layout(s)
    rng = np.random.default_rng(1)
    M = decode(rng.random((50, L.D)), s, L)
    specs = frame_to_specs(M, s, L)
    Z2 = np.vstack([encode(s, sp, L) for sp in specs])
    M2 = decode(Z2, s, L)
    for c in [f"b:{c}" for c in L.binder] + ["w_b", "s_b", "a:superplasticiser_pce", "a:vma_cellulose"]:
        assert np.allclose(M[c].to_numpy(), M2[c].to_numpy(), atol=1e-6), c
    comp, long, ctx = frame_to_composition(M.iloc[:5], specs[:5])
    assert len(comp) == 5 and np.allclose(comp["water_b"], M["w_b"].iloc[:5])
    assert np.allclose(comp["sand_b"], M["s_b"].iloc[:5])
    assert np.allclose(comp["pw_opc"], M["b:portland_cement"].iloc[:5])


def test_uncertainty():
    d = PredDist(np.array([10.0]), np.array([20.0]), np.array([40.0]))
    assert np.isclose(d.prob_ge(20.0), 0.5)
    assert np.isclose(d.prob_ge(10.0), 0.9, atol=1e-6)
    assert np.isclose(d.prob_le(40.0), 0.9, atol=1e-6)
    p = d.prob_in(10.0, 40.0)
    assert np.isclose(p, 0.8, atol=1e-6)
    assert satisfaction(d, "ge", 15.0, None) > satisfaction(d, "ge", 25.0, None)
    P = combine([np.array([0.9, 0.5]), np.array([0.8, 0.9])], "product")
    assert np.allclose(P, [0.72, 0.45])
    assert np.allclose(combine([np.array([0.9]), np.array([0.8])], "min"), [0.8])


def test_objectives_hand_calc():
    s = _spec()
    L = make_layout(s)
    M = pd.DataFrame({"b:portland_cement": [1.0], "b:silica_fume": [0.0], "b:limestone_powder": [0.0],
                      "b:fly_ash_class_F": [0.0], "w_b": [0.4], "s_b": [2.0], "a:superplasticiser_pce": [1.0],
                      "a:vma_cellulose": [0.0]})
    specs = frame_to_specs(M, s, L)
    comp, long, ctx = frame_to_composition(M, specs)
    cost = FactorTable(None, "cost"); co2 = FactorTable(None, "co2")
    F = comp.copy()
    F["fibre_total_mass_b"] = 0.0
    obj = compute_objectives(F, cost, co2)
    exp_cost = 1.0 * 0.12 + 0.4 * 0.001 + 2.0 * 0.02 + 0.01 * 3.0    # OPC + water + sand (natural default) + PCE
    assert np.isclose(obj["cost_per_kg_powder"].iloc[0], exp_cost, rtol=1e-6)
    assert np.isclose(obj["clinker_fraction"].iloc[0], 1.0)
    assert 300 < obj["powder_kg_m3"].iloc[0] < 900
    assert cost.is_default and co2.is_default
