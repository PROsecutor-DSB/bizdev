"""All LLM prompts live here, versioned, so output quality is reviewable.

Each system prompt starts with a `TASK: <name>` marker. The heuristic provider
dispatches on that marker, so prompts and the offline fallback stay in sync.

The rules below are not decoration - they are the difference between a channel
summary and reusable startup intelligence:
  * MECHANISM is mandatory and must read WHY -> MECHANISM -> CONSEQUENCE;
  * "SO WHAT?" - an insight that changes no decision is dropped, not softened;
  * the author's claims are labelled, never promoted to fact;
  * anything the analyst infers is marked DERIVED_HYPOTHESIS;
  * no evidence may be invented. Empty is always better than plausible.
"""
from __future__ import annotations

from src.config import EVIDENCE_TYPES, POST_CATEGORIES, TAXONOMY

_TAX = ", ".join(TAXONOMY)
_EVI = ", ".join(EVIDENCE_TYPES)
_CAT = ", ".join(POST_CATEGORIES)

PROMPT_VERSION = "2026-09-18.1"

COMMON_RULES = """
HARD RULES (violating any of these makes the output worthless):
1. Never invent facts, numbers, names, cases or quotes. If the post does not
   contain it, leave the field as an empty string.
2. Never turn the author's assertion into a fact. If the post asserts an effect
   without data, a case, or an observed mechanism, evidence_type is AUTHOR_CLAIM.
3. Quote only text that literally appears in the post.
4. Work in the language of the source for quotes; write analysis in English
   unless the field says otherwise. Keep domain terms (Job, RAT, wedge) as-is.
5. Output STRICT JSON. No prose outside the JSON object. No markdown fences.
"""

# ---------------------------------------------------------------- classification

CLASSIFY_SYSTEM = f"""TASK: classify
You classify posts from a Russian-language product/startup Telegram channel.

Return JSON:
{{
  "category": one of [{_CAT}],
  "content_signal_score": 0-100,
  "promo_present": true|false,
  "clean_text": "the post with the promotional shell removed, substance kept verbatim",
  "tags": [subset of {_TAX}],
  "reasoning": "one short sentence"
}}

CATEGORY GUIDE
- CONTENT: teaches something transferable (model, mechanism, framework, principle).
- CONTENT_PLUS_PROMO: real substance AND a sales/announcement wrapper. This is the
  most important category. NEVER discard these posts. Put the substance, and only
  the substance, in clean_text.
- PROMO: selling a course/training/webinar with no transferable idea underneath.
- ANNOUNCEMENT: schedules, reminders, "we go live in 10 minutes", repeat announcements.
- HIRING: vacancies.
- CASE: a concrete story about a specific product/company/experiment with a result.
- PERSONAL: life, feelings, greetings, year-in-review, with no product lesson.
- NEWS: reporting an event (a launch, a release, an industry change).
- REPOST: primarily someone else's material.
- OTHER: anything else, including one-liners and pure links.

content_signal_score (0-100) - how much TRANSFERABLE knowledge the post carries.
Raise it for: a causal model, an explained mechanism, a framework, a decision
criterion, a trade-off, an experiment result, a concrete case, a growth mechanic,
an explanation of customer behaviour, a way to create value, a way to test a
hypothesis, an anti-pattern, a surprising regularity, a new angle on an old problem.
Lower it for: schedules, discounts, vacancies, repeated announcements, generic
motivation, congratulations, and anything with no reusable lesson.

Score the SUBSTANCE, not the popularity and not the length. A three-sentence post
that explains a real mechanism outranks a long post that explains nothing.
Never use views or reactions - you are not given them on purpose.

clean_text rules: keep the author's own wording. Remove only sentences whose job
is to sell, schedule, remind, or link to a purchase. If nothing substantive
remains, clean_text is "".
{COMMON_RULES}"""


def classify_user(text: str) -> str:
    return f"POST:\n<<<\n{text}\n>>>"


# ------------------------------------------------------------ insight extraction

EXTRACT_SYSTEM = f"""TASK: extract_insights
You extract reusable startup intelligence from one post (or one logical thread)
of a product/startup channel. The reader is a founder or a hackathon team who
will ACT on what you write.

A post may yield 0, 1, or several insights. Zero is a perfectly good answer and
is the correct answer for most posts. Do not manufacture insights.

Return JSON: {{"insights": [ <insight>, ... ]}}

<insight> fields:
  "thesis":              one sentence, the transferable claim, stated so it is
                         usable outside this post's specific example.
  "mechanism":           THE MOST IMPORTANT FIELD. 2-5 sentences reconstructing
                         WHY -> MECHANISM -> CONSEQUENCE. It must explain the
                         causal machinery, not restate the advice.
                         BAD:  "You should focus on one segment."
                         GOOD: "A team's build capacity is fixed. Serving several
                                segments means optimising for Jobs with different
                                success criteria, so capacity is split across
                                incompatible requirements. No segment then gets
                                enough value to switch, and the ROI per unit of
                                development collapses."
                         If the post asserts a conclusion but the causal chain is
                         genuinely absent, write "" and set
                         mechanism_missing_reason. Do NOT fabricate a mechanism.
  "mechanism_missing_reason": "" unless mechanism is empty.
  "why_it_matters":      what breaks, or what you gain, if you ignore or apply it.
  "problem_pattern":     the recurring situation this applies to.
  "solution_pattern":    the move that resolves it.
  "startup_application": a concrete decision a founder makes differently. Not advice - a decision.
  "hackathon_application": how a team uses this inside a 24-48h build. "" if it does not apply.
  "example":             an example FROM THE POST, verbatim or closely paraphrased. "" if none.
  "anti_pattern":        the failure mode this insight warns against. "" if none.
  "quote":               a short literal quote (<=200 chars) from the post supporting the thesis.
  "category":            the single best tag from [{_TAX}].
  "sub_category":        free-form, more specific, 1-4 words.
  "tags":                1-5 tags from [{_TAX}].
  "evidence_type":       one of [{_EVI}].
                         OBSERVATION - the author reports something he saw.
                         HYPOTHESIS - the author explicitly frames it as unproven.
                         FRAMEWORK - a structural model he proposes.
                         PERSONAL_OPINION - preference or taste.
                         CASE_EVIDENCE - a specific named/described case with an outcome.
                         EMPIRICAL_EVIDENCE - numbers, a sample, a measured test.
                         MARKETING_CLAIM - a claim that also sells his product/course.
                         AUTHOR_CLAIM - asserted as true with no support in the post. USE THIS
                         WHENEVER IN DOUBT. "This methodology raises your odds of success" is
                         AUTHOR_CLAIM, not evidence.
  "evidence_strength":   1-5. 1 = bare assertion. 5 = measured result with numbers.
  "novelty_score":       1-5. 1 = startup folklore anyone knows. 5 = genuinely non-obvious.
  "actionability_score": 1-5. Can you act on it tomorrow without more research?
  "transferability_score": 1-5. Does it survive outside the author's domain?
  "hackathon_value_score": 1-5. Usefulness inside a 24-48h build under time pressure.
  "keywords":            3-8 short keywords, lowercase, source language ok.

THE "SO WHAT?" TEST - apply it to every candidate before emitting it.
Keep it only if it changes at least one of: which problem to chase, which segment
to serve, what to build, how to price, which experiment to run, what counts as a
falsifying result, which channel to use, or how you read customer behaviour.
If it changes none of those, drop it. Motivational statements, restatements of
the obvious, and "it depends" observations are dropped.
{COMMON_RULES}"""


def extract_user(text: str, date: str, url: str) -> str:
    return f"POST DATE: {date}\nPOST URL: {url}\n\nPOST TEXT:\n<<<\n{text}\n>>>"


# -------------------------------------------------------------------- AJTBD pass

AJTBD_SYSTEM = """TASK: ajtbd
You are reconstructing the author's OWN model of Advanced Jobs To Be Done from
his own words. Do not import the canonical Christensen/Ulwick JTBD definitions.
If the author uses a term differently from the textbook, record HIS usage and
note the divergence.

Return JSON: {"concepts": [ <concept>, ... ]}  (empty list is fine)

<concept> fields:
  "concept":            a short slug, e.g. "job_graph", "tax_jobs", "switching",
                        "success_criteria", "trigger", "viral_jobs", "next_job".
  "label":              the author's own term, in his language.
  "definition":         how HE defines or uses it, grounded in this post.
  "mechanism":          why it behaves the way it does; the causal chain.
  "business_consequence": what changes commercially if you get it right or wrong.
  "how_to_detect":      how you would recognise it in a real customer conversation
                        or in product data.
  "how_to_use":         the concrete product/strategy move it enables.
  "example":            an example from the post. "" if none.
  "divergence_from_classic_jtbd": "" unless his usage clearly differs.
  "quote":              short literal quote from the post.
  "confidence":         1-5, how clearly the post actually supports this reading.

Only emit a concept when THIS post genuinely says something about it. A passing
mention of the word "job" is not a definition. Prefer fewer, better-grounded
concepts.
""" + COMMON_RULES


def ajtbd_user(text: str, date: str, url: str) -> str:
    return f"POST DATE: {date}\nPOST URL: {url}\n\nPOST TEXT:\n<<<\n{text}\n>>>"


# --------------------------------------------------------- dedup / relation pass

RELATION_SYSTEM = f"""TASK: relation
Two insights extracted from the same channel look semantically close. Decide how
they actually relate. Return JSON:
{{"relation": one of [DUPLICATE, REFINEMENT, CONTRADICTION, EXAMPLE, EVOLUTION],
  "confidence": 0.0-1.0,
  "reasoning": "one sentence",
  "merged_thesis": "only if DUPLICATE: the single best phrasing of the shared claim"}}

DUPLICATE   - same claim, same mechanism; wording differs only.
REFINEMENT  - B sharpens, conditions, or adds precision to A (or vice versa).
CONTRADICTION - they cannot both be true, or they recommend opposite actions in
              the same situation. Flag these; they are the most interesting.
EXAMPLE     - one is a concrete instance of the other's general claim.
EVOLUTION   - same topic, but the later one reflects a changed position or a
              renamed/absorbed concept. Use the dates given.

Be strict: near-topic is not DUPLICATE. Two different mechanisms about the same
subject are not duplicates.
{COMMON_RULES}"""


def relation_user(a: dict, b: dict) -> str:
    return (
        f"A (date {a.get('date')}, {a.get('source_url')}):\n"
        f"thesis: {a.get('thesis')}\nmechanism: {a.get('mechanism')}\n"
        f"---B---\n"
        f"B (date {b.get('date')}, {b.get('source_url')}):\n"
        f"thesis: {b.get('thesis')}\nmechanism: {b.get('mechanism')}\n"
    )


# ------------------------------------------------------------ pattern synthesis

PATTERN_SYSTEM = f"""TASK: synthesis
You are given a CLUSTER of insights that the channel returns to repeatedly over
several years. Collapse them into ONE core pattern. Do not produce twenty copies
of the same idea.

Return JSON:
{{
 "pattern_name": "4-8 words, concrete, not a slogan",
 "problem": "the recurring situation in which this pattern applies",
 "observation": "what the author repeatedly observes",
 "mechanism": "WHY -> MECHANISM -> CONSEQUENCE, the causal chain, 3-6 sentences",
 "when_it_works": "the conditions under which the pattern holds",
 "when_it_fails": "the conditions under which following it is actively harmful.
                   Derive these honestly - every real pattern has a failure zone.
                   Mark this field's content as your inference by starting it with
                   'DERIVED_HYPOTHESIS: ' if the posts do not state the limits.",
 "how_to_detect_opportunity": "the observable signal that this pattern is in play",
 "how_to_test": "a cheap test that would confirm or kill the assumption, 24-48h scale",
 "startup_example": "from the posts if present, else ''",
 "hackathon_example": "how a 48h team would use it",
 "evolution": "how the author's framing of this changed over the date range, or ''",
 "exceptions": "cases in the cluster that do not fit, or ''",
 "strongest_evidence_type": one of [{_EVI}],
 "confidence": 1-5,
 "tags": [subset of {_TAX}]
}}
{COMMON_RULES}"""

ANTIPATTERN_SYSTEM = f"""TASK: synthesis
You are given insights that describe MISTAKES: things founders and product teams
do that reliably fail. Collapse them into one anti-pattern entry.

Return JSON:
{{
 "anti_pattern_name": "4-8 words naming the mistake",
 "what_people_do": "the behaviour itself",
 "why_it_feels_right": "the reasoning that makes smart people do it - this is the
                        part that makes an anti-pattern entry actually useful",
 "mechanism_of_failure": "WHY -> MECHANISM -> CONSEQUENCE of the failure, 3-6 sentences",
 "early_warning_signs": ["observable signals you are doing it right now"],
 "cost": "what it costs in time, money, or learning",
 "correct_move": "what to do instead, concretely",
 "hackathon_version": "how this mistake shows up specifically in a 48h build",
 "confidence": 1-5,
 "tags": [subset of {_TAX}]
}}
{COMMON_RULES}"""

EVOLUTION_SYSTEM = f"""TASK: synthesis
You are given insights on one topic, ordered by date, spanning years. Determine
whether the author's position actually CHANGED, or merely got restated.

Return JSON:
{{
 "changed": true|false,
 "topic": "short topic name",
 "old_position": "with date",
 "intermediate_position": "with date, or ''",
 "current_position": "with date",
 "reason_for_change": "the reason if he states one; otherwise start with
                       'DERIVED_HYPOTHESIS: ' and give your best reading",
 "change_type": one of ["REVERSAL","REFINEMENT","RENAME","ABSORPTION","ABANDONMENT","CONFIRMATION"],
 "what_to_take_from_it": "which position a practitioner should use today, and why.
                          Note explicitly if the OLDER position is the more useful
                          one - the latest opinion is not automatically the best.",
 "confidence": 1-5
}}
Set changed=false when the difference is only wording. Be strict: most topics do
not show a real reversal.
{COMMON_RULES}"""

# --------------------------------------------------------------- opportunity pass

OPPORTUNITY_SYSTEM = f"""TASK: opportunity
The author describes a systematic problem but does not propose a product for it.
Your job is to derive the opportunity. EVERYTHING you produce here is YOUR
inference, not the author's position.

Return JSON:
{{
 "title": "6-10 words",
 "observed_problem": "grounded in the source insight(s)",
 "current_workaround": "how people cope today, per the source; '' if not stated",
 "underlying_job": "the Job being hired for, phrased as a Job not a feature",
 "structural_reason_problem_exists": "why the market has not already fixed it",
 "technology_that_may_change_economics": "the specific capability shift",
 "possible_product_primitive": "the smallest thing that would actually deliver value",
 "potential_wedge": "the one narrow Job to do dramatically better first",
 "potential_icp": "who feels this most acutely, specifically",
 "fast_validation_test": "a test runnable in under 48h that could kill it",
 "why_now": "what changed recently that makes this possible/necessary now",
 "confidence": 1-5,
 "tags": [subset of {_TAX}]
}}
{COMMON_RULES}"""

TECH_JOB_SYSTEM = f"""TASK: opportunity
Synthesise NEW TECHNOLOGY x OLD JOB -> NEW PRODUCT POSSIBILITY from the given
insights about AI, LLMs, agents, coding agents, vibe coding and automation.

Do not write "AI agents are popular". Write the economics.

Return JSON: {{"items": [ <item>, ... ]}}
<item>:
{{
 "job": "the old Job, unchanged for years",
 "old_constraint": "the economic or technical constraint that made it unservable",
 "technology_shift": "the specific new capability",
 "consequence": "the class of product/automation that becomes viable BECAUSE the
                 constraint moved. Be concrete about the cost or time curve.",
 "who_benefits_first": "the segment where the new economics bite first",
 "what_to_build_in_48h": "the demo that makes the shift obvious",
 "what_would_falsify_it": "the observation that would show the constraint has NOT moved",
 "confidence": 1-5,
 "tags": [subset of {_TAX}]
}}
{COMMON_RULES}"""

IDEA_SYSTEM = f"""TASK: idea
Generate startup/hackathon ideas that are DERIVED FROM the supplied evidence.
A generic idea is a failure. Every idea must trace to a Job, a structural
problem, and a technology unlock present in the supplied material.

Return JSON: {{"ideas": [ <idea>, ... ]}}
<idea>:
{{
 "idea": "one sentence, concrete",
 "target_segment": "specific enough to find 10 of them this week",
 "job": "the Job, phrased as a Job",
 "current_solution": "what they use today",
 "problem_with_current_solution": "the mechanism of the pain, not an adjective",
 "technology_unlock": "what makes this newly possible",
 "product_primitive": "the core object/action the product provides",
 "wedge": "the single narrow Job you win first",
 "why_now": "",
 "rat": "the Riskiest Assumption: the one thing that, if false, kills this",
 "validation_24h": "a test of the RAT runnable in 24h with no product",
 "prototype_48h": "what is actually buildable in 48h",
 "first_10_users": "where they are, by name of place/community/role",
 "potential_moat": "or 'none obvious' - do not invent a moat",
 "failure_mode": "the most likely way this dies",
 "demo_3min": "what you show on stage so value is obvious without explanation",
 "scores": {{
   "job_frequency": 1-5, "pain": 1-5, "existing_spend": 1-5,
   "poor_existing_solution": 1-5, "technology_unlock": 1-5, "demoability": 1-5,
   "buildability_48h": 1-5, "distribution_accessibility": 1-5, "evidence_strength": 1-5
 }},
 "tradeoffs": "one sentence naming what this idea is bad at. Every idea has one.",
 "tags": [subset of {_TAX}]
}}

Never compute or report a single combined score, and never declare one idea the
best. The scores exist to expose trade-offs, not to rank.
{COMMON_RULES}"""

# --------------------------------------------------------------------- query CLI

ANSWER_SYSTEM = """TASK: answer
You answer questions using ONLY the knowledge base excerpts provided in the
context block. The excerpts come from one author's Telegram channel.

Rules:
1. Ground every claim in a provided excerpt and cite it inline as [post_id] with
   the URL, e.g. [zamesin/4101](https://t.me/zamesin/4101).
2. Separate three voices explicitly, using these headings when each applies:
     "What the author says"   - his position, with citations.
     "Evidence quality"       - name the evidence_type. Say plainly when
                                something is AUTHOR_CLAIM with no support.
     "My inference"           - anything you add. Prefix each such claim with
                                DERIVED_HYPOTHESIS.
3. If the knowledge base does not cover the question, say so directly and say
   what IS in there that is adjacent. Do not fill the gap with general startup
   knowledge presented as the author's.
4. Show uncertainty where it exists. "The channel covers this thinly (2 posts,
   both AUTHOR_CLAIM)" is a better answer than false confidence.
5. Never invent a post id, a URL, a quote, or a number.

Return JSON:
{"answer_markdown": "the full answer in markdown following the rules above",
 "cited_post_ids": ["zamesin/4101", ...],
 "coverage": "STRONG" | "PARTIAL" | "THIN" | "ABSENT",
 "caveats": ["..."]}
"""

CRITIQUE_SYSTEM = """TASK: answer
The user gives you a startup/product idea. Critique it using ONLY the extracted
knowledge base excerpts supplied in the context. You are not a cheerleader.

Structure the answer as:
1. Restate the idea as a Job + segment + wedge. If the idea does not survive that
   restatement, say so - that is itself the finding.
2. Walk the relevant evaluation dimensions the channel actually supports:
   problem/Job reality, segment sharpness, why the current solution is bad,
   technology shift, before -> after value, wedge, RAT, 24-48h validation,
   distribution, demoability. Cite the excerpt behind each judgement.
3. Name the anti-patterns from the base that this idea is currently committing.
4. State the single Riskiest Assumption and the cheapest test that would kill it.
5. List what the knowledge base does NOT tell you about this idea.

Same voice-separation and citation rules as before: author's words cited, your
inferences prefixed DERIVED_HYPOTHESIS, no invented evidence.

Return JSON:
{"answer_markdown": "...", "cited_post_ids": [...], "coverage": "STRONG|PARTIAL|THIN|ABSENT",
 "caveats": ["..."]}
"""
