"""`pmpredict agent` — REPL / one-shot chat with the same engine as the web app."""
from __future__ import annotations

import json
import sys

from .core import Agent, event_to_text
from .events import Done, Error
from .memory import SessionStore
from .providers import LABELS, detect_provider, make_provider
from .tools.runtime import get_runtime


def print_check(status: list[dict], chosen: str | None) -> None:
    from .secrets import secret_source
    print("provider status:")
    for s in status:
        mark = "ok " if s["available"] else "-- "
        print(f"  {mark} {s['name']:<10} {s['label']:<28} {s['reason']}")
    print(f"  keys: anthropic_api_key={secret_source('anthropic_api_key')}, openai_api_key={secret_source('openai_api_key')}")
    print(f"  chosen: {chosen or 'none'}")


def main(args) -> int:
    rt = get_runtime()
    store = SessionStore(rt.agent_root)
    if getattr(args, "list_sessions", False):
        for m in store.list():
            print(f"{m['id']}  {m.get('provider', ''):<10} {m.get('title', '')}")
        return 0
    chosen, status = detect_provider(getattr(args, "provider", None))
    if getattr(args, "check", False) or chosen is None:
        print_check(status, chosen)
        if chosen is None:
            print("no provider available: set ANTHROPIC_API_KEY / OPENAI_API_KEY (or the pastemortar config.json keys), "
                  "or log in to Claude Code / Codex CLI. Use --provider fake for a dry run.", file=sys.stderr)
            return 1
        if getattr(args, "check", False):
            return 0
    provider = make_provider(chosen, getattr(args, "model", None))
    session = store.get_or_create(getattr(args, "session", None), provider.name, provider.model)
    agent = Agent(provider, session, rt)
    as_json = getattr(args, "json", False)

    def run_turn(text: str) -> bool:
        ok = True
        for ev in agent.run(text):
            if as_json:
                print(json.dumps(_ev_dict(ev), ensure_ascii=False, default=str), flush=True)
            else:
                sys.stdout.write(event_to_text(ev)); sys.stdout.flush()
            if isinstance(ev, Error) and not ev.recoverable:
                ok = False
        if not as_json:
            print()
        return ok

    if getattr(args, "prompt", None):
        return 0 if run_turn(args.prompt) else 1
    print(f"pmpredict agent — {LABELS.get(provider.name, provider.name)} ({provider.model}); session {session.id}. "
          "commands: /new /sessions /artifacts /quit")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not text:
            continue
        if text in ("/quit", "/exit"):
            break
        if text == "/new":
            session = store.create(provider.name, provider.model); agent = Agent(provider, session, rt); print(f"new session {session.id}"); continue
        if text == "/sessions":
            for m in store.list()[:20]:
                print(f"  {m['id']}  {m.get('title', '')}")
            continue
        if text == "/artifacts":
            for a in session.artifacts():
                print(f"  {a['kind']:<9} {a['path']}")
            continue
        run_turn(text)
    return 0


def _ev_dict(ev) -> dict:
    d = dict(type=type(ev).__name__)
    if hasattr(ev, "result"):
        d.update(id=ev.id, name=ev.name, result=ev.result.to_dict(), elapsed_s=ev.elapsed_s)
    elif isinstance(ev, Done):
        d.update(usage=ev.usage, provider_session_id=ev.provider_session_id, cost_usd=ev.cost_usd)
    else:
        d.update({k: v for k, v in vars(ev).items()})
    return d
