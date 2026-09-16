"""Tests for presentation polisher client and service logic."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import httpx
import pptx
import pytest
from pptx.util import Inches

from research_platform.config import Settings
from research_platform.presentation_polisher import polish_presentation
from scripts.presentation_polisher_service import (
    BulletItem,
    PolishedSlideResult,
    SlidePolishItem,
    apply_polished_content,
    extract_polishable_slides,
    fallback_polish_item,
)


def _build_test_deck() -> bytes:
    prs = pptx.Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    # Heading shape
    h_shape = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
    h_shape.name = "content_heading"
    h_shape.text_frame.text = "BT taramalarından rapor oluşturmak için derin öğrenme modelleri nelerdir?"

    # Body shape
    b_shape = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(4))
    b_shape.name = "sections[].synthesis"
    b_shape.text_frame.text = (
        "Vision Transformers ve multimodal mimariler 2D ve 3D görüntülerden metin sentezinde öncü sistemlerdir [S1]. "
        "Büyük ölçekli veri setleri ile klinik doğruluk desteklenmektedir [S2]."
    )

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_polish_presentation_disabled():
    data = b"dummy_pptx_data"
    settings = Settings(presentation_polisher_enabled=False)
    result = await polish_presentation(data, run_id="test_run", settings=settings)
    assert result == data


@pytest.mark.asyncio
async def test_polish_presentation_unreachable_fallback():
    data = b"dummy_pptx_data"
    settings = Settings(
        presentation_polisher_enabled=True,
        presentation_polisher_url="http://127.0.0.1:59999",  # non-existent port
        presentation_polisher_timeout_s=2.0,
    )
    result = await polish_presentation(data, run_id="test_run", settings=settings)
    assert result == data


@pytest.mark.asyncio
async def test_polish_presentation_success():
    raw_data = b"raw_pptx_content"
    polished_data = b"polished_pptx_content"
    settings = Settings(
        presentation_polisher_enabled=True,
        presentation_polisher_url="http://127.0.0.1:3942",
    )

    mock_resp = httpx.Response(200, content=polished_data)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await polish_presentation(raw_data, run_id="test_run", settings=settings)
        assert result == polished_data
        mock_post.assert_called_once()


def test_extract_and_apply_polish():
    deck_bytes = _build_test_deck()
    prs = pptx.Presentation(io.BytesIO(deck_bytes))

    # 1. Extraction
    items = extract_polishable_slides(prs)
    assert len(items) == 1
    item = items[0]
    assert item.slide_number == 1
    assert item.heading_shape_name == "content_heading"
    assert "derin öğrenme" in (item.heading_text or "")
    assert item.body_shape_name == "sections[].synthesis"
    assert "[S1]" in item.citations and "[S2]" in item.citations

    # 2. Results to apply
    results = {
        1: PolishedSlideResult(
            new_heading="3.1 Derin Öğrenme Mimarileri",
            bullets=[
                BulletItem(prefix="• Öncü Mimariler:", text="Vision Transformers ve multimodal sistemler [S1]."),
                BulletItem(prefix="• Veri Kümeleri:", text="Büyük veri setleri klinik doğruluğu artırmaktadır [S2]."),
            ],
        )
    }

    # 3. Application
    apply_polished_content(prs, items, results)

    # Verify heading was updated
    slide = prs.slides[0]
    h_shape = next(s for s in slide.shapes if s.name == "content_heading")
    assert h_shape.text_frame.text == "3.1 Derin Öğrenme Mimarileri"
    assert h_shape.text_frame.paragraphs[0].runs[0].font.bold is True

    # Verify body paragraphs and bullets
    b_shape = next(s for s in slide.shapes if s.name == "sections[].synthesis")
    paragraphs = b_shape.text_frame.paragraphs
    assert len(paragraphs) == 2
    assert "• Öncü Mimariler:" in paragraphs[0].text
    assert "[S1]" in paragraphs[0].text
    assert "• Veri Kümeleri:" in paragraphs[1].text
    assert "[S2]" in paragraphs[1].text


def test_fallback_polish_item():
    item = SlidePolishItem(
        slide_index=0,
        slide_number=1,
        heading_shape_name="heading",
        heading_text="Bu çok uzun bir araştırma sorusu başlığıdır ve kısaltılması gerekmektedir (devam)",
        body_shape_name="synthesis",
        body_text="İlk cümle önemli bulguyu anlatır [S1]. İkinci cümle klinik analizi içerir [S2].",
        citations=["[S1]", "[S2]"],
    )

    res = fallback_polish_item(item)
    assert res.new_heading is not None
    assert "(devam)" in res.new_heading
    assert len(res.bullets) >= 2
    assert "[S1]" in res.bullets[0].text
    assert "[S2]" in res.bullets[1].text


def test_service_health_and_polish_endpoint():
    from starlette.testclient import TestClient

    from scripts.presentation_polisher_service import app

    client = TestClient(app)
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    data = health_resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "presentation-polisher"

    deck_bytes = _build_test_deck()
    polish_resp = client.post(
        "/polish",
        content=deck_bytes,
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        params={"language": "tr", "run_id": "test_service_run"},
    )
    assert polish_resp.status_code == 200
    assert len(polish_resp.content) > 0

    # Verify that the returned bytes are a valid pptx
    prs = pptx.Presentation(io.BytesIO(polish_resp.content))
    assert len(prs.slides) == 1

