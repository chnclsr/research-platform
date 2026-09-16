#!/usr/bin/env python3
"""Presentation Polisher Host Service.

Runs on the Windows host (port 3942) and bridges Docker worker export/revision
calls to `agy` (for semantic presentation polishing) and `soffice` (LibreOffice
headless validation).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pptx
from fastapi import FastAPI, HTTPException, Request, Response
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("presentation_polisher")

app = FastAPI(title="Research Platform Presentation Polisher", version="0.1.0")

PORT = int(os.environ.get("PRESENTATION_POLISHER_PORT", "3942"))
HOST = os.environ.get("PRESENTATION_POLISHER_HOST", "0.0.0.0")

_CITATION_REGEX = re.compile(r"\[S\d+\]")


def find_agy_binary() -> str | None:
    candidate = shutil.which("agy")
    if candidate:
        return candidate
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        p = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if p.is_file():
            return str(p)
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        p = Path(user_profile) / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
        if p.is_file():
            return str(p)
    return None


def find_soffice_binary() -> str | None:
    candidate = shutil.which("soffice")
    if candidate:
        return candidate
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates = [
        Path(program_files) / "LibreOffice" / "program" / "soffice.exe",
        Path(program_files + " (x86)") / "LibreOffice" / "program" / "soffice.exe",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


@dataclass
class BulletItem:
    prefix: str
    text: str


@dataclass
class SlidePolishItem:
    slide_index: int
    slide_number: int
    heading_shape_name: str | None
    heading_text: str | None
    body_shape_name: str
    body_text: str
    citations: list[str]


@dataclass
class PolishedSlideResult:
    new_heading: str | None
    bullets: list[BulletItem]


def extract_polishable_slides(prs: pptx.Presentation) -> list[SlidePolishItem]:
    items: list[SlidePolishItem] = []
    target_shape_names = {
        "summary",
        "sections[].synthesis",
        "sections[].consensus",
        "sections[].implications",
        "sections[].implications_2",
        "cross_study_assessment",
        "conclusion",
    }

    for idx, slide in enumerate(prs.slides):
        heading_shape_name: str | None = None
        heading_text: str | None = None
        body_shape_name: str | None = None
        body_text: str | None = None

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            name = shape.name.strip()
            text = shape.text_frame.text.strip()
            if not text:
                continue

            # Heading candidate
            if (
                name in {"content_heading", "heading"}
                or ("heading" in name.lower() and not any(k in name.lower() for k in ["rail", "rule", "label"]))
            ):
                heading_shape_name = name
                heading_text = text
            # Body candidate
            elif (
                name in target_shape_names
                or any(k in name.lower() for k in ["synthesis", "consensus", "implications", "summary", "assessment", "conclusion"])
            ) and not any(k in name.lower() for k in ["label", "rule", "rail", "number", "logo"]):
                body_shape_name = name
                body_text = text

        if body_shape_name and body_text:
            citations = _CITATION_REGEX.findall(body_text)
            items.append(
                SlidePolishItem(
                    slide_index=idx,
                    slide_number=idx + 1,
                    heading_shape_name=heading_shape_name,
                    heading_text=heading_text,
                    body_shape_name=body_shape_name,
                    body_text=body_text,
                    citations=citations,
                )
            )

    return items


def _extract_json_from_text(raw: str) -> Any:
    cleaned = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)


def fallback_polish_item(item: SlidePolishItem) -> PolishedSlideResult:
    """Deterministic fallback formatting if agy fails or is unavailable."""
    new_heading: str | None = None
    if item.heading_text:
        h = item.heading_text.strip()
        is_cont = "(devam)" in h
        h_clean = h.replace("(devam)", "").strip()
        if len(h_clean) > 60:
            words = h_clean.split()
            h_clean = " ".join(words[:7]) + ("..." if len(words) > 7 else "")
        new_heading = f"{h_clean} (devam)" if is_cont else h_clean

    raw_sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", item.body_text) if s.strip()]
    if not raw_sentences:
        raw_sentences = [item.body_text]

    bullets: list[BulletItem] = []
    # Take up to 3-4 sentences
    for s in raw_sentences[:4]:
        words = s.split()
        if len(words) > 3:
            prefix = "• " + " ".join(words[:3]) + ":"
            text = " ".join(words[3:])
        else:
            prefix = "• Bulgu:"
            text = s
        bullets.append(BulletItem(prefix=prefix, text=text))

    return PolishedSlideResult(new_heading=new_heading, bullets=bullets)


async def polish_batch_with_agy(
    agy_bin: str,
    batch: list[SlidePolishItem],
    language: str = "tr",
    timeout_s: float = 120.0,
) -> dict[int, PolishedSlideResult]:
    """Invoke `agy -p` to semantically polish a batch of slides."""
    payload = []
    for item in batch:
        payload.append(
            {
                "slide_number": item.slide_number,
                "current_heading": item.heading_text or "",
                "raw_text": item.body_text,
                "citations": item.citations,
            }
        )

    prompt = f"""You are an expert scientific presentation designer.
Below is a JSON array of slides from a research report.
For each slide:
1. Simplify 'current_heading' into a punchy, professional, and concise slide title (max 6-8 words). If it has '(devam)', preserve ' (devam)' at the end.
2. Convert 'raw_text' into 2 to 4 high-impact executive presentation bullet points.
Each bullet MUST have:
- 'prefix': A short bold title in {language.upper()} (e.g. "• Büyük Merkez (69.761 Çift):" or "• Model Doğruluğu:")
- 'text': The concise factual explanation.
CRITICAL MANDATORY REQUIREMENT:
You MUST preserve ALL citation references (like [S1], [S24], [S153]) exactly as they appear in the original raw_text. Never omit or alter a citation marker!

Input slides JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Respond with ONLY valid JSON matching this structure (no conversational text):
{{
  "slides": [
    {{
      "slide_number": 3,
      "new_heading": "...",
      "bullets": [
        {{"prefix": "• ...:", "text": "... [S1]"}}
      ]
    }}
  ]
}}
"""

    results: dict[int, PolishedSlideResult] = {}
    try:
        proc = await asyncio.create_subprocess_exec(
            agy_bin,
            "-p",
            prompt,
            "--print-timeout",
            f"{int(timeout_s)}s",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 15)

        if proc.returncode == 0 and stdout:
            parsed = _extract_json_from_text(stdout.decode("utf-8", errors="replace"))
            slide_entries = parsed.get("slides", [])
            for entry in slide_entries:
                s_num = entry.get("slide_number")
                if not s_num:
                    continue
                bullets = [
                    BulletItem(
                        prefix=b.get("prefix", "• Bulgu:").strip(),
                        text=b.get("text", "").strip(),
                    )
                    for b in entry.get("bullets", [])
                    if b.get("text")
                ]
                if bullets:
                    results[s_num] = PolishedSlideResult(
                        new_heading=entry.get("new_heading"),
                        bullets=bullets,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("agy semantic polish batch failed: %s; falling back to deterministic", exc)

    # Fill any missing items with deterministic fallback
    for item in batch:
        if item.slide_number not in results:
            results[item.slide_number] = fallback_polish_item(item)

    return results


def apply_polished_content(prs: pptx.Presentation, items: list[SlidePolishItem], results: dict[int, PolishedSlideResult]) -> None:
    """Applies formatted bullets and concise headings with layout spacing."""
    for item in items:
        res = results.get(item.slide_number)
        if not res:
            continue

        slide = prs.slides[item.slide_index]
        heading_shape = None
        body_shape = None

        for shape in slide.shapes:
            if item.heading_shape_name and shape.name == item.heading_shape_name:
                heading_shape = shape
            if shape.name == item.body_shape_name:
                body_shape = shape

        # 1. Update Heading
        if heading_shape and res.new_heading:
            tf_h = heading_shape.text_frame
            tf_h.clear()
            tf_h.word_wrap = True
            tf_h.margin_left = Inches(0.08)
            tf_h.margin_right = Inches(0.08)
            tf_h.margin_top = Inches(0.05)
            tf_h.margin_bottom = Inches(0.05)

            p_h = tf_h.paragraphs[0]
            p_h.space_before = Pt(0)
            p_h.space_after = Pt(0)
            run_h = p_h.add_run()
            run_h.text = res.new_heading
            run_h.font.name = "Arial"
            run_h.font.bold = True
            font_size = 22 if len(res.new_heading) <= 50 else 18
            run_h.font.size = Pt(font_size)
            run_h.font.color.rgb = RGBColor(0x24, 0x24, 0x24)

        # 2. Update Body with formatted bullets
        if body_shape and res.bullets:
            tf_b = body_shape.text_frame
            tf_b.clear()
            tf_b.word_wrap = True
            tf_b.margin_left = Inches(0.08)
            tf_b.margin_right = Inches(0.08)
            tf_b.margin_top = Inches(0.08)
            tf_b.margin_bottom = Inches(0.08)

            total_chars = sum(len(b.prefix) + len(b.text) for b in res.bullets)
            # Dynamic point size calculation to guarantee zero overflow
            body_font_pt = 14
            if total_chars > 500 or len(res.bullets) > 4:
                body_font_pt = 12
            elif total_chars > 350:
                body_font_pt = 13

            for i, bullet in enumerate(res.bullets):
                p = tf_b.paragraphs[0] if i == 0 else tf_b.add_paragraph()
                p.space_before = Pt(0)
                p.space_after = Pt(8 if body_font_pt >= 13 else 6)
                p.line_spacing = 1.15

                # Bold Prefix
                r_pre = p.add_run()
                r_pre.text = (bullet.prefix + " ") if not bullet.prefix.endswith(" ") else bullet.prefix
                r_pre.font.name = "Arial"
                r_pre.font.bold = True
                r_pre.font.size = Pt(body_font_pt)
                r_pre.font.color.rgb = RGBColor(0x24, 0x24, 0x24)

                # Explanatory Text
                r_txt = p.add_run()
                r_txt.text = bullet.text
                r_txt.font.name = "Arial"
                r_txt.font.bold = False
                r_txt.font.size = Pt(body_font_pt)
                r_txt.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

            # 3. Geometric Bounds and Position Adjustment
            if heading_shape and body_shape:
                # Ensure minimum 18pt clearance below heading
                min_body_top = heading_shape.top + heading_shape.height + Inches(0.15)
                if body_shape.top < min_body_top:
                    shift = min_body_top - body_shape.top
                    body_shape.top = min_body_top
                    body_shape.height = max(Inches(1.0), body_shape.height - shift)

            # Ensure shape bottom does not exceed footer line (486pt = ~6.75 inches)
            max_bottom = Inches(6.75)
            if body_shape.top + body_shape.height > max_bottom:
                body_shape.height = max_bottom - body_shape.top


def validate_with_soffice(pptx_path: Path, soffice_bin: str) -> bool:
    """Run headless LibreOffice export to verify OpenXML validity."""
    try:
        temp_dir = pptx_path.parent
        res = subprocess.run(
            [soffice_bin, "--headless", "--convert-to", "pdf", str(pptx_path), "--outdir", str(temp_dir)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        pdf_path = pptx_path.with_suffix(".pdf")
        if res.returncode == 0 and pdf_path.is_file():
            logger.info("LibreOffice headless validation passed for %s", pptx_path.name)
            return True
        logger.warning("LibreOffice conversion returned code %d: %s", res.returncode, res.stderr.decode(errors="ignore"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("LibreOffice validation exception: %s", exc)
    return False


@app.get("/health")
async def health():
    agy_bin = find_agy_binary()
    soffice_bin = find_soffice_binary()
    return {
        "status": "ok",
        "service": "presentation-polisher",
        "agy": bool(agy_bin),
        "agy_path": agy_bin,
        "soffice": bool(soffice_bin),
        "soffice_path": soffice_bin,
    }


@app.post("/polish")
async def polish_endpoint(request: Request, language: str = "tr", run_id: str | None = None):
    pptx_bytes = await request.body()
    if not pptx_bytes:
        raise HTTPException(status_code=400, detail="Empty request body")

    logger.info("Received polish request for run %s (%d bytes, language=%s)", run_id, len(pptx_bytes), language)

    with tempfile.TemporaryDirectory(prefix="agy_deck_polish_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_pptx = tmp_path / "raw.pptx"
        input_pptx.write_bytes(pptx_bytes)

        try:
            prs = pptx.Presentation(str(input_pptx))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse incoming PPTX: %s", exc)
            raise HTTPException(status_code=400, detail=f"Invalid PPTX file: {exc}")

        # 1. Extract slides needing polish
        items = extract_polishable_slides(prs)
        logger.info("Found %d polishable slides in run %s", len(items), run_id)

        agy_bin = find_agy_binary()
        soffice_bin = find_soffice_binary()

        # 2. Semantic Polish in batches
        results: dict[int, PolishedSlideResult] = {}
        batch_size = 10
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            if agy_bin:
                batch_res = await polish_batch_with_agy(agy_bin, batch, language=language)
            else:
                batch_res = {item.slide_number: fallback_polish_item(item) for item in batch}
            results.update(batch_res)

        # 3. Apply layout & geometry
        apply_polished_content(prs, items, results)

        output_pptx = tmp_path / "polished.pptx"
        prs.save(str(output_pptx))

        # 4. Optional validation with LibreOffice
        if soffice_bin:
            validate_with_soffice(output_pptx, soffice_bin)

        polished_bytes = output_pptx.read_bytes()
        logger.info("Polishing complete for run %s (%d -> %d bytes)", run_id, len(pptx_bytes), len(polished_bytes))

        return Response(
            content=polished_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Presentation Polisher Service on http://%s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT)
