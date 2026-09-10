"""Every material_class in the DB must map to a group; 'other_powder' must stay small."""
from __future__ import annotations

import pytest

from pmpredict import vocab
from pmpredict.config import load_config
from pmpredict.db import load_tables


@pytest.fixture(scope="module")
def tables():
    cfg = load_config()
    if not cfg.db_path.exists():
        pytest.skip("master.db not available")
    return load_tables(cfg, tables=["materials", "mix_components"])


def test_every_class_mapped(tables):
    classes = set(tables["materials"]["material_class"].dropna().unique())
    mapping = vocab.class_to_group()
    missing = sorted(c for c in classes if c not in mapping)
    assert not missing, f"unmapped material_class values: {missing}"


def test_group_defaults_complete():
    defaults = vocab.group_defaults()
    for cls, g in vocab.class_to_group().items():
        if g is not None:
            assert g in defaults, f"{cls} -> {g} has no group_defaults entry"
    for fam in vocab.FAMILIES:
        assert fam in {gi.family for gi in defaults.values()}


def test_resolve_other_by_role():
    assert vocab.resolve_group("other", "binder").group == "other_powder"
    assert vocab.resolve_group("other", "fine_aggregate").group == "other_agg"
    assert vocab.resolve_group("other", "admixture").group == "other_admix"
    assert vocab.resolve_group("other", "fibre").group == "other_fibre"
    assert vocab.resolve_group("other", "nanomaterial").group == "nano_other"
    assert vocab.resolve_group("unknown_class_xyz", "activator").group == "other_activator"
    assert vocab.resolve_group("silica_fume", "admixture").family == "powder"


def test_other_powder_share_small(tables):
    """Mass-weighted share of powder falling into other_powder must be <= 3%."""
    mc = tables["mix_components"].merge(
        tables["materials"][["material_uid", "material_class"]], on="material_uid", how="left")
    mc = mc[mc["role"].isin(["binder", "scm", "filler"]) & mc["dosage_reported"].notna()]
    grp = [vocab.resolve_group(c, r).group for c, r in zip(mc["material_class"], mc["role"])]
    mc = mc.assign(group=grp)
    # use kg/m3-basis rows only so masses are comparable
    k = mc[mc["basis_reported"] == "kg_m3"]
    share = k.loc[k["group"] == "other_powder", "dosage_reported"].sum() / k["dosage_reported"].sum()
    assert share <= 0.03, f"other_powder mass share = {share:.3f}"
