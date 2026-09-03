"""Bileşen CPU örnekleyicisinin hata üretmeye açık saf hesapları."""

from __future__ import annotations

from subprocess import CompletedProcess

import scripts.sample_container_cpu as sampler


def test_host_pidleri_ortusen_processleri_bir_kez_sayar(monkeypatch):
    """`ollama` deseni llama-server'ı da yakalasa aynı PID iki gruba yazılmamalı."""
    ciktilar = {"ollama": "10 20\n", "llama-server": "20 30\n"}

    def fake_run(args, **_kwargs):
        return CompletedProcess(args, 0, stdout=ciktilar[args[-1]], stderr="")

    monkeypatch.setattr(sampler.subprocess, "run", fake_run)

    assert sampler.host_pidleri(["ollama", "llama-server"]) == {
        "host:ollama": [10, 20],
        "host:llama-server": [30],
    }


def test_grup_usec_yok_olan_processi_toplama_katmaz(monkeypatch):
    degerler = {10: 120, 20: -1, 30: 80}
    monkeypatch.setattr(sampler, "_tek_process_usec", degerler.__getitem__)

    assert sampler._grup_usec([10, 20, 30]) == 200


def test_ozetle_eksik_bileseni_sifir_sayar():
    ornekler = [
        {"konteyner_cekirdek": {"worker": 1.0}},
        {"konteyner_cekirdek": {}},
        {"konteyner_cekirdek": {"worker": 2.0}},
    ]

    assert sampler._ozetle(ornekler)["worker"] == {
        "ort": 1.0,
        "p95": 2.0,
        "maks": 2.0,
    }


def test_ozetle_bilesenleri_birbirinden_ayirir():
    ornekler = [
        {"konteyner_cekirdek": {"worker": 0.2, "llama": 4.0}},
        {"konteyner_cekirdek": {"worker": 0.4, "llama": 6.0}},
    ]

    ozet = sampler._ozetle(ornekler)
    assert ozet["worker"]["ort"] == 0.3
    assert ozet["llama"]["ort"] == 5.0
