# DOCX raporuna yazılacaklar — GPU koşusu (2026-08-24)

Bu dosya **Codex için toplama listesidir.** DOCX'e hiçbir şey yazılmadı; aşağıdaki
maddeler yazılacak olanlardır. Her maddenin yanında hangi dosyanın hangi alanından
geldiği var — DOCX'e girecek her sayı bu kaynaklardan doğrulanabilir.

Kaynak bölüm: canonical rapor `previous_reports/PDF_PARSER_V0.1.0_RC1_REPORT.md`
**Bölüm P**. Ham kanıt: `research/pdf-parser/results/gpu_c1/`.

---

## 1. DÜZELTİLMESİ gereken mevcut ifadeler

| DOCX'te bugün ne yazıyor | Ne olmalı | Kaynak |
|---|---|---|
| Ağır motor kapıdan **~300×** pahalı | CPU'da 203–285×, **GPU'da 60–103×**. "300×" yalnız GPU'suz makine için geçerliydi. | `RAPOR_GPU.md` §2.3 |
| GPU hızlanması **3,06×** (tek sayı) | **2,78×–3,40× aralığı.** Aynı ölçüm iki kez koşuldu, tekrarlanmadı (CPU koşuları arası 1,40×, GPU 1,72×). | `hiz_kararliligi.json` |
| Aynı PDF CPU ve CUDA'da **farklı metin** veriyor (9 belgenin 4'ü) | Bu **bir makinede** gözlendi (RTX 4060 + docling 2.120.3), **ikinci makinede tekrarlanmadı** (Quadro RTX 4000 + docling 2.120.1, 261 sayfa + 65 belge, 0 fark). Atıf **çözülmedi** — GPU mimarisi mi docling sürümü mü ayrılamadı. | `esdegerlik_farklari.md`, `cache_esdegerlik.json` |
| GPU çıkarımı determinizmi bozabilir | Bu yığında **bozmuyor**: 6 ve 75 sayfalık belgede 3'er koşu bayt bayt aynı. Genel garanti değil, bu yığın için ölçüm. | `*_determinizm_*.json` |
| C1 örneklemi **201 belge**, precision 0,4713 | **380 belge**, precision **0,4000**. 201'lik örneklem isabeti olduğundan iyi gösteriyormuş. | `summary_gpu_tam_380.json` |
| `opendataloader_bench` NET −0,68 (72 belge) | **−1,5734** (200 belgenin tamamı). Zarar iki katına çıktı. | `gpu_tam_380/predictions.jsonl` |

## 2. YENİ eklenecek bölüm — "GPU'da uçtan uca doğrulama"

**Ortam (künye olarak yazılmalı):** Quadro RTX 4000 8 GB, sürücü 595.84, sm_75 ·
Intel Xeon W-2145 (8c/16t), 125 GB RAM · Ubuntu 22.04.5 · torch 2.6.0+cu124 ·
**docling 2.120.1** · depo `485a4b5` ·
`metric_fingerprint = c1_metrics_v1_2026-08-18+rapidfuzz`.

> Dikkat: nvidia-smi "CUDA 13.2" diyor (sürücü seviyesi), torch cu124 ile
> derlenmiş. DOCX'te ikisi karıştırılmamalı.

**Dört sorunun cevabı — tek tablo hâlinde:**

| soru | cevap |
|---|---|
| Hız / maliyet oranı | Oran düştü (60–103×) ama **sayfa seçmek hâlâ haklı**: "hepsi ağır" GPU'da bile toplamı 2,22× artırırdı |
| Determinizm | **Bozulmuyor** — 6 ve 75 sayfalık belgede 3'er koşu bayt bayt aynı |
| Cihaz eşdeğerliği | **Fark yok** (261 sayfa + 65 belge, tablo yapıları dahil) |
| C1 faydası | Aynı 201 belgede **hiçbir metrik değişmedi**; 380'in tamamında tablo değişti |

**Kapanan kanıt boşluğu (öne çıkarılmalı):** CPU'da C1 korpusunun 380 belgesinden
201'i işlenebiliyordu (179 "Docling cache yok" hatası — belgeler sağlamdı, CPU
yetişmemişti). GPU'da **380/380, 0 hata**.

**Veri ailesi tablosu (birleşik sayı tek başına yazılmamalı):**

| metrik | ocrturk (180) | opendataloader_bench (200) | birleşik (380) |
|---|---:|---:|---:|
| ağır yönlendirilen | 85 | 75 | 160 |
| route precision@0,02 | 0,5529 | **0,2267** | 0,4000 |
| route recall@0,02 | 0,6620 | 0,6296 | 0,6531 |
| NET = Σ(routed − fast) | **+5,6284** | **−1,5734** | +4,0550 |
| karantina red | 3 | 0 | 3 |

**Cümle olarak yazılacak asıl bulgu:** `opendataloader_bench` ailesinde ağır
çağrıların **%77,3'ü boşa** gidiyor ve `mean_utility.routed` (0,8799)
`mean_utility.fast`'in (0,8877) **altında** — yani o ailede yönlendirme çıktıyı
kötüleştiriyor. Bu, raporun "İngilizcede mevcut route kararı zarar veriyor"
hükmünün 72 değil **200 belgeye** dayanan hâlidir.

## 3. Metodoloji kutusu (yazılırsa raporun savunulabilirliğini artırır)

- **CPU tabanı aynı makinede alındı.** Başka makinenin CPU'suyla kıyaslamak
  işlemci ve GPU farkını karıştırırdı; önceki koşuda bu yapılmasaydı GPU'ya
  6,83× yazılacaktı, gerçek katkı 3,06×'tı.
- **Cihaz varsayılmadı, ölçüldü.** `c1_docling_cache.py` payload'una `"device"`
  alanı eklendi (`decide_device(AUTO)` sonucu). Cache dosyaları yalnız
  `pdf_sha256` ile adlandırılıyor — cihaz anahtarda yok, provenance başka yerde
  duramazdı.
- **Ölçülemeyen yere 0 yazılmadı.** Adım 6 (kendi korpusun tablo/şekil hükümleri)
  koşulmadı çünkü referans dosyaları yok ve kod eksik dosyada **hata vermeden**
  boş kümeye düşüyor — sayı yanlış değil, **hiç var olmayan** sayı olurdu.
- **`config/smart_router.yaml` ellenmedi**, `esik_version` değişmedi; koşunun tek
  değişkeni cihazdı.

## 4. DOCX'e girmemesi gerekenler

- **Birleşik tek sayı, aile kırılımı olmadan.** İki aile ters yönde davranıyor.
- **"Yakalanan fayda oranı"** (`max(delta,0)`) — asimetrik, gereksiz ağır
  çağrının zararını saymıyor; `opendataloader` rejiminde baskın olan tam da o.
- **Tek bir hızlanma katsayısı.** Ölçüm tekrarlanmadı; aralık verilmeli.
- **"GPU'da cihaz farkı yoktur" genellemesi.** Bir makinede fark vardı, birinde
  yoktu; atıf çözülmedi.

## 5. Görsel/ek olarak konabilecekler

- `html/gpu_panosu.html` — tek sayfa, "Yazdır / PDF kaydet" düğmesiyle doğrudan
  A4'e basılıyor; DOCX'e ek olarak konabilir.
- `html/c1_arayuz_gpu380.html` — 380 belge belge belge, ekran görüntüsü alınabilir.
- `telemetri.jsonl` → GPU sıcaklık/saat grafiği (kısılma kanıtı, 91 °C,
  SM 2100 → 1005 MHz).
