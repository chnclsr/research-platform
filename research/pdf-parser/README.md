# PDF ayrıştırma değerlendirmesi

Sistemin PDF okuma katmanı (`acquisition.py:238`, `pypdf`) ile dört alternatifin
ölçülmesi. Depoda PDF ayrıştırma için daha önce hiç değerlendirme yoktu — ne örnek
belge, ne benchmark. Bu çalışma o boşluğu dolduruyor.

Ölçülen motorlar: `pypdf` (mevcut), `pdf-inspector`, `opendataloader-pdf`,
`pymupdf4llm`, `MinerU`.

> **Hangi tabana göre ölçüldü:** `main` branch'i — `acquisition.py:238`,
> `PdfReader(io.BytesIO(...))`.
>
> `developments` branch'inde 2026-08-14 13:50'de (`a58874a`) PDF metin çıkarma
> `parsers/` paketine taşındı ve birincil yol **PyMuPDF** (`fitz.get_text("text",
> sort=True)`) oldu; pypdf yedeğe düştü. **O yapılandırma bu çalışmada ölçülmedi.**
> `developments` birleştirilirse taban değişir ve buradaki "mevcut sistem"
> karşılaştırmaları o yola göre yenilenmelidir.
>
> Not: PyMuPDF repoda yeni değil — 2026-07-30'dan beri (`835ec16`) bağımlılık ve
> `figure_analysis.py`'de şekil analizi için kullanılıyor. Yeni olan, **metin
> çıkarma** yolunda birincil hâle gelmesi.

---

## 🖥 Görsel arayüz

Bütün karşılaştırmalar tarayıcıda incelenebilir. Boyutu (140 MB) depo geçmişine
girmesin diye **Release eki** olarak duruyor:

**[→ pdf-parser-arayuz.zip indir](https://github.com/chnclsr/research-platform/releases/download/pdf-parser-arayuz-v1/pdf-parser-arayuz.zip)**

Zip'i açıp `html/index.html` dosyasına çift tıklayın. Sunucu, kurulum ve internet
gerekmiyor.

| sekme | ne var |
|---|---|
| **Belgeler** | Her sayfa için: gerçek PDF görüntüsü + 5 parser çıktısı yan yana |
| **Etiketli görünüm** | opendataloader'ın tanıdığı öğeler sayfa üzerinde kutulu |
| **Ölçümler** | 8 grafik — süre, ligatür, tireleme, başlık, kaynakça filtresi |
| **MinerU** | MinerU'ya özel inceleme + pipeline vs 1,2B VLM tablo karşılaştırması |

---

## En önemli bulgu: bölüm yolunda bölüm adı yok

`passages.py:_sections()` chunk'ların bölüm yolunu **Markdown başlıklarından**
türetiyor. `acquisition.py:239` PDF için `# Page 1`, `# Page 2`… üretiyor.

**Önce bir şeyi netleştirelim: `# Page N` bir kusur değil, kasıtlı.**
`passages.py:134` sayfa numarasını buradan çıkarıyor:

```python
page_number = int(m.group(1)) if (m := re.search(r"(?:^| > )Page (\d+)$", section_path)) else None
```

Yani alıntı konumu (`page_number`) bu başlığa bağlı. **Kaldırılmamalı.**

Sorun, `# Page N`'in **tek başına** olması — yanında bölüm adı yok. 8 belgede,
repodaki `chunk_document()` mantığı birebir uygulanarak ölçüldü:

| | pasaj | bölüm yolu sadece `Page N` / `Document` |
|---|---:|---:|
| **Mevcut (pypdf)** | 343 | **335 — %98** |
| **pdf-inspector çıktısıyla** | 398 | **0 — %0** |

İki sonucu var:

1. **Gömme vektörleri zayıflıyor** — `pipeline.py:1503` gömme girdisini
   `f"{section_path}\n{passage.text}"` diye kuruyor. Bugün her PDF pasajının
   vektörüne bilgi taşımayan bir `Page 7` öneki giriyor; `3 Model Architecture`
   girseydi anlamlı bağlam olurdu.
2. **Chunk sınırları sayfa sınırı oluyor** — bölüm bazlı değil. Bir bölüm 3 sayfaya
   yayılmışsa 3 parçaya bölünüyor, sayfa sonunda yarım kalan cümle ayrı chunk'a düşüyor.

**Öneri: `# Page N`'i koru, yanına gerçek başlığı ekle.** Regex `Page (\d+)$`
yolun **sonunu** aradığı için şu biçim hem sayfa numarasını korur hem bölüm adı verir:

```
3 Model Architecture > Page 5
```

Yani `# Page N` çıkarılmadan, parser gerçek başlıkları da üretirse ikisi birden olur.

---

## Ölçülmüş sonuçlar

### Doğruluk — 200 belge, üçüncü tarafın ground truth'u ve evaluator kodu

`opendataloader-bench` deposundan; kod değiştirilmedi.

| motor | overall | reading order | tables | headings |
|---|---:|---:|---:|---:|
| **pdf-inspector** | **0,876** | 0,915 | **0,814** | **0,788** |
| pymupdf4llm | 0,869 | 0,907 | 0,790 | 0,783 |
| opendataloader | 0,838 | 0,913 | 0,427 | 0,760 |
| **pypdf (mevcut)** | **0,576** | 0,870 | **0,000** | **0,000** |

Doğrulama: Firecrawl'ın yayınladığı `0,915 / 0,814 / 0,788` sayıları **birebir**
üretildi. Yani boru hattı doğrulanmış durumda.

⚠️ Bu 200 belgenin **hepsi tek sayfa** — çok sayfalı akademik makaledeki davranışı
söylemez. MinerU bu korpusta **henüz ölçülmedi** (en büyük kanıt boşluğu).

### Hız — 9 belge, 261 sayfa, makine boşken, 3 koşunun medyanı

| motor | toplam süre |
|---|---:|
| **pdf-inspector** | **1 sn** |
| pypdf (mevcut) | 5 sn |
| opendataloader | 13 sn |
| pymupdf4llm | 294 sn |
| MinerU (pipeline, CPU) | 1.395 sn |

**Süre oynaklığı kendi başına bir bulgu:** iki ayrı temiz koşu arasında
`pymupdf4llm` **3–4 kat** oynadı (attention 8,6 → 33,4 sn; resnet 38,0 → 11,8 sn),
MinerU ±%50; `opendataloader` %2–5, `pdf-inspector` kararlı. Öngörülemeyen süre,
`acquisition_stage_timeout_s = 900` bütçesinde gerçek bir risk.

### Metin kalitesi — 9 belge toplamı

| | pypdf | inspector | odl | p4llm | MinerU |
|---|---:|---:|---:|---:|---:|
| ligatür kalıntısı | 1.359 | **0** | 1.359 | 0 | **0** |
| bozuk kodlama | 0 | 0 | 0 | **207** | 0 |
| **satır içi tire** | 20 | **703** | 18 | 13 | 49 |

---

## `OPEN_ITEMS.md` ile bağlantı

### Madde 3 — "PDF tabloları yapısal değil"

Bu çalışma o maddeyi sayısallaştırıyor ve **çifte sayım** zorluğuna çözüm öneriyor.

**Ölçüm:** MinerU'nun tablo bulduğu 77 sayfanın **31'inde (%40)** `pdf-inspector`
hiç tablo yapısı üretmiyor — tablo **düz metne** dönüşüyor. Uzun belgelerde daha kötü:
gpt3'te 30 sayfanın 17'si, gpt4'te 16'nın 10'u.

**Asıl tehlike tablonun kaybolması değil, cümle kılığına girmesi.** Düzleşmiş tablo
metin akışına şöyle giriyor:

```
model top-1 err. top-5 err. VGG-16 [41] 28.07 9.33 GoogLeNet [44]-9.15 ...
```

Bu satır `chunk_document()` için normal bir cümleden ayırt edilemez; gömülür,
alıntılanır. Ajan buradan "GoogLeNet'in top-1 hatası 9.15" diyebilir — ve hiçbir
yerde uyarı çıkmaz.

**Öneri — tablo karantinası.** `pdf_inspector.process_pdf()` zaten aynı çağrıda
`pages_with_tables` döndürüyor (ek maliyet sıfır). Kural: sayfa tablo listesindeyse
ama çıktıda `|` satırı yoksa, o bölgeyi metin akışından **çıkar** ve yerine
`[TABLO — doğrulanmadı, s.6]` koy.

Bu, madde 3'te belirtilen **(b) çifte sayım** sorununu da çözüyor: bölge akıştan
çıktığı için aynı rakam iki kez geçmiyor.

### Madde 9 — "`_direct` 400 karakter eşiği"

Aynı eşiğin **ikinci bir etkisi** ölçüldü: **taranmış PDF'ler sessizce düşüyor.**

`taranmis_bert_2sutun_dipnot.pdf` (metin katmanı yok):

| motor | çıkarılan karakter |
|---|---:|
| pypdf (mevcut) | 70 → **eşiğin altında, belge atılıyor** |
| pdf-inspector | 0 |
| opendataloader | 12 |
| pymupdf4llm | 10 |
| **MinerU (pipeline, CPU)** | **24.554** |

MinerU, ölçülen beş motor arasında **OCR'ı olan tek motor** — ve bunu GPU'suz yapıyor.

---

## Öneri

| katman | motor | gerekçe |
|---|---|---|
| Gövde metni + başlıklar | **pdf-inspector** | 5× hızlı, `section_path` %98 → %0, MIT, sıfır bağımlılık, 6,4 MB |
| Tablo karantinası | (kural) | `pages_with_tables` + `\|` yokluğu → işaretle, akıştan çıkar |
| Taranmış belge + şüpheli tablo | **MinerU**, `arq` worker'da | canlı bütçeye girmez; `raw_content` DB'de olduğu için yeniden indirme yok |

**MinerU'yu `acquisition.py`'ye koymamak gerekiyor:** 7,66 sn/sayfa ve `ACQUIRE`
900 saniyelik bütçe altında `asyncio.as_completed(timeout=...)` ile kesiliyor —
kaynak kaybettirir.

---

## Bilinen sınırlar

- 9 belgelik korpusun **gerçek ground truth'u yok**. 6'sı için arXiv HTML'i vekil
  referans olarak kullanıldı; 3'ünde (sybil, turkce, taranmis) hiç referans yok.
  Bu korpustan üretilen skorlar "kesin doğruluk" değil, **ayrışma ölçüsü**.
- Tablo hücre değerleri **elle sadece 3 tabloda** doğrulandı (resnet s.6). "%40 düz
  metne dönüyor" oranı tablo **tespitine** dayanıyor, hücre doğruluğuna değil.
- MinerU 200 belgelik bench'te ölçülmedi → gerçek ground truth'a karşı doğruluk
  skoru **yok**.
- MinerU'nun ölçülen modu `pipeline` (CPU). Bu, MinerU'nun **tavanı değil tabanı**
  (OmniDocBench v1.6: pipeline 86,47 vs vlm/hybrid 95,26–95,69). Tek sayfada
  (resnet s.6) `hybrid-engine` CPU'da zorlandı: pipeline 3 tabloda satır kaydırırken
  VLM 26 hücrenin 26'sını doğru çıkardı.

---

## Tekrar üretmek

```bash
python scripts/compare.py           # 5 parser × 9 belge, 3 koşu medyanı → sonuclar.csv
python scripts/mineru_kos.py        # MinerU (ayrı .venv gerekir)
python scripts/mineru_csv_ekle.py   # MinerU'yu aynı measure() hattından geçirip CSV'ye ekle
python scripts/grafik_uret.py       # → html/olcumler.html
python scripts/html_uret.py         # → html/index.html + belge sayfaları
python scripts/mineru_html.py       # → html/mineru.html
python scripts/resmi_benchmark.py   # 200 belgelik bench (ayrı depo klonu gerekir)
```

Korpus ve taşınabilir JRE bu depoda değil — kurulumu `scripts/fetch_corpus.py`
ve `BULGULAR.md` içinde anlatılıyor.

## Sayfa yönlendirmeli parser RC1

<!-- CODEX-2026-08-18: A/B production entegrasyonu ve C calibration araçlarının
GitHub'daki tek giriş noktası. -->

İlk araştırmadan sonra production parser `src/research_platform/parsers/`
altında sayfa yönlendirmeli hale getirildi. Güncel uçtan uca sonuç ve dürüst
sınırlamalar `../../previous_reports/PDF_PARSER_V0.1.0_RC1_REPORT.md` dosyasındadır.

C araçları `scripts/c1_*.py`, `scripts/c2_kalibrasyon.py` ve
`scripts/korpus_*.py`; küçük ölçüm kanıtları `results/c1_rc1/` altındadır.
Ham corpus ve çalışma çıktıları Git'e girmez.

## Sayfa sayfa inceleme arayüzü

`scripts/hata_arayuzu.py` 9 belgelik korpusun 261 sayfasını tek HTML'de gözle
incelenebilir hâle getirir: sayfanın kendi görüntüsü üzerinde referans tablo/şekil
kutuları, kapının ne dediği, TP/FP/FN hükmü, yönlendirme kararı ve fast/heavy/seçilen
metinler yan yana. Üretilen HTML ve sayfa görüntüleri (~37 MB) Git'e girmez;
korpustan yeniden üretilir.

```powershell
python research\pdf-parser\scripts\hata_arayuzu.py   # -> research/pdf-parser/html/
```

## GPU ölçümleri

`scripts/gpu_docling_olc.py` Docling'in hızını, determinizmini ve CPU/GPU çıktı
eşdeğerliğini ölçer; `scripts/gpu_sekil_aciklama.py` `do_picture_description`
VLM'ini ölçer. Kanıtlar ve yorumu `results/gpu/README.md` içinde, kararlar
`previous_reports/PDF_PARSER_V0.1.0_RC1_REPORT.md` bölüm E/F/G'de.

Özet: GPU 3,06× hızlandırıyor · determinizm geçti · **eşdeğerlik geçmedi**
(261 sayfanın 7'si CPU'dan farklı, biri gerçek içerik kaybı) · şekil açıklaması
SmolVLM-256M ile **uyduruyor**, açılmadı.

9 belgelik korpusun PDF'leri depoda değil: `corpus/kendi/` altına konur ya da
`KENDI_KORPUS` ile yeri gösterilir.

Varsayılan corpus konumları:

- OCRTurk/DocLayNet/OmniDocBench: repo kökünde `corpus/raw`, gerekirse
  `KORPUS_RAW` ile değiştirilebilir.
- OpenDataLoader benchmark: `research/pdf-parser/corpus/opendataloader-bench`,
  gerekirse `OPENDATALOADER_BENCH` ile değiştirilebilir.

## Dosyalar

| dosya | içerik |
|---|---|
| `BULGULAR.md` | Belge belge ayrıntılı bulgular (53 KB) |
| `OLCUMLER.md` | Ölçüm yöntemi notları |
| `results/sonuclar.csv` | Ham ölçümler — 5 parser × 9 belge |
| `results/referans_skorlar.csv` | arXiv referansına göre skorlar |
| `results/resmi_benchmark_sonuc.json` | 200 belgelik bench sonucu |
| `scripts/` | Bütün ölçüm ve arayüz üretim scriptleri |
