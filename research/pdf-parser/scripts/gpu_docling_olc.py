"""GPU'lu makinede Docling'i olcer: hiz, determinizm ve cikti esdegerligi.

NEDEN BU KOSU
-------------
Butun yonlendirme mimarimiz TEK bir olculmus orana dayaniyor: kapi 12 ms/sayfa,
Docling 3.618 ms/sayfa -> agir motor ~300 kat pahali. Bu oran CPU'da olculdu
(Intel UHD 770, NVIDIA yok). GPU'da Docling ucuzlarsa "neden sayfa seciyoruz"
sorusunun cevabi zayiflar ve C2'nin en kotu bulgusu -- route precision 0,41,
yani agir cagrilarin %59'u bosa -- pahali olmaktan cikar.

Bu betik uc soruyu ayri ayri cevaplar:

  1) HIZ        -- ayni korpus, ayni Docling surumu, CPU vs GPU.
  2) DETERMINIZM-- ayni PDF birden cok kez kosuldugunda cikti BAYT BAYT ayni mi?
                   `registry.py` "ayni baytlar her kosuda ayni ciktiyi vermeli"
                   diyor ve `content_hash = sha256(metin)`. GPU inference
                   cogunlukla bit duzeyinde tekrarlanabilir DEGILDIR; degilse
                   GPU'lu uretim bu sozlesmeyi bozar. Hizdan onemli bir kisit.
  3) ESDEGERLIK -- GPU ciktisi CPU ciktisiyla ayni mi? Farkliysa kalite
                   olcumlerimiz (C1 utility, karantina kararlari) GPU'da
                   yeniden alinmali.

METODOLOJI KURALI -- ATLAMA
---------------------------
Bu makinedeki GPU sayisini bizim CPU sayimizla dogrudan karsilastirmak IKI
degiskeni birden degistirir: farkli islemci + GPU. Bu yuzden ayni makinede
once `--device cpu` kosulur, sonra `--device cuda`. Karsilastirma o iki sayi
arasinda yapilir.

KULLANIM
--------
    # 1) Ayni makinede CPU tabani
    python src/gpu_docling_olc.py --device cpu  --runs 1

    # 2) GPU
    python src/gpu_docling_olc.py --device cuda --runs 1

    # 3) Determinizm: tek belge, 3 kez, cikti hash'i karsilastirilir
    python src/gpu_docling_olc.py --device cuda --determinizm 3 --only turkce

    # 4) AYNI makinedeki CPU kosusuyla esdegerlik -- sayfa duzeyinde atif
    python src/gpu_docling_olc.py --device cuda --karsilastir out/gpu_docling_json_cpu

Cikti (ikisi de CIHAZA GORE ayri; ayni dizine yazmak CPU metnini eziyordu):
    out/gpu_docling_<device>.json                       -- sureler ve kararlar
    out/gpu_docling_json_<device>/<belge>_sayfalar.json -- sayfa markdown'i
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time

# torch.compile Windows'ta MSVC ariyor, yoksa donusumu tamamen coturuyor.
# docling_kos.py'de de ayni satir var; oradan bire bir tasindi.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kendi_korpus_yolu import BELGELER, CIKTI as OUT, dogrula, pdf as pdf_yolu  # noqa: E402


def json_dizini(device: str) -> str:
    """Cihaza gore AYRI dizin.

    Ilk surum ikisini de `gpu_docling_json/`a yazdi ve GPU kosusu CPU'nun sayfa
    metnini ezdi. Sonuc: ayni makinede CPU ile GPU'nun 9 belgenin 4'unde FARKLI
    cikti verdigi belge duzeyi hash'lerden kanitlanabildi, ama HANGI SAYFADA ve
    NEYIN kaybedildigi gosterilemedi -- `gpt3` s.50'de bir markdown tablosunun
    tamamen kaybolmasinin cihazdan mi Docling surumunden mi geldigi ayrilamadi.
    Cikti dizinini cihaza baglamak o atfi mumkun kiliyor.
    """
    return os.path.join(OUT, "gpu_docling_json_" + device)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def ortam() -> dict:
    """Sayilarin hangi donanimda alindigi cikti dosyasinda kalsin.

    Bir hiz sayisi hangi makinede alindigi yazilmadan tasinamaz; bu proje daha
    once ayni hatayi bir kez yapti (rapor kalici worker sureleri diye koprulu
    olculmus 51 belgeyi de sayiya katmisti).
    """
    bilgi = {
        "makine": platform.node(),
        "islemci": platform.processor(),
        "python": platform.python_version(),
        "os": platform.platform(),
    }
    try:
        import torch
        bilgi["torch"] = torch.__version__
        bilgi["cuda_var"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            bilgi["gpu"] = torch.cuda.get_device_name(0)
            bilgi["gpu_bellek_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
            bilgi["cuda_surum"] = torch.version.cuda
    except ImportError:
        bilgi["torch"] = "yok"
    try:
        import docling
        bilgi["docling"] = getattr(docling, "__version__", "?")
    except ImportError:
        bilgi["docling"] = "yok"
    return bilgi


def donusturucu(device: str, threads: int):
    """Cihazi ACIKCA secer. AUTO birakmak, hangi sayinin nereden geldigini belirsizlestirir."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    esleme = {"cpu": AcceleratorDevice.CPU, "cuda": AcceleratorDevice.CUDA,
              "auto": AcceleratorDevice.AUTO}
    secenek = PdfPipelineOptions()
    secenek.accelerator_options = AcceleratorOptions(
        num_threads=threads, device=esleme[device])
    return DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=secenek)})


def sayfa_metinleri(belge, sayfa_sayisi: int) -> list:
    """export_to_markdown(page_no=N) resmi API; docling_kos.py ile ayni yol."""
    sayfalar = []
    for no in range(1, sayfa_sayisi + 1):
        try:
            sayfalar.append(belge.export_to_markdown(page_no=no))
        except Exception:
            sayfalar.append("")
    return sayfalar


def _ozet(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def belge_kos(conv, pdf: str) -> tuple:
    """Tek belgeyi donustur; (sure_sn, sayfa_markdownlari, tam_markdown) dondurur."""
    basladi = time.perf_counter()
    sonuc = conv.convert(pdf)
    sure = time.perf_counter() - basladi
    belge = sonuc.document
    n = len(getattr(belge, "pages", []) or []) or 1
    return sure, sayfa_metinleri(belge, n), belge.export_to_markdown()


def main() -> int:
    p = argparse.ArgumentParser(description="Docling CPU/GPU olcumu")
    p.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto")
    p.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    p.add_argument("--runs", type=int, default=1, help="hiz icin tekrar sayisi (medyan)")
    p.add_argument("--determinizm", type=int, default=0,
                   help="tek belgeyi N kez kosup cikti hash'lerini karsilastirir")
    p.add_argument("--only", help="belge adinda gecen metin (ornek: turkce)")
    p.add_argument("--karsilastir", help="onceki kosunun <belge>_sayfalar.json dizini")
    args = p.parse_args()

    hedef = [b for b in BELGELER if not args.only or args.only in b]
    if not hedef:
        print("Eslesen belge yok.")
        return 2
    dogrula(hedef)
    json_out = json_dizini(args.device)
    os.makedirs(json_out, exist_ok=True)

    bilgi = ortam()
    print(json.dumps(bilgi, ensure_ascii=False, indent=1), flush=True)
    if args.device == "cuda" and not bilgi.get("cuda_var"):
        print("\nHATA: --device cuda istendi ama torch CUDA gormuyor.")
        print("Once `python -c \"import torch;print(torch.cuda.is_available())\"` kontrol et.")
        return 2

    print("\nModel yukleniyor (device=%s)..." % args.device, flush=True)
    yuk_basladi = time.perf_counter()
    conv = donusturucu(args.device, args.threads)
    # Ilk donusum modelleri gercekten yukler; isinma ayri olculur ki belge
    # sureleri model yukleme maliyetini icermesin.
    isinma_pdf = pdf_yolu(hedef[0])
    belge_kos(conv, isinma_pdf)
    isinma = time.perf_counter() - yuk_basladi
    print("Isinma (model yukleme + ilk belge): %.1f sn\n" % isinma, flush=True)

    kayit = {"ortam": bilgi, "device": args.device, "threads": args.threads,
             "runs": args.runs, "isinma_sn": round(isinma, 2), "belgeler": []}

    print("%-30s %6s %8s %10s" % ("belge", "sayfa", "sn", "ms/sayfa"), flush=True)
    print("-" * 60)
    for stem in hedef:
        pdf = pdf_yolu(stem)
        sureler, sayfalar, tam = [], None, None
        for _ in range(max(args.runs, 1)):
            sure, sayfalar, tam = belge_kos(conv, pdf)
            sureler.append(sure)
        n = len(sayfalar)
        medyan = statistics.median(sureler)
        with open(os.path.join(json_out, stem + "_sayfalar.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"sayfalar": sayfalar, "device": args.device}, f,
                      ensure_ascii=False)
        kayit["belgeler"].append({
            "belge": stem, "sayfa": n,
            "sure_sn": round(medyan, 3),
            "ms_sayfa": round(medyan * 1000 / max(n, 1), 1),
            "tum_kosular_sn": [round(s, 3) for s in sureler],
            "karakter": len(tam), "markdown_sha256": _ozet(tam),
        })
        print("%-30s %6d %8.2f %10.1f" % (stem, n, medyan, medyan * 1000 / max(n, 1)),
              flush=True)

    toplam_sn = sum(b["sure_sn"] for b in kayit["belgeler"])
    toplam_sayfa = sum(b["sayfa"] for b in kayit["belgeler"])
    kayit["toplam_sn"] = round(toplam_sn, 1)
    kayit["toplam_sayfa"] = toplam_sayfa
    kayit["ortalama_ms_sayfa"] = round(toplam_sn * 1000 / max(toplam_sayfa, 1), 1)
    print("-" * 60)
    print("TOPLAM %d sayfa  %.1f sn  ->  %.0f ms/sayfa"
          % (toplam_sayfa, toplam_sn, kayit["ortalama_ms_sayfa"]))

    # ---------------------------------------------------------- determinizm
    if args.determinizm > 1:
        stem = hedef[0]
        pdf = pdf_yolu(stem)
        print("\nDETERMINIZM: %s, %d kosu" % (stem, args.determinizm), flush=True)
        ozetler = []
        for i in range(args.determinizm):
            _, _, tam = belge_kos(conv, pdf)
            ozetler.append(_ozet(tam))
            print("  kosu %d: %s" % (i + 1, ozetler[-1][:16]), flush=True)
        ayni = len(set(ozetler)) == 1
        kayit["determinizm"] = {
            "belge": stem, "kosu": args.determinizm,
            "hepsi_ayni": ayni, "ozetler": ozetler,
        }
        print("  -> %s" % ("BAYT BAYT AYNI" if ayni else
                           "FARKLI! content_hash sozlesmesi GPU'da tutmuyor"))

    # --------------------------------------------------------- esdegerlik
    if args.karsilastir:
        kok = args.karsilastir if os.path.isabs(args.karsilastir) \
            else os.path.join(BASE, args.karsilastir)
        fark = []
        for stem in hedef:
            onceki = os.path.join(kok, stem + "_sayfalar.json")
            yeni = os.path.join(json_out, stem + "_sayfalar.json")
            if not os.path.isfile(onceki):
                fark.append({"belge": stem, "durum": "onceki kosu yok"})
                continue
            with open(onceki, encoding="utf-8") as f:
                a = json.load(f).get("sayfalar") or []
            with open(yeni, encoding="utf-8") as f:
                b = json.load(f).get("sayfalar") or []
            farkli = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
            fark.append({"belge": stem, "sayfa": len(b),
                         "farkli_sayfa": len(farkli), "ornekler": farkli[:5]})
        kayit["esdegerlik"] = {"taban": args.karsilastir, "belgeler": fark}
        toplam_farkli = sum(f.get("farkli_sayfa", 0) for f in fark)
        print("\nESDEGERLIK (taban: %s): %d sayfada fark" % (args.karsilastir, toplam_farkli))
        for f in fark:
            if f.get("farkli_sayfa"):
                print("  %-30s %d/%d sayfa farkli %s"
                      % (f["belge"], f["farkli_sayfa"], f["sayfa"], f["ornekler"]))

    yol = os.path.join(OUT, "gpu_docling_%s.json" % args.device)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)
    print("\n-> %s" % yol)
    print("-> %s" % json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
