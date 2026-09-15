"""Durable notes the PI asks the agent to remember (kept outside the repo)."""
from __future__ import annotations

from datetime import datetime

from .registry import ToolContext, ToolResult, tool


def notes_path(rt):
    return rt.agent_root / "notes.md"


def read_notes(rt, max_chars: int = 4000) -> str:
    p = notes_path(rt)
    if not p.exists():
        return ""
    s = p.read_text(encoding="utf-8")
    return s[-max_chars:] if len(s) > max_chars else s


@tool("remember",
      "사용자가 '기억해', '앞으로는 ~로 해'라고 한 사실·선호·할 일을 세션 간 유지되는 노트에 저장. 다음 세션 시스템 프롬프트에 포함됨.",
      {"properties": {"note": {"type": "string"}, "kind": {"type": "string", "enum": ["fact", "preference", "todo"]}}, "required": ["note"]},
      read_only=False)
def remember(args: dict, ctx: ToolContext) -> ToolResult:
    p = notes_path(ctx.runtime)
    line = f"- [{datetime.now():%Y-%m-%d}] ({args.get('kind', 'fact')}) {args['note'].strip()}\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(line)
    n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- "))
    return ToolResult(data=dict(saved=line.strip(), n_notes=n, path=str(p)), summary=f"노트 저장 ({n}개)")
