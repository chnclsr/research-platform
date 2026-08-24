#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orchestrator.py
===============
A KOLUNUN BIRLESTIGI YER: critic girisTEN cikisA tasindi (plan D2),
skor yol secmiyor kuyruk siralıyor (plan D8), OCR hedefi olculmus
motorlar (plan D10).

AKIS — ONCE / SONRA
-------------------

    ONCE (mentorun router.py'si)
        belgeye bakilir -> parser secilir -> belgenin TAMAMI o parser'a gider

    SONRA (bu modul)
        inspector TUM belgeyi cikarir      (2,6 ms/sayfa)
        giris kapisi sayfa bayraklari      (8,7-20,8 ms/sayfa, olculdu)
        critic ciktiyi SAYFA SAYFA denetler(0,42-0,92 ms/sayfa, olculdu)
        yalniz sorunlu sayfalar agir motora(Docling 1,55 sn/sayfa)

Gerekce (plan D2): critic'in girdisi zaten inspector'in ciktisi; inspector
kosmadan critic bir sey soyleyemiyor. Ayrica ilk 30 sayfasi temiz olan bir
belgenin tamamini agir motora gondermek gereksiz maliyet.

Olculen kazanc: sorunlu sayfalarin %27'si YALNIZ bu konumda gorulebiliyor
(8 belge, 255 sayfa: critic'in <75 verdigi 67 sayfanin 18'ini giris kapisi
hic isaretlemiyor — o sayfalarda tablo/sekil yok ama metin akisi bozuk).

SAYFA SECIMI (plan E3)
    agir hat = needs_ocr  UNION  has_table  UNION  {kalite < esik}
    `has_figure` TETIKLEYICI DEGIL — gerekce gate.sayfa_secici docstring'inde.

OCR HEDEFI (plan D10)
    critic.py OCR gereken belgeleri `miner-VL`ye yonlendiriyordu; o yol HIC
    KOSTURULMADI. Kosturulan MinerU `auto`/pipeline. Taranmis belgede (6
    sayfa) olculen karakter: Docling 24.963 · MinerU 24.554 · pypdf 70 ·
    opendataloader 12 · pymupdf4llm 10 · pdf-inspector 0. Beklenen ~26.338.
    Iki olculmus motor var; VLM'e gerek yok, opsiyonel ust basamak kalabilir.

NE OLCULMEDI
    - Agir motor bu hattan CAGRILMIYOR; plan uretiliyor ve dogrulaniyor, ama
      Docling/MinerU kosturulmuyor. Cikis denetimi (plan 6.3) hala acik.
    - Esikler kalibre edilmedi (plan D12); kalibrasyon C1 olmadan yapilamaz.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from .ayarlar import AYAR, Ayarlar
from .critic import PDFCritic
from .gate import GirisKapisi, sayfa_secici
from .inspector import PdfInspectorAdapter
from .pages import cagri_plani

ROUTER_VERSION = "orchestrator_v1_2026-08-18"

# Olculmus motor yetenekleri — elle etiket degil.
# Kaynak: resmi_benchmark_sonuc.json, 200 belge, 2026-08-17.
MOTOR: Dict[str, Dict[str, Any]] = {
    "pdf-inspector": {"genel": 0.876, "tablo": 0.814, "okuma_sirasi": 0.915,
                      "sn_sayfa": 0.0026, "ocr": False,
                      "rol": "hizli yol — metin, baslik, bolge metni"},
    "docling": {"genel": 0.894, "tablo": 0.934, "okuma_sirasi": 0.910,
                "sn_sayfa": 1.55, "ocr": True,
                "rol": "agir hat ve OCR — tablo, sekil"},
    "mineru": {"genel": 0.857, "tablo": 0.911, "okuma_sirasi": 0.871,
               "sn_sayfa": 5.30, "ocr": True,
               "rol": "OCR yedegi — Docling bir cumleyi bozmustu (tek gozlem)"},
}

YOL_MOTOR = {
    "HIZLI": ["pdf-inspector"],
    "AGIR": ["docling"],
    "OCR": ["docling", "mineru"],
}


def kuyruk_skoru(bayraklar: Dict[int, Any], sayfa_sayisi: int) -> float:
    """Yapisal skorun YENI GOREVI: yol secmez, SIRA belirler (plan D8).

    Gerekce (olculdu): tek skor yol secemiyor. 17 ozelligin hepsi
    `normalize(val, 0, 100)` ile olcekleniyordu ama cogu 0-1 arasi oran;
    skoru fiilen yalniz cizim sayisi, x0 std ve sayfa sayisi suruyordu.
    Sonuc: taranmis belge 4,3 puanla dokuz belgenin EN DUSUGU — bu skora
    esik baglanamaz.

    Burada sayinin yanlis olmasi yolu degistirmez, yalnizca sirayi
    degistirir. Tek skorun guvenle kullanilabilecegi tek yer.

    Formul `src/router_engine_v2.kuyruk_skoru` ile AYNI; degerler kapinin
    zaten hesapladigi sinyallerden okunuyor (ikinci PDF gecisi yok).
    KALIBRE EDILMEDI.
    """
    if not bayraklar:
        return 0.0
    n = len(bayraklar)
    ort_ortogonal = sum(b.kaynak.get("ortogonal_cizgi", 0) for b in bayraklar.values()) / n
    ort_bezier = sum(b.kaynak.get("bezier_egri", 0) for b in bayraklar.values()) / n
    ort_kaplama = sum(b.kaynak.get("gorsel_kaplama", 0.0) for b in bayraklar.values()) / n
    return round(
        0.4 * min(ort_ortogonal, 200) / 200
        + 0.3 * min(ort_bezier, 400) / 400
        + 0.2 * ort_kaplama
        + 0.1 * min(sayfa_sayisi, 200) / 200,
        4,
    )


class SmartRouterHatti:
    """inspector -> kapi -> critic -> sayfa secici -> agir motor plani."""

    def __init__(self, *, kalite_esik: Optional[float] = None,
                 yuksek_guven_yeter: Optional[bool] = None,
                 ocr_motoru: str = "docling",
                 ayar: Ayarlar = AYAR) -> None:
        """`ayar`: etkin esik profili (`config/smart_router.yaml`).

        Tekil esikler ayrica gecilebilir ve profili ezer; kalibrasyon taramalari
        boyle calisir. Ezilen deger `esik_version`'a GIRMEZ -- surum profilin
        hash'idir. Bu yuzden ezme olcum icindir; uretimde profil dosyasi degisir.
        """
        self.ayar = ayar
        self.kalite_esik = ayar.kalite_esik if kalite_esik is None else kalite_esik
        # KALIBRASYON anahtari, calisma ani butcesi DEGIL (plan 8.3):
        # `content_hash` ayristirilmis metinden uretiliyor ve ayni baytlar her
        # kosuda ayni ciktiyi vermek zorunda.
        self.yuksek_guven_yeter = (ayar.yuksek_guven_yeter
                                   if yuksek_guven_yeter is None else yuksek_guven_yeter)
        if ocr_motoru not in YOL_MOTOR["OCR"]:
            raise ValueError(f"OCR motoru olculmus degil: {ocr_motoru}")
        self.ocr_motoru = ocr_motoru
        self.kapi = GirisKapisi(esik=ayar.kapi_esikleri)
        self.critic = PDFCritic(fallback_threshold=self.kalite_esik, ceza=ayar.critic_ceza)

    def calistir(self, pdf_path: str, *,
                 metin_dahil: bool = False) -> Dict[str, Any]:
        """Hatti kostur ve karar planini dondur.

        `metin_dahil=True` iken sonuca `sayfa_metni` (1-tabanli sayfa no ->
        markdown) eklenir. `SmartPdfParser` bunu kullanir; boylece inspector
        IKINCI KEZ cagrilmaz — ayni hatayi A9'da `gate.bayrakla()` icin
        duzeltmistik. Olcum betikleri varsayilan `False` ile calisir, ciktilari
        sismez.
        """
        sure: Dict[str, float] = {}

        # --- 1) inspector TUM belgeyi cikarir (D2: once cikar, sonra denetle)
        t0 = time.perf_counter()
        insp = PdfInspectorAdapter.extract_pages(pdf_path)
        sure["inspector_ms"] = (time.perf_counter() - t0) * 1000

        # --- 2) giris kapisi: sayfa bayraklari (E2)
        # A9: inspector sonucu PAYLASILIYOR. Once `bayrakla()` kendi
        # `extract_pages()` cagrisini yapiyordu; ayni PDF inspector'dan iki kez
        # geciyordu ve olculen kapi maliyeti bu fazladan gecisi iceriyordu.
        t0 = time.perf_counter()
        source_text_by_page: Optional[Dict[int, str]] = {} if metin_dahil else None
        bayraklar = self.kapi.bayrakla(
            pdf_path, insp=insp, source_text_by_page=source_text_by_page,
        )
        sure["kapi_ms"] = (time.perf_counter() - t0) * 1000

        # --- 3) critic CIKISTA, sayfa sayfa (D2 + E1 + D3)
        sayfalar = [(s.sayfa_no, s.markdown) for s in insp.pages]
        ham_karakter = {no: b.kaynak.get("karakter", 0)
                        for no, b in bayraklar.items()}
        bayrak_sozluk = {no: b.sozluk() for no, b in bayraklar.items()}

        t0 = time.perf_counter()
        degerlendirme = self.critic.evaluate_pages(
            {"pdf_path": pdf_path}, sayfalar,
            ham_karakter=ham_karakter, bayraklar=bayrak_sozluk)
        sure["critic_ms"] = (time.perf_counter() - t0) * 1000

        kalite = {s["sayfa_no"]: s["quality_score"]
                  for s in degerlendirme["sayfalar"]}
        # A10: kritik teshis skordan bagimsiz tetikler (plan 3.1-3).
        kritik = {s["sayfa_no"]: s["critical_issue"]
                  for s in degerlendirme["sayfalar"]}

        # --- 4) sayfa secici (E3 + A10)
        secim = sayfa_secici(bayraklar, kalite,
                             kalite_esik=self.kalite_esik,
                             yuksek_guven_yeter=self.yuksek_guven_yeter,
                             kritik=kritik)

        # --- 5) yol ayrimi: OCR sayfalari ayri, kalan agir sayfalar ayri
        # A10 sonrasi OCR nedeni iki adla gelebilir: kapinin `needs_ocr` bayragi
        # ve critic'in `critical_SCANNED_NEEDS_OCR` teshisi. Ikisi de OCR yolu.
        ocr_sayfa = [n for n in secim["agir_sayfalar"]
                     if any(x == "needs_ocr" or x.endswith("SCANNED_NEEDS_OCR")
                            for x in secim["sebep"][n])]
        agir_sayfa = [n for n in secim["agir_sayfalar"] if n not in set(ocr_sayfa)]

        plan = {
            "OCR": cagri_plani(ocr_sayfa, self.ocr_motoru) if ocr_sayfa else None,
            "AGIR": cagri_plani(agir_sayfa, "docling") if agir_sayfa else None,
        }

        # --- 6) sayfa basina provenance (plan E8)
        sayfa_kaydi: List[Dict[str, Any]] = []
        for s in degerlendirme["sayfalar"]:
            no = s["sayfa_no"]
            nedenler = secim["sebep"].get(no, [])
            if not nedenler:
                yol, motor = "HIZLI", "pdf-inspector"
            elif any(x == "needs_ocr" or x.endswith("SCANNED_NEEDS_OCR")
                     for x in nedenler):
                yol, motor = "OCR", self.ocr_motoru
            else:
                yol, motor = "AGIR", "docling"
            sayfa_kaydi.append({
                "sayfa_no": no,
                "yol": yol,
                "islenecek_motor": motor,
                "karar_kaynagi": nedenler,
                "quality_score": s["quality_score"],
                # Hangi cezanin skoru ne kadar dusurdugu (critic.sayfa_skoru).
                # Karara girmez -- `low_quality` gerekcesinin ARDINDAKI sebebi
                # gorunur kilar; onsuz "neden dusuk puan" sorusu ancak kod
                # okunarak cevaplanabiliyordu (rapor O.8.2).
                "kalite_cezalari": s.get("cezalar") or {},
                "critical_issue": s["critical_issue"],
                "needs_ocr": s["needs_ocr"],
                "has_table": s["has_table"],
                "has_figure": s["has_figure"],
                "tablo_guven": bayraklar[no].tablo_guven if no in bayraklar else None,
                # CODEX-2026-08-18: Preserve raw gate observations so C2 can
                # replay threshold choices without parsing all PDFs again.
                "gate_signals": dict(bayraklar[no].kaynak) if no in bayraklar else {},
            })

        toplam = len(sayfa_kaydi)
        hizli = sum(1 for s in sayfa_kaydi if s["yol"] == "HIZLI")

        sonuc: Dict[str, Any] = {
            "pdf_path": pdf_path,
            # --- provenance (plan E8). Profil hash'e KATILMAZ, burada kalir.
            "parser_profile": insp.profil,
            "router_version": ROUTER_VERSION,
            # Modul sabiti DEGIL bu ornegin profili: `ayar=` ile ezilmis bir
            # kosuda modul sabiti yanlis surumu bildirirdi.
            "esik_version": self.ayar.esik_version,
            "esik_profili": self.ayar.ozet(),
            "kalite_esik": self.kalite_esik,
            "yuksek_guven_yeter": self.yuksek_guven_yeter,
            # --- sonuc
            "sayfa_sayisi": toplam,
            "sayfalar": sayfa_kaydi,
            "belge": degerlendirme["belge"],
            "plan": plan,
            "kuyruk_skoru": kuyruk_skoru(bayraklar, toplam),
            "ozet": {
                "hizli_sayfa": hizli,
                "agir_sayfa": len(agir_sayfa),
                "ocr_sayfa": len(ocr_sayfa),
                "hizli_oran": round(hizli / toplam, 4) if toplam else 0.0,
                "yalniz_kalite_yakaladi": secim["ozet"]["yalniz_kalite"],
                "olculemeyen_sayfa": degerlendirme["belge"]["olculemeyen_sayfa"],
                "agir_cagri_sayisi": sum(
                    p["cagri_sayisi"] for p in plan.values() if p),
            },
            "sureler_ms": {k: round(v, 1) for k, v in sure.items()},
            "ms_sayfa": {k: round(v / max(toplam, 1), 2) for k, v in sure.items()},
        }
        if metin_dahil:
            sonuc["sayfa_metni"] = {s.sayfa_no: s.markdown for s in insp.pages}
            # Internal parse payload. Strings keep this mode JSON-serialisable;
            # SmartPdfParser consumes and removes it before provenance is built.
            sonuc["_source_text_by_page"] = source_text_by_page or {}
        return sonuc


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print("Kullanim: python tools/smart_router/orchestrator.py <pdf> [--json]")
        sys.exit(1)

    r = SmartRouterHatti().calistir(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        sys.exit(0)

    o = r["ozet"]
    print(f"PDF          : {os.path.basename(r['pdf_path'])}  ({r['sayfa_sayisi']} sayfa)")
    print(f"profil       : {r['parser_profile']}  |  {r['router_version']}")
    print(f"esik surumu  : {r['esik_version']}")
    print(f"belge kalitesi: {r['belge']['quality_score']}  "
          f"(sayfa medyani; esik alti {r['belge']['esik_alti_sayfa']} sayfa)")
    print(f"kuyruk skoru : {r['kuyruk_skoru']}")
    print()
    print(f"HIZLI {o['hizli_sayfa']:>4} | AGIR {o['agir_sayfa']:>4} | "
          f"OCR {o['ocr_sayfa']:>4}   -> hizli yolda kalan %{o['hizli_oran'] * 100:.0f}")
    print(f"agir motor cagri sayisi: {o['agir_cagri_sayisi']} "
          f"(ardisik bloklara bolunmus)")
    print(f"yalniz kalite kapisinin yakaladigi sayfa: {o['yalniz_kalite_yakaladi']}")
    print()
    print("maliyet (ms/sayfa):", r["ms_sayfa"])
    print()
    print(f"{'sayfa':>5} {'yol':<6} {'motor':<14} {'kalite':>7}  karar kaynagi")
    print("-" * 82)
    for s in r["sayfalar"][:40]:
        q = "-" if s["quality_score"] is None else f"{s['quality_score']:.1f}"
        print(f"{s['sayfa_no']:5d} {s['yol']:<6} {s['islenecek_motor']:<14} "
              f"{q:>7}  {', '.join(s['karar_kaynagi']) or '-'}")
    if len(r["sayfalar"]) > 40:
        print(f"  ... {len(r['sayfalar']) - 40} sayfa daha")
