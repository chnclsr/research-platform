# Checkpoint State Boyutu ve Ham İçerik Taşıma

Platform sürümü: `v0.9.1`

Belge sürümü: `1.0`

Tarih: `2026-08-13`

## Olay

`01KZWZKYDV3D686W9PDTFXCQJB` numaralı araştırma (`küçük modüler reaktörlerin maliyet ve
takvim riskleri`, `literature_scan`, 30 dakika bütçe) `FAILED` durumuyla kapandı.

Yüzeydeki belirti acquisition hatası gibi görünüyordu, ancak olay kaydı acquisition'ın
**başarıyla tamamlandığını** gösterdi: 85 adaydan 85'i işlendi, 68'i başarılı oldu ve
`acquisition_metrics` olayı normal biçimde yayınlandı.

Çöküş bir sonraki aşamada, NORMALIZE checkpoint'i PostgreSQL'e yazılırken oldu:

```
asyncpg.exceptions.ProgramLimitExceededError:
total size of jsonb array elements exceeds the maximum of 268435455 bytes
[SQL: INSERT INTO run_checkpoints (run_id, stage, state) VALUES (...)]
[parameters: (... 340207582 characters truncated ...)]
```

PostgreSQL jsonb üst sınırı 256 MiB'dir. Yazılmak istenen state ~324 MiB idi.

## Kök sebep

`AcquiredDocument` iki içerik alanı taşır: `content` (çıkarılmış metin) ve `raw_content`
(dokunulmamış anlık görüntü). PDF'ler için `raw_content`, dosyanın tamamının base64
kodlanmış hâlidir:

```python
raw = (
    response.text if document_type != "pdf"
    else base64.b64encode(response.content).decode("ascii")
)
```

Belge başına indirme sınırı 25 MB'dir (`max_download_bytes`) ve base64 bunu yaklaşık %33
büyütür. NORMALIZE, kaydedilen belgeleri `output["documents"]` içine olduğu gibi koyduğu
için 68 belgenin ham gövdesi LangGraph state'inde taşınıyordu. `Repository.checkpoint()`
ise state'i hiçbir boyut denetimi olmadan jsonb'ye yazar.

Bu koşuda sınırın aşılmasının nedeni, Türkçe sorgunun büyük kurumsal PDF raporlarını
getirmesiydi (`enerji.gov.tr` faaliyet raporu, Sabancı sürdürülebilirlik raporu, kalkınma
kütüphanesi strateji belgeleri).

Checkpoint boyutlarının aşama aşama büyümesi:

| Aşama | State boyutu |
|---|---|
| VALIDATE_PROTOCOL | 2.4 kB |
| DECOMPOSE | 2.4 kB |
| BUILD_QUERY_BRANCHES | 3.1 kB |
| SEARCH | 9.3 kB |
| ACQUIRE | 458 kB |
| NORMALIZE | ~324 MiB — reddedildi |

## Veri kaybı

Başarısız `INSERT` transaction'ı geri aldığı için toplanan 68 belgenin tamamı kayboldu.
Hata sonrası veritabanı durumu: `sources = 0`, `source_versions = 0`, yalnızca ACQUIRE'a
kadarki 5 checkpoint kaldı.

## Uygulanan düzeltme

`ResearchPipeline.normalize()` içinde, belge yükü state'e eklenmeden önce `raw_content`
boşaltılır:

```python
payload = document.model_dump(mode="json")
payload["raw_content"] = ""
payload["source_id"] = source.id
payload["source_version_id"] = version.id
saved_docs.append(payload)
```

Bu satıra gelindiğinde ham içerik zaten kalıcıdır:

- MinIO'ya `raw_snapshot_key` altında yazılmıştır,
- `repo.save_document()` ile `source_versions.raw_content` sütununa kaydedilmiştir.

## Neden güvenli

`raw_content`'i state'ten çıkarmanın hiçbir aşamayı bozmadığı, tüm okuma noktaları
izlenerek doğrulandı:

| Kullanım | Konum | Kaynak |
|---|---|---|
| `enrich_publication_date` | `pipeline.py:1258` | NORMALIZE içi, boşaltmadan önce |
| MinIO anlık görüntüsü | `pipeline.py:1355` | NORMALIZE içi, boşaltmadan önce |
| PDF base64 çözme | `pipeline.py:1366` | NORMALIZE içi, boşaltmadan önce |
| Figür analizi | `figure_analysis.py:220,225,406` | `repo.list_source_versions()` — veritabanı |
| Dışa aktarım | `exporter.py:471` | `version.raw_content` — veritabanı |

NORMALIZE'dan sonra `raw_content`'e ihtiyaç duyan her tüketici onu veritabanından okur;
hiçbiri pipeline state'ine bakmaz. `content` alanı state'te korunur, çünkü `chunk_index()`
pasajları doğrudan ondan üretir.

## Doğrulama

- Ruff: başarılı.
- Tam pytest paketi: `155 passed`, yalnız üçüncü taraf Starlette deprecation uyarısı.

## Bilinen sınır

Bu düzeltme state'i şişiren baskın etkeni ortadan kaldırır, ancak `Repository.checkpoint()`
hâlâ boyut denetimi yapmaz. Yeterince çok sayıda büyük metin belgesi toplandığında
yalnızca `content` alanları da 256 MiB sınırını zorlayabilir. Kalıcı çözüm, checkpoint
yazımına bir boyut koruması eklemek ve sınır aşıldığında transaction'ı geri almak yerine
toplanan veriyi koruyarak açık bir hata üretmektir.

## Operasyonel sonuç

Büyük PDF ağırlıklı bir korpus artık NORMALIZE checkpoint'ini tek başına 256 MiB sınırının
üzerine çıkarmaz. Ham anlık görüntüler MinIO ve `source_versions` üzerinden erişilebilir
kalır; figür analizi ve dışa aktarım etkilenmez.
