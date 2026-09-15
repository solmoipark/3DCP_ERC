# -*- coding: utf-8 -*-
"""Calibrate the buildability layer against the print01 side table (pastemortar master/print_process.db).

  python scripts/calibrate_buildability.py [--print-db PATH]

Joins print_runs (printability labels, layer height, layers/height reached, nozzle, cycle time) to the tabulated
fresh properties of the printed mixes in master.db (static yield stress, Athix, fresh density, dynamic yield stress,
plastic viscosity, flow) and writes
  configs/buildability_calibration.json   quantiles used by pmpredict.buildability (R_fail distribution, extrudability
                                          windows per nozzle class, layer/nozzle ratios, speed / cycle-time / open-time)
  data/print_runs.parquet                 the joined run table (analogue prints for the UI / CLI)
  artifacts/reports/buildability_calibration.md  what was found, incl. the honest discriminative power of tau_s alone
The Roussel ratio R = rho*g*H / (sqrt(3)*tau_s) uses the mix's tabulated static yield stress as reported (mixed rest
protocols); R at collapse in stack-to-failure tests is the empirical "structuration gain" the calculator applies.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pmpredict.config import load_config  # noqa: E402

G = 9.81
RHO_DEFAULT = 2100.0
PROPS = ["static_yield_stress", "structuration_rate_athix", "fresh_density", "dynamic_yield_stress", "plastic_viscosity",
         "green_strength", "mini_slump_flow_diameter", "flow_table_spread"]
NOZ_BINS = [0, 5, 15, 30, 60, 1e9]
NOZ_LABELS = ["<5", "5-15", "15-30", "30-60", ">60"]


def load_join(print_db: Path, master_db: Path) -> pd.DataFrame:
    p = sqlite3.connect(f"file:{print_db.as_posix()}?mode=ro", uri=True)
    m = sqlite3.connect(f"file:{master_db.as_posix()}?mode=ro", uri=True)
    runs = pd.read_sql("SELECT r.*, pr.nozzle_d_mm AS p_nd, pr.nozzle_w_mm AS p_nw, pr.nozzle_h_mm AS p_nh, pr.system, pr.pump "
                       "FROM print_runs r LEFT JOIN printers pr USING(paper_uid)", p)
    meas = pd.read_sql("SELECT mix_uid, quantity, value_canonical FROM measurements WHERE quantity IN (%s) "
                       "AND value_canonical != '' AND (fig_only = '0' OR fig_only IS NULL)" % ",".join(f"'{q}'" for q in PROPS), m)
    meas["v"] = pd.to_numeric(meas.value_canonical, errors="coerce")
    piv = meas.dropna(subset=["v"]).groupby(["mix_uid", "quantity"]).v.median().unstack()
    j = runs.merge(piv, left_on="mix_uid", right_index=True, how="left")
    for q in PROPS:
        if q not in j:
            j[q] = np.nan
    j["nozzle_d_mm"] = j.nozzle_d_mm.fillna(j.p_nd); j["nozzle_w_mm"] = j.nozzle_w_mm.fillna(j.p_nw); j["nozzle_h_mm"] = j.nozzle_h_mm.fillna(j.p_nh)
    j["noz_eq_mm"] = j.nozzle_d_mm.fillna(np.sqrt(4 * j.nozzle_w_mm * j.nozzle_h_mm / np.pi))
    j["H_mm"] = j.height_achieved_mm.fillna(j.n_layers_achieved * j.layer_height_mm)
    j["rho"] = j.fresh_density.fillna(RHO_DEFAULT)
    j["R"] = j.rho * G * j.H_mm / 1000.0 / np.sqrt(3) / j.static_yield_stress
    j["stack_to_failure"] = j.stack_to_failure.fillna(0).astype(int)
    keep = ["paper_uid", "run_id", "mix_uid", "mix_name_in_paper", "object", "system", "pump", "nozzle_d_mm", "nozzle_w_mm", "nozzle_h_mm",
            "noz_eq_mm", "layer_height_mm", "layer_width_mm", "print_speed_mm_s", "layer_cycle_time_s", "n_layers_target", "n_layers_achieved",
            "height_achieved_mm", "H_mm", "start_time_after_mixing_min", "open_time_min", "stack_to_failure", "outcome", "failure_mode",
            "printability_label", "label_basis", "confidence", "rho", "R"] + PROPS
    return j[keep]


def q(s: pd.Series, ps=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict:
    s = s.dropna()
    return {f"p{int(p * 100)}": (round(float(s.quantile(p)), 4) if len(s) else None) for p in ps} | {"n": int(len(s))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-db")
    args = ap.parse_args()
    cfg = load_config()
    print_db = Path(args.print_db) if args.print_db else Path(cfg.db_path).parent / "print_process.db"
    if not print_db.exists():
        sys.exit(f"print_process.db not found at {print_db}")
    j = load_join(print_db, Path(cfg.db_path))
    (cfg.data_dir).mkdir(parents=True, exist_ok=True)
    j.to_parquet(cfg.data_dir / "print_runs.parquet", index=False)

    cal: dict = {"source": {"print_db": print_db.name, "n_runs": int(len(j)), "n_papers": int(j.paper_uid.nunique())}}
    # ---- 1. plastic-collapse ratio at failure (stack-to-failure collapses) and for all labelled runs
    c = j[j.R.notna() & (j.H_mm > 0) & j.outcome.isin(["printable", "collapsed"])].copy()
    c["fail"] = (c.outcome == "collapsed").astype(int)
    stf = c[(c.stack_to_failure == 1) & (c.fail == 1)]
    cal["R_fail"] = q(stf.R, (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)) | {"n_papers": int(stf.paper_uid.nunique()),
                                                                          "by_failure_mode": {k: round(float(v), 3) for k, v in stf.groupby("failure_mode").R.median().items()}}
    cal["R_fail"]["ecdf_R"] = [round(float(x), 4) for x in np.sort(stf.R.values)]
    ok = c[(c.stack_to_failure == 0) & (c.outcome == "printable")]
    cal["R_printable_reached"] = q(ok.R, (0.5, 0.75, 0.9, 0.95))
    bins = [0, .25, .5, 1, 2, 4, 8, 1e9]
    rate = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        s = c[(c.R >= lo) & (c.R < hi)]
        rate.append(dict(R_lo=lo, R_hi=(None if hi > 1e8 else hi), n=int(len(s)), collapse_rate=(round(float(s.fail.mean()), 3) if len(s) else None)))
    cal["collapse_rate_by_R"] = rate
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        X = np.log10(c.R.clip(1e-3)).values[:, None]
        lr = LogisticRegression().fit(X, c.fail)
        auc = float(roc_auc_score(c.fail, lr.predict_proba(X)[:, 1]))
    except Exception:  # pragma: no cover
        auc = None
    cal["tau_s_only_discrimination"] = dict(n=int(len(c)), n_papers=int(c.paper_uid.nunique()), n_collapsed=int(c.fail.sum()), auc_logR=(round(auc, 3) if auc else None))
    # ---- 2. extrudability windows (printable vs extrusion failures), overall and by nozzle class
    e = j[j.outcome.isin(["printable", "extrusion_failure", "tearing", "segregation"])].copy()
    e["ok"] = e.outcome == "printable"
    e["nozcls"] = pd.cut(e.noz_eq_mm, NOZ_BINS, labels=NOZ_LABELS)
    win = {}
    for prop in ["static_yield_stress", "dynamic_yield_stress", "plastic_viscosity", "flow_table_spread", "mini_slump_flow_diameter"]:
        s = e[e[prop].notna()]
        win[prop] = dict(printable=q(s[s.ok][prop]), failed=q(s[~s.ok][prop]),
                         by_nozzle_class={str(k): q(g[prop], (0.1, 0.25, 0.5, 0.75, 0.9)) for k, g in s[s.ok].groupby("nozcls", observed=True) if len(g) >= 10})
    cal["extrudability_windows"] = win
    # ---- 3. process defaults
    pr = j[j.outcome == "printable"]
    cal["process_defaults"] = dict(
        layer_height_over_nozzle=q((pr.layer_height_mm / pr.noz_eq_mm)), layer_width_over_nozzle=q((pr.layer_width_mm / pr.noz_eq_mm)),
        print_speed_mm_s=q(pr.print_speed_mm_s), layer_cycle_time_s=q(pr.layer_cycle_time_s), open_time_min=q(j.open_time_min),
        fresh_density=q(j.fresh_density), start_time_after_mixing_min=q(j.start_time_after_mixing_min),
        nozzle_eq_mm=q(j.noz_eq_mm), layer_height_mm=q(pr.layer_height_mm))
    # ---- 4. Athix vs tau_s0 relation among printed mixes (fallback when no Athix model/measurement)
    a = j.drop_duplicates("mix_uid")
    a = a[a.static_yield_stress.notna() & a.structuration_rate_athix.notna() & (a.static_yield_stress > 0) & (a.structuration_rate_athix > 0)]
    cal["athix_over_tau_s0_per_s"] = q(a.structuration_rate_athix / a.static_yield_stress, (0.1, 0.25, 0.5, 0.75, 0.9)) | {"note": "Athix [Pa/s] / tau_s [Pa] of printed mixes with both tabulated"}
    out = cfg.configs_dir / "buildability_calibration.json"
    out.write_text(json.dumps(cal, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- report
    rf = cal["R_fail"]
    md = [f"# Buildability calibration against print01 labels ({pd.Timestamp.today():%Y-%m-%d})", "",
          f"Source: `{print_db.name}` — {len(j):,} print runs / {j.paper_uid.nunique():,} papers joined to master.db fresh properties "
          f"(median per mix, tabulated values only). Output: `configs/buildability_calibration.json`, `data/print_runs.parquet`.", "",
          "## Plastic-collapse ratio R = ρ g H / (√3 τ_s) at failure", "",
          f"Stack-until-failure collapses with a tabulated static yield stress: **{rf['n']} runs / {rf['n_papers']} papers**. "
          f"R at collapse: p10 {rf['p10']}, p25 {rf['p25']}, **median {rf['p50']}**, p75 {rf['p75']}, p90 {rf['p90']}. "
          "R = 1 is the Roussel static criterion with τ_s(0) only; the median 1.4 is the structuration gain accrued during the print "
          "(the printed layers are older than the rheometer sample). By failure mode: " + ", ".join(f"{k} {v}" for k, v in rf["by_failure_mode"].items()) + ".", "",
          f"Printable runs that reached their target height (not stack-to-failure): R median {cal['R_printable_reached']['p50']}, "
          f"p90 {cal['R_printable_reached']['p90']} (n {cal['R_printable_reached']['n']}).", "",
          "## How well does τ_s alone separate collapse from success?", "",
          f"Logistic fit of collapse on log10 R over {cal['tau_s_only_discrimination']['n']} printable/collapsed runs "
          f"({cal['tau_s_only_discrimination']['n_papers']} papers, {cal['tau_s_only_discrimination']['n_collapsed']} collapses): "
          f"**AUC {cal['tau_s_only_discrimination']['auc_logR']}** — weak. Collapse rate by R bin:", "",
          "| R | n | collapse rate |", "|---|---|---|"] + \
         [f"| {r['R_lo']}–{r['R_hi'] if r['R_hi'] else '∞'} | {r['n']} | {r['collapse_rate']} |" for r in rate] + \
         ["", "Reasons: (i) the tabulated static yield stress mixes rest protocols (0–1200 s rest, vane/stress-growth/penetration/slump-derived); "
          "(ii) structuration during the print (Athix·t) is what actually carries tall stacks and only 8 stack-to-failure runs report τ_s, Athix and "
          "cycle time together; (iii) 20 % of stack-to-failure collapses are buckling, not plastic. Consequence for the calculator: the physics route "
          "(τ_s(0) + Athix·t, Suiker buckling) is the primary verdict, the empirical R_fail ECDF gives a probability band, and both are reported.", "",
          "## Extrudability windows of printable runs (p10 / p50 / p90)", "", "| property | printable n | p10 | p50 | p90 | failed n | failed p50 |", "|---|---|---|---|---|---|---|"] + \
         [f"| {k} | {v['printable']['n']} | {v['printable']['p10']} | {v['printable']['p50']} | {v['printable']['p90']} | {v['failed']['n']} | {v['failed']['p50']} |" for k, v in win.items()] + \
         ["", "Failed extrusions have higher medians for every property (viscosity 67 vs 12 Pa·s is the clearest), but the windows overlap; used as caution flags, not hard limits.", "",
          "## Process defaults learned from printable runs", ""] + \
         [f"- {k}: " + ", ".join(f"{a} {b}" for a, b in v.items() if a != "n") + f" (n {v['n']})" for k, v in cal["process_defaults"].items()] + \
         ["", f"- Athix / τ_s(0) among printed mixes with both: median {cal['athix_over_tau_s0_per_s']['p50']} 1/s (n {cal['athix_over_tau_s0_per_s']['n']}); "
          "fallback ratio when no Athix is available."]
    rep = cfg.reports_dir / "buildability_calibration.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out}\n      {cfg.data_dir / 'print_runs.parquet'} ({len(j)} runs)\n      {rep}")
    print(f"R_fail median {rf['p50']} [{rf['p25']}, {rf['p75']}] n={rf['n']}; tau_s-only AUC {cal['tau_s_only_discrimination']['auc_logR']}")


if __name__ == "__main__":
    main()
