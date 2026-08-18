"""Var olan bir PDF'ten 'taranmis' (resim tabanli) PDF uretir.

Mantik: her sayfayi goruntuye cevirip o goruntuleri yeni bir PDF'e koyar.
Sonucta PDF'in icinde HIC metin katmani kalmaz -> tipki tarayicidan gecmis
bir belge gibi. pdf-inspector'in 'image_based' + needs_ocr davranisini
temiz sekilde test etmemizi saglar.

Kullanim:
    .venv\\Scripts\\python.exe make_scanned.py
    .venv\\Scripts\\python.exe make_scanned.py corpus\\turkce_makale.pdf
"""
import os
import sys

import pypdfium2 as pdfium
from PIL import Image

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
CORPUS = os.path.join(
    os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj"),
    'corpus')
DEFAULT_SRC = os.path.join(CORPUS, "bert_2sutun_dipnot.pdf")
MAX_PAGES = 6      # dosya boyutu sismesin diye
DPI = 150          # tipik tarayici cozunurlugu


def make_scanned(src: str, dest: str) -> None:
    pdf = pdfium.PdfDocument(src)
    n = min(len(pdf), MAX_PAGES)
    scale = DPI / 72.0

    images: list[Image.Image] = []
    for i in range(n):
        bitmap = pdf[i].render(scale=scale)
        images.append(bitmap.to_pil().convert("RGB"))

    images[0].save(
        dest,
        save_all=True,
        append_images=images[1:],
        resolution=DPI,
    )
    size_mb = os.path.getsize(dest) / 1e6
    print(f"Uretildi: {os.path.basename(dest)}")
    print(f"  kaynak     : {os.path.basename(src)}")
    print(f"  sayfa      : {n}")
    print(f"  cozunurluk : {DPI} DPI")
    print(f"  boyut      : {size_mb:.1f} MB")


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.exists(src):
        print(f"Kaynak bulunamadi: {src}")
        sys.exit(1)
    stem = os.path.splitext(os.path.basename(src))[0]
    dest = os.path.join(CORPUS, f"taranmis_{stem}.pdf")
    make_scanned(src, dest)

    # Uretilen dosyanin gercekten metinsiz oldugunu dogrula
    import pypdf
    reader = pypdf.PdfReader(dest)
    chars = sum(len(p.extract_text() or "") for p in reader.pages)
    print(f"  pypdf metin: {chars} karakter  (0 olmali -> metin katmani yok)")


if __name__ == "__main__":
    main()
