"""NEW TECHNOLOGY x OLD JOB synthesis (brief section 16).

Inputs: every insight tagged AI / AI_AGENTS / VIBE_CODING / AUTOMATION, plus
insights whose text mentions the relevant tooling. Output: entries that state the
old constraint and how the technology moved it - not "AI agents are popular".
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import SCRAPE, TAXONOMY  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.synthesis.common import pack, provenance  # noqa: E402
from src.utils import clamp_int, derived_id, utcnow_iso  # noqa: E402

TECH_TAGS = {"AI", "AI_AGENTS", "VIBE_CODING", "AUTOMATION"}
TECH_RE = re.compile(
    r"\b(ai|ии|llm|gpt|codex|claude|cursor|copilot|agent|агент|нейросет|vibe|вайб|"
    r"автоматизац|automation|prompt|промпт)\b",
    re.IGNORECASE,
)
BATCH = 12


def _candidates(conn: Any) -> list[dict[str, Any]]:
    rows = store.query(conn, "SELECT * FROM insights ORDER BY date DESC")
    out = []
    for r in rows:
        tags = set(r.get("tags") or [])
        blob = " ".join(str(r.get(f) or "") for f in ("thesis", "mechanism", "keywords", "sub_category"))
        if tags & TECH_TAGS or TECH_RE.search(blob):
            out.append(r)
    return out


def run(channel: str = "", engine: str = "auto", limit: int | None = None) -> int:
    conn = store.connect()
    cands = _candidates(conn)
    if limit:
        cands = cands[:limit]
    provider = get_provider(engine)
    print(f"technology x job synthesis over {len(cands)} AI/automation insights", file=sys.stderr)
    run_id = store.start_run(conn, "tech_job", provider.engine, {"candidates": len(cands)})

    rows: list[dict[str, Any]] = []
    for i in range(0, len(cands), BATCH):
        batch = cands[i : i + BATCH]
        try:
            res = provider.complete_json(
                prompts.TECH_JOB_SYSTEM,
                f"{len(batch)} insights about technology capability from the channel:\n\n{pack(batch, full=True)}",
            )
        except Exception as exc:
            print(f"  ! tech_job batch {i} failed: {exc}", file=sys.stderr)
            continue
        posts, ins = provenance(batch)
        for item in res.get("items") or []:
            if not isinstance(item, dict) or not (item.get("job") or "").strip():
                continue
            title = f"{item.get('technology_shift', '')[:60]} -> {item.get('job', '')[:80]}"
            rows.append(
                {
                    "derived_id": derived_id("tj", title + str(i)),
                    "kind": "TECH_JOB",
                    "title": title[:200],
                    "payload": item,
                    "source_posts": posts,
                    "source_insights": ins,
                    "label": "DERIVED_HYPOTHESIS",
                    "confidence": clamp_int(item.get("confidence"), 1, 5, 2),
                    "tags": [t for t in (item.get("tags") or []) if t in TAXONOMY][:6] or ["AI"],
                    "engine": provider.engine,
                    "prompt_version": prompts.PROMPT_VERSION,
                    "created_at": utcnow_iso(),
                }
            )

    conn.execute("DELETE FROM derived WHERE kind='TECH_JOB'")
    store.upsert(conn, "derived", rows, ["derived_id"])
    store.finish_run(conn, run_id, {"tech_job_items": len(rows)})
    conn.close()
    print(f"{len(rows)} technology x job entries stored", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
