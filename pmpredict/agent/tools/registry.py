"""Tool registry: the single definition of every agent tool, projected to Anthropic / OpenAI / MCP schemas."""
from __future__ import annotations

import json
import math
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from .runtime import Runtime, get_runtime

ArtifactKind = Literal["table", "image", "markdown", "json", "file"]


@dataclass(frozen=True)
class Artifact:
    path: str
    kind: ArtifactKind
    title: str

    def to_dict(self) -> dict:
        return dict(path=self.path, kind=self.kind, title=self.title)


@dataclass
class ToolResult:
    data: dict
    artifacts: list[Artifact] = field(default_factory=list)
    summary: str = ""
    is_error: bool = False

    def to_dict(self) -> dict:
        return dict(data=_jsonable(self.data), artifacts=[a.to_dict() for a in self.artifacts], summary=self.summary, is_error=self.is_error)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolResult":
        return cls(data=d.get("data", {}), artifacts=[Artifact(**a) for a in d.get("artifacts", [])], summary=d.get("summary", ""),
                   is_error=bool(d.get("is_error", False)))


@dataclass
class ToolContext:
    runtime: Runtime
    session_id: str
    artifact_dir: Path
    progress: Callable[[float, str], None] = lambda pct, msg: None

    def path(self, name: str) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        return self.artifact_dir / name


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[dict, ToolContext], ToolResult]
    read_only: bool = True
    slow: bool = False
    timeout_s: float = 60.0


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, schema: dict, *, read_only: bool = True, slow: bool = False, timeout_s: float = 60.0):
    schema = dict(schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema.setdefault("additionalProperties", False)

    def deco(fn):
        REGISTRY[name] = ToolSpec(name=name, description=description.strip(), input_schema=schema, fn=fn,
                                  read_only=read_only, slow=slow, timeout_s=timeout_s)
        return fn
    return deco


# ------------------------------------------------------------------------------------------- projections
def to_anthropic_tools(names: list[str] | None = None) -> list[dict]:
    return [dict(name=t.name, description=t.description, input_schema=t.input_schema)
            for t in REGISTRY.values() if names is None or t.name in names]


def to_openai_tools(names: list[str] | None = None) -> list[dict]:
    return [dict(type="function", function=dict(name=t.name, description=t.description, parameters=t.input_schema))
            for t in REGISTRY.values() if names is None or t.name in names]


def to_mcp_tools(names: list[str] | None = None):
    from mcp import types
    return [types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema)
            for t in REGISTRY.values() if names is None or t.name in names]


# ------------------------------------------------------------------------------------------- execution
def _validate_args(spec: ToolSpec, args: dict) -> list[str]:
    errs = []
    props = spec.input_schema.get("properties", {})
    for k in spec.input_schema.get("required", []):
        if k not in args:
            errs.append(f"missing required argument '{k}'")
    for k in args:
        if k not in props and not spec.input_schema.get("additionalProperties", False):
            errs.append(f"unknown argument '{k}' (allowed: {', '.join(props)})")
    return errs


def call_tool(name: str, args: dict | None, ctx: ToolContext | None = None) -> ToolResult:
    args = dict(args or {})
    spec = REGISTRY.get(name)
    if spec is None:
        return ToolResult(data={"error": f"unknown tool '{name}'", "available": sorted(REGISTRY)}, is_error=True, summary="unknown tool")
    errs = _validate_args(spec, args)
    if errs:
        return ToolResult(data={"error": "; ".join(errs), "schema": spec.input_schema}, is_error=True, summary="invalid arguments")
    ctx = ctx or ToolContext(runtime=get_runtime(), session_id="adhoc", artifact_dir=get_runtime().session_artifact_dir("adhoc"))
    t0 = time.time()
    try:
        res = spec.fn(args, ctx)
    except Exception as e:  # noqa: BLE001 - every tool failure is returned to the model as data
        from ..secrets import redact
        tb = traceback.format_exc(limit=4)
        return ToolResult(data={"error": redact(f"{type(e).__name__}: {e}"), "traceback_tail": redact(tb[-1200:])}, is_error=True,
                          summary=f"{name} 실패: {type(e).__name__}")
    res.data = _jsonable(res.data)
    res.data.setdefault("_elapsed_s", round(time.time() - t0, 2))
    return res


def result_for_llm(res: ToolResult, max_chars: int = 6000) -> str:
    """Text handed to the model: JSON data + artifact list, capped."""
    payload = dict(res.data)
    if res.artifacts:
        payload["artifacts"] = [a.to_dict() for a in res.artifacts]
    if res.is_error:
        payload["is_error"] = True
    s = json.dumps(payload, ensure_ascii=False, default=str)
    if len(s) > max_chars:
        paths = ", ".join(a.path for a in res.artifacts) or "none"
        s = s[:max_chars] + f'... [truncated at {max_chars} chars; full data in files: {paths}]'
    return s


# ------------------------------------------------------------------------------------------- helpers for tools
def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, pd.DataFrame):
        return _jsonable(o.to_dict("records"))
    if isinstance(o, pd.Series):
        return _jsonable(o.to_dict())
    if isinstance(o, Path):
        return str(o)
    if o is None or isinstance(o, (str, int, bool)):
        return o
    if pd.isna(o) if not isinstance(o, (list, dict)) else False:
        return None
    return str(o)


def frame_to_result(df: pd.DataFrame, ctx: ToolContext, name: str, title: str, max_rows: int = 20,
                    columns: list[str] | None = None) -> tuple[dict, Artifact]:
    """Full table to CSV artifact; first `max_rows` rows inline."""
    p = ctx.path(f"{name}.csv")
    df.to_csv(p, index=False, encoding="utf-8-sig")
    show = df[columns] if columns else df
    data = dict(n_rows=int(len(df)), columns=list(show.columns), rows=_jsonable(show.head(max_rows)),
                truncated=bool(len(df) > max_rows), csv=str(p))
    return data, Artifact(path=str(p), kind="table", title=title)


def save_fig(fig, ctx: ToolContext, name: str, title: str) -> Artifact:
    import matplotlib
    matplotlib.use("Agg", force=False)
    p = ctx.path(f"{name}.png")
    fig.savefig(p, dpi=130, bbox_inches="tight")
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:  # noqa: BLE001
        pass
    return Artifact(path=str(p), kind="image", title=title)


def save_text(text: str, ctx: ToolContext, name: str, title: str, kind: ArtifactKind = "markdown") -> Artifact:
    p = ctx.path(name)
    p.write_text(text, encoding="utf-8")
    return Artifact(path=str(p), kind=kind, title=title)


def subsample(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    if len(df) <= n:
        return df
    idx = np.unique(np.linspace(0, len(df) - 1, n).round().astype(int))
    return df.iloc[idx]
