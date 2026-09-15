"""Forward prediction tools: MixSpec building, property prediction, flow and structuration curves."""
from __future__ import annotations

import json

import numpy as np

from .normalise import DEFAULT_TARGETS, KOR_TARGET, mix_from_dict
from .registry import Artifact, ToolContext, ToolResult, frame_to_result, save_fig, subsample, tool

MIX_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "description": "배합 dict. describe_vocabulary의 mix_dict_example 참고.",
    "properties": {
        "system_type": {"type": "string", "enum": ["mortar", "paste"]},
        "w_b": {"type": "number", "description": "물/결합재 질량비"},
        "s_b": {"type": "number", "description": "잔골재/결합재 질량비 (모르타르)"},
        "binder": {"type": "object", "additionalProperties": {"type": "number"}, "description": "결합재 클래스 → 질량분율 (합 1, 자동 정규화)"},
        "admixtures_pct": {"type": "object", "additionalProperties": {"type": "number"}, "description": "혼화제 클래스 → 결합재 대비 % (제품 기준)"},
        "fibres_vol_pct": {"type": "object", "additionalProperties": {"type": "number"}},
        "nano_pct": {"type": "object", "additionalProperties": {"type": "number"}},
        "activators": {"type": "object", "additionalProperties": {"type": "object", "properties": {"amount": {"type": "number"}, "molarity": {"type": "number"}},
                                                                   "additionalProperties": False}},
        "material_props": {"type": "object", "additionalProperties": {"type": "object"}, "description": "선택: 클래스별 {oxides:{SiO2..}, blaine_m2kg, sg, d50_um}"},
        "sand_class": {"type": "string"},
        "conditions": {"type": "object", "additionalProperties": False,
                       "properties": {"age_d": {"type": "number"}, "comparability_group": {"type": "string"},
                                      "curing": {"type": "string", "description": "양생 프리셋 이름 또는 water/moist/sealed/ambient/steam"},
                                      "rest_time_s": {"type": "number"}, "is_3dcp": {"type": "boolean"}}},
        "name": {"type": "string"},
    },
    "required": ["w_b", "binder"],
}


def _spec(args, ctx):
    spec, warns = mix_from_dict(args["mix"])
    return spec, warns


@tool("build_mix_spec",
      "배합 dict를 검증된 MixSpec JSON으로 변환(재료 클래스·분율·조건 확인). 예측 전에 배합이 올바른지 확인하거나 사용자에게 보여줄 때 사용.",
      {"properties": {"mix": MIX_SCHEMA}, "required": ["mix"]})
def build_mix_spec(args: dict, ctx: ToolContext) -> ToolResult:
    spec, warns = _spec(args, ctx)
    p = ctx.path(f"mix_{spec.name}.json")
    spec.to_json(p)
    return ToolResult(data=dict(mix_spec=spec.to_dict(), warnings=warns, components=[c.material_class for c in spec.components]),
                      artifacts=[Artifact(path=str(p), kind="json", title=f"MixSpec {spec.name}")], summary=f"MixSpec {spec.name} 검증 완료")


@tool("predict_properties",
      "배합의 성능(압축·휨강도, 플로우, 응결, 공극률, 정적/동적항복응력, 소성점도, Athix, 수축 등)을 80 % 예측구간과 함께 예측. "
      "targets를 비우면 기본 6개. conditions.is_3dcp=true이면 3DCP 전용 모델이 더 좋을 때 자동 선택.",
      {"properties": {"mix": MIX_SCHEMA,
                      "targets": {"type": "array", "items": {"type": "string"}, "description": "타깃 quantity 목록 (list_models 참고)"}},
       "required": ["mix"]})
def predict_properties(args: dict, ctx: ToolContext) -> ToolResult:
    from ...predict import predict_specs
    spec, warns = _spec(args, ctx)
    rt = ctx.runtime
    avail = rt.assets.available_targets()
    targets = [t for t in (args.get("targets") or DEFAULT_TARGETS) if t in avail]
    missing = [t for t in (args.get("targets") or []) if t not in avail]
    if not targets:
        return ToolResult(data=dict(error="no valid targets", available=avail), is_error=True)
    out = predict_specs([spec], rt.cfg, targets)
    man = rt.assets.manifest["models"]
    rows = []
    for r in out.itertuples():
        rows.append(dict(target=r.target, name_ko=KOR_TARGET.get(r.target, r.target), q10=r.q10, q50=r.q50, q90=r.q90, unit=r.unit,
                         model=r.model, weak_model=bool(man.get(r.model, {}).get("weak_model", False)),
                         n_range_violations=int(r.n_range_violations), range_violations=r.range_violations, n_train=r.n_train, cv_r2=r.cv_r2))
    data, art = frame_to_result(out, ctx, f"predictions_{spec.name}", f"예측 {spec.name}")
    data = dict(mix=spec.name, predictions=rows, warnings=warns + ([f"no model for: {', '.join(missing)}"] if missing else []), csv=data["csv"],
                conditions=dict(age_d=spec.conditions.age_d, comparability_group=spec.conditions.comparability_group,
                                rest_time_s=spec.conditions.rest_time_s, is_3dcp=spec.conditions.is_3dcp))
    # error-bar figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ...flowcurve import _korean_font
    kor = _korean_font()
    n = len(out)
    fig, axes = plt.subplots(1, n, figsize=(2.6 * n, 3.0), dpi=110)
    for ax, r in zip(np.atleast_1d(axes), out.itertuples()):
        ax.errorbar([0], [r.q50], yerr=[[max(r.q50 - r.q10, 0)], [max(r.q90 - r.q50, 0)]], fmt="o", color="#2563eb", capsize=6, lw=2)
        ax.set_xticks([]); ax.set_title(KOR_TARGET.get(r.target, r.target) if kor else r.target, fontsize=10)
        ax.set_ylabel(r.unit, fontsize=8); ax.grid(alpha=.3)
        if r.q90 / max(r.q10, 1e-9) > 30:
            ax.set_yscale("log")
    fig.tight_layout()
    arts = [art, save_fig(fig, ctx, f"predictions_{spec.name}", f"예측구간 {spec.name}")]
    top = "; ".join(f"{KOR_TARGET.get(r['target'], r['target'])} {r['q50']:.3g} {r['unit']}" for r in rows[:3])
    return ToolResult(data=data, artifacts=arts, summary=f"{len(rows)}개 타깃 예측 — {top}")


@tool("flow_curve",
      "Bingham 유동곡선 τ(γ̇)=τ₀+μγ̇ 예측(동적항복응력·소성점도 모델 분포 샘플링, 80 % 밴드)과 조성이 가장 가까운 문헌 실측 곡선. "
      "펌핑성·압출성 논의나 특정 전단속도에서의 응력이 필요할 때.",
      {"properties": {"mix": MIX_SCHEMA, "max_rate_1s": {"type": "number", "description": "최대 전단속도, 기본 150"},
                      "n_analogues": {"type": "integer", "description": "겹칠 문헌 곡선 수, 기본 3"}, "log_y": {"type": "boolean"}},
       "required": ["mix"]})
def flow_curve(args: dict, ctx: ToolContext) -> ToolResult:
    from ...flowcurve import analogue_curves, plot_flow_curve, predict_flow_curves
    spec, warns = _spec(args, ctx)
    rt = ctx.runtime
    gmax = float(args.get("max_rate_1s", 150.0))
    rates = np.concatenate([[0.0], np.geomspace(0.5, gmax, 40)])
    P, band = predict_flow_curves([spec], rt.cfg, rates, rt.assets)
    k = int(args.get("n_analogues", 3))
    an = analogue_curves(spec, rt.cfg, k=k, assets=rt.assets) if k > 0 else None
    r = P.iloc[0]
    fig = plot_flow_curve(band, an, title=spec.name, log_y=bool(args.get("log_y", False)))
    arts = [save_fig(fig, ctx, f"flow_curve_{spec.name}", f"유동곡선 {spec.name}")]
    d, art = frame_to_result(band, ctx, f"flow_curve_{spec.name}", f"유동곡선 표 {spec.name}", max_rows=0)
    arts.append(art)
    analog = []
    if an is not None and len(an):
        for u, g in an.groupby("mix_uid"):
            analog.append(dict(doi=u.split("::")[0], mix=u.split("::")[-1], distance=float(g.distance.iloc[0]), n_points=int(len(g))))
    data = dict(mix=spec.name, tau0_Pa=dict(q10=r.tau0_q10, q50=r.tau0_q50, q90=r.tau0_q90, weak=bool(r.tau0_weak)),
                mu_Pa_s=dict(q10=r.mu_q10, q50=r.mu_q50, q90=r.mu_q90, weak=bool(r.mu_weak)),
                curve_points=subsample(band[["shear_rate", "q10", "q50", "q90"]], 8), analogues=analog, warnings=warns, csv=d["csv"],
                note="점단위 오차 중앙 ×2.1, 밴드 커버리지 86 % (실측 137 믹스 OOF): 자릿수·경향 참고용")
    return ToolResult(data=data, artifacts=arts, summary=f"τ₀ {r.tau0_q50:.0f} Pa, μ {r.mu_q50:.1f} Pa·s")


@tool("structuration_curve",
      "구조화 곡선 τ_s(t)=τ_s(0)+Athix·t 예측(정적항복응력·Athix 모델 분포 샘플링, 80 % 밴드)과 문헌 실측 곡선. "
      "빌더빌리티 논의에서 휴지시간에 따른 정적항복응력 증가가 필요할 때.",
      {"properties": {"mix": MIX_SCHEMA, "max_rest_min": {"type": "number", "description": "최대 휴지시간(분), 기본 60"},
                      "n_analogues": {"type": "integer", "description": "기본 3"}},
       "required": ["mix"]})
def structuration_curve(args: dict, ctx: ToolContext) -> ToolResult:
    from ...thixocurve import analogue_static_curves, plot_static_curve, predict_static_curve
    spec, warns = _spec(args, ctx)
    rt = ctx.runtime
    tmax = float(args.get("max_rest_min", 60.0))
    rest = np.concatenate([[0.0], np.geomspace(30.0, tmax * 60.0, 30)])
    curve, info = predict_static_curve(spec, rt.cfg, rest, rt.assets)
    k = int(args.get("n_analogues", 3))
    an = analogue_static_curves(spec, rt.cfg, k=k, assets=rt.assets) if k > 0 else None
    fig = plot_static_curve(curve, an, title=spec.name, log_y=True, show_physical=False)
    arts = [save_fig(fig, ctx, f"structuration_{spec.name}", f"구조화곡선 {spec.name}")]
    d, art = frame_to_result(curve, ctx, f"structuration_{spec.name}", f"구조화곡선 표 {spec.name}", max_rows=0)
    arts.append(art)
    P = curve[curve.route == "physical"] if (curve.route == "physical").any() else curve[curve.route == "model"]
    t0 = info["tau0_model"]
    analog = []
    if an is not None and len(an):
        for u, g in an.groupby("mix_uid"):
            analog.append(dict(doi=u.split("::")[0], mix=u.split("::")[-1], distance=float(g.distance.iloc[0]), n_points=int(len(g))))
    data = dict(mix=spec.name, tau_s0_Pa=dict(q10=t0[0], q50=t0[1], q90=t0[2], weak=info["static_weak"]),
                athix_Pa_s=(dict(q10=info["athix_model"][0], q50=info["athix_model"][1], q90=info["athix_model"][2], weak=info.get("athix_weak")) if info.get("athix_model") else None),
                tau_s_at_max_rest=dict(rest_s=float(P.rest_s.iloc[-1]), q10=float(P.q10.iloc[-1]), q50=float(P.q50.iloc[-1]), q90=float(P.q90.iloc[-1])),
                curve_points=subsample(P[["rest_s", "q10", "q50", "q90"]], 8), analogues=analog, warnings=warns, csv=d["csv"],
                note="선형 Roussel 모델; 실측 곡선(91 믹스) 0–80 분 선형 R² 중앙 0.92")
    return ToolResult(data=data, artifacts=arts, summary=f"τ_s(0) {t0[1]:.0f} Pa → {P.q50.iloc[-1]:.0f} Pa @ {P.rest_s.iloc[-1] / 60:.0f} min")
