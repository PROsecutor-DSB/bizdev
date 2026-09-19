# telegram-startup-intelligence

Turn the public history of a Telegram channel into a **startup intelligence system**:
principles, causal mechanisms, anti-patterns, heuristics and testable opportunities you
can use when starting a product or walking into a hackathon.

Target channel: [`@zamesin`](https://t.me/zamesin) (configurable — nothing is hard-coded to it).

The goal is **not** a channel summary. The question every stage is built to answer is:

> *What did the author work out about building products that I can use on my next one?*

---

## ⚠️ Status of this repository: code complete, corpus not collected

The pipeline is finished and tested end to end. **It has not been run against the real
channel from here**, because this build environment's egress policy blocks `t.me`:

```
$ curl https://t.me/s/zamesin
curl: (56) CONNECT tunnel failed, response 403
$ curl -s "$HTTPS_PROXY/__agentproxy/status"
  "recentRelayFailures": [{ "kind": "connect_rejected",
     "detail": "gateway answered 403 to CONNECT (policy denial ...)", "host": "t.me:443" }]
```

`telegram.org`, `api.telegram.org` and general web hosts are blocked too; only package
registries and GitHub are reachable. This is an organisation network policy, and routing
around it is not something this tool does.

**Consequence you need to know about:** there are no real extracted insights in
`output/` and no real `database/intelligence.sqlite`. Producing files that *looked* like
analysis of `@zamesin` without having read a single one of his posts would be fabricated
evidence — the exact failure mode the brief spends sections 9, 15 and 24 guarding against.
So the repository ships the machine, not invented output.

**What is proven here instead:** the full pipeline runs end to end, on a synthetic corpus
written for the purpose (`tests/make_demo_corpus.py`), with results in
[`output/_demo_synthetic/`](output/_demo_synthetic/) and assertions in `tests/`. That
corpus is clearly labelled synthetic and uses the channel name `demo_channel` so it can
never be mistaken for an archive of a real person's writing.

**To get the real thing**, on any machine that can reach `t.me`:

```bash
pip install -r requirements.txt
export LLM_API_KEY=sk-...              # any OpenAI-compatible endpoint
python run_pipeline.py --stage all --max-posts 200   # MVP slice first
python run_pipeline.py --stage all                   # then the whole history
python query.py
```

---

## What it produces

| File | What it is |
|---|---|
| `output/START_HERE.md` | the one page a human reads: strongest principles, thinking models, how the author picks a segment / tests a product / thinks about strategy, what AI changed, top opportunities, 10 hackathon rules, 10 things not to do |
| `output/CORE_INSIGHTS.md` | every high-leverage claim with its **mechanism**, grouped by taxonomy area, one entry per idea |
| `output/STARTUP_PATTERNS.md` | recurring patterns: problem, observation, mechanism, when it works, when it fails, how to detect, how to test |
| `output/ANTI_PATTERNS.md` | documented mistakes + *why they feel right at the time*, with early warning signs |
| `output/AJTBD_KNOWLEDGE_BASE.md` | the author's **own** Advanced JTBD vocabulary, rebuilt from his posts, with divergences from textbook JTBD called out |
| `output/HACKATHON_COMPASS.md` | the 9-stage decision checklist (Problem → Segment → Technology shift → Value → Wedge → RAT → MVP → Distribution → Demo) with channel evidence attached to each stage |
| `output/OPPORTUNITY_MAP.md` | implied opportunities + `NEW TECHNOLOGY × OLD JOB` entries — all `DERIVED_HYPOTHESIS` |
| `output/IDEA_GENERATOR.md` | concrete ideas traced to a Job + structural problem + technology unlock, scored on 9 independent dimensions |
| `output/HIDDEN_GEMS.md` | rare, low-engagement, high-leverage observations |
| `output/EVOLUTION_OF_THOUGHT.md` | where the author changed his mind, and **which version to use today** |
| `output/DATASET_STATS.md` | what was collected and what is missing |
| `database/intelligence.sqlite` | the actual knowledge base; the markdown files are views over it |

Plus `query.py` — ask the base questions and get cited, uncertainty-aware answers.

---

## Pipeline

```
SCRAPE ─► NORMALIZE ─► THREADS ─► CLASSIFY ─► STATS
   │                                  │
   │                                  ▼
   │                          (pure noise costs no tokens)
   │                                  │
   └──────────────────────────────►  EXTRACT ─► AJTBD
                                       │
                                       ▼
                         EMBED ─► CLUSTER ─► RELATIONS (dedupe verification)
                                       │
                                       ▼
        PATTERNS · ANTI-PATTERNS · EVOLUTION · OPPORTUNITIES · TECH×JOB · IDEAS · GEMS
                                       │
                                       ▼
                                    REPORTS
```

Every stage is separately runnable, idempotent and resumable:

```bash
python -m src.scraper.tgweb --channel zamesin --max-posts 200
python -m src.parser.normalize      && python -m src.parser.threads
python -m src.classifier.classify   && python -m src.reports.dataset_stats
python -m src.classifier.audit sample --n 50     # then fill in labels, then:
python -m src.classifier.audit score
python -m src.extractor.insights --min-score 40
python -m src.deduplicator.embed && python -m src.deduplicator.cluster && python -m src.deduplicator.relations
python -m src.synthesis.patterns && python -m src.synthesis.antipatterns && python -m src.synthesis.evolution
python -m src.synthesis.opportunities && python -m src.synthesis.tech_job && python -m src.synthesis.ideas
python -m src.synthesis.hidden_gems && python -m src.reports.render
```

or `make mvp` / `make full` / `make demo` / `make test`.

---

## Architectural decisions

Every contestable call, and why it went the way it did.

### 1. The public web preview is the primary source; Telethon is the fallback

`https://t.me/s/<channel>` serves the channel's public posts as plain HTML with a
`?before=<id>` cursor. No account, no API credentials, no session file, no terms to
accept. `src/scraper/tgweb.py` walks it backwards from the newest post until the cursor
stops advancing.

Its limits are real and documented rather than worked around: it does not render reaction
counts for every channel, and for very old history Telegram may stop paginating.
`src/scraper/telethon_scraper.py` covers those cases through the **official** API, with
credentials read only from `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`. Both writers produce
the same record shape, so everything downstream is source-agnostic.

**No CAPTCHA solving, no auth bypass, no rate-limit evasion.** We add our own delay
(`TG_DELAY_SECONDS`, default 1s), and we obey `Retry-After` when Telegram sends one.
Only the channel's own public posts are read — never subscribers, never comment threads,
never private resources.

### 2. Raw is immutable and separate from analysis

`data/raw/<channel>.raw.jsonl` is verbatim extraction. `data/processed/` holds
normalisation, `data/insights/` holds extraction, `database/` holds the queryable base.
Re-running analysis never touches raw. Re-scraping only adds posts and refreshes volatile
fields like view counts.

### 3. Deterministic Python owns the data; the LLM only owns meaning

IDs, parsing, chunking, storage, clustering and selection are pure Python and
reproducible. `insight_id = sha1(source_post_uid + normalised_thesis)`, so the same post
producing the same thesis always yields the same id and re-runs upsert instead of
duplicating. The LLM is used only for classification, insight and mechanism extraction,
semantic synthesis, contradiction detection and opportunity generation.

### 4. The LLM provider is swappable, and there is an offline engine

`src/llm/provider.py` speaks the OpenAI-compatible chat-completions + embeddings API over
plain `requests` — no vendor SDK, so OpenAI, OpenRouter, Together, Groq, vLLM, LM Studio
and Ollama's `/v1` shim all work by changing `LLM_BASE_URL` and `LLM_MODEL`. API keys come
from the environment only.

`HeuristicProvider` is a deterministic rule engine that lets the whole pipeline run with no
key and no network. It is honest about its limits:

- it **extracts** — it quotes the sentences in a post that carry causal language, and
  aggregates a cluster from its members' own words;
- it **never generates** — asked for an opportunity, an idea, or a cited answer, it
  returns nothing rather than inventing one;
- everything it touches is stamped `engine="heuristic"`, and every report it produces
  carries a banner saying so.

Measured on the labelled synthetic corpus (`make test`): 80% exact category accuracy,
**100% content recall**, 100% noise caught. Content recall is the number that matters —
misreading promo as content costs a few tokens, misreading content as promo loses
knowledge permanently.

### 5. Threads, not posts, are the unit of analysis

A post that says "1/3." is meaningless alone. `src/parser/threads.py` merges a series
using four conservative signals: explicit `reply_to`, media `grouped_id`, part markers
("1/3", "Часть 2", "продолжение"), and a dangling opener followed closely in time. A
wrong merge destroys meaning while a missed merge only loses context, so the rules err
towards not merging. Every member's `post_uid` and permalink is carried through.

### 6. Nothing is ever deleted — noise is routed, not removed

Promo, hiring and announcement posts stay in the database with their category. They are
simply not sent to the extractor, which is where the token budget lives. `CONTENT_PLUS_PROMO`
gets special handling: the promotional shell is stripped into `removed_promo` and the
substance survives in `clean_text`, verbatim. Both are stored, so the cleaning is auditable.

### 7. Two signal scores, neither of which uses popularity

`rule_signal_score` (deterministic, from surface markers) and `content_signal_score` (the
LLM's judgement) are stored side by side. Neither can see views or reactions — the
classification prompt is not given them, on purpose. Engagement is stored on the post and
used only as a *secondary* signal, notably inverted in `HIDDEN_GEMS.md`, where low
engagement is evidence *for* inclusion.

### 8. `mechanism` is the load-bearing field

"Focus on one segment" is useless. The extractor is instructed to reconstruct
WHY → MECHANISM → CONSEQUENCE, and when the post genuinely does not contain a causal
chain it must write `""` and fill `mechanism_missing_reason` rather than invent one. The
reports print *"Mechanism: not stated in the source"* explicitly, so a missing mechanism
is visible rather than papered over.

### 9. The author is a subject of study, not an authority

Every insight carries `evidence_type` ∈ {OBSERVATION, HYPOTHESIS, FRAMEWORK,
PERSONAL_OPINION, CASE_EVIDENCE, EMPIRICAL_EVIDENCE, MARKETING_CLAIM, AUTHOR_CLAIM}.
The default when unsure is `AUTHOR_CLAIM`, and the reports render it with a ⚠️ and the
words *"unsupported in the material"*. "This methodology increases your odds of success"
is an `AUTHOR_CLAIM`, not a fact, and the system will say so.

### 10. Our inference is labelled, always

Opportunities, generated ideas and technology×Job entries are inference, not the author's
position. They are stored with `label='DERIVED_HYPOTHESIS'`, rendered with that badge on
every entry, and the page headers repeat it. `query.py` enforces the same split in its
answers, and warns when the model cites a post id that was not in the retrieved context.

### 11. Recurrence is found by embedding + clustering, verified by the LLM, and never auto-deleted

Cosine similarity over `thesis + mechanism + problem_pattern` (mechanism included
deliberately: two posts can share a thesis while explaining different machinery, and
those are *not* duplicates) builds a similarity graph; connected components above a
threshold become clusters. Then the LLM labels each close pair as `DUPLICATE`,
`REFINEMENT`, `CONTRADICTION`, `EXAMPLE` or `EVOLUTION`. A `DUPLICATE` verdict deletes
nothing — the cluster elects one representative for the reports and every member stays
queryable. `CONTRADICTION` pairs feed `EVOLUTION_OF_THOUGHT.md`.

Clustering is O(n²) and pure Python. At a few thousand insights that is seconds; past
roughly 20k, shard by tag or swap in a vector index. `--max-pairs` warns before it bites.

### 12. Nine scores, no magic total

`IDEA_GENERATOR.md` prints Job frequency, pain, existing spend, poor existing solution,
technology unlock, demoability, 48h buildability, distribution accessibility and evidence
strength as independent 1–5 columns. There is no combined score anywhere in the codebase
and no idea is called best, because the right choice depends on which dimension your
situation cannot tolerate being low — a hackathon team and a funded startup read the same
table in opposite directions.

### 13. Hidden gems are selected deterministically, not generated

Being a "hidden gem" is a property of the corpus (rare + neglected + high leverage), not
something to ask a model about. `src/synthesis/hidden_gems.py` computes leverage, rarity
and neglect separately and prints all three, so you can see why each entry qualified. An
insight with no mechanism cannot be a gem.

### 14. SQLite is the knowledge base; markdown files are views

One file, no server, FTS5 for lexical search, JSON columns for the flexible parts.
Re-render any report at any time with `python -m src.reports.render`. Every derived row
stores `source_posts`, `engine` and `prompt_version`, so in six months you can tell which
model wrote what, under which prompt.

The reports carry **no generation timestamp**. Re-rendering unchanged data would
otherwise produce a diff in all ten files every time, which buries real changes in
review. When each stage last ran — with its engine, parameters and result counts — is in
the `runs` table:

```bash
make when                      # latest run per stage
python -m src.reports.runs --all
```

Rendering the same database twice now produces byte-identical files.

### 15. Retrieval for `query.py` is hybrid and local

FTS5 lexical matching plus embedding cosine, merged by reciprocal-rank-ish scoring. The
LLM sees only the retrieved excerpts and is instructed to say *"the base does not cover
this"* rather than fill the gap with general startup knowledge dressed up as the author's.
Coverage is reported as `STRONG` / `PARTIAL` / `THIN` / `ABSENT` with every answer.

### 16. Prompts live in one versioned file

`src/llm/prompts.py` holds every prompt with a `PROMPT_VERSION`. Output quality is a
function of these prompts, so they are reviewable in one place rather than scattered
through the code. Each carries a `TASK:` marker that the heuristic engine dispatches on,
which keeps the two engines in sync.

### 17. Ship the MVP before the architecture

Per the brief: `--max-posts 200` runs the entire pipeline on a slice first. Check
`DATASET_STATS.md`, run `src.classifier.audit sample`, read fifty classifications by
hand, *then* scale to the full history. The LLM response cache (`data/processed/.llm_cache/`)
means nothing is paid for twice.

### Known limits

- The web preview may not reach the earliest posts of a very old channel. `DATASET_STATS.md`
  reports `post_ids_missing_in_range` and the largest id gaps so you can see the hole.
- Reactions are frequently absent from the preview. Treat engagement-based signals as
  optional; nothing load-bearing depends on them.
- Deleted and edited posts are invisible: you get the channel as it is now, not as it was.
- The heuristic engine's taxonomy tagging is broad (substring lexicons). With an LLM
  configured this stops mattering.
- `EVOLUTION_OF_THOUGHT.md` needs years of material on one topic to say anything. On a
  200-post slice it will be thin, and honestly so.

---

## Layout

```
telegram-startup-intelligence/
  run_pipeline.py          one command, all stages
  query.py                 ask the knowledge base
  src/
    config.py              env-driven config, taxonomy, category lists
    utils.py               deterministic ids, text handling, JSONL io
    scraper/tgweb.py             public web preview  (primary)
    scraper/telethon_scraper.py  official API        (fallback)
    parser/normalize.py    raw -> analysis-ready records
    parser/threads.py      logical series grouping
    cleaner/promo.py       promo-shell removal
    classifier/classify.py category + content signal score
    classifier/audit.py    STEP 4 manual review tooling
    extractor/insights.py  atomic insights with mechanisms
    extractor/ajtbd.py     the author's own JTBD vocabulary
    deduplicator/          embed -> cluster -> LLM relation verification
    synthesis/             patterns, anti-patterns, evolution,
                           opportunities, tech×job, ideas, hidden gems
    reports/render.py      every markdown file
    reports/dataset_stats.py
    reports/runs.py        when each stage last ran
    llm/provider.py        OpenAI-compatible + offline heuristic engine
    llm/prompts.py         all prompts, versioned
    llm/heuristic.py       the deterministic rule engine
    db/store.py            SQLite schema and access
  data/{raw,processed,insights}/
  output/
  database/intelligence.sqlite
  tests/
```

## Tests

```bash
make test      # or: python tests/run_all.py
```

Covers deterministic ids, text handling, thread merging, promo stripping, signal scoring,
chunk coverage, JSON repair, the scraper's HTML parsing against a fixture page, a full
end-to-end pipeline run with provenance and labelling assertions, and classifier quality
against a labelled corpus.

## Privacy and scope

Collected: public channel posts only — id, date, permalink, text, links, hashtags,
views/reactions where public, media flags, forward and reply metadata.

Never collected: subscriber data, personal data of users, private messages, individual
user comments, or the contents of closed Telegram resources.
