"""Group posts that only make sense together (brief section 20).

A "thread" here is a logical series: a post that continues the previous one.
We stay deterministic and conservative - a wrong merge destroys meaning, while a
missed merge only loses a little context. Signals used:

  1. explicit reply_to pointing at a nearby post of the same channel;
  2. album/grouped_id (same media group, split captions);
  3. explicit part markers: "1/5", "Часть 2", "продолжение", "(2)";
  4. a dangling opener: previous post ends with a colon or ellipsis AND the next
     post follows within THREAD_GAP_MINUTES.

Every thread keeps the post_uid + permanent_url of every member, so provenance
is never lost.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import PROCESSED_DIR, SCRAPE  # noqa: E402
from src.utils import load_jsonl, write_jsonl  # noqa: E402

THREAD_GAP_MINUTES = 90

PART_RE = re.compile(
    r"^\s*(?:\(?\d{1,2}\s*[/из]{1,3}\s*\d{1,2}\)?"          # 1/5, 2 из 5
    r"|часть\s*\d+|part\s*\d+"
    r"|продолжение|продолжаю|окончание|continued)\b",
    re.IGNORECASE,
)
DANGLING_END_RE = re.compile(r"(?::|\.\.\.|…|→|↓)\s*$")
CONTINUATION_START_RE = re.compile(r"^\s*(?:и\s|а\s|но\s|поэтому|итак|кстати|ещё|еще|\d[\.\)]\s)", re.IGNORECASE)


def _dt(post: dict[str, Any]) -> datetime | None:
    if not post.get("date"):
        return None
    try:
        return datetime.fromisoformat(post["date"])
    except ValueError:
        return None


def _minutes_between(a: dict[str, Any], b: dict[str, Any]) -> float:
    da, db = _dt(a), _dt(b)
    if da is None or db is None:
        return float("inf")
    return abs((db - da).total_seconds()) / 60.0


def continues(prev: dict[str, Any], cur: dict[str, Any]) -> tuple[bool, str]:
    if prev["channel"] != cur["channel"]:
        return False, ""
    if cur.get("grouped_id") and cur["grouped_id"] == prev.get("grouped_id"):
        return True, "grouped_media"
    if cur.get("reply_to") == prev["post_id"]:
        return True, "reply_to"
    gap = _minutes_between(prev, cur)
    if gap > THREAD_GAP_MINUTES:
        return False, ""
    if PART_RE.match(cur.get("text_without_links") or ""):
        return True, "part_marker"
    if DANGLING_END_RE.search((prev.get("text_without_links") or "").strip()) and gap <= 15:
        return True, "dangling_opener"
    if gap <= 5 and CONTINUATION_START_RE.match(cur.get("text_without_links") or "") and prev["char_len"] > 300:
        return True, "tight_followup"
    return False, ""


def build_threads(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    posts = sorted(posts, key=lambda p: p["post_id"])
    threads: list[list[dict[str, Any]]] = []
    reasons: list[list[str]] = []
    for post in posts:
        if post.get("is_empty"):
            threads.append([post])
            reasons.append([])
            continue
        if threads:
            ok, why = continues(threads[-1][-1], post)
            if ok:
                threads[-1].append(post)
                reasons[-1].append(why)
                continue
        threads.append([post])
        reasons.append([])

    out: list[dict[str, Any]] = []
    for members, why in zip(threads, reasons):
        head = members[0]
        text = "\n\n---\n\n".join(m["text_without_links"] for m in members if m["text_without_links"])
        out.append(
            {
                "thread_id": f"{head['channel']}/t{head['post_id']}",
                "channel": head["channel"],
                "post_ids": [m["post_id"] for m in members],
                "post_uids": [m["post_uid"] for m in members],
                "urls": [m["permanent_url"] for m in members],
                "size": len(members),
                "date_start": head["date"],
                "date_end": members[-1]["date"],
                "merge_reasons": sorted(set(why)),
                "text": text,
                "char_len": len(text),
                "token_estimate": sum(m["token_estimate"] for m in members),
                "views_max": max((m["views"] or 0) for m in members) or None,
                "reactions_total": sum((m["reactions_total"] or 0) for m in members) or None,
                "hashtags": sorted({h for m in members for h in m["hashtags"]}),
                "has_media": any(m["has_image"] or m["has_video"] or m["has_document"] for m in members),
                "is_forward": any(m["is_forward"] for m in members),
            }
        )
    return out


def build_threads_file(channel: str) -> Path:
    posts = load_jsonl(PROCESSED_DIR / f"{channel}.posts.jsonl")
    threads = build_threads(posts)
    out = PROCESSED_DIR / f"{channel}.threads.jsonl"
    write_jsonl(out, threads)
    merged = sum(1 for t in threads if t["size"] > 1)
    print(f"built {len(threads)} threads ({merged} multi-post) -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    args = ap.parse_args(argv)
    build_threads_file(args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
