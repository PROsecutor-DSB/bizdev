#!/usr/bin/env python3
"""End-to-end pipeline driver.

    SCRAPE -> NORMALIZE -> THREADS -> CLASSIFY -> STATS -> EXTRACT -> AJTBD
    -> EMBED -> CLUSTER -> RELATIONS -> PATTERNS -> ANTI-PATTERNS -> EVOLUTION
    -> OPPORTUNITIES -> TECH x JOB -> IDEAS -> HIDDEN GEMS -> REPORTS

Every stage is independently runnable (`python -m src.<stage>`), idempotent, and
resumable: re-running skips work already in the database.

Typical first run (brief section 30 - prove the MVP on a slice before scaling):

    python run_pipeline.py --stage all --max-posts 200

Then the full history:

    python run_pipeline.py --stage all
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import PROCESSED_DIR, SCRAPE, ScrapeConfig  # noqa: E402
from src.db import store  # noqa: E402
from src.utils import load_jsonl  # noqa: E402

STAGES = [
    "scrape", "normalize", "threads", "classify", "stats", "extract", "ajtbd",
    "embed", "cluster", "relations", "patterns", "antipatterns", "evolution",
    "opportunities", "techjob", "ideas", "gems", "reports",
]


def _load_db(channel: str) -> None:
    """Mirror the processed JSONL into SQLite so the DB is the single query surface."""
    conn = store.connect()
    posts = load_jsonl(PROCESSED_DIR / f"{channel}.posts.jsonl")
    threads = load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")
    if posts:
        store.upsert(conn, "posts", posts, ["post_uid"])
    if threads:
        store.upsert(conn, "threads", threads, ["thread_id"])
    store.rebuild_fts(conn)
    conn.close()
    print(f"  db: {len(posts)} posts, {len(threads)} threads", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--stage", default="all", help="'all', or a comma-separated subset of: " + ", ".join(STAGES))
    ap.add_argument("--from-stage", default=None, help="run this stage and everything after it")
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--max-posts", type=int, default=None, help="scrape only the N newest posts")
    ap.add_argument("--min-score", type=int, default=40, help="content_signal_score floor for extraction")
    ap.add_argument("--extract-limit", type=int, default=None)
    ap.add_argument("--idea-limit", type=int, default=25)
    ap.add_argument("--cluster-threshold", type=float, default=0.78)
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--out-dir", default=None, help="where to write the markdown reports (default: output/)")
    args = ap.parse_args(argv)

    if args.from_stage:
        if args.from_stage not in STAGES:
            raise SystemExit(f"unknown stage {args.from_stage}")
        wanted = STAGES[STAGES.index(args.from_stage):]
    elif args.stage == "all":
        wanted = list(STAGES)
    else:
        wanted = [s.strip() for s in args.stage.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in STAGES]
        if unknown:
            raise SystemExit(f"unknown stage(s): {unknown}")
    if args.skip_scrape and "scrape" in wanted:
        wanted.remove("scrape")

    ch, eng = args.channel, args.engine
    t_start = time.time()

    for stage in wanted:
        print(f"\n=== {stage.upper()} ===", file=sys.stderr)
        t0 = time.time()
        try:
            if stage == "scrape":
                from src.scraper.tgweb import scrape
                scrape(ScrapeConfig(channel=ch), max_posts=args.max_posts)
            elif stage == "normalize":
                from src.parser.normalize import normalize_file
                normalize_file(ch)
            elif stage == "threads":
                from src.parser.threads import build_threads_file
                build_threads_file(ch)
                _load_db(ch)
            elif stage == "classify":
                from src.classifier.classify import run as classify
                classify(ch, eng)
            elif stage == "stats":
                from src.reports.dataset_stats import compute, render_markdown
                from src.config import OUTPUT_DIR
                from src.utils import write_json
                s = compute(ch)
                out_dir = Path(args.out_dir) if args.out_dir else OUTPUT_DIR
                out_dir.mkdir(parents=True, exist_ok=True)
                write_json(PROCESSED_DIR / f"{ch}.stats.json", s)
                (out_dir / "DATASET_STATS.md").write_text(render_markdown(s), encoding="utf-8")
                print(f"  {s['posts_total']} posts, {s['date_earliest']} .. {s['date_latest']}", file=sys.stderr)
            elif stage == "extract":
                from src.extractor.insights import run as extract
                extract(ch, eng, args.min_score, args.extract_limit)
            elif stage == "ajtbd":
                from src.extractor.ajtbd import run as ajtbd
                ajtbd(ch, eng)
            elif stage == "embed":
                from src.deduplicator.embed import run as embed
                embed(ch, eng)
            elif stage == "cluster":
                from src.deduplicator.cluster import run as cluster
                cluster(ch, args.cluster_threshold)
            elif stage == "relations":
                from src.deduplicator.relations import run as relations
                relations(ch, eng)
            elif stage == "patterns":
                from src.synthesis.patterns import run as patterns
                patterns(ch, eng)
            elif stage == "antipatterns":
                from src.synthesis.antipatterns import run as antipatterns
                antipatterns(ch, eng)
            elif stage == "evolution":
                from src.synthesis.evolution import run as evolution
                evolution(ch, eng)
            elif stage == "opportunities":
                from src.synthesis.opportunities import run as opportunities
                opportunities(ch, eng)
            elif stage == "techjob":
                from src.synthesis.tech_job import run as techjob
                techjob(ch, eng)
            elif stage == "ideas":
                from src.synthesis.ideas import run as ideas
                ideas(ch, eng, args.idea_limit)
            elif stage == "gems":
                from src.synthesis.hidden_gems import run as gems
                gems(ch)
            elif stage == "reports":
                from src.config import OUTPUT_DIR
                from src.reports.render import run as reports
                reports(ch, Path(args.out_dir) if args.out_dir else OUTPUT_DIR)
        except SystemExit as exc:
            print(f"  ! {stage} stopped: {exc}", file=sys.stderr)
            if stage in ("scrape", "normalize", "threads", "classify"):
                return 1  # the corpus stages are load-bearing; later ones may legitimately have nothing to do
        print(f"  ({time.time() - t0:.1f}s)", file=sys.stderr)

    print(f"\ndone in {time.time() - t_start:.1f}s", file=sys.stderr)
    conn = store.connect()
    for table in ("posts", "threads", "classifications", "insights", "ajtbd_concepts", "clusters", "patterns", "derived"):
        print(f"  {table:<18} {store.count(conn, table)}", file=sys.stderr)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
