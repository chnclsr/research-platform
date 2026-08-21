"""Ayni leave-one-out ablation'i KENDI 9 belgelik korpusumuzda kosar.

Neden ayri bir script: iki korpus ayni soruyu SORAMAZ.

  * C1 (`c1_ablation.py`) -- metin referansi VAR, yani "cikti gercekten daha mi
    iyi oldu" olculebiliyor (utility). Ama sayfa goruntusu uzerinden tablo/sekil
    dogrulugu yok.
  * Kendi korpusumuz (bu script) -- metin referansi YOK, utility olculemez. Buna
    karsilik tablo/sekil icin gumus referans var (MinerU+Docling anlasmasi), yani
    "kapi dogru seyi mi gordu" olculebiliyor: TP/FP/FN, bosa agir cagrisi,
    karantina sayisi.

Bir degisiklik iki korpusta TERS yon gosteriyorsa, o degisiklik olculdugu
korpusa uydurulmus olabilir. Bu scriptin varlik sebebi tam olarak bu kontrol.

Kosum `hata_arayuzu.py`'yi SMART_ROUTER_CONFIG_PATH ile tekrar tekrar cagirir ve
her seferinde `out/hata_arayuzu_veri.json`'i saklar -- olculen davranistan sapma
riski olmasin diye metrikler yeniden hesaplanmaz, uretim arayuzunun kendi
hukumleri (tablo_hukmu / sekil_hukmu / yonlendirme) oldugu gibi okunur.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\korpus_ablation.py
    -> out/korpus_ablation/<deney>.json + out/korpus_ablation_ozet.json
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.abspath(os.path.join(BASE, os.pardir, os.pardir))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARAYUZ = os.path.join(BASE, "scripts", "hata_arayuzu.py")
VERI = os.path.join(BASE, "out", "hata_arayuzu_veri.json")
YAML_YOLU = os.path.join(KOK, "config", "smart_router.yaml")
SONUC = os.path.join(BASE, "out", "korpus_ablation")

#: c1_ablation.py ile AYNI liste olmali -- iki korpus ayni deneyi kosmazsa
#: yan yana konamaz.
DENEYLER = [
    ("bugun", "bugunku sistem (referans)", None, None),
    ("tablo_esigi", "dolu_dikdortgen 60 -> 8",
     ["kapi", "tablo", "dolu_dikdortgen"], 8),
    ("sekil_veto", "sekil_veto_kaplama 0.15 -> 0.0",
     ["kapi", "tablo", "sekil_veto_kaplama"], 0.0),
    ("karantina", "karantina_tolerans 0.1 -> 0.0",
     ["birlestirme", "karantina_tolerans"], 0.0),
    ("icerik_kaybi", "icerik_kaybi_esik 0.20 -> 0.0",
     ["birlestirme", "icerik_kaybi_esik"], 0.0),
    ("hyphen", "hyphen.kat 0.0 -> 1.5",
     ["critic_ceza", "hyphen", "kat"], 1.5),
    ("dangling", "dangling.kat 160.0 -> 0.0",
     ["critic_ceza", "dangling", "kat"], 0.0),
]


#: `hata_arayuzu._yonlendirme`'nin uretebildigi butun hukumler. Burada acikca
#: yazili, cunku 2026-08-21'e kadar bu modul "KACAN" diye olmayan bir anahtar
#: okuyordu ve kacirilan tablo sayisi HER kosuda sessizce 0 cikiyordu -- yanlis
#: olan sayi degil, hic var olmayan bir sayiydi. `tests/test_korpus_ablation.py`
#: bu kumeyi uretim fonksiyonuyla karsilastirir; anahtar kayarsa test duser.
YONLENDIRME_HUKUMLERI = frozenset(
    {"OCR", "GEREKLI", "BOSA", "KACIRILDI", "DOGRU_HIZLI"})


def olc(yol: str) -> dict:
    """hata_arayuzu.py'nin kendi hukumlerini sayar; yeniden yorumlamaz."""
    veri = json.load(open(yol, encoding="utf-8"))
    h: collections.Counter = collections.Counter()
    sayfa = 0
    bilinmeyen: set = set()
    for belge in veri:
        for s in belge["sayfalar"]:
            sayfa += 1
            h["tablo_" + s["tablo_hukmu"]] += 1
            h["sekil_" + s["sekil_hukmu"]] += 1
            hukum = s["yonlendirme"]
            if hukum not in YONLENDIRME_HUKUMLERI:
                bilinmeyen.add(hukum)
            h["yon_" + hukum] += 1
            if s["yol"] != "HIZLI":
                h["agir"] += 1
        h["karantina"] += int(belge.get("karantina_sayfa") or 0)
        h["fallback"] += int(belge.get("fallback_sayfa") or 0)
    if bilinmeyen:
        # Sessizce sifir saymaktansa gurultu cikar: bir hukum eklenmis ve bu
        # modul haberdar degil demektir.
        print("UYARI: taninmayan yonlendirme hukmu: %s" % sorted(bilinmeyen))
    tp, fp, fn = h["tablo_TP"], h["tablo_FP"], h["tablo_FN"]
    stp, sfp, sfn = h["sekil_TP"], h["sekil_FP"], h["sekil_FN"]
    return {
        "sayfa": sayfa, "agir": h["agir"],
        "tablo_TP": tp, "tablo_FP": fp, "tablo_FN": fn,
        "tablo_precision": tp / (tp + fp) if tp + fp else 0.0,
        "tablo_recall": tp / (tp + fn) if tp + fn else 0.0,
        "sekil_TP": stp, "sekil_FP": sfp, "sekil_FN": sfn,
        "bosa": h["yon_BOSA"], "kacirilan": h["yon_KACIRILDI"],
        "karantina": h["karantina"], "fallback": h["fallback"],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Kendi korpusta leave-one-out ablation")
    p.add_argument("--atla-kosu", action="store_true",
                   help="kosulari tekrar calistirma, var olan ciktilari topla")
    p.add_argument("--cikti", default=os.path.join(BASE, "out", "korpus_ablation_ozet.json"))
    p.add_argument("--c1-ozet", default=os.path.join(BASE, "out", "ablation_ozet.json"),
                   help="c1_ablation.py ciktisi -- iki korpusu yan yana koymak icin")
    args = p.parse_args()

    import yaml

    taban_yaml = yaml.safe_load(open(YAML_YOLU, encoding="utf-8"))
    os.makedirs(SONUC, exist_ok=True)
    profiller = os.path.join(BASE, "out", "ablation_profilleri")
    os.makedirs(profiller, exist_ok=True)

    for ad, aciklama, yol, deger in DENEYLER:
        hedef = os.path.join(SONUC, ad + ".json")
        if args.atla_kosu and os.path.isfile(hedef):
            print("atlandi (mevcut): %s" % ad, flush=True)
            continue
        veri = copy.deepcopy(taban_yaml)
        if yol:
            d = veri
            for k in yol[:-1]:
                d = d[k]
            d[yol[-1]] = deger
        veri["profil_adi"] = "ablation_" + ad
        profil = os.path.join(profiller, "korpus_" + ad + ".yaml")
        with open(profil, "w", encoding="utf-8") as f:
            yaml.safe_dump(veri, f, allow_unicode=True, sort_keys=False)

        print(">>> %-13s %s" % (ad, aciklama), flush=True)
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, ARAYUZ], cwd=BASE,
                           env=dict(os.environ, SMART_ROUTER_CONFIG_PATH=profil),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if os.path.isfile(VERI):
            shutil.copy(VERI, hedef)
            print("    %.0f sn" % (time.perf_counter() - t0), flush=True)
        else:
            print("    HATA: cikti yok\n%s" % (r.stdout or "")[-1000:], flush=True)

    olcumler = {ad: olc(os.path.join(SONUC, ad + ".json"))
                for ad, _, _, _ in DENEYLER
                if os.path.isfile(os.path.join(SONUC, ad + ".json"))}
    if "bugun" not in olcumler:
        raise SystemExit("referans kosu (bugun) yok")
    taban = olcumler["bugun"]

    c1 = {}
    if os.path.isfile(args.c1_ozet):
        with open(args.c1_ozet, encoding="utf-8") as f:
            c1 = {d["ad"]: d for d in json.load(f)["deneyler"]}

    sonuc = {"taban": taban, "deneyler": []}
    for ad, aciklama, _, _ in DENEYLER:
        if ad == "bugun" or ad not in olcumler:
            continue
        m = olcumler[ad]
        kayit = {
            "ad": ad, "aciklama": aciklama, "olcum": m,
            "d_agir": m["agir"] - taban["agir"],
            "d_tablo_fp": m["tablo_FP"] - taban["tablo_FP"],
            "d_tablo_fn": m["tablo_FN"] - taban["tablo_FN"],
            "d_bosa": m["bosa"] - taban["bosa"],
            "d_kacirilan": m["kacirilan"] - taban["kacirilan"],
            "d_karantina": m["karantina"] - taban["karantina"],
        }
        if ad in c1:
            kayit["c1_d_net"] = c1[ad]["d_net"]
            kayit["c1_d_heavy"] = c1[ad]["d_heavy"]
            kayit["c1_hukum"] = c1[ad]["hukum"]
            # Iki korpus ayni yonu mu gosteriyor? Kendi korpusta "geri almak
            # kotu" isareti = FP ya da bosa cagri ARTIYOR.
            kendi_kotu = (kayit["d_tablo_fp"] > 0 or kayit["d_bosa"] > 0
                          or kayit["d_kacirilan"] > 0)
            kendi_iyi = (kayit["d_tablo_fp"] < 0 or kayit["d_bosa"] < 0
                         or kayit["d_kacirilan"] < 0)
            c1_kotu = c1[ad]["hukum"] == "faydali"   # geri almak C1'de de kotu
            c1_iyi = c1[ad]["hukum"] == "zararli"
            if (kendi_kotu and c1_kotu) or (kendi_iyi and c1_iyi):
                kayit["hizalama"] = "ayni_yon"
            elif not kendi_kotu and not kendi_iyi:
                kayit["hizalama"] = "kendi_korpusta_etkisiz"
            elif c1[ad]["hukum"] == "notr":
                kayit["hizalama"] = "c1de_etkisiz"
            else:
                kayit["hizalama"] = "CELISKI"
        sonuc["deneyler"].append(kayit)

    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)

    print("\n=== KENDI KORPUS (9 belge / %d sayfa) ===" % taban["sayfa"])
    print("%-13s %-32s %5s %6s %6s %6s %5s %6s %5s" %
          ("deney", "geri alinan degisiklik", "agir", "tbTP", "tbFP", "tbFN",
           "bosa", "kacan", "karan"))
    print("-" * 100)
    for ad, aciklama, _, _ in DENEYLER:
        if ad not in olcumler:
            continue
        m = olcumler[ad]
        print("%-13s %-32s %5d %6d %6d %6d %5d %6d %5d" %
              (ad, "— referans" if ad == "bugun" else aciklama, m["agir"],
               m["tablo_TP"], m["tablo_FP"], m["tablo_FN"], m["bosa"],
               m["kacirilan"], m["karantina"]))

    if c1:
        print("\n=== IKI KORPUS YAN YANA (geri almanin etkisi) ===")
        print("%-13s | %-38s | %-24s | %s" %
              ("deney", "kendi korpus", "C1", "hizalama"))
        print("-" * 116)
        for d in sonuc["deneyler"]:
            kendi = "Δagir%+d ΔtbFP%+d Δbosa%+d Δkacan%+d Δkar%+d" % (
                d["d_agir"], d["d_tablo_fp"], d["d_bosa"], d["d_kacirilan"],
                d["d_karantina"])
            c1s = "ΔNET%+.4f Δagir%+d" % (d.get("c1_d_net", 0), d.get("c1_d_heavy", 0))
            print("%-13s | %-38s | %-24s | %s" %
                  (d["ad"], kendi, c1s, d.get("hizalama", "—")))

    print("\nyazildi: %s" % args.cikti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
