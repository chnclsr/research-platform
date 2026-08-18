# Qwen 4B Nesil Karşılaştırması — RTX 4060

Platform sürümü: `v0.2.4`

Belge sürümü: `1.1`

Benchmark sürümü: `1.3.0-24k-max-thinking-holdout`

Tarih: `2026-07-15`

## Karar

Mevcut `qwen3:4b-instruct-2507-q4_K_M` varsayılan model olarak korunmalıdır.
`qwen3.5:4b`, 24K context ve maksimum-thinking profiliyle non-thinking sonucunu önemli
ölçüde yükseltti ancak mevcut modeli kalite ortalamasında geçemedi ve yaklaşık 25,7 kat
daha uzun sürdü.

Bağımsız holdout ortalaması eski modelde **77,68**, maksimum-thinking Qwen 3.5 4B'de
**72,78** oldu. Qwen 3.5 4B'nin önceki non-thinking sonucu **61,89** idi.

## 24K maksimum-thinking profili

Qwen 3.5 4B aşağıdaki ayarlarla yeniden çalıştırıldı:

| Ayar | Değer |
|---|---:|
| Context | 24.576 |
| Thinking | Açık |
| Reasoning token tavanı | 20.480 |
| Temperature | 1,0 |
| Top-p / top-k | 0,95 / 20 |
| Presence penalty | 1,5 |
| Final JSON bütçesi | 2.048 |
| Ollama yerleşimi | %100 GPU |

Structured output iki aşamaya ayrıldı. İlk çağrı JSON grameri olmadan serbestçe düşündü;
ikinci kısa, thinking-kapalı çağrı yalnız final içeriğini JSON'a dönüştürdü. Böylece thinking
ile strict JSON arasındaki önceki tamamlanma sorunu giderildi.

Tek geliştirme entailment görevinde skor `33,33`ten `87,50`ye yükseldi. Çağrı 15.259
reasoning token kullandı ve 254,95 saniye sürdü.

Üç bağımsız holdout koşusunun sonucu:

| Ölçüm | Qwen 3 4B | Qwen 3.5 4B maksimum thinking |
|---|---:|---:|
| Ortalama kalite | **77,68** | 72,78 |
| Minimum–maksimum | **77,68–77,68** | 69,26–74,74 |
| Ortalama süre | **36,51 sn** | 937,11 sn |
| Üretim hızı | **81,71 token/sn** | 66,27 token/sn |
| Koşu başına reasoning token | 0 | 58.404 |
| Üç koşu reasoning token toplamı | 0 | 175.212 |
| Tepe VRAM | 6.656 MiB | **5.505 MiB** |
| Tepe GPU kullanımı | %99 | **%100** |
| Token sınırında kesilen çağrı | 0 | 0 |
| Hata / geçersiz JSON | 0 | 0 |

Maksimum-thinking alt başlık ortalamaları:

| Bölüm | Qwen 3 4B | Qwen 3.5 4B maksimum thinking |
|---|---:|---:|
| Decomposition | **95,00** | 91,67 |
| Query generation | 60,00 | **74,72** |
| Evidence extraction | **73,36** | 68,29 |
| Entailment | **75,00** | 58,33 |
| Synthesis | **100,00** | 93,33 |

Thinking, yeni modelin query generation ve genel kalite performansını ciddi biçimde
iyileştirdi. Ancak entailment sonucu koşular arasında `75 / 50 / 50` olarak değişti ve
mevcut modelin deterministik `%75` sonucunun gerisinde kaldı.

## Modeller

| Özellik | Qwen 3 4B Instruct 2507 | Qwen 3.5 4B |
|---|---:|---:|
| Ollama etiketi | `qwen3:4b-instruct-2507-q4_K_M` | `qwen3.5:4b` |
| Gerçek parametre bilgisi | 4,0B | 4,7B |
| Quantization | Q4_K_M | Q4_K_M |
| Yerel model dosyası | 2,5 GB | 3,4 GB |
| Native context | 262.144 | 262.144 |
| Vision | Hayır | Evet |

## Donanım optimizasyonu

Her model için context, Ollama model yerleşimi `%100 GPU` kaldığı sürece artırıldı.

| Model | En yüksek doğrulanan tam-GPU context | CPU offload başlayan ilk profil |
|---|---:|---:|
| Qwen 3 4B | 24.576 | 25.600 (`%92 GPU / %8 CPU`) |
| Qwen 3.5 4B | **73.728** | 81.920 (`%86 GPU / %14 CPU`) |

Qwen 3.5 4B, KV-cache yerleşimi bakımından açık biçimde daha verimliydi ve bu kartta eski
modelin yaklaşık üç katı context'i tamamen GPU üzerinde tutabildi.

Qwen 3.5 4B geliştirme taraması:

| Profil | Evidence + entailment kalite puanı |
|---|---:|
| `temperature=0` | **67,74** |
| `temperature=0,5` | 64,63 |
| `temperature=1` | 56,67 |
| Thinking, native sampling | Geçersiz JSON; 127,9 sn |

Presence penalty ve top-p/top-k kaldırıldığında `temperature=0` sonucu değişmedi. Bu
nedenle final profil deterministik, thinking kapalı ve ek sampling cezası olmadan seçildi.

## Non-thinking başlangıç sonucu

Profil seçiminde görülmeyen holdout; decomposition, query generation, prompt-injection
içeren evidence extraction, 12 claim-passage entailment çifti ve kaynaklı synthesis
görevlerinden oluşur. Her model üç kez çalıştırılmış ve iki model de üç koşuda aynı sonucu
üretmiştir.

| Ölçüm | Qwen 3 4B 24K | Qwen 3.5 4B 72K |
|---|---:|---:|
| Ortalama kalite | **77,68** | 61,89 |
| Minimum–maksimum | 77,68–77,68 | 61,89–61,89 |
| Ortalama süre | **36,51 sn** | 48,04 sn |
| Üretim hızı | **81,71 token/sn** | 69,21 token/sn |
| Tepe VRAM | **6.656 MiB** | 6.812 MiB |
| Tepe GPU kullanımı | %99 | **%100** |
| Ollama model yerleşimi | %100 GPU | %100 GPU |
| Hata / geçersiz JSON | 0 | 0 |

Kalite alt başlıkları:

| Bölüm | Qwen 3 4B | Qwen 3.5 4B |
|---|---:|---:|
| Decomposition | **95,00** | 90,00 |
| Query generation | 60,00 | **80,00** |
| Evidence extraction | **73,36** | 57,31 |
| Entailment | **75,00** | 33,33 |
| Synthesis | **100,00** | 80,00 |

Qwen 3.5 4B'nin esas kaybı entailment yönü sınıflandırmasındadır. Yeni model 12 holdout
çiftinin yalnız dördünü doğru sınıflandırırken eski model dokuzunu doğru sınıflandırdı.
Evidence extraction'ta da exact passage'ı bulsa bile `supports / contradicts / qualifies`
yönünü daha sık yanlış verdi.

## Güncel öneri

- Platform varsayılanı Qwen 3 4B olarak kalmalı.
- Qwen 3.5 4B maksimum thinking bütün agent akışına geçirilmemeli; kalite ortalaması daha
  düşük, gecikmesi yaklaşık 25,7 kat yüksektir.
- Maksimum-thinking profil yalnız zor query planning, adversarial review veya seçilmiş claim
  audit görevlerinde deneysel verifier olarak kullanılabilir.
- Hızlı extraction çağrılarında thinking açılmamalıdır.
- Claim audit, citation entailment ve evidence extraction düğümlerinde Qwen 3.5 4B mevcut
  haliyle kullanılmamalıdır.
- Qwen 3.5 9B tamamen bırakılmış, aktif profillerden ve Ollama'dan kaldırılmıştır.

## Yeniden üretim

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_optimized_models.py `
  --suite holdout `
  --repeats 3 `
  --output data\model-optimized-benchmark-qwen4b-generations.json
```

Dosyalar:

- Benchmark runner: `scripts/benchmark_optimized_models.py`
- Bağımsız holdout: `scripts/benchmark_holdout_cases.py`
- Ortak scoring: `scripts/benchmark_models.py`
- Ham sonuç: `data/model-optimized-benchmark-qwen4b-generations.json`
- Maksimum-thinking ilk koşu: `data/model-qwen35-4b-24k-max-thinking-holdout-r1.json`
- Maksimum-thinking ikinci ve üçüncü koşu:
  `data/model-qwen35-4b-24k-max-thinking-holdout-r2-r3.json`

## Sınırlamalar

- Bu çalışma araştırma agentına özgü küçük bir kabul testidir; genel model benchmarkı
  veya GPQA karşılaştırması değildir.
- Holdout kısa promptlar kullanır. Qwen 3.5 4B'nin 72K context avantajı doğrudan kalite
  skoruna yansımaz.
- Vision yeteneği bu text-only araştırma benchmarkında ölçülmemiştir.
- Sonuçlar RTX 4060 8 GB, Ollama `0.31.2`, Q4_K_M modeller ve 2026-07-15 sistem durumu
  için geçerlidir.
