"""Kurulum dogrulama: iki kutuphane de calisiyor mu, API yuzeyi ne?"""
import sys, io, glob, os

import pdf_inspector
import pypdf

print("pdf_inspector:", getattr(pdf_inspector, "__version__", "?"))
print("pypdf        :", pypdf.__version__)
print()
print("pdf_inspector public API:")
print([n for n in dir(pdf_inspector) if not n.startswith("_")])
print()

pdfs = glob.glob(os.path.join(
    os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj"), "*.pdf"))
if not pdfs:
    print("PDF bulunamadi.")
    sys.exit(0)

path = pdfs[0]
print("Test dosyasi:", path.rsplit("\\", 1)[-1])
print()

res = pdf_inspector.process_pdf(path)
print("result type   :", type(res))
print("result attrs  :", [n for n in dir(res) if not n.startswith("_")])
print()
print("pdf_type      :", res.pdf_type)
print("confidence    :", res.confidence)
print("page_count    :", res.page_count)
md = res.markdown or ""
print("markdown chars:", len(md))
print("markdown basliklari (ilk 15):")
for line in md.splitlines():
    if line.startswith("#"):
        print("   ", line[:90])

reader = pypdf.PdfReader(path)
text = "\n\n".join(
    f"# Page {i}\n\n{p.extract_text() or ''}"
    for i, p in enumerate(reader.pages, start=1)
)
print()
print("pypdf chars   :", len(text))
