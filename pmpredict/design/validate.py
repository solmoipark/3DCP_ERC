"""Closed-loop validation of the inverse layer on real mixes.

For held-out mixes with a measured 28 d compressive strength (plus optionally a fresh property),
build a design spec around their measured values, run the optimiser with a generic space, and check
(a) whether the candidate set lands closer to the true composition than random feasible mixes,
(b) whether the true mix itself is judged feasible by the models, and
(c) whether literature retrieval finds the mix or a sibling from the same paper.
"""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from .. import vocab as V
from ..config import PipelineConfig
from ..predict import Assets, add_covariates, featurize_specs
from ..reconstruct import spec_from_db
from ..features import build_context
from ..db import load_tables
from .domain import COMP_FEATURES
from .optimize import Evaluator, run_twostage
from .retrieve import LiteratureStore, retrieve
from .spec import DesignSpec
from .uncertainty import PredDist, satisfaction

log = logging.getLogger("pmpredict.validate")
GENERIC_BINDER = ["portland_cement", "ggbfs", "fly_ash_class_F", "silica_fume", "limestone_powder", "metakaolin", "calcined_clay"]
SECOND_TARGETS = ["flexural_strength", "flow_table_spread", "initial_setting_time", "plastic_viscosity", "porosity_total",
                  "water_absorption", "dynamic_yield_stress"]


def _spec_for_mix(store: LiteratureStore, uid: str, F_row: pd.Series) -> DesignSpec | None:
    t = store.targets[(store.targets["mix_uid"] == uid)]
    cs = t[(t["target"] == "compressive_strength") & (t["age_d"] == 28.0)]
    if cs.empty:
        return None
    cs = cs.iloc[0]
    targets = [dict(quantity="compressive_strength", kind="range", lo=float(cs.value) * 0.9, hi=float(cs.value) * 1.1,
                    conditions=dict(age_d=28.0, comparability_group=cs.comparability_group if isinstance(cs.comparability_group, str) else None))]
    fresh = t[t["target"].isin(SECOND_TARGETS)]
    if fresh.empty:
        return None                                  # need >= 2 targets for a meaningful closed loop
    fr = fresh.iloc[0]
    cond = dict(age_d=float(fr.age_d)) if pd.notna(fr.age_d) else {}
    targets.append(dict(quantity=fr.target, kind="range", lo=float(fr.value) * 0.85, hi=float(fr.value) * 1.15, conditions=cond))
    w = store.comp.loc[uid]
    present = [g for g in GENERIC_BINDER if w.get(f"pw_{V.class_to_group()[g]}", 0) > 0]
    if "portland_cement" not in present:
        return None
    binder = {c: dict(lo=0.0, hi=1.0, required=(c == "portland_cement")) for c in (present or GENERIC_BINDER)}
    sb = None if w["system_type"] == "paste" else [0.0, 6.0]
    return DesignSpec.from_dict(dict(
        name=f"closed_loop_{uid}", targets=targets,
        space=dict(system_type=str(w["system_type"]), w_b=[0.2, 0.7], s_b=sb, binder=binder, max_binder_components=4,
                   admixtures={"superplasticiser_pce": dict(lo=0.0, hi=2.0)},
                   fixed_conditions=dict(curing_temp_C=float(F_row["curing_temp_C"]) if pd.notna(F_row["curing_temp_C"]) else 20.0)),
        objectives=[], risk=dict(p_min=0.3), budget=dict(n_samples=4096, n_refine=3, refine_generations=8, time_limit_s=60),
        output=dict(top_n=10, n_literature=10, plots=False), seed=0))


def closed_loop(cfg: PipelineConfig, n: int = 50, seed: int = 0) -> dict:
    store = LiteratureStore(cfg)
    assets = Assets(cfg)
    F = store.features.set_index("mix_uid")
    T = load_tables(cfg, tables=["mixes", "papers"])
    ctx = build_context(T)
    comp_long = pd.read_parquet(cfg.data_dir / "composition_long.parquet")
    cand = store.targets[(store.targets["target"] == "compressive_strength") & (store.targets["age_d"] == 28.0)]["mix_uid"].unique()
    cand = [u for u in cand if u in store.comp.index and u in F.index and pd.notna(store.comp.loc[u, "water_b"])
            and store.comp.loc[u, "pw_opc"] > 0]
    rng = np.random.default_rng(seed)
    sample = rng.choice(cand, size=min(n, len(cand)), replace=False)
    cols = [c for c in COMP_FEATURES if c in F.columns]
    mu = F[cols].mean(); sd = F[cols].std().replace(0, 1.0)
    rows = []
    t0 = time.time()
    for uid in sample:
        spec = _spec_for_mix(store, uid, F.loc[uid])
        if spec is None:
            continue
        try:
            spec.validate(available_targets=set(assets.available_targets()))
            ev = Evaluator(spec, cfg)
            run = run_twostage(spec, cfg, evaluator=ev)
        except Exception as e:  # pragma: no cover
            log.warning("%s failed: %s", uid, e)
            continue
        f = run.final
        z = lambda df: ((df[cols].astype(float).fillna(mu) - mu) / sd).to_numpy(float)
        true = z(F.loc[[uid]])
        d_cand = np.linalg.norm(z(f.F) - true, axis=1).min()
        # random feasible reference from the stage-1 sweep
        feas = run.ev_all.feasible
        pool = run.ev_all.F[feas] if feas.any() else run.ev_all.F
        take = pool.sample(min(10, len(pool)), random_state=seed)
        d_rand = np.linalg.norm(z(take) - true, axis=1).min()
        # (b) is the true mix feasible under the models?
        true_spec = spec_from_db(uid, store.comp.reset_index(), comp_long, ctx)
        Ft, _ = featurize_specs([true_spec], assets)
        p_true, covered = [], []
        for t in spec.targets:
            m = ev.models[t.quantity]
            ts = true_spec
            ts.conditions.age_d = t.conditions.age_d; ts.conditions.comparability_group = t.conditions.comparability_group
            X = add_covariates(Ft, [ts], m.meta.get("covariates", []))
            q = m.predict_quantiles(X).iloc[0]
            p_true.append(float(satisfaction(PredDist(np.array([q.q10]), np.array([q.q50]), np.array([q.q90])), t.kind, t.lo, t.hi, t.goal)[0]))
            measured = (t.lo + t.hi) / 2.0                 # spec was built as +-x % around the measured value
            covered.append(bool(q.q10 <= measured <= q.q90))
        P_true = float(np.prod(p_true))
        P_cand_med = float(np.median(f.P))
        hits = retrieve(spec, store, n=200)
        paper = uid.split("::")[0]
        in_top10 = any(h.mix_uid == uid or h.paper_uid == paper for h in hits[:10])
        in_exact = any(h.mix_uid == uid and h.tier == "exact" for h in hits)
        rows.append(dict(mix_uid=uid, d_candidate=d_cand, d_random=d_rand, closer=d_cand < d_rand, P_true=P_true,
                         P_candidates_median=P_cand_med, true_not_worse_than_candidates=P_true >= 0.5 * P_cand_med,
                         true_covered_all=all(covered), retrieved_top10=in_top10, retrieved_exact=in_exact or in_top10,
                         n_feasible=int(feas.sum()), t_s=run.diagnostics["t_total_s"]))
        log.info("%s d_cand=%.2f d_rand=%.2f P_true=%.2f covered=%s retrieved=%s", uid, d_cand, d_rand, P_true, all(covered), in_exact)
    df = pd.DataFrame(rows)
    rep = dict(n=len(df),
               closer_than_random=float(df["closer"].mean()) if len(df) else None,
               true_covered_by_intervals=float(df["true_covered_all"].mean()) if len(df) else None,
               true_P_not_worse_than_candidates=float(df["true_not_worse_than_candidates"].mean()) if len(df) else None,
               retrieved_exact_or_top10=float(df["retrieved_exact"].mean()) if len(df) else None,
               retrieved_top10=float(df["retrieved_top10"].mean()) if len(df) else None,
               median_runtime_s=float(df["t_s"].median()) if len(df) else None, total_s=round(time.time() - t0, 1))
    out = cfg.reports_dir / "design"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "closed_loop.csv", index=False)
    return rep
