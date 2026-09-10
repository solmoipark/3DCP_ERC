# Design report — 3dcp_printable_mortar

Generated 2026-09-09T09:07:26+00:00 · pmpredict 0.1.0

## Request

| target | kind | lo | hi | goal | conditions |
|---|---|---|---|---|---|
| compressive_strength | ge | 40 |  |  | age_d=28, comparability_group=comp_cube50 |
| static_yield_stress | range | 1e+03 | 4e+03 |  | rest_time_s=0 |
| flow_table_spread | range | 140 | 200 |  |  |

Space: mortar, w/b (0.28, 0.45), s/b (0.8, 1.8), binder ['portland_cement', 'silica_fume', 'limestone_powder', 'fly_ash_class_F'], admixtures ['superplasticiser_pce', 'vma_cellulose'], max binder components 3.
Objectives: ['clinker_fraction min', 'co2 min']. Risk: p_min 0.7, ad_max 1.0, combine product.

## Models used

| target | model | n | papers | R² | R²(log) | Spearman | cov80 | weak |
|---|---|---|---|---|---|---|---|---|
| compressive_strength | compressive_strength | 11508 | 948 | 0.519 | 0.371 | 0.667 | 0.8 |  |
| static_yield_stress | static_yield_stress | 707 | 82 | -0.0518 | 0.165 | 0.403 | 0.8 |  |
| flow_table_spread | flow_table_spread | 1058 | 169 | -0.0607 | -0.0607 | 0.0947 | 0.8 | **yes** |

Weak models give order-of-magnitude guidance only; treat the literature hits below as the primary evidence for those targets.

## Candidates

Sampled 16384 → feasible 1 at the requested thresholds; relaxed to per-target p_min {'compressive_strength': 0.63, 'static_yield_stress': 0.27, 'flow_table_spread': 0.315} and ad_max 1.0. Shortlist 8, refined 8. Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.

| # | composition | compressive_strength | static_yield_stress | flow_table_spread | P_min | P_prod | AD | clinker_fraction | co2 | analogue |
|---|---|---|---|---|---|---|---|---|---|---|
| 1* | portland_cement 0.50 / silica_fume 0.13 / fly_ash_class_F 0.37; w/b 0.345; s/b 1.76; superplasticiser_pce 0.25%, vma_cellulose 0.09% | 50.3 [30.7, 77.7] p=0.75 | 170 [3.84, 5.37e+03] p=0.25 | 181 [121, 252] p=0.45 ⚠ | 0.25 | 0.08 | 0.46 | 0.5 | 315 | 10.1016/j.conbuildmat.2010.04.018 (d=0.50) |
| 2* | portland_cement 0.50 / limestone_powder 0.18 / fly_ash_class_F 0.32; w/b 0.315; s/b 1.79; superplasticiser_pce 0.47%, vma_cellulose 0.04% | 44.8 [21.4, 69.6] p=0.60 | 146 [5.81, 5.95e+03] p=0.23 | 182 [124, 251] p=0.46 ⚠ | 0.23 | 0.06 | 0.47 | 0.5 | 326 | 10.3390/ma18225123 (d=0.21) |
| 3* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.346; s/b 1.80; superplasticiser_pce 0.21%, vma_cellulose 0.06% | 44.4 [30.4, 81.6] p=0.66 | 145 [3.13, 6.43e+03] p=0.21 | 187 [123, 250] p=0.43 ⚠ | 0.21 | 0.06 | 0.78 | 0.55 | 350 | 10.1016/j.conbuildmat.2011.06.064 (d=0.33) |
| 4 | portland_cement 0.61 / limestone_powder 0.25 / fly_ash_class_F 0.15; w/b 0.282; s/b 0.88; superplasticiser_pce 0.24%, vma_cellulose 0.03% | 45.9 [23.1, 85.5] p=0.63 | 198 [3.99, 4.61e+03] p=0.27 | 185 [125, 255] p=0.44 ⚠ | 0.27 | 0.08 | 0.50 | 0.609 | 545 | 10.1016/j.cemconcomp.2024.105869 (d=0.33) |
| 5 | portland_cement 0.71 / silica_fume 0.07 / limestone_powder 0.23; w/b 0.412; s/b 1.65; superplasticiser_pce 0.24%, vma_cellulose 0.01% | 42 [37.7, 64.5] p=0.73 | 168 [1.67, 4.18e+03] p=0.28 | 179 [126, 251] p=0.47 ⚠ | 0.28 | 0.10 | 0.44 | 0.708 | 444 | 10.1016/j.conbuildmat.2011.06.064 (d=0.21) |
| 6* | portland_cement 0.70 / limestone_powder 0.30; w/b 0.325; s/b 1.79; superplasticiser_pce 0.29%, vma_cellulose 0.09% | 43.7 [25.4, 80.6] p=0.60 | 198 [3.4, 5.33e+03] p=0.25 | 185 [124, 247] p=0.45 ⚠ | 0.25 | 0.07 | 0.50 | 0.7 | 454 | 10.1016/j.cemconcomp.2025.106439 (d=0.10) |
| 7 | portland_cement 0.82 / limestone_powder 0.18; w/b 0.391; s/b 1.77; superplasticiser_pce 1.00%, vma_cellulose 0.04% | 46.8 [29.3, 76.6] p=0.69 | 153 [1.79, 4.48e+03] p=0.27 | 185 [124, 248] p=0.45 ⚠ | 0.27 | 0.08 | 0.34 | 0.821 | 514 | 10.1016/j.jclepro.2017.04.161 (d=0.10) |
| 8 | portland_cement 0.69 / silica_fume 0.07 / limestone_powder 0.25; w/b 0.292; s/b 0.85; superplasticiser_pce 0.51%, vma_cellulose 0.04% | 69.3 [39.4, 93.7] p=0.90 | 216 [3.82, 4.27e+03] p=0.29 | 188 [124, 268] p=0.41 ⚠ | 0.29 | 0.10 | 0.55 | 0.685 | 620 | 10.1016/j.conbuildmat.2011.06.064 (d=0.33) |
| 9 | portland_cement 0.69 / silica_fume 0.13 / fly_ash_class_F 0.18; w/b 0.292; s/b 0.93; superplasticiser_pce 0.24%, vma_cellulose 0.09% | 65.3 [33.6, 99.3] p=0.85 | 212 [3.78, 4.61e+03] p=0.27 | 182 [125, 259] p=0.45 ⚠ | 0.27 | 0.10 | 0.42 | 0.694 | 594 | 10.1016/j.conbuildmat.2010.04.018 (d=0.12) |
| 10 | portland_cement 0.80 / silica_fume 0.07 / limestone_powder 0.13; w/b 0.373; s/b 1.62; superplasticiser_pce 0.50%, vma_cellulose 0.30% | 49.7 [38.7, 79] p=0.87 | 204 [1.49, 4.68e+03] p=0.27 | 183 [124, 248] p=0.46 ⚠ | 0.27 | 0.11 | 0.54 | 0.8 | 524 | 10.1016/j.conbuildmat.2011.06.064 (d=0.60) |

\* refined by differential evolution. P_min = lowest per-target probability (the binding target); P_prod = product over targets. Units: compressive_strength [MPa], static_yield_stress [Pa], flow_table_spread [mm]

### Candidate 1 — portland_cement 0.50 / silica_fume 0.13 / fly_ash_class_F 0.37; w/b 0.345; s/b 1.76; superplasticiser_pce 0.25%, vma_cellulose 0.09%

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
   "amount": 0.12718496998858936
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.37281503001141064
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.002538122999955095
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0008672102940681305
  }
 ],
 "water_binder": 0.3449686025006181,
 "sand_binder": 1.7560051499596712,
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
- analogue 10.1016/j.conbuildmat.2010.04.018 'A3' (composition distance 0.50): opc 0.70 / fly_ash_f 0.20 / silica_fume 0.10; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.2 vs candidate 0.373; cement_share: analogue 0.7 vs candidate 0.5; pw_silica_fume: analogue 0.1 vs candidate 0.127
- analogue 10.1016/j.conbuildmat.2010.04.018 'A4' (composition distance 0.50): opc 0.70 / fly_ash_f 0.17 / silica_fume 0.13; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.171 vs candidate 0.373; cement_share: analogue 0.7 vs candidate 0.5; pw_opc: analogue 0.7 vs candidate 0.5

### Candidate 2 — portland_cement 0.50 / limestone_powder 0.18 / fly_ash_class_F 0.32; w/b 0.315; s/b 1.79; superplasticiser_pce 0.47%, vma_cellulose 0.04%

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
   "amount": 0.17849685201208126
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.32150314798791874
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.004705701946146812
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0003777798376787081
  }
 ],
 "water_binder": 0.31531193903597277,
 "sand_binder": 1.7884346937934685,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.21): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.178; filler_frac: analogue 0.15 vs candidate 0.178
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.21): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.178; filler_frac: analogue 0.15 vs candidate 0.178

### Candidate 3 — portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.346; s/b 1.80; superplasticiser_pce 0.21%, vma_cellulose 0.06%

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
   "amount": 0.0021376051957745367
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0005695829886038039
  }
 ],
 "water_binder": 0.3457976146799294,
 "sand_binder": 1.7988746713648358,
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
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L15S' (composition distance 0.33): opc 0.50 / limestone_powder 0.35 / silica_fume 0.15; w/b 0.50; s/b 3.00 → flow_table_spread=132 mm; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.46): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → flow_table_spread=135 mm; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.15; pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3

### Candidate 4 — portland_cement 0.61 / limestone_powder 0.25 / fly_ash_class_F 0.15; w/b 0.282; s/b 0.88; superplasticiser_pce 0.24%, vma_cellulose 0.03%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.6092453704215586
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.2451350535266101
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.14561957605183123
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0024329072363833797
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0003456863228367588
  }
 ],
 "water_binder": 0.28245332933031025,
 "sand_binder": 0.8801050122827292,
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
- analogue 10.1016/j.cemconcomp.2024.105869 'F10L20 mortar (C)[FGfam]' (composition distance 0.33): opc 0.70 / limestone_powder 0.20 / fly_ash_f 0.10; w/b 0.32; sp_pce 0.25% → no matching measurements; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.245; filler_frac: analogue 0.2 vs candidate 0.245; cement_share: analogue 0.7 vs candidate 0.609
- analogue 10.1016/j.cemconcomp.2024.105869 'F10L20 (C)[FGfam]' (composition distance 0.33): opc 0.70 / limestone_powder 0.20 / fly_ash_f 0.10; w/b 0.32; sp_pce 0.25% → no matching measurements; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.245; filler_frac: analogue 0.2 vs candidate 0.245; cement_share: analogue 0.7 vs candidate 0.609

### Candidate 5 — portland_cement 0.71 / silica_fume 0.07 / limestone_powder 0.23; w/b 0.412; s/b 1.65; superplasticiser_pce 0.24%, vma_cellulose 0.01%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.7082780009911706
  },
  {
   "material_class": "silica_fume",
   "amount": 0.06605101705839242
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.22567098195043703
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0024188944863068277
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00012320295749917507
  }
 ],
 "water_binder": 0.4120080649573356,
 "sand_binder": 1.6538530180230737,
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
- analogue 10.1016/j.conbuildmat.2011.06.064 '20L5S' (composition distance 0.21): opc 0.75 / limestone_powder 0.20 / silica_fume 0.05; w/b 0.50; s/b 3.00 → flow_table_spread=136 mm; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.226; pw_silica_fume: analogue 0.05 vs candidate 0.0661; filler_frac: analogue 0.2 vs candidate 0.226
- analogue 10.1016/j.conbuildmat.2011.06.064 '20L10S' (composition distance 0.28): opc 0.70 / limestone_powder 0.20 / silica_fume 0.10; w/b 0.50; s/b 3.00 → flow_table_spread=132 mm; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.0661; pw_limestone_powder: analogue 0.2 vs candidate 0.226; filler_frac: analogue 0.2 vs candidate 0.226

## Published mixes near the target

| tier | score | DOI | mix | composition | measured |
|---|---|---|---|---|---|
| near | 0.83 | 10.3390/buildings13061476 | M1 | opc 1.00; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | compressive_strength=24.8@1d; compressive_strength=42.9@7d; compressive_strength=48.6@28d; flow_table_spread=168 |
| near | 0.34 | 10.3390/buildings13061476 | M4 | glass_powder 0.60 / opc 0.40; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | compressive_strength=6.8@1d; compressive_strength=18.6@7d; compressive_strength=25.3@28d; flow_table_spread=194 |
| near | 0.30 | 10.3390/buildings15193436 | 1% Microfibre + SF | ggbfs 0.50 / opc 0.45 / silica_fume 0.05; w/b 0.26; s/b 1.00; sp_pce 2.00% | compressive_strength=66.5@7d; compressive_strength=86.1@28d; flow_table_spread=202; static_yield_stress=208 |
| near | 0.25 | 10.1016/j.conbuildmat.2017.12.112 | Mixture A | opc 0.48 / fly_ash_f 0.48 / silica_fume 0.05; w/b 0.14; s/b 0.50 | compressive_strength=49.7@28d; static_yield_stress=3.35e+03 |
| near | 0.25 | 10.1016/j.conbuildmat.2023.133561 | M2 | opc 0.50 / ggbfs 0.50; w/b 0.37; s/b 1.16 | compressive_strength=53.4@28d; compressive_strength=34.8@33d; flow_table_spread=176 |
| near | 0.25 | 10.1016/j.conbuildmat.2026.147445 | MK0 | fly_ash_f 0.60 / ggbfs 0.40; w/b 0.09; s/b 0.60; sp_pce 1.00%; fibre 2.17 vol%; activator 0.42/b | compressive_strength=66.6@28d; flow_table_spread=173 |
| near | 0.25 | 10.1016/j.cscm.2025.e05426 | Control (OPC) | opc 1.00; w/b 0.45; s/b 2.75 | compressive_strength=11.4@3d; compressive_strength=37.6@7d; compressive_strength=43.9@28d; flow_table_spread=186 |
| near | 0.25 | 10.1016/j.nxmate.2025.101552 | 0% BP | opc 1.00; w/b 0.42; s/b 1.48 | compressive_strength=30.1@7d; compressive_strength=46.3@14d; compressive_strength=52.4@28d; flow_table_spread=160 |
| near | 0.25 | 10.1016/j.pes.2026.100274 | UHPC-CC20 | opc 0.80 / calcined_clay 0.20; w/b 0.19; s/b 0.75; sp_pce 0.67%; fibre 1.49 vol% | compressive_strength=121@28d; flow_table_spread=183 |
| near | 0.25 | 10.1016/j.susmat.2018.05.001 | C | opc 1.00; w/b 0.48; s/b 2.75; sp_pce 0.53% | compressive_strength=31.4@3d; compressive_strength=41.9@7d; compressive_strength=53.1@28d; compressive_strength=58.8@90d |
| near | 0.15 | 10.1016/j.conbuildmat.2026.147445 | MK30 | ggbfs 0.40 / fly_ash_f 0.30 / metakaolin 0.30; w/b 0.09; s/b 0.60; sp_pce 1.00%; fibre 2.14 vol%; activator 0.42/b | compressive_strength=92.9@28d; flow_table_spread=141 |
| near | 0.15 | 10.1016/j.nxmate.2025.101552 | 0.2% BP | opc 1.00; w/b 0.42; s/b 1.48 | compressive_strength=35.9@7d; compressive_strength=50.7@14d; compressive_strength=61.8@28d; flow_table_spread=170 |
| near | 0.11 | 10.3390/buildings13061476 | M2 | opc 0.80 / glass_powder 0.20; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | flow_table_spread=173; static_yield_stress=3.7e+03; static_yield_stress=7.09e+03; static_yield_stress=9.99e+03 |
| near | 0.09 | 10.1016/j.conbuildmat.2026.147445 | MK10B2 | fly_ash_f 0.50 / ggbfs 0.40 / metakaolin 0.10 / other_powder 0.01; w/b 0.09; s/b 0.60; sp_pce 0.99%; fibre 2.19 vol%; activator 0.42/b | compressive_strength=106@28d; flow_table_spread=155 |
| near | 0.09 | 10.1016/j.nxmate.2025.101552 | 0.6% BP | opc 0.99 / other_powder 0.01; w/b 0.42; s/b 1.47 | compressive_strength=21.7@7d; compressive_strength=42@14d; compressive_strength=49.5@28d; flow_table_spread=185 |

## Provenance

Cost table: C:\Users\User\3D Printing Concrete Prediction\configs\unit_cost_default.yaml (hash c7dba05d5c80, DEFAULT PLACEHOLDER); CO2 table: C:\Users\User\3D Printing Concrete Prediction\configs\embodied_carbon_default.yaml (hash c7e6390d1a13, DEFAULT PLACEHOLDER).
**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**

Diagnostics: {"n_sampled": 16384, "n_feasible": 1, "t_stage1_s": 16.9, "relaxation": [{"threshold_scale": 0.9, "ad_max": 1.0, "n_feasible": 212}], "threshold_scale_used": 0.9, "ad_max_used": 1.0, "p_min_used": {"compressive_strength": 0.63, "static_yield_stress": 0.27, "flow_table_spread": 0.315}, "n_shortlist": 8, "t_stage2_s": 41.9, "n_final": 16, "evaluator_calls": 170, "t_total_s": 59.0, "weak_models": ["flow_table_spread"]}
