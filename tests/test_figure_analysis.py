from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import fitz
import httpx
import pytest
from PIL import Image

from research_platform.figure_analysis import (
    _FIGURE_CACHE_VERSION,
    _REPORT_DISPLAY_KEY,
    FigureCandidate,
    FigureObservation,
    _analysis_for_report,
    _analyze_candidate,
    _generated_figures,
    _language_matches,
    _localize_source_captions,
    _normalise_analysis,
    _numbers_match,
    _pdf_candidates,
    _repair_language,
    _source_excerpt_figures,
    analyze_run_figures,
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
        (
            "Şekil, kaynak tarafından tanımlanan 1–5 puan ölçeğindeki göreli değerleri "
            "gösterir; bunlar klinik performans yüzdeleri değildir."
        )
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


@pytest.mark.asyncio
async def test_source_caption_is_localized_without_mutating_provenance() -> None:
    candidate = FigureCandidate(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image=_png(),
        page_number=3,
        caption="Figure 2. The analysis has 3 stages and clinical outcomes.",
        locator="PDF page 3 figure crop",
        source_excerpt_ready=True,
    )
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash=candidate.image_hash,
        image_key="runs/test/figure.png",
        page_number=3,
        caption=candidate.caption,
        figure_type="flowchart",
        title="Şekil 2. Analizin üç aşaması",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=["Analiz üç aşamadan oluşur."],
        limitations=[],
        recommended_section="Yaklaşımlar ve yöntemler",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
        include_in_report=True,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload = json.loads(request.content)
        assert "TARGET LANGUAGE: Turkish" in request_payload["messages"][1]["content"]
        translated = {
            "translations": [
                {
                    "id": f"{candidate.image_hash}:caption",
                    "text": "Şekil 2. Analizin 3 aşaması ve klinik sonuçları.",
                }
            ]
        }
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(translated, ensure_ascii=False)}},
        )

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, updates, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
        )

    figures = _source_excerpt_figures(
        [observation],
        [candidate],
        minimum_relevance=0.55,
        minimum_confidence=0.75,
        maximum=3,
        turkish=True,
        caption_overrides=captions,
    )

    assert observation.caption == candidate.caption
    assert figures[0].caption == (
        "Kaynak figürü: Şekil 2. Analizin 3 aşaması ve klinik sonuçları. [S01, s. 3]."
    )
    assert "The analysis" not in figures[0].caption
    assert updates[candidate.image_hash]["caption_status"] == "translated"
    assert diagnostics["translated"] == 1


@pytest.mark.asyncio
async def test_caption_translation_failure_uses_deterministic_local_fallback() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="a" * 64,
        image_key="runs/test/figure.png",
        page_number=3,
        caption="Figure 2. The analysis of clinical outcomes.",
        figure_type="flowchart",
        title="Şekil 2. Klinik sonuçların analizi",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Yaklaşımlar ve yöntemler",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, updates, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
        )

    assert captions[observation.image_hash] == (
        "Şekil 2. Ayrıntılı özgün açıklama kaynak kaydında korunmuştur."
    )
    assert updates[observation.image_hash]["caption_status"] == "fallback"
    assert diagnostics["fallback"] == 1
    assert [row["attempt"] for row in diagnostics["failures"]] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_reason"),
    [
        ("invalid_json", "invalid_json:JSONDecodeError"),
        ("missing_item", "missing_item"),
        ("unknown_id", "unknown_id"),
    ],
)
async def test_caption_failure_reasons_are_distinguished(
    mode: str,
    expected_reason: str,
) -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="9" * 64,
        image_key="runs/test/figure.png",
        page_number=3,
        caption="Figure 2. The analysis reports 3 clinical outcomes.",
        figure_type="flowchart",
        title="Figure 2. Analysis outcomes",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Results",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if mode == "invalid_json":
            content = "not-json"
        elif mode == "missing_item":
            content = json.dumps({"translations": []})
        else:
            content = json.dumps(
                {"translations": [{"id": "wrong-hash:caption", "text": "Şekil 2."}]}
            )
        return httpx.Response(200, json={"message": {"content": content}})

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, updates, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
        )

    assert updates[observation.image_hash]["caption_status"] == "fallback"
    assert "Ayrıntılı özgün açıklama" in captions[observation.image_hash]
    assert any(row["reason"] == expected_reason for row in diagnostics["failures"])


@pytest.mark.asyncio
async def test_english_source_caption_is_not_rewritten_for_english_report() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="b" * 64,
        image_key="runs/test/figure.png",
        page_number=3,
        caption="Figure 2. The analysis has three stages and clinical outcomes.",
        figure_type="flowchart",
        title="Figure 2. Analysis stages",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Approaches and methods",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("A matching English caption must not call the translator")

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, updates, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "en",
        )

    assert captions[observation.image_hash] == observation.caption
    assert updates[observation.image_hash]["caption_status"] == "source_already_matching"
    assert diagnostics["direct"] == 1


@pytest.mark.asyncio
async def test_short_figure_labels_are_canonicalized_without_model_call() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="c" * 64,
        image_key="runs/test/figure.png",
        page_number=None,
        caption="Fig 2",
        figure_type="bar chart",
        title="Fig 2",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Bulgular",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("A short figure label must be canonicalized deterministically")

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, updates, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
        )

    assert captions[observation.image_hash] == "Şekil 2."
    assert updates[observation.image_hash]["caption_status"] == "canonicalized"
    assert diagnostics["direct"] == 1
    assert not _language_matches("Fig 2", "tr")
    assert _language_matches("Şekil 2", "tr")
    assert not _language_matches("Şekil 2", "en")


@pytest.mark.asyncio
async def test_caption_number_mismatch_is_retried_and_locale_grouping_is_accepted() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="d" * 64,
        image_key="runs/test/figure.png",
        page_number=10,
        caption="Figure 2. The 95% interval used 10,000 samples from 3 readers.",
        figure_type="scatter plot",
        title="Reader comparison",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Bulgular",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b",
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        reader_count = 4 if calls == 1 else 3
        translated = {
            "translations": [
                {
                    "id": f"{observation.image_hash}:caption",
                    "text": (
                        f"Şekil 2. %95 aralığında 10.000 örnek ve "
                        f"{reader_count} okuyucu kullanıldı."
                    ),
                }
            ]
        }
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(translated, ensure_ascii=False)}},
        )

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, _, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
        )

    assert calls == 2
    assert captions[observation.image_hash].endswith("3 okuyucu kullanıldı.")
    assert any(row["reason"] == "number_mismatch" for row in diagnostics["failures"])
    assert _numbers_match("10,000 samples", "10.000 örnek")


@pytest.mark.asyncio
async def test_valid_cached_caption_is_reused_without_model_call() -> None:
    observation = FigureObservation(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image_hash="e" * 64,
        image_key="runs/test/figure.png",
        page_number=3,
        caption="Figure 2. The analysis has 3 stages.",
        figure_type="flowchart",
        title="Şekil 2. Analiz aşamaları",
        axes={"x": "", "y": ""},
        series=[],
        data_points=[],
        flow_steps=[],
        main_findings=[],
        limitations=[],
        recommended_section="Yöntemler",
        relevance_score=0.9,
        exact_values_visible=False,
        confidence=0.9,
        vision_model="qwen3.5:4b#figure-v5",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("A validated cached display caption must not be translated again")

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    display = {
        "language": "tr",
        "caption": "Şekil 2. Analizin 3 aşaması.",
        "caption_status": "translated",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        captions, _, diagnostics = await _localize_source_captions(
            client,
            settings,
            [observation],
            "tr",
            displays={observation.image_hash: display},
        )

    assert captions[observation.image_hash] == display["caption"]
    assert diagnostics["reused"] == 1
    assert _FIGURE_CACHE_VERSION == "figure-v5"


@pytest.mark.asyncio
async def test_analysis_repair_projects_only_localized_display_fields() -> None:
    raw = {
        "is_research_figure": True,
        "title": "Figure 2. Reader performance",
        "main_findings": ["The model outperformed 3 readers."],
        "limitations": ["Only one validation set was available."],
        "flow_steps": [],
        "selection_reason": "The comparison supports the report.",
        "recommended_section": "Results",
        "relevance_score": 0.9,
        "confidence": 0.8,
        "axes": {"x": "Readers", "y": "Accuracy"},
        "series": ["Model"],
        "data_points": [],
    }
    translations = {
        "title": "Şekil 2. Okuyucu performansı",
        "main_findings": "Model 3 okuyucudan daha iyi performans gösterdi.",
        "limitations": "Yalnızca bir doğrulama kümesi kullanılabilirdi.",
        "selection_reason": "Karşılaştırma raporu destekler.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        rows = json.loads(payload["messages"][1]["content"].split("ITEMS:\n", 1)[1])
        output = []
        for row in rows:
            field_name = row["id"].split(":")[-2]
            output.append({"id": row["id"], "text": translations[field_name]})
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps({"translations": output})}},
        )

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        display, diagnostics = await _repair_language(
            client,
            settings,
            raw,
            "tr",
            ["Bulgular"],
            image_hash="f" * 64,
            fallback_source=raw["title"],
        )

    stored = dict(raw)
    stored[_REPORT_DISPLAY_KEY] = display
    projected = _analysis_for_report(stored, "tr")
    assert raw["title"] == "Figure 2. Reader performance"
    assert projected["title"] == translations["title"]
    assert projected["main_findings"] == [translations["main_findings"]]
    assert projected["axes"] is raw["axes"]
    assert projected["series"] is raw["series"]
    assert display["recommended_section"] == "Bulgular"
    assert diagnostics["translated"] == 4


@pytest.mark.asyncio
async def test_failed_analysis_translation_suppresses_narrative_fields() -> None:
    raw = {
        "is_research_figure": True,
        "title": "Figure 2. Reader performance",
        "main_findings": ["The model outperformed the readers."],
        "limitations": ["Only one validation set was available."],
        "selection_reason": "The comparison supports the report.",
        "recommended_section": "Results",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        display, diagnostics = await _repair_language(
            client,
            settings,
            raw,
            "tr",
            ["Bulgular"],
            image_hash="f" * 64,
            fallback_source=raw["title"],
        )

    assert display["title"] == "Şekil 2"
    assert display["main_findings"] == []
    assert display["limitations"] == []
    assert display["selection_reason"] == ""
    assert display["analysis_status"] == "partial"
    assert diagnostics["fallback"] == 1
    assert diagnostics["suppressed"] == 3


@pytest.mark.asyncio
async def test_vision_analysis_prompt_and_display_follow_english_report_language() -> None:
    candidate = FigureCandidate(
        source_id="source-1",
        source_version_id="version-1",
        source_label="S01",
        source_title="Clinical figure source",
        image=_png(),
        page_number=2,
        caption="Figure 2. Reader performance.",
        locator="PDF page 2",
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert "Write English" in payload["messages"][1]["content"]
        raw = {
            "is_research_figure": True,
            "figure_type": "scatter plot",
            "title": "Figure 2. Reader performance",
            "axes": {"x": "Readers", "y": "Accuracy"},
            "series": ["Model"],
            "data_points": [],
            "main_findings": ["The model outperformed the readers."],
            "limitations": ["Only one validation set was available."],
            "flow_steps": [],
            "recommended_section": "Results",
            "relevance_score": 0.9,
            "exact_values_visible": False,
            "confidence": 0.9,
            "include_in_report": True,
            "selection_reason": "The comparison supports the report.",
        }
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(raw)}},
        )

    settings = SimpleNamespace(
        ollama_url="http://ollama.test",
        vision_model="qwen3.5:4b",
        figure_analysis_timeout_s=30.0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        outcome = await _analyze_candidate(
            client,
            settings,
            candidate,
            "How does performance compare?",
            ["Results"],
            "runs/test/figure.png",
            "en",
            "qwen3.5:4b#figure-v5",
        )

    assert calls == 1
    assert outcome is not None
    assert outcome.observation.title == "Figure 2. Reader performance"
    assert outcome.stored_analysis["title"] == "Figure 2. Reader performance"
    assert outcome.stored_analysis[_REPORT_DISPLAY_KEY]["language"] == "en"


@pytest.mark.asyncio
async def test_figure_pipeline_emits_one_localization_summary_event() -> None:
    events: list[tuple[str, str, dict]] = []

    class Repo:
        async def list_source_versions(self, run_id: str) -> list:
            return []

        async def list_figure_observations(self, run_id: str) -> list:
            return []

        async def event(self, run_id: str, event_type: str, payload: dict) -> None:
            events.append((run_id, event_type, payload))

    settings = SimpleNamespace(
        testing=False,
        figure_analysis_enabled=True,
        figure_max_candidates=8,
        vision_model="qwen3.5:4b",
        figure_max_pages_per_source=2,
        figure_min_relevance=0.55,
        figure_source_embedding_enabled=True,
        figure_source_min_confidence=0.75,
        figure_source_max_exports=3,
    )
    result = await analyze_run_figures(
        run_id="01FIGUREEVENT",
        question="How do the models compare?",
        language="en",
        section_titles=["Results"],
        sources=[],
        repo=Repo(),  # type: ignore[arg-type]
        store=SimpleNamespace(),
        settings=settings,
    )

    assert result.observations == []
    assert len(events) == 1
    assert events[0][1] == "figure_localization"
    assert events[0][2]["target_language"] == "en"
    assert "failures" in events[0][2]
