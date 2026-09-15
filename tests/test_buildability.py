"""Physics and calibration checks for pmpredict.buildability (no models needed)."""
from __future__ import annotations

import math

import pytest

from pmpredict import buildability as B


def _job(**kw):
    d = dict(name="t", object_type="wall", target_height_mm=500, footprint_mm=1000, nozzle_d_mm=20, print_speed_mm_s=50)
    d.update(kw)
    return B.PrintJob(**d)


def test_resolve_defaults_from_nozzle():
    j, filled = _job().resolve({})
    assert j.layer_height_mm == pytest.approx(10.0) and j.layer_width_mm == pytest.approx(24.0)
    assert j.layer_cycle_time_s == pytest.approx(20.0) and j.n_layers == 50
    assert len(filled) == 3
    with pytest.raises(ValueError):
        B.PrintJob(name="x", object_type="column", target_height_mm=300).resolve({})


def test_roussel_limits():
    # no structuration: n_max = sqrt3 tau0 / (rho g h)
    assert B.plastic_n_max(10, 2100, 2000, 0.0, 30) == pytest.approx(math.sqrt(3) * 2000 / (2100 * 9.81 * 0.01))
    # structuration faster than loading -> unlimited
    assert math.isinf(B.plastic_n_max(10, 2100, 2000, 5.0, 60))
    # the critical cycle time is where n_max diverges
    t_crit = 2100 * 9.81 * 0.01 / (math.sqrt(3) * 1.0)
    assert math.isinf(B.plastic_n_max(10, 2100, 2000, 1.0, t_crit * 1.01))
    assert B.plastic_n_max(10, 2100, 2000, 1.0, t_crit * 0.99) > 1000
    # required tau0 / athix / cycle time are consistent with n_max
    n, h, rho, A, tc, sf = 40, 10, 2100, 0.5, 20, 1.5
    tau_req = B.required_tau0(n, h, rho, A, tc, sf)
    assert B.plastic_n_max(h, rho, tau_req, A, tc, sf) == pytest.approx(n)
    A_req = B.required_athix(n, h, rho, 1000, tc, sf)
    assert B.plastic_n_max(h, rho, 1000, A_req, tc, sf) == pytest.approx(n)
    t_min = B.min_cycle_time(n, h, rho, 1000, A, sf)
    assert B.plastic_n_max(h, rho, 1000, A, t_min, sf) == pytest.approx(n)


def test_buckling_monotone_in_thickness():
    a = B.buckling_n_max(10, 25, 2100, 2000, 0.5, 20, 25.0)
    b = B.buckling_n_max(10, 50, 2100, 2000, 0.5, 20, 25.0)
    assert 0 < a < b


def test_assess_and_schedule_labels():
    cal = B.load_calibration()
    strong = B.assess(_job(wall_filaments=2, check_buckling=False), B.FreshMaterial(tau_s0_Pa=8000, athix_Pa_s=3.0), cal)
    weak = B.assess(_job(wall_filaments=2, check_buckling=False), B.FreshMaterial(tau_s0_Pa=200, athix_Pa_s=0.05), cal)
    assert strong.label in ("printable", "borderline") and weak.label == "non_printable" and weak.governing == "plastic_collapse"
    assert strong.n_max_plastic > weak.n_max_plastic
    # a thin free wall fails by buckling first; the check can be switched off for closed/braced paths
    thin = B.assess(_job(wall_filaments=1), B.FreshMaterial(tau_s0_Pa=8000, athix_Pa_s=3.0), cal)
    thick = B.assess(_job(wall_filaments=3), B.FreshMaterial(tau_s0_Pa=8000, athix_Pa_s=3.0), cal)
    assert thin.governing == "elastic_buckling" and thin.n_max_buckling < thick.n_max_buckling
    assert B.assess(_job(wall_filaments=1, check_buckling=False), B.FreshMaterial(tau_s0_Pa=8000, athix_Pa_s=3.0), cal).n_max_buckling is None
    cyl = B.assess(B.PrintJob(name="c", object_type="hollow_cylinder", target_height_mm=300, footprint_mm=250, nozzle_d_mm=20, print_speed_mm_s=40),
                   B.FreshMaterial(tau_s0_Pa=8000, athix_Pa_s=3.0), cal)
    assert cyl.n_max_buckling is None and cyl.label in ("printable", "borderline")
    sc = B.schedule(_job(open_time_min=60, wall_filaments=2), B.FreshMaterial(tau_s0_Pa=6000, athix_Pa_s=3.0), cal)
    assert sc["t_c_min_s"] <= sc["t_c_recommended_s"] <= sc["t_c_max_s"] and sc["feasible"]
    assert sc["speed"]["v_min_mm_s"] <= sc["speed"]["v_recommended_mm_s"] <= sc["speed"]["v_max_mm_s"]
    if cal:
        assert 0.0 <= strong.p_collapse_empirical <= weak.p_collapse_empirical <= 1.0


def test_job_to_design_dict_encodes_roussel():
    cal = B.load_calibration()
    j = _job(target_height_mm=400)
    d, info = B.job_to_design_dict(j, {"system_type": "mortar", "binder": {"portland_cement": {"lo": 0.5, "hi": 1.0, "required": True}}}, cal)
    t = d["targets"][0]
    assert t["quantity"] == "static_yield_stress_at_rest" and t["conditions"]["rest_time_s"] == pytest.approx(info["print_time_s"])
    assert t["lo"] == pytest.approx(1.5 * 2100 * 9.81 * 0.4 / math.sqrt(3))
