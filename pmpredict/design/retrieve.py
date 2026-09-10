"""Literature retrieval: published mixes that satisfy / approach a design spec, and
closest published analogues of optimisation candidates."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from ..config import PipelineConfig
from ..db import load_tables
from ..reconstruct import composition_summary
from ..targets import load_target_rules
from .domain import COMP_FEATURES, DomainIndex
from .spec import DesignSpec, TargetSpec

log = logging.getLogger("pmpredict.retrieve")

AGE_TOL = 0.15
PEN_AGE_NA, PEN_CG_FAMILY, PEN_CG_NA, PEN_CG_OTHER = 0.3, 0.3, 0.5, 0.7
PEN_RT_NA, PEN_RT_DIFF = 0.3, 0.7
D_MISSING = 1.0
PAPER_DECAY, MAX_PER_PAPER = 0.6, 3


@dataclass
class MeasuredValue:
    quantity: str
    value: float
    unit: str
    age_d: float | None
    comparability_group: str | None
    rest_time_s: float | None


@dataclass
class LiteratureHit:
    mix_uid: str
    paper_uid: str
    doi: str
    title: str
    year: int | None
    is_3dcp: int
    mix_name: str
    system_type: str
    composition_summary: str
    measured: list[MeasuredValue]
    target_distance: float
    coverage: float
    qualifier_penalty: float
    score: float
    tier: str
    feature_distance: float | None = None
    top_deviations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class LiteratureStore:
    """Holds the target table, normalised compositions, features and paper metadata."""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.targets = pd.read_parquet(cfg.data_dir / "targets.parquet")
        self.comp = pd.read_parquet(cfg.data_dir / "composition.parquet").drop_duplicates("mix_uid").set_index("mix_uid")
        self.features = pd.read_parquet(cfg.data_dir / "features.parquet").drop_duplicates("mix_uid")
        T = load_tables(cfg, tables=["papers", "mixes"])
        self.papers = T["papers"].drop_duplicates("paper_uid").set_index("paper_uid")
        self.mixes = T["mixes"].drop_duplicates("mix_uid").set_index("mix_uid")
        rules, _ = load_target_rules()
        self.units = {t: r.get("unit", "") for t, r in rules.items()}
        # robust scale per quantity for target-space distances
        g = self.targets.groupby("target")["value"]
        self.scale = ((g.quantile(0.75) - g.quantile(0.25)) / 1.349).clip(lower=1e-9).to_dict()
        self._domain: DomainIndex | None = None
        self._flow: pd.DataFrame | None = None
        self._static: pd.DataFrame | None = None

    # ---- derived (curve) quantities from digitised curves
    def flow_stress_at(self, rate: float) -> pd.DataFrame:
        """Per mix: shear stress interpolated at `rate` from real flow curves spanning that rate."""
        from ..flowcurve import real_flow_curves
        if self._flow is None:
            self._flow = real_flow_curves(self.cfg)
        rows = []
        for cu, g in self._flow.groupby("curve_uid"):
            g = g.sort_values("shear_rate")
            if g.shear_rate.min() <= rate <= g.shear_rate.max() and len(g) >= 3:
                rows.append(dict(mix_uid=g.mix_uid.iloc[0], paper_uid=g.paper_uid.iloc[0], value=float(np.interp(rate, g.shear_rate, g.shear_stress))))
        df = pd.DataFrame(rows, columns=["mix_uid", "paper_uid", "value"])
        return df.groupby(["mix_uid", "paper_uid"], as_index=False)["value"].median()

    def static_yield_at_rest(self, rest_s: float, tol: float = 0.2) -> pd.DataFrame:
        """Per mix: static yield stress at rest time `rest_s` from digitised structuration curves (interpolated)
        and from tabulated static_yield_stress rows whose rest time is within +-tol."""
        from ..thixocurve import load_static_curves
        if self._static is None:
            self._static = load_static_curves(self.cfg.db_path)
        rows = []
        for cu, g in self._static.groupby("curve_uid"):
            g = g.sort_values("t_s")
            if g.t_s.min() <= rest_s <= g.t_s.max() and len(g) >= 3:
                rows.append(dict(mix_uid=g.mix_uid.iloc[0], paper_uid=g.paper_uid.iloc[0], value=float(np.interp(rest_s, g.t_s, g.tau))))
        tab = self.targets[(self.targets.target == "static_yield_stress") & self.targets.rest_time_s.notna()]
        tab = tab[(tab.rest_time_s - rest_s).abs() <= max(tol * rest_s, 30.0)]
        rows += [dict(mix_uid=r.mix_uid, paper_uid=r.paper_uid, value=float(r.value)) for r in tab.itertuples(index=False)]
        df = pd.DataFrame(rows, columns=["mix_uid", "paper_uid", "value"])
        return df.groupby(["mix_uid", "paper_uid"], as_index=False)["value"].median()

    @property
    def domain(self) -> DomainIndex:
        if self._domain is None:
            self._domain = DomainIndex().fit(self.features)
        return self._domain

    # ------------------------------------------------------------ helpers
    def paper_meta(self, paper_uid: str) -> dict:
        if paper_uid in self.papers.index:
            p = self.papers.loc[paper_uid]
            return dict(doi=str(p.get("doi", "")), title=str(p.get("title", "")) if pd.notna(p.get("title")) else "",
                        year=int(p["year"]) if pd.notna(p.get("year")) else None,
                        is_3dcp=int(p["is_3dcp_study"]) if pd.notna(p.get("is_3dcp_study")) else 0)
        return dict(doi="", title="", year=None, is_3dcp=0)

    def mix_name(self, mix_uid: str) -> str:
        if mix_uid in self.mixes.index:
            n = self.mixes.loc[mix_uid, "name_in_paper"]
            if isinstance(n, str):
                return n
        return mix_uid.split("::")[-1]

    def measured_for(self, mix_uid: str, quantities: list[str] | None = None) -> list[MeasuredValue]:
        t = self.targets[self.targets["mix_uid"] == mix_uid]
        if quantities:
            t = t[t["target"].isin(quantities)]
        out = []
        for r in t.itertuples(index=False):
            out.append(MeasuredValue(r.target, float(r.value), self.units.get(r.target, ""),
                                     None if pd.isna(r.age_d) else float(r.age_d),
                                     r.comparability_group if isinstance(r.comparability_group, str) else None,
                                     None if pd.isna(r.rest_time_s) else float(r.rest_time_s)))
        return out


# ------------------------------------------------------------------- scoring
def qualify(rows: pd.DataFrame, t: TargetSpec) -> pd.DataFrame:
    """Filter rows to matching conditions and attach a qualifier penalty in [0, 1)."""
    c = t.conditions
    pen = np.zeros(len(rows))
    keep = np.ones(len(rows), bool)
    if c.age_d is not None:
        age = rows["age_d"].to_numpy(float)
        na = np.isnan(age)
        match = ~na & (np.abs(np.log(np.where(na, 1.0, np.maximum(age, 1e-6)) / c.age_d)) <= np.log(1 + AGE_TOL))
        keep &= match | na
        pen += np.where(na, PEN_AGE_NA, 0.0)
    if c.comparability_group is not None:
        cg = rows["comparability_group"].astype("object")
        fam = c.comparability_group.split("_")[0] + "_" + c.comparability_group.split("_")[1][:3] \
            if "_" in c.comparability_group else c.comparability_group
        exact = (cg == c.comparability_group).to_numpy()
        isna = cg.isna().to_numpy()
        same_fam = cg.fillna("").astype(str).str.startswith(fam).to_numpy() & ~exact
        pen += np.where(exact, 0.0, np.where(same_fam, PEN_CG_FAMILY, np.where(isna, PEN_CG_NA, PEN_CG_OTHER)))
    if c.rest_time_s is not None:
        rt = rows["rest_time_s"].to_numpy(float)
        na = np.isnan(rt)
        exact = ~na & (np.abs(rt - c.rest_time_s) <= max(0.1 * c.rest_time_s, 1.0))
        pen += np.where(exact, 0.0, np.where(na, PEN_RT_NA, PEN_RT_DIFF))
    out = rows[keep].copy()
    out["penalty"] = np.clip(pen[keep], 0.0, 0.95)
    return out


def target_distance(values: np.ndarray, t: TargetSpec, scale: float) -> np.ndarray:
    v = np.asarray(values, float)
    if t.kind == "ge":
        gap = np.maximum(t.lo - v, 0.0)
    elif t.kind == "le":
        gap = np.maximum(v - t.hi, 0.0)
    elif t.kind == "range":
        gap = np.maximum(t.lo - v, 0.0) + np.maximum(v - t.hi, 0.0)
    elif t.kind == "goal":
        gap = np.abs(v - t.goal)
    else:
        gap = np.zeros_like(v)
    return gap / scale


def retrieve(spec: DesignSpec, store: LiteratureStore, n: int | None = None) -> list[LiteratureHit]:
    """Tier (i) exact hits, then tier (ii) nearest in target space; paper-diversified."""
    n = n or spec.output.n_literature
    per_t = []
    for ti, t in enumerate(spec.targets):
        if t.quantity == "shear_stress_at_rate":
            rows = store.flow_stress_at(float(t.conditions.shear_rate_1s)).assign(penalty=0.0)
            scale = store.scale.get("dynamic_yield_stress", 1.0)
        elif t.quantity == "static_yield_stress_at_rest":
            rows = store.static_yield_at_rest(float(t.conditions.rest_time_s)).assign(penalty=0.0)
            scale = store.scale.get("static_yield_stress", 1.0)
        else:
            rows = store.targets[store.targets["target"] == t.quantity]
            rows = qualify(rows, t)
            scale = store.scale.get(t.quantity, 1.0)
        if rows.empty:
            continue
        rows = rows.copy()
        rows["d"] = target_distance(rows["value"].to_numpy(), t, scale)
        rows["cost"] = rows["d"] + rows["penalty"]
        best = rows.sort_values("cost").drop_duplicates("mix_uid")
        per_t.append(best[["mix_uid", "paper_uid", "value", "d", "penalty"]].rename(
            columns={"value": f"v__{ti}", "d": f"d__{ti}", "penalty": f"p__{ti}"}))
    if not per_t:
        return []
    J = per_t[0]
    for x in per_t[1:]:
        J = J.merge(x.drop(columns=["paper_uid"]), on="mix_uid", how="outer")
    J["paper_uid"] = J["paper_uid"].fillna(J["mix_uid"].str.split("::").str[0])
    dcols = [c for c in J.columns if c.startswith("d__")]
    pcols = [c for c in J.columns if c.startswith("p__")]
    measured = J[dcols].notna().sum(axis=1)
    J["coverage"] = measured / len(dcols)
    D = J[dcols].fillna(D_MISSING).to_numpy()
    J["target_distance"] = np.sqrt((D ** 2).sum(axis=1))
    P = J[pcols].fillna(0.0).to_numpy()
    J["penalty"] = 1.0 - np.prod(1.0 - P, axis=1)
    # system type hard filter, 3DCP boost
    st = store.comp["system_type"].reindex(J["mix_uid"]).to_numpy()
    J = J[st == spec.space.system_type]
    is3 = np.array([store.paper_meta(p)["is_3dcp"] for p in J["paper_uid"]])
    boost = np.where((spec.space.is_3dcp is True) & (is3 == 1), 1.2, 1.0)
    J["score"] = np.exp(-J["target_distance"]) * np.sqrt(1.0 - J["penalty"]) * J["coverage"] * boost
    J["tier"] = np.where((J[dcols].fillna(D_MISSING) == 0).all(axis=1) & (J["coverage"] >= 0.999), "exact", "near")
    J = J.sort_values(["tier", "score"], ascending=[True, False])
    derived = [(ti, t) for ti, t in enumerate(spec.targets) if t.quantity in {"shear_stress_at_rate", "static_yield_stress_at_rest"}]
    Jv = J.set_index("mix_uid")
    # paper diversification (greedy MMR-style)
    seen: dict[str, int] = {}
    hits: list[LiteratureHit] = []
    for r in J.itertuples(index=False):
        k = seen.get(r.paper_uid, 0)
        if k >= MAX_PER_PAPER:
            continue
        seen[r.paper_uid] = k + 1
        score = float(r.score) * (PAPER_DECAY ** k)
        pm = store.paper_meta(r.paper_uid)
        w = store.comp.loc[r.mix_uid] if r.mix_uid in store.comp.index else None
        measured = store.measured_for(r.mix_uid, [t.quantity for t in spec.targets])
        for ti, t in derived:                  # curve-derived values are not in the target table: add them here
            v = Jv.loc[r.mix_uid, f"v__{ti}"] if f"v__{ti}" in Jv.columns else np.nan
            if pd.notna(v):
                c = t.conditions
                measured.append(MeasuredValue(t.label, float(v), "Pa", None, None,
                                              c.rest_time_s if t.quantity == "static_yield_stress_at_rest" else c.shear_rate_1s))
        hits.append(LiteratureHit(
            mix_uid=r.mix_uid, paper_uid=r.paper_uid, doi=pm["doi"], title=pm["title"], year=pm["year"],
            is_3dcp=pm["is_3dcp"], mix_name=store.mix_name(r.mix_uid),
            system_type=str(w["system_type"]) if w is not None else "", composition_summary=composition_summary(w) if w is not None else "",
            measured=measured,
            target_distance=float(r.target_distance), coverage=float(r.coverage), qualifier_penalty=float(r.penalty),
            score=score, tier=str(r.tier)))
        if len(hits) >= n:
            break
    hits.sort(key=lambda h: (h.tier != "exact", -h.score))
    return hits


def analogues(F_cand: pd.DataFrame, store: LiteratureStore, spec: DesignSpec, k: int = 3) -> list[list[LiteratureHit]]:
    """Closest published mixes (composition space) for each candidate feature row."""
    di = store.domain
    d, idx = di.neighbors(F_cand, k=k)
    feats = store.features.reset_index(drop=True)
    Zc = di._matrix(F_cand)
    out = []
    for i in range(len(F_cand)):
        lst = []
        for dist, j in zip(d[i], idx[i]):
            row = feats.iloc[j]
            uid = row["mix_uid"]
            Zr = di._matrix(feats.iloc[[j]])[0]
            diff = np.abs(Zc[i] - Zr)
            top = np.argsort(-diff)[:3]
            devs = [f"{di.cols[t]}: analogue {row[di.cols[t]]:.3g} vs candidate {F_cand.iloc[i][di.cols[t]]:.3g}"
                    for t in top if diff[t] > 0.25]
            pm = store.paper_meta(row["paper_uid"])
            w = store.comp.loc[uid] if uid in store.comp.index else None
            lst.append(LiteratureHit(
                mix_uid=uid, paper_uid=row["paper_uid"], doi=pm["doi"], title=pm["title"], year=pm["year"],
                is_3dcp=pm["is_3dcp"], mix_name=store.mix_name(uid),
                system_type=str(w["system_type"]) if w is not None else "",
                composition_summary=composition_summary(w) if w is not None else "",
                measured=store.measured_for(uid, [t.quantity for t in spec.targets]),
                target_distance=float("nan"), coverage=float("nan"), qualifier_penalty=0.0, score=float(np.exp(-dist)),
                tier="analogue", feature_distance=float(dist), top_deviations=devs))
        out.append(lst)
    return out
