"""Design-problem specification (YAML/JSON) with validation against the model registry.

Example (YAML)::

    name: printable_mortar
    targets:
      - {quantity: compressive_strength, kind: ge, lo: 40, unit: MPa, conditions: {age_d: 28, comparability_group: comp_cube50}}
      - {quantity: static_yield_stress, kind: range, lo: 1.0, hi: 3.0, unit: kPa, conditions: {rest_time_s: 0}}
      - {quantity: flow_table_spread, kind: range, lo: 150, hi: 200, unit: mm}
    space:
      system_type: mortar
      is_3dcp: true
      w_b: [0.28, 0.45]
      s_b: [0.8, 1.8]
      binder:
        portland_cement: {lo: 0.5, hi: 1.0, required: true}
        silica_fume:     {lo: 0.0, hi: 0.15}
        limestone_powder: {lo: 0.0, hi: 0.3}
        fly_ash_class_F: {lo: 0.0, hi: 0.4}
      max_binder_components: 3
      admixtures:
        superplasticiser_pce: {lo: 0.2, hi: 1.5}      # % of powder (as dosed)
        vma_cellulose:        {lo: 0.0, hi: 0.3}
      fixed_conditions: {curing_temp_C: 20, curing_rh_pct: 95, curing_regime: moist}
    objectives:
      - {name: clinker_fraction, direction: min}
      - {name: co2, direction: min}
    risk: {p_min: 0.8, ad_max: 1.0, combine: product}
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .. import vocab as V
from ..schema import COMPARABILITY_GROUPS
from .units import to_canonical

KINDS = {"ge", "le", "range", "goal", "minimize", "maximize"}
OBJECTIVES = {"cost", "co2", "clinker_fraction", "co2_per_mpa", "cost_per_mpa"}


class SpecValidationError(ValueError):
    pass


# derived (curve) quantities computed from base models: quantity -> (base models, required condition)
DERIVED_TARGETS: dict[str, tuple[tuple[str, ...], str]] = {
    "shear_stress_at_rate": (("dynamic_yield_stress", "plastic_viscosity"), "shear_rate_1s"),          # Bingham flow curve point
    "static_yield_stress_at_rest": (("static_yield_stress", "structuration_rate_athix"), "rest_time_s"),  # structuration curve point
}


@dataclass
class TargetConditions:
    age_d: float | None = None
    comparability_group: str | None = None
    rest_time_s: float | None = None
    curing_temp_C: float | None = None
    curing_rh_pct: float | None = None
    shear_rate_1s: float | None = None        # for shear_stress_at_rate


@dataclass
class TargetSpec:
    quantity: str
    kind: str = "ge"
    lo: float | None = None
    hi: float | None = None
    goal: float | None = None
    unit: str | None = None
    weight: float = 1.0
    conditions: TargetConditions = field(default_factory=TargetConditions)
    p_min: float | None = None
    retrieval_only: bool = False

    def canonicalise(self) -> None:
        """Convert lo/hi/goal from `unit` to the canonical unit in place."""
        self.lo = to_canonical(self.quantity, self.lo, self.unit)
        self.hi = to_canonical(self.quantity, self.hi, self.unit)
        self.goal = to_canonical(self.quantity, self.goal, self.unit)
        self.unit = None

    @property
    def is_constraint(self) -> bool:
        return self.kind in {"ge", "le", "range"}

    @property
    def label(self) -> str:
        """Unique key for this target: quantity, plus the defining condition for curve-derived quantities
        (so the same quantity can appear several times at different shear rates / rest times)."""
        if self.quantity == "shear_stress_at_rate" and self.conditions.shear_rate_1s is not None:
            return f"{self.quantity}@{self.conditions.shear_rate_1s:g}/s"
        if self.quantity == "static_yield_stress_at_rest" and self.conditions.rest_time_s is not None:
            return f"{self.quantity}@{self.conditions.rest_time_s:g}s"
        return self.quantity


@dataclass
class GroupBounds:
    lo: float = 0.0
    hi: float = 1.0
    required: bool = False
    log: bool = False


@dataclass
class VariableSpace:
    system_type: str = "mortar"
    is_3dcp: bool | None = None
    w_b: tuple[float, float] = (0.25, 0.6)
    s_b: tuple[float, float] | None = None
    binder: dict[str, GroupBounds] = field(default_factory=dict)
    max_binder_components: int = 4
    min_present_frac: float = 0.02
    admixtures: dict[str, GroupBounds] = field(default_factory=dict)   # % of powder
    fibres: dict[str, GroupBounds] = field(default_factory=dict)       # vol % of mix
    fixed_conditions: dict = field(default_factory=dict)


@dataclass
class ObjectiveSpec:
    name: str
    direction: str = "min"
    weight: float = 1.0
    table: str | None = None


@dataclass
class Risk:
    quantile: float = 0.10
    p_min: float = 0.80
    ad_max: float = 1.0
    combine: str = "product"


@dataclass
class Budget:
    n_samples: int = 32768
    n_refine: int = 10
    refine_generations: int = 30
    time_limit_s: float = 120.0


@dataclass
class Output:
    top_n: int = 10
    n_literature: int = 20
    plots: bool = True


@dataclass
class DesignSpec:
    name: str
    targets: list[TargetSpec]
    space: VariableSpace
    objectives: list[ObjectiveSpec] = field(default_factory=list)
    risk: Risk = field(default_factory=Risk)
    budget: Budget = field(default_factory=Budget)
    optimizer: str = "twostage"
    output: Output = field(default_factory=Output)
    seed: int = 0

    # ------------------------------------------------------------- loading
    @classmethod
    def from_dict(cls, d: dict) -> "DesignSpec":
        def gb(x):
            if isinstance(x, GroupBounds):
                return x
            if isinstance(x, (list, tuple)):
                return GroupBounds(lo=float(x[0]), hi=float(x[1]))
            return GroupBounds(**x)
        sp = d.get("space", {})
        space = VariableSpace(
            system_type=sp.get("system_type", "mortar"), is_3dcp=sp.get("is_3dcp"),
            w_b=tuple(sp.get("w_b", (0.25, 0.6))), s_b=tuple(sp["s_b"]) if sp.get("s_b") else None,
            binder={k: gb(v) for k, v in (sp.get("binder") or {}).items()},
            max_binder_components=int(sp.get("max_binder_components", 4)),
            min_present_frac=float(sp.get("min_present_frac", 0.02)),
            admixtures={k: gb(v) for k, v in (sp.get("admixtures") or {}).items()},
            fibres={k: gb(v) for k, v in (sp.get("fibres") or {}).items()},
            fixed_conditions=dict(sp.get("fixed_conditions") or {}),
        )
        targets = []
        for t in d.get("targets", []):
            cond = t.get("conditions") or {}
            targets.append(TargetSpec(quantity=t["quantity"], kind=t.get("kind", "ge"), lo=t.get("lo"), hi=t.get("hi"),
                                      goal=t.get("goal"), unit=t.get("unit"), weight=float(t.get("weight", 1.0)),
                                      conditions=TargetConditions(**cond), p_min=t.get("p_min"),
                                      retrieval_only=bool(t.get("retrieval_only", False))))
        objs = [ObjectiveSpec(**o) if not isinstance(o, ObjectiveSpec) else o for o in d.get("objectives", [])]
        return cls(name=d.get("name", "design"), targets=targets, space=space, objectives=objs,
                   risk=Risk(**(d.get("risk") or {})), budget=Budget(**(d.get("budget") or {})),
                   optimizer=d.get("optimizer", "twostage"), output=Output(**(d.get("output") or {})),
                   seed=int(d.get("seed", 0)))

    @classmethod
    def load(cls, path: str | Path) -> "DesignSpec":
        p = Path(path)
        txt = p.read_text(encoding="utf-8")
        d = json.loads(txt) if p.suffix.lower() == ".json" else yaml.safe_load(txt)
        return cls.from_dict(d)

    def to_dict(self) -> dict:
        return asdict(self)

    # ---------------------------------------------------------- validation
    def validate(self, available_targets: set[str] | None = None, age_support: dict[str, dict] | None = None,
                 cost_table: dict | None = None) -> list[str]:
        """Canonicalise units, check feasibility of the search space; raise on hard errors, return warnings."""
        warns: list[str] = []
        if not self.targets:
            raise SpecValidationError("no targets given")
        for t in self.targets:
            if t.kind not in KINDS:
                raise SpecValidationError(f"target {t.quantity}: kind must be one of {sorted(KINDS)}")
            t.canonicalise()
            if t.kind == "ge" and t.lo is None:
                raise SpecValidationError(f"target {t.quantity}: kind 'ge' needs lo")
            if t.kind == "le" and t.hi is None:
                raise SpecValidationError(f"target {t.quantity}: kind 'le' needs hi")
            if t.kind == "range" and (t.lo is None or t.hi is None or t.lo >= t.hi):
                raise SpecValidationError(f"target {t.quantity}: kind 'range' needs lo < hi")
            if t.kind == "goal" and t.goal is None:
                raise SpecValidationError(f"target {t.quantity}: kind 'goal' needs goal")
            if t.quantity in DERIVED_TARGETS:
                bases, cond_key = DERIVED_TARGETS[t.quantity]
                if getattr(t.conditions, cond_key) is None:
                    raise SpecValidationError(f"target {t.quantity}: conditions.{cond_key} is required")
                if available_targets is not None and not t.retrieval_only:
                    missing = [b for b in bases if b not in available_targets]
                    if missing:
                        raise SpecValidationError(f"{t.quantity} needs models {bases}; missing {missing}")
            elif available_targets is not None and t.quantity not in available_targets and not t.retrieval_only:
                raise SpecValidationError(f"no trained model for {t.quantity}; mark retrieval_only: true or train it")
            cg = t.conditions.comparability_group
            if cg is not None and cg not in COMPARABILITY_GROUPS:
                warns.append(f"{t.quantity}: comparability_group {cg!r} unknown -> treated as 'unknown'")
            if age_support and t.quantity in age_support and t.conditions.age_d is not None:
                s = age_support[t.quantity]
                if s and (t.conditions.age_d < s.get("min", 0) or t.conditions.age_d > s.get("max", 1e9)):
                    warns.append(f"{t.quantity}: age {t.conditions.age_d} d outside training support "
                                 f"[{s.get('min')}, {s.get('max')}] -> extrapolating")
        sp = self.space
        if sp.system_type not in {"paste", "mortar"}:
            raise SpecValidationError("space.system_type must be paste or mortar")
        if sp.system_type == "mortar" and sp.s_b is None:
            raise SpecValidationError("mortar design needs space.s_b bounds")
        if sp.system_type == "paste":
            sp.s_b = None
        known = set(V.class_to_group())
        for grp_name, table in (("binder", sp.binder), ("admixtures", sp.admixtures), ("fibres", sp.fibres)):
            for cls, b in table.items():
                if cls not in known:
                    raise SpecValidationError(f"space.{grp_name}: unknown material_class {cls!r}")
                if not (0 <= b.lo <= b.hi):
                    raise SpecValidationError(f"space.{grp_name}.{cls}: need 0 <= lo <= hi")
        if not sp.binder:
            raise SpecValidationError("space.binder is empty")
        for cls in sp.binder:
            if V.resolve_group(cls, "binder").family != "powder":
                raise SpecValidationError(f"space.binder.{cls} is not a powder class")
        req = [b for b in sp.binder.values() if b.required]
        lo_req = sum(b.lo for b in req)
        hi_all = sum(b.hi for b in sp.binder.values())
        if lo_req > 1.0 + 1e-9:
            raise SpecValidationError(f"required binder lower bounds sum to {lo_req:.2f} > 1")
        if hi_all < 1.0 - 1e-9:
            raise SpecValidationError(f"binder upper bounds sum to {hi_all:.2f} < 1")
        if len(req) > sp.max_binder_components:
            raise SpecValidationError("more required binder components than max_binder_components")
        for o in self.objectives:
            if o.name not in OBJECTIVES and not o.name.startswith("quantity:"):
                raise SpecValidationError(f"unknown objective {o.name!r}; use {sorted(OBJECTIVES)} or quantity:<name>")
            if o.direction not in {"min", "max"}:
                raise SpecValidationError(f"objective {o.name}: direction must be min or max")
            if o.name.startswith("quantity:") and o.name.split(":", 1)[1] not in {t.quantity for t in self.targets}:
                raise SpecValidationError(f"objective {o.name}: quantity must also appear in targets")
            if o.name in {"co2_per_mpa", "cost_per_mpa"} and "compressive_strength" not in {t.quantity for t in self.targets}:
                raise SpecValidationError(f"objective {o.name} needs a compressive_strength target")
        if cost_table is not None:
            missing = [c for c in list(sp.binder) + list(sp.admixtures) + list(sp.fibres)
                       if V.resolve_group(c, None).group not in cost_table]
            if missing:
                warns.append(f"cost/CO2 table has no entry for groups of {missing}; those candidates get null cost")
        if not (0 < self.risk.p_min <= 1):
            raise SpecValidationError("risk.p_min must be in (0, 1]")
        return warns


# ------------------------------------------------------------------ templates
TEMPLATES: dict[str, dict] = {
    "3dcp_printable_mortar": dict(
        name="3dcp_printable_mortar",
        targets=[
            dict(quantity="compressive_strength", kind="ge", lo=40, unit="MPa",
                 conditions=dict(age_d=28, comparability_group="comp_cube50"), p_min=0.7),
            # rheology / flow models are weak (wide intervals): require only a modest probability and
            # lean on the retrieved published printable mixes as primary evidence for these targets
            dict(quantity="static_yield_stress", kind="range", lo=1.0, hi=4.0, unit="kPa", conditions=dict(rest_time_s=0), p_min=0.3),
            dict(quantity="flow_table_spread", kind="range", lo=140, hi=200, unit="mm", p_min=0.35),
        ],
        space=dict(system_type="mortar", is_3dcp=True, w_b=[0.28, 0.45], s_b=[0.8, 1.8],
                   binder={"portland_cement": dict(lo=0.5, hi=1.0, required=True), "silica_fume": dict(lo=0.0, hi=0.15),
                           "limestone_powder": dict(lo=0.0, hi=0.3), "fly_ash_class_F": dict(lo=0.0, hi=0.4)},
                   max_binder_components=3,
                   admixtures={"superplasticiser_pce": dict(lo=0.2, hi=1.5), "vma_cellulose": dict(lo=0.0, hi=0.3)},
                   fixed_conditions=dict(curing_temp_C=20, curing_rh_pct=95, curing_regime="moist curing")),
        objectives=[dict(name="clinker_fraction", direction="min"), dict(name="co2", direction="min")],
        risk=dict(p_min=0.7, ad_max=1.0, combine="product"),
    ),
    "hpc_paste": dict(
        name="hpc_paste",
        targets=[
            dict(quantity="compressive_strength", kind="ge", lo=80, unit="MPa",
                 conditions=dict(age_d=28, comparability_group="comp_cube50")),
            dict(quantity="mini_slump_flow_diameter", kind="ge", lo=180, unit="mm"),
        ],
        space=dict(system_type="paste", w_b=[0.18, 0.35],
                   binder={"portland_cement": dict(lo=0.6, hi=1.0, required=True), "silica_fume": dict(lo=0.0, hi=0.25),
                           "ggbfs": dict(lo=0.0, hi=0.4)},
                   admixtures={"superplasticiser_pce": dict(lo=0.3, hi=2.5)},
                   fixed_conditions=dict(curing_temp_C=20, curing_rh_pct=100, curing_regime="water curing")),
        objectives=[dict(name="cost", direction="min")],
    ),
    "low_carbon_mortar": dict(
        name="low_carbon_mortar",
        targets=[
            dict(quantity="compressive_strength", kind="ge", lo=30, unit="MPa",
                 conditions=dict(age_d=28, comparability_group="comp_prism40")),
            dict(quantity="flow_table_spread", kind="ge", lo=160, unit="mm"),
        ],
        space=dict(system_type="mortar", w_b=[0.35, 0.6], s_b=[2.0, 3.5],
                   binder={"portland_cement": dict(lo=0.3, hi=1.0, required=True), "ggbfs": dict(lo=0.0, hi=0.6),
                           "fly_ash_class_F": dict(lo=0.0, hi=0.5), "limestone_powder": dict(lo=0.0, hi=0.35),
                           "calcined_clay": dict(lo=0.0, hi=0.35)},
                   max_binder_components=3,
                   admixtures={"superplasticiser_pce": dict(lo=0.0, hi=1.0)},
                   fixed_conditions=dict(curing_temp_C=20, curing_rh_pct=95, curing_regime="moist curing")),
        objectives=[dict(name="co2_per_mpa", direction="min"), dict(name="clinker_fraction", direction="min")],
    ),
}


def write_template(name: str, path: str | Path) -> Path:
    if name not in TEMPLATES:
        raise KeyError(f"unknown template {name!r}; available: {sorted(TEMPLATES)}")
    p = Path(path)
    p.write_text(yaml.safe_dump(TEMPLATES[name], sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p
