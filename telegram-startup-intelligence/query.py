#!/usr/bin/env python3
"""Ask the local knowledge base questions.

    python query.py                                  # interactive
    python query.py "What does he say about choosing a segment?"
    python query.py "An AI agent that negotiates purchases" --critique
    python query.py --tag RAT --limit 20             # no LLM, pure retrieval
    python query.py --jobs                           # unresolved Jobs / opportunities

Retrieval is hybrid and fully local: SQLite FTS5 lexical search combined with
embedding similarity over the stored insight vectors. The LLM only writes the
answer, and only from the retrieved excerpts.

Answer contract (brief section 29):
  1. grounded in the local base;
  2. every claim cites a real Telegram permalink;
  3. the author's words and our inference are separated;
  4. uncertainty is stated, including "the base does not cover this";
  5. no invented evidence - a missing answer is reported as missing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import SCRAPE, TAXONOMY  # noqa: E402
from src.db import store  # noqa: E402
from src.deduplicator.cluster import cosine  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.utils import allow_broken_pipe  # noqa: E402

FTS_CLEAN = re.compile(r"[^\w\s]", re.UNICODE)


def fts_query(text: str) -> str:
    """FTS5 chokes on punctuation; OR the terms so partial matches still rank."""
    words = [w for w in FTS_CLEAN.sub(" ", text).split() if len(w) > 2][:24]
    return " OR ".join(f'"{w}"' for w in words) if words else '""'


def retrieve(conn: Any, question: str, k: int = 18, tag: str | None = None, engine: str = "auto") -> list[dict[str, Any]]:
    scores: dict[str, float] = {}

    if question.strip():
        try:
            for i, r in enumerate(
                store.query(
                    conn,
                    "SELECT insight_id, rank FROM insights_fts WHERE insights_fts MATCH ? ORDER BY rank LIMIT 80",
                    (fts_query(question),),
                )
            ):
                scores[r["insight_id"]] = scores.get(r["insight_id"], 0.0) + 1.0 / (10 + i)
        except Exception:
            pass  # a malformed FTS expression must not kill the query

        embs = store.query(conn, "SELECT item_id, vector FROM embeddings WHERE kind='insight'")
        if embs:
            provider = get_provider(engine)
            qv = provider.embed([question])[0]
            for e in embs:
                v = json.loads(e["vector"])
                if len(v) == len(qv):
                    scores[e["item_id"]] = scores.get(e["item_id"], 0.0) + max(0.0, cosine(qv, v))

    if not scores:
        # No query text: fall back to the strongest insights, filtered in SQL so
        # the tag restriction is applied before the LIMIT, not after it.
        if tag:
            rows = store.query(
                conn,
                """SELECT DISTINCT i.* FROM insights i
                   LEFT JOIN insight_tags t ON t.insight_id = i.insight_id
                   WHERE t.tag = ? OR i.category = ?
                   ORDER BY (i.actionability_score + i.transferability_score + i.novelty_score) DESC
                   LIMIT ?""",
                (tag.upper(), tag.upper(), k),
            )
        else:
            rows = store.query(
                conn,
                "SELECT * FROM insights ORDER BY "
                "(actionability_score+transferability_score+novelty_score) DESC LIMIT ?",
                (k,),
            )
        return rows

    top_ids = [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])[: k * 5]]
    placeholders = ",".join("?" for _ in top_ids)
    rows = store.query(conn, f"SELECT * FROM insights WHERE insight_id IN ({placeholders})", top_ids)
    order = {i: n for n, i in enumerate(top_ids)}
    rows.sort(key=lambda r: order.get(r["insight_id"], 999))

    if tag:
        rows = [r for r in rows if tag.upper() in (r.get("tags") or []) or r["category"] == tag.upper()]
    return rows[:k]


def context_block(rows: list[dict[str, Any]], extras: list[dict[str, Any]] | None = None) -> str:
    parts = ["KNOWLEDGE BASE EXCERPTS (the only evidence you may cite):\n"]
    for r in rows:
        parts.append(
            f"--- post {r['source_post_id']} ({r.get('date','')[:10]}) {r['source_url']}\n"
            f"THESIS: {r['thesis']}\n"
            f"MECHANISM: {r.get('mechanism') or '(not stated in the post)'}\n"
            f"WHY IT MATTERS: {r.get('why_it_matters') or ''}\n"
            f"STARTUP APPLICATION: {r.get('startup_application') or ''}\n"
            f"HACKATHON APPLICATION: {r.get('hackathon_application') or ''}\n"
            f"ANTI-PATTERN: {r.get('anti_pattern') or ''}\n"
            f"EVIDENCE: {r['evidence_type']} (strength {r['evidence_strength']}/5)\n"
            f"QUOTE: {r.get('quote') or ''}\n"
        )
    for e in extras or []:
        parts.append(
            f"--- {e['kind']} ({e.get('label','')}) sources {', '.join(e['source_posts'][:6])}\n"
            f"{e['title']}\n{json.dumps(e['payload'], ensure_ascii=False)[:1500]}\n"
        )
    return "\n".join(parts)


def print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("nothing matched.")
        return
    for i, r in enumerate(rows, 1):
        print(f"\n{i}. {r['thesis']}")
        if r.get("mechanism"):
            print(f"   mechanism: {r['mechanism'][:400]}")
        print(f"   {r['evidence_type']} ({r['evidence_strength']}/5) · {r['category']} · {r.get('date','')[:10]}")
        print(f"   {r['source_url']}")


def answer(conn: Any, question: str, critique: bool, k: int, tag: str | None, engine: str) -> None:
    rows = retrieve(conn, question, k, tag, engine)
    extras: list[dict[str, Any]] = []
    if critique:
        extras = store.query(
            conn,
            "SELECT * FROM patterns WHERE kind='ANTI_PATTERN' ORDER BY support DESC LIMIT 6",
        ) + store.query(conn, "SELECT * FROM patterns WHERE kind='CORE_PATTERN' ORDER BY support DESC LIMIT 6")
        for e in extras:
            e.setdefault("label", "")

    provider = get_provider(engine)
    if provider.engine == "heuristic":
        print("\n! No LLM configured - showing raw retrieval instead of a written answer.")
        print("  Set LLM_API_KEY to get a grounded, cited answer.\n")
        print_rows(rows)
        return

    system = prompts.CRITIQUE_SYSTEM if critique else prompts.ANSWER_SYSTEM
    user = f"QUESTION / IDEA:\n{question}\n\n{context_block(rows, extras)}"
    res = provider.complete_json(system, user, max_tokens=4096)
    md = (res.get("answer_markdown") or "").strip()
    if not md:
        print("the model returned nothing usable; raw retrieval follows:")
        print_rows(rows)
        return
    print("\n" + md + "\n")
    cov = res.get("coverage") or "UNKNOWN"
    print(f"--- coverage: {cov} · {len(rows)} excerpts retrieved from {store.count(conn,'insights')} insights")
    for c in res.get("caveats") or []:
        print(f"    caveat: {c}")
    cited = res.get("cited_post_ids") or []
    known = {r["source_post_id"] for r in rows} | {p for r in rows for p in (r.get("source_posts") or [])}
    bad = [c for c in cited if c not in known]
    if bad:
        print(f"    ! the model cited post ids not present in the retrieved context: {bad}")


def list_jobs(conn: Any, limit: int) -> None:
    rows = store.query(conn, "SELECT * FROM derived WHERE kind='OPPORTUNITY' ORDER BY confidence DESC LIMIT ?", (limit,))
    if not rows:
        print("no derived opportunities yet - run `python -m src.synthesis.opportunities`")
        return
    print(f"\n{len(rows)} unresolved Jobs / opportunities (all DERIVED_HYPOTHESIS, not the author's position):\n")
    for i, r in enumerate(rows, 1):
        p = r["payload"]
        print(f"{i}. {r['title']}")
        print(f"   Job:    {p.get('underlying_job','')}")
        print(f"   Wedge:  {p.get('potential_wedge','')}")
        print(f"   ICP:    {p.get('potential_icp','')}")
        print(f"   Test:   {p.get('fast_validation_test','')}")
        print(f"   Source: {', '.join('https://t.me/' + s.replace('/', '/') for s in r['source_posts'][:4])}\n")


def interactive(conn: Any, engine: str, k: int) -> None:
    n = store.count(conn, "insights")
    print(f"telegram-startup-intelligence · {n} insights · engine={get_provider(engine).engine}")
    print("commands: /tag <TAG>  /jobs  /stats  /critique <idea>  /quit\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            continue
        if q in ("/quit", "/exit", "/q"):
            return
        if q == "/stats":
            for t in ("posts", "insights", "clusters", "patterns", "derived", "ajtbd_concepts"):
                print(f"  {t:<16} {store.count(conn, t)}")
            continue
        if q == "/jobs":
            list_jobs(conn, 10)
            continue
        if q.startswith("/tag"):
            tag = q.split(maxsplit=1)[1].upper() if len(q.split()) > 1 else ""
            if tag not in TAXONOMY:
                print(f"  unknown tag. Known: {', '.join(TAXONOMY)}")
                continue
            print_rows(store.query(
                conn,
                """SELECT DISTINCT i.* FROM insights i JOIN insight_tags t ON t.insight_id=i.insight_id
                   WHERE t.tag=? ORDER BY (i.actionability_score+i.transferability_score) DESC LIMIT 20""",
                (tag,),
            ))
            continue
        if q.startswith("/critique"):
            answer(conn, q.split(maxsplit=1)[1] if len(q.split()) > 1 else "", True, k, None, engine)
            continue
        answer(conn, q, False, k, None, engine)


def main(argv: list[str] | None = None) -> int:
    allow_broken_pipe()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="*", help="your question, or an idea to critique")
    ap.add_argument("--critique", action="store_true", help="treat the input as a startup idea and critique it")
    ap.add_argument("--tag", default=None, help="restrict retrieval to one taxonomy tag")
    ap.add_argument("--jobs", action="store_true", help="list unresolved Jobs / derived opportunities")
    ap.add_argument("--limit", "-k", type=int, default=18, help="how many excerpts to retrieve")
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--channel", default=SCRAPE.channel)
    args = ap.parse_args(argv)

    conn = store.connect()
    if store.count(conn, "insights") == 0:
        print("the knowledge base is empty - run `python run_pipeline.py --stage all` first", file=sys.stderr)
        return 1

    if args.jobs:
        list_jobs(conn, args.limit)
    elif args.question:
        answer(conn, " ".join(args.question), args.critique, args.limit, args.tag, args.engine)
    elif args.tag:
        print_rows(retrieve(conn, "", args.limit, args.tag, args.engine))
    else:
        interactive(conn, args.engine, args.limit)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
