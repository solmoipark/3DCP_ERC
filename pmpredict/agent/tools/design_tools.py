"""Inverse design and literature retrieval tools."""
from __future__ import annotations

from pathlib import Path

from .normalise import KOR_TARGET, design_from_dict
from .registry import Artifact, ToolContext, ToolResult, frame_to_result, tool

TARGET_ROW = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "quantity": {"type": "string", "description": "타깃 이름 (list_models/describe_vocabulary의 quantity). 예: compressive_strength, static_yield_stress, "
                                                        "flow_table_spread, shear_stress_at_rate(전단속도 지정), static_yield_stress_at_rest(휴지시간 지정)"},
        "kind": {"type": "string", "enum": ["ge", "le", "range", "goal"],
                 "description": "ge = 하한 이상(lo 필요) · le = 상한 이하(hi 필요) · range = lo–hi 사이(둘 다 필요) · goal = 목표값에 가깝게(goal 필요). 기본 ge. "
                                "'≥ 40 MPa'는 kind=ge, lo=40 이며 goal을 쓰지 않는다."},
        "lo": {"type": "number", "description": "하한 (ge, range에서 사용)"},
        "hi": {"type": "number", "description": "상한 (le, range에서 사용)"},
        "goal": {"type": "number", "description": "목표값 (kind=goal 전용; ge/le/range에서는 쓰지 않음)"},
        "unit": {"type": "string", "description": "입력값의 단위: MPa, kPa, Pa, mm, min, h, %, Pa.s … (정준 단위로 자동 변환)"},
        "age_d": {"type": "number", "description": "재령(일). 강도류에는 필수에 가까움(기본 28)"},
        "comparability_group": {"type": "string", "description": "압축 시험편 그룹 (comp_cube50 기본, comp_prism40, comp_cyl_small …)"},
        "shear_rate_1s": {"type": "number", "description": "shear_stress_at_rate 전용 전단속도 (1/s)"},
        "rest_time_s": {"type": "number", "description": "휴지시간 (s): static_yield_stress는 0(토출 직후), static_yield_stress_at_rest는 프린트/휴지 시간"},
        "p_min": {"type": "number", "description": "만족 확률 하한 0.05–1. 강도 0.6–0.7, 유변·플로우(weak 모델) 0.3–0.4 권장"},
    },
    "required": ["quantity"],
}
BOUNDS = {"type": "object", "additionalProperties": False,
          "properties": {"lo": {"type": "number"}, "hi": {"type": "number"}, "required": {"type": "boolean"}}}
SPACE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "description": "탐색 공간. 생략 시 OPC 필수 + 기본 범위.",
    "properties": {
        "system_type": {"type": "string", "enum": ["mortar", "paste"]},
        "is_3dcp": {"type": "boolean"},
        "w_b": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "s_b": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "binder": {"type": "object", "additionalProperties": BOUNDS, "description": "결합재 클래스 → {lo, hi, required}"},
        "max_binder_components": {"type": "integer"},
        "admixtures": {"type": "object", "additionalProperties": BOUNDS, "description": "혼화제 클래스 → {lo, hi} (결합재 대비 %)"},
        "curing": {"type": "string"},
        "fixed_conditions": {"type": "object", "additionalProperties": True},
    },
}


@tool("retrieve_literature",
      "목표 성능에 가까운 실제 문헌 배합을 검색(모델 불필요). tier exact = 모든 목표를 측정값으로 만족, near = 근접. "
      "3DCP 논문 우선 가능. 결과에 DOI·믹스명·조성 요약·측정값.",
      {"properties": {"targets": {"type": "array", "items": TARGET_ROW, "minItems": 1},
                      "system_type": {"type": "string", "enum": ["mortar", "paste"]},
                      "prefer_3dcp": {"type": "boolean"},
                      "n": {"type": "integer", "description": "기본 20"}},
       "required": ["targets"]})
def retrieve_literature(args: dict, ctx: ToolContext) -> ToolResult:
    from ...design.retrieve import retrieve
    rt = ctx.runtime
    spec, warns = design_from_dict(dict(targets=args["targets"], space=dict(system_type=args.get("system_type", "mortar"),
                                                                             is_3dcp=bool(args.get("prefer_3dcp", False)))), rt, retrieval_only=True)
    hits = retrieve(spec, rt.store, n=int(args.get("n", 20)))
    rows = [dict(tier=h.tier, score=round(h.score, 3), doi=h.doi, title=(h.title or "")[:120], year=h.year, is_3dcp=h.is_3dcp, mix=h.mix_name,
                 system_type=h.system_type, composition=h.composition_summary,
                 measured=[f"{m.quantity}={m.value:.3g}{m.unit}" + (f"@{m.age_d:g}d" if m.age_d else "") for m in h.measured[:5]]) for h in hits]
    import pandas as pd
    d, art = frame_to_result(pd.DataFrame(rows), ctx, "literature", "문헌 검색", max_rows=0)
    return ToolResult(data=dict(n_hits=len(rows), tiers={t: sum(r["tier"] == t for r in rows) for t in ("exact", "near")}, hits=rows[:12],
                                warnings=warns, csv=d["csv"]), artifacts=[art], summary=f"문헌 {len(rows)}건 (exact {sum(r['tier'] == 'exact' for r in rows)})")


@tool("design_mix",
      "역설계: 목표 성능 + 탐색 공간 → 확률적 스크리닝·정제로 후보 배합(Pareto)과 근처 문헌 배합. 느림(30–150 s). "
      "실행 전 사용자에게 목표·공간을 한 번 확인할 것(사용자가 이미 완전한 목표를 준 경우 제외).",
      {"properties": {"targets": {"type": "array", "items": TARGET_ROW, "minItems": 1},
                      "space": SPACE_SCHEMA,
                      "objectives": {"type": "array", "items": {"type": "string", "enum": ["clinker_fraction", "co2", "cost", "co2_per_mpa", "cost_per_mpa"]}},
                      "budget": {"type": "object", "additionalProperties": False,
                                 "properties": {"n_samples": {"type": "integer"}, "n_refine": {"type": "integer"}, "time_limit_s": {"type": "number"}}},
                      "top_n": {"type": "integer"}, "n_literature": {"type": "integer"}, "name": {"type": "string"}},
       "required": ["targets"]}, slow=True, timeout_s=300)
def design_mix(args: dict, ctx: ToolContext) -> ToolResult:
    from ...design.optimize import Evaluator, run_twostage
    from ...design.report import build_result, write_outputs
    rt = ctx.runtime
    spec, warns = design_from_dict(dict(args, name=args.get("name", "agent_design")), rt)
    ctx.progress(5, "Evaluator 준비")
    ev = Evaluator(spec, rt.cfg)
    ctx.progress(15, f"Sobol 스윕 + 정제 (최대 {spec.budget.time_limit_s:.0f} s)")
    run = run_twostage(spec, rt.cfg, evaluator=ev)
    ctx.progress(80, "문헌 검색 · 리포트")
    res = build_result(run, ev, rt.store, rt.cfg, warns)
    out = ctx.artifact_dir / f"design_{spec.name}"
    paths = write_outputs(res, out, plots=True)
    ctx.progress(100, "완료")
    cands = []
    for c in res.candidates[: spec.output.top_n]:
        preds = {q: dict(q50=p.q50, q10=p.q10, q90=p.q90, unit=p.unit, p=round(p.p_satisfied, 2), weak=p.weak_model) for q, p in c.predictions.items()}
        cands.append(dict(rank=c.rank, mix=c.summary, p_feasible=round(c.p_feasible, 3), p_min_targets=round(c.p_min_targets, 3), ad_max=round(c.ad_max, 2),
                          predictions=preds, objectives={k: round(v, 3) for k, v in c.objectives.items()},
                          analogue_doi=(c.analogues[0]["doi"] if c.analogues else None), mix_json=str(out / f"{c.name}.json")))
    lit = [dict(tier=h["tier"], doi=h["doi"], mix=h["mix_name"], year=h["year"], is_3dcp=h["is_3dcp"], composition=h["composition_summary"]) for h in res.literature[:5]]
    kinds = {"report": "markdown", "candidates": "table", "literature": "table", "pareto": "image", "parallel": "image", "result": "json"}
    arts = [Artifact(path=str(p), kind=kinds.get(k, "file"), title=f"{k} ({spec.name})") for k, p in paths.items()]
    diag = {k: res.diagnostics.get(k) for k in ("n_sampled", "n_feasible", "relaxation", "p_min_used", "t_total_s", "fallback_highest_P")}
    models = {q: dict(weak=m.get("weak"), n_train=m.get("n_train"), r2_log=m.get("r2_log")) for q, m in res.models.items()}
    return ToolResult(data=dict(name=spec.name, diagnostics=diag, warnings=res.warnings, models=models, candidates=cands, literature=lit,
                                targets=[dict(quantity=t.quantity, kind=t.kind, lo=t.lo, hi=t.hi, p_min=t.p_min) for t in spec.targets],
                                note="P는 타깃별 만족 확률의 곱(독립 가정). 유변 타깃 모델은 weak이므로 후보는 방향 제시, 문헌 배합이 1차 근거."),
                      artifacts=arts, summary=f"후보 {len(cands)}개, 실현가능 {diag['n_feasible']}/{diag['n_sampled']}")
