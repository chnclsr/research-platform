import io
from types import SimpleNamespace

import pptx

from research_platform.presentation_report import (
    PRESENTATION_REPORT_FALLBACK,
    build_presentation_report,
    presentation_report_name,
)
from research_platform.report_synthesis import SynthesisPackage, SynthesisSection


def _minimal_report_inputs():
    source1 = SimpleNamespace(
        id="src-1",
        title="Sağlıkta Yapay Zeka Uygulamaları",
        url="https://example.org/s1",
        connector_id="pubmed",
        metadata_json={"year": 2024, "type": "Makale", "research_scope_role": "primary_in_scope"},
    )
    claim1 = SimpleNamespace(
        id="claim-1",
        text="Yapay zeka modelleri tanı doğruluğunu artırır.",
        status="supported",
        confidence=0.95,
        audit={"question_relevance": 0.92},
    )
    link1 = SimpleNamespace(
        direction="supports",
        quote="Yapay zeka tanı sürecini hızlandırır.",
        location={"section_path": "Abstract"},
        entailment_score=0.95,
    )
    return {
        "run_id": "test-run-12345678",
        "title": "Sağlıkta Yapay Zeka",
        "question": "Yapay zeka tanı süreçlerini nasıl etkiler?",
        "language": "tr",
        "coverage": {
            "source_family_coverage": 0.90,
            "query_branch_coverage": 0.85,
            "claim_audit_coverage": 0.95,
            "estimated_completeness": "Yüksek",
            "unresolved_primary_claims": 0,
        },
        "sources": [source1],
        "claims": [claim1],
        "reportable_claims": [claim1],
        "evidence_by_claim": {"claim-1": [(link1, source1)]},
        "executive_summary": "Yapay zeka tanı süreçlerinde etkilidir [S01].",
        "narrative": "Kanıt sentezi detayları.",
        "uncertainty": "Veri kalitesi ve heterojenlik belirsizlik yaratmaktadır.",
        "scope": {
            "start_date": "2020",
            "end_date": "2024",
            "query_intent": "Klinik yapay zeka literatürü",
        },
        "sub_questions": ["Tanı performansı nedir?", "İş akışına etkisi nedir?"],
    }


def test_presentation_report_name():
    assert presentation_report_name("ai_in_lung_ct") == "16_ai_in_lung_ct_report.pptx"
    assert presentation_report_name(None) == PRESENTATION_REPORT_FALLBACK
    assert presentation_report_name("") == PRESENTATION_REPORT_FALLBACK
    assert presentation_report_name("sağlık_yapay_zekâ").endswith(".pptx")


def test_presentation_report_uses_title_for_report():
    inputs = _minimal_report_inputs()
    inputs["title"] = "Kısa Okuyucu Başlığı"
    inputs["question"] = "Uzun ve karmaşık orijinal araştırma sorusu?"
    res = build_presentation_report(**inputs)
    prs = pptx.Presentation(io.BytesIO(res.document))
    cover_slide = prs.slides[0]
    cover_texts = [shp.text for shp in cover_slide.shapes if shp.has_text_frame]
    assert any("Kısa Okuyucu Başlığı" in t for t in cover_texts)

    # Question is placed in research framework slide (slide 4)
    framework_slide = prs.slides[3]
    framework_texts = [shp.text for shp in framework_slide.shapes if shp.has_text_frame]
    assert any("Uzun ve karmaşık orijinal araştırma sorusu?" in t for t in framework_texts)


def test_compact_presentation_report_suppresses_thematic_slides():
    package = SynthesisPackage(
        executive_summary="Seyrek kanıt yalnız sınırlı bir sonuç destekler [S01].",
        sections=[
            SynthesisSection(
                title="Kanıt özeti",
                synthesis="Seyrek kanıt yalnız sınırlı bir sonuç destekler [S01].",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            )
        ],
        cross_study_assessment="",
        conclusion="",
        uncertainty="Kanıt hacmi sınırlıdır.",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="compact",
        quality_diagnostics={"mode_reasons": ["fewer_than_8_unique_claims"]},
    )
    inputs = _minimal_report_inputs()
    inputs.update(
        {
            "title": "Kompakt Sağlık Raporu",
            "synthesis_package": package,
        }
    )
    res = build_presentation_report(**inputs)
    assert len(res.document) > 50000

    prs = pptx.Presentation(io.BytesIO(res.document))
    # Compact mode should have fewer slides (no separate themes or cross-study assessment)
    all_texts = []
    for slide in prs.slides:
        texts = [shp.text for shp in slide.shapes if shp.has_text_frame]
        all_texts.extend(texts)
    full_text = " ".join(all_texts)

    assert "3. Tematik kanıt sentezi" not in full_text
    assert "4. Çalışmalar arası değerlendirme ve sonuç" not in full_text
    assert "3. Belirsizlikler ve araştırma boşlukları" in full_text
    assert "Seyrek kanıt yalnız sınırlı bir sonuç destekler [S01]." in full_text

    # Verify slide numbers are sequential
    slide_numbers = []
    for s in prs.slides:
        for shp in s.shapes:
            if shp.name == "slide_number" and shp.has_text_frame:
                slide_numbers.append(shp.text.strip())
    assert len(slide_numbers) > 0
    # Check that slide numbers are strictly increasing integers
    int_nums = [int(n) for n in slide_numbers if n.isdigit()]
    assert int_nums == sorted(int_nums)


def test_standard_presentation_report_renders_multiple_themes():
    package = SynthesisPackage(
        executive_summary="Kanıt iki temada ayrışır [S01].",
        sections=[
            SynthesisSection(
                title="Klinik Doğruluk",
                synthesis="Klinik doğruluk modellerde yüksektir [S01].",
                consensus="Modeller erken teşhiste etkilidir.",
                disagreements="Veri çeşitliliği eksiktir.",
                implications="Klinik iş akışını destekler.",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            ),
            SynthesisSection(
                title="İş Akışı Entegrasyonu",
                synthesis="Entegrasyon hastane sistemlerine uyumu gerektirir [S01].",
                consensus="HIS/PACS uyumu şarttır.",
                disagreements="",
                implications="Altyapı yatırımı gereklidir.",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            ),
        ],
        cross_study_assessment="Her iki tema birlikte değerlendirildiğinde klinik fayda belirgindir.",
        conclusion="Tanı süreçlerinde yapay zeka kullanımı önerilmektedir.",
        uncertainty="Daha fazla prospektif çalışmaya ihtiyaç vardır.",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="standard",
    )
    inputs = _minimal_report_inputs()
    inputs.update(
        {
            "title": "Standart Çok Temalı Rapor",
            "synthesis_package": package,
        }
    )
    res = build_presentation_report(**inputs)
    assert len(res.document) > 50000

    prs = pptx.Presentation(io.BytesIO(res.document))
    all_texts = []
    for slide in prs.slides:
        texts = [shp.text for shp in slide.shapes if shp.has_text_frame]
        all_texts.extend(texts)
    full_text = " ".join(all_texts)

    # Both themes should appear in the generated slides
    assert "Klinik Doğruluk" in full_text
    assert "İş Akışı Entegrasyonu" in full_text
    assert "3. Tematik kanıt sentezi" in full_text
    assert "4. Değerlendirme ve sonuç" in full_text


def test_standard_presentation_report_renders_multiple_figures():
    from PIL import Image, ImageDraw

    def make_img(text, color):
        img = Image.new("RGB", (800, 600), color=color)
        d = ImageDraw.Draw(img)
        d.text((50, 50), text, fill="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    fig1 = SimpleNamespace(
        title="Lezyon Segmentasyonu",
        caption="Şekil 1: Nodül tespiti",
        attribution="PubMed S01",
        rights_statement="CC-BY 4.0",
        data=make_img("Fig 1", "blue"),
        observation_hash="h1",
    )
    fig2 = SimpleNamespace(
        title="ROC Eğrisi Analizi",
        caption="Şekil 2: AUC=0.94",
        attribution="PubMed S01",
        rights_statement="CC-BY 4.0",
        data=make_img("Fig 2", "green"),
        observation_hash="h2",
    )
    obs1 = SimpleNamespace(
        image_hash="h1",
        selection_reason="Tanı duyarlılığı",
        main_findings=["Duyarlılık %94"],
        limitations=["Tek merkezli"],
    )
    obs2 = SimpleNamespace(
        image_hash="h2",
        selection_reason="Model başarımı",
        main_findings=["AUC 0.94"],
        limitations=["Validasyon sınırlı"],
    )

    inputs = _minimal_report_inputs()
    inputs.update(
        {
            "title": "Çok Figürlü Rapor",
            "research_figures": [fig1, fig2],
            "figure_observations": [obs1, obs2],
        }
    )
    res = build_presentation_report(**inputs)
    prs = pptx.Presentation(io.BytesIO(res.document))
    all_headings = []
    for s in prs.slides:
        for shp in s.shapes:
            if shp.name == "content_heading" and shp.has_text_frame:
                all_headings.append(shp.text.strip())

    assert any("Lezyon Segmentasyonu" in h for h in all_headings)
    assert any("ROC Eğrisi Analizi" in h for h in all_headings)
    # Both figures must be present as distinct slides
    fig_headings = [h for h in all_headings if "Figür" in h]
    assert len(fig_headings) == 2
