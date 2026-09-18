"""Unit tests for the deterministic layer: ids, text handling, threads, chunking."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extractor.insights import chunk_text, clean_thesis  # noqa: E402
from src.llm.heuristic import (  # noqa: E402
    extract_causal_sentences, payload_text, rule_category, rule_signal_score, strip_promo_shell,
)
from src.llm.provider import parse_json_loose  # noqa: E402
from src.parser.normalize import guess_lang, normalize_post, parse_date  # noqa: E402
from src.parser.threads import build_threads  # noqa: E402
from src.utils import extract_hashtags, extract_urls, insight_id, strip_links  # noqa: E402


def test_ids_are_deterministic() -> None:
    a = insight_id("zamesin/1", "Фокус на одном сегменте")
    b = insight_id("zamesin/1", "фокус  на  одном   сегменте!")
    c = insight_id("zamesin/2", "Фокус на одном сегменте")
    assert a == b, "normalisation must make the id stable across whitespace/case/punctuation"
    assert a != c, "different source posts must get different ids"


def test_text_helpers() -> None:
    t = "Смотри https://zamesin.me/a?b=1) и #jtbd #продукт"
    assert extract_urls(t) == ["https://zamesin.me/a?b=1"], "trailing bracket must be trimmed"
    assert extract_hashtags(t) == ["#jtbd", "#продукт"]
    assert "https" not in strip_links(t)
    assert guess_lang("привет мир как дела") == "ru"
    assert guess_lang("hello world how are you") == "en"
    iso, month = parse_date("2025-03-14T09:12:05+00:00")
    assert month == "2025-03" and iso.endswith("+00:00")


def test_normalize_post() -> None:
    raw = {
        "post_id": 7, "date": "2024-01-02T10:00:00+00:00",
        "raw_text": "Первая строка\n\n\n\nВторая  строка http://x.dev #tag",
        "text_html_links": ["https://y.dev"], "views": 100, "reactions": {"🔥": 3},
        "has_image": True, "permanent_url": "https://t.me/c/7",
    }
    p = normalize_post(raw, "c")
    assert p["post_uid"] == "c/7"
    assert "\n\n\n" not in p["raw_text"], "3+ newlines must collapse"
    assert set(p["outgoing_links"]) == {"http://x.dev", "https://y.dev"}
    assert p["hashtags"] == ["#tag"]
    assert p["reactions_total"] == 3
    assert p["lang"] == "ru" and p["is_empty"] is False


def test_threads_merge_series_not_neighbours() -> None:
    def post(pid, minutes, text):
        return normalize_post(
            {"post_id": pid, "date": f"2024-01-01T10:{minutes:02d}:00+00:00", "raw_text": text,
             "permanent_url": f"https://t.me/c/{pid}"}, "c")

    posts = [
        post(1, 0, "Разберу как искать wedge. Тред:"),
        post(2, 4, "1/3. Первая часть длинного объяснения механизма переключения."),
        post(3, 8, "2/3. Вторая часть."),
        post(4, 50, "Совершенно другая тема про unit-экономику и маржинальность продукта."),
    ]
    threads = build_threads(posts)
    assert len(threads) == 2, f"expected 2 threads, got {len(threads)}"
    assert threads[0]["post_ids"] == [1, 2, 3]
    assert threads[1]["post_ids"] == [4]
    assert threads[0]["urls"] == ["https://t.me/c/1", "https://t.me/c/2", "https://t.me/c/3"], \
        "every member's permalink must be preserved"


def test_promo_shell_removal_keeps_substance() -> None:
    text = (
        "Критерий выбора сегмента: Job случается часто, текущее решение болит измеримо, "
        "и вы можете найти десять таких людей за неделю. Механизм: если вы не можете их "
        "найти для интервью, канала продаж просто не существует.\n\n"
        "Разбираю на курсе, старт потока 1 марта. Записаться по ссылке, скидка 20%."
    )
    kept, removed = strip_promo_shell(text)
    assert "Критерий выбора сегмента" in kept
    assert "скидка" not in kept.lower() and len(removed) == 1
    assert rule_category(text) == "CONTENT_PLUS_PROMO"


def test_scoring_ignores_popularity_and_punishes_noise() -> None:
    content = ("Retention это диагноз. Если пользователи не возвращаются, значит Job либо "
               "редкая, либо выполняется плохо, поэтому смотреть надо на частоту Job, "
               "а не на кривую удержания. Механизм оттока всегда в частоте Job клиента.")
    promo = "Приходите на вебинар завтра в 19:00! Регистрация по ссылке, скидка 20%."
    greeting = "С Новым годом, друзья! Всё получится."
    assert rule_signal_score(content) > 50
    assert rule_signal_score(promo) < 30
    assert rule_signal_score(greeting) < 25
    assert rule_category(promo) == "PROMO"
    assert rule_category(greeting) == "PERSONAL"


def test_causal_extraction_is_verbatim() -> None:
    src = "Фокус это арифметика. Ресурсы ограничены, поэтому продукт для двух сегментов проигрывает."
    got = extract_causal_sentences(src)
    assert got and got in src, "the extracted mechanism must be literal text from the post"


def test_payload_unwrapping() -> None:
    assert payload_text("POST DATE: x\n\nPOST TEXT:\n<<<\nреальный текст\n>>>") == "реальный текст"


def test_chunking_overlaps_and_covers() -> None:
    paragraphs = [f"Параграф номер {i} " + "слово " * 120 for i in range(12)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=600)
    assert len(chunks) > 1
    for i, p in enumerate(paragraphs):
        head = p[:30]
        assert any(head in c for c in chunks), f"paragraph {i} was dropped by chunking"


def test_clean_thesis() -> None:
    assert clean_thesis("Тезис\n\n---\n\n1/3. Продолжение") == "Тезис Продолжение"


def test_json_repair() -> None:
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Here you go: {"a": [1,2]} hope that helps') == {"a": [1, 2]}
    assert parse_json_loose("not json at all") == {}


def run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  {name}: OK")


if __name__ == "__main__":
    run_all()
