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
from .llm import LLMProvider, display_items
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


# The prose the plan itself carries, in the language the request arrived in. Only text a
# person reads lives here: connector, parser and model names stay as they are because they
# are the running system's identifiers, not words.
NOTES = {
    "tr": {
        "wall": "Toplama bütçesi. Dolduğunda yeni arama ve edinim başlamaz; "
                "toplananlar normalize edilip raporlanır.",
        "sources": "Kaynak tavanı.",
        "sources_none": "Tavan yok — süre ve doygunluk karar verir.",
        "rounds_inert": "research_mode=literature_scan ve exhaustive_until_budget açık "
                        "olduğu için tur tavanı yok sayılır.",
        "rounds": "Tur tavanı bağlayıcı.",
        "raw": "output_mode=raw iddia çıkarımını tamamen atlar.",
        "full": "İddia çıkarımı, sentez ve Word raporu üretilir.",
    },
    "en": {
        "wall": "Collection budget. Once it runs out no new search or acquisition starts; "
                "what was collected is normalised and reported.",
        "sources": "Source cap.",
        "sources_none": "No cap — time and saturation decide.",
        "rounds_inert": "Ignored: research_mode=literature_scan with "
                        "exhaustive_until_budget leaves the round cap inert.",
        "rounds": "Round cap is binding.",
        "raw": "output_mode=raw skips claim extraction entirely.",
        "full": "Claim extraction, synthesis and the Word report are produced.",
    },
}


def _effective_limits(protocol: ResearchProtocol, language: str) -> list[dict[str, Any]]:
    """Which of the configured limits actually stop the run, and which are inert.

    `max_rounds` looks binding in the protocol but is ignored for an exhaustive
    literature scan (pipeline.py), which is exactly the kind of surprise this gate exists
    to remove.
    """
    budget = protocol.budget
    notes = NOTES[language]
    exhaustive = protocol.research_mode == "literature_scan" and budget.exhaustive_until_budget
    limits = [
        {
            "limit": "max_wall_minutes",
            "value": budget.max_wall_minutes,
            "binding": True,
            "note": notes["wall"],
        },
        {
            "limit": "max_sources",
            "value": budget.max_sources,
            "binding": budget.max_sources is not None,
            "note": notes["sources"] if budget.max_sources is not None else notes["sources_none"],
        },
        {
            "limit": "max_rounds",
            "value": budget.max_rounds,
            "binding": not exhaustive,
            "note": notes["rounds_inert"] if exhaustive else notes["rounds"],
        },
    ]
    return limits


def build_research_plan(
    *,
    protocol: ResearchProtocol,
    state: Mapping[str, Any],
    settings: Settings,
    sub_questions_display: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the approval document from resolved configuration and planning output.

    The plan reads in the language the request arrived in, while every string the run will
    actually use -- queries, connector, parser and model names -- stays exactly as it runs.
    """
    language = protocol.display_language()
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
    display_sub_questions = list(
        sub_questions_display or protocol.sub_question_report_titles
    )
    checkpoints = [
        name
        for name in ("planning_questions", "source_review", "outline_review")
        if getattr(protocol.hitl, name)
    ]
    return {
        "revision": len(state.get("plan_feedback", [])),
        "display_language": language,
        "questions": {
            "primary": protocol.primary_question,
            # The run researches in English. Showing the user's own wording next to the
            # translation is the point of approving before the budget is spent: a wrong
            # translation is the one mistake that quietly redirects the whole run.
            "original": protocol.original_question,
            "original_language": protocol.original_language,
            "translated": bool(protocol.original_question),
            "sub_questions": list(state.get("sub_questions", [])),
            # Reading copy only. The English list above is what becomes search queries.
            "sub_questions_display": display_sub_questions,
            "sub_question_records": [
                {
                    "id": f"SQ{index:02d}",
                    "search_text": question,
                    "evidence_match_text": question,
                    "report_title": (
                        display_sub_questions[index - 1]
                        if index <= len(display_sub_questions)
                        and display_sub_questions[index - 1]
                        else question
                    ),
                }
                for index, question in enumerate(state.get("sub_questions", []), 1)
            ],
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
        "scope_criteria": (
            protocol.scope_criteria.model_dump(mode="json")
            if protocol.scope_criteria is not None
            else None
        ),
        "budget": protocol.budget.model_dump(mode="json"),
        "effective_limits": _effective_limits(protocol, language),
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
            "note": NOTES[language]["raw"]
            if protocol.output_mode == "raw"
            else NOTES[language]["full"],
        },
        "remaining_checkpoints": checkpoints,
        # What the user chose while scoping, so the plan shows how their answers landed.
        "planning_answers": list(state.get("planning_answers", [])),
        # The subset that became protocol fields rather than prompt guidance. Shown
        # separately because it is the only part the run is obliged to honour.
        "applied_settings": list(state.get("applied_settings", [])),
        "feedback": list(state.get("plan_feedback", [])),
        # Rejections left before the gate gives up and cancels the run. Carried in the plan
        # because the moment a person needs it is the moment they are deciding whether to
        # reject again, and the limit was being reached without anyone having been told it
        # existed.
        "revisions_left": max(
            settings.plan_max_revisions - len(state.get("plan_feedback", []) or []), 0
        ),
        "strategy_note": "",
    }


def _strategy_system(language: str) -> str:
    """The language belongs in the system prompt, not in the payload.

    It used to say "in the requested language" and pass {"language": "tr"} inside JSON
    surrounded by English plan content; the model mirrored the content and wrote English.
    """
    target = "Turkish" if language == "tr" else "English"
    return (
        f"You write a short research strategy note for a plan that a person is about to "
        f"approve. Write it in {target}. Return JSON {{\"strategy\": \"...\"}} with 3 to 6 "
        f"sentences. Describe only what the supplied plan already states: how the questions "
        f"will be approached, what the budget implies, and where the plan is weak. Never "
        f"invent sources, numbers or tools that are not in the plan."
    )


def _strategy_payload(plan: dict[str, Any]) -> dict[str, Any]:
    """The half of the plan a strategy note may talk about."""
    return {
        "questions": plan.get("questions", {}),
        "scope_criteria": plan.get("scope_criteria"),
        "query_plan": plan.get("query_plan", []),
        "budget": plan.get("budget", {}),
        "effective_limits": plan.get("effective_limits", []),
        "date_scope": plan.get("date_scope", {}),
        "feedback": plan.get("feedback", []),
    }


async def plan_display_and_strategy(
    llm: LLMProvider,
    plan: dict[str, Any],
    items: list[str],
    language: str,
) -> tuple[list[str], str]:
    """The reading copy of the sub-questions and the strategy note, in one request.

    Both are display-only, both are written in the same language about the same plan, and
    both are optional -- so they are asked for together rather than spending two calls of an
    external quota on one approval screen. Failure stays fail-open on each half separately:
    a missing or mismatched translation leaves the English list, a missing note leaves the
    plan without one, and neither holds the gate shut.
    """
    if not items:
        return [], await plan_strategy(llm, plan, language)
    target = "Turkish" if language == "tr" else "English"
    try:
        data = await llm.complete_json(
            f"You prepare an approval screen for a research plan. Write in {target}. Return "
            'JSON with two keys. items: SUB_QUESTIONS translated into '
            f"{target}, same order and count, keeping named entities, acronyms and "
            'identifiers as they are. strategy: 3 to 6 sentences describing only what PLAN '
            "already states -- how the questions will be approached, what the budget "
            "implies, and where the plan is weak. Never invent sources, numbers or tools "
            "that are not in the plan. No prose outside the JSON.",
            json.dumps(
                {"PLAN": _strategy_payload(plan), "SUB_QUESTIONS": items},
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001 - the approval screen is complete without either half
        return [], ""
    if not isinstance(data, dict):
        return [], ""
    return display_items(data, items), str(data.get("strategy", "")).strip()[:2000]


async def plan_strategy(llm: LLMProvider, plan: dict[str, Any], language: str = "tr") -> str:
    """One narrative paragraph beside the deterministic dump -- never instead of it.

    A failure here must not block approval: the plan is complete without the note, so the
    gate opens with an empty string rather than failing the run.
    """
    try:
        data = await llm.complete_json(
            _strategy_system(language),
            json.dumps(_strategy_payload(plan), ensure_ascii=False),
        )
    except Exception:
        return ""
    if isinstance(data, dict):
        return str(data.get("strategy", "")).strip()[:2000]
    return ""
