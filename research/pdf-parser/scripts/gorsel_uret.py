"""Rapora eklenecek orijinal PDF sayfa goruntulerini uretir -> gorseller/ klasoru."""
import pymupdf
from pathlib import Path

CIKTI = Path("gorseller")
CIKTI.mkdir(exist_ok=True)
DPI = 170


def render(pdf, sayfa, ad, kirp=None, dpi=DPI):
    d = pymupdf.open(pdf)
    p = d[sayfa - 1]
    zoom = dpi / 72
    m = pymupdf.Matrix(zoom, zoom)
    pix = p.get_pixmap(matrix=m, clip=pymupdf.Rect(*kirp) if kirp else None)
    yol = CIKTI / f"{ad}.png"
    pix.save(str(yol))
    d.close()
    print(f"  {yol}  {pix.width}x{pix.height} px")
    return yol


print("goruntuler uretiliyor...")

# 1) Sybil TABLE 1 -- yatay sayfa, tablonun tamami
render("corpus/sybil_tip_2sutun.pdf", 5, "01_sybil_tablo1",
       kirp=(66, 234, 752, 352), dpi=300)

# 2) Turkce makale s.4 -- iki sutunun gorsel olarak apacik ayrik oldugunu gosterir
render("corpus/turkce_makale.pdf", 4, "02_turkce_s4_sutunlar")

# 2b) Ayni sayfanin alt kismi -- karisan govde metni, okunabilir olcekte
render("corpus/turkce_makale.pdf", 4, "02b_turkce_s4_govde",
       kirp=(38, 648, 578, 768), dpi=300)

# 3) Sybil s.4 -- kunyenin boldugu cumlenin orijinalde kesintisiz aktigi yer (sag sutun)
render("corpus/sybil_tip_2sutun.pdf", 4, "03_sybil_cumle",
       kirp=(48, 474, 545, 548), dpi=300)

# 4) VGG s.3 -- 2.1 ARCHITECTURE basliginin gercekten baslik oldugu yer
d = pymupdf.open("corpus/vgg_tablo_agirlikli.pdf")
for n in range(len(d)):
    r = d[n].search_for("2.1 A")
    if r:
        ust = min(q.y0 for q in r)
        print(f"  vgg '2.1 ARCHITECTURE' sayfa {n+1}, y={ust:.0f}")
        d.close()
        render("corpus/vgg_tablo_agirlikli.pdf", n + 1, "04_vgg_baslik",
               kirp=(60, max(0, ust - 10), 545, ust + 78), dpi=300)
        break
else:
    d.close()

print("bitti")
