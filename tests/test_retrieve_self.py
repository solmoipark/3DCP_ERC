"""Self-retrieval: a spec built around a real mix's own measurements must find that mix (or a
sibling from the same paper) at the top, and the paper cap must hold."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pmpredict.config import load_config
from pmpredict.design.retrieve import MAX_PER_PAPER, LiteratureStore, retrieve
from pmpredict.design.spec import DesignSpec


@pytest.fixture(scope="module")
def store():
    cfg = load_config()
    if not (cfg.data_dir / "targets.parquet").exists():
        pytest.skip("run build-targets first")
    return LiteratureStore(cfg)


def _spec_for(store, mix_uid, rows):
    w = store.comp.loc[mix_uid]
    targets = []
    for r in rows.itertuples(index=False):
        cond = {}
        if pd.notna(r.age_d):
            cond["age_d"] = float(r.age_d)
        if isinstance(r.comparability_group, str):
            cond["comparability_group"] = r.comparability_group
        targets.append(dict(quantity=r.target, kind="range", lo=float(r.value) * 0.95, hi=float(r.value) * 1.05, conditions=cond))
    binder = {"portland_cement": dict(lo=0.0, hi=1.0, required=True)}
    return DesignSpec.from_dict(dict(name="self", targets=targets,
                                     space=dict(system_type=str(w["system_type"]), w_b=[0.1, 1.0], s_b=[0.0, 6.0], binder=binder),
                                     output=dict(n_literature=10)))


def test_self_retrieval_top3(store):
    t = store.targets
    ok_mixes = t.groupby("mix_uid")["target"].nunique()
    cand = ok_mixes[ok_mixes >= 2].index
    cand = [m for m in cand if m in store.comp.index]
    rng = np.random.default_rng(0)
    sample = rng.choice(cand, size=min(150, len(cand)), replace=False)
    hit_top3 = 0
    for uid in sample:
        rows = t[t["mix_uid"] == uid].drop_duplicates("target").head(3)
        spec = _spec_for(store, uid, rows)
        spec.validate()
        hits = retrieve(spec, store, n=10)
        paper = uid.split("::")[0]
        top = [h.mix_uid for h in hits[:3]]
        if uid in top or any(h.paper_uid == paper for h in hits[:3]):
            hit_top3 += 1
    rate = hit_top3 / len(sample)
    assert rate >= 0.95, f"self-retrieval top-3 rate {rate:.2f}"


def test_paper_cap(store):
    t = store.targets
    # a paper with many compressive mixes
    cs = t[t["target"] == "compressive_strength"]
    big = cs.groupby("paper_uid")["mix_uid"].nunique().sort_values(ascending=False).index[0]
    rows = cs[cs["paper_uid"] == big]
    lo, hi = rows["value"].quantile(0.1), rows["value"].quantile(0.9)
    uid = rows["mix_uid"].iloc[0]
    st = store.comp.loc[uid, "system_type"] if uid in store.comp.index else "mortar"
    spec = DesignSpec.from_dict(dict(name="cap", targets=[dict(quantity="compressive_strength", kind="range", lo=float(lo), hi=float(hi))],
                                     space=dict(system_type=str(st), w_b=[0.1, 1.0], s_b=[0.0, 6.0],
                                                binder={"portland_cement": dict(lo=0.0, hi=1.0, required=True)}),
                                     output=dict(n_literature=20)))
    spec.validate()
    hits = retrieve(spec, store, n=20)
    per_paper = pd.Series([h.paper_uid for h in hits]).value_counts()
    assert per_paper.max() <= MAX_PER_PAPER
