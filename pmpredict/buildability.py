# -*- coding: utf-8 -*-
"""Buildability layer: print job (nozzle, geometry, schedule) x fresh material -> verdict, schedule window, design spec.

Physics
  plastic collapse (Roussel 2018, Perrot 2016): the bottom layer of an n-layer stack carries sigma_v = rho*g*n*h and
      yields when sigma_v > sqrt(3) * tau_s(t) with tau_s(t) = tau_s(0) + Athix*t (linear structuration, t = n*t_c).
      n_max = sqrt(3) tau_s(0) / (rho g h - sqrt(3) Athix t_c); unlimited when sqrt(3) Athix t_c >= rho g h.
  elastic buckling (Suiker 2018, free straight wall clamped at the base): l_cr = (7.8373 E(t) t_w^2 / (12 rho g))^(1/3)
      with the green modulus E(t) = (E/tau) * tau_s(t). Closed sections (hollow cylinder, column) are far stiffer and
      are not checked (reported as n/a).
  open time: start time after mixing + print duration must stay inside the open time when one is given.
Calibration (configs/buildability_calibration.json, from the print01 side table, scripts/calibrate_buildability.py):
  R_fail = rho g H_collapse / (sqrt(3) tau_s,tabulated) of 146 stack-until-failure collapses (median 1.39, IQR 0.64-2.87);
  its ECDF turns the static ratio of a job into an empirical collapse probability. Extrudability windows (p10-p90 of
  printable runs) per nozzle class flag pumping/extrusion risk. tau_s alone separates collapse from success with AUC
  0.59 only, so the physics route with structuration is the primary verdict and the empirical band is shown next to it.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import CONFIGS_DIR, PipelineConfig
from .schema import MixSpec

G = 9.81
SQ3 = math.sqrt(3.0)
SUIKER_C = 7.8373            # first buckling eigenvalue of a wall clamped at its base under self-weight (Suiker 2018)
OBJECTS = ("wall", "hollow_cylinder", "column", "other")


# ---------------------------------------------------------------------------------------------------- calibration
def load_calibration(cfg: PipelineConfig | None = None) -> dict:
    p = (cfg.configs_dir if cfg else CONFIGS_DIR) / "buildability_calibration.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _pd(cal: dict, key: str, stat: str, default: float) -> float:
    try:
        v = cal["process_defaults"][key][stat]
        return float(v) if v is not None else default
    except (KeyError, TypeError):
        return default


def nozzle_class(noz_eq_mm: float | None) -> str | None:
    if noz_eq_mm is None or not np.isfinite(noz_eq_mm):
        return None
    for hi, lab in ((5, "<5"), (15, "5-15"), (30, "15-30"), (60, "30-60")):
        if noz_eq_mm < hi:
            return lab
    return ">60"


def extrudability_window(cal: dict, prop: str, noz_eq_mm: float | None) -> dict | None:
    """p10/p50/p90 of printable runs for `prop`, per nozzle class when >= 10 runs, else overall."""
    w = (cal.get("extrudability_windows") or {}).get(prop)
    if not w:
        return None
    cls = nozzle_class(noz_eq_mm)
    byc = w.get("by_nozzle_class") or {}
    src = byc.get(cls) if cls in byc else None
    if src:
        return dict(src, scope=f"nozzle {cls} mm")
    return dict(w["printable"], scope="all printable runs")


# ---------------------------------------------------------------------------------------------------- inputs
@dataclass
class PrintJob:
    """What is printed, with what nozzle, at what schedule. None fields are filled by `resolve()` from calibrated defaults."""
    name: str = "job"
    object_type: str = "wall"                    # wall | hollow_cylinder | column | other
    target_height_mm: float = 500.0
    footprint_mm: float | None = None            # wall length or cylinder diameter (gives the path length per layer)
    path_length_mm: float | None = None          # printed path per layer; overrides footprint_mm
    wall_filaments: int = 1                      # filaments across the wall thickness
    nozzle_d_mm: float | None = None
    nozzle_w_mm: float | None = None
    nozzle_h_mm: float | None = None
    layer_height_mm: float | None = None         # default 0.5 x equivalent nozzle diameter (printable median)
    layer_width_mm: float | None = None          # default 1.2 x equivalent nozzle diameter
    print_speed_mm_s: float | None = None        # default 40 mm/s (printable median)
    layer_cycle_time_s: float | None = None      # default path length / speed + dwell
    dwell_s: float = 0.0
    start_time_after_mixing_min: float = 0.0
    open_time_min: float | None = None
    safety_factor: float = 1.5                   # applied to the self-weight load in the plastic criterion
    check_buckling: bool = True                  # Suiker free-wall buckling (walls only; most conservative boundary condition)
    notes: str = ""

    # ---- derived
    @property
    def nozzle_eq_mm(self) -> float | None:
        if self.nozzle_d_mm:
            return float(self.nozzle_d_mm)
        if self.nozzle_w_mm and self.nozzle_h_mm:
            return float(math.sqrt(4 * self.nozzle_w_mm * self.nozzle_h_mm / math.pi))
        return None

    @property
    def n_layers(self) -> int:
        return max(1, int(math.ceil(self.target_height_mm / self.layer_height_mm)))

    @property
    def wall_thickness_mm(self) -> float | None:
        return self.layer_width_mm * self.wall_filaments if self.layer_width_mm else None

    def resolve(self, cal: dict | None = None) -> tuple["PrintJob", list[str]]:
        """Fill missing process values from the calibration defaults; returns (copy, list of what was defaulted)."""
        cal = cal or {}
        j = PrintJob(**asdict(self))
        filled = []
        d = j.nozzle_eq_mm
        if j.object_type not in OBJECTS:
            raise ValueError(f"object_type must be one of {OBJECTS}")
        if j.layer_height_mm is None:
            if d is None:
                raise ValueError("give layer_height_mm or a nozzle size")
            j.layer_height_mm = round(d * _pd(cal, "layer_height_over_nozzle", "p50", 0.5), 2)
            filled.append(f"layer_height_mm = {j.layer_height_mm} (0.5 x nozzle, printable median)")
        if j.layer_width_mm is None:
            if d is not None:
                j.layer_width_mm = round(d * _pd(cal, "layer_width_over_nozzle", "p50", 1.2), 2)
                filled.append(f"layer_width_mm = {j.layer_width_mm} (1.2 x nozzle, printable median)")
            elif j.nozzle_w_mm:
                j.layer_width_mm = float(j.nozzle_w_mm)
        if j.path_length_mm is None and j.footprint_mm:
            if j.object_type == "wall":
                j.path_length_mm = j.footprint_mm * j.wall_filaments
            elif j.object_type == "hollow_cylinder":
                j.path_length_mm = math.pi * j.footprint_mm * j.wall_filaments
        if j.layer_cycle_time_s is None:
            if j.path_length_mm is None:
                raise ValueError("give layer_cycle_time_s, or path_length_mm / footprint_mm so it can be computed from the print speed")
            if j.print_speed_mm_s is None:
                j.print_speed_mm_s = _pd(cal, "print_speed_mm_s", "p50", 40.0)
                filled.append(f"print_speed_mm_s = {j.print_speed_mm_s} (printable median)")
            j.layer_cycle_time_s = j.path_length_mm / j.print_speed_mm_s + j.dwell_s
            filled.append(f"layer_cycle_time_s = {j.layer_cycle_time_s:.1f} (path {j.path_length_mm:.0f} mm / {j.print_speed_mm_s:g} mm/s + dwell {j.dwell_s:g} s)")
        return j, filled

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict) -> "PrintJob":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load(cls, path: str | Path) -> "PrintJob":
        p = Path(path)
        d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.suffix in (".yaml", ".yml") else json.loads(p.read_text(encoding="utf-8"))
        return cls.from_dict(d)


@dataclass
class FreshMaterial:
    """Fresh-state inputs at deposition. Bands (q10, q90) are optional and enable the probabilistic verdict."""
    tau_s0_Pa: float
    athix_Pa_s: float | None = None              # None -> calibrated fallback ratio x tau_s0 (flagged)
    rho_kg_m3: float = 2100.0
    E_over_tau: float = 25.0                     # green modulus / static yield stress (Wolfs et al. 2018 order: E0 ~ 80 kPa at tau ~ 3 kPa)
    dynamic_yield_Pa: float | None = None
    plastic_viscosity_Pa_s: float | None = None
    tau_s0_band: tuple[float, float] | None = None
    athix_band: tuple[float, float] | None = None
    source: str = "user"

    def athix(self, cal: dict | None = None) -> tuple[float, str | None]:
        if self.athix_Pa_s is not None:
            return float(self.athix_Pa_s), None
        ratio = float(((cal or {}).get("athix_over_tau_s0_per_s") or {}).get("p50") or 0.0007)
        return self.tau_s0_Pa * ratio, f"Athix not given: {ratio:.4f} 1/s x tau_s(0) (median of printed mixes with both tabulated)"


def material_from_mix(spec: MixSpec, cfg: PipelineConfig, assets=None) -> FreshMaterial:
    """Fresh material predicted by pmpredict for a MixSpec (static yield at rest 0, Athix, dynamic yield, viscosity)."""
    from .predict import Assets, predict_specs
    s = MixSpec.from_dict(spec.to_dict())
    s.conditions.rest_time_s = 0.0
    assets = assets or Assets(cfg)
    want = [t for t in ("static_yield_stress", "structuration_rate_athix", "dynamic_yield_stress", "plastic_viscosity") if t in assets.available_targets()]
    df = predict_specs([s], cfg, targets=want)
    g = {r.target: r for r in df.itertuples()}
    if "static_yield_stress" not in g:
        raise RuntimeError("no static_yield_stress model available")
    sy = g["static_yield_stress"]
    at = g.get("structuration_rate_athix")
    return FreshMaterial(tau_s0_Pa=float(sy.q50), athix_Pa_s=(float(at.q50) if at is not None else None),
                         dynamic_yield_Pa=(float(g["dynamic_yield_stress"].q50) if "dynamic_yield_stress" in g else None),
                         plastic_viscosity_Pa_s=(float(g["plastic_viscosity"].q50) if "plastic_viscosity" in g else None),
                         tau_s0_band=(float(sy.q10), float(sy.q90)), athix_band=((float(at.q10), float(at.q90)) if at is not None else None),
                         source=f"pmpredict ({sy.model}" + (f", {at.model}" if at is not None else "") + ")")


# ---------------------------------------------------------------------------------------------------- physics
def plastic_n_max(h_mm: float, rho: float, tau0: float, athix: float, t_c: float, sf: float = 1.0) -> float:
    """Roussel: sf*rho*g*h*n = sqrt(3)*(tau0 + Athix*n*t_c)  ->  n_max (inf when structuration outpaces loading)."""
    denom = sf * rho * G * h_mm / 1000.0 - SQ3 * athix * t_c
    if denom <= 0:
        return math.inf
    return SQ3 * tau0 / denom


def required_tau0(n: float, h_mm: float, rho: float, athix: float, t_c: float, sf: float) -> float:
    return max(0.0, sf * rho * G * h_mm / 1000.0 * n / SQ3 - athix * n * t_c)


def required_athix(n: float, h_mm: float, rho: float, tau0: float, t_c: float, sf: float) -> float:
    return max(0.0, (sf * rho * G * h_mm / 1000.0 * n / SQ3 - tau0) / max(n * t_c, 1e-9))


def min_cycle_time(n: float, h_mm: float, rho: float, tau0: float, athix: float, sf: float) -> float:
    """Smallest layer cycle time for which n layers stand with the load factor sf (0 = any; inf = impossible)."""
    need = sf * rho * G * h_mm / 1000.0 * n / SQ3 - tau0
    if need <= 0:
        return 0.0
    if athix <= 0:
        return math.inf
    return need / (athix * n)


def buckling_n_max(h_mm: float, t_wall_mm: float, rho: float, tau0: float, athix: float, t_c: float, E_over_tau: float,
                   n_cap: int = 5000) -> float:
    """Suiker (2018) self-weight buckling of a free wall; E grows with tau_s(t). Returns the last stable layer count."""
    tw = t_wall_mm / 1000.0
    for n in range(1, n_cap + 1):
        E = E_over_tau * (tau0 + athix * n * t_c)
        l_cr = (SUIKER_C * E * tw ** 2 / (12.0 * rho * G)) ** (1.0 / 3.0)
        if n * h_mm / 1000.0 > l_cr:
            return float(n - 1)
    return math.inf


def empirical_collapse_probability(R: float, cal: dict) -> float | None:
    """ECDF of the stack-to-failure collapse ratio at the job's static ratio R = rho g H / (sqrt3 tau_s0)."""
    ec = (cal.get("R_fail") or {}).get("ecdf_R")
    if not ec:
        return None
    ec = np.asarray(ec, float)
    return float((ec <= R).mean())


# ---------------------------------------------------------------------------------------------------- assessment
@dataclass
class Verdict:
    label: str                                   # printable | borderline | non_printable
    governing: str                               # plastic_collapse | elastic_buckling | open_time | none
    reasons: list[str]
    n_target: int
    layer_height_mm: float
    layer_cycle_time_s: float
    print_time_min: float
    tau_s0_Pa: float
    athix_Pa_s: float
    tau_s_end_Pa: float                          # tau_s at the end of the print (bottom layer)
    n_max_plastic: float
    n_max_plastic_sf: float                      # with the safety factor on the load
    n_max_buckling: float | None
    H_max_mm: float
    margin: float                                # n_max_plastic / n_target
    R_static: float                              # rho g H / (sqrt3 tau_s0)
    p_collapse_empirical: float | None
    p_stable_physics: float | None               # Monte Carlo over the material bands (None without bands)
    tau0_required_Pa: float                      # for the given schedule (with sf)
    athix_required_Pa_s: float
    min_cycle_time_s: float
    critical_cycle_time_s: float                 # rho g h / (sqrt3 Athix): unlimited stacking beyond this
    open_time_ok: bool | None
    extrudability: dict
    defaults_used: list[str]
    warnings: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float) and math.isinf(v):
                d[k] = None
        return d


def assess(job: PrintJob, mat: FreshMaterial, cal: dict | None = None, n_mc: int = 2000, seed: int = 0) -> Verdict:
    cal = cal if cal is not None else load_calibration()
    job, filled = job.resolve(cal)
    warnings: list[str] = []
    athix, note = mat.athix(cal)
    if note:
        warnings.append(note)
    h, n, t_c, rho, tau0, sf = job.layer_height_mm, job.n_layers, job.layer_cycle_time_s, mat.rho_kg_m3, mat.tau_s0_Pa, job.safety_factor
    t_print = n * t_c
    if t_print > 5400:
        warnings.append("print longer than 90 min: the linear tau_s(t) law overestimates late structuration (Perrot exponential regime)")
    n_pl = plastic_n_max(h, rho, tau0, athix, t_c)
    n_pl_sf = plastic_n_max(h, rho, tau0, athix, t_c, sf)
    n_bk = None
    if job.object_type == "wall" and job.wall_thickness_mm and job.check_buckling:
        n_bk = buckling_n_max(h, job.wall_thickness_mm, rho, tau0, athix, t_c, mat.E_over_tau)
    n_gov = min(n_pl, n_bk if n_bk is not None else math.inf)
    H_max = n_gov * h if math.isfinite(n_gov) else math.inf
    R_static = rho * G * (n * h / 1000.0) / SQ3 / tau0
    p_emp = empirical_collapse_probability(R_static, cal)
    # Monte Carlo over the material bands
    p_phys = None
    if mat.tau_s0_band or mat.athix_band:
        from .flowcurve import _sample_lognormal_split
        rng = np.random.default_rng(seed)
        t0s = _sample_lognormal_split(mat.tau_s0_band[0], tau0, mat.tau_s0_band[1], n_mc, rng) if mat.tau_s0_band else np.full(n_mc, tau0)
        ats = _sample_lognormal_split(mat.athix_band[0], athix, mat.athix_band[1], n_mc, rng) if mat.athix_band else np.full(n_mc, athix)
        denom = rho * G * h / 1000.0 - SQ3 * ats * t_c
        nmax = np.where(denom <= 0, np.inf, SQ3 * t0s / np.maximum(denom, 1e-12))
        p_phys = float((nmax >= n).mean())
    # extrudability flags
    ext = {}
    for prop, val in (("static_yield_stress", tau0), ("dynamic_yield_stress", mat.dynamic_yield_Pa), ("plastic_viscosity", mat.plastic_viscosity_Pa_s)):
        if val is None:
            continue
        w = extrudability_window(cal, prop, job.nozzle_eq_mm)
        if not w or w.get("p10") is None:
            continue
        status = "inside" if w["p10"] <= val <= w["p90"] else ("above p90" if val > w["p90"] else "below p10")
        ext[prop] = dict(value=val, p10=w["p10"], p50=w["p50"], p90=w["p90"], scope=w["scope"], status=status)
    open_ok = None
    if job.open_time_min is not None:
        open_ok = job.start_time_after_mixing_min + t_print / 60.0 <= job.open_time_min
    # verdict
    reasons = []
    governing = "none"
    if n_pl < n:
        governing = "plastic_collapse"
        reasons.append(f"plastic collapse expected at layer {n_pl:.0f} of {n} (H_max {n_pl * h:.0f} mm < {job.target_height_mm:.0f} mm)")
    if n_bk is not None and n_bk < n:
        governing = "elastic_buckling" if governing == "none" or n_bk < n_pl else governing
        reasons.append(f"self-weight buckling of a free straight wall expected at layer {n_bk:.0f} (thickness {job.wall_thickness_mm:.0f} mm, E = {mat.E_over_tau:g} x tau_s; closed or braced paths are stiffer: set check_buckling false or add wall_filaments)")
    if open_ok is False:
        governing = governing if governing != "none" else "open_time"
        reasons.append(f"print duration {t_print / 60:.0f} min + start {job.start_time_after_mixing_min:g} min exceeds open time {job.open_time_min:g} min")
    label = "non_printable" if reasons else "printable"
    if label == "printable":
        if n_pl_sf < n:
            label = "borderline"; reasons.append(f"stands without margin: with load factor {sf:g} collapse at layer {n_pl_sf:.0f} of {n}")
        if p_emp is not None and p_emp > 0.5:
            label = "borderline"; reasons.append(f"static ratio R = {R_static:.2f}: {p_emp:.0%} of published stack-to-failure collapses occurred below this ratio")
        if p_phys is not None and p_phys < 0.7:
            label = "borderline"; reasons.append(f"only {p_phys:.0%} of the predicted material band stands {n} layers")
        for prop, e in ext.items():
            if e["status"] != "inside":
                label = "borderline"; reasons.append(f"{prop} {e['value']:.3g} is {e['status']} of printable runs ({e['scope']}: {e['p10']:.3g}-{e['p90']:.3g})")
        if not reasons:
            reasons.append(f"stands {n} layers with load factor {sf:g}: n_max {n_pl:.0f}" + (f", buckling n_max {n_bk:.0f}" if n_bk is not None and math.isfinite(n_bk) else "")
                           + (f"; empirical collapse probability {p_emp:.0%}" if p_emp is not None else ""))
    return Verdict(label=label, governing=governing, reasons=reasons, n_target=n, layer_height_mm=h, layer_cycle_time_s=t_c,
                   print_time_min=t_print / 60.0, tau_s0_Pa=tau0, athix_Pa_s=athix, tau_s_end_Pa=tau0 + athix * t_print,
                   n_max_plastic=n_pl, n_max_plastic_sf=n_pl_sf, n_max_buckling=n_bk, H_max_mm=H_max, margin=(n_pl / n),
                   R_static=R_static, p_collapse_empirical=p_emp, p_stable_physics=p_phys,
                   tau0_required_Pa=required_tau0(n, h, rho, athix, t_c, sf), athix_required_Pa_s=required_athix(n, h, rho, tau0, t_c, sf),
                   min_cycle_time_s=min_cycle_time(n, h, rho, tau0, athix, sf),
                   critical_cycle_time_s=(rho * G * h / 1000.0 / (SQ3 * athix) if athix > 0 else math.inf),
                   open_time_ok=open_ok, extrudability=ext, defaults_used=filled, warnings=warnings)


# ---------------------------------------------------------------------------------------------------- schedule
def schedule(job: PrintJob, mat: FreshMaterial, cal: dict | None = None, n_grid: int = 60) -> dict:
    """Layer-cycle-time window for the target height, the matching print-speed window, and an n_max(t_c) sweep."""
    cal = cal if cal is not None else load_calibration()
    job, filled = job.resolve(cal)
    athix, _ = mat.athix(cal)
    h, n, rho, tau0, sf = job.layer_height_mm, job.n_layers, mat.rho_kg_m3, mat.tau_s0_Pa, job.safety_factor
    t_lo = min_cycle_time(n, h, rho, tau0, athix, sf)
    t_lo_nosf = min_cycle_time(n, h, rho, tau0, athix, 1.0)
    # upper bound: open time (hard) or the p90 cycle time of printable runs (interlayer-bond caution)
    bond_cap = _pd(cal, "layer_cycle_time_s", "p90", 1200.0)
    if job.open_time_min is not None:
        t_hi = max(0.0, (job.open_time_min - job.start_time_after_mixing_min) * 60.0 / n)
        t_hi_basis = f"open time {job.open_time_min:g} min - start {job.start_time_after_mixing_min:g} min over {n} layers"
    else:
        t_hi = bond_cap
        t_hi_basis = f"p90 layer cycle time of printable runs ({bond_cap:.0f} s); give open_time_min for a hard bound"
    feasible = math.isfinite(t_lo) and t_lo <= t_hi
    rec = None
    if feasible:
        rec = min(max(t_lo * 1.2, job.layer_cycle_time_s if t_lo <= job.layer_cycle_time_s <= t_hi else t_lo * 1.2), t_hi)
    speed = None
    if job.path_length_mm:
        L = job.path_length_mm
        v_hi = (L / max(t_lo - job.dwell_s, 1e-9)) if t_lo > job.dwell_s else math.inf
        v_lo = L / max(t_hi - job.dwell_s, 1e-9) if t_hi > job.dwell_s else math.inf
        speed = dict(v_min_mm_s=v_lo, v_max_mm_s=v_hi, current_mm_s=job.print_speed_mm_s,
                     v_recommended_mm_s=(L / max(rec - job.dwell_s, 1e-9) if rec else None))
    ts = np.geomspace(max(1.0, t_lo * 0.2 if t_lo > 0 else 1.0), max(t_hi * 2, 60.0), n_grid)
    sweep = pd.DataFrame(dict(layer_cycle_time_s=ts,
                              n_max=[plastic_n_max(h, rho, tau0, athix, t, 1.0) for t in ts],
                              n_max_sf=[plastic_n_max(h, rho, tau0, athix, t, sf) for t in ts],
                              print_time_min=ts * n / 60.0))
    return dict(n_layers=n, layer_height_mm=h, t_c_min_s=t_lo, t_c_min_no_sf_s=t_lo_nosf, t_c_max_s=t_hi, t_c_max_basis=t_hi_basis,
                t_c_current_s=job.layer_cycle_time_s, t_c_recommended_s=rec, feasible=feasible,
                print_time_recommended_min=(rec * n / 60.0 if rec else None), speed=speed,
                critical_cycle_time_s=(rho * G * h / 1000.0 / (SQ3 * athix) if athix > 0 else math.inf),
                tau0_required_at_current_Pa=required_tau0(n, h, rho, athix, job.layer_cycle_time_s, sf),
                athix_required_at_current_Pa_s=required_athix(n, h, rho, tau0, job.layer_cycle_time_s, sf),
                sweep=sweep, defaults_used=filled)


# ---------------------------------------------------------------------------------------------------- inverse: job -> design spec
def job_to_design_dict(job: PrintJob, space: dict, cal: dict | None = None, rho: float = 2100.0, extra_targets: list[dict] | None = None,
                       name: str | None = None, p_min_rheology: float = 0.4, objectives: list[dict] | None = None,
                       budget: dict | None = None, steer_athix: bool = True) -> tuple[dict, dict]:
    """DesignSpec dict whose rheology targets encode the job: the Roussel criterion at the end of the print becomes a
    `static_yield_stress_at_rest` >= target at rest_time = print duration (tau_s(0) + Athix*t through the two models),
    tau_s(0) is boxed into the extrudability window of the nozzle class, and viscosity is capped at its p90."""
    cal = cal if cal is not None else load_calibration()
    job, filled = job.resolve(cal)
    n, h, t_c, sf = job.n_layers, job.layer_height_mm, job.layer_cycle_time_s, job.safety_factor
    t_print = n * t_c
    S = sf * rho * G * h / 1000.0 * n / SQ3            # required tau_s at the end of the print [Pa]
    w_sy = extrudability_window(cal, "static_yield_stress", job.nozzle_eq_mm) or {}
    w_pv = extrudability_window(cal, "plastic_viscosity", job.nozzle_eq_mm) or {}
    targets = [dict(quantity="static_yield_stress_at_rest", kind="ge", lo=S, unit="Pa", conditions=dict(rest_time_s=t_print), p_min=0.5)]
    if w_sy.get("p10"):
        targets.append(dict(quantity="static_yield_stress", kind="range", lo=float(w_sy["p10"]), hi=float(max(w_sy["p90"], S * 0.5 + 1)),
                            unit="Pa", conditions=dict(rest_time_s=0), p_min=p_min_rheology))
    if w_pv.get("p90"):
        targets.append(dict(quantity="plastic_viscosity", kind="le", lo=None, hi=float(w_pv["p90"]), unit="Pa.s", p_min=p_min_rheology))
    if steer_athix:
        # the rheology models are wide, so P(satisfied) is a flat landscape; steering on the pessimistic Athix quantile keeps the
        # search moving toward mixes that structurate fast enough for the schedule
        targets.append(dict(quantity="structuration_rate_athix", kind="maximize", unit="Pa/s"))
    targets += list(extra_targets or [])
    sp = dict(space)
    sp.setdefault("is_3dcp", True)
    if objectives is None:
        objectives = ([dict(name="quantity:structuration_rate_athix", direction="min")] if steer_athix else []) + [dict(name="clinker_fraction", direction="min")]
    d = dict(name=name or f"print_{job.name}", targets=targets, space=sp, objectives=objectives,
             risk=dict(p_min=0.5, ad_max=1.0, combine="product"),
             budget=budget or dict(n_samples=8192, n_refine=6, refine_generations=15, time_limit_s=150),
             output=dict(top_n=8, n_literature=15, plots=True), seed=0)
    info = dict(n_layers=n, layer_height_mm=h, layer_cycle_time_s=t_c, print_time_s=t_print, tau_s_required_end_Pa=S,
                tau_s0_window=(w_sy or None), viscosity_cap=(w_pv or None), defaults_used=filled)
    return d, info


def design_for_job(job: PrintJob, space: dict, cfg: PipelineConfig, out_dir: Path | None = None, extra_targets: list[dict] | None = None,
                   rho: float = 2100.0, cal: dict | None = None, budget: dict | None = None, plots: bool = True):
    """Run the inverse design for a job and assess every candidate with its own predicted fresh state.
    Returns (DesignResult, per-candidate table, spec dict, info, output paths)."""
    from .design.optimize import Evaluator, run_twostage
    from .design.report import build_result, write_outputs
    from .design.retrieve import LiteratureStore
    from .design.spec import DesignSpec
    from .predict import Assets
    cal = cal if cal is not None else load_calibration(cfg)
    d, info = job_to_design_dict(job, space, cal, rho=rho, extra_targets=extra_targets, budget=budget)
    spec = DesignSpec.from_dict(d)
    assets = Assets(cfg)
    warns = spec.validate(available_targets=set(assets.available_targets()))
    ev = Evaluator(spec, cfg)
    run = run_twostage(spec, cfg, evaluator=ev)
    res = build_result(run, ev, LiteratureStore(cfg), cfg, warns)
    paths = {}
    if out_dir is not None:
        paths = write_outputs(res, Path(out_dir), plots=plots)
    rows = []
    for c in res.candidates:
        mix = MixSpec.from_dict(c.mix)
        mat = material_from_mix(mix, cfg, assets)
        mat.rho_kg_m3 = rho
        v = assess(job, mat, cal)
        sc = schedule(job, mat, cal)
        rows.append(dict(rank=c.rank, mix=c.summary, P_design=round(c.p_feasible, 2), AD=round(c.ad_max, 2),
                         tau_s0_Pa=round(mat.tau_s0_Pa), tau_s0_band=tuple(round(x) for x in mat.tau_s0_band) if mat.tau_s0_band else None,
                         athix_Pa_s=round(v.athix_Pa_s, 3), verdict=v.label, governing=v.governing,
                         n_max=(None if math.isinf(v.n_max_plastic) else round(v.n_max_plastic)), n_target=v.n_target,
                         p_stable=v.p_stable_physics, p_collapse_emp=v.p_collapse_empirical,
                         t_c_min_s=(None if math.isinf(sc["t_c_min_s"]) else round(sc["t_c_min_s"])), t_c_max_s=round(sc["t_c_max_s"]),
                         t_c_recommended_s=(round(sc["t_c_recommended_s"]) if sc["t_c_recommended_s"] else None),
                         v_recommended_mm_s=(round(sc["speed"]["v_recommended_mm_s"], 1) if sc["speed"] and sc["speed"]["v_recommended_mm_s"] else None),
                         reasons=" | ".join(v.reasons), mix_json=c.mix))
    table = pd.DataFrame(rows)
    if len(table):
        order = {"printable": 0, "borderline": 1, "non_printable": 2}
        table = table.assign(_o=table.verdict.map(order)).sort_values(["_o", "p_stable", "n_max"], ascending=[True, False, False]).drop(columns="_o").reset_index(drop=True)
        table.insert(0, "buildability_rank", range(1, len(table) + 1))
    if out_dir is not None and len(table):
        table.drop(columns=["mix_json"]).to_csv(Path(out_dir) / "candidates_buildability.csv", index=False)
        paths["candidates_buildability"] = Path(out_dir) / "candidates_buildability.csv"
    return res, table, d, info, paths


# ---------------------------------------------------------------------------------------------------- analogue prints
def similar_prints(job: PrintJob, mat: FreshMaterial | None, cfg: PipelineConfig, k: int = 8, cal: dict | None = None) -> pd.DataFrame:
    """Published print runs closest to the job (nozzle, layer height, height, tau_s) with their outcome and label."""
    p = cfg.data_dir / "print_runs.parquet"
    if not p.exists():
        return pd.DataFrame()
    job, _ = job.resolve(cal if cal is not None else load_calibration(cfg))
    r = pd.read_parquet(p)
    r = r[r.outcome.isin(["printable", "collapsed", "extrusion_failure", "tearing"]) & r.layer_height_mm.notna()]
    cols, ref = [], []
    if job.nozzle_eq_mm:
        cols.append("noz_eq_mm"); ref.append(job.nozzle_eq_mm)
    cols.append("layer_height_mm"); ref.append(job.layer_height_mm)
    cols.append("H_mm"); ref.append(job.target_height_mm)
    if mat is not None:
        cols.append("static_yield_stress"); ref.append(mat.tau_s0_Pa)
    X = np.log10(r[cols].astype(float).clip(lower=1e-3))
    d = np.zeros(len(r))
    for c, v in zip(cols, ref):
        x = X[c].to_numpy()
        d += np.where(np.isnan(x), 1.0, (x - math.log10(max(v, 1e-3))) ** 2)
    r = r.assign(distance=np.sqrt(d)).sort_values("distance")
    r = r.drop_duplicates(["paper_uid", "mix_uid", "layer_height_mm", "H_mm"]).head(k)
    return r[["paper_uid", "mix_name_in_paper", "object", "noz_eq_mm", "layer_height_mm", "layer_cycle_time_s", "print_speed_mm_s",
              "n_layers_achieved", "H_mm", "stack_to_failure", "outcome", "failure_mode", "printability_label", "static_yield_stress",
              "structuration_rate_athix", "R", "distance"]].reset_index(drop=True)


# ---------------------------------------------------------------------------------------------------- report
def render_markdown(job: PrintJob, mat: FreshMaterial, v: Verdict, sc: dict, analogues: pd.DataFrame | None = None) -> str:
    j, _ = job.resolve()

    def f(x, d=0):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "—"
        if isinstance(x, float) and math.isinf(x):
            return "∞"
        return f"{x:.{d}f}"
    L = [f"# Buildability assessment — {j.name}", "",
         f"**Verdict: {v.label.upper()}** (governing: {v.governing})", ""] + [f"- {r}" for r in v.reasons] + ["",
         "## Job", "", "| item | value |", "|---|---|",
         f"| object | {j.object_type}, target height {j.target_height_mm:g} mm, wall {j.wall_filaments} filament(s) |",
         f"| nozzle | {f(j.nozzle_eq_mm, 1)} mm equivalent |",
         f"| layer | h {j.layer_height_mm:g} mm × w {f(j.layer_width_mm, 1)} mm → {v.n_target} layers |",
         f"| schedule | cycle time {v.layer_cycle_time_s:.0f} s (speed {f(j.print_speed_mm_s, 1)} mm/s, path {f(j.path_length_mm)} mm) → print {v.print_time_min:.0f} min |",
         f"| open time | {f(j.open_time_min)} min, start {j.start_time_after_mixing_min:g} min after mixing → {'ok' if v.open_time_ok else ('EXCEEDED' if v.open_time_ok is False else 'not checked')} |",
         "", "## Material", "", "| item | value |", "|---|---|",
         f"| τ_s(0) | {v.tau_s0_Pa:.0f} Pa" + (f" [{mat.tau_s0_band[0]:.0f}, {mat.tau_s0_band[1]:.0f}]" if mat.tau_s0_band else "") + f" ({mat.source}) |",
         f"| Athix | {v.athix_Pa_s:.3f} Pa/s" + (f" [{mat.athix_band[0]:.3f}, {mat.athix_band[1]:.3f}]" if mat.athix_band else "") + " |",
         f"| τ_s at end of print | {v.tau_s_end_Pa:.0f} Pa |", f"| fresh density | {mat.rho_kg_m3:g} kg/m³, E/τ_s {mat.E_over_tau:g} |",
         "", "## Stability", "", "| criterion | value |", "|---|---|",
         f"| plastic collapse n_max (sf 1 / sf {j.safety_factor:g}) | {f(v.n_max_plastic)} / {f(v.n_max_plastic_sf)} layers (target {v.n_target}) |",
         f"| buckling n_max (free wall) | {f(v.n_max_buckling) if v.n_max_buckling is not None else 'n/a (closed section or disabled)'} |",
         f"| H_max | {f(v.H_max_mm)} mm |",
         f"| static ratio R = ρgH/(√3 τ_s0) | {v.R_static:.2f} → empirical collapse probability {f(v.p_collapse_empirical * 100 if v.p_collapse_empirical is not None else None)} % (ECDF of 146 published stack-to-failure collapses, median R 1.39) |",
         f"| P(stands) over the material band | {f(v.p_stable_physics * 100 if v.p_stable_physics is not None else None)} % |",
         f"| required for this schedule | τ_s(0) ≥ {v.tau0_required_Pa:.0f} Pa at Athix {v.athix_Pa_s:.3f}, or Athix ≥ {v.athix_required_Pa_s:.3f} Pa/s at τ_s(0) {v.tau_s0_Pa:.0f} |",
         "", "## Schedule window", "", "| item | value |", "|---|---|",
         f"| layer cycle time | min {f(sc['t_c_min_s'])} s (sf {j.safety_factor:g}; {f(sc['t_c_min_no_sf_s'])} s without) · max {f(sc['t_c_max_s'])} s ({sc['t_c_max_basis']}) · current {sc['t_c_current_s']:.0f} s |",
         f"| recommended | {f(sc['t_c_recommended_s'])} s per layer → {f(sc['print_time_recommended_min'])} min total" + (" |" if sc["feasible"] else " — **no feasible window**: raise τ_s(0)/Athix, lower the layer height, or extend the open time |"),
         f"| critical cycle time (unlimited stacking) | {f(sc['critical_cycle_time_s'])} s |"]
    if sc.get("speed"):
        s = sc["speed"]
        if sc["feasible"]:
            L.append(f"| print speed for the path | {f(s['v_min_mm_s'], 1)} – {f(s['v_max_mm_s'], 1)} mm/s (recommended {f(s['v_recommended_mm_s'], 1)}; current {f(s['current_mm_s'], 1)}) |")
        else:
            L.append(f"| print speed for the path | none: stability needs ≤ {f(s['v_max_mm_s'], 1)} mm/s, the time bound needs ≥ {f(s['v_min_mm_s'], 1)} mm/s (current {f(s['current_mm_s'], 1)}) |")
    for e, w in v.extrudability.items():
        L.append(f"| {e} vs printable runs | {w['value']:.3g} — {w['status']} ({w['scope']}: p10 {w['p10']:.3g}, p50 {w['p50']:.3g}, p90 {w['p90']:.3g}) |")
    if v.defaults_used or v.warnings:
        L += ["", "## Assumptions", ""] + [f"- {x}" for x in v.defaults_used + v.warnings]
    if analogues is not None and len(analogues):
        L += ["", "## Closest published prints", "", "| DOI | mix | object | nozzle | h | layers / H | cycle | outcome | label | τ_s |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in analogues.itertuples():
            L.append(f"| {r.paper_uid} | {r.mix_name_in_paper} | {r.object} | {f(r.noz_eq_mm, 1)} | {f(r.layer_height_mm, 1)} | {f(r.n_layers_achieved)} / {f(r.H_mm)} | "
                     f"{f(r.layer_cycle_time_s)} | {r.outcome}{' (stack-to-failure)' if r.stack_to_failure else ''} | {r.printability_label} | {f(r.static_yield_stress)} |")
    L += ["", "Physics: Roussel (2018) plastic criterion with linear structuration, Suiker (2018) wall buckling; calibration and extrudability windows "
          "from the print01 label set (`configs/buildability_calibration.json`). Labels follow the authors' verdicts; τ_s protocols in the literature are mixed."]
    return "\n".join(L)


JOB_TEMPLATE = dict(name="wall_1m", object_type="wall", target_height_mm=1000, footprint_mm=1500, wall_filaments=2, nozzle_d_mm=25,
                    layer_height_mm=None, layer_width_mm=None, print_speed_mm_s=50, layer_cycle_time_s=None, dwell_s=0,
                    start_time_after_mixing_min=10, open_time_min=60, safety_factor=1.5, check_buckling=True,
                    notes="null fields are filled from the calibrated printable medians (layer h = 0.5 x nozzle, w = 1.2 x nozzle, speed 40 mm/s)")


def write_job_template(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(yaml.safe_dump(JOB_TEMPLATE, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p
