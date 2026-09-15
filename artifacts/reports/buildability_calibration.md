# Buildability calibration against print01 labels (2026-09-14)

Source: `print_process.db` — 7,420 print runs / 928 papers joined to master.db fresh properties (median per mix, tabulated values only). Output: `configs/buildability_calibration.json`, `data/print_runs.parquet`.

## Plastic-collapse ratio R = ρ g H / (√3 τ_s) at failure

Stack-until-failure collapses with a tabulated static yield stress: **146 runs / 37 papers**. R at collapse: p10 0.333, p25 0.6429, **median 1.3903**, p75 2.8718, p90 5.8417. R = 1 is the Roussel static criterion with τ_s(0) only; the median 1.4 is the structuration gain accrued during the print (the printed layers are older than the rheometer sample). By failure mode: elastic_buckling 1.525, other 2.27, plastic_collapse 1.393, surface_tearing 0.846, unknown 1.066.

Printable runs that reached their target height (not stack-to-failure): R median 0.8283, p90 6.716 (n 402).

## How well does τ_s alone separate collapse from success?

Logistic fit of collapse on log10 R over 611 printable/collapsed runs (118 papers, 174 collapses): **AUC 0.591** — weak. Collapse rate by R bin:

| R | n | collapse rate |
|---|---|---|
| 0–0.25 | 97 | 0.155 |
| 0.25–0.5 | 89 | 0.112 |
| 0.5–1 | 123 | 0.325 |
| 1–2 | 118 | 0.39 |
| 2–4 | 72 | 0.472 |
| 4–8 | 51 | 0.373 |
| 8–∞ | 61 | 0.164 |

Reasons: (i) the tabulated static yield stress mixes rest protocols (0–1200 s rest, vane/stress-growth/penetration/slump-derived); (ii) structuration during the print (Athix·t) is what actually carries tall stacks and only 8 stack-to-failure runs report τ_s, Athix and cycle time together; (iii) 20 % of stack-to-failure collapses are buckling, not plastic. Consequence for the calculator: the physics route (τ_s(0) + Athix·t, Suiker buckling) is the primary verdict, the empirical R_fail ECDF gives a probability band, and both are reported.

## Extrudability windows of printable runs (p10 / p50 / p90)

| property | printable n | p10 | p50 | p90 | failed n | failed p50 |
|---|---|---|---|---|---|---|
| static_yield_stress | 762 | 273.064 | 1185.999 | 4920.0 | 81 | 1600.0 |
| dynamic_yield_stress | 648 | 62.028 | 310.175 | 1226.212 | 69 | 432.2 |
| plastic_viscosity | 611 | 2.7 | 12.0 | 56.99 | 70 | 67.0 |
| flow_table_spread | 726 | 125.5 | 162.25 | 197.0 | 66 | 169.5 |
| mini_slump_flow_diameter | 116 | 51.5 | 155.0 | 237.5 | 20 | 152.0 |

Failed extrusions have higher medians for every property (viscosity 67 vs 12 Pa·s is the clearest), but the windows overlap; used as caution flags, not hard limits.

## Process defaults learned from printable runs

- layer_height_over_nozzle: p10 0.3618, p25 0.45, p50 0.5, p75 0.6667, p90 0.75 (n 3128)
- layer_width_over_nozzle: p10 1.0, p25 1.0, p50 1.1843, p75 1.5, p90 1.9817 (n 1864)
- print_speed_mm_s: p10 10.0, p25 20.0, p50 40.0, p75 60.0, p90 100.0 (n 4116)
- layer_cycle_time_s: p10 10.0, p25 20.0, p50 67.5, p75 400.0, p90 1200.0 (n 1066)
- open_time_min: p10 10.0, p25 30.0, p50 45.0, p75 72.0, p90 110.0 (n 389)
- fresh_density: p10 1197.9, p25 1765.25, p50 2035.0, p75 2102.5, p90 2250.0 (n 88)
- start_time_after_mixing_min: p10 0.0, p25 5.0, p50 15.0, p75 30.0, p90 50.0 (n 802)
- nozzle_eq_mm: p10 9.4407, p25 15.0, p50 20.0, p75 26.2212, p90 31.9154 (n 6073)
- layer_height_mm: p10 5.0, p25 9.0, p50 10.0, p75 15.0, p90 20.0 (n 3593)

- Athix / τ_s(0) among printed mixes with both: median 0.0007 1/s (n 140); fallback ratio when no Athix is available.