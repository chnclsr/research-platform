"""Iki parser ciktisini sayfa sayfa hizalayip tek dosyada yan yana koyar.

Kullanim:  .\.venv\Scripts\python.exe hizala.py            (tum corpus)
           .\.venv\Scripts\python.exe hizala.py sybil      (tek dosya, isim parcasi yeter)

Cikti: out/karsilastirma_<dosya>.md
"""
import io
import re
import sys
from pathlib import Path

import pdf_inspector
import pypdf

CORPUS = Path("corpus")
OUT = Path("out")


def pypdf_pages(path: Path) -> list[str]:
    reader = pypdf.PdfReader(str(path))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def inspector_pages(path: Path) -> list[str]:
    result = pdf_inspector.extract_pages_markdown(str(path))
    pages = {}
    for page in result.pages:
        pages[page.page] = (page.markdown or "").strip()
    if not pages:
        return []
    top = max(pages)
    # sayfa numaralari 1-indexli gelebilir de 0-indexli de; ikisini de tolere et
    start = 0 if 0 in pages else 1
    return [pages.get(n, "") for n in range(start, top + 1)]


def build(path: Path) -> Path:
    name = path.stem
    left = pypdf_pages(path)
    right = inspector_pages(path)
    total = max(len(left), len(right))

    parts: list[str] = [
        f"# {name} — sayfa sayfa karşılaştırma",
        "",
        f"Toplam sayfa: **{total}**  ·  Sol = `pypdf` (sistemde kullanılan)  ·  "
        f"Sağ = `pdf-inspector` (aday)",
        "",
        "Referans orijinal PDF'tir: `corpus/" + path.name + "`",
        "",
        "> Not: pdf-inspector çıktısı Markdown'dır; kalın/italik/bağlantı biçimlendirmesi",
        "> hata sayılmaz. Tablolar `|` ile gösterilir.",
        "",
    ]

    for index in range(total):
        page_no = index + 1
        a = left[index] if index < len(left) else ""
        b = right[index] if index < len(right) else ""
        parts += [
            "",
            "---",
            "",
            f"# ═══════════  SAYFA {page_no} / {total}  ═══════════",
            "",
            f"## ▸ pypdf — sayfa {page_no}",
            "",
            "```text",
            a if a else "(bu sayfada metin cikmadi)",
            "```",
            "",
            f"## ▸ pdf-inspector — sayfa {page_no}",
            "",
            "```text",
            b if b else "(bu sayfada metin cikmadi)",
            "```",
        ]

    target = OUT / f"karsilastirma_{name}.md"
    io.open(target, "w", encoding="utf-8").write("\n".join(parts))
    return target


def main() -> None:
    OUT.mkdir(exist_ok=True)
    wanted = sys.argv[1].lower() if len(sys.argv) > 1 else None
    files = sorted(CORPUS.glob("*.pdf"))
    if wanted:
        files = [f for f in files if wanted in f.stem.lower()]
    if not files:
        print("Eslesen PDF bulunamadi.")
        return
    for path in files:
        try:
            target = build(path)
            size = target.stat().st_size / 1024
            print(f"  {target}  ({size:.0f} KB)")
        except Exception as exc:
            print(f"  {path.name}: HATA {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
