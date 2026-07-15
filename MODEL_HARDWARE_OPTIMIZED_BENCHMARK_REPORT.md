# RTX 4060 Donanım-Optimize Model Karşılaştırması

Platform sürümü: `v0.2.2`

Belge sürümü: `1.0`

Benchmark sürümü: `1.2.0-hardware-optimized-holdout`

Tarih: `2026-07-15`

## Sonuç

Bu bilgisayarda araştırma agentının varsayılan modeli olarak
`qwen3:4b-instruct-2507-q4_K_M` daha verimli ve daha güvenilir seçimdir. Bağımsız holdout
setinde 4B model **77,68**, `qwen3.5:9b` ise **71,05** ortalama kalite puanı aldı. 4B
yaklaşık **1,90 kat daha hızlı**, 9B ise daha fazla VRAM kullanmasına rağmen daha değişken
sonuç verdi.

Bu sonuç Qwen 3.5 9B'nin genel yetenek sıralaması değildir. Sonuç, Ollama Q4_K_M
quantization, RTX 4060 8 GB ve mevcut araştırma-agentı structured-output iş yükü için
geçerlidir.

## Adalet ilkesi ve profil seçimi

İki modele aynı context veya sampling zorlanmadı. Her model için aşağıdaki sıra izlendi:

1. Context artırılarak Ollama model yerleşiminin tamamen GPU'da kaldığı sınır arandı.
2. Deterministik, model-native sampling ve ara sıcaklık profilleri küçük geliştirme
   görevlerinde karşılaştırıldı.
3. Thinking yalnız fayda ve tamamlanmış structured output üretiyorsa aday kabul edildi.
4. Seçilen profil, optimizasyonda görülmeyen bağımsız holdout setinde üç kez çalıştırıldı.

Tam-GPU context sınırı:

| Model | En yüksek doğrulanan `%100 GPU` context | İlk doğrulanan CPU offload |
|---|---:|---:|
| Qwen 3 4B | 24.576 | 25.600 (`%92 GPU / %8 CPU`) |
| Qwen 3.5 9B | 4.096 | 5.120 (`%88 GPU / %12 CPU`) |

Powers-of-two taramasında 4B; 4K, 8K ve 16K'da, 9B ise yalnız 4K'da tamamen GPU'da
kaldı. Daha yüksek context'in teorik olarak açılabilmesi tam-GPU çalıştığı anlamına
gelmediğinden CPU offload başlayan profiller final teste alınmadı.

Seçilen profiller:

| Ayar | Qwen 3 4B | Qwen 3.5 9B |
|---|---:|---:|
| Context | 24.576 | 4.096 |
| Quantization | Q4_K_M | Q4_K_M |
| Thinking | Kapalı | Kapalı |
| Temperature | 0 | 0,5 |
| Top-p | Model/runtime varsayılanı | 0,95 |
| Top-k | Model/runtime varsayılanı | 20 |
| Presence penalty | Model/runtime varsayılanı | 1,5 |
| Max output | 2.048 | 2.048 |

## Optimizasyon bulguları

- 4B'nin deterministik profili geliştirme setinde `71,59` aldı. Native
  `temperature=0,7` profili `54,32` ve bir geçersiz JSON üretti.
- 9B'nin önceki deterministik profili `68,79` almıştı. Native `temperature=1` üç
  tekrarda `68,16` ortalama ve `58,49–74,23` aralığı üretti.
- 9B kısa evidence+entailment taramasında sıcaklık `0,2 / 0,5 / 0,7` için sırasıyla
  `59,72 / 66,06 / 58,88` aldı. Bu nedenle `0,5` seçildi.
- 9B `temperature=0,5` geliştirme doğrulamasında `70,85` ortalama
  (`67,82–75,30`) aldı. 4B aynı sette `71,59` ve sıfır varyans gösterdi.
- 4B thinking denemesinde entailment puanı `62,50` olarak değişmedi. 9B thinking
  denemesi 78,8 saniye sonunda geçerli JSON üretemedi. Bu nedenle thinking, bu kartta
  final agent profiline alınmadı.

## Bağımsız holdout sonucu

Holdout seti profil seçiminden sonra oluşturulan farklı decomposition, query generation,
evidence extraction, entailment ve synthesis vakalarını içerir. Her profil üç kez
çalıştırılmıştır.

| Ölçüm | Qwen 3 4B 24K | Qwen 3.5 9B 4K |
|---|---:|---:|
| Ortalama kalite | **77,68** | 71,05 |
| Minimum–maksimum | **77,68–77,68** | 62,90–75,29 |
| Ortalama süre | **33,92 sn** | 64,54 sn |
| Üretim hızı | **83,70 token/sn** | 43,65 token/sn |
| Tepe VRAM | **6.867 MiB** | 7.237 MiB |
| Tepe GPU kullanımı | %97 | **%100** |
| Ollama model yerleşimi | %100 GPU | %100 GPU |
| Hata / geçersiz JSON | 0 | 0 |

Kalite alt başlıkları:

| Bölüm | Qwen 3 4B | Qwen 3.5 9B |
|---|---:|---:|
| Decomposition | **95,00** | 80,00 |
| Query generation | 60,00 | **68,89** |
| Evidence extraction | **73,36** | 66,82 |
| Entailment | **75,00** | 66,67 |
| Synthesis | **100,00** | 86,67 |

9B yalnız query generation ortalamasında öne çıktı. 4B özellikle decomposition,
evidence extraction ve claim-passage entailment'ta daha güçlüydü. 9B'nin en iyi tek
koşusu `75,29` olsa da 4B'nin üç koşusundaki `77,68` değerine ulaşamadı.

## Kullanım kararı

- Varsayılan araştırma modeli: Qwen 3 4B, 24K context, thinking kapalı,
  `temperature=0`.
- Qwen 3.5 9B: deneysel profil; 4K context, thinking kapalı, `temperature=0,5`.
- 9B'nin query üretimindeki avantajı istenirse yalnız query-planner rolünde ayrıca A/B
  test edilebilir. Ancak mevcut sonuç, bütün agent akışını 9B'ye taşımayı desteklemiyor.
- Uzun reasoning için 9B thinking kullanımı, 8 GB kartta context/çıktı bütçesi ve JSON
  tamamlanma sorunu çözülmeden varsayılan yapılmamalıdır.

## Yeniden üretim

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_optimized_models.py `
  --suite holdout `
  --repeats 3 `
  --output data\model-optimized-benchmark-holdout-rtx4060.json
```

İlgili dosyalar:

- Profil ve benchmark runner: `scripts/benchmark_optimized_models.py`
- Bağımsız test vakaları: `scripts/benchmark_holdout_cases.py`
- Ortak scoring kodu: `scripts/benchmark_models.py`
- Ham 4B 24K sonuç: `data/model-optimized-benchmark-holdout-4b-24k.json`
- Ham karşılaştırma sonucu: `data/model-optimized-benchmark-holdout-rtx4060.json`

## Sınırlamalar

- Holdout küçük bir agent kabul setidir; GPQA veya genel amaçlı model benchmarkı değildir.
- Temperature `0,5` kullanılan 9B için üç tekrar, dağılımın kuyruklarını ölçmek için azdır.
- Context kapasitesi kısa holdout promptlarında doğrudan kalite avantajı sağlamaz; burada
  donanım yerleşimi ve ilerideki uzun belge çağrıları için profil sınırı olarak ölçülmüştür.
- Masaüstü görüntü belleği kullanımı değişirse tam-GPU sınırı da değişebilir.
- Sonuçlar Ollama `0.31.2`, yerel model dosyaları ve 2026-07-15 tarihindeki sistem durumu
  için geçerlidir.
