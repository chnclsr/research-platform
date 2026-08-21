"""C1 cache ve dogrulama kosulari icin ortak, deterministik orneklem secimi."""
from __future__ import annotations

# CODEX-2026-08-18: Cache ve dogrulayicinin farkli ilk-N belgeleri secmesini
# engeller; kucuk kosularda tur/zorluk/tablo kovalarini dengeli dolasir.

PDF_PARSE = "pdf_parse"
METIN_REFERANSI = "metin_referansi"


def sec(kayitlar: list[dict], kimlikler: list[str] | None, limit: int,
        datasets: list[str] | None = None) -> list[dict]:
    dataset_set = set(datasets or [])
    uygun = [
        kayit for kayit in kayitlar
        if {PDF_PARSE, METIN_REFERANSI} <= set(kayit.get("yetenekler") or [])
        and (not dataset_set or kayit.get("veri_seti") in dataset_set)
    ]
    if kimlikler:
        istenen = set(kimlikler)
        uygun = [kayit for kayit in uygun if kayit.get("kimlik") in istenen]

    kovalar: dict[tuple, list[dict]] = {}
    for kayit in uygun:
        ust, etiket = kayit.get("ustveri") or {}, kayit.get("etiketler") or {}
        anahtar = (ust.get("tur"), ust.get("zorluk"), bool(etiket.get("tablo")))
        kovalar.setdefault(anahtar, []).append(kayit)

    secili = []
    while kovalar:
        for anahtar in sorted(list(kovalar), key=str):
            secili.append(kovalar[anahtar].pop(0))
            if not kovalar[anahtar]:
                del kovalar[anahtar]
            if limit and len(secili) >= limit:
                return secili
    return secili
