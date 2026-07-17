from __future__ import annotations

from datetime import datetime, timezone

from research_platform.relevance import document_relevance, temporal_relevance
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ResearchProtocol,
    SourceFamily,
)
from research_platform.temporal import (
    constrain_text_to_scope,
    infer_relative_date_range,
    publication_datetime,
)


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def test_relative_last_three_months_becomes_an_explicit_utc_scope():
    start, end = infer_relative_date_range("papers from the last 3 months", now=NOW)
    assert start == datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    assert end == NOW


def test_scope_removes_year_invented_by_query_planner():
    cleaned = constrain_text_to_scope(
        "Recent clinical validation studies (2024) for lung cancer CT",
        datetime(2026, 4, 17, tzinfo=timezone.utc),
        datetime(2026, 7, 17, tzinfo=timezone.utc),
    )
    assert "2024" not in cleaned
    assert "lung cancer CT" in cleaned


def test_academic_recent_query_uses_only_academic_family_as_required_coverage():
    protocol = ResearchProtocol(
        title="Recent lung CT studies",
        primary_question=(
            "What clinical studies were published in the last 3 months about "
            "lung cancer radiomics?"
        ),
    )
    assert set(protocol.family_targets) == {SourceFamily.ACADEMIC}
    assert protocol.family_targets[SourceFamily.ACADEMIC].minimum_sources == 2
    assert protocol.scope.start_date is not None
    assert protocol.scope.end_date is not None


def test_crossref_and_europe_pmc_date_metadata_are_normalized():
    crossref, basis = publication_datetime({
        "published": {"date-parts": [[2026, 6, 19]]},
    })
    europe, europe_basis = publication_datetime({"firstPublicationDate": "2026-05-01"})
    assert crossref == datetime(2026, 6, 19, tzinfo=timezone.utc)
    assert basis == "published"
    assert europe == datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert europe_basis == "firstPublicationDate"


def test_temporal_gate_rejects_old_and_unknown_sources_for_bounded_research():
    protocol = ResearchProtocol(
        title="Bounded research",
        primary_question="Recent clinical studies about lung cancer",
        scope={"start_date": "2026-04-17T00:00:00Z", "end_date": "2026-07-17T23:59:59Z"},
        connectors={"profile": "custom", "included_families": ["academic"]},
    )
    old = ConnectorCandidate(
        connector_id="crossref", family=SourceFamily.ACADEMIC,
        title="Old lung CT paper", url="https://doi.org/10.1/old",
        published_at="2024-02-01T00:00:00Z",
    )
    unknown = ConnectorCandidate(
        connector_id="web", family=SourceFamily.WEB,
        title="Undated page", url="https://example.org/page",
    )
    assert temporal_relevance(old, protocol, reject_unknown=True)[0] is False
    assert temporal_relevance(unknown, protocol, reject_unknown=True) == (
        False, "publication_date_unknown",
    )


def test_post_acquisition_gate_rejects_finance_noise_and_keeps_lung_ct_study():
    protocol = ResearchProtocol(
        title="Recent lung CT studies",
        primary_question=(
            "What new clinical studies use axial chest CT for lung cancer risk estimation?"
        ),
        connectors={"profile": "custom", "included_families": ["academic"]},
    )
    finance_candidate = ConnectorCandidate(
        connector_id="crossref", family=SourceFamily.ACADEMIC,
        title="Financial Risk Prediction with Deep Learning Models",
        url="https://doi.org/10.1/finance",
    )
    finance = AcquiredDocument(
        candidate=finance_candidate, success=True,
        content="Stock volatility and firm leverage are modeled with deep learning.",
    )
    lung_candidate = ConnectorCandidate(
        connector_id="europe_pmc", family=SourceFamily.ACADEMIC,
        title="Lung cancer malignancy prediction from chest CT",
        url="https://europepmc.org/article/MED/1",
    )
    lung = AcquiredDocument(
        candidate=lung_candidate, success=True,
        content=(
            "The clinical study estimates pulmonary nodule malignancy and future lung "
            "cancer risk from axial chest CT imaging."
        ),
    )
    assert document_relevance(finance, protocol)[0] is False
    assert document_relevance(lung, protocol)[0] is True


def test_academic_gate_does_not_use_related_page_links_to_change_the_paper_subject():
    protocol = ResearchProtocol(
        title="Recent lung CT studies",
        primary_question="What radiomics methods estimate lung cancer risk from chest CT?",
        connectors={"profile": "custom", "included_families": ["academic"]},
    )
    candidate = ConnectorCandidate(
        connector_id="crossref", family=SourceFamily.ACADEMIC,
        title="CT radiomic prediction of TP53 mutation in pancreatic cancer",
        url="https://doi.org/10.1/pancreas",
    )
    document = AcquiredDocument(
        candidate=candidate, success=True,
        content=(
            "This paper studies pancreatic cancer. Related articles: lung cancer "
            "risk estimation, chest CT imaging, pulmonary nodule malignancy."
        ),
    )
    assert document_relevance(document, protocol)[0] is False
