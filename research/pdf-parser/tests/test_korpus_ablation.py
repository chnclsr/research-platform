"""`korpus_ablation.olc()` ile `hata_arayuzu._yonlendirme()` ayni dili konusmali.

2026-08-21'e kadar konusmuyorlardi: uretim tarafi "KACIRILDI" yaziyor, sayim
tarafi "KACAN" okuyordu. Counter eksik anahtarda 0 dondurdugu icin hata
gorunmedi -- kacirilan tablo sayisi her kosuda sessizce sifir cikti ve iki
korpus karsilastirmasinda o sutun hep bos kaldi. Yanlis olan sayi degil, hic
hesaplanmayan bir sayiydi; bu tur bir hatanin testi de sayiya degil ANAHTAR
UYUMUNA bakmali.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for yol in (os.path.join(BASE, "scripts"), os.path.join(BASE, "src")):
    if yol not in sys.path:
        sys.path.insert(0, yol)

korpus_ablation = pytest.importorskip("korpus_ablation")
hata_arayuzu = pytest.importorskip("hata_arayuzu")


def test_yonlendirme_hukumleri_uretimle_ayni():
    """Uretimin uretebildigi her hukum sayim tarafinda taninmali.

    `_yonlendirme` girdi uzayinin tamami uzerinde gezilir (yol x ref_tablo x
    ref_sekil); ciktilarin hepsi `YONLENDIRME_HUKUMLERI` icinde olmali.
    """
    uretilen = {
        hata_arayuzu._yonlendirme(yol, ref_tablo, ref_sekil)
        for yol in ("HIZLI", "AGIR", "OCR")
        for ref_tablo in (False, True)
        for ref_sekil in (False, True)
    }
    bilinmeyen = uretilen - korpus_ablation.YONLENDIRME_HUKUMLERI
    assert not bilinmeyen, (
        "korpus_ablation bu hukumleri tanimiyor, sessizce 0 sayacak: %s"
        % sorted(bilinmeyen))


def test_kacirilan_hukmu_gercekten_sayiliyor(tmp_path):
    """KACIRILDI iceren bir kayit `kacirilan` alanina yansimali.

    Asil regresyon budur: anahtar kayarsa bu sayi 0 kalir ve fark edilmez.
    """
    veri = [{
        "belge": "sahte",
        "karantina_sayfa": 0,
        "fallback_sayfa": 0,
        "sayfalar": [
            {"yonlendirme": "KACIRILDI", "tablo_hukmu": "FN",
             "sekil_hukmu": "TN", "yol": "HIZLI"},
            {"yonlendirme": "BOSA", "tablo_hukmu": "TN",
             "sekil_hukmu": "TN", "yol": "AGIR"},
            {"yonlendirme": "DOGRU_HIZLI", "tablo_hukmu": "TN",
             "sekil_hukmu": "TN", "yol": "HIZLI"},
        ],
    }]
    yol = tmp_path / "sahte.json"
    yol.write_text(json.dumps(veri), encoding="utf-8")

    olcum = korpus_ablation.olc(str(yol))
    assert olcum["kacirilan"] == 1
    assert olcum["bosa"] == 1
    assert olcum["agir"] == 1
    assert olcum["sayfa"] == 3


def test_taninmayan_hukum_sessiz_kalmaz(tmp_path, capsys):
    """Yeni bir hukum eklenirse sayim tarafi uyarmali, 0 sayip gecmemeli."""
    veri = [{
        "belge": "sahte", "karantina_sayfa": 0, "fallback_sayfa": 0,
        "sayfalar": [{"yonlendirme": "YEPYENI_HUKUM", "tablo_hukmu": "TN",
                      "sekil_hukmu": "TN", "yol": "HIZLI"}],
    }]
    yol = tmp_path / "sahte.json"
    yol.write_text(json.dumps(veri), encoding="utf-8")

    korpus_ablation.olc(str(yol))
    assert "YEPYENI_HUKUM" in capsys.readouterr().out
