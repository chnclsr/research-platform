from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from research_platform.llm import LLMProvider
from research_platform.report_synthesis import (
    SynthesisSection,
    _clean_cited_text,
    _deduplicated_executive_summary,
    _draft_overview,
    _merge_sections_into_compact_answer,
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
    assert package.report_mode == "compact"
    assert "[S99]" not in package.executive_summary
    assert "[S01]" in package.executive_summary


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


async def test_overview_overlap_triggers_one_distinct_role_repair() -> None:
    llm = OverlapRepairLLM()
    sections = [
        SynthesisSection(
            title="Tema",
            synthesis="Tema bulgusu aynen burada tekrar edilir [S01].",
            source_ids=["S01"],
        )
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
    assert llm.calls == 2
    assert overview["executive_summary"] != sections[0].synthesis


class ScopeDriftLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "Yaz dönemindeki nazal nodüller tedavi gerektirir [S01].",
            "consensus": "",
            "disagreements": "",
            "implications": "",
        }


async def test_scope_anchor_drift_uses_grounded_fallback_without_term_hardcoding() -> None:
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

    assert package.generation_diagnostics["theme_1"] == "fallback:scope_anchor_drift"
    assert "Bahar" in package.executive_summary
    assert "Yaz" not in package.executive_summary
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
    assert package.answerability_status == "insufficient"
    assert package.quality_diagnostics["answerability"] == {
        "status": "insufficient",
        "threshold": 0.35,
        "maximum_question_relevance": 0.2,
        "reason_codes": ["compact_low_question_relevance"],
        "invalid_repair_layers": [],
    }
    assert "insufficient" in package.executive_summary
    assert "Surgery" not in package.executive_summary
    assert package.quality_diagnostics["unique_claim_count"] == 6
    assert len(package.sections) == 1
    assert package.narrative == ""
    assert "estimated_completeness_below_0_5" in package.quality_diagnostics["mode_reasons"]


async def test_invalid_repair_is_recorded_but_does_not_define_answerability() -> None:
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

    assert package.answerability_status == "insufficient"
    assert package.generation_diagnostics["theme_1"] == "fallback:invalid_repair"
    assert package.quality_diagnostics["answerability"]["invalid_repair_layers"] == [
        "theme_1"
    ]
    assert claim.text not in package.executive_summary


async def test_relevance_boundary_keeps_a_grounded_compact_fallback() -> None:
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
    assert package.answerability_status == "answerable"
    assert package.generation_diagnostics["theme_1"] == "fallback:invalid_repair"
    assert "[S01]" in package.executive_summary


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
    assert package.answerability_status == "answerable"
    assert package.quality_diagnostics["answerability"]["maximum_question_relevance"] == 0.2


async def test_empty_reportable_corpus_keeps_existing_empty_behavior() -> None:
    package = await build_synthesis_package(
        llm=SynthesisLLM(),
        question="What does the evidence show?",
        language="en",
        sources=[],
        reportable_claims=[],
        evidence_by_claim={},
    )

    assert package.report_mode == "compact"
    assert package.answerability_status == "answerable"
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
    assert not prose_overlaps(
        package.executive_summary, package.sections[0].synthesis
    )
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
    assert package.generation_diagnostics["executive_summary"] in {
        "rebuilt_from_theme_leads",
        "fallback:scoped_pointer",
    }


async def test_overview_fallback_does_not_collapse_a_standard_report() -> None:
    package = await _standard_package(FailingOverviewLLM())

    assert package.report_mode == "standard"
    assert len(package.sections) >= 2
    assert package.narrative
    assert package.executive_summary
    assert not prose_overlaps(
        package.executive_summary, package.sections[0].synthesis
    )
    assert package.generation_diagnostics["overview"].startswith("fallback:")


def test_repeated_executive_summary_is_rebuilt_without_hiding_themes() -> None:
    sections = [
        SynthesisSection(
            title="Alpha",
            synthesis="Alpha findings concern design [S01]. Alpha needs replication [S01].",
            source_ids=["S01"],
        ),
        SynthesisSection(
            title="Beta",
            synthesis="Beta findings concern performance [S02]. Beta needs validation [S02].",
            source_ids=["S02"],
        ),
    ]

    summary, diagnostic = _deduplicated_executive_summary(
        sections[0].synthesis, sections, turkish=False
    )

    assert diagnostic == "rebuilt_from_theme_leads"
    assert not prose_overlaps(summary, sections[0].synthesis)
    assert "[S01]" in summary and "[S02]" in summary


def test_a_clean_executive_summary_is_left_untouched() -> None:
    sections = [
        SynthesisSection(
            title="Alpha",
            synthesis="Alpha findings concern design [S01].",
            source_ids=["S01"],
        )
    ]

    summary, diagnostic = _deduplicated_executive_summary(
        "The evidence answers the question only under stated conditions [S01].",
        sections,
        turkish=False,
    )

    assert diagnostic == "llm"
    assert summary == "The evidence answers the question only under stated conditions [S01]."


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
