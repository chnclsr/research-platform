"""Test PDF setini indirir. Her dosya bilincli olarak bir 'zorluk sinifini' temsil eder.

Calistir:  .venv\\Scripts\\python.exe fetch_corpus.py
"""
import os
import urllib.request

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
CORPUS_DIR = os.path.join(
    os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj"),
    'corpus')

# (dosya_adi, url, neden_bu_dosya)
FILES = [
    ("bert_2sutun_dipnot.pdf",
     "https://arxiv.org/pdf/1810.04805",
     "ACL formati: iki sutun + yogun dipnot. Asil sikayet konusu."),

    ("resnet_2sutun_gorsel.pdf",
     "https://arxiv.org/pdf/1512.03385",
     "CVPR formati: iki sutun + cok sayida figur/grafik."),

    ("attention_tablo.pdf",
     "https://arxiv.org/pdf/1706.03762",
     "Tek sutun ama tablo agirlikli, mimari diyagramli."),

    ("gpt3_uzun_75sayfa.pdf",
     "https://arxiv.org/pdf/2005.14165",
     "75+ sayfa: hiz ve bellek testi."),

    ("gpt4_uzun_gorsel.pdf",
     "https://arxiv.org/pdf/2303.08774",
     "100 sayfa civari, resim/tablo agirlikli, karisik duzen."),

    ("vgg_tablo_agirlikli.pdf",
     "https://arxiv.org/pdf/1409.1556",
     "ICLR formati: tek sutun, cok tablolu."),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (staj-pdf-karsilastirma; sude)"}


def main() -> None:
    os.makedirs(CORPUS_DIR, exist_ok=True)
    for name, url, why in FILES:
        dest = os.path.join(CORPUS_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 10_000:
            print(f"[atlandi] {name} ({os.path.getsize(dest)/1e6:.1f} MB)")
            continue
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            if not data.startswith(b"%PDF"):
                print(f"[HATA]    {name}: PDF degil (ilk baytlar: {data[:20]!r})")
                continue
            with open(dest, "wb") as f:
                f.write(data)
            print(f"[indi]    {name:32s} {len(data)/1e6:6.1f} MB  <- {why}")
        except Exception as exc:
            print(f"[HATA]    {name}: {exc}")


if __name__ == "__main__":
    main()
