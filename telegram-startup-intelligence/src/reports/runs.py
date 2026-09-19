"""When did each pipeline stage last run?

The reports deliberately carry no generation timestamp - it would make every
re-render a git diff even when the content is identical. The timing lives here
instead, in the database's `runs` table, which also records the engine, the
parameters and the resulting counts.

    python -m src.reports.runs
    python -m src.reports.runs --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db import store  # noqa: E402
from src.utils import allow_broken_pipe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    allow_broken_pipe()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="every run, not just the latest per stage")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    conn = store.connect()
    if args.all:
        rows = store.query(conn, "SELECT * FROM runs ORDER BY run_id DESC LIMIT ?", (args.limit,))
    else:
        rows = store.query(
            conn,
            """SELECT r.* FROM runs r
               JOIN (SELECT stage, MAX(run_id) AS m FROM runs GROUP BY stage) latest
                 ON latest.m = r.run_id
               ORDER BY r.run_id""",
        )
    conn.close()

    if not rows:
        print("no runs recorded yet")
        return 0

    print(f"{'stage':<16} {'finished (UTC)':<26} {'engine':<24} stats")
    print("-" * 100)
    for r in rows:
        stats = r.get("stats")
        if isinstance(stats, str):
            try:
                stats = json.loads(stats)
            except json.JSONDecodeError:
                pass
        summary = json.dumps(stats, ensure_ascii=False)[:60] if stats else "(did not finish)"
        print(f"{r['stage']:<16} {(r.get('finished_at') or '-'):<26} {(r.get('engine') or '-'):<24} {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
