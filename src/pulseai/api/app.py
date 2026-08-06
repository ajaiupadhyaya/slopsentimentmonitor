"""FastAPI application.

Read-only in Phase 1: ingestion runs from the CLI or a scheduler, never from a
request handler, so a slow collector can never hold an HTTP connection open.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pulseai.api.routes import router
from pulseai.db import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PulseAI",
        description="Real-time market intelligence for large language models",
        version="0.1.0",
        lifespan=lifespan,
    )

    # The dashboard is served from a different origin in development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
