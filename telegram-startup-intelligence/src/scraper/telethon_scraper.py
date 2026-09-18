"""Optional fallback collector: the OFFICIAL Telegram API via Telethon.

Use this only when the web preview cannot reach the whole history, or when you
need reaction counts that the preview does not render.

Rules enforced here:
  * credentials come from TELEGRAM_API_ID / TELEGRAM_API_HASH only (never argv,
    never a config file that could be committed);
  * only the public channel's own messages are read - no participants, no
    comment threads, no private chats;
  * flood-wait is obeyed by Telethon itself; we do not try to outrun it.

Install with:  pip install telethon
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import RAW_DIR, SCRAPE  # noqa: E402
from src.utils import load_jsonl, utcnow_iso, write_jsonl  # noqa: E402

SESSION_NAME = os.environ.get("TELEGRAM_SESSION_NAME", "tsi_session")


def _message_to_record(msg: Any, channel: str) -> dict[str, Any] | None:
    if getattr(msg, "action", None) is not None:
        return None  # service message (pin, join, ...) - no content
    text = msg.message or ""
    reactions: dict[str, int] = {}
    if getattr(msg, "reactions", None) and getattr(msg.reactions, "results", None):
        for r in msg.reactions.results:
            emoticon = getattr(getattr(r, "reaction", None), "emoticon", None) or "custom"
            reactions[emoticon] = reactions.get(emoticon, 0) + int(r.count or 0)

    fwd = getattr(msg, "fwd_from", None)
    forwarded_from = None
    if fwd is not None:
        forwarded_from = getattr(fwd, "from_name", None) or str(getattr(fwd, "from_id", "") or "") or "unknown"

    media = msg.media
    cls = type(media).__name__ if media is not None else ""
    has_image = cls == "MessageMediaPhoto"
    has_video = False
    has_document = False
    if cls == "MessageMediaDocument":
        mime = getattr(getattr(media, "document", None), "mime_type", "") or ""
        has_video = mime.startswith("video/")
        has_image = has_image or mime.startswith("image/")
        has_document = not (has_video or mime.startswith("image/"))

    return {
        "channel": channel,
        "post_id": int(msg.id),
        "permanent_url": f"https://t.me/{channel}/{msg.id}",
        "date": msg.date.isoformat() if msg.date else None,
        "raw_text": text,
        "text_html_links": [
            e.url
            for e in (getattr(msg, "entities", None) or [])
            if getattr(e, "url", None)
        ],
        "views": int(msg.views) if getattr(msg, "views", None) else None,
        "reactions": reactions or None,
        "forwarded_from": forwarded_from,
        "forwarded_from_url": None,
        "reply_to": int(msg.reply_to.reply_to_msg_id) if getattr(msg, "reply_to", None) and getattr(msg.reply_to, "reply_to_msg_id", None) else None,
        "reply_to_url": None,
        "has_image": bool(has_image),
        "image_count": 1 if has_image else 0,
        "has_video": bool(has_video),
        "has_document": bool(has_document),
        "has_poll": cls == "MessageMediaPoll",
        "has_sticker": False,
        "link_preview": (
            {
                "url": getattr(getattr(media, "webpage", None), "url", None),
                "site": getattr(getattr(media, "webpage", None), "site_name", "") or "",
                "title": getattr(getattr(media, "webpage", None), "title", "") or "",
                "description": getattr(getattr(media, "webpage", None), "description", "") or "",
            }
            if cls == "MessageMediaWebPage"
            else None
        ),
        "grouped_id": int(msg.grouped_id) if getattr(msg, "grouped_id", None) else None,
        "source": "telethon",
        "scraped_at": utcnow_iso(),
    }


async def _run(channel: str, limit: int | None, resume: bool) -> Path:
    try:
        from telethon import TelegramClient
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("telethon is not installed. Run: pip install telethon") from exc

    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in the environment.\n"
            "Get them from https://my.telegram.org -> API development tools."
        )

    out = RAW_DIR / f"{channel}.raw.jsonl"
    existing = {p["post_id"]: p for p in load_jsonl(out)} if resume else {}

    async with TelegramClient(SESSION_NAME, int(api_id), api_hash) as client:
        n = 0
        async for msg in client.iter_messages(channel, limit=limit):
            rec = _message_to_record(msg, channel)
            if rec is None:
                continue
            existing[rec["post_id"]] = rec
            n += 1
            if n % 200 == 0:
                print(f"  {n} messages...", file=sys.stderr)

    rows = [existing[k] for k in sorted(existing)]
    write_jsonl(out, rows)
    print(f"wrote {len(rows)} posts -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape a public channel through the official Telegram API.")
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args(argv)
    asyncio.run(_run(args.channel, args.limit, not args.no_resume))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
