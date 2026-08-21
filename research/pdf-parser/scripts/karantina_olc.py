"""Karantina kararinin isabetini olcer: bozulma skoru gercek faydayi ongoruyor mu.

`merge.py` bir heavy sayfayi kabul mu red mi edecegine BOZULMA skoruna bakarak
karar verir (`smart_pdf._page_scorer` -- yalniz gibberish + unicode). C1'de metin
referansi oldugu icin o kararin dogru olup olmadigi burada OLCULEBILIR: sayfanin
gercek faydasi (`utility_heavy - utility_fast`) referansa gore bilinir.

Olculen sey su: karantinanin baktigi sinyal (skor farki) ile gercek fayda ayni
yonu mu gosteriyor. Gostermiyorsa karantina esigi degil SINYALI yanlistir --
esigi oynatmak yalniz hatanin dagilimini degistirir.

C1'in her belgesi tek sayfa oldugu icin (olculdu, korpus_kaynak.py) belge
utility'si sayfa faydasidir; cok sayfali bir sete GENELLENEMEZ.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\karantina_olc.py \\
        --heavy-cache <c1_docling_cache dizini>
    -> out/karantina_olcum.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from c1_metrik import metrikler  # noqa: E402
from korpus_kaynak import KORPUS_KOK, METIN_REFERANSI, PDF_PARSE  # noqa: E402
from uretim_yolu import ekle  # noqa: E402
from c1_orneklem import sec as _sec  # noqa: E402

ekle()

from research_platform.parsers.smart_pdf import SmartPdfParser  # noqa: E402
from research_platform.parsers.smart_router import SmartRouterHatti  # noqa: E402
from research_platform.parsers.smart_router.ayarlar import AYAR  # noqa: E402
from research_platform.parsers.smart_router.engines import EngineResult  # noqa: E402
from research_platform.parsers.smart_router.merge import (  # noqa: E402
    MergedDocument, MergedPage, birlestir, sayfa_basliklariyla,
)

VARSAYILAN_MANIFEST = os.path.join(BASE, "out", "korpus_envanteri.jsonl")

#: "Heavy gercekten daha iyiydi" esigi -- c1_dogrulama.py ile ayni.
FAYDA_ESIK = 0.02


def _oku_jsonl(yol: str) -> list[dict]:
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def _coz(kayit: dict, goreli: str) -> str:
    kok = BASE if kayit.get("yol_koku") == "staj" else KORPUS_KOK
    return os.path.join(kok, *goreli.split("/"))


def _markdown(sayfalar: dict[int, str], motor: str) -> str:
    doc = MergedDocument(pages=[MergedPage(page_no=n, text=sayfalar.get(n, ""), engine=motor)
                                for n in sorted(sayfalar)])
    return sayfa_basliklariyla(doc)


def main() -> int:
    p = argparse.ArgumentParser(description="Karantina karar isabeti olcumu")
    p.add_argument("--manifest", default=VARSAYILAN_MANIFEST)
    p.add_argument("--heavy-cache", required=True)
    p.add_argument("--cikti", default=os.path.join(BASE, "out", "karantina_olcum.json"))
    args = p.parse_args()

    kayitlar = _sec(_oku_jsonl(args.manifest), None, 0, None)
    puanla = SmartPdfParser()._page_scorer()
    tolerans = AYAR.karantina_tolerans

    satirlar = []
    for kayit in kayitlar:
        onbellek = os.path.join(args.heavy_cache, (kayit.get("pdf_sha256") or "") + ".json")
        if not os.path.isfile(onbellek):
            continue
        try:
            pdf = _coz(kayit, kayit["pdf_yolu"])
            with open(_coz(kayit, kayit["referans"]["yol"]), encoding="utf-8-sig") as f:
                referans = f.read()
            with open(onbellek, encoding="utf-8") as f:
                yuk = json.load(f)
            heavy_sayfa = {int(n): t for n, t in (yuk.get("pages") or {}).items()}

            karar = SmartRouterHatti().calistir(pdf, metin_dahil=True)
            fast_sayfa = {int(n): t for n, t in karar["sayfa_metni"].items()}
            agir = [s["sayfa_no"] for s in karar["sayfalar"] if s.get("karar_kaynagi")]
            if not agir:
                continue

            # Karar UYRETIMDEN okunur, taklit edilmez: `birlestir()` toleransin
            # yani sira formul-kaybi ve icerik-kaybi katastrofik kurallarini da
            # uygular; yalniz skor farkina bakan bir taklit bu redleri kacirir.
            gerekce = {s["sayfa_no"]: s.get("karar_kaynagi") or [] for s in karar["sayfalar"]}
            sonuc = EngineResult(
                engine="docling",
                pages={n: heavy_sayfa[n] for n in agir if heavy_sayfa.get(n)},
                tables=[t for t in (yuk.get("tables") or []) if t.get("page") in set(agir)],
                ok=True, mode="persistent-cache",
            )
            birlesik = birlestir(fast_sayfa, decisions=gerekce, results=[sonuc],
                                 requested={"docling": agir}, score=puanla)
            reddedilen = set(birlesik.quarantined_pages or [])

            for no in agir:
                fast_metin = fast_sayfa.get(no, "")
                heavy_metin = heavy_sayfa.get(no, "")
                if not heavy_metin:
                    continue
                fast_skor = puanla(fast_metin)
                heavy_skor = puanla(heavy_metin)
                # merge.py::_karar_ver ile AYNI isaret: skorda yuksek = daha iyi
                # (merge.py docstring, "higher being better"), fark = heavy - fast.
                # Negatifse heavy daha kotu; `fark < -tolerans` ise red.
                skor_farki = heavy_skor - fast_skor

                u_fast = metrikler(referans, _markdown({no: fast_metin}, "pdf-inspector"))["utility"]
                u_heavy = metrikler(referans, _markdown({no: heavy_metin}, "docling"))["utility"]
                satirlar.append({
                    "id": kayit["kimlik"], "dataset": kayit["veri_seti"], "sayfa": no,
                    "fast_skor": round(fast_skor, 3), "heavy_skor": round(heavy_skor, 3),
                    "skor_farki": round(skor_farki, 3),
                    "kabul": no not in reddedilen,
                    "notlar": [n2 for n2 in birlesik.notes if str(no) in n2],
                    "gercek_fayda": round(u_heavy - u_fast, 4),
                })
        except Exception as exc:
            print("atlandi %s: %s" % (kayit["kimlik"], exc), flush=True)

    _rapor(satirlar, tolerans, args.cikti)
    return 0


def _rapor(satirlar: list[dict], tolerans: float, cikti: str) -> None:
    if not satirlar:
        raise SystemExit("olculecek heavy sayfa bulunamadi")

    iyi = [s for s in satirlar if s["gercek_fayda"] >= FAYDA_ESIK]
    kotu = [s for s in satirlar if s["gercek_fayda"] < FAYDA_ESIK]
    dogru_kabul = [s for s in iyi if s["kabul"]]
    yanlis_red = [s for s in iyi if not s["kabul"]]
    yanlis_kabul = [s for s in kotu if s["kabul"]]
    dogru_red = [s for s in kotu if not s["kabul"]]

    # Skor farki gercek faydayi ongoruyor mu -- Pearson ve isaret uyumu.
    n = len(satirlar)
    xs = [s["skor_farki"] for s in satirlar]
    ys = [s["gercek_fayda"] for s in satirlar]
    ox, oy = sum(xs) / n, sum(ys) / n
    pay = sum((x - ox) * (y - oy) for x, y in zip(xs, ys))
    px = sum((x - ox) ** 2 for x in xs) ** 0.5
    py = sum((y - oy) ** 2 for y in ys) ** 0.5
    r = pay / (px * py) if px and py else 0.0

    kayip = sum(s["gercek_fayda"] for s in yanlis_red)
    kurtarilan = -sum(s["gercek_fayda"] for s in dogru_red)

    ozet = {
        "tolerans": tolerans, "fayda_esik": FAYDA_ESIK,
        "olculen_heavy_sayfa": n,
        "gercekte_iyi": len(iyi), "gercekte_kotu": len(kotu),
        "dogru_kabul": len(dogru_kabul), "yanlis_red": len(yanlis_red),
        "yanlis_kabul": len(yanlis_kabul), "dogru_red": len(dogru_red),
        "red_precision": len(dogru_red) / max(len(dogru_red) + len(yanlis_red), 1),
        "korelasyon_r": round(r, 4),
        "yanlis_redde_kaybedilen_fayda": round(kayip, 4),
        "dogru_redde_kurtarilan_fayda": round(kurtarilan, 4),
        "net": round(kurtarilan - kayip, 4),
    }

    print("\n" + "=" * 74)
    print("KARANTINA KARAR KARNESI  (tolerans=%.2f, C1 = %d heavy sayfa)" % (tolerans, n))
    print("=" * 74)
    print("""
                        | gercekte IYI (>=%.2f) | gercekte KOTU
    --------------------+-----------------------+---------------
    karantina KABUL etti| %4d  dogru kabul      | %4d  yanlis kabul
    karantina REDDETTI  | %4d  YANLIS RED       | %4d  dogru red
""" % (FAYDA_ESIK, len(dogru_kabul), len(yanlis_kabul), len(yanlis_red), len(dogru_red)))
    print("  red isabeti (dogru_red / tum redler) : %.4f" % ozet["red_precision"])
    print("  skor farki <-> gercek fayda korelasyonu: r = %+.4f" % r)
    print("     (r>0 = sinyal dogru yonde calisiyor; r~0 = ayrim gucu yok)")
    ayrimsiz = len([s for s in satirlar if abs(s["skor_farki"]) < 1e-9])
    print("  skor farki TAM SIFIR olan sayfa      : %d / %d  (%.0f%%)"
          % (ayrimsiz, n, 100 * ayrimsiz / n))
    print("  yanlis redde KAYBEDILEN fayda        : %.4f" % kayip)
    print("  dogru redde KURTARILAN fayda         : %.4f" % kurtarilan)
    print("  NET (kurtarilan - kaybedilen)        : %+.4f" % ozet["net"])

    if yanlis_red:
        print("\n  --- YANLIS REDLER (heavy iyiydi, karantina atti) ---")
        print("  %-16s %-22s %10s %12s" % ("kimlik", "veri seti", "skor_farki", "gercek_fayda"))
        for s in sorted(yanlis_red, key=lambda x: -x["gercek_fayda"]):
            print("  %-16s %-22s %10.3f %12.4f"
                  % (s["id"], s["dataset"], s["skor_farki"], s["gercek_fayda"]))

    print("\n  --- veri seti bazli ---")
    print("  %-22s %6s %8s %10s %12s" % ("veri seti", "sayfa", "red", "yanlis_red", "kayip"))
    for ad in sorted({s["dataset"] for s in satirlar}):
        alt = [s for s in satirlar if s["dataset"] == ad]
        red = [s for s in alt if not s["kabul"]]
        yr = [s for s in red if s["gercek_fayda"] >= FAYDA_ESIK]
        print("  %-22s %6d %8d %10d %12.4f"
              % (ad, len(alt), len(red), len(yr), sum(s["gercek_fayda"] for s in yr)))

    with open(cikti, "w", encoding="utf-8") as f:
        json.dump({"ozet": ozet, "sayfalar": satirlar}, f, ensure_ascii=False, indent=2)
    print("\nyazildi: %s" % cikti)


if __name__ == "__main__":
    raise SystemExit(main())
