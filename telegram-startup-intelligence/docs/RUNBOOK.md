# Runbook

Step-by-step, following the order in the brief. Do not skip to `--stage all` on the full
history — a bad classifier on 4000 posts is expensive and you will not notice.

## 0. Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # edit it
set -a; . ./.env; set +a      # export everything
```

Without `LLM_API_KEY` the pipeline still runs, on the deterministic heuristic engine.
Use that to validate the plumbing; do not use it to judge the ideas.

## 1. Collect

```bash
python -m src.scraper.tgweb --channel zamesin --max-posts 200
```

Watch the page log. If it stops early with *"no further cursor"*, the preview has hit
its limit — see step 1b.

Full history:

```bash
python -m src.scraper.tgweb --channel zamesin
```

Resumable: re-running merges into the existing `data/raw/zamesin.raw.jsonl`.

### 1b. If the preview will not go back far enough

```bash
export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...     # from https://my.telegram.org
pip install telethon
python -m src.scraper.telethon_scraper --channel zamesin
```

First run asks for a phone number and a login code — that is Telegram's own auth, handled
by Telethon. Records merge into the same raw file.

## 2. Look at the dataset before trusting it

```bash
python -m src.parser.normalize && python -m src.parser.threads
python -m src.reports.dataset_stats
```

Read `output/DATASET_STATS.md`. Check specifically:

- `post_ids_missing_in_range` and `largest_id_gaps` — how much history is missing;
- `date_earliest` — did you actually reach the beginning;
- `exact_duplicate_posts` — repeated announcements, expected on a channel that sells;
- `reactions_available` — often 0 from the preview, which is fine.

## 3. Classify

```bash
python -m src.classifier.classify
```

The printed distribution is your first sanity check. On a channel that runs courses,
expect a substantial `PROMO` + `ANNOUNCEMENT` share and a meaningful `CONTENT_PLUS_PROMO`
bucket. If `CONTENT_PLUS_PROMO` is near zero, the classifier is probably collapsing mixed
posts into `PROMO` and you are losing knowledge — check step 4 before proceeding.

## 4. Audit it by hand. Actually do this one.

```bash
python -m src.classifier.audit sample --n 50
```

Open `output/CLASSIFIER_AUDIT.md` and read the fifty posts. Fill `human_category` and
`human_signal_score` in `data/processed/zamesin.audit.jsonl`, then:

```bash
python -m src.classifier.audit score
```

The metric to care about is **content recall** — of the posts you labelled substantive,
how many stayed in a category the extractor will read. Below ~90%, fix it before spending
tokens: raise `--min-score` sensitivity, or adjust the lexicons in `src/llm/heuristic.py`,
or sharpen `CLASSIFY_SYSTEM` in `src/llm/prompts.py`.

The sample is seeded, so your labels survive re-runs.

## 5–7. Extract, store, first reports

```bash
python -m src.extractor.insights --min-score 40
python -m src.extractor.ajtbd
python -m src.deduplicator.embed && python -m src.deduplicator.cluster && python -m src.deduplicator.relations
python -m src.reports.render --only CORE_INSIGHTS.md START_HERE.md
```

Read twenty entries in `CORE_INSIGHTS.md` and ask the brief's question of each one:
**so what?** If an insight changes no decision — not the problem, segment, build, price,
experiment, falsification criterion, channel, or your reading of customer behaviour —
the extraction prompt is too permissive. Tighten `EXTRACT_SYSTEM` and re-run with
`--force`.

Check that `mechanism` actually explains machinery rather than restating advice. That
single field is the difference between this and a summary.

## 8. The rest

```bash
python run_pipeline.py --from-stage patterns
```

Then read `HACKATHON_COMPASS.md` — it is the one you will actually use under time
pressure.

## Using it

```bash
python query.py
> How does he choose a segment?
> /tag RAT
> /jobs
> /critique an AI agent that negotiates purchases on your behalf
```

```bash
python query.py "What mistakes do founders make before building an MVP?"
python query.py "An AI agent that negotiates B2B purchases" --critique
```

## Cost control

- Classification runs on every thread; extraction only on threads above `--min-score`.
  Raising the floor from 40 to 55 cuts extraction volume sharply.
- Everything is cached in `data/processed/.llm_cache/`, keyed by model + prompt. Re-runs
  are free. Delete the directory to force a clean re-run.
- `LLM_CONCURRENCY` (default 4) controls parallelism. Raise it if your provider allows.
- Use a cheap model for `classify`, a strong one for `extract` and the synthesis stages:
  run them as separate commands with different `LLM_MODEL` values.
