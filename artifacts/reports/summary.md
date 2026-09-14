# pmpredict — model summary

Updated 2026-09-11T17:15:29+00:00. Feature schema `9dac026be72fb584`, 28001 normalised mixes, 138 features.

Metrics are out-of-fold under **GroupKFold by paper** (5 folds); intervals are 80 % after split-conformal scaling. R² is on the original scale (dominated by extreme values for heavy-tailed targets); R²(log) and Spearman describe the model's ranking power on the modelled (log) scale. `weak` flags models with n < 300, interval coverage < 0.65 or R²(log) < 0.15 — use their predictions as order-of-magnitude guidance only. `leak_gap` = R² gain a random KFold would have (falsely) reported.

| target | variant | unit | n rows | papers | tier | R² | R²(log) | Spearman | RMSE | MAE | medAPE | cov80 | Ridge R² | weak | leak_gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| compressive_strength | 3dcp | MPa | 2890 | 326 | medium | 0.342 | 0.416 | 0.573 | 18.68 | 13.73 | 0.307 | 0.80 | -0.077 |  |  |
| direct_tensile_strength | 3dcp | MPa | 83 | 32 | small | -0.158 | 0.093 | 0.328 | 2.85 | 2.14 | 0.469 | 0.80 | -0.863 | yes |  |
| drying_shrinkage | 3dcp | microstrain | 779 | 19 | small | -0.187 | 0.098 | 0.326 | 1942.64 | 1040.61 | 0.645 | 0.80 | -0.157 | yes |  |
| dynamic_yield_stress | 3dcp | Pa | 895 | 167 | medium | -0.019 | 0.021 | 0.205 | 1454.10 | 451.06 | 0.696 | 0.80 | -12.949 | yes |  |
| elastic_modulus | 3dcp | GPa | 74 | 26 | small | -0.219 | -0.113 | -0.078 | 8.61 | 7.21 | 0.270 | 0.80 | -3.167 | yes |  |
| final_setting_time | 3dcp | min | 221 | 56 | small | 0.066 | 0.243 | 0.510 | 229.24 | 142.98 | 0.452 | 0.80 | -0.730 | yes |  |
| flexural_strength | 3dcp | MPa | 1109 | 152 | medium | -0.006 | 0.122 | 0.285 | 3.53 | 2.46 | 0.287 | 0.80 | -8.588 | yes |  |
| flow_table_spread | 3dcp | mm | 660 | 127 | small | -0.080 | -0.080 | 0.093 | 45.42 | 31.61 | 0.138 | 0.80 | -1.422 | yes |  |
| hardened_density | 3dcp | kg/m3 | 89 | 23 | small | 0.224 | 0.224 | 0.457 | 401.46 | 297.27 | 0.100 | 0.80 | -0.152 | yes |  |
| initial_setting_time | 3dcp | min | 395 | 98 | small | -0.033 | -0.078 | 0.249 | 129.93 | 87.80 | 0.527 | 0.80 | -0.109 | yes |  |
| mini_slump_flow_diameter | 3dcp | mm | 306 | 67 | small | -0.323 | -0.323 | -0.237 | 78.51 | 56.00 | 0.191 | 0.80 | -0.987 | yes |  |
| plastic_viscosity | 3dcp | Pa.s | 781 | 147 | small | -0.013 | 0.108 | 0.379 | 164.33 | 27.00 | 0.730 | 0.80 | -27.015 | yes |  |
| porosity_total | 3dcp | % | 219 | 75 | small | -0.031 | -0.031 | 0.139 | 11.10 | 7.99 | 0.700 | 0.80 | -1.513 | yes |  |
| splitting_tensile_strength | 3dcp | MPa | 44 | 15 | small | -0.703 | -0.787 | -0.672 | 5.63 | 4.08 | 0.756 | 0.80 | -1.208 | yes |  |
| static_yield_stress | 3dcp | Pa | 1256 | 192 | medium | -0.084 | 0.158 | 0.322 | 11758.82 | 4162.00 | 0.740 | 0.80 | -9.876 |  |  |
| structuration_rate_athix | 3dcp | Pa/s | 570 | 100 | small | -0.076 | -0.162 | -0.105 | 21.70 | 6.26 | 0.952 | 0.80 | -5.634 | yes |  |
| water_absorption | 3dcp | % | 104 | 14 | small | 0.176 | 0.176 | 0.591 | 7.32 | 5.46 | 0.487 | 0.80 | -0.483 | yes |  |
| autogenous_shrinkage | general | microstrain | 10868 | 222 | large | 0.006 | 0.400 | 0.609 | 2381.55 | 601.67 | 0.725 | 0.80 | -7.922 |  |  |
| compressive_strength | general | MPa | 47125 | 1634 | large | 0.533 | 0.449 | 0.686 | 19.20 | 13.53 | 0.305 | 0.80 | 0.342 |  |  |
| cumulative_heat | general | J/g binder | 617 | 75 | small | 0.257 | 0.257 | 0.501 | 75.22 | 59.99 | 0.289 | 0.80 | -0.340 |  |  |
| direct_tensile_strength | general | MPa | 432 | 85 | small | 0.451 | 0.419 | 0.693 | 2.56 | 1.91 | 0.300 | 0.80 | -0.083 |  |  |
| drying_shrinkage | general | microstrain | 18236 | 287 | large | 0.173 | 0.520 | 0.739 | 2734.15 | 877.73 | 0.632 | 0.80 | -7.918 |  |  |
| dynamic_yield_stress | general | Pa | 2032 | 294 | medium | -0.002 | 0.254 | 0.537 | 1016.10 | 248.01 | 0.780 | 0.80 | -10.858 |  |  |
| elastic_modulus | general | GPa | 431 | 65 | small | -0.089 | 0.058 | 0.330 | 15.65 | 13.07 | 0.526 | 0.80 | -1.524 | yes |  |
| final_setting_time | general | min | 1440 | 290 | medium | 0.074 | 0.377 | 0.544 | 279.40 | 157.94 | 0.459 | 0.80 | -0.498 |  |  |
| flexural_strength | general | MPa | 6148 | 452 | large | 0.370 | 0.288 | 0.462 | 4.17 | 2.95 | 0.352 | 0.80 | -0.036 |  |  |
| flow_table_spread | general | mm | 1693 | 290 | medium | -0.027 | -0.027 | 0.075 | 48.06 | 36.60 | 0.174 | 0.80 | -0.669 | yes |  |
| hardened_density | general | kg/m3 | 432 | 69 | small | 0.119 | 0.119 | 0.512 | 355.17 | 246.29 | 0.084 | 0.80 | -0.729 | yes |  |
| initial_setting_time | general | min | 1747 | 348 | medium | 0.005 | 0.337 | 0.526 | 192.26 | 109.00 | 0.506 | 0.80 | -0.247 |  |  |
| mini_slump_flow_diameter | general | mm | 1563 | 186 | medium | -0.178 | -0.178 | 0.090 | 79.14 | 63.10 | 0.261 | 0.80 | -0.472 | yes |  |
| plastic_viscosity | general | Pa.s | 1817 | 274 | medium | -0.005 | 0.405 | 0.648 | 133.08 | 19.86 | 0.685 | 0.80 | -13.554 |  |  |
| porosity_total | general | % | 1625 | 315 | medium | 0.169 | 0.169 | 0.404 | 11.38 | 8.45 | 0.351 | 0.80 | -0.121 |  |  |
| splitting_tensile_strength | general | MPa | 390 | 51 | small | 0.485 | 0.388 | 0.640 | 2.30 | 1.61 | 0.388 | 0.80 | -0.500 |  |  |
| static_yield_stress | general | Pa | 1728 | 241 | medium | -0.044 | 0.399 | 0.618 | 10056.99 | 3153.08 | 0.819 | 0.80 | -1.983 |  |  |
| structuration_rate_athix | general | Pa/s | 692 | 124 | small | -0.056 | 0.036 | 0.222 | 19.65 | 5.15 | 0.925 | 0.80 | -2.161 | yes |  |
| water_absorption | general | % | 1040 | 117 | medium | 0.380 | 0.380 | 0.543 | 6.09 | 4.30 | 0.383 | 0.80 | -0.111 |  |  |

## Slices
Per-target slice metrics (age, specimen geometry, binder family, 3DCP) are in `artifacts/reports/<target>_slices.csv`; feature importances in `artifacts/models/<target>/importance.csv`.
