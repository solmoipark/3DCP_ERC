# Buildability assessment — wall_1m

**Verdict: NON_PRINTABLE** (governing: elastic_buckling)

- plastic collapse expected at layer 51 of 80 (H_max 639 mm < 1000 mm)
- self-weight buckling of a free straight wall expected at layer 18 (thickness 59 mm, E = 25 x tau_s; closed or braced paths are stiffer: set check_buckling false or add wall_filaments)
- print duration 80 min + start 10 min exceeds open time 60 min

## Job

| item | value |
|---|---|
| object | wall, target height 1000 mm, wall 2 filament(s) |
| nozzle | 25.0 mm equivalent |
| layer | h 12.5 mm × w 30.0 mm → 80 layers |
| schedule | cycle time 60 s (speed 50.0 mm/s, path 3000 mm) → print 80 min |
| open time | 60 min, start 10 min after mixing → EXCEEDED |

## Material

| item | value |
|---|---|
| τ_s(0) | 3000 Pa (user) |
| Athix | 1.500 Pa/s |
| τ_s at end of print | 10200 Pa |
| fresh density | 2100 kg/m³, E/τ_s 25 |

## Stability

| criterion | value |
|---|---|
| plastic collapse n_max (sf 1 / sf 1.5) | 51 / 23 layers (target 80) |
| buckling n_max (free wall) | 18 |
| H_max | 225 mm |
| static ratio R = ρgH/(√3 τ_s0) | 3.96 → empirical collapse probability 82 % (ECDF of 146 published stack-to-failure collapses, median R 1.39) |
| P(stands) over the material band | — % |
| required for this schedule | τ_s(0) ≥ 10641 Pa at Athix 1.500, or Athix ≥ 3.092 Pa/s at τ_s(0) 3000 |

## Schedule window

| item | value |
|---|---|
| layer cycle time | min 124 s (sf 1.5; 74 s without) · max 38 s (open time 60 min - start 10 min over 80 layers) · current 60 s |
| recommended | — s per layer → — min total — **no feasible window**: raise τ_s(0)/Athix, lower the layer height, or extend the open time |
| critical cycle time (unlimited stacking) | 99 s |
| print speed for the path | none: stability needs ≤ 24.3 mm/s, the time bound needs ≥ 80.0 mm/s (current 50.0) |
| static_yield_stress vs printable runs | 3e+03 — inside (nozzle 15-30 mm: p10 195, p50 1.12e+03, p90 4.7e+03) |

## Assumptions

- layer_height_mm = 12.5 (0.5 x nozzle, printable median)
- layer_width_mm = 29.61 (1.2 x nozzle, printable median)
- layer_cycle_time_s = 60.0 (path 3000 mm / 50 mm/s + dwell 0 s)

## Closest published prints

| DOI | mix | object | nozzle | h | layers / H | cycle | outcome | label | τ_s |
|---|---|---|---|---|---|---|---|---|---|
| 10.1080/17452759.2018.1555046 | 3DPFRCC | free-form | 23.9 | 10.0 | — / 900 | — | printable | printable | 3289 |
| 10.1016/j.heliyon.2022.e11598 | PCM-3DPC | hollow cylinder | 25.0 | 10.0 | 74 / 740 | 13 | collapsed (stack-to-failure) | printable | 3051 |
| 10.1016/j.conbuildmat.2017.12.112 | Mixture A | free-form | 20.0 | 10.0 | 80 / 800 | — | printable | printable | 3350 |
| 10.1016/j.rineng.2024.102112 | LC | hollow cylinder | 25.0 | 10.0 | 74 / 740 | — | collapsed (stack-to-failure) | printable | 2400 |
| 10.1016/j.rineng.2024.102112 | LCR | hollow cylinder | 25.0 | 10.0 | 90 / 900 | — | extrusion_failure (stack-to-failure) | borderline | 4499 |
| 10.1016/j.conbuildmat.2025.144187 | RFA-100 | hollow cylinder | 30.0 | 15.0 | — / 1000 | 19 | printable | printable | 1869 |
| 10.1016/j.jclepro.2026.148651 | LC2-100UWCF | hollow cylinder | 30.0 | 15.0 | 54 / 810 | 20 | collapsed (stack-to-failure) | non_printable | 1910 |
| 10.1016/j.jclepro.2026.148651 | RefMix | hollow cylinder | 30.0 | 15.0 | 64 / 1000 | 20 | printable | printable | 1800 |

Physics: Roussel (2018) plastic criterion with linear structuration, Suiker (2018) wall buckling; calibration and extrudability windows from the print01 label set (`configs/buildability_calibration.json`). Labels follow the authors' verdicts; τ_s protocols in the literature are mixed.