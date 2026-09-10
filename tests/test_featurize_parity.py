"""DB mix -> MixSpec -> featurize must reproduce the DB feature row (composition & context blocks)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pmpredict.composition import ACT_GROUPS, ADMIX_GROUPS, AGG_GROUPS, FIBRE_GROUPS, NANO_GROUPS, POWDER_GROUPS
from pmpredict.config import load_config
from pmpredict.db import load_tables
from pmpredict.features import build_context
from pmpredict.predict import Assets, featurize_specs
from pmpredict.reconstruct import spec_from_db

COMP_COLS = ([f"pw_{g}" for g in POWDER_GROUPS] + ["water_b", "sand_b", "cement_share", "scm_frac", "total_solids_b"]
             + [f"agg_{g}" for g in AGG_GROUPS] + [f"adx_{g}_pct" for g in ADMIX_GROUPS]
             + [f"fib_{g}_vol" for g in FIBRE_GROUPS] + [f"act_{g}" for g in ACT_GROUPS] + ["naoh_molarity"]
             + [f"nano_{g}_pct" for g in NANO_GROUPS] + ["curing_temp_C", "curing_rh_pct", "heat_cured", "is_3dcp"])
CAT_COLS = ["system_type", "curing_type", "binder_family"]
CHEM_COLS = ["ox_SiO2", "ox_CaO", "ox_Al2O3", "blaine_m2kg", "sg_powder"]


@pytest.fixture(scope="module")
def data():
    cfg = load_config()
    need = [cfg.data_dir / f for f in ("composition.parquet", "composition_long.parquet", "features.parquet",
                                        "class_medians.json", "feature_schema.json", "material_oxides.parquet",
                                        "material_phys.parquet")]
    if not all(p.exists() for p in need):
        pytest.skip("run build-features first")
    T = load_tables(cfg, tables=["mixes", "papers"])
    return dict(cfg=cfg, wide=pd.read_parquet(need[0]), long=pd.read_parquet(need[1]), F=pd.read_parquet(need[2]),
                mat_ox=pd.read_parquet(need[5]), mat_ph=pd.read_parquet(need[6]), ctx=build_context(T),
                assets=Assets(cfg))


def test_parity_on_random_mixes(data):
    wide, F = data["wide"], data["F"].set_index("mix_uid")
    # mixes whose composition is fully material-level reconstructible: no rounding artefacts from
    # group-level admixture/fibre/activator/nano dosages -> require those to be zero or simple
    fl = wide["flags"].fillna("")
    cand = wide[(wide["mode"].isin(["abs", "rel", "parts"])) & wide["water_b"].notna()
                & (wide["fibre_total_vol_pct"] == 0) & (wide["nano_total_pct"] == 0)
                & ~fl.str.contains("agg_share_only")]        # aggregate shares without an s/b cannot be expressed
    rng = np.random.default_rng(0)
    uids = list(rng.choice(cand["mix_uid"].to_numpy(), size=min(200, len(cand)), replace=False))
    specs = [spec_from_db(u, wide, data["long"], data["ctx"], data["mat_ox"], data["mat_ph"]) for u in uids]
    Fs, _ = featurize_specs(specs, data["assets"])
    Fs.index = uids
    ref = F.loc[uids]
    num_bad = {}
    for c in COMP_COLS:
        a, b = Fs[c].astype(float).to_numpy(), ref[c].astype(float).to_numpy()
        ok = np.isclose(a, b, atol=1e-9, rtol=1e-6) | (np.isnan(a) & np.isnan(b))
        if not ok.all():
            num_bad[c] = int((~ok).sum())
    assert not num_bad, f"composition/context mismatches: {num_bad}"
    for c in CAT_COLS:
        assert (Fs[c].astype(str).to_numpy() == ref[c].astype(str).to_numpy()).all(), c
    # chemistry parity where the DB material had accepted chemistry (props passed through)
    have = ref["chem_coverage"] >= 0.999
    if have.any():
        for c in CHEM_COLS:
            a, b = Fs.loc[have, c].astype(float).to_numpy(), ref.loc[have, c].astype(float).to_numpy()
            ok = np.isclose(a, b, atol=1e-6, rtol=1e-6) | (np.isnan(a) & np.isnan(b))
            assert ok.mean() >= 0.95, f"{c}: {int((~ok).sum())} of {len(ok)} differ"
