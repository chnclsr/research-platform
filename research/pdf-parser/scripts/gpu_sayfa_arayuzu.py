"""9 belgelik korpusun 261 sayfasini GPU agir motor ciktisiyla sayfa sayfa gosterir.

NE SORUYA CEVAP VERIYOR
-----------------------
`hata_arayuzu.py` ayni sayfalari gosteriyor ama agir metni TEK bir kaynaktan
(bizim CPU kosumuz) aliyor. Bu arayuz UC agir kaynagi yan yana koyuyor:

    bizim CPU (PC_7820)  ·  GPU makinesi CPU  ·  GPU makinesi CUDA

Boylece iki ayri soru ayni sayfada cevaplanabiliyor:

  1. Cihaz farki var mi?     -> ayni makinenin CPU ve CUDA sutunlari
  2. Makine farki var mi?    -> bizim CPU sutunu ile digerleri

Olculen (261 sayfa): ayni makinede CPU vs CUDA **0 fark**; makineler arasi
**15 sayfa** farkli. Yani agir motorun metni cihazdan cihaza degil, makineden
makineye degisiyor. Bu arayuz o hukmun gozle dogrulanabilir hali.

NE OLCMEZ -- ve neden 0 yazilmadi
---------------------------------
Tablo/sekil hukmu (TP/FP/FN) burada YOK. `hata_arayuzu.py` onlari
`out/docling_annot/` ve `out/mineru/.../*_middle.json` referanslarindan
uretiyor; bu iki girdi hicbir makinede yok ve ureten betik depoda da yok.
Eksik dosyada kod hata VERMIYOR, referans sessizce bos kumeye dusuyor ve
hukumler "hatasiz ama anlamsiz" cikiyor -- projenin daha once yasadigi
"hic var olmayan sayi" tuzagi. O yuzden bu arayuz o sutunlari hic
gostermiyor; `hata_arayuzu.html` neyi gosterebiliyorsa orada duruyor.

Yol karari (HIZLI/AGIR/OCR) cihazdan BAGIMSIZ: kapi sinyalleri pdf-inspector
ve PyMuPDF'ten geliyor, ikisi de GPU kullanmiyor. Bu 380 belgede olculdu
(route karari degisen belge: 0). Bu yuzden karar sutunu tek, cihaza gore
tekrarlanmiyor.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\gpu_sayfa_arayuzu.py
    -> html/gpu_sayfa_arayuzu.html
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(os.environ.get("PDF_PARSER_OUT", os.path.join(BASE, "out")))
HTML = os.path.join(BASE, "html")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Agir metin kaynaklari. Sira ONEMLI: ilk sutun bizim tabanimiz, digerleri
#: onunla karsilastirilan koseler.
KAYNAKLAR = [
    ("bizim_cpu", "bizim CPU", "docling_json", "PC_7820 · Intel UHD 770 · CPU"),
    ("gpu_cpu", "GPU mak. CPU", "gpu_docling_json_cpu", "server-cezeri · Xeon W-2145 · CPU"),
    ("gpu_cuda", "GPU mak. CUDA", "gpu_docling_json_cuda", "server-cezeri · Quadro RTX 4000"),
]

#: Sayfa metni arayuze gomulurken kirpilir; `hata_arayuzu.py` ile ayni sinir.
#: Kirpilan yer metnin sonunda ACIKCA yazilir -- sessiz kirpma bir kez yanlis
#: olcume yol acti (kirpilmis metinler karsilastirilinca 15 fark 43 gorundu).
METIN_SINIR = 6000


def _kirp(metin: str) -> str:
    if len(metin) <= METIN_SINIR:
        return metin
    return metin[:METIN_SINIR] + "\n\n[... %d karakter daha, arayüzde kırpıldı]" % (
        len(metin) - METIN_SINIR)


def _sayfalar(kok: str, stem: str):
    yol = os.path.join(OUT, kok, stem + "_sayfalar.json")
    if not os.path.isfile(yol):
        return None
    with open(yol, encoding="utf-8") as f:
        return json.load(f).get("sayfalar") or []


def veri_hazirla() -> dict:
    yol = os.path.join(OUT, "hata_arayuzu_veri.json")
    if not os.path.isfile(yol):
        raise SystemExit("Once hata_arayuzu.py kosulmali: %s yok" % yol)
    with open(yol, encoding="utf-8") as f:
        belgeler = json.load(f)

    eksik, cikti = [], []
    sayac = {"sayfa": 0, "agir": 0, "ocr": 0, "karantina": 0,
             "cihaz_farki": 0, "makine_farki": 0}

    for b in belgeler:
        stem = b["belge"]
        metinler = {}
        for anahtar, _ad, kok, _kunye in KAYNAKLAR:
            s = _sayfalar(kok, stem)
            if s is None:
                eksik.append("%s/%s_sayfalar.json" % (kok, stem))
            metinler[anahtar] = s

        sayfalar = []
        for s in b["sayfalar"]:
            i = s["sayfa_no"] - 1
            agir = {}
            for anahtar, _ad, _kok, _k in KAYNAKLAR:
                kaynak = metinler.get(anahtar)
                agir[anahtar] = None if kaynak is None or i >= len(kaynak) else kaynak[i]

            # Iki ayri soru, iki ayri bayrak. Birlestirmek ikisini de gizlerdi.
            ayni_makine = agir.get("gpu_cpu"), agir.get("gpu_cuda")
            cihaz_farki = (None not in ayni_makine and ayni_makine[0] != ayni_makine[1])
            capraz = agir.get("bizim_cpu"), agir.get("gpu_cuda")
            makine_farki = (None not in capraz and capraz[0] != capraz[1])

            sayac["sayfa"] += 1
            if s.get("yol") == "AGIR":
                sayac["agir"] += 1
            if s.get("yol") == "OCR":
                sayac["ocr"] += 1
            if s.get("karantina"):
                sayac["karantina"] += 1
            if cihaz_farki:
                sayac["cihaz_farki"] += 1
            if makine_farki:
                sayac["makine_farki"] += 1

            sayfalar.append({
                "no": s["sayfa_no"],
                "gorsel": s.get("gorsel"),
                "yol": s.get("yol"),
                "motor": s.get("motor"),
                "secilen_motor": s.get("secilen_motor"),
                "gerekce": s.get("gerekce") or [],
                "kalite": s.get("kalite"),
                "cezalar": s.get("cezalar") or {},
                "kritik": s.get("kritik"),
                "sinyaller": s.get("sinyaller") or {},
                "karantina": bool(s.get("karantina")),
                "fallback": bool(s.get("fallback")),
                "fast_metin": s.get("fast_metin") or "",
                "secilen_metin": s.get("secilen_metin") or "",
                "agir": {k: (None if v is None else _kirp(v)) for k, v in agir.items()},
                "agir_uzunluk": {k: (None if v is None else len(v)) for k, v in agir.items()},
                "cihaz_farki": cihaz_farki,
                "makine_farki": makine_farki,
            })

        cikti.append({"belge": stem, "sayfa_sayisi": b["sayfa_sayisi"],
                      "agir_sayfa": b.get("agir_sayfa"), "sayfalar": sayfalar})

    return {"belgeler": cikti, "sayac": sayac, "eksik": sorted(set(eksik)),
            "kaynaklar": [{"anahtar": a, "ad": ad, "kunye": k} for a, ad, _kok, k in KAYNAKLAR]}


CSS = """
:root{--kagit:#fff;--murekkep:#16181d;--soluk:#6b7280;--cizgi:#e3e6ea;--vurgu:#1d4ed8;
--zemin:#f6f7f9;--yesil:#0f7b3d;--yesilzemin:#e7f6ed;--kirmizi:#b42318;--kirmizizemin:#fdecea;
--sari:#8a6100;--sarizemin:#fdf3e0;--mor:#5b21b6;--morzemin:#f3eeff;}
*{box-sizing:border-box}
body{margin:0;background:var(--zemin);color:var(--murekkep);
font:14px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.ust{background:var(--kagit);border-bottom:1px solid var(--cizgi);padding:14px 20px;
position:sticky;top:0;z-index:20}
h1{margin:0 0 4px;font-size:19px}
.altbaslik{color:var(--soluk);font-size:12.5px;margin:0}
nav.arayuz-gecis{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:12.5px}
nav.arayuz-gecis a{color:var(--vurgu);text-decoration:none;border:1px solid var(--cizgi);
border-radius:6px;padding:3px 9px;background:var(--zemin)}
nav.arayuz-gecis a.aktif{background:var(--murekkep);color:#fff;border-color:var(--murekkep)}
.kontrol{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:10px}
select,button{font:inherit;font-size:13px;padding:4px 9px;border:1px solid var(--cizgi);
border-radius:6px;background:var(--kagit);cursor:pointer}
button.etkin{background:var(--murekkep);color:#fff;border-color:var(--murekkep)}
.ozet{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;font-size:12.5px}
.ozet span{background:var(--zemin);border:1px solid var(--cizgi);border-radius:20px;padding:2px 10px}
.sar{padding:18px 20px 80px}
.sayfa{background:var(--kagit);border:1px solid var(--cizgi);border-radius:12px;
padding:14px 16px;margin-bottom:14px}
.basl{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.basl b{font-size:15px}
.rozet{font-size:11.5px;padding:2px 9px;border-radius:20px;white-space:nowrap}
.r-hizli{background:var(--yesilzemin);color:var(--yesil)}
.r-agir{background:var(--morzemin);color:var(--mor)}
.r-ocr{background:var(--sarizemin);color:var(--sari)}
.r-uyari{background:var(--kirmizizemin);color:var(--kirmizi)}
.r-notr{background:var(--zemin);color:var(--soluk);border:1px solid var(--cizgi)}
.govde{display:grid;grid-template-columns:260px 1fr;gap:16px}
@media(max-width:900px){.govde{grid-template-columns:1fr}}
.sol img{width:100%;border:1px solid var(--cizgi);border-radius:8px;display:block}
.kunye{margin-top:8px;font-size:12px;color:var(--soluk);
font-family:ui-monospace,Consolas,monospace;line-height:1.5}
.kunye div{overflow-wrap:anywhere}
.sutunlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.sut{border:1px solid var(--cizgi);border-radius:8px;overflow:hidden;min-width:0}
.sut h4{margin:0;padding:6px 10px;font-size:12px;background:var(--zemin);
border-bottom:1px solid var(--cizgi);display:flex;justify-content:space-between;gap:8px}
.sut h4 em{font-style:normal;color:var(--soluk);font-weight:400}
.sut.fark h4{background:var(--kirmizizemin);color:var(--kirmizi)}
.sut pre{margin:0;padding:9px 10px;font-size:11.5px;line-height:1.45;
white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;
font-family:ui-monospace,Consolas,monospace}
.sut .yok{padding:12px 10px;color:var(--soluk);font-size:12px}
.not{background:var(--kagit);border:1px solid var(--cizgi);border-left:3px solid var(--vurgu);
border-radius:8px;padding:12px 16px;margin:0 20px 16px;font-size:13px}
.bos{padding:40px;text-align:center;color:var(--soluk)}
"""

JS = """
const K = D.kaynaklar;
let belge = D.belgeler[0].belge, suz = "hepsi";

function kacis(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function rozetler(p){
  const r=[];
  const yolSinif = p.yol==='AGIR'?'r-agir':(p.yol==='OCR'?'r-ocr':'r-hizli');
  r.push(`<span class="rozet ${yolSinif}">${p.yol}</span>`);
  r.push(`<span class="rozet r-notr">seçilen: ${kacis(p.secilen_motor||'-')}</span>`);
  if(p.kalite!==null&&p.kalite!==undefined)
    r.push(`<span class="rozet r-notr">kalite ${p.kalite}</span>`);
  if(p.kritik&&p.kritik!=='NONE') r.push(`<span class="rozet r-uyari">${kacis(p.kritik)}</span>`);
  if(p.karantina) r.push('<span class="rozet r-uyari">karantina</span>');
  if(p.fallback) r.push('<span class="rozet r-uyari">fallback</span>');
  if(p.cihaz_farki) r.push('<span class="rozet r-uyari">CİHAZ FARKI</span>');
  if(p.makine_farki) r.push('<span class="rozet r-uyari">makineler arası fark</span>');
  return r.join('');
}

function sutun(baslik, kunye, metin, uzunluk, fark){
  if(metin===null||metin===undefined)
    return `<div class="sut"><h4>${kacis(baslik)}</h4><div class="yok">ölçülmedi — kaynak dosya yok</div></div>`;
  const n = uzunluk===null||uzunluk===undefined ? '' : `<em>${uzunluk} krk</em>`;
  return `<div class="sut${fark?' fark':''}"><h4><span title="${kacis(kunye||'')}">${kacis(baslik)}</span>${n}</h4>`
       + `<pre>${kacis(metin)}</pre></div>`;
}

function ciz(){
  const b = D.belgeler.find(x=>x.belge===belge);
  let sayfalar = b.sayfalar;
  if(suz==='agir') sayfalar = sayfalar.filter(p=>p.yol==='AGIR');
  else if(suz==='ocr') sayfalar = sayfalar.filter(p=>p.yol==='OCR');
  else if(suz==='karantina') sayfalar = sayfalar.filter(p=>p.karantina||p.fallback);
  else if(suz==='fark') sayfalar = sayfalar.filter(p=>p.makine_farki||p.cihaz_farki);

  const hedef = document.getElementById('liste');
  if(!sayfalar.length){ hedef.innerHTML='<div class="bos">Bu süzgeçte sayfa yok.</div>'; return; }

  hedef.innerHTML = sayfalar.map(p=>{
    const sin = p.sinyaller||{};
    const kunye = [
      `motor: ${p.motor||'-'}`,
      `gerekçe: ${(p.gerekce||[]).join(', ')||'—'}`,
      `tablo(insp/v2): ${sin.tablo_inspector?'✓':'·'}/${sin.tablo_v2?'✓':'·'}`,
      `şekil(küme/raster): ${sin.sekil_kume?'✓':'·'}/${sin.sekil_raster?'✓':'·'}`,
      `karakter: ${sin.karakter??'-'}`,
      `ortogonal çizgi: ${sin.ortogonal_cizgi??'-'}`,
      `dolu dikdörtgen: ${sin.dolu_dikdortgen??'-'}`,
      `bezier: ${sin.bezier_egri??'-'}`,
      `eşik: ${sin.esik_version||'-'}`,
    ].map(x=>`<div>${kacis(x)}</div>`).join('');

    const gorsel = p.gorsel ? `<img loading="lazy" src="${kacis(p.gorsel)}" alt="sayfa ${p.no}">` : '';
    const agirSut = K.map(k=>sutun(
        'ağır · '+k.ad, k.kunye, p.agir[k.anahtar], p.agir_uzunluk[k.anahtar],
        // Kirmizi baslik: bu sutun bizim tabanimizdan ayrilan sutun.
        k.anahtar!=='bizim_cpu' && p.makine_farki)).join('');

    return `<div class="sayfa"><div class="basl"><b>s.${p.no}</b>${rozetler(p)}</div>
      <div class="govde">
        <div class="sol">${gorsel}<div class="kunye">${kunye}</div></div>
        <div class="sutunlar">
          ${sutun('hızlı · pdf-inspector','fast yol, GPU kullanmaz',p.fast_metin,p.fast_metin.length,false)}
          ${agirSut}
          ${sutun('seçilen (merge)','üretimdeki birlestir() çıktısı',p.secilen_metin,p.secilen_metin.length,false)}
        </div>
      </div></div>`;
  }).join('');
}

document.getElementById('belge').addEventListener('change',e=>{belge=e.target.value;ciz()});
document.querySelectorAll('[data-suz]').forEach(btn=>btn.addEventListener('click',e=>{
  document.querySelectorAll('[data-suz]').forEach(x=>x.classList.remove('etkin'));
  e.target.classList.add('etkin'); suz=e.target.dataset.suz; ciz();
}));
ciz();
"""


def main() -> int:
    p = argparse.ArgumentParser(description="GPU sayfa sayfa arayuzu")
    p.add_argument("--cikti", default=os.path.join(HTML, "gpu_sayfa_arayuzu.html"))
    args = p.parse_args()

    veri = veri_hazirla()
    s = veri["sayac"]

    secenek = "".join('<option value="%s">%s (%d sayfa)</option>'
                      % (b["belge"], b["belge"], b["sayfa_sayisi"]) for b in veri["belgeler"])
    suzgecler = "".join('<button data-suz="%s"%s>%s</button>' % (a, ' class="etkin"' if a == "hepsi" else "", ad)
                        for a, ad in [("hepsi", "hepsi"), ("agir", "yalnız ağır"), ("ocr", "yalnız OCR"),
                                      ("karantina", "karantina / fallback"),
                                      ("fark", "makineler arası farklı")])
    ozet = "".join("<span>%s</span>" % x for x in [
        "%d sayfa · 9 belge" % s["sayfa"],
        "ağır %d" % s["agir"], "OCR %d" % s["ocr"], "karantina %d" % s["karantina"],
        "aynı makinede cihaz farkı <b>%d</b>" % s["cihaz_farki"],
        "makineler arası fark <b>%d</b>" % s["makine_farki"],
    ])

    eksik_not = ""
    if veri["eksik"]:
        eksik_not = ('<div class="not"><b>Eksik kaynak:</b> %s — o sütun "ölçülmedi" '
                     'diyor, boş değil.</div>' % _html.escape(", ".join(veri["eksik"])))

    sayfa = (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GPU sayfa sayfa — smart_router</title><style>%s</style></head><body>'
        '<div class="ust"><h1>GPU koşusu — sayfa sayfa yol kararı ve ayrıştırılmış metin</h1>'
        '<p class="altbaslik">9 belge · 261 sayfa · üç ağır motor çıktısı yan yana. '
        'Yol kararı cihazdan bağımsızdır (kapı sinyalleri GPU kullanmaz, 380 belgede ölçüldü).</p>'
        '<nav class="arayuz-gecis"><a href="index.html">Arayüzler</a>'
        '<a href="gpu_panosu.html">GPU panosu</a>'
        '<a href="gpu_sayfa_arayuzu.html" class="aktif">GPU sayfa sayfa</a>'
        '<a href="c1_arayuz_gpu380.html">C1 380 belge</a>'
        '<a href="hata_arayuzu.html">Kendi korpus (CPU)</a></nav>'
        '<div class="kontrol"><select id="belge">%s</select>%s</div>'
        '<div class="ozet">%s</div></div>'
        '%s<div class="sar" id="liste"></div>'
        '<script>const D=%s;\n%s</script></body></html>'
        % (CSS, secenek, suzgecler, ozet, eksik_not,
           json.dumps(veri, ensure_ascii=False), JS))

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8") as f:
        f.write(sayfa)
    print("-> %s (%.1f MB)" % (args.cikti, os.path.getsize(args.cikti) / 1024 / 1024))
    print("   sayfa=%d · ağır=%d · OCR=%d · karantina=%d" % (
        s["sayfa"], s["agir"], s["ocr"], s["karantina"]))
    print("   aynı makinede cihaz farkı=%d · makineler arası fark=%d" % (
        s["cihaz_farki"], s["makine_farki"]))
    if veri["eksik"]:
        print("   eksik kaynak: %s" % ", ".join(veri["eksik"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
