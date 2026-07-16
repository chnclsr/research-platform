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
