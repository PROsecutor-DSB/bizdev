"""STEP 5: extract atomic insights from substantive threads.

Selection: only threads the classifier routed to an extractable category AND
whose content_signal_score clears --min-score. Pure noise never reaches the LLM,
which is where the token budget is saved on a multi-thousand-post channel.

Chunking: a thread longer than --chunk-tokens is split on paragraph boundaries
with overlap, so a mechanism split across two paragraphs is not lost. Every chunk
keeps the full provenance of the thread it came from.
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import (  # noqa: E402
    EVIDENCE_TYPES,
    EXTRACTABLE_CATEGORIES,
    INSIGHTS_DIR,
    LLM,
    PROCESSED_DIR,
    SCRAPE,
    TAXONOMY,
)
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.utils import clamp_int, insight_id, load_jsonl, token_count_estimate, utcnow_iso, write_jsonl  # noqa: E402

DEFAULT_MIN_SCORE = 40
DEFAULT_CHUNK_TOKENS = 1200
OVERLAP_PARAGRAPHS = 1


def chunk_text(text: str, max_tokens: int = DEFAULT_CHUNK_TOKENS) -> list[str]:
    if token_count_estimate(text) <= max_tokens:
        return [text]
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for p in paragraphs:
        pt = token_count_estimate(p)
        if cur and cur_tokens + pt > max_tokens:
            chunks.append("\n\n".join(cur))
            cur = cur[-OVERLAP_PARAGRAPHS:] if OVERLAP_PARAGRAPHS else []
            cur_tokens = sum(token_count_estimate(c) for c in cur)
        cur.append(p)
        cur_tokens += pt
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _norm_tags(raw: Any, fallback: list[str]) -> list[str]:
    tags = [t for t in (raw or []) if isinstance(t, str) and t.upper() in TAXONOMY]
    return sorted({t.upper() for t in tags}) or fallback


THESIS_NOISE_RE = re.compile(r"^\s*(?:-{3,}|\d{1,2}\s*/\s*\d{1,2}\.?|часть\s*\d+\.?)\s*", re.IGNORECASE)


def clean_thesis(text: str) -> str:
    """A thesis is one line. Thread separators and part markers are not part of it."""
    parts = [THESIS_NOISE_RE.sub("", ln).strip() for ln in (text or "").split("\n")]
    joined = " ".join(p for p in parts if p and not re.fullmatch(r"-{3,}", p))
    return re.sub(r"\s+", " ", joined).strip()


def normalize_insight(raw: dict[str, Any], thread: dict[str, Any], cls: dict[str, Any], engine: str) -> dict[str, Any] | None:
    thesis = clean_thesis(raw.get("thesis") or "")
    if len(thesis) < 15:
        return None

    tags = _norm_tags(raw.get("tags"), [])
    category = (raw.get("category") or "").upper()
    if category not in TAXONOMY:
        category = tags[0] if tags else "PRODUCT"
    if not tags:
        tags = [category]

    evidence_type = (raw.get("evidence_type") or "").upper()
    if evidence_type not in EVIDENCE_TYPES:
        # Section 9: when in doubt it is the author's unsupported claim, not evidence.
        evidence_type = "AUTHOR_CLAIM"

    head_uid = thread["post_uids"][0]
    mechanism = (raw.get("mechanism") or "").strip()

    return {
        "insight_id": insight_id(head_uid, thesis),
        "source_post_id": head_uid,
        "source_posts": thread["post_uids"],
        "source_url": thread["urls"][0],
        "source_urls": thread["urls"],
        "date": thread["date_start"],
        "category": category,
        "sub_category": (raw.get("sub_category") or "").strip()[:80],
        "tags": tags,
        "thesis": thesis[:800],
        "mechanism": mechanism[:2500],
        "mechanism_missing_reason": (raw.get("mechanism_missing_reason") or "").strip()[:300],
        "why_it_matters": (raw.get("why_it_matters") or "").strip()[:1200],
        "problem_pattern": (raw.get("problem_pattern") or "").strip()[:800],
        "solution_pattern": (raw.get("solution_pattern") or "").strip()[:800],
        "startup_application": (raw.get("startup_application") or "").strip()[:1200],
        "hackathon_application": (raw.get("hackathon_application") or "").strip()[:1200],
        "example": (raw.get("example") or "").strip()[:1200],
        "anti_pattern": (raw.get("anti_pattern") or "").strip()[:800],
        "quote": (raw.get("quote") or "").strip()[:300],
        "evidence_type": evidence_type,
        "evidence_strength": clamp_int(raw.get("evidence_strength"), 0, 5, 1),
        "novelty_score": clamp_int(raw.get("novelty_score"), 0, 5, 2),
        "actionability_score": clamp_int(raw.get("actionability_score"), 0, 5, 2),
        "transferability_score": clamp_int(raw.get("transferability_score"), 0, 5, 2),
        "hackathon_value_score": clamp_int(raw.get("hackathon_value_score"), 0, 5, 1),
        "keywords": [k for k in (raw.get("keywords") or []) if isinstance(k, str)][:10],
        "content_signal_score": cls["content_signal_score"],
        "views": thread.get("views_max"),
        "reactions_total": thread.get("reactions_total"),
        "engine": engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "extracted_at": utcnow_iso(),
    }


def extract_one(thread: dict[str, Any], cls: dict[str, Any], provider: Any, chunk_tokens: int) -> list[dict[str, Any]]:
    text = (cls.get("clean_text") or thread["text"]).strip()
    if not text:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunk_text(text, chunk_tokens):
        try:
            res = provider.complete_json(
                prompts.EXTRACT_SYSTEM,
                prompts.extract_user(chunk, thread["date_start"] or "", thread["urls"][0]),
            )
        except Exception as exc:
            print(f"  ! extract failed for {thread['thread_id']}: {exc}", file=sys.stderr)
            continue
        for raw in res.get("insights") or []:
            if not isinstance(raw, dict):
                continue
            rec = normalize_insight(raw, thread, cls, provider.engine)
            if rec and rec["insight_id"] not in seen:
                seen.add(rec["insight_id"])
                out.append(rec)
    return out


def run(
    channel: str,
    engine: str = "auto",
    min_score: int = DEFAULT_MIN_SCORE,
    limit: int | None = None,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    force: bool = False,
) -> Path:
    threads = {t["thread_id"]: t for t in load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")}
    classified = load_jsonl(PROCESSED_DIR / f"{channel}.classified.jsonl")
    if not classified:
        raise SystemExit("run the classifier first")

    selected = [
        c
        for c in classified
        if c["category"] in EXTRACTABLE_CATEGORIES
        and c["content_signal_score"] >= min_score
        and c["thread_id"] in threads
    ]
    selected.sort(key=lambda c: -c["content_signal_score"])
    if limit:
        selected = selected[:limit]

    provider = get_provider(engine)
    conn = store.connect()
    if force:
        conn.execute("DELETE FROM insights")
        conn.execute("DELETE FROM insight_tags")
        conn.commit()
    already = {r["source_post_id"] for r in store.query(conn, "SELECT DISTINCT source_post_id FROM insights")}
    todo = [c for c in selected if threads[c["thread_id"]]["post_uids"][0] not in already]

    skipped = len(classified) - len(selected)
    print(
        f"extracting from {len(todo)} threads "
        f"(selected {len(selected)} of {len(classified)}; skipped {skipped} below score {min_score} or non-extractable; "
        f"{len(selected)-len(todo)} cached) engine={provider.engine}",
        file=sys.stderr,
    )

    run_id = store.start_run(conn, "extract", provider.engine, {"channel": channel, "min_score": min_score, "limit": limit})
    results: list[dict[str, Any]] = []
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(extract_one, threads[c["thread_id"]], c, provider, chunk_tokens) for c in todo]
        for i, f in enumerate(futures, 1):
            results.extend(f.result())
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} threads, {len(results)} insights", file=sys.stderr)

    store.upsert(conn, "insights", results, ["insight_id"])
    store.upsert(
        conn,
        "insight_tags",
        [{"insight_id": r["insight_id"], "tag": t} for r in results for t in r["tags"]],
        ["insight_id", "tag"],
    )
    all_rows = store.query(conn, "SELECT * FROM insights ORDER BY date")
    store.rebuild_fts(conn)
    out = INSIGHTS_DIR / f"{channel}.insights.jsonl"
    write_jsonl(out, all_rows)

    with_mech = sum(1 for r in all_rows if (r.get("mechanism") or "").strip())
    store.finish_run(conn, run_id, {"new": len(results), "total": len(all_rows), "with_mechanism": with_mech})
    conn.close()
    print(f"{len(all_rows)} insights total, {with_mech} with a reconstructed mechanism -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.min_score, args.limit, args.chunk_tokens, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
