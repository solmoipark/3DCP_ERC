# -*- coding: utf-8 -*-
"""pmpredict — chat-first UI.

  streamlit run app/streamlit_app.py      (or: pmpredict ui)

The agent (pmpredict.agent) answers in Korean and calls the prediction / inverse-design / buildability / literature / SQL
tools; results (tables, figures, reports) render inline with download buttons. The former form pages stay reachable
through the sidebar toggle "직접 실행 (기존 폼)" (app/legacy_pages.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

st.set_page_config(page_title="pmpredict agent", page_icon="🧱", layout="wide")

# Streamlit Cloud: API keys live in the app's Secrets; expose them as environment variables for pmpredict.agent.secrets
try:
    for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PMPREDICT_PROVIDER", "PMPREDICT_OPENAI_MODEL"):
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # noqa: BLE001  (no secrets file locally)
    pass

from pmpredict.agent.events import Done, Error, TextDelta, ToolCall, ToolProgress, ToolResultEvent  # noqa: E402
from pmpredict.agent.memory import SessionStore  # noqa: E402
from pmpredict.agent.providers import LABELS, ORDER, detect_provider, make_provider, provider_status  # noqa: E402
from pmpredict.agent.secrets import secret_source  # noqa: E402
from pmpredict.agent.tools.runtime import get_runtime as _get_runtime  # noqa: E402

EXAMPLES = [
    "OPC 모르타르 w/b 0.40, s/b 2.0, PCE 0.5 %의 28일 압축강도와 플로우를 예측해줘",
    "25 mm 노즐로 높이 600 mm, 길이 1.5 m 벽(2필라멘트)을 50 mm/s로 뽑으려고 해. 정적항복 3 kPa, Athix 1 Pa/s인 재료면 되는지 판정하고 사이클 시간 창을 알려줘",
    "3DCP 논문 중 VMA를 쓴 논문이 몇 편이고, 그 믹스들의 정적항복응력 중앙값은?",
    "28일 압축 ≥ 40 MPa, 정적항복 1–4 kPa인 문헌 배합 10개를 찾아줘 (3DCP 우선)",
    "위 조건으로 클링커 최소화 배합을 역설계해줘 (OPC 필수, 실리카퓸·석회석 허용)",
]
MODEL_CHOICES = {"anthropic": ["claude-sonnet-5", "claude-opus-5"], "openai": ["gpt-5", "gpt-5-mini"], "claude_sdk": ["sonnet", "opus"],
                 "codex": [""], "fake": ["fake-1"]}


# ------------------------------------------------------------------ cached resources
@st.cache_resource(show_spinner="모델·데이터 로딩...")
def get_runtime():
    return _get_runtime()


@st.cache_resource(show_spinner=False)
def get_provider(name: str, model: str):
    return make_provider(name, model or None)


@st.cache_data(ttl=60, show_spinner=False)
def get_status():
    return provider_status()


def get_store() -> SessionStore:
    return SessionStore(get_runtime().agent_root)


# ------------------------------------------------------------------ rendering
def render_artifact(a: dict, key: str) -> None:
    p = Path(a["path"])
    if not p.exists():
        st.caption(f"(파일 없음) {p.name}")
        return
    kind = a.get("kind")
    try:
        if kind == "image":
            st.image(str(p), caption=a.get("title"), use_container_width=True)
        elif kind == "table":
            df = pd.read_csv(p)
            st.dataframe(df.head(200), hide_index=True, use_container_width=True)
            if len(df) > 200:
                st.caption(f"{len(df)}행 중 200행 표시")
        elif kind == "markdown":
            with st.expander(a.get("title") or p.name, expanded=False):
                st.markdown(p.read_text(encoding="utf-8"))
        elif kind == "json":
            with st.expander(a.get("title") or p.name, expanded=False):
                st.json(json.loads(p.read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001
        st.caption(f"표시 실패 {p.name}: {e}")
    mime = {"image": "image/png", "table": "text/csv", "markdown": "text/markdown", "json": "application/json"}.get(kind, "application/octet-stream")
    st.download_button(f"⬇ {p.name}", p.read_bytes(), file_name=p.name, mime=mime, key=f"dl_{key}")


def render_tool_result(name: str, res: dict, key: str, elapsed: float | None = None) -> None:
    data = res.get("data", {})
    if res.get("is_error"):
        st.error(f"{name}: {data.get('error', '오류')}")
    else:
        st.caption(f"{res.get('summary', '')}" + (f" · {elapsed:.1f} s" if elapsed else ""))
    for i, a in enumerate(res.get("artifacts", [])):
        render_artifact(a, f"{key}_{i}")
    with st.expander("도구 결과 JSON", expanded=False):
        st.json({k: v for k, v in data.items() if k not in ("rows",)} | ({"rows": data["rows"][:20]} if "rows" in data else {}))


def render_turn(turn: dict, key: str) -> None:
    role = turn["role"]
    with st.chat_message("user" if role == "user" else "assistant"):
        pending: dict[str, dict] = {}
        for i, b in enumerate(turn["content"]):
            if b["type"] == "text":
                st.markdown(b["text"])
            elif b["type"] == "tool_use":
                pending[b["id"]] = b
            elif b["type"] == "tool_result":
                call = pending.pop(b["id"], {"name": b.get("name"), "input": {}})
                label = f"🔧 {b.get('name')} — {b['result'].get('summary', '')}"
                with st.status(label, state="error" if b["result"].get("is_error") else "complete", expanded=False):
                    st.code(json.dumps(call.get("input", {}), ensure_ascii=False, indent=1)[:3000], language="json")
                    render_tool_result(b.get("name"), b["result"], f"{key}_{i}", b.get("elapsed_s"))
        for b in pending.values():
            st.caption(f"🔧 {b['name']} (결과 없음)")


# ------------------------------------------------------------------ sidebar
def sidebar() -> tuple[str | None, str, bool]:
    with st.sidebar:
        st.markdown("## pmpredict agent")
        status = get_status()
        chosen, _ = detect_provider()
        names = [s["name"] for s in status if s["available"]] + ["fake"]
        default = st.session_state.get("provider") or chosen or "fake"
        prov = st.selectbox("LLM 백엔드", names, index=names.index(default) if default in names else 0, format_func=lambda n: LABELS.get(n, n))
        st.session_state["provider"] = prov
        models = MODEL_CHOICES.get(prov, [""])
        model = st.selectbox("모델", models, index=0, format_func=lambda m: m or "(기본)")
        with st.expander("백엔드 상태", expanded=False):
            for s in status:
                st.markdown(("✅" if s["available"] else "⬜") + f" **{s['label']}** — {s['reason']}")
            st.caption(f"키: anthropic {secret_source('anthropic_api_key')} · openai {secret_source('openai_api_key')} (값은 표시하지 않음). "
                       "구독 경로(Claude/Codex)는 이 PC의 개인 사용 전용이며 웹 배포에 쓰지 않습니다.")
        st.markdown("---")
        store = get_store()
        sessions = store.list()
        labels = {m["id"]: f"{m.get('title') or '(새 세션)'} · {m['id'][:15]}" for m in sessions}
        cur = st.session_state.get("session_id")
        opts = ["(새 세션)"] + [m["id"] for m in sessions]
        pick = st.selectbox("세션", opts, index=(opts.index(cur) if cur in opts else 0), format_func=lambda x: labels.get(x, x))
        if pick == "(새 세션)":
            if cur is not None and st.session_state.get("_pick") != pick:
                st.session_state["session_id"] = None
        elif pick != cur:
            st.session_state["session_id"] = pick
        st.session_state["_pick"] = pick
        if st.button("새 세션 시작", use_container_width=True):
            st.session_state["session_id"] = None
            st.rerun()
        st.markdown("**예시 질문**")
        for i, ex in enumerate(EXAMPLES):
            if st.button(ex, key=f"ex_{i}", use_container_width=True):
                st.session_state["pending_prompt"] = ex
        st.markdown("---")
        legacy = st.toggle("직접 실행 (기존 폼)", value=st.session_state.get("legacy", False))
        st.session_state["legacy"] = legacy
        m = st.session_state.get("usage_caption")
        if m:
            st.caption(m)
    return prov, model, legacy


# ------------------------------------------------------------------ chat
def chat_page(prov: str, model: str) -> None:
    from pmpredict.agent.core import Agent
    rt = get_runtime()
    store = get_store()
    if st.session_state.get("session_id"):
        try:
            session = store.load(st.session_state["session_id"])
        except FileNotFoundError:
            session = store.create(prov, model)
    else:
        session = store.create(prov, model)
        st.session_state["session_id"] = session.id
    st.session_state["session_id"] = session.id
    st.title("pmpredict agent")
    st.caption("배합 → 성능 예측 · 목표 → 배합 역설계 · 노즐/구조물 → 빌더빌리티와 프린팅 스케줄 · 문헌 검색 · 문헌 DB 질의. "
               "수치는 모두 도구 결과이며 80 % 구간과 함께 제시됩니다. 유변 예측은 자릿수 참고용입니다.")
    for i, t in enumerate(session.turns):
        render_turn(t, f"t{i}")
    busy = st.session_state.get("busy", False)
    prompt = st.chat_input("무엇을 도와드릴까요? (예: 'w/b 0.35 3DCP 모르타르 정적항복응력 예측')", disabled=busy)
    pending = st.session_state.pop("pending_prompt", None)
    text = prompt or pending
    if not text:
        return
    st.session_state["busy"] = True
    try:
        provider = get_provider(prov, model)
    except Exception as e:  # noqa: BLE001
        st.session_state["busy"] = False
        st.error(f"백엔드 초기화 실패: {e}")
        return
    agent = Agent(provider, session, rt)
    with st.chat_message("user"):
        st.markdown(text)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        buf: list[str] = []
        statuses: dict[str, tuple] = {}
        try:
            for ev in agent.run(text):
                if isinstance(ev, TextDelta):
                    buf.append(ev.text)
                    placeholder.markdown("".join(buf) + "▌")
                elif isinstance(ev, ToolCall):
                    if buf:
                        placeholder.markdown("".join(buf)); buf.clear()
                    placeholder = st.empty()
                    box = st.status(f"🔧 {ev.name} 실행 중…", expanded=False)
                    with box:
                        st.code(json.dumps(ev.input, ensure_ascii=False, indent=1)[:3000], language="json")
                    statuses[ev.id] = (box, ev.name)
                    placeholder = st.empty()
                elif isinstance(ev, ToolProgress):
                    if ev.id in statuses:
                        statuses[ev.id][0].update(label=f"🔧 {statuses[ev.id][1]} … {ev.pct:.0f} % {ev.message}")
                elif isinstance(ev, ToolResultEvent):
                    box, name = statuses.get(ev.id, (None, ev.name))
                    if box is None:
                        box = st.status(f"🔧 {name}", expanded=False)
                    with box:
                        render_tool_result(name, ev.result.to_dict(), f"live_{ev.id}", ev.elapsed_s)
                    box.update(label=f"🔧 {name} — {ev.result.summary}", state="error" if ev.result.is_error else "complete")
                    placeholder = st.empty()
                elif isinstance(ev, Error):
                    st.error(ev.message)
                elif isinstance(ev, Done):
                    u = ev.usage or {}
                    st.session_state["usage_caption"] = (f"마지막 턴: in {u.get('input_tokens', '?')} / out {u.get('output_tokens', '?')} 토큰"
                                                         + (f" · 캐시 {u.get('cache_read_input_tokens')}" if u.get("cache_read_input_tokens") else "")
                                                         + (f" · ${ev.cost_usd:.4f}" if ev.cost_usd else ""))
            placeholder.markdown("".join(buf))
        finally:
            st.session_state["busy"] = False
    st.rerun()


# ------------------------------------------------------------------ router
prov, model, legacy = sidebar()
if legacy:
    import legacy_pages as LP
    page = st.sidebar.radio("페이지", list(LP.PAGES), label_visibility="collapsed")
    LP.PAGES[page]()
else:
    chat_page(prov, model)
