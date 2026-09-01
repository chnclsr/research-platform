"""The chain's last link: which sources the report cites, and why the rest are missing.

Everything up to the claim was already relational. These tests cover the step that was not
recorded at all -- from an audited claim to `[S03]` in the .docx -- and in particular the
four distinct reasons a source with real evidence can still be absent from the document.
"""

from __future__ import annotations

from types import SimpleNamespace

from research_platform.report_synthesis import (
    SynthesisPackage,
    SynthesisSection,
    citation_counts,
    cited_labels,
)
from research_platform.schemas import CitationDrop
from research_platform.word_report import _collect_citations


def source(source_id: str, title: str = "A study"):
    return SimpleNamespace(id=source_id, title=title, url=f"https://example.test/{source_id}")


def claim(claim_id: str, status: str = "supported"):
    return SimpleNamespace(
        id=claim_id, text=f"claim {claim_id}", status=status, importance="major", audit={}
    )


def link(link_id: str, src):
    return SimpleNamespace(id=link_id, quote="q", direction="supports", location={})


def section(title: str, prose: str, offered: list[str], note: str = "initial_passed"):
    return SynthesisSection(
        title=title,
        synthesis=prose,
        source_ids=offered,
        claim_ids=[],
        generation_note=note,
    )


def package(sections: list[SynthesisSection], summary: str = "") -> SynthesisPackage:
    return SynthesisPackage(
        executive_summary=summary,
        sections=sections,
        cross_study_assessment="",
        conclusion="",
        uncertainty="",
        study_profiles=[],
        generated_by_llm=True,
    )


def collect(sources, evidence_by_claim, reportable, pkg):
    return {
        citation.label: citation
        for citation in _collect_citations(
            sources=sources,
            source_numbers={s.id: i for i, s in enumerate(sources, 1)},
            evidence_by_claim=evidence_by_claim,
            reportable_claims=reportable,
            package=pkg,
            turkish=True,
        )
    }


def test_cited_labels_reads_the_prose_not_the_offered_packet():
    # The distinction the whole record turns on. `source_ids` is what the evidence packet
    # handed the model; the prose is what the reader actually gets.
    sec = section(
        "Tema",
        "Bulgu şudur [S01]. Başka bir bulgu [S03].",
        offered=["S01", "S02", "S03"],
    )
    assert cited_labels(sec) == {"S01", "S03"}
    assert set(sec.source_ids) - cited_labels(sec) == {"S02"}


def test_citation_counts_totals_repeat_mentions():
    counts = citation_counts("Bir [S01] ve yine [S01].", "Ayrıca [S02].")
    assert counts["S01"] == 2
    assert counts["S02"] == 1


def test_a_cited_source_records_its_sections_and_count():
    s1 = source("src-1")
    claims = {"c1": [(link("e1", s1), s1)]}
    pkg = package(
        [section("Tema A", "Sonuç böyledir [S01]. Yine [S01].", offered=["S01"])],
        summary="Özet [S01].",
    )
    citations = collect([s1], claims, [claim("c1")], pkg)
    record = citations["S01"]
    assert record.drop_reason == CitationDrop.CITED
    assert record.cited
    assert record.cited_sections == ["Tema A", "Yönetici Özeti"]
    # Two mentions in the theme plus one in the summary.
    assert record.citation_count == 3
    assert record.claim_ids == ["c1"]
    assert record.evidence_ids == ["e1"]


def test_a_source_cited_only_in_the_executive_summary_still_counts_as_cited():
    # The overview fields are part of the document. Scanning only the themed sections would
    # file this under offered_not_cited and send someone hunting a bug that is not there.
    s1 = source("src-1")
    claims = {"c1": [(link("e1", s1), s1)]}
    pkg = package([section("Tema A", "Genel bir cümle.", offered=["S01"])], summary="Özet [S01].")
    record = collect([s1], claims, [claim("c1")], pkg)["S01"]
    assert record.drop_reason == CitationDrop.CITED
    assert record.cited_sections == ["Yönetici Özeti"]


def test_a_source_with_no_evidence_is_recorded_as_such():
    s1 = source("src-1")
    record = collect([s1], {}, [], package([]))["S01"]
    assert record.drop_reason == CitationDrop.NO_EVIDENCE
    assert record.claim_ids == []


def test_evidence_that_never_cleared_the_reportable_threshold():
    # The source produced quotes, but its claim did not reach the report at all -- a
    # different failure from a model that saw the source and passed it over.
    s1 = source("src-1")
    claims = {"c1": [(link("e1", s1), s1)]}
    record = collect([s1], claims, [], package([]))["S01"]
    assert record.drop_reason == CitationDrop.NOT_REPORTABLE


def test_offered_to_the_model_and_never_cited():
    s1, s2 = source("src-1"), source("src-2")
    claims = {"c1": [(link("e1", s1), s1)], "c2": [(link("e2", s2), s2)]}
    pkg = package([section("Tema A", "Yalnız biri anılıyor [S01].", offered=["S01", "S02"])])
    citations = collect([s1, s2], claims, [claim("c1"), claim("c2")], pkg)
    assert citations["S01"].drop_reason == CitationDrop.CITED
    assert citations["S02"].drop_reason == CitationDrop.OFFERED_NOT_CITED
    # The offered/cited gap is what makes the two distinguishable at all.
    assert citations["S02"].offered_sections == ["Tema A"]
    assert citations["S02"].cited_sections == []


def test_a_discarded_section_draft_is_named_as_the_reason():
    # `_clean_cited_text` throws away a whole draft over one out-of-range citation. The
    # source did not fail on its own merits and the record must not imply that it did.
    s1 = source("src-1")
    claims = {"c1": [(link("e1", s1), s1)]}
    pkg = package(
        [section("Tema A", "Yedek metin.", offered=["S01"], note="fallback:invalid_repair")]
    )
    record = collect([s1], claims, [claim("c1")], pkg)["S01"]
    assert record.drop_reason == CitationDrop.SECTION_DISCARDED


def test_a_fallback_section_that_still_cites_the_source_is_not_a_drop():
    # The deterministic fallback writes real citations. A `fallback:` note alone is not an
    # absence -- only an absence is.
    s1 = source("src-1")
    claims = {"c1": [(link("e1", s1), s1)]}
    pkg = package(
        [
            section(
                "Tema A", "Yedek metin ama atıflı [S01].", offered=["S01"], note="fallback:timeout"
            )
        ]
    )
    assert collect([s1], claims, [claim("c1")], pkg)["S01"].drop_reason == CitationDrop.CITED


def test_without_a_synthesis_package_every_source_still_gets_a_row():
    # The legacy renderer has no sections to cite from. Writing nothing would make "this run
    # produced no citation record" and "this run predates the table" look identical.
    s1, s2 = source("src-1"), source("src-2")
    claims = {"c1": [(link("e1", s1), s1)]}
    citations = collect([s1, s2], claims, [claim("c1")], None)
    assert set(citations) == {"S01", "S02"}
    assert citations["S01"].drop_reason == CitationDrop.NOT_REPORTABLE
    assert citations["S02"].drop_reason == CitationDrop.NO_EVIDENCE


def test_labels_follow_the_catalogue_numbering():
    sources = [source(f"src-{i}") for i in range(1, 4)]
    citations = collect(sources, {}, [], package([]))
    assert [c.number for c in citations.values()] == [1, 2, 3]
    assert sorted(citations) == ["S01", "S02", "S03"]
    assert all(c.in_bibliography for c in citations.values())
