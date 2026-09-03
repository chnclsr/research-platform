"""
Ölçülecek her işin uyması gereken sözleşme.

NEDEN BU BİÇİM. İlk taslak tek bir state nesnesini bütün thread'lere paylaştırıyordu.
Bu production'ı temsil etmiyor: eşzamanlı araştırma koşuları aynı ConnectorCandidate'ı,
aynı SQLAlchemy session'ını ya da aynı render state'ini paylaşmaz -- her koşunun kendi
nesneleri vardır. Tek nesneyi paylaştırmak ölçüme ya yapay çekişme ya da yapay bir
thread-safety sorunu sokar, ve ikisi de kütüphanenin davranışı sanılır.

Bu yüzden kurulum ikiye ayrıldı:

    setup_process()        bir kez koşar; DEĞİŞMEZ fixture döndürür (yol, bytes, str)
    setup_worker(shared)   her worker için AYRI çalışma state'i kurar
    call(worker_state)     ölçülen tek sıcak çağrı
    canonicalize(result)   sonucun deterministik digest'i

`setup_worker` zamanlamanın dışındadır: ölçtüğümüz şey `call`, kurulum değil.

DIGEST NEDEN ZORUNLU. Free-threading hatası yalnız parser'da çıkmaz -- pydantic
çıktısında, gate kararında, passage offset'lerinde, ORM nesnesinde ve raporda da
çıkabilir. Her workload sonucunun digest'ini üretmek zorundadır ki kollar arası
karşılaştırma parser'a özel bir kontrol olmaktan çıksın.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

#: Çalışma state'inin kapsamı.
#:
#: "per_thread"  -- VARSAYILAN. setup_worker her worker için ayrı çağrılır. Production'da
#:                  koşular nesne paylaşmadığı için doğru model budur.
#: "shared"      -- setup_worker bir kez çağrılır, sonuç bütün worker'lara verilir.
#:                  YALNIZ gerçekten değişmez girdiler için (bytes, str, tuple, ...) ve
#:                  `shared_reason` doldurularak. Doğrulayıcı tipi denetler.
GECERLI_KAPSAM = ("per_thread", "shared")

#: `shared` kapsamında kabul edilen tipler. Bir nesnenin değişmezliğini genel olarak
#: kanıtlayamayız; kabul edilen tipleri saymak, "değişmez olduğunu varsaydık" demekten
#: daha dürüst bir sınır.
DEGISMEZ_TIPLER = (bytes, str, int, float, bool, tuple, frozenset, type(None))


class SozlesmeHatasi(ValueError):
    """Bir workload sözleşmeyi ihlal ediyor. Ölçüm başlamadan önce yükselir."""


@dataclass(frozen=True)
class Workload:
    """Ölçülecek tek bir sıcak iş."""

    name: str
    category: str
    setup_process: Callable[[], object]
    setup_worker: Callable[[object], object]
    call: Callable[[object], object]
    canonicalize: Callable[[object], str]
    state_scope: str = "per_thread"
    #: None ise otomatik kalibre edilir. Kalibrasyon N=1'de worker başına 200-500 ms
    #: hedefler; seçilen değer bütün N ve bütün kollarda sabitlenir.
    batch: int | None = None
    #: `state_scope == "shared"` ise zorunlu: neden paylaşmanın doğru olduğu.
    shared_reason: str = ""
    #: YALNIZ kontrollerde dolu ("linear" | "flat" | "partial"). Gerçek workload'larda
    #: None -- beklentiyi baştan yazmak sonucu kirletir.
    expected: str | None = None


def dogrula(workload: Workload) -> None:
    """Sözleşme ihlallerini ölçüm başlamadan önce yakalar."""
    if not workload.name.strip():
        raise SozlesmeHatasi("workload adı boş")
    if workload.state_scope not in GECERLI_KAPSAM:
        raise SozlesmeHatasi(
            f"{workload.name}: state_scope {workload.state_scope!r}, "
            f"beklenen {GECERLI_KAPSAM}"
        )
    if workload.state_scope == "shared" and not workload.shared_reason.strip():
        raise SozlesmeHatasi(
            f"{workload.name}: state_scope='shared' ise shared_reason zorunlu. "
            "Paylaşmanın neden doğru olduğu yazılmadan paylaşılan state kabul edilmez"
        )
    if workload.batch is not None and workload.batch < 1:
        raise SozlesmeHatasi(f"{workload.name}: batch {workload.batch}, en az 1 olmalı")


def dogrula_paylasilan_state(workload: Workload, state: object) -> None:
    """`shared` kapsamında state'in gerçekten değişmez bir tip olduğunu denetler.

    Ayrı bir fonksiyon, çünkü state ancak setup çalıştıktan sonra elde var; `dogrula`
    ise kayıt anında, setup koşmadan çalışır.
    """
    if workload.state_scope != "shared":
        return
    if not isinstance(state, DEGISMEZ_TIPLER):
        raise SozlesmeHatasi(
            f"{workload.name}: state_scope='shared' ama setup_worker "
            f"{type(state).__name__} döndürdü. Paylaşılan state yalnız "
            f"{[t.__name__ for t in DEGISMEZ_TIPLER]} olabilir"
        )


def dogrula_digest(workload: Workload, sonuc: object) -> str:
    """`canonicalize` gerçekten deterministik bir string üretiyor mu.

    İki kez çağırıp karşılaştırır. Bu bir thread-safety testi DEĞİLDİR -- ona per-thread
    state ile karşı konur; bu yalnız digest'in kendisinin kullanılabilir olduğunu
    doğrular.
    """
    birinci = workload.canonicalize(sonuc)
    if not isinstance(birinci, str):
        raise SozlesmeHatasi(
            f"{workload.name}: canonicalize {type(birinci).__name__} döndürdü, str bekleniyor"
        )
    ikinci = workload.canonicalize(sonuc)
    if birinci != ikinci:
        raise SozlesmeHatasi(
            f"{workload.name}: canonicalize deterministik değil, aynı sonuç için "
            f"iki farklı digest üretti"
        )
    return birinci


class Kayit:
    """Workload kaydı. Ad çakışması kayıt anında yakalanır."""

    def __init__(self) -> None:
        self._workloads: dict[str, Workload] = {}

    def ekle(self, workload: Workload) -> Workload:
        dogrula(workload)
        if workload.name in self._workloads:
            raise SozlesmeHatasi(f"{workload.name}: bu adla bir workload zaten kayıtlı")
        self._workloads[workload.name] = workload
        return workload

    def tumu(self) -> list[Workload]:
        return list(self._workloads.values())

    def kategori(self, category: str) -> list[Workload]:
        return [w for w in self._workloads.values() if w.category == category]

    def al(self, name: str) -> Workload:
        if name not in self._workloads:
            raise KeyError(f"{name}: kayıtlı değil. Kayıtlılar: {sorted(self._workloads)}")
        return self._workloads[name]

    def __len__(self) -> int:
        return len(self._workloads)


#: Süreç genelinde tek kayıt.
KAYIT = Kayit()
