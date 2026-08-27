"""What ``Repository.save_passages`` promises callers.

These are characterisation tests: they pin the behaviour the row-by-row
implementation has today so that a bulk rewrite has to reproduce it rather than
merely be faster. Re-ingest is the case that matters. The pipeline saves the same
``(source_version_id, chunk_index)`` again whenever a document is re-processed, so
"insert" and "update" are the same call site.
"""

from __future__ import annotations

import hashlib

import pytest
from conftest import acting_principal
from sqlalchemy import func, select

from research_platform.db import PassageRow, SessionLocal, create_schema
from research_platform.repository import Repository
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
    assert (
        rows[0].content_hash
        == hashlib.sha256(b"Revised passage text.").hexdigest()
    )


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
