"""
Parse hattının saf-Python / C sınırındaki sıcak çağrıları.

BU LİSTE NİHAİ DEĞİL. Başlangıç adaylarıdır: Aşama 2'nin gerçek profili başka bir yeri
gösterirse buraya eklenir ve ölçüm tekrar koşar. Gerekçe: REPORT.md.

PRODUCTION AKIŞINA SADIK KALINIYOR. orchestrator.calistir() sırası şu:

    insp   = PdfInspectorAdapter.extract_pages(pdf_path)
    bayrak = kapi.bayrakla(pdf_path, insp=insp)          <- insp GEÇİRİLİR
    degerl = critic.evaluate_pages({...}, sayfalar, ...)
    secim  = sayfa_secici(bayraklar, kalite, ...)

`bayrakla`'ya `insp` geçirmek kozmetik değil: geçirilmezse fonksiyon inspector'ı KENDİ
çağırır ve aynı PDF iki kez taranır. gate.py'nin kendi docstring'i bunu A9 borcu olarak
anlatıyor -- ölçülen kapı maliyeti bir zamanlar o fazladan geçişi içeriyordu. Aynı hatayı
ölçüm tarafında tekrarlamamak için burada da geçiriliyor.

GATE İKİ AYRI WORKLOAD'DIR. `bayrakla` pymupdf.open() ile belgeyi gerçekten tarar;
`sayfa_secici` yalnız hazır sözlükler üzerinde karar verir. İkisini tek isim altında
ölçmek, ucuz olanı pahalı olanın arkasına saklardı.

STATE KAPSAMI. PDF yolları `shared` (str, değişmez). Ama inspector SONUÇLARI per_thread:
production'da her koşunun kendi InspectorSonuc'u vardır, ve `bayrakla` ona
`source_text_by_page` yazabilir. Paylaşmak yapay çekişme üretirdi.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(KOK / "src"))

from research_platform.parsers.smart_router.critic import PDFCritic
from research_platform.parsers.smart_router.gate import GirisKapisi, sayfa_secici
from research_platform.parsers.smart_router.inspector import PdfInspectorAdapter
from research_platform.parsers.smart_router.merge import birlestir
from research_platform.passages import chunk_document

from .contract import KAYIT, Workload

#: Ölçüm belgesi. Korpustan orta boy, iki sütunlu, dipnotlu bir makale -- uç bir
#: örnek (75 sayfalık gpt3, ya da 6 sayfalık taranmış) tek başına ölçülürse sonuç o
#: belgenin özelliğine kayar. Belge adı sonuca yazılır; başkasıyla koşmak
#: GIL_SCALING_PDF ile mümkün.
VARSAYILAN_PDF = KOK / "research" / "pdf-parser" / "corpus" / "kendi" / "bert_2sutun_dipnot.pdf"


def _pdf_yolu() -> str:
    import os

    return os.environ.get("GIL_SCALING_PDF") or str(VARSAYILAN_PDF)


def _digest(deger: Any) -> str:
    return hashlib.sha256(repr(deger).encode("utf-8", "replace")).hexdigest()[:16]


# --- inspector.extract_pages -------------------------------------------------------

def _insp_setup_process() -> object:
    return _pdf_yolu()


def _insp_setup_worker(shared: object) -> object:
    return shared  # yalnız yol; str, değişmez


def _insp_call(state: object) -> object:
    return PdfInspectorAdapter.extract_pages(str(state))


def _insp_digest(sonuc: object) -> str:
    # Sayfa sayısı + metnin hash'i: aynı belgeyi aynı şekilde çıkardık mı.
    return _digest((len(sonuc.pages), sonuc.text))  # type: ignore[union-attr]


# --- gate.bayrakla -----------------------------------------------------------------

def _bayrakla_setup_process() -> object:
    return _pdf_yolu()


def _bayrakla_setup_worker(shared: object) -> object:
    # Production'da her koşunun KENDİ inspector sonucu ve KENDİ kapısı var.
    yol = str(shared)
    return (yol, GirisKapisi(), PdfInspectorAdapter.extract_pages(yol))


def _bayrakla_call(state: object) -> object:
    yol, kapi, insp = state  # type: ignore[misc]
    return kapi.bayrakla(yol, insp=insp)


def _bayrak_digest(sonuc: object) -> str:
    bayraklar: dict[int, Any] = sonuc  # type: ignore[assignment]
    return _digest(sorted((no, sorted(b.sozluk().items())) for no, b in bayraklar.items()))


# --- gate.sayfa_secici -------------------------------------------------------------

def _secici_setup_process() -> object:
    yol = _pdf_yolu()
    insp = PdfInspectorAdapter.extract_pages(yol)
    bayraklar = GirisKapisi().bayrakla(yol, insp=insp)
    kalite = {no: 80.0 for no in bayraklar}
    return (bayraklar, kalite)


def _secici_setup_worker(shared: object) -> object:
    # sayfa_secici girdilerini DEĞİŞTİRMEZ, ama sözleşme gereği yine de kopya
    # verilmiyor: paylaşım "shared" ilan edilmediği için her worker aynı
    # nesneyi alır ve bu bilinçli -- girdiler salt-okunur kullanılıyor.
    return shared


def _secici_call(state: object) -> object:
    bayraklar, kalite = state  # type: ignore[misc]
    return sayfa_secici(bayraklar, kalite)


def _secici_digest(sonuc: object) -> str:
    return _digest(sorted(sonuc.get("agir_sayfalar", [])))  # type: ignore[union-attr]


# --- critic.evaluate_pages ---------------------------------------------------------

def _critic_setup_process() -> object:
    yol = _pdf_yolu()
    insp = PdfInspectorAdapter.extract_pages(yol)
    bayraklar = GirisKapisi().bayrakla(yol, insp=insp)
    sayfalar: list[tuple[int, str]] = [(s.sayfa_no, s.markdown) for s in insp.pages]
    ham_karakter = {no: b.kaynak.get("karakter", 0) for no, b in bayraklar.items()}
    bayrak_sozluk = {no: b.sozluk() for no, b in bayraklar.items()}
    return (yol, sayfalar, ham_karakter, bayrak_sozluk)


def _critic_setup_worker(shared: object) -> object:
    yol, sayfalar, ham_karakter, bayrak_sozluk = shared  # type: ignore[misc]
    # PDFCritic per_thread: production'da her koşu kendi örneğini kurar.
    return (PDFCritic(), yol, sayfalar, ham_karakter, bayrak_sozluk)


def _critic_call(state: object) -> object:
    critic, yol, sayfalar, ham_karakter, bayrak_sozluk = state  # type: ignore[misc]
    return critic.evaluate_pages(
        {"pdf_path": yol}, sayfalar,
        ham_karakter=ham_karakter, bayraklar=bayrak_sozluk,
    )


def _critic_digest(sonuc: object) -> str:
    sayfalar = sonuc.get("sayfalar", [])  # type: ignore[union-attr]
    return _digest([(s["sayfa_no"], s["quality_score"], s["critical_issue"])
                    for s in sayfalar])


# --- merge.birlestir ---------------------------------------------------------------

def _merge_setup_process() -> object:
    insp = PdfInspectorAdapter.extract_pages(_pdf_yolu())
    return {s.sayfa_no: s.markdown for s in insp.pages}


def _merge_setup_worker(shared: object) -> object:
    # birlestir girdiyi tüketmez; sözlük her worker'a kopyalanıyor ki bir
    # yan etki çıkarsa o worker'da kalsın.
    return dict(shared)  # type: ignore[arg-type]


def _merge_call(state: object) -> object:
    # Ağır motor sonucu YOK: bu F2.1-a varyantı, yalnız hızlı yol. Yakalanmış
    # heavy çıktısıyla koşan F2.1-b Aşama 4'te eklenir.
    return birlestir(state, fast_engine="pdf-inspector")  # type: ignore[arg-type]


def _merge_digest(sonuc: object) -> str:
    return _digest(getattr(sonuc, "text", "") or repr(sonuc))


# --- passages.chunk_document -------------------------------------------------------

def _chunk_setup_process() -> object:
    return PdfInspectorAdapter.extract_pages(_pdf_yolu()).text


def _chunk_setup_worker(shared: object) -> object:
    return shared  # str, değişmez


def _chunk_call(state: object) -> object:
    return chunk_document(str(state), "GILSCALINGSOURCEVERSION0001")


def _chunk_digest(sonuc: object) -> str:
    # `Passage.id` her cagrida yeniden uretilir (default_factory=new_id), digest'e
    # GIRMEZ -- girseydi ayni girdi her kosuda farkli digest verirdi. Alinanlar
    # pipeline'in gercekten bagli oldugu alanlar: offsetler ve content_hash.
    passages: list[Any] = sonuc  # type: ignore[assignment]
    return _digest([(p.chunk_index, p.start_char, p.end_char, p.section_path,
                     p.content_hash) for p in passages])


KAYIT.ekle(Workload(
    name="inspector.extract_pages", category="parser",
    setup_process=_insp_setup_process, setup_worker=_insp_setup_worker,
    call=_insp_call, canonicalize=_insp_digest,
    state_scope="shared", shared_reason="state yalnız PDF yolu (str); çağrı onu değiştirmez",
))

KAYIT.ekle(Workload(
    name="gate.bayrakla", category="parser",
    setup_process=_bayrakla_setup_process, setup_worker=_bayrakla_setup_worker,
    call=_bayrakla_call, canonicalize=_bayrak_digest,
))

KAYIT.ekle(Workload(
    name="gate.sayfa_secici", category="parser",
    setup_process=_secici_setup_process, setup_worker=_secici_setup_worker,
    call=_secici_call, canonicalize=_secici_digest,
))

KAYIT.ekle(Workload(
    name="critic.evaluate_pages", category="parser",
    setup_process=_critic_setup_process, setup_worker=_critic_setup_worker,
    call=_critic_call, canonicalize=_critic_digest,
))

KAYIT.ekle(Workload(
    name="merge.birlestir", category="parser",
    setup_process=_merge_setup_process, setup_worker=_merge_setup_worker,
    call=_merge_call, canonicalize=_merge_digest,
))

KAYIT.ekle(Workload(
    name="passages.chunk_document", category="parser",
    setup_process=_chunk_setup_process, setup_worker=_chunk_setup_worker,
    call=_chunk_call, canonicalize=_chunk_digest,
    state_scope="shared", shared_reason="state belge metni (str); chunk onu değiştirmez",
))
