"""OPPORTUNITY_MAP: mine implied startup opportunities (brief section 15).

Everything produced here is labelled DERIVED_HYPOTHESIS at the database level.
It is our inference from the author's observation, never his position.

Candidate selection is deterministic: insights that describe a structural problem
(problem_pattern present, or a PROBLEM/NEED/JOB/COMPETITION category) and that do
NOT already hand you the product.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, SCRAPE, TAXONOMY  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.synthesis.common import insight_brief, provenance  # noqa: E402
from src.utils import clamp_int, derived_id, utcnow_iso  # noqa: E402

PROBLEM_CATEGORIES = {"PROBLEM", "NEED", "JOB", "CUSTOMER", "BEHAVIOR", "COMPETITION",
                      "ORGANIZATION", "DISTRIBUTION", "UNIT_ECONOMICS", "SEGMENT"}


def _candidates(conn: Any, limit: int | None) -> list[dict[str, Any]]:
    rows = store.query(
        conn,
        "SELECT * FROM insights WHERE is_cluster_representative=1 ORDER BY "
        "(transferability_score + actionability_score + novelty_score) DESC",
    )
    picked = [
        r
        for r in rows
        if (r.get("problem_pattern") or "").strip() or r["category"] in PROBLEM_CATEGORIES
    ]
    return picked[:limit] if limit else picked


def synth_one(row: dict[str, Any], provider: Any) -> dict[str, Any] | None:
    try:
        res = provider.complete_json(
            prompts.OPPORTUNITY_SYSTEM,
            "SOURCE INSIGHT (the author's observation; the opportunity below is YOUR inference):\n\n"
            + insight_brief(row, full=True),
        )
    except Exception as exc:
        print(f"  ! opportunity synthesis failed for {row['insight_id']}: {exc}", file=sys.stderr)
        return None
    title = (res.get("title") or "").strip()
    if not title or not (res.get("underlying_job") or "").strip():
        return None
    posts, ins = provenance([row])
    return {
        "derived_id": derived_id("opp", title + row["insight_id"]),
        "kind": "OPPORTUNITY",
        "title": title[:200],
        "payload": res,
        "source_posts": posts,
        "source_insights": ins,
        "label": "DERIVED_HYPOTHESIS",
        "confidence": clamp_int(res.get("confidence"), 1, 5, 2),
        "tags": [t for t in (res.get("tags") or []) if t in TAXONOMY][:6] or [row["category"]],
        "engine": provider.engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "created_at": utcnow_iso(),
    }


def run(channel: str = "", engine: str = "auto", limit: int | None = 60) -> int:
    conn = store.connect()
    cands = _candidates(conn, limit)
    provider = get_provider(engine)
    print(f"mining {len(cands)} problem insights for implied opportunities", file=sys.stderr)
    run_id = store.start_run(conn, "opportunities", provider.engine, {"candidates": len(cands)})
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = [r for r in pool.map(lambda r: synth_one(r, provider), cands) if r]

    conn.execute("DELETE FROM derived WHERE kind='OPPORTUNITY'")
    store.upsert(conn, "derived", rows, ["derived_id"])
    store.finish_run(conn, run_id, {"opportunities": len(rows)})
    conn.close()
    print(f"{len(rows)} derived opportunities stored (all labelled DERIVED_HYPOTHESIS)", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
