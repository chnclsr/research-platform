"""Docling'in `do_picture_description` VLM'ini olcer: sekillerin ici okunabiliyor mu.

NEDEN BU KOSU
-------------
Olculdu (9 belge, 261 sayfa): sekillerin ICINDEKI hicbir sey metne girmiyor.

  * Docling 92 yerde `<!-- image -->` yer tutucusu koyup iceriginden hicbir sey
    okumuyor.
  * pdf-inspector iz bile birakmiyor (0 yer tutucu) -- sonraki katman o sayfada
    eksik bir sey oldugunu ANLAYAMAZ.
  * Kalite skoru bunu goremiyor: gpt3 s.67'de sayfanin %54'u raster gorsel,
    iki motor da yalnizca caption'i cikariyor, `quality_score` yine de 100,0.

Ayni desen ikinci bir korpusta da gorundu: C2'de kacirilan 19 faydali agir-motor
vakasinin 18'inde sekil, 16'sinda kalite skoru 100.

Docling 2.120+ `do_picture_description` tasiyor ama VARSAYILAN KAPALI ve hic
denenmedi. Bu betik onu acip su dort soruyu olcer:

  1) KAPSAMA   -- kac sekil aciklama aldi, kaci esigin altinda kalip atlandi?
  2) ICERIK    -- aciklama sekildeki metni/veriyi tasiyor mu, yoksa jenerik mi?
  3) MALIYET   -- sayfa basina ve sekil basina ek sure ne?
  4) FARK      -- ayni belge aciklamasiz kosuldugunda ne kaybediliyor?

NE OLCMEZ
---------
Bu ozellik sekildeki metnin OCR'ini degil, seklin ACIKLAMASINI uretir. Bir
grafigin ekseni yerine "iki cubuklu bir bar grafigi" yazabilir. Deep research
ajani icin hangisinin daha degerli oldugu AYRI bir sorudur; bu betik yalnizca
ne uretildigini kaydeder, degerini yargilamaz -- ciktiya bakip insan karar verir.

VARSAYILAN ESIK -- ATLAMA
-------------------------
`smolvlm_picture_description.picture_area_threshold = 0.05`: sayfanin %5'inden
kucuk gorseller aciklanmaz. Betik kac seklin bu yuzden atlandigini ayrica sayar,
cunku "aciklama uretilmedi" ile "aciklanmaya deger bulunmadi" ayri seylerdir.

KULLANIM
--------
    # once model iner (~500 MB), sonra kosar
    python src/gpu_sekil_aciklama.py --device cuda

    # yalniz gorsel agirlikli belgeler (hizli ilk bakis)
    python src/gpu_sekil_aciklama.py --device cuda --only gpt3

    # kendi promptumuzla: metin/veri iste, "betimle" deme
    python src/gpu_sekil_aciklama.py --device cuda --prompt-metin

Cikti:
    out/sekil_aciklama_<device>.json   -- sekil sekil aciklama, bbox, sure
    out/sekil_aciklama_<device>.md     -- gozle okunacak insan raporu
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kendi_korpus_yolu import BELGELER, CIKTI as OUT, dogrula, pdf as pdf_yolu  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BELGELER = ["turkce_makale", "resnet_2sutun_gorsel", "vgg_tablo_agirlikli",
            "attention_tablo", "bert_2sutun_dipnot", "sybil_tip_2sutun",
            "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
            "taranmis_bert_2sutun_dipnot"]

#: Varsayilan prompt "Describe this image in a few sentences." Bir arastirma
#: ajani icin seklin BETIMI degil ICINDEKI VERI daha degerli olabilir; bu ikinci
#: prompt onu istiyor. Hangisinin ise yaradigi OLCULMEDI -- ikisi de kosulup
#: ciktilari yan yana konacak.
METIN_PROMPT = (
    "Transcribe every piece of text visible in this image: axis labels, legends, "
    "numbers, table cells and captions. Then state in one sentence what the figure "
    "shows. If there is no readable text, say 'NO TEXT'."
)


def ortam() -> dict:
    bilgi = {"makine": platform.node(), "python": platform.python_version()}
    try:
        import torch
        bilgi["torch"] = torch.__version__
        bilgi["cuda_var"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            bilgi["gpu"] = torch.cuda.get_device_name(0)
            bilgi["gpu_bellek_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
    except ImportError:
        bilgi["torch"] = "yok"
    try:
        import docling
        bilgi["docling"] = getattr(docling, "__version__", "?")
    except ImportError:
        bilgi["docling"] = "yok"
    return bilgi


def donusturucu(device: str, aciklama: bool, prompt: str | None):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions,
        smolvlm_picture_description,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    esleme = {"cpu": AcceleratorDevice.CPU, "cuda": AcceleratorDevice.CUDA,
              "auto": AcceleratorDevice.AUTO}
    secenek = PdfPipelineOptions()
    secenek.accelerator_options = AcceleratorOptions(
        num_threads=os.cpu_count() or 4, device=esleme[device])
    if aciklama:
        secenek.do_picture_description = True
        vlm = smolvlm_picture_description.model_copy(deep=True)
        if prompt:
            vlm.prompt = prompt
        secenek.picture_description_options = vlm
        # Aciklama gorseli gerektiriyor; uretilmezse annotation bos doner.
        secenek.generate_picture_images = True
    return DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=secenek)}), secenek


def _aciklamalar(picture) -> list:
    """PictureItem.annotations icinden aciklama metinlerini toplar.

    Docling surumleri arasinda annotation sinifi degisebiliyor; sinif adina degil
    `text` alanina bakiyoruz ki bir surum yukseltmesi olcumu sessizce sifirlamasin.
    """
    cikan = []
    for a in getattr(picture, "annotations", None) or []:
        metin = getattr(a, "text", None)
        if metin:
            cikan.append({"tur": type(a).__name__, "metin": metin.strip()})
    return cikan


def _bbox(picture) -> dict | None:
    prov = getattr(picture, "prov", None) or []
    if not prov:
        return None
    p = prov[0]
    b = getattr(p, "bbox", None)
    if b is None:
        return {"sayfa": getattr(p, "page_no", None)}
    return {"sayfa": getattr(p, "page_no", None),
            "l": round(b.l, 1), "t": round(b.t, 1),
            "r": round(b.r, 1), "b": round(b.b, 1),
            "orijin": str(getattr(b, "coord_origin", ""))}


def belge_kos(conv, pdf: str) -> tuple:
    basladi = time.perf_counter()
    sonuc = conv.convert(pdf)
    sure = time.perf_counter() - basladi
    belge = sonuc.document
    sekiller = []
    for pic in getattr(belge, "pictures", None) or []:
        kutu = _bbox(pic)
        cap = ""
        try:
            cap = (pic.caption_text(belge) or "").strip()
        except Exception:
            pass
        sekiller.append({
            "bbox": kutu,
            "caption": cap,
            "aciklamalar": _aciklamalar(pic),
        })
    return sure, sekiller, belge.export_to_markdown()


def main() -> int:
    p = argparse.ArgumentParser(description="Docling sekil aciklama (VLM) olcumu")
    p.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cuda")
    p.add_argument("--only", help="belge adinda gecen metin")
    p.add_argument("--prompt-metin", action="store_true",
                   help="varsayilan 'betimle' yerine metin/veri isteyen prompt")
    p.add_argument("--taban-atla", action="store_true",
                   help="aciklamasiz taban kosusunu atla (yalniz VLM kosusu)")
    args = p.parse_args()

    hedef = [b for b in BELGELER if not args.only or args.only in b]
    if not hedef:
        print("Eslesen belge yok.")
        return 2

    dogrula(hedef)
    bilgi = ortam()
    print(json.dumps(bilgi, ensure_ascii=False, indent=1), flush=True)
    if args.device == "cuda" and not bilgi.get("cuda_var"):
        print("\nHATA: --device cuda istendi ama torch CUDA gormuyor.")
        return 2

    prompt = METIN_PROMPT if args.prompt_metin else None
    kayit = {"ortam": bilgi, "device": args.device,
             "prompt": prompt or "(docling varsayilani)",
             "belgeler": []}

    # --- taban: aciklama KAPALI. Ek maliyeti ve ek icerigi ayirmak icin.
    taban_sure = {}
    if not args.taban_atla:
        print("\n--- TABAN (aciklama kapali) ---", flush=True)
        conv0, _ = donusturucu(args.device, False, None)
        belge_kos(conv0, pdf_yolu(hedef[0]))  # isinma
        for stem in hedef:
            sure, sekiller, _ = belge_kos(conv0, pdf_yolu(stem))
            taban_sure[stem] = sure
            print("%-30s %6.1f sn  %d sekil" % (stem, sure, len(sekiller)), flush=True)

    # --- VLM acik
    print("\n--- VLM ACIK (model iniyor olabilir, ilk kosu uzun surer) ---", flush=True)
    yukleme = time.perf_counter()
    conv, secenek = donusturucu(args.device, True, prompt)
    belge_kos(conv, pdf_yolu(hedef[0]))  # isinma + model indirme
    print("Isinma: %.1f sn\n" % (time.perf_counter() - yukleme), flush=True)
    kayit["esik"] = {
        "picture_area_threshold": secenek.picture_description_options.picture_area_threshold,
        "repo_id": secenek.picture_description_options.repo_id,
        "batch_size": secenek.picture_description_options.batch_size,
    }

    print("%-30s %6s %7s %7s %8s" % ("belge", "sn", "sekil", "aciklan", "ek sure"), flush=True)
    print("-" * 64)
    for stem in hedef:
        sure, sekiller, _ = belge_kos(conv, pdf_yolu(stem))
        aciklanan = sum(1 for s in sekiller if s["aciklamalar"])
        ek = sure - taban_sure.get(stem, sure)
        kayit["belgeler"].append({
            "belge": stem, "sure_sn": round(sure, 2),
            "taban_sn": round(taban_sure[stem], 2) if stem in taban_sure else None,
            "ek_sure_sn": round(ek, 2) if taban_sure else None,
            "sekil_sayisi": len(sekiller), "aciklanan": aciklanan,
            "atlanan": len(sekiller) - aciklanan,
            "sekiller": sekiller,
        })
        print("%-30s %6.1f %7d %7d %8s" % (
            stem, sure, len(sekiller), aciklanan,
            "%.1f" % ek if taban_sure else "-"), flush=True)

    toplam = sum(b["sekil_sayisi"] for b in kayit["belgeler"])
    aciklanan = sum(b["aciklanan"] for b in kayit["belgeler"])
    kayit["ozet"] = {"sekil": toplam, "aciklanan": aciklanan,
                     "atlanan": toplam - aciklanan,
                     "kapsama": round(aciklanan / max(toplam, 1), 3)}
    print("-" * 64)
    print("TOPLAM %d sekil, %d aciklandi (%%%.0f), %d atlandi"
          % (toplam, aciklanan, 100 * aciklanan / max(toplam, 1), toplam - aciklanan))

    yol = os.path.join(OUT, "sekil_aciklama_%s.json" % args.device)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)

    # --- gozle okunacak rapor: aciklamalar gercekten ise yariyor mu
    md = ["# Şekil açıklama (VLM) — gözle inceleme", "",
          "Model: `%s` · eşik: alanın %%%.0f'i · prompt: %s" % (
              kayit["esik"]["repo_id"],
              100 * kayit["esik"]["picture_area_threshold"],
              kayit["prompt"]),
          "",
          "**Bakılacak şey:** açıklama şekildeki gerçek metni/veriyi taşıyor mu, "
          "yoksa jenerik bir betim mi? Jenerikse bu özellik bizim boşluğumuzu "
          "kapatmıyor demektir.", ""]
    for b in kayit["belgeler"]:
        md.append("## %s — %d şekil, %d açıklandı" % (b["belge"], b["sekil_sayisi"], b["aciklanan"]))
        for i, s in enumerate(b["sekiller"], 1):
            if not s["aciklamalar"]:
                continue
            sayfa = (s["bbox"] or {}).get("sayfa", "?")
            md.append("")
            md.append("**%d. şekil — s.%s**" % (i, sayfa))
            if s["caption"]:
                md.append("- caption: %s" % s["caption"][:300])
            for a in s["aciklamalar"]:
                md.append("- açıklama (%s): %s" % (a["tur"], a["metin"][:600]))
        md.append("")
    with open(os.path.join(OUT, "sekil_aciklama_%s.md" % args.device), "w",
              encoding="utf-8") as f:
        f.write("\n".join(md))

    print("\n-> %s" % yol)
    print("-> %s" % os.path.join(OUT, "sekil_aciklama_%s.md" % args.device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
