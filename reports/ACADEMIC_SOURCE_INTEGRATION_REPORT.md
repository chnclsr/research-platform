# Akademik Kaynak Katmanı Uygulama Raporu

Platform sürümü: `v0.3.0`

Belge sürümü: `1.0`

Tarih: `2026-07-16`

## Sonuç

OpenAlex, Semantic Scholar, Zotero Local/Web ve opsiyonel PaperQA2 shadow katmanı mevcut
araştırma platformuna eklendi. Mevcut AgentSearch, acquisition, passage retrieval,
claim/evidence, coverage ve raporlama hattı korunmuştur. Varsayılan LLM modeli ve model
ayarları değiştirilmemiştir.

## Uygulanan bileşenler

### OpenAlex

- Güncel `OPENALEX_API_KEY` ve opsiyonel `OPENALEX_MAILTO` ayarları
- Inverted-index abstract'ın doğru metin sırasına dönüştürülmesi
- DOI ve OpenAlex ID normalizasyonu
- Primary/best-OA location ve bütün version location kayıtları
- Referenced-work citation edge üretimi
- Retraction, publication type, authorship ve citation count provenance'ı
- API key yokken connector registry'de disabled sağlık durumu

### Semantic Scholar

- Academic Graph paper search
- DOI, S2 PaperId, CorpusId, arXiv, PMID ve PMCID kimlikleri
- Abstract, venue, publication type ve open-access PDF metadata
- İleri ve geri citation traversal
- `x-api-key` authentication
- Connector-başına RPS sınırı
- HTTP 429 için `Retry-After` uyumlu üç denemeli backoff
- API key yokken shared public kotanın degraded olarak gösterilmesi

### Zotero

- Zotero Desktop Local API v3
- Zotero Web API v3 user/group library modu
- Collection ve tag filtreleri
- Bibliographic metadata, attachment ve Zotero-indexed full-text aktarımı
- Attachment/full-text bulunmayan bibliographic item'ın metadata-only source olarak
  korunması; bu kayıtların evidence extraction dışında tutulması
- Library version tabanlı incremental `since` sync
- Sync cursor'ın PostgreSQL'de kalıcı saklanması
- Kullanıcı note/annotation içeriklerinin `evidence_eligible=false` olarak ayrılması
- Yerel tam metin için genel SSRF/private-network politikasını gevşetmeyen özel acquisition
  yolu
- `GET /v1/zotero/collections`
- `POST /v1/zotero/sync`

### Akademik kimlik ve citation graph

- DOI, OpenAlex, S2, CorpusId, arXiv, PMID, PMCID, ISBN ve Zotero item key modeli
- DOI öncelikli provider-arası deduplication
- Başlık + ilk yazar + yıl fallback fingerprint'i
- Sağlayıcı ham metadata snapshot'larının tek kaynak altında korunması
- Alternatif landing/PDF location kayıtları
- PostgreSQL `source_relations` tablosu
- PostgreSQL `connector_sync_cursors` tablosu
- `GET /v1/research-runs/{id}/citation-graph`
- `GET /v1/research-runs/{id}/academic-coverage`

### Federated sıralama

- Sorgu ve connector sonuçlarına RRF rank sinyali
- DOI-temelli provider fusion
- Açık tam metin için küçük reranking artışı
- Review/meta-analysis türü için küçük reranking artışı
- Zotero priority tag için protokol kontrollü artış
- Retracted çalışma için görünür demotion
- Citation sayısı doğrudan kalite puanına dönüştürülmedi

### PaperQA2

- `AcademicEvidenceEngine` arayüzü
- Native ve PaperQA2 implementation ayrımı
- `paper-qa>=5` optional dependency grubu
- Varsayılan kapalı `PAPERQA2_ENABLED`
- Native sonucu değiştirmeyen `paperqa2_shadow` audit event'i
- Paket kurulu değilse açık health/audit mesajı

## API ve protokol değişiklikleri

Connector selection'a:

- `zotero_collections`
- `zotero_tags`
- `citation_depth`

alanları eklendi.

Yeni örnek protokol:

`examples/protocol_academic_zotero.yaml`

## Güvenlik değerlendirmesi

- Genel acquisition yalnız public HTTP/HTTPS ve standart port politikasını korur.
- Zotero Local API için kullanıcı tarafından değiştirilen rastgele localhost URL'lerine
  genel izin verilmez.
- Yalnız `zotero_local` connector'ının API üzerinden aldığı inline full-text, acquisition
  zincirine güvenilir transport kaynağı olarak girer.
- Zotero notları bilimsel kaynak pasajı olarak claim extraction'a alınmaz.
- API anahtarları yalnız environment üzerinden okunur ve çıktı dosyalarına yazılmaz.
- Zotero entegrasyonu salt okunurdur; kütüphaneye geri yazma uygulanmamıştır.

## Test sonucu

Fixture ve entegrasyon testleri şunları doğrular:

- OpenAlex abstract ve DOI normalizasyonu
- OpenAlex citation metadata
- Semantic Scholar search, kimlik çözümleme ve iki yönlü citation traversal
- Semantic Scholar 429 retry/backoff
- Zotero Local API sağlık, item, child attachment ve full-text akışı
- Zotero note'larının evidence dışı işaretlenmesi
- Aynı DOI'nin OpenAlex ve S2 provider snapshot'larıyla tek source'a birleşmesi
- Provider'a özgü citation edge'lerin korunması
- Mevcut pipeline ve API regresyon testleri

Canlı ortam smoke testinde:

- Migration zinciri `0004_academic_sources` head olarak doğrulandı.
- Eski `0001_initial` migration'ının güncel ORM metadata'sına bağlı olması nedeniyle temiz
  kurulumda oluşan tablo çakışması giderildi; başlangıç şeması tarihsel olarak sabitlendi.
- FastAPI sürümü `0.3.0` ve dört yeni API rotası doğrulandı.
- Yerel editable Python paket metadata'sı `research-platform 0.3.0` olarak yenilendi.
- Bu bilgisayarda Zotero Desktop Local API kapalı olduğundan gerçek kütüphane sync'i
  yapılamadı.
- OpenAlex, Semantic Scholar ve Zotero Web credential environment değerleri mevcut değildi.
- Semantic Scholar anahtarsız ortak kota çağrısı HTTP 429 döndürdü; connector buna karşı
  retry/backoff ve degraded health durumu üretmektedir.

## Kullanım için kalan yapılandırma

En az:

```env
OPENALEX_API_KEY=...
SEMANTIC_SCHOLAR_API_KEY=...
```

Yerel Zotero için Zotero Desktop açılmalı ve Local API etkin olmalıdır. Web kütüphanesi
için:

```env
ZOTERO_USER_ID=...
ZOTERO_API_KEY=...
```

veya:

```env
ZOTERO_GROUP_ID=...
ZOTERO_API_KEY=...
```

PaperQA2 istenirse:

```powershell
.\.venv\Scripts\pip.exe install -e ".[academic]"
```

ardından:

```env
PAPERQA2_ENABLED=true
PAPERQA2_SHADOW_MODE=true
```

## Sınırlamalar

- Credential olmadığı için bu teslimde gerçek OpenAlex ve authenticated S2 verisiyle
  uçtan uca canlı araştırma yapılmadı; connector davranışları dondurulmuş HTTP fixture'ları
  ile doğrulandı.
- Zotero Local API kapalı olduğu için gerçek kullanıcı kütüphanesi içeriği aktarılmadı.
- PaperQA2 varsayılan kurulumun parçası değildir ve bu teslimde native rapor üretimine
  yetki verilmemiştir.
- Citation traversal bütçeli ve seed başına sınırlıdır; tam akademik graph mirror değildir.
