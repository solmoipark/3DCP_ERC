"""Metadata tools: model registry and material vocabulary."""
from __future__ import annotations

from ... import vocab as V
from ...schema import COMPARABILITY_GROUPS
from .normalise import CURING_PRESETS, KOR_TARGET, classes_of
from .registry import ToolContext, ToolResult, tool


@tool("list_models",
      "학습된 예측 모델 목록과 품질(논문 단위 교차검증 R², 80 % 구간 커버리지, weak 여부). 어떤 성능을 예측할 수 있는지, "
      "3DCP 전용 변형이 있는지 확인할 때 사용.",
      {"properties": {"variant": {"type": "string", "enum": ["general", "3dcp", "all"], "description": "기본 all"}}})
def list_models(args: dict, ctx: ToolContext) -> ToolResult:
    man = ctx.runtime.assets.manifest["models"]
    want = args.get("variant", "all")
    rows = []
    for k, m in man.items():
        if want != "all" and m.get("variant") != want:
            continue
        rows.append(dict(key=k, target=m["target"], name_ko=KOR_TARGET.get(m["target"], m["target"]), variant=m.get("variant"),
                         unit=m.get("unit"), n_train=m.get("n_train"), n_papers=m.get("n_papers"), r2=m.get("r2"), r2_log=m.get("r2_log"),
                         spearman=m.get("spearman"), coverage80=m.get("coverage80"), weak_model=bool(m.get("weak_model", False)), tier=m.get("tier")))
    rows.sort(key=lambda r: (r["target"], r["variant"] != "general"))
    bs = ctx.runtime.build_summary()
    return ToolResult(data=dict(models=rows, n_models=len(rows), build_summary=bs,
                                note="weak_model = 80 % 구간이 매우 넓음(유변 타깃 대부분): 예측은 자릿수 참고, 문헌 유사 배합을 1차 근거로."),
                      summary=f"{len(rows)}개 모델")


@tool("describe_vocabulary",
      "재료 클래스 이름(결합재·혼화제·섬유·활성화제·나노·골재), 압축시험 시험편 그룹, 양생 프리셋, 예측 타깃과 단위를 조회. "
      "배합 dict를 만들기 전에 정확한 material_class 이름을 확인할 때 사용.",
      {"properties": {"family": {"type": "string", "enum": ["powder", "admixture", "fibre", "activator", "nano", "aggregate", "all"],
                                 "description": "재료군; 기본 all"},
                      "query": {"type": "string", "description": "이름 부분 문자열 필터 (예: 'vma', 'fly_ash')"}}})
def describe_vocabulary(args: dict, ctx: ToolContext) -> ToolResult:
    fam = args.get("family", "all")
    q = (args.get("query") or "").lower()
    c2g, gd = V.class_to_group(), V.group_defaults()
    fams = ["powder", "admixture", "fibre", "activator", "nano", "aggregate"] if fam == "all" else [fam]
    classes = {}
    for f in fams:
        names = [c for c in classes_of(f) if not q or q in c.lower() or q in (c2g[c] or "").lower()]
        classes[f] = [dict(material_class=c, group=c2g[c], sg=gd[c2g[c]].sg, solid_content=gd[c2g[c]].solid_content) for c in names]
    from ...targets import load_target_rules
    rules, _ = load_target_rules()
    targets = [dict(quantity=k, name_ko=KOR_TARGET.get(k, k), unit=v.get("unit"), requires_age=bool(v.get("requires_age")),
                    covariates=v.get("covariates", []), tier=v.get("tier")) for k, v in rules.items()]
    targets += [dict(quantity="shear_stress_at_rate", name_ko=KOR_TARGET["shear_stress_at_rate"], unit="Pa", note="conditions.shear_rate_1s 필요"),
                dict(quantity="static_yield_stress_at_rest", name_ko=KOR_TARGET["static_yield_stress_at_rest"], unit="Pa", note="conditions.rest_time_s 필요")]
    mix_example = dict(system_type="mortar", w_b=0.35, s_b=1.5, binder={"portland_cement": 0.85, "silica_fume": 0.15},
                       admixtures_pct={"superplasticiser_pce": 0.5, "vma_cellulose": 0.2}, fibres_vol_pct={}, nano_pct={},
                       conditions=dict(age_d=28, comparability_group="comp_cube50", curing="습윤 양생 (20 °C, RH 95 %)", rest_time_s=0, is_3dcp=True),
                       name="example")
    return ToolResult(data=dict(classes=classes, comparability_groups=COMPARABILITY_GROUPS, curing_presets=list(CURING_PRESETS),
                                targets=targets, mix_dict_example=mix_example,
                                conventions="binder: 결합재(powder) 질량분율 합 1; s_b: 잔골재/결합재 질량비(모르타르); admixtures_pct: 결합재 질량 대비 % (제품 투입량); "
                                            "fibres_vol_pct: 혼합물 부피 %; nano_pct: 결합재 대비 %; activators: {class: {amount(결합재 대비 질량비), molarity}}"),
                      summary=f"{sum(len(v) for v in classes.values())}개 클래스")
