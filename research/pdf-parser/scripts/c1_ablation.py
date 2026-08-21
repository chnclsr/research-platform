"""Dunku her ayar degisikligini TEK TEK geri alip tam C1 korpusunda olcer.

Neden leave-one-out: M.1'de izole ablation'in yaniltici oldugu zaten olculmustu
(bir sinyali tek basina test etmek, baska duzeltmelerle etkilesimini gizliyor).
Burada temel HER ZAMAN bugunku tam sistemdir; her kosuda yalniz bir parametre
dun-oncesi degerine dondurulur, geri kalan her sey yerinde kalir.

Neden NET olcut: `yakalanan fayda orani` yalniz pozitif deltalari toplar
(`max(delta, 0)`), yani gereksiz bir heavy cagrisinin verdigi ZARARI hic saymaz.
Bir esigi o metrige gore optimize etmek, zarari gorunmez kilar. NET =
`sum(routed_utility - fast_utility)` -- kazanci ve kaybi ayni terazide tartar.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\c1_ablation.py \\
        --heavy-cache <c1_docling_cache dizini>
    -> out/c1_runs/ablation_*_<tarih>/ + out/ablation_ozet.json
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

#: Referans "heavy gercekten daha iyiydi" esigi -- c1_dogrulama.py ile ayni.
FAYDA_ESIK = 0.02

#: |ΔNET| bunun altindaysa fark gurultu sayilir, hukum verilmez.
NET_ESIK = 0.01

#: (kisa_ad, aciklama, yaml_yolu, 20_agustos_oncesi_deger). `bugun` referanstir:
#: hicbir sey degistirmez, digerlerinin karsilastirildigi taban.
#:
#: Aciklamalar HEDEF degeri yazar, "X -> Y" yazmaz: taban zaman icinde
#: degisiyor (orn. karantina_tolerans 2026-08-21'de 0,1'den 5,0'a cikti) ve
#: sabit bir "X" etiketi ilk degismede yalan soylerdi. Baslangic degeri zaten
#: kosunun taban satirinda duruyor.
DENEYLER = [
    ("bugun", "bugunku sistem (referans)", None, None),
    ("tablo_esigi", "dolu_dikdortgen -> 8",
     ["kapi", "tablo", "dolu_dikdortgen"], 8),
    ("sekil_veto", "sekil_veto_kaplama -> 0.0 (veto kapali)",
     ["kapi", "tablo", "sekil_veto_kaplama"], 0.0),
    ("karantina", "karantina_tolerans -> 0.0 (olu bant yok)",
     ["birlestirme", "karantina_tolerans"], 0.0),
    ("icerik_kaybi", "icerik_kaybi_esik -> 0.0 (kural kapali)",
     ["birlestirme", "icerik_kaybi_esik"], 0.0),
    ("hyphen", "hyphen.kat -> 1.5",
     ["critic_ceza", "hyphen", "kat"], 1.5),
    ("dangling", "dangling.kat -> 0.0",
     ["critic_ceza", "dangling", "kat"], 0.0),
]


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


def olc(kayitlar: dict, kimlikler: list[str], *, ayristir: bool = True) -> dict:
    """Bir kosunun metrikleri. `ayristir` ile veri ailesi bazinda da doner.

    Birlesik NET tek basina YANILTIR: 2026-08-21'de olculdu, dangling'in etkisi
    ocrturk'te -0,2634 / opendataloader'da +0,3006 -- toplam +0,0373 yalnizca
    iki ters yonlu etkinin artigi ve korpustaki TR/EN oranina bagimli
    (rapor Bolum O.8.3). Bu yuzden ayristirma varsayilan olarak aciktir.
    """
    rows = [kayitlar[k] for k in kimlikler]
    routed = [r for r in rows if r["route"]["routed_heavy"]]
    kazanan = [r for r in rows if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    dogru = [r for r in routed if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    toplam = sum(max(r["delta"]["heavy_minus_fast"], 0.0) for r in rows)
    alinan = sum(max(r["delta"]["routed_minus_fast"], 0.0) for r in rows)
    kar = [r for r in rows if r["merge"]["quarantined_pages"]]

    aile = {}
    if ayristir:
        setler = {r["dataset"] for r in rows}
        if len(setler) > 1:
            for ad in sorted(setler):
                alt = [k for k in kimlikler if kayitlar[k]["dataset"] == ad]
                aile[ad] = olc(kayitlar, alt, ayristir=False)

    return {
        "veri_ailesi": aile,
        "routed": len(routed),
        "precision": (len(dogru) / len(routed)) if routed else 0.0,
        "recall": (len(dogru) / len(kazanan)) if kazanan else 0.0,
        "routed_u": sum(r["scores"]["routed"]["utility"] for r in rows) / len(rows),
        "yakalanan": (alinan / toplam) if toplam else 0.0,
        "net": sum(r["delta"]["routed_minus_fast"] for r in rows),
        "karantinali": len(kar),
        "karantina_maliyeti": sum(
            max(r["delta"]["heavy_minus_fast"] - r["delta"]["routed_minus_fast"], 0.0)
            for r in kar),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="C1 leave-one-out ablation")
    p.add_argument("--heavy-cache", required=True)
    p.add_argument("--etiket", default=datetime.now().strftime("%Y%m%d"))
    p.add_argument("--atla-kosu", action="store_true",
                   help="kosulari tekrar calistirma, var olan ciktilari topla")
    p.add_argument("--cikti", default=os.path.join(BASE, "out", "ablation_ozet.json"))
    args = p.parse_args()

    import yaml

    with open(YAML_YOLU, encoding="utf-8") as f:
        taban_yaml = yaml.safe_load(f)
    gecici = os.path.join(BASE, "out", "ablation_profilleri")
    os.makedirs(gecici, exist_ok=True)

    kosular = {}
    for ad, aciklama, yol, deger in DENEYLER:
        run_id = "ablation_%s_%s" % (ad, args.etiket)
        kosular[ad] = run_id
        if args.atla_kosu and os.path.isdir(os.path.join(KOSULAR, run_id)):
            print("atlandi (mevcut): %s" % run_id, flush=True)
            continue
        veri = copy.deepcopy(taban_yaml)
        if yol:
            d = veri
            for k in yol[:-1]:
                d = d[k]
            d[yol[-1]] = deger
        veri["profil_adi"] = "ablation_" + ad
        profil = os.path.join(gecici, ad + ".yaml")
        with open(profil, "w", encoding="utf-8") as f:
            yaml.safe_dump(veri, f, allow_unicode=True, sort_keys=False)

        print(">>> %-13s %s" % (ad, aciklama), flush=True)
        subprocess.run(
            [sys.executable, DOGRULAMA, "--heavy-cache", args.heavy_cache,
             "--run-id", run_id],
            env=dict(os.environ, SMART_ROUTER_CONFIG_PATH=profil),
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    veriler = {ad: _oku(run) for ad, run in kosular.items()
               if os.path.isdir(os.path.join(KOSULAR, run))}
    if "bugun" not in veriler:
        raise SystemExit("referans kosu (bugun) yok")
    ortak = sorted(set.intersection(*[set(v) for v in veriler.values()]))

    taban = olc(veriler["bugun"], ortak)
    sonuc = {
        "uretim": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "belge": len(ortak),
        "net_esik": NET_ESIK,
        "taban": taban,
        "deneyler": [],
    }
    for ad, aciklama, yol, deger in DENEYLER:
        if ad == "bugun" or ad not in veriler:
            continue
        m = olc(veriler[ad], ortak)
        d_net = m["net"] - taban["net"]
        d_heavy = m["routed"] - taban["routed"]
        if d_net > NET_ESIK:
            hukum = "zararli"
        elif d_net < -NET_ESIK:
            hukum = "faydali"
        else:
            hukum = "notr"
        # Veri ailesi bazinda ayni fark; isaretler ters cikiyorsa birlesik
        # sonuca gore karar VERILMEZ (rapor O.8.3).
        aile_farki = {
            ad2: {
                "d_net": m["veri_ailesi"][ad2]["net"] - taban["veri_ailesi"][ad2]["net"],
                "d_heavy": (m["veri_ailesi"][ad2]["routed"]
                            - taban["veri_ailesi"][ad2]["routed"]),
            }
            for ad2 in m.get("veri_ailesi", {}) if ad2 in taban.get("veri_ailesi", {})
        }
        isaretler = {(v["d_net"] > NET_ESIK) - (v["d_net"] < -NET_ESIK)
                     for v in aile_farki.values()}
        sonuc["deneyler"].append({
            "ad": ad, "aciklama": aciklama, "run_id": kosular[ad],
            "olcum": m, "d_net": d_net, "d_heavy": d_heavy,
            "d_routed_u": m["routed_u"] - taban["routed_u"],
            "hukum": hukum,
            "aile_farki": aile_farki,
            # {+1, -1} birlikte varsa aileler ters yon gosteriyor demektir.
            "aileler_celisiyor": bool({1, -1} <= isaretler),
        })

    sonuc["deneyler"].sort(key=lambda x: -x["d_net"])
    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)

    print("\n%-13s %-34s %7s %9s %7s  %s" %
          ("deney", "geri alinan degisiklik", "Δheavy", "ΔNET", "Δutil", "hukum"))
    print("-" * 96)
    for d in sonuc["deneyler"]:
        print("%-13s %-34s %+7d %+9.4f %+7.5f  %s%s" %
              (d["ad"], d["aciklama"], d["d_heavy"], d["d_net"],
               d["d_routed_u"], d["hukum"],
               "  << AILELER CELISIYOR" if d["aileler_celisiyor"] else ""))

    aileler = sorted(taban.get("veri_ailesi") or {})
    if aileler:
        print("\n--- veri ailesi bazinda ΔNET (birlesik sonuc bunlari gizler) ---")
        print("%-13s %s" % ("deney", "  ".join("%-24s" % a for a in aileler)))
        print("-" * (14 + 26 * len(aileler)))
        for d in sonuc["deneyler"]:
            hucre = []
            for a in aileler:
                v = d["aile_farki"].get(a)
                hucre.append("%-24s" % ("—" if v is None else
                                        "ΔNET%+8.4f Δhv%+3d" % (v["d_net"], v["d_heavy"])))
            print("%-13s %s" % (d["ad"], "  ".join(hucre)))

    print("\ntaban: heavy=%d precision=%.4f recall=%.4f NET=%.4f (%d belge)" %
          (taban["routed"], taban["precision"], taban["recall"],
           taban["net"], len(ortak)))
    for a in aileler:
        t = taban["veri_ailesi"][a]
        print("   %-22s belge=%d heavy=%d precision=%.4f recall=%.4f NET=%+.4f" %
              (a, len([k for k in ortak if veriler["bugun"][k]["dataset"] == a]),
               t["routed"], t["precision"], t["recall"], t["net"]))
    print("yazildi: %s" % args.cikti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
