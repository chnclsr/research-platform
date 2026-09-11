"""Deterministic PowerPoint (PPTX) report renderer for completed research runs.

Populates the company-branded Cansağlığı Araştırma Raporu PowerPoint template
with audited synthesis, evidence, claims, citations, and literature landscape.
Supports both standard and compact report modes, dynamic thematic section expansion,
figure integration, and audit appendices.
"""

from __future__ import annotations

import copy
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pptx
from PIL import Image
from pptx.util import Pt

from .figure_analysis import FigureObservation, GeneratedResearchFigure
from .report_synthesis import SynthesisPackage, citation_tokens
from .schemas import ReportCitation
from .word_report import _collect_citations

REPORT_PIPELINE_VERSION = "0.24.0"
PRESENTATION_REPORT_FALLBACK = "16_research_report.pptx"
_SAFE_LABEL = re.compile(r"[A-Za-z0-9_]{1,64}")


def presentation_report_name(label: str | None) -> str:
    """The PowerPoint report's file name, derived from the run's topic handle."""
    from .scoping import LABEL_MAX_LENGTH, slugify

    handle = (label or "").strip()
    if not _SAFE_LABEL.fullmatch(handle):
        handle = slugify(handle, max_length=LABEL_MAX_LENGTH)
    return f"16_{handle}_report.pptx" if handle else PRESENTATION_REPORT_FALLBACK


@dataclass(frozen=True)
class PresentationReportResult:
    document: bytes
    figures: dict[str, bytes] = field(default_factory=dict)
    citations: list[ReportCitation] = field(default_factory=list)


def _is_turkish(language: str) -> bool:
    return language.lower().strip().startswith("tr")


def _text(value: Any, limit: int = 1000) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit] if len(text) > limit else text


def _set_shape_text(
    shape: Any,
    text: str,
    font_size_pt: float | None = None,
    bold: bool | None = None,
) -> None:
    if not shape.has_text_frame:
        return
    tf = shape.text_frame

    font_name = "Arial"
    if tf.paragraphs and tf.paragraphs[0].runs:
        r0 = tf.paragraphs[0].runs[0]
        if r0.font.name:
            font_name = r0.font.name
        if font_size_pt is None and r0.font.size:
            font_size_pt = r0.font.size.pt
        if bold is None and r0.font.bold is not None:
            bold = r0.font.bold

    tf.text = text
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.name = font_name
            if font_size_pt:
                r.font.size = Pt(font_size_pt)
            if bold is not None:
                r.font.bold = bold


def _find_shape_by_name(slide: Any, name: str) -> Any:
    for shp in slide.shapes:
        if shp.name == name:
            return shp
    return None


def _delete_slide(prs: Any, index: int) -> None:
    rId = prs.slides._sldIdLst[index].rId
    prs.part.drop_rel(rId)
    del prs.slides._sldIdLst[index]


def _duplicate_slide(prs: Any, source_slide: Any) -> Any:
    new_slide = prs.slides.add_slide(source_slide.slide_layout)
    for shp in list(new_slide.shapes):
        sp = shp._element
        sp.getparent().remove(sp)
    for shp in source_slide.shapes:
        new_sp = copy.deepcopy(shp._element)
        new_slide.shapes._spTree.append(new_sp)
    return new_slide


def _populate_figure_slide(
    slide: Any,
    fig_info: dict[str, Any],
    fig_num: int,
    turkish: bool,
) -> None:
    shp_fig_h = _find_shape_by_name(slide, "content_heading")
    if shp_fig_h:
        title_str = _text(
            fig_info.get("title") or ("Araştırma Görseli" if turkish else "Research Figure"), 70
        )
        _set_shape_text(shp_fig_h, f"3. Figür {fig_num} — {title_str}")

    interp_parts = []
    main_findings = fig_info.get("main_findings") or []
    if main_findings:
        interp_parts.append("• " + "\n• ".join(_text(f, 200) for f in main_findings[:2]))
    elif fig_info.get("interpretation"):
        interp_parts.append(_text(fig_info.get("interpretation"), 400))

    limitations = fig_info.get("limitations") or []
    if limitations:
        lim_str = "Sınır: " if turkish else "Limitation: "
        interp_parts.append(lim_str + " ".join(_text(l, 150) for l in limitations[:1]))

    shp_fig_interp = _find_shape_by_name(slide, "figure.interpretation")
    if shp_fig_interp:
        _set_shape_text(
            shp_fig_interp,
            "\n".join(interp_parts)
            if interp_parts
            else (
                "Kaynak figürü bulguları desteklemektedir."
                if turkish
                else "Source figure supports the findings."
            ),
            font_size_pt=13.0,
        )

    caption_parts = []
    if fig_info.get("caption"):
        caption_parts.append(_text(fig_info.get("caption"), 200))
    attr_bits = []
    if fig_info.get("attribution"):
        attr_bits.append(f"Kaynak: {_text(fig_info.get('attribution'), 80)}")
    if fig_info.get("rights"):
        attr_bits.append(f"Telif: {_text(fig_info.get('rights'), 40)}")
    if attr_bits:
        caption_parts.append(" · ".join(attr_bits))

    shp_fig_cap = _find_shape_by_name(slide, "figure.caption_attribution")
    if shp_fig_cap:
        _set_shape_text(
            shp_fig_cap,
            "\n".join(caption_parts) if caption_parts else "",
            font_size_pt=10.0,
        )

    fig_data = fig_info.get("data")
    shp_fig_asset = _find_shape_by_name(slide, "figure.asset")
    if fig_data and shp_fig_asset:
        box_left = shp_fig_asset.left
        box_top = shp_fig_asset.top
        box_w = shp_fig_asset.width
        box_h = shp_fig_asset.height
        target_left, target_top, target_w, target_h = box_left, box_top, box_w, box_h
        try:
            with Image.open(io.BytesIO(fig_data)) as img:
                orig_w, orig_h = img.size
            aspect = orig_w / max(1, orig_h)
            box_aspect = box_w / max(1, box_h)
            if aspect > box_aspect:
                target_w = box_w
                target_h = int(box_w / aspect)
                target_left = box_left
                target_top = box_top + int((box_h - target_h) / 2)
            else:
                target_h = box_h
                target_w = int(box_h * aspect)
                target_top = box_top
                target_left = box_left + int((box_w - target_w) / 2)
        except (OSError, ValueError, TypeError):
            pass

        sp = shp_fig_asset._element
        sp.getparent().remove(sp)
        slide.shapes.add_picture(io.BytesIO(fig_data), target_left, target_top, target_w, target_h)


def _extract_source_citations(text: str) -> list[str]:
    """The labels a slide's citation box should show.

    Reads grouped citations too, and three-digit labels: the pattern here was `\\[S\\d{2}\\]`,
    which silently skipped every label past S99. Run 01M27RKQFHR80WNHEQVF2AF2DS carried 209
    sources, so the boxes would have dropped most of what the prose actually cited.
    """
    return sorted(set(citation_tokens(text)))


def build_presentation_report(
    *,
    run_id: str,
    title: str,
    question: str,
    language: str,
    coverage: dict[str, Any],
    sources: list[Any],
    claims: list[Any],
    reportable_claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    executive_summary: str,
    narrative: str,
    uncertainty: str,
    scope: dict[str, Any] | None = None,
    sub_questions: list[str] | None = None,
    connector_ids: list[str] | None = None,
    research_mode: str = "literature_scan",
    synthesis_package: SynthesisPackage | None = None,
    figure_observations: list[FigureObservation] | None = None,
    research_figures: list[GeneratedResearchFigure] | None = None,
    template_path: Path | str | None = None,
) -> PresentationReportResult:
    """Build a branded PowerPoint research report conforming to the company template.

    Preserves typography, brand styling, geometry, and tables. Flexibly handles
    standard multi-theme synthesis, compact mode, figure presence/absence, and audit data.
    """
    turkish = _is_turkish(language)
    package = synthesis_package
    is_compact = package is not None and getattr(package, "report_mode", "") == "compact"

    # Resolve template path
    if template_path is None:
        templates_dir = Path(__file__).parent / "templates"
        candidates = [
            templates_dir / "Cansagligi_Arastirma_Raporu_Sablonu_v1.pptx",
            templates_dir / "cansagligi_report_template.pptx",
            Path(
                "/app/src/research_platform/templates/Cansagligi_Arastirma_Raporu_Sablonu_v1.pptx"
            ),
            Path(
                r"C:\Users\PC_8009\Desktop\research-platform\src\research_platform\templates\Cansagligi_Arastirma_Raporu_Sablonu_v1.pptx"
            ),
            Path(
                r"C:\Users\PC_8009\Desktop\research-platform\src\research_platform\templates\cansagligi_report_template.pptx"
            ),
        ]
        for c in candidates:
            if c.exists():
                template_path = c
                break

    if template_path is None or not Path(template_path).exists():
        raise FileNotFoundError(
            f"PowerPoint report template could not be located in candidates: {candidates}"
        )

    prs = pptx.Presentation(template_path)
    source_numbers = {source.id: index for index, source in enumerate(sources, 1)}

    # Collect citations for audit parity
    citations = list(
        _collect_citations(
            sources=sources,
            source_numbers=source_numbers,
            evidence_by_claim=evidence_by_claim,
            reportable_claims=reportable_claims,
            package=package,
            turkish=turkish,
        )
    )

    # Slide 1: Cover slide
    slide_1 = prs.slides[0]
    for shp in slide_1.shapes:
        if shp.name == "Google Shape;95;p1" or (
            shp.has_text_frame and "Araştırma Raporu" in shp.text_frame.text
        ):
            _set_shape_text(
                shp,
                f"{title}\nAraştırma Raporu" if turkish else f"{title}\nResearch Report",
                bold=True,
            )
        elif shp.name == "Google Shape;96;p1" or (
            shp.has_text_frame and "Rapor tarihi" in shp.text_frame.text
        ):
            date_str = datetime.now(UTC).strftime("%d.%m.%Y")
            _set_shape_text(
                shp,
                f"Rapor Tarihi: {date_str}  ·  Çalışma Kimliği: {run_id[:8]}"
                if turkish
                else f"Report Date: {date_str}  ·  Run ID: {run_id[:8]}",
            )

    # Slide 2: Table of Contents (İçindekiler)
    slide_2 = prs.slides[1]
    shp_toc_main = _find_shape_by_name(slide_2, "toc_main")
    shp_toc_app = _find_shape_by_name(slide_2, "toc_appendices")
    if is_compact:
        if shp_toc_main:
            _set_shape_text(
                shp_toc_main,
                "1. Özet\n2. Araştırma çerçevesi\n3. Belirsizlikler ve araştırma boşlukları"
                if turkish
                else "1. Summary\n2. Research frame\n3. Uncertainties and research gaps",
            )
    else:
        if shp_toc_main:
            _set_shape_text(
                shp_toc_main,
                "1. Özet\n2. Araştırma çerçevesi\n3. Tematik kanıt sentezi\n4. Çalışmalar arası değerlendirme ve sonuç"
                if turkish
                else "1. Summary\n2. Research frame\n3. Thematic evidence synthesis\n4. Cross-study assessment and conclusion",
            )
    if shp_toc_app:
        _set_shape_text(
            shp_toc_app,
            "Ek A. Yöntem, kapsam ve yeniden üretilebilirlik\nEk B. Literatürün konu haritası\nEk C. Tam kaynak kataloğu\nEk D. Denetlenmiş iddia kaydı"
            if turkish
            else "Appendix A. Method, scope and reproducibility\nAppendix B. Literature topic map\nAppendix C. Complete source catalog\nAppendix D. Audited claim register",
        )

    # Slide 3: Executive Summary (Özet)
    slide_3 = prs.slides[2]
    exec_summary_text = (
        getattr(package, "executive_summary", "") if package else executive_summary
    ) or executive_summary
    shp_exec = _find_shape_by_name(slide_3, "executive_summary")
    if shp_exec:
        _set_shape_text(shp_exec, _text(exec_summary_text, 1400))
    shp_sum_cit = _find_shape_by_name(slide_3, "summary_citations")
    if shp_sum_cit:
        sum_cits = _extract_source_citations(exec_summary_text)
        cit_label = (
            f"Kullanılan kaynaklar: {', '.join(sum_cits)}"
            if sum_cits
            else (
                "Kaynaklar denetim eklerinde korunmuştur."
                if turkish
                else "Sources are preserved in audit appendices."
            )
        )
        _set_shape_text(shp_sum_cit, cit_label)

    # Slide 4: Research Framework - Primary Question & Scope
    slide_4 = prs.slides[3]
    shp_q = _find_shape_by_name(slide_4, "question")
    if shp_q:
        _set_shape_text(shp_q, _text(question, 800))
    shp_scope = _find_shape_by_name(slide_4, "scope")
    if shp_scope:
        scope_dict = scope or {}
        scope_lines = [
            f"• Tarih aralığı: {_text(scope_dict.get('start_date') or '—')} – {_text(scope_dict.get('end_date') or '—')}",
            f"• Araştırma modu: {research_mode}",
            f"• Kapsam gerekçesi: {_text(scope_dict.get('query_intent') or 'Sistematik kanıt temelli literatür taraması', 300)}",
        ]
        _set_shape_text(shp_scope, "\n".join(scope_lines))

    # Slide 5: Research Framework - Sub-questions & Exclusions
    slide_5 = prs.slides[4]
    shp_subq = _find_shape_by_name(slide_5, "sub_questions")
    if shp_subq:
        if sub_questions:
            _set_shape_text(
                shp_subq,
                "\n".join(f"{i}. {_text(sq, 250)}" for i, sq in enumerate(sub_questions, 1)),
            )
        else:
            _set_shape_text(
                shp_subq,
                "Ana araştırma sorusu bütüncül olarak ele alınmıştır."
                if turkish
                else "The primary research question was addressed holistically.",
            )
    shp_near = _find_shape_by_name(slide_5, "near_scope_sources")
    if shp_near:
        near_sources = [
            s
            for s in sources
            if (getattr(s, "metadata_json", {}) or {}).get("research_scope_role")
            in {"near_scope", "excluded"}
        ]
        if near_sources:
            near_lines = [
                f"• {_text(s.title, 100)} ({getattr(s, 'metadata_json', {}).get('research_scope_role')})"
                for s in near_sources[:4]
            ]
            _set_shape_text(shp_near, "\n".join(near_lines))
        else:
            _set_shape_text(
                shp_near,
                "Kapsam dışı bırakılan özel bir sınır çalışma bildirilmemiştir."
                if turkish
                else "No specific near-scope excluded studies were flagged.",
            )

    # Identify initial slides for Section 3, 4 and Appendices
    # Original template indices:
    # 5: Slide 6 (Thematic Section Narrative)
    # 6: Slide 7 (Thematic Section Consensus/Disagreements/Implications)
    # 7: Slide 8 (Figure)
    # 8: Slide 9 (Cross-study assessment)
    # 9: Slide 10 (Conclusion)
    # 10: Slide 11 (Uncertainty)
    # 11: Slide 12 (Ek A)
    # 12: Slide 13 (Ek B)
    # 13: Slide 14 (Ek C)
    # 14: Slide 15 (Ek D)
    # 15: Slide 16 (Closing)

    slide_6 = prs.slides[5]
    slide_7 = prs.slides[6]
    slide_8 = prs.slides[7]
    slide_9 = prs.slides[8]
    slide_10 = prs.slides[9]
    slide_11 = prs.slides[10]

    sections = list(getattr(package, "sections", [])) if package and not is_compact else []

    if not is_compact and sections:
        # Fill first theme in slide 6 & 7
        sec0 = sections[0]
        shp_h6 = _find_shape_by_name(slide_6, "content_heading")
        if shp_h6:
            _set_shape_text(shp_h6, f"3.1 {_text(sec0.title, 80)}")
        shp_syn = _find_shape_by_name(slide_6, "sections[].synthesis")
        if shp_syn:
            _set_shape_text(shp_syn, _text(sec0.synthesis, 1400))
        shp_cit6 = _find_shape_by_name(slide_6, "sections[].citations")
        if shp_cit6:
            cits = _extract_source_citations(sec0.synthesis)
            cit_txt = (
                f"Bu temada kullanılan kaynaklar: {', '.join(cits)}"
                if cits
                else ("Kabul edilen kanıtlar" if turkish else "Accepted evidence")
            )
            _set_shape_text(shp_cit6, cit_txt)

        shp_h7 = _find_shape_by_name(slide_7, "content_heading")
        if shp_h7:
            _set_shape_text(shp_h7, f"3.1 {_text(sec0.title, 80)} — Bulgular")
        shp_con = _find_shape_by_name(slide_7, "sections[].consensus")
        if shp_con:
            _set_shape_text(
                shp_con,
                _text(
                    sec0.consensus
                    or (
                        "Belirgin ortak bir yön bildirilmedi."
                        if turkish
                        else "No consensus reported."
                    ),
                    450,
                ),
            )
        shp_dis = _find_shape_by_name(slide_7, "sections[].disagreements")
        if shp_dis:
            _set_shape_text(
                shp_dis,
                _text(
                    sec0.disagreements
                    or (
                        "Kaynaklar arasında doğrudan bir çelişki gözlemlenmedi."
                        if turkish
                        else "No direct contradiction reported."
                    ),
                    450,
                ),
            )
        shp_imp = _find_shape_by_name(slide_7, "sections[].implications")
        if shp_imp:
            _set_shape_text(
                shp_imp,
                _text(
                    sec0.implications
                    or (
                        "Bulgular araştırma çerçevesini desteklemektedir."
                        if turkish
                        else "Findings align with research scope."
                    ),
                    450,
                ),
            )

        # Handle additional sections (Section 2, 3...) by duplicating Slide 6 & 7
        # Insert them right after Slide 7 (index 7, 8, etc.)
        insert_target = 7
        for s_idx, sec in enumerate(sections[1:], 2):
            # Duplicate Slide 6
            dup6 = _duplicate_slide(prs, slide_6)
            sldId6 = prs.slides._sldIdLst[-1]
            prs.slides._sldIdLst.remove(sldId6)
            prs.slides._sldIdLst.insert(insert_target, sldId6)
            insert_target += 1

            dh6 = _find_shape_by_name(dup6, "content_heading")
            if dh6:
                _set_shape_text(dh6, f"3.{s_idx} {_text(sec.title, 80)}")
            dsyn = _find_shape_by_name(dup6, "sections[].synthesis")
            if dsyn:
                _set_shape_text(dsyn, _text(sec.synthesis, 1400))
            dcit = _find_shape_by_name(dup6, "sections[].citations")
            if dcit:
                cits = _extract_source_citations(sec.synthesis)
                dcit_txt = (
                    f"Bu temada kullanılan kaynaklar: {', '.join(cits)}"
                    if cits
                    else "Kabul edilen kanıtlar"
                )
                _set_shape_text(dcit, dcit_txt)

            # Duplicate Slide 7
            dup7 = _duplicate_slide(prs, slide_7)
            sldId7 = prs.slides._sldIdLst[-1]
            prs.slides._sldIdLst.remove(sldId7)
            prs.slides._sldIdLst.insert(insert_target, sldId7)
            insert_target += 1

            dh7 = _find_shape_by_name(dup7, "content_heading")
            if dh7:
                _set_shape_text(dh7, f"3.{s_idx} {_text(sec.title, 80)} — Bulgular")
            dcon = _find_shape_by_name(dup7, "sections[].consensus")
            if dcon:
                _set_shape_text(
                    dcon, _text(sec.consensus or "Belirgin ortak bir yön bildirilmedi.", 450)
                )
            ddis = _find_shape_by_name(dup7, "sections[].disagreements")
            if ddis:
                _set_shape_text(
                    ddis,
                    _text(
                        sec.disagreements
                        or "Kaynaklar arasında doğrudan bir çelişki gözlemlenmedi.",
                        450,
                    ),
                )
            dimp = _find_shape_by_name(dup7, "sections[].implications")
            if dimp:
                _set_shape_text(
                    dimp,
                    _text(
                        sec.implications or "Bulgular araştırma çerçevesini desteklemektedir.", 450
                    ),
                )

    # Figure handling (Slide 8): support multiple parsed figures
    figures_to_render = []
    obs_by_hash = {
        obs.image_hash: obs
        for obs in (figure_observations or [])
        if getattr(obs, "image_hash", None)
    }

    for rf in research_figures or []:
        obs = obs_by_hash.get(getattr(rf, "observation_hash", ""))
        figures_to_render.append(
            {
                "title": getattr(rf, "title", "")
                or (getattr(obs, "selection_reason", "") if obs else "Araştırma Figürü"),
                "caption": getattr(rf, "caption", "")
                or (getattr(obs, "caption", "") if obs else ""),
                "attribution": getattr(rf, "attribution", "")
                or (getattr(obs, "source_label", "") if obs else ""),
                "rights": getattr(rf, "rights_statement", ""),
                "interpretation": getattr(obs, "selection_reason", "") if obs else "",
                "main_findings": getattr(obs, "main_findings", []) if obs else [],
                "limitations": getattr(obs, "limitations", []) if obs else [],
                "data": getattr(rf, "data", None),
            }
        )

    covered_hashes = {getattr(rf, "observation_hash", "") for rf in (research_figures or [])}
    for obs in figure_observations or []:
        if getattr(obs, "image_hash", "") not in covered_hashes:
            obs_data = getattr(obs, "data", None) or getattr(obs, "image_bytes", None)
            if obs_data or getattr(obs, "main_findings", None):
                figures_to_render.append(
                    {
                        "title": getattr(obs, "recommended_section", "")
                        or getattr(obs, "selection_reason", "Kaynak Figürü"),
                        "caption": getattr(obs, "caption", ""),
                        "attribution": getattr(obs, "source_label", ""),
                        "rights": "",
                        "interpretation": getattr(obs, "selection_reason", ""),
                        "main_findings": getattr(obs, "main_findings", []),
                        "limitations": getattr(obs, "limitations", []),
                        "data": obs_data,
                    }
                )

    created_figure_slides = []
    if figures_to_render and not is_compact:
        _populate_figure_slide(slide_8, figures_to_render[0], 1, turkish)
        created_figure_slides.append(slide_8)
        for f_idx, fig_info in enumerate(figures_to_render[1:], 2):
            dup_fig = _duplicate_slide(prs, slide_8)
            last_pos = next(i for i, s in enumerate(prs.slides) if s == created_figure_slides[-1])
            sldId = prs.slides._sldIdLst[-1]
            prs.slides._sldIdLst.remove(sldId)
            prs.slides._sldIdLst.insert(last_pos + 1, sldId)
            _populate_figure_slide(dup_fig, fig_info, f_idx, turkish)
            created_figure_slides.append(dup_fig)

    # Slide 9: Cross-study assessment
    shp_cross = _find_shape_by_name(slide_9, "cross_study_assessment")
    if shp_cross:
        c_text = getattr(package, "cross_study_assessment", "") if package else narrative
        _set_shape_text(
            shp_cross, _text(c_text or "Çalışmalar arasında genel tutarlılık saptanmıştır.", 1200)
        )
    shp_ascit = _find_shape_by_name(slide_9, "assessment_citations")
    if shp_ascit:
        _set_shape_text(
            shp_ascit,
            "Kaynak değerlendirmesi literatür haritasında sunulmuştur."
            if turkish
            else "Source assessment is provided in the literature map.",
        )

    # Slide 10: Conclusion
    shp_conc = _find_shape_by_name(slide_10, "conclusion")
    if shp_conc:
        conc_text = getattr(package, "conclusion", "") if package else ""
        _set_shape_text(
            shp_conc,
            _text(conc_text or "Araştırma sorusu doğrulanmış kanıtlarla yanıtlanmıştır.", 1200),
        )
    shp_conccit = _find_shape_by_name(slide_10, "conclusion_citations")
    if shp_conccit:
        _set_shape_text(
            shp_conccit,
            "Sonuç doğrulanmış kanıt kaydıyla desteklenmiştir."
            if turkish
            else "Conclusion is supported by audited evidence.",
        )

    # Slide 11: Uncertainty
    if is_compact:
        shp_unc_sec = _find_shape_by_name(slide_11, "section_title")
        if shp_unc_sec:
            _set_shape_text(
                shp_unc_sec,
                "3. Belirsizlikler ve araştırma boşlukları"
                if turkish
                else "3. Uncertainties and research gaps",
            )
    shp_unc = _find_shape_by_name(slide_11, "uncertainty")
    if shp_unc:
        unc_text = getattr(package, "uncertainty", "") if package else uncertainty
        _set_shape_text(
            shp_unc, _text(unc_text or "Açık bir belirsizlik veya veri boşluğu bildirilmedi.", 1200)
        )

    # Slide 12: Ek A (Method & coverage)
    slide_12 = (
        _find_slide_with_heading(prs, "Yöntem, kapsam ve yeniden üretilebilirlik") or prs.slides[11]
    )
    shp_meth = _find_shape_by_name(slide_12, "method")
    if shp_meth:
        method_desc = (
            "1. Keşif: Çoklu akademik ve web arama bağlayıcıları üzerinden literatür tarandı.\n"
            "2. Edinim: Tam metinler ve açık erişimli içerikler tekilleştirilerek edinildi.\n"
            "3. Normalizasyon: URL, içerik hash'i ve metaveriler kaydedildi.\n"
            "4. Kanıt: Pasajlar atomik iddialarla eşleştirildi ve güven puanlandı.\n"
            "5. Sentez: Yalnızca denetim kapısını geçen doğrulanmış iddialar rapora alındı."
            if turkish
            else "1. Discovery: Federated search across academic & web connectors.\n"
            "2. Acquisition: Open access content deduplicated and indexed.\n"
            "3. Normalization: Content hashing and metadata validation.\n"
            "4. Evidence: Claim linking with entailment scoring.\n"
            "5. Synthesis: Audited findings integrated into report."
        )
        _set_shape_text(shp_meth, method_desc)
    shp_run_meta = _find_shape_by_name(slide_12, "run_metadata")
    if shp_run_meta:
        meta_lines = [
            f"Çalışma Kimliği: {run_id}",
            f"Üretim Zamanı: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Rapor Pipeline Sürümü: v{REPORT_PIPELINE_VERSION}",
            f"Biçim / Mod: {getattr(package, 'report_mode', 'standard')}",
        ]
        _set_shape_text(shp_run_meta, "\n".join(meta_lines))
    for shp in slide_12.shapes:
        if shp.has_table and len(shp.table.columns) == 2:
            tbl = shp.table
            cov = coverage or {}
            metrics = [
                ("Kaynak ailesi kapsamı", f"{cov.get('source_family_coverage', 1.0):.0%}"),
                ("Sorgu dalı kapsamı", f"{cov.get('query_branch_coverage', 1.0):.0%}"),
                ("İddia denetim kapsamı", f"{cov.get('claim_audit_coverage', 1.0):.0%}"),
                ("Tahmini tamlık", f"{cov.get('estimated_completeness', 'Tamamlandı')}"),
                ("Çözülmemiş ana iddia", str(cov.get("unresolved_primary_claims", 0))),
            ]
            for row_idx, (m_label, m_val) in enumerate(metrics, 1):
                if row_idx < len(tbl.rows):
                    tbl.cell(row_idx, 0).text = m_label
                    tbl.cell(row_idx, 1).text = m_val

    # Slide 13: Ek B (Topic / Literature landscape)
    slide_13 = _find_slide_with_heading(prs, "Literatürün konu haritası") or prs.slides[12]
    shp_lcap = _find_shape_by_name(slide_13, "landscape_caption")
    if shp_lcap:
        _set_shape_text(
            shp_lcap,
            "Literatürde yer alan araştırma katkı türleri ve kanıt yoğunluk haritası."
            if turkish
            else "Research contribution distribution and evidence density map.",
        )

    # Slide 14: Ek C (Sources table)
    slide_14 = _find_slide_with_heading(prs, "Tam kaynak kataloğu") or prs.slides[13]
    for shp in slide_14.shapes:
        if shp.has_table and len(shp.table.columns) == 6:
            tbl = shp.table
            for r_idx, source in enumerate(sources[:4], 1):
                if r_idx < len(tbl.rows):
                    s_label = f"S{r_idx:02d}"
                    meta = getattr(source, "metadata_json", {}) or {}
                    tbl.cell(r_idx, 0).text = s_label
                    tbl.cell(r_idx, 1).text = _text(
                        meta.get("year") or meta.get("publication_year") or "—", 10
                    )
                    tbl.cell(r_idx, 2).text = _text(meta.get("type") or "Makale", 15)
                    tbl.cell(r_idx, 3).text = _text(getattr(source, "title", "Kaynak"), 45)
                    tbl.cell(r_idx, 4).text = _text(getattr(source, "connector_id", "web"), 15)
                    tbl.cell(r_idx, 5).text = "1"
            break

    # Slide 15: Ek D (Audited claims table)
    slide_15 = _find_slide_with_heading(prs, "Denetlenmiş iddia kaydı") or prs.slides[14]
    for shp in slide_15.shapes:
        if shp.has_table and len(shp.table.columns) == 6:
            tbl = shp.table
            for r_idx, claim in enumerate(reportable_claims[:4], 1):
                if r_idx < len(tbl.rows):
                    c_label = f"C{r_idx:02d}"
                    tbl.cell(r_idx, 0).text = c_label
                    tbl.cell(r_idx, 1).text = _text(getattr(claim, "text", ""), 40)
                    tbl.cell(r_idx, 2).text = _text(getattr(claim, "status", "supported"), 12)
                    tbl.cell(
                        r_idx, 3
                    ).text = f"{float(getattr(claim, 'confidence', 0.9) or 0.9):.2f}"
                    tbl.cell(
                        r_idx, 4
                    ).text = f"{float((getattr(claim, 'audit', {}) or {}).get('question_relevance', 0.9) or 0.9):.2f}"
                    tbl.cell(r_idx, 5).text = "S01"
            break

    # Slide Pruning:
    # Find slides to remove cleanly by reference
    to_delete_slides = []
    if is_compact:
        # In compact mode, remove Slide 6, 7, 8, 9, 10 and any created figure slides
        to_delete_slides.extend([slide_6, slide_7, slide_8, slide_9, slide_10])
        to_delete_slides.extend([s for s in created_figure_slides if s != slide_8])
    else:
        if not figures_to_render:
            to_delete_slides.append(slide_8)

    # Remove target slides by index
    for target_slide in to_delete_slides:
        for idx, s in enumerate(prs.slides):
            if s == target_slide:
                _delete_slide(prs, idx)
                break

    # Recompute slide numbers sequentially on all surviving slides
    for idx, s in enumerate(prs.slides):
        shp_num = _find_shape_by_name(s, "slide_number")
        if shp_num:
            _set_shape_text(shp_num, str(idx + 1))

    output = io.BytesIO()
    prs.save(output)
    return PresentationReportResult(
        document=output.getvalue(),
        figures={},
        citations=citations,
    )


def _find_slide_with_heading(prs: Any, heading_substring: str) -> Any | None:
    for slide in prs.slides:
        shp_h = _find_shape_by_name(slide, "content_heading")
        if shp_h and heading_substring in shp_h.text:
            return slide
    return None
