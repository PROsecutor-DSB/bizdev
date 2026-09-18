"""STEP 3: classify every thread and score its content signal.

Two scores are always stored side by side:
  rule_signal_score    - deterministic, from surface markers (src/llm/heuristic.py)
  content_signal_score - the LLM's judgement, or the rule score when no LLM is configured

Neither uses views or reactions. Popularity is stored on the post and used only
as a *secondary* signal in reports (brief section 4).

Nothing is deleted here. PROMO and HIRING posts stay in the database; the
extractor simply does not spend tokens on them.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, POST_CATEGORIES, PROCESSED_DIR, SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import heuristic, prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.utils import clamp_int, load_jsonl, utcnow_iso, write_jsonl  # noqa: E402


def classify_thread(thread: dict[str, Any], provider: Any, use_llm: bool) -> dict[str, Any]:
    text = thread["text"]
    rule_score = heuristic.rule_signal_score(text)
    rule_cat = heuristic.rule_category(text)
    clean_fallback, removed = heuristic.strip_promo_shell(text)

    category, score, clean_text, tags, reasoning = rule_cat, rule_score, clean_fallback, heuristic.rule_tags(text), "rule-based"
    engine = provider.engine

    if use_llm and text.strip():
        try:
            out = provider.complete_json(prompts.CLASSIFY_SYSTEM, prompts.classify_user(text))
        except Exception as exc:  # never lose the whole run to one bad call
            print(f"  ! classify failed for {thread['thread_id']}: {exc}", file=sys.stderr)
            out = {}
        if out.get("category") in POST_CATEGORIES:
            category = out["category"]
        if out.get("content_signal_score") is not None:
            score = clamp_int(out["content_signal_score"], 0, 100, rule_score)
        llm_clean = (out.get("clean_text") or "").strip()
        # Guard against a model that "cleans" by rewriting everything away.
        if llm_clean and len(llm_clean) >= 0.2 * len(text):
            clean_text = llm_clean
        if isinstance(out.get("tags"), list) and out["tags"]:
            tags = [t for t in out["tags"] if isinstance(t, str)][:8]
        reasoning = (out.get("reasoning") or reasoning)[:400]

    # A post whose substance is gone has no content signal, whatever the label says.
    if not clean_text.strip():
        score = min(score, 15)

    return {
        "thread_id": thread["thread_id"],
        "category": category,
        "content_signal_score": score,
        "rule_signal_score": rule_score,
        "promo_present": bool(removed) or category in ("PROMO", "CONTENT_PLUS_PROMO"),
        "clean_text": clean_text,
        "removed_promo": removed,
        "tags": tags,
        "reasoning": reasoning,
        "engine": engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "classified_at": utcnow_iso(),
    }


def run(channel: str, engine: str = "auto", limit: int | None = None, force: bool = False) -> Path:
    threads = load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")
    if not threads:
        raise SystemExit("no threads found - run normalize + threads first")
    if limit:
        threads = sorted(threads, key=lambda t: t["post_ids"][0], reverse=True)[:limit]

    provider = get_provider(engine)
    use_llm = provider.engine != "heuristic"

    conn = store.connect()
    done: set[str] = set()
    if not force:
        done = {r["thread_id"] for r in store.query(conn, "SELECT thread_id FROM classifications")}
    todo = [t for t in threads if t["thread_id"] not in done]
    print(f"classifying {len(todo)} threads (engine={provider.engine}, {len(done)} cached)", file=sys.stderr)

    run_id = store.start_run(conn, "classify", provider.engine, {"channel": channel, "limit": limit})
    results: list[dict[str, Any]] = []
    workers = LLM.concurrency if use_llm else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, res in enumerate(pool.map(lambda t: classify_thread(t, provider, use_llm), todo), 1):
            results.append(res)
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", file=sys.stderr)

    store.upsert(conn, "classifications", results, ["thread_id"])
    all_rows = store.query(conn, "SELECT * FROM classifications")
    out = PROCESSED_DIR / f"{channel}.classified.jsonl"
    write_jsonl(out, all_rows)

    dist: dict[str, int] = {}
    for r in all_rows:
        dist[r["category"]] = dist.get(r["category"], 0) + 1
    store.finish_run(conn, run_id, {"classified": len(results), "distribution": dist})
    conn.close()

    print("category distribution:", file=sys.stderr)
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {k:<20} {v}", file=sys.stderr)
    print(f"wrote {len(all_rows)} classifications -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="re-classify already-classified threads")
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.limit, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
