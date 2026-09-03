"""
Workload sözleşmesinin ihlalleri ölçüm başlamadan yakalanıyor mu.

Bu dosya performans ÖLÇMEZ. Gerçek makine eşikleri
`benchmark_thread_scaling.py self_check` içindedir; onları pytest'e koymak CI'da
flaky olurdu. Buradaki her test deterministiktir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "research" / "gil-scaling"))

from workloads.contract import (
    Kayit,
    SozlesmeHatasi,
    Workload,
    dogrula,
    dogrula_digest,
    dogrula_paylasilan_state,
)


def _wl(**degisiklik) -> Workload:
    varsayilan = {
        "name": "test_wl",
        "category": "test",
        "setup_process": lambda: b"veri",
        "setup_worker": lambda shared: shared,
        "call": lambda state: state,
        "canonicalize": lambda sonuc: "sabit",
    }
    varsayilan.update(degisiklik)
    return Workload(**varsayilan)  # type: ignore[arg-type]


def test_bos_ad_reddedilir():
    with pytest.raises(SozlesmeHatasi, match="boş"):
        dogrula(_wl(name="  "))


def test_bilinmeyen_kapsam_reddedilir():
    with pytest.raises(SozlesmeHatasi, match="state_scope"):
        dogrula(_wl(state_scope="global"))


def test_shared_kapsam_gerekce_ister():
    """Paylaşılan state varsayılan değil; nedeni yazılmadan kabul edilmez."""
    with pytest.raises(SozlesmeHatasi, match="shared_reason"):
        dogrula(_wl(state_scope="shared"))


def test_shared_kapsam_gerekceyle_gecer():
    dogrula(_wl(state_scope="shared", shared_reason="salt-okunur bytes"))


def test_varsayilan_kapsam_per_thread():
    """Production'da koşular nesne paylaşmıyor; varsayılan bunu yansıtmalı."""
    assert _wl().state_scope == "per_thread"


def test_sifir_batch_reddedilir():
    with pytest.raises(SozlesmeHatasi, match="batch"):
        dogrula(_wl(batch=0))


def test_shared_state_degismez_tip_olmali():
    """`shared` ilan edilmiş ama mutable dönen bir setup yakalanmalı."""
    w = _wl(state_scope="shared", shared_reason="gerekce")
    dogrula_paylasilan_state(w, b"bytes tamam")
    dogrula_paylasilan_state(w, ("tuple", "tamam"))
    with pytest.raises(SozlesmeHatasi, match="dict"):
        dogrula_paylasilan_state(w, {"mutable": True})
    with pytest.raises(SozlesmeHatasi, match="list"):
        dogrula_paylasilan_state(w, [1, 2, 3])


def test_per_thread_state_tip_denetimi_disinda():
    """per_thread state paylaşılmadığı için mutable olabilir."""
    dogrula_paylasilan_state(_wl(), {"mutable": True})


def test_canonicalize_str_dondurmeli():
    w = _wl(canonicalize=lambda sonuc: 42)
    with pytest.raises(SozlesmeHatasi, match="int döndürdü"):
        dogrula_digest(w, "girdi")


def test_canonicalize_deterministik_olmali():
    sayac = {"n": 0}

    def _kararsiz(sonuc):
        sayac["n"] += 1
        return f"digest-{sayac['n']}"

    with pytest.raises(SozlesmeHatasi, match="deterministik değil"):
        dogrula_digest(_wl(canonicalize=_kararsiz), "girdi")


def test_canonicalize_gecerliyse_digest_doner():
    assert dogrula_digest(_wl(), "girdi") == "sabit"


def test_ad_cakismasi_kayit_aninda_yakalanir():
    kayit = Kayit()
    kayit.ekle(_wl(name="ayni"))
    with pytest.raises(SozlesmeHatasi, match="zaten kayıtlı"):
        kayit.ekle(_wl(name="ayni"))


def test_kayit_kategoriye_gore_filtreler():
    kayit = Kayit()
    kayit.ekle(_wl(name="a", category="parser"))
    kayit.ekle(_wl(name="b", category="parser"))
    kayit.ekle(_wl(name="c", category="control"))
    assert len(kayit) == 3
    assert {w.name for w in kayit.kategori("parser")} == {"a", "b"}


def test_bilinmeyen_ad_acik_hata_verir():
    kayit = Kayit()
    kayit.ekle(_wl(name="var"))
    with pytest.raises(KeyError, match="var"):
        kayit.al("yok")


def test_kontroller_sozlesmeye_uyuyor():
    """Üç pozitif kontrol de kendi sözleşmesini geçmeli."""
    from workloads import controls
    from workloads.contract import KAYIT

    kontroller = KAYIT.kategori("control")
    assert {w.name for w in kontroller} == set(controls.ESIKLER)
    for w in kontroller:
        dogrula(w)
        shared = w.setup_process()
        state = w.setup_worker(shared)
        dogrula_paylasilan_state(w, state)
        dogrula_digest(w, w.call(state))
