# GPU koşusu sonuçları

Bu dizin, `smart_router` PDF ayrıştırma mimarisinin **GPU'lu bir makinede**
alınmış ölçümlerini içerir. Bütün ölçümler yalnız CPU'da alınmıştı; bu koşu
CPU sonuçlarıyla karşılaştırılabilir sayısal bir set üretmek için yapıldı.

## Sonuçlar tek satırda

- **Hız:** GPU, Docling'i 2,78×–3,40× hızlandırıyor (aralık, çünkü ölçüm bu
  makinede tekrarlanabilir değil). Ağır/kapı oranı CPU'da 203–285×, GPU'da
  **60–103×**. Her sayfayı ağıra yollamak GPU'da bile toplam süreyi 2,22×
  artırırdı — **sayfa seçmek hâlâ haklı.**
- **Determinizm:** GPU'da 3 koşu, hem 6 hem 75 sayfalık belgede **bayt bayt
  aynı**. `content_hash` sözleşmesi bozulmuyor.
- **Cihaz eşdeğerliği:** 261 sayfa + 65 belge, sayfa metni ve tablo yapıları
  dahil, CPU ile CUDA'da **fark yok**. Önceki RTX 4060'lı makinenin 7 sayfalık
  farkı tekrarlanmadı.
- **C1 faydası:** Aynı 201 belgede **hiçbir metrik değişmedi** (route kararı 0
  değişiklik). 380'in tamamı koşulunca precision 0,4713 → **0,4000** ve
  `opendataloader_bench`'te NET **negatif** (−1,57).
- **Kapanan boşluk:** 380 belgenin **tamamı** işlendi, 0 hata (CPU'da 201/380).

Ayrıntılar ve her sayının kaynağı: **[RAPOR_GPU.md](RAPOR_GPU.md)**
Koşan ajanın devir notu (tuzaklar ve ölçüm geçerliliği): **[DEVIR.md](DEVIR.md)**
Arayüzler: **`html/index.html`** (hepsinin listesi) · **`html/gpu_panosu.html`**
(tek sayfa, basılabilir) · **`html/c1_arayuz_gpu380.html`** (380 belge, belge belge)

## Bu depoda nereye kondu (2026-08-24 entegrasyonu)

| ne | yer | git'te |
|---|---|---|
| Özet kanıt dosyaları | `results/gpu_c1/` | evet |
| Pano betiği | `scripts/gpu_panosu.py` | evet |
| Cihaz provenance yaması | `scripts/c1_docling_cache.py` | evet |
| Arayüzler | `html/gpu_panosu.html`, `c1_arayuz_gpu380.html`, `c1_arayuz_gpu.html`, `index.html` | evet |
| Üç doğrulama koşusu (ham) | `out/c1_runs/{gpu_tam_380,gpu_ayni201,cpu_ayni_makine_60}/` | hayır |
| Docling cache'leri | `out/c1_docling_cache_{cuda,cpu,cpu_ek5}/` | hayır |
| Sayfa markdown'ları | `out/gpu_docling_json_{cpu,cuda}/` | hayır |
| Ara kanıt + loglar + koşum altyapısı | `out/gpu/` (`loglar/`, `kosum/`) | hayır |
| GPU makinesinin envanteri | `out/gpu/korpus_envanteri_gpu_makinesi.jsonl` | hayır |

> GPU makinesinin envanteri **ayrı adla** duruyor: kendi
> `out/korpus_envanteri.jsonl` dosyamız 3.047 kayıt (PDF'siz iki set dahil),
> onunki 380. Üzerine yazmak diğer iki setin kayıtlarını silerdi.

Pano bu depoda yeniden üretilebilir (doğrulandı, 2026-08-24):

```powershell
$env:PKT = "<gpu_paket_gonder dizini>"   # CPU tabani karsilastirmasi icin
$env:LOG = "$PWDesearch\pdf-parser\out\gpu\loglar"
.venv311\Scripts\python.exe research\pdf-parser\scripts\gpu_panosu.py
```

Koşum altyapısı (`kos.sh`, `NASIL_DEVAM.md`) `out/gpu/kosum/` altında.

## Ortam

| | |
|---|---|
| GPU | Quadro RTX 4000, 8 GB, sürücü 595.84, CUDA 13.2, sm_75 |
| işlemci | Intel Xeon W-2145 @ 3.70 GHz (8c/16t), 125 GB RAM |
| OS | Ubuntu 22.04.5, kernel 6.8.0-138 |
| ağır motor | Python 3.10.12, torch 2.6.0+cu124, **docling 2.120.1** |
| metrik | Python 3.11.16, rapidfuzz 3.14.5 |
| depo | `chnclsr/research-platform` @ `485a4b5` |
| metrik parmak izi | `c1_metrics_v1_2026-08-18+rapidfuzz` |

Tam kanıt: [`ortam.json`](ortam.json)

## Hangi dosya ne

| dosya | ne |
|---|---|
| `RAPOR_GPU.md` | Bulgular, tablolar, her iddianın altında kaynağı |
| `ortam.json` | Adım 0 — donanım/yazılım kanıtı, `nvidia-smi` çıktısı dahil |
| `envanter_karsilastirma.json` | Adım 1 — 380 PDF'in sha256'sı gönderilenle eşleşti mi |
| `gpu_docling_cpu.json` | Adım 3 — 9 belge, CPU, 1. ölçüm |
| `gpu_docling_cuda.json` | Adım 3 — 9 belge, CUDA, 1. ölçüm + eşdeğerlik |
| `gpu_docling_cpu_tekrar.json` | Adım 3 — aynı ölçüm, 2. kez (tekrarlanabilirlik) |
| `gpu_docling_cuda_tekrar.json` | aynı, CUDA |
| `gpu_docling_cuda_determinizm_turkce.json` | 6 sayfalık belge, GPU'da 3 koşu |
| `gpu_docling_cuda_determinizm_gpt3.json` | 75 sayfalık belge, GPU'da 3 koşu |
| `hiz_kararliligi.json` | İki ölçümün karşılaştırması, hızlanma aralığı |
| `summary_gpu_tam_380.json` | Adım 5(a) — 380 belgenin tamamı, GPU cache |
| `summary_gpu_ayni201.json` | Adım 5(b) — CPU tabanındaki aynı 201 belge |
| `summary_cpu_ayni_makine_60.json` | Adım 5(c) — bu makinede CPU, kontrol sütunu |
| `cache_esdegerlik.json` | Cihaz eşdeğerliği, C1 korpusu, tablo yapıları dahil |
| `atif_5belge.json` | Fark cihazdan mı makineden mi — ayrım ölçümü |
| `esdegerlik_farklari.md` | Sayfa sayfa eşdeğerlik listesi (fark çıkmadı) |
| `telemetri.jsonl` | 20 sn'de bir GPU kullanımı, sıcaklık, saat, throttle sebebi |
| `kosu_gunlugu.md` | Kaç kez kesildik, hangi adım ne zaman koştu |

**Git'e girmeyenler:** sayfa sayfa markdown çıktıları (`gpu_docling_json_*`,
`c1_docling_cache_*`). Büyükler ve yerel yol içeriyorlar; belge düzeyi SHA-256'lar
atıf için yeterli ve zaten özet JSON'ların içinde.

## Nasıl yeniden üretilir

```bash
# 1. Depo + korpus
git clone https://github.com/chnclsr/research-platform.git && cd research-platform
git fetch origin && git checkout 485a4b5
unzip <paket>/korpus/kendi9.zip              -d research/pdf-parser/
unzip <paket>/korpus/ocrturk.zip             -d corpus/raw/
unzip <paket>/korpus/opendataloader_bench.zip -d corpus/raw/

# 2. İki venv -- SIRA ÖNEMLİ: önce CUDA'lı torch, sonra docling
uv venv --python 3.11 .venv311
uv pip install --python .venv311/bin/python -r <paket>/kurulum/gereksinim_venv311.txt
uv venv --python 3.10 .venv-docling
uv pip install --python .venv-docling/bin/python \
    --index-url https://download.pytorch.org/whl/cu124 torch torchvision
uv pip install --python .venv-docling/bin/python docling==2.120.1

# 3. Bütün koşu -- kesintiye dayanıklı, kaldığı yerden devam eder
export OPENDATALOADER_BENCH=$PWD/corpus/raw/opendataloader_bench
<paket-disi>/kos.sh          # ./kos.sh durum  -> nerede kalındı
```

`kos.sh` her adımı ayrı ayrı takip eder; biten adım tekrar koşmaz. SSH kopması,
oturum ölümü ve reboot'a dayanıklıdır (crontab `@reboot` + 5 dakikalık watchdog).
Ayrıntı: `NASIL_DEVAM.md`.

## Metodoloji notları

- **CPU tabanı atlanmadı.** Karşılaştırma başka makinenin CPU'suyla değil,
  **aynı makinenin** CPU'su ile yapıldı; aksi hâlde iki değişken birden değişirdi.
- **Cache dizinleri ayrı.** `c1_docling_cache.py` dosyaları yalnız `pdf_sha256`
  ile adlandırıyor, cihaz adı anahtarda yok. GPU `c1_docling_cache_cuda`, CPU
  `c1_docling_cache_cpu` dizinlerine yazıldı; aynı dizin sessiz üzerine yazma
  demek olurdu.
- **Cihaz varsayılmadı.** Adım 2'de `c1_docling_cache.py` payload'una
  `"device": cihaz()` eklendi; `cihaz()` Docling'in `decide_device(AUTO)`
  sonucunu döndürür — tahmin değil, Docling'e sorulmuş cevap. Bu koşunun tek
  davranış değişikliği budur (ikincisi Adım 9'un yeni `gpu_panosu.py` betiği).
- **Üretim fonksiyonları çağrıldı, taklit edilmedi.** Karar sayıları
  `merge.birlestir()` ve kapının yazdığı alanlardan okundu.
- **Süreler süreç içi `perf_counter`'dan.** Kabuk duvar saati kullanılmadı;
  kesinti veya yeniden başlatma süre sayılarını etkilemez.
- **`config/smart_router.yaml` ellenmedi.** Bu koşuda tek değişken cihazdı.
