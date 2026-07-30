from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import PipelineHalted, PipelineStageTimeout, ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument, ConnectorCandidate, ResearchProtocol, RunStatus, SearchMission,
    SourceFamily,
)
from research_platform.storage import ObjectStore


class DummyConnector:
    id = "dummy_web"
    family = SourceFamily.WEB

    def missing_credentials(self):
        return []

    async def search(self, query: str, limit: int = 20):
        return [ConnectorCandidate(
            connector_id=self.id, family=self.family,
            title="Independent evidence source", url="https://example.com/evidence",
            snippet="Evidence summary", persistent_id="dummy:1",
        )]


class DummyRegistry:
    def selected(self, selection):
        return [DummyConnector()]


class CitationConnector(DummyConnector):
    id = "semantic_scholar"
    family = SourceFamily.ACADEMIC
    capabilities = ("search", "citations")

    def __init__(self):
        self.search_calls = 0

    async def search(self, query: str, limit: int = 20):
        self.search_calls += 1
        return [ConnectorCandidate(
            connector_id=self.id, family=self.family,
            title="Seed evidence", url="https://example.org/seed",
            snippet="lung CT cancer risk", persistent_id="seed",
            metadata={"scholarly_ids": {"semantic_scholar_id": "seed"}},
        )]

    async def fetch_citations(self, candidate):
        if candidate.persistent_id == "depth-2":
            return []
        target = "depth-1" if candidate.persistent_id == "seed" else "depth-2"
        return [{
            "relation_type": "cited_by",
            "target_persistent_id": target,
            "provider": self.id,
            "metadata": {"paperId": target, "title": f"Evidence {target}"},
        }]


class CitationRegistry:
    def __init__(self):
        self.connector = CitationConnector()

    def selected(self, selection):
        return [self.connector]


class FailingConnector(DummyConnector):
    id = "failing_web"

    async def search(self, query: str, limit: int = 20):
        raise httpx.ConnectError("fixture unavailable")


class FailingRegistry:
    def selected(self, selection):
        return [FailingConnector()]


class DummyAcquisition:
    async def acquire(self, candidate):
        content = (
            "Independent measurements show that the tested method improves accuracy by ten percent. "
            "The study reports its sampling method and limitations in a public appendix."
        )
        return AcquiredDocument(
            candidate=candidate, success=True, access_status="open", content=content,
            content_type="text/plain", acquisition_method="fixture",
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            strategies_tried=["fixture"],
        )


class SemanticJudgeLLM:
    def __init__(self, response):
        self.response = response

    async def complete_json(self, system_prompt, user_prompt):
        return self.response


class FailingSemanticJudgeLLM:
    def __init__(self):
        self.calls = 0

    async def complete_json(self, system_prompt, user_prompt):
        self.calls += 1
        raise ValueError("invalid model JSON")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            {
                "directly_relevant": False,
                "relevance_score": 0.1,
                "reason": "Adjacent disease only",
            },
            (False, 0.1, "Adjacent disease only"),
        ),
        (
            {
                "directly_relevant": True,
                "relevance_score": 0.9,
                "reason": "Direct CT risk evidence",
            },
            (True, 0.9, "Direct CT risk evidence"),
        ),
    ],
)
async def test_semantic_source_judge_uses_relevance_score(response, expected):
    protocol = ResearchProtocol(
        title="Semantic source admission",
        primary_question="What recent CT models estimate lung cancer risk?",
    )
    candidate = ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.ACADEMIC,
        title="Fixture publication",
        url="https://example.com/publication",
    )
    document = AcquiredDocument(
        candidate=candidate,
        success=True,
        content="Publication content",
        content_type="text/plain",
        acquisition_method="fixture",
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = SemanticJudgeLLM(response)
        assert await pipeline._semantic_source_judgment(protocol, document) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output_mode", "research_mode", "expected_relevant", "expected_policy"),
    [
        ("raw", "focused_answer", False, "fail_closed"),
        ("both", "focused_answer", True, "fail_open"),
        ("raw", "literature_scan", True, "fail_open"),
    ],
)
async def test_semantic_source_judge_retries_and_uses_delivery_failure_policy(
    output_mode, research_mode, expected_relevant, expected_policy,
):
    protocol = ResearchProtocol(
        title="Semantic source failure policy",
        primary_question="Which evidence directly answers the research question?",
        output_mode=output_mode,
        research_mode=research_mode,
    )
    document = AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title="Fixture source",
            url="https://example.com/source",
        ),
        success=True,
        content="Fixture content",
        content_type="text/plain",
        acquisition_method="fixture",
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        llm = FailingSemanticJudgeLLM()
        pipeline.llm = llm
        relevant, _, reason = await pipeline._semantic_source_judgment(protocol, document)
    assert relevant is expected_relevant
    assert expected_policy in reason
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_pipeline_preserves_cancellation_before_worker_start():
    await create_schema()
    protocol = ResearchProtocol(
        title="Pre-start cancellation",
        primary_question="Does a cancelled queued run remain cancelled?",
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        await repo.update_run(row.id, status=RunStatus.CANCEL_REQUESTED.value)
        pipeline = ResearchPipeline(get_settings(), session, client)
        await pipeline.run(row.id)
        cancelled = await repo.get_run(row.id)
        assert cancelled.status == RunStatus.CANCELLED.value
        events = await repo.events_after(row.id)
        assert any(event.event_type == "cancelled" for event in events)


@pytest.mark.asyncio
async def test_in_node_cancellation_interrupts_hung_io_promptly():
    await create_schema()
    protocol = ResearchProtocol(
        title="Hung I/O cancellation",
        primary_question="Can an active search be cancelled?",
    )
    settings = get_settings().model_copy(update={
        "pipeline_control_poll_s": 0.01,
        "search_stage_timeout_s": 1.0,
    })
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        await repo.update_run(row.id, status=RunStatus.RUNNING.value)
        pipeline = ResearchPipeline(settings, session, client)

        async def never_returns():
            await asyncio.Event().wait()

        async def request_cancel():
            await asyncio.sleep(0.03)
            async with SessionLocal() as control_session:
                await Repository(control_session).update_run(
                    row.id, status=RunStatus.CANCEL_REQUESTED.value,
                )

        control = asyncio.create_task(request_cancel())
        with pytest.raises(PipelineHalted, match="cancelled"):
            await pipeline._interruptible(
                never_returns(),
                {"run_id": row.id},
                "SEARCH",
                settings.search_stage_timeout_s,
            )
        await control
        await asyncio.sleep(0)
        cancelled = await repo.get_run(row.id)
        events = await repo.events_after(row.id)

    assert cancelled.status == RunStatus.CANCELLED.value
    assert any(
        event.event_type == "cancelled" and event.payload.get("in_node")
        for event in events
    )


@pytest.mark.asyncio
async def test_hung_node_has_a_hard_safety_timeout():
    await create_schema()
    protocol = ResearchProtocol(
        title="Hung node timeout",
        primary_question="Does a hung node terminate?",
    )
    settings = get_settings().model_copy(update={"pipeline_control_poll_s": 0.01})
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(settings, session, client)

        async def never_returns():
            await asyncio.Event().wait()

        with pytest.raises(PipelineStageTimeout, match="SEARCH exceeded"):
            await pipeline._interruptible(
                never_returns(), {"run_id": row.id}, "SEARCH", 0.03,
            )
        await asyncio.sleep(0)
        events = await repo.events_after(row.id)

    assert any(event.event_type == "stage_timeout" for event in events)


@pytest.mark.asyncio
async def test_collection_budget_is_persistent_and_skips_new_discovery_after_restart():
    await create_schema()
    protocol = ResearchProtocol(
        title="Persistent wall budget",
        primary_question="Does elapsed research time survive a worker restart?",
        budget={"max_wall_minutes": 1},
    )

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        await repo.checkpoint(row.id, "VALIDATE_PROTOCOL", {
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "budget_started_at": (
                datetime.now(timezone.utc) - timedelta(minutes=2)
            ).isoformat(),
        })
        pipeline = ResearchPipeline(get_settings(), session, client)
        result = await pipeline.search({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "budget_started_at": (
                datetime.now(timezone.utc) - timedelta(minutes=2)
            ).isoformat(),
        })
        events = await repo.events_after(row.id)

    assert result["candidates"] == []
    assert any(
        event.event_type == "collection_budget_exhausted"
        and event.payload["action"] == "skip_new_discovery"
        for event in events
    )


@pytest.mark.asyncio
async def test_acquisition_cutoff_keeps_completed_documents_for_postprocessing():
    await create_schema()
    protocol = ResearchProtocol(
        title="Graceful collection cutoff",
        primary_question="Does collection cutoff preserve completed sources?",
        budget={"max_wall_minutes": 1, "acquisition_concurrency": 2},
    )

    class TimedAcquisition:
        async def acquire(self, candidate):
            await asyncio.sleep(1 if "slow" in str(candidate.url) else 0.01)
            content = f"Evidence from {candidate.url}"
            return AcquiredDocument(
                candidate=candidate,
                success=True,
                access_status="open",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                acquisition_method="fixture",
            )

    candidates = [
        ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title="Fast source",
            url="https://example.com/fast",
        ),
        ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title="Slow source",
            url="https://example.com/slow",
        ),
    ]
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.acquisition = TimedAcquisition()
        result = await pipeline._acquire_node({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "budget_started_at": (
                datetime.now(timezone.utc) - timedelta(seconds=59.7)
            ).isoformat(),
        })
        events = await repo.events_after(row.id)

    assert len(result["documents"]) == 1
    assert "fast" in result["documents"][0]["candidate"]["url"]
    assert any(
        event.event_type == "collection_budget_exhausted"
        and event.payload["action"] == "continue_postprocessing"
        and event.payload["completed"] == 1
        for event in events
    )


@pytest.mark.asyncio
async def test_search_expands_citation_frontier_to_requested_depth():
    await create_schema()
    protocol = ResearchProtocol(
        title="Citation expansion",
        primary_question="Which lung CT systems estimate cancer risk?",
        connectors={
            "profile": "custom",
            "included_families": ["academic"],
            "citation_depth": 2,
        },
        budget={"max_sources": 10, "results_per_connector": 4},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.registry = CitationRegistry()
        mission = SearchMission(
            branch_id="query:0", query=protocol.primary_question,
            connector_ids=["semantic_scholar"], result_limit=4,
        )
        result = await pipeline.search({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "missions": [mission.model_dump(mode="json")],
            "queries": [protocol.primary_question],
            "round_number": 1,
        })
    depths = {
        candidate["metadata"].get("citation_depth")
        for candidate in result["candidates"]
        if candidate["metadata"].get("discovery_method") == "citation_frontier"
    }
    assert depths == {1, 2}


@pytest.mark.asyncio
async def test_public_semantic_scholar_fanout_is_limited_per_round():
    await create_schema()
    protocol = ResearchProtocol(
        title="Public S2 capacity",
        primary_question="Which studies evaluate retrieval evidence quality?",
        connectors={
            "profile": "custom", "included_families": ["academic"],
            "included_connectors": ["semantic_scholar"], "citation_depth": 0,
        },
        budget={"max_sources": 10, "results_per_connector": 2},
    )
    registry = CitationRegistry()
    missions = [
        SearchMission(
            branch_id=f"query:{index}", query=f"evidence quality branch {index}",
            connector_ids=["semantic_scholar"], result_limit=2,
        )
        for index in range(5)
    ]
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.registry = registry
        await pipeline.search({
            "run_id": row.id, "protocol": protocol.model_dump(mode="json"),
            "missions": [mission.model_dump(mode="json") for mission in missions],
            "queries": [mission.query for mission in missions], "round_number": 1,
        })
    assert registry.connector.search_calls == 2


@pytest.mark.asyncio
async def test_pipeline_resumes_to_auditable_export():
    await create_schema()
    protocol = ResearchProtocol(
        title="Pipeline acceptance",
        primary_question="Does the tested method improve measured accuracy?",
        research_mode="focused_answer",
        connectors={"profile": "custom", "included_families": ["web"]},
        budget={"max_rounds": 2, "max_sources": 5, "max_wall_minutes": 5, "results_per_connector": 2},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.registry = DummyRegistry()
        pipeline.acquisition = DummyAcquisition()
        await pipeline.run(row.id)
        completed = await repo.get_run(row.id)
        assert completed.status in {RunStatus.COMPLETED.value, RunStatus.COMPLETED_INCOMPLETE.value}
        assert completed.sources_count == 1
        assert completed.claims_count >= 1
        artifacts = await repo.list_artifacts(row.id)
        assert len(artifacts) == 21
        word_artifact = next(a for a in artifacts if a.name == "16_research_report.docx")
        word_report = await ObjectStore(get_settings()).get(word_artifact.object_key)
        with zipfile.ZipFile(io.BytesIO(word_report)) as archive:
            assert "word/document.xml" in archive.namelist()
            assert any(name.startswith("word/media/") for name in archive.namelist())
        inventory_artifact = next(
            a for a in artifacts if a.name == "15_literature_inventory.md"
        )
        inventory = await ObjectStore(get_settings()).get(inventory_artifact.object_key)
        assert "Independent evidence source" in inventory.decode("utf-8")
        assert "Bu kaynak ne söylüyor?" in inventory.decode("utf-8")
        assert any(a.name == "raw_bundle.zip" for a in artifacts)
        assert any(a.name == "result_bundle.zip" for a in artifacts)
        assert any(a.name == "research_bundle.zip" for a in artifacts)
        raw_artifact = next(a for a in artifacts if a.name == "raw_bundle.zip")
        raw_bundle = await ObjectStore(get_settings()).get(raw_artifact.object_key)
        with zipfile.ZipFile(io.BytesIO(raw_bundle)) as archive:
            assert "13_raw_sources.jsonl" in archive.namelist()
            assert "14_raw_passages.jsonl" in archive.namelist()
            assert "15_literature_inventory.md" in archive.namelist()
            assert "02_full_research_report.md" not in archive.namelist()


@pytest.mark.asyncio
async def test_concurrent_connector_failures_are_recorded_without_breaking_session():
    await create_schema()
    protocol = ResearchProtocol(
        title="Connector failure acceptance",
        primary_question="Can connector failures be reported safely?",
        research_mode="focused_answer",
        connectors={"profile": "custom", "included_families": ["web"]},
        budget={"max_rounds": 1, "max_sources": 5, "max_wall_minutes": 5, "results_per_connector": 2},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.registry = FailingRegistry()
        await pipeline.run(row.id)
        completed = await repo.get_run(row.id)
        assert completed.status == RunStatus.COMPLETED_INCOMPLETE.value
        events = await repo.events_after(row.id)
        assert any(event.event_type == "connector_error" for event in events)
