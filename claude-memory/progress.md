# pmpredict — progress log

Plan: `C:\Users\User\.claude\plans\elsevier-tdm-wiggly-biscuit.md` (approved 2026-09-09).
Source DB (read-only): `C:\Users\User\pastemortar_extraction_package_v1.2.2\master\master.db`.

## 2026-09-09 — M1 data layer

| step | result |
|---|---|
| 1 db.py | 9 tables cached as parquet in 1.2 s; 55,691 numeric measurements (quantity non-null); all NUMERIC_COLS numeric |
| 2 vocab + material_groups.yaml | 139/139 classes mapped to 71 groups (23 powder); other_powder mass share < 3 % (test passes) |
| 3 composition.py | **21,650 / 22,599 mixes normalised (95.8 %)**: abs 9,957 · rel 6,381 · parts 4,905 · solids 407 · failed 949. water_b available 87.8 %. computed-vs-reported w/b: 83.7 % within 0.02, 88.5 % within 0.05; s/b 87 % within 5 %. powder fractions sum to 1 exactly. |
| 4 features.py | 130 features, schema hash `3aac44f160edb9e8`; chem_coverage ≥ 0.8 for 73 %; OPC-family CaO median 62.9 %; blaine/d50/sg present (raw+class-median) 99.5 %; curing_type known 71 % |
| 5 targets.py | compressive 12,314 rows / 6,419 mixes / 1,002 papers (conflict-drop 1.4 %); static yield 780 / 570 / 88; athix 180 / 139 / 21; unit loss ≤ 1.7 % |
| 6 parity | DB mix → MixSpec → featurize reproduces DB features exactly on 200 random mixes (composition, context, chemistry blocks) |

### Decisions / findings worth remembering
- Powder denominator = role ∈ {binder, scm, filler}; class family wins over role except class `other` (role decides). `silica_fume` dosed as "admixture" is still powder.
- `mass_parts` rows mixing percent-parts powder with ratio-valued water/sand (cement 100 pct, water 0.5 ratio) → ratio-unit rows (or tiny values against a ≥20-part powder sum) are reinterpreted as ratios to binder (`parts_ratio_reinterpreted`, 634 mixes).
- 1,078 mixes have *all* powder rows relative to cement (cement = 100 % of itself) → `relc_primary` mode.
- 1,807 component rows have a blank dosage; water/aggregate ones fall back to `w_b_reported` / `sand_binder_ratio` instead of failing the mix.
- master.db has 17 duplicated mix rows (paper 10.1016/j.conbuildmat.2024.137257) → deduplicated on load; worth fixing upstream.
- NaN pitfalls: `nan or default` is truthy; string columns can carry float NaN → every text guard uses `isinstance(x, str)`.
- 6 lean masonry mortars have s/b ≈ 8 (172 kg/m³ cement) — genuine, kept.

| 7 compressive CV | n=11,508 rows / 948 papers. **GroupKFold R² 0.519, RMSE 20.7 MPa, MAE 14.9**, 80 % PI coverage 0.80 (conformal scale 1.47), Ridge R² 0.23, kNN 0.30; **leakage gap 0.24** (random KFold R² 0.745). Hyperparameter variants all within 0.45–0.52 → data-limited. Weak slices: alkali-activated (R² 0.14, RMSE 25), ages < 1 d, cac/mgo (tiny n). Activator-chemistry block (Na₂O %, SiO₂ %, Ms, solution water) added: AAM 0.10 → 0.14, overall 0.505 → 0.519. Accepted below the 0.55 plan guess: the number is leakage-safe over 948 papers. |

Feature schema after activator block: `46fc6fc1a95b98db`, 138 features.

## 2026-09-09 — M2 all targets (GroupKFold by paper, 80 % conformal intervals; `artifacts/reports/summary.md`)

| target | n / papers | R² | R²(log) | Spearman | verdict |
|---|---|---|---|---|---|
| compressive_strength | 11,508 / 948 | 0.52 | 0.37 | 0.67 | usable |
| flexural_strength | 2,991 / 277 | 0.46 | 0.20 | 0.48 | usable |
| direct_tensile_strength | 344 / 53 | 0.50 | 0.45 | 0.71 | usable (small) |
| water_absorption / hardened_density / porosity / cumulative_heat | 930 / 344 / 1,410 / 447 | 0.32 / 0.32 / 0.23 / 0.23 | – | 0.40–0.67 | usable, modest |
| plastic_viscosity | 1,092 / 136 | 0.00 | **0.39** | **0.66** | ranking only (heavy-tailed) |
| initial / final_setting_time | 1,400 / 1,252 | ≈0 | 0.29 / 0.36 | 0.48 / 0.49 | ranking only |
| dynamic / static_yield_stress | 1,201 / 707 | ≈0 | 0.20 / 0.17 | 0.39 / 0.40 | weak-ish; order of magnitude |
| flow_table_spread, mini_slump | 1,058 / 1,279 | −0.06 | −0.06 | 0.1–0.2 | **no signal** (weak) |
| structuration_rate_athix | 165 / 19 | −0.24 | −1.0 | −0.47 | **unusable** (weak) |
| drying / autogenous shrinkage, elastic_modulus, splitting_tensile | | ≈0 | ≈0 | 0.24–0.45 | weak |
| all `__3dcp` variants | 52–250 rows | worse than general | | | predict falls back to general |

- `weak_model` = n < 300 or coverage < 0.65 or R²(log) < 0.15 → flagged in manifest/summary; the inverse layer greys these out.
- predict CLI: OPC mortar w/b 0.40, 28 d cube50 → 53.7 MPa [28.5, 69.1]; flexural 8.4; flow 177 mm; initial set 231 min; porosity 17.5 %.
- Reading: composition explains strength well across 948 papers; fresh-state properties are dominated by paper-level protocol effects (mixer, shear history, measurement geometry) that the DB cannot encode → use literature retrieval (M3 tier-i) as the primary evidence for flow/rheology targets.

## 2026-09-09 — M3 inverse design (pmpredict/design/)
- Modules: `spec.py` (YAML/JSON spec + validation + 3 templates), `units.py`, `space.py` (z∈[0,1]^D ↔ MixSpec, bounded-simplex projection, gates, cardinality), `domain.py` (per-model kNN applicability domain), `uncertainty.py` (split-normal from q10/q50/q90), `objectives.py` (cost/CO₂/clinker with PLACEHOLDER tables), `optimize.py` (Sobol → per-target probability screening → NDS+crowding → farthest-point shortlist → vectorised DE refine), `retrieve.py` (tiered literature hits, paper cap 3), `report.py`/`plots.py`, `validate.py` (closed loop).
- Feasibility = every constraint target above its own `p_min` (target-level, else risk.p_min) & AD ≤ ad_max; relaxation ladder scales thresholds down to ×0.5 then widens AD; all recorded in diagnostics.
- `pmpredict design --spec examples/spec_3dcp_mortar.yaml`: 16,384 samples, 56 s, report/CSV/JSON/PNG written. Rheology targets: static-yield model gives 150–200 Pa with [3, 6000] Pa intervals for candidate printable mortars → P≈0.25; only 1/16,384 feasible at requested thresholds, 212 after ×0.9 relaxation. This is the documented weak-model limitation; the literature tier finds real printable mixes (e.g. w/b 0.14 FA/OPC/SF with 3.35 kPa static yield).
- Tests: design core (5), self-retrieval top-3 ≥ 95 % and paper cap (2), slow e2e + monotonicity in tests/slow.

- Closed loop (`pmpredict validate-design --n 15 --seed 2`, 7 usable mixes with 28 d strength + a second target, generic OPC-based space, ±10 %/±15 % ranges): measured values inside the models' 80 % intervals for 86 %; true mix retrieved (exact tier) 100 %; true mix's P not worse than half the candidates' median 43 %; candidate set closer to the true composition than random feasible mixes only 29 % → **the inverse problem is many-to-one**: many compositions satisfy the same targets, so candidates should be read as *alternatives*, anchored by the published analogues, not as a reconstruction of one "true" mix.
- Candidate de-duplication: distance-based in sweep-scaled composition space (τ = 0.8, admixture dims weighted 0.5) — the demo now returns 5+ distinct designs instead of DE-refined copies.
- Slow e2e tests pass (end-to-end report + monotonicity of w/b with strength target).

## 2026-09-09 — experiment: mixing-protocol features for rheology (PI request)
`use_mixing_protocol: true` → +4 features (mix_time_s, log_mix_time, max_rpm, mixer_type classified into 8 levels; filled 29 % / 13 % / 63 %). Retrained 8 fresh-state targets (GroupKFold):

| target | R²(log) before → after | Spearman before → after | protocol gain share |
|---|---|---|---|
| static_yield_stress | 0.165 → 0.155 | 0.40 → 0.40 | 6 % |
| dynamic_yield_stress | 0.197 → 0.178 | 0.39 → 0.36 | 2 % |
| plastic_viscosity | 0.393 → 0.382 | 0.66 → 0.65 | 1 % |
| structuration_rate_athix | −1.02 → −0.98 | −0.47 → −0.48 | 1 % |
| flow_table_spread | −0.06 → −0.01 | 0.10 → 0.14 | 3 % |
| mini_slump_flow_diameter | −0.06 → −0.01 | 0.18 → 0.20 | 14 % |
| initial / final_setting_time | 0.29 → 0.26 / 0.36 → 0.37 | 0.48 → 0.48 / 0.49 → 0.51 | 1 % / 0 % |

**Verdict: no gain (all within ±0.02 noise)** — the protocol variables that exist in the DB are too sparse and do not encode shear history / rheometer protocol. Reverted to `use_mixing_protocol: false` (schema `46fc6fc1a95b98db`, 138 features), 8 models retrained on the original schema; all 27 models coherent, predictions unchanged. `classify_mixer` and the Conditions.mixer_type field remain available for future use.

## 2026-09-09 — experiment: rheometer protocol covariates from test_protocols (PI request)
Per-test covariates (`targets.build_test_covariates`, joined on the modal `test_uid` of each target group): pre_shear_rate, pre_shear_duration, rest_time, temperature, shear_rate_max, ramp_duration, gap, vane_diameter (coverage 39–55 % of rheology rows) + `tp_geometry` (vane/coaxial/parallel_plate/cone) + `tp_method` (tests.method_name). Enabled via `covariates: [test_protocol]`.

| target | R²(log) before → after | Spearman before → after | tp gain share |
|---|---|---|---|
| static_yield_stress | 0.165 → 0.170 | 0.40 → 0.43 | 15 % (tp_method 11 %) |
| dynamic_yield_stress | 0.197 → 0.171 | 0.39 → 0.36 | 7 % |
| plastic_viscosity | 0.393 → 0.378 | 0.66 → 0.63 | 10 % (shear_rate_max 7 %) |
| structuration_rate_athix | −1.02 → −0.76 | −0.47 → −0.35 | 13 % |

**Verdict: no generalisable gain.** The trees use the protocol features (7–15 % gain share) but out-of-fold quality does not move: within a paper the protocol is constant, so under GroupKFold these covariates act as paper identifiers rather than physics. Reverted the rule (`test_protocol` off); the builder, `data/test_covariates.parquet`, and `Conditions.rheometer*` fields stay available.

Conclusion for rheology: the DB ceiling is reached with tabular features; improving it needs either raw flow-curve digitisation (curves table) or cross-paper protocol normalisation that the literature itself does not support.

## 2026-09-09 — experiment: rheology from digitised flow curves (PI request) → ADOPTED
`curves` table: 199 shear_rate→shear_stress / apparent_viscosity curves (144 mixes, 24 papers, ~6 points each). Bingham least-squares on the upper 80 % of the rate range: 149 good fits (R² ≥ 0.9, μ > 0).
- **Validation against tabulated values of the same mixes**: dynamic yield Spearman 0.88 (median bias +0.05 log10), plastic viscosity Spearman 0.97 (−0.03 log10) → digitisation + fitting reproduces the papers' own Bingham parameters.
- Augmenting the targets with curve-derived τ₀/μ for mixes lacking a tabulated value (+92 / +100 rows, +16 papers): plastic viscosity R²(log) 0.393 → **0.431**, Spearman 0.662 → **0.674**, original-scale R² 0.00 → 0.12; dynamic yield unchanged (0.197 → 0.193 / 0.385 → 0.390).
- Protocol-independent target "stress at 50 s⁻¹" (134 mixes / 21 papers): no signal (Spearman 0.18) — too few papers.
- Adopted as default: `pmpredict/curves.py` + `curve_augment_rheology: true` in targets.yaml; curve rows carry `value_kind_mode='curve_derived'`. `scripts/curves_rheology.py` prints the fit/agreement report.

## 2026-09-09 — Streamlit UI (PI request)
`app/streamlit_app.py`, launched by `pmpredict ui` (streamlit 1.63). Pages: 모델 현황 / 성능 예측 (mix builder → predict_specs, interval plot, MixSpec JSON download) / 역설계 (data_editor targets + slider space → run_twostage → candidates, plots, analogues, literature, report download) / 문헌 검색 (retrieve only). Cached resources: Assets, LiteratureStore. Verified in the in-app browser: prediction and a full design run (8,192 samples, 33 s).
Gotcha: Python kwarg names cannot start with a digit (`3DCP=` → `**{"3DCP": ...}`). The browser tool's launch.json lookup still points at the old project root; start the server with `python -m streamlit run ...` and open http://localhost:8501.

## 2026-09-09 — flow-curve prediction (PI request: rheological behaviour curves, not time curves)
`pmpredict/flowcurve.py`: Bingham τ(γ̇) = τ₀ + μ·γ̇ with τ₀ from the dynamic_yield_stress model and μ from plastic_viscosity; 80 % band by sampling both split-normal (log) predictive distributions independently; nearest published mixes with a digitised curve overlaid (`analogue_curves`). CLI `predict --flow-curve out.png`, UI page "유동 곡선".
Validation (`validate_against_curves`, OOF τ₀/μ from GroupKFold → line vs digitised points; 137 mixes / 23 papers / 1,033 points): mean |log10 err| 0.40 (median 0.33 ≈ ×2.1), 43 % of mixes within ×2, band coverage 0.86, median over-prediction ×1.5; global-median-curve baseline 0.45 → composition adds little beyond order of magnitude (same ceiling as the yield-stress model). One paper (cemconcomp.2012.01.008) is ×10–14 off (likely unit/geometry issue in the source).
Curve inventory (normalised mixes): compressive–age 1,020 curves/130 papers, drying shrinkage 656/96, autogenous 532/83, cumulative heat 503/101, heat flow 294/54, flexural–age 192/26, shear stress–rate 169/23, MIP 128/18. PI: time curves and MIP not of interest for now.

## 2026-09-09 — structuration curve (static yield stress vs rest time) — PI request
`pmpredict/thixocurve.py`, CLI `predict --thixo-curve`, UI page "구조화 곡선". Real curves: 93 (91 mixes / 18 papers), rest window median 80 min, linear (Roussel) fit R² median 0.92, growth ×7.4 median.
- Route "model" (sweep rest_time_s through the static_yield_stress model): level OK but slope ~1/12 of reality (growth ×1.35 vs ×7.4) — 56 % of its training rows lack a rest time. Kept as reference only.
- Route "physical" τ_s(t) = τ_s(0) + Athix·t — PRIMARY. Athix target augmented with curve-fitted Athix (`curves.augment_athix_targets`; +80 rows, papers 21 → 38). Athix model: R²(log) −1.0 → −0.23, Spearman −0.47 → +0.13 (still `weak` overall).
- OOF validation of the physical route on the 82 curve mixes / 17 papers: OOF Athix vs fitted Athix Spearman 0.47, median bias log10 −0.02 (unbiased), 66 % within ×3; curve points |log10 err| median 0.25 (≈×1.8) given the true intercept; 80 % band coverage 0.85.
Reading: the structuration *rate* is predictable to within a factor ~2–3 for printable-mortar-type mixes (which is where the curves come from); the level τ_s(0) inherits the static-yield model's wide interval.

## 2026-09-10 — curve targets in inverse design (PI request)
Derived targets (`design/spec.py: DERIVED_TARGETS`): `shear_stress_at_rate` (conditions.shear_rate_1s; τ₀ + μ·γ̇ from the dynamic-yield and viscosity models, 256-sample split-normal Monte Carlo per candidate) and `static_yield_stress_at_rest` (conditions.rest_time_s; τ_s(0) + Athix·t). A quantity may appear several times with different conditions → all dict keys use `TargetSpec.label` (`shear_stress_at_rate@50/s`). Retrieval interpolates real digitised curves at the requested rate / rest time (plus tabulated static rows within ±20 % rest time) and shows those values in the hits. UI target editor gained 전단속도 / 휴지시간 columns. Example `examples/spec_flowcurve_mortar.yaml`.

## 2026-09-10 — remaining extraction potential in the current corpus (PI question)
- 683 included papers still without full text (manual PDF) — not extractable now.
- Within fetched papers: **29,620 figure series reported, 10,427 digitised → 19,193 not digitised** (1,571 papers; presence-only rows). Rheology presence-only: plastic viscosity 814 rows / 721 mixes / 84 papers, dynamic yield 787 / 675 / 86, static yield 552 / 414 / 55, thixotropy area 186, apparent viscosity 162, shear stress 26. A targeted re-digitisation wave on rheology figures would roughly double rheology data (currently ~950–1,075 mixes per target).
- 3,692 numeric rows are `unmapped_proposed` (quantity NULL) and 10,996 unmapped terms await vocab v1.3 promotion — usable once mapped.

## Status: M1–M3 delivered (2026-09-09). Open items for v1.1
- Rheology/flow models are weak (data ceiling) — consider mixing-protocol features (`use_mixing_protocol: true`, 21k mixes have protocols) and shear-history covariates; curves ingestion; Streamlit UI; user cost/CO₂ tables.

## 2026-09-10 — redig01: rheology figure re-digitisation wave (PI request) → curves +317, strict augmentation filter
Wave in the extraction package (`extract/batches/redig01/`, summary `_WAVE_SUMMARY.md`): 144 papers with presence-only rheology rows; agents digitised figure series into `curves`/`curve_points` via `scripts/add_curves.py`. Result after clean-up: 45 records, **+317 curves / 2,394 points**; master.db curves 10,427 → 10,744.
- **Cheap-model lesson**: haiku agents fabricated data (identical point arrays copied across mixes, perfect lines through the origin, values beyond axis range, bar charts read as lines) in 8 of 23 verified papers and misattributed series in 6 more. All flagged curves deleted (`scripts/audit_redig.py`), affected papers re-done with sonnet + a sonnet verifier pass. Do not use haiku for figure digitisation.
- Bingham fits: 306 curves → 290 good (loose filter), 46 papers; agreement with tabulated values still high (τ0 Spearman 0.94, μ 0.90, n=54/52 mixes).
- **A/B on the same DB (GroupKFold R²log / Spearman)**: augmentation OFF = DY 0.197/0.385, PV 0.393/0.662, Athix −1.02/−0.47 (n=165). Loose filter ON: DY 0.114/0.288 (worse), PV 0.349/0.631 (worse), Athix −0.04/0.23. **Strict filter** (R² ≥ 0.97, xmax ≥ 50 1/s, n ≥ 6 → adopted in `curves.py`): DY **0.202/0.394** (+94 rows), PV 0.383/0.635 (+105 rows, −0.01/−0.03 vs OFF, within noise), Athix unchanged vs loose (structuration curves are filtered separately).
- Flow-curve validation (OOF Bingham band vs digitised curves): 155 mixes / 35 papers, median |log10 err| 0.353 (×2.25; was ×2.1 on 144 mixes/24 papers), 80 % band coverage 0.83, vs global-median-curve baseline 0.548. Athix OOF: Spearman 0.48 (was 0.47), 114 mixes / 23 papers, within ×3 = 0.54.
- Net: more coverage (DY +94, PV +105, Athix rows 165 → 276 mixes, 41 papers) at unchanged DY quality, marginally lower PV pooled quality; Athix went from no signal to weak signal. Tests: 30 passed.

## 2026-09-10 — redig02/redig03 waves + age-series curve augmentation (ADOPTED)
Extraction package: redig02 (3DCP + rheology remainder, 66 papers, 2 passes) +586 curves; redig03 (strength-vs-age + shrinkage-vs-time, 896 papers / 224 manifests, sonnet only) +3,075 curves / 23,504 points. master.db now **14,437 curves / 94,177 points** (was 10,427 / 63,627 before the three waves). QC: `audit_redig.py` 0 fabrication signatures in redig02/03; ~90 duplicate curves (control mix re-plotted across panels) and 3 rule-violating sets (bar-panel reconstruction, guessed mix attribution) removed; sonnet verifier samples all OK (redig02 7 papers, redig03 12 papers). G3 regenerated (gate_G3_record.md 2026-09-10 blocks; headline unchanged since fig_only excluded; A=0/C=0/D=0; all rebuilt workbooks SUBMITTABLE).
- **New: `curves.augment_age_series_targets`** (flag `curve_augment_age_series: true`): drying/autogenous shrinkage and compressive/flexural strength curves (x = age/curing_age/curing_time/time; units normalised to microstrain/MPa) linearly interpolated at the `age_grid` ages inside the plotted range, one `curve_derived` row per (mix, age_bin) lacking a tabulated value. Rows added: drying 16,397 (222 papers), autogenous 10,152 (176), compressive 9,913 (205), flexural 2,052 (46).
- **A/B (same DB, GroupKFold, R²log / Spearman)**, OFF → ON, evaluated on tabulated rows only under ON in brackets: drying_shrinkage 0.059/0.441 (n=815) → pooled 0.484/0.726 [tabulated 0.559/0.683]; autogenous_shrinkage 0.084/0.304 (n=670) → 0.386/0.620 [0.289/0.557]; compressive_strength 0.371/0.667 → 0.434/0.659 [0.432/0.667]; flexural_strength 0.199/0.482 → 0.232/0.484 [0.248/0.451]. Shrinkage models go from ~no signal to usable; strength gains R² at equal Spearman. Adopted.
- Curve inventory now available for future waves (redig04 candidates): cumulative_heat 580 mixes/119 papers, heat_flow 370/74, mass_loss_drying 265/44, expansion 219/36, chemical_shrinkage 158/28 — not yet used as targets.

## 2026-09-10 — redig04 bar-chart wave (Phase A) + per-target bar-curve switch (ADOPTED)
Extraction package: redig04 read grouped bar charts with ≥3 ages per mix as discrete per-mix age series (`curve_type *_vs_age_bars`; 626 papers / 126 manifests, sonnet only). After audit + dedup (12) + verifier removals (90: derived-from-%-labels, cross-panel reconstructions, exposure-condition axes): **589 papers, +5,025 curves / 19,364 points** (compressive 3,944, flexural 934, drying 109, autogenous 27, total shrinkage 11; 4,032 mixes). master.db now **19,462 curves / 113,541 points**. Details: `extract/batches/redig04/_WAVE_SUMMARY.md`, `_verify.md`, gate_G3_record.md 3차 block.
- `curves.load_age_curves` gained `exclude_curve_types` (SQL LIKE on curve_type); pipeline applies `age_series_exclude_curve_types` to every age-series target except those in `age_series_bars_targets`.
- **A/B (same DB, GroupKFold, R²log / Spearman; "tab" = rows of mixes with tabulated values, mix-level match)**, bars ON vs OFF: compressive pooled 0.422/0.688 (n 44,383, 1,325 papers) vs 0.424/0.658 (n 21,993), tab 0.408/0.670 vs 0.411/0.653 → bars **help**; flexural pooled 0.214/0.523 vs 0.249/0.468, tab 0.167/0.423 vs 0.238/0.433 → bars **hurt** (R²log); drying pooled 0.361/0.720 vs 0.372/0.735, tab 0.510/0.657 vs 0.522/0.706 → hurt; autogenous pooled 0.351/0.608 vs 0.376/0.620, tab 0.261/0.544 vs 0.254/0.550 → neutral/worse.
- **Decision**: `age_series_exclude_curve_types: ['%_vs_age_bars']`, `age_series_bars_targets: [compressive_strength]`. Final target table: compressive 12,116 reported + 34,225 curve_derived (bars included, 1,325 papers); flexural 3,194 + 2,206; drying 785 + 16,592; autogenous 729 + 10,164 (bars excluded). Compressive model retrained (R² 0.513, cov80 0.80, ridge 0.259); flexural/shrinkage models = bars-OFF run. Tests: 30 passed.
- Interpretation: manual bar reading (5–15 % uncertainty) is precise enough for compressive strength (large dynamic range, many papers) but adds noise where the tabulated pool is small and values are low (flexural) or where line curves already dominate (shrinkage). Phase B (1–2-age bar scalars) still awaits the PI's spec v1.3 decision.

## 2026-09-10 — full retrain on the redig04 DB + report refresh + inverse-design re-validation (PI: "pmpredict로 넘어가자")
- `train --target all --variant both` (27 models, schema `46fc6fc1a95b98db` unchanged) → `artifacts/reports/summary.md` refreshed. Changes vs the 2026-09-09 table: compressive 11,508 rows/948 papers → **44,383 / 1,325** (R² 0.52 → 0.51, R²log 0.37 → 0.42, Spearman 0.67 → 0.69); flexural 2,991/277 → 5,078/305 (R²log 0.20 → 0.25); drying shrinkage R²log ≈0 → 0.51 / Spearman 0.74; autogenous ≈0 → 0.39 / 0.62; plastic viscosity 0.39 → 0.41 / 0.65; Athix Spearman −0.47 → 0.39 (302 rows, still weak); dynamic yield 0.20 → 0.16 R²log (1,325 rows; within noise); everything else unchanged. Bar curves enter only compressive strength (see previous entry).
- Closed loop `validate-design --n 200 --seed 3` → 73 usable held-out mixes: measured values inside the 80 % intervals for **75 %** (was 86 % on 7 mixes), exact/top-10 literature retrieval **100 %**, true mix's P not worse than the candidates' median 42 %, candidate set closer to the true composition than random feasible mixes 29 % (many-to-one, as before); median 8.6 s per case. Coverage below the 80 % nominal → the joint requirement over ≥2 targets compounds per-target 80 % bands (per-target coverage is 0.80 in CV).
- Demos re-run: 3DCP printable mortar (`demo_3dcp_redig04`): 1/16,384 feasible at the requested thresholds, 258 after ×0.9 relaxation (was 212); static-yield model (p≈0.24) remains the bottleneck, top candidate 43 MPa / 185 Pa / 180 mm. Flow-curve spec (`demo_flowcurve_redig04`): 7,947/8,192 feasible, 12 final candidates, 99 s.
- Deliverable: HTML report "pmpredict 성능 보고서" (artifact) summarising DB state, model table, A/B, closed loop, demos and open items (Phase B, heat curves as targets, UI polish).
