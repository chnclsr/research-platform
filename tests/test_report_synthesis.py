from __future__ import annotations

from types import SimpleNamespace

from research_platform.llm import LLMProvider
from research_platform.report_synthesis import (
    SynthesisSection,
    _clean_cited_text,
    _draft_overview,
    build_synthesis_package,
)


class SynthesisLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system:
            return {
                "executive_summary": "The evidence indicates improvement in context [S01].",
                "cross_study_assessment": "The available design is limited [S01].",
                "conclusion": "Replication is needed before generalisation [S01].",
                "uncertainty": "External validation was not demonstrated [S01].",
            }
        return {
            "synthesis": "The study reports an improved measured outcome [S01].",
            "consensus": "The reported direction is favourable [S01].",
            "disagreements": "",
            "implications": "Independent validation remains necessary [S01].",
        }


class InventingLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "An invented source proves the result [S99].",
            "executive_summary": "An invented source proves the result [S99].",
            "conclusion": "Done [S99].",
        }


class OverviewRepairLLM(LLMProvider):
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            llm_context_tokens=8192,
            llm_max_output_tokens=2048,
        )
        self.requests: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str):
        self.requests.append((system, user))
        if "Repair or regenerate" not in system:
            return {
                "executive_summary": "Geçersiz kaynaklı ilk taslak [S99].",
                "cross_study_assessment": "Geçersiz kaynaklı değerlendirme [S99].",
                "conclusion": "Geçersiz kaynaklı sonuç [S99].",
                "uncertainty": "Geçersiz kaynaklı belirsizlik [S99].",
            }
        return {
            "executive_summary": [
                "Kanıt temalar arasında tutarlı bir yön göstermektedir [S01].",
                "Dış doğrulama yine de gereklidir [S01].",
            ],
            "cross_study_assessment": "Çalışmaların tasarımları farklıdır [S01].",
            "conclusion": "Genelleme öncesinde doğrulama gereklidir [S01].",
            "uncertainty": "Karşılaştırılabilirlik sınırlıdır [S01].",
        }


class InvalidOverviewLLM(LLMProvider):
    settings = SimpleNamespace(
        llm_context_tokens=8192,
        llm_max_output_tokens=2048,
    )

    async def complete_json(self, system: str, user: str):
        return {
            "executive_summary": "Uydurma kaynak [S99].",
            "cross_study_assessment": "Uydurma kaynak [S99].",
            "conclusion": "Uydurma kaynak [S99].",
            "uncertainty": "Uydurma kaynak [S99].",
        }


def _fixture():
    source = SimpleNamespace(
        id="source-1",
        title="External validation of a method",
        metadata_json={"abstract": "A retrospective external validation cohort."},
    )
    claim = SimpleNamespace(
        id="claim-1",
        text="The measured outcome improved in the validation cohort.",
        status="qualified",
    )
    link = SimpleNamespace(
        quote="The measured outcome improved in the validation cohort.",
        direction="supports",
    )
    return source, claim, link


async def test_synthesis_package_writes_bounded_thematic_prose() -> None:
    source, claim, link = _fixture()
    package = await build_synthesis_package(
        llm=SynthesisLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.generated_by_llm is True
    assert package.sections
    assert "[S01]" in package.sections[0].synthesis
    assert package.study_profiles[0].contribution == "External validation"
    assert "retrieval" not in package.executive_summary.lower()


async def test_unknown_source_citations_trigger_grounded_fallback() -> None:
    source, claim, link = _fixture()
    package = await build_synthesis_package(
        llm=InventingLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.generated_by_llm is False
    assert "[S99]" not in package.narrative
    assert "[S01]" in package.narrative


def test_flat_string_lists_become_prose_without_python_serialisation() -> None:
    cleaned = _clean_cited_text(
        ["İlk tam cümle [S01].", "İkinci tam cümle [S01]."],
        {"[S01]"},
    )

    assert cleaned == "İlk tam cümle [S01]. İkinci tam cümle [S01]."
    assert "['" not in cleaned
    assert _clean_cited_text({"sentence": "Metin [S01]."}, {"[S01]"}) == ""


async def test_overview_is_budgeted_and_repaired_once() -> None:
    llm = OverviewRepairLLM()
    long_sentence = (
        "Çok merkezli kanıt farklı klinik ortamlarda dikkatle doğrulanmalıdır [S01]. "
        * 80
    )
    sections = [
        SynthesisSection(
            title=f"Tema {index}",
            synthesis=long_sentence,
            consensus=long_sentence,
            disagreements=long_sentence,
            implications=long_sentence,
            source_ids=["S01"],
        )
        for index in range(5)
    ]

    overview, succeeded, diagnostic = await _draft_overview(
        llm,
        question="Kanıt ne gösteriyor?",
        sections=sections,
        language="tr",
        turkish=True,
    )

    assert succeeded is True
    assert diagnostic == "repair_passed"
    assert len(llm.requests) == 2
    assert len(llm.requests[0][1]) < 12000
    assert "THEME: Tema 4" in llm.requests[0][1]
    assert "['" not in overview["executive_summary"]
    assert overview["executive_summary"].endswith("[S01].")


async def test_deterministic_overview_fallback_uses_complete_sentences() -> None:
    sentence = "Bulgular farklı merkezlerde yeniden doğrulanmalıdır [S01]."
    sections = [
        SynthesisSection(
            title=f"Tema {index}",
            synthesis=" ".join([sentence] * 100),
            consensus=" ".join([sentence] * 100),
            disagreements=" ".join([sentence] * 100),
            implications=" ".join([sentence] * 100),
            source_ids=["S01"],
        )
        for index in range(5)
    ]

    overview, succeeded, diagnostic = await _draft_overview(
        InvalidOverviewLLM(),
        question="Kanıt ne gösteriyor?",
        sections=sections,
        language="tr",
        turkish=True,
    )

    assert succeeded is False
    assert diagnostic.startswith("fallback:")
    assert len(overview["executive_summary"]) <= 2600
    assert len(overview["cross_study_assessment"]) <= 3500
    assert len(overview["conclusion"]) <= 2400
    assert overview["executive_summary"].endswith("[S01].")
    assert overview["cross_study_assessment"].endswith("[S01].")
    assert overview["conclusion"].endswith("[S01].")
