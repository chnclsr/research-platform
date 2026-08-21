"""Aday "heavy'den fayda dusuk" vetolarini KOD DEGISTIRMEDEN offline dener.

`sinyal_ayrim.py` sinyallerin ayrim gucu oldugunu gosterdiyse, sirada "hangi
kural" sorusu var. Ama gate.py'yi degistirip tam replay kosmak her aday icin
pahali ve gereksiz: veto yalnizca AGIR MOTORA GIDEN sayfalari geri cekebilir,
yeni sayfa EKLEYEMEZ. Dolayisiyla etkisi mevcut kosunun tahminlerinden birebir
hesaplanabilir -- vetolanan sayfa fast'te kalir, o belgenin routed utility'si
fast utility'sine doner.

BU BIR SINIRLAMA TASIR: hesap yalnizca TEK SAYFALI belgelerde tam dogrudur (C1
korpusunun tamami oyle, korpus_kaynak.py'de olculdu). Cok sayfali bir belgede
bir sayfayi geri cekmek belge utility'sini kismen degistirir; oradaki tek dogru
yol gercek replay'dir.

DIKKAT: burada bulunan hicbir kural "kabul edildi" sayilmaz. Ayni korpusta hem
kural arayip hem basari ilan etmek projenin kendi kuralini (Q13) ihlal eder.
Bu script aday URETIR; dogrulama dokunulmamis holdout ister.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\veto_dene.py \\
        --run tolerans5_uygulandi_20260821
    -> out/veto_denemeleri.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KOSULAR = os.path.join(BASE, "out", "c1_runs")
FAYDA_ESIK = 0.02


def _oku(run: str) -> dict:
    yol = os.path.join(KOSULAR, run, "predictions.jsonl")
    son = {}
    with open(yol, encoding="utf-8") as f:
        for s in f:
            if s.strip():
                r = json.loads(s)
                if r.get("id"):
                    son[r["id"]] = r
    return {k: r for k, r in son.items() if r.get("status") == "ok"}


def _sayfa_bilgisi(r: dict) -> dict:
    """Agir motora giden ilk sayfanin sinyalleri (C1'de belge = tek sayfa)."""
    for s in r["route"]["pages"]:
        if s.get("karar_kaynagi"):
            g = s.get("gate_signals") or {}
            return {
                "gerekce": s.get("karar_kaynagi") or [],
                "kalite": s.get("quality_score"),
                "has_table": bool(s.get("has_table")),
                "has_figure": bool(s.get("has_figure")),
                "needs_ocr": bool(s.get("needs_ocr")),
                "kritik": (s.get("critical_issue") or "NONE") != "NONE",
                "bezier_egri": g.get("bezier_egri") or 0,
                "ortogonal_cizgi": g.get("ortogonal_cizgi") or 0,
                "karakter": g.get("karakter") or 0,
                "izgara_satir": g.get("izgara_satir") or 0,
                "tablo_v2": bool(g.get("tablo_v2")),
                "tablo_inspector": bool(g.get("tablo_inspector")),
            }
    return {}


# Aday vetolar. Her biri: (ad, aciklama, sayfa_bilgisi -> True ise HEAVY'E GITME)
# Hepsi yalniz YAPISAL sinyallere bakar; "dil == en" gibi bir korpus bayragi
# bilerek YOK -- 72 belgelik tek bir benchmark'in kompozisyonunu ezberlerdi.
#
# Her adayin bir HIPOTEZI var; kombinasyon taramasi degil. Sebep: 101 agir sayfa
# uzerinde yeterince kural denenirse biri tesadufen iyi cikar. Aday sayisini
# hipotezle sinirlamak, "hicbir ailede zarar verme" cubugunu anlamli tutuyor.
#
# Sinyallerin ayrim gucu (sinyal_ayrim.py, AUC): ocrturk'te ortogonal_cizgi
# 0,7691 en guclu; opendataloader'da bezier_egri 0,8268 ve karakter 0,7357.
# quality_score ocrturk'te tam rastgele (0,5006) -- bu yuzden kalite gerekcesi
# tek basina degil, hep bir yapisal kosulla birlikte deneniyor.
ADAYLAR = [
    # -- kalite gerekcesi tek basina (referans: neyi kaybediyoruz)
    ("lq_tek", "yalniz low_quality ile gelen sayfayi gonderme",
     lambda s: s["gerekce"] == ["low_quality"]),
    # -- kalite gerekcesi + "burada karmasik duzen yok" kosullari
    ("lq_tek_cizimsiz", "yalniz low_quality VE hic vektorel cizim yok",
     lambda s: s["gerekce"] == ["low_quality"] and s["bezier_egri"] == 0),
    ("lq_tek_cizim_az", "yalniz low_quality VE bezier_egri < 5",
     lambda s: s["gerekce"] == ["low_quality"] and s["bezier_egri"] < 5),
    ("lq_tek_cizgisiz", "yalniz low_quality VE ortogonal cizgi yok",
     lambda s: s["gerekce"] == ["low_quality"] and s["ortogonal_cizgi"] == 0),
    ("lq_tek_duz", "yalniz low_quality VE ne cizim ne ortogonal cizgi",
     lambda s: (s["gerekce"] == ["low_quality"] and s["bezier_egri"] == 0
                and s["ortogonal_cizgi"] == 0)),
    ("lq_tek_tablosuz", "yalniz low_quality VE tablo sinyali yok",
     lambda s: s["gerekce"] == ["low_quality"] and not s["has_table"]),
    ("lq_tek_cizimsiz_kisa", "yalniz low_quality VE cizim yok VE < 1500 karakter",
     lambda s: (s["gerekce"] == ["low_quality"] and s["bezier_egri"] == 0
                and s["karakter"] < 1500)),
    # -- kalite gerekcesinden bagimsiz yapisal vetolar
    ("cizimsiz_tablosuz", "hic bezier egri yok VE ortogonal cizgi yok",
     lambda s: s["bezier_egri"] == 0 and s["ortogonal_cizgi"] == 0),
    ("kisa_sayfa", "fast metin 1500 karakterden kisa ve kritik sorun yok",
     lambda s: s["karakter"] < 1500 and not s["kritik"] and not s["needs_ocr"]),
    ("kisa_cizimsiz", "< 1500 karakter VE hic vektorel cizim yok VE kritik yok",
     lambda s: (s["karakter"] < 1500 and s["bezier_egri"] == 0
                and not s["kritik"] and not s["needs_ocr"])),
    ("yogun_izgara", "izgara_satir >= 8 (yogun satir yapisi)",
     lambda s: s["izgara_satir"] >= 8),
]

#: `lq_tek_cizimsiz`in bezier esigi bir SECIM'di (0). Komsu degerler de
#: taranir; kural yalniz tek bir esikte calisiyorsa bu, sinyalden cok
#: gurultuye uyum isaretidir.
ESIK_TARAMASI = [0, 1, 2, 5, 10, 25]


def degerlendir(kayitlar: dict, kural, ids: list[str]) -> dict:
    """Veto uygulanirsa NET, precision, recall ve agir cagri ne olur."""
    net = 0.0
    heavy = 0
    veto = 0
    veto_kayip = 0.0     # vetolanan sayfa aslinda faydaliymis
    veto_kazanc = 0.0    # vetolanan sayfa zaten zararliymis
    dogru = kazanan = 0
    for k in ids:
        r = kayitlar[k]
        fayda = r["delta"]["heavy_minus_fast"]
        if fayda >= FAYDA_ESIK:
            kazanan += 1
        if not r["route"]["routed_heavy"]:
            continue
        s = _sayfa_bilgisi(r)
        if s and kural and kural(s):
            veto += 1
            # Sayfa fast'te kalir: o belgenin katkisi 0 olur.
            if fayda >= FAYDA_ESIK:
                veto_kayip += r["delta"]["routed_minus_fast"]
            else:
                veto_kazanc += -r["delta"]["routed_minus_fast"]
            continue
        heavy += 1
        net += r["delta"]["routed_minus_fast"]
        if fayda >= FAYDA_ESIK:
            dogru += 1
    return {
        "heavy": heavy, "veto": veto, "net": net,
        "precision": (dogru / heavy) if heavy else 0.0,
        "recall": (dogru / kazanan) if kazanan else 0.0,
        "veto_kayip": veto_kayip, "veto_kazanc": veto_kazanc,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Aday veto kurallarini offline dene")
    p.add_argument("--run", required=True)
    p.add_argument("--cikti", default=os.path.join(BASE, "out", "veto_denemeleri.json"))
    args = p.parse_args()

    kayitlar = _oku(args.run)
    ids = sorted(kayitlar)
    aileler = sorted({kayitlar[k]["dataset"] for k in ids})
    grup = {a: [k for k in ids if kayitlar[k]["dataset"] == a] for a in aileler}
    grup["BIRLESIK"] = ids

    sonuc = {"run": args.run, "adaylar": []}
    taban = {a: degerlendir(kayitlar, None, g) for a, g in grup.items()}

    for ad, aciklama, kural in ADAYLAR:
        olcum = {a: degerlendir(kayitlar, kural, g) for a, g in grup.items()}
        # Bir aday ancak HICBIR ailede NET dusurmuyorsa ilerletilebilir;
        # birlesik iyilesme tek basina yeterli degil (rapor O.8.3).
        zararsiz = all(olcum[a]["net"] >= taban[a]["net"] - 1e-9 for a in aileler)
        sonuc["adaylar"].append({
            "ad": ad, "aciklama": aciklama, "olcum": olcum,
            "hicbir_ailede_zarar_yok": zararsiz,
        })

    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump({"taban": taban, **sonuc}, f, ensure_ascii=False, indent=2)

    for a in aileler + ["BIRLESIK"]:
        t = taban[a]
        print("\n=== %s ===  taban: heavy=%d NET=%+.4f prec=%.4f rec=%.4f"
              % (a, t["heavy"], t["net"], t["precision"], t["recall"]))
        print("%-18s %6s %6s %10s %9s %8s %8s  %s" %
              ("aday", "heavy", "veto", "NET", "ΔNET", "prec", "recall", "veto kayip/kazanc"))
        for c in sonuc["adaylar"]:
            m = c["olcum"][a]
            print("%-18s %6d %6d %+10.4f %+9.4f %8.4f %8.4f  -%.4f / +%.4f"
                  % (c["ad"], m["heavy"], m["veto"], m["net"], m["net"] - t["net"],
                     m["precision"], m["recall"], m["veto_kayip"], m["veto_kazanc"]))

    # --- esik duyarliligi: kural yalniz tek bir esikte mi calisiyor?
    print("\n=== ESIK DUYARLILIGI: lq_tek VE bezier_egri < E ===")
    print("%6s %8s %10s %10s %10s  %s" %
          ("E", "veto", "ΔNET ocr", "ΔNET odl", "ΔNET birl", "zararsiz"))
    sonuc["esik_taramasi"] = []
    for esik in ESIK_TARAMASI:
        kural = (lambda e: (lambda s: s["gerekce"] == ["low_quality"]
                            and s["bezier_egri"] < max(e, 1) if e else
                            (s["gerekce"] == ["low_quality"] and s["bezier_egri"] == 0)))(esik)
        olcum = {a: degerlendir(kayitlar, kural, g) for a, g in grup.items()}
        zararsiz = all(olcum[a]["net"] >= taban[a]["net"] - 1e-9 for a in aileler)
        satir = {"esik": esik, "olcum": olcum, "zararsiz": zararsiz}
        sonuc["esik_taramasi"].append(satir)
        print("%6d %8d %+10.4f %+10.4f %+10.4f  %s" %
              (esik, olcum["BIRLESIK"]["veto"],
               olcum[aileler[0]]["net"] - taban[aileler[0]]["net"],
               olcum[aileler[1]]["net"] - taban[aileler[1]]["net"],
               olcum["BIRLESIK"]["net"] - taban["BIRLESIK"]["net"],
               "evet" if zararsiz else "HAYIR"))

    print("\n--- hicbir ailede NET dusurmeyen adaylar ---")
    gecen = [c for c in sonuc["adaylar"] if c["hicbir_ailede_zarar_yok"]]
    if not gecen:
        print("  YOK -- her aday en az bir veri ailesine zarar veriyor")
    for c in gecen:
        m = c["olcum"]["BIRLESIK"]
        print("  %-22s ΔNET %+.4f  veto %d  prec %.4f  %s"
              % (c["ad"], m["net"] - taban["BIRLESIK"]["net"], m["veto"],
                 m["precision"], c["aciklama"]))
    print("\nNOT: bu adaylar KABUL EDILMIS degildir; dogrulama dokunulmamis")
    print("holdout ister (Q13). Ayni korpusta hem arayip hem ilan etme.")
    print("yazildi: %s" % args.cikti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
