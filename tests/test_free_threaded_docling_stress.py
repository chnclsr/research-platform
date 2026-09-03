"""Docling stres koşucusunun converter paylaşımı ve hata kapıları."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import scripts.run_free_threaded_docling_stress as stress


class _SahteConverter:
    def convert(self, pdf: Path):
        belge = SimpleNamespace(export_to_markdown=lambda: f"sabit:{pdf.name}")
        return SimpleNamespace(document=belge)


def test_shared_mod_tek_converter_kullanir(monkeypatch, tmp_path):
    monkeypatch.setattr(stress, "_gil_etkin_mi", lambda: False)
    sayac = 0

    def factory():
        nonlocal sayac
        sayac += 1
        return _SahteConverter()

    sonuc = stress.thread_vakasi(factory, tmp_path / "a.pdf", "shared", 4, 3)
    assert sayac == 1
    assert sonuc["operations"] == 12
    assert sonuc["digest_divergence"] is False


def test_per_thread_mod_her_worker_icin_converter_kullanir(monkeypatch, tmp_path):
    monkeypatch.setattr(stress, "_gil_etkin_mi", lambda: False)
    sayac = 0

    def factory():
        nonlocal sayac
        sayac += 1
        return _SahteConverter()

    sonuc = stress.thread_vakasi(factory, tmp_path / "a.pdf", "per_thread", 4, 2)
    assert sayac == 5  # referans + dört worker
    assert sonuc["operations"] == 8


def test_sinyalle_kapanma_crash_olarak_siniflanir():
    assert stress._siniflandir(-11, "", "segfault")["status"] == "process_crash"


def test_klasik_python_gil_api_yokken_basarili_cocuk_gecer(monkeypatch, tmp_path, capsys):
    def sahte_vaka(_factory, _pdf, mode, threads, reps):
        return {
            "mode": mode,
            "threads": threads,
            "reps_per_thread": reps,
            "ok": True,
            "digest_divergence": False,
            "gil_enabled_at_end": None,
        }

    monkeypatch.setattr(stress, "thread_vakasi", sahte_vaka)
    monkeypatch.setattr(stress.importlib.metadata, "version", lambda _name: "2.120.1")

    assert stress.child(tmp_path / "a.pdf", "per_thread", 1, 1, expected_gil=True) == 0
    assert '"gil_status_api_available": false' in capsys.readouterr().out


def test_parent_timeoutu_deadlock_suphesi_sayar(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"pdf")

    def zaman_asimi(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["python"], 1.0, output="", stderr="askida")

    monkeypatch.setattr(stress.subprocess, "run", zaman_asimi)
    sonuc = stress.parent(pdf, ["shared"], [8], reps=1, timeout_s=1.0)
    assert sonuc["passed"] is False
    assert sonuc["cases"][0]["status"] == "deadlock_suspected"


def test_klasik_referans_ayni_pdf_ve_digest_ister():
    vaka = {"status": "passed", "mode": "shared", "threads": 4,
            "result": {"digest": "sha256:ayni"}}
    sonuc = stress.referansla_karsilastir(
        {"passed": True, "input_sha256": "pdf", "cases": [vaka]},
        {"python": "3.14", "input_sha256": "pdf", "cases": [vaka]},
    )
    assert sonuc["passed"] is True
    assert sonuc["reference_comparison"]["digest_mismatches"] == []


def test_klasik_referans_farkli_pdfyi_reddeder():
    vaka = {"status": "passed", "mode": "shared", "threads": 2,
            "result": {"digest": "sha256:ayni"}}
    sonuc = stress.referansla_karsilastir(
        {"passed": True, "input_sha256": "a", "cases": [vaka]},
        {"input_sha256": "b", "cases": [vaka]},
    )
    assert sonuc["passed"] is False
    assert sonuc["reference_comparison"]["same_input"] is False
