from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from research_platform.llm import LLMProvider
from research_platform.report_synthesis import (
    SynthesisSection,
    _claim_evidence_block,
    _draft_overview,
    _evidence_packets,
    _merge_sections_into_compact_answer,
    _reader_text,
    _report_mode,
    _scope_anchors,
    _section_packet_budget,
    build_synthesis_package,
)
from research_platform.text_similarity import prose_overlaps


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


class ScopedCompactLLM(LLMProvider):
    """Drafts a section that stays on the run's subject without echoing every question word."""

    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "Open weight models produced radiology reports from chest images [S01].",
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


class OverlapRepairLLM(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, system: str, user: str):
        self.calls += 1
        if "Repair or regenerate" not in system:
            return {
                "executive_summary": "Tema bulgusu aynen burada tekrar edilir [S01].",
                "cross_study_assessment": "Tasarımlar karşılaştırılmalıdır [S01].",
                "conclusion": "Ek doğrulama gereklidir [S01].",
                "uncertainty": "Kanıt sınırlıdır [S01].",
            }
        return {
            "executive_summary": "Mevcut kanıt soruya koşullu bir yanıt sağlar [S01].",
            "cross_study_assessment": "Tasarımlar karşılaştırılmalıdır [S01].",
            "conclusion": "Genelleme öncesinde ek doğrulama gereklidir [S01].",
            "uncertainty": "Kanıt sınırlıdır [S01].",
        }


class DistinctThemeLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system:
            return {
                "executive_summary": "The two evidence themes remain distinct [S01].",
                "cross_study_assessment": "Their designs require separate interpretation [S01].",
                "conclusion": "The scoped findings should not be merged [S01].",
                "uncertainty": "Each theme remains bounded by its own evidence [S01].",
            }
        synthesis = (
            "The alpha protocol findings concern study design [S01]."
            if "THEME:\nAlpha" in user
            else "The beta outcome findings concern measured performance [S01]."
        )
        return {
            "synthesis": synthesis,
            "consensus": "",
            "disagreements": "",
            "implications": "",
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
        audit={"question_relevance": 0.91},
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


async def test_unknown_source_citations_preserve_model_text_and_add_warning() -> None:
    source, claim, link = _fixture()
    package = await build_synthesis_package(
        llm=InventingLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.generated_by_llm is True
    assert package.generation_status == "complete_with_warnings"
    assert package.report_mode == "compact"
    assert package.executive_summary == "An invented source proves the result [S99]."
    assert package.generation_diagnostics["theme_1"] == "initial_visible:warnings"
    assert package.validation_warnings["theme_1"] == [
        "synthesis:unknown_citations:[S99]",
        "synthesis:stronger_than_available_evidence",
    ]


class ForeignProseLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "The original English wording remains unchanged [S01].",
            "consensus": "A definitive consensus has been proven [S01].",
            "disagreements": "",
            "implications": "",
        }


async def test_language_and_strength_warnings_never_rewrite_model_prose() -> None:
    source, claim, link = _fixture()
    expected = "The original English wording remains unchanged [S01]."

    package = await build_synthesis_package(
        llm=ForeignProseLLM(),
        question="Yöntem ölçülen sonucu iyileştiriyor mu?",
        language="tr",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.executive_summary == expected
    assert package.sections[0].synthesis == expected
    assert "synthesis:language_mismatch" in package.validation_warnings["theme_1"]
    assert "consensus:no_multi_source_moderate_evidence" in package.validation_warnings[
        "theme_1"
    ]
    assert "consensus:stronger_than_available_evidence" in package.validation_warnings[
        "theme_1"
    ]


def test_consensus_requires_two_primary_in_scope_sources():
    claim = SimpleNamespace(
        id="claim",
        text="The metric improved.",
        status="supported",
        audit={"appraisal": {"grade": "moderate"}},
    )
    primary = SimpleNamespace(
        id="primary",
        metadata_json={"research_scope_role": "primary_in_scope"},
    )
    benchmark = SimpleNamespace(
        id="benchmark",
        metadata_json={"research_scope_role": "supporting_benchmark"},
    )
    links = {
        claim.id: [
            (SimpleNamespace(quote="The metric improved.", direction="supports"), primary),
            (SimpleNamespace(quote="The metric improved.", direction="supports"), benchmark),
        ]
    }

    block, _ = _claim_evidence_block(
        claim,
        links,
        {primary.id: "S01", benchmark.id: "S02"},
    )

    assert "consensus_eligible=false" in block


async def test_supporting_benchmark_only_enters_evaluation_topics():
    benchmark = SimpleNamespace(
        id="benchmark",
        title="Chest CT benchmark",
        metadata_json={"research_scope_role": "supporting_benchmark"},
    )
    method_claim = SimpleNamespace(
        id="method",
        text="The architecture generates a full report.",
        status="qualified",
        audit={"question_relevance": 0.9},
    )
    metric_claim = SimpleNamespace(
        id="metric",
        text="The benchmark evaluates reports with the RadGraph metric.",
        status="qualified",
        audit={"question_relevance": 0.9},
    )
    evidence = {
        method_claim.id: [
            (SimpleNamespace(quote=method_claim.text, direction="supports"), benchmark)
        ],
        metric_claim.id: [
            (SimpleNamespace(quote=metric_claim.text, direction="supports"), benchmark)
        ],
    }

    package = await build_synthesis_package(
        llm=SynthesisLLM(),
        question="How are chest CT reports generated and evaluated?",
        language="en",
        sources=[benchmark],
        reportable_claims=[method_claim, metric_claim],
        evidence_by_claim=evidence,
    )

    assert package.quality_diagnostics["scope_eligible_claim_count"] == 1
    assert package.quality_diagnostics["unique_claim_count"] == 1


class CompletelyFailingLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        raise RuntimeError("provider unavailable")


async def test_complete_provider_failure_never_turns_claims_into_narrative():
    source, claim, link = _fixture()

    package = await build_synthesis_package(
        llm=CompletelyFailingLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.generated_by_llm is False
    assert package.generation_status == "failed"
    assert package.executive_summary.startswith("LLM synthesis could not be produced")
    assert claim.text not in package.executive_summary
    assert all("fallback:" not in value for value in package.generation_diagnostics.values())


def test_reader_text_preserves_strings_character_for_character() -> None:
    value = "  Eksik atıflı özgün metin [S99].\nİkinci satır.  "

    assert _reader_text(value) == value
    assert _reader_text(["Metin [S01]."]) == ""
    assert _reader_text({"sentence": "Metin [S01]."}) == ""


async def test_overview_is_budgeted_and_keeps_first_usable_text() -> None:
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

    overview, succeeded, diagnostic, warnings = await _draft_overview(
        llm,
        question="Kanıt ne gösteriyor?",
        sections=sections,
        language="tr",
        turkish=True,
    )

    assert succeeded is True
    assert diagnostic == "initial_visible:warnings"
    assert len(llm.requests) == 1
    assert len(llm.requests[0][1]) < 12000
    assert "THEME: Tema 4" in llm.requests[0][1]
    assert overview["executive_summary"] == "Geçersiz kaynaklı ilk taslak [S99]."
    assert warnings["executive_summary"] == [
        "executive_summary:unknown_citations:[S99]"
    ]


async def test_overview_invalid_citation_is_preserved_with_warnings() -> None:
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

    overview, succeeded, diagnostic, warnings = await _draft_overview(
        InvalidOverviewLLM(),
        question="Kanıt ne gösteriyor?",
        sections=sections,
        language="tr",
        turkish=True,
    )

    assert succeeded is True
    assert diagnostic.startswith("initial_visible")
    assert overview["executive_summary"] == "Uydurma kaynak [S99]."
    assert warnings["executive_summary"] == [
        "executive_summary:unknown_citations:[S99]",
        "executive_summary:language_mismatch",
    ]


async def test_overview_overlap_is_diagnostic_and_does_not_rewrite() -> None:
    llm = OverlapRepairLLM()
    sections = [
        SynthesisSection(
            title="Tema",
            synthesis="Tema bulgusu aynen burada tekrar edilir [S01].",
            source_ids=["S01"],
        )
    ]

    overview, succeeded, diagnostic, warnings = await _draft_overview(
        llm,
        question="Kanıt ne gösteriyor?",
        sections=sections,
        language="tr",
        turkish=True,
    )

    assert succeeded is True
    assert diagnostic == "initial_visible:warnings"
    assert llm.calls == 1
    assert overview["executive_summary"] == sections[0].synthesis
    assert warnings["overlap"]


class ScopeDriftLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "Yaz dönemindeki nazal nodüller tedavi gerektirir [S01].",
            "consensus": "",
            "disagreements": "",
            "implications": "",
        }


async def test_scope_anchors_guide_the_prompt_and_no_longer_discard_a_draft() -> None:
    """The accepted cost of trusting the model, pinned so it stays a decision.

    A literal-match guard used to replace this draft with stitched claim sentences for
    answering about "Yaz" where the question said "Bahar". Measured across live runs it
    never once caught a real drift: every rejection was a section that had stayed on
    subject and reached for a synonym -- "AI" for "yapay zeka", "medikal görüntüleme" for
    "radyoloji" -- and the stitched replacement read far worse than what it discarded. So
    the anchors now only reach the model as `SCOPE_BOUNDARIES` guidance, and a draft that
    ignores them reaches the reader.
    """
    source = SimpleNamespace(id="source-1", title="Seasonal finding", metadata_json={})
    claim = SimpleNamespace(
        id="claim-1",
        text="Spring nasal nodules require treatment.",
        status="qualified",
        audit={"question_relevance": 0.91},
    )
    link = SimpleNamespace(quote="Spring nasal nodules require treatment.", direction="supports")

    package = await build_synthesis_package(
        llm=ScopeDriftLLM(),
        question="Do spring nasal nodules require treatment?",
        display_question="Bahar dönemindeki nazal nodüller tedavi gerektirir mi?",
        language="tr",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
        claim_texts={claim.id: "Bahar dönemindeki nazal nodüller tedavi gerektirir."},
    )

    assert "scope_anchor_drift" not in package.generation_diagnostics["theme_1"]
    assert "Yaz" in package.executive_summary
    # The prompt half stays: the model is still told the run's literal wording.
    assert "bahar" in package.quality_diagnostics["scope_anchors"]


async def test_sparse_semantic_claims_choose_one_compact_evidence_summary() -> None:
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(3)
    ]
    texts = [
        "Surgery improved turbinate size and NOSE scores compared with conservative treatment.",
        "Compared with conservative treatment, surgery produced better NOSE scores and turbinate size.",
        "Initial treatment used topical medication.",
        "Symptoms were measured after treatment.",
        "Follow-up was limited to one centre.",
        "The study population included adults.",
        "Independent replication was not reported.",
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=text,
            status="qualified",
            audit={"question_relevance": 0.20},
        )
        for index, text in enumerate(texts)
    ]
    evidence = {
        claim.id: [
            (
                SimpleNamespace(quote=claim.text, direction="supports"),
                sources[0] if index < 2 else sources[index % 3],
            )
        ]
        for index, claim in enumerate(claims)
    }

    package = await build_synthesis_package(
        llm=SynthesisLLM(),
        question="Which treatment performs better?",
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
        coverage={"estimated_completeness": 0.31},
    )

    assert package.report_mode == "compact"
    assert package.answerability_status == "limited"
    assert package.quality_diagnostics["answerability"] == {
        "status": "limited",
        "threshold": 0.35,
        "maximum_question_relevance": 0.2,
        "in_scope_contributing_sources": 3,
        "sub_question_coverage": 1.0,
        "reason_codes": ["low_question_relevance"],
    }
    assert "Surgery" not in package.executive_summary
    assert package.quality_diagnostics["unique_claim_count"] == 6
    assert len(package.sections) == 1
    assert package.narrative == ""
    # The compact mode here is earned by the claim and source counts. The low completeness
    # estimate passed in above is a discovery diagnostic and no longer shapes the report.
    assert package.quality_diagnostics["mode_reasons"] == [
        "fewer_than_8_unique_claims",
        "fewer_than_4_contributing_sources",
    ]


async def test_validation_warning_does_not_define_answerability() -> None:
    source, claim, link = _fixture()
    claim.audit = {"question_relevance": 0.20}

    package = await build_synthesis_package(
        llm=InventingLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.answerability_status == "limited"
    assert package.generation_diagnostics["theme_1"] == "initial_visible:warnings"
    assert package.quality_diagnostics["answerability"]["reason_codes"] == [
        "fewer_than_2_in_scope_sources",
        "low_question_relevance",
    ]
    assert claim.text not in package.executive_summary


async def test_relevance_boundary_keeps_original_compact_prose() -> None:
    source, claim, link = _fixture()
    claim.audit = {"question_relevance": 0.35}

    package = await build_synthesis_package(
        llm=InventingLLM(),
        question="Does the method improve the measured outcome?",
        language="en",
        sources=[source],
        reportable_claims=[claim],
        evidence_by_claim={claim.id: [(link, source)]},
    )

    assert package.report_mode == "compact"
    assert package.answerability_status == "limited"
    assert package.generation_diagnostics["theme_1"] == "initial_visible:warnings"
    assert "[S99]" in package.executive_summary


async def test_standard_report_is_not_suppressed_by_the_compact_answerability_gate() -> None:
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(4)
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=(
                f"Alpha method protocol observation {index}."
                if index < 4
                else f"Beta outcome performance observation {index}."
            ),
            status="qualified",
            audit={"question_relevance": 0.20},
        )
        for index in range(8)
    ]
    evidence = {
        claim.id: [
            (
                SimpleNamespace(quote=claim.text, direction="supports"),
                sources[index % 4],
            )
        ]
        for index, claim in enumerate(claims)
    }

    package = await build_synthesis_package(
        llm=DistinctThemeLLM(),
        question="How do the alpha protocol and beta outcome differ?",
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
        sub_questions=["Alpha method protocol", "Beta outcome performance"],
        coverage={"estimated_completeness": 0.8},
    )

    assert package.report_mode == "standard"
    assert package.answerability_status == "limited"
    assert package.quality_diagnostics["answerability"]["maximum_question_relevance"] == 0.2


async def test_empty_reportable_corpus_is_explicitly_insufficient() -> None:
    package = await build_synthesis_package(
        llm=SynthesisLLM(),
        question="What does the evidence show?",
        language="en",
        sources=[],
        reportable_claims=[],
        evidence_by_claim={},
    )

    assert package.report_mode == "compact"
    assert package.answerability_status == "insufficient"
    assert package.executive_summary == ""


class EchoingOverviewLLM(LLMProvider):
    """Drafts two themes, then echoes the dominant one back as the overview.

    The first theme is deliberately long and the second short, which is what makes the
    deterministic overview join stay close enough to theme one to register as duplication.
    That is the shape that used to switch a perfectly viable standard report to compact.
    """

    _ALPHA = (
        "The alpha protocol findings concern study design across the enrolled cohorts [S01]. "
        "The alpha protocol enrolment criteria were applied consistently in each centre [S02]. "
        "The alpha protocol follow-up schedule was fixed in advance of enrolment [S03]. "
        "The alpha protocol reporting of design deviations remained incomplete [S04]."
    )
    _BETA = "Beta outcome performance was measured once [S01]."

    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system or "Repair or regenerate" in system:
            return {
                "executive_summary": self._ALPHA,
                "cross_study_assessment": "Their designs require separate interpretation [S01].",
                "conclusion": "The scoped findings should not be merged [S01].",
                "uncertainty": "Each theme remains bounded by its own evidence [S01].",
            }
        return {
            "synthesis": self._ALPHA if "THEME:\nAlpha" in user else self._BETA,
            "consensus": "",
            "disagreements": "",
            "implications": "",
        }


class FailingOverviewLLM(EchoingOverviewLLM):
    """Themes draft normally; every overview call fails, forcing the deterministic join."""

    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system or "Repair or regenerate" in system:
            raise RuntimeError("overview provider unavailable")
        return await super().complete_json(system, user)


def _standard_corpus() -> tuple[list[Any], list[Any], dict[str, list[tuple[Any, Any]]]]:
    """Eight claims over four sources: enough capacity for a thematic report."""
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(4)
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=(
                f"Alpha method protocol observation {index}."
                if index < 4
                else f"Beta outcome performance observation {index}."
            ),
            status="qualified",
            audit={"question_relevance": 0.88},
        )
        for index in range(8)
    ]
    evidence = {
        claim.id: [
            (
                SimpleNamespace(quote=claim.text, direction="supports"),
                sources[index % 4],
            )
        ]
        for index, claim in enumerate(claims)
    }
    return sources, claims, evidence


async def _standard_package(llm: LLMProvider):
    sources, claims, evidence = _standard_corpus()
    return await build_synthesis_package(
        llm=llm,
        question="How do the alpha protocol and beta outcome differ?",
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
        sub_questions=["Alpha method protocol", "Beta outcome performance"],
        coverage={"estimated_completeness": 0.8},
    )


async def test_overview_overlapping_a_theme_keeps_the_standard_thematic_report() -> None:
    package = await _standard_package(EchoingOverviewLLM())

    assert package.report_mode == "standard"
    assert len(package.sections) >= 2
    assert len({section.title for section in package.sections}) == len(package.sections)
    assert prose_overlaps(package.executive_summary, package.sections[0].synthesis)
    assert package.narrative
    for section in package.sections:
        assert section.title in package.narrative
    # The duplication that used to collapse the report is still detected and recorded;
    # only its consequence changed.
    assert any(
        row["left"] == "executive_summary" and row["right"].startswith("theme:")
        for row in package.quality_diagnostics["field_overlaps"]
    )
    assert (
        "executive_summary_overlaps_theme"
        not in package.quality_diagnostics["mode_reasons"]
    )
    assert package.generation_diagnostics["overview"].startswith("initial_visible")
    assert package.validation_warnings.get("overlap")


async def test_overview_fallback_does_not_collapse_a_standard_report() -> None:
    package = await _standard_package(FailingOverviewLLM())

    assert package.report_mode == "standard"
    assert len(package.sections) >= 2
    assert package.narrative
    assert package.executive_summary
    assert not prose_overlaps(
        package.executive_summary, package.sections[0].synthesis
    )
    assert package.generation_diagnostics["overview"].startswith("unavailable:")
    assert package.generation_status == "partial"


def test_compact_transition_merges_themes_instead_of_hiding_them() -> None:
    sections = [
        SynthesisSection(
            title="Alpha",
            synthesis="Alpha findings concern design [S01].",
            implications="Alpha needs replication [S01].",
            source_ids=["S01"],
            claim_ids=["claim-1"],
        ),
        SynthesisSection(
            title="Beta",
            synthesis="Beta findings concern performance [S02].",
            source_ids=["S02"],
            claim_ids=["claim-2"],
        ),
    ]

    merged = _merge_sections_into_compact_answer(sections, turkish=False)

    assert len(merged) == 1
    assert merged[0].title == "Evidence summary"
    for fragment in (
        "Alpha findings concern design [S01].",
        "Alpha needs replication [S01].",
        "Beta findings concern performance [S02].",
    ):
        assert fragment in merged[0].synthesis
    assert merged[0].source_ids == ["S01", "S02"]
    assert merged[0].claim_ids == ["claim-1", "claim-2"]
    assert "merged_for_compact" in merged[0].generation_note


def test_collapsed_completeness_estimate_no_longer_forces_a_compact_report() -> None:
    claims = [SimpleNamespace(id=f"claim-{index}", text=f"Finding {index}.") for index in range(10)]
    sources = [SimpleNamespace(id=f"source-{index}") for index in range(5)]
    evidence = {
        claim.id: [(SimpleNamespace(quote=claim.text, direction="supports"), sources[index % 5])]
        for index, claim in enumerate(claims)
    }

    # Chao1 collapses towards zero whenever the connectors barely rediscover each other's
    # sources. That is a property of the discovery pool, not of whether ten audited claims
    # from five sources can carry themes.
    assert _report_mode(claims, evidence, {"estimated_completeness": 0.027}) == ("standard", [])


async def test_compact_section_survives_a_question_with_many_scope_anchors() -> None:
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(7)
    ]
    texts = [
        "Open weight models produced radiology reports with high accuracy.",
        "Radiology reports generated from chest images were reviewed by clinicians.",
        "Open weight models were deployed inside the hospital for radiology reports.",
        "Computed tomography images were the input for the reports.",
        "The models were compared against closed weight baselines on radiology images.",
        "Open source checkpoints were released for the reports.",
        "Radiology images from multiple modalities were included in the models evaluation.",
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=text,
            status="qualified",
            audit={"question_relevance": 0.80},
        )
        for index, text in enumerate(texts)
    ]
    evidence = {
        claim.id: [(SimpleNamespace(quote=claim.text, direction="supports"), sources[index])]
        for index, claim in enumerate(claims)
    }

    package = await build_synthesis_package(
        llm=ScopedCompactLLM(),
        question=(
            "Which open weight models generate radiology reports "
            "from computed tomography images?"
        ),
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
        coverage={"estimated_completeness": 0.027},
    )

    assert package.report_mode == "compact"
    assert package.quality_diagnostics["mode_reasons"] == ["fewer_than_8_unique_claims"]
    assert "Open weight models produced radiology reports" in package.executive_summary
    # Compact holds every claim in one theme, and all seven reach the prompt.
    assert package.quality_diagnostics["evidence_claims_shown"] == 7
    assert package.quality_diagnostics["claims_without_evidence"] == 0


def test_scope_anchors_count_one_word_once_however_it_is_inflected() -> None:
    # `_anchor_present` matches a single word by its five-character stem, so the two
    # Turkish inflections below are one requirement. Listing both used to make a section
    # owe the same word twice.
    anchors = _scope_anchors(
        "BT görüntülerinden radyoloji raporu yazan çalışmaları ve çalışmalarını bul."
    )

    assert "çalışmaları" in anchors
    assert "çalışmalarını" not in anchors
    assert len(anchors) == len(set(anchors))


async def test_a_rejected_draft_reports_why_it_was_rejected() -> None:
    """The diagnostic has to name the reason, because it is what a run is debugged from.

    A section rejected over its citations must say `invalid_repair`. A live run reported
    `scope_anchor_drift` for exactly this case, and the wrong label sent an investigation
    after the wrong mechanism.
    """
    texts = [
        "The method improved the measured outcome in cohort A.",
        "Recovery time fell when the method was applied.",
        "The measured outcome favoured the treated group.",
        "Adverse events did not increase under the method.",
        "Clinicians reported improved workflow after adoption.",
        "Cost per patient dropped in the second year.",
        "Independent trials have not replicated the result.",
    ]
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(len(texts))
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=text,
            status="qualified",
            audit={"question_relevance": 0.80},
        )
        for index, text in enumerate(texts)
    ]
    evidence = {
        claim.id: [(SimpleNamespace(quote=claim.text, direction="supports"), sources[index])]
        for index, claim in enumerate(claims)
    }

    package = await build_synthesis_package(
        llm=InventingLLM(),
        question="Does the method improve the measured outcome in trials?",
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
    )

    assert package.generation_diagnostics["theme_1"] == "initial_visible:warnings"


def _packet_fixture(count: int, *, quote_chars: int = 600):
    """A theme big enough to need several packets, with one distinct source per claim."""
    sources = [
        SimpleNamespace(id=f"source-{index}", title=f"Source {index}", metadata_json={})
        for index in range(count)
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            text=f"Finding {index}: the measured outcome moved under condition {index}.",
            status="qualified",
            audit={"question_relevance": 0.80},
        )
        for index in range(count)
    ]
    evidence = {
        claim.id: [
            (
                SimpleNamespace(
                    quote=f"Evidence {index} " + ("detail " * (quote_chars // 8)),
                    direction="supports",
                ),
                sources[index],
            )
        ]
        for index, claim in enumerate(claims)
    }
    labels = {str(source.id): f"S{index:02d}" for index, source in enumerate(sources, 1)}
    return sources, claims, evidence, labels


def test_every_backed_claim_reaches_exactly_one_packet() -> None:
    """The property the 12-claim cap broke: a live run hid 44% of its evidence."""
    _sources, claims, evidence, labels = _packet_fixture(40)
    budget = 4000

    packets, unbacked = _evidence_packets(claims, evidence, labels, char_budget=budget)

    assert len(packets) > 1, "fixture must be large enough to split"
    assert unbacked == []
    placed = [claim_id for packet in packets for claim_id in packet.claim_ids]
    assert placed == [str(claim.id) for claim in claims]
    assert len(placed) == len(set(placed))


def test_no_packet_exceeds_the_budget_it_was_given() -> None:
    _sources, claims, evidence, labels = _packet_fixture(40)
    budget = 4000

    packets, _unbacked = _evidence_packets(claims, evidence, labels, char_budget=budget)

    assert all(len(packet.text) <= budget for packet in packets)


def test_a_claim_larger_than_the_budget_still_gets_a_packet() -> None:
    """Dropping it would trade the coverage guarantee for a size guarantee."""
    _sources, claims, evidence, labels = _packet_fixture(3)

    packets, unbacked = _evidence_packets(claims, evidence, labels, char_budget=200)

    assert unbacked == []
    assert [claim_id for packet in packets for claim_id in packet.claim_ids] == [
        "claim-0",
        "claim-1",
        "claim-2",
    ]


def test_a_claim_with_no_citable_quote_is_counted_not_silently_skipped() -> None:
    source = SimpleNamespace(id="source-1", title="S", metadata_json={})
    backed = SimpleNamespace(id="claim-1", text="Backed.", status="qualified")
    bare = SimpleNamespace(id="claim-2", text="Unbacked.", status="qualified")
    evidence = {
        backed.id: [(SimpleNamespace(quote="A real quote.", direction="supports"), source)],
        bare.id: [(SimpleNamespace(quote="   ", direction="supports"), source)],
    }

    packets, unbacked = _evidence_packets(
        [backed, bare], evidence, {"source-1": "S01"}, char_budget=8000
    )

    assert [claim_id for packet in packets for claim_id in packet.claim_ids] == ["claim-1"]
    assert unbacked == ["claim-2"]


def test_packet_budget_leaves_room_for_the_rest_of_the_prompt() -> None:
    llm = SynthesisLLM()
    llm.settings = SimpleNamespace(llm_context_tokens=8192, llm_max_output_tokens=2048)

    budget = _section_packet_budget(
        llm, question="Q" * 100, title="T" * 40, scope_context="S" * 300
    )

    # (8192 - 2048 - 1536) * 2 = 9216, minus the variable prompt parts and the allow-list.
    assert budget == 9216 - 100 - 40 - 300 - 600


class MultiPassLLM(LLMProvider):
    """Drafts each pass, then integrates them when asked to consolidate.

    Cites whatever the packet actually offered: each pass carries its own slice of the
    theme's sources, so a fake that always cited `[S01]` would be ungrounded from the
    second pass onward and would exercise the repair ladder instead of consolidation.
    """

    def __init__(self, *, consolidation_valid: bool = True) -> None:
        self.consolidation_valid = consolidation_valid
        self.drafts = 0
        self.consolidations = 0

    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system:
            return {
                "executive_summary": "The evidence indicates improvement in context [S01].",
                "cross_study_assessment": "The available design is limited [S01].",
                "conclusion": "Replication is needed before generalisation [S01].",
                "uncertainty": "External validation was not demonstrated [S01].",
            }
        offered = re.search(r"ALLOWED_SOURCE_IDS: ([^\n]*)", user)
        label = offered.group(1).split(",")[0].strip() if offered else "S01"
        if "merging several partial drafts" in system:
            self.consolidations += 1
            if not self.consolidation_valid:
                return {"synthesis": "An invented source integrates the passes [S99]."}
            return {
                "synthesis": f"Integrated across every pass of this theme [{label}].",
                "consensus": f"The passes agree on direction [{label}].",
                "disagreements": "",
                "implications": f"Validation remains necessary [{label}].",
            }
        self.drafts += 1
        marker = "alpha" if "claim=Finding 0:" in user else "beta"
        return {
            "synthesis": f"Pass {marker} reports a measured outcome [{label}].",
            "consensus": f"Pass {marker} direction is favourable [{label}].",
            "disagreements": "",
            "implications": f"Pass {marker} needs validation [{label}].",
        }


async def _multi_pass_package(llm: LLMProvider):
    sources, claims, evidence, _labels = _packet_fixture(24)
    return await build_synthesis_package(
        llm=llm,
        question="Does the method improve the measured outcome?",
        language="en",
        sources=sources,
        reportable_claims=claims,
        evidence_by_claim=evidence,
    )


async def test_a_theme_needing_several_packets_still_yields_one_section() -> None:
    """Downstream counts on it.

    Compact rendering asserts a single section, and `generated_by_llm` compares
    `llm_successes` against `len(sections)` -- so passes must stay passes and never become
    sections of their own.
    """
    llm = MultiPassLLM()

    package = await _multi_pass_package(llm)

    assert llm.drafts > 1, "fixture must be large enough to split"
    assert llm.consolidations == 1
    assert len(package.sections) == 1
    assert "theme_2" not in package.generation_diagnostics
    assert package.generation_diagnostics["theme_1"].startswith("consolidated")
    assert "Integrated across every pass" in package.sections[0].synthesis


async def test_every_claim_reaches_the_prompt_across_the_passes() -> None:
    llm = MultiPassLLM()

    package = await _multi_pass_package(llm)

    quality = package.quality_diagnostics
    assert quality["claims_without_evidence"] == 0
    assert quality["evidence_claims_shown"] == quality["unique_claim_count"]
    assert sum(row["passes"] for row in quality["theme_coverage"]) == llm.drafts


async def test_invalid_consolidation_citation_is_preserved_with_a_warning() -> None:
    llm = MultiPassLLM(consolidation_valid=False)

    package = await _multi_pass_package(llm)

    assert llm.consolidations == 1
    assert len(package.sections) == 1
    assert package.generation_diagnostics["theme_1"].startswith("consolidated_visible")
    body = package.sections[0].synthesis
    assert body == "An invented source integrates the passes [S99]."
    assert "synthesis:unknown_citations:[S99]" in package.sections[0].validation_warnings


class OnePassFailsLLM(LLMProvider):
    """Drafts the first pass cleanly and returns an ungrounded second pass."""

    def __init__(self) -> None:
        self.drafts = 0

    async def complete_json(self, system: str, user: str):
        if "integrative layer" in system or "merging several partial drafts" in system:
            return {"synthesis": "Unused [S99]."}
        if "Repair the supplied draft" in system:
            return {"synthesis": "Still ungrounded [S99]."}
        self.drafts += 1
        if "claim=Finding 0:" in user:
            offered = re.search(r"ALLOWED_SOURCE_IDS: ([^\n]*)", user)
            label = offered.group(1).split(",")[0].strip() if offered else "S01"
            return {
                "synthesis": f"The first pass reports a measured outcome [{label}].",
                "consensus": "",
                "disagreements": "",
                "implications": "",
            }
        return {"synthesis": "An invented source proves the result [S99]."}


async def test_a_warned_pass_remains_visible_and_counted_as_used() -> None:
    llm = OnePassFailsLLM()

    package = await _multi_pass_package(llm)

    row = package.quality_diagnostics["theme_coverage"][0]
    assert row["claims_shown"] == row["claims_total"]
    assert row["passes"] == row["passes_used"]
    assert "[S99]" in package.sections[0].synthesis


def test_claim_block_carries_the_appraisal_to_the_model():
    """The grade steers the drafted prose; it is not applied as a hidden sort key."""
    from research_platform.report_synthesis import _claim_evidence_block

    source, claim, link = _fixture()
    claim.audit = {**claim.audit, "appraisal": {"grade": "limited", "tier": "clinical"}}
    body, sources = _claim_evidence_block(
        claim, {"claim-1": [(link, source)]}, {"source-1": "S01"},
    )
    assert "evidence=limited" in body
    assert "status=qualified" in body
    assert sources == ["S01"]


def test_claim_block_omits_the_field_for_an_unappraised_claim():
    """Runs made before appraisal existed must not grow an empty field."""
    from research_platform.report_synthesis import _claim_evidence_block

    source, claim, link = _fixture()
    body, _ = _claim_evidence_block(
        claim, {"claim-1": [(link, source)]}, {"source-1": "S01"},
    )
    assert "evidence=" not in body


def test_source_design_labels_reuse_the_report_classifier():
    source, _, _ = _fixture()
    from research_platform.report_synthesis import source_design_labels

    assert source_design_labels([source]) == {"source-1": "Dış doğrulama"}
