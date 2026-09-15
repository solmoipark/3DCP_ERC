"""Agent layer tests that need no LLM: registry projections, SQL guard, normalisers, secrets, fake end-to-end."""
from __future__ import annotations

import json
import sqlite3

import pytest

from pmpredict.agent import secrets as S
from pmpredict.agent.tools import REGISTRY, to_anthropic_tools, to_openai_tools
from pmpredict.agent.tools.normalise import NormaliseError, job_from_dict, mix_from_dict, space_from_dict, target_rows_to_specs
from pmpredict.agent.tools.registry import ToolResult, result_for_llm
from pmpredict.agent.tools.sql_tools import SQLGuardError, guard_sql, run_query


def test_registry_schemas_consistent():
    assert len(REGISTRY) >= 16
    for t in REGISTRY.values():
        s = t.input_schema
        assert s["type"] == "object" and s.get("additionalProperties") is False, t.name
        assert set(s.get("required", [])) <= set(s["properties"]), t.name
        assert t.description and any("가" <= ch <= "힣" for ch in t.description), t.name
    a = {d["name"]: d["input_schema"] for d in to_anthropic_tools()}
    o = {d["function"]["name"]: d["function"]["parameters"] for d in to_openai_tools()}
    assert a == o and set(a) == set(REGISTRY)
    mcp = pytest.importorskip("mcp")  # noqa: F841
    from pmpredict.agent.tools.registry import to_mcp_tools
    assert {t.name for t in to_mcp_tools()} == set(REGISTRY)


def test_result_for_llm_truncates_and_keeps_artifacts():
    from pmpredict.agent.tools.registry import Artifact
    res = ToolResult(data={"big": "x" * 10000}, artifacts=[Artifact(path="a.csv", kind="table", title="t")], summary="s")
    s = result_for_llm(res, max_chars=500)
    assert len(s) < 700 and "truncated" in s and "a.csv" in s


def test_sql_guard(tmp_path):
    for ok in ["SELECT 1", "with t as (select 1 x) select * from t", "  select count(*) from papers -- comment", "/* c */ SELECT 2;"]:
        assert guard_sql(ok)
    for bad in ["DROP TABLE papers", "PRAGMA table_info(x)", "SELECT 1; DELETE FROM papers", "ATTACH 'x' AS y", "/*x*/DELETE FROM papers",
                "select load_extension('x')", ""]:
        with pytest.raises(SQLGuardError):
            guard_sql(bad)
    db = tmp_path / "t.db"
    con = sqlite3.connect(db); con.execute("CREATE TABLE t(a)"); con.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(50)]); con.commit(); con.close()
    df, trunc, _ = run_query(db, "SELECT a FROM t ORDER BY a", max_rows=10)
    assert len(df) == 10 and trunc
    with pytest.raises(SQLGuardError):     # a write hidden inside a SELECT is still caught by the keyword guard
        run_query(db, "SELECT * FROM t WHERE 1 = (DELETE FROM t)")
    from pmpredict.agent.tools.sql_tools import _authorizer
    assert _authorizer(sqlite3.SQLITE_INSERT, "t", None, "main", None) == sqlite3.SQLITE_DENY   # second line of defence
    assert _authorizer(sqlite3.SQLITE_READ, "t", "a", "main", None) == sqlite3.SQLITE_OK
    con = sqlite3.connect(db); con.set_authorizer(_authorizer)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO t VALUES (99)")
    con.close()


def test_mix_from_dict_matches_form_rules():
    spec, warns = mix_from_dict(dict(system_type="mortar", w_b=0.4, s_b=2.0, binder={"portland_cement": 7, "silica_fume": 3},
                                     admixtures_pct={"superplasticiser_pce": 0.5}, fibres_vol_pct={"pva_fibre": 1.0} if "pva_fibre" in _fibres() else {},
                                     conditions=dict(age_d=28, curing="water", is_3dcp=True)))
    comps = {c.material_class: c for c in spec.components}
    assert comps["portland_cement"].amount == pytest.approx(0.7) and comps["silica_fume"].amount == pytest.approx(0.3)
    assert comps["natural_sand"].amount == pytest.approx(2.0) and comps["superplasticiser_pce"].amount == pytest.approx(0.005)
    assert spec.conditions.curing_regime == "water curing at 20 C" and spec.conditions.curing_rh_pct == 100.0 and spec.conditions.is_3dcp == 1
    assert any("normalised" in w for w in warns)
    paste, w2 = mix_from_dict(dict(system_type="paste", w_b=0.3, s_b=1.0, binder={"portland_cement": 1}))
    assert "natural_sand" not in {c.material_class for c in paste.components} and any("ignored" in w for w in w2)
    with pytest.raises(NormaliseError) as e:
        mix_from_dict(dict(w_b=0.3, binder={"portland_cment": 1}))
    assert "portland_cement" in str(e.value)


def _fibres():
    from pmpredict.agent.tools.normalise import classes_of
    return classes_of("fibre")


def test_targets_space_job():
    ts = target_rows_to_specs([dict(quantity="compressive_strength", kind="ge", lo=40, unit="MPa", age_d=28, comparability_group="comp_cube50"),
                               dict(quantity="shear_stress_at_rate", kind="range", lo=100, hi=500, unit="Pa", shear_rate_1s=50)])
    assert ts[0]["conditions"]["age_d"] == 28 and ts[1]["conditions"]["shear_rate_1s"] == 50 and ts[1]["lo"] == 100
    sp = space_from_dict(dict(system_type="mortar", w_b=[0.3, 0.45], binder={"portland_cement": {"lo": 0.5, "hi": 1, "required": True}}, curing="moist"))
    assert sp["fixed_conditions"]["curing_rh_pct"] == 95.0 and sp["s_b"] == [1.0, 3.0]
    job = job_from_dict(dict(target_height_mm=300, nozzle={"d_mm": 20}, footprint_mm=250, object_type="hollow_cylinder", open_time_min=0))
    assert job.nozzle_d_mm == 20 and job.open_time_min is None
    j2, filled = job.resolve({})
    assert j2.layer_height_mm == 10 and len(filled) >= 2


def test_secrets(tmp_path, monkeypatch):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"anthropic_api_key": "sk-ant-secretvalue12345"}), encoding="utf-8")
    monkeypatch.setenv("PMPREDICT_SECRETS_FILE", str(f))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert S.get_secret("anthropic_api_key") == "sk-ant-secretvalue12345" and S.secret_source("anthropic_api_key") == "config"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-envvalue67890")
    assert S.get_secret("anthropic_api_key") == "sk-ant-envvalue67890" and S.secret_source("anthropic_api_key") == "env"
    assert "envvalue" not in S.redact("error sk-ant-envvalue67890 happened") and "secretvalue" not in S.redact("x sk-ant-secretvalue12345")
    monkeypatch.setenv("PMPREDICT_SECRETS_FILE", str(tmp_path / "missing.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert S.get_secret("anthropic_api_key") is None and S.secret_source("anthropic_api_key") == "none"


def test_fake_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("PMPREDICT_HOME", str(tmp_path / "home"))
    from pmpredict.agent.core import Agent
    from pmpredict.agent.events import Done, ToolCall, ToolResultEvent
    from pmpredict.agent.memory import SessionStore
    from pmpredict.agent.providers.fake import FakeProvider
    from pmpredict.agent.tools.runtime import Runtime
    rt = Runtime()
    store = SessionStore(rt.agent_root)
    session = store.create("fake", "fake-1")
    prov = FakeProvider(script=[[("text", "안녕하세요"), ("tool", "remember", {"note": "PI는 SKKU", "kind": "fact"}), ("text", "저장했습니다")],
                                [("tool", "describe_vocabulary", {"family": "powder", "query": "fly"})]])
    agent = Agent(prov, session, rt)
    evs = list(agent.run("기억해: PI는 SKKU"))
    assert any(isinstance(e, ToolCall) and e.name == "remember" for e in evs) and isinstance(evs[-1], Done)
    assert (rt.agent_root / "notes.md").read_text(encoding="utf-8").count("PI는 SKKU") == 1
    evs2 = list(agent.run("fly ash 클래스?"))
    res = next(e for e in evs2 if isinstance(e, ToolResultEvent)).result
    assert not res.is_error and any("fly_ash" in c["material_class"] for c in res.data["classes"]["powder"])
    # persistence
    again = store.load(session.id)
    assert len(again.turns) == 4 and again.meta["provider"] == "fake" and again.meta["provider_session_id"] == "fake-2"
    msgs = again.messages_for_provider()
    assert msgs[0]["role"] == "user" and msgs[-1]["role"] == "assistant"
    from pmpredict.agent.prompt import build_system_prompt
    sp = build_system_prompt(rt, again.summary)
    assert "PI는 SKKU" in sp and "compressive_strength" in sp
