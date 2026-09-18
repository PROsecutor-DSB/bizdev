"""Deterministic rule engine used when no LLM is configured.

It is intentionally simple and auditable. Everything it emits carries
engine="heuristic" upstream, and the reports print a banner saying so, because a
rule engine cannot reconstruct a causal mechanism - it can only recognise the
surface markers of one.

It is also genuinely useful on its own: the promo/content lexicons here drive the
cheap pre-filter that keeps LLM cost down on a multi-thousand-post channel.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

# ---------------------------------------------------------------- lexicons (ru/en)

PROMO_MARKERS = [
    "курс", "тренинг", "вебинар", "воркшоп", "интенсив", "мастер-класс", "мастеркласс",
    "записаться", "запишись", "регистрация", "регистрируйся", "оплатить", "оплата",
    "скидк", "промокод", "тариф", "рассрочк", "мест осталось", "осталось мест",
    "старт потока", "поток стартует", "набор на", "успей", "дедлайн записи",
    "по ссылке ниже", "ссылка в описании", "купить", "стоимость", "цена курса",
    "приходите на", "приглашаю на", "буду выступать", "анонс",
    "course", "webinar", "workshop", "enroll", "sign up", "register now",
    "discount", "promo code", "early bird", "seats left", "buy now",
]

HIRING_MARKERS = ["вакансия", "ищем", "мы нанимаем", "ищу в команду", "резюме", "hiring", "we are looking for", "job opening"]
ANNOUNCE_MARKERS = ["анонс", "напоминаю", "напоминание", "завтра в", "сегодня в", "начинаем через", "эфир", "стрим", "live в"]
PERSONAL_MARKERS = ["я переехал", "мой день", "личное", "отпуск", "день рождения", "поздравля", "спасибо всем", "рефлекси", "мои итоги года"]
NEWS_MARKERS = ["новость", "вышел", "выпустили", "релиз", "запустили", "объявил", "announced", "released", "launched"]
CASE_MARKERS = ["кейс", "мы сделали", "мы запустили", "в проекте", "клиент", "команда сделала", "эксперимент показал", "case study", "we ran", "results were"]
REPOST_MARKERS = ["репост", "делюсь постом", "из канала", "forwarded from"]

# Markers of transferable knowledge (section 4 of the brief).
MECHANISM_MARKERS = [
    "потому что", "поэтому", "из-за того что", "в результате", "следовательно",
    "механизм", "причина", "приводит к", "влияет на", "зависит от", "если .* то",
    "за счёт", "за счет", "таким образом", "это значит", "работает так",
    "because", "therefore", "as a result", "leads to", "mechanism", "which means",
]
FRAMEWORK_MARKERS = [
    "фреймворк", "модель", "схема", "алгоритм", "методология", "принцип", "критери",
    "правило", "шаг 1", "во-первых", "признак", "чеклист", "матрица",
    "framework", "model", "principle", "criteria", "checklist", "rule of thumb",
]
DOMAIN_MARKERS = [
    "jtbd", "job", "джоб", "сегмент", "гипотез", "rat", "mvp", "retention", "churn",
    "конверси", "unit", "юнит", "экономик", "ценност", "value", "ицп", "icp",
    "дистрибуц", "distribution", "growth", "рост", "продукт", "product",
    "disrupt", "подрыв", "стратег", "strategy", "customdev", "кастдев", "интервью",
    "метрик", "эксперимент", "прототип", "pmf", "pricing", "цена", "воронк", "funnel",
    "discovery", "клиент", "пользовател", "поведени", "wedge", "активац", "удержан",
    "монетизац", "конкурент", "альтернатив", "позиционир", "аудитор", "канал",
    "триггер", "контекст", "потребност", "боль", "спрос", "рынок", "оффер",
    "виральн", "referral", "реферал", "онбординг", "onboarding", "фич", "feature",
    "cac", "ltv", "команд", "фокус", "приоритет", "решени", "выборк", "сигнал",
]
ANTIPATTERN_MARKERS = [
    "ошибк", "не работает", "провал", "зря", "не делайте", "типичная", "ловушк",
    "заблужден", "миф", "плохая идея", "mistake", "fails", "anti-pattern", "trap", "myth",
]
EVIDENCE_MARKERS = [
    "мы измерили", "данные показывают", "в цифрах", "выборка", "n=", "процент",
    "исследование", "мы протестировали", "a/b", "аб-тест", "measured", "data shows", "we tested",
]
AI_MARKERS = [
    "ai", "ии", "llm", "gpt", "нейросет", "агент", "agent", "codex", "claude",
    "cursor", "vibe coding", "вайб", "автоматизац", "automation", "copilot",
]
LOW_SIGNAL_MARKERS = [
    "с новым годом", "с праздником", "поздравляю", "доброе утро", "хорошего дня",
    "верьте в себя", "просто начните", "всё получится", "мотивация", "happy new year",
]

TAXONOMY_LEXICON: dict[str, list[str]] = {
    "CUSTOMER": ["клиент", "пользовател", "customer", "user"],
    "JOB": ["job", "джоб", "jtbd", "работа которую", "задача клиента"],
    "SEGMENT": ["сегмент", "segment", "icp", "ицп", "аудитор"],
    "PROBLEM": ["проблем", "боль", "pain", "problem"],
    "NEED": ["потребност", "need"],
    "BEHAVIOR": ["поведени", "behavior", "привычк", "habit"],
    "VALUE": ["ценност", "value", "польз"],
    "VALUE_PROPOSITION": ["ценностное предложение", "value prop", "оффер", "offer"],
    "COMPETITION": ["конкурент", "competitor", "альтернатив", "competition"],
    "PRODUCT": ["продукт", "product", "фич", "feature"],
    "MVP": ["mvp", "прототип", "prototype", "минимальн"],
    "EXPERIMENT": ["эксперимент", "experiment", "тест", "a/b", "проверк"],
    "RISK": ["риск", "risk", "допущен", "assumption"],
    "RAT": ["rat", "riskiest", "самое рискован", "ключевое допущение"],
    "GROWTH": ["рост", "growth", "масштаб", "scal"],
    "RETENTION": ["retention", "удержан", "churn", "отток", "возвращ"],
    "CONVERSION": ["конверси", "conversion", "воронк", "funnel", "activation", "активац"],
    "DISTRIBUTION": ["дистрибуц", "distribution", "канал привлеч", "трафик", "acquisition"],
    "MARKETING": ["маркетинг", "marketing", "реклам", "позиционир", "positioning"],
    "PRICING": ["цена", "pricing", "прайс", "монетизац", "платят"],
    "UNIT_ECONOMICS": ["unit", "юнит", "ltv", "cac", "маржа", "margin", "economics", "экономик"],
    "STRATEGY": ["стратег", "strategy", "долгосроч", "ставк"],
    "FOCUS": ["фокус", "focus", "приоритет", "priorit", "отказать"],
    "DISRUPTION": ["disrupt", "подрыв", "новая категор", "category"],
    "BUSINESS_MODEL": ["бизнес-модел", "business model", "монетизац", "revenue"],
    "PRODUCT_MARKET_FIT": ["pmf", "product market fit", "product-market"],
    "ORGANIZATION": ["организац", "процесс", "org", "команда работает"],
    "TEAM": ["команд", "team", "найм", "founder", "основател"],
    "AI": ["ai", "ии", "llm", "gpt", "нейросет"],
    "AI_AGENTS": ["агент", "agent", "autonom"],
    "VIBE_CODING": ["vibe coding", "вайб", "cursor", "claude code", "codex"],
    "AUTOMATION": ["автоматиз", "automation", "скрипт", "workflow"],
    "STARTUP": ["стартап", "startup", "основател", "founder", "запуск"],
    "HACKATHON": ["хакатон", "hackathon", "48 часов", "за выходные"],
}


_MARKER_CACHE: dict[str, re.Pattern[str]] = {}


def _marker_re(marker: str) -> re.Pattern[str]:
    """Short alphanumeric markers ("ai", "ии", "mvp") need word boundaries,
    otherwise "демографии" counts as a mention of AI."""
    if marker not in _MARKER_CACHE:
        if len(marker) <= 4 and marker.replace("/", "").isalnum():
            pat = r"(?<![\w])" + re.escape(marker) + r"(?![\w])"
        else:
            pat = re.escape(marker)
        _MARKER_CACHE[marker] = re.compile(pat, re.IGNORECASE | re.UNICODE)
    return _MARKER_CACHE[marker]


def _hits(text: str, markers: list[str]) -> int:
    t = text.lower()
    return sum(1 for m in markers if _marker_re(m).search(t))


def _bullet_lines(text: str) -> int:
    return sum(1 for ln in text.split("\n") if re.match(r"^\s*(?:[-–—•*]|\d{1,2}[\.\)])\s+\S", ln))


# ------------------------------------------------------------------ public rules

def signal_features(text: str) -> dict[str, int]:
    return {
        "mechanism": _hits(text, MECHANISM_MARKERS),
        "framework": _hits(text, FRAMEWORK_MARKERS),
        "domain": _hits(text, DOMAIN_MARKERS),
        "antipattern": _hits(text, ANTIPATTERN_MARKERS),
        "evidence": _hits(text, EVIDENCE_MARKERS),
        "promo": _hits(text, PROMO_MARKERS),
        "hiring": _hits(text, HIRING_MARKERS),
        "announce": _hits(text, ANNOUNCE_MARKERS),
        "personal": _hits(text, PERSONAL_MARKERS),
        "news": _hits(text, NEWS_MARKERS),
        "case": _hits(text, CASE_MARKERS),
        "ai": _hits(text, AI_MARKERS),
        "low": _hits(text, LOW_SIGNAL_MARKERS),
        "bullets": _bullet_lines(text),
        "chars": len(text),
    }


def rule_signal_score(text: str) -> int:
    """0-100 content signal score from surface features only.

    Deliberately popularity-blind: views and reactions never enter this number
    (brief section 4). They are stored separately as a secondary signal.
    """
    f = signal_features(text)
    if f["chars"] < 80:
        return max(0, 8 + min(7, f["domain"] * 2))

    # Calibrated against tests/make_demo_corpus.py, whose labels are known.
    score = 16.0
    score += min(28, f["mechanism"] * 10)
    score += min(18, f["framework"] * 5)
    score += min(22, f["domain"] * 3.5)
    score += min(12, f["antipattern"] * 6)
    score += min(14, f["evidence"] * 7)
    score += min(10, f["case"] * 5)
    score += min(6, f["bullets"] * 1.5)
    score += min(10, math.log10(max(f["chars"], 100) / 100) * 11)

    # Promo is penalised on the promo density, not its mere presence: one
    # "register here" line at the end of a strong post should not zero it out.
    promo_density = f["promo"] / max(1.0, f["chars"] / 400.0)
    score -= min(38, promo_density * 16)
    score -= min(25, f["hiring"] * 15)
    score -= min(16, f["announce"] * 6)
    score -= min(22, f["low"] * 11)
    return int(max(0, min(100, round(score))))


def rule_category(text: str) -> str:
    f = signal_features(text)
    knowledge = f["mechanism"] + f["framework"] + f["domain"] + f["antipattern"]
    if f["hiring"] >= 1:
        return "HIRING"
    if f["promo"] >= 1:
        # The question is not "does it advertise" but "does anything survive the
        # advertisement". Judge the body that remains once the promo shell is cut.
        body, _removed = strip_promo_shell(text)
        body_knowledge = (
            _hits(body, MECHANISM_MARKERS)
            + _hits(body, FRAMEWORK_MARKERS)
            + _hits(body, DOMAIN_MARKERS)
            + _hits(body, ANTIPATTERN_MARKERS)
        )
        if body_knowledge >= 3 and len(body) >= 200:
            return "CONTENT_PLUS_PROMO"
    if f["promo"] >= 2:
        return "PROMO"
    if f["announce"] >= 2 and knowledge < 3:
        return "ANNOUNCEMENT"
    if f["case"] >= 2 and knowledge >= 2:
        return "CASE"
    if knowledge >= 4 or (knowledge >= 2 and f["chars"] >= 200 and f["mechanism"] >= 1):
        return "CONTENT"
    if f["personal"] >= 1 or (f["low"] >= 1 and knowledge < 2):
        return "PERSONAL"
    if f["news"] >= 2:
        return "NEWS"
    if f["chars"] < 60:
        return "OTHER"
    return "OTHER"


def rule_tags(text: str, limit: int = 6) -> list[str]:
    t = text.lower()
    scored = [(tag, sum(1 for m in ms if _marker_re(m).search(t))) for tag, ms in TAXONOMY_LEXICON.items()]
    scored = [(tag, n) for tag, n in scored if n > 0]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [tag for tag, _ in scored[:limit]] or ["PRODUCT"]


PROMO_SENTENCE_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in PROMO_MARKERS) + r")", re.IGNORECASE
)


def strip_promo_shell(text: str) -> tuple[str, list[str]]:
    """Drop promo paragraphs, keep the substantive ones (brief section 3)."""
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    kept, removed = [], []
    for b in blocks:
        promo_hits = len(PROMO_SENTENCE_RE.findall(b))
        knowledge = _hits(b, MECHANISM_MARKERS) + _hits(b, FRAMEWORK_MARKERS) + _hits(b, DOMAIN_MARKERS)
        if promo_hits >= 1 and knowledge <= promo_hits:
            removed.append(b)
        else:
            kept.append(b)
    if not kept:  # nothing survived - the post really is pure promo
        return "", blocks
    return "\n\n".join(kept), removed


# ------------------------------------------------------------- task dispatch

def _first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n]).strip()


def _heuristic_classify(text: str) -> dict[str, Any]:
    cat = rule_category(text)
    return {
        "category": cat,
        "content_signal_score": rule_signal_score(text),
        "tags": rule_tags(text),
        "reasoning": "rule-based surface markers (no LLM)",
        "promo_present": rule_category(text) in ("PROMO", "CONTENT_PLUS_PROMO"),
    }


CAUSAL_SENTENCE_RE = re.compile(
    r"(?:потому что|поэтому|из-за|в результате|следовательно|механизм|приводит к|"
    r"за счёт|за счет|таким образом|это значит|because|therefore|as a result|"
    r"leads to|mechanism|which means|если .{3,60} то)",
    re.IGNORECASE,
)


def extract_causal_sentences(text: str, limit: int = 4) -> str:
    """Pull the sentences that literally carry causal language.

    This is EXTRACTIVE, not generative: every word returned appears in the post.
    It is a weaker thing than a reconstructed WHY -> MECHANISM -> CONSEQUENCE
    chain, and the pipeline labels it as such - but it is honest, and it beats
    an empty field.
    """
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    picked = [s.strip() for s in sentences if s.strip() and CAUSAL_SENTENCE_RE.search(s)]
    return " ".join(picked[:limit])[:1200]


def _heuristic_extract(text: str) -> dict[str, Any]:
    """A rule engine cannot RECONSTRUCT a mechanism, but it can quote one."""
    score = rule_signal_score(text)
    if score < 45:
        return {"insights": []}
    f = signal_features(text)
    thesis = _first_sentences(text, 2)[:400]
    if not thesis:
        return {"insights": []}
    mechanism = extract_causal_sentences(text)
    return {
        "insights": [
            {
                "thesis": thesis,
                "mechanism": mechanism,
                "mechanism_missing_reason": (
                    "" if mechanism
                    else "heuristic engine found no causal language to quote; re-run with an LLM"
                ),
                "why_it_matters": "",
                "problem_pattern": "",
                "solution_pattern": "",
                "startup_application": "",
                "hackathon_application": "",
                "example": "",
                "anti_pattern": "",
                "category": rule_tags(text, 1)[0],
                "sub_category": "",
                "tags": rule_tags(text),
                "evidence_type": "CASE_EVIDENCE" if f["evidence"] else "AUTHOR_CLAIM",
                "evidence_strength": 2 if f["evidence"] else 1,
                "novelty_score": min(5, 1 + f["framework"]),
                "actionability_score": min(5, 1 + f["framework"] + f["mechanism"]),
                "why_it_matters_extractive": True,
                "transferability_score": min(5, 1 + f["domain"] // 2),
                "hackathon_value_score": min(5, 1 + f["ai"]),
                "keywords": rule_tags(text, 5),
                "quote": _first_sentences(text, 1)[:200],
            }
        ]
    }


def _heuristic_relation(user: str) -> dict[str, Any]:
    a, _, b = user.partition("---B---")
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return {"relation": "DUPLICATE", "confidence": 0.3, "reasoning": "heuristic"}
    jac = len(sa & sb) / max(1, len(sa | sb))
    rel = "DUPLICATE" if jac > 0.6 else ("REFINEMENT" if jac > 0.35 else "EXAMPLE")
    return {"relation": rel, "confidence": round(jac, 2), "reasoning": "jaccard overlap (no LLM)"}


_BLOCK_RE = re.compile(r"^(THESIS|MECHANISM|ANTI_PATTERN|PROBLEM_PATTERN|SOLUTION_PATTERN|EVIDENCE):\s*(.+)$", re.MULTILINE)


def _parse_packed(user: str) -> dict[str, list[str]]:
    """Read back the fields src/synthesis/common.py packed into the prompt."""
    out: dict[str, list[str]] = {}
    for key, value in _BLOCK_RE.findall(user):
        out.setdefault(key, []).append(value.strip())
    return out


def _heuristic_pattern(user: str) -> dict[str, Any]:
    """Extractive aggregation of a cluster: no new claims, only the members' own
    words plus the count. Reasoning fields are left empty on purpose."""
    parts = _parse_packed(user)
    theses, mechs = parts.get("THESIS", []), parts.get("MECHANISM", [])
    if not theses:
        return {}
    mechanism = max(mechs, key=len) if mechs else ""
    return {
        "pattern_name": theses[0][:90],
        "problem": parts.get("PROBLEM_PATTERN", [""])[0],
        "observation": theses[0],
        "mechanism": mechanism,
        "when_it_works": "",
        "when_it_fails": "",
        "how_to_detect_opportunity": "",
        "how_to_test": "",
        "startup_example": "",
        "hackathon_example": "",
        "evolution": "",
        "exceptions": "",
        "strongest_evidence_type": "AUTHOR_CLAIM",
        "confidence": 1,
        "tags": [],
        "_engine_note": "extractive aggregation by the heuristic engine; no reasoning applied",
    }


def _heuristic_antipattern(user: str) -> dict[str, Any]:
    parts = _parse_packed(user)
    antis = [a for a in parts.get("ANTI_PATTERN", []) if a]
    theses = parts.get("THESIS", [])
    if not antis and not theses:
        return {}
    name = (antis[0] if antis else theses[0])[:90]
    return {
        "anti_pattern_name": name,
        "what_people_do": antis[0] if antis else theses[0],
        "why_it_feels_right": "",
        "mechanism_of_failure": max(parts.get("MECHANISM", [""]), key=len),
        "early_warning_signs": [],
        "cost": "",
        "correct_move": parts.get("SOLUTION_PATTERN", [""])[0],
        "hackathon_version": "",
        "confidence": 1,
        "tags": [],
        "_engine_note": "extractive aggregation by the heuristic engine; no reasoning applied",
    }


def _heuristic_evolution(user: str) -> dict[str, Any]:
    """The heuristic engine never claims a change of position - deciding that a
    position REVERSED is a judgement, and a rule engine has no business making it."""
    parts = _parse_packed(user)
    theses = parts.get("THESIS", [])
    if not theses:
        return {}
    return {
        "changed": False,
        "topic": theses[0][:80],
        "old_position": theses[0],
        "intermediate_position": theses[len(theses) // 2] if len(theses) > 2 else "",
        "current_position": theses[-1],
        "reason_for_change": "",
        "change_type": "CONFIRMATION",
        "what_to_take_from_it": "",
        "confidence": 1,
    }


_PAYLOAD_RE = re.compile(r"<<<\s*(.*?)\s*>>>", re.DOTALL)


def payload_text(user: str) -> str:
    """The prompt builders wrap the post between <<< and >>>. The rule engine
    must score the POST, not the scaffolding around it."""
    m = _PAYLOAD_RE.search(user)
    return (m.group(1) if m else user).strip()


def dispatch(system: str, user: str) -> dict[str, Any]:
    s = system.lower()
    if "task: classify" in s:
        return _heuristic_classify(payload_text(user))
    if "task: extract_insights" in s:
        return _heuristic_extract(payload_text(user))
    if "task: relation" in s:
        return _heuristic_relation(user)
    if "task: ajtbd" in s:
        return {"concepts": []}
    if "task: synthesis" in s:
        if "anti_pattern_name" in system:
            return _heuristic_antipattern(user)
        if '"changed"' in system:
            return _heuristic_evolution(user)
        return _heuristic_pattern(user)
    if "task: opportunity" in s or "task: idea" in s or "task: answer" in s:
        # Inventing an opportunity, an idea, or a cited answer is exactly the kind
        # of fabrication the brief forbids. The rule engine declines.
        return {"items": [], "ideas": [],
                "note": "the heuristic engine does not generate opportunities, ideas or answers; configure an LLM"}
    return {}


# ------------------------------------------------------------------- embeddings

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def hash_embed(text: str, dim: int = 512) -> list[float]:
    """Deterministic hashed bag-of-features (word unigrams + char 4-grams).

    Not semantic like a trained embedding, but stable, offline and good enough to
    cluster near-identical restatements, which is what dedup needs first.
    """
    vec = [0.0] * dim
    t = (text or "").lower()
    tokens = _TOKEN_RE.findall(t)
    feats = list(tokens)
    feats += [f"__{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    squashed = " ".join(tokens)
    feats += [squashed[i : i + 4] for i in range(0, max(0, len(squashed) - 3))]
    for f in feats:
        h = int.from_bytes(hashlib.md5(f.encode("utf-8")).digest()[:8], "big")
        vec[h % dim] += 1.0 if h & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
