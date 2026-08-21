# -*- coding: utf-8 -*-
"""Mentore gonderilecek paketi hazirlar -> pdf-parser-karsilastirma.zip"""
import io
import zipfile
from pathlib import Path

KOK = Path(__file__).parent
HEDEF = KOK / "pdf-parser-karsilastirma.zip"
ICKLASOR = "pdf-parser-karsilastirma"

def ekle(z, kaynak: Path, hedef: str):
    z.write(kaynak, f"{ICKLASOR}/{hedef}")
    return kaynak.stat().st_size


def main():
    toplam = 0
    sayac = {}
    with zipfile.ZipFile(HEDEF, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for ad in ["olcumler.md", "sonuclar.csv", "compare.py"]:
            p = KOK / ad
            if p.exists():
                toplam += ekle(z, p, ad)
                sayac[ad] = 1

        n = 0
        for p in sorted((KOK / "corpus").glob("*.pdf")):
            toplam += ekle(z, p, f"corpus/{p.name}")
            n += 1
        sayac["corpus PDF"] = n

        for desen, etiket in [("*__pypdf_plain.md", "pypdf ciktisi"),
                              ("*__inspector.md", "inspector ciktisi"),
                              ("basliklar_*.txt", "baslik listesi")]:
            n = 0
            for p in sorted((KOK / "out").glob(desen)):
                toplam += ekle(z, p, f"out/{p.name}")
                n += 1
            sayac[etiket] = n

    print(f"olusturuldu: {HEDEF.name}")
    print(f"  sikistirilmamis: {toplam/1024/1024:.1f} MB")
    print(f"  zip boyutu:      {HEDEF.stat().st_size/1024/1024:.1f} MB\n")
    for k, v in sayac.items():
        print(f"  {k:20} {v}")


if __name__ == "__main__":
    main()
