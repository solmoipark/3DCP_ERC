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
The literature database is included compressed as `data/master.db.xz` (13 MB; 174 MB unpacked). It is only
required to **rebuild** features, targets or models: the first command that needs it unpacks it to
`data/master.db` automatically. To use another copy, set `db_path` in `configs/pipeline.yaml` (relative to
the repo root), the `PMPREDICT_DB` environment variable, or `--db`. After changing the database, refresh the
bundle with `xz -9 -k master.db` (or Python `lzma`) and commit the new `data/master.db.xz`.

## AI agent (chat-first UI and `pmpredict agent`)

사용 설명서(한국어): [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)

```bash
pip install -e ".[agent]"                 # anthropic, openai, mcp, claude-agent-sdk, openpyxl
pmpredict agent --check                   # which LLM backend will be used and why
pmpredict agent                           # REPL (commands: /new /sessions /artifacts /quit)
pmpredict agent -p "w/b 0.35 3DCP 모르타르의 정적항복응력과 28일 압축강도 예측해줘"
streamlit run app/streamlit_app.py        # chat UI (or: pmpredict ui)
```

The web app is now a chat: you describe the mix, the target performance, or the print job in Korean (or English) and the
agent calls the package's functions as tools, quotes every number from those results with its 80 % interval, and
renders tables, figures and reports inline with download buttons. The former form pages are still available through the
sidebar toggle "직접 실행 (기존 폼)".

**Backends** (`pmpredict/agent/providers/`), auto-detected in this order and selectable in the sidebar or with `--provider`:

| provider | needs | notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` or `anthropic_api_key` in the pastemortar `config.json` | default; streaming, prompt caching, `claude-sonnet-5` (option `claude-opus-5`) |
| `openai` | `OPENAI_API_KEY` or `openai_api_key` in the same file | function calling; model via `PMPREDICT_OPENAI_MODEL` |
| `claude_sdk` | Claude Pro/Max login of the bundled Claude Code CLI: `python -m pmpredict.cli agent --check` prints the exact `claude.exe auth login` command | personal local use only (headless use draws from a separate weekly pool); never deploy publicly on this path |
| `codex` | `npm i -g @openai/codex` and `codex login` (ChatGPT subscription) | tools are served over MCP (`pmpredict agent-mcp`) to `codex exec --json` |
| `fake` | nothing | scripted provider for tests and UI smoke runs |

Keys are read from the environment or from `C:\Users\User\pastemortar_extraction_package_v1.2.2\config.json`
(`PMPREDICT_SECRETS_FILE` to change) and never printed, logged or stored in the repository.

**Tools** (`pmpredict/agent/tools/`, one registry projected to Anthropic / OpenAI / MCP schemas): `list_models`,
`describe_vocabulary`, `build_mix_spec`, `predict_properties`, `flow_curve`, `structuration_curve`, `retrieve_literature`,
`design_mix` (slow), `assess_buildability`, `print_schedule`, `similar_prints`, `design_for_print_job` (slow),
`describe_schema`, `sql_query` (SELECT-only, authorizer-guarded, 20 s / 200 rows), `save_report` (md/xlsx),
`remember` (durable notes). Sessions and notes live under `~/.pmpredict/agent/` (`PMPREDICT_HOME`); artifacts under
`artifacts/reports/agent/<session>/` (git-ignored). The MCP server (`python -m pmpredict.agent.mcp_server`) can also be
attached to any MCP client (Claude Code, Codex, Cursor).

## Run the web UI

```bash
streamlit run app/streamlit_app.py        # http://localhost:8501   (or: pmpredict ui) — chat-first; form pages behind the sidebar toggle
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

## Buildability & print schedule (nozzle + geometry → mix requirement, layer cycle time, verdict)

```bash
pmpredict init-job --out my_job.yaml                                   # template: object, height, nozzle, speed, open time
pmpredict buildability --job examples/print_job_wall.yaml --tau-s0 3000 --athix 1.5 --out artifacts/reports/buildability/wall
pmpredict buildability --job examples/print_job_cylinder.yaml --mix examples/opc_mortar.json      # fresh state predicted by pmpredict
pmpredict buildability --job examples/print_job_cylinder.yaml --design --space examples/space_3dcp_design.yaml --out artifacts/reports/buildability/cyl
```

`pmpredict/buildability.py` turns a **print job** (`PrintJob`: object type, target height, wall length or cylinder
diameter, nozzle size, layer height/width, print speed or layer cycle time, start time after mixing, open time, load
safety factor) and a **fresh material** (`FreshMaterial`: static yield stress at deposition τ_s(0), structuration rate
Athix, fresh density, green-modulus ratio E/τ_s; measured, or predicted from a `MixSpec`) into

- a **verdict** (`printable` / `borderline` / `non_printable` with the governing mode and reasons): Roussel plastic
  collapse ρgH ≤ √3·τ_s(t) with τ_s(t) = τ_s(0) + Athix·t evaluated as the stack grows (n_max with and without the
  safety factor), Suiker self-weight buckling of a free straight wall (E grows with τ_s; closed sections are stiffer and
  skipped), open-time check, and extrudability flags (τ_s, dynamic yield stress, viscosity against the p10–p90 window of
  printable runs for the nozzle class);
- a **schedule window**: minimum layer cycle time for stability, maximum from the open time (or the p90 of printable
  runs), a recommended cycle time and total print time, the matching print-speed window for the path length, the
  critical cycle time beyond which stacking is unlimited, and the τ_s(0)/Athix required for the current schedule;
- the **closest published prints** (nozzle, layer height, height, τ_s) with their outcome and label;
- with `--design`, an **inverse design**: the Roussel requirement becomes a `static_yield_stress_at_rest ≥ sf·ρgH/√3`
  target at rest time = print duration (τ_s(0) + Athix·t through the two models), τ_s(0) is boxed into the
  extrudability window of the nozzle class, viscosity is capped at its p90, Athix is maximised as a steering objective,
  and every candidate mix is re-assessed with its own predicted fresh state (`candidates_buildability.csv`, ranked by
  verdict and P(stands)).

Calibration comes from the print01 label set of the literature extraction (1,014 3DCP papers, 7,420 print runs with
printability labels, `scripts/calibrate_buildability.py` → `configs/buildability_calibration.json`,
`data/print_runs.parquet`, report `artifacts/reports/buildability_calibration.md`): the ratio R = ρgH/(√3·τ_s) at collapse
in 146 stack-until-failure tests (median 1.39, IQR 0.64–2.87) gives the empirical collapse probability shown next to the
physics verdict; τ_s alone separates collapse from success with AUC 0.59 only, because tabulated static yield stresses
mix rest protocols and structuration during the print carries tall stacks. The rheology models are wide (80 % intervals
span more than a decade), so P(stands) from the predicted band is honest but low; treat the retrieved printable mixes
as the primary evidence and the design candidates as directions. Web UI page: **빌더빌리티·스케줄**.

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
