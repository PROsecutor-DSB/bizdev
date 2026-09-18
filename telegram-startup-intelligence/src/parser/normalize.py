"""Raw scrape records -> normalised, analysis-ready post records.

Deterministic. No LLM. Raw stays untouched in data/raw/; this writes
data/processed/<channel>.posts.jsonl.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import PROCESSED_DIR, RAW_DIR, SCRAPE  # noqa: E402
from src.utils import (  # noqa: E402
    clean_whitespace,
    extract_hashtags,
    extract_urls,
    load_jsonl,
    normalize_for_hash,
    post_uid,
    sha1,
    strip_links,
    token_count_estimate,
    write_jsonl,
)

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")


def guess_lang(text: str) -> str:
    cyr = len(CYRILLIC_RE.findall(text or ""))
    lat = len(LATIN_RE.findall(text or ""))
    if cyr == 0 and lat == 0:
        return "unknown"
    if cyr >= lat * 1.5:
        return "ru"
    if lat >= cyr * 1.5:
        return "en"
    return "mixed"


def parse_date(value: str | None) -> tuple[str | None, str | None]:
    """Returns (iso_utc, yyyy-mm)."""
    if not value:
        return None, None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat(), dt.strftime("%Y-%m")


def normalize_post(raw: dict[str, Any], channel: str) -> dict[str, Any]:
    raw_text = clean_whitespace(raw.get("raw_text") or "")
    text_without_links = strip_links(raw_text)

    # Outgoing links = URLs written in the text + hrefs of anchor tags.
    links: list[str] = []
    for u in extract_urls(raw_text) + list(raw.get("text_html_links") or []):
        if u not in links:
            links.append(u)
    preview = raw.get("link_preview") or {}
    if preview.get("url") and preview["url"] not in links:
        links.append(preview["url"])

    date_iso, month = parse_date(raw.get("date"))
    reactions = raw.get("reactions") or {}
    pid = raw["post_id"]

    return {
        "post_uid": post_uid(channel, pid),
        "channel": channel,
        "post_id": int(pid),
        "date": date_iso,
        "month": month,
        "year": int(date_iso[:4]) if date_iso else None,
        "permanent_url": raw.get("permanent_url") or f"https://t.me/{channel}/{pid}",
        "raw_text": raw_text,
        "text_without_links": text_without_links,
        "outgoing_links": links,
        "hashtags": extract_hashtags(raw_text),
        "views": raw.get("views"),
        "reactions": reactions or None,
        "reactions_total": sum(reactions.values()) if reactions else None,
        "has_image": bool(raw.get("has_image")),
        "has_video": bool(raw.get("has_video")),
        "has_document": bool(raw.get("has_document")),
        "has_poll": bool(raw.get("has_poll")),
        "has_sticker": bool(raw.get("has_sticker")),
        "is_forward": bool(raw.get("forwarded_from")),
        "forwarded_from": raw.get("forwarded_from"),
        "forwarded_from_url": raw.get("forwarded_from_url"),
        "reply_to": raw.get("reply_to"),
        "grouped_id": raw.get("grouped_id"),
        "link_preview": raw.get("link_preview"),
        "char_len": len(raw_text),
        "word_count": len(raw_text.split()),
        "token_estimate": token_count_estimate(raw_text),
        "lang": guess_lang(raw_text),
        "is_empty": len(text_without_links.strip()) == 0,
        # exact-duplicate detector (re-posted announcements)
        "content_hash": sha1(normalize_for_hash(text_without_links)),
        "source": raw.get("source"),
    }


def normalize_file(channel: str) -> Path:
    raw_file = RAW_DIR / f"{channel}.raw.jsonl"
    if not raw_file.exists():
        raise SystemExit(f"no raw data at {raw_file}. Run the scraper first.")
    rows = [normalize_post(r, channel) for r in load_jsonl(raw_file)]
    rows.sort(key=lambda r: r["post_id"])

    # mark exact duplicates (keep them all; flag the later ones)
    first_seen: dict[str, int] = {}
    for r in rows:
        if r["is_empty"]:
            r["duplicate_of"] = None
            continue
        h = r["content_hash"]
        if h in first_seen:
            r["duplicate_of"] = first_seen[h]
        else:
            first_seen[h] = r["post_id"]
            r["duplicate_of"] = None

    out = PROCESSED_DIR / f"{channel}.posts.jsonl"
    write_jsonl(out, rows)
    print(f"normalised {len(rows)} posts -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    args = ap.parse_args(argv)
    normalize_file(args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
