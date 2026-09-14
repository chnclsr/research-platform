"""Deterministic PowerPoint (PPTX) report renderer for completed research runs.

Populates the company-branded Cansağlığı Araştırma Raporu PowerPoint template
with audited synthesis, evidence, claims, citations, and literature landscape.
Supports both standard and compact report modes, dynamic thematic section expansion,
figure integration, and audit appendices.
"""

from __future__ import annotations

import copy
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pptx
from PIL import Image
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches, Pt

from .figure_analysis import FigureObservation, GeneratedResearchFigure
from .report_synthesis import _REPORT_WITHOUT_SUMMARY, SynthesisPackage, citation_tokens
from .schemas import ReportCitation
from .word_report import _collect_citations, _format_date

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


def _text(value: Any, limit: int = 10000) -> str:
    """Return string representation, preserving full text within a generous limit."""
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit] if len(text) > limit else text


def _estimate_text_height(
    text: str,
    width_pt: float,
    font_size_pt: float,
    line_spacing: float = 1.20,
    paragraph_space_pt: float = 3.0,
) -> float:
    """Estimate rendered height of text in points for a given width and font size."""
    if not text:
        return 0.0
    # Average character width for Arial/Calibri is ~0.53 * font_size
    char_width_pt = font_size_pt * 0.53
    # Usable width after internal text frame margins (default ~14.4 pt total)
    usable_width = max(40.0, width_pt - 14.4)
    chars_per_line = max(10.0, usable_width / char_width_pt)

    paragraphs = text.split("\n")
    total_lines = 0
    for p in paragraphs:
        p_len = len(p)
        if p_len == 0:
            total_lines += 1
        else:
            # 1.08 safety multiplier for word wrapping
            lines_in_p = max(1, math.ceil((p_len * 1.08) / chars_per_line))
            total_lines += lines_in_p

    line_h = font_size_pt * line_spacing
    return (total_lines * line_h) + (max(0, len(paragraphs) - 1) * paragraph_space_pt)


def _fit_font_size(
    text: str,
    width_pt: float,
    height_pt: float,
    max_font_pt: float = 18.0,
    min_font_pt: float = 8.0,
) -> float:
    """Find the optimal font size that fits text comfortably within width and height.

    Steadily steps down font size so that the entire text is preserved without truncation.
    """
    if not text:
        return max_font_pt
    # Target 88% of usable height for safe visual margins
    usable_height = max(20.0, height_pt - 8.0)
    target_h = usable_height * 0.88

    candidate = max_font_pt
    while candidate > min_font_pt:
        h = _estimate_text_height(text, width_pt, candidate)
        if h <= target_h:
            return candidate
        candidate -= 0.5
    return min_font_pt


def _set_shape_text(
    shape: Any,
    text: str,
    font_size_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    max_font_pt: float = 18.0,
    min_font_pt: float = 8.0,
    auto_fit: bool = True,
) -> None:
    """Assign text to shape with word wrap, dynamic font fitting, and native auto-size."""
    if not shape.has_text_frame:
        return
    tf = shape.text_frame
    tf.word_wrap = True

    font_name = "Arial"
    if tf.paragraphs and tf.paragraphs[0].runs:
        r0 = tf.paragraphs[0].runs[0]
        if r0.font.name:
            font_name = r0.font.name
        if font_size_pt is None and r0.font.size:
            max_font_pt = min(max_font_pt, r0.font.size.pt)
        if bold is None and r0.font.bold is not None:
            bold = r0.font.bold

    if font_size_pt is None and auto_fit:
        w_pt = shape.width.pt if shape.width else 600.0
        h_pt = shape.height.pt if shape.height else 200.0
        font_size_pt = _fit_font_size(
            text, w_pt, h_pt, max_font_pt=max_font_pt, min_font_pt=min_font_pt
        )
    elif font_size_pt is None:
        font_size_pt = max_font_pt

    tf.text = text
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass

    for p in tf.paragraphs:
        p.space_after = Pt(max(2.0, font_size_pt * 0.25))
        for r in p.runs:
            r.font.name = font_name
            if font_size_pt:
                r.font.size = Pt(font_size_pt)
            if bold is not None:
                r.font.bold = bold
            if italic is not None:
                r.font.italic = italic


def _set_cell_text(
    cell: Any,
    text: str,
    font_size_pt: float = 10.0,
    bold: bool = False,
    font_name: str = "Arial",
) -> None:
    """Format table cell with word wrap, compact margins, and explicit font size."""
    cell.text = text
    tf = cell.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(4)
    tf.margin_right = Pt(4)
    tf.margin_top = Pt(2)
    tf.margin_bottom = Pt(2)
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.name = font_name
            r.font.size = Pt(font_size_pt)
            r.font.bold = bold


def _claim_sources(
    claim_id: str,
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    source_numbers: dict[Any, int],
) -> list[int]:
    """Return ordered source numbers that back a given claim."""
    numbers: list[int] = []
    for _, source in evidence_by_claim.get(str(claim_id), []):
        number = source_numbers.get(source.id)
        if number is not None and number not in numbers:
            numbers.append(number)
    return numbers


def _source_evidence_counts(
    sources: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
) -> dict[str, int]:
    """Count how many claims each source supports."""
    counts: dict[str, int] = {str(s.id): 0 for s in sources}
    for links in evidence_by_claim.values():
        seen: set[str] = set()
        for _, source in links:
            s_id = str(source.id)
            if s_id not in seen:
                counts[s_id] = counts.get(s_id, 0) + 1
                seen.add(s_id)
    return counts


def _replace_shape_with_picture(slide: Any, target_shape: Any, img_bytes: bytes) -> Any | None:
    """Replace a placeholder shape with a picture fitting inside target bounds while preserving aspect ratio."""
    if not img_bytes:
        return None
    box_left = target_shape.left
    box_top = target_shape.top
    box_w = target_shape.width
    box_h = target_shape.height
    t_left, t_top, t_w, t_h = box_left, box_top, box_w, box_h
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            orig_w, orig_h = img.size
        aspect = orig_w / max(1, orig_h)
        box_aspect = box_w / max(1, box_h)
        if aspect > box_aspect:
            t_w = box_w
            t_h = int(box_w / aspect)
            t_left = box_left
            t_top = box_top + int((box_h - t_h) / 2)
        else:
            t_h = box_h
            t_w = int(box_h * aspect)
            t_top = box_top
            t_left = box_left + int((box_w - t_w) / 2)
    except (OSError, ValueError, TypeError):
        pass

    sp = target_shape._element
    sp.getparent().remove(sp)
    return slide.shapes.add_picture(io.BytesIO(img_bytes), t_left, t_top, t_w, t_h)


def _add_slide_bottom_note(slide: Any, text: str) -> None:
    """Add or update a small unobtrusive footnote below tables on appendix slides."""
    existing = _find_shape_by_name(slide, "table_footnote")
    if existing:
        _set_shape_text(existing, text, font_size_pt=9.5, italic=True)
        return
    tx_box = slide.shapes.add_textbox(Inches(0.5), Inches(5.60), Inches(11.4), Inches(0.4))
    tx_box.name = "table_footnote"
    _set_shape_text(tx_box, text, font_size_pt=9.5, italic=True)


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


def _format_findings_slide(
    slide: Any,
    consensus_text: str,
    disagreements_text: str,
    implications_text: str,
    turkish: bool,
) -> None:
    """Layout the three thematic findings blocks with dynamic auto-fit and non-overlapping vertical slots."""
    shp_con = _find_shape_by_name(slide, "sections[].consensus")
    shp_dis = _find_shape_by_name(slide, "sections[].disagreements")
    shp_imp = _find_shape_by_name(slide, "sections[].implications")
    lbl_con = _find_shape_by_name(slide, "label_consensus")
    lbl_dis = _find_shape_by_name(slide, "label_disagreements")
    lbl_imp = _find_shape_by_name(slide, "label_implications")

    # Available vertical range: Top = 2.20 in to 6.65 in (4.45 in total)
    # 3 rows of 1.35 in height with 0.15 in gap
    row_height = Inches(1.35)
    y1 = Inches(2.20)
    y2 = Inches(3.70)
    y3 = Inches(5.20)

    con_fallback = "Bu tema için ortak bir yön bildirilmedi." if turkish else "No consensus reported."
    dis_fallback = (
        "Kaynaklar arasında doğrudan bir çelişki bildirilmedi."
        if turkish
        else "No direct contradiction reported."
    )
    imp_fallback = (
        "Bu tema için özel bir araştırma çıkarımı belirtilmedi."
        if turkish
        else "No specific research implication reported."
    )

    if lbl_con:
        lbl_con.top = y1
        lbl_con.height = row_height
        _set_shape_text(lbl_con, lbl_con.text_frame.text, font_size_pt=14.0, bold=True, auto_fit=False)
    if shp_con:
        shp_con.top = y1
        shp_con.height = row_height
        _set_shape_text(
            shp_con,
            _text(consensus_text) or con_fallback,
            max_font_pt=14.0,
            min_font_pt=8.5,
        )

    if lbl_dis:
        lbl_dis.top = y2
        lbl_dis.height = row_height
        _set_shape_text(lbl_dis, lbl_dis.text_frame.text, font_size_pt=14.0, bold=True, auto_fit=False)
    if shp_dis:
        shp_dis.top = y2
        shp_dis.height = row_height
        _set_shape_text(
            shp_dis,
            _text(disagreements_text) or dis_fallback,
            max_font_pt=14.0,
            min_font_pt=8.5,
        )

    if lbl_imp:
        lbl_imp.top = y3
        lbl_imp.height = row_height
        _set_shape_text(lbl_imp, lbl_imp.text_frame.text, font_size_pt=14.0, bold=True, auto_fit=False)
    if shp_imp:
        shp_imp.top = y3
        shp_imp.height = row_height
        _set_shape_text(
            shp_imp,
            _text(implications_text) or imp_fallback,
            max_font_pt=14.0,
            min_font_pt=8.5,
        )


def _populate_figure_slide(
    slide: Any,
    fig_info: dict[str, Any],
    fig_num: int,
    turkish: bool,
) -> None:
    shp_fig_h = _find_shape_by_name(slide, "content_heading")
    if shp_fig_h:
        raw_title = str(fig_info.get("title") or "").strip()
        if raw_title.lower() in ("şekil", "sekil", "figure", "figür", ""):
            raw_title = str(fig_info.get("recommended_section") or fig_info.get("selection_reason") or "").strip()
        if not raw_title:
            raw_title = "Araştırma Görseli" if turkish else "Research Figure"
        title_str = _text(raw_title, 130)
        _set_shape_text(shp_fig_h, f"3. Figür {fig_num} — {title_str}", bold=True, max_font_pt=22.0, min_font_pt=13.0)

    interp_parts = []
    main_findings = fig_info.get("main_findings") or []
    if main_findings:
        interp_parts.append("• " + "\n• ".join(_text(f, 300) for f in main_findings[:2]))
    elif fig_info.get("interpretation"):
        interp_parts.append(_text(fig_info.get("interpretation"), 600))

    limitations = fig_info.get("limitations") or []
    if limitations:
        lim_str = "Sınır: " if turkish else "Limitation: "
        interp_parts.append(lim_str + " ".join(_text(l, 200) for l in limitations[:1]))

    shp_fig_interp = _find_shape_by_name(slide, "figure.interpretation")
    if shp_fig_interp:
        shp_fig_interp.height = Inches(2.70)
        _set_shape_text(
            shp_fig_interp,
            "\n".join(interp_parts)
            if interp_parts
            else (
                "Kaynak figürü bulguları desteklemektedir."
                if turkish
                else "Source figure supports the findings."
            ),
            max_font_pt=13.0,
            min_font_pt=8.5,
        )

    caption_parts = []
    if fig_info.get("caption"):
        caption_parts.append(_text(fig_info.get("caption"), 300))
    attr_bits = []
    if fig_info.get("attribution"):
        attr_str = _text(fig_info.get("attribution"), 120)
        prefix = ("Kaynak: " if turkish else "Source: ") if not attr_str.lower().startswith(("kaynak:", "source:")) else ""
        attr_bits.append(f"{prefix}{attr_str}")
    if fig_info.get("rights"):
        rights_str = _text(fig_info.get("rights"), 60)
        prefix = ("Telif: " if turkish else "Rights: ") if not rights_str.lower().startswith(("telif:", "rights:")) else ""
        attr_bits.append(f"{prefix}{rights_str}")
    if attr_bits:
        caption_parts.append(" · ".join(attr_bits))

    shp_fig_cap = _find_shape_by_name(slide, "figure.caption_attribution")
    if shp_fig_cap:
        shp_fig_cap.top = Inches(6.20)
        shp_fig_cap.height = Inches(0.60)
        _set_shape_text(
            shp_fig_cap,
            "\n".join(caption_parts) if caption_parts else "",
            font_size_pt=10.0,
        )

    fig_data = fig_info.get("data")
    shp_fig_asset = _find_shape_by_name(slide, "figure.asset")
    if fig_data and shp_fig_asset:
        _replace_shape_with_picture(slide, shp_fig_asset, fig_data)


def _section_text(section: Any) -> str:
    """A theme's prose for its slide, headed by the reader note when it carries one."""
    note = str(getattr(section, "reader_note", "") or "").strip()
    synthesis = str(getattr(section, "synthesis", "") or "")
    return f"{note}\n\n{synthesis}" if note else synthesis


def _extract_source_citations(text: str) -> list[str]:
    """The labels a slide's citation box should show."""
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
    figures: dict[str, bytes] | None = None,
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
    evidence_counts = _source_evidence_counts(sources, evidence_by_claim)

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
                max_font_pt=32.0,
                min_font_pt=18.0,
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
                font_size_pt=11.0,
            )

    # Slide 2: Table of Contents (İçindekiler)
    slide_2 = prs.slides[1]
    shp_toc_main = _find_shape_by_name(slide_2, "toc_main")
    shp_toc_app = _find_shape_by_name(slide_2, "toc_appendices")
    sections = list(getattr(package, "sections", [])) if package and not is_compact else []
    if is_compact:
        if shp_toc_main:
            _set_shape_text(
                shp_toc_main,
                "1. Özet\n2. Araştırma çerçevesi\n3. Belirsizlikler ve araştırma boşlukları"
                if turkish
                else "1. Summary\n2. Research frame\n3. Uncertainties and research gaps",
                font_size_pt=18.0,
            )
    else:
        if shp_toc_main:
            main_lines = [
                "1. Özet" if turkish else "1. Summary",
                "2. Araştırma çerçevesi" if turkish else "2. Research frame",
                "3. Tematik kanıt sentezi" if turkish else "3. Thematic evidence synthesis",
            ]
            for s_idx, sec in enumerate(sections[:5], 1):
                main_lines.append(f"   • 3.{s_idx} {_text(sec.title, 42)}")
            main_lines.append("4. Değerlendirme ve sonuç" if turkish else "4. Assessment and conclusion")
            _set_shape_text(
                shp_toc_main,
                "\n".join(main_lines),
                max_font_pt=16.0,
                min_font_pt=10.5,
            )
    if shp_toc_app:
        _set_shape_text(
            shp_toc_app,
            "Ek A. Yöntem, kapsam ve yeniden üretilebilirlik\nEk B. Literatürün konu haritası\nEk C. Tam kaynak kataloğu\nEk D. Denetlenmiş iddia kaydı"
            if turkish
            else "Appendix A. Method, scope and reproducibility\nAppendix B. Literature topic map\nAppendix C. Complete source catalog\nAppendix D. Audited claim register",
            font_size_pt=18.0,
        )

    # Slide 3: Executive Summary (Özet)
    slide_3 = prs.slides[2]
    exec_summary_text = (
        getattr(package, "executive_summary", "") if package else executive_summary
    ) or executive_summary
    if not exec_summary_text or not exec_summary_text.strip():
        # The synthesis layer's own wording, so every surface says the same plain thing and
        # none of them gives the reader a reason the run did not establish.
        exec_summary_text = _REPORT_WITHOUT_SUMMARY[turkish]
    shp_exec = _find_shape_by_name(slide_3, "executive_summary")
    if shp_exec:
        shp_exec.top = Inches(2.24)
        shp_exec.height = Inches(3.70)
        _set_shape_text(shp_exec, _text(exec_summary_text), max_font_pt=16.0, min_font_pt=8.5)
    shp_sum_cit = _find_shape_by_name(slide_3, "summary_citations")
    if shp_sum_cit:
        shp_sum_cit.top = Inches(6.20)
        shp_sum_cit.height = Inches(0.55)
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
        _set_shape_text(shp_sum_cit, cit_label, font_size_pt=11.0)

    # Slide 4: Research Framework - Primary Question & Scope
    slide_4 = prs.slides[3]
    shp_q = _find_shape_by_name(slide_4, "question")
    if shp_q:
        shp_q.top = Inches(2.19)
        shp_q.height = Inches(1.30)
        _set_shape_text(shp_q, _text(question), max_font_pt=18.0, min_font_pt=11.0)
    shp_scopelbl = _find_shape_by_name(slide_4, "scope_label")
    if shp_scopelbl:
        shp_scopelbl.top = Inches(3.65)
    shp_scope = _find_shape_by_name(slide_4, "scope")
    if shp_scope:
        shp_scope.top = Inches(4.15)
        shp_scope.height = Inches(2.30)
        scope_dict = scope or {}
        start_fmt = _format_date(scope_dict.get('start_date'))
        end_fmt = _format_date(scope_dict.get('end_date'))
        date_range_str = f"{start_fmt} – {end_fmt}"
        scope_lines = [
            f"• Tarih aralığı: {date_range_str}" if turkish else f"• Date range: {date_range_str}",
            f"• Araştırma modu: {research_mode}" if turkish else f"• Research mode: {research_mode}",
            f"• Kapsam gerekçesi: {_text(scope_dict.get('query_intent') or ('Sistematik kanıt temelli literatür taraması' if turkish else 'Systematic evidence-based literature scan'))}",
        ]
        _set_shape_text(shp_scope, "\n".join(scope_lines), max_font_pt=15.0, min_font_pt=10.0)

    # Slide 5: Research Framework - Sub-questions & Exclusions
    slide_5 = prs.slides[4]
    shp_subq = _find_shape_by_name(slide_5, "sub_questions")
    if shp_subq:
        shp_subq.top = Inches(2.19)
        shp_subq.height = Inches(4.20)
        if sub_questions:
            _set_shape_text(
                shp_subq,
                "\n".join(f"{i}. {_text(sq)}" for i, sq in enumerate(sub_questions, 1)),
                max_font_pt=15.0,
                min_font_pt=9.5,
            )
        else:
            _set_shape_text(
                shp_subq,
                "Ana araştırma sorusu bütüncül olarak ele alınmıştır."
                if turkish
                else "The primary research question was addressed holistically.",
                max_font_pt=15.0,
                min_font_pt=11.0,
            )
    shp_near = _find_shape_by_name(slide_5, "near_scope_sources")
    if shp_near:
        shp_near.top = Inches(3.10)
        shp_near.height = Inches(3.30)
        near_sources = [
            s
            for s in sources
            if (getattr(s, "metadata_json", {}) or {}).get("research_scope_role")
            in {"near_scope", "excluded"}
        ]
        if near_sources:
            near_lines = [
                f"• {_text(s.title)} ({getattr(s, 'metadata_json', {}).get('research_scope_role')})"
                for s in near_sources[:5]
            ]
            _set_shape_text(shp_near, "\n".join(near_lines), max_font_pt=13.0, min_font_pt=9.0)
        else:
            _set_shape_text(
                shp_near,
                "Kapsam dışı bırakılan özel bir sınır çalışma bildirilmemiştir."
                if turkish
                else "No specific near-scope excluded studies were flagged.",
                max_font_pt=13.0,
                min_font_pt=10.0,
            )

    # Identify initial slides for Section 3, 4 and Appendices
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
            _set_shape_text(shp_h6, f"3.1 {_text(sec0.title, 80)}", bold=True, font_size_pt=24.0)
        shp_syn = _find_shape_by_name(slide_6, "sections[].synthesis")
        if shp_syn:
            shp_syn.top = Inches(2.24)
            shp_syn.height = Inches(3.70)
            _set_shape_text(shp_syn, _text(_section_text(sec0)), max_font_pt=16.0, min_font_pt=8.5)
        shp_cit6 = _find_shape_by_name(slide_6, "sections[].citations")
        if shp_cit6:
            shp_cit6.top = Inches(6.20)
            shp_cit6.height = Inches(0.55)
            cits = _extract_source_citations(sec0.synthesis)
            cit_txt = (
                f"Bu temada kullanılan kaynaklar: {', '.join(cits)}"
                if cits
                else ("Kabul edilen kanıtlar" if turkish else "Accepted evidence")
            )
            _set_shape_text(shp_cit6, cit_txt, font_size_pt=11.0)

        shp_h7 = _find_shape_by_name(slide_7, "content_heading")
        if shp_h7:
            _set_shape_text(shp_h7, f"3.1 {_text(sec0.title, 80)} — Bulgular", bold=True, font_size_pt=24.0)
        _format_findings_slide(
            slide_7,
            sec0.consensus,
            sec0.disagreements,
            sec0.implications,
            turkish,
        )

        # Handle additional sections (Section 2, 3...) by duplicating Slide 6 & 7
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
                _set_shape_text(dh6, f"3.{s_idx} {_text(sec.title, 80)}", bold=True, font_size_pt=24.0)
            dsyn = _find_shape_by_name(dup6, "sections[].synthesis")
            if dsyn:
                dsyn.top = Inches(2.24)
                dsyn.height = Inches(3.70)
                _set_shape_text(dsyn, _text(_section_text(sec)), max_font_pt=16.0, min_font_pt=8.5)
            dcit = _find_shape_by_name(dup6, "sections[].citations")
            if dcit:
                dcit.top = Inches(6.20)
                dcit.height = Inches(0.55)
                cits = _extract_source_citations(sec.synthesis)
                dcit_txt = (
                    f"Bu temada kullanılan kaynaklar: {', '.join(cits)}"
                    if cits
                    else ("Kabul edilen kanıtlar" if turkish else "Accepted evidence")
                )
                _set_shape_text(dcit, dcit_txt, font_size_pt=11.0)

            # Duplicate Slide 7 (Findings) ONLY IF the section has at least one finding
            sec_has_findings = bool(
                (sec.consensus and sec.consensus.strip())
                or (sec.disagreements and sec.disagreements.strip())
                or (sec.implications and sec.implications.strip())
            )
            if sec_has_findings:
                dup7 = _duplicate_slide(prs, slide_7)
                sldId7 = prs.slides._sldIdLst[-1]
                prs.slides._sldIdLst.remove(sldId7)
                prs.slides._sldIdLst.insert(insert_target, sldId7)
                insert_target += 1

                dh7 = _find_shape_by_name(dup7, "content_heading")
                if dh7:
                    _set_shape_text(dh7, f"3.{s_idx} {_text(sec.title, 80)} — Bulgular", bold=True, font_size_pt=24.0)
                _format_findings_slide(
                    dup7,
                    sec.consensus,
                    sec.disagreements,
                    sec.implications,
                    turkish,
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
        shp_cross.top = Inches(2.24)
        shp_cross.height = Inches(3.70)
        c_text = getattr(package, "cross_study_assessment", "") if package else narrative
        _set_shape_text(
            shp_cross,
            _text(c_text)
            or (
                "Çalışmalar arası değerlendirme bu raporda ayrıca yer almıyor."
                if turkish
                else "No separate cross-study assessment is included in this report."
            ),
            max_font_pt=16.0,
            min_font_pt=8.5,
        )
    shp_ascit = _find_shape_by_name(slide_9, "assessment_citations")
    if shp_ascit:
        shp_ascit.top = Inches(6.20)
        shp_ascit.height = Inches(0.55)
        _set_shape_text(
            shp_ascit,
            "Kaynak değerlendirmesi literatür haritasında sunulmuştur."
            if turkish
            else "Source assessment is provided in the literature map.",
            font_size_pt=11.0,
        )

    # Slide 10: Conclusion
    conc_text = getattr(package, "conclusion", "") if package else ""
    shp_conc = _find_shape_by_name(slide_10, "conclusion")
    if shp_conc:
        shp_conc.top = Inches(2.24)
        shp_conc.height = Inches(3.70)
        _set_shape_text(
            shp_conc,
            _text(conc_text)
            or (
                "Sonuç bölümü bu raporda ayrıca yer almıyor."
                if turkish
                else "No separate conclusion is included in this report."
            ),
            max_font_pt=16.0,
            min_font_pt=8.5,
        )
    shp_conccit = _find_shape_by_name(slide_10, "conclusion_citations")
    if shp_conccit:
        shp_conccit.top = Inches(6.20)
        shp_conccit.height = Inches(0.55)
        conc_cits = _extract_source_citations(conc_text)
        _set_shape_text(
            shp_conccit,
            f"Kullanılan kaynaklar: {', '.join(conc_cits)}"
            if conc_cits
            else (
                "Kaynaklar denetim eklerinde korunmuştur."
                if turkish
                else "Sources are preserved in audit appendices."
            ),
            font_size_pt=11.0,
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
                font_size_pt=16.5,
            )
    shp_unc = _find_shape_by_name(slide_11, "uncertainty")
    if shp_unc:
        shp_unc.top = Inches(2.24)
        shp_unc.height = Inches(4.20)
        unc_text = getattr(package, "uncertainty", "") if package else uncertainty
        _set_shape_text(
            shp_unc,
            _text(unc_text)
            or (
                "Belirsizlik bölümü bu raporda ayrıca yer almıyor."
                if turkish
                else "No separate uncertainty section is included in this report."
            ),
            max_font_pt=16.0,
            min_font_pt=8.5,
        )

    # Slide 12: Ek A (Method & coverage)
    slide_12 = (
        _find_slide_with_heading(prs, "Yöntem, kapsam ve yeniden üretilebilirlik") or prs.slides[11]
    )
    shp_meth = _find_shape_by_name(slide_12, "method")
    if shp_meth:
        shp_meth.top = Inches(2.14)
        shp_meth.height = Inches(3.80)
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
        _set_shape_text(shp_meth, method_desc, max_font_pt=12.0, min_font_pt=9.0)
    shp_run_meta = _find_shape_by_name(slide_12, "run_metadata")
    if shp_run_meta:
        shp_run_meta.top = Inches(6.20)
        shp_run_meta.left = Inches(0.50)
        shp_run_meta.width = Inches(11.40)  # Avoid overlapping slide_number at 12.40
        shp_run_meta.height = Inches(0.65)
        meta_lines = [
            f"Çalışma Kimliği: {run_id}",
            f"Üretim Zamanı: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Rapor Pipeline Sürümü: v{REPORT_PIPELINE_VERSION}",
            f"Biçim / Mod: {getattr(package, 'report_mode', 'standard')}",
        ]
        _set_shape_text(shp_run_meta, "\n".join(meta_lines), font_size_pt=9.5)
    for shp in slide_12.shapes:
        if shp.has_table and len(shp.table.columns) == 2:
            tbl = shp.table
            cov = coverage or {}

            def share(key: str) -> str:
                value = cov.get(key)
                return f"{value:.0%}" if isinstance(value, (int, float)) else "—"

            unresolved = cov.get("unresolved_major_claims")
            metrics = [
                ("Kaynak ailesi kapsamı", share("source_family_coverage")),
                ("Sorgu dalı kapsamı", share("query_branch_coverage")),
                ("İddia denetim kapsamı", share("claim_audit_coverage")),
                ("Tahmini tamlık", share("estimated_completeness")),
                ("Çözülmemiş ana iddia", str(unresolved) if unresolved is not None else "—"),
            ]
            for row_idx, (m_label, m_val) in enumerate(metrics, 1):
                if row_idx < len(tbl.rows):
                    _set_cell_text(tbl.cell(row_idx, 0), m_label, font_size_pt=10.5, bold=False)
                    _set_cell_text(tbl.cell(row_idx, 1), m_val, font_size_pt=10.5, bold=True)

    # Slide 13: Ek B (Topic / Literature landscape)
    slide_13 = _find_slide_with_heading(prs, "Literatürün konu haritası") or prs.slides[12]
    shp_lcap = _find_shape_by_name(slide_13, "landscape_caption")
    if shp_lcap:
        shp_lcap.top = Inches(6.15)
        shp_lcap.height = Inches(0.65)
        _set_shape_text(
            shp_lcap,
            "Literatürde yer alan araştırma katkı türleri ve kanıt yoğunluk haritası."
            if turkish
            else "Research contribution distribution and evidence density map.",
            font_size_pt=11.0,
        )

    figs_map = dict(figures or {})
    if not figs_map and package is not None and sources:
        try:
            from .word_report import _bar_chart, _theme_evidence_map
            contribution_counts = Counter(
                getattr(profile, "contribution", "") for profile in getattr(package, "study_profiles", [])
            )
            title_chart = "Araştırma katkısı dağılımı" if turkish else "Research contribution distribution"
            figs_map["16a_research_contribution_landscape.png"] = _bar_chart(title_chart, contribution_counts.most_common())
            figs_map["16b_theme_evidence_map.png"] = _theme_evidence_map(package, turkish=turkish)
        except Exception:  # noqa: BLE001, S110 - a chart that fails to draw leaves its "not available" text; it must not fail the deck
            pass

    land_bytes = (
        figs_map.get("16a_research_contribution_landscape.png")
        or next((v for k, v in figs_map.items() if "landscape" in k.lower() or "contribution" in k.lower()), None)
    )
    theme_bytes = (
        figs_map.get("16b_theme_evidence_map.png")
        or next((v for k, v in figs_map.items() if "theme" in k.lower() or "evidence_map" in k.lower()), None)
    )

    shp_cl = _find_shape_by_name(slide_13, "contribution_landscape")
    if shp_cl:
        if land_bytes:
            _replace_shape_with_picture(slide_13, shp_cl, land_bytes)
        else:
            _set_shape_text(
                shp_cl,
                "Araştırma katkısı dağılımı bu koşuda üretilmedi." if turkish else "Research contribution distribution not available.",
                font_size_pt=12.0,
            )

    shp_tem = _find_shape_by_name(slide_13, "theme_evidence_map")
    if shp_tem:
        if theme_bytes:
            _replace_shape_with_picture(slide_13, shp_tem, theme_bytes)
        else:
            _set_shape_text(
                shp_tem,
                "Tema-kanıt haritası bu koşuda üretilmedi." if turkish else "Theme-evidence map not available.",
                font_size_pt=12.0,
            )

    # Slide 14: Ek C (Sources table)
    slide_14 = _find_slide_with_heading(prs, "Tam kaynak kataloğu") or prs.slides[13]
    for shp in slide_14.shapes:
        if shp.has_table and len(shp.table.columns) == 6:
            tbl = shp.table
            num_sources = len(sources)
            if num_sources == 0:
                _set_cell_text(tbl.cell(1, 0), "—", font_size_pt=10.0)
                _set_cell_text(
                    tbl.cell(1, 3),
                    "Araştırmada kayıtlı kaynak bulunamadı." if turkish else "No retained sources found.",
                    font_size_pt=10.0,
                )
                for col_i in (1, 2, 4, 5):
                    _set_cell_text(tbl.cell(1, col_i), "—", font_size_pt=10.0)
                for r_idx in range(2, len(tbl.rows)):
                    for col_i in range(len(tbl.columns)):
                        _set_cell_text(tbl.cell(r_idx, col_i), "", font_size_pt=10.0)
            else:
                for r_idx in range(1, len(tbl.rows)):
                    s_idx = r_idx - 1
                    if s_idx < num_sources:
                        source = sources[s_idx]
                        s_label = f"S{r_idx:02d}"
                        meta = getattr(source, "metadata_json", {}) or {}
                        _set_cell_text(tbl.cell(r_idx, 0), s_label, font_size_pt=10.0, bold=True)
                        _set_cell_text(
                            tbl.cell(r_idx, 1),
                            _text(meta.get("year") or meta.get("publication_year") or "—", 10),
                            font_size_pt=10.0,
                        )
                        _set_cell_text(tbl.cell(r_idx, 2), _text(meta.get("type") or "Makale", 20), font_size_pt=10.0)
                        _set_cell_text(tbl.cell(r_idx, 3), _text(getattr(source, "title", "Kaynak"), 100), font_size_pt=9.5)
                        _set_cell_text(tbl.cell(r_idx, 4), _text(getattr(source, "connector_id", "web"), 20), font_size_pt=10.0)
                        _set_cell_text(tbl.cell(r_idx, 5), str(evidence_counts.get(str(source.id), 1)), font_size_pt=10.0)
                    else:
                        for col_i in range(len(tbl.columns)):
                            _set_cell_text(tbl.cell(r_idx, col_i), "", font_size_pt=10.0)

            if num_sources > 4:
                note_text = (
                    f"Araştırmada korunan {num_sources} kaynaktan ilk 4'ü özetlenmiştir; tam liste Word raporu Ek C'de yer alır."
                    if turkish
                    else f"Showing first 4 of {num_sources} retained sources; full inventory is in Word report Appendix C."
                )
                _add_slide_bottom_note(slide_14, note_text)
            break

    # Slide 15: Ek D (Audited claims table)
    slide_15 = _find_slide_with_heading(prs, "Denetlenmiş iddia kaydı") or prs.slides[14]
    for shp in slide_15.shapes:
        if shp.has_table and len(shp.table.columns) == 6:
            tbl = shp.table
            num_claims = len(reportable_claims)
            if num_claims == 0:
                _set_cell_text(tbl.cell(1, 0), "—", font_size_pt=10.0)
                _set_cell_text(
                    tbl.cell(1, 1),
                    "Denetlenmiş iddia kaydı bulunamadı." if turkish else "No audited claims found.",
                    font_size_pt=10.0,
                )
                for col_i in (2, 3, 4, 5):
                    _set_cell_text(tbl.cell(1, col_i), "—", font_size_pt=10.0)
                for r_idx in range(2, len(tbl.rows)):
                    for col_i in range(len(tbl.columns)):
                        _set_cell_text(tbl.cell(r_idx, col_i), "", font_size_pt=10.0)
            else:
                for r_idx in range(1, len(tbl.rows)):
                    c_idx = r_idx - 1
                    if c_idx < num_claims:
                        claim = reportable_claims[c_idx]
                        c_label = f"C{r_idx:02d}"
                        _set_cell_text(tbl.cell(r_idx, 0), c_label, font_size_pt=10.0, bold=True)
                        claim_txt = getattr(claim, "text", "") or getattr(claim, "claim", "")
                        _set_cell_text(tbl.cell(r_idx, 1), _text(claim_txt, 120), font_size_pt=9.5)
                        _set_cell_text(tbl.cell(r_idx, 2), _text(getattr(claim, "status", "supported"), 15), font_size_pt=10.0)
                        _set_cell_text(
                            tbl.cell(r_idx, 3),
                            f"{float(getattr(claim, 'confidence', 0.9) or 0.9):.2f}",
                            font_size_pt=10.0,
                        )
                        _set_cell_text(
                            tbl.cell(r_idx, 4),
                            f"{float((getattr(claim, 'audit', {}) or {}).get('question_relevance', 0.9) or 0.9):.2f}",
                            font_size_pt=10.0,
                        )
                        src_nums = _claim_sources(str(getattr(claim, "id", "")), evidence_by_claim, source_numbers)
                        src_str = ", ".join(f"S{num:02d}" for num in src_nums) if src_nums else "—"
                        _set_cell_text(tbl.cell(r_idx, 5), src_str, font_size_pt=10.0)
                    else:
                        for col_i in range(len(tbl.columns)):
                            _set_cell_text(tbl.cell(r_idx, col_i), "", font_size_pt=10.0)

            if num_claims > 4:
                note_text = (
                    f"Raporlanan {num_claims} denetlenmiş iddiadan ilk 4'ü özetlenmiştir; tam iddia kaydı Word raporu Ek D ve claim_ledger ekindedir."
                    if turkish
                    else f"Showing first 4 of {num_claims} audited claims; full register is in Word report Appendix D and claim ledger."
                )
                _add_slide_bottom_note(slide_15, note_text)
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
            _set_shape_text(shp_num, str(idx + 1), font_size_pt=12.0, auto_fit=False)

    output = io.BytesIO()
    prs.save(output)
    return PresentationReportResult(
        document=output.getvalue(),
        figures=figs_map,
        citations=citations,
    )


def _find_slide_with_heading(prs: Any, heading_substring: str) -> Any | None:
    for slide in prs.slides:
        shp_h = _find_shape_by_name(slide, "content_heading")
        if shp_h and heading_substring in shp_h.text:
            return slide
    return None
