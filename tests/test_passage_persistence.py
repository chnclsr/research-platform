"""What ``Repository.save_passages`` promises callers.

These are characterisation tests: they pin the behaviour the row-by-row
implementation has today so that a bulk rewrite has to reproduce it rather than
merely be faster. Re-ingest is the case that matters. The pipeline saves the same
``(source_version_id, chunk_index)`` again whenever a document is re-processed, so
"insert" and "update" are the same call site.
"""

from __future__ import annotations

import contextlib
import hashlib
from unittest import mock

import pytest
from conftest import acting_principal
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from research_platform.db import PassageRow, SessionLocal, create_schema, engine
from research_platform.repository import PASSAGE_UPSERT_BATCH, Repository
from research_platform.schemas import Passage

VERSION_A = "01VERSIONA".ljust(26, "0")
VERSION_B = "01VERSIONB".ljust(26, "0")


def make_passage(
    *,
    passage_id: str,
    version_id: str = VERSION_A,
    chunk_index: int = 0,
    text: str = "Original passage text.",
    embedding: list[float] | None = None,
    section_path: str = "Document/Intro",
) -> Passage:
    return Passage(
        id=passage_id,
        source_version_id=version_id,
        chunk_index=chunk_index,
        section_path=section_path,
        page_number=1,
        start_char=0,
        end_char=len(text),
        text=text,
        token_count=max(1, len(text.split())),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        language="en",
        document_type="text",
        embedding=embedding if embedding is not None else [0.1, 0.2, 0.3],
        retrieval_score=0.5,
        matched_questions=["q1"],
    )


async def save(passages: list[Passage]) -> None:
    async with SessionLocal() as session:
        await Repository(session, actor=acting_principal()).save_passages(passages)


async def fetch(version_id: str = VERSION_A) -> list[PassageRow]:
    async with SessionLocal() as session:
        return list(
            await session.scalars(
                select(PassageRow)
                .where(PassageRow.source_version_id == version_id)
                .order_by(PassageRow.chunk_index)
            )
        )


@pytest.fixture(autouse=True)
async def clean_passages():
    await create_schema()
    async with SessionLocal() as session:
        for row in await session.scalars(select(PassageRow)):
            await session.delete(row)
        await session.commit()


@pytest.mark.anyio
async def test_save_passages_writes_every_field():
    await save([make_passage(passage_id="01PA".ljust(26, "0"))])

    rows = await fetch()

    assert len(rows) == 1
    row = rows[0]
    assert row.id == "01PA".ljust(26, "0")
    assert row.text == "Original passage text."
    assert row.embedding == [0.1, 0.2, 0.3]
    assert row.section_path == "Document/Intro"
    assert row.metadata_json["retrieval_score"] == 0.5
    assert row.metadata_json["matched_questions"] == ["q1"]
    assert row.metadata_json["language"] == "en"
    assert row.metadata_json["document_type"] == "text"


@pytest.mark.anyio
async def test_resaving_the_same_chunk_updates_in_place_instead_of_duplicating():
    await save([make_passage(passage_id="01PA".ljust(26, "0"))])
    await save(
        [
            make_passage(
                passage_id="01PA".ljust(26, "0"),
                text="Revised passage text.",
                embedding=[0.9, 0.8, 0.7],
                section_path="Document/Results",
            )
        ]
    )

    rows = await fetch()

    assert len(rows) == 1
    assert rows[0].text == "Revised passage text."
    assert rows[0].embedding == [0.9, 0.8, 0.7]
    assert rows[0].section_path == "Document/Results"
    assert rows[0].content_hash == hashlib.sha256(b"Revised passage text.").hexdigest()


@pytest.mark.anyio
async def test_reingest_with_a_new_passage_id_keeps_the_existing_row_identity():
    """Chunk identity is ``(version, chunk_index)``, not the generated passage id.

    Re-chunking mints fresh ids, and claims already reference the stored row, so the
    row must keep the id it was written with.
    """
    await save([make_passage(passage_id="01PA".ljust(26, "0"))])
    await save([make_passage(passage_id="01PDIFFERENT".ljust(26, "0"), text="Second pass.")])

    rows = await fetch()

    assert len(rows) == 1
    assert rows[0].id == "01PA".ljust(26, "0")
    assert rows[0].text == "Second pass."


@pytest.mark.anyio
async def test_mixed_batch_inserts_new_chunks_and_updates_existing_ones():
    await save(
        [
            make_passage(passage_id="01P0".ljust(26, "0"), chunk_index=0, text="Chunk zero."),
            make_passage(passage_id="01P1".ljust(26, "0"), chunk_index=1, text="Chunk one."),
        ]
    )
    await save(
        [
            make_passage(passage_id="01P0".ljust(26, "0"), chunk_index=0, text="Chunk zero v2."),
            make_passage(passage_id="01P2".ljust(26, "0"), chunk_index=2, text="Chunk two."),
        ]
    )

    rows = await fetch()

    assert [row.chunk_index for row in rows] == [0, 1, 2]
    assert [row.text for row in rows] == ["Chunk zero v2.", "Chunk one.", "Chunk two."]


@pytest.mark.anyio
async def test_same_chunk_index_under_different_versions_stays_separate():
    await save(
        [
            make_passage(passage_id="01PA".ljust(26, "0"), version_id=VERSION_A, text="From A."),
            make_passage(passage_id="01PB".ljust(26, "0"), version_id=VERSION_B, text="From B."),
        ]
    )

    assert [row.text for row in await fetch(VERSION_A)] == ["From A."]
    assert [row.text for row in await fetch(VERSION_B)] == ["From B."]


@pytest.mark.anyio
async def test_saving_an_empty_list_is_a_no_op():
    await save([])

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(PassageRow)) == 0


class StatementLog:
    """Counts what actually reaches the driver, which is the point of the change."""

    def __init__(self) -> None:
        self.inserts = 0
        self.commits = 0

    def on_execute(self, conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().upper().startswith("INSERT INTO PASSAGES"):
            self.inserts += 1

    def on_commit(self, conn) -> None:
        self.commits += 1


@contextlib.contextmanager
def statement_log():
    log = StatementLog()
    event.listen(engine.sync_engine, "before_cursor_execute", log.on_execute)
    event.listen(engine.sync_engine, "commit", log.on_commit)
    try:
        yield log
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", log.on_execute)
        event.remove(engine.sync_engine, "commit", log.on_commit)


def bulk_passages(count: int, *, version_id: str = VERSION_A) -> list[Passage]:
    return [
        make_passage(
            passage_id=f"01BULK{index:020d}",
            version_id=version_id,
            chunk_index=index,
            text=f"Bulk chunk {index}.",
        )
        for index in range(count)
    ]


@pytest.mark.anyio
async def test_save_passages_sends_one_statement_per_batch_and_commits_once():
    """The whole point of the rewrite: round trips scale with batches, not passages."""
    passages = bulk_passages(2 * PASSAGE_UPSERT_BATCH + 1)

    with statement_log() as log:
        await save(passages)

    assert log.inserts == 3
    assert log.commits == 1
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(PassageRow)) == len(passages)


@pytest.mark.anyio
async def test_a_failing_batch_leaves_no_earlier_batch_behind():
    """Batches share one transaction, so a late failure must undo the early writes."""
    await save([make_passage(passage_id="01CLASH".ljust(26, "0"), version_id=VERSION_B)])

    passages = bulk_passages(PASSAGE_UPSERT_BATCH + 1)
    # Lands in the second batch and collides on the primary key, which the conflict
    # target does not cover, so the statement fails after batch one has executed.
    passages[PASSAGE_UPSERT_BATCH].id = "01CLASH".ljust(26, "0")

    with statement_log() as log, pytest.raises(IntegrityError):
        await save(passages)

    # Without this the test would also pass if the first batch had never been sent,
    # which would prove nothing about rollback.
    assert log.inserts == 2
    assert log.commits == 0
    async with SessionLocal() as session:
        surviving = await session.scalar(
            select(func.count())
            .select_from(PassageRow)
            .where(PassageRow.source_version_id == VERSION_A)
        )
    assert surviving == 0


@pytest.mark.anyio
async def test_duplicate_chunks_in_one_call_keep_first_id_and_last_content():
    """The old loop resolved these last-write-wins; a raw batch would be rejected."""
    first = make_passage(passage_id="01FIRST".ljust(26, "0"), chunk_index=4, text="First write.")
    second = make_passage(passage_id="01SECOND".ljust(26, "0"), chunk_index=4, text="Last write.")

    await save([first, second])

    rows = await fetch()
    assert len(rows) == 1
    assert rows[0].id == "01FIRST".ljust(26, "0")
    assert rows[0].text == "Last write."


@pytest.mark.anyio
async def test_batch_is_ordered_by_the_conflict_key():
    """A fixed lock order is what keeps two concurrent writers from deadlocking."""
    shuffled = [
        make_passage(passage_id=f"01ORD{index:021d}", chunk_index=index, text=f"Chunk {index}.")
        for index in (7, 2, 9, 0, 4)
    ]

    rows = Repository._passage_upsert_rows(shuffled)

    assert [row["chunk_index"] for row in rows] == [0, 2, 4, 7, 9]


@pytest.mark.anyio
async def test_unsupported_dialect_is_refused_rather_than_silently_degraded():
    """There is no row-by-row fallback, so an unsupported driver must say so."""
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        with (
            mock.patch.object(type(session.get_bind().dialect), "name", "oracle", create=True),
            pytest.raises(RuntimeError, match="ON CONFLICT"),
        ):
            await repo.save_passages([make_passage(passage_id="01X".ljust(26, "0"))])


@pytest.mark.anyio
async def test_saving_an_empty_list_still_commits_the_callers_pending_work():
    """zotero_sync flushes a document and leans on this call to make it durable.

    ``save_document`` only flushes, so for an item that chunks to nothing the
    document write is still hanging in the transaction when save_passages runs.
    Returning early without committing would drop it on session close.
    """
    pending = make_passage(passage_id="01PENDING".ljust(26, "0"))

    async with SessionLocal() as session:
        session.add(PassageRow(**Repository._passage_values(pending)))
        await session.flush()
        await Repository(session, actor=acting_principal()).save_passages([])
        # No explicit commit here: leaving the block rolls back anything uncommitted.

    assert [row.id for row in await fetch()] == ["01PENDING".ljust(26, "0")]


@pytest.mark.anyio
async def test_rows_already_loaded_in_the_session_see_the_update():
    """The pipeline reads passages, saves them, then reads them again on one session.

    RETRIEVE_PASSAGES loads the run's passages, writes retrieval metadata back
    through save_passages, and a later stage lists them again from the same session.
    A core-level write leaves the identity map holding the pre-write objects, so
    without expiring them that second read would miss the metadata just written.
    """
    await save([make_passage(passage_id="01SEEN".ljust(26, "0"), text="Original.")])

    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        loaded = await session.scalars(select(PassageRow))
        assert [row.text for row in loaded] == ["Original."]

        await repo.save_passages(
            [make_passage(passage_id="01SEEN".ljust(26, "0"), text="Rewritten.")]
        )

        reread = await session.scalars(select(PassageRow))
        assert [row.text for row in reread] == ["Rewritten."]
