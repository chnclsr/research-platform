from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

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
    ResearchProtocol,
    SearchMission,
    SourceFamily,
)
from scripts import benchmark_pipeline_connector_io as pipeline_benchmark
from scripts.benchmark_connector_io import OperationSpec, run_once


@pytest.mark.asyncio
async def test_local_benchmark_proves_overlap_and_preserves_results() -> None:
    specs = [OperationSpec(f"search-{index}", "search", 20) for index in range(6)]

    serial = await run_once(specs, mode="serial", concurrency=1, timeout_ms=200)
    concurrent = await run_once(specs, mode="asyncio", concurrency=3, timeout_ms=200)

    assert serial["max_in_flight"] == 1
    assert concurrent["max_in_flight"] == 3
    assert serial["result_fingerprint"] == concurrent["result_fingerprint"]
    assert concurrent["counts"] == {"success": 6, "error": 0, "timeout": 0}


@pytest.mark.asyncio
async def test_local_benchmark_isolates_errors_and_timeouts() -> None:
    specs = [
        OperationSpec("acquisition-ok-1", "acquisition", 50),
        OperationSpec("acquisition-error", "acquisition", 70, outcome="error"),
        OperationSpec("acquisition-timeout", "acquisition", 800),
        OperationSpec("acquisition-ok-2", "acquisition", 60),
    ]

    serial = await run_once(specs, mode="serial", concurrency=1, timeout_ms=300)
    concurrent = await run_once(specs, mode="asyncio", concurrency=3, timeout_ms=300)

    assert serial["counts"] == {"success": 2, "error": 1, "timeout": 1}
    assert concurrent["counts"] == serial["counts"]
    assert concurrent["result_fingerprint"] == serial["result_fingerprint"]
    assert concurrent["max_in_flight"] == 3


class ConcurrencyProbe:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0
        self.calls = 0
        self._lock = asyncio.Lock()

    async def wait(self, delay_s: float = 0.02) -> None:
        async with self._lock:
            self.active += 1
            self.calls += 1
            self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(delay_s)
        finally:
            async with self._lock:
                self.active -= 1


class DelayedConnector:
    id = "delayed_web"
    family = SourceFamily.WEB
    capabilities = ("search", "metadata")

    def __init__(self, probe: ConcurrencyProbe) -> None:
        self.probe = probe

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        await self.probe.wait()
        identity = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        return [
            ConnectorCandidate(
                connector_id=self.id,
                family=self.family,
                title=f"Evidence for {query}",
                url=f"https://example.test/{identity}",
                snippet=f"Direct evidence about {query}",
                persistent_id=f"delayed:{identity}",
            )
        ]


class OneConnectorRegistry:
    def __init__(self, connector: DelayedConnector) -> None:
        self.connector = connector

    def selected(self, selection) -> list[DelayedConnector]:
        return [self.connector]


@pytest.mark.asyncio
async def test_pipeline_search_honours_configured_concurrency() -> None:
    await create_schema()
    protocol = ResearchProtocol(
        title="Search concurrency probe",
        primary_question="Which sources test connector concurrency?",
        connectors={
            "profile": "custom",
            "included_families": ["web"],
            "included_connectors": ["delayed_web"],
            "citation_depth": 0,
        },
        budget={
            "max_sources": 20,
            "results_per_connector": 2,
            "max_wall_minutes": 5,
        },
    )
    missions = [
        SearchMission(
            branch_id=f"query:{index}",
            query=f"connector concurrency evidence {index}",
            connector_ids=["delayed_web"],
            result_limit=2,
        )
        for index in range(6)
    ]
    probe = ConcurrencyProbe()
    settings = get_settings().model_copy(update={"search_concurrency": 2})

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(settings, session, client)
        pipeline.registry = OneConnectorRegistry(DelayedConnector(probe))
        await pipeline._search_node(
            {
                "run_id": row.id,
                "protocol": protocol.model_dump(mode="json"),
                "missions": [mission.model_dump(mode="json") for mission in missions],
                "queries": [mission.query for mission in missions],
                "round_number": 1,
            }
        )

    assert probe.calls == 6
    assert probe.maximum == 2


class DelayedAcquisition:
    def __init__(self, probe: ConcurrencyProbe) -> None:
        self.probe = probe
        self.parser_overrides: dict[str, str] = {}

    async def acquire(self, candidate: ConnectorCandidate) -> AcquiredDocument:
        await self.probe.wait()
        content = f"Evidence downloaded from {candidate.url}"
        return AcquiredDocument(
            candidate=candidate,
            success=True,
            access_status="open",
            content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            acquisition_method="fixture",
        )


@pytest.mark.asyncio
async def test_pipeline_acquisition_honours_protocol_concurrency() -> None:
    await create_schema()
    protocol = ResearchProtocol(
        title="Acquisition concurrency probe",
        primary_question="Does acquisition respect its concurrency budget?",
        connectors={"profile": "custom", "included_families": ["web"]},
        budget={"max_sources": 20, "max_wall_minutes": 5, "acquisition_concurrency": 2},
    )
    candidates = [
        ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title=f"Source {index}",
            url=f"https://example.test/source-{index}",
        )
        for index in range(5)
    ]
    probe = ConcurrencyProbe()

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.acquisition = DelayedAcquisition(probe)
        result = await pipeline._acquire_node(
            {
                "run_id": row.id,
                "protocol": protocol.model_dump(mode="json"),
                "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
                "budget_started_at": datetime.now(UTC).isoformat(),
            }
        )

    assert probe.calls == 5
    assert probe.maximum == 2
    assert len(result["documents"]) == 5


@pytest.mark.asyncio
async def test_pipeline_node_benchmark_preserves_results_and_measures_speedup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_benchmark, "PIPELINE_DELAYS_MS", [40] * 8)

    search_c1 = await pipeline_benchmark.run_pipeline_search_once(1)
    search_c4 = await pipeline_benchmark.run_pipeline_search_once(4)
    acquisition_c1 = await pipeline_benchmark.run_pipeline_acquisition_once(1)
    acquisition_c4 = await pipeline_benchmark.run_pipeline_acquisition_once(4)

    assert search_c1["max_in_flight"] == 1
    assert search_c4["max_in_flight"] == 4
    assert search_c4["result_fingerprint"] == search_c1["result_fingerprint"]
    assert search_c4["wall_ms"] < search_c1["wall_ms"] * 0.65

    assert acquisition_c1["max_in_flight"] == 1
    assert acquisition_c4["max_in_flight"] == 4
    assert acquisition_c4["result_fingerprint"] == acquisition_c1["result_fingerprint"]
    assert acquisition_c4["wall_ms"] < acquisition_c1["wall_ms"] * 0.65


@pytest.mark.asyncio
async def test_threadpool_reference_preserves_blocking_io_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_benchmark, "PIPELINE_DELAYS_MS", [40] * 8)

    serial = await asyncio.to_thread(pipeline_benchmark.run_threadpool_once, 1)
    concurrent = await asyncio.to_thread(pipeline_benchmark.run_threadpool_once, 4)

    assert serial["max_in_flight"] == 1
    assert concurrent["max_in_flight"] == 4
    assert concurrent["result_fingerprint"] == serial["result_fingerprint"]
    assert concurrent["wall_ms"] < serial["wall_ms"] * 0.65
