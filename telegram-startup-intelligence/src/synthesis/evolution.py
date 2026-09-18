"""EVOLUTION_OF_THOUGHT synthesis (brief section 10).

Candidate topics come from two deterministic signals:
  1. relation pairs the verifier labelled CONTRADICTION or EVOLUTION;
  2. taxonomy areas whose insights span a long period (>= --min-span-days), where
     a position could plausibly have drifted.

The model then decides whether the position ACTUALLY changed. changed=false is
recorded too - that is useful information, and it stops the report from inventing
drama where the author simply repeated himself.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.synthesis.common import date_range, pack, provenance  # noqa: E402
from src.utils import clamp_int, derived_id, utcnow_iso  # noqa: E402

MIN_SPAN_DAYS = 365


def _span_days(rows: list[dict[str, Any]]) -> int:
    d0, d1 = date_range(rows)
    if not d0 or not d1:
        return 0
    try:
        return (datetime.fromisoformat(d1) - datetime.fromisoformat(d0)).days
    except ValueError:
        return 0


def _topics(conn: Any, min_span_days: int) -> list[tuple[str, list[dict[str, Any]]]]:
    insights = {r["insight_id"]: r for r in store.query(conn, "SELECT * FROM insights")}
    topics: dict[str, dict[str, dict[str, Any]]] = {}

    for rel in store.query(conn, "SELECT * FROM relations WHERE relation IN ('CONTRADICTION','EVOLUTION')"):
        a, b = insights.get(rel["a_id"]), insights.get(rel["b_id"])
        if not a or not b:
            continue
        key = f"conflict::{a['category']}::{rel['a_id']}"
        topics.setdefault(key, {})[a["insight_id"]] = a
        topics[key][b["insight_id"]] = b

    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in insights.values():
        by_cat.setdefault(r["category"], []).append(r)
    for cat, rows in by_cat.items():
        if len(rows) >= 3 and _span_days(rows) >= min_span_days:
            topics.setdefault(f"span::{cat}", {}).update({r["insight_id"]: r for r in rows})

    return [(k, sorted(v.values(), key=lambda r: r.get("date") or "")) for k, v in topics.items()]


def synth_one(topic: tuple[str, list[dict[str, Any]]], provider: Any) -> dict[str, Any] | None:
    key, rows = topic
    try:
        res = provider.complete_json(
            prompts.EVOLUTION_SYSTEM,
            f"Topic key: {key}\nSpan: {_span_days(rows)} days\n\n{pack(rows, full=True)}",
        )
    except Exception as exc:
        print(f"  ! evolution synthesis failed for {key}: {exc}", file=sys.stderr)
        return None
    if not res or not (res.get("topic") or "").strip():
        return None
    posts, ins = provenance(rows)
    return {
        "derived_id": derived_id("evo", key),
        "kind": "EVOLUTION",
        "title": (res.get("topic") or key)[:200],
        "payload": res,
        "source_posts": posts,
        "source_insights": ins,
        # The narrative of a change is our reading unless the author states the
        # reason himself; the prompt makes the model prefix inferred reasons.
        "label": "DERIVED_HYPOTHESIS" if res.get("changed") else "OBSERVED",
        "confidence": clamp_int(res.get("confidence"), 1, 5, 2),
        "tags": [rows[0]["category"]],
        "engine": provider.engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "created_at": utcnow_iso(),
    }


def run(channel: str = "", engine: str = "auto", min_span_days: int = MIN_SPAN_DAYS, limit: int | None = None) -> int:
    conn = store.connect()
    topics = _topics(conn, min_span_days)
    topics.sort(key=lambda t: -len(t[1]))
    if limit:
        topics = topics[:limit]
    provider = get_provider(engine)
    print(f"checking {len(topics)} topics for changes of position", file=sys.stderr)
    run_id = store.start_run(conn, "evolution", provider.engine, {"topics": len(topics)})
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = [r for r in pool.map(lambda t: synth_one(t, provider), topics) if r]

    conn.execute("DELETE FROM derived WHERE kind='EVOLUTION'")
    store.upsert(conn, "derived", rows, ["derived_id"])
    changed = sum(1 for r in rows if r["payload"].get("changed"))
    store.finish_run(conn, run_id, {"topics": len(rows), "actually_changed": changed})
    conn.close()
    print(f"{len(rows)} topics analysed, {changed} show a real change of position", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--min-span-days", type=int, default=MIN_SPAN_DAYS)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.min_span_days, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
