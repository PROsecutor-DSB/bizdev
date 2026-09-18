"""Reconstruct the author's own Advanced JTBD vocabulary (brief section 8).

Runs on the subset of threads that actually talk about Jobs, and on the highest
signal threads regardless of vocabulary (the author often describes the mechanism
without naming it). Concepts are stored one row per (concept, source post), so
AJTBD_KNOWLEDGE_BASE.md can show how the same concept was framed over time.
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import AJTBD_CONCEPTS, EXTRACTABLE_CATEGORIES, INSIGHTS_DIR, LLM, PROCESSED_DIR, SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.utils import clamp_int, derived_id, load_jsonl, write_jsonl  # noqa: E402

JOB_LANGUAGE = re.compile(
    r"jtbd|job\b|джоб|работ\w* котор|нанима\w+ продукт|триггер|trigger|"
    r"контекст|сегмент|критери\w+ успеха|switch|переключ|конкурирующ|альтернатив",
    re.IGNORECASE,
)

CONCEPT_SLUGS = {c.lower() for c in AJTBD_CONCEPTS}


def _slugify_concept(raw: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (raw or "").lower()).strip("_")
    return s or "other"


def extract_one(thread: dict[str, Any], cls: dict[str, Any], provider: Any) -> list[dict[str, Any]]:
    text = (cls.get("clean_text") or thread["text"]).strip()
    if not text:
        return []
    try:
        res = provider.complete_json(
            prompts.AJTBD_SYSTEM, prompts.ajtbd_user(text, thread["date_start"] or "", thread["urls"][0])
        )
    except Exception as exc:
        print(f"  ! ajtbd failed for {thread['thread_id']}: {exc}", file=sys.stderr)
        return []

    out: list[dict[str, Any]] = []
    head = thread["post_uids"][0]
    for c in res.get("concepts") or []:
        if not isinstance(c, dict) or not (c.get("definition") or "").strip():
            continue
        slug = _slugify_concept(c.get("concept", ""))
        out.append(
            {
                "concept_uid": derived_id("ajt", f"{head}|{slug}"),
                "concept": slug,
                "label": (c.get("label") or "").strip()[:120],
                "definition": (c.get("definition") or "").strip()[:2000],
                "mechanism": (c.get("mechanism") or "").strip()[:2000],
                "business_consequence": (c.get("business_consequence") or "").strip()[:1500],
                "how_to_detect": (c.get("how_to_detect") or "").strip()[:1500],
                "how_to_use": (c.get("how_to_use") or "").strip()[:1500],
                "example": (c.get("example") or "").strip()[:1200],
                "divergence_from_classic_jtbd": (c.get("divergence_from_classic_jtbd") or "").strip()[:800],
                "quote": (c.get("quote") or "").strip()[:300],
                "confidence": clamp_int(c.get("confidence"), 1, 5, 2),
                "source_post_id": head,
                "source_url": thread["urls"][0],
                "date": thread["date_start"],
                "engine": provider.engine,
                "prompt_version": prompts.PROMPT_VERSION,
            }
        )
    return out


def run(channel: str, engine: str = "auto", min_score: int = 45, limit: int | None = None) -> Path:
    threads = {t["thread_id"]: t for t in load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")}
    classified = load_jsonl(PROCESSED_DIR / f"{channel}.classified.jsonl")

    selected = []
    for c in classified:
        t = threads.get(c["thread_id"])
        if not t or c["category"] not in EXTRACTABLE_CATEGORIES:
            continue
        body = c.get("clean_text") or t["text"]
        if JOB_LANGUAGE.search(body) or c["content_signal_score"] >= 70:
            if c["content_signal_score"] >= min_score:
                selected.append(c)
    selected.sort(key=lambda c: -c["content_signal_score"])
    if limit:
        selected = selected[:limit]

    provider = get_provider(engine)
    conn = store.connect()
    done = {r["source_post_id"] for r in store.query(conn, "SELECT DISTINCT source_post_id FROM ajtbd_concepts")}
    todo = [c for c in selected if threads[c["thread_id"]]["post_uids"][0] not in done]
    print(f"AJTBD pass over {len(todo)} threads (of {len(selected)} selected) engine={provider.engine}", file=sys.stderr)

    run_id = store.start_run(conn, "ajtbd", provider.engine, {"channel": channel, "min_score": min_score})
    results: list[dict[str, Any]] = []
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(extract_one, threads[c["thread_id"]], c, provider) for c in todo]
        for f in futures:
            results.extend(f.result())

    store.upsert(conn, "ajtbd_concepts", results, ["concept_uid"])
    rows = store.query(conn, "SELECT * FROM ajtbd_concepts ORDER BY concept, date")
    out = INSIGHTS_DIR / f"{channel}.ajtbd.jsonl"
    write_jsonl(out, rows)
    known = sum(1 for r in rows if r["concept"] in CONCEPT_SLUGS)
    store.finish_run(conn, run_id, {"new": len(results), "total": len(rows), "in_canonical_list": known})
    conn.close()
    print(f"{len(rows)} AJTBD concept observations -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--min-score", type=int, default=45)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.min_score, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
