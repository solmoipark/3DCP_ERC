"""dict -> MixSpec / DesignSpec / PrintJob: the conversions that used to live only in the Streamlit forms."""
from __future__ import annotations

import difflib

from ... import vocab as V
from ...buildability import PrintJob
from ...design.spec import DesignSpec
from ...schema import COMPARABILITY_GROUPS, Component, Conditions, MixSpec

KOR_TARGET = {
    "compressive_strength": "압축강도", "flexural_strength": "휨강도", "direct_tensile_strength": "직접인장강도",
    "splitting_tensile_strength": "쪼갬인장강도", "elastic_modulus": "탄성계수", "flow_table_spread": "플로우(테이블)",
    "mini_slump_flow_diameter": "미니슬럼프 플로우", "initial_setting_time": "초결시간", "final_setting_time": "종결시간",
    "porosity_total": "총공극률", "water_absorption": "흡수율", "hardened_density": "경화 밀도",
    "dynamic_yield_stress": "동적항복응력", "static_yield_stress": "정적항복응력", "plastic_viscosity": "소성점도",
    "structuration_rate_athix": "구조화속도 Athix", "drying_shrinkage": "건조수축", "autogenous_shrinkage": "자기수축",
    "cumulative_heat": "누적수화열",
    "shear_stress_at_rate": "전단응력(유동곡선 점)", "static_yield_stress_at_rest": "정적항복응력(휴지시간 지정)",
}
CURING_PRESETS = {"수중 양생 (20 °C)": ("water curing at 20 C", 20.0, 100.0), "습윤 양생 (20 °C, RH 95 %)": ("moist curing", 20.0, 95.0),
                  "밀봉 양생 (20 °C)": ("sealed curing", 20.0, None), "상온 공기 중": ("ambient air curing", 20.0, 60.0),
                  "증기/고온 양생 (60 °C)": ("steam curing at 60 C", 60.0, 100.0)}
CURING_ALIASES = {"water": "수중 양생 (20 °C)", "moist": "습윤 양생 (20 °C, RH 95 %)", "sealed": "밀봉 양생 (20 °C)",
                  "ambient": "상온 공기 중", "air": "상온 공기 중", "steam": "증기/고온 양생 (60 °C)", "heat": "증기/고온 양생 (60 °C)",
                  "수중": "수중 양생 (20 °C)", "습윤": "습윤 양생 (20 °C, RH 95 %)", "밀봉": "밀봉 양생 (20 °C)", "상온": "상온 공기 중",
                  "증기": "증기/고온 양생 (60 °C)", "고온": "증기/고온 양생 (60 °C)"}
DEFAULT_TARGETS = ["compressive_strength", "flexural_strength", "flow_table_spread", "static_yield_stress", "dynamic_yield_stress",
                   "plastic_viscosity"]


class NormaliseError(ValueError):
    pass


def label(q: str) -> str:
    return f"{KOR_TARGET.get(q, q)} ({q})"


def classes_of(family: str) -> list[str]:
    return sorted(c for c, g in V.class_to_group().items() if g and V.group_defaults()[g].family == family)


def _check_class(name: str, family: str | None = None) -> str:
    c2g = V.class_to_group()
    if name in c2g and c2g[name]:
        if family and V.group_defaults()[c2g[name]].family != family:
            raise NormaliseError(f"'{name}' is a {V.group_defaults()[c2g[name]].family} class, not {family}")
        return name
    pool = classes_of(family) if family else sorted(k for k, g in c2g.items() if g)
    near = difflib.get_close_matches(name, pool, n=5, cutoff=0.4)
    raise NormaliseError(f"unknown material class '{name}'" + (f"; closest: {', '.join(near)}" if near else "") +
                         f". Use describe_vocabulary(family='{family or 'powder'}') to list valid names.")


def curing_from(v) -> tuple[str | None, float | None, float | None]:
    if v is None:
        return ("moist curing", 20.0, 95.0)
    if isinstance(v, dict):
        return (v.get("regime") or "curing", v.get("temp_C", 20.0), v.get("rh_pct"))
    s = str(v).strip()
    if s in CURING_PRESETS:
        return CURING_PRESETS[s]
    for k, name in CURING_ALIASES.items():
        if k in s.lower():
            return CURING_PRESETS[name]
    raise NormaliseError(f"unknown curing '{s}'; use one of {list(CURING_PRESETS)} or {{regime, temp_C, rh_pct}}")


def mix_from_dict(d: dict) -> tuple[MixSpec, list[str]]:
    """Same rules as the old Streamlit mix form (app/streamlit_app.py::mix_form)."""
    warns: list[str] = []
    system = str(d.get("system_type", "mortar"))
    if system not in ("mortar", "paste"):
        raise NormaliseError("system_type must be 'mortar' or 'paste'")
    if "w_b" not in d:
        raise NormaliseError("w_b (water/binder mass ratio) is required")
    wb = float(d["w_b"])
    sb = float(d.get("s_b") or 0.0)
    binder = d.get("binder") or {}
    if not binder:
        raise NormaliseError("binder must map at least one powder class to a mass fraction, e.g. {'portland_cement': 1.0}")
    binder = {_check_class(c, "powder"): float(f) for c, f in binder.items()}
    tot = sum(binder.values())
    if tot <= 0:
        raise NormaliseError("binder fractions must be positive")
    if abs(tot - 1) > 1e-6:
        warns.append(f"binder fractions sum to {tot:.3f}; normalised to 1")
    props = d.get("material_props") or {}
    comps = [Component(material_class=c, amount=f / tot, props=dict(props.get(c, {}))) for c, f in binder.items()]
    if system == "mortar" and sb > 0:
        comps.append(Component(material_class=str(d.get("sand_class") or "natural_sand"), amount=sb))
    elif system == "paste" and sb > 0:
        warns.append("s_b ignored for a paste")
    for c, pct in (d.get("admixtures_pct") or {}).items():
        if float(pct) > 0:
            comps.append(Component(material_class=_check_class(c, "admixture"), amount=float(pct) / 100.0))
    for c, vp in (d.get("fibres_vol_pct") or {}).items():
        if float(vp) > 0:
            comps.append(Component(material_class=_check_class(c, "fibre"), vol_pct=float(vp)))
    for c, spec in (d.get("activators") or {}).items():
        spec = spec if isinstance(spec, dict) else {"amount": spec}
        if float(spec.get("amount", 0)) > 0:
            comps.append(Component(material_class=_check_class(c, "activator"), amount=float(spec["amount"]),
                                   molarity=(float(spec["molarity"]) if spec.get("molarity") is not None else None)))
    for c, pct in (d.get("nano_pct") or {}).items():
        if float(pct) > 0:
            comps.append(Component(material_class=_check_class(c, "nano"), amount=float(pct) / 100.0))
    cond = dict(d.get("conditions") or {})
    regime, temp, rh = curing_from(cond.get("curing"))
    cg = cond.get("comparability_group", "comp_cube50")
    if cg is not None and cg not in COMPARABILITY_GROUPS:
        raise NormaliseError(f"comparability_group must be one of {COMPARABILITY_GROUPS}")
    spec = MixSpec(system_type=system, components=comps, water_binder=wb,
                   conditions=Conditions(age_d=float(cond.get("age_d", 28.0)), comparability_group=cg,
                                         rest_time_s=float(cond.get("rest_time_s", 0.0)), curing_temp_C=temp, curing_rh_pct=rh,
                                         curing_regime=regime, is_3dcp=int(bool(cond.get("is_3dcp", False)))),
                   name=str(d.get("name") or "agent_mix"))
    warns += spec.validate() or []
    return spec, warns


def target_rows_to_specs(rows: list[dict]) -> list[dict]:
    """Flat target rows (as the old data editor produced) -> DesignSpec target dicts."""
    out = []
    for r in rows:
        if not r.get("quantity"):
            raise NormaliseError("each target needs a quantity")
        cond = dict(r.get("conditions") or {})
        for k in ("age_d", "comparability_group", "shear_rate_1s", "rest_time_s"):
            if r.get(k) is not None:
                cond[k] = r[k]
        kind = r.get("kind", "ge")
        t = dict(quantity=r["quantity"], kind=kind, unit=r.get("unit"), conditions=cond, p_min=r.get("p_min"))
        lo, hi, goal = r.get("lo"), r.get("hi"), r.get("goal")
        if kind == "goal":
            t["goal"] = goal if goal is not None else lo
            if t["goal"] is None:
                raise NormaliseError(f"{r['quantity']}: kind=goal needs 'goal'")
        else:
            # be forgiving: a lone 'goal' with ge/le is read as the bound it obviously means
            if kind == "ge" and lo is None and goal is not None:
                lo = goal
            if kind == "le" and hi is None and goal is not None:
                hi = goal
            if kind == "ge" and lo is None:
                raise NormaliseError(f"{r['quantity']}: kind=ge needs 'lo' (the lower bound), e.g. '≥ 40 MPa' -> lo=40")
            if kind == "le" and hi is None:
                raise NormaliseError(f"{r['quantity']}: kind=le needs 'hi' (the upper bound)")
            if kind == "range" and (lo is None or hi is None):
                raise NormaliseError(f"{r['quantity']}: kind=range needs both 'lo' and 'hi'")
            t["lo"], t["hi"] = lo, hi
        out.append(t)
    return out


def space_from_dict(s: dict) -> dict:
    s = dict(s or {})
    system = s.get("system_type", "mortar")
    binder = {}
    for c, b in (s.get("binder") or {"portland_cement": {"lo": 0.5, "hi": 1.0, "required": True}}).items():
        b = b if isinstance(b, dict) else {"lo": b[0], "hi": b[1]}
        binder[_check_class(c, "powder")] = dict(lo=float(b.get("lo", 0.0)), hi=float(b.get("hi", 1.0)), required=bool(b.get("required", False)))
    adm = {}
    for c, b in (s.get("admixtures") or {}).items():
        b = b if isinstance(b, dict) else {"lo": b[0], "hi": b[1]}
        adm[_check_class(c, "admixture")] = dict(lo=float(b.get("lo", 0.0)), hi=float(b.get("hi", 1.5)))
    fixed = dict(s.get("fixed_conditions") or {})
    if "curing" in s or not fixed:
        regime, temp, rh = curing_from(s.get("curing"))
        fixed = dict(curing_temp_C=temp, curing_rh_pct=rh, curing_regime=regime) | fixed
    return dict(system_type=system, is_3dcp=bool(s.get("is_3dcp", False)), w_b=list(s.get("w_b", [0.3, 0.5])),
                s_b=(list(s["s_b"]) if system == "mortar" and s.get("s_b") else ([1.0, 3.0] if system == "mortar" else None)),
                binder=binder, max_binder_components=int(s.get("max_binder_components", 3)), admixtures=adm, fixed_conditions=fixed)


def design_from_dict(d: dict, rt, retrieval_only: bool = False) -> tuple[DesignSpec, list[str]]:
    targets = target_rows_to_specs(d.get("targets") or [])
    if not targets:
        raise NormaliseError("at least one target is required")
    objs = d.get("objectives") or ["clinker_fraction", "co2"]
    objs = [o if isinstance(o, dict) else dict(name=o, direction="min") for o in objs]
    budget = dict(n_samples=8192, n_refine=6, refine_generations=15, time_limit_s=150) | dict(d.get("budget") or {})
    spec = DesignSpec.from_dict(dict(name=d.get("name", "agent_design"), targets=targets, space=space_from_dict(d.get("space") or {}),
                                     objectives=objs, risk=dict(p_min=0.7, ad_max=1.0) | dict(d.get("risk") or {}), budget=budget,
                                     output=dict(top_n=int(d.get("top_n", 8)), n_literature=int(d.get("n_literature", 15)), plots=True),
                                     seed=int(d.get("seed", 0))))
    avail = None if retrieval_only else set(rt.assets.available_targets())
    warns = spec.validate(available_targets=avail, age_support=rt.age_support)
    return spec, warns


def job_from_dict(d: dict) -> PrintJob:
    d = dict(d or {})
    noz = d.pop("nozzle", None)
    if isinstance(noz, dict):
        if noz.get("d_mm"):
            d["nozzle_d_mm"] = float(noz["d_mm"])
        if noz.get("w_mm") and noz.get("h_mm"):
            d["nozzle_w_mm"], d["nozzle_h_mm"] = float(noz["w_mm"]), float(noz["h_mm"])
    elif isinstance(noz, (int, float)):
        d["nozzle_d_mm"] = float(noz)
    if d.get("open_time_min") in (0, 0.0):
        d["open_time_min"] = None
    return PrintJob.from_dict(d)
