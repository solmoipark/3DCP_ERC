# Design report — print_cylinder_300

Generated 2026-09-14T07:49:07+00:00 · pmpredict 0.1.0

## Request

| target | kind | lo | hi | goal | conditions |
|---|---|---|---|---|---|
| static_yield_stress_at_rest | ge | 5.35e+03 |  |  | rest_time_s=589.0486225480861 |
| static_yield_stress | range | 195 | 4.7e+03 |  | rest_time_s=0 |
| plastic_viscosity | le |  | 65.4 |  |  |
| compressive_strength | ge | 30 |  |  | age_d=28, comparability_group=comp_cube50 |

Space: mortar, w/b (0.25, 0.42), s/b (0.8, 1.8), binder ['portland_cement', 'silica_fume', 'limestone_powder', 'fly_ash_class_F'], admixtures ['superplasticiser_pce', 'vma_cellulose'], max binder components 3.
Objectives: ['clinker_fraction min', 'co2 min']. Risk: p_min 0.5, ad_max 1.0, combine product.

## Models used

| target | model | n | papers | R² | R²(log) | Spearman | cov80 | weak |
|---|---|---|---|---|---|---|---|---|
| static_yield_stress_at_rest@589.049s | derived(static_yield_stress + structuration_rate_athix) | 692 | 124 |  | 0.0362 | 0.222 | 0.8 | **yes** |
| static_yield_stress | static_yield_stress | 1728 | 241 | -0.0437 | 0.399 | 0.618 | 0.8 |  |
| plastic_viscosity | plastic_viscosity | 1817 | 274 | -0.00469 | 0.405 | 0.648 | 0.8 |  |
| compressive_strength | compressive_strength | 47125 | 1634 | 0.533 | 0.449 | 0.686 | 0.8 |  |

Weak models give order-of-magnitude guidance only; treat the literature hits below as the primary evidence for those targets.

## Candidates

Sampled 8192 → feasible 0 at the requested thresholds; relaxed to per-target p_min {'static_yield_stress_at_rest@589.049s': 0.35, 'static_yield_stress': 0.28, 'plastic_viscosity': 0.28, 'compressive_strength': 0.42} and ad_max 1.0. Shortlist 6, refined 6. Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.

| # | composition | static_yield_stress_at_rest@589.049s | static_yield_stress | plastic_viscosity | compressive_strength | P_min | P_prod | AD | clinker_fraction | co2 | analogue |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.419; s/b 1.78; superplasticiser_pce 0.18% | 1.55e+03 [86.8, 1.07e+04] p=0.30 ⚠ | 393 [12.5, 5.77e+03] p=0.59 | 7.82 [0.516, 33.2] p=1.00 | 45.1 [26.3, 65.6] p=0.85 | 0.30 | 0.15 | 0.78 | 0.55 | 333 | 10.1016/j.conbuildmat.2011.06.064 (d=0.29) |
| 2* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.413; s/b 1.79; superplasticiser_pce 0.68%, vma_cellulose 0.06% | 1.68e+03 [112, 1.08e+04] p=0.30 ⚠ | 516 [17.5, 6.06e+03] p=0.63 | 7.75 [0.514, 33.3] p=1.00 | 41.1 [27, 68] p=0.84 | 0.30 | 0.16 | 0.79 | 0.55 | 339 | 10.1016/j.conbuildmat.2011.06.064 (d=0.29) |
| 3 | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.279; s/b 1.75; superplasticiser_pce 0.13% | 1.69e+03 [97.9, 1.39e+04] p=0.35 ⚠ | 400 [17.2, 7.05e+03] p=0.55 | 11.4 [0.788, 40.4] p=0.99 | 49.9 [42.7, 77.9] p=1.00 | 0.35 | 0.19 | 0.80 | 0.55 | 372 | 10.1016/j.conbuildmat.2011.06.064 (d=0.29) |
| 4 | portland_cement 0.61 / silica_fume 0.10 / limestone_powder 0.29; w/b 0.276; s/b 1.73; superplasticiser_pce 1.20% | 1.35e+03 [82.4, 1.86e+04] p=0.38 ⚠ | 278 [20, 1.07e+04] p=0.37 | 10.6 [0.725, 56.2] p=0.94 | 51.9 [43.3, 85.7] p=1.00 | 0.37 | 0.13 | 0.69 | 0.606 | 424 | 10.1016/j.cemconcomp.2025.106044 (d=0.27) |
| 5 | portland_cement 0.62 / silica_fume 0.15 / limestone_powder 0.23; w/b 0.403; s/b 0.87; superplasticiser_pce 1.03% | 1.04e+03 [56.6, 1.64e+04] p=0.36 ⚠ | 276 [10.7, 9.19e+03] p=0.39 | 4.35 [0.505, 37.5] p=0.99 | 47.1 [26.3, 80.7] p=0.85 | 0.36 | 0.12 | 0.74 | 0.624 | 506 | 10.1016/j.jobe.2026.115254 (d=0.07) |
| 6* | portland_cement 0.70 / limestone_powder 0.30; w/b 0.418; s/b 1.80; superplasticiser_pce 0.99% | 1.54e+03 [110, 1.12e+04] p=0.31 ⚠ | 631 [11.7, 7.04e+03] p=0.61 | 6.38 [0.41, 36.5] p=0.99 | 44.9 [22.8, 64.3] p=0.81 | 0.31 | 0.15 | 0.52 | 0.7 | 430 | 10.1016/j.cemconcomp.2025.106439 (d=0.01) |
| 7 | portland_cement 0.70 / silica_fume 0.15 / limestone_powder 0.15; w/b 0.306; s/b 1.65; superplasticiser_pce 0.79%, vma_cellulose 0.33% | 1.54e+03 [120, 1.52e+04] p=0.36 ⚠ | 524 [24.5, 8.94e+03] p=0.54 | 8.27 [0.685, 39.9] p=0.99 | 51.2 [34.4, 83.2] p=0.95 | 0.36 | 0.18 | 0.73 | 0.703 | 484 | 10.1016/j.addma.2021.102127 (d=0.05) |
| 8 | portland_cement 0.74 / limestone_powder 0.26; w/b 0.333; s/b 1.80; superplasticiser_pce 1.17% | 1.68e+03 [131, 1.54e+04] p=0.37 ⚠ | 513 [23.5, 9.17e+03] p=0.53 | 7.14 [0.596, 36.8] p=0.99 | 51 [34.3, 73.6] p=0.95 | 0.37 | 0.18 | 0.41 | 0.741 | 485 | 10.1016/j.conbuildmat.2024.139358 (d=0.06) |

\* refined by differential evolution. P_min = lowest per-target probability (the binding target); P_prod = product over targets. Units: static_yield_stress_at_rest@589.049s [Pa], static_yield_stress [Pa], plastic_viscosity [Pa.s], compressive_strength [MPa]

### Candidate 1 — portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.419; s/b 1.78; superplasticiser_pce 0.18%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5499999999999999
  },
  {
   "material_class": "silica_fume",
   "amount": 0.15
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.3
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0018105435177520255
  }
 ],
 "water_binder": 0.4193667318518748,
 "sand_binder": 1.7842912078620734,
 "conditions": {
  "curing_temp_C": 20,
  "curing_rh_pct": 95,
  "curing_regime": "moist curing",
  "is_3dcp": 1
 },
 "basis": "mass_frac_of_powder",
 "name": "cand_01",
 "schema_version": "1.0"
}
```
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L15S' (composition distance 0.29): opc 0.50 / limestone_powder 0.35 / silica_fume 0.15; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.40): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.15; pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3

### Candidate 2 — portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.413; s/b 1.79; superplasticiser_pce 0.68%, vma_cellulose 0.06%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.55
  },
  {
   "material_class": "silica_fume",
   "amount": 0.15
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.3
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.006794201365446538
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0005502514787097845
  }
 ],
 "water_binder": 0.41336106671729406,
 "sand_binder": 1.7934612625079331,
 "conditions": {
  "curing_temp_C": 20,
  "curing_rh_pct": 95,
  "curing_regime": "moist curing",
  "is_3dcp": 1
 },
 "basis": "mass_frac_of_powder",
 "name": "cand_02",
 "schema_version": "1.0"
}
```
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L15S' (composition distance 0.29): opc 0.50 / limestone_powder 0.35 / silica_fume 0.15; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.40): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.15; pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3

### Candidate 3 — portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.279; s/b 1.75; superplasticiser_pce 0.13%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.55
  },
  {
   "material_class": "silica_fume",
   "amount": 0.15
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.3
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0012585576148837982
  }
 ],
 "water_binder": 0.27916285484097897,
 "sand_binder": 1.7487517783418298,
 "conditions": {
  "curing_temp_C": 20,
  "curing_rh_pct": 95,
  "curing_regime": "moist curing",
  "is_3dcp": 1
 },
 "basis": "mass_frac_of_powder",
 "name": "cand_03",
 "schema_version": "1.0"
}
```
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L15S' (composition distance 0.29): opc 0.50 / limestone_powder 0.35 / silica_fume 0.15; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.40): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.15; pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3

### Candidate 4 — portland_cement 0.61 / silica_fume 0.10 / limestone_powder 0.29; w/b 0.276; s/b 1.73; superplasticiser_pce 1.20%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.605785924413552
  },
  {
   "material_class": "silica_fume",
   "amount": 0.10455061200385295
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.2896634635825952
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.01195194518038578
  }
 ],
 "water_binder": 0.2763571966998279,
 "sand_binder": 1.7322804575785995,
 "conditions": {
  "curing_temp_C": 20,
  "curing_rh_pct": 95,
  "curing_regime": "moist curing",
  "is_3dcp": 1
 },
 "basis": "mass_frac_of_powder",
 "name": "cand_04",
 "schema_version": "1.0"
}
```
- analogue 10.1016/j.cemconcomp.2025.106044 'Printable PE-ECC' (composition distance 0.27): opc 0.59 / limestone_powder 0.33 / silica_fume 0.08; w/b 0.26; sp_pce 0.20%; fibre 1.23 vol% → no matching measurements; deviations: pw_limestone_powder: analogue 0.327 vs candidate 0.29; filler_frac: analogue 0.327 vs candidate 0.29; pw_silica_fume: analogue 0.0839 vs candidate 0.105
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.35): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.29; filler_frac: analogue 0.35 vs candidate 0.29

### Candidate 5 — portland_cement 0.62 / silica_fume 0.15 / limestone_powder 0.23; w/b 0.403; s/b 0.87; superplasticiser_pce 1.03%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.6235295802820474
  },
  {
   "material_class": "silica_fume",
   "amount": 0.15
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.22647041971795262
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.010257107402819045
  }
 ],
 "water_binder": 0.4025883572269231,
 "sand_binder": 0.8715666357427836,
 "conditions": {
  "curing_temp_C": 20,
  "curing_rh_pct": 95,
  "curing_regime": "moist curing",
  "is_3dcp": 1
 },
 "basis": "mass_frac_of_powder",
 "name": "cand_05",
 "schema_version": "1.0"
}
```
- analogue 10.1016/j.jobe.2026.115254 'Paste 0% PPR' (composition distance 0.07): opc 0.62 / limestone_powder 0.22 / silica_fume 0.16; w/b 0.42; sp_other 0.44% → no matching measurements
- analogue 10.1016/j.conbuildmat.2011.06.064 '20L15S' (composition distance 0.16): opc 0.65 / limestone_powder 0.20 / silica_fume 0.15; w/b 0.50; s/b 3.00 → no matching measurements; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.226

## Published mixes near the target

| tier | score | DOI | mix | composition | measured |
|---|---|---|---|---|---|
| near | 0.28 | 10.1016/j.conbuildmat.2017.12.112 | Mixture A | opc 0.48 / fly_ash_f 0.48 / silica_fume 0.05; w/b 0.14; s/b 0.50 | compressive_strength=49.7@28d; plastic_viscosity=16.6; static_yield_stress=3.35e+03 |
| near | 0.28 | 10.1016/j.mtsust.2026.101398 | M0PE | ggbfs 0.60 / opc 0.30 / silica_fume 0.10; w/b 0.25; s/b 0.36; sp_pce 0.41%, vma 0.66% | compressive_strength=49.7@28d; plastic_viscosity=6.5; static_yield_stress=894 |
| near | 0.28 | 10.3390/buildings15193436 | 1% Microfibre + SF | ggbfs 0.50 / opc 0.45 / silica_fume 0.05; w/b 0.26; s/b 1.00; sp_pce 2.00% | compressive_strength=66.5@7d; compressive_strength=86.1@28d; plastic_viscosity=13.6; static_yield_stress=208 |
| near | 0.28 | 10.1016/j.rineng.2025.106680 | C4G6 | ggbfs 0.60 / opc 0.40; w/b 0.24; s/b 1.00; sp_pce 0.01% | compressive_strength=77.5@7d; compressive_strength=94.8@28d; plastic_viscosity=9.7; static_yield_stress=178 |
| near | 0.27 | 10.1016/j.conbuildmat.2025.144187 | RFA-50 | opc 0.55 / other_powder 0.45; w/b 0.40; s/b 1.50 | compressive_strength=30.2@3d; compressive_strength=44.6@28d; plastic_viscosity=68.2; static_yield_stress=1.76e+03 |
| near | 0.23 | 10.1016/j.addma.2023.103722 | 3DPC mixture | opc 1.00; w/b 0.35; s/b 1.00; sp_pce 0.05%, vma 0.06% | compressive_strength=25.6@1d; compressive_strength=47.2@7d; compressive_strength=55.7@28d; plastic_viscosity=1.12 |
| near | 0.23 | 10.1016/j.cemconcomp.2024.105446 | S-3D printed concrete (V70A8D60) / cast counterpart | fly_ash_f 0.50 / silica_fume 0.50; w/b 0.35; s/b 0.60; fibre 0.62 vol% | compressive_strength=42.8@28d; plastic_viscosity=7.65; static_yield_stress=859 |
| near | 0.23 | 10.1016/j.clema.2025.100358 | M-0 | opc 1.00; w/b 0.32; s/b 2.00; sp_pce 0.99%, vma 0.12% | compressive_strength=30@28d; plastic_viscosity=15; static_yield_stress=360 |
| near | 0.17 | 10.1016/j.mtsust.2026.101398 | M0.5PE | ggbfs 0.60 / opc 0.30 / silica_fume 0.10; w/b 0.25; s/b 0.36; sp_pce 0.50%, vma 0.66%; fibre 0.66 vol% | compressive_strength=50.3@28d; plastic_viscosity=9.1; static_yield_stress=1.03e+03 |
| near | 0.17 | 10.1016/j.rineng.2025.106680 | C3G7N1 | ggbfs 0.70 / opc 0.30; w/b 0.24; s/b 1.00; sp_pce 0.01% | compressive_strength=89.9@7d; compressive_strength=105@28d; plastic_viscosity=9.1; static_yield_stress=78.6 |
| near | 0.17 | 10.3390/buildings15193436 | 0.75% Microfibre + SF | ggbfs 0.50 / opc 0.45 / silica_fume 0.05; w/b 0.26; s/b 1.00; sp_pce 2.00% | compressive_strength=76.4@7d; compressive_strength=98@28d; plastic_viscosity=9.67; static_yield_stress=67.9 |
| near | 0.14 | 10.1016/j.clema.2025.100358 | M-10 | opc 0.90 / ash_other 0.10; w/b 0.32; s/b 2.00; sp_pce 0.99%, vma 0.12% | compressive_strength=30@28d; plastic_viscosity=12.5; static_yield_stress=400 |
| near | 0.10 | 10.1016/j.mtsust.2026.101398 | M0.75PE | ggbfs 0.60 / opc 0.30 / silica_fume 0.10; w/b 0.25; s/b 0.36; sp_pce 0.54%, vma 0.66%; fibre 0.98 vol% | compressive_strength=47.8@28d; plastic_viscosity=10.6; static_yield_stress=1.29e+03 |
| near | 0.10 | 10.1016/j.rineng.2025.106680 | C4G6N1 | ggbfs 0.60 / opc 0.40; w/b 0.24; s/b 1.00; sp_pce 0.01% | compressive_strength=84.1@7d; compressive_strength=104@28d; plastic_viscosity=6.4; static_yield_stress=45.1 |
| near | 0.10 | 10.3390/buildings15193436 | 0.5% Microfibre + SF | ggbfs 0.50 / opc 0.45 / silica_fume 0.05; w/b 0.26; s/b 1.00; sp_pce 2.00% | compressive_strength=82.3@7d; compressive_strength=109@28d; plastic_viscosity=3.75; static_yield_stress=9.35 |

## Provenance

Cost table: C:\Users\User\3D Printing Concrete Prediction\configs\unit_cost_default.yaml (hash c7dba05d5c80, DEFAULT PLACEHOLDER); CO2 table: C:\Users\User\3D Printing Concrete Prediction\configs\embodied_carbon_default.yaml (hash c7e6390d1a13, DEFAULT PLACEHOLDER).
**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**

Diagnostics: {"n_sampled": 8192, "n_feasible": 0, "t_stage1_s": 11.5, "relaxation": [{"threshold_scale": 0.9, "ad_max": 1.0, "n_feasible": 0}, {"threshold_scale": 0.8, "ad_max": 1.0, "n_feasible": 2}, {"threshold_scale": 0.7, "ad_max": 1.0, "n_feasible": 638}], "threshold_scale_used": 0.7, "ad_max_used": 1.0, "p_min_used": {"static_yield_stress_at_rest@589.049s": 0.35, "static_yield_stress": 0.28, "plastic_viscosity": 0.28, "compressive_strength": 0.42}, "n_shortlist": 6, "t_stage2_s": 37.7, "n_final": 12, "evaluator_calls": 98, "t_total_s": 50.0, "weak_models": ["structuration_rate_athix", "static_yield_stress_at_rest"]}
