import hashlib

import pytest

from research_platform.db import SessionLocal, create_schema
from research_platform.recovery import (
    diagnose_gaps,
    initial_missions,
    matches_target_entities,
    mission_signature,
    recovery_missions,
    select_mission_balanced_candidates,
)
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    CoverageMetrics,
    ResearchProtocol,
    RunStatus,
    SearchMission,
    SourceFamily,
)


def official_protocol() -> ResearchProtocol:
    return ResearchProtocol(
        title="Official integration research",
        primary_question=(
            "Codex, Claude Code ve Telegram üzerinden MCP tabanlı araştırma servisi "
            "nasıl güvenli kurulmalı? Resmi dokümantasyon kullan."
        ),
        connectors={
            "profile": "custom",
            "included_families": ["web", "official_legal", "code_data"],
        },
        budget={"max_sources": 12},
    )


@pytest.mark.asyncio
async def test_repository_refreshes_run_status_changed_by_another_session():
    await create_schema()
    protocol = official_protocol()
    async with SessionLocal() as worker_session:
        worker_repo = Repository(worker_session)
        run = await worker_repo.create_run(protocol)
        cached = await worker_repo.get_run(run.id)
        assert cached.status == RunStatus.QUEUED.value

        async with SessionLocal() as api_session:
            api_repo = Repository(api_session)
            await api_repo.update_run(run.id, status=RunStatus.CANCEL_REQUESTED.value)

        refreshed = await worker_repo.get_run(run.id)
        assert refreshed.status == RunStatus.CANCEL_REQUESTED.value


def test_initial_missions_resolve_named_entities_to_official_domains():
    missions = initial_missions(official_protocol(), ["secure MCP integration"])
    domains = {
        domain
        for mission in missions
        for domain in mission.domain_allowlist
    }
    assert "modelcontextprotocol.io" in domains
    assert "developers.openai.com" in domains
    assert "code.claude.com" in domains
    assert "core.telegram.org" in domains
    assert all(
        mission.required_family == SourceFamily.OFFICIAL_LEGAL
        for mission in missions if mission.domain_allowlist
    )
    seed_urls = {str(url) for mission in missions for url in mission.seed_urls}
    assert (
        "https://modelcontextprotocol.io/docs/tutorials/security/authorization"
        in seed_urls
    )
    assert "https://developers.openai.com/codex/mcp/" in seed_urls
    assert "https://code.claude.com/docs/en/mcp" in seed_urls
    assert "https://core.telegram.org/bots/api" in seed_urls
    assert "https://github.com/openai/codex" in seed_urls


def test_uncovered_branch_recovery_preserves_original_branch_id():
    protocol = official_protocol()
    gaps = diagnose_gaps(
        protocol,
        CoverageMetrics(query_branch_coverage=0.5, authority_coverage=1.0),
        ["web", "official_legal"],
        [],
        {"query:0": 1, "query:1": 0},
        {"query:0": "covered query", "query:1": "missing security evidence"},
    )
    gap = next(item for item in gaps if item.branch_id == "query:1")
    missions = recovery_missions(protocol, [gap], set())
    assert missions[0].branch_id == "query:1"
    assert "missing security evidence" in missions[0].query


def test_code_branch_recovery_uses_entity_seed_and_rejects_generic_agentic_result():
    protocol = official_protocol()
    gaps = diagnose_gaps(
        protocol,
        CoverageMetrics(query_branch_coverage=0.5, authority_coverage=1.0),
        ["web", "official_legal", "code_data"],
        [],
        {"code:OpenAI Codex": 0},
        {"code:OpenAI Codex": "OpenAI Codex official source repository security"},
    )
    gap = next(item for item in gaps if item.branch_id == "code:OpenAI Codex")
    mission = recovery_missions(protocol, [gap], set())[0]
    assert str(mission.seed_urls[0]) == "https://github.com/openai/codex"
    assert mission.required_authority == "primary"
    assert matches_target_entities("GitHub openai/codex", mission.target_entities)
    assert not matches_target_entities(
        "SENTINEL sovereign autonomous attribution forensics",
        mission.target_entities,
    )


def test_recovery_does_not_repeat_attempted_mission_signature():
    protocol = official_protocol()
    gaps = diagnose_gaps(
        protocol,
        CoverageMetrics(authority_coverage=0.0),
        ["web"],
        [],
    )
    first = recovery_missions(protocol, gaps, set())
    attempted = {mission_signature(mission) for mission in first}
    second = recovery_missions(protocol, gaps, attempted)
    assert second == []


def test_saturation_probe_is_added_after_branch_threshold_is_met():
    protocol = official_protocol()
    protocol.stopping_criteria.minimum_query_branch_coverage = 0.8
    gaps = diagnose_gaps(
        protocol,
        CoverageMetrics(
            query_branch_coverage=0.8,
            authority_coverage=1.0,
            saturated_rounds=0,
        ),
        ["web", "official_legal", "code_data"],
        [],
        {"query:0": 1, "query:1": 0},
        {"query:0": "covered", "query:1": "uncovered"},
    )
    assert any("saturation probe 1" in gap.topic for gap in gaps)


def test_candidate_selection_reserves_capacity_across_missions():
    missions = [
        SearchMission(branch_id="official:a", query="a", acquisition_slots=1),
        SearchMission(branch_id="query:b", query="b", acquisition_slots=1),
    ]
    candidates = [
        ConnectorCandidate(
            connector_id="web",
            family="web",
            title="A1",
            url="https://example.com/a1",
            metadata={"query_branches": ["official:a"]},
        ),
        ConnectorCandidate(
            connector_id="web",
            family="web",
            title="A2",
            url="https://example.com/a2",
            metadata={"query_branches": ["official:a"]},
        ),
        ConnectorCandidate(
            connector_id="web",
            family="web",
            title="B1",
            url="https://example.com/b1",
            metadata={"query_branches": ["query:b"]},
        ),
    ]
    selected = select_mission_balanced_candidates(candidates, missions, 2)
    assert {candidate.title for candidate in selected} == {"A1", "B1"}


@pytest.mark.asyncio
async def test_novelty_filter_enriches_existing_source_without_reacquisition():
    await create_schema()
    protocol = official_protocol()
    async with SessionLocal() as session:
        repo = Repository(session)
        run = await repo.create_run(protocol)
        original = ConnectorCandidate(
            connector_id="agentsearch_web",
            family="web",
            title="MCP security",
            url="https://modelcontextprotocol.io/docs/security",
            metadata={"query_branches": ["query:0"], "authority": "unknown"},
        )
        content = "Official MCP security documentation."
        await repo.save_document(
            run.id,
            AcquiredDocument(
                candidate=original,
                success=True,
                access_status="open",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                acquisition_method="fixture",
            ),
        )
        targeted = original.model_copy(deep=True)
        targeted.metadata = {
            "query_branches": ["official:Model Context Protocol"],
            "authority": "official",
        }
        novel, rejected = await repo.filter_novel_candidates(run.id, [targeted])
        assert novel == []
        assert rejected[0]["reason"] == "existing_source"
        source = (await repo.list_sources(run.id))[0]
        assert source.metadata_json["authority"] == "official"
        assert set(source.metadata_json["query_branches"]) == {
            "query:0", "official:Model Context Protocol",
        }
