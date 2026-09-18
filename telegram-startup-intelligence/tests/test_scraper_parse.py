import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import ScrapeConfig
from src.scraper.tgweb import parse_page

FIXTURE = Path(__file__).parent / "fixtures" / "tgweb_page.html"


def test_parse_page():
    cfg = ScrapeConfig(channel="zamesin")
    posts, cursor = parse_page(FIXTURE.read_text(encoding="utf-8"), "zamesin", cfg)
    assert cursor == 4100
    assert [p["post_id"] for p in posts] == [4101, 4100]

    a = posts[0]
    assert a["permanent_url"] == "https://t.me/zamesin/4101"
    assert a["date"] == "2025-03-14T09:12:05+00:00"
    assert a["views"] == 12400
    assert a["reactions"] == {"🔥": 124, "👍": 37}
    assert a["reply_to"] == 4098
    assert a["has_image"] is True and a["image_count"] == 1
    assert "Сегментация по демографии не работает." in a["raw_text"]
    assert "\n" in a["raw_text"], "<br> must become a newline"
    assert a["text_html_links"] == ["https://zamesin.me/ajtbd"]
    assert a["forwarded_from"] is None

    b = posts[1]
    assert b["views"] == 8213
    assert b["forwarded_from"] == "Other Channel"
    assert b["has_document"] is True
    assert b["reactions"] is None
    print("scraper parse: OK")




def test_backward_pagination_walk(monkeypatch_target=None):
    """The backward walk must page until history runs out, without looping or
    re-yielding, and must respect --max-posts."""
    import src.scraper.tgweb as tgweb

    pages: dict[str | None, tuple[list[int], int | None]] = {
        None: ([120, 119, 118], 118),
        "118": ([117, 116, 115], 115),
        "115": ([114, 113], 113),
        "113": ([], None),          # end of available history
    }

    def fake_fetch(session, url, cfg):
        cursor = url.split("before=")[1] if "before=" in url else None
        ids, more = pages[cursor]
        rows = "".join(
            f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="zamesin/{i}">'
            f'<div class="tgme_widget_message_text js-message_text">пост {i}</div>'
            f'<a class="tgme_widget_message_date"><time datetime="2025-01-0{(i%9)+1}T10:00:00+00:00"></time></a>'
            f"</div></div>"
            for i in ids
        )
        more_link = f'<a class="tme_messages_more" data-before="{more}"></a>' if more else ""
        return f"<html><body>{rows}{more_link}</body></html>"

    original = tgweb.fetch
    tgweb.fetch = fake_fetch
    try:
        cfg = ScrapeConfig(channel="zamesin", delay_seconds=0.0)
        got = [p["post_id"] for p in tgweb.iter_history(cfg, verbose=False)]
        assert got == [120, 119, 118, 117, 116, 115, 114, 113], got
        assert len(set(got)) == len(got), "a post must never be yielded twice"

        capped = [p["post_id"] for p in tgweb.iter_history(cfg, max_posts=4, verbose=False)]
        assert capped == [120, 119, 118, 117], capped

        stopped = [p["post_id"] for p in tgweb.iter_history(cfg, stop_at_post_id=116, verbose=False)]
        assert stopped == [120, 119, 118, 117, 116, 115], stopped
    finally:
        tgweb.fetch = original
    print("pagination walk: OK")


def run_all() -> None:
    test_parse_page()
    test_backward_pagination_walk()


if __name__ == "__main__":
    run_all()
