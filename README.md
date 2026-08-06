# PulseAI

Market intelligence for large language models. Ingests public discussion from
Hacker News, GitHub, news RSS and Reddit, works out which models each document
is talking about, scores sentiment toward each of them separately, and serves
the result as an API and a dashboard.

The full product vision is in [`docs/VISION.md`](docs/VISION.md). This README
covers what is built and how to run it.

```
Collectors ──► Clean ──► Detect ──► Analyze ──► Postgres ──► FastAPI ──► Next.js
HN, GitHub,    strip     alias      sentiment   pgvector-
RSS, Reddit    boilerplate matching  per model   ready
```

## Run it

Requires Docker, [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
make setup      # start Postgres + Redis, migrate, seed the model catalog
make env        # optional: lift a GitHub token from your `gh` login
make pipeline   # collect and analyse real documents
make dev        # API on :8000, dashboard on :3000
```

No API keys are required. The pipeline collects from Hacker News, GitHub and
news RSS with no credentials at all, and analysis runs locally.

## What is built

**Collectors.** Hacker News (Algolia full-text), GitHub (issues and PRs), news
and vendor RSS, and Reddit. Each is isolated: a source that 4xxs is logged and
reported as a skip while the others still land their data. Ingestion is
idempotent on `(source, external_id)`, so re-running updates rows instead of
duplicating them — and refreshed text clears the enrichment flag, so improving a
parser heals the stored corpus on the next run.

**Reddit is built but dormant.** Reddit's public `.json` endpoints now return an
HTML interstitial, so OAuth is required. The collector is complete and tested;
it reports why it is skipping until you create a free "script" app at
[reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) and set
`PULSEAI_REDDIT_CLIENT_ID` / `PULSEAI_REDDIT_CLIENT_SECRET`.

**Boilerplate removal.** On the first live corpus, **18.6% of all model mentions
were machine-generated** — `Co-Authored-By: Claude Opus 5` trailers, GitHub
issue-template placeholders in HTML comments, and bot-authored PRs. Counting
those inflates whichever assistant wrote the commit and attaches the sentiment
of an unrelated eslint fix to it. Removing them cut Claude Code's apparent
mention count from 85 to 28 and moved its sentiment from −0.06 to −0.35.

**Model detection.** 33 models with hand-weighted aliases, matched longest-first
so `Claude Code` beats a bare `Claude`. Precision is favoured over recall
because every downstream metric is a count of these matches:

- word boundaries, so `Casanova` is not Nova and `codexes` is not Codex
- case sensitivity, so `grok` the verb is not Grok the product
- context gating, so `Gemini` counts only when the document is also about AI —
  checked with the model's own matches masked out, so a name can never vouch
  for itself
- a blocklist for famous humans, because Claude Monet is not a language model

**Sentiment.** Scored per `(document, model)` rather than per document, over a
window around each model's own mentions — so a comparison post counts as praise
for one model and a complaint about the other. The default analyzer is a
lexicon tuned for developer vocabulary, where general-purpose tools fail:
"insane at refactoring" is praise, "stupid fast" is not an insult. Install the
`ml` extra for an on-device RoBERTa model instead:

```bash
uv sync --extra ml
PULSEAI_ANALYZER=local make enrich
```

**Analytics.** All averages are weighted by detection and analyzer confidence,
and every figure ships with the mention count behind it. Momentum is reported as
`null` rather than `+100%` when there is no prior window — growth from zero is
unknown, not infinite.

## Commands

| Command | Does |
|---|---|
| `make setup` | Containers, migrations, catalog seed |
| `make pipeline` | Ingest then enrich |
| `make status` | Corpus totals and the current leaderboard |
| `make test` | 131 tests, ~5s |
| `make lint` | ruff + tsc |
| `uv run pulseai detect "<text>"` | Debug alias rules against a string |
| `uv run pytest -m live` | Hit the real APIs; catches upstream shape changes |

## API

`GET /api/overview`, `/models`, `/models/{slug}`, `/sentiment`, `/mentions`,
`/compare`, `/sources`. Every endpoint takes `hours` (1–2160, default 168).
Interactive docs at `http://localhost:8000/docs`.

## Layout

```
src/pulseai/
  collectors/    source adapters; know nothing about the database
  pipeline/      clean → detect → analyze → persist
  analytics.py   aggregate queries
  api/           FastAPI routes
  registry.py    the model catalog that seeds the database
web/             Next.js dashboard
tests/           131 tests; `db` needs Postgres, `live` needs the internet
```

Models are stored in the database, not hardcoded — detection compiles its
matcher from `models` rows at runtime, so adding one is an insert.

## Not built yet

Phase 2 onward from the vision doc: embeddings and semantic search (pgvector is
enabled, the table is not), deduplication, topic and intent classification,
comparison extraction, trend detection, AI-generated reports, and the alert
system. Redis is provisioned for the collector/worker split that Phase 2 needs;
Phase 1 runs the pipeline in-process.
