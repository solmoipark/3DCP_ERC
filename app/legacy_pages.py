# -*- coding: utf-8 -*-
"""Legacy form pages of the pmpredict UI (model status · prediction · curves · inverse design · buildability · retrieval).

Reached from the chat app (app/streamlit_app.py) through the sidebar toggle "직접 실행 (기존 폼)".
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pmpredict import vocab as V  # noqa: E402
from pmpredict.config import load_config  # noqa: E402
from pmpredict.schema import COMPARABILITY_GROUPS, Component, Conditions, MixSpec, SpecError  # noqa: E402


KOR_TARGET = {
    "compressive_strength": "압축강도", "flexural_strength": "휨강도", "direct_tensile_strength": "직접인장강도",
    "splitting_tensile_strength": "쪼갬인장강도", "elastic_modulus": "탄성계수", "flow_table_spread": "플로우(테이블)",
    "mini_slump_flow_diameter": "미니슬럼프 플로우", "initial_setting_time": "초결시간", "final_setting_time": "종결시간",
    "porosity_total": "총공극률", "water_absorption": "흡수율", "hardened_density": "경화 밀도",
    "dynamic_yield_stress": "동적항복응력", "static_yield_stress": "정적항복응력", "plastic_viscosity": "소성점도",
    "structuration_rate_athix": "구조화속도 Athix", "drying_shrinkage": "건조수축", "autogenous_shrinkage": "자기수축",
    "cumulative_heat": "누적수화열",
}
CURING_PRESETS = {"수중 양생 (20 °C)": ("water curing at 20 C", 20.0, 100.0), "습윤 양생 (20 °C, RH 95 %)": ("moist curing", 20.0, 95.0),
                  "밀봉 양생 (20 °C)": ("sealed curing", 20.0, None), "상온 공기 중": ("ambient air curing", 20.0, 60.0),
                  "증기/고온 양생 (60 °C)": ("steam curing at 60 C", 60.0, 100.0)}


# ------------------------------------------------------------------ cached resources (shared with the agent runtime)
from pmpredict.agent.tools.runtime import get_runtime as _get_runtime  # noqa: E402


@st.cache_resource(show_spinner="모델 로딩...")
def get_runtime():
    return _get_runtime()


def get_cfg():
    return get_runtime().cfg


def get_assets():
    return get_runtime().assets


def get_store():
    return get_runtime().store


def label(q: str) -> str:
    return f"{KOR_TARGET.get(q, q)} ({q})"


def classes_of(family: str) -> list[str]:
    return sorted(c for c, g in V.class_to_group().items() if g and V.group_defaults()[g].family == family)


def unit_of(assets, q: str) -> str:
    m = assets.manifest["models"].get(q)
    return m["unit"] if m else ""


# ------------------------------------------------------------------ page: status
def page_status():
    st.title("🧱 pmpredict — 모델 현황")
    cfg = get_cfg()
    assets = get_assets()
    bs = cfg.data_dir / "build_summary.json"
    if bs.exists():
        s = json.loads(bs.read_text(encoding="utf-8"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("정규화된 믹스", f"{s['n_normalised']:,} / {s['n_mixes']:,}")
        c2.metric("특성 수", s["n_features"])
        c3.metric("w/b 일치 (±0.02)", f"{100 * s['wb_agree_0p02']:.0f} %" if s.get("wb_agree_0p02") is not None else "n/a (build --qa)")
        c4.metric("스키마", s["schema_hash"])
    rows = []
    for k, m in assets.manifest["models"].items():
        rows.append(dict(타깃=label(m["target"]), 변형=m["variant"], 단위=m["unit"], n=m["n_train"], 논문=m["n_papers"],
                         R2=m.get("r2"), R2_log=m.get("r2_log"), Spearman=m.get("spearman"), cov80=m.get("coverage80"),
                         weak="⚠" if m.get("weak_model") else ""))
    df = pd.DataFrame(rows).sort_values(["변형", "타깃"])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%.3f") for c in ["R2", "R2_log", "Spearman", "cov80"]})
    st.caption("GroupKFold(논문 단위) out-of-fold 지표. R²는 원척도(꼬리가 긴 타깃에서는 극단값이 지배), R²(log)·Spearman은 로그척도 순위력. "
               "⚠ weak = n<300 또는 구간 커버리지<0.65 또는 R²(log)<0.15 — 자릿수 참고용.")
    smd = cfg.reports_dir / "summary.md"
    if smd.exists():
        with st.expander("summary.md 원문"):
            st.markdown(smd.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ mix input widget
def mix_form(key: str) -> MixSpec | None:
    """Interactive MixSpec builder; returns a validated MixSpec or None."""
    assets = get_assets()
    c1, c2, c3 = st.columns([1, 1, 1])
    system = c1.selectbox("시스템", ["mortar", "paste"], key=f"{key}_sys")
    wb = c2.number_input("w/b (물/결합재 질량비)", 0.05, 3.0, 0.40, 0.01, key=f"{key}_wb")
    sb = c3.number_input("s/b (잔골재/결합재 질량비)", 0.0, 8.0, 3.0 if system == "mortar" else 0.0, 0.05,
                         key=f"{key}_sb", disabled=(system == "paste"))
    st.markdown("**결합재(powder) 조성** — 질량분율, 합계 1")
    powder_classes = classes_of("powder")
    default_b = ["portland_cement"]
    sel = st.multiselect("결합재 재료", powder_classes, default=default_b, key=f"{key}_bsel")
    fracs = {}
    cols = st.columns(max(len(sel), 1))
    for i, c in enumerate(sel):
        fracs[c] = cols[i].number_input(c, 0.0, 1.0, 1.0 if len(sel) == 1 else (0.7 if i == 0 else round(0.3 / (len(sel) - 1), 3)),
                                         0.01, key=f"{key}_bf_{c}")
    tot = sum(fracs.values())
    if sel and abs(tot - 1) > 1e-6:
        st.info(f"결합재 분율 합 = {tot:.3f} → 자동 정규화됩니다.")
    with st.expander("혼화제 (감수제/HRWR/SP, VMA, 지연제, 촉진제 …) · 섬유 · 활성화제 · 나노재료", expanded=True):
        adm_sel = st.multiselect("혼화제 (결합재 질량 대비 %, 제품 투입량 기준)", classes_of("admixture"), default=["superplasticiser_pce"], key=f"{key}_asel",
                                 help="superplasticiser_pce = PCE계 고성능감수제(HRWR) · superplasticiser_snf/smf = 나프탈렌/멜라민계 · "
                                      "water_reducer = 일반 감수제 · lignosulfonate · vma_* = 증점제 · retarder / accelerator_* · superabsorbent_polymer · air_entraining_agent …")
        adm = {}
        if adm_sel:
            ac = st.columns(len(adm_sel))
            for i, c in enumerate(adm_sel):
                adm[c] = ac[i].number_input(c, 0.0, 20.0, 0.5 if "superplast" in c else 0.1, 0.05, key=f"{key}_ad_{c}")
        fib_sel = st.multiselect("섬유 (혼합물 부피 %)", classes_of("fibre"), key=f"{key}_fsel")
        fib = {}
        if fib_sel:
            fc = st.columns(len(fib_sel))
            for i, c in enumerate(fib_sel):
                fib[c] = fc[i].number_input(c, 0.0, 6.0, 0.5, 0.1, key=f"{key}_fb_{c}")
        act_sel = st.multiselect("활성화제 (결합재 대비 질량비, 용액 기준)", classes_of("activator"), key=f"{key}_actsel")
        act, mol = {}, {}
        if act_sel:
            acc = st.columns(len(act_sel))
            for i, c in enumerate(act_sel):
                act[c] = acc[i].number_input(c, 0.0, 2.0, 0.1, 0.01, key=f"{key}_act_{c}")
                if c in ("sodium_hydroxide", "potassium_hydroxide"):
                    mol[c] = acc[i].number_input(f"{c} 몰농도 (M)", 0.0, 20.0, 10.0, 0.5, key=f"{key}_mol_{c}")
        nano_sel = st.multiselect("나노재료 (결합재 대비 %)", classes_of("nano"), key=f"{key}_nsel")
        nano = {}
        if nano_sel:
            nc = st.columns(len(nano_sel))
            for i, c in enumerate(nano_sel):
                nano[c] = nc[i].number_input(c, 0.0, 10.0, 1.0, 0.1, key=f"{key}_nn_{c}")
    with st.expander("재료 물성 (선택 — 없으면 재료 클래스 중앙값으로 대치)"):
        props: dict[str, dict] = {}
        for c in sel:
            if V.is_cement_class(c) or c in ("ggbfs", "fly_ash_class_F", "fly_ash_class_C", "silica_fume", "metakaolin", "calcined_clay"):
                st.markdown(f"*{c}*")
                pc = st.columns(6)
                ox = {}
                for j, o in enumerate(["SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3"]):
                    v = pc[j].number_input(f"{o} %", 0.0, 100.0, 0.0, 0.1, key=f"{key}_ox_{c}_{o}")
                    if v > 0:
                        ox[o] = v
                pc2 = st.columns(3)
                blaine = pc2[0].number_input("Blaine (m²/kg)", 0.0, 3000.0, 0.0, 10.0, key=f"{key}_bl_{c}")
                sg = pc2[1].number_input("비중", 0.0, 8.0, 0.0, 0.01, key=f"{key}_sg_{c}")
                d50 = pc2[2].number_input("d50 (µm)", 0.0, 1000.0, 0.0, 0.5, key=f"{key}_d50_{c}")
                p = {}
                if ox:
                    p["oxides"] = ox
                if blaine > 0:
                    p["blaine_m2kg"] = blaine
                if sg > 0:
                    p["sg"] = sg
                if d50 > 0:
                    p["d50_um"] = d50
                if p:
                    props[c] = p
    st.markdown("**시험 조건**")
    k1, k2, k3, k4 = st.columns(4)
    age = k1.number_input("재령 (일)", 0.04, 1000.0, 28.0, 1.0, key=f"{key}_age")
    cg = k2.selectbox("압축시험 시험편", COMPARABILITY_GROUPS, index=0, key=f"{key}_cg",
                      help="comp_cube50: 50 mm 큐브 · comp_prism40: 40×40×160 프리즘(EN 196) · comp_cyl_*: 원주")
    cur = k3.selectbox("양생", list(CURING_PRESETS), key=f"{key}_cur")
    rest = k4.number_input("정적항복 휴지시간 (s)", 0.0, 7200.0, 0.0, 30.0, key=f"{key}_rest")
    is3 = st.checkbox("3D 프린팅용 배합 (is_3dcp)", key=f"{key}_3d")
    regime, temp, rh = CURING_PRESETS[cur]
    comps = [Component(material_class=c, amount=(f / tot if tot > 0 else f), props=props.get(c, {})) for c, f in fracs.items()]
    if system == "mortar" and sb > 0:
        comps.append(Component(material_class="natural_sand", amount=float(sb)))
    comps += [Component(material_class=c, amount=v / 100.0) for c, v in adm.items() if v > 0]
    comps += [Component(material_class=c, vol_pct=v) for c, v in fib.items() if v > 0]
    comps += [Component(material_class=c, amount=v, molarity=mol.get(c)) for c, v in act.items() if v > 0]
    comps += [Component(material_class=c, amount=v / 100.0) for c, v in nano.items() if v > 0]
    spec = MixSpec(system_type=system, components=comps, water_binder=float(wb),
                   conditions=Conditions(age_d=float(age), comparability_group=cg, rest_time_s=float(rest),
                                         curing_temp_C=temp, curing_rh_pct=rh, curing_regime=regime, is_3dcp=int(is3)),
                   name="ui_mix")
    try:
        spec.validate()
    except SpecError as e:
        st.error(str(e))
        return None
    return spec


# ------------------------------------------------------------------ page: predict
def page_predict():
    st.title("성능 예측 (배합 → 성능)")
    assets = get_assets()
    left, right = st.columns([1.15, 1])
    with left:
        spec = mix_form("p")
        targets = st.multiselect("예측 타깃", assets.available_targets(),
                                 default=[t for t in ["compressive_strength", "flexural_strength", "flow_table_spread",
                                                      "initial_setting_time", "plastic_viscosity", "porosity_total"] if t in assets.available_targets()],
                                 format_func=label, key="p_targets")
        go = st.button("예측 실행", type="primary", disabled=spec is None)
    with right:
        if spec is not None:
            with st.expander("MixSpec JSON", expanded=False):
                st.code(json.dumps({k: v for k, v in spec.to_dict().items()}, indent=1, ensure_ascii=False, default=str), language="json")
                st.download_button("JSON 다운로드", json.dumps(spec.to_dict(), indent=1, ensure_ascii=False, default=str),
                                   file_name="mix.json", mime="application/json")
        if go and spec is not None and targets:
            from pmpredict.predict import predict_specs
            with st.spinner("예측 중..."):
                out = predict_specs([spec], get_cfg(), targets)
            st.session_state["p_out"] = out
        out = st.session_state.get("p_out")
        if out is not None and len(out):
            show = out.copy()
            show["타깃"] = show["target"].map(label)
            show["예측 (q50)"] = show["q50"]
            show["80 % 구간"] = show.apply(lambda r: f"[{r.q10:.3g}, {r.q90:.3g}]", axis=1)
            show["단위"] = show["unit"]
            show["신뢰"] = show.apply(lambda r: ("⚠ weak" if assets.manifest["models"].get(r.model, {}).get("weak_model") else "") +
                                     (f" · 범위밖 {r.n_range_violations}" if r.n_range_violations else ""), axis=1)
            st.dataframe(show[["타깃", "예측 (q50)", "80 % 구간", "단위", "신뢰"]], hide_index=True, use_container_width=True,
                         column_config={"예측 (q50)": st.column_config.NumberColumn(format="%.3g")})
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from pmpredict.flowcurve import _korean_font
            kor_ok = _korean_font()
            n = len(out)
            fig, axes = plt.subplots(1, n, figsize=(2.6 * n, 3.0), dpi=110)
            axes = np.atleast_1d(axes)
            for ax, r in zip(axes, out.itertuples()):
                ax.errorbar([0], [r.q50], yerr=[[r.q50 - r.q10], [r.q90 - r.q50]], fmt="o", color="#2563eb", capsize=6, lw=2)
                ax.set_xticks([]); ax.set_title(KOR_TARGET.get(r.target, r.target) if kor_ok else r.target, fontsize=10)
                ax.set_ylabel(r.unit, fontsize=8); ax.grid(alpha=.3)
                if r.q90 / max(r.q10, 1e-9) > 30:
                    ax.set_yscale("log")
            fig.tight_layout()
            st.pyplot(fig, use_container_width=False)
            plt.close(fig)
            st.caption("점 = 중앙 예측, 막대 = 80 % 예측구간(논문 단위 교차검증으로 보정). 구간이 매우 넓은 타깃(레올로지)은 자릿수 참고용.")


# ------------------------------------------------------------------ page: flow curve
def page_flowcurve():
    st.title("유동 곡선 예측 (전단속도 → 전단응력)")
    st.caption("Bingham 모델 τ(γ̇) = τ₀ + μ·γ̇ — τ₀는 동적항복응력 모델, μ는 소성점도 모델의 예측분포에서 샘플링하여 80 % 밴드를 만듭니다. "
               "검증(실측 곡선 137 믹스/23편, 논문 단위 OOF): 점단위 오차 중앙값 ×2.1, 밴드 커버리지 86 % → 자릿수·경향 참고용.")
    from pmpredict.flowcurve import analogue_curves, plot_flow_curve, predict_flow_curves
    left, right = st.columns([1.1, 1])
    with left:
        spec = mix_form("f")
        c1, c2, c3 = st.columns(3)
        gmax = c1.number_input("최대 전단속도 (1/s)", 10.0, 500.0, 150.0, 10.0)
        k = c2.number_input("겹칠 문헌 곡선 수", 0, 6, 3)
        logy = c3.checkbox("y 로그축")
        go = st.button("곡선 예측", type="primary", disabled=spec is None)
    with right:
        if go and spec is not None:
            rates = np.concatenate([[0.0], np.geomspace(0.5, gmax, 40)])
            with st.spinner("예측 중..."):
                P, band = predict_flow_curves([spec], get_cfg(), rates, get_assets())
                an = analogue_curves(spec, get_cfg(), k=int(k), assets=get_assets()) if k > 0 else None
            st.session_state["f_res"] = (P, band, an)
        if "f_res" in st.session_state:
            P, band, an = st.session_state["f_res"]
            r = P.iloc[0]
            m1, m2 = st.columns(2)
            m1.metric("동적항복응력 τ₀", f"{r.tau0_q50:.0f} Pa", f"[{r.tau0_q10:.0f}, {r.tau0_q90:.0f}]" + (" ⚠weak" if r.tau0_weak else ""), delta_color="off")
            m2.metric("소성점도 μ", f"{r.mu_q50:.2f} Pa·s", f"[{r.mu_q10:.2f}, {r.mu_q90:.2f}]" + (" ⚠weak" if r.mu_weak else ""), delta_color="off")
            fig = plot_flow_curve(band, an, log_y=logy)
            st.pyplot(fig, use_container_width=True)
            if an is not None and len(an):
                st.caption("점선 = 조성이 가장 가까운 문헌 배합의 실측 곡선 (d = 표준화 조성거리; 작을수록 유사). 겉보기점도 곡선은 응력으로 환산.")
                docs = an.drop_duplicates("mix_uid")[["mix_uid", "distance"]]
                st.dataframe(pd.DataFrame(dict(DOI=[f"https://doi.org/{u.split('::')[0]}" for u in docs.mix_uid], 믹스=[u.split("::")[-1] for u in docs.mix_uid],
                                               조성거리=docs.distance.round(2).values)), hide_index=True, column_config={"DOI": st.column_config.LinkColumn()})
            st.download_button("곡선 CSV 다운로드", band.to_csv(index=False).encode("utf-8-sig"), "flow_curve.csv", "text/csv")


# ------------------------------------------------------------------ page: structuration curve
def page_thixo():
    st.title("구조화 곡선 예측 (정적항복응력 – 휴지시간)")
    st.caption("τ_s(t) = τ_s(0) + Athix·t (Roussel 선형 모델). τ_s(0)는 정적항복응력 모델(휴지 0 s), Athix는 구조화속도 모델(디지타이즈 곡선 피팅값으로 보강)에서 "
               "각각 예측분포를 샘플링해 80 % 밴드를 만듭니다. 실측 곡선(91 믹스/18편)은 0–80 분에서 선형 근사 R² 중앙 0.92, 휴지 중 중앙 ×7 증가. "
               "점선은 정적항복 모델의 휴지시간 스윕(참고용 — 기울기가 실제의 1/12로 과소).")
    from pmpredict.thixocurve import analogue_static_curves, plot_static_curve, predict_static_curve
    left, right = st.columns([1.1, 1])
    with left:
        spec = mix_form("t")
        c1, c2, c3, c4 = st.columns(4)
        tmax = c1.number_input("최대 휴지시간 (min)", 5.0, 240.0, 60.0, 5.0)
        k = c2.number_input("겹칠 문헌 곡선 수", 0, 6, 3)
        logy = c3.checkbox("y 로그축", value=True)
        phys = c4.checkbox("참고 경로(모델 스윕) 표시", value=False)
        go = st.button("곡선 예측", type="primary", disabled=spec is None, key="t_go")
    with right:
        if go and spec is not None:
            rest = np.concatenate([[0.0], np.geomspace(30.0, tmax * 60.0, 30)])
            with st.spinner("예측 중..."):
                curve, info = predict_static_curve(spec, get_cfg(), rest, get_assets())
                an = analogue_static_curves(spec, get_cfg(), k=int(k), assets=get_assets()) if k > 0 else None
            st.session_state["t_res"] = (curve, info, an)
        if "t_res" in st.session_state:
            curve, info, an = st.session_state["t_res"]
            t0 = info["tau0_model"]
            P = curve[curve.route == "physical"] if (curve.route == "physical").any() else curve[curve.route == "model"]
            m1, m2, m3 = st.columns(3)
            m1.metric("τ_s(0)", f"{t0[1]:.0f} Pa", f"[{t0[0]:.0f}, {t0[2]:.0f}]" + (" ⚠weak" if info["static_weak"] else ""), delta_color="off")
            m2.metric(f"τ_s({P.rest_s.iloc[-1] / 60:.0f} min)", f"{P.q50.iloc[-1]:.0f} Pa", f"[{P.q10.iloc[-1]:.0f}, {P.q90.iloc[-1]:.0f}]", delta_color="off")
            if info.get("athix_model"):
                am = info["athix_model"]
                m3.metric("Athix (구조화속도)", f"{am[1]:.3f} Pa/s", f"[{am[0]:.3f}, {am[2]:.3f}]" + (" ⚠weak" if info.get("athix_weak") else ""), delta_color="off")
            fig = plot_static_curve(curve, an, log_y=logy, show_physical=phys)
            st.pyplot(fig, use_container_width=True)
            if an is not None and len(an):
                docs = an.drop_duplicates("mix_uid")[["mix_uid", "distance"]]
                st.dataframe(pd.DataFrame(dict(DOI=[f"https://doi.org/{u.split('::')[0]}" for u in docs.mix_uid], 믹스=[u.split("::")[-1] for u in docs.mix_uid],
                                               조성거리=docs.distance.round(2).values)), hide_index=True, column_config={"DOI": st.column_config.LinkColumn()})
            st.download_button("곡선 CSV 다운로드", curve.to_csv(index=False).encode("utf-8-sig"), "structuration_curve.csv", "text/csv", key="t_dl")


# ------------------------------------------------------------------ target editor
def target_editor(key: str, assets, allow_missing_models: bool) -> list[dict]:
    st.markdown("**목표 성능**")
    default = pd.DataFrame([
        dict(quantity="compressive_strength", kind="ge", lo=40.0, hi=None, unit="MPa", age_d=28.0, comparability_group="comp_cube50",
             shear_rate_1s=None, rest_time_s=None, p_min=0.7),
        dict(quantity="flow_table_spread", kind="range", lo=140.0, hi=200.0, unit="mm", age_d=None, comparability_group=None,
             shear_rate_1s=None, rest_time_s=None, p_min=0.35),
        dict(quantity="shear_stress_at_rate", kind="range", lo=200.0, hi=800.0, unit="Pa", age_d=None, comparability_group=None,
             shear_rate_1s=50.0, rest_time_s=None, p_min=0.3),
    ])
    derived = ["shear_stress_at_rate", "static_yield_stress_at_rest"]
    qs = (sorted(KOR_TARGET) if allow_missing_models else assets.available_targets()) + derived
    ed = st.data_editor(default, num_rows="dynamic", key=f"{key}_targets", use_container_width=True,
                        column_config={
                            "quantity": st.column_config.SelectboxColumn("타깃", options=qs, required=True,
                                                                         help="shear_stress_at_rate = 유동곡선 점(전단속도 지정) · static_yield_stress_at_rest = 구조화곡선 점(휴지시간 지정)"),
                            "kind": st.column_config.SelectboxColumn("종류", options=["ge", "le", "range", "goal"], required=True),
                            "lo": st.column_config.NumberColumn("하한 / 목표"), "hi": st.column_config.NumberColumn("상한"),
                            "unit": st.column_config.TextColumn("단위", help="MPa, kPa, Pa, mm, min, h, %, Pa.s ..."),
                            "age_d": st.column_config.NumberColumn("재령 (일)"),
                            "comparability_group": st.column_config.SelectboxColumn("시험편", options=[None] + COMPARABILITY_GROUPS),
                            "shear_rate_1s": st.column_config.NumberColumn("전단속도 (1/s)", help="shear_stress_at_rate 전용"),
                            "rest_time_s": st.column_config.NumberColumn("휴지시간 (s)", help="static_yield_stress / static_yield_stress_at_rest"),
                            "p_min": st.column_config.NumberColumn("최소 확률", min_value=0.05, max_value=1.0, step=0.05),
                        })
    targets = []
    for r in ed.itertuples(index=False):
        if not isinstance(r.quantity, str):
            continue
        cond = {}
        if pd.notna(r.age_d):
            cond["age_d"] = float(r.age_d)
        if isinstance(r.comparability_group, str):
            cond["comparability_group"] = r.comparability_group
        if pd.notna(r.shear_rate_1s):
            cond["shear_rate_1s"] = float(r.shear_rate_1s)
        if pd.notna(r.rest_time_s):
            cond["rest_time_s"] = float(r.rest_time_s)
        t = dict(quantity=r.quantity, kind=r.kind, unit=(r.unit if isinstance(r.unit, str) and r.unit else None), conditions=cond,
                 p_min=float(r.p_min) if pd.notna(r.p_min) else None)
        if r.kind == "goal":
            t["goal"] = float(r.lo) if pd.notna(r.lo) else None
        else:
            t["lo"] = float(r.lo) if pd.notna(r.lo) else None
            t["hi"] = float(r.hi) if pd.notna(r.hi) else None
        targets.append(t)
    return targets


def space_editor(key: str) -> dict:
    st.markdown("**탐색 공간**")
    c1, c2, c3, c4 = st.columns(4)
    system = c1.selectbox("시스템", ["mortar", "paste"], key=f"{key}_sys")
    wb = c2.slider("w/b 범위", 0.1, 1.0, (0.3, 0.5), 0.01, key=f"{key}_wb")
    sb = c3.slider("s/b 범위", 0.0, 6.0, (1.0, 3.0), 0.1, key=f"{key}_sb", disabled=(system == "paste"))
    maxc = c4.number_input("결합재 최대 성분 수", 1, 6, 3, key=f"{key}_maxc")
    is3 = st.checkbox("3D 프린팅 맥락 (is_3dcp)", key=f"{key}_3d")
    powder_classes = classes_of("powder")
    bsel = st.multiselect("허용 결합재 재료", powder_classes,
                          default=["portland_cement", "fly_ash_class_F", "ggbfs", "silica_fume", "limestone_powder"], key=f"{key}_bsel")
    binder = {}
    if bsel:
        bc = st.columns(len(bsel))
        for i, c in enumerate(bsel):
            with bc[i]:
                st.caption(c)
                req = st.checkbox("필수", value=(c == "portland_cement"), key=f"{key}_req_{c}")
                lo, hi = st.slider("분율", 0.0, 1.0, (0.4, 1.0) if c == "portland_cement" else (0.0, 0.4), 0.05, key=f"{key}_bb_{c}")
                binder[c] = dict(lo=lo, hi=hi, required=req)
    asel = st.multiselect("혼화제 (결합재 대비 %)", classes_of("admixture"), default=["superplasticiser_pce"], key=f"{key}_asel")
    adm = {}
    if asel:
        ac = st.columns(len(asel))
        for i, c in enumerate(asel):
            lo, hi = ac[i].slider(c, 0.0, 5.0, (0.0, 1.5), 0.05, key=f"{key}_ab_{c}")
            adm[c] = dict(lo=lo, hi=hi)
    cur = st.selectbox("양생 (고정)", list(CURING_PRESETS), index=1, key=f"{key}_cur")
    regime, temp, rh = CURING_PRESETS[cur]
    return dict(system_type=system, is_3dcp=is3, w_b=list(wb), s_b=(list(sb) if system == "mortar" else None), binder=binder,
                max_binder_components=int(maxc), admixtures=adm,
                fixed_conditions=dict(curing_temp_C=temp, curing_rh_pct=rh, curing_regime=regime))


# ------------------------------------------------------------------ page: design
def page_design():
    st.title("역설계 (목표 성능 → 배합 후보 + 문헌 배합)")
    assets = get_assets()
    from pmpredict.design.spec import DesignSpec, SpecValidationError
    targets = target_editor("d", assets, allow_missing_models=False)
    space = space_editor("d")
    c1, c2, c3, c4 = st.columns(4)
    objs = c1.multiselect("목적함수 (최소화)", ["clinker_fraction", "co2", "cost", "co2_per_mpa", "cost_per_mpa"], default=["clinker_fraction", "co2"])
    n_samples = c2.select_slider("후보 샘플 수", [2048, 4096, 8192, 16384, 32768], value=8192)
    n_refine = c3.number_input("정제 후보 수", 2, 12, 6)
    top_n = c4.number_input("표시 후보 수", 3, 20, 8)
    name = st.text_input("설계 이름", "ui_design")
    if st.button("역설계 실행", type="primary", disabled=not targets):
        d = dict(name=name, targets=targets, space=space, objectives=[dict(name=o, direction="min") for o in objs],
                 risk=dict(p_min=0.7, ad_max=1.0), budget=dict(n_samples=n_samples, n_refine=int(n_refine), refine_generations=15, time_limit_s=150),
                 output=dict(top_n=int(top_n), n_literature=15, plots=True), seed=0)
        try:
            spec = DesignSpec.from_dict(d)
            ages = {}
            for k, m in assets.manifest["models"].items():
                if m["variant"] == "general":
                    mp = get_cfg().artifacts_dir / m["path"] / "meta.json"
                    if mp.exists():
                        ages[m["target"]] = json.loads(mp.read_text(encoding="utf-8")).get("age_support") or {}
            warns = spec.validate(available_targets=set(assets.available_targets()), age_support=ages)
        except SpecValidationError as e:
            st.error(str(e)); return
        from pmpredict.design.optimize import Evaluator, run_twostage
        from pmpredict.design.report import build_result, write_outputs
        t0 = time.time()
        prog = st.progress(0, "평가기 준비...")
        ev = Evaluator(spec, get_cfg())
        prog.progress(15, "Sobol 스윕 + 스크리닝 + 정제 실행 중 (최대 2분)...")
        run = run_twostage(spec, get_cfg(), evaluator=ev)
        prog.progress(80, "문헌 검색 · 리포트 작성...")
        res = build_result(run, ev, get_store(), get_cfg(), warns)
        out_dir = Path(tempfile.mkdtemp(prefix="pmdesign_"))
        paths = write_outputs(res, out_dir, plots=True)
        prog.progress(100, f"완료 ({time.time() - t0:.0f}s)")
        st.session_state["d_res"] = (res, paths, run.diagnostics)
    if "d_res" in st.session_state:
        res, paths, diag = st.session_state["d_res"]
        for w in res.warnings:
            st.warning(w)
        st.caption(f"샘플 {diag.get('n_sampled')} → 요청 임계값 실현가능 {diag.get('n_feasible')}"
                   + (f" · 완화 후 임계값 {diag.get('p_min_used')}" if diag.get("relaxation") else "") + f" · {diag.get('t_total_s')}s")
        if any(m["weak"] for m in res.models.values()):
            st.warning("일부 타깃 모델이 weak(구간 매우 넓음)입니다. 그 타깃은 아래 문헌 배합을 1차 근거로 보세요.")
        rows = []
        for c in res.candidates:
            r = dict(순위=c.rank, 배합=c.summary, P_min=c.p_min_targets, AD=c.ad_max)
            for q, p in c.predictions.items():
                r[KOR_TARGET.get(q, q)] = f"{p.q50:.3g} [{p.q10:.3g}, {p.q90:.3g}] p={p.p_satisfied:.2f}" + (" ⚠" if p.weak_model else "")
            for o in res.spec["objectives"]:
                from pmpredict.design.objectives import OBJECTIVE_COLUMN
                col = OBJECTIVE_COLUMN.get(o["name"], o["name"])
                r[o["name"]] = round(c.objectives.get(col, float("nan")), 3)
            r["analogue DOI"] = c.analogues[0]["doi"] if c.analogues else ""
            rows.append(r)
        st.subheader("후보 배합")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        p1, p2 = st.columns(2)
        if "pareto" in paths:
            p1.image(str(paths["pareto"]))
        if "parallel" in paths:
            p2.image(str(paths["parallel"]))
        with st.expander("후보 상세 (JSON, 유사 문헌 배합)"):
            for c in res.candidates:
                st.markdown(f"**#{c.rank}** {c.summary}")
                for an in c.analogues[:2]:
                    meas = "; ".join(f"{m['quantity']}={m['value']:.3g} {m['unit']}" for m in an["measured"][:3])
                    st.markdown(f"- 유사 문헌: [{an['doi']}](https://doi.org/{an['doi']}) '{an['mix_name']}' (조성거리 {an['feature_distance']:.2f}) — {an['composition_summary']} → {meas}")
                st.code(json.dumps({k: v for k, v in c.mix.items() if k in ("system_type", "components", "water_binder", "sand_binder", "conditions")},
                                   indent=1, ensure_ascii=False, default=str), language="json")
        st.subheader("목표 근처의 실제 문헌 배합")
        lit = pd.DataFrame([dict(tier=h["tier"], score=round(h["score"], 2), DOI=f"https://doi.org/{h['doi']}", 믹스=h["mix_name"], 연도=h["year"],
                                 **{"3DCP": h["is_3dcp"]}, 조성=h["composition_summary"],
                                 측정값="; ".join(f"{m['quantity']}={m['value']:.3g}{m['unit']}" + (f"@{m['age_d']:g}d" if m["age_d"] else "") for m in h["measured"][:4]))
                            for h in res.literature])
        st.dataframe(lit, hide_index=True, use_container_width=True, column_config={"DOI": st.column_config.LinkColumn()})
        st.download_button("report.md 다운로드", Path(paths["report"]).read_text(encoding="utf-8"), file_name="report.md")
        st.download_button("result.json 다운로드", Path(paths["result"]).read_text(encoding="utf-8"), file_name="result.json", mime="application/json")


# ------------------------------------------------------------------ page: retrieve
def page_retrieve():
    st.title("문헌 배합 검색 (모델 없이)")
    assets = get_assets()
    from pmpredict.design.retrieve import retrieve
    from pmpredict.design.spec import DesignSpec, SpecValidationError
    targets = target_editor("r", assets, allow_missing_models=True)
    c1, c2, c3 = st.columns(3)
    system = c1.selectbox("시스템", ["mortar", "paste"], key="r_sys")
    only3 = c2.checkbox("3DCP 논문 가중", key="r_3d")
    n = c3.number_input("결과 수", 5, 100, 20, key="r_n")
    if st.button("검색", type="primary", disabled=not targets):
        d = dict(name="retrieve", targets=[dict(t, retrieval_only=True) for t in targets],
                 space=dict(system_type=system, is_3dcp=only3, w_b=[0.1, 1.0], s_b=([0.0, 6.0] if system == "mortar" else None),
                            binder={"portland_cement": dict(lo=0.0, hi=1.0, required=True)}),
                 output=dict(n_literature=int(n)))
        try:
            spec = DesignSpec.from_dict(d)
            spec.validate()
        except SpecValidationError as e:
            st.error(str(e)); return
        hits = retrieve(spec, get_store(), n=int(n))
        st.session_state["r_hits"] = hits
    hits = st.session_state.get("r_hits")
    if hits is not None:
        st.caption(f"{len(hits)}건 — exact: 모든 목표를 측정값으로 충족 · near: 목표 공간에서 가까움 (논문당 최대 3건)")
        df = pd.DataFrame([dict(tier=h.tier, score=round(h.score, 2), DOI=f"https://doi.org/{h.doi}", 제목=h.title[:90], 믹스=h.mix_name, 연도=h.year,
                                **{"3DCP": h.is_3dcp}, 조성=h.composition_summary,
                                측정값="; ".join(f"{m.quantity}={m.value:.3g}{m.unit}" + (f"@{m.age_d:g}d" if m.age_d else "") for m in h.measured[:4]))
                           for h in hits])
        st.dataframe(df, hide_index=True, use_container_width=True, column_config={"DOI": st.column_config.LinkColumn()})
        st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"), file_name="literature.csv", mime="text/csv")


# ------------------------------------------------------------------ page: buildability
def job_form(key: str):
    from pmpredict import buildability as B
    st.markdown("**프린트 작업 (노즐 · 구조물 · 스케줄)**")
    c1, c2, c3, c4 = st.columns(4)
    obj = c1.selectbox("구조물", ["wall", "hollow_cylinder", "column", "other"],
                       format_func=lambda o: {"wall": "직선 벽", "hollow_cylinder": "중공 원통", "column": "기둥(속 찬)", "other": "기타"}[o], key=f"{key}_obj")
    H = c2.number_input("목표 높이 (mm)", 20.0, 5000.0, 500.0, 10.0, key=f"{key}_H")
    fp = c3.number_input("벽 길이 / 원통 직경 (mm)", 10.0, 20000.0, 1000.0, 10.0, key=f"{key}_fp", disabled=obj in ("column", "other"))
    nf = c4.number_input("벽 두께 방향 필라멘트 수", 1, 6, 2 if obj == "wall" else 1, key=f"{key}_nf")
    c1, c2, c3, c4 = st.columns(4)
    shape = c1.selectbox("노즐", ["원형", "직사각형"], key=f"{key}_shape")
    if shape == "원형":
        nd = c2.number_input("노즐 직경 (mm)", 0.5, 150.0, 25.0, 0.5, key=f"{key}_nd"); nw = nh = None
    else:
        nd = None
        nw = c2.number_input("노즐 폭 (mm)", 0.5, 200.0, 40.0, 0.5, key=f"{key}_nw"); nh = c3.number_input("노즐 높이 (mm)", 0.5, 150.0, 10.0, 0.5, key=f"{key}_nh")
    auto = c4.checkbox("층 높이·폭 자동 (0.5·d, 1.2·d)", value=True, key=f"{key}_auto")
    c1, c2, c3, c4 = st.columns(4)
    lh = None if auto else c1.number_input("층 높이 (mm)", 0.05, 150.0, 10.0, 0.5, key=f"{key}_lh")
    lw = None if auto else c2.number_input("층 폭 (mm)", 0.3, 400.0, 30.0, 0.5, key=f"{key}_lw")
    v = c3.number_input("프린트 속도 (mm/s)", 0.1, 1000.0, 50.0, 1.0, key=f"{key}_v")
    mode = c4.radio("층 사이클 시간", ["경로/속도로 계산", "직접 입력"], key=f"{key}_tm", horizontal=True)
    tc = None
    if mode == "직접 입력" or obj in ("column", "other"):
        tc = st.number_input("층 사이클 시간 (s)", 0.5, 7200.0, 30.0, 1.0, key=f"{key}_tc")
    c1, c2, c3, c4 = st.columns(4)
    t0 = c1.number_input("믹싱 후 시작 시각 (min)", 0.0, 600.0, 10.0, 1.0, key=f"{key}_t0")
    ot = c2.number_input("오픈 타임 (min, 0 = 미지정)", 0.0, 600.0, 60.0, 5.0, key=f"{key}_ot")
    sf = c3.number_input("하중 안전율", 1.0, 3.0, 1.5, 0.1, key=f"{key}_sf")
    cb = c4.checkbox("자유 벽 좌굴 검토 (Suiker)", value=(obj == "wall"), key=f"{key}_cb", disabled=obj != "wall")
    return B.PrintJob(name="ui_job", object_type=obj, target_height_mm=float(H), footprint_mm=(float(fp) if obj in ("wall", "hollow_cylinder") else None),
                      wall_filaments=int(nf), nozzle_d_mm=nd, nozzle_w_mm=nw, nozzle_h_mm=nh, layer_height_mm=lh, layer_width_mm=lw,
                      print_speed_mm_s=float(v), layer_cycle_time_s=tc, start_time_after_mixing_min=float(t0), open_time_min=(float(ot) if ot > 0 else None),
                      safety_factor=float(sf), check_buckling=bool(cb))


def _inf(x, d=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if isinstance(x, float) and np.isinf(x):
        return "∞"
    return f"{x:.{d}f}"


def page_buildability():
    from pmpredict import buildability as B
    st.title("빌더빌리티 · 프린팅 스케줄 (노즐 + 구조물 → 배합 요구 · 층 사이클 시간)")
    st.caption("Roussel 소성붕괴 기준 ρgH ≤ √3·τ_s(t), τ_s(t)=τ_s(0)+Athix·t, Suiker 자유 벽 좌굴, 오픈 타임. 경험 보정: print01 라벨(1,014편 · 7,420 프린트 런)에서 "
               "스택 파괴 시 비율 R=ρgH/(√3 τ_s)의 분포(146 붕괴, 중앙 1.39)와 노즐 등급별 출력 가능 유변 범위. τ_s 단독의 판별력은 AUC 0.59로 약하므로 물리 경로가 1차 판정입니다.")
    cal = B.load_calibration(get_cfg())
    job = job_form("b")
    st.markdown("**신선 재료**")
    src = st.radio("재료 입력", ["배합에서 예측 (pmpredict)", "측정값 직접 입력"], horizontal=True, key="b_src")
    mat = None
    if src == "측정값 직접 입력":
        c1, c2, c3, c4 = st.columns(4)
        tau = c1.number_input("정적항복응력 τ_s(0) (Pa)", 1.0, 100000.0, 2000.0, 50.0, key="b_tau")
        ath_on = c2.checkbox("Athix 지정", value=True, key="b_ath_on")
        ath = c2.number_input("Athix (Pa/s)", 0.0, 100.0, 1.0, 0.05, key="b_ath", disabled=not ath_on)
        rho = c3.number_input("신선 밀도 (kg/m³)", 1000.0, 3000.0, 2100.0, 10.0, key="b_rho")
        et = c4.number_input("E/τ_s (그린 탄성계수 비)", 5.0, 200.0, 25.0, 1.0, key="b_et")
        mat = B.FreshMaterial(tau_s0_Pa=float(tau), athix_Pa_s=(float(ath) if ath_on else None), rho_kg_m3=float(rho), E_over_tau=float(et), source="measured")
        go = st.button("평가", type="primary", key="b_go")
    else:
        spec = mix_form("bm")
        c1, c2 = st.columns(2)
        rho = c1.number_input("신선 밀도 (kg/m³)", 1000.0, 3000.0, 2100.0, 10.0, key="b_rho2")
        et = c2.number_input("E/τ_s (그린 탄성계수 비)", 5.0, 200.0, 25.0, 1.0, key="b_et2")
        go = st.button("평가", type="primary", key="b_go2", disabled=spec is None)
        if go and spec is not None:
            with st.spinner("신선 상태 예측..."):
                mat = B.material_from_mix(spec, get_cfg(), get_assets())
                mat.rho_kg_m3 = float(rho); mat.E_over_tau = float(et)
    if go and mat is not None:
        try:
            v = B.assess(job, mat, cal); sc = B.schedule(job, mat, cal); an = B.similar_prints(job, mat, get_cfg(), k=8, cal=cal)
        except ValueError as e:
            st.error(str(e)); return
        st.session_state["b_res"] = (job, mat, v, sc, an)
    if "b_res" in st.session_state:
        job, mat, v, sc, an = st.session_state["b_res"]
        color = {"printable": "green", "borderline": "orange", "non_printable": "red"}[v.label]
        st.markdown(f"### 판정: :{color}[{v.label}]  (지배 모드: {v.governing})")
        for r in v.reasons:
            st.markdown(f"- {r}")
        m = st.columns(6)
        m[0].metric("층 수 / 층 높이", f"{v.n_target} / {v.layer_height_mm:g} mm")
        m[1].metric("층 사이클 (현재)", f"{v.layer_cycle_time_s:.0f} s", f"프린트 {v.print_time_min:.0f} min", delta_color="off")
        m[2].metric("소성붕괴 n_max (sf1 / sf)", f"{_inf(v.n_max_plastic)} / {_inf(v.n_max_plastic_sf)}")
        m[3].metric("좌굴 n_max (자유 벽)", _inf(v.n_max_buckling) if v.n_max_buckling is not None else "n/a")
        m[4].metric("경험적 붕괴 확률", f"{v.p_collapse_empirical:.0%}" if v.p_collapse_empirical is not None else "—", f"R = {v.R_static:.2f}", delta_color="off")
        m[5].metric("재료 밴드 내 안정 확률", f"{v.p_stable_physics:.0%}" if v.p_stable_physics is not None else "—")
        st.markdown(f"**재료**: τ_s(0) {v.tau_s0_Pa:.0f} Pa" + (f" [{mat.tau_s0_band[0]:.0f}, {mat.tau_s0_band[1]:.0f}]" if mat.tau_s0_band else "")
                    + f", Athix {v.athix_Pa_s:.3f} Pa/s" + (f" [{mat.athix_band[0]:.3f}, {mat.athix_band[1]:.3f}]" if mat.athix_band else "")
                    + f" ({mat.source}) → 프린트 종료 시 τ_s {v.tau_s_end_Pa:.0f} Pa. 이 스케줄에 필요한 τ_s(0) ≥ {v.tau0_required_Pa:.0f} Pa (Athix 고정) "
                    + f"또는 Athix ≥ {v.athix_required_Pa_s:.3f} Pa/s (τ_s(0) 고정).")
        st.subheader("스케줄 창")
        s1, s2 = st.columns([1, 1.2])
        with s1:
            rows = [("층 사이클 시간 최소 (안정, sf)", f"{_inf(sc['t_c_min_s'])} s"), ("최소 (sf 없이)", f"{_inf(sc['t_c_min_no_sf_s'])} s"),
                    ("최대", f"{_inf(sc['t_c_max_s'])} s — {sc['t_c_max_basis']}"),
                    ("권장", f"{_inf(sc['t_c_recommended_s'])} s → 총 {_inf(sc['print_time_recommended_min'])} min"),
                    ("무한 적층 임계 사이클 시간", f"{_inf(sc['critical_cycle_time_s'])} s")]
            if sc.get("speed"):
                sp_ = sc["speed"]
                rows.append(("경로 기준 속도 창", (f"{_inf(sp_['v_min_mm_s'], 1)} – {_inf(sp_['v_max_mm_s'], 1)} mm/s (권장 {_inf(sp_['v_recommended_mm_s'], 1)})" if sc["feasible"]
                                              else f"없음: 안정에는 ≤ {_inf(sp_['v_max_mm_s'], 1)} mm/s, 시간 한도에는 ≥ {_inf(sp_['v_min_mm_s'], 1)} mm/s")))
            st.table(pd.DataFrame(rows, columns=["항목", "값"]))
            if not sc["feasible"]:
                st.error("실현 가능한 사이클 시간 창이 없습니다: τ_s(0)·Athix를 높이거나(촉진제·VMA·낮은 w/b), 층 높이를 낮추거나, 오픈 타임을 늘리세요. "
                         "아래 '배합 역설계'가 필요한 유변 물성을 만족하는 배합을 찾습니다.")
            for e, w in v.extrudability.items():
                st.caption(f"{KOR_TARGET.get(e, e)} {w['value']:.3g}: 출력 가능 런의 {w['status']} ({w['scope']}, p10 {w['p10']:.3g} · p50 {w['p50']:.3g} · p90 {w['p90']:.3g})")
        with s2:
            import matplotlib.pyplot as plt
            from pmpredict.flowcurve import _korean_font
            _korean_font()
            sw = sc["sweep"]
            fig, ax = plt.subplots(figsize=(6, 3.6))
            ax.plot(sw.layer_cycle_time_s, sw.n_max.clip(upper=v.n_target * 3), label="n_max (sf 1)")
            ax.plot(sw.layer_cycle_time_s, sw.n_max_sf.clip(upper=v.n_target * 3), label=f"n_max (sf {job.safety_factor:g})", ls="--")
            ax.axhline(v.n_target, color="k", lw=0.8, label=f"목표 {v.n_target} 층")
            ax.axvline(v.layer_cycle_time_s, color="gray", lw=0.8, ls=":", label="현재 사이클")
            if np.isfinite(sc["t_c_max_s"]):
                lo = sc["t_c_min_s"] if np.isfinite(sc["t_c_min_s"]) else sw.layer_cycle_time_s.min()
                ax.axvspan(max(lo, 1e-3), max(sc["t_c_max_s"], lo + 1e-3), color="green" if sc["feasible"] else "red", alpha=0.08)
            ax.set_xscale("log"); ax.set_xlabel("층 사이클 시간 (s)"); ax.set_ylabel("적층 가능 층 수"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
            st.pyplot(fig, use_container_width=True)
        if len(an):
            st.subheader("가장 비슷한 문헌 프린트")
            st.dataframe(pd.DataFrame(dict(DOI=[f"https://doi.org/{p}" for p in an.paper_uid], 믹스=an.mix_name_in_paper, 구조물=an.object, 노즐=an.noz_eq_mm.round(1),
                                           층높이=an.layer_height_mm, 층수=an.n_layers_achieved, 높이=an.H_mm, 사이클=an.layer_cycle_time_s,
                                           결과=an.outcome + np.where(an.stack_to_failure == 1, " (stack-to-failure)", ""), 라벨=an.printability_label,
                                           τ_s=an.static_yield_stress, R=an.R.round(2))), hide_index=True, use_container_width=True, column_config={"DOI": st.column_config.LinkColumn()})
        md = B.render_markdown(job, mat, v, sc, an)
        st.download_button("assessment.md 다운로드", md, file_name="buildability_assessment.md", key="b_dl")
    # ---- inverse design for the job
    st.markdown("---")
    st.subheader("배합 역설계: 이 작업이 요구하는 유변 물성을 만족하는 배합 찾기")
    st.caption("Roussel 기준을 프린트 종료 시각의 정적항복응력 목표(static_yield_stress_at_rest ≥ sf·ρgH/√3 @ rest = 프린트 시간)로 바꾸고, τ_s(0)는 노즐 등급의 출력 가능 범위, "
               "소성점도는 p90 이하로 제한합니다. 후보마다 예측 신선 상태로 다시 판정·스케줄을 계산합니다. 유변 모델의 구간이 넓어 P가 낮게 나오는 것이 정상이며, 후보 옆의 문헌 배합을 함께 보세요.")
    with st.expander("탐색 공간 · 추가 목표", expanded=False):
        space = space_editor("bd")
        fc = st.checkbox("28 d 압축강도 목표 추가", value=True, key="bd_fc")
        fc_lo = st.number_input("압축강도 ≥ (MPa)", 5.0, 150.0, 30.0, 5.0, key="bd_fc_lo", disabled=not fc)
        n_samples = st.select_slider("후보 샘플 수", [2048, 4096, 8192, 16384], value=4096, key="bd_ns")
    if st.button("배합 역설계 실행", key="bd_go"):
        extra = [dict(quantity="compressive_strength", kind="ge", lo=float(fc_lo), unit="MPa", conditions=dict(age_d=28, comparability_group="comp_cube50"), p_min=0.6)] if fc else []
        with st.spinner("Sobol 스윕 + 정제 + 후보별 판정 (1–2분)..."):
            try:
                out_dir = Path(tempfile.mkdtemp(prefix="pmbuild_"))
                res, table, d, info, paths = B.design_for_job(job, space, get_cfg(), out_dir=out_dir, extra_targets=extra, cal=cal,
                                                              budget=dict(n_samples=int(n_samples), n_refine=5, refine_generations=12, time_limit_s=150))
            except Exception as e:  # noqa: BLE001
                st.error(str(e)); return
        st.session_state["bd_res"] = (res, table, d, info, paths)
    if "bd_res" in st.session_state:
        res, table, d, info, paths = st.session_state["bd_res"]
        w = info.get("tau_s0_window") or {}
        st.caption(f"요구: {info['n_layers']} 층 × {info['layer_cycle_time_s']:.0f} s → 프린트 종료 시 τ_s ≥ {info['tau_s_required_end_Pa']:.0f} Pa; "
                   f"τ_s(0) 창 {w.get('p10', '—')}–{w.get('p90', '—')} Pa ({w.get('scope', '')}). "
                   f"설계 실현가능 {res.diagnostics.get('n_feasible')} / {res.diagnostics.get('n_sampled')}"
                   + (f" · 완화 후 임계값 {res.diagnostics.get('p_min_used')}" if res.diagnostics.get("relaxation") else ""))
        if len(table):
            show = table.drop(columns=["mix_json"]).rename(columns=dict(rank="순위", mix="배합", verdict="판정", governing="지배 모드", n_target="목표 층",
                                                                       p_stable="P(안정)", p_collapse_emp="P(붕괴, 경험)", t_c_min_s="사이클 최소 s", t_c_max_s="사이클 최대 s",
                                                                       t_c_recommended_s="권장 사이클 s", v_recommended_mm_s="권장 속도 mm/s", reasons="근거"))
            st.dataframe(show, hide_index=True, use_container_width=True)
            for c in res.candidates[:3]:
                an_ = c.analogues[:1]
                if an_:
                    st.markdown(f"- #{c.rank} 유사 문헌 배합: [{an_[0]['doi']}](https://doi.org/{an_[0]['doi']}) '{an_[0]['mix_name']}' — {an_[0]['composition_summary']}")
            st.download_button("candidates_buildability.csv", table.drop(columns=["mix_json"]).to_csv(index=False).encode("utf-8-sig"), "candidates_buildability.csv", "text/csv", key="bd_dl")
        else:
            st.warning("후보가 없습니다.")


# ------------------------------------------------------------------ registry (used by the chat app's '직접 실행' mode)
PAGES = {"모델 현황": page_status, "성능 예측": page_predict, "유동 곡선": page_flowcurve, "구조화 곡선": page_thixo,
         "역설계": page_design, "빌더빌리티·스케줄": page_buildability, "문헌 검색": page_retrieve}
