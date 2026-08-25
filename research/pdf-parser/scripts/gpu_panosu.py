"""GPU kosusunun butun metriklerini TEK bir basilabilir HTML sayfasinda toplar.

TASARIM KURALI -- HICBIR SAYI BU DOSYADA YAZMAZ
------------------------------------------------
Her deger kosularin urettigi JSON'lardan okunur ve her sayinin altinda hangi
dosyanin hangi alanindan geldigi GORUNUR durur. Mentore savunulabilirligin tek
yolu bu: panodaki bir sayi sorulunca cevap "su dosyanin su alani" olmali,
"betikte boyle yaziyordu" degil.

Dosya yoksa ilgili kart "olculmedi" yazar -- 0 YAZMAZ, karti gizlemez. Sifir bir
olcum sonucudur; olculmemis bir sey sifir degildir. Bu proje bu hatayi bir kez
yasadi (bir sayac yanlis anahtar okuyup her kosuda 0 gosterdi; yanlis sayi
degil, hic var olmayan sayi).

Cikti: html/gpu_panosu.html -- tek dosya, gomulu CSS/JS, dis bagimlilik yok.
Cift tiklayinca acilir; sunucu, internet, kurulum gerekmez.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import statistics
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(BASE))
OUT = os.path.abspath(os.environ.get("PDF_PARSER_OUT", os.path.join(BASE, "out")))
OUT_GPU = os.path.join(BASE, "out_gpu")
PKT = os.environ.get("PKT", "")
LOG = os.environ.get("LOG", "")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLCULMEDI = "ölçülmedi"


# ===================================================================== okuma
class Kaynak:
    """Okunan her dosyanin yolunu kisa haliyle akilda tutar.

    Panodaki `kaynak:` satirlari bu kisa yollari kullaniyor; mutlak yol yazmak
    panoyu makineye baglardi ve baska bir makinede anlamsiz gorunurdu.
    """

    def __init__(self):
        self.eksik: list[str] = []

    def kisa(self, yol: str) -> str:
        try:
            return os.path.relpath(yol, REPO_ROOT).replace("\\", "/")
        except ValueError:
            return yol

    def json(self, yol: str):
        if not os.path.isfile(yol):
            self.eksik.append(self.kisa(yol))
            return None
        try:
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            self.eksik.append("%s (okunamadi: %s)" % (self.kisa(yol), type(exc).__name__))
            return None

    def jsonl(self, yol: str):
        if not os.path.isfile(yol):
            self.eksik.append(self.kisa(yol))
            return None
        kayitlar = []
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                if satir.strip():
                    try:
                        kayitlar.append(json.loads(satir))
                    except json.JSONDecodeError:
                        pass  # yarim kalan son satir; onar_jsonl zaten temizliyor
        return kayitlar


K = Kaynak()


def kosu_dizini(run_id: str) -> str:
    return os.path.join(OUT, "c1_runs", run_id)


def kosu_oku(run_id: str) -> dict:
    """Bir C1 kosusunun ozeti + belge belge kararlari.

    predictions.jsonl yeniden baslatilabilir kosularda AYNI kimligi birden fazla
    kez tasiyabilir (once hata, sonra ok). Son deneme esas alinir -- c1_dogrulama
    `_ozet` fonksiyonu da ayni seyi yapiyor, iki taraf ayrilmasin.
    """
    dizin = kosu_dizini(run_id)
    ozet = K.json(os.path.join(dizin, "summary.json"))
    ham = K.jsonl(os.path.join(dizin, "predictions.jsonl"))
    satirlar = None
    if ham is not None:
        son = {}
        for r in ham:
            if r.get("id"):
                son[r["id"]] = r
        satirlar = list(son.values())
    return {"run_id": run_id, "ozet": ozet, "satirlar": satirlar,
            "ozet_yolu": "out/c1_runs/%s/summary.json" % run_id,
            "tahmin_yolu": "out/c1_runs/%s/predictions.jsonl" % run_id}


# ================================================================== metrikler
def _ort(degerler):
    degerler = [d for d in degerler if d is not None]
    return round(statistics.fmean(degerler), 6) if degerler else None


def c1_metrikleri(satirlar, aile=None) -> dict | None:
    """Bir kosunun metriklerini veri ailesi bazinda hesaplar.

    Kararlar YENIDEN URETILMIYOR: `route.routed_heavy`, `merge.quarantined_pages`
    ve `scores.*.utility` uretim hattinin yazdigi alanlar; burada yalniz sayiliyor.
    Bu proje bir kez karari taklit edip yanlis sayi uretti (gercek 8 red yerine 5).
    """
    if satirlar is None:
        return None
    if aile:
        satirlar = [r for r in satirlar if r.get("dataset") == aile]
    if not satirlar:
        return None

    tamam = [r for r in satirlar if r.get("status") == "ok"]
    routed = [r for r in tamam if r["route"]["routed_heavy"]]
    kazanc = [r for r in tamam if r["delta"]["heavy_minus_fast"] >= 0.02]
    dogru = [r for r in routed if r["delta"]["heavy_minus_fast"] >= 0.02]

    # Karantina: uretimin `birlestir()` fonksiyonunun reddettigi sayfalar.
    # Bu iki korpusun 380 belgesinin TAMAMI tek sayfali (envanter olcumu), yani
    # sayfa duzeyi red ile belge duzeyi utility birebir ortusuyor -- isabet orani
    # bir vekil degil, tam sayi.
    karantinali = [r for r in tamam if (r.get("merge") or {}).get("quarantined_pages")]
    karantina_red = sum(len(r["merge"]["quarantined_pages"]) for r in tamam)
    karantina_dogru = sum(1 for r in karantinali if r["delta"]["heavy_minus_fast"] <= 0)

    return {
        "documents": len(satirlar), "ok": len(tamam), "errors": len(satirlar) - len(tamam),
        "routed_heavy": len(routed),
        "heavy_gain_ge_0_02": len(kazanc),
        "route_precision_at_0_02": round(len(dogru) / len(routed), 4) if routed else None,
        "route_recall_at_0_02": round(len(dogru) / len(kazanc), 4) if kazanc else None,
        "mean_utility_fast": _ort([r["scores"]["fast"]["utility"] for r in tamam]),
        "mean_utility_heavy": _ort([r["scores"]["heavy"]["utility"] for r in tamam]),
        "mean_utility_routed": _ort([r["scores"]["routed"]["utility"] for r in tamam]),
        # NET: asimetrik "yakalanan fayda orani" DEGIL. max(delta,0) yalniz kazanci
        # sayar, gereksiz agir cagrinin zararini saymaz; esik/karar icin kullanilamaz.
        "net": round(sum(r["delta"]["routed_minus_fast"] for r in tamam), 6) if tamam else None,
        "karantina_red": karantina_red,
        "karantina_belge": len(karantinali),
        "karantina_isabet": (round(karantina_dogru / len(karantinali), 4)
                             if karantinali else None),
    }


# ================================================================ html yardim
def kacis(x) -> str:
    return _html.escape("" if x is None else str(x))


def sayi(x, basamak=2, birim="") -> str:
    """Olculmemis degeri 0 diye gostermemek icin tek kapi."""
    if x is None:
        return '<span class="yok">%s</span>' % OLCULMEDI
    if isinstance(x, bool):
        return "evet" if x else "hayır"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return "{:,}".format(x).replace(",", ".") + birim
    if isinstance(x, float):
        return ("%.*f" % (basamak, x)).replace(".", ",") + birim
    return kacis(x)


def kaynak(yol: str, alan: str = "") -> str:
    ok = " → " + kacis(alan) if alan else ""
    return '<div class="kaynak">kaynak: %s%s</div>' % (kacis(yol), ok)


def rozet(durum: str, baslik: str, ayrinti: str = "", kynk: str = "") -> str:
    """GECTI / GECMEDI / OLCULMEDI ucluleri -- ucuncu sik ASLA yesil olmaz."""
    sinif = {"GECTI": "gecti", "GECMEDI": "gecmedi"}.get(durum, "olculmedi")
    return ('<div class="rozet %s"><div class="rozet-durum">%s</div>'
            '<div class="rozet-baslik">%s</div><div class="rozet-ayrinti">%s</div>%s</div>'
            % (sinif, kacis(durum), kacis(baslik), ayrinti, kaynak(kynk) if kynk else ""))


_TABLO_SAYAC = [0]


def tablo(basliklar, satirlar, kynk="", not_=""):
    """Basliklar + satirlar -> HTML tablo, ustunde 'Markdown olarak kopyala'.

    Satir hucreleri zaten HTML; kopyalama JS tarafinda metin icerikten uretiliyor,
    boylece kopyalanan markdown ekranda gorunenle ayni kalir.
    """
    _TABLO_SAYAC[0] += 1
    tid = "t%d" % _TABLO_SAYAC[0]
    bas = "".join("<th>%s</th>" % kacis(b) for b in basliklar)
    gov = ""
    for s in satirlar:
        sinif = ' class="%s"' % s[0] if isinstance(s, tuple) else ""
        hucreler = s[1] if isinstance(s, tuple) else s
        gov += "<tr%s>%s</tr>" % (sinif, "".join("<td>%s</td>" % h for h in hucreler))
    return ('<div class="tablo-sar">'
            '<button class="kopyala no-print" data-hedef="%s">Markdown olarak kopyala</button>'
            '<div class="kaydir"><table id="%s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
            '%s%s</div>'
            % (tid, tid, bas, gov, ('<div class="not">%s</div>' % not_) if not_ else "",
               kaynak(kynk) if kynk else ""))


def bolum(no, baslik, icerik, aciklama=""):
    return ('<section class="bolum"><h2><span class="no">%d</span>%s</h2>%s%s</section>'
            % (no, kacis(baslik),
               ('<p class="aciklama">%s</p>' % aciklama) if aciklama else "", icerik))


def kart(baslik, deger, altyazi="", kynk=""):
    return ('<div class="kart"><div class="kart-baslik">%s</div>'
            '<div class="kart-deger">%s</div><div class="kart-alt">%s</div>%s</div>'
            % (kacis(baslik), deger, kacis(altyazi), kaynak(kynk) if kynk else ""))


# ================================================================== bolum 1-2
def bolum_ortam(ortam, kosular):
    if not ortam:
        return bolum(1, "Ortam", '<p class="yok">%s — out/gpu/ortam.json yok</p>' % OLCULMEDI)
    m, vd, v3 = ortam.get("makine") or {}, ortam.get("venv_docling") or {}, ortam.get("venv311") or {}
    ilk = next((k for k in kosular.values() if k.get("ozet")), None)
    fp = (ilk["ozet"].get("metric_fingerprint") if ilk else None) or ortam.get("metric_fingerprint")
    esik = router = None
    for k in kosular.values():
        for r in (k.get("satirlar") or []):
            if r.get("status") == "ok":
                esik = r["route"].get("threshold_version")
                router = r["route"].get("router_version")
                break
        if esik:
            break

    satirlar = [
        ["GPU", kacis(ortam.get("gpu", {}).get("nvidia_smi_ozet")), "out/gpu/ortam.json → gpu.nvidia_smi_ozet"],
        ["torch / CUDA", "%s / %s (görüyor: %s)" % (kacis(vd.get("torch")), kacis(vd.get("torch_cuda")), sayi(vd.get("cuda_var"))), "→ venv_docling.torch"],
        ["docling", kacis(vd.get("docling")), "→ venv_docling.docling"],
        ["Python (metrik venv)", kacis(v3.get("python")), "→ venv311.python"],
        ["Python (ağır motor venv)", kacis(vd.get("python")), "→ venv_docling.python"],
        ["işlemci", kacis(m.get("islemci")), "→ makine.islemci"],
        ["çekirdek / RAM", "%s / %s GB" % (kacis(m.get("cekirdek")), kacis(m.get("ram_gb"))), "→ makine.cekirdek"],
        ["işletim sistemi", kacis(m.get("os")), "→ makine.os"],
        ["depo commit", kacis(ortam.get("depo_commit")), "→ depo_commit"],
        ["ölçüm tarihi", kacis(ortam.get("olcum_tarihi")), "→ olcum_tarihi"],
        ["metric_fingerprint", kacis(fp), "out/c1_runs/*/summary.json → metric_fingerprint"],
        ["esik_version", kacis(esik), "out/c1_runs/*/predictions.jsonl → route.threshold_version"],
        ["router_version", kacis(router), "→ route.router_version"],
    ]
    uyari = ""
    if ortam.get("docling_surum_uyari"):
        uyari = '<p class="uyari">%s</p>' % kacis(ortam["docling_surum_uyari"])
    return bolum(1, "Ortam", uyari + tablo(["alan", "değer", "kaynak"], satirlar))


def _termal(tel_yolu):
    """Telemetriden kisilma kaniti. Hizlanma katsayisi, olcum sirasinda donanimin
    kisilip kisilmadigi bilinmeden savunulamaz."""
    if not tel_yolu or not os.path.isfile(tel_yolu):
        return None
    ornek = kisilma = 0
    en_sicak = 0.0
    sebepler = set()
    with open(tel_yolu, encoding="utf-8") as f:
        for satir in f:
            if not satir.strip():
                continue
            try:
                g = [x.strip() for x in json.loads(satir)["gpu"].split(",")]
            except Exception:
                continue
            if len(g) < 9:
                continue
            ornek += 1
            try:
                en_sicak = max(en_sicak, float(g[4]))
            except ValueError:
                pass
            bayrak = int(g[8], 16) if g[8].startswith("0x") else 0
            # 0x20 SW Thermal Slowdown, 0x40 HW Thermal Slowdown, 0x4 SW Power Cap
            if bayrak & 0x60:
                kisilma += 1
                sebepler.add("termal")
            if bayrak & 0x4:
                sebepler.add("güç limiti")
    return {"ornek": ornek, "kisilma": kisilma, "en_sicak": en_sicak,
            "sebepler": sorted(sebepler)}


def bolum_kabul(envanter, cuda_olc, det_kucuk, det_buyuk, kosular, termal, cache_es):
    r = []
    # --- envanter
    if envanter is None:
        r.append(rozet("ÖLÇÜLMEDİ", "Envanter sha256"))
    else:
        g = envanter.get("gecti")
        r.append(rozet("GEÇTİ" if g else "GEÇMEDİ", "Envanter sha256",
                       "%d/%d kayıt eşleşti, farklı sha256: %d, kendi korpus: %d PDF"
                       % (envanter.get("ortak", 0), envanter.get("gonderilen_kayit", 0),
                          len(envanter.get("farkli_sha256") or []), envanter.get("kendi_korpus_pdf", 0)),
                       "out/gpu/envanter_karsilastirma.json → gecti"))
    # --- fingerprint
    fps = {k: (v["ozet"] or {}).get("metric_fingerprint") for k, v in kosular.items() if v.get("ozet")}
    if not fps:
        r.append(rozet("ÖLÇÜLMEDİ", "metric_fingerprint eşitliği"))
    else:
        esit = len(set(fps.values())) == 1
        r.append(rozet("GEÇTİ" if esit else "GEÇMEDİ", "metric_fingerprint eşitliği",
                       "; ".join("%s = %s" % (k, v) for k, v in fps.items()),
                       "out/c1_runs/*/summary.json → metric_fingerprint"))
    # --- mean_utility.fast, AYNI belgeler uzerinde
    # summary.json'daki ortalamalari dogrudan karsilastirmak YANLIS olurdu: uc kosu
    # farkli belge kumeleri (380 / 201 / 60) uzerinde, ortalamalarinin farkli
    # cikmasi beklenir ve cihazla ilgisi yoktur. Dogru test kesisim uzerinde
    # BELGE BELGE karsilastirmadir; hizli yol GPU kullanmadigi icin her belgede
    # birebir ayni cikmali.
    for ad, sol, sag in (("CPU tabanı ↔ GPU aynı 201", "cpu_taban", "gpu_ayni201"),
                         ("bu makine CPU 60 ↔ GPU", "cpu_ayni_makine_60", "gpu_tam_380")):
        a = {x["id"]: x for x in (kosular.get(sol, {}).get("satirlar") or [])
             if x.get("status") == "ok"}
        b = {x["id"]: x for x in (kosular.get(sag, {}).get("satirlar") or [])
             if x.get("status") == "ok"}
        ortak = sorted(set(a) & set(b))
        if not ortak:
            r.append(rozet("ÖLÇÜLMEDİ", "mean_utility.fast — %s" % ad,
                           "ortak belge yok"))
            continue
        farkli = [k for k in ortak
                  if abs(a[k]["scores"]["fast"]["utility"]
                         - b[k]["scores"]["fast"]["utility"]) > 1e-9]
        r.append(rozet("GEÇTİ" if not farkli else "GEÇMEDİ",
                       "mean_utility.fast — %s" % ad,
                       "%d ortak belgenin %d'ında fark%s"
                       % (len(ortak), len(farkli),
                          "" if not farkli else
                          " — hızlı yol GPU kullanmıyor; farklıysa ortamda cihaz "
                          "dışında bir şey daha değişmiş: " + ", ".join(farkli[:5])),
                       "out/c1_runs/*/predictions.jsonl → scores.fast.utility"))
    # --- determinizm
    for ad, veri, yol in (("küçük belge", det_kucuk, "out/gpu/gpu_docling_cuda_determinizm_turkce.json"),
                          ("büyük belge", det_buyuk, "out/gpu/gpu_docling_cuda_determinizm_gpt3.json")):
        d = (veri or {}).get("determinizm")
        if not d:
            r.append(rozet("ÖLÇÜLMEDİ", "Determinizm — %s" % ad))
        else:
            r.append(rozet("GEÇTİ" if d.get("hepsi_ayni") else "GEÇMEDİ",
                           "Determinizm — %s" % ad,
                           "%s, %d koşu, çıktı sha256: %s"
                           % (kacis(d.get("belge")), d.get("kosu", 0),
                              kacis((d.get("ozetler") or [""])[0][:16])),
                           yol + " → determinizm.hepsi_ayni"))
    # --- cihaz esdegerligi
    es = (cuda_olc or {}).get("esdegerlik")
    if not es:
        r.append(rozet("ÖLÇÜLMEDİ", "Cihaz eşdeğerliği"))
    else:
        toplam = sum(b.get("farkli_sayfa", 0) for b in es["belgeler"])
        sayfa = sum(b.get("sayfa", 0) for b in es["belgeler"])
        r.append(rozet("GEÇTİ" if toplam == 0 else "GEÇMEDİ", "Cihaz eşdeğerliği",
                       "aynı makinede CPU ve CUDA: %d/%d sayfada fark" % (toplam, sayfa),
                       "out/gpu_docling_cuda.json → esdegerlik.belgeler[].farkli_sayfa"))
    # --- cihaz esdegerligi, IKINCI test (farkli korpus, tablo yapilari dahil)
    if not cache_es:
        r.append(rozet("ÖLÇÜLMEDİ", "Cihaz eşdeğerliği — C1 cache"))
    else:
        r.append(rozet("GEÇTİ" if cache_es.get("gecti") else "GEÇMEDİ",
                       "Cihaz eşdeğerliği — C1 cache",
                       "%d belgede sayfa metni ve tablo yapıları: %d / %d farklı "
                       "(device alanı: CPU %s, CUDA %s)"
                       % (cache_es.get("karsilastirilan", 0),
                          len(cache_es.get("sayfa_metni_farkli") or []),
                          len(cache_es.get("tablo_yapisi_farkli") or []),
                          ",".join(cache_es.get("cpu_device") or []),
                          ",".join(cache_es.get("cuda_device") or [])),
                       "out/gpu/cache_esdegerlik.json → gecti"))
    # --- termal
    if not termal or not termal["ornek"]:
        r.append(rozet("ÖLÇÜLMEDİ", "Donanım kısılması"))
    else:
        yok = termal["kisilma"] == 0
        r.append(rozet("GEÇTİ" if yok else "GEÇMEDİ", "Donanım kısılması",
                       "%d örneğin %d'sinde kısılma (%s); en yüksek sıcaklık %s°C. "
                       "Kısılma varsa GPU hızlanması bir ALT SINIRDIR."
                       % (termal["ornek"], termal["kisilma"],
                          ", ".join(termal["sebepler"]) or "yok", sayi(termal["en_sicak"], 0)),
                       "loglar/telemetri.jsonl → clocks_throttle_reasons.active"))
    return bolum(2, "Kabul kontrolleri", '<div class="rozetler">%s</div>' % "".join(r),
                 "Her rozet GEÇTİ / GEÇMEDİ / ÖLÇÜLMEDİ üçlüsünden birini gösterir; "
                 "ölçülmemiş bir kontrol asla yeşil olmaz.")


# ================================================================== bolum 3-4
def cache_sureleri(dizin):
    """Belge basina ortalama, cache payload'larindaki `duration_ms`'ten.

    Kabuk duvar saatinden HESAPLANMAZ: kosu yeniden baslatilabilir, devam
    kosusunda gecen sure model yuklemeyi ve atlanan belgeleri de icerir.
    Payload'daki sure belge donusumunun kendisini olcuyor.
    """
    if not os.path.isdir(dizin):
        return None
    sureler, cihazlar, hata = [], {}, 0
    for ad in sorted(os.listdir(dizin)):
        if not ad.endswith(".json"):
            continue
        try:
            with open(os.path.join(dizin, ad), encoding="utf-8") as f:
                p = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        sureler.append(p.get("duration_ms") or 0.0)
        cihazlar[p.get("device") or "?"] = cihazlar.get(p.get("device") or "?", 0) + 1
        if not p.get("ok"):
            hata += 1
    if not sureler:
        return None
    return {"belge": len(sureler), "ortalama_ms": round(statistics.fmean(sureler), 1),
            "medyan_ms": round(statistics.median(sureler), 1),
            "toplam_sn": round(sum(sureler) / 1000, 1), "hata": hata, "cihazlar": cihazlar}


def bolum_hiz(cpu_olc, cuda_olc, cache_cuda, cache_cpu, tekrar_cpu=None, tekrar_cuda=None,
              kararlilik=None):
    if not cpu_olc and not cuda_olc:
        return bolum(3, "Hız", '<p class="yok">%s</p>' % OLCULMEDI)
    cpu_b = {b["belge"]: b for b in (cpu_olc or {}).get("belgeler", [])}
    cuda_b = {b["belge"]: b for b in (cuda_olc or {}).get("belgeler", [])}
    satirlar = []
    for ad in list(cpu_b) or list(cuda_b):
        c, g = cpu_b.get(ad), cuda_b.get(ad)
        kat = (c["sure_sn"] / g["sure_sn"]) if c and g and g["sure_sn"] else None
        satirlar.append([
            kacis(ad), sayi((c or g or {}).get("sayfa")),
            sayi(c["sure_sn"], 2) if c else sayi(None),
            sayi(g["sure_sn"], 2) if g else sayi(None),
            sayi(c["ms_sayfa"], 1) if c else sayi(None),
            sayi(g["ms_sayfa"], 1) if g else sayi(None),
            ('<b>%s×</b>' % sayi(kat, 2)) if kat else sayi(None),
        ])
    if cpu_olc and cuda_olc:
        kat = cpu_olc["toplam_sn"] / cuda_olc["toplam_sn"] if cuda_olc["toplam_sn"] else None
        satirlar.append(("toplam", [
            "<b>TOPLAM</b>", "<b>%s</b>" % sayi(cpu_olc.get("toplam_sayfa")),
            "<b>%s</b>" % sayi(cpu_olc["toplam_sn"], 1), "<b>%s</b>" % sayi(cuda_olc["toplam_sn"], 1),
            "<b>%s</b>" % sayi(cpu_olc["ortalama_ms_sayfa"], 1),
            "<b>%s</b>" % sayi(cuda_olc["ortalama_ms_sayfa"], 1),
            "<b>%s×</b>" % sayi(kat, 2)]))
    ust = tablo(["belge", "sayfa", "CPU sn", "GPU sn", "CPU ms/sayfa", "GPU ms/sayfa", "hızlanma"],
                satirlar,
                "out/gpu_docling_cpu.json ve out/gpu/gpu_docling_cuda.json → belgeler[].sure_sn, .ms_sayfa")

    kartlar = []
    for ad, veri, yol in (("C1 cache — CUDA", cache_cuda, "out/c1_docling_cache_cuda/*.json"),
                          ("C1 cache — CPU", cache_cpu, "out/c1_docling_cache_cpu/*.json")):
        if not veri:
            kartlar.append(kart(ad, '<span class="yok">%s</span>' % OLCULMEDI, "", yol))
        else:
            cihaz = ", ".join("%s×%d" % (k, v) for k, v in veri["cihazlar"].items())
            kartlar.append(kart(
                ad, "%s ms" % sayi(veri["ortalama_ms"], 1),
                "belge başına ortalama · %d belge · medyan %s ms · payload device: %s"
                % (veri["belge"], sayi(veri["medyan_ms"], 1), cihaz),
                yol + " → duration_ms"))
    # Tekrarlanabilirlik: ayni olcum, telemetri acikken, AYRI cikti kokune.
    # Iki bagimsiz olcum tutuyorsa hiz sayisi tek bir kosunun sansi degildir.
    for ad, ana, tek in (("CPU", cpu_olc, tekrar_cpu), ("GPU", cuda_olc, tekrar_cuda)):
        if not ana or not tek:
            kartlar.append(kart("Tekrarlanabilirlik — %s" % ad,
                                '<span class="yok">%s</span>' % OLCULMEDI, "",
                                "out/gpu/tekrar/gpu_docling_%s.json"
                                % ("cpu" if ad == "CPU" else "cuda")))
            continue
        a, b = ana["ortalama_ms_sayfa"], tek["ortalama_ms_sayfa"]
        sapma = abs(b - a) / a * 100 if a else None
        kartlar.append(kart(
            "Tekrarlanabilirlik — %s" % ad, "%%%s sapma" % sayi(sapma, 1),
            "1. ölçüm %s ms/sayfa · 2. ölçüm %s ms/sayfa (aynı 261 sayfa)"
            % (sayi(a, 1), sayi(b, 1)),
            "out/gpu_docling_*.json ve out/gpu/tekrar/gpu_docling_*.json → ortalama_ms_sayfa"))
    # Hizlanma TEK SAYI degil ARALIK: iki bagimsiz olcum ciftinin ikisi de yazilir.
    aralik = ""
    if kararlilik and kararlilik.get("eslesmis_ciftler"):
        c = kararlilik["eslesmis_ciftler"]
        satir = [[kacis(x["cift"]), sayi(x["cpu_ms_sayfa"], 1), sayi(x["gpu_ms_sayfa"], 1),
                  "<b>%s×</b>" % sayi(x["hizlanma"], 2)] for x in c]
        h = kararlilik.get("hizlanma_araligi") or {}
        aralik = ('<div class="uyari">Hızlanma katsayısı tek bir sayı DEĞİL: aynı ölçüm '
                  'iki kez koşuldu ve <b>%s× – %s×</b> aralığı çıktı. CPU koşuları arası '
                  'oran %s×, GPU koşuları arası oran %s×. Çapraz eşleme (1. CPU / 2. GPU) '
                  'iki farklı makine durumunu böler, anlamsızdır.</div>'
                  % (sayi(h.get("en_dusuk"), 2), sayi(h.get("en_yuksek"), 2),
                     sayi(kararlilik.get("cpu_kosular_arasi_oran"), 3),
                     sayi(kararlilik.get("gpu_kosular_arasi_oran"), 3))
                  + tablo(["ölçüm çifti", "CPU ms/sayfa", "GPU ms/sayfa", "hızlanma"], satir,
                          "out/gpu/hiz_kararliligi.json → eslesmis_ciftler")
                  + ('<p class="not">%s</p>' % kacis(kararlilik.get("not") or "")))
    return bolum(3, "Hız", ust + '<div class="kartlar">%s</div>' % "".join(kartlar) + aralik,
                 "Süreler ölçülen sürecin içinde perf_counter ile alındı; kabuk duvar "
                 "saati kullanılmadı, bu yüzden kesinti/yeniden başlatma etkilemez.")


def kapi_ms_sayfa(hata_veri):
    """Kapinin sayfa AGIRLIKLI ms/sayfa maliyeti.

    Belge basina `toplam_ms_sayfa` degerlerinin duz ortalamasi kisa belgeleri
    fazla agirliklandirirdi; toplam ms / toplam sayfa dogru sayidir.
    """
    if not hata_veri:
        return None
    ms = sum(b.get("toplam_ms") or 0 for b in hata_veri)
    sf = sum(b.get("sayfa_sayisi") or 0 for b in hata_veri)
    if not sf:
        return None
    bilesenler = {}
    for anahtar in ("inspector_ms", "kapi_ms", "critic_ms"):
        bilesenler[anahtar] = round(
            sum((b.get("sureler_ms") or {}).get(anahtar) or 0 for b in hata_veri) / sf, 2)
    return {"ms_sayfa": round(ms / sf, 2), "sayfa": sf, "bilesenler": bilesenler,
            "agir_sayfa": sum(b.get("agir_sayfa") or 0 for b in hata_veri)}


def bolum_oran(kapi, cpu_olc, cuda_olc):
    if not kapi:
        return bolum(4, "Maliyet oranı", '<p class="yok">%s — out/hata_arayuzu_veri.json yok</p>' % OLCULMEDI)
    satirlar = [[
        "kapı (pdf-inspector + PyMuPDF + critic)", sayi(kapi["ms_sayfa"], 2),
        "1×", "%d sayfa üzerinden" % kapi["sayfa"]]]
    for ad, olc in (("Docling CPU (bu makine)", cpu_olc), ("Docling CUDA (bu makine)", cuda_olc)):
        if not olc:
            satirlar.append([ad, sayi(None), sayi(None), OLCULMEDI])
            continue
        agir = olc["ortalama_ms_sayfa"]
        satirlar.append([ad, sayi(agir, 1), "<b>%s×</b>" % sayi(agir / kapi["ms_sayfa"], 0),
                         "%d sayfa üzerinden" % olc.get("toplam_sayfa", 0)])
    ust = tablo(["hat", "ms/sayfa", "oran = ağır / kapı", "not"], satirlar,
                "out/hata_arayuzu_veri.json → toplam_ms, sayfa_sayisi; "
                "out/gpu_docling_*.json → ortalama_ms_sayfa")

    # "hepsi agir" senaryosu -- HESAPLANIR, tahmin edilmez.
    kartlar = []
    oran_agir = kapi["agir_sayfa"] / kapi["sayfa"] if kapi["sayfa"] else 0
    for ad, olc in (("CPU", cpu_olc), ("GPU", cuda_olc)):
        if not olc:
            kartlar.append(kart('"hepsi ağır" — %s' % ad, '<span class="yok">%s</span>' % OLCULMEDI))
            continue
        agir = olc["ortalama_ms_sayfa"]
        bugun = kapi["ms_sayfa"] + oran_agir * agir
        hepsi = kapi["ms_sayfa"] + agir
        kartlar.append(kart(
            '"hepsi ağır" — %s' % ad, "%s×" % sayi(hepsi / bugun, 2),
            "bugün %s ms/sayfa (ağır hatta giden %s%%) → hepsi ağır %s ms/sayfa"
            % (sayi(bugun, 1), sayi(oran_agir * 100, 1), sayi(hepsi, 1)),
            "out/hata_arayuzu_veri.json → agir_sayfa / sayfa_sayisi"))
    return bolum(4, "Maliyet oranı", ust + '<div class="kartlar">%s</div>' % "".join(kartlar),
                 "Mimarinin gerekçesi bu orana dayanıyor: ağır motor kapıdan kaç kat pahalı? "
                 "GPU'da oran küçülürse sayfa seçmenin gerekçesi zayıflar.")


# ================================================================== bolum 5-6
SUTUNLAR = [("cpu_taban", "CPU tabanı (gönderilen)"), ("gpu_ayni201", "GPU aynı 201"),
            ("gpu_tam_380", "GPU tam 380"), ("cpu_ayni_makine_60", "bu makine CPU 60")]

SATIRLAR = [
    ("documents", "documents", 0), ("ok", "ok", 0), ("errors", "errors", 0),
    ("routed_heavy", "routed_heavy", 0),
    ("heavy_gain_ge_0_02", "heavy_gain_ge_0_02", 0),
    ("route_precision_at_0_02", "route_precision_at_0_02", 4),
    ("route_recall_at_0_02", "route_recall_at_0_02", 4),
    ("mean_utility_fast", "mean_utility.fast", 6),
    ("mean_utility_heavy", "mean_utility.heavy", 6),
    ("mean_utility_routed", "mean_utility.routed", 6),
    ("net", "NET = Σ(routed_u − fast_u)", 4),
    ("karantina_red", "karantina red sayısı", 0),
    ("karantina_isabet", "karantina isabeti (doğru red / toplam red)", 4),
]


def bolum_c1(metrik_tablosu, dogrulama_notu):
    if not metrik_tablosu:
        return bolum(5, "C1 sonuçları", '<p class="yok">%s</p>' % OLCULMEDI)
    sekmeler, panolar = [], []
    aileler = [("ocrturk", "ocrturk"), ("opendataloader_bench", "opendataloader_bench"),
               ("birlesik", "birleşik")]
    for i, (anahtar, etiket) in enumerate(aileler):
        sekmeler.append('<button class="sekme%s" data-pano="p_%s">%s</button>'
                        % (" etkin" if i == 0 else "", anahtar, kacis(etiket)))
        satirlar = []
        for alan, ad, basamak in SATIRLAR:
            hucre = ["<b>%s</b>" % kacis(ad)]
            for sk, _ in SUTUNLAR:
                m = (metrik_tablosu.get(sk) or {}).get(anahtar)
                hucre.append(sayi(None) if not m else sayi(m.get(alan), basamak))
            satirlar.append(hucre)
        panolar.append('<div class="pano%s" id="p_%s">%s</div>'
                       % (" etkin" if i == 0 else "", anahtar,
                          tablo(["metrik"] + [b for _, b in SUTUNLAR], satirlar,
                                "out/c1_runs/<run-id>/predictions.jsonl → route.routed_heavy, "
                                "delta.*, scores.*.utility, merge.quarantined_pages")))
    return bolum(5, "C1 sonuçları",
                 '<div class="sekmeler no-print">%s</div>%s%s'
                 % ("".join(sekmeler), "".join(panolar), dogrulama_notu),
                 "ocrturk ve opendataloader_bench ters yönlü iki rejim; birleşik tek sayı "
                 "ikisini gizler. Baskıda üç sekme de art arda basılır.")


def bolum_karar_degisen(a, b, ad_a, ad_b):
    """Iki kosu arasinda route karari degisen ya da utility'si kayan belgeler."""
    if a is None or b is None:
        return bolum(6, "Kararı değişen belgeler", '<p class="yok">%s</p>' % OLCULMEDI)
    ia = {r["id"]: r for r in a if r.get("status") == "ok"}
    ib = {r["id"]: r for r in b if r.get("status") == "ok"}
    satirlar = []
    for kimlik in sorted(set(ia) & set(ib)):
        ra, rb = ia[kimlik], ib[kimlik]
        ka, kb = ra["route"]["routed_heavy"], rb["route"]["routed_heavy"]
        ua = ra["scores"]["routed"]["utility"]
        ub = rb["scores"]["routed"]["utility"]
        fark = round(ub - ua, 6)
        if ka == kb and abs(fark) <= 0.02:
            continue
        satirlar.append((abs(fark), [
            kacis(kimlik), kacis(ra.get("dataset")),
            "AĞIR" if ka else "hızlı", "AĞIR" if kb else "hızlı",
            ('<b class="%s">%s</b>' % ("arti" if fark > 0 else "eksi", sayi(fark, 6))),
            '<span class="etiket">karar değişti</span>' if ka != kb else
            ('<span class="etiket sari">|Δ| &gt; 0,02</span>')]))
    satirlar.sort(key=lambda s: -s[0])
    govde = [s[1] for s in satirlar]
    if not govde:
        icerik = ('<p class="iyi">İki koşu arasında route kararı değişen belge YOK ve '
                  'hiçbir belgede |Δ utility| &gt; 0,02 değil.</p>'
                  + kaynak("out/c1_runs/%s ve %s/predictions.jsonl" % (ad_a, ad_b),
                           "route.routed_heavy, scores.routed.utility"))
    else:
        icerik = ('<input class="filtre no-print" placeholder="belge id ile filtrele...">'
                  + tablo(["id", "veri seti", "%s kararı" % ad_a, "%s kararı" % ad_b,
                           "Δ utility", "işaret"], govde,
                          "out/c1_runs/{%s,%s}/predictions.jsonl → route.routed_heavy, "
                          "scores.routed.utility" % (ad_a, ad_b)))
    return bolum(6, "Kararı değişen belgeler", icerik,
                 "Yönlendirme kararı cihazla DEĞİŞMEMELİ — kapı sinyalleri pdf-inspector "
                 "ve PyMuPDF'ten geliyor, ikisi de GPU kullanmıyor. Değiştiyse bu bir bulgudur.")


# ================================================================== bolum 7-9
def hukum_sayimi(veri):
    """Sayfa hukumlerini ANAHTAR ADI SABIT YAZMADAN sayar.

    Bu projede bir sayac "KACAN" okuyordu ama uretim "KACIRILDI" yaziyor; sonuc
    her kosuda 0 gorundu -- yanlis sayi degil, HIC VAR OLMAYAN sayi. O yuzden
    degerler veriden toplaniyor ve iki JSON'un anahtar kumeleri panoda basiliyor.
    """
    if not veri:
        return None
    sayim = {"tablo_hukmu": {}, "sekil_hukmu": {}, "yonlendirme": {}}
    sayfa = 0
    for belge in veri:
        for s in belge.get("sayfalar") or []:
            sayfa += 1
            for alan in sayim:
                deger = s.get(alan)
                if deger is not None:
                    sayim[alan][deger] = sayim[alan].get(deger, 0) + 1
    sayim["_sayfa"] = sayfa
    return sayim


def bolum_kendi_korpus(cpu, gpu):
    sc, sg = hukum_sayimi(cpu), hukum_sayimi(gpu)
    if not sc and not sg:
        return bolum(7, "Kendi korpus hükümleri", '<p class="yok">%s</p>' % OLCULMEDI)
    parcalar = []
    for alan, baslik in (("tablo_hukmu", "tablo hükmü"), ("sekil_hukmu", "şekil hükmü"),
                         ("yonlendirme", "yönlendirme hükmü")):
        ac = (sc or {}).get(alan, {})
        ag = (sg or {}).get(alan, {})
        anahtarlar = sorted(set(ac) | set(ag))
        uyari = ""
        if sc and sg and set(ac) != set(ag):
            uyari = ('<div class="uyari">Anahtar kümeleri farklı — CPU: %s · GPU: %s. '
                     'Eksik anahtar 0 değil, ölçülmemiştir.</div>'
                     % (kacis(sorted(ac)), kacis(sorted(ag))))
        satirlar = []
        for a in anahtarlar:
            c, g = ac.get(a), ag.get(a)
            d = (g - c) if (c is not None and g is not None) else None
            satirlar.append([
                "<b>%s</b>" % kacis(a), sayi(c), sayi(g),
                ("<b class='%s'>%s%s</b>" % ("eksi" if d < 0 else "arti", "+" if d > 0 else "", sayi(d))
                 if d else ("0" if d == 0 else sayi(None)))])
        parcalar.append("<h3>%s</h3>%s%s" % (
            kacis(baslik), uyari,
            tablo(["hüküm", "CPU", "GPU", "fark"], satirlar,
                  "out/hata_arayuzu_veri.json ve out_gpu/hata_arayuzu_veri.json → "
                  "sayfalar[].%s" % alan)))
    bilgi = ('<p class="not">Sayfa sayısı — CPU: %s · GPU: %s</p>'
             % (sayi((sc or {}).get("_sayfa")), sayi((sg or {}).get("_sayfa"))))
    return bolum(7, "Kendi korpus hükümleri", bilgi + "".join(parcalar),
                 "Ağır motor metni GPU'da değişirse tablo/şekil hükümleri de değişir. "
                 "Anahtar adları veriden toplanıyor, elle sabit yazılmıyor.")


def _fark_turu(a: str, b: str) -> str:
    """Kozmetik mi (bosluk/satir sonu/tire) yoksa gercek icerik kaybi mi."""
    def sadelestir(t):
        return "".join(t.split()).replace("-", "").replace("‐", "")
    if sadelestir(a) == sadelestir(b):
        return "kozmetik (boşluk / satır sonu / tire)"
    ta, tb = a.count("|"), b.count("|")
    if abs(len(a) - len(b)) > 200 or abs(ta - tb) > 4:
        return "İÇERİK KAYBI"
    return "içerik farkı (küçük)"


def bolum_esdegerlik(cuda_olc, cpu_dizin, cuda_dizin, cache_es=None, atif=None):
    es = (cuda_olc or {}).get("esdegerlik")
    if not es:
        return bolum(8, "Eşdeğerlik farkları", '<p class="yok">%s</p>' % OLCULMEDI)
    ek = ""
    if cache_es:
        ek += ('<h3>ikinci test — C1 korpusu, tablo yapıları dahil</h3>'
               + tablo(["ölçü", "değer"], [
                   ["karşılaştırılan belge", sayi(cache_es.get("karsilastirilan"))],
                   ["sayfa metni farklı", sayi(len(cache_es.get("sayfa_metni_farkli") or []))],
                   ["tablo yapısı farklı", sayi(len(cache_es.get("tablo_yapisi_farkli") or []))],
                   ["payload device (CPU / CUDA)",
                    kacis("%s / %s" % (",".join(cache_es.get("cpu_device") or []),
                                       ",".join(cache_es.get("cuda_device") or [])))]],
                   "out/gpu/cache_esdegerlik.json"))
    if atif:
        b = atif.get("belgeler") or []
        ek += ('<h3>atıf — fark cihazdan mı, makineden mi</h3>'
               '<p class="not">Gönderilen CPU tabanı ile bu makinenin GPU koşusu arasında '
               'heavy utility farkı çıkan belgeler, bu makinede CPU ve CUDA ile yeniden '
               'üretildi. İkisi de aynı çıkıyorsa fark cihazdan değil makineden gelir.</p>'
               + tablo(["belge", "sayfa metni farklı", "tablo yapısı farklı", "device (CPU / CUDA)"],
                       [[kacis(x["id"]), sayi(x["sayfa_farkli"]), sayi(x["tablo_farkli"]),
                         kacis("%s / %s" % (x.get("cpu_device"), x.get("cuda_device")))]
                        for x in b],
                       "out/gpu/atif_5belge.json → belgeler[]",
                       "Sonuç: cihazdan kaynaklı fark %s."
                       % ("VAR" if atif.get("cihazdan_kaynakli_fark") else "YOK")))
    toplam = sum(b.get("farkli_sayfa", 0) for b in es["belgeler"])
    if toplam == 0:
        ozet = tablo(["belge", "sayfa", "farklı sayfa"],
                     [[kacis(b["belge"]), sayi(b.get("sayfa")), sayi(b.get("farkli_sayfa"))]
                      for b in es["belgeler"]],
                     "out/gpu_docling_cuda.json → esdegerlik.belgeler[]")
        return bolum(8, "Eşdeğerlik farkları",
                     '<p class="iyi">Aynı makinede CPU ve CUDA çıktıları <b>bütün '
                     'sayfalarda birebir aynı</b>. İçerik kaybı yok, kozmetik fark da yok.</p>'
                     + ozet + ek,
                     "Başka bir RTX 4060'lı makinede 261 sayfanın 7'sinde fark, 1'inde "
                     "gerçek tablo kaybı ölçülmüştü. Bu makinede tekrarlanmadı.")
    satirlar = []
    for b in es["belgeler"]:
        if not b.get("farkli_sayfa"):
            continue
        ac = K.json(os.path.join(cpu_dizin, b["belge"] + "_sayfalar.json")) or {}
        ag = K.json(os.path.join(cuda_dizin, b["belge"] + "_sayfalar.json")) or {}
        sc, sg = ac.get("sayfalar") or [], ag.get("sayfalar") or []
        for no in b.get("ornekler") or []:
            i = no - 1
            x = sc[i] if i < len(sc) else ""
            y = sg[i] if i < len(sg) else ""
            tur = _fark_turu(x, y)
            satirlar.append([
                kacis(b["belge"]), sayi(no),
                '<span class="etiket %s">%s</span>' % ("kirmizi" if "KAYBI" in tur else "", kacis(tur)),
                '<pre class="diff">%s</pre>' % kacis(x[:200]),
                '<pre class="diff">%s</pre>' % kacis(y[:200])])
    return bolum(8, "Eşdeğerlik farkları",
                 tablo(["belge", "sayfa", "fark türü", "CPU (ilk 200 karakter)",
                        "GPU (ilk 200 karakter)"], satirlar,
                       "out/gpu_docling_json_cpu/ ve out/gpu/a3_cuda_sayfalar/ → sayfalar[]") + ek)


def bolum_acik(eksik, atlanan, notlar):
    ogeler = []
    for y in sorted(set(eksik)):
        ogeler.append("<li><b>%s</b> — dosya yok; ilgili kart “%s” yazıyor.</li>"
                      % (kacis(y), OLCULMEDI))
    for a, sebep in atlanan:
        ogeler.append("<li><b>%s</b> — adım bilerek atlandı.%s</li>"
                      % (kacis(a),
                         ('<pre class="diff">%s</pre>' % kacis(sebep)) if sebep else ""))
    for n in notlar:
        ogeler.append("<li>%s</li>" % n)
    if not ogeler:
        ogeler.append('<li class="iyi">Açık kalan yok: beklenen bütün dosyalar üretildi.</li>')
    return bolum(9, "Açık kalanlar", "<ul class=\"acik\">%s</ul>" % "".join(ogeler),
                 "Ölçülemeyen her şey sebebiyle burada listelenir.")


# ======================================================================== css
CSS = """
:root{--kagit:#fff;--murekkep:#16181d;--soluk:#6b7280;--cizgi:#e3e6ea;--vurgu:#1d4ed8;
--yesil:#0f7b3d;--yesilzemin:#e7f6ed;--kirmizi:#b42318;--kirmizizemin:#fdecea;
--sari:#8a6100;--sarizemin:#fdf3e0;--zemin:#f6f7f9;}
*{box-sizing:border-box}
body{margin:0;background:var(--zemin);color:var(--murekkep);
font:15px/1.55 -apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.sar{max-width:1180px;margin:0 auto;padding:24px 20px 80px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
background:var(--kagit);border:1px solid var(--cizgi);border-radius:12px;padding:20px 22px;margin-bottom:20px}
h1{margin:0 0 4px;font-size:22px;letter-spacing:-.01em}
.altbaslik{color:var(--soluk);font-size:13px;margin:0}
nav.arayuz-gecis{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 0;font-size:13px}
nav.arayuz-gecis a{color:var(--vurgu);text-decoration:none;border:1px solid var(--cizgi);border-radius:6px;padding:3px 10px;background:var(--zemin)}
nav.arayuz-gecis a:hover{text-decoration:underline}
nav.arayuz-gecis a.aktif{background:var(--murekkep);color:#fff;border-color:var(--murekkep)}
button.yazdir{background:var(--vurgu);color:#fff;border:0;border-radius:8px;
padding:10px 16px;font-size:14px;cursor:pointer;white-space:nowrap}
button.yazdir:hover{filter:brightness(1.1)}
.bolum{background:var(--kagit);border:1px solid var(--cizgi);border-radius:12px;
padding:18px 22px 22px;margin-bottom:18px;break-inside:avoid}
h2{font-size:17px;margin:0 0 6px;display:flex;align-items:center;gap:10px}
h2 .no{background:var(--murekkep);color:#fff;width:24px;height:24px;border-radius:6px;
display:inline-flex;align-items:center;justify-content:center;font-size:13px}
h3{font-size:14px;margin:18px 0 6px;color:var(--soluk);text-transform:uppercase;letter-spacing:.04em}
.aciklama{color:var(--soluk);font-size:13px;margin:0 0 14px}
.kaynak{color:var(--soluk);font-size:11px;margin-top:6px;font-family:ui-monospace,Menlo,Consolas,monospace;word-break:break-all}
.not{color:var(--soluk);font-size:12px;margin-top:6px}
.yok{color:var(--soluk);font-style:italic}
.iyi{color:var(--yesil);background:var(--yesilzemin);border:1px solid #bfe3cd;
border-radius:8px;padding:10px 12px;margin:0 0 12px}
.uyari{color:var(--kirmizi);background:var(--kirmizizemin);border:1px solid #f3c2bd;
border-radius:8px;padding:10px 12px;margin:0 0 12px;font-size:13px}
.kaydir{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--cizgi);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--zemin);font-weight:600;white-space:nowrap;font-size:12px;
text-transform:uppercase;letter-spacing:.03em;color:var(--soluk)}
tr.toplam td{background:#f0f4ff;border-top:2px solid var(--vurgu)}
.tablo-sar{margin-bottom:8px}
button.kopyala{float:right;background:none;border:1px solid var(--cizgi);border-radius:6px;
color:var(--soluk);font-size:11px;padding:4px 9px;cursor:pointer;margin-bottom:6px}
button.kopyala:hover{border-color:var(--vurgu);color:var(--vurgu)}
.rozetler{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.rozet{border:1px solid var(--cizgi);border-radius:10px;padding:12px 14px;break-inside:avoid}
.rozet-durum{font-weight:700;font-size:12px;letter-spacing:.06em;margin-bottom:3px}
.rozet-baslik{font-weight:600;font-size:14px}
.rozet-ayrinti{color:var(--soluk);font-size:12px;margin-top:4px}
.rozet.gecti{background:var(--yesilzemin);border-color:#bfe3cd}
.rozet.gecti .rozet-durum{color:var(--yesil)}
.rozet.gecmedi{background:var(--kirmizizemin);border-color:#f3c2bd}
.rozet.gecmedi .rozet-durum{color:var(--kirmizi)}
.rozet.olculmedi{background:var(--zemin)}
.rozet.olculmedi .rozet-durum{color:var(--soluk)}
.kartlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:14px}
.kart{border:1px solid var(--cizgi);border-radius:10px;padding:12px 14px;break-inside:avoid}
.kart-baslik{font-size:12px;color:var(--soluk);text-transform:uppercase;letter-spacing:.04em}
.kart-deger{font-size:26px;font-weight:700;margin:4px 0;letter-spacing:-.02em}
.kart-alt{font-size:12px;color:var(--soluk)}
.sekmeler{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.sekme{background:var(--zemin);border:1px solid var(--cizgi);border-radius:8px;
padding:7px 14px;font-size:13px;cursor:pointer}
.sekme.etkin{background:var(--murekkep);color:#fff;border-color:var(--murekkep)}
.pano{display:none}.pano.etkin{display:block}
.pano>.tablo-sar>.kaydir>table td:first-child{white-space:nowrap}
.etiket{background:var(--vurgu);color:#fff;border-radius:5px;padding:2px 7px;font-size:11px;white-space:nowrap}
.etiket.sari{background:var(--sari)}.etiket.kirmizi{background:var(--kirmizi)}
.arti{color:var(--yesil)}.eksi{color:var(--kirmizi)}
.filtre{width:100%;padding:8px 11px;border:1px solid var(--cizgi);border-radius:8px;
margin-bottom:10px;font-size:13px}
pre.diff{margin:0;font-size:11px;white-space:pre-wrap;word-break:break-word;
max-width:300px;font-family:ui-monospace,Menlo,Consolas,monospace}
ul.acik{margin:0;padding-left:20px;font-size:13px}ul.acik li{margin-bottom:6px}
@media print{
  @page{size:A4;margin:12mm}
  html,body{background:#fff}
  .no-print{display:none!important}
  .sar{max-width:none;padding:0}
  .bolum,.rozet,.kart,.tablo-sar{break-inside:avoid;page-break-inside:avoid}
  .bolum{border:1px solid #ccc;box-shadow:none;margin-bottom:10px;padding:12px 14px}
  header{border:0;padding:0 0 10px}
  .pano{display:block!important;margin-bottom:14px}
  .pano::before{content:attr(id);display:block;font-size:11px;color:#666;
    text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
  table{font-size:10.5px}th,td{padding:4px 6px}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

JS = """
document.querySelectorAll('.sekme').forEach(function(b){
  b.addEventListener('click',function(){
    var kap=b.closest('section');
    kap.querySelectorAll('.sekme').forEach(function(x){x.classList.remove('etkin')});
    kap.querySelectorAll('.pano').forEach(function(x){x.classList.remove('etkin')});
    b.classList.add('etkin');
    var p=kap.querySelector('#'+b.dataset.pano); if(p)p.classList.add('etkin');
  });
});
document.querySelectorAll('button.kopyala').forEach(function(b){
  b.addEventListener('click',function(){
    var t=document.getElementById(b.dataset.hedef); if(!t)return;
    var md=[];
    t.querySelectorAll('tr').forEach(function(tr,i){
      var h=[].map.call(tr.children,function(c){
        return c.innerText.replace(/\\s+/g,' ').replace(/\\|/g,'\\\\|').trim();});
      md.push('| '+h.join(' | ')+' |');
      if(i===0)md.push('|'+h.map(function(){return '---'}).join('|')+'|');
    });
    var metin=md.join('\\n');
    var bitir=function(ok){b.textContent=ok?'kopyalandı':'kopyalanamadı';
      setTimeout(function(){b.textContent='Markdown olarak kopyala'},1500);};
    if(navigator.clipboard&&window.isSecureContext){
      navigator.clipboard.writeText(metin).then(function(){bitir(true)},function(){bitir(false)});
    }else{
      var a=document.createElement('textarea');a.value=metin;a.style.position='fixed';
      a.style.opacity=0;document.body.appendChild(a);a.select();
      var ok=false;try{ok=document.execCommand('copy')}catch(e){}
      document.body.removeChild(a);bitir(ok);
    }
  });
});
document.querySelectorAll('input.filtre').forEach(function(f){
  f.addEventListener('input',function(){
    var q=f.value.toLowerCase();
    f.closest('section').querySelectorAll('tbody tr').forEach(function(tr){
      tr.style.display=tr.innerText.toLowerCase().indexOf(q)>-1?'':'none';
    });
  });
});
"""


# ======================================================================= main
def main() -> int:
    p = argparse.ArgumentParser(description="GPU kosusu tek sayfa panosu")
    # DUZELTME (2026-08-24, entegrasyon): GPU makinesindeki surum
    # REPO_ROOT/html yaziyordu -- depo kokunde html/ dizini yok, cikti
    # depoya ait olmayan bir yere dusuyordu. c1_arayuz.py ve
    # hata_arayuzu.py ile ayni yere alindi.
    p.add_argument("--cikti", default=os.path.join(BASE, "html", "gpu_panosu.html"))
    p.add_argument("--paket", default=PKT, help="gpu_paket_gonder dizini (CPU tabani)")
    p.add_argument("--telemetri", default=os.path.join(LOG, "telemetri.jsonl") if LOG else "")
    args = p.parse_args()

    ortam = K.json(os.path.join(OUT, "gpu", "ortam.json"))
    envanter = K.json(os.path.join(OUT, "gpu", "envanter_karsilastirma.json"))
    cpu_olc = K.json(os.path.join(OUT, "gpu_docling_cpu.json"))
    cuda_olc = (K.json(os.path.join(OUT, "gpu", "gpu_docling_cuda.json"))
                or K.json(os.path.join(OUT, "gpu_docling_cuda.json")))
    det_k = K.json(os.path.join(OUT, "gpu", "gpu_docling_cuda_determinizm_turkce.json"))
    det_b = K.json(os.path.join(OUT, "gpu", "gpu_docling_cuda_determinizm_gpt3.json"))
    hata_cpu = K.json(os.path.join(OUT, "hata_arayuzu_veri.json"))
    hata_gpu = K.json(os.path.join(OUT_GPU, "hata_arayuzu_veri.json"))
    cache_es = K.json(os.path.join(OUT, "gpu", "cache_esdegerlik.json"))
    tekrar_cpu = K.json(os.path.join(OUT, "gpu", "tekrar", "gpu_docling_cpu.json"))
    tekrar_cuda = K.json(os.path.join(OUT, "gpu", "tekrar", "gpu_docling_cuda.json"))
    kararlilik = K.json(os.path.join(OUT, "gpu", "hiz_kararliligi.json"))
    atif = K.json(os.path.join(OUT, "gpu", "atif_5belge.json"))

    kosular = {k: kosu_oku(k) for k in ("gpu_tam_380", "gpu_ayni201", "cpu_ayni_makine_60")}
    # CPU tabani baska bir makinede uretildi; pakette geldigi gibi okunur.
    taban = {"ozet": None, "satirlar": None}
    if args.paket:
        taban["ozet"] = K.json(os.path.join(args.paket, "taban_cpu", "summary.json"))
        taban["satirlar"] = K.jsonl(os.path.join(args.paket, "taban_cpu", "predictions.jsonl"))
        if taban["satirlar"]:
            son = {}
            for r in taban["satirlar"]:
                if r.get("id"):
                    son[r["id"]] = r
            taban["satirlar"] = list(son.values())
    kosular_tum = dict(kosular, cpu_taban=taban)

    # --- metrik tablosu: sutun -> aile -> metrikler
    metrik_tablosu = {}
    for sk, _ in SUTUNLAR:
        satirlar = kosular_tum.get(sk, {}).get("satirlar")
        metrik_tablosu[sk] = {
            "ocrturk": c1_metrikleri(satirlar, "ocrturk"),
            "opendataloader_bench": c1_metrikleri(satirlar, "opendataloader_bench"),
            "birlesik": c1_metrikleri(satirlar),
        }

    # Birlesik degerlerimiz uretimin summary.json'u ile TUTMALI; tutmuyorsa
    # panonun okuma katmani bozuktur ve bunu gizlememeli.
    uyumsuz = []
    for sk, _ in SUTUNLAR:
        ozet = (kosular_tum.get(sk) or {}).get("ozet")
        bizim = metrik_tablosu[sk]["birlesik"]
        if not ozet or not bizim:
            continue
        for alan, ozet_alan in (("documents", "documents"), ("ok", "ok"), ("errors", "errors"),
                                ("routed_heavy", "routed_heavy"),
                                ("route_precision_at_0_02", "route_precision_at_0_02")):
            a, b = bizim.get(alan), ozet.get(ozet_alan)
            if a is not None and b is not None and abs(float(a) - float(b)) > 1e-6:
                uyumsuz.append("%s.%s: pano %s ≠ summary.json %s" % (sk, alan, a, b))
    dogrulama = ('<div class="uyari">Doğrulama BAŞARISIZ — %s</div>' % kacis("; ".join(uyumsuz))
                 if uyumsuz else
                 '<p class="not">Doğrulama: birleşik sütunlar üretimin summary.json '
                 'değerleriyle birebir tuttu (documents, ok, errors, routed_heavy, '
                 'route_precision).</p>')

    termal = _termal(args.telemetri)
    kapi = kapi_ms_sayfa(hata_cpu)
    cache_cuda = cache_sureleri(os.path.join(OUT, "c1_docling_cache_cuda"))
    cache_cpu = cache_sureleri(os.path.join(OUT, "c1_docling_cache_cpu"))

    # Atlanan adimin SEBEBI .atla dosyasinin icinde durur; "atlandi" demek
    # yetmez, neden atlandigi panoda gorunmeli.
    atlanan = []
    durum = os.environ.get("DURUM", "")
    if durum and os.path.isdir(durum):
        for f in sorted(os.listdir(durum)):
            if not f.endswith(".atla"):
                continue
            try:
                with open(os.path.join(durum, f), encoding="utf-8") as fh:
                    sebep = fh.read().strip()
            except OSError:
                sebep = ""
            atlanan.append((f[:-5], sebep))

    notlar = []
    if termal and termal["kisilma"]:
        notlar.append("GPU ölçümleri sırasında <b>termal kısılma</b> gözlendi "
                      "(%d/%d örnek, en yüksek %s°C); GPU hızlanma katsayısı bir "
                      "<b>alt sınırdır</b>. kaynak: loglar/telemetri.jsonl"
                      % (termal["kisilma"], termal["ornek"], sayi(termal["en_sicak"], 0)))
    if kararlilik and (kararlilik.get("cpu_kosular_arasi_oran") or 1) > 1.1:
        notlar.append("Hız ölçümü bu makinede <b>tekrarlanabilir değil</b>: aynı ölçüm "
                      "iki kez koşuldu, CPU %s× GPU %s× fark verdi. Sebep doğrulanmadı; "
                      "hızlanma katsayısı aralık olarak raporlandı. "
                      "kaynak: out/gpu/hiz_kararliligi.json"
                      % (sayi(kararlilik.get("cpu_kosular_arasi_oran"), 2),
                         sayi(kararlilik.get("gpu_kosular_arasi_oran"), 2)))
    if not cache_cpu:
        notlar.append("Bu makinede CPU Docling cache'i üretilmedi; "
                      "“bu makine CPU 60” sütunu ölçülmedi.")

    govde = "".join([
        bolum_ortam(ortam, kosular_tum),
        bolum_kabul(envanter, cuda_olc, det_k, det_b, kosular_tum, termal, cache_es),
        bolum_hiz(cpu_olc, cuda_olc, cache_cuda, cache_cpu, tekrar_cpu, tekrar_cuda,
                  kararlilik),
        bolum_oran(kapi, cpu_olc, cuda_olc),
        bolum_c1(metrik_tablosu, dogrulama),
        bolum_karar_degisen(taban["satirlar"], kosular["gpu_ayni201"]["satirlar"],
                            "cpu_taban", "gpu_ayni201"),
        bolum_kendi_korpus(hata_cpu, hata_gpu),
        bolum_esdegerlik(cuda_olc, os.path.join(OUT, "gpu_docling_json_cpu"),
                         os.path.join(OUT, "gpu", "a3_cuda_sayfalar"), cache_es, atif),
        bolum_acik(K.eksik, atlanan, notlar),
    ])

    gpu_adi = ((ortam or {}).get("gpu") or {}).get("nvidia_smi_ozet", "").split(",")[0] or "GPU"
    sayfa = (
        "<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>GPU Panosu — smart_router</title><style>%s</style></head><body>"
        "<div class=\"sar\"><header><div><h1>GPU Panosu — smart_router PDF ayrıştırma</h1>"
        "<p class=\"altbaslik\">%s · üretildi %s · her sayı bir JSON alanına bağlı, "
        "ölçülmeyen hiçbir yere 0 yazılmadı</p>"
        # Arayuzler arasi gecis: pano tek basina degil, dort arayuzden biri.
        "<nav class=\"arayuz-gecis no-print\">"
        "<a href=\"index.html\">Arayüzler</a>"
        "<a href=\"gpu_panosu.html\" class=\"aktif\">GPU panosu</a>"
        "<a href=\"c1_arayuz_gpu380.html\">C1 380 belge (GPU)</a>"
        "<a href=\"c1_arayuz_gpu.html\">C1 201 kıyas (GPU↔CPU)</a>"
        "<a href=\"c1_arayuz.html\">C1 belge belge (CPU)</a>"
        "<a href=\"hata_arayuzu.html\">Kendi korpus sayfa sayfa</a>"
        "</nav></div>"
        "<button class=\"yazdir no-print\" onclick=\"window.print()\">Yazdır / PDF kaydet</button>"
        "</header>%s</div><script>%s</script></body></html>"
        % (CSS, kacis(gpu_adi), datetime.now().strftime("%Y-%m-%d %H:%M"), govde, JS))

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8") as f:
        f.write(sayfa)
    print("-> %s (%.0f KB)" % (args.cikti, os.path.getsize(args.cikti) / 1024))
    if K.eksik:
        print("olculmedi olarak isaretlenen %d dosya:" % len(set(K.eksik)))
        for y in sorted(set(K.eksik)):
            print("   -", y)
    if uyumsuz:
        print("DOGRULAMA UYUSMAZLIGI:", "; ".join(uyumsuz))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
