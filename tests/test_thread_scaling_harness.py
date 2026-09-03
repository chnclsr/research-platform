"""
Harness'ın mekaniği doğru mu: state kapsamı, bariyer, sayaçlar, formüller.

Bu dosya performans ÖLÇMEZ ve makine hızına dayalı eşik içermez -- gerçek eşikler
`benchmark_thread_scaling.py self_check` içindedir. Buradaki testler sahte workload'lar
kullanır ve deterministiktir; tek istisna, bariyerin eşzamanlılığını sınayan testin
cömert bir üst sınır kullanmasıdır (gerçek zamanlama olmadan bariyer sınanamaz).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "research" / "gil-scaling"))
sys.path.insert(0, str(KOK / "scripts"))

import benchmark_thread_scaling as harness
from workloads.contract import Workload


def _sayan_workload(**degisiklik) -> tuple[Workload, dict]:
    """setup_worker ve call çağrılarını sayan bir sahte workload."""
    sayac = {"setup_worker": 0, "call": 0, "threadler": set()}
    kilit = threading.Lock()

    def _setup_worker(shared):
        with kilit:
            sayac["setup_worker"] += 1
        return {"deger": 0}

    def _call(state):
        with kilit:
            sayac["call"] += 1
            sayac["threadler"].add(threading.get_ident())
        state["deger"] += 1
        return state["deger"]

    varsayilan = {
        "name": "sahte",
        "category": "test",
        "setup_process": lambda: b"shared",
        "setup_worker": _setup_worker,
        "call": _call,
        "canonicalize": lambda sonuc: "sabit",
    }
    varsayilan.update(degisiklik)
    return Workload(**varsayilan), sayac  # type: ignore[arg-type]


def test_per_thread_state_her_worker_icin_ayri_kurulur():
    """Production'da koşular nesne paylaşmaz; harness bunu yansıtmalı."""
    w, sayac = _sayan_workload()
    harness.olc_bir_kez(w, w.setup_process(), threads=4, batch=3)
    assert sayac["setup_worker"] == 4


def test_shared_state_bir_kez_kurulur():
    """`shared` kapsamda setup_worker 4 thread icin degil, BIR kez cagrilir."""
    sayac = {"n": 0}

    def _setup_worker(shared):
        sayac["n"] += 1
        return shared          # bytes -> degismez tip, sozlesmeye uyar

    w = Workload(
        name="sahte_shared",
        category="test",
        setup_process=lambda: b"shared",
        setup_worker=_setup_worker,
        call=lambda state: len(state),
        canonicalize=lambda sonuc: str(sonuc),
        state_scope="shared",
        shared_reason="salt-okunur bytes",
    )
    harness.olc_bir_kez(w, w.setup_process(), threads=4, batch=3)
    assert sayac["n"] == 1


def test_butun_threadler_gercekten_kosuyor():
    w, sayac = _sayan_workload()
    harness.olc_bir_kez(w, w.setup_process(), threads=8, batch=2)
    assert len(sayac["threadler"]) == 8


def test_ops_sayimi_thread_carpi_batch():
    w, sayac = _sayan_workload()
    m = harness.olc_bir_kez(w, w.setup_process(), threads=4, batch=5)
    assert m["ops_ok"] == 20
    assert m["ops_failed"] == 0
    assert sayac["call"] == 20


def test_setup_worker_zamanlama_disinda():
    """Yavaş bir kurulum duvar saatine yansımamalı -- ölçülen `call`, kurulum değil."""
    def _yavas_kurulum(shared):
        time.sleep(0.05)
        return {}

    w, _ = _sayan_workload(setup_worker=_yavas_kurulum)
    m = harness.olc_bir_kez(w, w.setup_process(), threads=4, batch=1)
    # 4 x 50 ms kurulum ölçüme girseydi duvar saati en az 200 ms olurdu.
    assert m["wall_ns"] < 100_000_000


def test_bariyer_threadleri_ayni_anda_baslatiyor():
    """Bariyer olmasaydı ilk thread son thread'den çok önce başlardı."""
    baslangiclar = []
    kilit = threading.Lock()

    def _call(state):
        with kilit:
            baslangiclar.append(time.perf_counter_ns())
        time.sleep(0.02)
        return 1

    w, _ = _sayan_workload(call=_call)
    harness.olc_bir_kez(w, w.setup_process(), threads=8, batch=1)
    yayilma_ms = (max(baslangiclar) - min(baslangiclar)) / 1e6
    # Comert ust sinir: bariyer calisiyorsa yayilma milisaniye mertebesinde kalir.
    assert yayilma_ms < 50, f"threadler {yayilma_ms:.1f} ms araliga yayildi"


def test_hata_yakalanip_sonuca_yaziliyor():
    def _patlayan(state):
        raise ValueError("bilerek")

    w, _ = _sayan_workload(call=_patlayan)
    m = harness.olc_bir_kez(w, w.setup_process(), threads=2, batch=5)
    assert m["ops_ok"] == 0
    assert m["ops_failed"] == 10
    assert "ValueError: bilerek" in m["exception"]


def test_digest_ayrismasi_isaretleniyor():
    """İki worker farklı sonuç üretirse bu bir bulgudur, sessizce geçilmez."""
    def _threade_gore(sonuc):
        return f"digest-{threading.get_ident()}"

    w, _ = _sayan_workload(canonicalize=_threade_gore)
    m = harness.olc_bir_kez(w, w.setup_process(), threads=4, batch=1)
    assert m["digest_divergence"] is True

    w2, _ = _sayan_workload()
    m2 = harness.olc_bir_kez(w2, w2.setup_process(), threads=4, batch=1)
    assert m2["digest_divergence"] is False
    assert m2["result_digest"] == "sabit"


def test_ham_alanlar_eksiksiz():
    """Rapor scripti bu alanları bekliyor; biri düşerse orada değil burada bilinsin."""
    w, _ = _sayan_workload()
    m = harness.olc_bir_kez(w, w.setup_process(), threads=2, batch=2)
    beklenen = {
        "workload", "threads", "batch", "ops_ok", "ops_failed", "exception",
        "wall_ns", "thread_time_ns_total", "per_thread_ns", "process_cpu_ns",
        "child_cpu_ns", "rss_start", "rss_end", "result_digest",
        "digest_divergence", "load_at_start",
    }
    assert beklenen <= set(m)
    assert len(m["per_thread_ns"]) == 2
    assert m["process_cpu_ns"] >= 0


def test_kalibrasyon_uzun_cagride_batch_bir_birakir():
    """Tek çağrısı hedeften uzun olan workload'da batch=1 meşrudur."""
    def _uzun(state):
        time.sleep(0.25)
        return 1

    w, _ = _sayan_workload(call=_uzun)
    batch, olcumler = harness.kalibre_et(w, w.setup_process())
    assert batch == 1
    assert olcumler


def test_kalibrasyon_kisa_cagriyi_buyutur():
    """Çok kısa bir çağrı thread/future maliyetinin yanında kaybolmasın diye
    batch büyütülmeli."""
    w, _ = _sayan_workload(call=lambda state: 1)
    batch, _ = harness.kalibre_et(w, w.setup_process())
    assert batch > 100


def test_olcekleme_formulu():
    """throughput(N)/throughput(1); medyan üzerinden."""
    sonuc = {"measurements": [
        # N=1: 100 op / 100 ns  -> 1.0 op/ns
        {"workload": "w", "threads": 1, "ops_ok": 100, "wall_ns": 100},
        {"workload": "w", "threads": 1, "ops_ok": 100, "wall_ns": 100},
        # N=4: 400 op / 100 ns  -> 4.0 op/ns  => scaling 4.0
        {"workload": "w", "threads": 4, "ops_ok": 400, "wall_ns": 100},
        {"workload": "w", "threads": 4, "ops_ok": 400, "wall_ns": 100},
        # baska bir workload karismmali
        {"workload": "diger", "threads": 1, "ops_ok": 1, "wall_ns": 1},
    ]}
    olcek = harness.olcekleme(sonuc, "w")
    assert olcek[1] == 1.0
    assert olcek[4] == 4.0


def test_olcekleme_taban_yoksa_bos_doner():
    sonuc = {"measurements": [
        {"workload": "w", "threads": 4, "ops_ok": 400, "wall_ns": 100},
    ]}
    assert harness.olcekleme(sonuc, "w") == {}


def test_medyan():
    assert harness._medyan([]) == 0.0
    assert harness._medyan([5.0]) == 5.0
    assert harness._medyan([1.0, 3.0]) == 2.0
    assert harness._medyan([3.0, 1.0, 2.0]) == 2.0
