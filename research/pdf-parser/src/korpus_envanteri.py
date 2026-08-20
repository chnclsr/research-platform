"""
Korpus envanteri cikarir -- C1 dogrulama kosusunun girdi listesi.

C1 ("yonlendirme ciktiyi gercekten iyilestiriyor mu") kosulmadan once tek bir
sorunun net cevabi lazim: ELIMIZDE NE VAR, hangisi hangi ise yarar. Uc veri
seti indirildi ve ucu de farkli seyler veriyor; ikisinde PDF hic yok. Bu betik
o uc seti tek bir manifestoya cevirir, boylece C1 "hangi belgeleri kosayim"
sorusunu tahminle degil filtreyle cevaplar.

TASARIM KARARI -- ATLANAN SET DE ENVANTERE GIRER
------------------------------------------------
PDF'i olmayan set listeden DUSMEZ; atlama_sebebi ile birlikte gorunur kalir.
Sessiz atlama bu projede zaten bir kez zarar verdi (pipeline.py --legacy bos
metinle cikis 0 donuyordu, hata veriyor sanildi). Ayni ilke: bozunma gorunur
olacak. Boylece "1651 sayfa neden kullanilmadi" sorusunun cevabi manifestonun
kendi icinde durur.

CIKTI
-----
out/korpus_envanteri.jsonl   satir basina bir sayfa/belge kaydi
out/korpus_envanteri.json    ozet: sayimlar, dagilimlar, tespit edilen sorunlar

--kaynak / --limit verilirse cikti *_kismi.* dosyalarina gider; kanonik
manifesto eksik veriyle UZERINE YAZILMAZ.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\korpus_envanteri.py
    .\\.venv\\Scripts\\python.exe src\\korpus_envanteri.py --kaynak ocrturk
    .\\.venv\\Scripts\\python.exe src\\korpus_envanteri.py --hashsiz

Veri seti dosyalarina yazilmaz; betik yalnizca okur ve out/ altina yazar.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from korpus_kaynak import (  # noqa: E402
    KORPUS_KOK, MANIFEST_SCHEMA_VERSION, METIN_REFERANSI, PDF_PARSE,
    SAYFA_ETIKETI, kaynaklar,
)

OUT = os.path.join(BASE, "out")
JSONL = os.path.join(OUT, "korpus_envanteri.jsonl")
OZET = os.path.join(OUT, "korpus_envanteri.json")


def _ozet(kayitlar: list) -> dict:
    """
    Manifestoyu C1'in soracagi sorulara gore ozetler.

    Onemli olan toplam sayi degil, KESISIM: hem PDF'i hem referans metni olan
    kac belge var? C1 ancak o kesisimde kosulabilir.
    """
    setler: dict = {}
    for kayit in kayitlar:
        d = setler.setdefault(kayit["veri_seti"], {
            "kayit": 0, "pdf_parse": 0, "metin_referansi": 0,
            "sayfa_etiketi": 0, "c1_uygun": 0, "atlama": Counter(),
            "sayfa_dagilimi": Counter(), "belge_turu": Counter(),
            "zorluk": Counter(), "tablo_iceren": 0, "sekil_iceren": 0,
            "denklem_iceren": 0, "toplam_bayt": 0,
        })
        yetenek = set(kayit["yetenekler"])
        d["kayit"] += 1
        for ad in ("pdf_parse", "metin_referansi", "sayfa_etiketi"):
            if ad in yetenek:
                d[ad] += 1
        if {PDF_PARSE, METIN_REFERANSI} <= yetenek:
            d["c1_uygun"] += 1
        if kayit.get("atlama_sebebi"):
            d["atlama"][kayit["atlama_sebebi"]] += 1
        if kayit.get("sayfa_sayisi") is not None:
            d["sayfa_dagilimi"][kayit["sayfa_sayisi"]] += 1
        d["toplam_bayt"] += kayit.get("pdf_bayt") or 0
        ust = kayit.get("ustveri") or {}
        if ust.get("belge_turu") or ust.get("tur"):
            d["belge_turu"][ust.get("belge_turu") or ust.get("tur")] += 1
        if ust.get("zorluk"):
            d["zorluk"][ust["zorluk"]] += 1
        etiket = kayit.get("etiketler") or {}
        for anahtar, alan in (("tablo", "tablo_iceren"), ("sekil", "sekil_iceren"),
                              ("denklem", "denklem_iceren")):
            if (etiket.get(anahtar) or 0) > 0:
                d[alan] += 1

    for d in setler.values():
        d["atlama"] = dict(d["atlama"])
        d["sayfa_dagilimi"] = {str(k): v for k, v in sorted(d["sayfa_dagilimi"].items())}
        d["belge_turu"] = dict(d["belge_turu"].most_common())
        d["zorluk"] = dict(d["zorluk"].most_common())
    return setler


def _uyarilar(kayitlar: list, setler: dict) -> list:
    """
    Manifestonun kendisinden okunabilen supheli noktalar.

    Rapora elle yazilan uyari eskir; buradakiler her kosuda yeniden olculur.
    """
    uyari = []
    c1 = [k for k in kayitlar
          if {PDF_PARSE, METIN_REFERANSI} <= set(k["yetenekler"])]
    if not c1:
        uyari.append("C1 kosulamaz: PDF ve referans metni birlikte olan kayit yok.")

    cok_sayfali = [k for k in c1 if (k.get("sayfa_sayisi") or 0) > 1]
    if c1 and not cok_sayfali:
        uyari.append(
            "C1'e uygun %d kaydin TAMAMI tek sayfali. Sayfa sinirini asan "
            "mekanizmalar (kosan baslik, sayfa sinirinda bolunen cumle, ardisik "
            "blok gruplama) bu setle SINANAMAZ." % len(c1)
        )

    # Etiket ile referans metin celisiyor mu: "tablo var" diyen belgenin
    # referansinda tablo izi yoksa o referans C1'de tabloyu puanlayamaz.
    celiski = [k["kimlik"] for k in c1
               if (k.get("etiketler", {}).get("tablo") or 0) > 0
               and (k.get("referans", {}).get("tablo_izi") or 0) == 0]
    if celiski:
        uyari.append(
            "%d belgede etiket tablo diyor ama referans metinde tablo izi yok "
            "(ornek: %s). Bu belgelerde tablo kalitesi olculemez."
            % (len(celiski), ", ".join(celiski[:5]))
        )

    bos = [k["kimlik"] for k in c1 if (k.get("referans", {}).get("karakter") or 0) < 200]
    if bos:
        uyari.append(
            "%d belgenin referans metni 200 karakterden kisa (ornek: %s) -- "
            "puanlamada gurultu yapar." % (len(bos), ", ".join(bos[:5]))
        )

    hashsiz = [k for k in kayitlar if PDF_PARSE in k["yetenekler"] and not k.get("pdf_sha256")]
    if hashsiz:
        uyari.append(
            "%d PDF icin sha256 yok -- C1 kosusunun ayni baytlarla yapildigi "
            "sonradan kanitlanamaz." % len(hashsiz)
        )

    # CODEX-2026-08-18: Manifestte yazan bir varlik yolu gercekte yoksa bunu
    # sonraki runner'in sessizce atlamasina birakma.
    sorunlu = [k for k in kayitlar if k.get("sorunlar")]
    if sorunlu:
        uyari.append(
            "%d kayitta dosya/annotasyon sorunu var (ornek: %s)."
            % (len(sorunlu), ", ".join(k["kimlik"] for k in sorunlu[:5]))
        )

    doclaynet = [k for k in kayitlar if k["veri_seti"] == "doclaynet"]
    ad_sayimi = Counter(os.path.basename((k.get("ustveri") or {}).get("gorsel", ""))
                        for k in doclaynet)
    tekrar = sum(v - 1 for ad, v in ad_sayimi.items() if ad and v > 1)
    if tekrar:
        uyari.append(
            "DocLayNet alt kumelerinde %d tekrar sayfa goruntusu var; toplam kayit "
            "sayisi benzersiz sayfa sayisi degildir." % tekrar
        )

    for ad, d in setler.items():
        if d["kayit"] and not d["pdf_parse"]:
            uyari.append(
                "%s: %d kaydin hicbirinde PDF yok (%s). Yalnizca duzen sinyali "
                "olarak kullanilabilir." % (ad, d["kayit"], d["atlama"])
            )
    return uyari


# CODEX-2026-08-18: Kesilen bir kosu kanonik manifesti yarim birakmasin.
def _atomik_yaz(yol: str, metin: str) -> None:
    gecici = yol + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8", newline="") as f:
            f.write(metin)
        os.replace(gecici, yol)
    finally:
        if os.path.exists(gecici):
            os.unlink(gecici)


def main() -> int:
    ayrist = argparse.ArgumentParser(description="Korpus envanteri cikarir.")
    ayrist.add_argument("--kaynak", action="append", default=None,
                        choices=["ocrturk", "doclaynet", "omnidocbench",
                                 "opendataloader_bench"],
                        help="yalniz bu veri setini tara (birden fazla verilebilir)")
    ayrist.add_argument("--hashsiz", action="store_true",
                        help="PDF sha256 hesaplama (hizli, ama girdi kaniti olmaz)")
    ayrist.add_argument("--limit", type=int, default=0,
                        help="veri seti basina en fazla N kayit (deneme icin)")
    arg = ayrist.parse_args()

    if not os.path.isdir(KORPUS_KOK):
        print("Korpus koku bulunamadi: %s" % KORPUS_KOK)
        print("KORPUS_RAW ortam degiskeniyle baska bir yol verebilirsin.")
        return 2

    os.makedirs(OUT, exist_ok=True)
    # Kisitli kosu kanonik manifestonun UZERINE YAZMAZ. `--kaynak ocrturk` ile
    # bir deneme yapip sonra C1'i calistirmak, C1'e 180 kayitlik bir dosyayi tam
    # envanter diye yutturur -- hata vermeden, eksik girdiyle.
    kismi = bool(arg.kaynak or arg.limit)
    jsonl, ozet_yolu = (JSONL, OZET)
    if kismi:
        jsonl = JSONL.replace(".jsonl", "_kismi.jsonl")
        ozet_yolu = OZET.replace(".json", "_kismi.json")

    print("korpus koku : %s" % KORPUS_KOK)
    if kismi:
        print("KISMI KOSU  : cikti *_kismi.* dosyalarina yaziliyor")

    t0 = time.perf_counter()
    kayitlar = []
    durum = {}
    for kaynak in kaynaklar(hash_hesapla=not arg.hashsiz):
        if arg.kaynak and kaynak.ad not in arg.kaynak:
            continue
        if not kaynak.mevcut():
            # Set indirilmemis olabilir; bu bir hata degil, eksik girdi.
            durum[kaynak.ad] = "bulunamadi"
            print("  %-14s BULUNAMADI -- atlandi" % kaynak.ad)
            continue
        basla = time.perf_counter()
        alinan = 0
        for kayit in kaynak.kayitlar():
            kayitlar.append(kayit.sozluk())
            alinan += 1
            if arg.limit and alinan >= arg.limit:
                break
        durum[kaynak.ad] = "tarandi"
        print("  %-14s %5d kayit  (%.1f sn)"
              % (kaynak.ad, alinan, time.perf_counter() - basla))

    satirlar = "".join(json.dumps(k, ensure_ascii=False) + "\n" for k in kayitlar)
    _atomik_yaz(jsonl, satirlar)

    setler = _ozet(kayitlar)
    uyari = _uyarilar(kayitlar, setler)
    ozet = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "uretim_zamani": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "korpus_koku": KORPUS_KOK.replace("\\", "/"),
        "manifest": os.path.relpath(jsonl, BASE).replace("\\", "/"),
        "kismi_kosu": kismi,
        "hash_hesaplandi": not arg.hashsiz,
        "toplam_kayit": len(kayitlar),
        "kaynak_durumu": durum,
        "veri_setleri": setler,
        "uyarilar": uyari,
    }
    _atomik_yaz(ozet_yolu, json.dumps(ozet, ensure_ascii=False, indent=2) + "\n")

    print("\n%-14s %7s %9s %9s %9s %9s"
          % ("veri seti", "kayit", "pdf", "referans", "etiket", "C1 uygun"))
    for ad, d in setler.items():
        print("%-14s %7d %9d %9d %9d %9d"
              % (ad, d["kayit"], d["pdf_parse"], d["metin_referansi"],
                 d["sayfa_etiketi"], d["c1_uygun"]))

    if uyari:
        print("\nUYARILAR")
        for satir in uyari:
            print("  - %s" % satir)

    print("\nmanifest : %s" % jsonl)
    print("ozet     : %s" % ozet_yolu)
    print("sure     : %.1f sn" % (time.perf_counter() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
