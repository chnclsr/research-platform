"""
Ölçüm betiklerinin ÜRETİM smart_router paketini bulmasını sağlar.

Neden: kod iki yerde durursa kısa sürede birbirinden kopar. Bir oturumda
yaşandı — `tools/smart_router/orchestrator.py` ile üretim kopyası 16 satır
ayrıldı, çünkü değişiklik yalnız birine yapılmıştı. Tek kaynak:

    research-platform/src/research_platform/parsers/smart_router/

2026-08-20: Bu dosya (ve yanındaki `korpus_kaynak.py`, `c1_*.py`) daha önce
`sude-staj` deposunda (git'e hiç girmeyen, yerel bir klasörde) yaşıyordu.
Ölçüm kodunun tek, doğru ve git'e pushlanan yerde durması için
`research-platform/research/pdf-parser/src/` altına taşındı — bkz.
entegrasyon_plani.md Bölüm 17 ("kodlar tek ve doğru yerde senkron olsun").
Artık bu dosya `research-platform`'un KENDİ İÇİNDE duruyor (kardeş depo değil),
bu yüzden üretim kaynağı iki üst dizine çıkılarak bulunuyor:
`research/pdf-parser/src/` -> `research/pdf-parser` -> `research` ->
`research-platform` -> `src`.

Depo yapısı başka bir yere taşınırsa `RESEARCH_PLATFORM_SRC` ortam
değişkeniyle ezilebilir.
"""
import os
import sys

#: Bu dosyanin bulundugu yer: research-platform/research/pdf-parser/src
OLCUM_SRC = os.path.dirname(os.path.abspath(__file__))
#: research-platform/research/pdf-parser
OLCUM_KOK = os.path.dirname(OLCUM_SRC)
#: research-platform (research/pdf-parser'in iki ust dizini)
DEPO_KOKU = os.path.dirname(os.path.dirname(OLCUM_KOK))

#: Üretim kaynağı. Klon başka yerdeyse ortam değişkeniyle ez.
URETIM_SRC = os.environ.get(
    "RESEARCH_PLATFORM_SRC",
    os.path.join(DEPO_KOKU, "src"),
)


def ekle():
    """Üretim paketini ve ölçüm `src/`'ini yola ekler."""
    if not os.path.isdir(URETIM_SRC):
        raise RuntimeError(
            f"Uretim kaynagi bulunamadi: {URETIM_SRC}\n"
            "Depoyu klonla ya da RESEARCH_PLATFORM_SRC ortam degiskenini ayarla."
        )
    for yol in (URETIM_SRC, OLCUM_SRC):
        if yol not in sys.path:
            sys.path.insert(0, yol)
    return URETIM_SRC
