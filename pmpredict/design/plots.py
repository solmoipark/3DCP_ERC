"""Static plots for design results (matplotlib, Agg backend)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .objectives import OBJECTIVE_COLUMN


def pareto_plot(res, path: Path) -> Path | None:
    objs = res.spec["objectives"]
    cands = res.candidates
    if not cands:
        return None
    if len(objs) >= 2:
        xa, ya = OBJECTIVE_COLUMN.get(objs[0]["name"], objs[0]["name"]), OBJECTIVE_COLUMN.get(objs[1]["name"], objs[1]["name"])
    else:
        xa = OBJECTIVE_COLUMN.get(objs[0]["name"], objs[0]["name"]) if objs else "co2_per_m3"
        ya = "__p"
    x = np.array([c.objectives.get(xa, np.nan) for c in cands])
    y = np.array([c.p_min_targets for c in cands]) if ya == "__p" else np.array([c.objectives.get(ya, np.nan) for c in cands])
    P = np.array([c.p_min_targets for c in cands])
    fig, ax = plt.subplots(figsize=(6, 4.2), dpi=130)
    sc = ax.scatter(x, y, c=P, cmap="viridis", vmin=0, vmax=1, s=60, edgecolor="k", linewidth=0.5)
    for c, xi, yi in zip(cands, x, y):
        ax.annotate(str(c.rank), (xi, yi), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel(xa); ax.set_ylabel("min P(target satisfied)" if ya == "__p" else ya)
    ax.set_title(f"Candidates — {res.spec['name']}")
    fig.colorbar(sc, label="min P(target satisfied)")
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return path


def parallel_plot(res, path: Path) -> Path | None:
    cands = res.candidates
    if not cands:
        return None
    binder = list(res.spec["space"]["binder"])
    adm = list(res.spec["space"]["admixtures"])
    qs = list(cands[0].predictions)
    axes = [f"b:{b}" for b in binder] + ["w/b"] + (["s/b"] if res.spec["space"].get("s_b") else []) + [f"a:{a}" for a in adm] + qs
    rows = []
    for c in cands:
        comp = {x["material_class"]: x for x in c.mix["components"]}
        vals = [comp.get(b, {}).get("amount") or 0.0 for b in binder] + [c.mix["water_binder"]] + \
            ([c.mix["sand_binder"] or 0.0] if res.spec["space"].get("s_b") else []) + \
            [100.0 * (comp.get(a, {}).get("amount") or 0.0) for a in adm] + [c.predictions[q].q50 for q in qs]
        rows.append(vals)
    A = np.array(rows, float)
    lo, hi = np.nanmin(A, axis=0), np.nanmax(A, axis=0)
    span = np.where(hi - lo > 1e-12, hi - lo, 1.0)
    N = (A - lo) / span
    fig, ax = plt.subplots(figsize=(max(7, 0.9 * len(axes)), 4.2), dpi=130)
    cm = plt.get_cmap("viridis")
    for i, c in enumerate(cands):
        ax.plot(range(len(axes)), N[i], color=cm(c.p_min_targets), alpha=0.9, lw=1.6, label=f"#{c.rank}")
    ax.set_xticks(range(len(axes)))
    ax.set_xticklabels([f"{a}\n{lo[j]:.3g}–{hi[j]:.3g}" for j, a in enumerate(axes)], rotation=45, ha="right", fontsize=7)
    ax.set_yticks([]); ax.set_title("Candidate compositions and predicted properties (colour = min P(target satisfied))")
    ax.legend(fontsize=7, ncol=2, loc="upper right")
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return path
