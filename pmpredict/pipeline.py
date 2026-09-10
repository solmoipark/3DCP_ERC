"""Orchestration of the data steps: DB -> composition -> features -> targets."""
from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd

from . import features as FE
from .composition import compose_all
from .config import CONFIGS_DIR, PipelineConfig
from .db import load_tables
from .targets import build_targets, load_target_rules

log = logging.getLogger("pmpredict.pipeline")


def build_features(cfg: PipelineConfig, refresh: bool = False, qa: bool = True) -> dict:
    t0 = time.time()
    cfg.ensure_dirs()
    T = load_tables(cfg, refresh=refresh)
    wide, qa_df, long = compose_all(T)
    wide.to_parquet(cfg.data_dir / "composition.parquet", index=False)
    long.to_parquet(cfg.data_dir / "composition_long.parquet", index=False)
    qa_df.to_csv(cfg.data_dir / "composition_qa.csv", index=False)
    mat_ox = FE.build_material_oxides(T)
    mat_ph = FE.build_material_phys(T)
    med = FE.build_class_medians(mat_ox, mat_ph)
    (cfg.data_dir / "class_medians.json").write_text(json.dumps(med, indent=1), encoding="utf-8")
    mat_ox.to_parquet(cfg.data_dir / "material_oxides.parquet", index=False)
    mat_ph.to_parquet(cfg.data_dir / "material_phys.parquet", index=False)
    ctx = FE.build_context(T, cfg.use_mixing_protocol)
    F = FE.featurize_frame(wide, long, mat_ox, mat_ph, ctx, med)
    schema = FE.schema_of(F, FE.file_hash(CONFIGS_DIR / "material_groups.yaml"),
                          FE.file_hash(cfg.data_dir / "class_medians.json"))
    (cfg.data_dir / "feature_schema.json").write_text(json.dumps(schema, indent=1), encoding="utf-8")
    F.to_parquet(cfg.data_dir / "features.parquet", index=False)
    summary = dict(
        n_mixes=int(len(T["mixes"].drop_duplicates("mix_uid"))), n_normalised=int(len(wide)),
        modes=qa_df["mode"].value_counts().to_dict(), n_features=len(schema["columns"]), schema_hash=schema["hash"],
        water_b_available=float(wide["water_b"].notna().mean()), chem_coverage_ge_0p8=float((F["chem_coverage"] >= 0.8).mean()),
        curing_known=float((F["curing_type"].astype(str) != "unknown").mean()), seconds=round(time.time() - t0, 1),
    )
    m = wide.merge(T["mixes"][["mix_uid", "w_b_reported"]].drop_duplicates("mix_uid"), on="mix_uid")
    c = m[(m["water_b_source"] == "computed") & m["w_b_reported"].notna()]
    d = (c["water_b"] - c["w_b_reported"]).abs()
    summary["wb_agree_0p02"] = float((d <= 0.02).mean()) if len(c) else None
    summary["wb_agree_0p05"] = float((d <= 0.05).mean()) if len(c) else None
    if qa:
        top = qa_df["flags"].fillna("").str.split(";").explode()
        summary["top_flags"] = top[top != ""].value_counts().head(12).to_dict()
    (cfg.data_dir / "build_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    log.info("build-features done: %s", summary)
    return summary


def write_summary(cfg: PipelineConfig) -> str:
    """Render artifacts/reports/summary.md from manifest.json (one row per trained model)."""
    p = cfg.artifacts_dir / "manifest.json"
    if not p.exists():
        return ""
    man = json.loads(p.read_text(encoding="utf-8"))
    rows = pd.DataFrame(man["models"]).T.sort_values(["variant", "target"])
    fs = json.loads((cfg.data_dir / "build_summary.json").read_text(encoding="utf-8")) \
        if (cfg.data_dir / "build_summary.json").exists() else {}
    lines = ["# pmpredict — model summary", "",
             f"Updated {man.get('updated', '')}. Feature schema `{fs.get('schema_hash', '?')}`, "
             f"{fs.get('n_normalised', '?')} normalised mixes, {fs.get('n_features', '?')} features.", "",
             "Metrics are out-of-fold under **GroupKFold by paper** (5 folds); intervals are 80 % after split-conformal "
             "scaling. R² is on the original scale (dominated by extreme values for heavy-tailed targets); "
             "R²(log) and Spearman describe the model's ranking power on the modelled (log) scale. "
             "`weak` flags models with n < 300, interval coverage < 0.65 or R²(log) < 0.15 — use their predictions as "
             "order-of-magnitude guidance only. `leak_gap` = R² gain a random KFold would have (falsely) reported.", "",
             "| target | variant | unit | n rows | papers | tier | R² | R²(log) | Spearman | RMSE | MAE | medAPE | cov80 | Ridge R² | weak | leak_gap |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in rows.iterrows():
        f = lambda v, d=3: ("" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{float(v):.{d}f}")
        lines.append(f"| {r['target']} | {r['variant']} | {r['unit']} | {int(r['n_train'])} | {int(r['n_papers'])} | {r['tier']} | "
                     f"{f(r.get('r2'))} | {f(r.get('r2_log'))} | {f(r.get('spearman'))} | {f(r.get('rmse'), 2)} | {f(r.get('mae'), 2)} | "
                     f"{f(r.get('medape'))} | {f(r.get('coverage80'), 2)} | {f(r.get('ridge_r2'))} | "
                     f"{'yes' if r.get('weak_model') else ''} | {f(r.get('leakage_gap_r2'))} |")
    lines += ["", "## Slices", "Per-target slice metrics (age, specimen geometry, binder family, 3DCP) are in "
              "`artifacts/reports/<target>_slices.csv`; feature importances in `artifacts/models/<target>/importance.csv`."]
    md = "\n".join(lines) + "\n"
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    (cfg.reports_dir / "summary.md").write_text(md, encoding="utf-8")
    return md


def build_target_table(cfg: PipelineConfig, only: list[str] | None = None) -> pd.DataFrame:
    from .targets import build_test_covariates
    T = load_tables(cfg, tables=["measurements", "tests", "test_protocols"])
    rules, meta = load_target_rules()
    long, qa = build_targets(T, rules, meta, only=only)
    if meta.get("curve_augment_rheology", True) and (only is None or
                                                       {"dynamic_yield_stress", "plastic_viscosity", "structuration_rate_athix"} & set(only)):
        from .curves import augment_athix_targets, augment_rheology_targets
        long, summ = augment_rheology_targets(long, cfg.db_path)
        long, summ2 = augment_athix_targets(long, cfg.db_path)
        summ["added"].update(summ2.get("added", {}))
        for tgt, s in summ.get("added", {}).items():
            if tgt in set(qa["target"]):
                qa.loc[qa["target"] == tgt, "curve_rows_added"] = s["rows"]
                qa.loc[qa["target"] == tgt, "curve_papers_added"] = s["papers"]
    age_targets = ("drying_shrinkage", "autogenous_shrinkage", "compressive_strength", "flexural_strength")
    if meta.get("curve_augment_age_series", False) and (only is None or set(age_targets) & set(only)):
        from .curves import augment_age_series_targets
        excl = tuple(meta.get("age_series_exclude_curve_types") or ())
        allow_bars = set(meta.get("age_series_bars_targets") or ())  # targets that may also use excluded patterns
        wanted = [t for t in age_targets if only is None or t in only]
        groups = [(tuple(t for t in wanted if t not in allow_bars), excl), (tuple(t for t in wanted if t in allow_bars), ())]
        for tg, ex in groups:
            if not tg:
                continue
            long, summ3 = augment_age_series_targets(long, cfg.db_path, grid=meta.get("age_grid"), targets=tg,
                                                     exclude_curve_types=ex)
            for tgt, s in summ3.get("added", {}).items():
                if tgt in set(qa["target"]):
                    qa.loc[qa["target"] == tgt, "curve_rows_added"] = s["rows"]
                    qa.loc[qa["target"] == tgt, "curve_papers_added"] = s["papers"]
    long.to_parquet(cfg.data_dir / "targets.parquet", index=False)
    qa.to_csv(cfg.data_dir / "targets_qa.csv", index=False)
    build_test_covariates(T).to_parquet(cfg.data_dir / "test_covariates.parquet", index=False)
    return qa
