# -*- coding: utf-8 -*-
"""Compare the 20 pastes of Kim, Park & Choi (ACEM26 deck, slide 9) with pmpredict.

Three predictors for static yield stress (SYS, Pa):
  A. full pmpredict model (auto variant; general variant also reported)
  B. literature analogues: DB rows with the same protocol class (paste, rest 0 s) and similar w/b / admixture
  C. protocol-stratified quick model: LightGBM trained only on rest_time_s == 0 rows of the DB
Outputs: artifacts/reports/external/kim2026_ppt_comparison.{csv,md,png}
"""
import copy
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, ".")
from pmpredict.config import load_config  # noqa: E402
from pmpredict.schema import MixSpec  # noqa: E402
from pmpredict.predict import predict_specs, featurize_specs, Assets  # noqa: E402

OUT = "artifacts/reports/external"
# slide 9 table: No, w/c, VA %, HRWRA %, shear stress at yield point (amplitude sweep, Pa), static yield stress (Pa)
KIM = [(1, .30, 0, 0, 55.208, 40.424), (2, .35, 0, 0, 48.100, 15.466), (3, .40, 0, 0, 39.628, 12.021),
       (4, .45, 0, 0, 23.854, 13.423), (5, .50, 0, 0, 22.328, 13.206), (6, .30, .1, 0, 110.610, 37.563),
       (7, .35, .1, 0, 67.687, 26.733), (8, .40, .1, 0, 43.466, 12.754), (9, .50, .1, 0, 21.405, 12.200),
       (10, .30, .2, 0, 141.500, 35.308), (11, .40, .2, 0, 40.167, 22.417), (12, .50, .2, 0, 17.438, 13.945),
       (13, .30, .1, .05, 41.927, 18.238), (14, .30, .1, .10, 6.783, 18.093), (15, .30, .1, .15, 3.297, 14.016),
       (16, .40, .1, .05, 28.796, 15.434), (17, .40, .1, .10, 7.320, 11.843), (18, .40, .1, .15, 5.611, 8.106),
       (19, .50, .1, .05, 11.133, 9.777), (20, .50, .1, .10, 5.499, 6.039)]
K = pd.DataFrame(KIM, columns=["no", "wb", "va", "hrwra", "tau_as", "sys"])

cfg = load_config()
specs = MixSpec.from_json(f"{OUT}/kim2026_pastes.json")
assert len(specs) == 20
NAMES = [s.name for s in specs]


def run(specs_, label):
    df = predict_specs(specs_, cfg, targets=["static_yield_stress"])
    df = df.set_index("spec").loc[[s.name for s in specs_]]
    return df[["q10", "q50", "q90", "model"]].rename(columns=lambda c: f"{label}_{c}")


# A. full model, auto variant (is_3dcp=1 -> 3dcp variant if its CV r2 is higher) and forced general
A_auto = run(specs, "auto")
specs_g = copy.deepcopy(specs)
for s in specs_g:
    s.conditions.is_3dcp = 0
A_gen = run(specs_g, "gen")
# rest-time sensitivity (auto variant)
sens = {}
for rt in [0, None, 300, 1800]:
    ss = copy.deepcopy(specs)
    for s in ss:
        s.conditions.rest_time_s = rt
    sens[str(rt)] = run(ss, "s")["s_q50"].median()

# B. literature analogues with the same protocol class
F = pd.read_parquet("data/features.parquet")
T = pd.read_parquet("data/targets.parquet")
t = T[T.target == "static_yield_stress"].merge(F, on="mix_uid", suffixes=("", "_f"))
pool = t[(t.system_type == "paste") & (t.rest_time_s == 0)].copy()
for c in ["water_b", "adx_vma_pct", "adx_sp_pce_pct", "adx_sp_other_pct"]:
    pool[c] = pool[c].astype(float)
pool["sp"] = pool.adx_sp_pce_pct.fillna(0) + pool.adx_sp_other_pct.fillna(0)
ana = []
for r in K.itertuples():
    m = pool[(abs(pool.water_b - r.wb) <= 0.05) & (pool.adx_vma_pct.fillna(0) <= max(0.3, r.va * 2)) & (pool.sp <= max(0.2, r.hrwra * 2))]
    v = m.value.astype(float)
    ana.append(dict(ana_n=len(m), ana_papers=m.paper_uid.nunique(), ana_med=v.median() if len(m) else np.nan,
                    ana_q25=v.quantile(.25) if len(m) else np.nan, ana_q75=v.quantile(.75) if len(m) else np.nan))
ANA = pd.DataFrame(ana, index=NAMES)

# C. protocol-stratified quick model on rest_time_s == 0 rows (all system types)
import lightgbm as lgb  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

feat = ["water_b", "adx_vma_pct", "adx_sp_pce_pct", "adx_sp_other_pct", "sand_b", "cement_share", "scm_frac", "is_3dcp",
        "pw_silica_fume", "pw_fly_ash_f", "pw_ggbfs", "pw_limestone_powder", "pw_metakaolin"]
feat = [f for f in feat if f in t.columns]
r0 = t[t.rest_time_s == 0].copy()
X0 = r0[feat].astype(float)
y0 = np.log(r0.value.astype(float).clip(lower=0.1))
g0 = r0.paper_uid
params = dict(n_estimators=300, learning_rate=0.05, num_leaves=7, max_depth=4, min_child_samples=10, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0)
oof = np.zeros(len(r0))
for tr, te in GroupKFold(5).split(X0, y0, g0):
    m = lgb.LGBMRegressor(**params).fit(X0.iloc[tr], y0.iloc[tr])
    oof[te] = m.predict(X0.iloc[te])
cv_rho = spearmanr(oof, y0).correlation
cv_r2 = 1 - ((oof - y0) ** 2).sum() / ((y0 - y0.mean()) ** 2).sum()
mC = lgb.LGBMRegressor(**params).fit(X0, y0)
assets = Assets(cfg)
FK, _ = featurize_specs(specs, assets)
XK = FK[feat].astype(float)
XK["is_3dcp"] = 1
C_pred = np.exp(mC.predict(XK))
XK0 = XK.copy()
XK0["is_3dcp"] = 0
C_pred0 = np.exp(mC.predict(XK0))
# how strongly the 3DCP flag acts as a protocol proxy inside the training pool
flag = {k: dict(n=len(g), papers=g.paper_uid.nunique(), median=float(g.value.astype(float).median()),
                rest0=float((g.rest_time_s == 0).mean()), rest_unknown=float(g.rest_time_s.isna().mean()))
        for k, g in t.groupby("is_3dcp")}
flag_paste = {k: float(g.value.astype(float).median()) for k, g in t[t.system_type == "paste"].groupby("is_3dcp")}

R = K.copy()
R["spec"] = NAMES
R["A_auto_q50"] = A_auto.auto_q50.values
R["A_auto_q10"] = A_auto.auto_q10.values
R["A_auto_q90"] = A_auto.auto_q90.values
R["A_auto_model"] = A_auto.auto_model.values
R["A_gen_q50"] = A_gen.gen_q50.values
R["B_ana_med"] = ANA.ana_med.values
R["B_ana_n"] = ANA.ana_n.values
R["B_ana_papers"] = ANA.ana_papers.values
R["C_rest0_q50"] = C_pred
R["C_rest0_gen_q50"] = C_pred0
R["A_gen_q10"] = A_gen.gen_q10.values
R["A_gen_q90"] = A_gen.gen_q90.values


def metrics(pred, meas=R.sys):
    pred = pd.Series(np.asarray(pred, dtype=float), index=meas.index)
    ok = pred.notna()
    p, m = pred[ok], meas[ok]
    return dict(n=int(ok.sum()), spearman=spearmanr(p, m).correlation, median_ratio=float(np.median(p / m)),
                mdape=float(np.median(abs(p - m) / m)))


def factor_signs(pred):
    """Mean Spearman of the prediction along each design axis, inside subsets where the other two axes are fixed."""
    d = R.assign(p=np.asarray(pred, dtype=float))
    out = {}
    for name, key in [("w/b", "wb"), ("VA", "va"), ("HRWRA", "hrwra")]:
        other = [c for c in ["wb", "va", "hrwra"] if c != key]
        rho = []
        for _, grp in d.groupby(other):
            if grp[key].nunique() >= 3 and grp.p.notna().all():
                rho.append(spearmanr(grp[key], grp.p).correlation)
        out[name] = float(np.nanmean(rho)) if rho else np.nan
    return out


M = {"A 전체 모델(auto)": metrics(R.A_auto_q50), "A 전체 모델(general)": metrics(R.A_gen_q50),
     "B 문헌 유사배합 중앙값(rest 0 s, paste)": metrics(R.B_ana_med), "C rest-0 층화 모델(is_3dcp=1)": metrics(C_pred),
     "C rest-0 층화 모델(is_3dcp=0)": metrics(C_pred0)}
S = {"측정값 SYS (Kim)": factor_signs(R.sys), "τ_AS (Kim, 진폭스윕)": factor_signs(R.tau_as), "A 전체 모델(auto)": factor_signs(R.A_auto_q50),
     "A 전체 모델(general)": factor_signs(R.A_gen_q50), "B 유사배합": factor_signs(R.B_ana_med), "C rest-0 모델(is_3dcp=0)": factor_signs(C_pred0)}
cov80 = float(((R.sys >= R.A_auto_q10) & (R.sys <= R.A_auto_q90)).mean())
cov80g = float(((R.sys >= R.A_gen_q10) & (R.sys <= R.A_gen_q90)).mean())
width_g = float((R.A_gen_q90 / R.A_gen_q10).median())
tau_rho = spearmanr(R.tau_as, R.sys).correlation
R.to_csv(f"{OUT}/kim2026_ppt_comparison.csv", index=False)

# figure
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pmpredict.flowcurve import _korean_font  # noqa: E402

_korean_font()
fig, axes = plt.subplots(1, 3, figsize=(12, 4), dpi=130)
panels = [("A_auto_q50", "A. pmpredict 전체 모델 (is_3dcp=1)"), ("A_gen_q50", "A'. 전체 모델, is_3dcp=0"),
          ("B_ana_med", "B. 문헌 유사배합 중앙값 (paste, 정치 0 s)")]
for ax, (col, ttl) in zip(axes, panels):
    sc = ax.scatter(R.sys, R[col], c=R.hrwra, cmap="viridis", s=45, edgecolor="k", lw=.4)
    ax.plot([1, 1e4], [1, 1e4], "k--", lw=.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(3, 100)
    ax.set_ylim(1, 1e4)
    mm = metrics(R[col])
    ax.set_title(f"{ttl}\nρ={mm['spearman']:.2f}, 중앙 비 {mm['median_ratio']:.1f}×", fontsize=9)
    ax.set_xlabel("측정 정적항복응력 (Pa)")
    ax.grid(alpha=.3, which="both")
axes[0].set_ylabel("예측 (Pa)")
fig.colorbar(sc, ax=axes, label="HRWRA (%)", shrink=.8)
fig.savefig(f"{OUT}/kim2026_ppt_comparison.png", bbox_inches="tight")
plt.close(fig)

# report
n0, p0 = len(pool), pool.paper_uid.nunique()
L = ["# Kim et al. (ACEM26 발표자료) 실험값 vs pmpredict 비교 — wave 25/26 재학습 모델 기준", "",
     "자료: `ACEM26_Kim_static_yield_buildability.pdf` 슬라이드 9 (20 배합, 결합재 C70:FA20:SF10, w/b 0.30–0.50, VA 0–0.2 %, HRWRA 0–0.15 %). "
     "측정: 회전식 저전단속도 정적항복응력(SYS, 정치 0 s)과 진폭스윕 항복점 전단응력(τ_AS). "
     f"슬라이드 내 τ_AS→SYS 회귀 R²=0.79 (Spearman τ_AS vs SYS = {tau_rho:.2f}). "
     "슬라이드 10의 자체 ML(Ridge R² 0.91)은 20점 내부 적합값이므로 외부 예측 성능과 직접 비교할 수 없다.", "",
     "## 세 가지 예측자의 성적", "", "| 예측자 | n | Spearman ρ | 중앙 예측/측정 비 | 중앙 절대 %오차 |", "|---|---|---|---|---|"]
for k, v in M.items():
    L.append(f"| {k} | {v['n']} | {v['spearman']:.2f} | {v['median_ratio']:.1f}× | {v['mdape'] * 100:.0f} % |")
L += ["", f"전체 모델(is_3dcp=1)의 80 % 예측구간 포함률: {cov80 * 100:.0f} % (20배합 중 {int(round(cov80 * 20))}); "
      f"is_3dcp=0으로 두면 {cov80g * 100:.0f} %지만 구간 폭 중앙값이 {width_g:,.0f}배(q90/q10)로 사실상 정보가 없다. "
      f"사용 모델: {', '.join(sorted(set(R.A_auto_model)))} (3DCP 변형은 CV R²가 낮아 선택되지 않음).",
      "정치시간 조건 민감도(전체 모델, 20배합 q50 중앙값): " + ", ".join(f"rest={k}: {v:.0f} Pa" for k, v in sens.items()) + ".", "",
      "## 설계 축별 효과 부호 (다른 두 축을 고정한 부분집합에서 축 3수준 이상일 때의 평균 Spearman)", "",
      "| 예측자 | w/b | VA | HRWRA |", "|---|---|---|---|"]
for k, v in S.items():
    L.append(f"| {k} | {v['w/b']:+.2f} | {v['VA']:+.2f} | {v['HRWRA']:+.2f} |")
f1, f0 = flag.get(1, {}), flag.get(0, {})
ratio_flag = float(np.median(R.A_auto_q50 / R.A_gen_q50))
L += ["", "## 해석", "",
      f"- **편향의 주원인은 `is_3dcp` 플래그다.** 같은 배합·조건에서 플래그만 1→0으로 바꾸면 예측이 중앙값 기준 {ratio_flag:.0f}배 내려가고 순위상관은 "
      f"{M['A 전체 모델(auto)']['spearman']:.2f}→{M['A 전체 모델(general)']['spearman']:.2f}, 수준 비는 {M['A 전체 모델(auto)']['median_ratio']:.0f}×→{M['A 전체 모델(general)']['median_ratio']:.1f}×가 된다. "
      f"학습 풀에서 3DCP 논문의 정적항복응력 중앙값은 {f1.get('median', float('nan')):,.0f} Pa({f1.get('n', 0)}행/{f1.get('papers', 0)}편), 비3DCP 논문은 {f0.get('median', float('nan')):,.0f} Pa({f0.get('n', 0)}행/{f0.get('papers', 0)}편); "
      f"페이스트만 보면 {flag_paste.get(1, float('nan')):,.0f} Pa 대 {flag_paste.get(0, float('nan')):,.0f} Pa. 정치시간이 0 s로 명시된 행은 두 그룹 모두 {f1.get('rest0', 0) * 100:.0f} %/{f0.get('rest0', 0) * 100:.0f} %에 불과하고 "
      f"{f1.get('rest_unknown', 0) * 100:.0f} %/{f0.get('rest_unknown', 0) * 100:.0f} %는 미기재다. 즉 플래그가 '인쇄용 배합'이 아니라 '정치 후 측정 프로토콜'의 대리변수로 학습됐다.",
      f"- DB에서 Kim과 같은 프로토콜 계열(페이스트, 정치 0 s)의 행은 {n0}행/{p0}편뿐이고 중앙값 {pool.value.astype(float).median():.0f} Pa로 Kim(6–40 Pa)과 같은 자릿수다. "
      "다만 w/b 0.35–0.40 구간의 유사배합은 2편(약 300 Pa, 다른 결합재)에 의존해 B의 순위상관은 음수다. 유사배합 검색은 표본이 너무 작아 검증 수단이 못 된다.",
      f"- 정치 0 s 행만으로 학습한 층화 모델 C(행 {len(r0)}, 논문 {g0.nunique()}, 논문 단위 5겹 CV Spearman {cv_rho:.2f}, R²log {cv_r2:.2f})도 "
      f"플래그 값에 따라 {M['C rest-0 층화 모델(is_3dcp=1)']['median_ratio']:.0f}× / {M['C rest-0 층화 모델(is_3dcp=0)']['median_ratio']:.1f}×로 갈리고 순위상관은 두 경우 모두 낮다. "
      "표본이 작아 프로토콜 층화만으로는 부족하고, 정치시간·전단이력을 명시 특성으로 재추출하는 idea 2가 필요하다.",
      "- 설계 축: w/b 효과(음)는 전체 모델이 측정과 같은 부호·크기로 재현한다. VA는 모델이 단조 증가로 보지만 Kim 측정에서는 약한 효과다. "
      "HRWRA 0.05–0.15 %는 학습 풀 5분위(0.08 %) 근처의 저용량이라 모델 예측이 세 수준에서 거의 같고, 측정의 단조 감소(ρ −0.93)를 재현하지 못한다.",
      "- τ_AS(진폭스윕 항복점)는 DB 어휘에 없는 양(storage_modulus_g_prime, critical_strain_lvr만 존재)이라 모델 비교 대상이 아니다. "
      "Kim 자체 데이터에서 τ_AS와 SYS의 순위상관은 0.72다.",
      "", "## 권고", "",
      "1. 예측 시 `is_3dcp`는 '인쇄 논문 출처'가 아니라 '정치 후 측정'의 대리변수로 작동하므로, 실험실 페이스트의 τ_s(0)를 물을 때는 is_3dcp=0으로 두고 구간을 자릿수 참고로만 쓴다.",
      "2. idea 2: 정적항복응력을 rest_time·전단이력 프로토콜 클래스와 함께 재추출하고 τ_s(0)·Athix를 분리 타깃으로 두면 이 편향은 구조적으로 제거된다.",
      "3. Kim 20배합은 DB의 저용량 HRWRA 공백(0.05–0.15 %)을 채우는 데이터이므로, 인쇄성 결과가 나오면 DB에 등록할 가치가 있다(현재 우선순위는 낮음).",
      "", "파일: `kim2026_ppt_comparison.csv`, `kim2026_ppt_comparison.png` (이 폴더)."]
open(f"{OUT}/kim2026_ppt_comparison.md", "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
