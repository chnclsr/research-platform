from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_platform.schemas import ResearchProtocol, SourceFamily
from research_platform.scoping import (
    LABEL_MAX_LENGTH,
    apply_planning_answers,
    date_suffix,
    feedback_answers,
    fixed_questions,
    slugify,
)


def protocol(**overrides) -> ResearchProtocol:
    payload = {
        "title": "Scoping run",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(overrides)
    return ResearchProtocol.model_validate(payload)


def test_slugify_keeps_turkish_words_readable():
    # NFKD leaves the dotless i alone, so an ASCII filter on its own eats it: "isi"
    # would come back as "s" and the label would say nothing about the topic.
    assert slugify("Akciğer BT'sinde yapay zeka ısısı") == "Akciger_BT_sinde_yapay_zeka_isisi"
    assert slugify("What is the role of AI in lung CT?") == "role_AI_lung_CT"
    assert slugify("???") == ""


def test_slugify_stops_at_a_word_boundary():
    slug = slugify("alpha beta gamma delta epsilon zeta eta theta", max_length=20)
    assert len(slug) <= 20
    assert not slug.endswith("_")


def test_a_tapped_option_becomes_a_protocol_field():
    before = protocol()
    after, applied = apply_planning_answers(
        before,
        [
            {"question": "Dates?", "answer": "Son 1 yıl", "id": "date_scope",
             "value": "last_1y"},
            {"question": "Sources?", "answer": "Resmî", "id": "source_families",
             "value": "official"},
        ],
    )
    assert after.connectors.included_families == [
        SourceFamily.OFFICIAL_LEGAL, SourceFamily.WEB, SourceFamily.ACADEMIC
    ]
    assert after.connectors.profile == "custom"
    window = (after.scope.end_date - after.scope.start_date).days
    assert 360 <= window <= 370
    # The window is now a decision, not something read out of the wording.
    assert after.scope.dates_inferred is False
    # Targets were rebuilt for the new families rather than filtered down to nothing.
    assert set(after.family_targets) == set(after.connectors.included_families)
    assert [item["id"] for item in applied] == ["date_scope", "source_families"]


def test_a_typed_answer_binds_nothing_and_stays_guidance():
    before = protocol()
    after, applied = apply_planning_answers(
        before,
        [{"question": "Sources?", "answer": "Only Turkish hospital reports", "id": "",
          "value": ""}],
    )
    assert after is before
    assert applied == []


def test_a_value_the_table_does_not_know_changes_nothing():
    """A model-invented option must not be able to corrupt the protocol."""
    before = protocol()
    after, applied = apply_planning_answers(
        before,
        [{"question": "Sources?", "answer": "Clinical anecdotes", "id": "source_families",
          "value": "clinical_anecdotes"}],
    )
    assert after is before
    assert applied == []


def test_a_selection_that_would_not_validate_leaves_the_protocol_alone():
    """Widening the families past max_sources must cost the answer, not the run."""
    before = protocol(
        budget={"max_wall_minutes": 30, "max_sources": 2},
        connectors={"included_families": ["academic", "web"]},
    )
    after, applied = apply_planning_answers(
        before,
        [{"question": "Sources?", "answer": "Geniş", "id": "source_families",
          "value": "core"}],
    )
    assert after is before
    assert applied == []


def test_no_date_limit_clears_the_window():
    before = protocol(primary_question="Son 3 ay içinde akciğer BT yapay zeka çalışmaları")
    assert before.scope.dates_inferred is True
    after, applied = apply_planning_answers(
        before,
        [{"question": "Dates?", "answer": "Sınır yok", "id": "date_scope", "value": "any"}],
    )
    assert after.scope.start_date is None and after.scope.end_date is None
    assert after.scope.dates_inferred is False
    assert applied[0]["detail"] == "sınır yok"


def test_keeping_the_inferred_window_is_offered_first_and_changes_nothing():
    before = protocol(primary_question="Son 3 ay içinde akciğer BT yapay zeka çalışmaları")
    questions = fixed_questions(before, "tr")
    assert questions[0]["values"][0] == "keep"
    assert before.scope.start_date.date().isoformat() in questions[0]["options"][0]

    after, applied = apply_planning_answers(
        before,
        [{"question": "Dates?", "answer": "Aynı", "id": "date_scope", "value": "keep"}],
    )
    assert after is before
    assert applied == []


def test_fixed_questions_offer_only_values_that_can_be_applied():
    questions = fixed_questions(protocol(), "en")
    assert [item["id"] for item in questions] == ["date_scope", "source_families"]
    for item in questions:
        assert len(item["options"]) == len(item["values"])
        # Every option has to be applicable; an option that binds to nothing is exactly
        # the failure this module exists to remove.
        for value in item["values"]:
            after, applied = apply_planning_answers(
                protocol(),
                [{"question": item["question"], "answer": "x", "id": item["id"],
                  "value": value}],
            )
            assert applied or value == "keep"


def test_date_suffix_describes_the_window_the_run_will_use():
    end = datetime.now(timezone.utc)
    assert date_suffix(protocol()) == ""
    quarter = protocol(scope={"start_date": end - timedelta(days=90), "end_date": end})
    assert date_suffix(quarter) == "_last_3m"
    triennium = protocol(scope={"start_date": end - timedelta(days=3 * 365), "end_date": end})
    assert date_suffix(triennium) == "_last_3y"


def test_a_label_is_short_enough_to_retype_into_a_command():
    """Measured on a live run: the model produced
    "Research artificial intelligence studies that", which slugified to 44 characters of
    which two words carried the topic. The label is now typed into /cancel and /status,
    so filler in front of the meaningful part is a usability cost, not just noise."""
    slug = slugify(
        "Research artificial intelligence studies that write radiology reports",
        max_length=LABEL_MAX_LENGTH,
    )
    assert slug == "artificial_intelligence_write"
    assert len(slug) <= LABEL_MAX_LENGTH
    for filler in ("research", "studies", "study", "that", "about", "using", "review"):
        assert filler not in slugify(f"{filler} nodule detection").casefold()


def test_feedback_naming_a_window_binds_it_like_a_tapped_option():
    """A rejection is another way of answering the question the gate already asked."""
    assert feedback_answers(["Tarih aralığını son 1 yıl yap"]) == [
        {"id": "date_scope", "value": "last_1y"}
    ]
    assert feedback_answers(["make it the last 2 years please"]) == [
        {"id": "date_scope", "value": "last_2y"}
    ]
    assert feedback_answers(["tarih sınırı olmasın"]) == [
        {"id": "date_scope", "value": "any"}
    ]


def test_the_later_note_wins_when_the_user_revises_twice():
    assert feedback_answers(["son 5 yıl olsun", "aslında son 1 yıl yeter"]) == [
        {"id": "date_scope", "value": "last_1y"}
    ]


def test_feedback_binds_a_family_only_behind_an_explicit_only():
    """Mentioning a family describes the topic; narrowing to it is a different sentence."""
    assert feedback_answers(["sadece akademik kaynak kullan"]) == [
        {"id": "source_families", "value": "academic"}
    ]
    # The topic happens to be academic sources. Nothing binds; it stays prompt guidance.
    assert feedback_answers(["akademik kaynakların maliyetini de ele al"]) == []


def test_feedback_that_names_nothing_bindable_changes_nothing():
    assert feedback_answers(["daha derin analiz istiyorum"]) == []


def test_a_window_from_feedback_reaches_the_protocol():
    before = protocol()
    answers = feedback_answers(["son 1 yıl olsun"])
    after, applied = apply_planning_answers(before, answers)
    window = (after.scope.end_date - after.scope.start_date).days
    assert 360 <= window <= 370
    assert after.scope.dates_chosen is True
    assert [item["id"] for item in applied] == ["date_scope"]


def test_an_arbitrary_year_count_binds_even_though_no_button_offers_it():
    """The buttons offer three windows; a typed sentence is not limited to them."""
    after, applied = apply_planning_answers(
        protocol(), feedback_answers(["son 2 yıl yeterli"])
    )
    window = (after.scope.end_date - after.scope.start_date).days
    assert 720 <= window <= 740
    assert applied
