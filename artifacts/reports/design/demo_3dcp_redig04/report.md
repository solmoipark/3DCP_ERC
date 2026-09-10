# Design report — 3dcp_printable_mortar

Generated 2026-09-10T04:05:55+00:00 · pmpredict 0.1.0

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
| compressive_strength | compressive_strength | 44383 | 1325 | 0.513 | 0.422 | 0.688 | 0.8 |  |
| static_yield_stress | static_yield_stress | 707 | 82 | -0.0518 | 0.165 | 0.403 | 0.8 |  |
| flow_table_spread | flow_table_spread | 1058 | 169 | -0.0607 | -0.0607 | 0.0947 | 0.8 | **yes** |

Weak models give order-of-magnitude guidance only; treat the literature hits below as the primary evidence for those targets.

## Candidates

Sampled 16384 → feasible 1 at the requested thresholds; relaxed to per-target p_min {'compressive_strength': 0.63, 'static_yield_stress': 0.27, 'flow_table_spread': 0.315} and ad_max 1.0. Shortlist 8, refined 8. Feasibility = every target above its own p_min and AD ≤ ad_max; P_feas (product) assumes independence between targets.

| # | composition | compressive_strength | static_yield_stress | flow_table_spread | P_min | P_prod | AD | clinker_fraction | co2 | analogue |
|---|---|---|---|---|---|---|---|---|---|---|
| 1* | portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.418; s/b 1.76; superplasticiser_pce 0.33%, vma_cellulose 0.09% | 43.4 [26.4, 66.1] p=0.60 | 185 [1.77, 5.7e+03] p=0.24 | 180 [121, 253] p=0.45 ⚠ | 0.24 | 0.06 | 0.45 | 0.5 | 300 | 10.3389/fmats.2021.712551 (d=0.47) |
| 2* | portland_cement 0.50 / limestone_powder 0.20 / fly_ash_class_F 0.30; w/b 0.398; s/b 1.79; superplasticiser_pce 0.24%, vma_cellulose 0.02% | 43.6 [22.5, 70.3] p=0.59 | 146 [2.03, 5.17e+03] p=0.25 | 180 [124, 250] p=0.47 ⚠ | 0.25 | 0.07 | 0.44 | 0.5 | 305 | 10.3390/ma18225123 (d=0.35) |
| 3* | portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.432; s/b 1.80; superplasticiser_pce 0.26%, vma_cellulose 0.01% | 42.5 [30.5, 59.8] p=0.60 | 145 [1.76, 6.17e+03] p=0.22 | 183 [125, 252] p=0.45 ⚠ | 0.22 | 0.06 | 0.78 | 0.55 | 330 | 10.1016/j.conbuildmat.2011.06.064 (d=0.32) |
| 4 | portland_cement 0.60 / limestone_powder 0.24 / fly_ash_class_F 0.16; w/b 0.290; s/b 1.76; superplasticiser_pce 0.21%, vma_cellulose 0.09% | 46.8 [24.6, 89.5] p=0.65 | 183 [4.18, 4.62e+03] p=0.27 | 183 [125, 246] p=0.46 ⚠ | 0.27 | 0.08 | 0.43 | 0.602 | 402 | 10.1016/j.cemconcomp.2024.105869 (d=0.31) |
| 5 | portland_cement 0.67 / limestone_powder 0.13 / fly_ash_class_F 0.21; w/b 0.355; s/b 0.89; superplasticiser_pce 0.33%, vma_cellulose 0.01% | 47.8 [24.5, 72.6] p=0.67 | 198 [1.3, 4.61e+03] p=0.27 | 183 [125, 256] p=0.45 ⚠ | 0.27 | 0.08 | 0.44 | 0.668 | 550 | 10.1016/j.conbuildmat.2023.134586 (d=0.12) |
| 6 | portland_cement 0.67 / silica_fume 0.09 / limestone_powder 0.24; w/b 0.399; s/b 1.72; superplasticiser_pce 0.29%, vma_cellulose 0.29% | 48.3 [33.6, 69.7] p=0.77 | 223 [1.42, 4.68e+03] p=0.27 | 182 [125, 250] p=0.46 ⚠ | 0.27 | 0.10 | 0.57 | 0.674 | 423 | 10.1016/j.conbuildmat.2011.06.064 (d=0.43) |
| 7* | portland_cement 0.70 / limestone_powder 0.30; w/b 0.420; s/b 1.80; superplasticiser_pce 0.21%, vma_cellulose 0.03% | 43.6 [24.5, 66.8] p=0.60 | 158 [1.73, 5.83e+03] p=0.23 | 179 [126, 248] p=0.48 ⚠ | 0.23 | 0.07 | 0.48 | 0.7 | 422 | 10.1016/j.cemconcomp.2025.106439 (d=0.03) |
| 8 | portland_cement 0.78 / limestone_powder 0.22; w/b 0.377; s/b 1.77; superplasticiser_pce 0.28%, vma_cellulose 0.06% | 49.3 [26.5, 77] p=0.70 | 153 [1.79, 4.43e+03] p=0.28 | 181 [125, 248] p=0.47 ⚠ | 0.28 | 0.09 | 0.35 | 0.775 | 485 | 10.1016/j.cscm.2024.e03149 (d=0.09) |
| 9 | portland_cement 0.69 / silica_fume 0.07 / limestone_powder 0.25; w/b 0.292; s/b 0.85; superplasticiser_pce 0.51%, vma_cellulose 0.04% | 63.4 [31.3, 97.7] p=0.83 | 216 [3.82, 4.27e+03] p=0.29 | 188 [124, 268] p=0.41 ⚠ | 0.29 | 0.10 | 0.55 | 0.685 | 620 | 10.1016/j.conbuildmat.2011.06.064 (d=0.33) |
| 10 | portland_cement 0.75 / silica_fume 0.11 / fly_ash_class_F 0.14; w/b 0.377; s/b 1.47; superplasticiser_pce 0.40%, vma_cellulose 0.28% | 52.4 [33.6, 76.2] p=0.80 | 204 [1.28, 4.62e+03] p=0.27 | 181 [125, 252] p=0.46 ⚠ | 0.27 | 0.10 | 0.62 | 0.751 | 505 | 10.1016/j.conbuildmat.2026.145233 (d=0.32) |

\* refined by differential evolution. P_min = lowest per-target probability (the binding target); P_prod = product over targets. Units: compressive_strength [MPa], static_yield_stress [Pa], flow_table_spread [mm]

### Candidate 1 — portland_cement 0.50 / silica_fume 0.12 / fly_ash_class_F 0.38; w/b 0.418; s/b 1.76; superplasticiser_pce 0.33%, vma_cellulose 0.09%

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
   "amount": 0.11763402964353982
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.3823659703564602
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.003342187400677908
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0009156162243332033
  }
 ],
 "water_binder": 0.41840345734314643,
 "sand_binder": 1.763021323135492,
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
- analogue 10.3389/fmats.2021.712551 'M9' (composition distance 0.47): opc 0.48 / fly_ash_f 0.30 / ggbfs 0.15 / silica_fume 0.06; w/b 0.30; sp_pce 0.50% → compressive_strength=38.2 MPa @3 d; compressive_strength=65.8 MPa @7 d; compressive_strength=93.9 MPa @28 d; compressive_strength=107 MPa @56 d; deviations: pw_silica_fume: analogue 0.0606 vs candidate 0.118; pw_ggbfs: analogue 0.152 vs candidate 0; pw_fly_ash_f: analogue 0.303 vs candidate 0.382
- analogue 10.1016/j.conbuildmat.2010.04.018 'A3' (composition distance 0.49): opc 0.70 / fly_ash_f 0.20 / silica_fume 0.10; w/b 0.30; sp_other 1.04% → no matching measurements; deviations: pw_fly_ash_f: analogue 0.2 vs candidate 0.382; cement_share: analogue 0.7 vs candidate 0.5; pw_opc: analogue 0.7 vs candidate 0.5

### Candidate 2 — portland_cement 0.50 / limestone_powder 0.20 / fly_ash_class_F 0.30; w/b 0.398; s/b 1.79; superplasticiser_pce 0.24%, vma_cellulose 0.02%

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
   "amount": 0.2039723792130333
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.2960276207869667
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.0024342276264363687
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00016764896913807142
  }
 ],
 "water_binder": 0.3978999767000123,
 "sand_binder": 1.7903644884353342,
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
- analogue 10.3390/ma18225123 'HVFA' (composition distance 0.35): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.204; filler_frac: analogue 0.15 vs candidate 0.204
- analogue 10.3390/ma18225123 'HVFA (mortar)' (composition distance 0.35): opc 0.55 / fly_ash_f 0.30 / limestone_powder 0.15; w/b 0.50 → compressive_strength=12 MPa @2 d; compressive_strength=13.6 MPa @3 d; compressive_strength=20 MPa @7 d; compressive_strength=23.3 MPa @14 d; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.204; filler_frac: analogue 0.15 vs candidate 0.204

### Candidate 3 — portland_cement 0.55 / silica_fume 0.15 / limestone_powder 0.30; w/b 0.432; s/b 1.80; superplasticiser_pce 0.26%, vma_cellulose 0.01%

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
   "amount": 0.002608208515724519
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.00011058342193789612
  }
 ],
 "water_binder": 0.43242620419547617,
 "sand_binder": 1.7994570226885755,
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
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L15S' (composition distance 0.32): opc 0.50 / limestone_powder 0.35 / silica_fume 0.15; w/b 0.50; s/b 3.00 → flow_table_spread=132 mm; deviations: pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3
- analogue 10.1016/j.conbuildmat.2011.06.064 '35L10S' (composition distance 0.46): opc 0.55 / limestone_powder 0.35 / silica_fume 0.10; w/b 0.50; s/b 3.00 → flow_table_spread=135 mm; deviations: pw_silica_fume: analogue 0.1 vs candidate 0.15; pw_limestone_powder: analogue 0.35 vs candidate 0.3; filler_frac: analogue 0.35 vs candidate 0.3

### Candidate 4 — portland_cement 0.60 / limestone_powder 0.24 / fly_ash_class_F 0.16; w/b 0.290; s/b 1.76; superplasticiser_pce 0.21%, vma_cellulose 0.09%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.6022339409217238
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.23513974705711008
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.16262631202116612
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.00214817961050341
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0008869651667533253
  }
 ],
 "water_binder": 0.2904247216135264,
 "sand_binder": 1.7588240263983608,
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
- analogue 10.1016/j.cemconcomp.2024.105869 'F10L20 (C)[FGfam]' (composition distance 0.31): opc 0.70 / limestone_powder 0.20 / fly_ash_f 0.10; w/b 0.32; sp_pce 0.25% → no matching measurements; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.235; cement_share: analogue 0.7 vs candidate 0.602; filler_frac: analogue 0.2 vs candidate 0.235
- analogue 10.1016/j.cemconcomp.2024.105869 'F10L20 mortar (C)[FGfam]' (composition distance 0.31): opc 0.70 / limestone_powder 0.20 / fly_ash_f 0.10; w/b 0.32; sp_pce 0.25% → compressive_strength=18 MPa @1 d; compressive_strength=26.5 MPa @2 d; compressive_strength=35 MPa @3 d; compressive_strength=37 MPa @7 d; deviations: pw_limestone_powder: analogue 0.2 vs candidate 0.235; cement_share: analogue 0.7 vs candidate 0.602; filler_frac: analogue 0.2 vs candidate 0.235

### Candidate 5 — portland_cement 0.67 / limestone_powder 0.13 / fly_ash_class_F 0.21; w/b 0.355; s/b 0.89; superplasticiser_pce 0.33%, vma_cellulose 0.01%

```json
{
 "system_type": "mortar",
 "components": [
  {
   "material_class": "portland_cement",
   "amount": 0.6681922049261629
  },
  {
   "material_class": "limestone_powder",
   "amount": 0.12610147055238485
  },
  {
   "material_class": "fly_ash_class_F",
   "amount": 0.2057063245214522
  },
  {
   "material_class": "superplasticiser_pce",
   "amount": 0.003283057995964732
  },
  {
   "material_class": "vma_cellulose",
   "amount": 0.0001212473778905519
  }
 ],
 "water_binder": 0.35504808875732125,
 "sand_binder": 0.8866250945255161,
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
- analogue 10.1016/j.conbuildmat.2023.134586 'LS paste (13.0% microfines)' (composition distance 0.12): opc 0.71 / fly_ash_f 0.18 / limestone_powder 0.12; w/b 0.47 → no matching measurements
- analogue 10.1016/j.cemconcomp.2024.105869 'F15L15 (C)[FGfam]' (composition distance 0.19): opc 0.70 / fly_ash_f 0.15 / limestone_powder 0.15; w/b 0.32; sp_pce 0.25% → no matching measurements; deviations: pw_limestone_powder: analogue 0.15 vs candidate 0.126; pw_fly_ash_f: analogue 0.15 vs candidate 0.206

## Published mixes near the target

| tier | score | DOI | mix | composition | measured |
|---|---|---|---|---|---|
| near | 0.83 | 10.3390/buildings13061476 | M1 | opc 1.00; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | compressive_strength=24.8@1d; compressive_strength=42.9@7d; compressive_strength=48.6@28d; flow_table_spread=168 |
| near | 0.48 | 10.3390/buildings13061476 | M2 | opc 0.80 / glass_powder 0.20; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | flow_table_spread=173; static_yield_stress=3.7e+03; static_yield_stress=7.09e+03; static_yield_stress=9.99e+03 |
| near | 0.30 | 10.3390/buildings15193436 | 1% Microfibre + SF | ggbfs 0.50 / opc 0.45 / silica_fume 0.05; w/b 0.26; s/b 1.00; sp_pce 2.00% | compressive_strength=66.5@7d; compressive_strength=86.1@28d; flow_table_spread=202; static_yield_stress=208 |
| near | 0.25 | 10.1016/j.conbuildmat.2017.12.112 | Mixture A | opc 0.48 / fly_ash_f 0.48 / silica_fume 0.05; w/b 0.14; s/b 0.50 | compressive_strength=49.7@28d; static_yield_stress=3.35e+03 |
| near | 0.25 | 10.1016/j.conbuildmat.2023.133561 | M2 | opc 0.50 / ggbfs 0.50; w/b 0.37; s/b 1.16 | compressive_strength=53.4@28d; compressive_strength=34.8@33d; flow_table_spread=176 |
| near | 0.25 | 10.1016/j.conbuildmat.2026.147445 | MK0 | fly_ash_f 0.60 / ggbfs 0.40; w/b 0.09; s/b 0.60; sp_pce 1.00%; fibre 2.17 vol%; activator 0.42/b | compressive_strength=66.6@28d; flow_table_spread=173 |
| near | 0.25 | 10.1016/j.cscm.2025.e05426 | Control (OPC) | opc 1.00; w/b 0.45; s/b 2.75 | compressive_strength=11.4@3d; compressive_strength=37.6@7d; compressive_strength=43.9@28d; flow_table_spread=186 |
| near | 0.25 | 10.1016/j.nxmate.2025.101552 | 0% BP | opc 1.00; w/b 0.42; s/b 1.48 | compressive_strength=30.1@7d; compressive_strength=46.3@14d; compressive_strength=52.4@28d; flow_table_spread=160 |
| near | 0.25 | 10.1016/j.pes.2026.100274 | UHPC-CC20 | opc 0.80 / calcined_clay 0.20; w/b 0.19; s/b 0.75; sp_pce 0.67%; fibre 1.49 vol% | compressive_strength=121@28d; flow_table_spread=183; compressive_strength=70@1d; compressive_strength=75.7@2d |
| near | 0.25 | 10.1016/j.susmat.2018.05.001 | C | opc 1.00; w/b 0.48; s/b 2.75; sp_pce 0.53% | compressive_strength=31.4@3d; compressive_strength=41.9@7d; compressive_strength=53.1@28d; compressive_strength=58.8@90d |
| near | 0.19 | 10.3390/buildings13061476 | M4 | glass_powder 0.60 / opc 0.40; w/b 0.35; s/b 1.00; sp_pce 0.10%, vma 0.10% | compressive_strength=6.8@1d; compressive_strength=18.6@7d; compressive_strength=25.3@28d; flow_table_spread=194 |
| near | 0.15 | 10.1016/j.conbuildmat.2026.147445 | MK30 | ggbfs 0.40 / fly_ash_f 0.30 / metakaolin 0.30; w/b 0.09; s/b 0.60; sp_pce 1.00%; fibre 2.14 vol%; activator 0.42/b | compressive_strength=92.9@28d; flow_table_spread=141 |
| near | 0.15 | 10.1016/j.nxmate.2025.101552 | 0.2% BP | opc 1.00; w/b 0.42; s/b 1.48 | compressive_strength=35.9@7d; compressive_strength=50.7@14d; compressive_strength=61.8@28d; flow_table_spread=170 |
| near | 0.09 | 10.1016/j.conbuildmat.2026.147445 | MK10B2 | fly_ash_f 0.50 / ggbfs 0.40 / metakaolin 0.10 / other_powder 0.01; w/b 0.09; s/b 0.60; sp_pce 0.99%; fibre 2.19 vol%; activator 0.42/b | compressive_strength=106@28d; flow_table_spread=155 |
| near | 0.09 | 10.1016/j.nxmate.2025.101552 | 0.6% BP | opc 0.99 / other_powder 0.01; w/b 0.42; s/b 1.47 | compressive_strength=21.7@7d; compressive_strength=42@14d; compressive_strength=49.5@28d; flow_table_spread=185 |

## Provenance

Cost table: C:\Users\User\3D Printing Concrete Prediction\configs\unit_cost_default.yaml (hash c7dba05d5c80, DEFAULT PLACEHOLDER); CO2 table: C:\Users\User\3D Printing Concrete Prediction\configs\embodied_carbon_default.yaml (hash c7e6390d1a13, DEFAULT PLACEHOLDER).
**Cost and CO2 use illustrative placeholder factors — replace them with your own tables before quoting numbers.**

Diagnostics: {"n_sampled": 16384, "n_feasible": 1, "t_stage1_s": 18.0, "relaxation": [{"threshold_scale": 0.9, "ad_max": 1.0, "n_feasible": 258}], "threshold_scale_used": 0.9, "ad_max_used": 1.0, "p_min_used": {"compressive_strength": 0.63, "static_yield_stress": 0.27, "flow_table_spread": 0.315}, "n_shortlist": 8, "t_stage2_s": 44.8, "n_final": 16, "evaluator_calls": 170, "t_total_s": 63.1, "weak_models": ["flow_table_spread"]}
