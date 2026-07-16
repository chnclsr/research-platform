# Değişiklik Günlüğü

Platform sürümü: `v0.4.1-dev`

Belge sürümü: `2.0`

Son güncelleme: `2026-07-16`

## v0.4.1-dev — 2026-07-16

- Coverage eksikleri `CoverageGap` nesnelerine, sonraki tur aramaları bütçeli
  `SearchMission` görevlerine dönüştürüldü.
- Kaynak ailesi, otorite, claim desteği ve cevapsız sorgu dalı için ayrı recovery
  stratejileri eklendi.
- Acquisition öncesi kalıcı corpus novelty filtresi ve tekrar bulunan kaynağı yeniden
  indirmeden metadata/query-branch ile zenginleştirme eklendi.
- Resmî-domain görevlerinde sonuç URL'sinin gerçekten izinli domaine ait olduğu doğrulandı.
- MCP, Codex, Claude Code ve Telegram için doğrulanmış resmî doküman ve kaynak depo seed
  registry'si eklendi.
- İlk tur ve sonraki turlar için ayrı kaynak bütçeleri ile mission-balanced aday seçimi
  eklendi.
- Coverage yalnız gerçek edinilmiş kaynak ve kanıtlardan hesaplanmaya başladı; recovery
  görevlerinin paydada sahte sorgu dalı oluşturması engellendi.
- Yeni kaynak yoksa eski source version'ların chunk, embedding ve claim extraction
  işlemlerine yeniden girmesi engellendi.
- Ulaşılamayan Zotero ve anahtarsız/degraded connector'lar her arama çağrısında hata
  üretmek yerine health preflight ile atlanıyor.
- Prompt-injection benzeri discovery başlıkları karantinaya alınıyor; named-product
  araştırmalarında alakasız official/legal sonuçlar coverage'a giremiyor.
- Akademik/web ve code/data aileleri için ayrı coverage eligibility eşikleri eklendi.
- `raw` modu claim extraction ve model sentezini gerçekten atlıyor; MCP ve Telegram
  output mode seçimi protokole taşınıyor.
- Canlı doğrulama run'ı `01KXNFSF8B53543WY39NGJNNE4`, 14 kaynakla aile coverage `1.0`,
  sorgu dalı coverage `0.9167`, otorite coverage `1.0` ve doygunluk `1` üreterek
  `completed` durumunda bitti.

## v0.4.0-dev — 2026-07-16

- Platformun rolü, tek başına cevap veren yerel ajandan Codex ve Claude gibi genel amaçlı
  ajanlara kanıt sağlayan yerel Research Gateway'e genişletildi.
- `raw`, `result` ve `both` teslimat modları eklendi.
- Ham kaynak sürümlerini ve normalize passage'ları taşıyan `13_raw_sources.jsonl` ve
  `14_raw_passages.jsonl` artifact'leri eklendi.
- `raw_bundle.zip`, `result_bundle.zip` ve birleşik `research_bundle.zip` üretimi eklendi.
- Codex ve Claude istemcileri için MCP server ve yedi araştırma aracı eklendi.
- Streamable HTTP MCP endpoint'ine bearer token ve Origin allowlist koruması eklendi.
- Telegram long-polling botu; araştırma başlatma, durum, teslimat, pause/resume/cancel
  komutları ve kullanıcı/chat allowlist'i ile eklendi.
- Codex ve Claude örnek MCP yapılandırmaları ile Agent Gateway mimari raporu eklendi.

## v0.3.0 — 2026-07-16

- OpenAlex connector'ı güncel API key, abstract reconstruction, OA location, version,
  retraction ve citation relation metadata ile yenilendi.
- Semantic Scholar Academic Graph connector'ı; DOI/S2/CorpusId eşleme, rate limiting,
  açık PDF metadata ve citation/reference traversal ile eklendi.
- Zotero Local API ve Web API connector'ları, attachment full-text, collection/tag
  filtresi ve incremental library-version sync desteğiyle eklendi.
- Zotero kullanıcı notları corpus'ta saklanabilse de bilimsel evidence extraction dışında
  tutuldu.
- DOI/PMID/PMCID/arXiv/OpenAlex/S2/Zotero kimliklerini birleştiren scholarly identity
  katmanı ve provider snapshot kaydı eklendi.
- PostgreSQL `source_relations` citation graph ve `connector_sync_cursors` tabloları
  eklendi.
- Federated akademik sonuçlarda RRF sinyali, açık tam metin, çalışma türü, retraction ve
  Zotero priority-tag sinyalleri reranking'e eklendi.
- Citation graph, academic coverage, Zotero collections ve Zotero sync API'leri eklendi.
- PaperQA2 mevcut pipeline'ı değiştirmeyen, varsayılan kapalı optional shadow evidence
  backend'i olarak eklendi.

## v0.2.7 — 2026-07-16

- Nitel model değerlendirme metodolojisindeki sayısal ölçüm sınırı netleştirildi.
- Hız, token, VRAM, context, hata oranı ve formatter oranı gibi nesnel metriklerin
  sayısal raporlanmasına izin verildi.
- Etiketleri önceden dondurulmuş corpus üzerinde retrieval precision, recall, hit-rate,
  MRR ve nDCG ölçüm kuralları eklendi.
- Yasak, nesnel ölçümlere değil; öznel kalite boyutlarını keyfî ağırlıklarla tek bileşik
  model puanına dönüştürmeye sınırlandı.

## v0.2.6 — 2026-07-16

- Sayısal model sıralaması yerine ham çıktıların uzman yorumuna dayanan nitel değerlendirme
  metodolojisi önceden kilitlenmiş belge olarak eklendi.
- Körleştirme, formatter ayrımı, tartışmalı gold etiketleri ve metodoloji ihlali kuralları
  tanımlandı.
- Önceki otomatik holdout'un model ve parser geliştirmesinde kullanıldığı için bağımsız
  holdout sayılamayacağı belgelendi.

## v0.2.5 — 2026-07-16

- Nanbeige4.1-3B Q8_0, Q6_K ve Q4_K_M quantization adayları RTX 4060 üzerinde incelendi.
- Q8_0 için 36.864 token tam-GPU context ve 32.768-token reasoning profili doğrulandı.
- Ollama sampling arayüzüne `min_p` ve `repeat_penalty` desteği eklendi.
- Thinking finali geçerli JSON ise gereksiz formatter çağrısı atlanmaya başlandı.
- Evidence extraction top-level JSON array ve `{claims: [...]}` biçimlerini kabul ediyor.
- Nanbeige maksimum-quality profili bağımsız holdout üzerinde iki temiz koşuyla ölçüldü.

## v0.2.4 — 2026-07-15

- Qwen 3.5 4B için 24K context ve 20.480-token reasoning tavanlı profil eklendi.
- Serbest thinking çağrısını ayrı deterministic JSON formatter çağrısına bağlayan iki
  aşamalı Ollama structured-output desteği eklendi.
- Maksimum-thinking profili bağımsız holdout üzerinde üç kez doğrulandı.
- Reasoning ve formatting süre/token metrikleri ayrı kaydedilmeye başlandı.

## v0.2.3 — 2026-07-15

- Qwen 3.5 9B benchmark adaylarından ve yerel Ollama kurulumundan çıkarıldı.
- Qwen 3 4B ile Qwen 3.5 4B için model başına tam-GPU profil taraması yapıldı.
- Qwen 3.5 4B'nin 73.728 token tam-GPU context sınırı doğrulandı.
- Bağımsız holdout üzerinde üç tekrarlı Qwen 4B nesil karşılaştırması eklendi.

## v0.2.2 — 2026-07-15

- RTX 4060 üzerinde model başına tam-GPU context ve sampling profil taraması eklendi.
- Ayrı geliştirme ve bağımsız holdout setleriyle üç tekrarlı model benchmarkı eklendi.
- Ollama sağlayıcısına temperature, top-p, top-k ve presence-penalty ayarları eklendi.
- Qwen 3 4B için 24K, Qwen 3.5 9B için 4K tam-GPU profilleri doğrulandı.

## v0.2.1 — 2026-07-15

- Qwen 3 4B ve Qwen 3.5 9B için araştırma-agentına özgü hard benchmark eklendi.
- Ollama structured-output çağrılarına açık thinking, context ve output token sınırları eklendi.
- RTX 4060 üzerinde 4K/8K context GPU yerleşimi ve kalite/hız karşılaştırması raporlandı.

## v0.2.0 — 2026-07-15

- Yapısal passage üretimi ve belgenin tamamını kapsayan extraction eklendi.
- BM25, yerel embedding, RRF ve ikinci aşama reranking eklendi.
- Kalıcı yerel corpus araması ve `/v1/corpus/search` API'si eklendi.
- Canonical URL, içerik hash'i, raw snapshot ve provenance kapsamı genişletildi.
- Kontrollü link frontier, PDF normalizasyonu ve Scrapling fallback eklendi.
- Migration işlemi transaction güvenli hale getirildi ve Compose migrate servisi eklendi.
- Araştırma kalitesi golden recall ölçümünde %33,3'ten %100'e yükseldi.

## v0.1.0 — 2026-07-14

- FastAPI, LangGraph worker, connector registry ve çıktı paketiyle ilk çalışan V1 oluşturuldu.
- PostgreSQL, Redis, MinIO, AgentSearch, Crawl4AI, Langflow ve Ollama entegrasyonları eklendi.
