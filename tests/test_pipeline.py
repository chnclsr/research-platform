from __future__ import annotations

import hashlib
import io
import zipfile

import httpx
import pytest

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument, ConnectorCandidate, ResearchProtocol, RunStatus, SourceFamily,
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
    ("output_mode", "expected_relevant", "expected_policy"),
    [
        ("raw", False, "fail_closed"),
        ("both", True, "fail_open"),
    ],
)
async def test_semantic_source_judge_retries_and_uses_delivery_failure_policy(
    output_mode, expected_relevant, expected_policy,
):
    protocol = ResearchProtocol(
        title="Semantic source failure policy",
        primary_question="Which evidence directly answers the research question?",
        output_mode=output_mode,
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
async def test_pipeline_resumes_to_auditable_export():
    await create_schema()
    protocol = ResearchProtocol(
        title="Pipeline acceptance",
        primary_question="Does the tested method improve measured accuracy?",
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
        assert len(artifacts) == 17
        assert any(a.name == "raw_bundle.zip" for a in artifacts)
        assert any(a.name == "result_bundle.zip" for a in artifacts)
        assert any(a.name == "research_bundle.zip" for a in artifacts)
        raw_artifact = next(a for a in artifacts if a.name == "raw_bundle.zip")
        raw_bundle = await ObjectStore(get_settings()).get(raw_artifact.object_key)
        with zipfile.ZipFile(io.BytesIO(raw_bundle)) as archive:
            assert "13_raw_sources.jsonl" in archive.namelist()
            assert "14_raw_passages.jsonl" in archive.namelist()
            assert "02_full_research_report.md" not in archive.namelist()


@pytest.mark.asyncio
async def test_concurrent_connector_failures_are_recorded_without_breaking_session():
    await create_schema()
    protocol = ResearchProtocol(
        title="Connector failure acceptance",
        primary_question="Can connector failures be reported safely?",
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
