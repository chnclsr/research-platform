from __future__ import annotations

import io

import httpx
import pytest
from conftest import acting_principal
from docx import Document

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.exporter import build_exports, word_report_name
from research_platform.pipeline import ResearchPipeline
from research_platform.report_titles import clean_report_titles
from research_platform.repository import Repository
from research_platform.schemas import CoverageMetrics, ResearchProtocol
from research_platform.storage import ObjectStore

TITLES = {
    "tr": "Akciğer BT Görüntülerinde Yapay Zekâ ve Tanısal Doğruluk",
    "en": "Artificial Intelligence and Diagnostic Accuracy in Lung CT Imaging",
}
QUESTION = "What does the evidence say about diagnostic accuracy and AI in lung CT?"


class NamingLLM:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def complete_json(self, system, user):
        self.calls.append((system, user))
        if self.fail:
            raise RuntimeError("offline")
        assert "report_titles" in system
        assert "Turkish" in system and "English" in system
        return {
            "question": QUESTION,
            "sub_questions": [],
            "source_language": "tr",
            "label": "ai_lung_ct",
            "report_titles": TITLES,
        }

    def drain_metrics(self):
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize("translated", [False, True])
@pytest.mark.parametrize("language", ["tr", "en"])
async def test_naming_persists_both_titles_in_one_call_and_reuses_them(translated, language):
    await create_schema()
    question = "Akciğer BT görüntülerinde yapay zekâ ne sağlar?" if translated else QUESTION
    protocol = ResearchProtocol(
        title="Original question title", primary_question=question,
        budget={"max_wall_minutes": 30}, report_language=language,
    )
    llm = NamingLLM()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = llm
        protocol, suggested = await pipeline._to_research_language(row.id, protocol)
        protocol = await pipeline._name_run(row.id, protocol, suggested)
        assert len(llm.calls) == 1
        assert protocol.title_for_report() == TITLES[language]
        assert protocol.label == "ai_lung_ct"
        assert protocol.title == "Original question title"
        stored = await repo.get_run(row.id)
        restored = ResearchProtocol.model_validate(stored.protocol)
        restored = await pipeline._name_run(row.id, restored)
        assert len(llm.calls) == 1
        other = "en" if language == "tr" else "tr"
        restored.report_language = other
        assert restored.title_for_report() == TITLES[other]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_client_label_is_preserved_and_model_failure_is_nonfatal(fail):
    await create_schema()
    protocol = ResearchProtocol(
        title="User supplied title", primary_question=QUESTION, label="custom_handle",
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = NamingLLM(fail=fail)
        named = await pipeline._name_run(row.id, protocol)
        assert named.label == "custom_handle"
        assert named.title_for_report() == (protocol.title if fail else TITLES["tr"])


def test_title_format_language_and_legacy_fallback():
    assert clean_report_titles({"tr": TITLES["tr"].replace(" ", "_")}) == {"tr": TITLES["tr"]}
    assert clean_report_titles({"tr": TITLES["en"], "en": TITLES["tr"]}) == {}
    assert clean_report_titles({"tr": ["bad"], "en": "x" * 121}) == {}
    protocol = ResearchProtocol(
        title="Legacy title", primary_question=QUESTION, budget={"max_wall_minutes": 30},
    )
    assert protocol.title_for_report() == "Legacy title"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["tr", "en"])
async def test_export_uses_display_title_in_word_and_markdown(language):
    await create_schema()
    protocol = ResearchProtocol(
        title="Old question-based title", primary_question=QUESTION,
        report_titles=TITLES, report_language=language, label="ai_lung_ct",
        budget={"max_wall_minutes": 30},
    )
    settings = get_settings()
    store = ObjectStore(settings)
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        await build_exports(row.id, protocol, CoverageMetrics(), repo, store, NamingLLM())
        markdown = await store.get(f"runs/{row.id}/02_full_research_report.md")
        assert markdown.decode().startswith(f"# {TITLES[language]}\n")
        word = await store.get(f"runs/{row.id}/{word_report_name(protocol.label)}")
        document = Document(io.BytesIO(word))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        assert TITLES[language] in paragraphs
        assert protocol.title not in paragraphs
        assert any(QUESTION in paragraph for paragraph in paragraphs)
