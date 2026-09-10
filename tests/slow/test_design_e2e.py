"""Slow end-to-end tests for the inverse layer (need built features and trained models)."""
from __future__ import annotations

import copy

import numpy as np
import pytest

from pmpredict.config import load_config
from pmpredict.design.optimize import Evaluator, run_twostage
from pmpredict.design.report import build_result, write_outputs
from pmpredict.design.retrieve import LiteratureStore
from pmpredict.design.spec import TEMPLATES, DesignSpec

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def cfg():
    c = load_config()
    if not (c.artifacts_dir / "manifest.json").exists():
        pytest.skip("train models first")
    return c


def _small(template: str, **over) -> DesignSpec:
    d = copy.deepcopy(TEMPLATES[template])
    d["budget"] = dict(n_samples=2048, n_refine=3, refine_generations=5, time_limit_s=60)
    d["output"] = dict(top_n=6, n_literature=5, plots=True)
    d.update(over)
    return DesignSpec.from_dict(d)


def test_design_end_to_end(cfg, tmp_path):
    spec = _small("3dcp_printable_mortar")
    ev = Evaluator(spec, cfg)
    spec.validate(available_targets=set(ev.models))
    run = run_twostage(spec, cfg, evaluator=ev)
    assert run.diagnostics["t_total_s"] < 90
    res = build_result(run, ev, LiteratureStore(cfg), cfg, [])
    assert 1 <= len(res.candidates) <= 6
    for c in res.candidates:
        b = sum(x["amount"] or 0 for x in c.mix["components"] if x["material_class"] in spec.space.binder)
        assert abs(b - 1.0) < 1e-6
        assert spec.space.w_b[0] - 1e-9 <= c.mix["water_binder"] <= spec.space.w_b[1] + 1e-9
        assert set(c.predictions) == {t.quantity for t in spec.targets}
    paths = write_outputs(res, tmp_path, plots=True)
    for k in ("result", "report", "candidates", "literature", "pareto", "parallel"):
        assert paths[k].exists() and paths[k].stat().st_size > 0


def test_monotonic_wb_with_strength(cfg):
    med = {}
    for lo in (30, 70):
        d = copy.deepcopy(TEMPLATES["low_carbon_mortar"])
        d["targets"] = [dict(quantity="compressive_strength", kind="ge", lo=lo, unit="MPa",
                             conditions=dict(age_d=28, comparability_group="comp_prism40"))]
        d["budget"] = dict(n_samples=4096, n_refine=3, refine_generations=4, time_limit_s=60)
        d["output"] = dict(top_n=10, n_literature=1, plots=False)
        spec = DesignSpec.from_dict(d)
        ev = Evaluator(spec, cfg)
        spec.validate(available_targets=set(ev.models))
        run = run_twostage(spec, cfg, evaluator=ev)
        f = run.final
        order = np.lexsort((-run.crowding, run.pareto_rank, ~f.feasible))[:10]
        med[lo] = float(f.M.iloc[order]["w_b"].median())
    assert med[70] < med[30], med
