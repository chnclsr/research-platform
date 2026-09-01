"""A restart may delay a run. It may not empty it.

Two runs collected sources and produced zero claims. Nothing was lost: run
`01M1E06KQSW6HQHNDCGERTKRGW` still holds 61 versions of 83k characters each, and
`01M1E0HQ9CGJYJCPQZ2MXPS6MA` still holds 1673 passages. Both reports came out empty, both
ended `completed_incomplete`, and `error` was blank on both.

The trigger was a worker restart mid-flight. The cause was two nodes that both ask "what
arrived this round": a resumed pass re-acquires nothing, so `CHUNK_INDEX` chunked nothing and
`RETRIEVE_PASSAGES` returned `no_new_source_versions` while the corpus sat in the database.

Recovery is deliberately narrow -- versions with no passages, or passages with no evidence.
A healthy later round has neither, so the round economy below is tested as carefully as the
recovery itself: re-mining passages already extracted would be its own bug.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import acting_principal

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ExtractedClaim,
    Passage,
    ResearchProtocol,
    new_id,
)

CONTENT = (
    "Sepsis prediction models are evaluated against external cohorts. "
    "The reported area under the curve fell from 0.83 to 0.63 on independent data. "
    "Alert burden rose while sensitivity dropped, and the authors call for local validation. "
) * 12


def protocol(**overrides) -> ResearchProtocol:
    payload = {
        "title": "Resume",
        "primary_question": "Why did the sepsis model underperform on external validation?",
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(overrides)
    return ResearchProtocol.model_validate(payload)


class StubEmbeddings:
    """Deterministic vectors; the retrieval maths is tested in test_passage_retrieval."""

    def __init__(self):
        self.calls = 0

    async def embed(self, inputs):
        self.calls += 1
        return [[0.1, 0.2, 0.3] for _ in inputs]

    def drain_metrics(self):
        return []


async def _run_with_corpus(repo, *, chunked: bool) -> tuple[str, list[str]]:
    """A run whose sources are acquired, optionally already chunked."""
    row = await repo.create_run(protocol())
    version_ids: list[str] = []
    for index in range(2):
        document = AcquiredDocument(
            candidate=ConnectorCandidate(
                title=f"External validation {index}",
                url=f"https://example.test/paper-{index}",
                snippet="external validation of a sepsis model",
                connector_id="semantic_scholar",
                family="academic",
            ),
            content=CONTENT,
            language="en",
            document_type="text",
            content_hash=new_id(),
            success=True,
            provenance={"language": "en", "document_type": "text"},
        )
        _, version = await repo.save_document(row.id, document)
        version_ids.append(version.id)
    await repo.session.commit()
    if chunked:
        await repo.save_passages(
            [
                Passage(
                    id=new_id(),
                    source_version_id=version_id,
                    chunk_index=index,
                    section_path="Document/Results",
                    page_number=1,
                    start_char=0,
                    end_char=40,
                    text=f"External validation reported 0.63 for cohort {index}.",
                    token_count=9,
                    content_hash=new_id(),
                    embedding=[0.1, 0.2, 0.3],
                    language="en",
                    document_type="text",
                )
                for version_id in version_ids
                for index in range(3)
            ]
        )
    return row.id, version_ids


async def _add_evidence(repo, run_id: str, version_id: str) -> None:
    """One claim with one evidence link, which is all `has_evidence` asks about."""
    await repo.save_claims(
        run_id,
        [(
            ExtractedClaim(
                text="External validation reported 0.63.",
                source_candidate_id=version_id,
                quote="External validation reported 0.63 for cohort 0.",
            ),
            version_id,
        )],
    )
    await repo.session.commit()


async def _pipeline(session, client):
    pipeline = ResearchPipeline(get_settings(), session, client)
    pipeline.embeddings = StubEmbeddings()
    return pipeline


# ------------------------------------------------------------------- chunk recovery


@pytest.mark.asyncio
async def test_an_interrupted_run_chunks_what_it_already_acquired():
    """The sepsis failure: 61 versions with content, zero passages, zero claims."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=False)
        pipeline = await _pipeline(session, client)
        # The shape a resumed pass hands the node: nothing new arrived this round.
        await pipeline.chunk_index({"run_id": run_id, "documents": []})
        passages = await repo.list_passages(run_id)
        events = await repo.events_by_types(run_id, {"passage_index"})
    assert passages, "corpus in the database must reach the index"
    assert events[-1].payload["recovered_versions"] == 2
    assert events[-1].payload["passage_count"] == len(passages)


@pytest.mark.asyncio
async def test_a_run_whose_versions_are_already_chunked_recovers_nothing():
    """Recovery must not re-chunk work that was done, or every empty round pays for it."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=True)
        before = len(await repo.list_passages(run_id))
        pipeline = await _pipeline(session, client)
        await pipeline.chunk_index({"run_id": run_id, "documents": []})
        after = await repo.list_passages(run_id)
        events = await repo.events_by_types(run_id, {"passage_index"})
    assert len(after) == before
    assert events[-1].payload["recovered_versions"] == 0


@pytest.mark.asyncio
async def test_a_round_with_new_documents_still_recovers_the_older_ones():
    """The case an earlier draft missed.

    Requiring an empty `documents` list would have skipped recovery whenever a resumed round
    happened to find one new source -- leaving everything acquired before the interruption
    unchunked, which is the bulk of it.
    """
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=False)
        _, versions = zip(*await repo.list_source_versions(run_id))
        document = AcquiredDocument(
            candidate=ConnectorCandidate(
                title="Fresh", url="https://example.test/fresh", snippet="s",
                connector_id="arxiv", family="academic",
            ),
            content=CONTENT,
            language="en",
            document_type="text",
            content_hash=new_id(),
            success=True,
        )
        payload = {**document.model_dump(mode="json"), "source_version_id": versions[0].id}
        pipeline = await _pipeline(session, client)
        await pipeline.chunk_index({"run_id": run_id, "documents": [payload]})
        events = await repo.events_by_types(run_id, {"passage_index"})
    # The version handed in this round is chunked normally; the other one is recovered.
    # The in-flight version is excluded, or it would be chunked twice in one pass.
    assert events[-1].payload["recovered_versions"] == 1
    assert events[-1].payload["passage_count"] > 0


# --------------------------------------------------------------- retrieval recovery


@pytest.mark.asyncio
async def test_retrieval_falls_back_to_the_whole_corpus_before_any_evidence():
    """The nodules failure: 1673 passages in the database, none of them retrieved."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=True)
        row = await repo.get_run(run_id)
        pipeline = await _pipeline(session, client)
        output = await pipeline.retrieve_relevant_passages(
            {"run_id": run_id, "protocol": row.protocol, "documents": [], "sub_questions": []}
        )
        events = await repo.events_by_types(run_id, {"passage_retrieval"})
    assert output["passages"], "the run's own passages must be usable"
    payload = events[-1].payload
    assert payload["reason"] == "recovered_run_corpus"
    assert payload["candidate_count"] == 6
    assert payload["selected_count"] > 0


@pytest.mark.asyncio
async def test_retrieval_keeps_the_early_return_once_evidence_exists():
    """A later empty round must not re-mine passages an earlier round already used."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, version_ids = await _run_with_corpus(repo, chunked=True)
        await _add_evidence(repo, run_id, version_ids[0])
        row = await repo.get_run(run_id)
        pipeline = await _pipeline(session, client)
        output = await pipeline.retrieve_relevant_passages(
            {"run_id": run_id, "protocol": row.protocol, "documents": [], "sub_questions": []}
        )
        events = await repo.events_by_types(run_id, {"passage_retrieval"})
    assert output["passages"] == []
    assert events[-1].payload["reason"] == "no_new_source_versions"


@pytest.mark.asyncio
async def test_has_evidence_is_what_separates_the_two_cases():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run_id, version_ids = await _run_with_corpus(repo, chunked=True)
        assert await repo.has_evidence(run_id) is False
        await _add_evidence(repo, run_id, version_ids[0])
        assert await repo.has_evidence(run_id) is True


# -------------------------------------------------------------------- visibility


@pytest.mark.asyncio
async def test_a_corpus_without_claims_is_announced_rather_than_shipped_quietly():
    """It used to end `completed_incomplete` with a blank error and a short report."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=True)
        pipeline = await _pipeline(session, client)
        await pipeline._warn_on_empty_synthesis({"run_id": run_id})
        events = await repo.events_by_types(run_id, {"empty_synthesis_with_corpus"})
    assert len(events) == 1
    payload = events[0].payload
    assert payload["sources"] == 2
    assert payload["claims"] == 0
    assert payload["passages"] == 6
    # Names where the chain broke, so the reader is not inferring it from counts.
    assert payload["reason"] == "no_evidence_extracted"


@pytest.mark.asyncio
async def test_a_run_without_passages_says_so_specifically():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, _ = await _run_with_corpus(repo, chunked=False)
        pipeline = await _pipeline(session, client)
        await pipeline._warn_on_empty_synthesis({"run_id": run_id})
        events = await repo.events_by_types(run_id, {"empty_synthesis_with_corpus"})
    assert events[0].payload["reason"] == "no_passages_indexed"


@pytest.mark.asyncio
async def test_a_run_with_claims_says_nothing():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, version_ids = await _run_with_corpus(repo, chunked=True)
        await _add_evidence(repo, run_id, version_ids[0])
        pipeline = await _pipeline(session, client)
        await pipeline._warn_on_empty_synthesis({"run_id": run_id})
        events = await repo.events_by_types(run_id, {"empty_synthesis_with_corpus"})
    assert events == []


def test_the_empty_corpus_note_exists_in_both_report_languages():
    from research_platform.exporter import _report_labels

    assert "kanıt çıkarılamadı" in _report_labels("tr")["empty_corpus_note"]
    assert "extracted no evidence" in _report_labels("en")["empty_corpus_note"]


# ------------------------------------------------- evidence over recovered passages


@pytest.mark.asyncio
async def test_evidence_extraction_survives_passages_this_round_did_not_acquire():
    """The regression the first recovery caused, found by running it against real data.

    Retrieval started handing back the run's whole corpus, and evidence extraction looked up
    a document payload per passage in `state["documents"]` -- which holds only this round's
    acquisitions. The first recovered passage raised `KeyError` and took the run down:
    `01M1E0HQ9CGJYJCPQZ2MXPS6MA` failed that way within seconds of being requeued.
    """
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, version_ids = await _run_with_corpus(repo, chunked=True)
        pipeline = await _pipeline(session, client)
        passages = await repo.list_passages(run_id)
        rebuilt = await pipeline._documents_for_recovered_passages(run_id, passages, {})
    # Every passage can name the source it came from, with no round state at all.
    assert set(rebuilt) == set(version_ids)
    for version_id in version_ids:
        payload = rebuilt[version_id]
        assert payload["source_version_id"] == version_id
        assert payload["candidate"]["title"].startswith("External validation")
        assert payload["candidate"]["url"]


@pytest.mark.asyncio
async def test_documents_already_in_hand_are_not_rebuilt():
    """A healthy round must not pay a query for records it is already holding."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run_id, version_ids = await _run_with_corpus(repo, chunked=True)
        pipeline = await _pipeline(session, client)
        passages = await repo.list_passages(run_id)
        known = {version_id: {"source_version_id": version_id} for version_id in version_ids}
        rebuilt = await pipeline._documents_for_recovered_passages(run_id, passages, known)
    assert rebuilt == {}
