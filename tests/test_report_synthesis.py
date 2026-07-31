from __future__ import annotations

from types import SimpleNamespace

from research_platform.llm import LLMProvider
from research_platform.report_synthesis import build_synthesis_package


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
