"""Lazy, ownership-scoped historical stage and event reads for the control panel."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased

from .auth import Principal
from .control_panel_metrics import (
    PIPELINE_STAGES,
    query_branch_summary,
    serialize_event,
    source_funnel,
)
from .db import ClaimRow, EventRow, ResearchRunRow, SessionLocal
from .diagnostics import (
    EVENT_LABELS,
    coverage_checks,
    decision_summary,
    event_severity,
    safe_diagnostic,
)
from .hardware_telemetry import SAMPLE_EVENT

SUMMARY_EVENTS = frozenset({
    "audit_summary", "coverage_snapshot", "coverage_gaps", "normalization_summary",
    "extraction_summary", "claim_deduplication", "claim_filter", "passage_index",
    "passage_retrieval", "claim_appraisal", "recovery_plan", "recovery_no_progress",
    "synthesis_generation", "artifacts", "claim_extraction_skipped", "research_plan",
    "protocol_synthesis", "decomposition_summary", "scope_criteria_resolved", "complete",
    "protocol_validated", "query_plan", "connector_selection",
    "collection_budget_exhausted",
})


async def run_aggregates(session: Any, run_id: str, source_count: int) -> dict[str, Any]:
    """Scan only aggregate inputs in bounded batches; never load audit history or PDFs."""
    kinds = {"connector_metrics", "acquisition_metrics", "llm_metrics", "novelty_filter",
             "temporal_scope_filter", "relevance_filter", "content_relevance_filter"}
    stream = await session.stream(select(EventRow.event_type, EventRow.payload).where(
        EventRow.run_id == run_id, EventRow.event_type.in_(kinds),
    ).order_by(EventRow.id).execution_options(yield_per=100))
    funnel = source_funnel([], source_count)
    counts = funnel["counts"]
    branches: dict[str, dict[str, Any]] = {}
    llm = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
           "wall_seconds": 0.0, "tokens_per_second": 0.0, "models": []}
    generation_seconds = 0.0
    models: set[str] = set()
    latest_quality = await session.scalar(select(EventRow.payload).where(
        EventRow.run_id == run_id, EventRow.event_type == "coverage_gaps",
    ).order_by(EventRow.id.desc()).limit(1))
    quality = (latest_quality or {}).get("discovery_quality", {})
    funnel["admission"] = {
        "accept": int(quality.get("accepted_candidates", 0)),
        "reserve": int(quality.get("reserve_selected", 0)),
        "reject": int(quality.get("hard_rejected", 0)),
    }
    async for batch in stream.partitions(100):
        events = [{"event_type": kind, "payload": payload or {}} for kind, payload in batch]
        chunk = source_funnel(events, 0)
        for key, value in chunk["counts"].items():
            if key != "final_sources":
                counts[key] += value
        for branch in query_branch_summary(events):
            key = branch["branch_id"]
            if key not in branches:
                branches[key] = branch
            else:
                target = branches[key]
                for field in ("calls", "successful_calls", "result_count", "latency_seconds"):
                    target[field] += branch[field]
                target["connectors"] = sorted(set(target["connectors"]) | set(branch["connectors"]))
        for kind, payload in batch:
            payload = payload or {}
            if kind == "llm_metrics":
                for call in payload.get("calls", []):
                    llm["calls"] += 1
                    for field in ("prompt_tokens", "completion_tokens", "wall_seconds"):
                        llm[field] += call.get(field, 0) or 0
                    generation_seconds += call.get("generation_seconds", 0) or 0
                    if call.get("model"):
                        models.add(str(call["model"]))
    values = [counts["discovered"], max(0, counts["discovered"] - counts["deduplicated"]),
              max(0, counts["discovered"] - counts["deduplicated"] - counts["temporal_rejected"]),
              counts["acquisition_attempted"], counts["acquisition_succeeded"], source_count]
    for step, value in zip(funnel["steps"], values):
        step["value"] = value
    llm["models"] = sorted(models)
    llm["wall_seconds"] = round(llm["wall_seconds"], 2)
    llm["tokens_per_second"] = round(llm["completion_tokens"] / generation_seconds, 2) if generation_seconds else 0.0
    return {"funnel": funnel, "quality": quality, "llm": llm,
            "query_branches": [branches[key] for key in sorted(branches)]}


async def owned_run(session: Any, run_id: str, principal: Principal) -> ResearchRunRow:
    run = await session.get(ResearchRunRow, run_id)
    if run is None or not (principal.is_admin or run.owner_id == principal.user_id):
        raise HTTPException(404, "Araştırma bulunamadı")
    return run


async def current_claims(run_id: str, principal: Principal, offset: int = 0) -> dict[str, Any]:
    """Latest values are explicitly not historical audit decisions."""
    async with SessionLocal() as session:
        await owned_run(session, run_id, principal)
        total = await session.scalar(select(func.count()).select_from(ClaimRow).where(ClaimRow.run_id == run_id))
        rows = list(await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id)
                                         .order_by(ClaimRow.id).offset(max(0, offset)).limit(50)))
        return {"temporal_basis": "current_only", "label": "Son durum — geçmiş tur kararı değildir",
                "offset": max(0, offset), "total": total,
                "has_more": max(0, offset) + len(rows) < (total or 0),
                "claims": [safe_diagnostic({"claim_id": row.id, "claim_text": row.text,
                                            "status": row.status, "audit": row.audit}) for row in rows]}


def diagnostic_event(event: Any) -> dict[str, Any]:
    result = serialize_event(event)
    payload = safe_diagnostic(result["payload"])
    result.update(payload=payload, label=EVENT_LABELS.get(result["type"], result["type"]),
                  severity=event_severity(result["type"], payload),
                  description=decision_summary(result["type"], payload))
    if result["type"] == "coverage_snapshot":
        result["checks"] = coverage_checks(payload)
    return result


async def event_page(
    run_id: str, principal: Principal, *, offset: int = 0, limit: int = 50,
    stage: str | None = None, visit_id: int | None = None,
    event_type: str | None = None, severity: str | None = None,
    connector: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    async with SessionLocal() as session:
        run = await owned_run(session, run_id, principal)
        conditions = [EventRow.run_id == run_id, EventRow.event_type != SAMPLE_EVENT]
        visit = None
        end = None
        if visit_id is not None:
            visit = await session.get(EventRow, visit_id)
            if (visit is None or visit.run_id != run_id or visit.event_type != "stage"
                    or (stage is not None and (visit.payload or {}).get("stage") != stage)):
                raise HTTPException(404, "Aşama ziyareti bulunamadı")
            end = await session.scalar(select(EventRow.id).where(
                EventRow.run_id == run_id, EventRow.event_type == "stage", EventRow.id > visit_id,
            ).order_by(EventRow.id).limit(1))
            conditions.append(EventRow.id >= visit_id)
            if end is not None:
                conditions.append(EventRow.id < end)
        elif stage is not None:
            raise HTTPException(400, "Aşama filtresi ziyaret kimliği gerektirir")
        base = list(conditions)
        # Canonical per-call records supersede mirrored legacy metric/error events.
        canonical = aliased(EventRow)
        mirrored = exists(select(canonical.id).where(
            canonical.run_id == run_id, canonical.event_type == "connector_call",
            canonical.payload["call_id"].as_string() == EventRow.payload["call_id"].as_string(),
        ))
        conditions.append(~((EventRow.event_type == "connector_error") & mirrored))
        if event_type:
            conditions.append(EventRow.event_type == event_type)
        if severity == "error":
            conditions.append(or_(EventRow.event_type.contains("error"),
                                  EventRow.payload["success"].as_boolean() == False))
        elif severity == "warning":
            conditions.append(or_(EventRow.payload["diagnostic_severity"].as_string() == "warning",
                                  EventRow.event_type.contains("degraded"),
                                  EventRow.event_type.contains("fallback"),
                                  EventRow.payload["invalid_evidence"].as_integer() > 0))
        elif severity:
            raise HTTPException(422, "Geçersiz önem filtresi")
        if connector:
            conditions.append(EventRow.payload["connector"].as_string() == connector)
        total = await session.scalar(select(func.count()).select_from(EventRow).where(*conditions))
        events = list(await session.scalars(select(EventRow).where(*conditions)
                                           .order_by(EventRow.id.desc()).offset(offset).limit(limit)))
        summaries = []
        if visit is not None:
            summaries = list(await session.scalars(select(EventRow).where(
                *base, EventRow.event_type.in_(SUMMARY_EVENTS),
            ).order_by(EventRow.id.desc()).limit(20)))
        active = bool(visit is not None and end is None and run.status == "running")
        recorded_state = "recorded"
        if visit is not None:
            has_details = await session.scalar(select(EventRow.id).where(
                *base, EventRow.event_type != "stage",
            ).limit(1))
            if not has_details:
                recorded_state = "missing"
            if any((e.payload or {}).get("skipped") or e.event_type.endswith("_skipped")
                   or e.event_type == "collection_budget_exhausted" for e in summaries):
                recorded_state = "skipped"
            if any((e.payload or {}).get("reason") == "no_input" for e in summaries):
                recorded_state = "no_input"
        return {
            "run_id": run_id, "visit_id": visit_id,
            "stage": (visit.payload or {}).get("stage") if visit else None,
            "round": (visit.payload or {}).get("round") if visit else None,
            "recorded_state": recorded_state,
            "state": "active" if active else "failed" if end is None and run.status == "failed"
                     else "cancelled" if end is None and run.status == "cancelled"
                     else "paused" if end is None and run.status in {"paused", "awaiting_input"}
                     else "completed",
            "offset": offset, "limit": limit, "total": total,
            "has_more": offset + len(events) < (total or 0),
            "next_offset": offset + len(events),
            "events": [diagnostic_event(e) for e in events],
            "summaries": [diagnostic_event(e) for e in reversed(summaries)],
            "history_available": any((e.payload or {}).get("schema_version") and e.event_type in {
                "audit_summary", "coverage_snapshot", "claim_appraisal",
            } for e in summaries),
            "label": dict(PIPELINE_STAGES).get(stage or "", stage),
        }
