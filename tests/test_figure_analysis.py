from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import fitz
from PIL import Image

from research_platform.figure_analysis import (
    FigureCandidate,
    FigureObservation,
    _generated_figures,
    _normalise_analysis,
    _pdf_candidates,
    _source_excerpt_figures,
)


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (800, 480), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_vision_output_is_normalised_and_unknown_values_are_not_invented() -> None:
    candidate = FigureCandidate(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image=_png(),
        page_number=4,
        caption="Figure 2. Explicit cohort values.",
        locator="PDF page 4",
    )
    observation = _normalise_analysis(
        {
            "is_research_figure": True,
            "figure_type": "horizontal bar chart",
            "title": "Cohort distribution",
            "axes": {"x": "Participants", "y": "Cohort"},
            "series": ["Participants"],
            "data_points": [
                {"label": "A", "value": 120, "unit": ""},
                {"label": "B", "value": "80", "unit": ""},
                {"label": "Unreadable", "value": "unknown"},
            ],
            "main_findings": ["Cohort A is larger than cohort B."],
            "limitations": ["Only two cohorts are shown."],
            "recommended_section": "Study populations",
            "relevance_score": 0.9,
            "exact_values_visible": True,
            "confidence": 0.88,
        },
        candidate,
        "runs/test/figure.png",
        "qwen3.5:4b",
    )

    assert observation is not None
    assert [row["value"] for row in observation.data_points] == [120.0, 80.0]
    assert observation.source_label == "S01"


def test_source_defined_score_scale_is_not_reinterpreted_as_clinical_percentages() -> None:
    candidate = FigureCandidate(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image=_png(),
        page_number=4,
        caption="Figure 2. AI performance metrics.",
        locator="PDF page 4",
    )
    observation = _normalise_analysis(
        {
            "is_research_figure": True,
            "figure_type": "bar chart",
            "title": "AI performance metrics",
            "axes": {
                "x": ["Sensitivity", "Specificity", "AUC"],
                "y": "Effectiveness score (1-Low to 5-Excellent)",
            },
            "data_points": [
                {"label": "Sensitivity", "value": 4.5},
                {"label": "Specificity", "value": 4.2},
                {"label": "AUC", "value": 4.7},
            ],
            "main_findings": ["Sensitivity is 4.5 and therefore 4.5 percent."],
            "limitations": [],
            "recommended_section": "Comparative outcomes",
            "relevance_score": 0.9,
            "exact_values_visible": True,
            "confidence": 0.9,
        },
        candidate,
        "runs/test/figure.png",
        "qwen3.5:4b",
        language="tr",
    )

    assert observation is not None
    assert observation.main_findings == [
        "Şekil, kaynak tarafından tanımlanan 1–5 puan ölçeğindeki göreli değerleri "
        "gösterir; bunlar klinik performans yüzdeleri değildir."
    ]
    assert "yüzdesi olarak" in observation.limitations[0]


def test_only_explicit_high_confidence_bar_values_are_reconstructed() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="a" * 64,
        image_key="runs/test/figure.png",
        page_number=4,
        caption="Figure 2.",
        figure_type="bar chart",
        title="Outcome by cohort",
        axes={"x": "Cohort", "y": "Percent"},
        series=["Outcome"],
        data_points=[
            {"label": "A", "value": 30.0, "unit": "%", "series": "Outcome"},
            {"label": "B", "value": 40.0, "unit": "%", "series": "Outcome"},
            {"label": "C", "value": 50.0, "unit": "%", "series": "Outcome"},
        ],
        flow_steps=[],
        main_findings=["Outcome differs across cohorts."],
        limitations=[],
        recommended_section="Comparative outcomes",
        relevance_score=0.9,
        exact_values_visible=True,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )

    figures = _generated_figures(
        [observation],
        minimum_relevance=0.55,
        turkish=False,
    )

    assert len(figures) == 1
    assert figures[0].name == "17a_source_figure_reconstruction.png"
    assert figures[0].data.startswith(b"\x89PNG")
    assert figures[0].source_labels == ["S01"]


def test_pdf_pages_with_figure_markers_become_candidates() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Figure 1. Model performance by cohort")
    page.draw_rect(fitz.Rect(100, 120, 400, 300), color=(0, 0, 1))
    raw = document.tobytes()
    document.close()
    source = SimpleNamespace(id="source-1", title="PDF source")
    version = SimpleNamespace(id="version-1", raw_content=base64.b64encode(raw).decode())

    candidates = _pdf_candidates(
        source,
        version,
        "S01",
        "model performance cohort",
        maximum=2,
    )

    assert len(candidates) == 1
    assert candidates[0].page_number == 1
    assert candidates[0].image.startswith(b"\x89PNG")
    assert "Figure 1" in candidates[0].caption
    assert candidates[0].source_excerpt_ready
    with Image.open(io.BytesIO(candidates[0].image)) as cropped:
        assert cropped.width > cropped.height


def test_model_selected_source_crop_is_preferred_for_the_report() -> None:
    candidate = FigureCandidate(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image=_png(),
        page_number=4,
        caption="Figure 2. Outcome by cohort.",
        locator="PDF page 4 figure crop",
        source_url="https://example.org/paper",
        rights_statement="Kaynak metadata kaydında açık lisans bilgisi bulunamadı.",
        source_excerpt_ready=True,
    )
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash=candidate.image_hash,
        image_key="runs/test/figure.png",
        page_number=4,
        caption=candidate.caption,
        figure_type="bar chart",
        title="Outcome by cohort",
        axes={"x": "Cohort", "y": "Percent"},
        series=["Outcome"],
        data_points=[],
        flow_steps=[],
        main_findings=["The figure compares outcomes across cohorts."],
        limitations=[],
        recommended_section="Comparative outcomes",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
        include_in_report=True,
        selection_reason="The visual comparison is central to the finding.",
    )

    figures = _source_excerpt_figures(
        [observation],
        [candidate],
        minimum_relevance=0.55,
        minimum_confidence=0.75,
        maximum=3,
        turkish=False,
    )

    assert len(figures) == 1
    assert figures[0].data == candidate.image
    assert figures[0].origin == "source_excerpt"
    assert figures[0].observation_hash == candidate.image_hash
    assert "p. 4" in figures[0].caption
    assert "internal research review" in figures[0].rights_statement
