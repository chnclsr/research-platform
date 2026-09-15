from pathlib import Path

import pytest
from PIL import ImageFont

from research_platform.presentation_layout import (
    Flow,
    TextStyle,
    fit_sentences,
    paginate,
    sentences,
    text_height,
    text_width,
    wrap,
)

BODY = TextStyle(16, leading=1.5)


@pytest.mark.parametrize(("installed", "bold"), [("arial.ttf", False), ("arialbd.ttf", True)])
def test_bundled_metrics_match_arial_where_arial_is_installed(installed, bold):
    """The deck is set in Arial and measured with Arimo; the two must break lines alike."""
    arial = Path("C:/Windows/Fonts") / installed
    if not arial.exists():
        pytest.skip("Arial is not installed on this machine")
    sample = "Yapay zeka tarafından oluşturulan BT radyoloji raporları İÇĞÜŞÖ 0123 [S105]."
    reference = ImageFont.truetype(str(arial), 320).getlength(sample) / 20
    # Arimo Bold differs from Arial Bold by about 0.1%; wrapping keeps a 3% margin.
    assert abs(text_width(sample, TextStyle(16, bold=bold)) - reference) <= reference * 0.005


def test_wrap_keeps_every_word_and_breaks_only_at_spaces():
    text = (
        "Yapay zeka tarafından oluşturulan BT radyoloji raporları klinik doğruluk, olgusal "
        "doğruluk ve dil kalitesi açısından nasıl değerlendirilir?"
    )
    lines = wrap(text, TextStyle(24, bold=True), 627)
    assert " ".join(lines) == text
    assert len(lines) >= 2


def test_a_word_wider_than_the_box_breaks_by_characters():
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC13045517/figures/fig-2-supplementary-data"
    lines = wrap(url, BODY, 120)
    assert "".join(lines) == url
    assert all(text_width(line, BODY) <= 120 for line in lines)


def test_sentences_do_not_end_at_abbreviations_or_decimals():
    text = (
        "AUC 0.93 seviyesine çıktı [S01]. Örn. farklı merkezlerde sonuçlar değişir. "
        "Veri kümeleri sınırlıdır [S18]."
    )
    parts = sentences(text)
    assert parts == [
        "AUC 0.93 seviyesine çıktı [S01].",
        "Örn. farklı merkezlerde sonuçlar değişir.",
        "Veri kümeleri sınırlıdır [S18].",
    ]


def test_fit_sentences_returns_whole_sentences_only():
    text = " ".join(f"Bu {index}. uzun cümle radyoloji raporları hakkında bilgi verir." for index in range(40))
    head, rest = fit_sentences(text, BODY, 400, 5 * BODY.line_height)
    assert head and rest
    assert head.endswith(".")
    assert f"{head} {rest}" == text
    assert text_height(head, BODY, 400) <= 5 * BODY.line_height


def test_paginate_never_loses_or_reorders_text():
    paragraph = " ".join(
        f"Cümle {index} kanıtın sınırlarını ve yöntemsel farklılıkları anlatır [S{index:02d}]."
        for index in range(1, 60)
    )
    flows = [Flow(paragraph, BODY, 627, gap_before=12), Flow("Kısa kapanış paragrafı.", BODY, 627, gap_before=12)]
    pages = paginate(flows, 300)
    assert len(pages) > 1
    rebuilt = " ".join(piece.text for page in pages for piece in page)
    assert rebuilt == f"{paragraph} Kısa kapanış paragrafı."
    for page in pages:
        assert max(piece.top + piece.height for piece in page) <= 300 + 0.01
    assert all(piece.continued for piece in pages[1][:1])


def test_a_label_is_never_left_alone_at_the_bottom_of_a_page():
    label_style = TextStyle(12, bold=True)
    filler = Flow("Doldurma. " * 40, BODY, 627)
    labelled = Flow("İlk cümle. İkinci cümle.", BODY, 627, label="ORTAK YÖN", label_style=label_style)
    pages = paginate([filler, labelled], text_height(filler.text, BODY, 627) + 20)
    labelled_pieces = [piece for page in pages for piece in page if piece.flow is labelled]
    first = labelled_pieces[0]
    assert not first.continued
    assert first.text
