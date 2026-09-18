"""Primary collector: the PUBLIC web preview of a Telegram channel (t.me/s/<channel>).

Why this is the default source (see README):
  * no account, no API credentials, no session file;
  * it only ever serves content the channel has made public;
  * it is stable HTML that degrades gracefully.

What we deliberately do NOT do: no CAPTCHA solving, no auth bypass, no
rate-limit evasion. We add our own delay between requests and we honour
Retry-After when Telegram asks us to slow down.

Limitation (documented, not worked around): the preview does not expose
reaction counts for every channel and sometimes truncates very old history.
`src/scraper/telethon_scraper.py` is the opt-in fallback for full history.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import RAW_DIR, SCRAPE, ScrapeConfig  # noqa: E402
from src.utils import load_jsonl, utcnow_iso, write_jsonl  # noqa: E402

POST_ID_RE = re.compile(r"^(?P<channel>[^/]+)/(?P<post_id>\d+)$")
BG_URL_RE = re.compile(r"background-image\s*:\s*url\(['\"]?(?P<url>[^'\")]+)['\"]?\)", re.I)
VIEWS_RE = re.compile(r"(?P<num>[\d.,]+)\s*(?P<suffix>[KMKМк]?)", re.I)


# --------------------------------------------------------------------- fetching

def build_session(cfg: ScrapeConfig) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru,en;q=0.8",
        }
    )
    return s


def fetch(session: requests.Session, url: str, cfg: ScrapeConfig) -> str:
    """GET with polite backoff. 429/5xx are retried; Retry-After is obeyed."""
    delay = cfg.delay_seconds
    last_error: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            resp = session.get(url, timeout=cfg.timeout_seconds)
        except requests.RequestException as exc:  # network flake
            last_error = exc
            time.sleep(min(60.0, delay * (2 ** attempt)))
            continue
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = float(resp.headers.get("Retry-After") or min(60.0, delay * (2 ** attempt)))
            print(f"  [http {resp.status_code}] backing off {wait:.1f}s -> {url}", file=sys.stderr)
            time.sleep(wait)
            last_error = RuntimeError(f"HTTP {resp.status_code}")
            continue
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    raise RuntimeError(f"giving up on {url}: {last_error}")


# ---------------------------------------------------------------------- parsing

def _text_with_newlines(node: Tag | None) -> str:
    """Telegram uses <br> for line breaks; BeautifulSoup's get_text eats them."""
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    return node.get_text("", strip=False)


def _parse_views(raw: str) -> int | None:
    """'12.3K' -> 12300. Returns None when the widget does not show views."""
    raw = (raw or "").strip()
    if not raw:
        return None
    m = VIEWS_RE.search(raw.replace(" ", ""))
    if not m:
        return None
    num = m.group("num").replace(",", ".")
    try:
        value = float(num)
    except ValueError:
        return None
    suffix = m.group("suffix").upper()
    if suffix in ("K", "К"):
        value *= 1_000
    elif suffix in ("M", "М"):
        value *= 1_000_000
    return int(value)


def _links_in_text(node: Tag | None) -> list[str]:
    """Outgoing links as authored (href), excluding hashtag/search links."""
    if node is None:
        return []
    out: list[str] = []
    for a in node.find_all("a", href=True):
        href = a["href"]
        if "?q=%23" in href or href.startswith("?q="):
            continue  # hashtag search link, not an outgoing link
        if href.startswith("/"):
            href = "https://t.me" + href
        if href not in out:
            out.append(href)
    return out


def parse_message(wrap: Tag, channel: str, cfg: ScrapeConfig) -> dict[str, Any] | None:
    msg = wrap.find("div", class_="tgme_widget_message")
    if msg is None or not msg.get("data-post"):
        return None
    m = POST_ID_RE.match(msg["data-post"].strip())
    if not m:
        return None
    post_id = int(m.group("post_id"))

    text_node = msg.find("div", class_=lambda c: bool(c) and "tgme_widget_message_text" in c)
    raw_text = _text_with_newlines(text_node)

    time_node = msg.find("time", datetime=True)
    date = time_node["datetime"] if time_node else None

    views_node = msg.find("span", class_="tgme_widget_message_views")
    views = _parse_views(views_node.get_text(strip=True) if views_node else "")

    # Reactions are not always rendered in the preview; parse them when they are.
    reactions: dict[str, int] = {}
    def _is_reaction(tag: Tag) -> bool:
        classes = tag.get("class") or []
        return "tgme_reaction" in classes  # exact token, not tgme_reaction_count

    for r in msg.find_all(_is_reaction):
        emoji_node = r.find(class_=lambda c: bool(c) and "emoji" in str(c))
        emoji = (emoji_node.get_text(strip=True) if emoji_node else r.get_text(strip=True))[:8]
        count_node = r.find(class_=lambda c: bool(c) and "count" in str(c))
        try:
            count = int(re.sub(r"\D", "", count_node.get_text() if count_node else "") or 0)
        except ValueError:
            count = 0
        if emoji:
            reactions[emoji] = reactions.get(emoji, 0) + count

    fwd_node = msg.find("a", class_="tgme_widget_message_forwarded_from_name")
    forwarded_from = fwd_node.get_text(strip=True) if fwd_node else None
    forwarded_from_url = fwd_node.get("href") if fwd_node else None

    reply_node = msg.find("a", class_=lambda c: bool(c) and "tgme_widget_message_reply" in c)
    reply_to_url = reply_node.get("href") if reply_node else None
    reply_to = None
    if reply_to_url:
        rm = re.search(r"/(\d+)(?:\?|$)", reply_to_url)
        if rm:
            reply_to = int(rm.group(1))

    photos = [
        m2.group("url")
        for a in msg.find_all(class_=lambda c: bool(c) and "tgme_widget_message_photo_wrap" in c)
        if (m2 := BG_URL_RE.search(a.get("style", "")))
    ]
    has_video = bool(
        msg.find(class_=lambda c: bool(c) and ("tgme_widget_message_video" in c or "tgme_widget_message_roundvideo" in c))
    )
    has_document = bool(msg.find(class_=lambda c: bool(c) and "tgme_widget_message_document" in c))
    has_poll = bool(msg.find(class_=lambda c: bool(c) and "tgme_widget_message_poll" in c))
    has_sticker = bool(msg.find(class_=lambda c: bool(c) and "tgme_widget_message_sticker" in c))

    preview = msg.find("a", class_=lambda c: bool(c) and "tgme_widget_message_link_preview" in c)
    link_preview = None
    if preview is not None:
        def _sub(cls: str) -> str:
            n = preview.find(class_=lambda c: bool(c) and cls in c)
            return n.get_text(" ", strip=True) if n else ""
        link_preview = {
            "url": preview.get("href"),
            "site": _sub("link_preview_site_name"),
            "title": _sub("link_preview_title"),
            "description": _sub("link_preview_description"),
        }

    return {
        "channel": channel,
        "post_id": post_id,
        "permanent_url": cfg.post_url(post_id),
        "date": date,
        "raw_text": raw_text,
        "text_html_links": _links_in_text(text_node),
        "views": views,
        "reactions": reactions or None,
        "forwarded_from": forwarded_from,
        "forwarded_from_url": forwarded_from_url,
        "reply_to": reply_to,
        "reply_to_url": reply_to_url,
        "has_image": bool(photos),
        "image_count": len(photos),
        "has_video": has_video,
        "has_document": has_document,
        "has_poll": has_poll,
        "has_sticker": has_sticker,
        "link_preview": link_preview,
        "source": "tg_web_preview",
        "scraped_at": utcnow_iso(),
    }


def parse_page(html: str, channel: str, cfg: ScrapeConfig) -> tuple[list[dict[str, Any]], int | None]:
    """Returns (posts_on_page, cursor_for_older_page)."""
    soup = BeautifulSoup(html, "lxml")
    posts: list[dict[str, Any]] = []
    for wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
        parsed = parse_message(wrap, channel, cfg)
        if parsed:
            posts.append(parsed)

    cursor: int | None = None
    more = soup.find("a", class_=lambda c: bool(c) and "tme_messages_more" in c)
    if more is not None and more.get("data-before"):
        try:
            cursor = int(more["data-before"])
        except ValueError:
            cursor = None
    if cursor is None and posts:
        cursor = min(p["post_id"] for p in posts)
    return posts, cursor


# ----------------------------------------------------------------------- driver

def iter_history(
    cfg: ScrapeConfig,
    max_posts: int | None = None,
    max_pages: int | None = None,
    stop_at_post_id: int | None = None,
    start_before: int | None = None,
    verbose: bool = True,
) -> Iterator[dict[str, Any]]:
    """Walk the channel backwards from the newest post to the oldest available."""
    session = build_session(cfg)
    cursor = start_before
    seen_cursors: set[int] = set()
    seen_ids: set[int] = set()
    pages = 0

    while True:
        url = cfg.preview_url if cursor is None else f"{cfg.preview_url}?before={cursor}"
        html = fetch(session, url, cfg)
        posts, next_cursor = parse_page(html, cfg.channel, cfg)
        pages += 1

        new_posts = [p for p in posts if p["post_id"] not in seen_ids]
        for p in sorted(new_posts, key=lambda x: -x["post_id"]):
            seen_ids.add(p["post_id"])
            yield p
            if max_posts is not None and len(seen_ids) >= max_posts:
                if verbose:
                    print(f"  reached --max-posts={max_posts}", file=sys.stderr)
                return

        if verbose:
            oldest = min((p["post_id"] for p in posts), default=None)
            print(
                f"  page {pages:>4}  cursor={cursor}  posts={len(posts)}  total={len(seen_ids)}  oldest={oldest}",
                file=sys.stderr,
            )

        if not posts:
            if verbose:
                print("  empty page -> end of available history", file=sys.stderr)
            return
        if stop_at_post_id is not None and min(p["post_id"] for p in posts) <= stop_at_post_id:
            if verbose:
                print(f"  reached --stop-at-post-id={stop_at_post_id}", file=sys.stderr)
            return
        if max_pages is not None and pages >= max_pages:
            if verbose:
                print(f"  reached --max-pages={max_pages}", file=sys.stderr)
            return
        if next_cursor is None or next_cursor in seen_cursors or next_cursor <= 1:
            if verbose:
                print("  no further cursor -> end of available history", file=sys.stderr)
            return
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        time.sleep(cfg.delay_seconds)


def raw_path(channel: str) -> Path:
    return RAW_DIR / f"{channel}.raw.jsonl"


def scrape(
    cfg: ScrapeConfig,
    max_posts: int | None = None,
    max_pages: int | None = None,
    resume: bool = True,
    verbose: bool = True,
) -> Path:
    """Scrape and merge into data/raw/<channel>.raw.jsonl (raw stays immutable-ish:
    we only ever add posts and refresh volatile fields like views)."""
    out = raw_path(cfg.channel)
    existing = {p["post_id"]: p for p in load_jsonl(out)} if resume else {}
    if verbose and existing:
        print(f"resuming: {len(existing)} posts already in {out.name}", file=sys.stderr)

    fetched = 0
    for post in iter_history(cfg, max_posts=max_posts, max_pages=max_pages, verbose=verbose):
        existing[post["post_id"]] = post
        fetched += 1

    rows = [existing[k] for k in sorted(existing)]
    write_jsonl(out, rows)
    if verbose:
        print(f"wrote {len(rows)} posts ({fetched} fetched this run) -> {out}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape the public web preview of a Telegram channel.")
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--max-posts", type=int, default=None, help="stop after N posts (MVP runs)")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--delay", type=float, default=SCRAPE.delay_seconds)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args(argv)

    cfg = ScrapeConfig(channel=args.channel, delay_seconds=args.delay)
    print(f"source: {cfg.preview_url}", file=sys.stderr)
    scrape(cfg, max_posts=args.max_posts, max_pages=args.max_pages, resume=not args.no_resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
