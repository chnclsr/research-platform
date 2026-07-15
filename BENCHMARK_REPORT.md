# Research Platform V1 — Çalıştırma ve Benchmark Raporu

Platform sürümü: `v0.2.0`  
Belge sürümü: `1.1`  
İlk yayın tarihi: `2026-07-14`  
Son güncelleme: `2026-07-15`  
Run ID: `01KXGGEQ84ASAH2134MMKDCEFM`

## Sonuç

Platform teknik olarak uçtan uca çalıştı ve kaynak edinme, LLM çıkarımı, checkpoint, audit ve ZIP üretimini tamamladı. Ancak araştırma kalitesi kabul edilebilir değil: arama sonuç kotasını AgentSearch'ten gelen alakasız genel sayfalar doldurdu, GitHub connector sonuçları corpus'a giremedi ve nihai rapor araştırma sorusunu yanıtlamadı. Sonuç bu nedenle yalnız `completed_incomplete` değil, ürün kalitesi açısından başarısız bir benchmark olarak değerlendirilmelidir.

## Test ortamı

- GPU: NVIDIA GeForce RTX 4060, 8.188 MB VRAM
- Sürücü: 595.95
- Model: `qwen3:4b-instruct-2507-q4_K_M`
- Model formatı: GGUF, Q4_K_M, 4B
- Model dosyası: 2.497.293.803 bayt
- Çalışma biçimi: Ollama host üzerinde; API ve worker Docker container'larında
- Connector'lar: `agentsearch_web`, `github`
- Bütçe: 1 tur, 4 kaynak, connector başına 2 sonuç, 2 paralel acquisition, 10 dakika

## Otomatik doğrulama

| Kontrol | Sonuç |
|---|---:|
| Pytest | 14/14 geçti |
| Ruff | Geçti |
| Docker Compose config | Geçti |
| API health | PostgreSQL, Redis, Ollama, AgentSearch, Crawl4AI ve MinIO `ok` |
| Langflow | HTTP 200; dört custom component import edildi |
| ZIP bütünlüğü | Geçti; 12/12 planlanan dosya mevcut |

Pytest sırasında yalnız Starlette TestClient'in gelecekteki `httpx2` geçişiyle ilgili bir deprecation uyarısı görüldü; test başarısını etkilemedi.

## Performans

| Ölçüm | Sonuç |
|---|---:|
| Toplam duvar süresi | 196,7 saniye |
| Kabul edilen kaynak | 4 |
| Çıkarılan claim | 48 |
| Artifact | 13 (12 dosya + ZIP) |
| Ortalama GPU kullanımı | %85,9 |
| Tepe GPU kullanımı | %100 |
| Ortalama VRAM | 4.562 MB |
| Tepe VRAM | 4.628 MB |
| Tepe sıcaklık | 73 °C |
| OOM / worker çökmesi | Yok |

### Aşama süreleri

PostgreSQL event zaman damgalarından hesaplanmıştır.

| Aşama | Yaklaşık süre |
|---|---:|
| Protocol validation + decomposition başlangıcı | 0,02 sn |
| Query branch üretimi | 3,52 sn |
| Search | 1,12 sn |
| Acquisition | 20,25 sn |
| Normalization | 0,05 sn |
| Evidence/claim extraction | 80,48 sn |
| Claim analysis + coverage + audit | 0,37 sn |
| Adversarial review + synthesis/export | 89,38 sn |

Sürenin yaklaşık %86'sı LLM kullanan extraction ve synthesis/export aşamalarında harcandı.

### Ollama mikro benchmark

Sıcak model üzerinde 40 prompt token ve 225 output token içeren JSON üretimi:

- Toplam süre: 5,46 sn
- Model yükleme: 2,57 sn
- Üretim süresi: 2,81 sn
- Üretim hızı: 80,07 token/sn

RTX 4060 bellek açısından yeterli görünüyor. Tepe kullanım toplam VRAM'in yaklaşık %56,5'i; bu koşuda daha büyük modele geçmekten önce kalite sorunlarını sorgu/ranking katmanında çözmek daha doğru olacaktır.

## Coverage ve audit

| Metrik | Sonuç |
|---|---:|
| Source-family coverage | 0,40 |
| Query-branch coverage | 1,00 |
| Claim-audit coverage | 1,00 |
| Unresolved major claim | 0 |
| Saturated rounds | 0 |

Tamamlanmama nedenleri `source_family_coverage` ve `query_saturation` olarak kaydedildi.

Bu değerler tek başına kaliteyi göstermiyor. Claim audit değerinin 1,00 olması bütün claim'lerin bir passage'a çözümlenebildiği anlamına geliyor; passage'ın araştırma sorusuyla ilgili olduğunu göstermiyor. Adversarial review 48 claim'in tamamını zayıf olarak işaretledi.

## Kaynak ve rapor kalite incelemesi

Kabul edilen dört kaynak:

1. Architecture — Wikipedia
2. ArchDaily
3. COMPONENT — Merriam-Webster
4. COMPONENT — Cambridge Dictionary

Kaynakların hiçbiri hedef GitHub deposunu açıklamıyor. Nihai rapor; mimari haberleri, sözlük tanımları ve AgentSearch ile ilgisiz iddialar içeriyor. Ayrıca `02_full_research_report.md` okunabilir bir rapor yerine Python liste/dict gösterimine yakın ham bir yapı üretiyor.

Kök nedenler:

1. LLM sorguları arasında doğru ve hedefe özel sorgular bulunmasına rağmen connector sonuçları global relevance sıralamasından geçmiyor.
2. `max_sources=4` kotası ilk connector'ın adaylarıyla doluyor; connector/aile çeşitliliği için kota ayrılmıyor.
3. Trusted domain ayarı discovery sonucunu zorunlu filtreye dönüştürmüyor.
4. Acquisition öncesi başlık/snippet–araştırma sorusu relevance eşiği yok.
5. Coverage hesabı passage izlenebilirliğini ölçüyor fakat semantic relevance ölçmüyor.
6. Sentez katmanı zayıf/alakasız claim'leri nihai rapordan dışlamıyor.

## Karar ve önerilen düzeltme sırası

Mevcut haliyle platform altyapı ve performans smoke testini geçiyor; araştırma doğruluğu kabulünü geçmiyor.

V1'i gerçek kullanım öncesi kabul edilebilir hale getirmek için:

1. Exact URL/repository sorgularını deterministik olarak algılayıp GitHub direct-fetch yoluna yönlendirin.
2. Connector başına aday kotası uygulayın; global `max_sources` kesmesini relevance ve aile çeşitliliği sıralamasından sonra yapın.
3. Trusted domain için zorunlu filtre ve domain önceliği ekleyin.
4. Acquisition öncesi deterministik lexical + embedding relevance kapısı koyun.
5. Claim audit'e `question_relevance` metriği ekleyin; alakasız claim'ler coverage'a sayılmasın.
6. Adversarial review'un zayıf işaretlediği claim'leri synthesis girdisinden çıkarın veya ayrı belirsizlik bölümüne taşıyın.
7. Rapor renderer'ını yapılandırılmış Markdown üretimine çevirin; ham Python nesnesi gösterimini kaldırın.
8. Aşama bazında LLM token, prompt süresi, generation süresi ve connector latency metriklerini kalıcı olarak saklayın.

## Üretilen dosyalar

- Benchmark ZIP: `data/benchmark-01KXGGEQ84ASAH2134MMKDCEFM.zip`
- Platform acceptance ZIP: `data/acceptance-research-bundle.zip`

## Düzeltme sonrası doğrulama

İlk benchmarkta bulunan kalite sorunları giderildi ve aynı AgentSearch araştırması yeniden çalıştırıldı.

Son kalite run'ı: `01KXGHE5MMV22X2CTQPQVZY7VB`

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Süre | 196,7 sn | 42,27 sn |
| Kabul edilen kaynak | 4 alakasız | 1 exact hedef repo |
| Çıkarılan claim | 48 | 15 |
| Raporlanabilir claim | 0 ilgili | 5 güçlü quote eşleşmeli |
| Sentezden dışlanan | 0 | 10 zayıf entailment |
| İlgisiz claim | 48 | 0 |
| Ham Python liste gösterimi | Var | Yok |

Uygulanan düzeltmeler:

1. GitHub URL/slug algılama ve doğrudan `/repos/{owner}/{repo}` edinimi.
2. Canonical URL deduplication ve exact GitHub adayını tercih etme.
3. Connector round-robin kotası ve relevance tabanlı global sıralama.
4. Trusted-domain zorunlu filtresi.
5. Acquisition öncesi lexical relevance kapısı.
6. Claim seviyesinde soru ilgisi ve kaynak ilgisi denetimi.
7. Claim–quote lexical entailment üst sınırı.
8. Zayıf ve tek kaynaklı claim'leri ayrı raporlama; unresolved claim'leri sentezden çıkarma.
9. Yapılandırılmış Markdown renderer.
10. Kalıcı LLM token/süre, connector latency ve acquisition latency event'leri.

Son telemetri kabul run'ı `01KXGHMEK3RWPYZK9RK50SJWFJ` 39,23 saniyede tamamlandı. Ollama çağrılarının prompt/output tokenları ve süreleri, sekiz GitHub sorgusunun ayrı gecikmeleri ve direct acquisition süresi PostgreSQL `run_events` tablosunda doğrulandı.

Son çıktı paketi: `data/benchmark-final-01KXGHE5MMV22X2CTQPQVZY7VB.zip`
