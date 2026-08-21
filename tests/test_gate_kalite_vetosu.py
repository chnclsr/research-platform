"""`sayfa_secici`'nin dusuk-fayda vetosu: neyi geri ceker, neye dokunmaz.

Veto 2026-08-21'de eklendi (rapor O.13). Varsayilani KAPALI; bu testler hem
kapaliyken davranisin degismedigini hem de aciksa yalniz hedefledigi sayfayi
geri cektigini sabitler. Vetonun tehlikesi genislemesidir: tablo/OCR/kritik
gerekcesiyle gelen bir sayfayi da kesmeye baslarsa, olculen kazanc (C1'de
kaybedilen fayda 0,0000) gecersizlesir.
"""
from __future__ import annotations

from research_platform.parsers.smart_router.gate import SayfaBayrak, sayfa_secici


def _bayrak(**ustune) -> SayfaBayrak:
    """Temiz bir sayfa; testler tek tek alan degistirir."""
    alanlar = {
        "sayfa_no": 1, "needs_ocr": False, "has_table": False,
        "has_figure": False, "has_vector_figure": False, "bos": False,
        "tablo_guven": None, "kaynak": {"bezier_egri": 0},
    }
    alanlar.update(ustune)
    return SayfaBayrak(**{k: v for k, v in alanlar.items()
                          if k in SayfaBayrak.__dataclass_fields__})


def _sec(bayrak: SayfaBayrak, kalite: float, veto: bool):
    return sayfa_secici({1: bayrak}, {1: kalite}, kalite_vetosu_cizimsiz=veto)


def test_veto_kapaliyken_davranis_degismez():
    s = _sec(_bayrak(), kalite=60.0, veto=False)
    assert s["agir_sayfalar"] == [1]
    assert s["sebep"][1] == ["low_quality"]


def test_veto_yalniz_kalite_gerekceli_cizimsiz_sayfayi_geri_ceker():
    s = _sec(_bayrak(), kalite=60.0, veto=True)
    assert s["agir_sayfalar"] == []
    assert s["sebep"][1] == []


def test_cizim_varsa_veto_calismaz():
    """bezier_egri > 0 = karmasik duzen; vetonun dayandigi varsayim bozulur."""
    s = _sec(_bayrak(kaynak={"bezier_egri": 3}), kalite=60.0, veto=True)
    assert s["agir_sayfalar"] == [1]


def test_tablo_gerekcesi_varsa_veto_dokunmaz():
    """Gerekce yalniz low_quality DEGILSE sayfa agir kalmali."""
    s = _sec(_bayrak(has_table=True, tablo_guven="yuksek"), kalite=60.0, veto=True)
    assert s["agir_sayfalar"] == [1]
    assert "low_quality" in s["sebep"][1]


def test_ocr_gerekcesi_varsa_veto_dokunmaz():
    s = _sec(_bayrak(needs_ocr=True), kalite=60.0, veto=True)
    assert s["agir_sayfalar"] == [1]


def test_kritik_teshis_varsa_veto_dokunmaz():
    s = sayfa_secici({1: _bayrak()}, {1: 60.0}, kalite_vetosu_cizimsiz=True,
                     kritik={1: "TOTAL_TEXT_DROPPED"})
    assert s["agir_sayfalar"] == [1]


def test_bezier_olculmemisse_veto_calismaz():
    """Eksik olcumu 'cizim yok' saymak sayfayi sessizce hizli yolda birakirdi."""
    s = _sec(_bayrak(kaynak={}), kalite=60.0, veto=True)
    assert s["agir_sayfalar"] == [1]


def test_kalite_esigin_ustundeyse_zaten_agir_degil():
    s = _sec(_bayrak(), kalite=90.0, veto=True)
    assert s["agir_sayfalar"] == []
    assert s["sebep"][1] == []


def test_ozet_veto_durumunu_bildiriyor():
    s = _sec(_bayrak(), kalite=60.0, veto=True)
    assert s["ozet"]["kalite_vetosu_cizimsiz"] is True
