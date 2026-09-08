"""Versioned, reader-safe stage observations; never used to make research decisions."""
from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

CONNECTOR_OBSERVATION: ContextVar[dict[str, Any] | None] = ContextVar("connector_observation", default=None)


def observe_connector(**fields: Any) -> None:
    """Attach provider facts to the current call, isolated across concurrent tasks."""
    current = CONNECTOR_OBSERVATION.get()
    if current is not None:
        current.update(fields)


def observe_attempt(response: Any, attempt: int, *, phase: str | None = None) -> None:
    """Record one provider response. `attempt` is the caller's 0-based retry index.

    `phase` names which request this is when a single search makes several distinct ones --
    GitHub looks a repository up before searching, OpenAlex reads references and cited_by.
    It stays absent otherwise: written unconditionally it would read every one-request
    connector as if it had retried.
    """
    current = CONNECTOR_OBSERVATION.get()
    if current is not None:
        record: dict[str, Any] = {
            "attempt": attempt + 1, "http_status": response.status_code,
            "retry_after": response.headers.get("Retry-After"),
        }
        if phase is not None:
            record["phase"] = phase
        current.setdefault("attempts", []).append(record)
        current["http_status"] = response.status_code


def observe_transport_error(exc: Exception, attempt: int, *, phase: str | None = None) -> None:
    current = CONNECTOR_OBSERVATION.get()
    if current is not None:
        record: dict[str, Any] = {
            "attempt": attempt + 1, "http_status": None, "error_type": type(exc).__name__,
        }
        if phase is not None:
            record["phase"] = phase
        current.setdefault("attempts", []).append(record)
        current["http_status"] = None

SECRET_KEY = re.compile(r"^token$|authorization|cookie|password|secret|api[-_]?key|access[-_]?token|refresh[-_]?token", re.IGNORECASE)
SECRET_TEXT = re.compile(
    r"(?i)(\b(?:bearer|basic)\s+)[\w.+/=:-]+|"
    r"((?:api[-_]?key|token|password|secret|signature|credential)=)[^\s&#]+|"
    r"(https?://)[^\s/@]+:[^\s/@]+@"
)


def safe_diagnostic(value: Any) -> Any:
    """Mask credentials in both historical payloads and newly recorded diagnostics."""
    if isinstance(value, dict):
        return {
            str(key): "[MASKED]" if SECRET_KEY.search(str(key)) else safe_diagnostic(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_diagnostic(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT.sub(lambda m: (m[1] or m[2] or m[3]) + "[MASKED]", value)
    return value


def error_details(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {})
    return safe_diagnostic({
        "error": str(exc)[:2000],
        "error_type": type(exc).__name__,
        "http_status": getattr(response, "status_code", None),
        "retry_after": headers.get("Retry-After") or getattr(exc, "retry_after", None),
    })


EVENT_LABELS = {
    "protocol_validated": "Protokol ve onaylanan kapsam",
    "query_plan": "Sorgu dalları ve connector planı",
    "connector_selection": "Connector kullanılabilirliği",
    "collection_budget_exhausted": "Toplama süresi doldu; yeni dış edinim atlandı",
    "claim_extraction_skipped": "İddia çıkarımı atlandı",
    "decomposition_summary": "Alt sorular ve kavramlar",
    "synthesis_section": "Sentez teması ve kanıtları",
    "stage": "Aşama başladı",
    "connector_metrics": "Arama çağrıları",
    "connector_error": "Connector hatası",
    "connector_call": "Connector çağrısı",
    "acquisition_call": "Kaynak edinimi ve ayrıştırma",
    "source_rejected": "Kaynak eleme kararı",
    "synthesis_generation": "Sentez üretim sonucu",
    "acquisition_metrics": "Edinim ve parser çağrıları",
    "source_decision": "Kaynak kapsam kararı",
    "normalization_summary": "Normalizasyon sonucu",
    "passage_index": "Pasaj indeksi",
    "passage_retrieval": "Pasaj seçimi",
    "extraction_summary": "Kanıt çıkarımı sonucu",
    "claim_deduplication": "İddia birleştirme",
    "claim_filter": "İddia eleme gerekçeleri",
    "claim_decision": "İddia kabul, eleme veya birleştirme kararı",
    "audit_claim": "İddia denetimi",
    "audit_summary": "Denetim sonucu",
    "coverage_snapshot": "Kapsam kararı ve eşikler",
    "coverage_gaps": "Eksikler ve devam kararı",
    "recovery_plan": "Eksikler için araştırma görevleri",
    "recovery_no_progress": "İlerleme sağlanamadı",
    "appraisal_claim": "İddianın kanıt derecesi",
    "claim_appraisal": "Kanıt derecelendirme sonucu",
    "synthesis_quality": "Sentez kalitesi",
    "artifacts": "Üretilen dosyalar",
    "llm_metrics": "Model çağrıları",
    "embedding_metrics": "Embedding çağrıları",
}


def event_severity(event_type: str, payload: dict[str, Any]) -> str:
    if "error" in event_type or payload.get("success") is False:
        return "error"
    if ("degraded" in event_type or "fallback" in event_type
            or any(payload.get(key) for key in ("validation_warnings", "rejected", "invalid_evidence"))
            or (payload.get("audit") or {}).get("invalid_evidence")):
        return "warning"
    if (payload.get("parse_provenance") or {}).get("degraded"):
        return "warning"
    return "info"


def decision_summary(event_type: str, payload: dict[str, Any]) -> str:
    """Compact facts, not generated explanations or inferred historical decisions."""
    if event_type == "audit_summary":
        if payload.get("skipped"):
            return "Ham çıktı modunda iddia denetimi atlandı."
        statuses = {"supported": "desteklenmiş", "qualified": "tek çalışma bulgusu",
                    "unresolved": "çözümlenmemiş", "irrelevant": "ilgisiz"}
        counts = ", ".join(f"{n} {statuses.get(status, status)}"
                           for status, n in payload.get("statuses", {}).items())
        return f"{payload.get('claim_count', 0)} iddia denetlendi · {counts}"
    if event_type in {"coverage_snapshot", "coverage_gaps"}:
        labels = {"expand": "Araştırma genişletilecek", "coverage_sufficient": "Kapsam yeterli",
                  "budget_exhausted": "Bütçe/operasyon sınırı", "recovery_exhausted_no_progress": "İlerleme sağlanamadı"}
        return labels.get(payload.get("stop_reason"), str(payload.get("stop_reason", "")))
    if event_type == "audit_claim":
        return f"{payload.get('previous_status')} → {payload.get('status')}"
    if event_type == "appraisal_claim":
        return str(payload.get("appraisal", {}).get("grade", ""))
    if payload.get("error"):
        return str(payload["error"])[:300]
    count_labels = {"candidate_count": "Aday", "selected_count": "Seçilen", "new_count": "Yeni",
                    "merged_count": "Birleştirilen", "rejected_count": "Elenen",
                    "passage_count": "Pasaj", "claim_count": "İddia",
                    "generation_status": "Üretim durumu", "stop_reason": "Durma nedeni"}
    counts = [f"{count_labels[key]}: {payload[key]}" for key in (
        "candidate_count", "selected_count", "new_count", "merged_count", "rejected_count",
        "passage_count", "claim_count", "generation_status", "stop_reason",
    ) if key in payload]
    return " · ".join(counts) or EVENT_LABELS.get(event_type, event_type)


def coverage_checks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Explain the recorded check without recalculating or changing its decision."""
    c, t, i = (snapshot.get(key, {}) for key in ("coverage", "thresholds", "inputs"))
    quality = i.get("quality_diagnostics_active", False)
    targets = i.get("family_targets", {})
    family_numerator = sum(
        (1.0 if target["minimum_sources"] == 0 else min(
            1.0, i.get("source_families", {}).get(family, 0) / target["minimum_sources"]
        )) * target["weight"] for family, target in targets.items()
    )
    rows = [
        ("source_family_coverage", "Kaynak aileleri (ağırlıklı)", "minimum_source_coverage", ">=", True,
         [family_numerator, sum(target["weight"] for target in targets.values())]),
        ("query_branch_coverage", "Cevap üreten soru dalları", "minimum_query_branch_coverage", ">=", True,
         [sum(v >= 1 for v in i.get("branch_counts", {}).values()), len(i.get("branch_counts", {}))]),
        ("claim_audit_coverage", "Denetlenmiş major iddialar", "minimum_claim_audit_coverage", ">=", True,
         [i.get("audited_major_count"), i.get("major_claim_count")]),
        ("saturated_rounds", "Doygunluk turları", "saturation_rounds", ">=", True, None),
        ("unresolved_major_claims", "Çözümlenmemiş major iddialar", "unresolved_major_claim_limit", "<=", True, None),
        ("authority_coverage", "Otorite kapsamı", None, ">=", i.get("strict_authority"), None),
        ("sentinel_recall", "Kritik kaynak geri çağırımı", "minimum_sentinel_recall", ">=", i.get("has_sentinels"), None),
        ("estimated_completeness", "Tahmini tamlık", "minimum_estimated_completeness", ">=",
         quality and i.get("discovery_observations", 0) >= 5 and c.get("estimated_completeness") is not None, None),
        ("reserve_false_negative_rate", "Rezerv yanlış eleme", "maximum_reserve_false_negative_rate", "<=", quality, None),
        ("citation_frontier_novelty", "Atıf yeniliği", "maximum_citation_frontier_novelty", "<=", quality, None),
        ("critical_connector_coverage", "Gerekli connector kapsamı", None, ">=", i.get("has_required_connectors"), None),
    ]
    reason_keys = {"saturated_rounds": "query_saturation"}
    return [{"metric": key, "label": label, "value": c.get(key),
             "threshold": t.get(threshold) if threshold else 1.0,
             "operator": operator, "active": bool(active),
             "fraction": fraction if fraction is not None else i.get("fractions", {}).get(key),
             "result": "inactive" if not active else
             "fail" if reason_keys.get(key, key) in c.get("reasons", []) else "pass"}
            for key, label, threshold, operator, active, fraction in rows]
