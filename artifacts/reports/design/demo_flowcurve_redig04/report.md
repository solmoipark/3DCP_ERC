# Design report — printable_mortar_flowcurve

Generated 2026-09-10T04:07:39+00:00 · pmpredict 0.1.0

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
| compressive_strength | compressive_strength | 44383 | 1325 | 0.513 | 0.422 | 0.688 | 0.8 |  |
| shear_stress_at_rate@50/s | derived(dynamic_yield_stress + plastic_viscosity) | 1241 | 157 |  | 0.16 | 0.386 | 0.8 |  |
| shear_stress_at_rate@150/s | derived(dynamic_yield_stress + plastic_viscosity) | 1241 | 157 |  | 0.16 | 0.386 | 0.8 |  |
| static_yield_stress_at_rest@1200s | derived(static_yield_stress + structuration_rate_athix) | 302 | 45 |  | 0.141 | 0.394 | 0.8 | **yes** |

Weak models give order-of-magnitude guidance only; treat the literature hits below as the primary evidence for those targets.

## Candidates

Sampled 8192 → feasible 7947 at the requested thresholds. Shortlist 6, refined 6. Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.

| # | composition | compressive_strength | shear_stress_at_rate@50/s | shear_stress_at_rate@150/s | static_yield_stress_at_rest@1200s | P_min | P_prod | AD | clinker_fraction | analogue |
|---|---|---|---|---|---|---|---|---|---|---|
| 1* | portland_cement 0.50 / limestone_powder 0.16 / fly_ash_class_F 0.34; w/b 0.355; s/b 1.41; superplasticiser_pce 1.16%, vma_cellulose 0.07% | 44.3 [25.5, 70.7] p=0.74 | 464 [66.6, 1.59e+03] p=0.45 | 886 [139, 4.34e+03] p=0.66 | 1e+03 [41.4, 8.98e+03] p=0.47 ⚠ | 0.45 | 0.10 | 0.51 | 0.5 | 10.3390/ma18225123 (d=0.16) |
| 2* | portland_cement 0.50 / limestone_powder 0.17 / fly_ash_class_F 0.33; w/b 0.318; s/b 1.23; superplasticiser_pce 0.21% | 48.5 [24.5, 78.1] p=0.76 | 378 [57.8, 1.19e+03] p=0.51 | 814 [122, 3.15e+03] p=0.74 | 979 [45, 1.35e+04] p=0.48 ⚠ | 0.48 | 0.14 | 0.49 | 0.5 | 10.3390/ma18225123 (d=0.17) |
| 3* | portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.395; s/b 1.58; superplasticiser_pce 0.73%, vma_cellulose 0.07% | 48.2 [26.4, 75] p=0.78 | 503 [84.5, 1.38e+03] p=0.49 | 985 [178, 3.68e+03] p=0.69 | 908 [46, 1.21e+04] p=0.47 ⚠ | 0.47 | 0.12 | 0.48 | 0.5 | 10.1016/j.conbuildmat.2010.04.018 (d=0.49) |
| 4* | portland_cement 0.50 / silica_fume 0.11 / fly_ash_class_F 0.39; w/b 0.281; s/b 1.63; superplasticiser_pce 0.25% | 60.2 [34.7, 94.2] p=0.90 | 460 [79.4, 1.37e+03] p=0.49 | 990 [174, 3.6e+03] p=0.69 | 864 [41.6, 1.61e+04] p=0.48 ⚠ | 0.48 | 0.15 | 0.42 | 0.5 | 10.3389/fmats.2021.712551 (d=0.41) |
| 5* | portland_cement 0.50 / limestone_powder 0.17 / fly_ash_class_F 0.33; w/b 0.315; s/b 1.80; superplasticiser_pce 0.22%, vma_cellulose 0.08% | 47.9 [24.6, 77.8] p=0.76 | 647 [78.2, 1.41e+03] p=0.44 | 1.11e+03 [173, 3.47e+03] p=0.69 | 1.08e+03 [52, 1.12e+04] p=0.48 ⚠ | 0.44 | 0.11 | 0.47 | 0.5 | 10.3390/ma18225123 (d=0.19) |
| 6 | portland_cement 0.50 / limestone_powder 0.21 / fly_ash_class_F 0.29; w/b 0.282; s/b 0.80; superplasticiser_pce 1.13%, vma_cellulose 0.07% | 49.6 [23.9, 84.8] p=0.77 | 491 [64.7, 1.37e+03] p=0.48 | 833 [143, 3.67e+03] p=0.70 | 1.17e+03 [48.4, 1.05e+04] p=0.48 ⚠ | 0.48 | 0.13 | 0.55 | 0.5 | 10.3390/ma18225123 (d=0.39) |
| 7 | portland_cement 0.53 / silica_fume 0.15 / fly_ash_class_F 0.32; w/b 0.410; s/b 1.56; superplasticiser_pce 0.85%, vma_cellulose 0.05% | 45.1 [27.7, 67.7] p=0.77 | 474 [83.4, 1.41e+03] p=0.49 | 909 [179, 3.82e+03] p=0.68 | 867 [46.1, 1.4e+04] p=0.48 ⚠ | 0.48 | 0.12 | 0.51 | 0.535 | 10.1016/j.cemconcomp.2021.103974 (d=0.36) |
| 8 | portland_cement 0.54 / limestone_powder 0.25 / fly_ash_class_F 0.21; w/b 0.307; s/b 0.81; superplasticiser_pce 0.25% | 50.2 [23.1, 80.7] p=0.76 | 326 [52.7, 1.23e+03] p=0.47 | 682 [114, 3.41e+03] p=0.73 | 971 [41.4, 1.51e+04] p=0.48 ⚠ | 0.47 | 0.13 | 0.53 | 0.536 | 10.1016/j.cemconcomp.2024.105869 (d=0.47) |

\* refined by differential evolution. P_min = lowest per-target probability (the binding target); P_prod = product over targets. Units: compressive_strength [MPa], shear_stress_at_rate@50/s [Pa], shear_stress_at_rate@150/s [Pa], static_yield_stress_at_rest@1200s [Pa]

### Candidate 1 — portland_cement 0.50 / limestone_powder 0.16 / fly_ash_class_F 0.34; w/b 0.355; s/b 1.41; superplasticiser_pce 1.16%, vma_cellulose 0.07%

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
   "amount": 0.16358118477242614
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.336418815227574
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.011642044398268497
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0006875997633525376
  }
 ],
 "water_binder": 0.3553305726010621,
 "sand_binder": 1.4086925463000344,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.16): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.16): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → compressive_strength=12 MPa @2 d; compressive_strength=13.6 MPa @3 d; compressive_strength=20 MPa @7 d; compressive_strength=23.3 MPa @14 d

### Candidate 2 — portland_cement 0.50 / limestone_powder 0.17 / fly_ash_class_F 0.33; w/b 0.318; s/b 1.23; superplasticiser_pce 0.21%

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
   "amount": 0.17206047325734689
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.32793952674265325
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0021144958929881067
  }
 ],
 "water_binder": 0.31757108138043844,
 "sand_binder": 1.2292434950648523,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.17): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.172
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.17): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → compressive_strength=12 MPa @2 d; compressive_strength=13.6 MPa @3 d; compressive_strength=20 MPa @7 d; compressive_strength=23.3 MPa @14 d; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.172

### Candidate 3 — portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.395; s/b 1.58; superplasticiser_pce 0.73%, vma_cellulose 0.07%

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
   "amount": 0.12369299808983727
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.37630700191016286
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.007324862593399731
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0007394606031603949
  }
 ],
 "water_binder": 0.3948152778395747,
 "sand_binder": 1.5846282416265702,
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
- analogue 10.1016/j.conbuildmat.2010.04.018 'A3' (composition distance 0.49): opc 0.70 / fly_ash_f 0.20 / silica_fume 0.10; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.2 vs candidate 0.376; cement_share: analogue 0.7 vs candidate 0.5; pw_opc: analogue 0.7 vs candidate 0.5
- analogue 10.3389/fmats.2021.712551 'M9' (composition distance 0.49): opc 0.48 / fly_ash_f 0.30 / ggbfs 0.15 / silica_fume 0.06; w/b 0.30; sp_pce 0.50% → compressive_strength=38.2 MPa @3 d; compressive_strength=65.8 MPa @7 d; compressive_strength=93.9 MPa @28 d; compressive_strength=107 MPa @56 d; deviations: pw_silica_fume: analogue 0.0606 vs candidate 0.124; pw_ggbfs: analogue 0.152 vs candidate 0; pw_fly_ash_f: analogue 0.303 vs candidate 0.376

### Candidate 4 — portland_cement 0.50 / silica_fume 0.11 / fly_ash_class_F 0.39; w/b 0.281; s/b 1.63; superplasticiser_pce 0.25%

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
   "amount": 0.10772153022614765
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.3922784697738525
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0025396130379367033
  }
 ],
 "water_binder": 0.28097879328853964,
 "sand_binder": 1.634689737628132,
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
- analogue 10.3389/fmats.2021.712551 'M9' (composition distance 0.41): opc 0.48 / fly_ash_f 0.30 / ggbfs 0.15 / silica_fume 0.06; w/b 0.30; sp_pce 0.50% → compressive_strength=38.2 MPa @3 d; compressive_strength=65.8 MPa @7 d; compressive_strength=93.9 MPa @28 d; compressive_strength=107 MPa @56 d; deviations: pw_silica_fume: analogue 0.0606 vs candidate 0.108; pw_ggbfs: analogue 0.152 vs candidate 0; pw_fly_ash_f: analogue 0.303 vs candidate 0.392
- analogue 10.1016/j.conbuildmat.2010.04.018 'A3' (composition distance 0.48): opc 0.70 / fly_ash_f 0.20 / silica_fume 0.10; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.2 vs candidate 0.392; cement_share: analogue 0.7 vs candidate 0.5; pw_opc: analogue 0.7 vs candidate 0.5

### Candidate 5 — portland_cement 0.50 / limestone_powder 0.17 / fly_ash_class_F 0.33; w/b 0.315; s/b 1.80; superplasticiser_pce 0.22%, vma_cellulose 0.08%

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
   "amount": 0.17042839443315186
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.3295716055668483
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0021514856397836396
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0008069064376687757
  }
 ],
 "water_binder": 0.31456699903158974,
 "sand_binder": 1.7976399320936747,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.19): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.17
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.19): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → compressive_strength=12 MPa @2 d; compressive_strength=13.6 MPa @3 d; compressive_strength=20 MPa @7 d; compressive_strength=23.3 MPa @14 d; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.17

## Published mixes near the target

| tier | score | DOI | mix | composition | measured |
|---|---|---|---|---|---|
| near | 0.15 | 10.1016/j.istruc.2025.110861 | Ref | opc 0.88 / silica_fume 0.12; w/b 0.19; s/b 0.30; sp_pce 1.75%, expansive 2.00%, other_admix 0.30%; fibre 1.75 vol% | compressive_strength=110@28d; shear_stress_at_rate@50/s=240; shear_stress_at_rate@150/s=710 |
| near | 0.15 | 10.1016/j.jobe.2025.113480 | AS0 | opc 0.91 / silica_fume 0.09; w/b 0.36; s/b 0.18; sp_other 0.27%, vma 0.09%, clay_modifier 0.45% | compressive_strength=40.3@3d; compressive_strength=49@7d; shear_stress_at_rate@50/s=355; static_yield_stress_at_rest@1200s=1.62e+03 |
| near | 0.15 | 10.1016/j.jobe.2026.116405 | Ms06/GGBFS50 | ggbfs 0.50 / fly_ash_f 0.40 / slag_other 0.10; w/b 0.37; s/b 1.50; retarder 1.00%; activator 0.09/b | compressive_strength=27.7@7d; compressive_strength=42.8@28d; static_yield_stress_at_rest@1200s=1.75e+03 |
| near | 0.12 | 10.1016/j.jobe.2025.114496 | 0.1SF0.23W | opc 0.60 / limestone_powder 0.30 / silica_fume 0.10; w/b 0.23; s/b 0.36; sp_pce 2.00%, other_admix 0.02% | shear_stress_at_rate@50/s=237; shear_stress_at_rate@150/s=1.03e+03 |
| near | 0.10 | 10.1016/j.cemconcomp.2026.106741 | F70-Ms0-20 | fly_ash_f 0.70 / ggbfs 0.30; w/b 0.30; s/b 0.20; sp_pce 1.00%, retarder 0.10%; fibre 1.50 vol%; activator 0.06/b | compressive_strength=18.4@28d; shear_stress_at_rate@50/s=260 |
| near | 0.10 | 10.1016/j.cemconcomp.2021.104158 | M3 | opc 0.84 / silica_fume 0.16; w/b 0.35; s/b 1.00 | compressive_strength=19.1@3d; compressive_strength=21.2@7d; compressive_strength=22.5@14d; compressive_strength=23.8@21d |
| near | 0.09 | 10.1016/j.jobe.2025.113480 | AS2 | opc 0.91 / silica_fume 0.09; w/b 0.36; s/b 0.18; sp_other 0.27%, vma 0.09%, clay_modifier 0.45% | compressive_strength=47.8@3d; compressive_strength=53@7d; shear_stress_at_rate@50/s=575; static_yield_stress_at_rest@1200s=1.81e+03 |
| near | 0.07 | 10.1016/j.jobe.2025.114496 | 0.3SF0.23W | opc 0.60 / silica_fume 0.30 / limestone_powder 0.10; w/b 0.23; s/b 0.36; sp_pce 2.00%, other_admix 0.02% | shear_stress_at_rate@50/s=650; shear_stress_at_rate@150/s=1.42e+03 |
| near | 0.07 | 10.1016/j.jobe.2026.116405 | GGBFS30 | fly_ash_f 0.60 / ggbfs 0.30 / slag_other 0.10; w/b 0.37; s/b 1.50; retarder 1.00%; activator 0.09/b | compressive_strength=17.8@7d; compressive_strength=22.2@28d; static_yield_stress_at_rest@1200s=1.13e+03 |
| near | 0.07 | 10.1016/j.istruc.2025.110861 | LC3-45 | opc 0.48 / calcined_clay 0.25 / limestone_powder 0.13 / silica_fume 0.12; w/b 0.19; s/b 0.30; sp_pce 1.75%, expansive 2.00%, other_admix 0.30%; fibre 1.75 vol% | compressive_strength=92.7@28d; shear_stress_at_rate@50/s=125; shear_stress_at_rate@150/s=415 |
| near | 0.04 | 10.1016/j.jobe.2025.114496 | 0.2SF0.21W | opc 0.60 / silica_fume 0.20 / limestone_powder 0.20; w/b 0.21; s/b 0.36; sp_pce 2.00%, other_admix 0.02% | shear_stress_at_rate@50/s=405; shear_stress_at_rate@150/s=1.53e+03 |
| near | 0.03 | 10.1016/j.istruc.2025.110861 | LC3-30 | opc 0.62 / calcined_clay 0.17 / silica_fume 0.12 / limestone_powder 0.08; w/b 0.19; s/b 0.30; sp_pce 1.75%, expansive 2.00%, other_admix 0.30%; fibre 1.75 vol% | compressive_strength=111@28d; shear_stress_at_rate@50/s=108; shear_stress_at_rate@150/s=335 |

## Provenance

Cost table: C:\Users\User\3D Printing Concrete Prediction\configs\unit_cost_default.yaml (hash c7dba05d5c80, DEFAULT PLACEHOLDER); CO2 table: C:\Users\User\3D Printing Concrete Prediction\configs\embodied_carbon_default.yaml (hash c7e6390d1a13, DEFAULT PLACEHOLDER).
**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**

Diagnostics: {"n_sampled": 8192, "n_feasible": 7947, "t_stage1_s": 11.4, "n_shortlist": 6, "t_stage2_s": 28.2, "n_final": 12, "evaluator_calls": 77, "t_total_s": 99.5, "weak_models": ["structuration_rate_athix", "static_yield_stress_at_rest"]}
