from __future__ import annotations

import pytest

from research_platform.config import get_settings
from research_platform.research_plan import build_research_plan, plan_strategy
from research_platform.schemas import ResearchProtocol


def protocol(**overrides) -> ResearchProtocol:
    payload = {
        "title": "Plan document",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(overrides)
    return ResearchProtocol(**payload)


def plan_for(protocol_obj: ResearchProtocol, **state) -> dict:
    return build_research_plan(
        protocol=protocol_obj,
        state=state,
        settings=get_settings(),
    )


def test_plan_states_the_questions_and_query_branches_that_will_run():
    plan = plan_for(
        protocol(),
        sub_questions=["Which datasets are used?"],
        concepts=["nodule detection"],
        missions=[
            {
                "branch_id": "query:0",
                "query": "pulmonary nodule detection CT",
                "required_family": "academic",
                "result_limit": 10,
            }
        ],
    )
    assert plan["questions"]["sub_questions"] == ["Which datasets are used?"]
    assert plan["query_plan"][0]["branch_id"] == "query:0"
    # The connector list is deliberately absent: reachability is a run-time fact that
    # would go stale while the plan waits for approval.
    assert "connectors" not in plan
    assert "profile" in plan["source_selection"]


def test_plan_says_when_the_date_window_came_from_the_question_rather_than_the_user():
    inferred = plan_for(
        protocol(primary_question="Which lung CT AI results appeared in the last 3 months?")
    )
    assert inferred["date_scope"]["inferred_from_question"] is True
    assert inferred["date_scope"]["start_date"]

    stated = plan_for(protocol())
    assert stated["date_scope"]["inferred_from_question"] is False


def test_plan_marks_the_round_cap_inert_for_an_exhaustive_literature_scan():
    limits = {row["limit"]: row for row in plan_for(protocol())["effective_limits"]}
    # literature_scan + exhaustive_until_budget is the default pair, and pipeline.py
    # ignores max_rounds for it -- the plan has to say so rather than list a limit that
    # never fires.
    assert limits["max_rounds"]["binding"] is False
    assert limits["max_wall_minutes"]["binding"] is True
    assert limits["max_wall_minutes"]["value"] == 30
    assert limits["max_sources"]["binding"] is False

    focused = plan_for(
        protocol(research_mode="focused_answer", budget={"max_wall_minutes": 15, "max_sources": 8})
    )
    focused_limits = {row["limit"]: row for row in focused["effective_limits"]}
    assert focused_limits["max_rounds"]["binding"] is True
    assert focused_limits["max_sources"]["binding"] is True


def test_plan_carries_models_acquisition_order_and_rejection_feedback():
    settings = get_settings()
    plan = plan_for(protocol(), plan_feedback=["Add regulatory sources"])
    assert plan["models"]["llm"] == settings.llm_model
    assert plan["models"]["context_tokens"] == settings.llm_context_tokens
    assert plan["acquisition"]["strategy_order"][0] == "direct"
    assert "html_structured" in plan["acquisition"]["parsers"]
    assert plan["feedback"] == ["Add regulatory sources"]
    assert plan["revision"] == 1


class BrokenLLM:
    async def complete_json(self, system: str, user: str):
        raise RuntimeError("model unavailable")


class NotesLLM:
    async def complete_json(self, system: str, user: str):
        return {"strategy": "  Search academic sources first.  "}


@pytest.mark.asyncio
async def test_strategy_note_is_optional_and_never_blocks_approval():
    """The deterministic plan is the contract; the narrative is a courtesy."""
    plan = plan_for(protocol())
    assert await plan_strategy(BrokenLLM(), plan) == ""
    assert await plan_strategy(NotesLLM(), plan) == "Search academic sources first."
