"""Historical diagnostics are observable facts, not a new research decision gate."""
from datetime import UTC, datetime

import httpx
import pytest
from conftest import acting_principal
from fastapi import HTTPException
from fastapi.testclient import TestClient

from research_platform import control_panel
from research_platform.auth import Principal
from research_platform.control_panel import _run_detail, _run_stage_detail
from research_platform.control_panel_auth import require_user
from research_platform.coverage import calculate_coverage
from research_platform.db import ClaimRow, EventRow, SessionLocal, create_schema
from research_platform.diagnostics import coverage_checks, error_details, safe_diagnostic
from research_platform.panel_diagnostics import current_claims, event_page
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, new_id


def protocol():
    return ResearchProtocol(title="Panel diagnostics", primary_question="What improves accuracy?",
                            budget={"max_wall_minutes": 5})


@pytest.mark.parametrize("status", [429, 400, 503])
def test_http_failure_has_status_and_safe_reason(status):
    request = httpx.Request("GET", "https://example.org/search?api_key=topsecret")
    response = httpx.Response(status, request=request, headers={"Retry-After": "7"})
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    details = error_details(caught.value)
    assert details["http_status"] == status
    assert details["retry_after"] == "7"
    assert details["error_type"] == "HTTPStatusError"
    assert "topsecret" not in str(details)


def test_timeout_and_nested_credentials():
    assert error_details(httpx.ReadTimeout("timed out"))["error_type"] == "ReadTimeout"
    payload = {"headers": {"Authorization": "Bearer abc", "X-Api-Key": "abc"},
               "token": "abc", "prompt_tokens": 123,
               "error": "Bearer abc https://user:password@example.org?token=abc"}
    masked = safe_diagnostic(payload)
    assert "abc" not in str(masked)
    assert "password" not in masked["error"]
    assert masked["prompt_tokens"] == 123


@pytest.mark.asyncio
async def test_new_routes_enforce_session_and_ownership():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        visit = await repo.event(run.id, "stage", {"stage": "AUDIT"})
        run_id = run.id
    paths = [f"/api/runs/{run_id}/events", f"/api/runs/{run_id}/claims/current",
             f"/api/runs/{run_id}/stages/AUDIT/visits/{visit}"]
    with TestClient(control_panel.app) as client:
        for path in paths:
            assert client.get(path).status_code == 401
        try:
            control_panel.app.dependency_overrides[require_user] = lambda: Principal.user("outsider", "user")
            for path in paths:
                assert client.get(path).status_code == 404
            control_panel.app.dependency_overrides[require_user] = lambda: Principal.user(acting_principal().user_id, "user")
            for path in paths:
                assert client.get(path).status_code == 200
            response = client.get(paths[-1]).json()
            assert response["recorded_state"] == "missing"
            assert not response["history_available"]
        finally:
            control_panel.app.dependency_overrides.pop(require_user, None)


@pytest.mark.asyncio
async def test_visit_identity_and_immutable_audit_with_same_round_and_timestamp():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        first = await repo.event(run.id, "stage", {"stage": "AUDIT", "round": 2})
        await repo.diagnostic_batch(run.id, "audit_claim", [{"claim_id": "c1",
            "previous_status": "unresolved", "status": "qualified"}])
        await repo.event(run.id, "audit_summary", {"claim_count": 1, "statuses": {"qualified": 1}})
        second = await repo.event(run.id, "stage", {"stage": "AUDIT", "round": 2})
        await repo.diagnostic_batch(run.id, "audit_claim", [{"claim_id": "c1",
            "previous_status": "qualified", "status": "supported"}])
        await repo.event(run.id, "audit_summary", {"claim_count": 1, "statuses": {"supported": 1}})
        session.add(ClaimRow(id=new_id(), run_id=run.id, text="Latest claim", importance="major",
                             status="supported"))
        await session.commit()
        run_id = run.id
    one = await event_page(run_id, acting_principal(), stage="AUDIT", visit_id=first)
    two = await event_page(run_id, acting_principal(), stage="AUDIT", visit_id=second)
    assert one["history_available"] and two["history_available"]
    assert next(e for e in one["events"] if e["type"] == "audit_claim")["payload"]["status"] == "qualified"
    assert next(e for e in two["events"] if e["type"] == "audit_claim")["payload"]["status"] == "supported"
    assert all(e["payload"]["visit_id"] == first for e in one["events"])
    stages = await _run_stage_detail(run_id, "AUDIT", 0, acting_principal())
    assert [v["visit_id"] for v in stages["visits"]] == [first, second]
    assert "tek çalışma bulgusu" in stages["visits"][0]["decisions"][0]["description"]
    latest = await current_claims(run_id, acting_principal())
    assert latest["temporal_basis"] == "current_only"
    with pytest.raises(HTTPException) as exc:
        await event_page(run_id, Principal.user("outsider", "user"), visit_id=first)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await event_page(run_id, acting_principal(), stage="SEARCH", visit_id=first)


@pytest.mark.asyncio
async def test_connector_call_correlation_zero_results_and_global_filters():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        visit = await repo.event(run.id, "stage", {"stage": "SEARCH", "round": 1})
        calls = [{"call_id": "ok", "connector": "arxiv", "success": True,
                  "result_count": 0, "operation": "search"},
                 {"call_id": "bad", "connector": "arxiv", "success": False,
                  "result_count": 0, "http_status": 429, "operation": "search"},
                 {"call_id": "citation", "connector": "arxiv", "success": False,
                  "result_count": 0, "operation": "citation", "error_type": "ReadTimeout"}]
        await repo.diagnostic_batch(run.id, "connector_call", calls)
        await repo.event(run.id, "connector_error", calls[1])
        await repo.event(run.id, "connector_error", calls[2])
        await repo.event(run.id, "connector_metrics", {"calls": calls[:2]})
        await repo.diagnostic_batch(run.id, "acquisition_call", [{"success": True,
            "parse_provenance": {"degraded": True, "reason": "docling_unavailable"}}])
        run_id = run.id
    errors = await event_page(run_id, acting_principal(), visit_id=visit, severity="error", limit=1)
    assert errors["total"] == 2 and errors["has_more"]
    assert errors["events"][0]["payload"]["operation"] == "citation"
    page2 = await event_page(run_id, acting_principal(), visit_id=visit, severity="error", offset=1)
    assert page2["events"][0]["payload"]["http_status"] == 429
    stage = await _run_stage_detail(run_id, "SEARCH", 0, acting_principal())
    row = next(t for t in stage["visits"][0]["tools"] if t["kind"] == "connector")
    assert row["calls"] == 3 and row["errors"] == 2 and row["ok"] == 1
    assert (await event_page(run_id, acting_principal(), connector="missing"))["total"] == 0
    parser = await event_page(run_id, acting_principal(), event_type="acquisition_call")
    assert parser["events"][0]["payload"]["parse_provenance"]["degraded"]


@pytest.mark.asyncio
async def test_long_history_totals_last_decision_and_201st_visit():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        run_id = run.id
        now = datetime.now(UTC)
        # Same timestamps deliberately stress visit-id rather than timestamp joins.
        rows = []
        for i in range(205):
            rows.append(EventRow(run_id=run_id, event_type="stage", created_at=now,
                                 payload={"stage": "SEARCH", "round": i}))
            rows.append(EventRow(run_id=run_id, event_type="connector_metrics", created_at=now,
                                 payload={"calls": [{"connector": "web", "success": True,
                                            "result_count": i, "branch_id": "q1"}]}))
        rows += [EventRow(run_id=run_id, event_type="progress", payload={"n": i}) for i in range(5100)]
        rows += [EventRow(run_id=run_id, event_type="coverage_gaps", payload={
            "stop_reason": "budget_exhausted", "discovery_quality": {"sentinel_recall": .875}})]
        session.add_all(rows)
        await session.commit()
    detail = await _run_detail(run_id, acting_principal())
    assert detail["funnel"]["counts"]["discovered"] == sum(range(205))
    assert detail["quality"]["sentinel_recall"] == .875
    first = await _run_stage_detail(run_id, "SEARCH", 0, acting_principal())
    second = await _run_stage_detail(run_id, "SEARCH", 200, acting_principal())
    assert first["has_more"] and len(first["visits"]) == 200
    assert not second["has_more"] and len(second["visits"]) == 5
    assert [v["tools"][0]["results"] for v in second["visits"]] == list(range(200, 205))
    page = await event_page(run_id, acting_principal(), limit=9999)
    assert len(page["events"]) == 200 and page["total"] == 5511
    filtered = await event_page(run_id, acting_principal(), event_type="coverage_gaps")
    assert filtered["total"] == 1 and filtered["events"][0]["payload"]["stop_reason"] == "budget_exhausted"
    historical = await event_page(run_id, acting_principal(), visit_id=second["visits"][-1]["visit_id"])
    assert not historical["history_available"]


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("branch_count", [0, 1])
def test_coverage_explanation_uses_actual_threshold_decisions(raw, branch_count):
    p = protocol()
    c = calculate_coverage(p, [], {"q1": branch_count}, 0, 0, 0, 0, 10,
                           claim_audit_required=not raw)
    snapshot = {"coverage": c.model_dump(), "thresholds": p.stopping_criteria.model_dump(),
                "inputs": {"branch_counts": {"q1": branch_count}, "major_claim_count": 0,
                           "audited_major_count": 0, "claim_audit_required": not raw},
                "literature_budget_mode": True, "stop_reason": "expand"}
    checks = {r["metric"]: r for r in coverage_checks(snapshot)}
    assert checks["query_branch_coverage"]["fraction"] == [branch_count, 1]
    assert checks["query_branch_coverage"]["result"] == ("pass" if branch_count else "fail")
    assert checks["claim_audit_coverage"]["result"] == ("pass" if raw else "fail")
    assert snapshot["stop_reason"] == "expand"
    assert checks["estimated_completeness"]["result"] == "inactive"
