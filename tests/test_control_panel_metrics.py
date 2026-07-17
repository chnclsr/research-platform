from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_platform.control_panel_metrics import (
    connector_operations,
    llm_summary,
    query_branch_summary,
    source_funnel,
    stage_timeline,
)


def event(event_type: str, payload: dict, second: int = 0) -> dict:
    return {
        "id": second + 1,
        "event_type": event_type,
        "payload": payload,
        "created_at": datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=second),
    }


def test_stage_timeline_reports_round_and_duration():
    rows = [
        event("stage", {"stage": "SEARCH", "round": 1}, 0),
        event("stage", {"stage": "ACQUIRE", "round": 1}, 12),
    ]
    timeline = stage_timeline(
        rows, datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=20),
    )
    assert timeline[0]["duration_seconds"] == 12
    assert timeline[1]["duration_seconds"] == 8
    assert timeline[1]["active"] is True


def test_source_funnel_aggregates_filters_and_admission():
    rows = [
        event("connector_metrics", {"calls": [
            {"connector": "crossref", "result_count": 10, "success": True},
            {"connector": "arxiv", "result_count": 5, "success": True},
        ]}),
        event("novelty_filter", {"rejected_count": 3}),
        event("temporal_scope_filter", {"rejected_count": 2}),
        event("acquisition_metrics", {"calls": [
            {"success": True}, {"success": False}, {"success": True},
        ]}),
        event("content_relevance_filter", {"rejected_count": 1}),
        event("coverage_gaps", {"discovery_quality": {
            "accepted_candidates": 8, "reserve_selected": 2, "hard_rejected": 4,
        }}),
    ]
    funnel = source_funnel(rows, final_sources=1)
    assert [step["value"] for step in funnel["steps"]] == [15, 12, 10, 3, 2, 1]
    assert funnel["admission"] == {"accept": 8, "reserve": 2, "reject": 4}


def test_connector_operations_exposes_success_rate_latency_and_error_classes():
    rows = [
        event("connector_metrics", {"calls": [
            {"connector": "semantic_scholar", "success": True,
             "result_count": 3, "latency_seconds": 1.0},
            {"connector": "semantic_scholar", "success": False,
             "result_count": 0, "latency_seconds": 3.0},
        ]}, 1),
        event("connector_error", {
            "connector": "semantic_scholar", "error": "HTTP 429 throttled",
        }, 2),
    ]
    row = connector_operations(rows)["semantic_scholar"]
    assert row["success_rate"] == 0.5
    assert row["average_latency_seconds"] == 2.0
    assert row["error_types"] == {"429": 1}


def test_query_and_llm_summaries_are_run_auditable():
    rows = [
        event("connector_metrics", {"calls": [{
            "branch_id": "query:0", "query": "lung CT", "connector": "crossref",
            "success": True, "result_count": 4, "latency_seconds": 1.5,
        }]}),
        event("llm_metrics", {"calls": [{
            "model": "qwen", "prompt_tokens": 100, "completion_tokens": 20,
            "generation_seconds": 2.0, "wall_seconds": 2.5,
        }]}),
    ]
    assert query_branch_summary(rows)[0]["result_count"] == 4
    summary = llm_summary(rows)
    assert summary["tokens_per_second"] == 10.0
    assert summary["models"] == ["qwen"]
