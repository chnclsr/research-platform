"""MinerU'yu 9 PDF'lik korpusta kostur, sureyi TEMIZ olc, ciktilari uyumlu isimle yaz.

NEDEN AYRI SCRIPT / AYRI ORTAM
------------------------------
MinerU ana .venv'e KURULMADI. torch + 112 paket ana ortama girerse numpy/pillow
surumleri degisip mevcut kalibre olcumleri (inspector 0.0042 sn/belge,
pymupdf4llm 1.65 sn/belge) sessizce kaydirabilir. Bu yuzden .venv-mineru ayri.
Bu script ANA .venv ile calisir, MinerU'yu alt surec olarak cagirir.

SURE OLCUMU -- neden kalici servis
----------------------------------
`mineru` CLI'si her cagrida gecici bir FastAPI servisi acip modelleri bastan
yukluyor. Duman testinde bu ~25 sn ek yuk demekti. Belge basina sureye bunu
katmak yaniltici olur: gercek kullanimda servis bir kez ayaga kalkar.
Bu yuzden servisi BIR KEZ baslatip her belgeyi --api-url ile ona yolluyoruz.
Olculen sey: modeller yuklendikten SONRA belge basina sure.
Servisin ayaga kalkma suresi ayrica raporlanir (baslangic_sn).

GPU YOK
-------
Bu makinede NVIDIA GPU yok (Intel UHD 770). Bu yuzden backend=pipeline.
MinerU'nun SOTA modlari (vlm-engine / hybrid-engine, OmniDocBench 95.3-95.7)
Volta+ NVIDIA GPU istiyor; pipeline 86.47. Yani buradaki sayilar MinerU'nun
tavani DEGIL, GPU'suz tabanidir.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\mineru_kos.py
    .\\.venv\\Scripts\\python.exe src\\mineru_kos.py --only resnet
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
CORPUS_DIR = os.path.join(BASE, "corpus")
OUT_DIR = os.path.join(BASE, "out")
MINERU_OUT = os.path.join(OUT_DIR, "mineru")
JSON_OUT = os.path.join(OUT_DIR, "mineru_json")

VENV = os.path.join(BASE, ".venv-mineru", "Scripts")
MINERU_EXE = os.path.join(VENV, "mineru.exe")
API_EXE = os.path.join(VENV, "mineru-api.exe")

HOST = "127.0.0.1"
PORT = 5010
API_URL = f"http://{HOST}:{PORT}"
BACKEND = "pipeline"          # GPU olmadigi icin tek gercekci secenek
SERVIS_TAVAN_SN = 300         # servis bu surede ayaga kalkmazsa vazgec
BELGE_TAVAN_SN = 3600         # tek belge icin azami sure (gpt4 100 sayfa, CPU)

BELGELER = [
    "attention_tablo", "bert_2sutun_dipnot", "vgg_tablo_agirlikli",
    "resnet_2sutun_gorsel", "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
    "sybil_tip_2sutun", "turkce_makale", "taranmis_bert_2sutun_dipnot",
]


def servisi_baslat():
    """Kalici mineru-api servisini ac ve hazir olana kadar bekle."""
    log = open(os.path.join(OUT_DIR, "_mineru_servis.log"), "w", encoding="utf-8")
    p = subprocess.Popen([API_EXE, "--host", HOST, "--port", str(PORT)],
                         stdout=log, stderr=subprocess.STDOUT)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < SERVIS_TAVAN_SN:
        if p.poll() is not None:
            raise RuntimeError("mineru-api surec olarak oldu; out/_mineru_servis.log'a bak")
        try:
            with urllib.request.urlopen(f"{API_URL}/docs", timeout=2) as r:
                if r.status == 200:
                    return p, round(time.perf_counter() - t0, 2)
        except (urllib.error.URLError, OSError):
            time.sleep(1.0)
    p.terminate()
    raise RuntimeError(f"mineru-api {SERVIS_TAVAN_SN} sn icinde hazir olmadi")


def belgeyi_kostur(stem: str) -> dict:
    pdf = os.path.join(CORPUS_DIR, stem + ".pdf")
    if not os.path.exists(pdf):
        return {"belge": stem, "hata": "PDF yok"}

    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            [MINERU_EXE, "-p", pdf, "-o", MINERU_OUT, "-b", BACKEND,
             "--api-url", API_URL],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=BELGE_TAVAN_SN,
        )
    except subprocess.TimeoutExpired:
        return {"belge": stem, "hata": f"{BELGE_TAVAN_SN} sn asildi",
                "sure_sn": None}
    sure = round(time.perf_counter() - t0, 3)

    if r.returncode != 0:
        return {"belge": stem, "hata": f"cikis kodu {r.returncode}",
                "sure_sn": sure, "stderr_kuyruk": (r.stderr or "")[-800:]}

    # MinerU cikti duzeni: <out>/<stem>/<method>/<stem>.md
    kok = os.path.join(MINERU_OUT, stem)
    yontem = None
    if os.path.isdir(kok):
        altlar = [d for d in os.listdir(kok) if os.path.isdir(os.path.join(kok, d))]
        yontem = altlar[0] if altlar else None
    if not yontem:
        return {"belge": stem, "hata": "cikti klasoru bulunamadi", "sure_sn": sure}

    md_yol = os.path.join(kok, yontem, f"{stem}.md")
    cl_yol = os.path.join(kok, yontem, f"{stem}_content_list.json")
    if not os.path.exists(md_yol):
        return {"belge": stem, "hata": "markdown uretilmedi", "sure_sn": sure}

    # compare.py ile ayni isimlendirme: out/<belge>__<parser>.md
    shutil.copyfile(md_yol, os.path.join(OUT_DIR, f"{stem}__mineru.md"))
    if os.path.exists(cl_yol):
        os.makedirs(JSON_OUT, exist_ok=True)
        shutil.copyfile(cl_yol, os.path.join(JSON_OUT, f"{stem}_content_list.json"))

    md = open(md_yol, encoding="utf-8").read()
    ogeler = []
    if os.path.exists(cl_yol):
        ogeler = json.load(open(cl_yol, encoding="utf-8"))

    from collections import Counter
    tipler = Counter(o.get("type") for o in ogeler)

    return {
        "belge": stem,
        "yontem": yontem,                       # auto / txt / ocr
        "sure_sn": sure,
        "karakter": len(md),
        "html_tablo": md.count("<table>"),
        "gorsel_ref": md.count("!["),
        "oge_sayisi": len(ogeler),
        "oge_tipleri": dict(tipler),
        "sayfa": (max((o.get("page_idx", 0) for o in ogeler), default=-1) + 1),
    }


def main():
    hedef = BELGELER
    if "--only" in sys.argv:
        ara = sys.argv[sys.argv.index("--only") + 1].lower()
        hedef = [b for b in BELGELER if ara in b.lower()]
        if not hedef:
            print(f"'{ara}' ile eslesen belge yok"); return

    os.makedirs(MINERU_OUT, exist_ok=True)
    print(f"MinerU backend={BACKEND} (GPU yok -> pipeline)  {len(hedef)} belge")
    print("Servis baslatiliyor...", flush=True)
    p, bas_sn = servisi_baslat()
    print(f"  servis hazir: {bas_sn} sn (modeller yukleniyor, ilk belgede ek gecikme olabilir)\n",
          flush=True)

    sonuc = {"backend": BACKEND, "baslangic_sn": bas_sn, "belgeler": []}
    try:
        for i, stem in enumerate(hedef, 1):
            print(f"[{i}/{len(hedef)}] {stem} ...", end=" ", flush=True)
            r = belgeyi_kostur(stem)
            sonuc["belgeler"].append(r)
            if "hata" in r:
                print(f"HATA: {r['hata']}", flush=True)
            else:
                print(f"{r['sure_sn']:8.2f} sn  {r['karakter']:7,} krk  "
                      f"{r['html_tablo']:3} tablo  {r['sayfa']:3} sayfa", flush=True)
            with open(os.path.join(OUT_DIR, "mineru_sureler.json"), "w",
                      encoding="utf-8") as f:
                json.dump(sonuc, f, ensure_ascii=False, indent=2)
    finally:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()

    print("\nout/mineru_sureler.json yazildi")


if __name__ == "__main__":
    main()
