# Qwen 4B Nesil Karşılaştırması — RTX 4060

Platform sürümü: `v0.2.3`

Belge sürümü: `1.0`

Benchmark sürümü: `1.2.0-hardware-optimized-holdout`

Tarih: `2026-07-15`

## Karar

Mevcut `qwen3:4b-instruct-2507-q4_K_M` varsayılan model olarak korunmalıdır.
`qwen3.5:4b`, daha büyük tam-GPU context ve daha iyi query generation sunmasına rağmen
araştırma agentının evidence extraction ve entailment görevlerinde belirgin biçimde daha
zayıf kaldı.

Bağımsız holdout ortalaması eski modelde **77,68**, Qwen 3.5 4B'de **61,89** oldu.
Eski model aynı zamanda yaklaşık `%24` daha kısa sürede tamamlandı ve `%18` daha yüksek
token üretim hızına ulaştı.

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

## Bağımsız holdout sonucu

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

## Öneri

- Platform varsayılanı Qwen 3 4B olarak kalmalı.
- Qwen 3.5 4B bütün agent akışına geçirilmemeli.
- 72K tam-GPU context avantajı nedeniyle uzun doküman ön-eleme veya yalnız query-planner
  rolünde ayrı bir deneysel sağlayıcı olarak tutulabilir.
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

## Sınırlamalar

- Bu çalışma araştırma agentına özgü küçük bir kabul testidir; genel model benchmarkı
  veya GPQA karşılaştırması değildir.
- Holdout kısa promptlar kullanır. Qwen 3.5 4B'nin 72K context avantajı doğrudan kalite
  skoruna yansımaz.
- Vision yeteneği bu text-only araştırma benchmarkında ölçülmemiştir.
- Sonuçlar RTX 4060 8 GB, Ollama `0.31.2`, Q4_K_M modeller ve 2026-07-15 sistem durumu
  için geçerlidir.
