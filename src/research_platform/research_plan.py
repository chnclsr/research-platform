"""The document a run must get approved before it is allowed to search.

Everything here is derived from settings and protocol -- no network, no database. A plan
may sit awaiting approval for hours, so it must not contain facts that go stale while it
waits: which connectors are reachable right now is a property of the run, not of the plan,
and stays in the `connectors_skipped` event where it already lives.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .acquisition import ACQUISITION_STRATEGY_ORDER
from .config import Settings
from .llm import LLMProvider
from .parsers import build_parser_registry
from .schemas import ResearchProtocol


def _date_scope(protocol: ResearchProtocol) -> dict[str, Any]:
    """Report the date window and, crucially, whether the user actually asked for it.

    ResearchProtocol.normalize_targets_and_validate_budget() quietly derives a range from
    wording like "son 3 ayda". That inference silently narrows every query, so the plan
    has to say out loud that it happened -- reading the flag the validator set rather than
    recomputing, because the same inference run a minute later yields different bounds.
    """
    start = protocol.scope.start_date
    end = protocol.scope.end_date
    return {
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "inferred_from_question": protocol.scope.dates_inferred,
        "geography": list(protocol.scope.geography),
        "domains": list(protocol.scope.domains),
    }


def _effective_limits(protocol: ResearchProtocol) -> list[dict[str, Any]]:
    """Which of the configured limits actually stop the run, and which are inert.

    `max_rounds` looks binding in the protocol but is ignored for an exhaustive
    literature scan (pipeline.py), which is exactly the kind of surprise this gate exists
    to remove.
    """
    budget = protocol.budget
    exhaustive = protocol.research_mode == "literature_scan" and budget.exhaustive_until_budget
    limits = [
        {
            "limit": "max_wall_minutes",
            "value": budget.max_wall_minutes,
            "binding": True,
            "note": "Toplama bütçesi. Dolduğunda yeni arama ve edinim başlamaz; "
                    "toplananlar normalize edilip raporlanır.",
        },
        {
            "limit": "max_sources",
            "value": budget.max_sources,
            "binding": budget.max_sources is not None,
            "note": "Kaynak tavanı."
            if budget.max_sources is not None
            else "Tavan yok — süre ve doygunluk karar verir.",
        },
        {
            "limit": "max_rounds",
            "value": budget.max_rounds,
            "binding": not exhaustive,
            "note": "research_mode=literature_scan ve exhaustive_until_budget açık "
                    "olduğu için tur tavanı yok sayılır."
            if exhaustive
            else "Tur tavanı bağlayıcı.",
        },
    ]
    return limits


def build_research_plan(
    *,
    protocol: ResearchProtocol,
    state: Mapping[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """Assemble the approval document from resolved configuration and planning output."""
    missions = [
        {
            "branch_id": mission.get("branch_id"),
            "query": mission.get("query"),
            "required_family": mission.get("required_family"),
            "result_limit": mission.get("result_limit"),
        }
        for mission in state.get("missions", [])
    ]
    selection = protocol.connectors
    checkpoints = [
        name
        for name in ("planning_questions", "source_review", "outline_review")
        if getattr(protocol.hitl, name)
    ]
    return {
        "revision": len(state.get("plan_feedback", [])),
        "questions": {
            "primary": protocol.primary_question,
            "sub_questions": list(state.get("sub_questions", [])),
            "concepts": list(state.get("concepts", [])),
        },
        "query_plan": missions,
        "source_selection": {
            "profile": selection.profile,
            "included_families": [family.value for family in selection.included_families],
            "included_connectors": list(selection.included_connectors),
            "excluded_connectors": list(selection.excluded_connectors),
            "required_connectors": list(selection.required_connectors),
            "trusted_domains": list(selection.trusted_domains),
            "citation_depth": selection.citation_depth,
        },
        "date_scope": _date_scope(protocol),
        "budget": protocol.budget.model_dump(mode="json"),
        "effective_limits": _effective_limits(protocol),
        "stopping_criteria": protocol.stopping_criteria.model_dump(mode="json"),
        "models": {
            "llm": settings.llm_model,
            "embedding": settings.embedding_model,
            "vision": settings.vision_model,
            "context_tokens": settings.llm_context_tokens,
        },
        "acquisition": {
            "strategy_order": list(ACQUISITION_STRATEGY_ORDER),
            "parsers": [parser.id for parser in build_parser_registry().parsers],
            "parser_overrides": dict(protocol.parsers.overrides),
        },
        "deliverables": {
            "output_mode": protocol.output_mode,
            "report_language": protocol.report_language,
            "languages": list(protocol.languages),
            "bundles": ["raw_bundle.zip", "result_bundle.zip", "research_bundle.zip"],
            "note": "output_mode=raw iddia çıkarımını tamamen atlar."
            if protocol.output_mode == "raw"
            else "İddia çıkarımı, sentez ve Word raporu üretilir.",
        },
        "remaining_checkpoints": checkpoints,
        "feedback": list(state.get("plan_feedback", [])),
        "strategy_note": "",
    }


STRATEGY_SYSTEM = (
    "You write a short research strategy note for a plan that a person is about to "
    "approve. Return JSON {\"strategy\": \"...\"} with 3 to 6 sentences in the requested "
    "language. Describe only what the supplied plan already states: how the questions "
    "will be approached, what the budget implies, and where the plan is weak. Never "
    "invent sources, numbers or tools that are not in the plan."
)


async def plan_strategy(llm: LLMProvider, plan: dict[str, Any], language: str = "tr") -> str:
    """One narrative paragraph beside the deterministic dump -- never instead of it.

    A failure here must not block approval: the plan is complete without the note, so the
    gate opens with an empty string rather than failing the run.
    """
    payload = {
        "language": language,
        "questions": plan.get("questions", {}),
        "query_plan": plan.get("query_plan", []),
        "budget": plan.get("budget", {}),
        "effective_limits": plan.get("effective_limits", []),
        "date_scope": plan.get("date_scope", {}),
        "feedback": plan.get("feedback", []),
    }
    try:
        data = await llm.complete_json(STRATEGY_SYSTEM, json.dumps(payload, ensure_ascii=False))
    except Exception:
        return ""
    if isinstance(data, dict):
        return str(data.get("strategy", "")).strip()[:2000]
    return ""
