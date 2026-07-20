from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


PIPELINE_STAGES = (
    ("INIT", "Başlangıç"),
    ("VALIDATE_PROTOCOL", "Protokol"),
    ("DECOMPOSE", "Ayrıştırma"),
    ("BUILD_QUERY_BRANCHES", "Sorgu planı"),
    ("SEARCH", "Arama"),
    ("ACQUIRE", "Edinim"),
    ("NORMALIZE", "Normalizasyon"),
    ("CHUNK_INDEX", "Parçalama ve indeks"),
    ("RETRIEVE_PASSAGES", "Pasaj retrieval"),
    ("EXTRACT_EVIDENCE", "Kanıt çıkarımı"),
    ("ANALYZE_CLAIMS", "İddia analizi"),
    ("AUDIT", "Audit"),
    ("CHECK_COVERAGE", "Coverage kontrolü"),
    ("PLAN_RECOVERY", "Recovery planı"),
    ("ADVERSARIAL_REVIEW", "Karşı inceleme"),
    ("SYNTHESIZE_EXPORT", "Sentez ve çıktı"),
    ("COMPLETE", "Tamamlandı"),
)


def pipeline_progress(current_stage: str, status: str) -> int:
    if status in {"completed", "completed_incomplete"} or current_stage == "COMPLETE":
        return 100
    if status == "queued" or current_stage == "INIT":
        return 0
    order = [stage for stage, _ in PIPELINE_STAGES if stage != "PLAN_RECOVERY"]
    if current_stage not in order:
        return 0
    return round(order.index(current_stage) / (len(order) - 1) * 100)


def pipeline_flow(
    events: list[Any],
    *,
    current_stage: str,
    status: str,
    round_number: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    timeline = stage_timeline(events, now)
    durations: dict[str, float] = defaultdict(float)
    visits: dict[str, int] = defaultdict(int)
    for item in timeline:
        stage = str(item["stage"])
        durations[stage] += float(item["duration_seconds"])
        visits[stage] += 1
    last_observed = str(timeline[-1]["stage"]) if timeline else current_stage
    effective_stage = (
        "COMPLETE"
        if current_stage == "COMPLETE"
        else last_observed if timeline else current_stage
    )
    terminal = status in {"completed", "completed_incomplete", "failed", "cancelled"}
    nodes = []
    for stage, label in PIPELINE_STAGES:
        state = "completed" if visits[stage] else "pending"
        if stage == "INIT" and not timeline:
            state = "active" if status in {"queued", "running"} else state
        if stage == effective_stage and not terminal:
            state = "paused" if status == "paused" else "active"
        if stage == last_observed and status in {"failed", "cancelled"}:
            state = "error"
        if stage == "COMPLETE" and status in {"completed", "completed_incomplete"}:
            state = "completed"
        if terminal and state == "pending":
            state = "skipped"
        nodes.append({
            "stage": stage,
            "label": label,
            "state": state,
            "visits": visits[stage],
            "duration_seconds": round(durations[stage], 2),
        })
    return {
        "nodes": nodes,
        "progress_percent": pipeline_progress(effective_stage, status),
        "current_stage": effective_stage,
        "round_number": round_number,
        "has_recovery_loop": bool(visits["PLAN_RECOVERY"]),
    }


def _event_value(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def serialize_event(event: Any) -> dict[str, Any]:
    created_at = _event_value(event, "created_at")
    return {
        "id": _event_value(event, "id"),
        "type": _event_value(event, "event_type", "unknown"),
        "payload": _event_value(event, "payload", {}) or {},
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }


def stage_timeline(events: list[Any], now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    stages = []
    for event in events:
        if _event_value(event, "event_type") != "stage":
            continue
        payload = _event_value(event, "payload", {}) or {}
        created_at = _event_value(event, "created_at")
        stages.append({
            "stage": payload.get("stage", "UNKNOWN"),
            "round": payload.get("round", 0),
            "created_at": created_at,
        })
    stages.sort(key=lambda item: item["created_at"] or now)
    output = []
    for index, item in enumerate(stages):
        start = item["created_at"] or now
        end = stages[index + 1]["created_at"] if index + 1 < len(stages) else now
        output.append({
            "stage": item["stage"],
            "round": item["round"],
            "started_at": start.isoformat(),
            "duration_seconds": round(max(0.0, (end - start).total_seconds()), 2),
            "active": index == len(stages) - 1,
        })
    return output


def source_funnel(events: list[Any], final_sources: int) -> dict[str, Any]:
    values = {
        "discovered": 0,
        "deduplicated": 0,
        "temporal_rejected": 0,
        "relevance_rejected": 0,
        "acquisition_attempted": 0,
        "acquisition_succeeded": 0,
        "content_rejected": 0,
        "final_sources": final_sources,
    }
    admission = {"accept": 0, "reserve": 0, "reject": 0}
    latest_quality: dict[str, Any] = {}
    for event in events:
        event_type = _event_value(event, "event_type")
        payload = _event_value(event, "payload", {}) or {}
        if event_type == "connector_metrics":
            values["discovered"] += sum(
                int(call.get("result_count", 0)) for call in payload.get("calls", [])
            )
        elif event_type == "novelty_filter":
            values["deduplicated"] += int(payload.get("rejected_count", 0))
        elif event_type == "temporal_scope_filter":
            values["temporal_rejected"] += int(payload.get("rejected_count", 0))
        elif event_type == "relevance_filter":
            values["relevance_rejected"] += int(payload.get("rejected_count", 0))
        elif event_type == "acquisition_metrics":
            calls = payload.get("calls", [])
            values["acquisition_attempted"] += len(calls)
            values["acquisition_succeeded"] += sum(bool(call.get("success")) for call in calls)
        elif event_type == "content_relevance_filter":
            values["content_rejected"] += int(payload.get("rejected_count", 0))
        elif event_type == "coverage_gaps":
            latest_quality = payload.get("discovery_quality", {}) or latest_quality
    admission.update({
        "accept": int(latest_quality.get("accepted_candidates", 0)),
        "reserve": int(latest_quality.get("reserve_selected", 0)),
        "reject": int(latest_quality.get("hard_rejected", 0)),
    })
    ordered = [
        {"id": "discovered", "label": "Arama sonucu", "value": values["discovered"]},
        {"id": "after_dedupe", "label": "Tekilleştirme sonrası", "value": max(
            0, values["discovered"] - values["deduplicated"],
        )},
        {"id": "after_temporal", "label": "Tarih filtresi sonrası", "value": max(
            0,
            values["discovered"] - values["deduplicated"] - values["temporal_rejected"],
        )},
        {"id": "acquisition_attempted", "label": "Edinime seçilen", "value": values[
            "acquisition_attempted"
        ]},
        {"id": "acquired", "label": "Başarılı edinim", "value": values["acquisition_succeeded"]},
        {"id": "final", "label": "Nihai ilgili kaynak", "value": final_sources},
    ]
    return {"steps": ordered, "counts": values, "admission": admission}


def query_branch_summary(events: list[Any]) -> list[dict[str, Any]]:
    branches: dict[str, dict[str, Any]] = {}
    for event in events:
        if _event_value(event, "event_type") != "connector_metrics":
            continue
        for call in (_event_value(event, "payload", {}) or {}).get("calls", []):
            branch_id = str(call.get("branch_id") or "unknown")
            branch = branches.setdefault(branch_id, {
                "branch_id": branch_id,
                "query": call.get("query") or "",
                "result_count": 0,
                "calls": 0,
                "successful_calls": 0,
                "connectors": [],
                "latency_seconds": 0.0,
            })
            branch["calls"] += 1
            branch["successful_calls"] += int(bool(call.get("success")))
            branch["result_count"] += int(call.get("result_count", 0))
            branch["latency_seconds"] += float(call.get("latency_seconds", 0.0))
            connector = str(call.get("connector") or "unknown")
            if connector not in branch["connectors"]:
                branch["connectors"].append(connector)
    return sorted(branches.values(), key=lambda row: row["branch_id"])


def connector_operations(events: list[Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "calls": 0,
        "successes": 0,
        "result_count": 0,
        "latencies": [],
        "errors": 0,
        "error_types": defaultdict(int),
        "last_success_at": None,
        "last_error_at": None,
    })
    for event in events:
        event_type = _event_value(event, "event_type")
        payload = _event_value(event, "payload", {}) or {}
        created_at = _event_value(event, "created_at")
        stamp = created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
        if event_type == "connector_metrics":
            for call in payload.get("calls", []):
                connector = str(call.get("connector") or "unknown")
                row = rows[connector]
                row["calls"] += 1
                success = bool(call.get("success"))
                row["successes"] += int(success)
                row["result_count"] += int(call.get("result_count", 0))
                row["latencies"].append(float(call.get("latency_seconds", 0.0)))
                if success:
                    row["last_success_at"] = stamp
        elif event_type == "connector_error":
            connector = str(payload.get("connector") or "unknown")
            row = rows[connector]
            row["errors"] += 1
            error = str(payload.get("error") or "unknown").lower()
            error_type = next((
                name for name in ("429", "403", "timeout", "connection", "citation")
                if name in error
            ), "other")
            row["error_types"][error_type] += 1
            row["last_error_at"] = stamp
    output = {}
    for connector, row in rows.items():
        latencies = row.pop("latencies")
        ordered = sorted(latencies)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95))) if ordered else 0
        output[connector] = {
            **row,
            "error_types": dict(row["error_types"]),
            "success_rate": round(row["successes"] / max(1, row["calls"]), 4),
            "average_latency_seconds": round(sum(latencies) / max(1, len(latencies)), 3),
            "p95_latency_seconds": round(ordered[p95_index], 3) if ordered else 0.0,
        }
    return output


def llm_summary(events: list[Any]) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    for event in events:
        if _event_value(event, "event_type") == "llm_metrics":
            calls.extend((_event_value(event, "payload", {}) or {}).get("calls", []))
    completion_tokens = sum(int(call.get("completion_tokens", 0)) for call in calls)
    generation_seconds = sum(float(call.get("generation_seconds", 0.0)) for call in calls)
    return {
        "calls": len(calls),
        "prompt_tokens": sum(int(call.get("prompt_tokens", 0)) for call in calls),
        "completion_tokens": completion_tokens,
        "wall_seconds": round(sum(float(call.get("wall_seconds", 0.0)) for call in calls), 2),
        "tokens_per_second": round(
            completion_tokens / generation_seconds, 2,
        ) if generation_seconds else 0.0,
        "models": sorted({str(call.get("model")) for call in calls if call.get("model")}),
    }
