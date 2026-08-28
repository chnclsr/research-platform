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


def test_plan_shows_the_users_own_wording_next_to_the_english_research_question():
    """The one mistake that quietly redirects a whole run is a wrong translation."""
    translated = plan_for(
        protocol(
            primary_question="What does AI provide for lung CT diagnostic accuracy?",
            original_question="Akciğer BT'sinde yapay zeka tanısal doğruluğu ne sağlıyor?",
            original_language="tr",
        )
    )["questions"]
    assert translated["translated"] is True
    assert translated["original"].startswith("Akciğer")
    assert translated["original_language"] == "tr"

    untouched = plan_for(protocol())["questions"]
    assert untouched["translated"] is False
    assert untouched["original"] is None


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
    assert plan["acquisition"]["strategy_order"][:2] == ["github_repository", "direct"]
    assert "html_structured" in plan["acquisition"]["parsers"]
    assert plan["feedback"] == ["Add regulatory sources"]
    assert plan["revision"] == 1


def test_the_plan_separates_answers_that_became_settings_from_answers_that_only_steer():
    """Only the applied half is something the run has no choice about."""
    plan = plan_for(
        protocol(),
        planning_answers=["Which angle? -> Clinical"],
        applied_settings=[{"id": "source_families", "label": "Kaynak", "value": "official",
                           "detail": "official_legal, web, academic"}],
    )
    assert plan["planning_answers"] == ["Which angle? -> Clinical"]
    assert plan["applied_settings"][0]["detail"] == "official_legal, web, academic"


def test_the_plan_reads_in_the_language_the_request_arrived_in():
    """Display only: the strings the run will use are identical in both renderings."""
    turkish = plan_for(
        protocol(original_question="Hangi yöntemler BT'de nodül tespit ediyor?",
                 original_language="tr"),
        missions=[{"branch_id": "query:0", "query": "pulmonary nodule detection CT"}],
    )
    english = plan_for(
        protocol(original_language="en"),
        missions=[{"branch_id": "query:0", "query": "pulmonary nodule detection CT"}],
    )
    assert turkish["display_language"] == "tr"
    assert english["display_language"] == "en"

    tr_limits = {row["limit"]: row["note"] for row in turkish["effective_limits"]}
    en_limits = {row["limit"]: row["note"] for row in english["effective_limits"]}
    assert "Toplama bütçesi" in tr_limits["max_wall_minutes"]
    assert "Collection budget" in en_limits["max_wall_minutes"]
    assert tr_limits["max_rounds"] != en_limits["max_rounds"]
    assert turkish["deliverables"]["note"] != english["deliverables"]["note"]

    # What the run actually does is the same text in both.
    assert turkish["query_plan"] == english["query_plan"]
    assert turkish["acquisition"] == english["acquisition"]
    assert turkish["models"] == english["models"]


def test_sub_question_display_copies_never_replace_the_operational_list():
    plan = build_research_plan(
        protocol=protocol(original_question="Hangi yöntemler?", original_language="tr"),
        state={"sub_questions": ["Which datasets are used?"]},
        settings=get_settings(),
        sub_questions_display=["Hangi veri setleri kullanılıyor?"],
    )
    assert plan["questions"]["sub_questions"] == ["Which datasets are used?"]
    assert plan["questions"]["sub_questions_display"] == ["Hangi veri setleri kullanılıyor?"]


def test_the_strategy_prompt_names_the_language_instead_of_burying_it():
    """It used to pass {"language": "tr"} inside JSON full of English plan content, and the
    model mirrored the content."""
    from research_platform.research_plan import _strategy_system

    assert "in Turkish" in _strategy_system("tr")
    assert "in English" in _strategy_system("en")


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


def test_the_plan_says_how_many_revisions_are_left():
    """The gate cancels at the limit; the person deciding whether to reject needs to know."""
    settings = get_settings()
    fresh = plan_for(protocol())
    assert fresh["revisions_left"] == settings.plan_max_revisions
    once = plan_for(protocol(), plan_feedback=["Add regulatory sources"])
    assert once["revisions_left"] == settings.plan_max_revisions - 1
    spent = plan_for(
        protocol(), plan_feedback=[f"note {n}" for n in range(settings.plan_max_revisions + 2)]
    )
    # Never negative: the count is read as "how many are left", not as an offset.
    assert spent["revisions_left"] == 0
