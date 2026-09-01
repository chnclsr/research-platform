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

# Row order of the per-stage tool table, and a ceiling so one stage visit cannot bloat the
# run detail payload. A real visit produces well under ten rows.
TOOL_KIND_ORDER = ("connector", "method", "parser", "model", "embedding")
MAX_TOOL_ROWS = 40

# The seven links between a raw search hit and a reference in the .docx, in the order the
# data travels. The panel draws one cell per step, so this tuple is also the column order.
CHAIN_STEPS = (
    ("discover", "Keşif"),
    ("acquire", "Edinim"),
    ("parse", "Ayrıştırma"),
    ("retrieve", "Getirme"),
    ("evidence", "Kanıt"),
    ("claim", "İddia"),
    ("report", "Rapor"),
)

# What a source's stopping point means, in the operator's words. Keys that match a
# `CitationDrop` value are the reasons the export itself recorded; the rest are derived from
# where the chain ran out.
FATE_LABELS = {
    "cited": "Rapora girdi",
    "not_acquired": "Edinilemedi",
    "not_parsed": "Ayrıştırılamadı",
    "not_retrieved": "Getirmede elendi",
    "no_evidence": "Kanıt çıkarılamadı",
    "claim_below_threshold": "İddia denetimden geçmedi",
    "not_reportable": "İddia rapor eşiğini geçmedi",
    "section_discarded": "Bölüm taslağı elendi",
    "offered_not_cited": "Kanıt var, atıf yok",
    "no_export": "Rapor henüz üretilmedi",
}

# Claim statuses that count as the source having produced a usable claim. The finer
# reportable threshold (`_is_reportable`: relevance and supporting-evidence floors) is not
# applied here on purpose -- a claim that clears audit but not that floor stops at the
# report step instead, where the export's own `not_reportable` reason explains it.
CLAIM_OK_STATUSES = frozenset({"supported", "qualified"})


def source_chain(
    *,
    acquired: bool,
    passage_count: int,
    best_retrieval: float,
    evidence_count: int,
    claim_status_ok: bool,
    citation: dict[str, Any] | None,
    exported: bool,
) -> dict[str, Any]:
    """How far one source travelled, and where it stopped.

    Each cell is `on` (passed), `stop` (ran out here) or `off` (never reached). Exactly one
    cell can be `stop`: the fate names a single point of failure, because a source that never
    got acquired has not also "failed retrieval" -- reporting both would bury the one fact
    that explains the rest.

    `citation` is the export's own record for this source and is authoritative for the last
    step; without it the run either predates the citation table or has not exported yet, and
    `exported` is what separates those from a source the report genuinely dropped.
    """
    reached = {
        "discover": True,
        "acquire": acquired,
        "parse": acquired and passage_count > 0,
        "retrieve": acquired and passage_count > 0 and best_retrieval > 0,
        "evidence": evidence_count > 0,
        "claim": claim_status_ok,
        "report": bool(citation) and citation.get("drop_reason") is None,
    }
    # A later step cannot stand without the ones before it: evidence implies its passage was
    # retrieved. Clamping forwards keeps a gap in the middle from reading as two failures.
    passed = True
    chain: dict[str, str] = {}
    stopped_at: str | None = None
    for key, _ in CHAIN_STEPS:
        if not passed:
            chain[key] = "off"
            continue
        if reached[key]:
            chain[key] = "on"
            continue
        chain[key] = "stop"
        stopped_at = key
        passed = False

    if stopped_at is None:
        code = "cited"
    elif stopped_at == "report":
        if citation:
            code = str(citation.get("drop_reason") or "cited")
        else:
            code = "no_export" if not exported else "offered_not_cited"
    else:
        code = {
            "acquire": "not_acquired",
            "parse": "not_parsed",
            "retrieve": "not_retrieved",
            "evidence": "no_evidence",
            "claim": "claim_below_threshold",
        }[stopped_at]
    return {
        "chain": chain,
        "fate": {"code": code, "label": FATE_LABELS.get(code, code)},
    }


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
    # Only stage/duration is read below, so the tool-free walk is enough -- and it lets the
    # caller feed every stage event rather than a truncated slice of the whole event log.
    timeline = stage_visits(events, now)
    durations: dict[str, float] = defaultdict(float)
    visits: dict[str, int] = defaultdict(int)
    for item in timeline:
        stage = str(item["stage"])
        durations[stage] += float(item["duration_seconds"])
        visits[stage] += 1
    last_observed = str(timeline[-1]["stage"]) if timeline else current_stage
    effective_stage = (
        "COMPLETE" if current_stage == "COMPLETE" else last_observed if timeline else current_stage
    )
    terminal = status in {"completed", "completed_incomplete", "failed", "cancelled"}
    nodes = []
    for stage, label in PIPELINE_STAGES:
        state = "completed" if visits[stage] else "pending"
        if stage == "INIT" and not timeline:
            state = "active" if status in {"queued", "running"} else state
        if stage == effective_stage and not terminal:
            state = "paused" if status in {"paused", "awaiting_input"} else "active"
        if stage == last_observed and status in {"failed", "cancelled"}:
            state = "error"
        if stage == "COMPLETE" and status in {"completed", "completed_incomplete"}:
            state = "completed"
        if terminal and state == "pending":
            state = "skipped"
        nodes.append(
            {
                "stage": stage,
                "label": label,
                "state": state,
                "visits": visits[stage],
                "duration_seconds": round(durations[stage], 2),
            }
        )
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


def _tool_row(
    rows: dict[tuple[str, str], dict[str, Any]],
    kind: str,
    name: str,
) -> dict[str, Any]:
    key = (kind, name)
    row = rows.get(key)
    if row is None:
        row = {
            "kind": kind,
            "name": name,
            "calls": 0,
            "ok": 0,
            "errors": 0,
            "results": 0,
            "tokens": 0,
            "seconds": 0.0,
            "phases": [],
        }
        rows[key] = row
    return row


def _tool_rows(events: list[Any]) -> list[dict[str, Any]]:
    """Aggregate the metric events of a single stage visit into per-tool rows."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        event_type = _event_value(event, "event_type")
        payload = _event_value(event, "payload", {}) or {}
        if event_type == "connector_metrics":
            for call in payload.get("calls", []):
                row = _tool_row(rows, "connector", str(call.get("connector") or "unknown"))
                row["calls"] += 1
                row["ok"] += int(bool(call.get("success")))
                row["results"] += int(call.get("result_count", 0))
                row["seconds"] += float(call.get("latency_seconds", 0.0))
        elif event_type == "connector_error":
            _tool_row(rows, "connector", str(payload.get("connector") or "unknown"))["errors"] += 1
        elif event_type == "acquisition_metrics":
            for call in payload.get("calls", []):
                success = int(bool(call.get("success")))
                method = _tool_row(rows, "method", str(call.get("method") or "unknown"))
                method["calls"] += 1
                method["ok"] += success
                method["seconds"] += float(call.get("latency_seconds", 0.0))
                # Runs recorded before parser_id joined this event carry no parser at all.
                # Leaving the row out is honest; inventing an "unknown" parser is not.
                parser_id = str(call.get("parser_id") or "")
                if parser_id:
                    parser = _tool_row(rows, "parser", parser_id)
                    parser["calls"] += 1
                    parser["ok"] += success
        elif event_type in {"llm_metrics", "embedding_metrics"}:
            kind = "model" if event_type == "llm_metrics" else "embedding"
            # The payload stage is a finer-grained phase label than the pipeline stage --
            # CONTENT_RELEVANCE runs inside NORMALIZE and is absent from PIPELINE_STAGES --
            # so it annotates the row rather than placing it.
            phase = str(payload.get("stage") or "")
            for call in payload.get("calls", []):
                row = _tool_row(rows, kind, str(call.get("model") or "unknown"))
                row["calls"] += 1
                row["ok"] += 1
                row["tokens"] += int(call.get("prompt_tokens", 0)) + int(
                    call.get("completion_tokens", 0)
                )
                row["seconds"] += float(call.get("wall_seconds", 0.0))
                if phase and phase not in row["phases"]:
                    row["phases"].append(phase)
    ordered = sorted(
        rows.values(),
        key=lambda row: (TOOL_KIND_ORDER.index(row["kind"]), -row["calls"], row["name"]),
    )
    for row in ordered:
        row["seconds"] = round(row["seconds"], 2)
    return ordered[:MAX_TOOL_ROWS]


def _utc_now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _walk_stage_boundaries(events: list[Any], now: datetime) -> list[dict[str, Any]]:
    """Split a run's events into stage visits, in time order."""
    visits: list[dict[str, Any]] = []
    for event in events:
        if _event_value(event, "event_type") == "stage":
            payload = _event_value(event, "payload", {}) or {}
            visits.append(
                {
                    "stage": payload.get("stage", "UNKNOWN"),
                    "round": payload.get("round", 0),
                    "created_at": _event_value(event, "created_at"),
                    "event_id": _event_value(event, "id"),
                    "events": [],
                }
            )
        elif visits:
            # Metric events name no stage of their own. `_boundary` emits the stage event
            # at the start of a stage, so an event belongs to the visit whose boundary
            # opened the window it arrived in -- which also keeps repeated visits of the
            # same stage across rounds separate.
            visits[-1]["events"].append(event)
    visits.sort(key=lambda item: item["created_at"] or now)
    return visits


def _visit_row(visits: list[dict[str, Any]], index: int, now: datetime) -> dict[str, Any]:
    item = visits[index]
    start = item["created_at"] or now
    end = visits[index + 1]["created_at"] if index + 1 < len(visits) else now
    return {
        "stage": item["stage"],
        "round": item["round"],
        "started_at": start.isoformat(),
        "duration_seconds": round(max(0.0, (end - start).total_seconds()), 2),
        "active": index == len(visits) - 1,
    }


def _visit_summary(tools: list[dict[str, Any]]) -> dict[str, int]:
    """The one-line headline a visit row shows before its tool table is opened."""
    return {
        "connectors": sum(1 for row in tools if row["kind"] == "connector"),
        "calls": sum(int(row["calls"]) for row in tools),
        "errors": sum(int(row["errors"]) for row in tools),
        "tokens": sum(int(row["tokens"]) for row in tools),
    }


def stage_visits(events: list[Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """Every stage visit without its tool rows.

    Aggregating tools is what makes the timeline expensive, so a caller that only needs
    "which stage ran when, and for how long" can afford to pass every stage event a long
    run produced instead of a truncated slice of the whole event log.
    """
    now = _utc_now(now)
    visits = _walk_stage_boundaries(events, now)
    output = []
    for index, item in enumerate(visits):
        row = _visit_row(visits, index, now)
        row["start_event_id"] = item["event_id"]
        row["end_event_id"] = (
            visits[index + 1]["event_id"] if index + 1 < len(visits) else None
        )
        output.append(row)
    return output


def stage_visit_details(
    events: list[Any], stage: str, now: datetime | None = None
) -> list[dict[str, Any]]:
    """The visits of one stage, each with its tool rows and headline counts."""
    now = _utc_now(now)
    visits = _walk_stage_boundaries(events, now)
    output = []
    for index, item in enumerate(visits):
        if item["stage"] != stage:
            continue
        row = _visit_row(visits, index, now)
        row["tools"] = _tool_rows(item["events"])
        row["summary"] = _visit_summary(row["tools"])
        output.append(row)
    return output


def stage_timeline(events: list[Any], now: datetime | None = None) -> list[dict[str, Any]]:
    now = _utc_now(now)
    visits = _walk_stage_boundaries(events, now)
    output = []
    for index, item in enumerate(visits):
        row = _visit_row(visits, index, now)
        row["tools"] = _tool_rows(item["events"])
        output.append(row)
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
    admission.update(
        {
            "accept": int(latest_quality.get("accepted_candidates", 0)),
            "reserve": int(latest_quality.get("reserve_selected", 0)),
            "reject": int(latest_quality.get("hard_rejected", 0)),
        }
    )
    ordered = [
        {"id": "discovered", "label": "Arama sonucu", "value": values["discovered"]},
        {
            "id": "after_dedupe",
            "label": "Tekilleştirme sonrası",
            "value": max(
                0,
                values["discovered"] - values["deduplicated"],
            ),
        },
        {
            "id": "after_temporal",
            "label": "Tarih filtresi sonrası",
            "value": max(
                0,
                values["discovered"] - values["deduplicated"] - values["temporal_rejected"],
            ),
        },
        {
            "id": "acquisition_attempted",
            "label": "Edinime seçilen",
            "value": values["acquisition_attempted"],
        },
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
            branch = branches.setdefault(
                branch_id,
                {
                    "branch_id": branch_id,
                    "query": call.get("query") or "",
                    "result_count": 0,
                    "calls": 0,
                    "successful_calls": 0,
                    "connectors": [],
                    "latency_seconds": 0.0,
                },
            )
            branch["calls"] += 1
            branch["successful_calls"] += int(bool(call.get("success")))
            branch["result_count"] += int(call.get("result_count", 0))
            branch["latency_seconds"] += float(call.get("latency_seconds", 0.0))
            connector = str(call.get("connector") or "unknown")
            if connector not in branch["connectors"]:
                branch["connectors"].append(connector)
    return sorted(branches.values(), key=lambda row: row["branch_id"])


def connector_operations(events: list[Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "successes": 0,
            "result_count": 0,
            "latencies": [],
            "errors": 0,
            "error_types": defaultdict(int),
            "last_success_at": None,
            "last_error_at": None,
        }
    )
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
            error_type = next(
                (
                    name
                    for name in ("429", "403", "timeout", "connection", "citation")
                    if name in error
                ),
                "other",
            )
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
            completion_tokens / generation_seconds,
            2,
        )
        if generation_seconds
        else 0.0,
        "models": sorted({str(call.get("model")) for call in calls if call.get("model")}),
    }
