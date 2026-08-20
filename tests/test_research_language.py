from __future__ import annotations

import httpx
import pytest

from conftest import acting_principal
from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol

TURKISH_QUESTION = "Akciğer BT görüntülemesinde yapay zeka tanısal doğruluğu ne sağlıyor?"
ENGLISH_QUESTION = "What does AI provide for diagnostic accuracy in lung CT imaging?"


class TranslatingLLM:
    def __init__(self, result=None, fail: bool = False):
        self.calls = 0
        self.result = result or {
            "question": ENGLISH_QUESTION,
            "sub_questions": ["Which datasets are used?"],
        }
        self.fail = fail

    async def complete_json(self, system: str, user: str):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.result

    def drain_metrics(self):
        return []


async def run_with(llm, **protocol_overrides):
    payload = {
        "title": "Language",
        "primary_question": TURKISH_QUESTION,
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(protocol_overrides)
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(ResearchProtocol(**payload))
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = llm
        protocol = await pipeline._to_research_language(
            row.id, ResearchProtocol.model_validate(row.protocol)
        )
        events = {event.event_type for event in await repo.events_after(row.id)}
        stored = await repo.get_run(row.id)
    return protocol, events, stored


@pytest.mark.asyncio
async def test_a_turkish_request_is_researched_in_english_and_keeps_the_original():
    llm = TranslatingLLM()
    protocol, events, stored = await run_with(llm, sub_questions=["Hangi veri setleri?"])
    assert llm.calls == 1
    assert protocol.primary_question == ENGLISH_QUESTION
    assert protocol.sub_questions == ["Which datasets are used?"]
    assert protocol.original_question == TURKISH_QUESTION
    assert protocol.original_sub_questions == ["Hangi veri setleri?"]
    assert protocol.original_language == "tr"
    assert "research_language_translated" in events
    # Persisted: a resumed run reloads its protocol from the row, and every later stage
    # reads the English wording from there.
    assert stored.protocol["primary_question"] == ENGLISH_QUESTION
    assert stored.protocol["original_question"] == TURKISH_QUESTION


@pytest.mark.asyncio
async def test_an_unmistakably_english_request_costs_no_translation_call():
    llm = TranslatingLLM()
    protocol, events, _ = await run_with(
        llm,
        primary_question=(
            "What does the evidence say about AI and radiologist performance, "
            "and which findings come from screening trials with reported limitations?"
        ),
    )
    assert llm.calls == 0
    assert protocol.original_question is None
    assert "research_language_translated" not in events


@pytest.mark.asyncio
async def test_a_short_english_request_is_not_reported_as_translated():
    """detect_language() wants two English stopwords, so short questions reach the model.

    When it hands the text back unchanged nothing was translated, and the plan must not
    show the user a "your question" block for a question that never moved.
    """
    llm = TranslatingLLM(result={"question": ENGLISH_QUESTION, "sub_questions": []})
    protocol, events, stored = await run_with(llm, primary_question=ENGLISH_QUESTION)
    assert llm.calls == 1
    assert protocol.original_question is None
    assert protocol.primary_question == ENGLISH_QUESTION
    assert "research_language_translated" not in events
    assert stored.protocol["original_question"] is None


@pytest.mark.asyncio
async def test_a_failed_translation_leaves_the_run_alive_in_the_original_language():
    """Researching in Turkish is worse than in English; failing the run is worse than both."""
    llm = TranslatingLLM(fail=True)
    protocol, events, stored = await run_with(llm)
    assert protocol.primary_question == TURKISH_QUESTION
    assert protocol.original_question is None
    assert "research_language_fallback" in events
    assert stored.protocol["primary_question"] == TURKISH_QUESTION


@pytest.mark.asyncio
async def test_translation_does_not_run_twice_when_a_run_resumes():
    llm = TranslatingLLM()
    protocol, _, _ = await run_with(
        llm,
        primary_question=ENGLISH_QUESTION,
        original_question=TURKISH_QUESTION,
        original_language="tr",
    )
    assert llm.calls == 0
    assert protocol.original_question == TURKISH_QUESTION


def test_report_prints_the_question_in_the_language_it_is_written_in():
    translated = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        sub_questions=["Which datasets are used?"],
        original_question=TURKISH_QUESTION,
        original_sub_questions=["Hangi veri setleri?"],
        original_language="tr",
        report_language="tr",
        budget={"max_wall_minutes": 30},
    )
    assert translated.question_for_report() == TURKISH_QUESTION
    assert translated.sub_questions_for_report() == ["Hangi veri setleri?"]

    # An English report of a Turkish question prints the English wording rather than
    # inventing a translation back.
    english_report = translated.model_copy(update={"report_language": "en"})
    assert english_report.question_for_report() == ENGLISH_QUESTION
    assert english_report.sub_questions_for_report() == ["Which datasets are used?"]

    untranslated = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        report_language="en",
        budget={"max_wall_minutes": 30},
    )
    assert untranslated.question_for_report() == ENGLISH_QUESTION


def test_display_language_follows_the_request_not_the_report():
    """The plan is read by whoever typed the question; report_language is about the
    deliverable, which is a different decision."""
    turkish = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        original_question=TURKISH_QUESTION,
        original_language="tr",
        report_language="en",
        budget={"max_wall_minutes": 30},
    )
    assert turkish.display_language() == "tr"

    english = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        original_language="en",
        report_language="tr",
        budget={"max_wall_minutes": 30},
    )
    assert english.display_language() == "en"

    # Runs recorded before the field existed keep the panel's original Turkish.
    legacy = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        budget={"max_wall_minutes": 30},
    )
    assert legacy.original_language == ""
    assert legacy.display_language() == "tr"


@pytest.mark.asyncio
async def test_the_model_reports_the_source_language_detect_cannot_settle():
    """detect_language() answers "und" for short text, which left original_language unusable
    and made a Turkish report print the English question."""
    short_turkish = "Yapay zeka radyolojide ne yapar?"
    llm = TranslatingLLM(result={
        "question": "What does artificial intelligence do in radiology?",
        "sub_questions": [],
        "source_language": "tr",
    })
    protocol, _, stored = await run_with(llm, primary_question=short_turkish)
    assert protocol.original_language == "tr"
    assert stored.protocol["original_language"] == "tr"
    assert protocol.display_language() == "tr"
    # The report can now print what the user typed instead of the translation.
    turkish_report = protocol.model_copy(update={"report_language": "tr"})
    assert turkish_report.question_for_report() == short_turkish


@pytest.mark.asyncio
async def test_an_english_request_records_its_language_too():
    llm = TranslatingLLM()
    protocol, _, stored = await run_with(
        llm,
        primary_question=(
            "What does the evidence say about AI and radiologist performance, "
            "and which findings come from screening trials with reported limitations?"
        ),
    )
    assert llm.calls == 0
    assert protocol.display_language() == "en"
    assert stored.protocol["original_language"] == "en"


def test_display_translation_accepts_the_shapes_the_model_actually_returns():
    """Asked for {"items": [...]}, a 4B model answers with a bare array or a
    source-to-translation mapping just as often. Measured against the live model: it
    returned the mapping, and the strict reader silently dropped every translation."""
    from research_platform.llm import _display_items

    items = ["What is the diagnostic accuracy?", "Which datasets are used?"]
    expected = ["Tanısal doğruluk nedir?", "Hangi veri setleri kullanılıyor?"]

    assert _display_items({"items": expected}, items) == expected
    assert _display_items(expected, items) == expected
    assert _display_items(dict(zip(items, expected)), items) == expected

    # Anything that cannot be lined up one-to-one is dropped rather than misaligned.
    assert _display_items({"items": expected[:1]}, items) == []
    assert _display_items({"translation": "tek bir dize"}, items) == []
    assert _display_items("prose", items) == []


def test_relevance_gates_see_both_languages():
    protocol = ResearchProtocol(
        title="Language",
        primary_question=ENGLISH_QUESTION,
        sub_questions=["Which datasets are used?"],
        original_question=TURKISH_QUESTION,
        original_sub_questions=["Hangi veri setleri?"],
        original_language="tr",
        budget={"max_wall_minutes": 30},
    )
    assert protocol.primary_questions() == [ENGLISH_QUESTION, TURKISH_QUESTION]
    phrasings = protocol.research_questions()
    assert TURKISH_QUESTION in phrasings and ENGLISH_QUESTION in phrasings
    assert "Hangi veri setleri?" in phrasings
