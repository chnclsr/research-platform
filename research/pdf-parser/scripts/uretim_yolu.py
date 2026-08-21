"""
Ölçüm betiklerinin ÜRETİM smart_router paketini bulmasını sağlar.

Neden: kod iki yerde durursa kısa sürede birbirinden kopar. Bir oturumda
yaşandı — `tools/smart_router/orchestrator.py` ile üretim kopyası 16 satır
ayrıldı, çünkü değişiklik yalnız birine yapılmıştı. Tek kaynak:

    research-platform/src/research_platform/parsers/smart_router/

`tools/smart_router/` altında yalnız ÖLÇÜLEN ama üretime girmeyen şeyler kalır:
`router.py` (legacy 17 özellikli skor), `benchmark.py` (mentörün dosyası),
`pipeline.py` (uyumluluk sarmalayıcısı), `docs/`.

Depo yeri `RESEARCH_PLATFORM_SRC` ile değiştirilebilir; varsayılan bu dosyanın
içinde bulunduğu research-platform klonudur.
"""
import os
import sys

CALIBRATION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(CALIBRATION_ROOT))

#: Üretim kaynağı. Klon başka yerdeyse ortam değişkeniyle ez.
URETIM_SRC = os.environ.get(
    "RESEARCH_PLATFORM_SRC",
    os.path.join(REPO_ROOT, "src"),
)


def ekle():
    """Üretim paketini ve bu araştırmanın script/legacy yollarını ekler."""
    if not os.path.isdir(URETIM_SRC):
        raise RuntimeError(
            f"Uretim kaynagi bulunamadi: {URETIM_SRC}\n"
            "Depoyu klonla ya da RESEARCH_PLATFORM_SRC ortam degiskenini ayarla."
        )
    for yol in (URETIM_SRC, os.path.join(CALIBRATION_ROOT, "scripts"),
                os.path.join(CALIBRATION_ROOT, "smart_router")):
        if yol not in sys.path:
            sys.path.insert(0, yol)
    return URETIM_SRC
