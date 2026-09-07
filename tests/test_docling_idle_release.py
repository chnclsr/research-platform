"""Docling servisinin boşta VRAM bırakma kancası.

torch önbelleğe aldığı bloğu kendiliğinden geri vermiyor; servis resident olduğu için
VRAM yalnızca yukarı tırmanıyor (2026-09-04 ölçümü: iki günlük servis 4818 MiB, tek
dönüşüm tepesi 1838 MiB). Buradaki testler kancanın yalnızca gerçekten boştayken
çalıştığını ve borcu bir kez kapattığını doğruluyor.
"""

from __future__ import annotations

import enum
import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVIS = Path(__file__).resolve().parents[1] / "scripts" / "docling_service.py"


class _Cihaz(enum.Enum):
    CUDA = "cuda"
    CPU = "cpu"


def _sahte_moduller(sayac: dict) -> dict:
    """torch ve docling kurulu değil (yalnız docling imajında var), yerlerine vekil."""

    cuda = SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda i: "Sahte Kart",
        memory_reserved=lambda: sayac["reserved"],
        empty_cache=lambda: sayac.__setitem__("empty_cache", sayac["empty_cache"] + 1),
    )
    torch = SimpleNamespace(cuda=cuda, __version__="0.0-test")

    pipeline_options = SimpleNamespace(
        AcceleratorDevice=_Cihaz,
        AcceleratorOptions=lambda **kw: SimpleNamespace(**kw),
        PdfPipelineOptions=lambda: SimpleNamespace(
            accelerator_options=None, artifacts_path=None
        ),
    )
    converter = SimpleNamespace(
        DocumentConverter=lambda **kw: SimpleNamespace(
            convert=lambda *a, **k: None, initialize_pipeline=lambda fmt: None
        ),
        PdfFormatOption=lambda **kw: SimpleNamespace(**kw),
    )
    return {
        "torch": torch,
        "docling": SimpleNamespace(),
        "docling.datamodel": SimpleNamespace(),
        "docling.datamodel.base_models": SimpleNamespace(
            InputFormat=SimpleNamespace(PDF="pdf")
        ),
        "docling.datamodel.pipeline_options": pipeline_options,
        "docling.document_converter": converter,
        "_docling_worker": SimpleNamespace(_table_grid=lambda t: {}),
    }


@pytest.fixture
def servis(monkeypatch):
    """Stub'lanmış bağımlılıklarla docling_service'i taze yükler."""
    sayac = {"empty_cache": 0, "reserved": 4818 * 1024 * 1024}
    for ad, mod in _sahte_moduller(sayac).items():
        monkeypatch.setitem(sys.modules, ad, mod)
    monkeypatch.setenv("DOCLING_DEVICE", "cuda")
    monkeypatch.setenv("DOCLING_IDLE_RELEASE_S", "0.01")
    monkeypatch.setenv("DOCLING_IDLE_POLL_S", "0.01")
    monkeypatch.delitem(sys.modules, "docling_service", raising=False)

    spec = importlib.util.spec_from_file_location("docling_service", SERVIS)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "docling_service", mod)
    spec.loader.exec_module(mod)
    mod._sayac = sayac
    return mod


def test_bosta_birakma_onbellegi_geri_verir(servis):
    servis._isi_isaretle()
    olcum = servis._bosta_serbest_birak()

    assert servis._sayac["empty_cache"] == 1
    assert olcum is not None
    assert olcum["reserved_before"] == 4818 * 1024 * 1024


def test_donusum_surerken_kart_birakilmaz(servis):
    """Kapı doluysa süpürme sırasını beklemeli, dönüşümle yarışmamalı."""
    servis._KAPI.acquire()
    try:
        assert servis._bosta_serbest_birak() is None
        assert servis._sayac["empty_cache"] == 0
    finally:
        servis._KAPI.release()


def test_cpu_kurulumunda_kanca_calismaz(servis):
    servis._DEVICE = _Cihaz.CPU
    assert servis._bosta_serbest_birak() is None
    assert servis._sayac["empty_cache"] == 0


def test_gozcu_bosta_bir_kez_supurur(servis):
    """Boşta kalan servis kendini sonsuza dek CUDA'ya çağırmamalı."""
    threading.Thread(target=servis._gozcu, daemon=True).start()

    servis._isi_isaretle()
    for _ in range(200):
        if servis._serbest_sayisi == 1:
            break
        time.sleep(0.01)

    assert servis._serbest_sayisi == 1
    time.sleep(0.15)
    assert servis._serbest_sayisi == 1, "borç kapandıktan sonra tekrar süpürmemeli"


def test_her_donusum_yeni_bir_supurme_hak_eder(servis):
    threading.Thread(target=servis._gozcu, daemon=True).start()

    for beklenen in (1, 2):
        servis._isi_isaretle()
        for _ in range(200):
            if servis._serbest_sayisi == beklenen:
                break
            time.sleep(0.01)
        assert servis._serbest_sayisi == beklenen
