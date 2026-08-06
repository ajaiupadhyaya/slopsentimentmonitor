"""Command line entry points.

Ingestion lives here rather than in the API so a slow or hanging collector can
never occupy an HTTP worker. A scheduler calls these commands directly.
"""

from __future__ import annotations

import asyncio
import json

import structlog
import typer

from pulseai.config import get_settings

app = typer.Typer(help="PulseAI — LLM market intelligence", no_args_is_help=True)

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)


@app.command()
def seed() -> None:
    """Insert or refresh the model catalog and source list."""
    from pulseai.seed import seed_all

    created = asyncio.run(seed_all())
    typer.echo(f"models: +{created['models']}  sources: +{created['sources']}")


@app.command()
def ingest(
    limit: int = typer.Option(200, help="Max documents per source"),
    source: str | None = typer.Option(None, help="Run one collector by name"),
) -> None:
    """Fetch new documents from every enabled source."""
    from pulseai.pipeline.run import default_collectors
    from pulseai.pipeline.run import ingest as run_ingest

    collectors = default_collectors()
    if source:
        collectors = [c for c in collectors if c.name == source]
        if not collectors:
            raise typer.BadParameter(f"unknown source: {source}")

    report = asyncio.run(run_ingest(collectors, limit))
    typer.echo(report.render())
    typer.echo(f"\ntotal: {report.total_fetched} fetched, {report.total_inserted} new")


@app.command()
def enrich(
    batch: int = typer.Option(200, help="Documents per transaction"),
    max_documents: int | None = typer.Option(None, "--max", help="Stop after N documents"),
    reprocess: bool = typer.Option(
        False, "--reprocess", help="Re-analyse already-enriched documents"
    ),
) -> None:
    """Detect models and score sentiment for pending documents."""
    from pulseai.pipeline.run import enrich as run_enrich

    stats = asyncio.run(run_enrich(batch, max_documents, reprocess))
    typer.echo(
        f"{stats['documents']} documents  "
        f"{stats['mentions']} mentions  {stats['sentiments']} sentiments"
    )


@app.command()
def pipeline(limit: int = typer.Option(200, help="Max documents per source")) -> None:
    """Ingest then enrich — the single command that refreshes everything."""
    from pulseai.pipeline.run import enrich as run_enrich
    from pulseai.pipeline.run import ingest as run_ingest

    async def _run() -> None:
        report = await run_ingest(limit_per_source=limit)
        typer.echo(report.render())
        stats = await run_enrich()
        typer.echo(
            f"\nenriched {stats['documents']} documents → "
            f"{stats['mentions']} mentions, {stats['sentiments']} sentiments"
        )

    asyncio.run(_run())


@app.command()
def status() -> None:
    """Corpus totals and configuration, for checking the system is actually live."""
    from pulseai.analytics import corpus_summary, model_leaderboard
    from pulseai.db import session_scope

    async def _run() -> None:
        settings = get_settings()
        async with session_scope() as session:
            summary = await corpus_summary(session)
            top = await model_leaderboard(session, hours=168, limit=10)

        typer.echo(json.dumps(summary, indent=2))
        typer.echo(f"\nanalyzer: {settings.analyzer}   reddit: {settings.reddit_enabled}")
        if top:
            typer.echo("\ntop models (7d):")
            for stat in top:
                typer.echo(
                    f"  {stat.name:<18} {stat.mentions:>5} mentions  "
                    f"sentiment {stat.sentiment:+.3f}"
                )
        else:
            typer.echo("\nno mentions yet — run `pulseai pipeline`")

    asyncio.run(_run())


@app.command()
def detect(text: str) -> None:
    """Run detection against a string. Useful for debugging alias rules."""
    from pulseai.pipeline.detect import ModelDetector
    from pulseai.registry import MODELS

    detector = ModelDetector.from_specs(MODELS)
    found = detector.detect(text)
    if not found:
        typer.echo("no models detected")
        return
    for mention in found:
        typer.echo(
            f"{mention.name:<18} confidence={mention.confidence:.2f} "
            f"occurrences={mention.count} matched={mention.matched_text!r}"
        )


if __name__ == "__main__":
    app()
