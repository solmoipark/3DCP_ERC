# pmpredict

Property prediction and inverse mix design for cement paste and mortar, trained on a validated
literature database (2,124 papers, 22,616 mixes, 174,565 measurements; `master.db` of the
pastemortar extraction package, opened read-only).

- **Forward**: mix composition + conditions (age, specimen geometry, curing) → properties with 80 %
  prediction intervals. One LightGBM bundle per target (point + q10/q90 quantile models, split-conformal
  scaling, paper-bootstrap ensemble), evaluated with **GroupKFold by paper** (no leakage from same-paper mixes).
- **Inverse**: target requirements → candidate mix designs (Sobol sweep → probabilistic screening →
  non-dominated sort → diverse shortlist → differential-evolution refinement over the forward models) **plus**
  real published mixes near the target, with closest published analogues for every candidate.

## Install

```bash
git clone https://github.com/solmoipark/3DCP_ERC.git
cd 3DCP_ERC
pip install -r requirements.txt      # runtime (UI, predict, design)
pip install -e .                     # optional: the `pmpredict` command
```

The repository ships everything the UI, `predict` and `design` need: trained models (`artifacts/models/`,
54 MB), feature/target/composition caches and the paper/mix tables (`data/`), and the digitised-curve caches.
The literature database itself (`master.db`, 174 MB, not in git) is only required to **rebuild** features,
targets or models; point to it with `configs/pipeline.yaml` (`db_path`, relative to the repo root),
the `PMPREDICT_DB` environment variable, or `--db`.

## Run the web UI

```bash
streamlit run app/streamlit_app.py        # http://localhost:8501   (or: pmpredict ui)
```

Share it on a local network with `--server.address 0.0.0.0` (open port 8501 in the firewall). To host it on
**Streamlit Community Cloud**: sign in with the GitHub account that owns this repository → *New app* →
repository `solmoipark/3DCP_ERC`, branch `main`, main file `app/streamlit_app.py` (Python 3.12). The cloud
installs `requirements.txt`; no database or secrets are needed.

## Pipeline

```bash
pmpredict build-features --qa           # DB -> data/composition.parquet, features.parquet, feature_schema.json
pmpredict build-targets                 # measurements -> data/targets.parquet (unit harmonisation, replicate/condition rules)
pmpredict train --target all --variant both      # grouped CV + fit + artifacts/models/<target>/ + manifest + reports/summary.md
pmpredict info                          # configuration, feature build summary, model table
```

## Predict

```bash
pmpredict predict --mix examples/opc_mortar.json --targets compressive_strength,flexural_strength
```

Input is a `MixSpec` JSON (see `pmpredict/schema.py`): components as `material_class` + `amount`
(mass fraction of total powder, powder amounts summing to 1; sand as mass/powder; admixtures as mass/powder),
`water_binder`, optional material properties (`props.oxides`, `blaine_m2kg`, `sg`, ...) and `conditions`
(`age_d`, `comparability_group`, curing). Output per target: q50 with [q10, q90], epistemic std, model
metadata and applicability flags.

## Web UI pages

**모델 현황** (model table with grouped-CV quality and weak flags), **성능 예측** (build a mix with material
pickers, w/b, s/b, admixtures, conditions → predictions with 80 % intervals and downloadable MixSpec JSON),
**유동 곡선** (Bingham flow curve τ(γ̇) with band and published analogue curves), **구조화 곡선** (static yield
stress vs rest time, τ_s(0) + Athix·t), **역설계** (edit targets and search space in tables → candidates,
Pareto / parallel-coordinate plots, published analogues, report download), **문헌 검색** (published mixes near
a target, no models needed).

## Inverse design

```bash
pmpredict init-spec --template 3dcp_printable_mortar --out my_spec.yaml   # also: hpc_paste, low_carbon_mortar
pmpredict retrieve --spec my_spec.yaml -n 20          # published mixes only (no models needed)
pmpredict design --spec my_spec.yaml --out artifacts/reports/design/my_spec
```

A design spec lists **targets** (`ge`/`le`/`range`/`goal`/`minimize`/`maximize` with units and
conditions, optional per-target `p_min`; curve targets `shear_stress_at_rate` with `conditions.shear_rate_1s`
and `static_yield_stress_at_rest` with `conditions.rest_time_s` — see `examples/spec_flowcurve_mortar.yaml`), the **space** (system type, w/b and s/b ranges, allowed binder
classes with bounds, admixtures, fixed curing), **objectives** (`cost`, `co2`, `clinker_fraction`,
`co2_per_mpa`, `cost_per_mpa`) and **risk** (`p_min`, `ad_max`). The report (`report.md`, `result.json`,
`candidates.csv`, `literature.csv`, `pareto.png`, `parallel_coords.png`, one JSON per candidate) states
every model's out-of-fold quality, flags weak models, records any threshold relaxation, and marks the
placeholder cost/CO₂ tables (`configs/*_default.yaml` — replace with your own via `--cost-table/--co2-table`).

`pmpredict validate-design --n 50` runs the closed-loop test (real mixes → their measured values as
targets → does the optimiser land near the true composition, is the true mix judged feasible, is it retrieved).

## Model quality (grouped CV, see `artifacts/reports/summary.md`)

Models are trained on tabulated values plus values read off digitised figure curves (strength/shrinkage vs
age at a standard age grid, Bingham parameters from flow curves, Athix from structuration curves; rows carry
`value_kind_mode = curve_derived`). Composition explains **strength** well across 1,325 papers (compressive
strength: 44,383 rows, R² 0.51 / R²(log) 0.42 / Spearman 0.69; flexural R²(log) 0.25; direct tensile R² 0.50).
**Shrinkage** became usable through the curve data (drying R²(log) 0.51 / Spearman 0.74, autogenous 0.39 / 0.62).
Porosity, water absorption, density and heat are modest (R² 0.23–0.32). **Fresh-state properties** (flow,
setting, yield stress, viscosity, Athix) are dominated by paper-level protocol effects the database cannot
encode: they have ranking power on the log scale at best (plastic viscosity Spearman 0.65, setting times ≈0.5)
and are flagged `weak` when uninformative — for these, treat the retrieved published mixes as the primary
evidence. Closed-loop check on 73 held-out published mixes: measured values inside the 80 % intervals 75 %,
the true mix retrieved from the literature tier 100 %; the inverse problem is many-to-one, so candidates are
alternatives anchored by the published analogues.

## Layout

- `pmpredict/` — `db.py`, `vocab.py`, `composition.py` (dosage → mass fractions of powder; 95.8 % of mixes),
  `features.py` (shared `featurize_frame`), `targets.py`, `models.py`, `train.py`, `evaluate.py`, `predict.py`,
  `reconstruct.py`, `design/` (`spec`, `units`, `space`, `domain`, `uncertainty`, `objectives`, `optimize`,
  `retrieve`, `report`, `plots`, `validate`), `cli.py`.
- `configs/` — `material_groups.yaml` (139 classes → groups), `targets.yaml`, `model_defaults.yaml`,
  cost/CO₂ placeholder tables. `tests/` (`pytest tests/`; `pytest tests/slow -m slow` for end-to-end).
- `data/`, `artifacts/` — generated by the pipeline and **committed** so the UI runs from a clone (the raw
  measurement/component tables and out-of-fold prediction files are git-ignored). `claude-memory/progress.md` —
  build log and decisions.
