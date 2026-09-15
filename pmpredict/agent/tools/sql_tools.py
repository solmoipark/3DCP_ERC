"""Read-only SQL over master.db and print_process.db."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import pandas as pd

from .registry import ToolContext, ToolResult, frame_to_result, tool

FORBIDDEN = re.compile(r"\b(ATTACH|DETACH|PRAGMA|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|VACUUM|REINDEX|TRUNCATE|GRANT)\b|load_extension", re.I)
MASTER_HINTS = {
    "papers": "paper_uid(=DOI), title, year, journal, is_3dcp_study('1'/'0'), n_mixes …",
    "mixes": "mix_uid, paper_uid, mix_name, system_type(paste/mortar), w_b_reported, sand_binder_ratio, binder_total_kg_m3 …",
    "mix_components": "mix_uid, material_uid, material_class, role, dosage_reported, basis_reported, unit_reported …",
    "materials": "material_uid, paper_uid, material_class, name_in_paper",
    "measurements": "mix_uid, test_uid, quantity, value_canonical, unit_canonical, age_norm_d, condition_note, fig_only …",
    "tests": "test_uid, paper_uid, quantity, method_name, rest_time_s, comparability_group …",
    "curves": "curve_uid, mix_uid, x_quantity, y_quantity, x_unit, y_unit; curve_points: curve_uid, x_canonical, y_canonical",
}
PRINT_HINTS = {
    "printers": "paper_uid, system, pump, nozzle_shape, nozzle_d_mm, nozzle_w_mm, nozzle_h_mm",
    "print_runs": "paper_uid, run_id, mix_uid, object, layer_height_mm, print_speed_mm_s, layer_cycle_time_s, n_layers_achieved, height_achieved_mm, "
                  "stack_to_failure, outcome, failure_mode, printability_label, label_basis, confidence, open_time_min",
    "rheology_protocols": "paper_uid, test_uid, quantity, protocol_class, rest_time_s, preshear, shear_rate_s1, device",
}


class SQLGuardError(ValueError):
    pass


def guard_sql(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s).strip().rstrip(";").strip()
    if not s:
        raise SQLGuardError("empty statement")
    if ";" in s:
        raise SQLGuardError("only one statement is allowed")
    first = re.match(r"\s*(\w+)", s)
    if not first or first.group(1).upper() not in ("SELECT", "WITH"):
        raise SQLGuardError("only SELECT / WITH queries are allowed")
    if FORBIDDEN.search(s):
        raise SQLGuardError("statement contains a forbidden keyword (read-only access)")
    return s


def _authorizer(action, arg1, arg2, dbname, source):
    return sqlite3.SQLITE_OK if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION) else sqlite3.SQLITE_DENY


def run_query(db_path: Path, sql: str, max_rows: int = 200, timeout_s: float = 20.0) -> tuple[pd.DataFrame, bool, float]:
    s = guard_sql(sql)
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        con.set_authorizer(_authorizer)
        deadline = time.time() + timeout_s

        def _tick():
            return 1 if time.time() > deadline else 0
        con.set_progress_handler(_tick, 10_000)
        t0 = time.time()
        df = pd.read_sql_query(f"SELECT * FROM ({s}) AS q LIMIT {int(max_rows) + 1}", con)
        el = time.time() - t0
    finally:
        con.close()
    truncated = len(df) > max_rows
    return df.head(max_rows), truncated, el


def _db_path(ctx: ToolContext, db: str) -> Path:
    p = ctx.runtime.print_db_path if db == "print_process" else ctx.runtime.master_db_path
    if not p.exists():
        raise FileNotFoundError(f"{db} database not found at {p}")
    return p


@tool("describe_schema",
      "문헌 DB(master: 논문·믹스·재료·측정·시험·곡선)와 프린트 라벨 DB(print_process: printers·print_runs·rheology_protocols)의 테이블·컬럼·샘플 행. "
      "sql_query 전에 먼저 호출. master.db는 전 컬럼이 TEXT이므로 수치 비교는 CAST(col AS REAL), 빈 문자열은 NULL로 취급.",
      {"properties": {"db": {"type": "string", "enum": ["master", "print_process"], "description": "기본 master"},
                      "table": {"type": "string", "description": "지정 시 컬럼 목록 + 샘플 3행"}}})
def describe_schema(args: dict, ctx: ToolContext) -> ToolResult:
    db = args.get("db", "master")
    p = _db_path(ctx, db)
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        hints = MASTER_HINTS if db == "master" else PRINT_HINTS
        if args.get("table"):
            t = args["table"]
            if t not in tables:
                return ToolResult(data=dict(error=f"no table {t}", tables=tables), is_error=True)
            cols = [dict(name=r[1], type=r[2]) for r in con.execute(f'PRAGMA table_info("{t}")')]
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            sample = pd.read_sql_query(f'SELECT * FROM "{t}" LIMIT 3', con).to_dict("records")
            return ToolResult(data=dict(db=db, table=t, n_rows=n, columns=cols, sample=sample, hint=hints.get(t)), summary=f"{t}: {n} rows")
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()
    return ToolResult(data=dict(db=db, path=str(p), tables=[dict(table=t, n_rows=counts[t], hint=hints.get(t)) for t in tables],
                                notes=["master.db: 모든 컬럼 TEXT, ''=결측, fig_only='1'은 그림에서 읽은 값", "join keys: paper_uid, mix_uid, test_uid",
                                       "print_process.db: 논문 저자 판정 기반 라벨; stack_to_failure=1이면 collapsed여도 printable 가능"]),
                      summary=f"{db}: {len(tables)} tables")


@tool("sql_query",
      "읽기 전용 SELECT(단일 문장, 최대 200행, 20 s). 문헌 DB 통계·조건 검색('VMA 쓴 3DCP 논문 수', '정적항복 2 kPa 이상 믹스')에 사용. "
      "먼저 describe_schema로 컬럼을 확인. 결과 20행은 인라인, 전체는 CSV.",
      {"properties": {"sql": {"type": "string"}, "db": {"type": "string", "enum": ["master", "print_process"]},
                      "max_rows": {"type": "integer", "description": "기본 200, 최대 2000"}},
       "required": ["sql"]})
def sql_query(args: dict, ctx: ToolContext) -> ToolResult:
    db = args.get("db", "master")
    p = _db_path(ctx, db)
    max_rows = min(int(args.get("max_rows", 200)), 2000)
    try:
        df, truncated, el = run_query(p, args["sql"], max_rows=max_rows)
    except SQLGuardError as e:
        return ToolResult(data=dict(error=str(e)), is_error=True, summary="SQL 거부")
    except sqlite3.Error as e:
        return ToolResult(data=dict(error=f"sqlite: {e}"), is_error=True, summary="SQL 오류")
    d, a = frame_to_result(df, ctx, f"sql_{int(time.time())}", "SQL 결과", max_rows=20)
    d.update(db=db, row_limit_hit=truncated, elapsed_s=round(el, 2))
    return ToolResult(data=d, artifacts=[a] if len(df) > 20 else [], summary=f"{len(df)}행" + (" (제한 도달)" if truncated else ""))
