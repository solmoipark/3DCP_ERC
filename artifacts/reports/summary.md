# pmpredict — model summary

Updated 2026-09-10T04:04:37+00:00. Feature schema `46fc6fc1a95b98db`, 21650 normalised mixes, 138 features.

Metrics are out-of-fold under **GroupKFold by paper** (5 folds); intervals are 80 % after split-conformal scaling. R² is on the original scale (dominated by extreme values for heavy-tailed targets); R²(log) and Spearman describe the model's ranking power on the modelled (log) scale. `weak` flags models with n < 300, interval coverage < 0.65 or R²(log) < 0.15 — use their predictions as order-of-magnitude guidance only. `leak_gap` = R² gain a random KFold would have (falsely) reported.

| target | variant | unit | n rows | papers | tier | R² | R²(log) | Spearman | RMSE | MAE | medAPE | cov80 | Ridge R² | weak | leak_gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| compressive_strength | 3dcp | MPa | 508 | 41 | small | 0.139 | 0.047 | 0.331 | 22.58 | 17.94 | 0.379 | 0.80 | -0.361 | yes |  |
| dynamic_yield_stress | 3dcp | Pa | 288 | 44 | small | -0.086 | 0.074 | 0.336 | 1174.98 | 577.19 | 0.693 | 0.80 | -1.591 | yes |  |
| flexural_strength | 3dcp | MPa | 148 | 15 | small | 0.015 | 0.061 | 0.340 | 3.18 | 2.42 | 0.274 | 0.80 | -2.117 | yes |  |
| flow_table_spread | 3dcp | mm | 62 | 13 | small | -0.292 | -0.292 | 0.151 | 37.73 | 27.31 | 0.113 | 0.79 | -2.517 | yes |  |
| initial_setting_time | 3dcp | min | 52 | 12 | small | -0.100 | 0.039 | 0.174 | 96.38 | 64.84 | 0.503 | 0.79 | -0.311 | yes |  |
| plastic_viscosity | 3dcp | Pa.s | 299 | 42 | small | -0.071 | 0.114 | 0.320 | 61.42 | 23.47 | 0.823 | 0.80 | -2.772 | yes |  |
| static_yield_stress | 3dcp | Pa | 250 | 34 | small | -0.176 | 0.012 | 0.184 | 3001.32 | 1344.14 | 0.855 | 0.80 | -5.068 | yes |  |
| structuration_rate_athix | 3dcp | Pa/s | 191 | 25 | small | -0.101 | 0.088 | 0.329 | 4.98 | 2.13 | 0.886 | 0.80 | -6.122 | yes |  |
| autogenous_shrinkage | general | microstrain | 10643 | 213 | large | -0.001 | 0.390 | 0.620 | 2413.37 | 620.50 | 0.723 | 0.80 | -10.557 |  |  |
| compressive_strength | general | MPa | 44383 | 1325 | large | 0.513 | 0.422 | 0.688 | 19.75 | 13.77 | 0.303 | 0.80 | 0.259 |  |  |
| cumulative_heat | general | J/g binder | 447 | 50 | small | 0.231 | 0.231 | 0.476 | 72.91 | 59.30 | 0.302 | 0.80 | -0.728 |  |  |
| direct_tensile_strength | general | MPa | 344 | 53 | small | 0.495 | 0.453 | 0.711 | 2.52 | 1.97 | 0.315 | 0.80 | -0.762 |  |  |
| drying_shrinkage | general | microstrain | 17270 | 264 | large | 0.141 | 0.508 | 0.735 | 2837.55 | 909.17 | 0.664 | 0.80 | -9.664 |  |  |
| dynamic_yield_stress | general | Pa | 1325 | 160 | medium | 0.032 | 0.160 | 0.386 | 594.34 | 190.39 | 0.827 | 0.80 | -0.245 |  |  |
| elastic_modulus | general | GPa | 340 | 39 | small | 0.094 | -0.005 | 0.450 | 14.99 | 12.85 | 0.428 | 0.80 | -2.051 | yes |  |
| final_setting_time | general | min | 1252 | 239 | medium | 0.001 | 0.357 | 0.492 | 297.56 | 169.88 | 0.514 | 0.80 | -0.335 |  |  |
| flexural_strength | general | MPa | 5078 | 305 | large | 0.289 | 0.249 | 0.468 | 4.66 | 3.21 | 0.377 | 0.80 | 0.168 |  |  |
| flow_table_spread | general | mm | 1058 | 169 | medium | -0.061 | -0.061 | 0.095 | 50.18 | 39.61 | 0.185 | 0.80 | -0.450 | yes |  |
| hardened_density | general | kg/m3 | 344 | 46 | small | 0.318 | 0.318 | 0.673 | 270.60 | 182.55 | 0.062 | 0.80 | -1.240 |  |  |
| initial_setting_time | general | min | 1400 | 260 | medium | -0.051 | 0.293 | 0.481 | 209.35 | 118.51 | 0.517 | 0.80 | -0.915 |  |  |
| mini_slump_flow_diameter | general | mm | 1279 | 126 | medium | -0.057 | -0.057 | 0.182 | 74.90 | 60.65 | 0.239 | 0.80 | -0.562 | yes |  |
| plastic_viscosity | general | Pa.s | 1241 | 157 | medium | 0.118 | 0.408 | 0.651 | 40.69 | 13.49 | 0.674 | 0.80 | -1.412 |  |  |
| porosity_total | general | % | 1410 | 245 | medium | 0.232 | 0.232 | 0.495 | 10.75 | 7.98 | 0.317 | 0.80 | -0.305 |  |  |
| splitting_tensile_strength | general | MPa | 344 | 34 | small | 0.006 | 0.011 | 0.242 | 2.94 | 2.17 | 0.580 | 0.80 | -0.348 | yes |  |
| static_yield_stress | general | Pa | 707 | 82 | small | -0.052 | 0.165 | 0.403 | 1908.10 | 709.55 | 0.936 | 0.80 | -19.040 |  |  |
| structuration_rate_athix | general | Pa/s | 302 | 45 | small | -0.005 | 0.141 | 0.394 | 3.92 | 1.43 | 0.834 | 0.80 | -5.116 | yes |  |
| water_absorption | general | % | 930 | 103 | medium | 0.324 | 0.324 | 0.395 | 6.23 | 4.27 | 0.373 | 0.80 | -0.082 |  |  |

## Slices
Per-target slice metrics (age, specimen geometry, binder family, 3DCP) are in `artifacts/reports/<target>_slices.csv`; feature importances in `artifacts/models/<target>/importance.csv`.
