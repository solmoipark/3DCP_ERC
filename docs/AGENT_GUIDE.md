# pmpredict 에이전트 사용 설명서

3DCP(3D 프린팅 콘크리트) 연구실용 배합 설계 조수. 채팅으로 물어보면 문헌 DB로 학습된 예측 모델·역설계기·빌더빌리티 계산기·문헌 검색·읽기 전용 SQL을 도구로 써서 답합니다. 모든 수치는 도구 결과에서 오고, 예측값은 항상 `q50 [q10, q90]`(80 % 구간)과 단위를 함께 씁니다.

---

## 1. 한눈에

| 하고 싶은 것 | 물어보는 예 | 에이전트가 쓰는 도구 |
|---|---|---|
| 배합 → 성능 예측 | "w/b 0.35, OPC 85 % + SF 15 %, PCE 0.3 % 모르타르의 28일 압축강도와 정적항복응력" | `predict_properties`, `flow_curve`, `structuration_curve` |
| 목표 → 배합 역설계 | "28일 압축 ≥ 40 MPa, 정적항복 1–4 kPa, 클링커 최소" | `design_mix` (+ `retrieve_literature`) |
| 노즐·구조물 → 빌더빌리티·스케줄 | "25 mm 노즐, 600 mm 벽, τ_s 3 kPa면 되나? 사이클 시간은?" | `assess_buildability`, `print_schedule`, `similar_prints`, `design_for_print_job` |
| 문헌 배합 찾기 | "정적항복 2 kPa 이상 3DCP 배합 10개" | `retrieve_literature` |
| 문헌 DB 통계 | "VMA 쓴 3DCP 논문이 몇 편?" | `describe_schema` → `sql_query` |
| 정리·저장·기억 | "보고서로 저장해줘", "앞으로 시험편은 prism40으로 기억해" | `save_report`, `remember` |

데이터: 문헌 DB 3,274편 / 29,626 믹스(정규화 28,001), 프린트 라벨 DB 1,014편 / 7,420 프린트 런. 모델 지표는 논문 단위 교차검증(GroupKFold).

---

## 2. 시작하기

### 웹 (권장)
```bash
streamlit run app/streamlit_app.py
```
브라우저에서 `http://localhost:8501`. 왼쪽 사이드바에서 백엔드·모델·세션을 고르고, 아래 입력창에 질문합니다. 예시 질문 버튼을 누르면 바로 실행됩니다. 기존 폼 화면은 사이드바의 **"직접 실행 (기존 폼)"** 토글로 열 수 있습니다.

### 터미널
```bash
python -m pmpredict.cli agent            # 대화형 (명령: /new /sessions /artifacts /quit)
python -m pmpredict.cli agent -p "질문"  # 한 번만 묻고 종료
python -m pmpredict.cli agent --check    # 어떤 백엔드가 쓰이는지 확인
```

### LLM 백엔드
자동 감지 순서: **API 키 → 로그인된 구독**. 사이드바나 `--provider`로 바꿀 수 있습니다.

| 백엔드 | 준비 | 비고 |
|---|---|---|
| Anthropic API | `ANTHROPIC_API_KEY` 또는 pastemortar `config.json`의 `anthropic_api_key` | 기본 모델 claude-sonnet-5, 옵션 claude-opus-5 |
| OpenAI API | `OPENAI_API_KEY` 또는 `openai_api_key` | 모델은 `PMPREDICT_OPENAI_MODEL` |
| Claude 구독 | 내장 CLI 로그인 1회 (아래) | 개인 로컬 사용 전용, 웹 배포 금지. 헤드리스 사용은 별도 주간 한도 |
| ChatGPT 구독 | `npm i -g @openai/codex` + `codex login` | 도구는 MCP로 전달 |

Claude 구독 로그인 (PowerShell, `&` 필요):
```powershell
& "C:\Users\User\AppData\Local\Programs\Python\Python312\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe" auth login
```
정확한 경로는 `--check` 출력에 나옵니다. 키 값은 화면·로그·저장소 어디에도 기록되지 않습니다.

---

## 3. 이렇게 물어보세요

좋은 질문에는 다음이 들어 있습니다. 빠진 값은 에이전트가 **기본값을 쓰고 그 사실을 답에 명시**합니다.

- **배합**: 시스템(paste/mortar), w/b, s/b, 결합재 조성(분율), 혼화제(결합재 대비 %), 섬유(부피 %).
- **조건**: 재령(기본 28 d), 압축 시험편(기본 50 mm 큐브), 양생(기본 습윤 20 °C), 3DCP 배합 여부.
- **목표**(역설계·검색): 타깃마다 "≥ / ≤ / 범위 / 목표값" 중 하나와 단위.
- **프린트 작업**: 구조물 종류, 목표 높이, 벽 길이 또는 원통 직경, 노즐 크기, 속도, 오픈 타임, 재료(정적항복응력·Athix 또는 배합).

예시:
- "OPC 모르타르 w/b 0.40, s/b 2.0, PCE 0.5 %의 28일 압축강도와 플로우"
- "위 배합의 유동곡선과 구조화 곡선(60분)도 뽑고 문헌 실측 곡선과 비교"
- "28일 압축 ≥ 40 MPa, 정적항복 1–4 kPa(휴지 0 s)인 문헌 배합 10개, 3DCP 우선"
- "같은 조건으로 클링커 최소화 역설계. OPC 필수 0.5–1.0, SF 0–0.15, 석회석 0–0.3, w/b 0.28–0.45. 확인 없이 바로 실행"
- "25 mm 노즐, 높이 600 mm, 길이 1.5 m 벽(2필라멘트), 50 mm/s, 오픈타임 60분. τ_s 3 kPa, Athix 1 Pa/s면 되는지 판정하고 사이클 시간 창"
- "이 작업에 맞는 배합을 역설계해줘 (design_for_print_job)"
- "3DCP 논문 중 VMA를 쓴 논문 수와 그 믹스들의 정적항복응력 중앙값"
- "지금까지 결과를 보고서 파일(md + xlsx)로 저장"
- "기억해: 우리 랩 기본 시험편은 comp_prism40"

느린 도구(`design_mix`, `design_for_print_job`, 30–150 s)는 목표와 탐색 공간이 충분히 주어지면 바로 실행하고, 부족하면 한 번만 되묻습니다. "확인 없이 실행"이라고 쓰면 되묻지 않습니다.

---

## 4. 배합을 말하는 법 (mix)

에이전트는 자연어를 아래 규약의 dict로 바꿔 도구에 넘깁니다. 직접 JSON으로 줘도 됩니다.

```json
{"system_type": "mortar", "w_b": 0.35, "s_b": 1.5,
 "binder": {"portland_cement": 0.85, "silica_fume": 0.15},
 "admixtures_pct": {"superplasticiser_pce": 0.5, "vma_cellulose": 0.2},
 "fibres_vol_pct": {}, "nano_pct": {},
 "conditions": {"age_d": 28, "comparability_group": "comp_cube50", "curing": "moist", "rest_time_s": 0, "is_3dcp": true},
 "name": "my_mix"}
```

| 항목 | 의미 | 규약 |
|---|---|---|
| `binder` | 결합재(powder) 클래스 → 질량분율 | 합이 1이 아니면 자동 정규화(경고 표시) |
| `s_b` | 잔골재/결합재 질량비 | 모르타르만; 페이스트는 무시 |
| `admixtures_pct` | 혼화제 → 결합재 질량 대비 % | 제품 투입량 기준 (고형분 아님) |
| `fibres_vol_pct` | 섬유 → 혼합물 부피 % | |
| `nano_pct` | 나노재료 → 결합재 대비 % | |
| `activators` | 활성화제 → {amount(결합재 대비 질량비), molarity} | 알칼리 활성 계열 |
| `material_props` | 클래스별 산화물·Blaine·비중·d50 | 없으면 클래스 중앙값 대치 |
| `conditions.curing` | 양생 | `water`/`moist`/`sealed`/`ambient`/`steam` 또는 프리셋 이름 |
| `conditions.is_3dcp` | 3DCP 배합 여부 | true면 3DCP 전용 모델을 품질이 더 높을 때 자동 선택 |

재료 클래스 이름은 고정 어휘입니다(예: `portland_cement`, `fly_ash_class_F`, `ggbfs`, `silica_fume`, `limestone_powder`, `metakaolin`, `superplasticiser_pce`, `vma_cellulose`, `accelerator_setting`, `nano_clay`). 모르면 "결합재 클래스 목록 보여줘"라고 하면 `describe_vocabulary`로 확인합니다. 틀린 이름은 가장 비슷한 후보와 함께 오류로 돌아옵니다.

---

## 5. 목표를 말하는 법 (targets)

| kind | 뜻 | 필요한 값 | 예 |
|---|---|---|---|
| `ge` | 하한 이상 | `lo` | 압축 ≥ 40 MPa → `lo: 40` |
| `le` | 상한 이하 | `hi` | 소성점도 ≤ 50 Pa·s → `hi: 50` |
| `range` | 사이 | `lo`, `hi` | 정적항복 1–4 kPa → `lo: 1, hi: 4, unit: kPa` |
| `goal` | 목표값에 가깝게 | `goal` | 플로우 180 mm 근처 |

- 단위(`unit`)를 쓰면 자동 변환합니다(kPa→Pa, h→min …).
- 조건: `age_d`, `comparability_group`(강도), `rest_time_s`(정적항복), `shear_rate_1s`(유동곡선 점).
- 파생 타깃: `shear_stress_at_rate`(전단속도 지정), `static_yield_stress_at_rest`(휴지시간 지정; 빌더빌리티의 "프린트 종료 시 τ_s").
- `p_min`: 만족 확률 하한. 강도 0.6–0.7, 유변·플로우처럼 모델이 약한 타깃은 0.3–0.4.

탐색 공간(`space`): `w_b`, `s_b` 범위, 결합재 클래스별 `{lo, hi, required}`, 혼화제 범위(%), 최대 결합재 성분 수, 양생. 목적함수: `clinker_fraction`, `co2`, `cost`, `co2_per_mpa`, `cost_per_mpa`(비용·CO₂ 표는 예시값이니 교체 필요).

---

## 6. 프린트 작업을 말하는 법 (job)

| 항목 | 의미 | 기본값 |
|---|---|---|
| `object_type` | wall / hollow_cylinder / column / other | wall |
| `target_height_mm` | 목표 높이 | 필수 |
| `footprint_mm` | 벽 길이 또는 원통 직경 → 층당 경로 | — |
| `wall_filaments` | 벽 두께 방향 필라멘트 수 | 1 |
| `nozzle_d_mm` 또는 `nozzle_w_mm`+`nozzle_h_mm` | 노즐 | — |
| `layer_height_mm`, `layer_width_mm` | 층 높이·폭 | 0.5·노즐, 1.2·노즐 (출력 가능 런 중앙값) |
| `print_speed_mm_s` | 속도 | 40 |
| `layer_cycle_time_s` | 층 사이클 시간 | 경로/속도 + dwell |
| `open_time_min`, `start_time_after_mixing_min` | 오픈 타임, 시작 시각 | — / 0 |
| `safety_factor` | 하중 안전율 | 1.5 |
| `check_buckling` | 자유 벽 좌굴 검토(벽만) | true |

재료는 측정값(`tau_s0_Pa`, `athix_Pa_s`, 밀도, E/τ_s) 또는 배합(mix → pmpredict 예측)으로 줍니다. Athix가 없으면 문헌 비율(중앙 0.0007 s⁻¹ × τ_s)로 채우고 그 사실을 표시합니다.

---

## 7. 결과 읽는 법

- **예측값** `q50 [q10, q90]`: 중앙 예측과 80 % 구간. 구간이 한 자릿수 이상 넓으면 자릿수 참고용.
- **weak_model**: 학습 표본이 적거나 구간 커버리지·순위력이 낮은 모델(유변·플로우 대부분). 이때는 문헌 유사 배합이 1차 근거.
- **n_range_violations**: 학습 범위 밖 특성 수. 0이 아니면 외삽.
- **문헌 검색 tier**: `exact` = 모든 목표를 실측값으로 만족, `near` = 근접.
- **역설계 후보**: `p_feasible`(타깃별 만족 확률의 곱), `ad_max`(적용가능영역 거리, 1 이하가 내삽), 목적함수 값, 유사 문헌 DOI. 유변 타깃이 약하면 P가 0.3 수준으로 낮은 것이 정상.
- **빌더빌리티**: `printable / borderline / non_printable`과 지배 모드(plastic_collapse, elastic_buckling, open_time). `n_max`는 안전율 없이/있이 두 값. `R = ρgH/(√3·τ_s)`와 경험적 붕괴확률(146 스택 파괴 시험의 분포)은 보조 지표. 사이클 시간 창은 최소(안정) ≤ 최대(오픈 타임)일 때만 실현 가능하며, 닫혀 있으면 필요한 τ_s(0)/Athix와 대안이 함께 나옵니다.

---

## 8. 도구 레퍼런스

`*` = 필수 입력. 느린 도구는 ★.

| 도구 | 용도 | 입력 | 산출물 |
|---|---|---|---|
| `list_models` | 예측 가능한 타깃과 모델 품질 | variant | 모델표 |
| `describe_vocabulary` | 재료 클래스·시험편·양생·타깃 이름 | family, query | 목록 + mix 예시 |
| `build_mix_spec` | 배합 dict 검증 | mix* | MixSpec JSON |
| `predict_properties` | 성능 예측 | mix*, targets | 표 CSV, 예측구간 PNG |
| `flow_curve` | Bingham 유동곡선 + 문헌 실측 | mix*, max_rate_1s, n_analogues | PNG, CSV |
| `structuration_curve` | τ_s(t) 구조화 곡선 + 문헌 실측 | mix*, max_rest_min, n_analogues | PNG, CSV |
| `retrieve_literature` | 목표 근처 문헌 배합 | targets*, system_type, prefer_3dcp, n | literature.csv |
| `design_mix` ★ | 역설계 | targets*, space, objectives, budget, top_n | report.md, candidates.csv, pareto.png … |
| `assess_buildability` | 판정 + 스케줄 + 유사 프린트 | job*, material 또는 mix | assessment.md, 스윕 PNG/CSV |
| `print_schedule` | 사이클 시간·속도 창만 | job*, material 또는 mix | 스윕 PNG |
| `similar_prints` | 비슷한 문헌 프린트 | job*, material, k | CSV |
| `design_for_print_job` ★ | 작업 → 필요 유변 → 배합 후보 → 후보별 판정 | job*, space, extra_targets, budget | candidates_buildability.csv + 역설계 산출물 |
| `describe_schema` | DB 테이블·컬럼·샘플 | db, table | — |
| `sql_query` | 읽기 전용 SELECT (200행, 20 s) | sql*, db, max_rows | 20행 초과 시 CSV |
| `save_report` | 보고서 저장 | title*, markdown*, tables, include_artifacts, format | .md, .xlsx |
| `remember` | 세션 간 노트 | note*, kind | notes.md |

---

## 9. 세션·기억·파일

- 세션은 `~/.pmpredict/agent/sessions/<id>/`에 저장됩니다(트랜스크립트, 메타, 요약). 사이드바나 `--session <id>`로 이어갑니다. 대화가 길어지면 자동 요약이 앞부분을 대신합니다.
- "기억해"로 남긴 노트는 `~/.pmpredict/agent/notes.md`에 쌓이고 모든 세션의 시스템 프롬프트에 들어갑니다.
- 도구가 만든 파일은 `artifacts/reports/agent/<세션 id>/`에 있습니다(웹에서는 다운로드 버튼). `save_report`는 그 아래 `reports/`에 md와 xlsx를 만듭니다. 이 폴더는 git에 올라가지 않습니다.
- 도구 결과가 크면 표는 20행만 모델에 보이고 전체는 CSV로 남습니다.

---

## 10. 한계와 주의

- 모델은 문헌 데이터의 상관관계입니다. 실험을 대체하지 않으며 최종 배합은 실험 검증이 필요합니다.
- 정적항복응력·Athix·플로우 모델은 80 % 구간이 한 자릿수 이상 넓습니다. 문헌 정적항복응력은 시험 프로토콜(휴지시간·장비)이 섞여 있습니다.
- 빌더빌리티의 자유 벽 좌굴은 가장 보수적인 경계조건입니다. 닫힌 경로나 보강된 벽이면 `check_buckling=false` 또는 필라멘트 수를 늘리세요. 선형 구조화 법칙은 90분 이상 프린트에서 과대평가할 수 있습니다.
- 비용·CO₂ 표는 예시값입니다.
- 느린 도구 실행 중에는 웹 입력이 잠기고 중단 버튼이 없습니다(최대 약 2.5분).
- 구독 백엔드는 이 PC의 개인 사용 전용입니다. 공개 배포에는 API 키를 쓰세요.

---

## 11. 문제 해결

| 증상 | 조치 |
|---|---|
| `--check`에 chosen: none | API 키를 넣거나 구독 로그인(2절). |
| PowerShell에서 경로 실행 오류 | 따옴표 경로 앞에 `&` |
| "Not logged in · Please run /login" | 내장 CLI 로그인은 데스크톱 앱과 별개입니다. 2절의 `auth login` 실행 |
| 도구 오류 `SpecValidationError`/`NormaliseError` | 에이전트가 입력을 고쳐 재시도합니다(최대 2회). 반복되면 재료 클래스 이름·단위·kind를 명시 |
| 답이 너무 길다 | "짧게", "표로만"이라고 덧붙이면 됩니다 |
| 이전 대화를 잊음 | 세션을 확인(`/sessions`). 새 세션이면 요약을 붙여 다시 물어보기 |

---

## 12. 파일 구조

```
pmpredict/agent/
  tools/registry.py      도구 정의 (이름·설명·JSON schema·함수) → Anthropic/OpenAI/MCP 투영
  tools/normalise.py     자연어 dict → MixSpec / DesignSpec / PrintJob
  tools/*_tools.py       16개 도구 구현
  providers/             anthropic_api · openai_api · claude_sdk · codex_cli · fake
  core.py                Agent (프롬프트·기록·도구 실행 루프)
  memory.py, prompt.py   세션 저장, 시스템 프롬프트
  mcp_server.py          stdio MCP 서버 (pmpredict agent-mcp)
  cli.py                 pmpredict agent
app/streamlit_app.py     채팅 UI · app/legacy_pages.py 기존 폼
tests/test_agent.py      스키마·SQL 가드·변환·비밀키·가짜 백엔드 종단 간 테스트
```
