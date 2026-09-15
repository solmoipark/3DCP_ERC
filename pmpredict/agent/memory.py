"""Sessions (transcript + meta + rolling summary) under ~/.pmpredict/agent and durable notes."""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .tools.registry import ToolResult

SUMMARY_TRIGGER_CHARS = 40_000
WINDOW_TURNS = 20


@dataclass
class Session:
    id: str
    dir: Path
    meta: dict = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)      # {"role": user|assistant, "content": [blocks], "ts"}
    summary: str = ""

    # ------------------------------------------------------------------ persistence
    @property
    def transcript_path(self) -> Path:
        return self.dir / "transcript.jsonl"

    def save_meta(self) -> None:
        self.meta["updated"] = datetime.now().isoformat(timespec="seconds")
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=1, ensure_ascii=False), encoding="utf-8")

    def _append_line(self, rec: dict) -> None:
        with open(self.transcript_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def append_user(self, text: str) -> None:
        rec = dict(role="user", content=[dict(type="text", text=text)], ts=datetime.now().isoformat(timespec="seconds"))
        self.turns.append(rec); self._append_line(rec)
        if not self.meta.get("title"):
            self.meta["title"] = text.strip().replace("\n", " ")[:40]
            self.save_meta()

    def append_assistant(self, blocks: list[dict]) -> None:
        """blocks: {"type":"text","text"} | {"type":"tool_use","id","name","input"} | {"type":"tool_result","id","name","result": ToolResult.to_dict(), "elapsed_s"}"""
        if not blocks:
            return
        rec = dict(role="assistant", content=blocks, ts=datetime.now().isoformat(timespec="seconds"))
        self.turns.append(rec); self._append_line(rec)

    # ------------------------------------------------------------------ views
    def transcript_chars(self) -> int:
        return sum(len(json.dumps(t, ensure_ascii=False, default=str)) for t in self.turns)

    def messages_for_provider(self, window_turns: int = WINDOW_TURNS, keep_results_turns: int = 3) -> list[dict]:
        """Provider-neutral history: summary (if any) + last `window_turns` user/assistant records, old tool results elided."""
        recent = self.turns[-window_turns:]
        n_assist = sum(1 for t in recent if t["role"] == "assistant")
        out = []
        if self.summary and len(self.turns) > window_turns:
            out.append(dict(role="user", content=[dict(type="text", text=f"[이전 대화 요약]\n{self.summary}")]))
            out.append(dict(role="assistant", content=[dict(type="text", text="요약을 확인했습니다. 이어서 진행합니다.")]))
        seen_assist = 0
        for t in recent:
            if t["role"] == "assistant":
                seen_assist += 1
                old = (n_assist - seen_assist) >= keep_results_turns
                blocks = []
                for b in t["content"]:
                    if b["type"] == "tool_result" and old:
                        paths = ", ".join(a["path"] for a in b["result"].get("artifacts", [])) or "없음"
                        blocks.append(dict(b, result=dict(data={"note": f"[결과 생략 — 파일: {paths}]", "summary": b["result"].get("summary", "")},
                                                          artifacts=b["result"].get("artifacts", []), summary=b["result"].get("summary", ""),
                                                          is_error=b["result"].get("is_error", False))))
                    else:
                        blocks.append(b)
                out.append(dict(role="assistant", content=blocks))
            else:
                out.append(dict(role="user", content=t["content"]))
        return out

    def artifacts(self) -> list[dict]:
        seen, out = set(), []
        for t in self.turns:
            for b in t["content"]:
                if b["type"] == "tool_result":
                    for a in b["result"].get("artifacts", []):
                        if a["path"] not in seen:
                            seen.add(a["path"]); out.append(a)
        return out

    def needs_summary(self) -> bool:
        return self.transcript_chars() > SUMMARY_TRIGGER_CHARS and len(self.turns) > WINDOW_TURNS

    def set_summary(self, text: str) -> None:
        self.summary = text
        (self.dir / "summary.md").write_text(text, encoding="utf-8")

    def plain_text(self, max_chars: int = 60_000) -> str:
        """Readable transcript for summarisation."""
        lines = []
        for t in self.turns:
            for b in t["content"]:
                if b["type"] == "text":
                    lines.append(f"{t['role']}: {b['text']}")
                elif b["type"] == "tool_use":
                    lines.append(f"assistant → tool {b['name']}({json.dumps(b['input'], ensure_ascii=False)[:300]})")
                elif b["type"] == "tool_result":
                    lines.append(f"tool {b.get('name')} ⇒ {b['result'].get('summary', '')}")
        s = "\n".join(lines)
        return s[-max_chars:]


class SessionStore:
    def __init__(self, root: Path):
        self.root = Path(root) / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), reverse=True):
            mp = d / "meta.json"
            if d.is_dir() and mp.exists():
                try:
                    out.append(json.loads(mp.read_text(encoding="utf-8")))
                except ValueError:
                    continue
        return out

    def create(self, provider: str = "", model: str = "") -> Session:
        sid = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        d = self.root / sid
        d.mkdir(parents=True, exist_ok=True)
        s = Session(id=sid, dir=d, meta=dict(id=sid, title="", created=datetime.now().isoformat(timespec="seconds"), provider=provider,
                                             model=model, provider_session_id=None, usage_total={}, cost_usd=0.0))
        s.save_meta()
        return s

    def load(self, sid: str) -> Session:
        d = self.root / sid
        if not (d / "meta.json").exists():
            raise FileNotFoundError(f"session {sid} not found")
        s = Session(id=sid, dir=d, meta=json.loads((d / "meta.json").read_text(encoding="utf-8")))
        if s.transcript_path.exists():
            for ln in s.transcript_path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    s.turns.append(json.loads(ln))
        sp = d / "summary.md"
        if sp.exists():
            s.summary = sp.read_text(encoding="utf-8")
        return s

    def get_or_create(self, sid: str | None, provider: str = "", model: str = "") -> Session:
        if sid:
            try:
                return self.load(sid)
            except FileNotFoundError:
                pass
        return self.create(provider, model)


def tool_result_block(call_id: str, name: str, res: ToolResult, elapsed_s: float) -> dict:
    return dict(type="tool_result", id=call_id, name=name, result=res.to_dict(), elapsed_s=round(elapsed_s, 2))
