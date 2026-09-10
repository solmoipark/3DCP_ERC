"""Report on rheology from digitised flow curves (see pmpredict/curves.py, which the pipeline uses).

  python scripts/curves_rheology.py

Prints fit statistics, agreement between curve-derived Bingham parameters and tabulated values of
the same mixes, and how many rows the curve augmentation adds to the two rheology targets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmpredict.config import load_config  # noqa: E402
from pmpredict.curves import REF_RATES, agreement_report, fit_all, good_fits  # noqa: E402

cfg = load_config()
F = fit_all(cfg.db_path)
G = good_fits(F)
print(f"flow curves fitted: {len(F)} | mixes {F.mix_uid.nunique()} | papers {F.paper_uid.nunique()}")
print(f"good Bingham fits (R2>=0.9, mu>0): {len(G)} | tau0 pct {G.tau0.quantile([.1, .5, .9]).round(1).tolist()} Pa | "
      f"mu pct {G.mu.quantile([.1, .5, .9]).round(2).tolist()} Pa.s")
print("stress at fixed rates available:", {f"tau_{int(r)}": int(F[f'tau_{int(r)}'].notna().sum()) for r in REF_RATES})
T = pd.read_parquet(cfg.data_dir / "targets.parquet")
print(agreement_report(T, cfg.db_path).round(3).to_string(index=False))
cd = T[T.value_kind_mode == "curve_derived"].groupby("target").agg(rows=("mix_uid", "size"), papers=("paper_uid", "nunique"))
print("curve-derived rows currently in targets.parquet:\n", cd.to_string() if len(cd) else " none (run build-targets)")
F.to_csv(cfg.reports_dir / "flow_curve_fits.csv", index=False)
