"""Mekanik olarak tespit edilebilen kusur adaylarini sayfa numarasi ve baglamiyla listeler.

Cikti: dogrulama_<dosya>.md  --  her satirda bir aday, basinda [ ] kutusu.
Kullanici [x] isaretler, sonra say.py sayar.

Kullanim: .\.venv\Scripts\python.exe aday_uret.py bert
"""
import io
import random
import re
import sys
from pathlib import Path

import pdf_inspector
import pypdf

random.seed(42)
ORNEK_LIMIT = 30  # bu sayidan fazla aday varsa orneklem alinir


def pypdf_pages(path):
    return [(p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages]


def inspector_pages(path):
    res = pdf_inspector.extract_pages_markdown(str(path))
    d = {p.page: (p.markdown or "") for p in res.pages}
    if not d:
        return []
    start = 0 if 0 in d else 1
    return [d.get(n, "") for n in range(start, max(d) + 1)]


KATEGORILER = [
    (
        "caprazref",
        "Çapraz referans boşluğu",
        r"\b(?:Figure|Table|Section|Eq|Appendix|Fig)\d{1,2}\b",
        "'Figure 1' gibi bir referansta boşluk kaybolmuş mu? "
        "Kaybolmuşsa HATA. Gerçekten bitişik yazılmış bir ad ise değil.",
    ),
    (
        "dipnot",
        "Dipnot işareti / alt simge yapışması",
        # Capraz referans kelimeleri haric tutulur; onlar ayri kategoride sayilir
        r"\b(?!Figure|Table|Section|Appendix|Fig\b)[a-zA-Z]{4,}\d{1,2}\b",
        "Sondaki rakam bir dipnot işareti veya alt simge mi (HATA), "
        "yoksa adın parçası mı (örn. CVPR09, GPT2 → hata değil)?",
    ),
    (
        "tireleme",
        "Birleşmemiş tireleme",
        r"\w{2,}-\s+\w{2,}",
        "Satır sonu tiresi birleştirilmemiş mi (örn. 'evalu- ation' → HATA)? "
        "Gerçek birleşik yazım ise (örn. 'pre- and post-') hata değil.",
    ),
]


def adaylar(sayfalar, desen):
    out = []
    for no, metin in enumerate(sayfalar, start=1):
        for m in re.finditer(desen, metin):
            bag = metin[max(0, m.start() - 45): m.end() + 45]
            bag = " ".join(bag.split())
            esles = " ".join(m.group(0).split())  # satir sonlarini tek satira indir
            out.append((no, esles, bag))
    return out


def blok(baslik, aciklama, kayitlar, parser_adi):
    toplam = len(kayitlar)
    if toplam > ORNEK_LIMIT:
        secili = sorted(random.sample(kayitlar, ORNEK_LIMIT))
        not_ = (
            f"**{toplam} aday bulundu, rastgele {ORNEK_LIMIT} tanesi örneklendi "
            f"(seed=42).** İşaretlediğin oran toplama uygulanacak."
        )
    else:
        secili = sorted(kayitlar)
        not_ = f"**{toplam} aday — hepsi listelendi.**"

    satirlar = [f"### {parser_adi} — {baslik}", "", not_, "", f"> {aciklama}", ""]
    if not secili:
        satirlar += ["*(aday yok)*", ""]
        return satirlar
    for no, esles, bag in secili:
        satirlar.append(f"- [ ] `s.{no}` **{esles}** — ...{bag}...")
    satirlar.append("")
    return satirlar


def main():
    hedef = sys.argv[1].lower() if len(sys.argv) > 1 else "bert"
    yollar = [p for p in sorted(Path("corpus").glob("*.pdf")) if hedef in p.stem.lower()]
    yollar = [p for p in yollar if "taranmis" not in p.stem]
    if not yollar:
        print("PDF bulunamadi")
        return
    path = yollar[0]
    isim = path.stem

    kaynaklar = [
        ("pypdf", pypdf_pages(path)),
        ("inspector", inspector_pages(path)),
    ]

    parts = [
        f"# {isim} — kusur adayı doğrulama listesi",
        "",
        "Her satır **mekanik olarak bulunmuş bir aday**. Gerçekten hata olup olmadığına",
        "sen karar vereceksin.",
        "",
        "## Nasıl doldurulur",
        "",
        "- Hata ise `- [ ]` yerine `- [x]` yaz (VS Code'da kutuya tıklamak yeter)",
        "- Hata değilse boş bırak",
        "- Emin değilsen satır sonuna ` ?` ekle",
        "- Bitince: `.\\.venv\\Scripts\\python.exe say.py` çalıştır, sayılar dökülür",
        "",
        "`s.N` = kaçıncı sayfada bulunduğu. Şüphelendiğinde o sayfayı PDF'te aç.",
        "",
        "---",
        "",
        "## Otomatik sayılanlar (tiklemene gerek yok)",
        "",
    ]

    # ligatur: mekanik olarak kesin
    for ad, sayfalar in kaynaklar:
        n = sum(len(re.findall(r"[ﬀ-ﬄ]", s)) for s in sayfalar)
        parts.append(f"- **Ligatür ({ad}):** {n} adet — `ﬁ ﬂ ﬀ` karakterleri. "
                     f"Tespit kesin, karar gerektirmez.")
    parts += [
        "",
        "**Gözle sayman gerekenler (mekanik tespit güvenilir değil):**",
        "bölünmüş kelime · okuma sırası bozukluğu · dipnot sızması · "
        "sayfa mobilyası sızması · kayıp içerik · tablo çözülmesi",
        "",
        "---",
        "",
    ]

    for anahtar, baslik, desen, aciklama in KATEGORILER:
        parts.append(f"## {baslik}")
        parts.append("")
        for ad, sayfalar in kaynaklar:
            parts += blok(baslik, aciklama, adaylar(sayfalar, desen), ad)
        parts.append("---")
        parts.append("")

    hedef_dosya = Path(f"dogrulama_{isim}.md")
    io.open(hedef_dosya, "w", encoding="utf-8").write("\n".join(parts))
    print(f"olusturuldu: {hedef_dosya}")
    for anahtar, baslik, desen, _ in KATEGORILER:
        for ad, sayfalar in kaynaklar:
            print(f"  {baslik:32} {ad:10} {len(adaylar(sayfalar, desen)):5} aday")


if __name__ == "__main__":
    main()
