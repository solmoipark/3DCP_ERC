"""Assemble a DesignResult from an optimisation run and render JSON / CSV / Markdown."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .. import __version__
from ..config import PipelineConfig
from ..schema import MixSpec
from .objectives import OBJECTIVE_COLUMN
from .optimize import DesignRun, Evaluator
from .retrieve import LiteratureHit, LiteratureStore, analogues, retrieve
from .spec import DesignSpec


@dataclass
class TargetPrediction:
    quantity: str
    unit: str
    q10: float
    q50: float
    q90: float
    p_satisfied: float
    ad_score: float
    n_train: int
    weak_model: bool


@dataclass
class Candidate:
    rank: int
    name: str
    mix: dict
    z: list[float]
    predictions: dict[str, TargetPrediction]
    p_feasible: float                   # product over constraint targets (independence assumption)
    p_min_targets: float                # binding target: min over constraint targets of P(satisfied)
    ad_max: float
    feasible: bool
    pareto_rank: int
    crowding: float
    objectives: dict[str, float]
    summary: str
    analogues: list[dict] = field(default_factory=list)
    refined: bool = False


@dataclass
class DesignResult:
    spec: dict
    created: str
    package_version: str
    models: dict
    tables: dict
    candidates: list[Candidate]
    literature: list[dict]
    diagnostics: dict
    warnings: list[str]

    def to_json(self, path: Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=1, default=_default), encoding="utf-8")


def _compact(o):
    """Drop None / empty containers recursively (for readable MixSpec JSON in reports)."""
    if isinstance(o, dict):
        return {k: _compact(v) for k, v in o.items() if v is not None and v != {} and v != []}
    if isinstance(o, list):
        return [_compact(v) for v in o]
    return o


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _summary(m: MixSpec) -> str:
    from .. import vocab as V
    parts = [f"{c.material_class} {c.amount:.2f}" for c in m.components if c.amount is not None
             and V.resolve_group(c.material_class, c.role).family == "powder"]
    s = " / ".join(parts)
    if m.water_binder is not None:
        s += f"; w/b {m.water_binder:.3f}"
    if m.sand_binder is not None:
        s += f"; s/b {m.sand_binder:.2f}"
    adm = [f"{c.material_class} {100 * c.amount:.2f}%" for c in m.components if c.amount is not None
           and V.resolve_group(c.material_class, c.role).family == "admixture"]
    if adm:
        s += "; " + ", ".join(adm)
    fib = [f"{c.material_class} {c.vol_pct:.2f} vol%" for c in m.components if c.vol_pct]
    if fib:
        s += "; " + ", ".join(fib)
    return s


def build_result(run: DesignRun, ev: Evaluator, store: LiteratureStore | None, cfg: PipelineConfig,
                 warnings: list[str]) -> DesignResult:
    spec = run.spec
    f = run.final
    n_short = run.diagnostics.get("n_shortlist", 0)
    order = np.lexsort((-run.crowding, run.pareto_rank, ~f.feasible))
    order = [i for i in order if f.feasible[i]] + [i for i in order if not f.feasible[i]]
    # de-duplicate near-identical candidates (a shortlisted point and its refined copy): drop any
    # candidate within `tau` standard deviations (sweep-scale) of an already kept one in composition space
    L = ev.L
    comp_cols = [f"b:{c}" for c in L.binder] + ["w_b"] + (["s_b"] if L.has_sb else []) + \
        [f"a:{c}" for c in L.adm] + [f"f:{c}" for c in L.fib]
    sd = run.ev_all.M[comp_cols].to_numpy(float).std(axis=0)
    sd[sd < 1e-9] = 1.0
    X = f.M[comp_cols].to_numpy(float) / sd
    # admixture dosages count half: two mixes differing only by a little VMA are the same design
    n_main = len(L.binder) + 1 + int(L.has_sb)
    X[:, n_main:] *= 0.5
    tau = 0.8
    kept: list[int] = []
    for i in order:
        if all(np.linalg.norm(X[i] - X[j]) > tau for j in kept):
            kept.append(i)
    order = kept[: spec.output.top_n]
    man = ev.assets.manifest["models"]
    cands: list[Candidate] = []
    an = analogues(f.F.iloc[order], store, spec, k=3) if store is not None else [[] for _ in order]
    for rank, (i, alist) in enumerate(zip(order, an), start=1):
        preds = {}
        for t in spec.targets:
            k = t.label
            if k not in f.pred:
                continue
            q = f.pred[k].iloc[i]
            mi = ev.info(k)
            preds[k] = TargetPrediction(k, mi["unit"], float(q.q10), float(q.q50), float(q.q90),
                                        float(f.p[k][i]), float(f.ad[k][i]), int(mi.get("n_train") or 0), bool(mi.get("weak", False)))
        objs = {c: float(f.obj[c].iloc[i]) for c in f.obj.columns}
        mix = f.specs[i]
        mix.name = f"cand_{rank:02d}"
        cons = [preds[t.label].p_satisfied for t in spec.targets if t.is_constraint and t.label in preds]
        cands.append(Candidate(rank=rank, name=mix.name, mix=mix.to_dict(), z=[float(v) for v in run.Z_final[i]],
                               predictions=preds, p_feasible=float(f.P[i]), p_min_targets=float(min(cons)) if cons else 1.0,
                               ad_max=float(f.AD[i]), feasible=bool(f.feasible[i]),
                               pareto_rank=int(run.pareto_rank[i]), crowding=float(run.crowding[i]), objectives=objs,
                               summary=_summary(mix), analogues=[h.to_dict() for h in alist], refined=i >= n_short))
    lit = [h.to_dict() for h in retrieve(spec, store)] if store is not None else []
    models = {t.label: ev.info(t.label) for t in spec.targets if t.label in f.pred}
    tables = dict(cost=ev.cost.provenance(), co2=ev.co2.provenance())
    return DesignResult(spec=spec.to_dict(), created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        package_version=__version__, models=models, tables=tables, candidates=cands, literature=lit,
                        diagnostics=run.diagnostics, warnings=warnings)


# ---------------------------------------------------------------- rendering
def _fmt(v, d=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return f"{v:.{d}g}"


def candidates_frame(res: DesignResult) -> pd.DataFrame:
    rows = []
    for c in res.candidates:
        r = dict(rank=c.rank, name=c.name, summary=c.summary, p_feasible=c.p_feasible, p_min_targets=c.p_min_targets,
                 ad_max=c.ad_max, feasible=c.feasible,
                 pareto_rank=c.pareto_rank, refined=c.refined)
        for q, p in c.predictions.items():
            r[f"{q}_q50"] = p.q50; r[f"{q}_q10"] = p.q10; r[f"{q}_q90"] = p.q90; r[f"{q}_p"] = p.p_satisfied; r[f"{q}_ad"] = p.ad_score
        r.update({k: v for k, v in c.objectives.items()})
        r["analogue_doi"] = c.analogues[0]["doi"] if c.analogues else ""
        r["analogue_distance"] = c.analogues[0]["feature_distance"] if c.analogues else None
        rows.append(r)
    return pd.DataFrame(rows)


def literature_frame(res: DesignResult) -> pd.DataFrame:
    rows = []
    for h in res.literature:
        r = dict(tier=h["tier"], score=h["score"], doi=h["doi"], year=h["year"], is_3dcp=h["is_3dcp"], mix=h["mix_name"],
                 system_type=h["system_type"], composition=h["composition_summary"], target_distance=h["target_distance"],
                 coverage=h["coverage"], penalty=h["qualifier_penalty"])
        for m in h["measured"]:
            key = m["quantity"] + (f"@{m['age_d']:g}d" if m["age_d"] else "")
            r[key] = m["value"]
        rows.append(r)
    return pd.DataFrame(rows)


def render_markdown(res: DesignResult) -> str:
    spec = res.spec
    L = [f"# Design report — {spec['name']}", "", f"Generated {res.created} · pmpredict {res.package_version}", ""]
    if res.warnings:
        L += ["## Warnings", *[f"- {w}" for w in res.warnings], ""]
    L += ["## Request", "", "| target | kind | lo | hi | goal | conditions |", "|---|---|---|---|---|---|"]
    for t in spec["targets"]:
        cond = ", ".join(f"{k}={v}" for k, v in (t["conditions"] or {}).items() if v is not None)
        L.append(f"| {t['quantity']} | {t['kind']} | {_fmt(t['lo'])} | {_fmt(t['hi'])} | {_fmt(t['goal'])} | {cond} |")
    sp = spec["space"]
    L += ["", f"Space: {sp['system_type']}, w/b {sp['w_b']}, s/b {sp.get('s_b')}, binder {list(sp['binder'])}, "
          f"admixtures {list(sp['admixtures'])}, max binder components {sp['max_binder_components']}.",
          f"Objectives: {[o['name'] + ' ' + o['direction'] for o in spec['objectives']] or 'feasibility only'}. "
          f"Risk: p_min {spec['risk']['p_min']}, ad_max {spec['risk']['ad_max']}, combine {spec['risk']['combine']}.", ""]
    L += ["## Models used", "", "| target | model | n | papers | R² | R²(log) | Spearman | cov80 | weak |", "|---|---|---|---|---|---|---|---|---|"]
    for q, m in res.models.items():
        L.append(f"| {q} | {m['key']} | {m['n_train']} | {m['n_papers']} | {_fmt(m['r2'])} | {_fmt(m['r2_log'])} | "
                 f"{_fmt(m['spearman'])} | {_fmt(m['coverage80'], 2)} | {'**yes**' if m['weak'] else ''} |")
    if any(m["weak"] for m in res.models.values()):
        L.append("\nWeak models give order-of-magnitude guidance only; treat the literature hits below as the primary "
                 "evidence for those targets.")
    d = res.diagnostics
    L += ["", "## Candidates", "",
          f"Sampled {d.get('n_sampled')} → feasible {d.get('n_feasible')} at the requested thresholds"
          + (f"; relaxed to per-target p_min {d.get('p_min_used')} and ad_max {d.get('ad_max_used')}" if d.get("relaxation") else "")
          + f". Shortlist {d.get('n_shortlist')}, refined {d.get('n_final', 0) - d.get('n_shortlist', 0)}. "
          "Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.", ""]
    qs = list(res.candidates[0].predictions) if res.candidates else []
    L.append("| # | composition | " + " | ".join(qs) + " | P_min | P_prod | AD | " + " | ".join(o["name"] for o in spec["objectives"]) + " | analogue |")
    L.append("|---|---|" + "---|" * len(qs) + "---|---|---|" + "---|" * len(spec["objectives"]) + "---|")
    for c in res.candidates:
        cells = []
        for q in qs:
            p = c.predictions[q]
            cells.append(f"{_fmt(p.q50)} [{_fmt(p.q10)}, {_fmt(p.q90)}] p={p.p_satisfied:.2f}" + (" ⚠" if p.weak_model else ""))
        objs = [_fmt(c.objectives.get(OBJECTIVE_COLUMN.get(o["name"], o["name"]))) for o in spec["objectives"]]
        an = c.analogues[0] if c.analogues else None
        an_s = f"{an['doi']} (d={an['feature_distance']:.2f})" if an else ""
        L.append(f"| {c.rank}{'*' if c.refined else ''} | {c.summary} | " + " | ".join(cells) + f" | {c.p_min_targets:.2f} | {c.p_feasible:.2f} | {c.ad_max:.2f} | "
                 + " | ".join(objs) + f" | {an_s} |")
    L += ["", "\\* refined by differential evolution. P_min = lowest per-target probability (the binding target); "
          "P_prod = product over targets. Units: " + ", ".join(f"{q} [{res.models[q]['unit']}]" for q in qs), ""]
    for c in res.candidates[: min(len(res.candidates), 5)]:
        L += [f"### Candidate {c.rank} — {c.summary}", "", "```json", json.dumps(_compact(c.mix), indent=1, ensure_ascii=False), "```"]
        for an in c.analogues[:2]:
            meas = "; ".join(f"{m['quantity']}={_fmt(m['value'])} {m['unit']}" + (f" @{m['age_d']:g} d" if m["age_d"] else "")
                             for m in an["measured"][:4])
            L.append(f"- analogue {an['doi']} '{an['mix_name']}' (composition distance {an['feature_distance']:.2f}): "
                     f"{an['composition_summary']} → {meas or 'no matching measurements'}"
                     + (f"; deviations: {'; '.join(an['top_deviations'])}" if an["top_deviations"] else ""))
        L.append("")
    L += ["## Published mixes near the target", ""]
    if res.literature:
        L += ["| tier | score | DOI | mix | composition | measured |", "|---|---|---|---|---|---|"]
        for h in res.literature:
            meas = "; ".join(f"{m['quantity']}={_fmt(m['value'])}" + (f"@{m['age_d']:g}d" if m["age_d"] else "") for m in h["measured"][:4])
            L.append(f"| {h['tier']} | {h['score']:.2f} | {h['doi']} | {h['mix_name']} | {h['composition_summary']} | {meas} |")
    else:
        L.append("(no literature store available)")
    L += ["", "## Provenance", "",
          f"Cost table: {res.tables['cost']['path']} (hash {res.tables['cost']['hash']}, {'DEFAULT PLACEHOLDER' if res.tables['cost']['default'] else 'user'}); "
          f"CO2 table: {res.tables['co2']['path']} (hash {res.tables['co2']['hash']}, {'DEFAULT PLACEHOLDER' if res.tables['co2']['default'] else 'user'}).",
          "" if not (res.tables["cost"]["default"] or res.tables["co2"]["default"]) else
          "**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**",
          "", f"Diagnostics: {json.dumps(d, default=_default)}"]
    return "\n".join(L) + "\n"


def write_outputs(res: DesignResult, out_dir: Path, plots: bool = True) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    res.to_json(out_dir / "result.json"); paths["result"] = out_dir / "result.json"
    (out_dir / "report.md").write_text(render_markdown(res), encoding="utf-8"); paths["report"] = out_dir / "report.md"
    candidates_frame(res).to_csv(out_dir / "candidates.csv", index=False); paths["candidates"] = out_dir / "candidates.csv"
    literature_frame(res).to_csv(out_dir / "literature.csv", index=False); paths["literature"] = out_dir / "literature.csv"
    for c in res.candidates:
        MixSpec.from_dict(c.mix).to_json(out_dir / f"{c.name}.json")
    if plots:
        from .plots import pareto_plot, parallel_plot
        p = pareto_plot(res, out_dir / "pareto.png")
        if p:
            paths["pareto"] = p
        p = parallel_plot(res, out_dir / "parallel_coords.png")
        if p:
            paths["parallel"] = p
    return paths
