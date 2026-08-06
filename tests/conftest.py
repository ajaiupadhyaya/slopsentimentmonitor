"""Test fixtures.

Database tests run against a throwaway `pulseai_test` database created from the
same metadata as production, not against the development corpus. They are
marked `db` and skip cleanly when Postgres is not running, so `make test` works
before `make up`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pulseai.config import get_settings
from pulseai.models import Base, Document, Mention, Model, Sentiment, Source

TEST_DB = "pulseai_test"


def _admin_url() -> str:
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + "/postgres"


def _test_url() -> str:
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest_asyncio.fixture(scope="function")
async def session() -> AsyncGenerator[AsyncSession]:
    """A session against a freshly-created schema.

    Function scoped and rebuilt each time: aggregate queries are order- and
    accumulation-sensitive, so leaking rows between tests would produce failures
    that only appear in certain run orders.
    """
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
            await connection.exec_driver_sql(f'CREATE DATABASE "{TEST_DB}"')
    except Exception as exc:  # noqa: BLE001 - reported as a skip, not a failure
        await admin.dispose()
        pytest.skip(f"Postgres unavailable ({type(exc).__name__}); run `make up`")
    await admin.dispose()

    engine = create_async_engine(_test_url())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db_session:
        yield db_session

    await engine.dispose()


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


class CorpusBuilder:
    """Builds documents with mentions and sentiment in one call.

    Aggregate tests are unreadable when half of each test is row construction;
    this keeps the arithmetic under test visible.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._source: Source | None = None
        self._models: dict[str, Model] = {}
        self._counter = 0

    async def source(self) -> Source:
        if self._source is None:
            self._source = Source(name="test", type="forum", priority=1, enabled=True)
            self.session.add(self._source)
            await self.session.flush()
        return self._source

    async def model(self, slug: str, company: str = "TestCo") -> Model:
        if slug not in self._models:
            model = Model(slug=slug, name=slug.title(), company=company, aliases=[], active=True)
            self.session.add(model)
            await self.session.flush()
            self._models[slug] = model
        return self._models[slug]

    async def add(
        self,
        slug: str,
        *,
        compound: float,
        hours_ago: float = 1.0,
        mention_confidence: float = 1.0,
        sentiment_confidence: float = 1.0,
        title: str = "doc",
    ) -> Document:
        source = await self.source()
        model = await self.model(slug)
        self._counter += 1

        document = Document(
            source_id=source.id,
            external_id=f"ext-{self._counter}",
            title=title,
            content="body",
            published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
            url=f"https://example.test/{self._counter}",
            author="tester",
        )
        self.session.add(document)
        await self.session.flush()

        self.session.add(
            Mention(
                document_id=document.id,
                model_id=model.id,
                confidence=mention_confidence,
                position=0,
                occurrences=1,
            )
        )
        self.session.add(
            Sentiment(
                document_id=document.id,
                model_id=model.id,
                positive=max(compound, 0.0),
                negative=max(-compound, 0.0),
                neutral=1 - abs(compound),
                confidence=sentiment_confidence,
                compound=compound,
                analyzer="test",
            )
        )
        await self.session.flush()
        return document


@pytest_asyncio.fixture
async def corpus(session: AsyncSession) -> CorpusBuilder:
    return CorpusBuilder(session)
