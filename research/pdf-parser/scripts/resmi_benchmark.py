"""RESMI opendataloader-bench'i kendi parser'larimizla calistirir.

NEDEN BU SCRIPT
---------------
Onceki skorlar (referans_skor.py) BENIM yazdigim metriklerdi. "Kendi
metrigini yazip kendi sonucunu uretmek" itirazi hakli. Bu script o itirazi
tamamen kapatir:

    * PDF'ler         : ONLARIN 200 belgesi        (tools/opendataloader-bench/pdfs)
    * Referans        : ONLARIN elle hazirladigi   (ground-truth/markdown)
    * Metrik kodu     : ONLARIN kodu               (src/evaluator_*.py, degistirilmedi)
    * Toplama mantigi : ONLARIN mantigi            (belge basi ortalama, sonra belgeler arasi)

Bizim kattigimiz tek sey: parser'lari calistirip Markdown uretmek.

DOGRULAMA
---------
Depoda opendataloader ve pymupdf4llm icin ONLARIN yayinladigi sonuclar da
var (prediction/<motor>/evaluation.json). Ayni motorlari biz de kosturup
sayilari karsilastiriyoruz. Tutuyorsa boru hattimiz dogru demektir; bu,
"olcumu kendine gore ayarlamis olabilir misin" sorusunun cevabidir.

SURUM UYARISI: onlarin sayilari farkli surumlerle alinmis --
    opendataloader 2.2.1  (bizde 2.5.0)
    pymupdf4llm    0.2.0   (bizde 1.28.2, ONNX duzen modeli ile)
Yani birebir ayni cikmasi beklenmez; YAKIN cikmasi beklenir.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\resmi_benchmark.py            # hepsi
    .\\.venv\\Scripts\\python.exe src\\resmi_benchmark.py --limit 25 # ilk 25 belge (deneme)
    .\\.venv\\Scripts\\python.exe src\\resmi_benchmark.py --only inspector
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import traceback

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
BENCH = os.path.join(BASE, "tools", "opendataloader-bench")
PDF_DIR = os.path.join(BENCH, "pdfs")
GT_DIR = os.path.join(BENCH, "ground-truth", "markdown")
CIKTI = os.path.join(BASE, "out", "resmi_benchmark")
JSON_YOL = os.path.join(BASE, "resmi_benchmark_sonuc.json")

JRE_BIN = os.path.join(BASE, "tools", "jdk-21.0.12+8-jre", "bin")
if os.path.isdir(JRE_BIN):
    os.environ["PATH"] = JRE_BIN + os.pathsep + os.environ.get("PATH", "")
    os.environ["JAVA_HOME"] = os.path.dirname(JRE_BIN)

# ONLARIN metrik kodu -- degistirilmeden import ediliyor
sys.path.insert(0, os.path.join(BENCH, "src"))
from evaluator_heading_level import evaluate_heading_level  # noqa: E402
from evaluator_reading_order import evaluate_reading_order  # noqa: E402
from evaluator_table import evaluate_table  # noqa: E402

import opendataloader_pdf  # noqa: E402
import pdf_inspector  # noqa: E402
import pymupdf4llm  # noqa: E402
import pypdf  # noqa: E402


# ======================================================================
#  PARSERLAR  (compare.py ile ayni cagrilar)
# ======================================================================

def p_pypdf(path: str) -> str:
    reader = pypdf.PdfReader(path)
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def p_inspector(path: str) -> str:
    return pdf_inspector.process_pdf(path).markdown or ""


def p_odl(path: str) -> str:
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="odlb_")
    try:
        opendataloader_pdf.convert(input_path=path, output_dir=tmp,
                                   format=["markdown"], image_output="off",
                                   quiet=True)
        for root, _d, files in os.walk(tmp):
            for fn in files:
                if fn.lower().endswith(".md"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        return f.read()
        return ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def p_p4llm(path: str) -> str:
    return pymupdf4llm.to_markdown(path, show_progress=False)


PARSERS = {
    "pypdf": p_pypdf,
    "inspector": p_inspector,
    "opendataloader": p_odl,
    "pymupdf4llm": p_p4llm,
}

# Depoda yayinlanmis, karsilastirma icin (motor adi -> klasor)
ONLARIN = {"opendataloader": "opendataloader", "pymupdf4llm": "pymupdf4llm"}


# ======================================================================

def onlarin_skoru(klasor: str) -> dict | None:
    f = os.path.join(BENCH, "prediction", klasor, "evaluation.json")
    if not os.path.exists(f):
        return None
    with open(f, encoding="utf-8") as fh:
        j = json.load(fh)
    s = (j.get("score") or j.get("metrics", {}).get("score") or {})
    if not s:
        for v in j.values():
            if isinstance(v, dict) and "overall_mean" in v:
                s = v
                break
    return s or None


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].lower()

    pdfs = sorted(f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf"))
    if limit:
        pdfs = pdfs[:limit]
    print(f"{len(pdfs)} belge | referans: {GT_DIR}")
    print("metrik kodu: ONLARIN (tools/opendataloader-bench/src), degistirilmedi\n")

    os.makedirs(CIKTI, exist_ok=True)
    tum = {}

    for ad, fn in PARSERS.items():
        if only and only not in ad:
            continue
        print(f"=== {ad} ===", flush=True)
        hedef = os.path.join(CIKTI, ad)
        os.makedirs(hedef, exist_ok=True)

        belge_skor, sureler, hata = [], [], 0
        for i, pdf in enumerate(pdfs, 1):
            doc_id = os.path.splitext(pdf)[0]
            gt_yol = os.path.join(GT_DIR, doc_id + ".md")
            if not os.path.exists(gt_yol):
                continue
            with open(gt_yol, encoding="utf-8") as f:
                gt = f.read()

            md_yol = os.path.join(hedef, doc_id + ".md")
            if os.path.exists(md_yol):
                with open(md_yol, encoding="utf-8") as f:
                    pred = f.read()
            else:
                t0 = time.perf_counter()
                try:
                    pred = fn(os.path.join(PDF_DIR, pdf))
                except Exception:
                    pred, hata = "", hata + 1
                    if hata <= 2:
                        print("   HATA:", traceback.format_exc(limit=1).strip()[:120])
                sureler.append(time.perf_counter() - t0)
                with open(md_yol, "w", encoding="utf-8") as f:
                    f.write(pred)

            nid, _ = evaluate_reading_order(gt, pred)
            teds, _ = evaluate_table(gt, pred)
            mhs, _ = evaluate_heading_level(gt, pred)
            bilesen = [v for v in (nid, teds, mhs) if v is not None]
            belge_skor.append({
                "id": doc_id, "nid": nid, "teds": teds, "mhs": mhs,
                "overall": (sum(bilesen) / len(bilesen)) if bilesen else None,
            })
            if i % 50 == 0:
                print(f"   {i}/{len(pdfs)}", flush=True)

        def ort(k):
            d = [s[k] for s in belge_skor if s[k] is not None]
            return (sum(d) / len(d)) if d else 0.0

        def adet(k):
            return sum(1 for s in belge_skor if s[k] is not None)

        tum[ad] = {
            "overall": ort("overall"), "nid": ort("nid"),
            "teds": ort("teds"), "mhs": ort("mhs"),
            "nid_adet": adet("nid"), "teds_adet": adet("teds"),
            "mhs_adet": adet("mhs"),
            "belge": len(belge_skor), "hata": hata,
            "sn_belge": round(statistics.mean(sureler), 4) if sureler else None,
        }
        r = tum[ad]
        print(f"   overall={r['overall']:.3f}  nid={r['nid']:.3f}  "
              f"teds={r['teds']:.3f} ({r['teds_adet']} belgede)  "
              f"mhs={r['mhs']:.3f} ({r['mhs_adet']} belgede)"
              + (f"  {r['sn_belge']:.3f} sn/belge" if r["sn_belge"] else "")
              + (f"  HATA={hata}" if hata else ""), flush=True)

    # ---------------- sonuc ----------------
    print("\n" + "=" * 92)
    print(f"RESMI BENCHMARK  ({len(pdfs)} belge, onlarin PDF'i / referansi / metrik kodu)")
    print("=" * 92)
    print(f"{'ENGINE':20}{'OVERALL':>10}{'READING ORDER':>15}{'TABLES':>9}{'HEADINGS':>11}"
          f"{'sn/belge':>11}")
    print("-" * 92)
    for ad, r in sorted(tum.items(), key=lambda x: -x[1]["overall"]):
        print(f"{ad:20}{r['overall']:>10.3f}{r['nid']:>15.3f}{r['teds']:>9.3f}"
              f"{r['mhs']:>11.3f}"
              + (f"{r['sn_belge']:>11.3f}" if r["sn_belge"] else f"{'-':>11}"))
    print("-" * 92)

    # ---------------- dogrulama ----------------
    print("\nDOGRULAMA -- ayni motorda bizim sayimiz vs onlarin yayinladigi")
    print(f"{'motor':20}{'bizim':>10}{'onlarin':>10}{'fark':>9}   not")
    print("-" * 78)
    for ad, klasor in ONLARIN.items():
        if ad not in tum:
            continue
        o = onlarin_skoru(klasor)
        if not o:
            continue
        bizim = tum[ad]["overall"]
        onlar = o.get("overall_mean", 0.0)
        print(f"{ad:20}{bizim:>10.3f}{onlar:>10.3f}{bizim - onlar:>+9.3f}   "
              f"(surum farki var)")
    print("-" * 78)

    with open(JSON_YOL, "w", encoding="utf-8") as f:
        json.dump(tum, f, ensure_ascii=False, indent=2)
    print(f"\nJSON: {JSON_YOL}")


if __name__ == "__main__":
    main()
