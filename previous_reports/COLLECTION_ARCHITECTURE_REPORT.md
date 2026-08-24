# Bilgi Toplama Mimarisi — Kısa Rapor

Platform sürümü: `v0.3.0`

Belge sürümü: `1.1`

Son güncelleme: `2026-07-16`

## Amaç

Mevcut connector, AgentSearch, Crawl4AI, güvenlik, yapısal chunking ve kanıt hattı korunarak bilgi toplama katmanı kalıcı corpus ve çok aşamalı retrieval yapısına genişletildi.

## Akış

```text
QUERY → decomposition / expansion
  ├─ connector + AgentSearch web discovery
  ├─ OpenAlex + Semantic Scholar academic discovery
  ├─ Zotero local/web library corpus
  └─ kalıcı yerel corpus (BM25 + embedding)
        ↓
candidate fusion + protokol relevance filtresi
        ↓
persistent-id + canonical URL + content hash dedup
        ↓
SSRF / redirect / boyut / MIME politikası
        ↓
direct HTTP/API → AgentSearch /read → Crawl4AI → Scrapling fallback
        ↓
raw snapshot (MinIO) + provenance + outgoing-link frontier
        ↓
HTML/PDF/JSON/XML normalizasyonu + dil tespiti
        ↓
yapısal ve örtüşmeli passage üretimi
        ↓
BM25 rank + vector rank → RRF → relevance/kalite/çeşitlilik reranker
        ↓
evidence-ready passage ve /v1/corpus/search API
```

> **Not (2026-08-17):** Yukarıdaki edinim zinciri v0.3.0 dönemini yansıtır ve o günden beri
> iki adım eklenmiştir. Güncel sıra: Zotero inline fulltext / metadata (yalnız `zotero_*`
> connector'ları) → `direct` → `scholarly_metadata` (yalnız akademik aile; yeterli uzunlukta
> özet varsa tam metin denenmeden kısa devre yapar) → AgentSearch `/read` → Crawl4AI →
> Scrapling. `scholarly_metadata` adımı v0.9.1 ile eklenmiştir.
>
> Ayrıştırma da artık `parsers/` paketindeki kayıt defteri üzerinden yapılır; ayrıntı için
> [DEVELOPMENTS_IMPLEMENTATION_REPORT.md](../DEVELOPMENTS_IMPLEMENTATION_REPORT.md) 8. ve
> 9. bölümler.

> **Not (2026-08-24):** Edinim zinciri yeniden genişledi. Güncel son bölüm
> `Crawl4AI → Jina Reader → Scrapling` sırasındadır. Jina Reader anonim ve zorla browser
> motoruyla çalışan dış fallback'tir; ayrıntı için aktif geliştirme raporunun 32. bölümüne
> bakınız.

> **Not (2026-08-24):** GitHub repository URL'leri artık genel HTTP zincirinden önce
> `git clone --depth 1` ile geçici alana alınır; izlenen README, manifest ve kaynak dosyaları
> commit kimliğiyle yapılandırılmış metne dönüşür. İşlem bittiğinde geçici checkout
> temizlenir, başarısızlıkta yukarıdaki genel zincir devam eder. Ayrıntı için aktif
> geliştirme raporunun 33. bölümüne bakınız.

## Akademik katman

- OpenAlex DOI, abstract, OA location, version ve reference metadata sağlar.
- Semantic Scholar DOI/S2/CorpusId eşleme, citation/reference traversal ve açık PDF
  metadata sağlar.
- Zotero yerel veya web kütüphanesindeki bibliographic item, attachment ve tam metni
  corpus'a aktarır; kullanıcı notları evidence olarak kullanılmaz.
- Aynı çalışma DOI/PMID/arXiv/OpenAlex/S2 kimlikleri üzerinden tek `Source` altında
  birleştirilir; sağlayıcı cevapları ayrı provenance snapshot'ları olarak korunur.
- Citation ve sürüm ilişkileri PostgreSQL `source_relations` tablosunda saklanır.
- PaperQA2 yalnız opsiyonel shadow evidence backend'idir; native retrieval sonucunun
  yerine geçmez.

## Eklenenler

- Run'lar arası kalıcı corpus araması; web discovery ile paralel çalışır.
- `POST /v1/corpus/search`: metin, kaynak, bölüm, sayfa, karakter aralığı ve skor döndürür.
- Tracking parametrelerini ve fragment'i temizleyen canonical URL normalizasyonu.
- Kalıcı kimlik, canonical URL, içerik hash'i ve sıkı başlık eşleşmesine dayalı dedup.
- Ham snapshot'ın MinIO'ya; raw içerik, final URL, redirect zinciri, MIME, dil ve stratejilerin provenance'a yazılması.
- HTML link çıkarma ve domain öncelikli, bütçeli kalıcı crawl frontier.
- PDF metin çıkarma ve sayfa başlığı/numarası; HTML/JSON/XML/text tür ayrımı.
- Türkçe/İngilizce hafif dil tespiti ve passage metadata'sı.
- BM25 ve embedding listeleri için Reciprocal Rank Fusion (RRF).
- Query coverage, prose kalitesi, bölüm ve doküman çeşitliliği reranking'i.
- Aynı içerik hash'ine sahip passage'ların retrieval sırasında tekilleştirilmesi.
- Crawl4AI başarısızlığından sonra opsiyonel Scrapling HTTP fallback'i.
- API/worker başlamadan çalışan, transaction güvenli Alembic `migrate` servisi.

## Güvenlik sınırları

Scrapling yalnız normal HTTP fetch fallback'i olarak kullanılır; stealth/anti-bot veya paywall aşma etkin değildir. Tüm uzak URL'ler mevcut SSRF, public-IP, redirect, port, dosya boyutu ve domain rate-limit kontrollerinden geçer. Frontier yalnız daha sonraki kontrollü acquisition turuna aday üretir; sayfadaki talimatlar yürütülmez.

## Doğrulama

- 36 test geçti; Ruff temiz.
- Migration: `0003_collection_pipeline (head)`.
- Canlı corpus sorgusunda güvenlik sorusu için ilk sonuç `Limitations and security notes`, skor `0.8487`.
- Canlı kabul run'ı: `01KXJBS4ABKD271DA9TC3425PP`; 252 eski passage tarandı, 90 passage indekslendi ve 71 claim üretildi.
- Canlı testte bulunan alakasız GitHub repo yayılımı kapatıldı: açık bir GitHub hedefi varsa diğer repository'ler, trusted domain olsa bile reddedilir.
- PostgreSQL, Redis, Ollama, AgentSearch, Crawl4AI ve MinIO sağlık kontrolleri başarılı.

## Bilinen sınırlar

- Dil tespiti hafif ve deterministiktir; çok dilli kısa metinlerde `und` dönebilir.
- Reranker şu anda deterministik feature reranker'dır; ayrı bir cross-encoder modeli kullanılmıyor.
- PDF tabloları ve görselleri metin olarak sınırlı çözülür; OCR/multimodal işlem sonraki katmandır.
- Frontier derinliği tutulur, ancak kapsamlı host başına crawl-budget scheduler V2 işidir.
