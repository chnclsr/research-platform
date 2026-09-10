from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from conftest import acting_principal

from research_platform.config import get_settings
from sqlalchemy import select

from research_platform.db import (
    ClaimRow,
    EvidenceRow,
    FrontierRow,
    SessionLocal,
    SourceRow,
    SourceVersionRow,
    create_schema,
)
from research_platform.pipeline import (
    PipelineHalted,
    PipelineStageTimeout,
    ResearchPipeline,
    _scope_role_allows_evidence,
    _validated_scope_role,
)
from research_platform.repository import (
    CheckpointTooLarge,
    Repository,
    checkpoint_payload,
)
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ResearchProtocol,
    ResearchScopeCriteria,
    RunStatus,
    SearchMission,
    SourceFamily,
    SourceScopeRole,
    new_id,
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


def test_scope_role_requires_complete_facets_and_enforces_exclusions():
    criteria = ResearchScopeCriteria.model_validate(
        {
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["chest"]},
                {"name": "modality", "accepted_values": ["CT"]},
                {"name": "input_form", "accepted_values": ["3D"]},
                {"name": "task", "accepted_values": ["report generation"]},
            ],
            "exclusion_signals": ["PET/CT", "2D-only input"],
        }
    )
    text = "Chest CT uses a 3D volume for report generation; PET/CT is not used."
    facets = [
        {"facet": "anatomy", "matched": True, "reason": "anatomy", "evidence": "Chest"},
        {"facet": "modality", "matched": True, "reason": "modality", "evidence": "CT"},
        {"facet": "input_form", "matched": True, "reason": "input", "evidence": "3D volume"},
        {"facet": "task", "matched": True, "reason": "task", "evidence": "report generation"},
    ]
    clear_exclusions = [
        {"exclusion": "PET/CT", "matched": False, "reason": "absent", "evidence": ""},
        {"exclusion": "2D-only input", "matched": False, "reason": "absent", "evidence": ""},
    ]

    assert _validated_scope_role(
        criteria,
        SourceScopeRole.PRIMARY_IN_SCOPE,
        facets,
        clear_exclusions,
        text,
        "all required facets are present",
    ) == SourceScopeRole.PRIMARY_IN_SCOPE
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.PRIMARY_IN_SCOPE,
        facets[:-1],
        clear_exclusions,
        text,
        "one facet is missing",
    ) == SourceScopeRole.NEAR_SCOPE
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.SUPPORTING_BENCHMARK,
        [
            *facets[:-1],
            {
                "facet": "task",
                "matched": False,
                "reason": "benchmark does not generate reports",
                "evidence": "",
            },
        ],
        clear_exclusions,
        text,
        "benchmark supports evaluation",
    ) == SourceScopeRole.SUPPORTING_BENCHMARK

    matched_exclusion = [
        {"exclusion": "PET/CT", "matched": True, "reason": "explicit", "evidence": "PET/CT"},
        clear_exclusions[1],
    ]
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.PRIMARY_IN_SCOPE,
        facets,
        matched_exclusion,
        text,
        "an exclusion applies",
    ) == SourceScopeRole.EXCLUDED

    # A bare label is not evidence in either direction. Every facet is proven and no
    # exclusion is, so an unsupported EXCLUDED label no longer parks the source in near.
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.EXCLUDED,
        facets,
        clear_exclusions,
        text,
        "the model asserted exclusion without evidence",
    ) == SourceScopeRole.PRIMARY_IN_SCOPE
    # Run 01M203's 89-source failure: the model downgraded itself and the proof says
    # otherwise. This is the single line that would have kept CT2Rep in the report.
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.NEAR_SCOPE,
        facets,
        clear_exclusions,
        text,
        "the model downgraded itself",
    ) == SourceScopeRole.PRIMARY_IN_SCOPE
    # ...but only where the proof holds. A facet the model itself declined bars promotion,
    # and the accepted-value route may not overrule that decision even though the value
    # ("report generation") is in the text.
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.EXCLUDED,
        [*facets[:-1], {**facets[-1], "matched": False, "reason": "no report generation"}],
        clear_exclusions,
        text,
        "the model declined one facet",
    ) == SourceScopeRole.NEAR_SCOPE
    assert _validated_scope_role(
        criteria,
        SourceScopeRole.PRIMARY_IN_SCOPE,
        [{**item, "reason": ""} for item in facets],
        clear_exclusions,
        text,
        "all required facets are present",
    ) == SourceScopeRole.NEAR_SCOPE


def test_scope_roles_gate_evidence_and_coverage_but_keep_legacy_runs_compatible():
    scoped = ResearchProtocol(
        title="Scoped",
        primary_question="Which volumetric chest CT systems generate reports?",
        scope_criteria={
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["chest"]},
            ],
        },
        budget={"max_wall_minutes": 30},
    )
    assert _scope_role_allows_evidence(
        scoped, {"research_scope_role": "primary_in_scope"}
    )
    assert _scope_role_allows_evidence(
        scoped, {"research_scope_role": "supporting_benchmark"}
    )
    assert not _scope_role_allows_evidence(
        scoped, {"research_scope_role": "near_scope"}
    )
    assert not _scope_role_allows_evidence(scoped, {"research_scope_role": "excluded"})
    assert _scope_role_allows_evidence(scoped, {})

    legacy = ResearchProtocol(
        title="Legacy",
        primary_question="What is known?",
        budget={"max_wall_minutes": 30},
    )
    assert _scope_role_allows_evidence(legacy, {"research_scope_role": "excluded"})
    assert _scope_role_allows_evidence(None, {"research_scope_role": "excluded"})


def test_filtered_chest_ct_list_scope_regression():
    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "chest_ct_scope_cases.json").read_text(
            encoding="utf-8"
        )
    )
    criteria = ResearchScopeCriteria.model_validate(
        {
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["chest", "thorax", "lung"]},
                {"name": "modality", "accepted_values": ["CT"]},
                {"name": "input_form", "accepted_values": ["3D", "volumetric", "axial"]},
                {"name": "task", "accepted_values": ["report generation"]},
            ],
            "exclusion_signals": ["PET/CT", "2D-only input"],
        }
    )
    results = []
    for case in cases:
        text = case["text"]
        missing = case.get("missing_facet")
        evidence = {
            "anatomy": "chest",
            "modality": "CT",
            "input_form": next(
                (
                    value
                    for value in ("3D", "volumetric", "volume", "axial")
                    if value in text
                ),
                "",
            ),
            "task": next(
                (value for value in ("report generation", "generates", "generate") if value in text),
                "",
            ),
        }
        facets = [
            {"facet": name, "matched": True, "reason": "matched", "evidence": value}
            for name, value in evidence.items()
            if name != missing and value
        ]
        facets.extend(
            {
                "facet": name,
                "matched": False,
                "reason": "not established",
                "evidence": "",
            }
            for name in evidence
            if name == missing or not evidence[name]
        )
        matched_exclusion = case.get("matched_exclusion")
        exclusions = [
            {
                "exclusion": signal,
                "matched": signal == matched_exclusion,
                "reason": "matched" if signal == matched_exclusion else "absent",
                "evidence": signal if signal == matched_exclusion else "",
            }
            for signal in criteria.exclusion_signals
        ]
        requested = (
            SourceScopeRole.SUPPORTING_BENCHMARK
            if case["role"] == SourceScopeRole.SUPPORTING_BENCHMARK.value
            else SourceScopeRole.PRIMARY_IN_SCOPE
        )
        results.append(
            _validated_scope_role(
                criteria,
                requested,
                facets,
                exclusions,
                text,
                "fixture classification",
            ).value
        )

    assert results.count(SourceScopeRole.PRIMARY_IN_SCOPE.value) == 11
    assert results.count(SourceScopeRole.SUPPORTING_BENCHMARK.value) == 2
    assert results.count(SourceScopeRole.EXCLUDED.value) == 2
    assert results.count(SourceScopeRole.NEAR_SCOPE.value) == 2


def test_collection_budget_counts_only_active_search_and_acquisition_time():
    state = {
        "protocol": ResearchProtocol(
            title="Collection budget",
            primary_question="Which evidence answers this research question?",
            budget={"max_wall_minutes": 1},
        ).model_dump(mode="json"),
        "budget_started_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
        "collection_elapsed_seconds": 10.0,
        "collection_round_started_at": (
            datetime.now(UTC) - timedelta(seconds=20)
        ).isoformat(),
    }

    remaining = ResearchPipeline._collection_seconds_remaining(state)

    assert 28 <= remaining <= 31


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
async def test_required_sentinel_is_scope_classified_and_excluded_source_is_retained():
    await create_schema()
    protocol = ResearchProtocol(
        title="Sentinel scope classification",
        primary_question="Which systems generate reports from volumetric chest CT?",
        research_mode="literature_scan",
        scope_criteria={
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["chest"]},
                {"name": "modality", "accepted_values": ["CT"]},
                {"name": "input_form", "accepted_values": ["3D", "volumetric"]},
                {"name": "task", "accepted_values": ["report generation"]},
            ],
            "exclusion_signals": ["PET/CT"],
        },
        budget={"max_wall_minutes": 30},
        hitl={"source_review": False},
    )
    content = (
        "This study generates radiology reports from volumetric chest CT acquisitions. "
        "The excluded comparator uses whole-body PET/CT for report generation. "
    ) * 8
    candidate = ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.ACADEMIC,
        title="Whole-body PET/CT report generator",
        url="https://example.com/pet-report",
        metadata={"sentinel_required": True},
    )
    document = AcquiredDocument(
        candidate=candidate,
        success=True,
        access_status="open",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        acquisition_method="fixture",
    )

    class MemoryStore:
        async def put(self, *_args, **_kwargs):
            return None

    judged: list[str] = []

    async def classify(_protocol, acquired):
        judged.append(acquired.candidate.title)
        acquired.candidate.metadata["research_scope_role"] = "excluded"
        acquired.candidate.metadata["scope_assessment"] = {
            "role": "excluded",
            "reason": "PET/CT exclusion is explicit",
        }
        return True, 0.95, "direct: relevant but excluded by scope"

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        settings = get_settings().model_copy(update={"testing": False})
        pipeline = ResearchPipeline(settings, session, client)
        pipeline.store = MemoryStore()
        pipeline._semantic_source_judgment = classify

        result = await pipeline.normalize(
            {
                "run_id": row.id,
                "protocol": protocol.model_dump(mode="json"),
                "documents": [document.model_dump(mode="json")],
                "sub_questions": [],
            }
        )
        sources = await repo.list_sources(row.id)
        versions = await repo.list_source_versions(row.id)

    assert judged == [candidate.title]
    assert result["documents"] == []
    assert len(sources) == len(versions) == 1
    assert sources[0].metadata_json["research_scope_role"] == "excluded"
    assert sources[0].metadata_json["evidence_eligible"] is False


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
            "collection_elapsed_seconds": 120.0,
        })
        pipeline = ResearchPipeline(get_settings(), session, client)
        result = await pipeline.search({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "collection_elapsed_seconds": 120.0,
        })
        events = await repo.events_after(row.id)

    assert result["candidates"] == []
    assert any(
        event.event_type == "collection_budget_exhausted"
        and event.payload["action"] == "skip_new_discovery"
        for event in events
    )


@pytest.mark.asyncio
async def test_search_hands_the_open_collection_marker_to_acquisition():
    """SEARCH must return the marker, not only write it onto its local state dict.

    The graph merges node return values into state.  While the marker was set in place
    only, the stage checkpoint showed it -- that dump is taken from the same local dict --
    but ACQUIRE received the previous, empty value and closed every round against it.
    `collection_elapsed_seconds` then stayed at 0.0 for the whole run, so the wall budget
    never fired and a literature scan, whose round cap is deliberately disabled, lost its
    only time-based stop condition.
    """
    await create_schema()
    protocol = ResearchProtocol(
        title="Collection marker handover",
        primary_question="Does the collection marker survive the hop to acquisition?",
        budget={"max_wall_minutes": 180},
    )

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)

        async def search_without_connectors(state):
            return {"candidates": [], "corpus_documents": [], "branch_result_counts": {}}

        pipeline._search_node = search_without_connectors
        state = {
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "collection_elapsed_seconds": 0.0,
            "collection_round_started_at": "",
        }

        search_update = await pipeline.search(state)
        assert search_update["collection_round_started_at"], (
            "SEARCH returned no collection marker, so ACQUIRE cannot close the round"
        )

        # Exactly what the graph does between the two nodes.
        state.update(search_update)
        await asyncio.sleep(0.05)
        acquire_update = await pipeline._acquire_node(state)

    assert acquire_update["collection_elapsed_seconds"] > 0.0
    assert acquire_update["collection_round_started_at"] == ""


@pytest.mark.asyncio
async def test_collection_marker_is_not_restarted_by_a_second_search_in_one_round():
    """A round already holding a marker keeps it, so its elapsed time is not reset."""
    await create_schema()
    protocol = ResearchProtocol(
        title="Collection marker continuity",
        primary_question="Does an open collection round keep its original start time?",
        budget={"max_wall_minutes": 180},
    )
    opened_at = (datetime.now(UTC) - timedelta(seconds=45)).isoformat()

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)

        async def search_without_connectors(state):
            return {"candidates": [], "corpus_documents": [], "branch_result_counts": {}}

        pipeline._search_node = search_without_connectors
        search_update = await pipeline.search({
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "collection_elapsed_seconds": 0.0,
            "collection_round_started_at": opened_at,
        })

    assert search_update["collection_round_started_at"] == opened_at


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
            "collection_elapsed_seconds": 59.7,
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
        diagnostics = await repo.events_by_types(row.id, {
            "connector_call", "acquisition_call", "source_decision", "audit_claim",
            "audit_summary", "coverage_snapshot", "appraisal_claim", "synthesis_generation",
        })
        assert {event.event_type for event in diagnostics} == {
            "connector_call", "acquisition_call", "source_decision", "audit_claim",
            "audit_summary", "coverage_snapshot", "appraisal_claim", "synthesis_generation",
        }
        assert all(event.payload["visit_id"] and event.payload["schema_version"] == 1
                   for event in diagnostics)
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
        connector_error = next(
            event for event in events if event.event_type == "connector_error"
        )
        assert connector_error.payload["compiled_query"]
        assert connector_error.payload["provider_query"] == connector_error.payload[
            "compiled_query"
        ]


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


def _organlens_kriterleri() -> ResearchScopeCriteria:
    """Run 01M1XQTGQEFT08K2F0S0YP3665's approved scope, verbatim."""
    return ResearchScopeCriteria.model_validate(
        {
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["lung"]},
                {"name": "modality", "accepted_values": ["CT"]},
                {"name": "input_form", "accepted_values": ["3D"]},
            ],
            "exclusion_signals": [
                "2D-only input",
                "single-slice input",
                "PET/CT unless CT-only image input is evaluated separately",
            ],
        }
    )


_ORGANLENS_METIN = (
    "OrganLens: Organ-Specific Representation Learning for CT Foundation Models. "
    "An organ identity conditions a shared CT encoder, while organ-specific distillation "
    "and anatomy-mask supervision shape features for anatomy-weighted pooling."
)
_ORGANLENS_FACETS = [
    {
        "facet": "anatomy",
        "matched": True,
        "reason": "chest CT includes lung",
        "evidence": "Organ-Specific Representation Learning",
    },
    {
        "facet": "modality",
        "matched": True,
        "reason": "CT foundation model",
        "evidence": "a shared CT encoder",
    },
    {
        "facet": "input_form",
        "matched": True,
        "reason": "volumetric",
        "evidence": "anatomy-weighted pooling",
    },
]


def test_merged_exclusion_label_no_longer_discards_an_in_scope_source():
    """OrganLens was downgraded for wording alone; EXACT passed only by echoing labels."""
    merged = [
        # The label the model actually returned, standing for two approved signals.
        {
            "exclusion": "2D-only or single-slice input",
            "matched": False,
            "reason": "the model operates on 3D volumetric CT",
            "evidence": "",
        },
        {
            "exclusion": "PET/CT unless CT-only image input is evaluated separately",
            "matched": False,
            "reason": "CT only",
            "evidence": "",
        },
    ]

    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        _ORGANLENS_FACETS,
        merged,
        _ORGANLENS_METIN,
        "direct: meets all required criteria",
    ) == SourceScopeRole.PRIMARY_IN_SCOPE


def test_invented_exclusion_label_is_ignored_not_counted():
    """The model also returned 'X-ray (CXR) input', which no approved signal names."""
    invented_only = [
        {"exclusion": "X-ray (CXR) input", "matched": False, "reason": "CT", "evidence": ""},
    ]

    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        _ORGANLENS_FACETS,
        invented_only,
        _ORGANLENS_METIN,
        "direct: meets all required criteria",
    ) == SourceScopeRole.NEAR_SCOPE


def test_merged_label_may_complete_a_decision_but_never_prove_an_exclusion():
    """`A or B: matched=true` asserts a per-signal finding the model never made."""
    merged_hit = [
        {
            "exclusion": "2D-only or single-slice input",
            "matched": True,
            "reason": "single slice",
            "evidence": "a shared CT encoder",
        },
        {
            "exclusion": "PET/CT unless CT-only image input is evaluated separately",
            "matched": False,
            "reason": "CT only",
            "evidence": "",
        },
    ]

    # Not EXCLUDED: the merged label cannot carry an exclusion for either signal, and with
    # the decision left incomplete the source is held for inspection.
    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        _ORGANLENS_FACETS,
        merged_hit,
        _ORGANLENS_METIN,
        "direct: meets all required criteria",
    ) == SourceScopeRole.NEAR_SCOPE


def test_verbatim_exclusion_label_still_proves_an_exclusion():
    """Fix 1 must not weaken the path that removes a genuinely excluded source."""
    exact_hit = [
        {
            "exclusion": "2D-only input",
            "matched": True,
            "reason": "single axial slice",
            "evidence": "a shared CT encoder",
        },
        {"exclusion": "single-slice input", "matched": False, "reason": "n/a", "evidence": ""},
        {
            "exclusion": "PET/CT unless CT-only image input is evaluated separately",
            "matched": False,
            "reason": "CT only",
            "evidence": "",
        },
    ]

    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        _ORGANLENS_FACETS,
        exact_hit,
        _ORGANLENS_METIN,
        "direct:",
    ) == SourceScopeRole.EXCLUDED


def test_ambiguous_exclusion_fragment_decides_nothing():
    """'input' fits both approved signals, so it may not stand for either."""
    ambiguous = [
        {"exclusion": "input", "matched": False, "reason": "vague", "evidence": ""},
        {
            "exclusion": "PET/CT unless CT-only image input is evaluated separately",
            "matched": False,
            "reason": "CT only",
            "evidence": "",
        },
    ]

    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        _ORGANLENS_FACETS,
        ambiguous,
        _ORGANLENS_METIN,
        "direct:",
    ) == SourceScopeRole.NEAR_SCOPE


def test_empty_facet_evidence_downgrades_when_no_accepted_value_is_present():
    """Supersedes run 01M1XQ's "Fix 1 is deliberately narrow" scope for this case.

    An empty quote is no longer fatal on its own -- the accepted-value route can prove a
    facet the model answered without quoting. It is fatal here because none of OrganLens's
    accepted values ("lung", "3D") appear in the text either, so neither route reaches it.
    """
    no_evidence = [dict(item, evidence="") for item in _ORGANLENS_FACETS]
    clean = [
        {"exclusion": signal, "matched": False, "reason": "absent", "evidence": ""}
        for signal in _organlens_kriterleri().exclusion_signals
    ]

    assert _validated_scope_role(
        _organlens_kriterleri(),
        SourceScopeRole.PRIMARY_IN_SCOPE,
        no_evidence,
        clean,
        _ORGANLENS_METIN,
        "direct:",
    ) == SourceScopeRole.NEAR_SCOPE


class PromptYakalayanJudgeLLM:
    """Keeps the system prompt so a test can assert what the judge was actually told."""

    def __init__(self):
        self.system_prompts: list[str] = []

    async def complete_json(self, system_prompt, user_prompt):
        self.system_prompts.append(system_prompt)
        return {"directly_relevant": True, "relevance_score": 0.9, "reason": "direct:"}


@pytest.mark.asyncio
async def test_scope_prompt_enumerates_every_exclusion_signal_verbatim():
    """A reworded or merged label costs the source its scope; spell the list out."""
    protocol = ResearchProtocol(
        title="Scope prompt",
        primary_question="Which 3D lung CT foundation models exist?",
        budget={"max_wall_minutes": 30},
        scope_criteria={
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["lung"]},
                {"name": "modality", "accepted_values": ["CT"]},
            ],
            "exclusion_signals": [
                "2D-only input",
                "single-slice input",
                "PET/CT unless CT-only image input is evaluated separately",
            ],
        },
    )
    document = AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.ACADEMIC,
            title="Fixture publication",
            url="https://example.com/publication",
        ),
        success=True,
        content="Publication content",
        content_type="text/plain",
        acquisition_method="fixture",
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        judge = PromptYakalayanJudgeLLM()
        pipeline.llm = judge
        await pipeline._semantic_source_judgment(protocol, document)

    assert judge.system_prompts
    prompt = judge.system_prompts[0]
    for index, signal in enumerate(protocol.scope_criteria.exclusion_signals, 1):
        assert f"  {index}. {signal}" in prompt, f"{signal!r} is not spelled out"
    assert "Never merge two signals" in prompt
    assert "EVIDENCE IS MANDATORY" in prompt


@pytest.mark.asyncio
async def test_scope_prompt_is_absent_without_approved_scope_criteria():
    """A run with no scope contract must not be told to fill scope fields."""
    protocol = ResearchProtocol(
        title="No scope",
        primary_question="What recent CT models estimate lung cancer risk?",
        budget={"max_wall_minutes": 30},
    )
    document = AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.ACADEMIC,
            title="Fixture publication",
            url="https://example.com/publication",
        ),
        success=True,
        content="Publication content",
        content_type="text/plain",
        acquisition_method="fixture",
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        judge = PromptYakalayanJudgeLLM()
        pipeline.llm = judge
        await pipeline._semantic_source_judgment(protocol, document)

    assert "EVIDENCE IS MANDATORY" not in judge.system_prompts[0]
    assert "exclusion_assessments" not in judge.system_prompts[0]


class KapsamKararliJudgeLLM:
    """Answers the way the 4B judge did in run 01M203: reworded facet, reformatted quote."""

    def __init__(self, payload: dict):
        self.payload = payload

    async def complete_json(self, system_prompt, user_prompt):
        return self.payload


CT2REP_ICERIK = (
    "CT2Rep: Automated Radiology Report Generation for 3D Medical Imaging. "
    "We introduce the first method to generate radiology reports for 3D chest CT volumes."
)


def _ct2rep_belge() -> AcquiredDocument:
    return AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.ACADEMIC,
            title="CT2Rep",
            url="https://example.com/ct2rep",
        ),
        success=True,
        content=CT2REP_ICERIK,
        content_type="text/plain",
        acquisition_method="fixture",
    )


def _ct2rep_protokol() -> ResearchProtocol:
    return ResearchProtocol(
        title="Scope diagnostics",
        primary_question="Which 3D chest CT models generate radiology reports?",
        budget={"max_wall_minutes": 30},
        scope_criteria={
            "required_facets": [
                {"name": "modality", "accepted_values": ["CT"]},
                {"name": "application_task", "accepted_values": ["report generation"]},
            ],
            "exclusion_signals": ["PET/CT"],
        },
    )


@pytest.mark.asyncio
async def test_scope_assessment_records_the_deterministic_decision_it_acted_on():
    """The 89-source correction, end to end, with the diagnostics that would have found it.

    Run 01M203 recorded neither `requested_role` nor why a facet failed, so the cause had to
    be reconstructed offline from `source_versions`. Everything needed is now in the event.
    """
    document = _ct2rep_belge()
    judge = KapsamKararliJudgeLLM(
        {
            "directly_relevant": True,
            "relevance_score": 0.9,
            "reason": "direct: generates reports from 3D chest CT",
            # The model downgrades itself, names the facet its own way, and reformats the
            # quote it is copying. Each of the three used to be fatal on its own.
            "scope_role": "near_scope",
            "facet_assessments": [
                {
                    "facet": "modality",
                    "matched": True,
                    "reason": "chest CT",
                    "evidence": "3D chest CT volumes",
                },
                {
                    "facet": "Application Task",
                    "matched": True,
                    "reason": "report generation",
                    "evidence": "CT2Rep - Automated Radiology Report Generation",
                },
            ],
            "exclusion_assessments": [
                {"exclusion": "PET/CT", "matched": False, "reason": "CT only", "evidence": ""},
            ],
        }
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = judge
        await pipeline._semantic_source_judgment(_ct2rep_protokol(), document)

    assessment = document.candidate.metadata["scope_assessment"]
    assert assessment["role"] == SourceScopeRole.PRIMARY_IN_SCOPE.value
    assert document.candidate.metadata["research_scope_role"] == (
        SourceScopeRole.PRIMARY_IN_SCOPE.value
    )
    assert assessment["requested_role"] == SourceScopeRole.NEAR_SCOPE.value
    assert assessment["role_source"] == "deterministic"
    assert assessment["proof_schema"] == 1
    assert assessment["proven_facets"] == ["modality", "application task"]
    assert assessment["unproven_facets"] == []
    assert "role_promoted_from:near_scope" in assessment["role_reasons"]

    # A folded name means one entry per facet: the backfill no longer writes a second,
    # undecided copy under the canonical spelling.
    facets = assessment["facet_assessments"]
    assert len(facets) == 2
    by_key = {item["facet_key"]: item for item in facets}
    assert by_key["modality"]["proof_route"] == "verbatim"
    assert by_key["application task"]["proof_route"] == "normalized"
    assert by_key["application task"]["facet"] == "Application Task", "recorded as written"
    assert by_key["modality"]["value_present"] is True

    exclusion = assessment["exclusion_assessments"][0]
    assert exclusion["exclusion_key"] == "pet ct"
    assert exclusion["proof_route"] == "unproven"


@pytest.mark.asyncio
async def test_an_undecided_facet_is_backfilled_and_named_in_the_diagnostics():
    """The other direction: what the model left out must still be visible and still bar it."""
    document = _ct2rep_belge()
    judge = KapsamKararliJudgeLLM(
        {
            "directly_relevant": True,
            "relevance_score": 0.9,
            "reason": "direct:",
            "scope_role": "primary_in_scope",
            "facet_assessments": [
                {
                    "facet": "modality",
                    "matched": True,
                    "reason": "chest CT",
                    "evidence": "3D chest CT volumes",
                },
            ],
            "exclusion_assessments": [
                {"exclusion": "PET/CT", "matched": False, "reason": "CT only", "evidence": ""},
            ],
        }
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = judge
        await pipeline._semantic_source_judgment(_ct2rep_protokol(), document)

    assessment = document.candidate.metadata["scope_assessment"]
    assert assessment["role"] == SourceScopeRole.NEAR_SCOPE.value
    assert "facet_decision_missing:application task" in assessment["role_reasons"]
    backfilled = next(
        item for item in assessment["facet_assessments"] if item["matched"] is None
    )
    assert backfilled["facet"] == "application_task"
    assert backfilled["reason"] == "model_decision_missing"
    assert backfilled["proof_route"] == "unproven"


async def _normalize_ineligible_document(*, settings_policy: int, state_policy: int | None):
    """NORMALIZE one excluded document that points at two external links.

    Returns (frontier_rows, discovery_shadow_payloads). The document is excluded by an
    explicit scope signal, so it never enters chunking or the evidence quota either way;
    the only thing under test is what happens to the links it points at.
    """
    await create_schema()
    protocol = ResearchProtocol(
        title="Discovery contribution of an excluded source",
        primary_question="Which systems generate reports from volumetric chest CT?",
        research_mode="literature_scan",
        scope_criteria={
            "required_facets": [
                {"name": "anatomy", "accepted_values": ["chest"]},
                {"name": "modality", "accepted_values": ["CT"]},
            ],
            "exclusion_signals": ["PET/CT"],
        },
        budget={"max_wall_minutes": 30},
        hitl={"source_review": False},
    )
    content = (
        "This survey of whole-body PET/CT report generation indexes the primary "
        "volumetric chest CT studies it compares. "
    ) * 8
    document = AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="fixture",
            family=SourceFamily.ACADEMIC,
            title="A survey that is excluded but indexes the field",
            url="https://survey.example/review",
        ),
        success=True,
        access_status="open",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        acquisition_method="fixture",
        outgoing_links=[
            "https://primary.example/study-one",
            "https://primary.example/study-two",
        ],
    )

    class MemoryStore:
        async def put(self, *_args, **_kwargs):
            return None

    async def classify(_protocol, acquired):
        acquired.candidate.metadata["research_scope_role"] = "excluded"
        acquired.candidate.metadata["scope_assessment"] = {
            "role": "excluded",
            "reason": "PET/CT exclusion is explicit",
        }
        return True, 0.95, "direct: relevant but excluded by scope"

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        settings = get_settings().model_copy(
            update={"testing": False, "admission_policy_version": settings_policy}
        )
        pipeline = ResearchPipeline(settings, session, client)
        pipeline.store = MemoryStore()
        pipeline._semantic_source_judgment = classify

        state = {
            "run_id": row.id,
            "protocol": protocol.model_dump(mode="json"),
            "documents": [document.model_dump(mode="json")],
            "sub_questions": [],
        }
        if state_policy is not None:
            state["admission_policy_version"] = state_policy
        result = await pipeline.normalize(state)

        frontier = list(
            await session.scalars(
                select(FrontierRow).where(FrontierRow.run_id == row.id)
            )
        )
        shadow = [
            event.payload
            for event in await repo.events_by_types(row.id, {"discovery_shadow"})
        ]
    # The document is excluded either way: it must never reach chunking.
    assert result["documents"] == []
    return frontier, shadow


@pytest.mark.asyncio
async def test_excluded_source_discovery_is_measured_but_not_harvested_under_policy_1():
    """Policy 1 is today's behaviour, and the shadow record is how we price policy 2.

    The links are walked through the identical code path -- canonicalised, deduped,
    checked against this run's frontier -- and then thrown away. Nothing is written, so
    a live run costs exactly what it costs today, but `frontier_links` says precisely
    what switching the policy on would have admitted.
    """
    frontier, shadow = await _normalize_ineligible_document(
        settings_policy=1, state_policy=None
    )
    assert frontier == []
    assert len(shadow) == 1
    record = shadow[0]
    assert record["dropped_as"] == "scope_ineligible"
    assert record["role"] == "excluded"
    assert record["outgoing_links"] == 2
    assert record["frontier_links"] == 2
    assert record["harvested"] is False
    assert record["admission_policy_version"] == 1


@pytest.mark.asyncio
async def test_excluded_source_links_are_harvested_under_policy_2():
    """Policy 2 keeps the document out of evidence but takes the map it was holding."""
    frontier, shadow = await _normalize_ineligible_document(
        settings_policy=2, state_policy=None
    )
    assert {row.canonical_url for row in frontier} == {
        "https://primary.example/study-one",
        "https://primary.example/study-two",
    }
    assert shadow[0]["harvested"] is True
    assert shadow[0]["frontier_links"] == 2
    assert shadow[0]["admission_policy_version"] == 2


@pytest.mark.asyncio
async def test_pinned_policy_in_state_beats_the_current_setting():
    """The resume guarantee.

    A run pinned to policy 1 and preempted keeps admitting sources by policy 1 when it
    resumes, even though the operator has since switched the setting to 2. Without this
    half a run's sources would be admitted under one rule and half under another, and
    the recorded provenance would not say which.
    """
    frontier, shadow = await _normalize_ineligible_document(
        settings_policy=2, state_policy=1
    )
    assert frontier == []
    assert shadow[0]["harvested"] is False
    assert shadow[0]["admission_policy_version"] == 1


@pytest.mark.asyncio
async def test_frontier_dry_run_counts_exactly_what_a_real_call_would_add():
    """The shadow measurement is only worth having if it is exact.

    dry_run must walk the same path -- hostless links skipped, duplicates collapsed,
    cap applied, links already in this run's frontier not counted twice -- and write
    nothing. If it ever diverges, every shadow number we use to price a policy change
    silently becomes fiction.
    """
    await create_schema()
    links = [
        "mailto:someone@example.org",
        "https://example.org/next",
        "https://example.org/next",
        "https://other.example/page",
    ]
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(ResearchProtocol(
            title="Frontier dry run",
            primary_question="Does a dry run count what a real call would add?",
            budget={"max_wall_minutes": 30},
        ))

        predicted = await repo.add_frontier_links(
            run.id, "https://example.org/article", links, max_links=10, dry_run=True
        )
        after_dry = list(
            await session.scalars(select(FrontierRow).where(FrontierRow.run_id == run.id))
        )
        assert after_dry == [], "dry_run wrote rows"

        actual = await repo.add_frontier_links(
            run.id, "https://example.org/article", links, max_links=10
        )
        assert predicted == actual == 2

        # And once they are really there, a second dry run must predict zero rather
        # than re-counting links the frontier already holds.
        assert await repo.add_frontier_links(
            run.id, "https://example.org/article", links, max_links=10, dry_run=True
        ) == 0
