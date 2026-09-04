from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from conftest import acting_principal
from research_platform.config import get_settings
from research_platform.db import (
    ClaimRow, EvidenceRow, SessionLocal, SourceRow, SourceVersionRow, create_schema,
)
from research_platform.pipeline import PipelineHalted, PipelineStageTimeout, ResearchPipeline
from research_platform.repository import (
    CheckpointTooLarge, Repository, checkpoint_payload,
)
from research_platform.schemas import (
    AcquiredDocument, ConnectorCandidate, ResearchProtocol, RunStatus, SearchMission,
    SourceFamily, new_id,
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
        budget={"max_wall_minutes": 30},
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
        budget={"max_wall_minutes": 30},
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
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
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
        budget={"max_wall_minutes": 30},
    )
    settings = get_settings().model_copy(update={
        "pipeline_control_poll_s": 0.01,
        "search_stage_timeout_s": 1.0,
    })
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        await repo.update_run(row.id, status=RunStatus.RUNNING.value)
        pipeline = ResearchPipeline(settings, session, client)

        async def never_returns():
            await asyncio.Event().wait()

        async def request_cancel():
            await asyncio.sleep(0.03)
            async with SessionLocal() as control_session:
                await Repository(control_session, actor=acting_principal()).update_run(
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
        budget={"max_wall_minutes": 30},
    )
    settings = get_settings().model_copy(update={"pipeline_control_poll_s": 0.01})
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
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
        repo = Repository(session, actor=acting_principal())
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
        repo = Repository(session, actor=acting_principal())
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
async def test_acquisition_metrics_name_the_parser_that_produced_the_text():
    """The panel breaks a stage down by tool from this event alone, without joining
    source_versions.provenance, so the parser has to travel with the metric."""
    await create_schema()
    protocol = ResearchProtocol(
        title="Parser provenance",
        primary_question="Which parser produced the text of each acquired source?",
        budget={"max_wall_minutes": 30},
    )

    class ParsingAcquisition:
        async def acquire(self, candidate):
            content = f"Evidence from {candidate.url}"
            return AcquiredDocument(
                candidate=candidate,
                success=True,
                access_status="open",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                acquisition_method="direct",
                parser_id="pymupdf_fast" if str(candidate.url).endswith(".pdf") else "html_structured",
            )

    candidates = [
        ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title="Report",
            url="https://example.com/report.pdf",
        ),
        ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.WEB,
            title="Article",
            url="https://example.com/article",
        ),
    ]
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.acquisition = ParsingAcquisition()
        await pipeline._acquire_node({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "budget_started_at": datetime.now(timezone.utc).isoformat(),
        })
        events = await repo.events_after(row.id)

    metrics = next(event for event in events if event.event_type == "acquisition_metrics")
    assert sorted(call["parser_id"] for call in metrics.payload["calls"]) == ["html_structured", "pymupdf_fast"]


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
        budget={"max_sources": 10, "results_per_connector": 4, "max_wall_minutes": 30},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
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
        budget={"max_sources": 10, "results_per_connector": 2, "max_wall_minutes": 30},
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
        repo = Repository(session, actor=acting_principal())
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
async def test_exhaustive_scan_stops_after_two_empty_recovery_rounds():
    await create_schema()
    protocol = ResearchProtocol(
        title="Empty recovery breaker",
        primary_question="How should a small language model be trained?",
        research_mode="literature_scan",
        output_mode="raw",
        connectors={"profile": "custom", "included_families": ["web"]},
        budget={"max_wall_minutes": 30, "max_rounds": 3},
        hitl={"plan_review": False},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        result = await asyncio.wait_for(
            pipeline.check_coverage({
                "run_id": row.id,
                "protocol": protocol.model_dump(mode="json"),
                "round_number": 3,
                "round_new_source_versions": 0,
                "consecutive_empty_recovery_rounds": 1,
                "source_count_before_round": 0,
                "available_connectors": ["agentsearch_web"],
                "budget_started_at": datetime.now(UTC).isoformat(),
                "discovery_stats": {
                    "round_provider_candidates": 0,
                    "round_novel_candidates": 0,
                    "round_selected_candidates": 0,
                    "round_acquisition_successful": 0,
                    "round_content_rejected": 0,
                },
            }),
            timeout=5,
        )
        events = await repo.events_after(row.id)

    assert result["stop_reason"] == "recovery_exhausted_no_progress"
    assert result["consecutive_empty_recovery_rounds"] == 2
    assert result["coverage"]["sufficient"] is False
    assert "recovery_no_progress" in result["coverage"]["reasons"]
    no_progress = next(event for event in events if event.event_type == "recovery_no_progress")
    assert no_progress.payload["reason"] == "no_provider_candidates"
    assert no_progress.payload["terminal"] is True


@pytest.mark.asyncio
async def test_pipeline_resumes_to_auditable_export():
    await create_schema()
    protocol = ResearchProtocol(
        title="Pipeline acceptance",
        primary_question="Does the tested method improve measured accuracy?",
        research_mode="focused_answer",
        connectors={"profile": "custom", "included_families": ["web"]},
        budget={"max_rounds": 2, "max_sources": 5, "max_wall_minutes": 5, "results_per_connector": 2},
        # Unattended run: the plan gate is on by default and would park this at
        # awaiting_input before SEARCH. Approving it is covered in test_hitl.py.
        hitl={"plan_review": False},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
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
        # The report's name now carries the run's topic handle, so it is looked up by the
        # prefix the naming rule guarantees rather than by a fixed string.
        word_artifact = next(
            a for a in artifacts if a.name.startswith("16_") and a.name.endswith(".docx")
        )
        word_report = await ObjectStore(get_settings()).get(word_artifact.object_key)
        with zipfile.ZipFile(io.BytesIO(word_report)) as archive:
            assert "word/document.xml" in archive.namelist()
            assert any(name.startswith("word/media/") for name in archive.namelist())
        # The chain's last link is written with the document, not derived afterwards: the
        # label and the sections citing it exist only while the report is being rendered.
        citations = await repo.list_report_citations(row.id)
        assert len(citations) == completed.sources_count
        assert citations[0].label == "S01"
        assert citations[0].number == 1
        # Cited or not, the row says which -- that is the whole point of recording it.
        assert citations[0].drop_reason is None or citations[0].drop_reason in {
            "no_evidence", "not_reportable", "answerability_gate", "section_discarded",
            "offered_not_cited",
        }
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
        hitl={"plan_review": False},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.registry = FailingRegistry()
        await pipeline.run(row.id)
        completed = await repo.get_run(row.id)
        assert completed.status == RunStatus.COMPLETED_INCOMPLETE.value
        events = await repo.events_after(row.id)
        assert any(event.event_type == "connector_error" for event in events)


def test_checkpoint_payload_strips_raw_content_without_touching_live_state():
    document = {"content": "metin", "raw_content": "BASE64PDF", "source_id": "S1"}
    state = {"run_id": "R1", "documents": [document], "candidates": [{"url": "https://x"}]}

    persisted = checkpoint_payload(state)

    assert persisted["documents"][0]["raw_content"] == ""
    # NORMALIZE reads raw_content out of the live state to write the MinIO snapshot and
    # source_versions, so trimming the persisted copy must not reach back into it.
    assert document["raw_content"] == "BASE64PDF"
    assert state["documents"][0]["raw_content"] == "BASE64PDF"
    assert persisted["candidates"] is state["candidates"]
    assert persisted["run_id"] == "R1"


def test_checkpoint_payload_is_a_noop_without_documents():
    state = {"run_id": "R1", "candidates": []}
    assert checkpoint_payload(state) is state


@pytest.mark.asyncio
async def test_checkpoint_refuses_a_state_over_the_size_limit(monkeypatch):
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(ResearchProtocol(
            title="Checkpoint size",
            primary_question="Does the checkpoint guard reject oversized state?",
            budget={"max_wall_minutes": 30},
        ))
        monkeypatch.setattr("research_platform.repository.CHECKPOINT_MAX_BYTES", 2048)

        with pytest.raises(CheckpointTooLarge) as excinfo:
            await repo.checkpoint(run.id, "NORMALIZE", {"passages": ["x" * 4096]})

        message = str(excinfo.value)
        assert "NORMALIZE" in message
        assert "passages" in message
        # The session must stay usable so the pipeline can still record the failure.
        await repo.event(run.id, "failed", {"error": message[:200]})


@pytest.mark.asyncio
async def test_frontier_skips_hostless_links_instead_of_failing_the_run():
    """
    crawl4ai reports mailto:/javascript: hrefs. A hostless URL has no domain to compare,
    and letting it through used to abort the whole run with IndexError.
    """
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(ResearchProtocol(
            title="Frontier hostless",
            primary_question="Does a hostless link abort the frontier?",
            budget={"max_wall_minutes": 30},
        ))
        added = await repo.add_frontier_links(
            run.id,
            "https://example.org/article",
            [
                "mailto:someone@example.org",
                "javascript:void(0)",
                "https://example.org/next",
                "https://other.example/page",
            ],
            max_links=10,
        )
        assert added == 2

        rows = await repo.list_frontier(run.id) if hasattr(repo, "list_frontier") else None
        if rows is not None:
            hosts = {r.canonical_url for r in rows}
            assert not any(h.startswith(("mailto:", "javascript:")) for h in hosts)


async def _appraisal_run():
    """A committed run with two claims and their evidence, ready for ADVERSARIAL_REVIEW."""
    await create_schema()
    protocol = ResearchProtocol(
        title="Appraisal",
        primary_question="Does the therapy reduce mortality in a randomized trial?",
        budget={"max_wall_minutes": 5},
        hitl={"plan_review": False},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        source = SourceRow(
            id=new_id(), run_id=row.id, url="https://example.org/trial",
            title="A randomized controlled trial", dedupe_key="trial",
            family="academic", connector_id="europe_pmc", persistent_id="10.1/a",
            metadata_json={},
        )
        session.add(source)
        await session.flush()
        version = SourceVersionRow(
            id=new_id(), source_id=source.id, content_hash="h1", content="text",
            acquisition_method="fixture", access_status="open",
            retrieved_at=datetime.now(UTC),
        )
        session.add(version)
        await session.flush()
        strong = ClaimRow(
            id=new_id(), run_id=row.id, text="The therapy reduces mortality.", importance="major",
            status="supported", confidence=0.8,
            audit={
                "supporting_evidence": 2, "counter_evidence": 0,
                "independent_domains": 2, "question_relevance": 0.9,
            },
        )
        thin = ClaimRow(
            id=new_id(), run_id=row.id, text="The therapy is cost effective.", importance="minor",
            status="qualified", confidence=0.4,
            audit={
                "supporting_evidence": 1, "counter_evidence": 0,
                "independent_domains": 1, "question_relevance": 0.5,
            },
        )
        session.add_all([strong, thin])
        await session.flush()
        session.add(EvidenceRow(
            id=new_id(), claim_id=strong.id, source_version_id=version.id, direction="supports",
            quote="mortality fell", location={}, entailment_score=0.9,
        ))
        await session.commit()

        pipeline = ResearchPipeline(get_settings(), session, client)
        state = {"run_id": row.id, "protocol": protocol.model_dump(mode="json")}
        await pipeline.adversarial_review(state)

        claims = {c.id: (c.status, dict(c.audit)) for c in await repo.list_claims(row.id)}
        events = [
            dict(e.payload) for e in await repo.events_by_types(row.id, {"claim_appraisal"})
        ]
        return claims, events, strong.id, thin.id


@pytest.mark.asyncio
async def test_adversarial_review_writes_appraisal_into_claim_audit():
    claims, _, strong_id, thin_id = await _appraisal_run()

    _, strong = claims[strong_id]
    assert strong["appraisal"]["grade"] == "strong"
    assert strong["appraisal"]["tier"] in {"universal", "clinical"}
    assert strong["appraisal"]["generated_by"] in {"model", "deterministic"}
    # The keys AUDIT writes must survive the nested addition untouched.
    assert strong["supporting_evidence"] == 2
    assert strong["question_relevance"] == 0.9

    assert claims[thin_id][1]["appraisal"]["grade"] == "limited"


@pytest.mark.asyncio
async def test_adversarial_review_emits_a_consumable_event():
    _, events, _, _ = await _appraisal_run()
    assert len(events) == 1
    appraisal = events[0]
    assert appraisal["tier"] in {"universal", "clinical"}
    assert appraisal["grades"]
    assert appraisal["generated_by"] in {"model", "fallback"}
    assert "score" in appraisal["tier_evidence"]
    assert isinstance(appraisal["latency_ms"], int)


@pytest.mark.asyncio
async def test_adversarial_review_does_not_change_claim_status():
    """The grade informs the prose; it never decides what reaches the report."""
    claims, _, strong_id, thin_id = await _appraisal_run()
    assert claims[strong_id][0] == "supported"
    assert claims[thin_id][0] == "qualified"
