"""Two-stage inverse design: Sobol sweep -> probabilistic screening -> non-dominated sort ->
diverse shortlist -> vectorised differential-evolution refinement."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution
from scipy.stats import qmc

from ..config import PipelineConfig
from ..features import featurize_frame
from ..models import TargetModel
from ..predict import Assets, _spec_material_tables, add_covariates
from ..schema import MixSpec
from .domain import DomainIndex, domain_for_model
from .objectives import OBJECTIVE_COLUMN, FactorTable, compute_objectives
from .space import Layout, decode, frame_to_composition, frame_to_specs, make_layout
from .spec import DERIVED_TARGETS, DesignSpec, TargetSpec
from .uncertainty import Z80, PredDist, combine, satisfaction

log = logging.getLogger("pmpredict.optimize")


# --------------------------------------------------------------- evaluator
@dataclass
class Evaluation:
    M: pd.DataFrame                     # decoded mix frame
    F: pd.DataFrame                     # features (schema-aligned, no covariates)
    pred: dict[str, pd.DataFrame]       # quantity -> q10/q50/q90
    p: dict[str, np.ndarray]            # quantity -> satisfaction probability
    ad: dict[str, np.ndarray]           # quantity -> AD score
    P: np.ndarray                       # combined feasibility probability
    AD: np.ndarray                      # max AD over targets
    obj: pd.DataFrame                   # objectives
    feasible: np.ndarray
    specs: list[MixSpec] = field(default_factory=list)


class Evaluator:
    """Batch: decision vectors -> features -> per-target predictions, probabilities, AD and objectives."""

    def __init__(self, spec: DesignSpec, cfg: PipelineConfig, cost_table: str | None = None, co2_table: str | None = None):
        self.spec = spec
        self.cfg = cfg
        self.assets = Assets(cfg)
        self.L: Layout = make_layout(spec)
        self.models: dict[str, TargetModel] = {}
        self.domains: dict[str, DomainIndex] = {}
        feats = pd.read_parquet(cfg.data_dir / "features.parquet")
        man = self.assets.manifest["models"]
        self.keys: dict[str, str] = {}          # quantity -> manifest key actually used
        self.derived: dict[str, tuple[str, ...]] = {}

        def _load(q: str):
            if q in self.models or q not in man:
                return
            key = q
            k3 = f"{q}__3dcp"
            if spec.space.is_3dcp and k3 in man and (man[k3].get("r2") or -9) > (man[key].get("r2") or -9):
                key = k3
            self.models[q] = self.assets.model(key)
            self.domains[q] = domain_for_model(cfg.artifacts_dir / man[key]["path"], feats)
            self.keys[q] = key

        for t in spec.targets:
            if t.retrieval_only:
                continue
            if t.quantity in DERIVED_TARGETS:
                bases, _ = DERIVED_TARGETS[t.quantity]
                for b in bases:
                    _load(b)
                if all(b in self.models for b in bases):
                    self.derived[t.quantity] = bases
            else:
                _load(t.quantity)
        self.cost = FactorTable(cost_table, "cost")
        self.co2 = FactorTable(co2_table, "co2")
        self.weak = {q: bool(man[k].get("weak_model", False)) for q, k in self.keys.items()}
        for q, bases in self.derived.items():
            self.weak[q] = any(self.weak.get(b, False) for b in bases)
        self.n_calls = 0
        self.t_predict = 0.0

    def info(self, q: str) -> dict:
        """Model metadata for a (base or derived) quantity or target label, for reports."""
        man = self.assets.manifest["models"]
        q = q.split("@")[0]
        if q in self.derived:
            bases = self.derived[q]
            ms = [man[self.keys[b]] for b in bases]
            return dict(key="derived(" + " + ".join(self.keys[b] for b in bases) + ")", unit="Pa",
                        n_train=int(min(m["n_train"] for m in ms)), n_papers=int(min(m["n_papers"] for m in ms)),
                        r2=None, r2_log=min((m.get("r2_log") or 0) for m in ms), spearman=min((m.get("spearman") or 0) for m in ms),
                        coverage80=min((m.get("coverage80") or 0) for m in ms), weak=self.weak.get(q, True))
        m = man[self.keys[q]]
        return dict(key=self.keys[q], unit=m["unit"], n_train=m["n_train"], n_papers=m["n_papers"], r2=m.get("r2"),
                    r2_log=m.get("r2_log"), spearman=m.get("spearman"), coverage80=m.get("coverage80"), weak=self.weak.get(q, False))

    @staticmethod
    def _derived_quantiles(qa: pd.DataFrame, qb: pd.DataFrame, x: float, n: int = 256, seed: int = 0) -> pd.DataFrame:
        """Quantiles of a + b*x with a, b independent split-normal (log10) per candidate."""
        rng = np.random.default_rng(seed)
        def samp(q):
            l10 = np.log10(np.maximum(q[["q10", "q50", "q90"]].to_numpy(float), 1e-9))
            s_lo = np.maximum((l10[:, 1] - l10[:, 0]) / Z80, 1e-6); s_hi = np.maximum((l10[:, 2] - l10[:, 1]) / Z80, 1e-6)
            z = rng.standard_normal((n, 1))
            return 10 ** (l10[:, 1][None, :] + np.where(z < 0, s_lo[None, :], s_hi[None, :]) * z)
        v = samp(qa) + samp(qb) * x
        return pd.DataFrame(dict(q10=np.quantile(v, .1, axis=0), q50=np.quantile(v, .5, axis=0), q90=np.quantile(v, .9, axis=0)),
                            index=qa.index)

    # ---- features for a frame
    def featurize(self, M: pd.DataFrame) -> tuple[pd.DataFrame, list[MixSpec]]:
        specs = frame_to_specs(M, self.spec, self.L)
        comp, long, ctx = frame_to_composition(M, specs)
        mat_ox, mat_ph = _spec_material_tables(specs)
        F = featurize_frame(comp, long, mat_ox, mat_ph, ctx, self.assets.class_medians)
        for c in self.assets.schema["columns"]:
            if c not in F.columns:
                F[c] = np.nan
        for c, lv in self.assets.schema["categorical_levels"].items():
            F[c] = pd.Categorical(F[c].astype("object"), categories=lv)
        return F.reset_index(drop=True), specs

    def _conditions_spec(self, base: MixSpec, t: TargetSpec) -> MixSpec:
        c = t.conditions
        s = MixSpec.from_dict(base.to_dict())
        s.conditions.age_d = c.age_d
        s.conditions.comparability_group = c.comparability_group
        s.conditions.rest_time_s = c.rest_time_s
        if c.curing_temp_C is not None:
            s.conditions.curing_temp_C = c.curing_temp_C
        return s

    def evaluate(self, Z: np.ndarray) -> Evaluation:
        t0 = time.time()
        M = decode(Z, self.spec, self.L)
        F, specs = self.featurize(M)
        pred, p, ad = {}, {}, {}
        base_cache: dict[str, pd.DataFrame] = {}

        def base_q(q: str, rest: float | None = None) -> pd.DataFrame:
            ck = f"{q}@{rest}"
            if ck not in base_cache:
                m = self.models[q]
                cs = []
                for s in specs:
                    s2 = MixSpec.from_dict(s.to_dict()); s2.conditions.rest_time_s = rest; cs.append(s2)
                base_cache[ck] = m.predict_quantiles(add_covariates(F, cs, m.meta.get("covariates", [])))
            return base_cache[ck]

        for t in self.spec.targets:
            k = t.label
            if t.quantity in self.derived:
                bases, _ = DERIVED_TARGETS[t.quantity]
                if t.quantity == "shear_stress_at_rate":
                    q = self._derived_quantiles(base_q("dynamic_yield_stress"), base_q("plastic_viscosity"), float(t.conditions.shear_rate_1s))
                else:  # static_yield_stress_at_rest
                    q = self._derived_quantiles(base_q("static_yield_stress", 0.0), base_q("structuration_rate_athix"), float(t.conditions.rest_time_s))
                pred[k] = q
                p[k] = satisfaction(PredDist.from_frame(q), t.kind, t.lo, t.hi, t.goal)
                ad[k] = np.max(np.vstack([self.domains[b].score(F) for b in bases]), axis=0)
                continue
            if t.quantity not in self.models:
                continue
            m = self.models[t.quantity]
            cond_specs = [self._conditions_spec(s, t) for s in specs]
            X = add_covariates(F, cond_specs, m.meta.get("covariates", []))
            q = m.predict_quantiles(X)
            pred[k] = q
            p[k] = satisfaction(PredDist.from_frame(q), t.kind, t.lo, t.hi, t.goal)
            ad[k] = self.domains[t.quantity].score(F)
        P = combine([p[t.label] for t in self.spec.targets if t.label in p and t.is_constraint], self.spec.risk.combine) \
            if any(t.is_constraint and t.label in p for t in self.spec.targets) else np.ones(len(M))
        AD = np.max(np.vstack(list(ad.values())), axis=0) if ad else np.zeros(len(M))
        cs = pred.get("compressive_strength")
        obj = compute_objectives(F, self.cost, self.co2, strength_q10=cs["q10"].to_numpy() if cs is not None else None)
        for t in self.spec.targets:               # quantity objectives (pessimistic quantile)
            if t.label in pred and t.kind in {"minimize", "maximize", "goal"}:
                q = pred[t.label]
                if t.kind == "goal":
                    obj[f"quantity:{t.quantity}"] = np.abs(q["q50"].to_numpy() - t.goal)
                else:
                    obj[f"quantity:{t.quantity}"] = q["q90"].to_numpy() if t.kind == "minimize" else -q["q10"].to_numpy()
        feasible = self.feasibility(p, AD)
        self.n_calls += 1
        self.t_predict += time.time() - t0
        return Evaluation(M, F, pred, p, ad, P, AD, obj, feasible, specs)

    def thresholds(self, scale: float = 1.0) -> dict[str, float]:
        """Per-target minimum satisfaction probability (target p_min, else risk.p_min), scaled for relaxation."""
        return {t.label: min(1.0, (t.p_min if t.p_min is not None else self.spec.risk.p_min) * scale)
                for t in self.spec.targets if t.is_constraint and (t.quantity in self.models or t.quantity in self.derived)}

    def feasibility(self, p: dict[str, np.ndarray], AD: np.ndarray, scale: float = 1.0,
                    ad_max: float | None = None) -> np.ndarray:
        th = self.thresholds(scale)
        ok = np.ones(len(AD), bool)
        for q, thr in th.items():
            ok &= p[q] >= thr
        return ok & (AD <= (ad_max if ad_max is not None else self.spec.risk.ad_max))

    # ---- objective matrix (minimisation) for NDS
    def objective_matrix(self, ev: Evaluation) -> np.ndarray:
        cols = []
        for o in self.spec.objectives:
            col = OBJECTIVE_COLUMN.get(o.name, o.name)
            v = ev.obj[col].to_numpy(float) if col in ev.obj.columns else np.zeros(len(ev.M))
            cols.append(v if o.direction == "min" else -v)
        if not cols:
            cols.append(-ev.P)                      # no explicit objective: maximise feasibility probability
        return np.column_stack(cols)


# ------------------------------------------------------- non-dominated sort
def fast_nondominated_sort(Fm: np.ndarray) -> np.ndarray:
    """Return Pareto rank (0 = front) for a minimisation objective matrix (n, m)."""
    n = len(Fm)
    rank = np.full(n, -1)
    remaining = np.arange(n)
    r = 0
    while len(remaining):
        A = Fm[remaining]
        dominated = np.zeros(len(remaining), bool)
        for i in range(len(remaining)):
            if dominated[i]:
                continue
            le = (A <= A[i]).all(axis=1)
            lt = (A < A[i]).any(axis=1)
            dominated[i] = bool((le & lt).any())
        front = remaining[~dominated]
        rank[front] = r
        remaining = remaining[dominated]
        r += 1
    return rank


def crowding_distance(Fm: np.ndarray) -> np.ndarray:
    n, m = Fm.shape
    if n <= 2:
        return np.full(n, np.inf)
    cd = np.zeros(n)
    for j in range(m):
        order = np.argsort(Fm[:, j])
        span = Fm[order[-1], j] - Fm[order[0], j]
        cd[order[0]] = cd[order[-1]] = np.inf
        if span <= 0:
            continue
        cd[order[1:-1]] += (Fm[order[2:], j] - Fm[order[:-2], j]) / span
    return cd


def farthest_point_subset(X: np.ndarray, k: int, first: int = 0) -> list[int]:
    """Greedy farthest-point selection for a diverse shortlist."""
    if len(X) <= k:
        return list(range(len(X)))
    chosen = [first]
    d = np.linalg.norm(X - X[first], axis=1)
    while len(chosen) < k:
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.linalg.norm(X - X[i], axis=1))
    return chosen


# ------------------------------------------------------------------ driver
@dataclass
class DesignRun:
    spec: DesignSpec
    ev_all: Evaluation                  # stage-1 sweep
    final: Evaluation                   # shortlisted + refined candidates
    Z_final: np.ndarray
    pareto_rank: np.ndarray
    crowding: np.ndarray
    diagnostics: dict


def _relax(spec: DesignSpec, ev_: "Evaluator", ev: Evaluation, top_n: int, diag: dict) -> np.ndarray:
    """Lower the per-target probability thresholds (down to half), then widen the AD limit, until
    at least top_n candidates are feasible. Every step is recorded in the diagnostics."""
    feasible = ev.feasible.copy()
    scale, ad_max = 1.0, spec.risk.ad_max
    steps = []
    while feasible.sum() < top_n and (scale > 0.5 + 1e-9 or ad_max < 2.0):
        if scale > 0.5 + 1e-9:
            scale = round(max(scale - 0.1, 0.5), 2)
        else:
            ad_max = round(ad_max * 1.25, 3)
        feasible = ev_.feasibility(ev.p, ev.AD, scale, ad_max)
        steps.append(dict(threshold_scale=scale, ad_max=ad_max, n_feasible=int(feasible.sum())))
    diag["relaxation"] = steps
    diag["threshold_scale_used"], diag["ad_max_used"] = scale, ad_max
    diag["p_min_used"] = {q: round(v, 3) for q, v in ev_.thresholds(scale).items()}
    return feasible


def run_twostage(spec: DesignSpec, cfg: PipelineConfig, cost_table: str | None = None, co2_table: str | None = None,
                 evaluator: Evaluator | None = None) -> DesignRun:
    t0 = time.time()
    ev_ = evaluator or Evaluator(spec, cfg, cost_table, co2_table)
    L = ev_.L
    diag: dict = {}
    # ---- stage 1: Sobol sweep
    m = int(np.ceil(np.log2(max(spec.budget.n_samples, 64))))
    Z = qmc.Sobol(L.D, scramble=True, seed=spec.seed).random_base2(m)
    ev = ev_.evaluate(Z)
    diag["n_sampled"] = len(Z)
    diag["n_feasible"] = int(ev.feasible.sum())
    diag["t_stage1_s"] = round(time.time() - t0, 1)
    feasible = _relax(spec, ev_, ev, spec.output.top_n, diag) if ev.feasible.sum() < spec.output.top_n else ev.feasible
    fallback = not feasible.any()
    if fallback:
        # nothing feasible even after relaxation: take the highest-P candidates and rank them by P only
        idx = np.argsort(-ev.P)[: max(spec.budget.n_refine * 5, 50)]
        diag["fallback_highest_P"] = True
    else:
        idx = np.flatnonzero(feasible)
    Fm = (-ev.P[idx][:, None]) if fallback else ev_.objective_matrix(ev)[idx]
    if len(idx) > 5000:                          # keep the best 5000 by P before O(n^2) sorting
        keep = np.argsort(-ev.P[idx])[:5000]
        idx, Fm = idx[keep], Fm[keep]
    rank = fast_nondominated_sort(Fm)
    cd = crowding_distance(Fm)
    order = np.lexsort((-cd, rank))
    pool = idx[order][: max(spec.budget.n_refine * 10, 50)]
    # ---- diverse shortlist in standardised composition space
    comp_cols = [f"b:{c}" for c in L.binder] + ["w_b"] + (["s_b"] if L.has_sb else []) + [f"a:{c}" for c in L.adm]
    Xc = ev.M.iloc[pool][comp_cols].to_numpy(float)
    sd = Xc.std(axis=0); sd[sd < 1e-9] = 1.0
    short = [pool[i] for i in farthest_point_subset((Xc - Xc.mean(axis=0)) / sd, spec.budget.n_refine)]
    diag["n_shortlist"] = len(short)
    # ---- stage 2: vectorised DE refinement around each shortlisted point (presence pattern frozen)
    t1 = time.time()
    Z_ref = []
    th_used = ev_.thresholds(diag.get("threshold_scale_used", 1.0))
    ad_max_used = diag.get("ad_max_used", spec.risk.ad_max)
    obj_scale = np.maximum(np.nanstd(ev_.objective_matrix(ev)[idx], axis=0), 1e-9)
    for z0 in Z[short]:
        if time.time() - t0 > spec.budget.time_limit_s:
            diag["time_limit_hit"] = True
            break
        gate_idx = list(range(L.i_gate.start, L.i_gate.stop)) + [L.i_adm[0] + j for j in range(len(L.adm))] + \
            [L.i_fib[0] + j for j in range(len(L.fib))]
        cont = np.array([i for i in range(L.D) if i not in gate_idx])

        def f(Zc):  # Zc: (len(cont), S) with vectorized=True
            S = Zc.shape[1]
            Zfull = np.tile(z0, (S, 1))
            Zfull[:, cont] = Zc.T
            e = ev_.evaluate(Zfull)
            Fm_ = ev_.objective_matrix(e) / obj_scale
            w = np.array([o.weight for o in spec.objectives]) if spec.objectives else np.ones(Fm_.shape[1])
            pen_p = sum(np.maximum(0, thr - e.p[q]) ** 2 for q, thr in th_used.items())
            pen_ad = sum(np.maximum(0, e.ad[q] - ad_max_used) ** 2 for q in e.ad)
            return (Fm_ * w).sum(axis=1) + 25.0 * pen_p + 25.0 * pen_ad

        init = np.clip(z0[cont] + np.random.default_rng(spec.seed).normal(0, 0.08, (10 * len(cont), len(cont))), 0, 1)
        init[0] = z0[cont]
        res = differential_evolution(f, bounds=[(0, 1)] * len(cont), init=init, maxiter=spec.budget.refine_generations,
                                     popsize=10, tol=1e-6, polish=False, vectorized=True, updating="deferred",
                                     seed=spec.seed)
        zr = z0.copy(); zr[cont] = res.x
        Z_ref.append(zr)
    diag["t_stage2_s"] = round(time.time() - t1, 1)
    Z_final = np.vstack([Z[short]] + ([np.vstack(Z_ref)] if Z_ref else []))
    final = ev_.evaluate(Z_final)
    Fm_f = (-final.P[:, None]) if fallback else ev_.objective_matrix(final)
    rank_f = fast_nondominated_sort(Fm_f)
    cd_f = crowding_distance(Fm_f)
    diag["n_final"] = len(Z_final)
    diag["evaluator_calls"] = ev_.n_calls
    diag["t_total_s"] = round(time.time() - t0, 1)
    diag["weak_models"] = [q for q, w in ev_.weak.items() if w]
    return DesignRun(spec, ev, final, Z_final, rank_f, cd_f, diag)
