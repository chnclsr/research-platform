# GPU ölçümleri — kanıt

<!-- CLAUDE-2026-08-19: RTX 4060'li ikinci makinede alinan olcumlerin ozet kanitlari. -->

Ortam: PC_6605 · RTX 4060 8 GB · CUDA 13.2 · torch 2.13.0+cu132 ·
Docling 2.120.3 · Python 3.12.7.

Yorumu ve kararları `reports/PDF_PARSER_V0.1.0_RC1_REPORT.md` bölüm **E, F, G**
içinde. Buradaki dosyalar o bölümlerin dayandığı ham sayılar.

## Ne nerede

| Dosya | İçerik |
|---|---|
| `gpu_docling_cpu.json` | Aynı makinede **CPU** koşusu — belge süreleri, sayfa sayıları, belge markdown SHA-256'ları |
| `gpu_docling_cuda.json` | Aynı makinede **GPU** koşusu, aynı alanlar |
| `gpu_docling_cuda_step3_determinizm.json` | Tek belge, GPU'da 3 koşu, çıktı hash'leri |
| `sekil_aciklama_cuda_a_varsayilan.json` / `.md` | `do_picture_description`, Docling'in varsayılan promptu |
| `sekil_aciklama_cuda_b_metin.json` / `.md` | Aynısı, metin/veri isteyen promptla |

`.md` dosyaları **gözle okunmak için**: her şeklin caption'ı ve VLM'in ürettiği
açıklama yan yana. G.2'deki "model uyduruyor" kararı bu iki dosyaya dayanıyor —
okuyup kendin doğrulayabilirsin.

## Üç sonuç, tek satırda

- **Hız:** aynı makinede CPU 1.622 → GPU 530 ms/sayfa = **3,06×**. Yeni makinenin
  CPU'su tek başına eski makineden 2,23× hızlı; aynı makinede taban alınmasaydı
  GPU'ya 6,83× yazılacaktı.
- **Determinizm:** GPU'da 3 koşu **bayt bayt aynı** → geçti.
- **Eşdeğerlik:** aynı makine, aynı Docling, tek değişken cihaz — **261 sayfanın
  7'si farklı**, 6'sı kozmetik, 1'i gerçek kayıp (`gpt3` s.50, bir markdown tablosu
  kayboldu) → **geçmedi**.

## Burada olmayanlar

Sayfa sayfa markdown çıktıları (`gpu_docling_json_cpu/`, `gpu_docling_json_cuda/`,
~2,3 MB) depoya girmiyor: yerel yol içeriyorlar ve betikler yeniden üretebiliyor.
Atıf için gereken bilgi belge düzeyi SHA-256'larda zaten var.

## Yeniden üretmek

PDF'ler depoda değil; `research/pdf-parser/corpus/kendi/` altına koy ya da
`KENDI_KORPUS` ile yerini göster.

```powershell
# Docling'in CUDA'li kurulumu gerekiyor -- once CUDA'li torch, SONRA docling
python research\pdf-parser\scripts\gpu_docling_olc.py --device cpu  --runs 1
python research\pdf-parser\scripts\gpu_docling_olc.py --device cuda --runs 1
python research\pdf-parser\scripts\gpu_docling_olc.py --device cuda --determinizm 3 --only turkce
python research\pdf-parser\scripts\gpu_docling_olc.py --device cuda --karsilastir out\gpu_docling_json_cpu

# Sekil aciklamasi (SmolVLM-256M ~500 MB iner)
python research\pdf-parser\scripts\gpu_sekil_aciklama.py --device cuda
python research\pdf-parser\scripts\gpu_sekil_aciklama.py --device cuda --prompt-metin --taban-atla
```

**CPU tabanını atlama.** Farklı makinelerin sayılarını kıyaslamak işlemci ve GPU
farkını birbirine karıştırır; karşılaştırma aynı makinedeki iki koşu arasında
yapılmalıdır.
