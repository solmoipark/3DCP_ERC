"""pmpredict command-line interface."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd


def _cfg(args):
    from .config import load_config
    return load_config(db_path=getattr(args, "db", None))


def cmd_build_features(args):
    from .pipeline import build_features
    s = build_features(_cfg(args), refresh=args.refresh, qa=args.qa)
    print(json.dumps(s, indent=1))


def cmd_build_targets(args):
    from .pipeline import build_target_table
    only = None if args.targets in (None, "all") else args.targets.split(",")
    qa = build_target_table(_cfg(args), only)
    pd.set_option("display.width", 250)
    print(qa.set_index("target")[["rows_in", "final_rows", "n_mixes", "n_papers", "conflict_dropped"]].to_string())


def _targets_arg(args, cfg):
    from .targets import load_target_rules
    rules, _ = load_target_rules()
    if args.target in (None, "all"):
        return [t for t, r in rules.items() if r.get("tier", 2) <= (1 if args.tier1 else 2)]
    return args.target.split(",")


def cmd_train(args):
    from .train import train_target
    cfg = _cfg(args)
    variants = ["general"] + (["3dcp"] if args.variant in ("3dcp", "both") else [])
    if args.variant == "3dcp":
        variants = ["3dcp"]
    for t in _targets_arg(args, cfg):
        for v in variants:
            meta = train_target(t, cfg, variant=v, do_cv=not args.no_cv, leakage_check=args.leakage_check,
                                n_boot=args.n_boot)
            if meta:
                cv = meta["cv"]
                print(f"{t:28s} {v:8s} n={meta['n_train']:6d} papers={meta['n_papers']:4d} tier={meta['tier']:6s} "
                      f"R2={cv.get('r2', float('nan')):.3f} RMSE={cv.get('rmse', float('nan')):.3g} "
                      f"cov80={cv.get('coverage_conformal', float('nan')):.2f} ridgeR2={cv.get('ridge_r2', float('nan')):.3f}"
                      + (f" leak_gap={cv.get('leakage_gap_r2'):.3f}" if cv.get("leakage_gap_r2") is not None else ""))
    from .pipeline import write_summary
    write_summary(cfg)


def cmd_evaluate(args):
    args.no_cv = False
    args.n_boot = 0
    cmd_train(args)


def cmd_predict(args):
    from .predict import predict_specs
    from .schema import MixSpec
    cfg = _cfg(args)
    specs = MixSpec.from_json(args.mix)
    specs = specs if isinstance(specs, list) else [specs]
    targets = None if args.targets in (None, "all") else args.targets.split(",")
    out = predict_specs(specs, cfg, targets, allow_schema_mismatch=args.allow_schema_mismatch)
    if args.flow_curve:
        from .flowcurve import analogue_curves, plot_flow_curve, predict_flow_curves
        P, band = predict_flow_curves(specs, cfg)
        base = Path(args.flow_curve)
        band.to_csv(base.with_suffix(".csv"), index=False)
        for r in P.itertuples(index=False):
            b = band[band.spec == r.spec]
            an = analogue_curves(specs[[s.name or f"mix{i}" for i, s in enumerate(specs)].index(r.spec)], cfg)
            fig = plot_flow_curve(b, an, title=f"{r.spec}: τ₀={r.tau0_q50:.0f} Pa [{r.tau0_q10:.0f},{r.tau0_q90:.0f}], "
                                                f"μ={r.mu_q50:.2f} Pa·s [{r.mu_q10:.2f},{r.mu_q90:.2f}]")
            p = base.with_suffix(".png") if len(P) == 1 else base.with_name(f"{base.stem}_{r.spec}.png")
            fig.savefig(p)
            print(f"flow curve -> {p}")
    if args.thixo_curve:
        from .thixocurve import analogue_static_curves, plot_static_curve, predict_static_curve
        base = Path(args.thixo_curve)
        for i, s in enumerate(specs):
            curve, info = predict_static_curve(s, cfg)
            an = analogue_static_curves(s, cfg)
            t0 = info["tau0_model"]
            am = info.get("athix_model")
            ath_txt = f"Athix={am[1]:.3f} Pa/s [{am[0]:.3f},{am[2]:.3f}]" if am else f"Athix(모델 함의)≈{info['athix_implied_model']:.3f} Pa/s"
            fig = plot_static_curve(curve, an, title=f"{s.name or f'mix{i}'}: τ_s(0)={t0[1]:.0f} Pa [{t0[0]:.0f},{t0[2]:.0f}], {ath_txt}")
            p = base.with_suffix(".png") if len(specs) == 1 else base.with_name(f"{base.stem}_{s.name or i}.png")
            fig.savefig(p); curve.to_csv(p.with_suffix(".csv"), index=False)
            print(f"structuration curve -> {p}")
    if args.out:
        out.to_json(args.out, orient="records", indent=1)
    if args.json:
        print(out.to_json(orient="records", indent=1))
    else:
        pd.set_option("display.width", 250)
        cols = ["spec", "target", "q50", "q10", "q90", "unit", "pred_std", "n_train", "cv_r2", "n_range_violations", "model"]
        print(out[cols].to_string(index=False, float_format=lambda v: f"{v:.3g}"))


def cmd_info(args):
    cfg = _cfg(args)
    print(f"db_path      : {cfg.db_path}")
    print(f"data_dir     : {cfg.data_dir}")
    print(f"artifacts_dir: {cfg.artifacts_dir}")
    s = cfg.data_dir / "build_summary.json"
    if s.exists():
        print("features     :", json.loads(s.read_text(encoding="utf-8")))
    m = cfg.artifacts_dir / "manifest.json"
    if m.exists():
        man = json.loads(m.read_text(encoding="utf-8"))
        rows = pd.DataFrame(man["models"]).T
        pd.set_option("display.width", 250)
        print(rows[["target", "variant", "n_train", "n_papers", "tier", "r2", "rmse", "coverage80", "ridge_r2"]].to_string())
    else:
        print("no trained models yet")


def _load_spec(args, cfg):
    from .design.optimize import Evaluator  # noqa: F401  (import check)
    from .design.spec import DesignSpec
    from .predict import Assets
    spec = DesignSpec.load(args.spec)
    if getattr(args, "optimizer", None):
        spec.optimizer = args.optimizer
    if getattr(args, "n_samples", None):
        spec.budget.n_samples = args.n_samples
    if getattr(args, "seed", None) is not None:
        spec.seed = args.seed
    if getattr(args, "no_plots", False):
        spec.output.plots = False
    assets = Assets(cfg)
    ages = {}
    for k, m in assets.manifest["models"].items():
        if m["variant"] == "general":
            meta_p = cfg.artifacts_dir / m["path"] / "meta.json"
            if meta_p.exists():
                ages[m["target"]] = json.loads(meta_p.read_text(encoding="utf-8")).get("age_support") or {}
    warnings = spec.validate(available_targets=set(assets.available_targets()) if not getattr(args, "retrieval_only", False) else None,
                             age_support=ages)
    return spec, warnings


def cmd_design(args):
    import time
    from .design.optimize import Evaluator, run_twostage
    from .design.report import build_result, write_outputs
    from .design.retrieve import LiteratureStore
    cfg = _cfg(args)
    spec, warnings = _load_spec(args, cfg)
    t0 = time.time()
    ev = Evaluator(spec, cfg, cost_table=args.cost_table, co2_table=args.co2_table)
    run = run_twostage(spec, cfg, evaluator=ev)
    store = LiteratureStore(cfg)
    res = build_result(run, ev, store, cfg, warnings)
    out = Path(args.out or (cfg.reports_dir / "design" / spec.name))
    paths = write_outputs(res, out, plots=spec.output.plots)
    print(f"design '{spec.name}': {len(res.candidates)} candidates, {len(res.literature)} literature hits in {time.time() - t0:.0f}s")
    print(f"  feasible {run.diagnostics.get('n_feasible')} / {run.diagnostics.get('n_sampled')} sampled; "
          f"relaxation {run.diagnostics.get('relaxation') or 'none'}")
    for c in res.candidates[:5]:
        preds = ", ".join(f"{q}={p.q50:.3g} [{p.q10:.3g},{p.q90:.3g}] p={p.p_satisfied:.2f}" for q, p in c.predictions.items())
        print(f"  #{c.rank} P={c.p_feasible:.2f} AD={c.ad_max:.2f} :: {c.summary} :: {preds}")
    print("  outputs: " + ", ".join(str(p) for p in paths.values()))


def cmd_retrieve(args):
    from .design.report import literature_frame
    from .design.retrieve import LiteratureStore, retrieve
    cfg = _cfg(args)
    args.retrieval_only = True
    spec, warnings = _load_spec(args, cfg)
    store = LiteratureStore(cfg)
    hits = retrieve(spec, store, n=args.n)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    for h in hits:
        meas = "; ".join(f"{m.quantity}={m.value:.3g}{m.unit}" + (f"@{m.age_d:g}d" if m.age_d else "") for m in h.measured[:4])
        print(f"[{h.tier}] {h.score:.2f} {h.doi} '{h.mix_name}' ({h.year}, 3dcp={h.is_3dcp}) :: {h.composition_summary} :: {meas}")
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        class _R:  # minimal shim for literature_frame
            literature = [h.to_dict() for h in hits]
        literature_frame(_R).to_csv(Path(args.out) / "literature.csv", index=False)
        json.dump([h.to_dict() for h in hits], open(Path(args.out) / "literature.json", "w", encoding="utf-8"), indent=1, default=str)
    for w in warnings:
        print("warning:", w, file=sys.stderr)


def cmd_init_spec(args):
    from .design.spec import TEMPLATES, write_template
    if args.template not in TEMPLATES:
        print(f"unknown template {args.template!r}; available: {sorted(TEMPLATES)}", file=sys.stderr); sys.exit(2)
    p = write_template(args.template, args.out or f"{args.template}.yaml")
    print(f"wrote {p}")


def cmd_list_models(args):
    cmd_info(args)


def cmd_ui(args):
    import subprocess
    from .config import ROOT
    app = ROOT / "app" / "streamlit_app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(args.port)]
    if args.headless:
        cmd += ["--server.headless", "true"]
    print(" ".join(cmd))
    subprocess.run(cmd, check=False)


def cmd_validate_design(args):
    from .design.validate import closed_loop
    cfg = _cfg(args)
    rep = closed_loop(cfg, n=args.n, seed=args.seed or 0)
    print(json.dumps(rep, indent=1, default=str))


def main(argv=None):
    p = argparse.ArgumentParser(prog="pmpredict", description="Paste/mortar property prediction & inverse mix design")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.add_argument("--db", help="path to master.db (overrides config / PMPREDICT_DB)")
    sp = p.add_subparsers(dest="cmd", required=True)

    a = sp.add_parser("build-features", help="DB -> composition -> features (parquet caches)")
    a.add_argument("--refresh", action="store_true", help="re-read the DB instead of the parquet cache")
    a.add_argument("--qa", action="store_true", help="add QA statistics to the summary")
    a.set_defaults(func=cmd_build_features)

    a = sp.add_parser("build-targets", help="measurements -> target table")
    a.add_argument("--targets", default="all")
    a.set_defaults(func=cmd_build_targets)

    for name, fn, help_ in (("train", cmd_train, "grouped CV + fit + save"), ("evaluate", cmd_evaluate, "grouped CV only (no ensemble)")):
        a = sp.add_parser(name, help=help_)
        a.add_argument("--target", default="all", help="target name(s), comma separated, or all")
        a.add_argument("--tier1", action="store_true", help="with 'all': tier-1 targets only")
        a.add_argument("--variant", default="general", choices=["general", "3dcp", "both"])
        a.add_argument("--no-cv", action="store_true")
        a.add_argument("--leakage-check", action="store_true", help="also run random KFold and report the R2 gap")
        a.add_argument("--n-boot", type=int, default=None, help="bootstrap ensemble size (default from config)")
        a.set_defaults(func=fn)

    a = sp.add_parser("predict", help="predict properties for a MixSpec JSON (object or list)")
    a.add_argument("--mix", required=True)
    a.add_argument("--targets", default="all")
    a.add_argument("--out")
    a.add_argument("--json", action="store_true")
    a.add_argument("--allow-schema-mismatch", action="store_true")
    a.add_argument("--flow-curve", metavar="OUT.png", help="also predict the Bingham flow curve (PNG + CSV, with nearest published curves)")
    a.add_argument("--thixo-curve", metavar="OUT.png", help="also predict the static yield stress vs rest time curve (PNG + CSV)")
    a.set_defaults(func=cmd_predict)

    a = sp.add_parser("info", help="show configuration, feature build summary and trained models")
    a.set_defaults(func=cmd_info)

    a = sp.add_parser("design", help="inverse design: spec.yaml -> candidate mixes + literature (report dir)")
    a.add_argument("--spec", required=True)
    a.add_argument("--out")
    a.add_argument("--optimizer", choices=["twostage"])
    a.add_argument("--n-samples", type=int)
    a.add_argument("--seed", type=int)
    a.add_argument("--no-plots", action="store_true")
    a.add_argument("--cost-table", help="YAML with groups: {group: cost_per_kg}")
    a.add_argument("--co2-table", help="YAML with groups: {group: kgCO2e_per_kg}")
    a.set_defaults(func=cmd_design)

    a = sp.add_parser("retrieve", help="published mixes near the target spec (no models needed)")
    a.add_argument("--spec", required=True)
    a.add_argument("-n", type=int, default=20)
    a.add_argument("--out")
    a.set_defaults(func=cmd_retrieve)

    a = sp.add_parser("init-spec", help="write a template design spec")
    a.add_argument("--template", required=True)
    a.add_argument("--out")
    a.set_defaults(func=cmd_init_spec)

    a = sp.add_parser("list-models", help="alias of info")
    a.set_defaults(func=cmd_list_models)

    a = sp.add_parser("ui", help="launch the Streamlit web UI (predict / design / retrieve)")
    a.add_argument("--port", type=int, default=8501)
    a.add_argument("--headless", action="store_true")
    a.set_defaults(func=cmd_ui)

    a = sp.add_parser("validate-design", help="closed-loop test of the inverse layer on held-out real mixes")
    a.add_argument("--n", type=int, default=50)
    a.add_argument("--seed", type=int)
    a.set_defaults(func=cmd_validate_design)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING - 10 * min(args.verbose, 2),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.func(args)


if __name__ == "__main__":
    main()
