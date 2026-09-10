# Design report — printable_mortar_flowcurve

Generated 2026-09-09T15:08:11+00:00 · pmpredict 0.1.0

## Request

| target | kind | lo | hi | goal | conditions |
|---|---|---|---|---|---|
| compressive_strength | ge | 35 |  |  | age_d=28, comparability_group=comp_cube50 |
| shear_stress_at_rate | range | 200 | 800 |  | shear_rate_1s=50 |
| shear_stress_at_rate | le |  | 2e+03 |  | shear_rate_1s=150 |
| static_yield_stress_at_rest | ge | 1.5e+03 |  |  | rest_time_s=1200 |

Space: mortar, w/b (0.28, 0.45), s/b (0.8, 1.8), binder ['portland_cement', 'silica_fume', 'limestone_powder', 'fly_ash_class_F'], admixtures ['superplasticiser_pce', 'vma_cellulose'], max binder components 3.
Objectives: ['clinker_fraction min']. Risk: p_min 0.6, ad_max 1.0, combine product.

## Models used

| target | model | n | papers | R² | R²(log) | Spearman | cov80 | weak |
|---|---|---|---|---|---|---|---|---|
| compressive_strength | compressive_strength | 11508 | 948 | 0.519 | 0.371 | 0.667 | 0.8 |  |
| shear_stress_at_rate@50/s | derived(dynamic_yield_stress + plastic_viscosity) | 1192 | 147 |  | 0.193 | 0.39 | 0.8 |  |
| shear_stress_at_rate@150/s | derived(dynamic_yield_stress + plastic_viscosity) | 1192 | 147 |  | 0.193 | 0.39 | 0.8 |  |
| static_yield_stress_at_rest@1200s | derived(static_yield_stress + structuration_rate_athix) | 245 | 36 |  | -0.225 | 0.13 | 0.8 | **yes** |

Weak models give order-of-magnitude guidance only; treat the literature hits below as the primary evidence for those targets.

## Candidates

Sampled 8192 → feasible 7134 at the requested thresholds. Shortlist 6, refined 6. Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.

| # | composition | compressive_strength | shear_stress_at_rate@50/s | shear_stress_at_rate@150/s | static_yield_stress_at_rest@1200s | P_min | P_prod | AD | clinker_fraction | analogue |
|---|---|---|---|---|---|---|---|---|---|---|
| 1* | portland_cement 0.50 / limestone_powder 0.12 / fly_ash_class_F 0.38; w/b 0.293; s/b 1.07; superplasticiser_pce 0.51%, vma_cellulose 0.04% | 41.5 [26, 81.6] p=0.70 | 479 [75.8, 1.06e+03] p=0.57 | 857 [162, 2.54e+03] p=0.81 | 669 [128, 1.01e+04] p=0.46 ⚠ | 0.46 | 0.15 | 0.56 | 0.5 | 10.3390/ma18225123 (d=0.24) |
| 2* | portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.287; s/b 1.12; superplasticiser_pce 0.21%, vma_cellulose 0.02% | 56.9 [35.7, 99.9] p=0.91 | 469 [82.6, 1.49e+03] p=0.48 | 914 [170, 4.06e+03] p=0.67 | 613 [88.9, 1.03e+04] p=0.45 ⚠ | 0.45 | 0.13 | 0.49 | 0.5 | 10.1016/j.conbuildmat.2010.04.018 (d=0.49) |
| 3* | portland_cement 0.50 / limestone_powder 0.20 / fly_ash_class_F 0.30; w/b 0.316; s/b 1.21; superplasticiser_pce 0.11%, vma_cellulose 0.07% | 39.7 [23.2, 73] p=0.64 | 449 [73.6, 941] p=0.62 | 859 [154, 2.34e+03] p=0.84 | 633 [120, 7.5e+03] p=0.44 ⚠ | 0.44 | 0.15 | 0.48 | 0.5 | 10.3390/ma18225123 (d=0.34) |
| 4 | portland_cement 0.50 / limestone_powder 0.11 / fly_ash_class_F 0.39; w/b 0.304; s/b 1.67; superplasticiser_pce 0.66%, vma_cellulose 0.02% | 41.2 [23.4, 74.1] p=0.67 | 515 [81.7, 989] p=0.60 | 1.45e+03 [155, 1.94e+03] p=0.93 | 647 [114, 8.97e+03] p=0.45 ⚠ | 0.45 | 0.17 | 0.51 | 0.5 | 10.1016/j.cemconcomp.2021.104174 (d=0.25) |
| 5* | portland_cement 0.50 / limestone_powder 0.26 / fly_ash_class_F 0.24; w/b 0.285; s/b 1.27; superplasticiser_pce 1.04% | 43.3 [20.7, 93.6] p=0.68 | 355 [53.5, 804] p=0.64 | 849 [108, 1.87e+03] p=0.93 | 588 [66.9, 1.2e+04] p=0.46 ⚠ | 0.46 | 0.19 | 0.57 | 0.5 | 10.1016/j.powtec.2016.05.054 (d=0.52) |
| 6* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.282; s/b 1.43; superplasticiser_pce 0.10% | 57.2 [30.5, 92.9] p=0.86 | 482 [68.3, 1.1e+03] p=0.56 | 1.11e+03 [118, 2.96e+03] p=0.73 | 643 [30.9, 2.82e+04] p=0.48 ⚠ | 0.48 | 0.17 | 0.80 | 0.55 | 10.1016/j.conbuildmat.2011.06.064 (d=0.32) |
| 7* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.331; s/b 1.35; superplasticiser_pce 0.46% | 51.9 [34.9, 87.3] p=0.90 | 471 [63.8, 1.03e+03] p=0.58 | 1.11e+03 [113, 2.57e+03] p=0.78 | 536 [32.1, 2.16e+04] p=0.48 ⚠ | 0.48 | 0.19 | 0.80 | 0.55 | 10.1016/j.conbuildmat.2011.06.064 (d=0.32) |
| 8 | portland_cement 0.57 / limestone_powder 0.29 / fly_ash_class_F 0.14; w/b 0.289; s/b 1.07; superplasticiser_pce 1.41% | 46.7 [19.8, 96] p=0.71 | 289 [48.3, 919] p=0.53 | 557 [104, 2.38e+03] p=0.84 | 691 [65.2, 1.97e+04] p=0.48 ⚠ | 0.48 | 0.15 | 0.60 | 0.57 | 10.1016/j.powtec.2016.05.054 (d=0.30) |

\* refined by differential evolution. P_min = lowest per-target probability (the binding target); P_prod = product over targets. Units: compressive_strength [MPa], shear_stress_at_rate@50/s [Pa], shear_stress_at_rate@150/s [Pa], static_yield_stress_at_rest@1200s [Pa]

### Candidate 1 — portland_cement 0.50 / limestone_powder 0.12 / fly_ash_class_F 0.38; w/b 0.293; s/b 1.07; superplasticiser_pce 0.51%, vma_cellulose 0.04%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.1231166112073542
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.37688338879264593
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0050951085418129705
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00039426171252251064
  }
 ],
 "water_binder": 0.2927768220897295,
 "sand_binder": 1.0665253211112402,
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
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.24): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_fly_ash_f: analogue 0.3 vs candidate 0.377; pw_limestone_powder: analogue 0.15 vs candidate 0.123; filler_frac: analogue 0.15 vs candidate 0.123
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.24): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_fly_ash_f: analogue 0.3 vs candidate 0.377; pw_limestone_powder: analogue 0.15 vs candidate 0.123; filler_frac: analogue 0.15 vs candidate 0.123

### Candidate 2 — portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.287; s/b 1.12; superplasticiser_pce 0.21%, vma_cellulose 0.02%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5
  },
  {
   "material_class": "silica_fume",
   "amount": 0.124329253367821
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.37567074663217914
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0020548980726696076
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00018489967528055988
  }
 ],
 "water_binder": 0.28653509857895304,
 "sand_binder": 1.1233116601666686,
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
- analogue 10.1016/j.conbuildmat.2010.04.018 'A3' (composition distance 0.49): opc 0.70 / fly_ash_f 0.20 / silica_fume 0.10; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.2 vs candidate 0.376; cement_share: analogue 0.7 vs candidate 0.5; pw_opc: analogue 0.7 vs candidate 0.5
- analogue 10.3389/fmats.2021.712551 'M9' (composition distance 0.49): opc 0.48 / fly_ash_f 0.30 / ggbfs 0.15 / silica_fume 0.06; w/b 0.30; sp_pce 0.50% → compressive_strength=38.2 MPa @3 d; compressive_strength=65.8 MPa @7 d; compressive_strength=93.9 MPa @28 d; compressive_strength=107 MPa @56 d; deviations: pw_silica_fume: analogue 0.0606 vs candidate 0.124; pw_ggbfs: analogue 0.152 vs candidate 0; pw_fly_ash_f: analogue 0.303 vs candidate 0.376

### Candidate 3 — portland_cement 0.50 / limestone_powder 0.20 / fly_ash_class_F 0.30; w/b 0.316; s/b 1.21; superplasticiser_pce 0.11%, vma_cellulose 0.07%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.20151232255359378
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.29848767744640636
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.001111348960467233
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0007112082259226703
  }
 ],
 "water_binder": 0.31556966587937685,
 "sand_binder": 1.2065441027027977,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.34): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.202; filler_frac: analogue 0.15 vs candidate 0.202
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.34): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.202; filler_frac: analogue 0.15 vs candidate 0.202

### Candidate 4 — portland_cement 0.50 / limestone_powder 0.11 / fly_ash_class_F 0.39; w/b 0.304; s/b 1.67; superplasticiser_pce 0.66%, vma_cellulose 0.02%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.11015477394685148
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.38984522605314853
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.006554066934908243
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00020121869793974102
  }
 ],
 "water_binder": 0.30418429026380184,
 "sand_binder": 1.674644486233592,
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
- analogue 10.1016/j.cemconcomp.2021.104174 'LF40' (composition distance 0.25): opc 0.60 / fly_ash_f 0.30 / limestone_powder 0.10 → no matching measurements; deviations: pw_fly_ash_f: analogue 0.3 vs candidate 0.39; cement_share: analogue 0.6 vs candidate 0.5
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.31): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.11; pw_fly_ash_f: analogue 0.3 vs candidate 0.39; filler_frac: analogue 0.15 vs candidate 0.11

### Candidate 5 — portland_cement 0.50 / limestone_powder 0.26 / fly_ash_class_F 0.24; w/b 0.285; s/b 1.27; superplasticiser_pce 1.04%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.5
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.2637142683844658
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.2362857316155341
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.010422702465357545
  }
 ],
 "water_binder": 0.28487118764592606,
 "sand_binder": 1.2683058424737468,
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
- analogue 10.1016/j.powtec.2016.05.054 'Sample L3 (steam curing)' (composition distance 0.52): opc 0.60 / limestone_powder 0.30 / ggbfs 0.10; w/b 0.40 → no matching measurements; deviations: pw_fly_ash_f: analogue 0 vs candidate 0.236; pw_limestone_powder: analogue 0.3 vs candidate 0.264; cement_share: analogue 0.6 vs candidate 0.5
- analogue 10.1016/j.powtec.2016.05.054 'Sample L3 (standard curing)' (composition distance 0.52): opc 0.60 / limestone_powder 0.30 / ggbfs 0.10; w/b 0.40 → no matching measurements; deviations: pw_fly_ash_f: analogue 0 vs candidate 0.236; pw_limestone_powder: analogue 0.3 vs candidate 0.264; cement_share: analogue 0.6 vs candidate 0.5

## Published mixes near the target

| tier | score | DOI | mix | composition | measured |
|---|---|---|---|---|---|
| near | 0.05 | 10.1016/j.addma.2020.101069 | Plain (fibre-free) mix | opc 1.00; w/b 0.31; s/b 1.20 | compressive_strength=50.8@28d |
| near | 0.05 | 10.1016/j.cemconcomp.2021.104060 | M5 | ggbfs 0.50 / fly_ash_f 0.50; w/b 0.36; s/b 1.50; retarder 0.50%; activator 0.10/b | compressive_strength=52.6@3d; static_yield_stress_at_rest@1200s=7.7e+03 |
| near | 0.05 | 10.1016/j.cemconcomp.2021.104158 | N2 | opc 1.00; w/b 0.35; s/b 1.00; vma 0.20% | shear_stress_at_rate@50/s=278 |
| near | 0.05 | 10.1016/j.cemconcomp.2023.104960 | Mixture A (mortar) | csa 1.00; w/b 0.35; s/b 1.20; retarder 1.99% | shear_stress_at_rate@50/s=401 |
| near | 0.05 | 10.1016/j.cemconcomp.2024.105641 | LC3-ECC | fly_ash_f 0.55 / opc 0.25 / calcined_clay 0.14 / limestone_powder 0.07; w/b 0.25; s/b 0.36; sp_pce 0.54%, vma 0.15%; fibre 2.25 vol% | compressive_strength=45.3@28d |
| near | 0.05 | 10.1016/j.conbuildmat.2018.12.061 | S/C=0.6 | opc 0.98 / silica_fume 0.02; w/b 0.34; s/b 0.59; sp_pce 0.25%, vma 0.01% | shear_stress_at_rate@50/s=465 |
| near | 0.03 | 10.1016/j.addma.2020.101069 | 1% E6-glass fibre mix | opc 1.00; w/b 0.33; s/b 1.20; fibre 0.73 vol% | compressive_strength=51.9@28d |
| near | 0.03 | 10.1016/j.cemconcomp.2021.104158 | N3 | opc 1.00; w/b 0.35; s/b 1.00; vma 0.30% | shear_stress_at_rate@50/s=358 |
| near | 0.03 | 10.1016/j.cemconcomp.2023.104960 | Mixture B0 (mortar) | opc 1.00; w/b 0.35; s/b 1.20; sp_pce 0.60% | shear_stress_at_rate@50/s=290 |
| near | 0.03 | 10.1016/j.conbuildmat.2018.12.061 | S/C=0.8 | opc 0.98 / silica_fume 0.02; w/b 0.34; s/b 0.78; sp_pce 0.25%, vma 0.01% | shear_stress_at_rate@50/s=460 |
| near | 0.02 | 10.1016/j.cemconcomp.2021.104158 | M3 | opc 0.84 / silica_fume 0.16; w/b 0.35; s/b 1.00 | shear_stress_at_rate@50/s=269 |
| near | 0.02 | 10.1016/j.cemconcomp.2023.104960 | Mixture B2 (mortar) | opc 0.98 / lime 0.02; w/b 0.35; s/b 1.20; sp_pce 0.59% | shear_stress_at_rate@50/s=332 |

## Provenance

Cost table: C:\Users\User\3D Printing Concrete Prediction\configs\unit_cost_default.yaml (hash c7dba05d5c80, DEFAULT PLACEHOLDER); CO2 table: C:\Users\User\3D Printing Concrete Prediction\configs\embodied_carbon_default.yaml (hash c7e6390d1a13, DEFAULT PLACEHOLDER).
**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**

Diagnostics: {"n_sampled": 8192, "n_feasible": 7134, "t_stage1_s": 10.1, "n_shortlist": 6, "t_stage2_s": 25.0, "n_final": 12, "evaluator_calls": 77, "t_total_s": 79.1, "weak_models": ["structuration_rate_athix", "static_yield_stress_at_rest"]}
