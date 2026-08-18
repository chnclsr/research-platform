# Smart Router Architecture (14 Boyutlu Enterprise Versiyon)

Bu doküman, PDF dosyalarının işlenmesi sırasında otonom kararlar alarak belgeleri en uygun parser'a (**`pdf-inspector`**, **`docling`** veya **`miner-VL`**) yönlendiren 14 boyutlu açık kaynak standardındaki hibrit mimariyi açıklar.

---

## 1. Genel Bakış ve Sistem Akışı (Workflow Diagram)

Mimarinin merkezinde **Router** (`router.py`) yer alır. Ajanlar (Agent), RAG sistemleri veya arka plan servisleri doğrudan Router'ı çağırır.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     LLM AGENT / PIPELINE                                    │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │
                                               │ 1. route_document(pdf_path)
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PDF ROUTER (router.py)                                    │
│   [Aşama 1: 17 Yapısal Geometri ve Tipografi Analizi]                                       │
│    • Font & CID Oranları    • Vektör Çizimleri       • Bounding Box Çakışması               │
│    • Görüntü Yoğunluğu      • Sayfa Sayısı           • Scanned / OCR Proxy                  │
└───────────────────────┬──────────────────────────────────────────────▲──────────────────────┘
                        │                                              │
                        │ 2. extract_text(pdf_path)                    │ 3. inspector_text
                        ▼                                              │ (Ham Metin)
┌──────────────────────────────────────────────┐                       │
│         PDF INSPECTOR (inspector.py)         │───────────────────────┘
│   [Varsayılan Hızlı Metin Çıkarıcı Motor]    │
└──────────────────────────────────────────────┘
                        │
                        │ 4. evaluate(router_json, inspector_text)
                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PDF CRITIC (critic.py)                                    │
│   [Aşama 2: 14 Boyutlu Açık Kaynak Kalite ve Anomali Denetimi]                              │
│    1. Char Drop Gap          6. 2-Sütun Dangling Cuts       11. Repetition Loops            │
│    2. Scanned Proxy          7. Broken Line Ratio           12. LaTeX Delimiter Balance     │
│    3. Vector Table Drop      8. Hyphenation Artifacts       13. Markdown Table Integrity    │
│    4. Gibberish Ratio        9. Orphan Footnotes            14. Heading Hierarchy Tree      │
│    5. Unicode Noise         10. Header/Footer Bleed                                         │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │
                                               │ 5. Decision Result JSON
                                               ▼
                            ┌──────────────────────────────────────┐
                            │      NİHAİ PARSER YÖNLENDİRMESİ      │
                            └──────────────────┬───────────────────┘
                                               │
               ┌───────────────────────────────┼───────────────────────────────┐
               ▼                               ▼                               ▼
┌──────────────────────────────┐┌──────────────────────────────┐┌──────────────────────────────┐
│        pdf-inspector         ││           docling            ││           miner-VL           │
│          [DEFAULT]           ││          [FALLBACK]          ││          [FALLBACK]          │
│  Kalite >= 75.0 &            ││  Sütun atlaması,             ││  Taranmış evrak (OCR),       │
│  Metin akışı sorunsuz        ││  Tablo parçalanması,         ││  Ağır matematik formülleri,  │
│  (Hızlı Yol Korundu)         ││  Akış bozulması              ││  Karmaşık IEEE şablonları    │
└──────────────────────────────┘└──────────────────────────────┘└──────────────────────────────┘
```

---

## 2. UML Sınıf Diyagramı (Class Diagram)

Sistemdeki sınıflar, metod imzaları ve veri yapıları arasındaki ilişkiler:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          PDFRouter                                          │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ - feature_weights: dict                                                                     │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ + extract_features(pdf_path: str) -> dict                                                   │
│ + compute_total_score(features: dict) -> tuple                                              │
│ + normalize(val: float, min_val: float, max_val: float) -> float                            │
│ + route_document(pdf_path: str) -> dict  <══════════════════════════ [ANA GİRİŞ NOKTASI]    │
└──────────────────────┬───────────────────────────────────────────────┬──────────────────────┘
                       │                                               │
                       │ queries                                       │ delegates evaluation
                       ▼                                               ▼
┌──────────────────────────────────────────────┐┌─────────────────────────────────────────────┐
│               PDFInspectorMock               ││                  PDFCritic                  │
├──────────────────────────────────────────────┤├─────────────────────────────────────────────┤
│                                              ││ - fallback_threshold: float = 75.0          │
├──────────────────────────────────────────────┤│ - SENTENCE_END_PUNCT: tuple                 │
│ + extract_text(pdf_path: str)$ -> str        ││ - HEADER_PREFIXES: tuple                    │
└──────────────────────────────────────────────┘├─────────────────────────────────────────────┤
                                                │ + evaluate(router_json, insp_text) -> dict  │
                                                └──────────────────────┬──────────────────────┘
                                                                       │
                                                                       │ creates & returns
                                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       DecisionResult                                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ + pdf_path: str                                                                             │
│ + target_parser: str                   ("pdf-inspector" | "docling" | "miner-VL")           │
│ + fallback_triggered: bool             (True | False)                                       │
│ + quality_score: float                 (0.0 - 100.0)                                        │
│ + structural_score: float              (17 Metrik Puanı)                                    │
│ + critical_issue: str                  ("NONE" | "SCANNED_NEEDS_OCR" | "TWO_COLUMN_...")    │
│ + reason: str                          (Kararın açık gerekçesi)                             │
│ + detailed_metrics: DetailedMetrics    (14 Metriğin alt kırılımları)                        │
│ + elapsed_ms: float                    (İşlem süresi ~ms)                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 14 Boyutlu Critic Kalite ve Anomali Boyutları

Açık kaynak standartları (**Docling**, **Marker**, **MinerU**, **Nougat**, **DocLayNet**) entegre edilerek geliştirilen 14 analiz boyutu:

### [A. Metin Kayıp & Atlamalar]
1. **Char/Word Density Gap:** Ham PDF karakter sayısı ile çıkarılan metin arasındaki kayıp oranı.
2. **Scanned / OCR Proxy:** Sayfa alanı görsel oranı > %80 ve karakter sayısı < 50 olan sayfaları tespit eder (OCR ihtiyacı).
3. **Vector Drawing Drop:** Yoğun çizim ve tablo çizgilerinin metin sanılıp yutulması durumu.

### [B. Font & Kodlama Bozulmaları]
4. **CID Font / Gibberish Ratio:** Identity-H veya CMap eksikliğinde oluşan anlamsız glif ve bozuk karakter oranı.
5. **Unicode & Control Noise *(Marker)*:** `\ufffd` (replacement char), `\u200b` (zero-width space), `\x00-\x1f` kontrol karakteri sızıntıları.

### [C. Dilbilgisi & Okuma Sırası]
6. **Two-Column Dangling Cuts:** Cümle ortasında beklenmedik büyük harfle sonraki sütuna veya görsele zıplama oranı.
7. **Broken Lines:** Aynı paragraf içinde olması gereken satırların kopması.
8. **Hyphenation Artifacts:** Satır sonundaki asılı tireleme bozulmaları (`transfor- \n mer`).
9. **Orphan Footnotes & Numbers:** Metin akışının içine düşen izole sayfa numaraları ve dipnotlar.
10. **Running Header/Footer Leakage *(Docling)*:** Sayfa üst/alt bilgi satırlarının gövde metnine her sayfada tekrarlayarak karışması.
11. **Repetition Loops & Degeneration *(Nougat)*:** Kötü layout ayrıştırmasında oluşan 4-gram tekrar döngüleri.

### [D. Formül & Tablo & Hiyerarşi Bütünlüğü]
12. **LaTeX & Math Delimiter Balance *(MinerU)*:** Açık kalan veya eşleşmeyen `$`, `$$`, `\begin{equation}` parantezleri.
13. **Markdown Table Structural Integrity *(Docling-eval)*:** Satır başına düşen sütun (`|`) sayısındaki tutarsızlıklar ve kırık tablolar.
14. **Heading Hierarchy Coherence *(DocLayNet)*:** Başlık seviyelerinin (`#` -> `####`) mantıksız atlama ve derinlik sapması.

---

## 4. Fallback (Geri Dönüş) Kuralları

- **`pdf-inspector` [DEFAULT]:** 14 Metrik Kalite Skoru $\ge 75.0$ ve hiçbir kritik atlama yoksa en hızlı yol korunur.
- **`docling` [FALLBACK]:** Sütun atlaması, tablo parçalanması, akış kırılması veya running header sızıntısında devreye girer.
- **`miner-VL` [FALLBACK]:** Taranmış (scanned) belgeler, aşırı yoğun matematik/formül (`MATH_FORMULA_HEAVY`) veya yapısal karmaşıklığı 150'nin üzerindeki IEEE konferans şablonlarında devreye girer.

---

## 5. Kullanım Örneği

```python
from smart_router.router import PDFRouter

router = PDFRouter()
decision = router.route_document("ornek_makale.pdf")

print("Seçilen Parser :", decision["target_parser"])
print("Fallback Durumu:", decision["fallback_triggered"])
print("14-M Kalite    :", decision["quality_score"])
print("Gerekçe        :", decision["reason"])
```

*(Not: İnteraktif HTML versiyonu için: [`smart_router/docs/architecture_diagram.html`](architecture_diagram.html))*
