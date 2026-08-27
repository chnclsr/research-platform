"""Concurrent writers against real PostgreSQL.

The rest of the suite runs on SQLite, which serialises writers and so cannot show
what ``save_passages`` does when two of them overlap. Upsert takes row locks, and
two callers saving the same chunks in different orders would deadlock if they took
those locks in different sequences. That is the risk this file exists to cover, and
it needs a server that actually detects deadlocks.

Skipped unless the isolated benchmark database from ``research/bulk-insert`` is up:

    docker compose -f research/bulk-insert/compose.yml up -d --wait postgres
"""

from __future__ import annotations

import asyncio
import hashlib
import socket

import pytest
from conftest import acting_principal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from research_platform.db import PassageRow
from research_platform.repository import Repository
from research_platform.schemas import Passage

BENCHMARK_HOST = "127.0.0.1"
BENCHMARK_PORT = 55433
BENCHMARK_URL = (
    f"postgresql+asyncpg://bulk_benchmark:bulk_benchmark@"
    f"{BENCHMARK_HOST}:{BENCHMARK_PORT}/bulk_benchmark"
)
VERSION_ID = "01PGCONCURRENCY".ljust(26, "0")
CHUNK_COUNT = 40


def benchmark_database_is_up() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((BENCHMARK_HOST, BENCHMARK_PORT)) == 0


pytestmark = pytest.mark.skipif(
    not benchmark_database_is_up(),
    reason=(
        "needs the isolated benchmark PostgreSQL: "
        "docker compose -f research/bulk-insert/compose.yml up -d --wait postgres"
    ),
)


def make_passages(marker: str) -> list[Passage]:
    passages = []
    for index in range(CHUNK_COUNT):
        text = f"{marker} chunk {index}."
        passages.append(
            Passage(
                id=f"01PG{marker}{index:018d}"[:26].ljust(26, "0"),
                source_version_id=VERSION_ID,
                chunk_index=index,
                section_path="Document/Concurrency",
                page_number=1,
                start_char=0,
                end_char=len(text),
                text=text,
                token_count=max(1, len(text.split())),
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                language="en",
                document_type="text",
                embedding=[0.1, 0.2, 0.3],
                retrieval_score=0.5,
                matched_questions=["q"],
            )
        )
    return passages


@pytest.fixture
async def postgres_sessions():
    engine = create_async_engine(BENCHMARK_URL, pool_size=4, max_overflow=0)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(PassageRow.__table__.create, checkfirst=True)
            await connection.execute(
                delete(PassageRow).where(PassageRow.source_version_id == VERSION_ID)
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.execute(
                delete(PassageRow).where(PassageRow.source_version_id == VERSION_ID)
            )
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_overlapping_writers_in_opposite_order_do_not_deadlock(postgres_sessions):
    """Both callers touch the same chunks; only a shared lock order keeps them safe."""

    async def writer(marker: str, reverse: bool) -> None:
        passages = make_passages(marker)
        if reverse:
            passages.reverse()
        for _ in range(4):
            async with postgres_sessions() as session:
                await Repository(session, actor=acting_principal()).save_passages(passages)

    # A deadlock surfaces as DeadlockDetected from one of these, failing the test.
    await asyncio.gather(writer("A", reverse=False), writer("B", reverse=True))

    async with postgres_sessions() as session:
        rows = list(
            await session.scalars(
                select(PassageRow)
                .where(PassageRow.source_version_id == VERSION_ID)
                .order_by(PassageRow.chunk_index)
            )
        )

    assert [row.chunk_index for row in rows] == list(range(CHUNK_COUNT))
    # Whichever writer committed last owns every row: the writers do not interleave
    # within a chunk, so a mixture would mean a batch was applied only in part.
    markers = {row.text.split()[0] for row in rows}
    assert len(markers) == 1


@pytest.mark.anyio
async def test_concurrent_first_writes_settle_on_one_row_per_chunk(postgres_sessions):
    """Two writers inserting the same new chunks must not produce duplicates."""
    await asyncio.gather(*(_save_once(postgres_sessions, marker) for marker in ("X", "Y", "Z")))

    async with postgres_sessions() as session:
        rows = list(
            await session.scalars(
                select(PassageRow).where(PassageRow.source_version_id == VERSION_ID)
            )
        )

    assert len(rows) == CHUNK_COUNT
    assert len({row.chunk_index for row in rows}) == CHUNK_COUNT


async def _save_once(session_factory, marker: str) -> None:
    async with session_factory() as session:
        await Repository(session, actor=acting_principal()).save_passages(make_passages(marker))
