"""Tek bir ayari birden cok degerde tam sistem replay'iyle tarar.

`c1_ablation.py` "bu degisikligi geri alsak ne olurdu" sorusunu sorar; bu script
"bu ayar su degerlerde ne yapar" sorusunu sorar. Ikisi de tam sistemi kosar --
izole ablation'in etkilesimi gizledigi M.1'de zaten olculmustu.

CIKIS KRITERI: tarama bir KARAR araci degil, bir TESHIS aracidir. Hicbir aday
`--kapi-precision` / `--kapi-recall` esiklerini UC VERI AILESINDE BIRDEN
tutturamazsa sonuc "bu ayar bu sorunu cozmuyor" olarak kaydedilir ve holdout
dogrulamasi hic kosulmaz -- dogrulanacak bir aday yoktur. Bunu bastan yazmak,
taramayi "bir sey cikana kadar deneme" dongusune donusmekten korur.

Her aday icin veri ailesi bazinda raporlanan: agir cagri, yalniz-low_quality
cagrisi, bosa heavy, route precision/recall, NET, karantinanin kabul/reddettigi
gercek fayda.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\c1_tarama.py \\
        --ayar critic_ceza.dangling.kat --degerler 0,80,160 \\
        --heavy-cache <c1_docling_cache dizini>
    -> out/c1_runs/tarama_<ayar>_<deger>_<etiket>/ + out/tarama_<ayar>.json
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.abspath(os.path.join(BASE, os.pardir, os.pardir))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KOSULAR = os.path.join(BASE, "out", "c1_runs")
DOGRULAMA = os.path.join(BASE, "scripts", "c1_dogrulama.py")
YAML_YOLU = os.path.join(KOK, "config", "smart_router.yaml")

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


def olc(kayitlar: dict, kimlikler: list[str]) -> dict:
    rows = [kayitlar[k] for k in kimlikler]
    if not rows:
        return {}
    routed = [r for r in rows if r["route"]["routed_heavy"]]
    kazanan = [r for r in rows if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    dogru = [r for r in routed if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    # Yalniz kalite skoru yuzunden agir motora giden sayfa: dangling agirliginin
    # dogrudan sorumlu oldugu cagri kumesi (rapor O.8.2).
    yalniz_lq = sum(
        1 for r in rows
        for s in r["route"]["pages"]
        if (s.get("karar_kaynagi") or []) == ["low_quality"])
    bosa = [r for r in routed if r["delta"]["heavy_minus_fast"] < FAYDA_ESIK]
    kar = [r for r in rows if r["merge"]["quarantined_pages"]]
    return {
        "belge": len(rows),
        "heavy": len(routed),
        "yalniz_low_quality_sayfa": yalniz_lq,
        "bosa_heavy": len(bosa),
        "precision": (len(dogru) / len(routed)) if routed else 0.0,
        "recall": (len(dogru) / len(kazanan)) if kazanan else 0.0,
        "net": sum(r["delta"]["routed_minus_fast"] for r in rows),
        "karantinali": len(kar),
        # Karantina kabul edip elde kalan / reddedip kaybedilen gercek fayda.
        "karantina_kaybi": sum(
            max(r["delta"]["heavy_minus_fast"] - r["delta"]["routed_minus_fast"], 0.0)
            for r in kar),
        "karantina_kurtardigi": sum(
            max(r["delta"]["routed_minus_fast"] - r["delta"]["heavy_minus_fast"], 0.0)
            for r in kar),
    }


def _yaz_profil(yol_parcalari: list[str], deger, hedef: str) -> str:
    import yaml

    with open(YAML_YOLU, encoding="utf-8") as f:
        veri = yaml.safe_load(f)
    d = veri
    for k in yol_parcalari[:-1]:
        if k not in d:
            raise SystemExit("YAML'da yol yok: %s" % ".".join(yol_parcalari))
        d = d[k]
    if yol_parcalari[-1] not in d:
        raise SystemExit("YAML'da anahtar yok: %s" % ".".join(yol_parcalari))
    d[yol_parcalari[-1]] = deger
    veri["profil_adi"] = "tarama_%s_%s" % (yol_parcalari[-1], deger)
    with open(hedef, "w", encoding="utf-8") as f:
        yaml.safe_dump(veri, f, allow_unicode=True, sort_keys=False)
    return hedef


def main() -> int:
    p = argparse.ArgumentParser(description="Tek ayar icin tam sistem taramasi")
    p.add_argument("--ayar", required=True,
                   help="YAML yolu, nokta ayrali (orn. critic_ceza.dangling.kat)")
    p.add_argument("--degerler", required=True, help="virgul ayrali (orn. 0,80,160)")
    p.add_argument("--heavy-cache", required=True)
    p.add_argument("--etiket", default=datetime.now().strftime("%Y%m%d"))
    p.add_argument("--atla-kosu", action="store_true")
    p.add_argument("--kapi-precision", type=float, default=0.50)
    p.add_argument("--kapi-recall", type=float, default=0.60)
    p.add_argument("--cikti")
    args = p.parse_args()

    yol = args.ayar.split(".")
    degerler = [float(d) if "." in d or d.isdigit() else d
                for d in args.degerler.split(",")]
    kisa = yol[-2] if yol[-1] in ("kat", "esik", "tavan") else yol[-1]
    cikti = args.cikti or os.path.join(BASE, "out", "tarama_%s.json" % kisa)
    profiller = os.path.join(BASE, "out", "tarama_profilleri")
    os.makedirs(profiller, exist_ok=True)

    kosular = {}
    for deger in degerler:
        run_id = "tarama_%s_%s_%s" % (kisa, str(deger).replace(".", "_"), args.etiket)
        kosular[deger] = run_id
        if args.atla_kosu and os.path.isdir(os.path.join(KOSULAR, run_id)):
            print("atlandi (mevcut): %s" % run_id, flush=True)
            continue
        profil = _yaz_profil(yol, deger, os.path.join(profiller, "%s_%s.yaml" % (kisa, deger)))
        print(">>> %s = %s" % (args.ayar, deger), flush=True)
        subprocess.run(
            [sys.executable, DOGRULAMA, "--heavy-cache", args.heavy_cache,
             "--run-id", run_id],
            env=dict(os.environ, SMART_ROUTER_CONFIG_PATH=profil),
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    veriler = {d: _oku(r) for d, r in kosular.items()
               if os.path.isdir(os.path.join(KOSULAR, r))}
    if not veriler:
        raise SystemExit("hicbir kosu uretilemedi")
    ortak = sorted(set.intersection(*[set(v) for v in veriler.values()]))
    herhangi = next(iter(veriler.values()))
    aileler = sorted({herhangi[k]["dataset"] for k in ortak})

    sonuc = {"ayar": args.ayar, "etiket": args.etiket, "belge": len(ortak),
             "kapi": {"precision": args.kapi_precision, "recall": args.kapi_recall},
             "adaylar": []}
    for deger in degerler:
        if deger not in veriler:
            continue
        kayitlar = veriler[deger]
        aile_olcum = {a: olc(kayitlar, [k for k in ortak if kayitlar[k]["dataset"] == a])
                      for a in aileler}
        birlesik = olc(kayitlar, ortak)
        gecti = {a: (m["precision"] >= args.kapi_precision
                     and m["recall"] >= args.kapi_recall)
                 for a, m in aile_olcum.items()}
        sonuc["adaylar"].append({
            "deger": deger, "run_id": kosular[deger],
            "birlesik": birlesik, "aile": aile_olcum,
            "kapi_gecti": gecti, "tum_ailelerde_gecti": all(gecti.values()),
        })

    gecen = [a for a in sonuc["adaylar"] if a["tum_ailelerde_gecti"]]
    sonuc["kapiyi_gecen_aday"] = [a["deger"] for a in gecen]
    sonuc["sonuc"] = ("aday_var" if gecen else
                      "ayar_bu_sorunu_cozmuyor -- holdout kosulmayacak")

    with open(cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)

    print("\n=== TARAMA: %s  (%d belge) ===" % (args.ayar, len(ortak)))
    for a in aileler + ["BIRLESIK"]:
        print("\n--- %s ---" % a)
        print("%8s %6s %10s %6s %10s %9s %9s %8s %10s" %
              ("deger", "heavy", "yalniz_lq", "bosa", "precision", "recall",
               "NET", "karan", "kar_kaybi"))
        for aday in sonuc["adaylar"]:
            m = aday["birlesik"] if a == "BIRLESIK" else aday["aile"][a]
            isaret = ""
            if a != "BIRLESIK":
                isaret = "  <- kapi gecti" if aday["kapi_gecti"][a] else ""
            print("%8s %6d %10d %6d %10.4f %9.4f %+9.4f %8d %10.4f%s" %
                  (aday["deger"], m["heavy"], m["yalniz_low_quality_sayfa"],
                   m["bosa_heavy"], m["precision"], m["recall"], m["net"],
                   m["karantinali"], m["karantina_kaybi"], isaret))

    print("\nkapi: precision>=%.2f ve recall>=%.2f, UC AILEDE BIRDEN"
          % (args.kapi_precision, args.kapi_recall))
    print("SONUC: %s" % sonuc["sonuc"])
    print("yazildi: %s" % cikti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
