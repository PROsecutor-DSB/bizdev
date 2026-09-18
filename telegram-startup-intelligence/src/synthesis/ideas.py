"""IDEA_GENERATOR (brief sections 17-18).

Each idea is grounded in a bundle of: a derived opportunity, the technology x job
entries that share its tags, and the core patterns that apply. No free-floating
"AI for X" ideas.

Scores are stored as nine independent 1-5 dimensions. There is deliberately no
combined score anywhere in this file - the report prints the vector and the
trade-off sentence, and never ranks.
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
from src.utils import clamp_int, derived_id, utcnow_iso  # noqa: E402

SCORE_KEYS = [
    "job_frequency", "pain", "existing_spend", "poor_existing_solution",
    "technology_unlock", "demoability", "buildability_48h",
    "distribution_accessibility", "evidence_strength",
]


def _bundle(conn: Any, opp: dict[str, Any], tech: list[dict[str, Any]], patterns: list[dict[str, Any]]) -> str:
    tags = set(opp.get("tags") or [])
    rel_tech = [t for t in tech if tags & set(t.get("tags") or [])][:4] or tech[:2]
    rel_pat = [p for p in patterns if tags & set(p.get("tags") or [])][:3]

    parts = ["DERIVED OPPORTUNITY (our inference from the channel):", str(opp["payload"])]
    if rel_tech:
        parts.append("\nRELEVANT TECHNOLOGY x JOB ENTRIES:")
        parts += [str(t["payload"]) for t in rel_tech]
    if rel_pat:
        parts.append("\nAPPLICABLE PATTERNS FROM THE CHANNEL:")
        parts += [f"{p['name']}: {p['payload'].get('mechanism', '')}" for p in rel_pat]
    parts.append(
        "\nSOURCE POSTS (cite these, invent no others): " + ", ".join(opp["source_posts"][:12])
    )
    return "\n".join(parts)[:14000]


def synth_one(args: tuple[dict[str, Any], str, Any]) -> list[dict[str, Any]]:
    opp, bundle, provider = args
    try:
        res = provider.complete_json(prompts.IDEA_SYSTEM, bundle)
    except Exception as exc:
        print(f"  ! idea generation failed for {opp['derived_id']}: {exc}", file=sys.stderr)
        return []
    out: list[dict[str, Any]] = []
    for item in res.get("ideas") or []:
        if not isinstance(item, dict) or not (item.get("idea") or "").strip():
            continue
        raw_scores = item.get("scores") or {}
        item["scores"] = {k: clamp_int(raw_scores.get(k), 1, 5, 1) for k in SCORE_KEYS}
        out.append(
            {
                "derived_id": derived_id("idea", item["idea"] + opp["derived_id"]),
                "kind": "IDEA",
                "title": item["idea"][:200],
                "payload": item,
                "source_posts": opp["source_posts"],
                "source_insights": opp["source_insights"],
                "label": "DERIVED_HYPOTHESIS",
                "confidence": item["scores"]["evidence_strength"],
                "tags": [t for t in (item.get("tags") or []) if t in TAXONOMY][:6] or opp.get("tags") or ["STARTUP"],
                "engine": provider.engine,
                "prompt_version": prompts.PROMPT_VERSION,
                "created_at": utcnow_iso(),
            }
        )
    return out


def run(channel: str = "", engine: str = "auto", limit: int = 25) -> int:
    conn = store.connect()
    opps = store.query(conn, "SELECT * FROM derived WHERE kind='OPPORTUNITY' ORDER BY confidence DESC")[:limit]
    if not opps:
        raise SystemExit("no derived opportunities - run src.synthesis.opportunities first")
    tech = store.query(conn, "SELECT * FROM derived WHERE kind='TECH_JOB'")
    patterns = store.query(conn, "SELECT * FROM patterns WHERE kind='CORE_PATTERN'")

    provider = get_provider(engine)
    print(f"generating ideas from {len(opps)} opportunities", file=sys.stderr)
    run_id = store.start_run(conn, "ideas", provider.engine, {"opportunities": len(opps)})
    jobs = [(o, _bundle(conn, o, tech, patterns), provider) for o in opps]
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for res in pool.map(synth_one, jobs):
            rows.extend(res)

    conn.execute("DELETE FROM derived WHERE kind='IDEA'")
    store.upsert(conn, "derived", rows, ["derived_id"])
    store.finish_run(conn, run_id, {"ideas": len(rows)})
    conn.close()
    print(f"{len(rows)} ideas stored (no combined score is computed, by design)", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
