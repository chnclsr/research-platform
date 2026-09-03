"""Free-threaded stres koşucusunun süreç ve doğruluk kapıları."""

from __future__ import annotations

import json
import subprocess

import scripts.run_free_threaded_stress as stress


def test_thread_vakasi_tum_operasyonlari_kosar(monkeypatch):
    monkeypatch.setattr(stress, "_gil_etkin_mi", lambda: False)
    sonuc = stress.thread_vakasi(lambda: "sha256:sabit", threads=4, reps=3)
    assert sonuc["operations"] == 12
    assert sonuc["digest_count"] == 1
    assert sonuc["digest_divergence"] is False


def test_thread_vakasi_digest_ayrismasini_yakalar(monkeypatch):
    monkeypatch.setattr(stress, "_gil_etkin_mi", lambda: False)
    sayac = iter(("a", "b", "b"))
    sonuc = stress.thread_vakasi(lambda: next(sayac), threads=2, reps=1)
    assert sonuc["digest_divergence"] is True


def test_siniflandir_sinyali_crash_sayar():
    assert stress.siniflandir(-11, "", "segfault")["status"] == "process_crash"


def test_siniflandir_gecerli_basarili_child():
    stdout = json.dumps({"ok": True, "digest_divergence": False})
    assert stress.siniflandir(0, stdout, "")["status"] == "passed"


def test_siniflandir_python_hatasini_basarili_saymaz():
    stdout = json.dumps({"ok": False, "error": "RuntimeError: bilerek"})
    assert stress.siniflandir(1, stdout, "")["status"] == "error"


def test_siniflandir_bos_ciktiyi_yakalar():
    assert stress.siniflandir(1, "", "traceback")["status"] == "invalid_child_output"


def test_parent_timeoutu_deadlock_suphesi_sayar(monkeypatch):
    def zaman_asimi(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["python"], 1.0, output="", stderr="askida")

    monkeypatch.setattr(stress.subprocess, "run", zaman_asimi)
    sonuc = stress.parent(["numpy"], [4], reps=2, timeout_s=1.0)
    assert sonuc["passed"] is False
    assert sonuc["cases"][0]["status"] == "deadlock_suspected"


def test_referans_karsilastirmasi_esit_digestleri_kabul_eder():
    vaka = {"status": "passed", "workload": "numpy", "threads": 4,
            "result": {"digest": "sha256:ayni"}}
    sonuc = stress.referansla_karsilastir(
        {"passed": True, "cases": [vaka]}, {"python": "3.14", "cases": [vaka]})
    assert sonuc["passed"] is True
    assert sonuc["reference_comparison"]["digest_mismatches"] == []


def test_referans_karsilastirmasi_ayrismayi_reddeder():
    mevcut = {"status": "passed", "workload": "torch", "threads": 8,
              "result": {"digest": "sha256:yeni"}}
    eski = {"status": "passed", "workload": "torch", "threads": 8,
            "result": {"digest": "sha256:eski"}}
    sonuc = stress.referansla_karsilastir(
        {"passed": True, "cases": [mevcut]}, {"python": "3.14", "cases": [eski]})
    assert sonuc["passed"] is False
    assert sonuc["reference_comparison"]["digest_mismatches"][0]["threads"] == 8
