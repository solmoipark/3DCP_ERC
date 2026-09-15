"""Report / file generation."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pandas as pd

from .registry import Artifact, ToolContext, ToolResult, tool


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s.strip(), flags=re.U).strip("_")
    return s[:60] or "report"


@tool("save_report",
      "대화 결과를 보고서 파일로 저장(markdown, 선택적으로 xlsx에 표 시트). 이번 세션의 다른 아티팩트(그림·CSV)를 함께 묶을 수 있음. "
      "사용자가 '정리해서 파일로 줘', '보고서로 만들어'라고 할 때.",
      {"properties": {"title": {"type": "string"}, "markdown": {"type": "string", "description": "본문 (한국어, 표·수치 포함)"},
                      "tables": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "object"}},
                                 "description": "시트명 → 행 목록 (xlsx)"},
                      "include_artifacts": {"type": "array", "items": {"type": "string"}, "description": "복사해 넣을 파일 경로들"},
                      "format": {"type": "string", "enum": ["md", "xlsx", "both"], "description": "기본 both(표가 있을 때) / md"}},
       "required": ["title", "markdown"]}, read_only=False)
def save_report(args: dict, ctx: ToolContext) -> ToolResult:
    slug = _slug(args["title"])
    out = ctx.artifact_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{slug}.md"
    body = f"# {args['title']}\n\n{args['markdown'].strip()}\n"
    copied = []
    for src in args.get("include_artifacts") or []:
        sp = Path(src)
        if sp.exists() and sp.is_file():
            dst = out / sp.name
            if sp.resolve() != dst.resolve():
                shutil.copy2(sp, dst)
            copied.append(dst.name)
    if copied:
        body += "\n## 첨부\n\n" + "\n".join(f"- {n}" + (f"\n\n![{n}]({n})" if n.lower().endswith(".png") else "") for n in copied) + "\n"
    md_path.write_text(body, encoding="utf-8")
    arts = [Artifact(path=str(md_path), kind="markdown", title=args["title"])]
    fmt = args.get("format") or ("both" if args.get("tables") else "md")
    if fmt in ("xlsx", "both"):
        x_path = out / f"{slug}.xlsx"
        with pd.ExcelWriter(x_path, engine="openpyxl") as w:
            pd.DataFrame({"보고서": [args["title"]], "본문": [args["markdown"][:32000]]}).to_excel(w, sheet_name="summary", index=False)
            for name, rows in (args.get("tables") or {}).items():
                pd.DataFrame(rows).to_excel(w, sheet_name=_slug(name)[:31], index=False)
            for n in copied:
                if n.lower().endswith(".csv"):
                    try:
                        pd.read_csv(out / n).to_excel(w, sheet_name=_slug(Path(n).stem)[:31], index=False)
                    except Exception:  # noqa: BLE001
                        pass
        arts.append(Artifact(path=str(x_path), kind="file", title=f"{args['title']} (xlsx)"))
    return ToolResult(data=dict(files=[a.path for a in arts], attached=copied), artifacts=arts, summary=f"보고서 저장: {md_path.name}")
