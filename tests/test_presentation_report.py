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


def test_presentation_report_long_synthesis_autofit_and_no_overlap():
    long_synthesis = (
        "Akciğer bilgisayarlı tomografi taramalarında yapay zeka modellerinin tanısal doğruluğu, derin evrişimli sinir ağları "
        "ve transformatör tabanlı mimarilerle belirgin biçimde artmıştır. Çok merkezli kohortlarda 3 mm altındaki nodüllerin "
        "yakalanma hassasiyeti %95 üzerine çıkmış ve radyologların gözden kaçırma oranı önemli ölçüde düşürülmüştür [S01]. "
        "Malignite derecelendirmesinde radyomik özniteliklerin entegrasyonu benign lezyonları malign tümörlerden ayırt etmede "
        "ROC-AUC skorunu 0.93 seviyesine yükseltmiştir. Bu sayede invaziv biyopsi ihtiyacı olan hastalar daha güvenilir şekilde "
        "tabakalandırılabilmektedir. Bununla birlikte DICOM standartlarındaki farklılıklar ve rekonstrüksiyon filtreleri "
        "modellerin genellenebilirliğinde sapmalara yol açabilmektedir."
    )
    package = SynthesisPackage(
        executive_summary="Özet [S01].",
        sections=[
            SynthesisSection(
                title="Klinik Doğruluk ve Hassasiyet",
                synthesis=long_synthesis,
                consensus="YZ tespit doğruluğunu artırır.",
                disagreements="Cihaz varyasyonları genellenebilirliği etkiler.",
                implications="İkinci okuyucu desteği olarak kullanılmalıdır.",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            )
        ],
        cross_study_assessment="Değerlendirme",
        conclusion="Sonuç",
        uncertainty="Belirsizlik",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="standard",
    )
    inputs = _minimal_report_inputs()
    inputs.update({"title": "Uzun Sentez Testi", "synthesis_package": package})
    res = build_presentation_report(**inputs)
    prs = pptx.Presentation(io.BytesIO(res.document))

    # Theme 1 synthesis slide (Slide 6)
    s6 = prs.slides[5]
    shp_syn = next(s for s in s6.shapes if s.name == "sections[].synthesis")
    shp_cit = next(s for s in s6.shapes if s.name == "sections[].citations")
    font_pt = shp_syn.text_frame.paragraphs[0].runs[0].font.size.pt

    # Font should be scaled down to accommodate long text
    assert font_pt <= 16.0
    # Text box must not collide with citations box
    assert shp_syn.top.inches + shp_syn.height.inches <= shp_cit.top.inches + 0.05

    # Very long synthesis should scale down further (<= 12.5pt)
    package2 = SynthesisPackage(
        executive_summary="Özet [S01].",
        sections=[
            SynthesisSection(
                title="Klinik Doğruluk ve Hassasiyet",
                synthesis=long_synthesis + "\n\n" + long_synthesis,
                consensus="YZ tespit doğruluğunu artırır.",
                disagreements="Cihaz varyasyonları genellenebilirliği etkiler.",
                implications="İkinci okuyucu desteği olarak kullanılmalıdır.",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            )
        ],
        cross_study_assessment="Değerlendirme",
        conclusion="Sonuç",
        uncertainty="Belirsizlik",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="standard",
    )
    inputs2 = _minimal_report_inputs()
    inputs2.update({"title": "Çok Uzun Sentez Testi", "synthesis_package": package2})
    res2 = build_presentation_report(**inputs2)
    prs2 = pptx.Presentation(io.BytesIO(res2.document))
    s6_2 = prs2.slides[5]
    shp_syn_2 = next(s for s in s6_2.shapes if s.name == "sections[].synthesis")
    shp_cit_2 = next(s for s in s6_2.shapes if s.name == "sections[].citations")
    font_pt_2 = shp_syn_2.text_frame.paragraphs[0].runs[0].font.size.pt
    assert font_pt_2 <= 12.5
    assert shp_syn_2.top.inches + shp_syn_2.height.inches <= shp_cit_2.top.inches + 0.05

    # Theme 1 findings slide (Slide 7): vertical stacking without overlaps
    s7 = prs.slides[6]
    shp_con = next(s for s in s7.shapes if s.name == "sections[].consensus")
    shp_dis = next(s for s in s7.shapes if s.name == "sections[].disagreements")
    shp_imp = next(s for s in s7.shapes if s.name == "sections[].implications")

    assert shp_con.top.inches + shp_con.height.inches <= shp_dis.top.inches
    assert shp_dis.top.inches + shp_dis.height.inches <= shp_imp.top.inches
    assert shp_imp.top.inches + shp_imp.height.inches <= 7.0


def test_presentation_asserts_nothing_the_run_did_not_establish():
    """Empty sections used to become verdicts on the slides.

    "Çalışmalar arasında genel tutarlılık saptanmıştır", "Araştırma sorusu doğrulanmış
    kanıtlarla yanıtlanmıştır", "Açık bir belirsizlik veya veri boşluğu bildirilmedi", a
    conclusion box that always called the conclusion supported by audited evidence, and a
    coverage table reading 100% / "Tamamlandı" / 0 whenever the numbers were missing.
    """
    inputs = _minimal_report_inputs()
    inputs["coverage"] = {}
    inputs["synthesis_package"] = SynthesisPackage(
        executive_summary="Özet cümlesi [S01].",
        sections=[
            SynthesisSection(
                title="Tema bir",
                synthesis="Birinci taslak [S01].",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
                reader_note="Bu tema tek bir metinde birleştirilemedi.",
            ),
            SynthesisSection(
                title="Tema iki", synthesis="İkinci tema [S01].", source_ids=["src-1"]
            ),
        ],
        cross_study_assessment="",
        conclusion="",
        uncertainty="",
        study_profiles=[],
        generated_by_llm=False,
        generation_status="partial",
    )
    prs = pptx.Presentation(io.BytesIO(build_presentation_report(**inputs).document))

    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if shape.has_table:
                texts.extend(cell.text for row in shape.table.rows for cell in row.cells)
    deck = "\n".join(texts)

    for verdict in (
        "genel tutarlılık saptanmıştır",
        "doğrulanmış kanıtlarla yanıtlanmıştır",
        "belirsizlik veya veri boşluğu bildirilmedi",
        "doğrulanmış kanıt kaydıyla desteklenmiştir",
        "Tamamlandı",
        "100%",
    ):
        assert verdict not in deck, verdict
    assert "Bu tema tek bir metinde birleştirilemedi." in deck


def test_presentation_report_formats_date_and_toc_subsections():
    inputs = _minimal_report_inputs()
    inputs["scope"] = {
        "start_date": "2023-09-15T08:37:12.273500Z",
        "end_date": "2026-09-14T10:00:00Z",
        "query_intent": "Transformer mimarisi",
    }
    inputs["synthesis_package"] = SynthesisPackage(
        executive_summary="Özet metni [S01].",
        sections=[
            SynthesisSection(
                title="Dikkat Mekanizmaları",
                synthesis="Self-attention formülasyonu [S01].",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            ),
            SynthesisSection(
                title="Pozisyonel Kodlama",
                synthesis="Sinüzoidal pozisyonel kodlama [S01].",
                source_ids=["src-1"],
                claim_ids=["claim-1"],
            ),
        ],
        cross_study_assessment="",
        conclusion="",
        uncertainty="",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="standard",
    )
    prs = pptx.Presentation(io.BytesIO(build_presentation_report(**inputs).document))

    # Check Slide 2 TOC
    toc_slide = prs.slides[1]
    toc_text = "\n".join(shp.text for shp in toc_slide.shapes if shp.has_text_frame)
    assert "3.1 Dikkat Mekanizmaları" in toc_text
    assert "3.2 Pozisyonel Kodlama" in toc_text

    # Check Slide 4 Scope date formatting
    scope_slide = prs.slides[3]
    scope_text = "\n".join(shp.text for shp in scope_slide.shapes if shp.has_text_frame)
    assert "15.09.2023 – 14.09.2026" in scope_text
    assert "2023-09-15T" not in scope_text


def test_presentation_report_findings_slide_conditional_and_appendices():
    from PIL import Image as PILImage

    # Create dummy PNG bytes
    buf_a = io.BytesIO()
    PILImage.new("RGB", (400, 300), color="blue").save(buf_a, format="PNG")
    png_a = buf_a.getvalue()

    buf_b = io.BytesIO()
    PILImage.new("RGB", (400, 300), color="green").save(buf_b, format="PNG")
    png_b = buf_b.getvalue()

    inputs = _minimal_report_inputs()
    # Provide 6 sources and 5 claims to test bottom notes (> 4)
    sources = [
        SimpleNamespace(
            id=f"src-{i}",
            title=f"Araştırma Kaynağı {i}",
            url=f"https://example.org/s{i}",
            connector_id="crossref",
            metadata_json={"year": 2020 + i, "type": "Makale", "research_scope_role": "primary_in_scope"},
        )
        for i in range(1, 7)
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{i}",
            text=f"Doğrulanmış iddia {i}",
            status="supported",
            confidence=0.90 + (i * 0.01),
            audit={"question_relevance": 0.85},
        )
        for i in range(1, 6)
    ]
    evidence_by_claim = {
        "claim-1": [(SimpleNamespace(), sources[0]), (SimpleNamespace(), sources[1])],
        "claim-2": [(SimpleNamespace(), sources[1])],
    }

    inputs["sources"] = sources
    inputs["claims"] = claims
    inputs["reportable_claims"] = claims
    inputs["evidence_by_claim"] = evidence_by_claim
    inputs["figures"] = {
        "16a_research_contribution_landscape.png": png_a,
        "16b_theme_evidence_map.png": png_b,
    }

    # Section 1 has findings, Section 2 does NOT have findings
    sec1 = SynthesisSection(
        title="Tema 1",
        synthesis="Tema 1 sentezi [S01].",
        consensus="Tema 1 konsensus",
        disagreements="",
        implications="Tema 1 çıkarım",
        source_ids=["src-1"],
        claim_ids=["claim-1"],
    )
    sec2 = SynthesisSection(
        title="Tema 2",
        synthesis="Tema 2 sentezi [S02].",
        consensus="",
        disagreements="",
        implications="",
        source_ids=["src-2"],
        claim_ids=["claim-2"],
    )

    inputs["synthesis_package"] = SynthesisPackage(
        executive_summary="Özet [S01].",
        sections=[sec1, sec2],
        cross_study_assessment="Değerlendirme",
        conclusion="Sonuç",
        uncertainty="Belirsizlik",
        study_profiles=[],
        generated_by_llm=True,
        report_mode="standard",
    )

    res = build_presentation_report(**inputs)
    prs = pptx.Presentation(io.BytesIO(res.document))

    # Check that Slide 7 (Findings) was created for sec1, but NOT duplicated for sec2
    findings_headings = [
        shp.text
        for s in prs.slides
        for shp in s.shapes
        if shp.has_text_frame and "Bulgular" in shp.text
    ]
    assert len(findings_headings) == 1
    assert "3.1 Tema 1 — Bulgular" in findings_headings[0]

    # Check Slide 13 / Ek B (Topic Landscape) has pictures replaced
    all_slide_texts = []
    for s in prs.slides:
        for shp in s.shapes:
            if shp.has_text_frame:
                all_slide_texts.append(shp.text)
    deck_str = "\n".join(all_slide_texts)

    # Placeholders should be gone
    assert "[Araştırma katkısı dağılımı]" not in deck_str
    assert "[Tema–kanıt haritası]" not in deck_str

    # Check Ek C bottom note (because sources > 4)
    assert "Araştırmada korunan 6 kaynaktan ilk 4'ü özetlenmiştir" in deck_str

    # Check Ek D bottom note (because claims > 4)
    assert "Raporlanan 5 denetlenmiş iddiadan ilk 4'ü özetlenmiştir" in deck_str

    # Check that Ek D claim sources uses real citations S01, S02 instead of hardcoded S01
    claims_slide = next(
        s for s in prs.slides
        if any(shp.name == "content_heading" and "Denetlenmiş iddia kaydı" in shp.text for shp in s.shapes if shp.has_text_frame)
    )
    tbl = next(shp.table for shp in claims_slide.shapes if shp.has_table)
    # Row 1 is claim-1 which is backed by src-1 (S01) and src-2 (S02)
    c1_sources = tbl.cell(1, 5).text
    assert "S01, S02" in c1_sources


def test_presentation_report_empty_summary_fallback():
    inputs = _minimal_report_inputs()
    inputs["executive_summary"] = ""
    inputs["synthesis_package"] = SynthesisPackage(
        executive_summary="",
        sections=[],
        cross_study_assessment="",
        conclusion="",
        uncertainty="",
        study_profiles=[],
        generated_by_llm=False,
    )
    res = build_presentation_report(**inputs)
    prs = pptx.Presentation(io.BytesIO(res.document))
    slide_3 = prs.slides[2]
    slide_3_text = "\n".join(shp.text for shp in slide_3.shapes if shp.has_text_frame)
    assert "doğrulanmış kanıt eşiğini geçen bir yönetici özeti üretilemedi" in slide_3_text

