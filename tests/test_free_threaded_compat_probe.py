"""Free-threaded ortam kapısının yanlış pozitif vermesini önleyen testler."""

from __future__ import annotations

import warnings

import scripts.probe_free_threaded_compat as probe


def _basarili_import(_ad: str):
    return object()


def test_tum_importlar_ve_gil_kapaliysa_kapi_gecer(monkeypatch):
    monkeypatch.setattr(probe, "free_threaded_build_mi", lambda: True)
    monkeypatch.setattr(probe, "gil_etkin_mi", lambda: False)

    sonuc = probe.ortam_kapisi(_basarili_import, lambda ad: f"{ad}-1.0")

    assert sonuc["passed"] is True
    assert [p["module"] for p in sonuc["packages"]] == ["numpy", "torch", "docling"]


def test_klasik_yorumlayici_reddedilir(monkeypatch):
    monkeypatch.setattr(probe, "free_threaded_build_mi", lambda: False)
    monkeypatch.setattr(probe, "gil_etkin_mi", lambda: True)

    assert probe.ortam_kapisi(_basarili_import, lambda _ad: "1.0")["passed"] is False


def test_import_gili_sonradan_acarsa_reddedilir(monkeypatch):
    durumlar = iter((False, False, True, True, True))
    monkeypatch.setattr(probe, "free_threaded_build_mi", lambda: True)
    monkeypatch.setattr(probe, "gil_etkin_mi", lambda: next(durumlar))

    sonuc = probe.ortam_kapisi(_basarili_import, lambda _ad: "1.0")

    assert sonuc["passed"] is False
    assert sonuc["packages"][1]["gil_enabled_after_import"] is True


def test_import_hatasi_kaydedilir_ve_kapi_reddedilir(monkeypatch):
    monkeypatch.setattr(probe, "free_threaded_build_mi", lambda: True)
    monkeypatch.setattr(probe, "gil_etkin_mi", lambda: False)

    def import_et(ad: str):
        if ad == "torch":
            raise ImportError("uyumlu wheel yok")
        return object()

    sonuc = probe.ortam_kapisi(import_et, lambda _ad: "1.0")

    assert sonuc["passed"] is False
    assert sonuc["packages"][1]["error"] == "ImportError: uyumlu wheel yok"


def test_import_uyarilari_kanita_yazilir(monkeypatch):
    monkeypatch.setattr(probe, "free_threaded_build_mi", lambda: True)
    monkeypatch.setattr(probe, "gil_etkin_mi", lambda: False)

    def uyarili_import(_ad: str):
        warnings.warn("GIL yeniden etkinleştirildi", RuntimeWarning, stacklevel=2)
        return object()

    sonuc = probe.ortam_kapisi(uyarili_import, lambda _ad: "1.0")

    assert sonuc["packages"][0]["warnings"] == ["GIL yeniden etkinleştirildi"]
