"""Decision-vector encoding of the design space: z in [0,1]^D  <->  MixSpec.

Layout of z for K binder classes (K_opt of them optional), A admixtures, F fibres:
  raw_binder[K] | gate_binder[K_opt] | w_b | s_b? | gate_adm[A] dose_adm[A] | gate_fib[F] dose_fib[F]
Decoding is vectorised over an (n, D) array and always yields powder fractions that respect the
per-class bounds, the cardinality limit and sum to one (bounded-simplex projection).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import vocab as V
from ..composition import _to_record, normalize_mix
from ..schema import Component, Conditions, MixSpec
from .spec import DesignSpec, GroupBounds


@dataclass
class Layout:
    binder: list[str]
    b_lo: np.ndarray
    b_hi: np.ndarray
    b_req: np.ndarray
    opt_idx: np.ndarray
    adm: list[str]
    a_lo: np.ndarray
    a_hi: np.ndarray
    fib: list[str]
    f_lo: np.ndarray
    f_hi: np.ndarray
    has_sb: bool
    D: int

    # slice helpers
    @property
    def i_raw(self): return slice(0, len(self.binder))
    @property
    def i_gate(self): return slice(len(self.binder), len(self.binder) + len(self.opt_idx))
    @property
    def i_wb(self): return len(self.binder) + len(self.opt_idx)
    @property
    def i_sb(self): return self.i_wb + 1 if self.has_sb else None
    @property
    def i_adm(self):
        s = self.i_wb + 1 + int(self.has_sb)
        return s, s + len(self.adm), s + 2 * len(self.adm)
    @property
    def i_fib(self):
        s = self.i_adm[2]
        return s, s + len(self.fib), s + 2 * len(self.fib)


def make_layout(spec: DesignSpec) -> Layout:
    sp = spec.space
    binder = list(sp.binder)
    b_lo = np.array([sp.binder[c].lo for c in binder], float)
    b_hi = np.array([sp.binder[c].hi for c in binder], float)
    b_req = np.array([sp.binder[c].required for c in binder], bool)
    opt_idx = np.flatnonzero(~b_req)
    adm = list(sp.admixtures); fib = list(sp.fibres)
    D = len(binder) + len(opt_idx) + 1 + int(sp.s_b is not None) + 2 * len(adm) + 2 * len(fib)
    return Layout(binder, b_lo, b_hi, b_req, opt_idx, adm,
                  np.array([sp.admixtures[c].lo for c in adm], float), np.array([sp.admixtures[c].hi for c in adm], float),
                  fib, np.array([sp.fibres[c].lo for c in fib], float), np.array([sp.fibres[c].hi for c in fib], float),
                  sp.s_b is not None, D)


def project_bounded_simplex(x: np.ndarray, lo: np.ndarray, hi: np.ndarray, iters: int = 50) -> np.ndarray:
    """Row-wise projection onto {lo <= x <= hi, sum x = 1} (exact when the box-simplex is non-empty)."""
    x = np.clip(x, lo, hi)
    for _ in range(iters):
        r = 1.0 - x.sum(axis=1, keepdims=True)
        if np.all(np.abs(r) < 1e-10):
            break
        free = np.where(r > 0, x < hi - 1e-12, x > lo + 1e-12)
        nfree = free.sum(axis=1, keepdims=True)
        step = np.where(free, r / np.maximum(nfree, 1), 0.0)
        x = np.clip(x + step, lo, hi)
    return x


def decode(Z: np.ndarray, spec: DesignSpec, L: Layout | None = None) -> pd.DataFrame:
    """Decode (n, D) unit-cube points into a MixFrame (one row per candidate)."""
    L = L or make_layout(spec)
    sp = spec.space
    Z = np.atleast_2d(np.asarray(Z, float))
    n, K = Z.shape[0], len(L.binder)
    raw = Z[:, L.i_raw]
    present = np.tile(L.b_req, (n, 1))
    if len(L.opt_idx):
        gate = Z[:, L.i_gate]
        present[:, L.opt_idx] = gate > 0.5
        # cardinality: keep required + top optional gates
        n_req = int(L.b_req.sum())
        k_opt = max(sp.max_binder_components - n_req, 0)
        if k_opt < len(L.opt_idx):
            order = np.argsort(-gate, axis=1)
            keep = np.zeros_like(gate, dtype=bool)
            rows = np.arange(n)[:, None]
            keep[rows, order[:, :k_opt]] = True
            present[:, L.opt_idx] = (gate > 0.5) & keep
    lo_eff = np.where(present, L.b_lo, 0.0)
    hi_eff = np.where(present, L.b_hi, 0.0)
    # make sure each row's box-simplex is feasible: open more gates if sum(hi) < 1, close if sum(lo) > 1
    for _ in range(K):
        bad_hi = hi_eff.sum(axis=1) < 1.0 - 1e-9
        if not bad_hi.any():
            break
        for i in np.flatnonzero(bad_hi):
            cands = [j for j in L.opt_idx if not present[i, j]]
            if not cands:
                break
            j = max(cands, key=lambda jj: Z[i, L.i_gate][list(L.opt_idx).index(jj)])
            present[i, j] = True
        lo_eff = np.where(present, L.b_lo, 0.0); hi_eff = np.where(present, L.b_hi, 0.0)
    x = lo_eff + raw * (hi_eff - lo_eff)
    f = project_bounded_simplex(x, lo_eff, hi_eff)
    # sparsity: drop tiny optional components and re-project
    tiny = (f < sp.min_present_frac) & ~np.tile(L.b_req, (n, 1)) & present
    if tiny.any():
        present = present & ~tiny
        lo_eff = np.where(present, L.b_lo, 0.0); hi_eff = np.where(present, L.b_hi, 0.0)
        f = project_bounded_simplex(np.where(tiny, 0.0, f), lo_eff, hi_eff)
    out = {f"b:{c}": f[:, j] for j, c in enumerate(L.binder)}
    out["w_b"] = sp.w_b[0] + Z[:, L.i_wb] * (sp.w_b[1] - sp.w_b[0])
    if L.has_sb:
        out["s_b"] = sp.s_b[0] + Z[:, L.i_sb] * (sp.s_b[1] - sp.s_b[0])
    a0, a1, a2 = L.i_adm
    for j, c in enumerate(L.adm):
        g = Z[:, a0 + j] > 0.5 if L.a_lo[j] <= 0 else np.ones(n, bool)
        lo = max(L.a_lo[j], 0.01); hi = max(L.a_hi[j], lo * 1.0001)
        dose = np.exp(np.log(lo) + Z[:, a1 + j] * (np.log(hi) - np.log(lo)))
        out[f"a:{c}"] = np.where(g, dose, 0.0)
    f0, f1, f2 = L.i_fib
    for j, c in enumerate(L.fib):
        g = Z[:, f0 + j] > 0.5 if L.f_lo[j] <= 0 else np.ones(n, bool)
        dose = L.f_lo[j] + Z[:, f1 + j] * (L.f_hi[j] - L.f_lo[j])
        out[f"f:{c}"] = np.where(g, dose, 0.0)
    return pd.DataFrame(out)


def encode(spec: DesignSpec, mix: MixSpec, L: Layout | None = None) -> np.ndarray:
    """Inverse of decode for warm starts / closed-loop tests (components outside the space are ignored)."""
    L = L or make_layout(spec)
    sp = spec.space
    z = np.full(L.D, 0.5)
    amounts = {c.material_class: (c.amount or 0.0) for c in mix.components}
    for j, c in enumerate(L.binder):
        a = amounts.get(c, 0.0)
        span = L.b_hi[j] - L.b_lo[j]
        z[j] = np.clip((a - L.b_lo[j]) / span, 0, 1) if span > 0 else 0.5
    for k, j in enumerate(L.opt_idx):
        z[len(L.binder) + k] = 0.9 if amounts.get(L.binder[j], 0.0) > 0 else 0.1
    z[L.i_wb] = np.clip(((mix.water_binder or sp.w_b[0]) - sp.w_b[0]) / (sp.w_b[1] - sp.w_b[0]), 0, 1)
    if L.has_sb:
        sb = mix.sand_binder if mix.sand_binder is not None else sum(
            (c.amount or 0.0) for c in mix.components if V.resolve_group(c.material_class, c.role).family == "aggregate")
        z[L.i_sb] = np.clip((sb - sp.s_b[0]) / (sp.s_b[1] - sp.s_b[0]), 0, 1)
    a0, a1, _ = L.i_adm
    for j, c in enumerate(L.adm):
        pct = 100.0 * amounts.get(c, 0.0)
        z[a0 + j] = 0.9 if pct > 0 else 0.1
        lo = max(L.a_lo[j], 0.01); hi = max(L.a_hi[j], lo * 1.0001)
        z[a1 + j] = np.clip((np.log(max(pct, lo)) - np.log(lo)) / (np.log(hi) - np.log(lo)), 0, 1)
    f0, f1, _ = L.i_fib
    vols = {c.material_class: (c.vol_pct or 0.0) for c in mix.components}
    for j, c in enumerate(L.fib):
        v = vols.get(c, 0.0)
        z[f0 + j] = 0.9 if v > 0 else 0.1
        span = L.f_hi[j] - L.f_lo[j]
        z[f1 + j] = np.clip((v - L.f_lo[j]) / span, 0, 1) if span > 0 else 0.5
    return z


def frame_to_specs(M: pd.DataFrame, spec: DesignSpec, L: Layout | None = None) -> list[MixSpec]:
    """MixFrame rows -> MixSpec objects (the shared schema)."""
    L = L or make_layout(spec)
    sp = spec.space
    fc = sp.fixed_conditions or {}
    specs = []
    for i, r in M.iterrows():
        comps = []
        for c in L.binder:
            if r[f"b:{c}"] > 0:
                comps.append(Component(material_class=c, amount=float(r[f"b:{c}"])))
        for c in L.adm:
            if r[f"a:{c}"] > 0:
                comps.append(Component(material_class=c, amount=float(r[f"a:{c}"]) / 100.0))
        for c in L.fib:
            if r[f"f:{c}"] > 0:
                comps.append(Component(material_class=c, vol_pct=float(r[f"f:{c}"])))
        cond = Conditions(curing_temp_C=fc.get("curing_temp_C"), curing_rh_pct=fc.get("curing_rh_pct"),
                          curing_regime=fc.get("curing_regime"), is_3dcp=int(bool(sp.is_3dcp)) if sp.is_3dcp is not None else 0)
        specs.append(MixSpec(system_type=sp.system_type, components=comps, water_binder=float(r["w_b"]),
                             sand_binder=float(r["s_b"]) if L.has_sb else None, conditions=cond, name=f"cand_{i:05d}"))
    return specs


def frame_to_composition(M: pd.DataFrame, specs: list[MixSpec]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Vectorised path from MixFrame to the (comp_wide, long, ctx) inputs of featurize_frame.

    Uses normalize_mix per row for exact parity with the DB path; ~2 ms per row.
    """
    recs, long, ctx = [], [], []
    for si, spec in enumerate(specs):
        rows = spec.to_component_rows()
        uid = f"{si}|{spec.name}"
        rows["material_uid"] = [f"{si}|{m}" for m in rows["material_uid"]]
        mix_row = spec.to_mix_row(); mix_row["mix_uid"] = uid
        comp = normalize_mix(rows, mix_row)
        r = mix_row.to_dict(); r["paper_uid"] = "design"
        rec = _to_record(comp, r); rec["mix_uid"] = uid
        recs.append(rec)
        for m in comp.materials_long:
            long.append({"mix_uid": uid, **m})
        cd = spec.conditions
        ctx.append(dict(mix_uid=uid, paper_uid="design", system_type=spec.system_type, curing_regime=cd.curing_regime,
                        curing_temp_C=cd.curing_temp_C, curing_rh_pct=cd.curing_rh_pct, is_3dcp=cd.is_3dcp,
                        year=spec.year))
    return pd.DataFrame(recs), pd.DataFrame(long), pd.DataFrame(ctx)
