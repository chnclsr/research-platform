"""Ağır motora giden sayfalarda hangi sinyal "heavy fayda sağlar mı"yı öngörüyor.

Bu bir KALIBRASYON degil, bir KESIF aracidir. Sordugu tek soru: bir kural
yazmadan once, elimizdeki sinyallerin ayrim gucu VAR MI. Yoksa yazacak kural da
yoktur ve holdout kurmaya gerek kalmaz.

Neden gerekli: C1'de agir motora giden 101 sayfanin 60'inda heavy aslinda daha
kotu cikti; opendataloader_bench tarafinda 43 cagrinin 35'i bosa ve o ailenin
NET'i -0,9842 -- yani orada yonlendirme zarar veriyor (rapor O.11.1). Eger
bir yapisal sinyal bu bosa cagrilari ayirabiliyorsa "heavy'den fayda dusuk"
vetosu yazilabilir; ayiramiyorsa dogru cevap veto degil, o veri ailesinde
politikayi tamamen degistirmek.

OLCUT: AUC (Mann-Whitney U). 0,5 = ayrim yok. Yon onemli degil, 0,5'ten UZAKLIK
onemli -- 0,3 de 0,7 kadar bilgilidir, isareti ters cevrilir. Kucuk orneklemde
AUC gurultuludur; bu yuzden her satirda pozitif/negatif sayilari da yazilir ve
veri ailesi ayri raporlanir (birlesik sayi iki rejimi gizler, rapor O.8.3).

DIKKAT -- bu script esik SECMEZ. Ayrim gucu bulursa bile, degeri secmek ve
dogrulamak ayri bir is ve dokunulmamis holdout ister (Q13).

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\sinyal_ayrim.py \\
        --run tolerans5_uygulandi_20260821
    -> out/sinyal_ayrim.json
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

#: "Heavy gercekten daha iyiydi" esigi -- c1_dogrulama.py ile ayni.
FAYDA_ESIK = 0.02

#: AUC bu kadar 0,5'ten uzaksa "bakmaya deger" sayilir. Kesin bir istatistik
#: degil, tarama esigi: altindakiler icin kural yazmanin anlami yok.
ILGINC_AUC = 0.10


def _oku(run: str) -> dict:
    yol = os.path.join(KOSULAR, run, "predictions.jsonl")
    if not os.path.isfile(yol):
        raise SystemExit("kosu bulunamadi: %s" % yol)
    son = {}
    with open(yol, encoding="utf-8") as f:
        for s in f:
            if s.strip():
                r = json.loads(s)
                if r.get("id"):
                    son[r["id"]] = r
    return {k: r for k, r in son.items() if r.get("status") == "ok"}


def auc(pozitif: list[float], negatif: list[float]) -> float | None:
    """Mann-Whitney U / (n1*n2). Beraberlikler yarim sayilir."""
    if not pozitif or not negatif:
        return None
    kazanc = 0.0
    for p in pozitif:
        for n in negatif:
            if p > n:
                kazanc += 1.0
            elif p == n:
                kazanc += 0.5
    return kazanc / (len(pozitif) * len(negatif))


def satirlar(kayitlar: dict) -> list[dict]:
    """Agir motora giden her sayfa icin sinyaller + gercek fayda etiketi.

    C1'in her belgesi tek sayfa oldugu icin (korpus_kaynak.py'de olculdu) belge
    utility'si sayfa faydasidir; cok sayfali bir sete GENELLENEMEZ.
    """
    cikti = []
    for kimlik, r in kayitlar.items():
        if not r["route"]["routed_heavy"]:
            continue
        fayda = r["delta"]["heavy_minus_fast"]
        for s in r["route"]["pages"]:
            if not (s.get("karar_kaynagi") or []):
                continue
            g = s.get("gate_signals") or {}
            cezalar = s.get("kalite_cezalari") or {}
            cikti.append({
                "id": kimlik,
                "dataset": r["dataset"],
                "iyi": fayda >= FAYDA_ESIK,
                "fayda": fayda,
                "sayisal": {
                    "kalite_skoru": s.get("quality_score"),
                    "karakter": g.get("karakter"),
                    "kume_kaplama": g.get("kume_kaplama"),
                    "gorsel_kaplama": g.get("gorsel_kaplama"),
                    "ortogonal_cizgi": g.get("ortogonal_cizgi"),
                    "dolu_dikdortgen": g.get("dolu_dikdortgen"),
                    "bezier_egri": g.get("bezier_egri"),
                    "izgara_sutun": g.get("izgara_sutun"),
                    "izgara_satir": g.get("izgara_satir"),
                    "toplam_ceza": sum(cezalar.values()),
                    "dangling_cezasi": cezalar.get("dangling", 0.0),
                },
                "ikili": {
                    "has_table": bool(s.get("has_table")),
                    "has_figure": bool(s.get("has_figure")),
                    "needs_ocr": bool(s.get("needs_ocr")),
                    "tablo_inspector": bool(g.get("tablo_inspector")),
                    "tablo_v2": bool(g.get("tablo_v2")),
                    "sekil_kume": bool(g.get("sekil_kume")),
                    "sekil_raster": bool(g.get("sekil_raster")),
                    "kritik_var": (s.get("critical_issue") or "NONE") != "NONE",
                    "yalniz_low_quality": (s.get("karar_kaynagi") or []) == ["low_quality"],
                },
            })
    return cikti


def _olc(veri: list[dict]) -> dict:
    iyi = [d for d in veri if d["iyi"]]
    kotu = [d for d in veri if not d["iyi"]]
    sonuc = {"n": len(veri), "iyi": len(iyi), "kotu": len(kotu),
             "sayisal": {}, "ikili": {}}
    if not iyi or not kotu:
        return sonuc

    for ad in (veri[0]["sayisal"] if veri else {}):
        p = [d["sayisal"][ad] for d in iyi if d["sayisal"][ad] is not None]
        n = [d["sayisal"][ad] for d in kotu if d["sayisal"][ad] is not None]
        a = auc(p, n)
        if a is not None:
            sonuc["sayisal"][ad] = {"auc": round(a, 4), "guc": round(abs(a - 0.5), 4)}

    for ad in (veri[0]["ikili"] if veri else {}):
        pi = sum(1 for d in iyi if d["ikili"][ad])
        ni = sum(1 for d in kotu if d["ikili"][ad])
        # Bayrak acikken faydali olma orani vs kapaliyken -- fark ne kadar buyukse
        # o kadar ayirici.
        acik = pi + ni
        kapali = len(veri) - acik
        oran_acik = (pi / acik) if acik else None
        oran_kapali = ((len(iyi) - pi) / kapali) if kapali else None
        sonuc["ikili"][ad] = {
            "acik": acik, "acikken_iyi_orani": None if oran_acik is None else round(oran_acik, 4),
            "kapaliyken_iyi_orani": None if oran_kapali is None else round(oran_kapali, 4),
            "guc": None if (oran_acik is None or oran_kapali is None)
                   else round(abs(oran_acik - oran_kapali), 4),
        }
    return sonuc


def main() -> int:
    p = argparse.ArgumentParser(description="Yapisal sinyallerin ayrim gucu")
    p.add_argument("--run", required=True)
    p.add_argument("--cikti", default=os.path.join(BASE, "out", "sinyal_ayrim.json"))
    args = p.parse_args()

    veri = satirlar(_oku(args.run))
    if not veri:
        raise SystemExit("agir motora giden sayfa bulunamadi")

    aileler = sorted({d["dataset"] for d in veri})
    sonuc = {"run": args.run, "fayda_esik": FAYDA_ESIK,
             "birlesik": _olc(veri),
             "aile": {a: _olc([d for d in veri if d["dataset"] == a]) for a in aileler}}

    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)

    for etiket in aileler + ["birlesik"]:
        m = sonuc["birlesik"] if etiket == "birlesik" else sonuc["aile"][etiket]
        print("\n=== %s === agir sayfa=%d (heavy iyi %d / kotu %d)"
              % (etiket, m["n"], m["iyi"], m["kotu"]))
        if not m["sayisal"]:
            print("  tek sinifli, olculemez")
            continue
        print("  --- sayisal sinyaller (AUC; 0,50 = ayrim yok) ---")
        for ad, v in sorted(m["sayisal"].items(), key=lambda x: -x[1]["guc"]):
            isaret = "  <-- bakmaya deger" if v["guc"] >= ILGINC_AUC else ""
            print("  %-20s AUC %.4f   guc %.4f%s" % (ad, v["auc"], v["guc"], isaret))
        print("  --- ikili bayraklar (acikken vs kapaliyken faydali olma orani) ---")
        for ad, v in sorted(m["ikili"].items(),
                            key=lambda x: -(x[1]["guc"] or 0)):
            if v["guc"] is None:
                print("  %-20s tek yonlu (acik=%d)" % (ad, v["acik"]))
                continue
            isaret = "  <-- bakmaya deger" if v["guc"] >= ILGINC_AUC else ""
            print("  %-20s acik=%-3d  acikken %.4f  kapaliyken %.4f  fark %.4f%s"
                  % (ad, v["acik"], v["acikken_iyi_orani"],
                     v["kapaliyken_iyi_orani"], v["guc"], isaret))

    print("\nyazildi: %s" % args.cikti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
