# Nanbeige4.1-3B Maksimum Kalite Testi — RTX 4060

Platform sürümü: `v0.2.5`

Belge sürümü: `1.0`

Benchmark sürümü: `1.2.0-hardware-optimized-holdout`

Tarih: `2026-07-16`

## Sonuç

Nanbeige4.1-3B bu bilgisayarda en yüksek kalite profiliyle mevcut
`qwen3:4b-instruct-2507-q4_K_M` modeline çok yaklaştı fakat onu geçemedi. İki temiz
bağımsız holdout koşusunda Nanbeige ortalama **76,44**, Qwen3-4B-2507 ise **77,68** aldı.

Nanbeige özellikle araştırma planlama ve query generation için güçlü bir adaydır.
Evidence extraction performansı Qwen ile yaklaşık eşittir. Entailment ve final synthesis
ise daha değişken ve biraz daha zayıftır. Maksimum profil yaklaşık **48,4 kat** daha uzun
sürdüğünden bütün rutin agent çağrılarında kullanılması uygun değildir.

## Neden bu profil maksimum kalite profili sayılıyor?

Üç quantization indirildi ve incelendi:

| Quantization | Model dosyası | Amaç |
|---|---:|---|
| Q8_0 | 4,2 GB | En düşük quantization kaybı; final kalite adayı |
| Q6_K | 3,2 GB | Kalite/context dengesi adayı |
| Q4_K_M | 2,4 GB | Hız ve uzun context adayı |

Q8_0 modeli tamamen GPU'ya sığdığı için daha düşük hassasiyetli Q6/Q4 final profile
alınmadı. Test sonrasında yalnız Q8_0 yerelde bırakıldı.

Model Ollama tarafından 3,9B parametre, 262.144 native context, Q8_0, thinking ve tool-use
destekli olarak raporlandı. Model-native sampling değerleri korundu:

- `temperature=0,6`
- `top_p=0,95`
- `top_k=0`
- `min_p=0,01`
- `repeat_penalty=1`

## Donanım sınırı

Q8_0 için context artırılarak Ollama model yerleşimi ölçüldü:

| Context | Ollama yerleşimi |
|---:|---|
| 8.192 | %100 GPU |
| 16.384 | %100 GPU |
| 24.576 | %100 GPU |
| 32.768 | %100 GPU |
| **36.864** | **%100 GPU** |
| 40.960 | %90 GPU / %10 CPU |
| 49.152 | %83 GPU / %17 CPU |

Final profil 36.864 context ve 32.768 reasoning token tavanıyla çalıştırıldı. Böylece
prompt için güvenli alan bırakılırken kartın doğrulanmış en yüksek tam-GPU context'i
kullanıldı.

## Structured-output entegrasyonu

Nanbeige, Ollama `format=json` ile thinking kapalı kullanıldığında agent şemasını güvenilir
biçimde takip etmedi. Bu sonuç model kalitesi olarak puanlanmadı. Maksimum profil:

1. JSON grammar zorlamadan model-native thinking çalıştırır.
2. Final cevap geçerli fenced/plain JSON ise doğrudan parse eder.
3. Yalnız final JSON bozuksa ikinci deterministic formatter çağrısı yapar.
4. Evidence için hem top-level array hem `{claims: [...]}` kabul eder.

İki temiz final koşuda dokuz çağrının tamamı geçerli JSON verdi; formatter çağrısı ve parser
hatası oluşmadı.

## Bağımsız holdout sonuçları

| Ölçüm | Nanbeige Q8 max-thinking | Qwen3-4B-2507 |
|---|---:|---:|
| Ortalama kalite | 76,44 | **77,68** |
| Koşu aralığı | 76,17–76,72 | 77,68–77,68 |
| Ortalama süre | 1.768,54 sn | **36,51 sn** |
| Üretim hızı | 52,33 token/sn | **81,71 token/sn** |
| Context | **36.864** | 24.576 |
| Koşu başına reasoning token | 92.138 | 0 |
| Tepe VRAM | 7.057 MiB | **6.656 MiB** |
| Ollama model yerleşimi | %100 GPU | %100 GPU |
| Token sınırında kesilen çağrı | 0 | 0 |
| Formatter çağrısı | 0 | 0 |
| Hata / geçersiz JSON | 0 | 0 |

Alt bölüm ortalamaları:

| Bölüm | Nanbeige Q8 max-thinking | Qwen3-4B-2507 |
|---|---:|---:|
| Decomposition | 95,00 | 95,00 |
| Query generation | **66,67** | 60,00 |
| Evidence extraction | 72,82 | **73,36** |
| Entailment | 70,83 | **75,00** |
| Synthesis | 90,00 | **100,00** |

Nanbeige'nin toplam skoru iki temiz koşuda oldukça kararlı olsa da bölüm skorları değişti:
query generation `73,33 / 60,00`, evidence `76,83 / 68,81`, entailment
`58,33 / 83,33`, synthesis `100 / 80`. Bu nedenle tek bir çağrıda kritik claim kararı
vermek yerine sonuçları başka bir model veya deterministik audit ile doğrulamak gerekir.

## Qwen3.5-4B maksimum-thinking ile karşılaştırma

Önceki Qwen3.5-4B maksimum-thinking profili 24K context'te ortalama `72,78` kalite ve
`937,11` saniye süre üretmişti. Nanbeige:

- Kalitede `+3,66` puan daha iyi.
- Yaklaşık `1,89 kat` daha yavaş.
- Daha yüksek tam-GPU context ve Q8 hassasiyet kullanıyor.

## Mimari öneri

Nanbeige'yi tek başına platform varsayılanı yapmak önerilmiyor. En uygun hibrit rol:

- Dinamik decomposition ve araştırma planı.
- Query expansion ve karşı-kanıt arama stratejisi.
- Zor bilimsel soru veya adversarial review.
- Coverage yetersizliğinde yeni araştırma dalları üretme.

Mevcut Qwen3-4B-2507 şu görevlerde korunmalı:

- Hızlı passage/evidence extraction.
- Citation entailment ve structured audit.
- Rutin JSON üretimi ve final paketleme.

Nanbeige maksimum-thinking çağrısı pahalı olduğundan her kaynağa uygulanmamalı; run başına
az sayıda planlama/audit düğümünde kullanılmalıdır.

## Yeniden üretim

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_optimized_models.py `
  --suite holdout `
  --repeats 1 `
  --profiles nanbeige4.1-3b-q8-rtx4060-max-thinking `
  --output data\model-nanbeige-q8-36k-max-thinking-holdout.json
```

Ham sonuçlar:

- `data/model-nanbeige-q8-36k-max-thinking-holdout-clean.json`
- `data/model-nanbeige-q8-36k-max-thinking-holdout-clean-r2.json`
- `data/profile-nanbeige-q8-36k-max-thinking-entailment.json`

## Sınırlamalar

- Bu test araştırma agentına özgü holdout'tur; GPQA'nın yeniden çalıştırılması değildir.
- İki temiz tekrar stochastic dağılımı bütünüyle ölçmek için azdır.
- Resmî model kartındaki GPQA ve deep-search sonuçları farklı değerlendirme düzeniyle
  üretilmiştir; yerel Q8/Ollama sonucu olarak yorumlanmamalıdır.
- Context sınırı masaüstünün o andaki VRAM kullanımına bağlıdır.
- Sonuçlar RTX 4060 8 GB, Ollama `0.31.2`, Q8_0 ve 2026-07-16 sistem durumu için geçerlidir.

Kaynaklar: [resmî model kartı](https://huggingface.co/Nanbeige/Nanbeige4.1-3B),
[teknik rapor](https://arxiv.org/abs/2602.13367),
[Ollama quantization etiketleri](https://ollama.com/tomng/nanbeige4.1/tags).
