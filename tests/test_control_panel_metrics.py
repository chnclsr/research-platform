from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_platform.control_panel_metrics import (
    connector_operations,
    llm_summary,
    pipeline_flow,
    pipeline_progress,
    query_branch_summary,
    source_chain,
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


def tools_by_name(visit: dict) -> dict[str, dict]:
    return {f"{row['kind']}:{row['name']}": row for row in visit["tools"]}


def test_stage_timeline_attributes_tools_to_the_enclosing_stage_visit():
    rows = [
        event("stage", {"stage": "SEARCH", "round": 1}, 0),
        event("connector_metrics", {"calls": [
            {"connector": "crossref", "success": True, "result_count": 7,
             "latency_seconds": 1.5},
            {"connector": "crossref", "success": False, "result_count": 0,
             "latency_seconds": 0.5},
        ]}, 1),
        event("connector_error", {"connector": "crossref", "error": "HTTP 429"}, 2),
        event("stage", {"stage": "ACQUIRE", "round": 1}, 5),
        event("acquisition_metrics", {"calls": [
            {"connector": "crossref", "success": True, "method": "direct",
             "parser_id": "html", "latency_seconds": 2.0},
            {"connector": "crossref", "success": True, "method": "crawl4ai",
             "parser_id": "html", "latency_seconds": 4.0},
            {"connector": "crossref", "success": False, "method": "direct",
             "parser_id": "", "latency_seconds": 1.0},
        ]}, 6),
        event("stage", {"stage": "NORMALIZE", "round": 1}, 9),
        event("llm_metrics", {"stage": "CONTENT_RELEVANCE", "calls": [
            {"model": "qwen", "prompt_tokens": 90, "completion_tokens": 10,
             "wall_seconds": 3.0},
        ]}, 10),
        event("embedding_metrics", {"stage": "CHUNK_INDEX", "calls": [
            {"model": "nomic", "prompt_tokens": 400, "wall_seconds": 0.5},
        ]}, 11),
    ]
    timeline = stage_timeline(
        rows, datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=12),
    )
    search, acquire, normalize = timeline
    connector = tools_by_name(search)["connector:crossref"]
    assert (connector["calls"], connector["ok"], connector["results"]) == (2, 1, 7)
    assert connector["errors"] == 1
    assert connector["seconds"] == 2.0
    acquire_tools = tools_by_name(acquire)
    assert acquire_tools["method:direct"]["calls"] == 2
    assert acquire_tools["method:crawl4ai"]["ok"] == 1
    # Two documents parsed, and the failed acquisition contributes no parser row.
    assert acquire_tools["parser:html"]["calls"] == 2
    assert [row["kind"] for row in acquire["tools"]] == ["method", "method", "parser"]
    normalize_tools = tools_by_name(normalize)
    # The finer-grained phase label annotates the row; placement follows the stage window.
    assert normalize_tools["model:qwen"]["tokens"] == 100
    assert normalize_tools["model:qwen"]["phases"] == ["CONTENT_RELEVANCE"]
    assert normalize_tools["embedding:nomic"]["tokens"] == 400


def test_stage_timeline_keeps_repeated_visits_of_a_stage_separate():
    rows = [
        event("stage", {"stage": "SEARCH", "round": 1}, 0),
        event("connector_metrics", {"calls": [
            {"connector": "crossref", "success": True, "result_count": 4},
        ]}, 1),
        event("stage", {"stage": "SEARCH", "round": 2}, 5),
        event("connector_metrics", {"calls": [
            {"connector": "arxiv", "success": True, "result_count": 9},
        ]}, 6),
    ]
    first, second = stage_timeline(
        rows, datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=8),
    )
    assert [row["name"] for row in first["tools"]] == ["crossref"]
    assert [row["name"] for row in second["tools"]] == ["arxiv"]
    assert second["round"] == 2


def test_stage_timeline_tolerates_runs_recorded_without_parser_ids():
    rows = [
        event("stage", {"stage": "ACQUIRE", "round": 1}, 0),
        event("acquisition_metrics", {"calls": [{"success": True, "method": "direct"}]}, 1),
    ]
    visit = stage_timeline(
        rows, datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=2),
    )[0]
    assert [row["kind"] for row in visit["tools"]] == ["method"]


def test_pipeline_progress_maps_live_stage_and_terminal_completion():
    assert pipeline_progress("INIT", "queued") == 0
    assert 25 <= pipeline_progress("SEARCH", "running") <= 35
    assert pipeline_progress("COMPLETE", "completed_incomplete") == 100


def test_pipeline_flow_marks_completed_active_and_recovery_nodes():
    rows = [
        event("stage", {"stage": "VALIDATE_PROTOCOL", "round": 1}, 0),
        event("stage", {"stage": "SEARCH", "round": 1}, 5),
        event("stage", {"stage": "PLAN_RECOVERY", "round": 1}, 10),
        event("stage", {"stage": "SEARCH", "round": 2}, 15),
        event("stage", {"stage": "ACQUIRE", "round": 2}, 20),
    ]
    flow = pipeline_flow(
        rows,
        current_stage="ACQUIRE",
        status="running",
        round_number=2,
        now=datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(seconds=30),
    )
    nodes = {node["stage"]: node for node in flow["nodes"]}
    assert nodes["SEARCH"]["state"] == "completed"
    assert nodes["SEARCH"]["visits"] == 2
    assert nodes["ACQUIRE"]["state"] == "active"
    assert nodes["SYNTHESIZE_EXPORT"]["state"] == "pending"
    assert flow["has_recovery_loop"] is True


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


def chain_of(**overrides):
    facts = {
        "acquired": True,
        "passage_count": 12,
        "best_retrieval": 0.7,
        "evidence_count": 3,
        "claim_status_ok": True,
        "citation": {"drop_reason": None},
        "exported": True,
    }
    facts.update(overrides)
    return source_chain(**facts)


def test_a_source_that_reached_the_report_has_no_stop():
    result = chain_of()
    assert set(result["chain"].values()) == {"on"}
    assert result["fate"]["code"] == "cited"
    assert result["fate"]["label"] == "Rapora girdi"


def test_the_fate_names_one_stopping_point_not_every_missing_step():
    # A source that was never acquired has not also "failed retrieval". Reporting both would
    # bury the single fact that explains the rest of the row.
    result = chain_of(acquired=False, passage_count=0, best_retrieval=0.0, evidence_count=0,
                      claim_status_ok=False, citation=None)
    assert result["chain"] == {
        "discover": "on", "acquire": "stop", "parse": "off", "retrieve": "off",
        "evidence": "off", "claim": "off", "report": "off",
    }
    assert list(result["chain"].values()).count("stop") == 1
    assert result["fate"]["code"] == "not_acquired"


def test_a_passage_that_was_never_retrieved_stops_at_retrieval():
    result = chain_of(best_retrieval=0.0, evidence_count=0, claim_status_ok=False, citation=None)
    assert result["chain"]["parse"] == "on"
    assert result["chain"]["retrieve"] == "stop"
    assert result["fate"]["code"] == "not_retrieved"


def test_the_export_record_supplies_the_reason_for_the_last_step():
    # The four report-stage reasons are the export's own; the chain cannot derive them.
    result = chain_of(citation={"drop_reason": "offered_not_cited"})
    assert result["chain"]["report"] == "stop"
    assert result["fate"]["code"] == "offered_not_cited"
    assert result["fate"]["label"] == "Kanıt var, atıf yok"


def test_a_run_without_an_export_is_not_reported_as_a_dropped_source():
    # No citation row and no export is a run that has not got there yet. Calling that a
    # dropped source would invent a failure.
    result = chain_of(citation=None, exported=False)
    assert result["fate"]["code"] == "no_export"
    assert result["fate"]["label"] == "Rapor henüz üretilmedi"


def test_evidence_without_an_audited_claim_stops_at_the_claim_step():
    result = chain_of(claim_status_ok=False, citation=None)
    assert result["chain"]["evidence"] == "on"
    assert result["chain"]["claim"] == "stop"
    assert result["fate"]["code"] == "claim_below_threshold"
