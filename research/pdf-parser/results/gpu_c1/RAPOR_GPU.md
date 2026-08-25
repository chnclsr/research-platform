# GPU koşusu — bulgular

**Makine:** Quadro RTX 4000 (8 GB, sürücü 595.84, CUDA 13.2) · Intel Xeon W-2145
(8c/16t) · 125 GB RAM · Ubuntu 22.04.5 · torch 2.6.0+cu124 · docling **2.120.1**
(istenen sürüm) · Python 3.11.16 (metrik) / 3.10.12 (ağır motor)
· depo commit `485a4b5`
· `metric_fingerprint = c1_metrics_v1_2026-08-18+rapidfuzz`

Her iddianın altında hangi dosyanın hangi alanından geldiği yazılıdır.
Ölçülemeyen hiçbir yere 0 yazılmadı; "ölçülemedi" denildi.

---

## Tek ekranlık cevap

| soru | ölçülmüş cevap |
|---|---|
| **1. Hız / maliyet oranı** | Oran **düştü ama sayfa seçmeyi hâlâ haklı çıkarıyor.** Kapı 8,65 ms/sayfa; Docling CPU'da 203–285×, **GPU'da 60–103×** pahalı. "Her sayfayı ağıra yolla" politikası GPU'da bile toplam süreyi **2,22×** artırırdı. |
| **2. Determinizm** | **Bozulmuyor.** GPU'da 3 koşu, hem 6 sayfalık hem 75 sayfalık belgede **bayt bayt aynı**. `content_hash` sözleşmesi bu makinede GPU'da tutuyor. |
| **3. Cihaz eşdeğerliği** | **Fark YOK.** 261 sayfa + 65 belge, sayfa metni ve tablo yapıları dahil, CPU ile CUDA'da birebir aynı. Önceki RTX 4060'lı makinenin 7 sayfalık farkı **tekrarlanmadı**. |
| **4. C1 faydası GPU'da ayakta mı** | **Aynı 201 belgede hiçbir metrik değişmedi** (precision 0,4713 → 0,4713; route kararı 0 değişiklik). Ama **380'in tamamı koşulduğunda tablo değişiyor**: precision 0,4713 → **0,4000** ve `opendataloader_bench`'te NET **negatif** (−1,57). |

**Bu koşunun en değerli çıktısı:** CPU'da kapanamayan kanıt boşluğu kapandı —
380 belgenin **tamamı** işlendi, **0 hata** (CPU'da 380'in 201'i, 179 hata).

---

## 1. Kabul kontrolleri

| kontrol | sonuç | kaynak |
|---|---|---|
| Envanter sha256 | **GEÇTİ** — 380/380 kayıt eşleşti, farklı sha256: 0; kendi korpus 9 PDF | `out/gpu/envanter_karsilastirma.json → gecti` |
| `metric_fingerprint` eşitliği | **GEÇTİ** — üç koşu + CPU tabanı hepsi `c1_metrics_v1_2026-08-18+rapidfuzz` | `out/c1_runs/*/summary.json → metric_fingerprint` |
| `mean_utility.fast` — CPU tabanı ↔ GPU aynı 201 | **GEÇTİ** — 201 ortak belgenin **0**'ında fark | `predictions.jsonl → scores.fast.utility` |
| `mean_utility.fast` — bu makine CPU 60 ↔ GPU | **GEÇTİ** — 60 ortak belgenin **0**'ında fark | aynı |
| Determinizm — küçük belge (turkce_makale, 6 s.) | **GEÇTİ** — 3/3 bayt bayt aynı | `out/gpu/..._determinizm_turkce.json → determinizm.hepsi_ayni` |
| Determinizm — büyük belge (gpt3, 75 s.) | **GEÇTİ** — 3/3 bayt bayt aynı | `out/gpu/..._determinizm_gpt3.json` |
| Cihaz eşdeğerliği — 9 belge / 261 sayfa | **GEÇTİ** — 0 sayfada fark | `out/gpu_docling_cuda.json → esdegerlik` |
| Cihaz eşdeğerliği — C1 cache, 60 belge | **GEÇTİ** — sayfa metni 0, tablo yapısı 0 fark | `out/gpu/cache_esdegerlik.json → gecti` |
| **Donanım kısılması** | **GEÇMEDİ** — 153 örneğin 16'sında kısılma (termal + güç), en yüksek 91 °C | `loglar/telemetri.jsonl → clocks_throttle_reasons.active` |

> `mean_utility.fast` rozetinin **ortalamaları değil belge belge** karşılaştırdığına
> dikkat: üç koşu farklı belge kümeleri (380 / 201 / 60) üzerinde, ortalamalarının
> farklı çıkması beklenir ve cihazla ilgisi yoktur.

---

## 2. Soru 1 — Hız ve maliyet oranı

### 2.1 Ham hız (9 belge, 261 sayfa)

| ölçüm | CPU ms/sayfa | GPU ms/sayfa | hızlanma |
|---|---|---|---|
| 1. ölçüm | 1757,0 | 516,4 | **3,40×** |
| 2. ölçüm | 2464,0 | 887,4 | **2,78×** |

`kaynak: out/gpu_docling_cpu.json, out/gpu/gpu_docling_cuda.json,
out/gpu/tekrar/*.json → ortalama_ms_sayfa`

**Hızlanma tek bir sayı değil, 2,78×–3,40× aralığıdır.** Aynı ölçüm iki kez
koşuldu ve CPU koşuları arası oran 1,40×, GPU koşuları arası oran 1,72× çıktı.
Kısılma kaydedildi (SW Thermal Slowdown, SM saati 2100 → 1005 MHz, 91 °C),
CPU tarafında PROCHOT sayacı 0, rakip süreç yok (>%92 boşta), governor
(`powersave`/`intel_pstate`) ve EPP (`balance_performance`) değişmedi.
**Sebep doğrulanmadı.** Hipotez (kanıt değil): 1. ölçüm ~45 dakikalık sürekli
GPU yükünden önce, 2. ölçüm sonra koştu; sıcak kasada turbo binleri PROCHOT
bayrağı kaldırmadan düşer. `kaynak: out/gpu/hiz_kararliligi.json`

### 2.2 C1 korpusunda belge başına (380 tek sayfalık belge)

| cihaz | belge | ortalama | medyan | payload `device` |
|---|---|---|---|---|
| CUDA | 380 | **987,5 ms** | 830,5 ms | `cuda:0` (380/380) |
| CPU | 60 | **4005,0 ms** | 2814,0 ms | `cpu` (60/60) |

`kaynak: out/c1_docling_cache_{cuda,cpu}/*.json → duration_ms, device`

Cihaz **varsayılmadı, payload'dan okundu** — Adım 2'de eklenen alan tam da bunun
için. `CUDA_VISIBLE_DEVICES=""` ile koşulan cache gerçekten `cpu` yazıyor.

### 2.3 Maliyet oranı — mimarinin gerekçesi

| hat | ms/sayfa | oran = ağır / kapı |
|---|---|---|
| kapı (inspector 2,14 + gate 5,75 + critic 0,69) | **8,65** | 1× |
| Docling CPU (bu makine) | 1757 – 2464 | **203× – 285×** |
| Docling CUDA (bu makine) | 516 – 887 | **60× – 103×** |

`kaynak: out/hata_arayuzu_veri.json → toplam_ms / sayfa_sayisi;
out/gpu_docling_*.json → ortalama_ms_sayfa`

**Oran GPU'da 3–4 kat küçüldü.** Promptun dayandığı "~300×" varsayımı GPU'da
geçerli değil; oran 60–103× bandına indi.

**"Hepsi ağır" senaryosu — hesaplandı, tahmin edilmedi.** Bugün 261 sayfanın
115'i (%44,1) ağır hatta gidiyor. Ağır hattı %100'e çıkarmak:

| cihaz | bugün ms/sayfa | hepsi ağır ms/sayfa | maliyet artışı |
|---|---|---|---|
| CPU | 782,8 | 1765,7 | **2,26×** |
| GPU | 236,2 | 525,1 | **2,22×** |

`kaynak: out/hata_arayuzu_veri.json → agir_sayfa, sayfa_sayisi`

> **Tek cümlelik yorum:** Evet, GPU'da bile sayfa seçmek haklı — her sayfayı ağır
> motora yollamak toplam süreyi 2,22× artırırdı. Ama gerekçe zayıfladı: karar
> "300 kat pahalı" değil, "60–103 kat pahalı ve toplamda 2,2 kat" üzerinden
> savunulmalı.

---

## 3. Soru 2 — Determinizm

| belge | sayfa | koşu | sonuç | çıktı sha256 |
|---|---|---|---|---|
| turkce_makale | 6 | 3 | **bayt bayt aynı** | `0f51d4ac4b1441fc740b96524827d1c350f81fe794efd99bf8d8561ec3c0d66d` |
| gpt3_uzun_75sayfa | 75 | 3 | **bayt bayt aynı** | `53d45db19a56c7ffee1864a210b121748a2709ec2915b75447bc8046ba26461b` |

`kaynak: out/gpu/gpu_docling_cuda_determinizm_{turkce,gpt3}.json → determinizm`

Uzun belge testi kasten koşuldu: 75 sayfada GPU'nun kayan nokta toplama sırası
6 sayfalıktan çok daha fazla yer bulur. İkisi de geçti.

Ek gözlem: `turkce_makale` hash'i **önceki makinenin** (RTX 4060, docling
2.120.3) hash'iyle birebir aynı. `kaynak: taban_cpu/onceki_makine_determinizm.json`

**Sonuç:** `registry.py`'nin "aynı baytlar her koşuda aynı çıktıyı vermeli"
sözleşmesi ve `content_hash = sha256(metin)` bu makinede GPU'da **bozulmuyor.**
Bu, "GPU çıkarımı çoğunlukla bit düzeyinde tekrarlanabilir değildir" beklentisinin
bu yığın için (Docling 2.120.1 + torch 2.6.0+cu124 + Turing/sm_75) tutmadığını
gösterir. Başka bir sürüm/mimaride tekrar ölçülmelidir.

---

## 4. Soru 3 — Cihaz eşdeğerliği

Üç bağımsız test, hepsi **aynı makinede** CPU ve CUDA:

| test | kapsam | karşılaştırılan | fark |
|---|---|---|---|
| Adım 3 | 9 belge / 261 sayfa | `export_to_markdown()` sayfa metni | **0** |
| C1 cache | 60 belge | sayfa metni **+ tablo yapıları** | **0 / 0** |
| Atıf | 5 belge | sayfa metni + tablo yapıları | **0 / 0** |

`kaynak: out/gpu_docling_cuda.json → esdegerlik; out/gpu/cache_esdegerlik.json;
out/gpu/atif_5belge.json`

İkinci test kasten farklı bir şey soruyor: markdown'ın aynı çıkması tablo
**yapısının** da aynı çıktığını kanıtlamaz; `_table_grid` ayrı bir çıktı yolu.
İkisi de aynı.

**Önceki makinenin bulgusu tekrarlanmadı.** Orada (RTX 4060, docling 2.120.3)
261 sayfanın 7'si farklıydı ve `gpt3` s.50'de bir markdown tablosu kaybolmuştu.
Bu makinede (Quadro RTX 4000, docling **2.120.1**) hiçbir sayfada fark yok.
İki değişken birden farklı olduğu için (GPU mimarisi **ve** docling sürümü)
hangisinin sorumlu olduğu bu koşuyla **ayrılamaz**.

### 4.1 Fark cihazdan mı, makineden mi — ayrıldı

Gönderilen CPU tabanı ile bu makinenin GPU koşusu arasında, aynı 201 belgede
**5 belgede** heavy utility farkı çıktı (hepsi `ocrturk`):

| belge | Δ heavy utility |
|---|---|
| data_53 | −0,143506 |
| data_135 | +0,026515 |
| data_52 | +0,015388 |
| data_175 | −0,004866 |
| data_59 | +0,000459 |

Bu 5 belge bu makinede CPU ve CUDA ile yeniden üretildi: **beşinde de sayfa metni
ve tablo yapısı birebir aynı.** `kaynak: out/gpu/atif_5belge.json → cihazdan_kaynakli_fark = false`

> **Sonuç:** Ağır motorun metni **makineden makineye** değişiyor, ama **aynı
> makinede cihazdan cihaza değişmiyor.** `EngineResult.device` yorumundaki
> "iki worker farklı hızlandırıcıda birbirinin yerine geçmez" uyarısı bu makinede
> doğrulanmadı; asıl değişken cihaz değil, makinenin kendisi görünüyor.

---

## 5. Soru 4 — C1 faydası GPU'da

### 5.1 Elmayla elma: aynı 201 belge

| metrik | CPU tabanı | GPU aynı 201 | fark |
|---|---|---|---|
| routed_heavy | 87 | 87 | **0** |
| heavy_gain ≥ 0,02 | 63 | 63 | **0** |
| route_precision@0,02 | 0,4713 | 0,4713 | **0** |
| route_recall@0,02 | 0,6508 | 0,6508 | **0** |
| mean_utility.fast | 0,835381 | 0,835381 | **0** |
| mean_utility.heavy | 0,849617 | 0,849089 | −0,000528 |
| mean_utility.routed | 0,852394 | 0,852504 | +0,000110 |
| NET = Σ(routed−fast) | 3,4198 | 3,4419 | +0,0221 |
| karantina red | 1 | 1 | 0 |

**Route kararı değişen belge: 0. Fast utility farklı belge: 0.**
Yönlendirme kararı cihazla değişmedi — beklendiği gibi, kapı sinyalleri
pdf-inspector ve PyMuPDF'ten geliyor, ikisi de GPU kullanmıyor.

`kaynak: taban_cpu/predictions.jsonl ve out/c1_runs/gpu_ayni201/predictions.jsonl`

### 5.2 Kapanan kanıt boşluğu: 380'in tamamı

Veri ailesi bazında ayrı ayrı **ve** birleşik:

| metrik | ocrturk | opendataloader_bench | **birleşik** |
|---|---|---|---|
| documents / ok / errors | 180 / 180 / 0 | 200 / 200 / 0 | 380 / 380 / 0 |
| routed_heavy | 85 | 75 | 160 |
| heavy_gain ≥ 0,02 | 71 | 27 | 98 |
| route_precision@0,02 | 0,5529 | **0,2267** | 0,4000 |
| route_recall@0,02 | 0,6620 | 0,6296 | 0,6531 |
| mean_utility.fast | 0,8028 | 0,8877 | 0,8475 |
| mean_utility.heavy | 0,8330 | 0,8675 | 0,8512 |
| mean_utility.routed | 0,8340 | 0,8799 | 0,8582 |
| **NET = Σ(routed − fast)** | **+5,6284** | **−1,5734** | +4,0550 |
| karantina red | 3 | 0 | 3 |
| karantina isabeti | 0,3333 | — | 0,3333 |

`kaynak: out/c1_runs/gpu_tam_380/predictions.jsonl → route.routed_heavy,
delta.*, scores.*.utility, merge.quarantined_pages`

**En önemli bulgu:** 380'in tamamı koşulduğunda birleşik precision 0,4713'ten
**0,4000'e** düşüyor. Ve birleşik sayı iki ters rejimi gizliyor:

- `ocrturk`: precision 0,5529, **NET +5,63** — yönlendirme fayda üretiyor.
- `opendataloader_bench`: precision 0,2267, **NET −1,57** — yönlendirme
  **fayda kaybettiriyor.** Ağır çağrıların %77,3'ü boşa; toplamda routed
  çıktısı fast çıktısından **daha kötü**.

Bu, CPU'da 201 belgeyle görülemiyordu: orada `opendataloader_bench`'ten sadece
72 belge vardı ve NET −0,68 idi; 200 belgenin tamamı koşulunca zarar iki katına
çıktı.

> "Yakalanan fayda oranı" (`max(delta,0)`) burada kasten kullanılmadı: asimetrik,
> yalnız kazancı sayar, gereksiz ağır çağrının zararını saymaz. `opendataloader`
> rejiminde tam da o zarar baskın.

### 5.3 Kontrol sütunu: aynı makinede CPU, 60 belge

| metrik | değer |
|---|---|
| documents / ok / errors | 60 / 60 / 0 |
| route_precision@0,02 | 0,4000 |
| NET | 1,0829 |
| GPU ile fark (aynı 60 belge) | fast **0**, heavy **0**, routed **0**, route kararı **0** |

`kaynak: out/c1_runs/cpu_ayni_makine_60/predictions.jsonl`

Cihaz dışında her şey sabitken **hiçbir metrik değişmiyor.** Soru 4'ün cevabı
budur: C1 fayda ölçümü GPU'da ayakta kalıyor.

---

## 6. Adım 6 — ölçülemedi

Kendi 9 belgelik korpusun tablo/şekil hükümleri **bu makinede ölçülemedi.**
`hata_arayuzu.py` iki girdi istiyor, ikisi de pakette gelmedi ve depoda üreten
betik yok:

- `out/docling_annot/<belge>.json` — referans tablo/şekil etiketleri
- `out/mineru/<belge>/auto/*_middle.json` — tablo referansının MinerU yarısı

İkincisi kritik: kod `if os.path.exists` ile koruyor, yani dosya yoksa referans
**sessizce boş kümeye düşüyor** ve tablo hükümleri hata vermeden anlamsız
çıkardı — bu projenin daha önce yaşadığı "hiç var olmayan sayı" hatasının aynısı.
Ayrıca `hata_arayuzu.py:55` içinde `OUT` sabit yazılı (`out/`), `PDF_PARSER_OUT`
dinlenmiyor; promptun Adım 6 tarifi bu sürümle çalışmıyor.

**Yerine ölçülen:** Adım 4'teki cihaz eşdeğerliği testi (65 belge, tablo
yapıları dahil, 0 fark). Ağır motorun metni ve tablo yapıları cihazla
değişmediği için tablo/şekil hükümlerinin de değişmeyeceği **çıkarımı** yapılabilir
— ama bu bir çıkarımdır, ölçüm değildir. Ölçmek için `docling_annot` ve `mineru`
çıktıları gerekir.

---

## 7. Açık kalanlar

1. **Hız ölçümü bu makinede tekrarlanabilir değil.** İki koşu arası CPU 1,40×,
   GPU 1,72× fark verdi; sebep doğrulanmadı. Hızlanma aralık olarak raporlandı.
2. **Donanım kısılması var** (SW Thermal Slowdown, 91 °C, SM 2100 → 1005 MHz).
   GPU hızlanma katsayısı bir **alt sınırdır**.
3. **Adım 6 ölçülemedi** — `docling_annot` ve `mineru` çıktıları yok (Bölüm 6).
4. **Önceki makinenin 7 sayfalık farkı açıklanamadı.** Bu makinede tekrarlanmadı
   ama iki değişken birden farklı (GPU mimarisi + docling 2.120.3 vs 2.120.1);
   hangisinin sorumlu olduğu ayrılamaz. Ayırmak için aynı makinede 2.120.3
   koşulmalı.
5. **`doclaynet` ve `omnidocbench` gönderilmedi** (ikisinde de PDF yok); envanter
   onları eksik görüyor, bu koşuda işe yaramazlar.
6. **`opendataloader_bench`'te NET negatif** bulgusu bu koşunun kapsamı dışında;
   eşik kalibrasyonu gerektirir ve `config/smart_router.yaml` bu koşuda kasten
   ellenmedi.
