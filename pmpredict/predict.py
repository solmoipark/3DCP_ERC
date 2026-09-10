"""Predict properties for user-specified mixes (MixSpec) with the saved model bundles."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .composition import _to_record, normalize_mix
from .config import PipelineConfig
from .features import OX, PHYS_AGG, PHYS_FIB, PHYS_POWDER, featurize_frame
from .models import TargetModel
from .schema import COMPARABILITY_GROUPS, MixSpec

log = logging.getLogger("pmpredict.predict")
CG_LEVELS = COMPARABILITY_GROUPS + ["unknown"]


class Assets:
    """Lazy holder for the data-dir artefacts needed to featurize a MixSpec."""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.class_medians = json.loads((cfg.data_dir / "class_medians.json").read_text(encoding="utf-8"))
        self.schema = json.loads((cfg.data_dir / "feature_schema.json").read_text(encoding="utf-8"))
        p = cfg.artifacts_dir / "manifest.json"
        self.manifest = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"models": {}}
        self._models: dict[str, TargetModel] = {}

    def model(self, key: str) -> TargetModel:
        if key not in self._models:
            self._models[key] = TargetModel.load(self.cfg.artifacts_dir / self.manifest["models"][key]["path"])
        return self._models[key]

    def available_targets(self) -> list[str]:
        return sorted({m["target"] for m in self.manifest["models"].values()})


# ------------------------------------------------------- spec -> features
def _spec_material_tables(specs: list[MixSpec]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ox_rows, ph_rows = [], []
    for si, spec in enumerate(specs):
        for muid, p in spec.material_props().items():
            uid = f"{si}|{muid}"
            cls = next((c.material_class for i, c in enumerate(spec.components) if f"spec::{i}" == muid), None)
            if "oxides" in p:
                row = {"material_uid": uid, "material_class": cls, "chem_ok": True}
                row.update({o: float(p["oxides"].get(o, np.nan)) for o in OX})
                ox_rows.append(row)
            ph = {"material_uid": uid, "material_class": cls}
            for c in PHYS_POWDER + PHYS_AGG + PHYS_FIB + ["solid_content_pct"]:
                if c in p:
                    ph[c] = float(p[c])
            if "fibre_length_mm" in p:
                ph["fibre_length_mm"] = float(p["fibre_length_mm"])
            if "fibre_diameter_um" in p:
                ph["fibre_diameter_um"] = float(p["fibre_diameter_um"])
            if len(ph) > 2:
                ph_rows.append(ph)
    ox_cols = ["material_uid", "material_class", "chem_ok"] + OX
    ph_cols = ["material_uid", "material_class"] + PHYS_POWDER + PHYS_AGG + PHYS_FIB + ["solid_content_pct"]
    mat_ox = pd.DataFrame(ox_rows, columns=ox_cols) if ox_rows else pd.DataFrame(columns=ox_cols)
    mat_ph = pd.DataFrame(ph_rows, columns=ph_cols) if ph_rows else pd.DataFrame(columns=ph_cols)
    for c in PHYS_POWDER + PHYS_AGG + PHYS_FIB + ["solid_content_pct"]:
        if c not in mat_ph.columns:
            mat_ph[c] = np.nan
    mat_ph["agg_sg"] = mat_ph["sg"] if "sg" in mat_ph.columns else np.nan
    for c in ("silica_modulus", "density_solution"):
        if c not in mat_ph.columns:
            mat_ph[c] = np.nan
    return mat_ox, mat_ph


def featurize_specs(specs: list[MixSpec], assets: Assets) -> tuple[pd.DataFrame, list[list[str]]]:
    """Return (feature frame aligned to the training schema, per-spec warnings)."""
    recs, long, ctx, warns = [], [], [], []
    for si, spec in enumerate(specs):
        w = spec.validate()
        rows = spec.to_component_rows()
        rows["material_uid"] = [f"{si}|{m}" for m in rows["material_uid"]]
        mix_row = spec.to_mix_row()
        uid = f"{si}|{spec.name or 'mix'}"
        mix_row["mix_uid"] = uid
        comp = normalize_mix(rows, mix_row)
        if not comp.ok:
            raise ValueError(f"spec {spec.name!r} could not be normalised: {comp.flags}")
        r = mix_row.to_dict(); r["paper_uid"] = "spec"
        rec = _to_record(comp, r); rec["mix_uid"] = uid
        recs.append(rec)
        for m in comp.materials_long:
            long.append({"mix_uid": uid, **m})
        cd = spec.conditions
        ctx.append(dict(mix_uid=uid, paper_uid="spec", system_type=spec.system_type, curing_regime=cd.curing_regime,
                        curing_temp_C=cd.curing_temp_C, curing_rh_pct=cd.curing_rh_pct, is_3dcp=cd.is_3dcp,
                        year=spec.year, mix_time_s=cd.mix_time_s, max_rpm=cd.max_rpm, mixer_type=cd.mixer_type))
        warns.append(w + comp.flags)
    mat_ox, mat_ph = _spec_material_tables(specs)
    ctx_df = pd.DataFrame(ctx)
    ctx_df["mix_time_s"] = pd.to_numeric(ctx_df["mix_time_s"], errors="coerce")
    ctx_df["max_rpm"] = pd.to_numeric(ctx_df["max_rpm"], errors="coerce")
    F = featurize_frame(pd.DataFrame(recs), pd.DataFrame(long) if long else pd.DataFrame(
        columns=["mix_uid", "material_uid", "cls", "group", "family", "frac"]), mat_ox, mat_ph, ctx_df,
        assets.class_medians)
    # align to schema
    for c in assets.schema["columns"]:
        if c not in F.columns:
            F[c] = np.nan
    for c, lv in assets.schema["categorical_levels"].items():
        F[c] = pd.Categorical(F[c].astype("object"), categories=lv)
    return F, warns


def add_covariates(F: pd.DataFrame, specs: list[MixSpec], covariates: list[str]) -> pd.DataFrame:
    X = F.copy()
    if "age_d" in covariates:
        age = np.array([s.conditions.age_d if s.conditions.age_d else np.nan for s in specs], float)
        X["age_d"] = age
        X["log_age"] = np.log(np.clip(age, 1e-3, None))
    if "comparability_group" in covariates:
        cg = [s.conditions.comparability_group if s.conditions.comparability_group in COMPARABILITY_GROUPS else "unknown" for s in specs]
        X["comparability_group"] = pd.Categorical(cg, categories=CG_LEVELS)
    if "rest_time_s" in covariates:
        rt = np.array([s.conditions.rest_time_s if s.conditions.rest_time_s is not None else np.nan for s in specs], float)
        X["rest_time_s"] = rt
        X["rest_time_known"] = (~np.isnan(rt)).astype(int)
    if "test_protocol" in covariates:
        from .targets import TP_GEOMETRY, TP_METHODS, TP_NUMERIC, classify_geometry
        for feat, _ in TP_NUMERIC.values():
            key = feat[3:]                                   # tp_rest_s -> rest_s
            X[feat] = np.array([float(s.conditions.rheometer.get(key, np.nan)) if s.conditions.rheometer else np.nan for s in specs])
        if "tp_rest_s" in X.columns and "rest_time_s" in covariates:
            X["tp_rest_s"] = X["tp_rest_s"].where(X["tp_rest_s"].notna(), X["rest_time_s"])
        X["tp_geometry"] = pd.Categorical([classify_geometry(s.conditions.rheometer_geometry) for s in specs], categories=TP_GEOMETRY)
        X["tp_method"] = pd.Categorical([(s.conditions.rheometer_method if s.conditions.rheometer_method in TP_METHODS else
                                          ("unknown" if not s.conditions.rheometer_method else "other")) for s in specs],
                                        categories=TP_METHODS)
    return X


def domain_flags(model: TargetModel, X: pd.DataFrame) -> list[dict]:
    ranges = model.meta.get("feature_ranges", {})
    out = []
    for _, r in X.iterrows():
        viol = [c for c, (lo, hi) in ranges.items() if c in r.index and pd.notna(r[c]) and (r[c] < lo or r[c] > hi)]
        out.append(dict(n_range_violations=len(viol), range_violations=viol[:6],
                        chem_imputed_frac=float(r.get("chem_imputed_frac", np.nan)),
                        wb_out_of_range=("water_b" in viol)))
    return out


def predict_specs(specs: list[MixSpec], cfg: PipelineConfig, targets: list[str] | None = None,
                  allow_schema_mismatch: bool = False) -> pd.DataFrame:
    assets = Assets(cfg)
    F, warns = featurize_specs(specs, assets)
    keys = assets.manifest["models"]
    wanted = targets or assets.available_targets()
    rows = []
    for t in wanted:
        general = t if t in keys else None
        if general is None:
            log.warning("no model for target %s", t); continue
        for si, spec in enumerate(specs):
            key = general
            k3 = f"{t}__3dcp"
            if spec.conditions.is_3dcp and k3 in keys and (keys[k3].get("r2") or -9) >= (keys[general].get("r2") or -9):
                key = k3
            m = assets.model(key)
            if m.meta.get("feature_schema_hash") != assets.schema["hash"] and not allow_schema_mismatch:
                raise RuntimeError(f"model {key} was trained on feature schema {m.meta.get('feature_schema_hash')} "
                                   f"but current schema is {assets.schema['hash']}; rebuild/retrain or pass allow_schema_mismatch")
            X = add_covariates(F.iloc[[si]], [spec], m.meta.get("covariates", []))
            q = m.predict_quantiles(X).iloc[0]
            sd = float(m.predict_std(X)[0])
            dom = domain_flags(m, X)[0]
            rows.append(dict(spec=spec.name or f"mix{si}", target=t, unit=m.unit, q10=q.q10, q50=q.q50, q90=q.q90,
                             pred_std=sd, model=key, n_train=m.meta.get("n_train"), cv_r2=m.meta.get("cv", {}).get("r2"),
                             **dom, warnings=";".join(warns[si])))
    return pd.DataFrame(rows)
