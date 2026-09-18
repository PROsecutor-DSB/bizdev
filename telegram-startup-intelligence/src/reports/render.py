"""Render every markdown report from the SQLite knowledge base.

The markdown files are *views*. The database is the source of truth. Regenerate
any time with `python -m src.reports.render`.

Two invariants hold in every file:
  * nothing appears without a clickable Telegram permalink behind it;
  * the author's position and our inference are visually separated, and any
    block produced by inference carries a DERIVED_HYPOTHESIS marker.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import OUTPUT_DIR, SCRAPE, TAXONOMY  # noqa: E402
from src.db import store  # noqa: E402
from src.utils import utcnow_iso  # noqa: E402

# Seed list from the brief, used only as a coverage checklist.
SEED_ANTI_PATTERNS = [
    "building before understanding demand", "ICP too wide", "generic customer interviews",
    "feature factory", "solution looking for a problem", "wrong segmentation",
    "demographics instead of Jobs", "vanity metrics", "premature scaling",
    "wrong RAT", "no distribution", "copying a competitor",
    "incremental feature competition", "building for everyone",
]


# ------------------------------------------------------------------ small helpers

def link(post_uid: str) -> str:
    channel, _, pid = (post_uid or "").partition("/")
    return f"[{post_uid}](https://t.me/{channel}/{pid})" if channel and pid else (post_uid or "?")


def links(post_uids: Iterable[str], limit: int = 8) -> str:
    uids = list(post_uids or [])
    shown = " · ".join(link(u) for u in uids[:limit])
    extra = f" _(+{len(uids)-limit} more)_" if len(uids) > limit else ""
    return (shown + extra) if shown else "_no source recorded_"


PIPE = "|"
ESCAPED_PIPE = "\\|"


def esc(text: str) -> str:
    """Escape a cell for a markdown table (f-strings cannot hold backslashes)."""
    return (text or "").replace(PIPE, ESCAPED_PIPE).replace("\n", " ")


def field(payload: dict[str, Any], key: str, default: str = "") -> str:
    v = payload.get(key)
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return (str(v).strip() if v is not None else "") or default


def evidence_badge(row: dict[str, Any]) -> str:
    et = row.get("evidence_type") or "AUTHOR_CLAIM"
    strength = row.get("evidence_strength") or 0
    warn = " ⚠️ _unsupported in the material_" if et in ("AUTHOR_CLAIM", "MARKETING_CLAIM") else ""
    return f"`{et}` (strength {strength}/5){warn}"


def header(title: str, subtitle: str, meta: dict[str, Any]) -> str:
    banner = ""
    engines = meta.get("engines") or []
    if engines and all(e.startswith("heuristic") or e == "deterministic-selection" for e in engines):
        banner = (
            "\n> ⚠️ **Generated with the offline heuristic engine, not an LLM.**\n"
            "> Mechanisms and syntheses are placeholders. Set `LLM_API_KEY` and re-run\n"
            "> `python run_pipeline.py --stage all` for real analysis.\n"
        )
    return (
        f"# {title}\n\n{subtitle}\n{banner}\n"
        f"<sub>Channel: `@{meta.get('channel')}` · "
        f"posts {meta.get('posts', 0)} · insights {meta.get('insights', 0)} · "
        f"generated {utcnow_iso()} · engines: {', '.join(sorted(set(engines))) or 'n/a'}</sub>\n\n"
        "---\n"
    )


def meta_of(conn: Any, channel: str) -> dict[str, Any]:
    engines = [r["engine"] for r in store.query(conn, "SELECT DISTINCT engine FROM insights") if r["engine"]]
    engines += [r["engine"] for r in store.query(conn, "SELECT DISTINCT engine FROM patterns") if r["engine"]]
    return {
        "channel": channel,
        "posts": store.count(conn, "posts"),
        "insights": store.count(conn, "insights"),
        "engines": engines,
    }


def _leverage(r: dict[str, Any]) -> int:
    return (
        r.get("transferability_score", 0) + r.get("actionability_score", 0)
        + r.get("novelty_score", 0) + r.get("evidence_strength", 0)
    )


# ------------------------------------------------------------------ CORE_INSIGHTS

def core_insights(conn: Any, channel: str, top: int = 150) -> str:
    rows = store.query(
        conn,
        "SELECT * FROM insights WHERE is_cluster_representative=1 ORDER BY date DESC",
    )
    rows.sort(key=lambda r: (-_leverage(r), r.get("date") or ""))
    rows = rows[:top]

    L = [
        header(
            "Core insights",
            "The highest-leverage extracted claims, one entry per idea (cluster representatives only). "
            "Ranked by transferability + actionability + novelty + evidence strength — **not** by views or reactions.",
            meta_of(conn, channel),
        )
    ]
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    L.append("\n## Contents\n")
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        L.append(f"- [{cat}](#{cat.lower().replace('_','-')}) — {len(by_cat[cat])}")
    L.append("")

    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        L.append(f"\n## {cat}\n")
        for r in by_cat[cat]:
            L.append(f"### {r['thesis']}\n")
            if r.get("mechanism"):
                L.append(f"**Mechanism.** {r['mechanism']}\n")
            else:
                reason = r.get("mechanism_missing_reason") or "not reconstructable from the post"
                L.append(f"**Mechanism.** _Not stated in the source ({reason})._\n")
            for label, key in (
                ("Why it matters", "why_it_matters"),
                ("Applies when", "problem_pattern"),
                ("The move", "solution_pattern"),
                ("Startup application", "startup_application"),
                ("Hackathon application", "hackathon_application"),
                ("Anti-pattern it warns against", "anti_pattern"),
                ("Example from the post", "example"),
            ):
                if r.get(key):
                    L.append(f"- **{label}:** {r[key]}")
            if r.get("quote"):
                L.append(f"\n> {r['quote']}\n")
            L.append(
                f"\n<sub>{evidence_badge(r)} · novelty {r['novelty_score']}/5 · "
                f"actionability {r['actionability_score']}/5 · transferability {r['transferability_score']}/5 · "
                f"hackathon {r['hackathon_value_score']}/5 · signal {r['content_signal_score']}/100</sub>"
            )
            L.append(f"\n<sub>Source: {links(r['source_posts'])} · {r.get('date','')[:10]} · `{r['insight_id']}`</sub>\n")
    return "\n".join(L)


# --------------------------------------------------------------- STARTUP_PATTERNS

def startup_patterns(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM patterns WHERE kind='CORE_PATTERN' ORDER BY support DESC")
    L = [
        header(
            "Startup pattern library",
            "Recurring mechanisms the channel returns to over years. Each entry collapses a whole cluster "
            "of posts into one pattern, with the supporting posts listed. "
            "`When it fails` is frequently our inference — it is marked where so.",
            meta_of(conn, channel),
        )
    ]
    if not rows:
        L.append("\n_No patterns synthesised yet. Run `python -m src.synthesis.patterns`._\n")
        return "\n".join(L)

    L.append("\n## Contents\n")
    for r in rows:
        L.append(f"- **{r['name']}** — {r['support']} supporting insights, {', '.join(r['tags'])}")
    for r in rows:
        p = r["payload"]
        L.append(f"\n---\n\n## {r['name']}\n")
        L.append(f"**Problem.** {field(p,'problem','—')}\n")
        L.append(f"**Observation.** {field(p,'observation','—')}\n")
        L.append(f"**Mechanism.** {field(p,'mechanism','—')}\n")
        L.append(f"**When it works.** {field(p,'when_it_works','—')}\n")
        L.append(f"**When it fails.** {field(p,'when_it_fails','—')}\n")
        L.append(f"**How to detect the opportunity.** {field(p,'how_to_detect_opportunity','—')}\n")
        L.append(f"**How to test it.** {field(p,'how_to_test','—')}\n")
        if field(p, "startup_example"):
            L.append(f"**Startup example.** {field(p,'startup_example')}\n")
        if field(p, "hackathon_example"):
            L.append(f"**Hackathon example.** {field(p,'hackathon_example')}\n")
        if field(p, "evolution"):
            L.append(f"**How the framing changed.** {field(p,'evolution')}\n")
        if field(p, "exceptions"):
            L.append(f"**Exceptions in the evidence.** {field(p,'exceptions')}\n")
        L.append(
            f"<sub>Support: {r['support']} insights · {(r['date_start'] or '')[:10]} → {(r['date_end'] or '')[:10]} · "
            f"strongest evidence `{field(p,'strongest_evidence_type','AUTHOR_CLAIM')}` · confidence {r['confidence']}/5</sub>\n"
        )
        L.append(f"<sub>Source posts: {links(r['source_posts'], 12)}</sub>\n")
    return "\n".join(L)


# ------------------------------------------------------------------ ANTI_PATTERNS

def anti_patterns(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM patterns WHERE kind='ANTI_PATTERN' ORDER BY support DESC")
    L = [
        header(
            "Anti-pattern library",
            "Mistakes the channel documents, with the reason they feel correct at the time — "
            "that is the part that makes an anti-pattern usable.",
            meta_of(conn, channel),
        )
    ]
    if not rows:
        L.append("\n_Nothing synthesised yet. Run `python -m src.synthesis.antipatterns`._\n")
        return "\n".join(L)

    for r in rows:
        p = r["payload"]
        L.append(f"\n---\n\n## {r['name']}\n")
        L.append(f"**What people do.** {field(p,'what_people_do','—')}\n")
        L.append(f"**Why it feels right.** {field(p,'why_it_feels_right','—')}\n")
        L.append(f"**Mechanism of failure.** {field(p,'mechanism_of_failure','—')}\n")
        warns = p.get("early_warning_signs") or []
        if warns:
            L.append("**Early warning signs.**\n")
            for w in warns:
                L.append(f"- {w}")
            L.append("")
        L.append(f"**Cost.** {field(p,'cost','—')}\n")
        L.append(f"**Correct move.** {field(p,'correct_move','—')}\n")
        if field(p, "hackathon_version"):
            L.append(f"**In a 48-hour build.** {field(p,'hackathon_version')}\n")
        L.append(f"<sub>Support: {r['support']} insights · confidence {r['confidence']}/5 · tags {', '.join(r['tags'])}</sub>\n")
        L.append(f"<sub>Source posts: {links(r['source_posts'], 12)}</sub>\n")

    # coverage check against the brief's seed list
    blob = " ".join((r["name"] + " " + str(r["payload"])).lower() for r in rows)
    missing = [s for s in SEED_ANTI_PATTERNS if not any(w in blob for w in s.lower().split() if len(w) > 4)]
    L.append("\n---\n\n## Coverage check against the standard failure list\n")
    L.append("The brief lists well-known failure modes. This is which of them the channel's own material covers.\n")
    L.append("| Known failure mode | Covered by extracted material |")
    L.append("|---|---|")
    for s in SEED_ANTI_PATTERNS:
        L.append(f"| {s} | {'no' if s in missing else 'yes'} |")
    L.append("\n_'no' means the channel does not discuss it in the collected posts — not that it is unimportant. "
             "Do not treat this table as the author's opinion._\n")
    return "\n".join(L)


# ------------------------------------------------------------- AJTBD_KNOWLEDGE_BASE

def ajtbd_kb(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM ajtbd_concepts ORDER BY concept, date")
    L = [
        header(
            "Advanced JTBD — reconstructed from the channel",
            "The author's **own** vocabulary, rebuilt from his own posts rather than from the textbook. "
            "Where his usage diverges from classic JTBD, the divergence is stated explicitly. "
            "Multiple observations of one concept are kept in date order so you can see the framing move.",
            meta_of(conn, channel),
        )
    ]
    if not rows:
        L.append("\n_Nothing extracted yet. Run `python -m src.extractor.ajtbd`._\n")
        return "\n".join(L)

    by_concept: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_concept.setdefault(r["concept"], []).append(r)

    L.append("\n## Concepts found in the material\n")
    for c in sorted(by_concept, key=lambda c: -len(by_concept[c])):
        L.append(f"- `{c}` — {len(by_concept[c])} observation(s)")
    L.append("")

    for c in sorted(by_concept, key=lambda c: -len(by_concept[c])):
        obs = by_concept[c]
        best = max(obs, key=lambda o: (o["confidence"], len(o["mechanism"] or "")))
        L.append(f"\n---\n\n## {c}" + (f" — «{best['label']}»" if best.get("label") else "") + "\n")
        L.append(f"**Definition (as the author uses it).** {best['definition']}\n")
        if best.get("mechanism"):
            L.append(f"**Mechanism.** {best['mechanism']}\n")
        if best.get("business_consequence"):
            L.append(f"**Business consequence.** {best['business_consequence']}\n")
        if best.get("how_to_detect"):
            L.append(f"**How to detect it.** {best['how_to_detect']}\n")
        if best.get("how_to_use"):
            L.append(f"**How to use it.** {best['how_to_use']}\n")
        if best.get("example"):
            L.append(f"**Example.** {best['example']}\n")
        if best.get("divergence_from_classic_jtbd"):
            L.append(f"**Diverges from classic JTBD.** {best['divergence_from_classic_jtbd']}\n")
        if best.get("quote"):
            L.append(f"> {best['quote']}\n")
        L.append(f"<sub>Primary source: {link(best['source_post_id'])} · {(best['date'] or '')[:10]} · confidence {best['confidence']}/5</sub>\n")
        if len(obs) > 1:
            L.append(f"\n**All {len(obs)} observations of this concept**\n")
            L.append("| Date | Source | Framing |")
            L.append("|---|---|---|")
            for o in obs:
                framing = esc(o["definition"])[:160]
                L.append(f"| {(o['date'] or '')[:10]} | {link(o['source_post_id'])} | {framing} |")
            L.append("")
    return "\n".join(L)


# --------------------------------------------------------- EVOLUTION_OF_THOUGHT

def evolution(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM derived WHERE kind='EVOLUTION' ORDER BY confidence DESC")
    changed = [r for r in rows if r["payload"].get("changed")]
    same = [r for r in rows if not r["payload"].get("changed")]
    contradictions = store.query(
        conn,
        """SELECT r.*, a.thesis AS a_thesis, a.date AS a_date, a.source_post_id AS a_post,
                  b.thesis AS b_thesis, b.date AS b_date, b.source_post_id AS b_post
           FROM relations r
           JOIN insights a ON a.insight_id = r.a_id
           JOIN insights b ON b.insight_id = r.b_id
           WHERE r.relation='CONTRADICTION' ORDER BY r.confidence DESC""",
    )

    L = [
        header(
            "Evolution of thought",
            "Where the author's position moved, and where it only got restated. "
            "**The latest opinion is not automatically the most useful one** — each entry says which version to use today.",
            meta_of(conn, channel),
        )
    ]
    L.append(f"\n{len(changed)} topics show a real change of position; {len(same)} were restatements only.\n")

    if not rows:
        L.append("\n_Nothing analysed yet. Run `python -m src.synthesis.evolution`._\n")

    for r in changed:
        p = r["payload"]
        L.append(f"\n---\n\n## {p.get('topic', r['title'])}\n")
        L.append(f"`{field(p,'change_type','REFINEMENT')}`\n")
        L.append("```")
        L.append(f"Old position         {field(p,'old_position','—')}")
        L.append("        ↓")
        L.append(f"Intermediate         {field(p,'intermediate_position','(none recorded)')}")
        L.append("        ↓")
        L.append(f"Current position     {field(p,'current_position','—')}")
        L.append("        ↓")
        L.append(f"Reason for change    {field(p,'reason_for_change','—')}")
        L.append("```\n")
        L.append(f"**What to take from it.** {field(p,'what_to_take_from_it','—')}\n")
        L.append(f"<sub>`{r['label']}` · confidence {r['confidence']}/5 · source posts: {links(r['source_posts'], 12)}</sub>\n")

    if same:
        L.append("\n---\n\n## Topics checked, no real change found\n")
        L.append("| Topic | Position | Sources |")
        L.append("|---|---|---|")
        for r in same:
            p = r["payload"]
            L.append(f"| {p.get('topic', r['title'])} | {esc(field(p,'current_position','—')[:180])} | {links(r['source_posts'], 3)} |")
        L.append("")

    if contradictions:
        L.append("\n---\n\n## Direct contradictions between individual insights\n")
        L.append("Pairs the deduplicator flagged as mutually incompatible. These are raw signals, not conclusions.\n")
        L.append("| Earlier | Later | Why they conflict |")
        L.append("|---|---|---|")
        for c in contradictions[:40]:
            a_first = (c["a_date"] or "") <= (c["b_date"] or "")
            first, second = ((c["a_thesis"], c["a_post"], c["a_date"]), (c["b_thesis"], c["b_post"], c["b_date"])) if a_first \
                else ((c["b_thesis"], c["b_post"], c["b_date"]), (c["a_thesis"], c["a_post"], c["a_date"]))
            L.append(
                f"| {esc(first[0][:130])}<br><sub>{(first[2] or '')[:10]} {link(first[1])}</sub> "
                f"| {esc(second[0][:130])}<br><sub>{(second[2] or '')[:10]} {link(second[1])}</sub> "
                f"| {esc((c['reasoning'] or '')[:160])} |"
            )
        L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------- HIDDEN_GEMS

def hidden_gems(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM derived WHERE kind='HIDDEN_GEM'")
    rows.sort(key=lambda r: r["payload"].get("rank", 999))
    L = [
        header(
            "Hidden gems",
            "Rarely-repeated, low-engagement observations that carry unusually high startup leverage. "
            "Selected deterministically: leverage × rarity × audience neglect. The components are printed so you can "
            "see why each one qualified.",
            meta_of(conn, channel),
        )
    ]
    if not rows:
        L.append("\n_Nothing selected yet. Run `python -m src.synthesis.hidden_gems`._\n")
        return "\n".join(L)
    for r in rows:
        p = r["payload"]
        L.append(f"\n---\n\n## {p['rank']}. {p['thesis']}\n")
        L.append(f"**Mechanism.** {p.get('mechanism') or '—'}\n")
        if p.get("why_it_matters"):
            L.append(f"**Why it matters.** {p['why_it_matters']}\n")
        if p.get("startup_application"):
            L.append(f"**Startup application.** {p['startup_application']}\n")
        if p.get("hackathon_application"):
            L.append(f"**Hackathon application.** {p['hackathon_application']}\n")
        L.append(
            f"<sub>Why it is a gem — leverage {p['leverage']}/20 · rarity {p['rarity']} · neglect {p['neglect']} · "
            f"cluster size {p['cluster_size']} · views {p.get('views') or 'n/a'} · reactions {p.get('reactions_total') or 'n/a'} · "
            f"`{p['evidence_type']}` · area {p['category']}</sub>\n"
        )
        L.append(f"<sub>Source: {links(r['source_posts'])}</sub>\n")
    return "\n".join(L)


# ---------------------------------------------------------------- OPPORTUNITY_MAP

def opportunity_map(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM derived WHERE kind='OPPORTUNITY' ORDER BY confidence DESC")
    tech = store.query(conn, "SELECT * FROM derived WHERE kind='TECH_JOB' ORDER BY confidence DESC")
    L = [
        header(
            "Opportunity map",
            "**Everything on this page is DERIVED_HYPOTHESIS.** The author described a structural problem; "
            "the opportunity is our inference from it. Do not attribute any of it to him. "
            "The source posts are linked so you can check what he actually said.",
            meta_of(conn, channel),
        )
    ]
    if rows:
        L.append("\n## Implied opportunities\n")
    for i, r in enumerate(rows, 1):
        p = r["payload"]
        L.append(f"\n---\n\n### {i}. {r['title']}  `DERIVED_HYPOTHESIS`\n")
        L.append(f"- **Observed problem:** {field(p,'observed_problem','—')}")
        L.append(f"- **Current workaround:** {field(p,'current_workaround','not stated in the source')}")
        L.append(f"- **Underlying Job:** {field(p,'underlying_job','—')}")
        L.append(f"- **Why the problem persists:** {field(p,'structural_reason_problem_exists','—')}")
        L.append(f"- **Technology that may change the economics:** {field(p,'technology_that_may_change_economics','—')}")
        L.append(f"- **Possible product primitive:** {field(p,'possible_product_primitive','—')}")
        L.append(f"- **Potential wedge:** {field(p,'potential_wedge','—')}")
        L.append(f"- **Potential ICP:** {field(p,'potential_icp','—')}")
        L.append(f"- **Fast validation test:** {field(p,'fast_validation_test','—')}")
        L.append(f"- **Why now:** {field(p,'why_now','—')}")
        L.append(f"\n<sub>Confidence {r['confidence']}/5 · tags {', '.join(r['tags'])} · source: {links(r['source_posts'])}</sub>\n")

    L.append("\n---\n\n## New technology × old Job\n")
    if not tech:
        L.append("\n_Nothing synthesised yet. Run `python -m src.synthesis.tech_job`._\n")
    for t in tech:
        p = t["payload"]
        L.append(f"\n### {field(p,'job','—')}  `DERIVED_HYPOTHESIS`\n")
        L.append(f"- **Old constraint:** {field(p,'old_constraint','—')}")
        L.append(f"- **Technology shift:** {field(p,'technology_shift','—')}")
        L.append(f"- **Consequence:** {field(p,'consequence','—')}")
        L.append(f"- **Who benefits first:** {field(p,'who_benefits_first','—')}")
        L.append(f"- **What to build in 48h:** {field(p,'what_to_build_in_48h','—')}")
        L.append(f"- **What would falsify it:** {field(p,'what_would_falsify_it','—')}")
        L.append(f"\n<sub>Confidence {t['confidence']}/5 · source: {links(t['source_posts'])}</sub>\n")
    return "\n".join(L)


# ---------------------------------------------------------------- IDEA_GENERATOR

SCORE_LABELS = {
    "job_frequency": "Job frequency", "pain": "Pain", "existing_spend": "Existing spend",
    "poor_existing_solution": "Poor existing solution", "technology_unlock": "Technology unlock",
    "demoability": "Demoability", "buildability_48h": "48h buildability",
    "distribution_accessibility": "Distribution accessibility", "evidence_strength": "Evidence strength",
}


def idea_generator(conn: Any, channel: str) -> str:
    rows = store.query(conn, "SELECT * FROM derived WHERE kind='IDEA'")
    rows.sort(key=lambda r: r["title"])
    L = [
        header(
            "Idea generator",
            "**All DERIVED_HYPOTHESIS.** Each idea traces to a Job, a structural problem and a technology unlock "
            "found in the channel — the source posts are linked. "
            "Scores are nine independent dimensions; **no combined score is computed and no idea is called best**, "
            "because the right choice depends on which dimension your situation cannot tolerate being low.",
            meta_of(conn, channel),
        )
    ]
    if not rows:
        L.append("\n_Nothing generated yet. Run `python -m src.synthesis.ideas`._\n")
        return "\n".join(L)

    L.append("\n## Trade-off table\n")
    L.append("| # | Idea | " + " | ".join(SCORE_LABELS[k][:14] for k in SCORE_LABELS) + " |")
    L.append("|---|---|" + "---|" * len(SCORE_LABELS))
    for i, r in enumerate(rows, 1):
        s = r["payload"].get("scores") or {}
        L.append(f"| {i} | {esc(r['title'][:70])} | " + " | ".join(str(s.get(k, "-")) for k in SCORE_LABELS) + " |")
    L.append("\n_Read the columns, not a total. An idea with 48h buildability 2 is wrong for a hackathon "
             "however good the rest looks; an idea with distribution accessibility 2 is wrong for a weekend launch._\n")

    for i, r in enumerate(rows, 1):
        p = r["payload"]
        L.append(f"\n---\n\n## {i}. {p.get('idea', r['title'])}  `DERIVED_HYPOTHESIS`\n")
        for label, key in (
            ("Target segment", "target_segment"), ("Job", "job"),
            ("Current solution", "current_solution"),
            ("Problem with the current solution", "problem_with_current_solution"),
            ("Technology unlock", "technology_unlock"), ("Product primitive", "product_primitive"),
            ("Wedge", "wedge"), ("Why now", "why_now"),
            ("Riskiest Assumption (RAT)", "rat"),
            ("24-hour validation", "validation_24h"), ("48-hour prototype", "prototype_48h"),
            ("First 10 users", "first_10_users"), ("Potential moat", "potential_moat"),
            ("Failure mode", "failure_mode"), ("3-minute demo", "demo_3min"),
            ("Trade-off", "tradeoffs"),
        ):
            if field(p, key):
                L.append(f"- **{label}:** {field(p,key)}")
        s = p.get("scores") or {}
        L.append("\n<sub>" + " · ".join(f"{SCORE_LABELS[k]} {s.get(k,'-')}/5" for k in SCORE_LABELS) + "</sub>\n")
        L.append(f"<sub>Insight source: {links(r['source_posts'])}</sub>\n")
    return "\n".join(L)


# -------------------------------------------------------------- HACKATHON_COMPASS

COMPASS_STAGES: list[tuple[str, str, list[str], list[str]]] = [
    ("Problem", "What real Job exists, and why is today's solution bad?",
     ["JOB", "PROBLEM", "NEED", "CUSTOMER", "BEHAVIOR"],
     ["What Job is actually being hired for here — stated as a Job, not a feature?",
      "How do these people get it done today, including with a spreadsheet, a person, or nothing?",
      "Why is the current solution bad — mechanically, not adjectivally?",
      "What is the trigger that starts the Job?",
      "What are their criteria of success? How will they know it worked?"]),
    ("Segment", "Who has this problem worse than everyone else?",
     ["SEGMENT", "CUSTOMER", "FOCUS"],
     ["Who feels this most acutely, and what makes them different from the average user?",
      "How often does the Job occur for them — daily, monthly, once a year?",
      "How painful is the current solution, in time or money they already spend?",
      "Can you find ten of them this week, by name of place or role?"]),
    ("Technology shift", "What became possible only recently?",
     ["AI", "AI_AGENTS", "VIBE_CODING", "AUTOMATION", "DISRUPTION"],
     ["What capability exists now that did not 18 months ago?",
      "Can the old Job now be done faster, cheaper, simpler, automatically, at higher quality, "
      "without an intermediary, or in fewer steps?",
      "Which of those is the one that actually changes the economics?",
      "What would falsify your belief that the constraint has moved?"]),
    ("Value", "What changes for the user — before → after?",
     ["VALUE", "VALUE_PROPOSITION", "PRODUCT"],
     ["Write it as Before → After, in the user's terms. Never as 'we use AI agents'.",
      "What did the Before cost them in time, money, or risk?",
      "Would they notice the difference without being told?"]),
    ("Wedge", "Which single narrow Job do you do dramatically better?",
     ["FOCUS", "STRATEGY", "COMPETITION", "DISRUPTION"],
     ["Which one Job can you be 10x on, rather than 10% on across five?",
      "What are you explicitly NOT doing in v1?",
      "What does winning that wedge give you access to next?"]),
    ("RAT", "Which assumption kills the idea if it is false?",
     ["RAT", "RISK", "EXPERIMENT"],
     ["List the assumptions. Which single one, if false, makes everything else irrelevant?",
      "Is it a demand assumption, a technical assumption, or a distribution assumption?",
      "What observation would falsify it? If you cannot state one, it is not a RAT."]),
    ("MVP", "How do you test the RAT in 24-48 hours?",
     ["MVP", "EXPERIMENT", "PRODUCT"],
     ["What is the cheapest artefact that produces a real signal — not a nicer opinion?",
      "Can the test run without building the product at all?",
      "What result would make you stop?"]),
    ("Distribution", "Where are the first 10 users?",
     ["DISTRIBUTION", "MARKETING", "GROWTH", "CONVERSION"],
     ["Name the specific place: a community, a Slack, a queue, a physical location.",
      "What is your reason to be there that is not 'we are launching a product'?",
      "What is the single message that would make one of them reply?"]),
    ("Demo", "What can you show in 3 minutes so value is obvious?",
     ["HACKATHON", "PRODUCT", "VALUE"],
     ["What is the one moment on stage where the audience gets it without explanation?",
      "Can you show the Before as well as the After?",
      "What are you cutting so the demo fits in three minutes?"]),
]


def hackathon_compass(conn: Any, channel: str) -> str:
    L = [
        header(
            "Hackathon compass",
            "A decision checklist for evaluating an idea, with the channel's own evidence attached to each stage. "
            "Work top to bottom. A stage you cannot answer is the stage to work on next — "
            "that is the point of the tool.",
            meta_of(conn, channel),
        )
    ]
    L.append("\n## How to use this\n")
    L.append("1. Write one sentence per question. If a sentence needs a hedge, mark the stage red.\n"
             "2. Stop at the first red stage and fix it before building anything.\n"
             "3. `python query.py \"<your idea>\" --critique` runs the same checklist against the knowledge base.\n")

    L.append("\n## Scorecard\n")
    L.append("| Stage | Question | Your answer | Red / amber / green |")
    L.append("|---|---|---|---|")
    for name, q, _, _ in COMPASS_STAGES:
        L.append(f"| {name} | {q} | | |")
    L.append("")

    for name, q, tags, questions in COMPASS_STAGES:
        L.append(f"\n---\n\n## {name} — {q}\n")
        for question in questions:
            L.append(f"- {question}")
        L.append("")

        placeholders = ",".join("?" for _ in tags)
        rows = store.query(
            conn,
            f"""SELECT DISTINCT i.* FROM insights i
                JOIN insight_tags t ON t.insight_id = i.insight_id
                WHERE t.tag IN ({placeholders}) AND i.is_cluster_representative=1
                  AND i.mechanism != ''
                ORDER BY (i.actionability_score + i.transferability_score + i.hackathon_value_score) DESC
                LIMIT 6""",
            tags,
        )
        if rows:
            L.append("**What the channel says about this stage**\n")
            for r in rows:
                L.append(f"- **{r['thesis']}**")
                if r.get("mechanism"):
                    L.append(f"  <br><sub>{r['mechanism'][:400]}</sub>")
                L.append(f"  <br><sub>{evidence_badge(r)} · {links(r['source_posts'], 4)}</sub>")
            L.append("")
        else:
            L.append("_No extracted insight in the base covers this stage yet. "
                     "Treat the questions above as the checklist and answer them from your own research._\n")

        antis = store.query(
            conn,
            f"""SELECT * FROM patterns WHERE kind='ANTI_PATTERN' AND (
                   {' OR '.join(["tags LIKE ?"] * len(tags))}
                ) LIMIT 3""",
            [f'%"{t}"%' for t in tags],
        )
        if antis:
            L.append("**Mistakes to avoid at this stage**\n")
            for a in antis:
                L.append(f"- **{a['name']}** — {field(a['payload'],'why_it_feels_right','')[:200]} "
                         f"<br><sub>{links(a['source_posts'], 3)}</sub>")
            L.append("")
    return "\n".join(L)


# -------------------------------------------------------------------- START_HERE

def start_here(conn: Any, channel: str) -> str:
    meta = meta_of(conn, channel)
    ins = store.query(conn, "SELECT * FROM insights WHERE is_cluster_representative=1")
    patterns = store.query(conn, "SELECT * FROM patterns WHERE kind='CORE_PATTERN' ORDER BY support DESC")
    antis = store.query(conn, "SELECT * FROM patterns WHERE kind='ANTI_PATTERN' ORDER BY support DESC")
    opps = store.query(conn, "SELECT * FROM derived WHERE kind='OPPORTUNITY' ORDER BY confidence DESC")
    ideas = store.query(conn, "SELECT * FROM derived WHERE kind='IDEA'")
    evo = store.query(conn, "SELECT * FROM derived WHERE kind='EVOLUTION'")
    dates = [r["date"] for r in store.query(conn, "SELECT date FROM posts WHERE date IS NOT NULL") if r["date"]]

    def top(tags: set[str], n: int, require_mechanism: bool = True) -> list[dict[str, Any]]:
        rows = [
            r for r in ins
            if (set(r["tags"]) & tags or r["category"] in tags)
            and (not require_mechanism or (r.get("mechanism") or "").strip())
        ]
        rows.sort(key=lambda r: -(r["actionability_score"] + r["transferability_score"] + r["novelty_score"]))
        return rows[:n]

    def bullet(r: dict[str, Any]) -> str:
        return f"1. **{r['thesis']}**\n   <br><sub>{(r.get('mechanism') or '')[:320]}</sub>\n   <br><sub>{evidence_badge(r)} · {links(r['source_posts'], 3)}</sub>"

    L = [
        header(
            "Start here",
            "The short version of everything in this repository. Read this page, then jump into the section you need. "
            "This is a decision aid, not a summary of the channel.",
            meta,
        )
    ]
    L.append(
        f"\nBuilt from **{meta['posts']} posts** "
        f"({(min(dates) if dates else '?')[:10]} → {(max(dates) if dates else '?')[:10]}), "
        f"**{meta['insights']} extracted insights**, {len(patterns)} core patterns, {len(antis)} anti-patterns, "
        f"{len(opps)} derived opportunities, {len(ideas)} generated ideas.\n"
    )
    L.append(
        "\n**How to read the labels.** `OBSERVATION` / `CASE_EVIDENCE` / `EMPIRICAL_EVIDENCE` mean the post shows "
        "something. `AUTHOR_CLAIM` and `MARKETING_CLAIM` mean the post asserts it without support — treat those as "
        "hypotheses, not facts. Anything marked `DERIVED_HYPOTHESIS` is **our** inference, not the author's position.\n"
    )
    L.append("\n## Map of this repository\n")
    for f, what in [
        ("CORE_INSIGHTS.md", "every high-leverage claim, grouped by area, with mechanisms and sources"),
        ("STARTUP_PATTERNS.md", "recurring mechanisms, with when-it-works / when-it-fails"),
        ("ANTI_PATTERNS.md", "documented mistakes and why they feel correct at the time"),
        ("AJTBD_KNOWLEDGE_BASE.md", "the author's own Jobs-To-Be-Done vocabulary, rebuilt from his posts"),
        ("HACKATHON_COMPASS.md", "the checklist to run an idea through, stage by stage"),
        ("OPPORTUNITY_MAP.md", "problems in the channel turned into opportunity hypotheses (derived)"),
        ("IDEA_GENERATOR.md", "concrete idea candidates with nine-dimension trade-offs (derived)"),
        ("HIDDEN_GEMS.md", "rare, low-engagement, high-leverage observations"),
        ("EVOLUTION_OF_THOUGHT.md", "where the author changed his mind, and which version to use"),
        ("DATASET_STATS.md", "what was collected, and what is missing"),
    ]:
        L.append(f"- [`{f}`]({f}) — {what}")
    L.append("")

    sections: list[tuple[str, str, set[str], int]] = [
        ("20 strongest principles", "The highest-leverage claims across all areas.", set(TAXONOMY), 20),
        ("How the author looks for value", "", {"VALUE", "VALUE_PROPOSITION", "JOB", "NEED"}, 8),
        ("How the author chooses a segment", "", {"SEGMENT", "FOCUS", "CUSTOMER"}, 8),
        ("How the author tests a product", "", {"EXPERIMENT", "RAT", "RISK", "MVP"}, 8),
        ("How the author thinks about strategy", "", {"STRATEGY", "DISRUPTION", "COMPETITION", "BUSINESS_MODEL"}, 8),
        ("What changed with AI", "", {"AI", "AI_AGENTS", "VIBE_CODING", "AUTOMATION"}, 8),
    ]
    for title, sub, tags, n in sections:
        rows = top(tags, n)
        L.append(f"\n---\n\n## {title}\n")
        if sub:
            L.append(sub + "\n")
        if not rows:
            L.append("_Nothing extracted in this area yet._\n")
        for r in rows:
            L.append(bullet(r))
        L.append("")

    L.append("\n---\n\n## 10 most important thinking models\n")
    if patterns:
        for p in patterns[:10]:
            L.append(f"1. **{p['name']}** — {field(p['payload'],'mechanism','')[:300]}\n"
                     f"   <br><sub>{p['support']} supporting insights · {links(p['source_posts'], 3)}</sub>")
    else:
        L.append("_Run `python -m src.synthesis.patterns`._")
    L.append("")

    L.append("\n---\n\n## 10 most interesting startup opportunities  `DERIVED_HYPOTHESIS`\n")
    if opps:
        for o in opps[:10]:
            p = o["payload"]
            L.append(f"1. **{o['title']}** — Job: {field(p,'underlying_job','')[:160]}. "
                     f"Wedge: {field(p,'potential_wedge','')[:160]}.\n"
                     f"   <br><sub>{links(o['source_posts'], 3)}</sub>")
    else:
        L.append("_Run `python -m src.synthesis.opportunities`._")
    L.append("")

    L.append("\n---\n\n## 10 rules for a hackathon team\n")
    hack = [r for r in ins if r["hackathon_value_score"] >= 4 and (r.get("hackathon_application") or "").strip()]
    hack.sort(key=lambda r: -(r["hackathon_value_score"] + r["actionability_score"]))
    if hack:
        for r in hack[:10]:
            L.append(f"1. **{r['thesis']}**\n   <br><sub>{r['hackathon_application'][:300]}</sub>"
                     f"\n   <br><sub>{links(r['source_posts'], 3)}</sub>")
    else:
        L.append("_No insight yet carries a hackathon application. See [`HACKATHON_COMPASS.md`](HACKATHON_COMPASS.md)._")
    L.append("")

    L.append("\n---\n\n## 10 things not to do\n")
    if antis:
        for a in antis[:10]:
            L.append(f"1. **{a['name']}** — {field(a['payload'],'mechanism_of_failure','')[:300]}\n"
                     f"   <br><sub>{links(a['source_posts'], 3)}</sub>")
    else:
        L.append("_Run `python -m src.synthesis.antipatterns`._")
    L.append("")

    changed = [r for r in evo if r["payload"].get("changed")]
    if changed:
        L.append("\n---\n\n## Where the author changed his mind\n")
        for r in changed[:6]:
            p = r["payload"]
            L.append(f"- **{p.get('topic')}** (`{field(p,'change_type','')}`): "
                     f"{field(p,'old_position','')[:120]} → {field(p,'current_position','')[:120]}. "
                     f"[Full entry](EVOLUTION_OF_THOUGHT.md)")
        L.append("")

    L.append("\n---\n\n## Ask the base a question\n")
    L.append("```bash\npython query.py                       # interactive\n"
             'python query.py "How does he choose a segment?"\n'
             'python query.py "My idea: an AI agent that negotiates purchases" --critique\n'
             "python query.py --tag RAT --limit 20\n```\n")
    return "\n".join(L)


# ------------------------------------------------------------------------- driver

RENDERERS = {
    "START_HERE.md": start_here,
    "CORE_INSIGHTS.md": core_insights,
    "AJTBD_KNOWLEDGE_BASE.md": ajtbd_kb,
    "STARTUP_PATTERNS.md": startup_patterns,
    "ANTI_PATTERNS.md": anti_patterns,
    "HACKATHON_COMPASS.md": hackathon_compass,
    "HIDDEN_GEMS.md": hidden_gems,
    "EVOLUTION_OF_THOUGHT.md": evolution,
    "OPPORTUNITY_MAP.md": opportunity_map,
    "IDEA_GENERATOR.md": idea_generator,
}


def run(channel: str = SCRAPE.channel, out_dir: Path = OUTPUT_DIR, only: list[str] | None = None) -> list[Path]:
    conn = store.connect()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, fn in RENDERERS.items():
        if only and name not in only:
            continue
        try:
            text = fn(conn, channel)
        except Exception as exc:
            print(f"  ! {name} failed: {exc}", file=sys.stderr)
            continue
        p = out_dir / name
        p.write_text(text.rstrip() + "\n", encoding="utf-8")
        written.append(p)
        print(f"  wrote {p.relative_to(p.parent.parent)} ({len(text):,} chars)", file=sys.stderr)
    conn.close()
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--out-dir", default=str(OUTPUT_DIR))
    args = ap.parse_args(argv)
    run(args.channel, Path(args.out_dir), args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
