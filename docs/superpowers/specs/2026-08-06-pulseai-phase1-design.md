# PulseAI — Phase 1 Design

**Date:** 2026-08-06
**Status:** Approved (infra / NLP / Reddit / scope decisions confirmed by user)

## Context

`README.md` is a ~1,200-line vision spec describing roughly ten independent
subsystems. It is a destination, not a plan. This document specifies Phase 1:
the narrowest slice that ingests real public data, enriches it, stores it, and
displays it — end to end, actually running.

## Decomposition of the README

| Phase | Scope |
|---|---|
| **1 (this doc)** | Schema, collectors (HN/GitHub/RSS/Reddit), model detection, sentiment, REST API, minimal dashboard |
| 2 | Embeddings + pgvector semantic search, deduplication, more collectors |
| 3 | Topic/intent classification, aspect sentiment, comparison extraction, analytics scores, trend detection |
| 4 | Full dashboard pages, AI daily reports, alert system |

## Environment constraints (measured, not assumed)

Probed on 2026-08-06:

- Hacker News Algolia API — works, no auth, full-text + comments.
- GitHub API via `gh auth token` — works, 5,000 req/hr.
- News RSS feeds — work, no auth.
- Reddit public `.json` — **blocked**, returns HTML. OAuth now required.
- No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` on this machine.
- Docker installed, daemon was not running. Postgres 14 + Redis via brew, no pgvector.

Phase 1 must therefore produce real data with **zero credentials**.

## Architecture

```
Collectors ──► Normalizer ──► Model Detection ──► Analyzer ──► Postgres ──► FastAPI ──► Next.js
(HN, GitHub,    RawDocument     alias matching     sentiment    (pgvector-
 RSS, Reddit)   → Document      → Mention          → Sentiment   ready)
```

Phase 1 runs the pipeline in-process. Redis Streams is provisioned in
`docker-compose.yml` and becomes the collector/worker boundary in Phase 2, when
ingest volume justifies decoupling.

### Decisions

**Infrastructure — Docker Compose.** `pgvector/pgvector:pg17` plus `redis:7-alpine`
on non-default ports (5433/6380) to avoid colliding with the brew-installed
Postgres 14 and Redis. Ships pgvector for Phase 2 with no migration.

**NLP — local models behind a protocol.** No API keys exist, so the default
`Analyzer` runs locally: `cardiffnlp/twitter-roberta-base-sentiment-latest` on
Apple Silicon MPS. A `HeuristicAnalyzer` (pure Python, no downloads) is the
fallback so tests and cold starts never require a model. An LLM-backed analyzer
implements the same protocol later without touching callers.

**Reddit — built dormant.** The collector is written with full OAuth support and
skips cleanly when `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are absent, so it
activates by adding credentials rather than by writing code.

### Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `collectors/*` | Fetch source-native payloads → `RawDocument` | httpx |
| `pipeline/normalize` | `RawDocument` → canonical `Document` | — |
| `pipeline/detect` | Text → `[Mention]` via alias matching | `registry` |
| `pipeline/analyze` | Text → `Sentiment` | transformers (optional) |
| `pipeline/run` | Orchestrate + persist, idempotently | all of the above |
| `analytics` | Aggregate queries: counts, timeseries, momentum | SQLAlchemy |
| `api/*` | REST surface | analytics |
| `web/` | Dashboard | api |

Each collector is independently testable against recorded fixtures; none of them
know about the database.

## Model detection — the crux

Detection quality determines whether every downstream number is meaningful. The
hard cases are ambiguity, not coverage:

- `grok` is also an English verb ("I grok it") — requires case sensitivity.
- `Llama` is an animal; `llama.cpp`/`Llama 3` are not.
- `Gemini` is a zodiac sign.
- `Nova`, `Kimi`, `Codex`, `Copilot` are common words or ambiguous products.
- `Claude` vs `Claude Code` vs `Claude Sonnet` — the longest match must win.

Approach: an alias table where each alias carries `case_sensitive` and
`requires_context` flags, matched longest-first with regex word boundaries.
Ambiguous aliases only count when AI context terms co-occur in the document.
Each mention records a confidence score and character position.

This is the one component built test-first, with an adversarial fixture set of
strings that must NOT match.

## Data flow and idempotency

Collectors return documents keyed by `(source, external_id)`. Ingestion upserts
on that key, so re-running a collector never duplicates rows. Mentions and
sentiment are recomputed and replaced per document, making the enrichment stage
safely re-runnable as models improve.

## Error handling

A failing collector must not stop ingestion. Each collector runs inside a
per-source boundary that logs and continues. HTTP calls get bounded retries with
backoff for 5xx/429 and fail fast on 4xx. A document that fails enrichment is
stored unenriched and retried later rather than dropped.

## Testing

- Unit: detection (including the must-not-match corpus), normalization, analyzer protocol conformance, analytics math.
- Integration: collectors against recorded fixtures; pipeline against a real Postgres from Compose.
- Live smoke: one opt-in test that hits HN for real, marked so CI skips it.

## Success criteria

Phase 1 is done when a single `make` target ingests real Hacker News, GitHub, and
RSS documents into Postgres, the API returns non-empty mention and sentiment data
for tracked models, the dashboard renders that data in a browser, and the test
suite passes. Nothing is claimed working until it is observed working.
