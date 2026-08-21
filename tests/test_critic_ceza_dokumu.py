"""`sayfa_skoru` ceza dokumu: teshis eklendi, DAVRANIS degismedi.

Dokum 2026-08-21'de eklendi (rapor O.8.2). Eklenmesinin sebebi, yalniz
`low_quality` yuzunden agir motora giden sayfalarda "hangi ceza bu skoru
dusurdu" sorusunun ancak kod okunarak cevaplanabilmesiydi. Buradaki testlerin
isi, dokumun dogru olmasindan once `quality_score`'un AYNI kalmasini
garantilemek: dokum bir gozlemci, bir karar mercii degil.
"""
from __future__ import annotations

import pytest

from research_platform.parsers.smart_router.critic import PDFCritic


def _metrik(**ustune):
    """Hicbir cezanin tetiklenmedigi temiz bir sayfa; testler ustune yazar."""
    temiz = {
        "karakter": 2000,
        "char_drop_ratio": None,
        "gibberish_ratio": 0.0,
        "unicode_bozuk": False,
        "dangling_sentence_ratio": 0.0,
        "broken_line_ratio": 0.0,
        "hyphen_density_per_1k_words": 0.0,
        "orphan_density_per_1k_words": 0.0,
        "latex_imbalance": 0,
        "table_irregularity_ratio": 0.0,
        "heading_incoherence_ratio": 0.0,
    }
    temiz.update(ustune)
    return temiz


def test_temiz_sayfada_ceza_yok():
    sonuc = PDFCritic().sayfa_skoru(_metrik())
    assert sonuc["quality_score"] == 100.0
    assert sonuc["cezalar"] == {}


def test_dokum_toplami_skoru_aciklar():
    """100 - toplam(ceza) == quality_score. Dokum skorun TAM aciklamasi olmali."""
    critic = PDFCritic()
    m = _metrik(dangling_sentence_ratio=0.30, gibberish_ratio=0.05,
                hyphen_density_per_1k_words=9.0, latex_imbalance=2)
    sonuc = critic.sayfa_skoru(m)
    toplam = sum(sonuc["cezalar"].values())
    assert sonuc["quality_score"] == pytest.approx(100.0 - toplam, abs=0.05)


def test_dangling_tek_basina_tavani_doldurabiliyor():
    """26 low_quality sayfasinin 17'si tam 65,0'ta yigiliyordu (rapor O.8.2).

    Sebebi bu: dangling tavani 35 ve tek basina dolabiliyor. Bu davranis
    kasitli degistirilene kadar testle sabitlenir -- degisirse rapor O.8.2'deki
    yigilma analizi de gecersizlesir.
    """
    sonuc = PDFCritic().sayfa_skoru(_metrik(dangling_sentence_ratio=0.90))
    assert list(sonuc["cezalar"]) == ["dangling"]
    assert sonuc["quality_score"] == 65.0


def test_bos_ve_metinsiz_sayfada_dokum_alani_var():
    critic = PDFCritic()
    bos = critic.sayfa_skoru(_metrik(), bos=True)
    assert bos["quality_score"] is None and bos["cezalar"] == {}

    dusmus = critic.sayfa_skoru(_metrik(karakter=5, dangling_sentence_ratio=0.5))
    assert dusmus["critical_issue"] == "TOTAL_TEXT_DROPPED"
    assert dusmus["quality_score"] == 0.0
    # Metin dusmus olsa da o ana kadar birikmis cezalar teshis icin kalir.
    assert "dangling" in dusmus["cezalar"]


def test_ceza_kapatilinca_dokumden_de_dusuyor():
    """Katsayisi 0 olan bir sinyal dokumde GORUNMEMELI -- 'ceza yok' demek."""
    ceza = dict(PDFCritic().ceza)
    ceza["dangling_kat"] = 0.0
    sonuc = PDFCritic(ceza=ceza).sayfa_skoru(_metrik(dangling_sentence_ratio=0.90))
    assert "dangling" not in sonuc["cezalar"]
    assert sonuc["quality_score"] == 100.0
