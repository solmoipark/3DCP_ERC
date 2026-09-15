"""Buildability / print schedule tools."""
from __future__ import annotations

import math

import numpy as np

from ... import buildability as B
from .design_tools import SPACE_SCHEMA, TARGET_ROW
from .normalise import job_from_dict, mix_from_dict
from .predict_tools import MIX_SCHEMA
from .registry import Artifact, ToolContext, ToolResult, frame_to_result, save_fig, save_text, tool

JOB_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "description": "프린트 작업. 층 높이/폭·사이클 시간이 없으면 출력 가능 런 중앙값(0.5·노즐, 1.2·노즐, 경로/속도)으로 채움.",
    "properties": {
        "name": {"type": "string"},
        "object_type": {"type": "string", "enum": ["wall", "hollow_cylinder", "column", "other"]},
        "target_height_mm": {"type": "number"},
        "footprint_mm": {"type": "number", "description": "벽 길이 또는 원통 직경 (mm) → 층당 경로 길이"},
        "path_length_mm": {"type": "number", "description": "층당 경로 길이 직접 지정"},
        "wall_filaments": {"type": "integer", "description": "벽 두께 방향 필라멘트 수"},
        "nozzle_d_mm": {"type": "number"}, "nozzle_w_mm": {"type": "number"}, "nozzle_h_mm": {"type": "number"},
        "layer_height_mm": {"type": "number"}, "layer_width_mm": {"type": "number"},
        "print_speed_mm_s": {"type": "number"}, "layer_cycle_time_s": {"type": "number"}, "dwell_s": {"type": "number"},
        "start_time_after_mixing_min": {"type": "number"}, "open_time_min": {"type": "number", "description": "0 또는 생략 = 미지정"},
        "safety_factor": {"type": "number", "description": "하중 안전율, 기본 1.5"},
        "check_buckling": {"type": "boolean", "description": "자유 벽 좌굴 검토(벽만), 기본 true"},
    },
    "required": ["target_height_mm"],
}
MATERIAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "description": "측정된 신선 상태 (mix 대신)",
    "properties": {"tau_s0_Pa": {"type": "number", "description": "정적항복응력 at 토출 (Pa)"},
                   "athix_Pa_s": {"type": "number", "description": "구조화속도 (Pa/s); 생략 시 보정 비율×τ_s0"},
                   "rho_kg_m3": {"type": "number"}, "E_over_tau": {"type": "number"},
                   "dynamic_yield_Pa": {"type": "number"}, "plastic_viscosity_Pa_s": {"type": "number"}},
    "required": ["tau_s0_Pa"],
}


def _material(args: dict, ctx: ToolContext) -> tuple[B.FreshMaterial, list[str]]:
    warns = []
    if args.get("material"):
        m = args["material"]
        mat = B.FreshMaterial(tau_s0_Pa=float(m["tau_s0_Pa"]), athix_Pa_s=m.get("athix_Pa_s"), rho_kg_m3=float(m.get("rho_kg_m3", 2100.0)),
                              E_over_tau=float(m.get("E_over_tau", 25.0)), dynamic_yield_Pa=m.get("dynamic_yield_Pa"),
                              plastic_viscosity_Pa_s=m.get("plastic_viscosity_Pa_s"), source="measured (user)")
    elif args.get("mix"):
        spec, warns = mix_from_dict(args["mix"])
        mat = B.material_from_mix(spec, ctx.runtime.cfg, ctx.runtime.assets)
        if args.get("rho_kg_m3"):
            mat.rho_kg_m3 = float(args["rho_kg_m3"])
        if args.get("E_over_tau"):
            mat.E_over_tau = float(args["E_over_tau"])
    else:
        raise ValueError("give either material {tau_s0_Pa, athix_Pa_s,...} or mix")
    return mat, warns


def _fin(x):
    return None if x is None or (isinstance(x, float) and (math.isinf(x) or math.isnan(x))) else x


def _sweep_fig(sc: dict, v: B.Verdict, sf: float):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ...flowcurve import _korean_font
    _korean_font()
    sw = sc["sweep"]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.plot(sw.layer_cycle_time_s, sw.n_max.clip(upper=v.n_target * 3), label="n_max (sf 1)")
    ax.plot(sw.layer_cycle_time_s, sw.n_max_sf.clip(upper=v.n_target * 3), label=f"n_max (sf {sf:g})", ls="--")
    ax.axhline(v.n_target, color="k", lw=0.8, label=f"목표 {v.n_target} 층")
    ax.axvline(v.layer_cycle_time_s, color="gray", lw=0.8, ls=":", label="현재 사이클")
    if np.isfinite(sc["t_c_max_s"]):
        lo = sc["t_c_min_s"] if np.isfinite(sc["t_c_min_s"]) else sw.layer_cycle_time_s.min()
        ax.axvspan(max(lo, 1e-3), max(sc["t_c_max_s"], lo + 1e-3), color="green" if sc["feasible"] else "red", alpha=0.08)
    ax.set_xscale("log"); ax.set_xlabel("층 사이클 시간 (s)"); ax.set_ylabel("적층 가능 층 수"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
    return fig


def _schedule_dict(sc: dict) -> dict:
    return {k: _fin(v) for k, v in sc.items() if k not in ("sweep", "speed")} | {"speed": ({k: _fin(v) for k, v in sc["speed"].items()} if sc.get("speed") else None)}


@tool("assess_buildability",
      "프린트 작업(노즐·구조물·스케줄) × 신선 재료(측정값 또는 배합에서 예측) → 판정(printable/borderline/non_printable), "
      "Roussel 소성붕괴 n_max(구조화 포함)·Suiker 좌굴·오픈타임·출력 가능 유변 범위 플래그, 층 사이클 시간 창, 필요한 τ_s(0)/Athix, "
      "가장 비슷한 문헌 프린트. 물리 판정이 1차, 경험적 붕괴확률(146 스택 파괴 시험 ECDF)은 보조.",
      {"properties": {"job": JOB_SCHEMA, "material": MATERIAL_SCHEMA, "mix": MIX_SCHEMA,
                      "rho_kg_m3": {"type": "number"}, "E_over_tau": {"type": "number"}, "n_similar": {"type": "integer"}},
       "required": ["job"]})
def assess_buildability(args: dict, ctx: ToolContext) -> ToolResult:
    rt = ctx.runtime
    job = job_from_dict(args["job"])
    mat, warns = _material(args, ctx)
    v = B.assess(job, mat, rt.cal)
    sc = B.schedule(job, mat, rt.cal)
    an = B.similar_prints(job, mat, rt.cfg, k=int(args.get("n_similar", 8)), cal=rt.cal)
    md = B.render_markdown(job, mat, v, sc, an)
    arts = [save_text(md, ctx, f"assessment_{job.name}.md", f"빌더빌리티 평가 {job.name}"),
            save_fig(_sweep_fig(sc, v, job.safety_factor), ctx, f"cycle_sweep_{job.name}", f"사이클 시간 스윕 {job.name}")]
    d_sw, a_sw = frame_to_result(sc["sweep"], ctx, f"cycle_sweep_{job.name}", "스윕 표", max_rows=0)
    arts.append(a_sw)
    sim = []
    if len(an):
        d_an, a_an = frame_to_result(an, ctx, f"similar_prints_{job.name}", "유사 문헌 프린트", max_rows=8)
        arts.append(a_an); sim = d_an["rows"]
    jr, _ = job.resolve(rt.cal)
    data = dict(job=dict(name=jr.name, object_type=jr.object_type, target_height_mm=jr.target_height_mm, nozzle_eq_mm=jr.nozzle_eq_mm,
                         layer_height_mm=jr.layer_height_mm, layer_width_mm=jr.layer_width_mm, n_layers=jr.n_layers, layer_cycle_time_s=jr.layer_cycle_time_s,
                         print_speed_mm_s=jr.print_speed_mm_s, open_time_min=jr.open_time_min, safety_factor=jr.safety_factor),
                material=dict(tau_s0_Pa=mat.tau_s0_Pa, tau_s0_band=mat.tau_s0_band, athix_Pa_s=v.athix_Pa_s, athix_band=mat.athix_band,
                              rho_kg_m3=mat.rho_kg_m3, E_over_tau=mat.E_over_tau, source=mat.source),
                verdict=v.to_dict(), schedule=_schedule_dict(sc), similar_prints=sim, warnings=warns)
    return ToolResult(data=data, artifacts=arts, summary=f"{v.label} ({v.governing}); n_max {_fin(v.n_max_plastic) or '∞'} / 목표 {v.n_target}")


@tool("print_schedule",
      "주어진 재료로 목표 높이를 쌓기 위한 층 사이클 시간 창(최소=안정, 최대=오픈타임)과 경로 기준 속도 창, 총 프린트 시간. "
      "'사이클 타임/속도를 얼마로?' 질문용(assess_buildability의 가벼운 버전).",
      {"properties": {"job": JOB_SCHEMA, "material": MATERIAL_SCHEMA, "mix": MIX_SCHEMA}, "required": ["job"]})
def print_schedule(args: dict, ctx: ToolContext) -> ToolResult:
    rt = ctx.runtime
    job = job_from_dict(args["job"])
    mat, warns = _material(args, ctx)
    v = B.assess(job, mat, rt.cal)
    sc = B.schedule(job, mat, rt.cal)
    arts = [save_fig(_sweep_fig(sc, v, job.safety_factor), ctx, f"cycle_sweep_{job.name}", f"사이클 시간 스윕 {job.name}")]
    data = dict(schedule=_schedule_dict(sc), verdict_label=v.label, governing=v.governing, reasons=v.reasons,
                tau_s0_Pa=mat.tau_s0_Pa, athix_Pa_s=v.athix_Pa_s, warnings=warns)
    rec = sc["t_c_recommended_s"]
    return ToolResult(data=data, artifacts=arts, summary=(f"권장 사이클 {rec:.0f} s (창 {sc['t_c_min_s']:.0f}–{sc['t_c_max_s']:.0f} s)" if rec else "실현 가능한 창 없음"))


@tool("similar_prints",
      "print01 라벨 DB(1,014편·7,420 런)에서 노즐·층 높이·높이·τ_s가 가장 비슷한 문헌 프린트와 결과(printable/collapsed…)를 조회.",
      {"properties": {"job": JOB_SCHEMA, "material": MATERIAL_SCHEMA, "k": {"type": "integer"}}, "required": ["job"]})
def similar_prints(args: dict, ctx: ToolContext) -> ToolResult:
    rt = ctx.runtime
    job = job_from_dict(args["job"])
    mat = None
    if args.get("material"):
        mat, _ = _material(args, ctx)
    an = B.similar_prints(job, mat, rt.cfg, k=int(args.get("k", 8)), cal=rt.cal)
    if not len(an):
        return ToolResult(data=dict(n=0, note="data/print_runs.parquet 없음 또는 매칭 없음"), summary="없음")
    d, a = frame_to_result(an, ctx, f"similar_prints_{job.name}", "유사 문헌 프린트", max_rows=int(args.get("k", 8)))
    return ToolResult(data=d, artifacts=[a], summary=f"유사 프린트 {len(an)}건")


@tool("design_for_print_job",
      "프린트 작업 → 필요한 유변 물성(Roussel: 프린트 종료 시 τ_s ≥ sf·ρgH/√3, 노즐 등급 출력 가능 범위) → 역설계로 후보 배합 → "
      "후보마다 예측 신선 상태로 판정·스케줄. 느림(30–150 s). 실행 전 사용자 확인 권장.",
      {"properties": {"job": JOB_SCHEMA, "space": SPACE_SCHEMA,
                      "extra_targets": {"type": "array", "items": TARGET_ROW, "description": "예: 28 d 압축강도 ≥ 30 MPa"},
                      "budget": {"type": "object", "additionalProperties": False,
                                 "properties": {"n_samples": {"type": "integer"}, "n_refine": {"type": "integer"}, "time_limit_s": {"type": "number"}}},
                      "rho_kg_m3": {"type": "number"}},
       "required": ["job"]}, slow=True, timeout_s=300)
def design_for_print_job(args: dict, ctx: ToolContext) -> ToolResult:
    from ...design.spec import TEMPLATES
    from .normalise import space_from_dict, target_rows_to_specs
    rt = ctx.runtime
    job = job_from_dict(args["job"])
    space = space_from_dict(args["space"]) if args.get("space") else dict(TEMPLATES["3dcp_printable_mortar"]["space"])
    extra = target_rows_to_specs(args["extra_targets"]) if args.get("extra_targets") else \
        [dict(quantity="compressive_strength", kind="ge", lo=30, unit="MPa", conditions=dict(age_d=28, comparability_group="comp_cube50"), p_min=0.6)]
    budget = dict(n_samples=4096, n_refine=5, refine_generations=12, time_limit_s=150) | dict(args.get("budget") or {})
    ctx.progress(10, "요구 유변 물성 계산 + 역설계")
    out = ctx.artifact_dir / f"printdesign_{job.name}"
    res, table, d, info, paths = B.design_for_job(job, space, rt.cfg, out_dir=out, extra_targets=extra, rho=float(args.get("rho_kg_m3", 2100.0)),
                                                  cal=rt.cal, budget=budget)
    ctx.progress(100, "완료")
    kinds = {"report": "markdown", "candidates": "table", "literature": "table", "pareto": "image", "parallel": "image", "result": "json",
             "candidates_buildability": "table"}
    arts = [Artifact(path=str(p), kind=kinds.get(k, "file"), title=f"{k} ({job.name})") for k, p in paths.items()]
    rows = table.drop(columns=["mix_json"]).to_dict("records") if len(table) else []
    return ToolResult(data=dict(requirement=dict(n_layers=info["n_layers"], layer_cycle_time_s=info["layer_cycle_time_s"], print_time_s=info["print_time_s"],
                                                 tau_s_required_end_Pa=info["tau_s_required_end_Pa"], tau_s0_window=info["tau_s0_window"],
                                                 viscosity_cap=info["viscosity_cap"], defaults_used=info["defaults_used"]),
                                diagnostics={k: res.diagnostics.get(k) for k in ("n_sampled", "n_feasible", "relaxation", "p_min_used")},
                                candidates=rows, warnings=res.warnings,
                                note="유변 모델 구간이 넓어 P(안정)이 0.3 수준으로 낮은 것이 정상. 판정이 모두 non_printable이면 스케줄(사이클 시간) 쪽 답을 우선 제시."),
                      artifacts=arts, summary=f"후보 {len(rows)}개; 요구 τ_s(종료) {info['tau_s_required_end_Pa']:.0f} Pa")
