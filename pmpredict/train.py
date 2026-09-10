"""Assemble per-target datasets, run grouped CV, fit and save model bundles."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .config import PipelineConfig
from .evaluate import cross_validate_target, gain_importance, slice_metrics
from .models import TargetModel, fit_bundle, model_defaults, param_tier
from .schema import COMPARABILITY_GROUPS
from .targets import load_target_rules

log = logging.getLogger("pmpredict.train")

CG_LEVELS = COMPARABILITY_GROUPS + ["unknown"]


def load_feature_table(cfg: PipelineConfig) -> tuple[pd.DataFrame, dict]:
    F = pd.read_parquet(cfg.data_dir / "features.parquet")
    schema = json.loads((cfg.data_dir / "feature_schema.json").read_text(encoding="utf-8"))
    for c, lv in schema["categorical_levels"].items():
        F[c] = pd.Categorical(F[c].astype("object"), categories=lv)
    return F, schema


def assemble(target: str, cfg: PipelineConfig, rule: dict, F: pd.DataFrame, schema: dict,
             variant: str = "general") -> dict:
    """Join target rows with mix features; append covariates; return arrays for training."""
    TL = pd.read_parquet(cfg.data_dir / "targets.parquet")
    t = TL[TL["target"] == target].drop(columns=["paper_uid"])
    df = t.merge(F, on="mix_uid", how="inner")
    if variant == "3dcp":
        df = df[df["is_3dcp"] == 1]
    # plausibility guard on the key composition variable
    df = df[df["water_b"].isna() | ((df["water_b"] >= 0.05) & (df["water_b"] <= 3.0))]
    cov = rule.get("covariates") or []
    feat = list(schema["columns"])
    cat_levels = dict(schema["categorical_levels"])
    if "age_d" in cov:
        df["log_age"] = np.log(df["age_d"].clip(lower=1e-3))
        feat += ["age_d", "log_age"]
    if "comparability_group" in cov:
        cg = df["comparability_group"].astype("object").where(df["comparability_group"].isin(COMPARABILITY_GROUPS), "unknown")
        df["comparability_group"] = pd.Categorical(cg, categories=CG_LEVELS)
        feat.append("comparability_group"); cat_levels["comparability_group"] = CG_LEVELS
    if "rest_time_s" in cov:
        feat += ["rest_time_s", "rest_time_known"]
    if "test_protocol" in cov:
        from .targets import TP_GEOMETRY, TP_METHODS, TP_NUMERIC
        tc = pd.read_parquet(cfg.data_dir / "test_covariates.parquet")
        df = df.merge(tc, on="test_uid", how="left")
        num = [f for f, _ in TP_NUMERIC.values()]
        feat += num
        df["tp_geometry"] = pd.Categorical(df["tp_geometry"].astype("object").fillna("unknown"), categories=TP_GEOMETRY)
        df["tp_method"] = pd.Categorical(df["tp_method"].astype("object").fillna("unknown"), categories=TP_METHODS)
        feat += ["tp_geometry", "tp_method"]
        cat_levels["tp_geometry"] = TP_GEOMETRY
        cat_levels["tp_method"] = TP_METHODS
    df = df.reset_index(drop=True)
    groups = df["paper_uid"].to_numpy()
    if cfg.paper_weighting == "sqrt":
        cnt = df.groupby("paper_uid")["mix_uid"].transform("size").to_numpy()
        w = 1.0 / np.sqrt(cnt)
    else:
        w = None
    return dict(df=df, X=df[feat], y=df["value"].to_numpy(float), groups=groups, w=w,
                feature_names=feat, cat_levels=cat_levels)


def train_target(target: str, cfg: PipelineConfig, variant: str = "general", do_cv: bool = True,
                 leakage_check: bool = False, n_boot: int | None = None) -> dict | None:
    rules, _ = load_target_rules()
    if target not in rules:
        raise KeyError(f"unknown target {target}; known: {sorted(rules)}")
    rule = rules[target]
    d = model_defaults()
    F, schema = load_feature_table(cfg)
    A = assemble(target, cfg, rule, F, schema, variant)
    df, X, y, groups, w = A["df"], A["X"], A["y"], A["groups"], A["w"]
    n_papers = int(pd.Series(groups).nunique())
    if len(y) < 30 or n_papers < d.get("min_papers_for_cv", 10):
        log.warning("%s/%s: too little data (%d rows, %d papers) - skipped", target, variant, len(y), n_papers)
        return None
    tier, params = param_tier(len(y), n_papers, d)
    transform = rule.get("transform", "none")
    t0 = time.time()
    cv = None
    report = {}
    if do_cv:
        cv = cross_validate_target(X, y, groups, w, params, transform, cfg.seed, A["feature_names"], A["cat_levels"],
                                   n_splits=d.get("cv_folds", 5), defaults=d)
        report = dict(cv["metrics"])
        oof = cv["oof"]
        sl = []
        for by in ["age_d", "comparability_group", "binder_family", "system_type", "is_3dcp", "curing_type"]:
            if by in df.columns:
                sl.append(slice_metrics(oof, df, by))
        slices = pd.concat(sl, ignore_index=True) if sl else pd.DataFrame()
        if leakage_check:
            rnd = cross_validate_target(X, y, groups, w, params, transform, cfg.seed, A["feature_names"], A["cat_levels"],
                                        n_splits=d.get("cv_folds", 5), defaults=d, baselines=False, random_kfold=True)
            report["r2_random_kfold"] = rnd["metrics"]["r2"]
            report["leakage_gap_r2"] = rnd["metrics"]["r2"] - report["r2"]
        rep_dir = cfg.reports_dir
        rep_dir.mkdir(parents=True, exist_ok=True)
        tag = target if variant == "general" else f"{target}__{variant}"
        oof.assign(mix_uid=df["mix_uid"], paper_uid=df["paper_uid"]).to_parquet(rep_dir / f"oof_{tag}.parquet", index=False)
        slices.to_csv(rep_dir / f"{tag}_slices.csv", index=False)
    # final fit on all rows
    point, q_lo, q_hi, ens, best = fit_bundle(
        X, y, groups, w, params, transform, cfg.seed, n_boot=d.get("bootstrap_ensemble", 10) if n_boot is None else n_boot,
        best_iter=(cv["metrics"]["best_iter_median"] if cv else None), defaults=d)
    scale = cv["conformal_scale"] if cv else 1.0
    Xn = X.select_dtypes("number")
    ranges = {c: [float(Xn[c].quantile(0.01)), float(Xn[c].quantile(0.99))] for c in Xn.columns if Xn[c].notna().any()}
    meta = dict(
        target=target, variant=variant, unit=rule.get("unit", ""), n_train=int(len(y)), n_mixes=int(df["mix_uid"].nunique()),
        n_papers=n_papers, tier=tier, params=dict(params, n_estimators=best), transform=transform,
        feature_schema_hash=schema["hash"], featurizer_version=schema.get("featurizer_version"),
        package_version=__version__, created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        cv=report, feature_ranges=ranges,
        age_support=(dict(min=float(df["age_d"].min()), max=float(df["age_d"].max()),
                          common=[float(a) for a in df["age_d"].value_counts().head(8).index]) if "age_d" in df.columns else None),
        categorical_levels=A["cat_levels"], covariates=rule.get("covariates") or [],
        train_time_s=round(time.time() - t0, 1),
    )
    tm = TargetModel(target=target, unit=meta["unit"], transform=transform, feature_names=A["feature_names"],
                     cat_levels=A["cat_levels"], point=point, q_lo=q_lo, q_hi=q_hi, ensemble=ens,
                     conformal_scale=scale, meta=meta)
    out_dir = cfg.models_dir / (target if variant == "general" else f"{target}__{variant}")
    tm.save(out_dir)
    (out_dir / "train_mix_uids.txt").write_text("\n".join(df["mix_uid"].astype(str)), encoding="utf-8")
    gain_importance(point, A["feature_names"]).to_csv(out_dir / "importance.csv", index=False)
    update_manifest(cfg, meta, str(out_dir.relative_to(cfg.artifacts_dir)))
    log.info("%s/%s: n=%d papers=%d tier=%s R2=%.3f RMSE=%.3g cov80=%.2f (%.0fs)", target, variant, len(y), n_papers,
             tier, report.get("r2", np.nan), report.get("rmse", np.nan), report.get("coverage_conformal", np.nan),
             time.time() - t0)
    return meta


def update_manifest(cfg: PipelineConfig, meta: dict, rel_path: str) -> None:
    p = cfg.artifacts_dir / "manifest.json"
    man = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"models": {}}
    key = meta["target"] if meta["variant"] == "general" else f"{meta['target']}__{meta['variant']}"
    man["models"][key] = manifest_entry(meta, rel_path)
    man["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p.write_text(json.dumps(man, indent=1), encoding="utf-8")


def manifest_entry(meta: dict, rel_path: str) -> dict:
    cv = meta.get("cv", {})
    r2_log = cv.get("r2_t")
    weak = (meta["n_train"] < 300) or (cv.get("coverage_conformal") or 1.0) < 0.65 or \
        ((r2_log if r2_log is not None else cv.get("r2", 0)) or 0) < 0.15
    return dict(path=rel_path, target=meta["target"], variant=meta["variant"], unit=meta["unit"],
                n_train=meta["n_train"], n_papers=meta["n_papers"], tier=meta["tier"], transform=meta.get("transform"),
                feature_schema_hash=meta["feature_schema_hash"], created=meta["created"],
                r2=cv.get("r2"), r2_log=r2_log, spearman=cv.get("spearman"), rmse=cv.get("rmse"), mae=cv.get("mae"),
                medape=cv.get("medape"), rel_width=cv.get("rel_width"), coverage80=cv.get("coverage_conformal"),
                ridge_r2=cv.get("ridge_r2"), knn_r2=cv.get("knn_r2"), leakage_gap_r2=cv.get("leakage_gap_r2"),
                weak_model=bool(weak))


def rebuild_manifest(cfg: PipelineConfig) -> dict:
    """Recreate manifest.json from every saved model directory."""
    man = {"models": {}}
    for d in sorted(cfg.models_dir.glob("*")):
        mp = d / "meta.json"
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
            key = meta["target"] if meta.get("variant", "general") == "general" else f"{meta['target']}__{meta['variant']}"
            man["models"][key] = manifest_entry(meta, str(d.relative_to(cfg.artifacts_dir)))
    man["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (cfg.artifacts_dir / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return man
