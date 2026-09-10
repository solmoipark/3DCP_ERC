"""Read-only access to the literature master.db and typed table loading.

Every column in master.db is TEXT with a mix of NULL and '' for missing
values. ``load_tables`` strips strings, turns '' into NA, casts the known
numeric columns and caches each table as parquet under ``data/raw``.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import pandas as pd

from .config import PipelineConfig

log = logging.getLogger("pmpredict.db")

# Columns loaded per table (None = all columns).
TABLE_COLUMNS: dict[str, list[str] | None] = {
    "papers": [
        "paper_uid", "doi", "title", "journal", "year", "is_3dcp_study", "binder_system_tag",
        "system_types_present", "screening_status", "extraction_confidence_overall", "wave",
    ],
    "mixes": [
        "mix_uid", "paper_uid", "mix_id", "name_in_paper", "system_type", "mix_basis",
        "w_b_reported", "w_b_source", "w_c_reported", "binder_total_kg_m3", "sand_binder_ratio",
        "sand_binder_basis", "liquid_solid_ratio", "liquid_solid_basis", "fresh_density_kg_m3",
        "curing_regime", "curing_temp_C", "curing_rh_pct", "is_control_mix", "protocol_uid", "notes",
    ],
    "mix_components": [
        "component_uid", "mix_uid", "material_uid", "paper_uid", "role", "dosage_reported",
        "unit_reported", "basis_reported", "dosage_kg_m3", "mass_frac_of_binder", "notes",
    ],
    "materials": [
        "material_uid", "paper_uid", "material_id", "material_class", "name_in_paper",
        "standard_designation", "supplier", "chemistry_status", "oxide_sum_basis", "oxide_sum_computed_pct",
    ],
    "material_chemistry": [
        "chem_uid", "material_uid", "component", "value_reported_pct", "basis", "included_in_sum", "method",
    ],
    "material_physical": [
        "phys_uid", "material_uid", "property", "value_reported", "unit_reported", "value_si", "unit_si",
    ],
    "measurements": [
        "obs_uid", "mix_uid", "test_uid", "paper_uid", "quantity", "quantity_family", "proposed_quantity",
        "mapping_status", "value_canonical", "unit_canonical", "value_kind", "age_value", "age_unit",
        "age_norm_d", "rest_time_norm_s", "basis", "condition_note", "replicate_n", "fig_only",
        "extraction_confidence",
    ],
    "tests": [
        "test_uid", "paper_uid", "test_family", "method_name", "standard", "geometry",
        "comparability_group", "protocol_completeness",
    ],
    "mixing_protocols": [
        "protocol_uid", "paper_uid", "mixer_type", "total_mixing_time_s", "max_speed_rpm",
        "batch_volume_L", "ambient_temp_C", "ambient_rh_pct",
    ],
    "test_protocols": ["param_uid", "test_uid", "parameter", "value_reported", "unit_reported", "value_si", "unit_si"],
}

NUMERIC_COLS: dict[str, list[str]] = {
    "papers": ["year", "is_3dcp_study"],
    "mixes": [
        "w_b_reported", "w_c_reported", "binder_total_kg_m3", "sand_binder_ratio", "liquid_solid_ratio",
        "fresh_density_kg_m3", "curing_temp_C", "curing_rh_pct", "is_control_mix",
    ],
    "mix_components": ["dosage_reported", "dosage_kg_m3", "mass_frac_of_binder"],
    "materials": ["oxide_sum_computed_pct"],
    "material_chemistry": ["value_reported_pct", "included_in_sum"],
    "material_physical": ["value_reported", "value_si"],
    "measurements": ["value_canonical", "age_norm_d", "rest_time_norm_s", "replicate_n", "fig_only"],
    "tests": [],
    "mixing_protocols": ["total_mixing_time_s", "max_speed_rpm", "batch_volume_L", "ambient_temp_C", "ambient_rh_pct"],
    "test_protocols": ["value_si"],
}

# Pre-filter applied in SQL so only numeric-usable measurements are loaded.
MEASUREMENT_WHERE = (
    "TRIM(COALESCE(value_canonical,'')) <> '' AND (fig_only = '0' OR fig_only IS NULL) "
    "AND TRIM(COALESCE(quantity,'')) <> ''"
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open master.db strictly read-only."""
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _clean(df: pd.DataFrame, numeric: list[str]) -> pd.DataFrame:
    for c in df.columns:
        if df[c].dtype == object:
            s = df[c].astype("string").str.strip()
            df[c] = s.mask(s == "", pd.NA)
    for c in numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def read_table(con: sqlite3.Connection, table: str) -> pd.DataFrame:
    cols = TABLE_COLUMNS.get(table)
    sel = ", ".join(cols) if cols else "*"
    sql = f"SELECT {sel} FROM {table}"
    if table == "measurements":
        sql += f" WHERE {MEASUREMENT_WHERE}"
    df = pd.read_sql_query(sql, con)
    if table == "mix_components":
        # keep the printed dosage string so '~1.5' / '<=0.75' can be rescued downstream
        df["dosage_raw"] = df["dosage_reported"]
    return _clean(df, NUMERIC_COLS.get(table, []))


def load_tables(cfg: PipelineConfig, refresh: bool = False,
                tables: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Load (and cache) all tables needed by the pipeline."""
    cfg.ensure_dirs()
    names = tables or list(TABLE_COLUMNS)
    out: dict[str, pd.DataFrame] = {}
    con = None
    t0 = time.time()
    try:
        for name in names:
            cache = cfg.raw_dir / f"{name}.parquet"
            if cache.exists() and not refresh:
                out[name] = pd.read_parquet(cache)
                continue
            if con is None:
                con = connect(cfg.db_path)
            df = read_table(con, name)
            df.to_parquet(cache, index=False)
            out[name] = df
            log.info("loaded %s: %d rows", name, len(df))
    finally:
        if con is not None:
            con.close()
    log.info("tables ready in %.1fs", time.time() - t0)
    return out
