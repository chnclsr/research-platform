"""
Harness'ın kendini kanıtladığı üç kontrol.

BUNLAR NEDEN VAR. Bir workload'ın "ölçeklenmiyor" çıkması iki şeyden biri olabilir:
kütüphane gerçekten tek çekirdeğe sıkışıyordur, ya da HARNESS yanlış ölçüyordur.
İkisini ayırmanın tek yolu, sonucu önceden bilinen işleri aynı harness'tan geçirmektir.
Bu üçü beklenen sonucu vermiyorsa hiçbir gerçek ölçüm güvenilir değildir.

ÜÇÜ AYRI İSİMDEDİR ve ayrı şeyleri kanıtlar -- ilk taslakta tek bir `time.sleep`
kontrolü vardı ve o bir throughput kontrolü sanılıyordu. Değil: sleep hiç CPU işi
yapmaz, yalnız harness'ın paralelliği görebildiğini gösterir.

    control_io_like        sleep. CPU işi YOK. Harness N thread'i gerçekten aynı anda
                           koşturabiliyor mu? Ölçeklenmezse hata harness'tadır.
    control_gil_bound      saf-Python döngü. GIL çekişmesi görülebiliyor mu?
                           Ölçeklenirse harness çekişmeyi kaçırıyordur.
    control_gil_releasing  büyük blok hashlib. GIL bırakan C işi görülebiliyor mu?
                           Ölçeklenmezse harness paralel CPU işini kaçırıyordur.
"""

from __future__ import annotations

import hashlib
import time

from .contract import KAYIT, Workload

#: sleep süresi. Tek çağrı kısa tutulur; batch kalibrasyonu hedef süreye çıkarır.
UYKU_SN = 0.002

#: Saf-Python döngünün tur sayısı. Tek çağrı ~1 ms mertebesinde kalsın diye seçildi;
#: kesin değeri önemli değil, batch kalibrasyonu geri kalanı halleder.
DONGU_TURU = 20_000

#: hashlib'e verilen blok. GIL'in bırakılması için blok yeterince büyük olmalı --
#: küçük bloklarda çağrı maliyeti işin önüne geçer ve kontrol yanlış sonuç verir.
HASH_BLOGU = b"x" * (4 * 1024 * 1024)


# --- control_io_like ---------------------------------------------------------------

def _io_kurulum_process() -> object:
    return UYKU_SN


def _io_kurulum_worker(shared: object) -> object:
    return shared


def _io_cagri(state: object) -> object:
    time.sleep(float(state))  # type: ignore[arg-type]
    return None


def _io_digest(sonuc: object) -> str:
    return "none"


# --- control_gil_bound -------------------------------------------------------------

def _dongu_kurulum_process() -> object:
    return DONGU_TURU


def _dongu_kurulum_worker(shared: object) -> object:
    return shared


def _dongu_cagri(state: object) -> object:
    # Bilinçli olarak saf Python: her bytecode adımı GIL tutar. Toplamın kendisi
    # önemsiz, ama derleyicinin işi atmasını engellemek için döndürülür.
    toplam = 0
    for i in range(int(state)):  # type: ignore[arg-type]
        toplam += i * i % 7
    return toplam


def _dongu_digest(sonuc: object) -> str:
    return str(sonuc)


# --- control_gil_releasing ---------------------------------------------------------

def _hash_kurulum_process() -> object:
    return HASH_BLOGU


def _hash_kurulum_worker(shared: object) -> object:
    return shared


def _hash_cagri(state: object) -> object:
    return hashlib.sha256(state).hexdigest()  # type: ignore[arg-type]


def _hash_digest(sonuc: object) -> str:
    return str(sonuc)


CONTROL_IO_LIKE = KAYIT.ekle(Workload(
    name="control_io_like",
    category="control",
    setup_process=_io_kurulum_process,
    setup_worker=_io_kurulum_worker,
    call=_io_cagri,
    canonicalize=_io_digest,
    # float, DEGISMEZ_TIPLER içinde -- paylaşmak güvenli.
    state_scope="shared",
    shared_reason="state yalnız bir float (uyku süresi); değiştirilemez",
    expected="linear",
))

CONTROL_GIL_BOUND = KAYIT.ekle(Workload(
    name="control_gil_bound",
    category="control",
    setup_process=_dongu_kurulum_process,
    setup_worker=_dongu_kurulum_worker,
    call=_dongu_cagri,
    canonicalize=_dongu_digest,
    state_scope="shared",
    shared_reason="state yalnız bir int (tur sayısı); değiştirilemez",
    expected="flat",
))

CONTROL_GIL_RELEASING = KAYIT.ekle(Workload(
    name="control_gil_releasing",
    category="control",
    setup_process=_hash_kurulum_process,
    setup_worker=_hash_kurulum_worker,
    call=_hash_cagri,
    canonicalize=_hash_digest,
    state_scope="shared",
    shared_reason="state salt-okunur bytes; hashlib onu değiştirmez",
    expected="linear",
))

#: `self_check` bu eşikleri kullanır. Gerekçeleri:
#:   io_like       sleep paralelleşmiyorsa harness thread'leri gerçekten aynı anda
#:                 koşturmuyordur. 4 thread'de en az 3x bekleriz; 4.0 değil, çünkü
#:                 barrier ve zamanlayıcı gürültüsü payı var.
#:   gil_bound     saf Python 4 thread'de hızlanmamalı. 1.5 üstü, harness'ın işi
#:                 gerçekten paralel koşturmadığına ya da döngünün optimize edildiğine
#:                 işarettir.
#:   gil_releasing hashlib GIL bırakır; 4 thread'de en az 2.5x. Altındaysa harness
#:                 paralel CPU işini göremiyordur.
ESIKLER = {
    "control_io_like": ("scaling(4) >=", 3.0),
    "control_gil_bound": ("scaling(4) <=", 1.5),
    "control_gil_releasing": ("scaling(4) >=", 2.5),
}
