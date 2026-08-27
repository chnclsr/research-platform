# Bulk insert çalışması: güncel durum

Bu dosya deney raporu değildir. Teknik sonuçların kanonik kaynağı `REPORT.md`, sayısal
kaynakları ise `results/postgres_bulk_insert.json` ve
`results/postgres_bulk_insert_partial.json` dosyalarıdır.

## Son durum

- Ana matris: 10 yöntem, 3 veri boyutu, 10 tekrar, toplam 300/300 geçerli koşu.
- Kısmi çakışma matrisi: 2 yöntem, 3 veri boyutu, 10 tekrar, toplam 60/60 geçerli koşu.
- Ana matriste 10 yöntem ve 10 tekrar kullanıldığı için her yöntem her sıra pozisyonunda
  tam bir kez çalıştı.
- Re-ingest warm-up kolları ölçümden önce gerçekten dolu tablo üzerinde UPDATE yolunu
  çalıştırıyor.
- `src/research_platform/repository.py` **değiştirildi**: `save_passages` batch upsert'e
  çevrildi. Commit hazır, PR açılmadı, merge edilmedi. Mentör onayı bekleniyor.

## Ölçülen sonuç

`core_upsert_batched`, mevcut `Repository.save_passages` yoluna göre medyan sürede:

| Senaryo | 100 | 1.000 | 5.000 |
|---|---:|---:|---:|
| Boş tablo, INSERT | 4.388x | 5.495x | 5.634x |
| Tam çakışma, UPDATE | 5.411x | 6.071x | 5.646x |
| Yüzde 50 INSERT, yüzde 50 UPDATE | 2.053x | 6.106x | 5.136x |

5.000 kayıtta aday upsert 1.000 satırlık batch nedeniyle 5 SQL statement üretirken
mevcut yöntem 10.000 statement üretti. İki yol da tek commit kullandı. Kazancın ana
kaynağı kalıcı veri veya WAL azalması değil, ağ gidiş dönüşü sayısının düşmesidir.

Native pgvector kolu JSONB kolundan daha hızlı yazdı, fakat yüzde 19-24 daha fazla disk
alanı kullandı. HNSW/IVFFlat indeksli yazma ve benzerlik sorguları ölçülmediği için bu
sonuç pgvector şema değişikliği kararı değildir.

## Dosyalar

| Dosya | Rolü |
|---|---|
| `scripts/benchmark_bulk_insert.py` | Ana 10 yöntemli PostgreSQL matrisi. |
| `scripts/benchmark_partial_conflict.py` | Yüzde 50 çakışmalı ek matris. |
| `scripts/report_bulk_insert.py` | Markdown raporu, CSV'yi ve SVG grafikleri üretir. |
| `tests/test_bulk_insert_benchmark.py` | Veri, upsert sütunları, rotasyon ve rapor yardımcı testleri. |
| `src/research_platform/repository.py` | Üretim değişikliği: `save_passages` batch upsert. |
| `tests/test_passage_persistence.py` | 6 karakterizasyon + 5 entegrasyon testi (SQLite). |
| `tests/test_passage_persistence_postgres.py` | Eşzamanlı writer ve deadlock testleri (gerçek PostgreSQL, container yoksa atlanır). |
| `research/bulk-insert/REPORT.md` | İncelenecek teknik rapor. |

## Gerçek koşu doğrulaması

Entegrasyondan sonra platformun tamamı yeniden build edilip (`docker compose build worker api`)
gerçek bir araştırma koşusu çalıştırıldı: `01M11STV8YQXCFY16AQ8GSJKM3`. Gerçek LLM
(`qwen3:4b-instruct`), gerçek connector'lar, gerçek PostgreSQL. Koşu öncesi platform
veritabanı boştu (0 koşu, 0 passage), aktif koşu yoktu.

Sonuç: upsert'in **her iki dalı da üretimde çalıştı.**

| Kontrol | Sonuç |
|---|---:|
| CHUNK_INDEX'te yazılan passage | 21 |
| Embedding'i dolu olan | 21 |
| RETRIEVE_PASSAGES'ta yerinde UPDATE edilen | 9 |
| Kopya satır | 0 |

Yani INSERT dalı 21 satır yazdı, UPDATE dalı 9 satırın `retrieval_score` ve
`matched_questions` alanlarını çakışma üzerinden güncelledi, satır sayısı 21'de kaldı.

Notlar:

- Worker `arq`/Redis kuyruğu kullanıyor; veritabanına koşu satırı yazmak yetmiyor,
  `queueing.enqueue_run` ile Redis'e de bırakmak gerekiyor.
- Koşan container'lar kaynağı image'a gömüyor, bind-mount yok. Kod değişikliğinden
  sonra `docker compose build worker api` yapılmadan eski kod çalışmaya devam eder.

### Üretimde şema kayması: `json` vs `jsonb`

Koşu sırasında fark edildi, **bu çalışmadan bağımsız ve önceden var olan** bir sorun:

- `db.py` içindeki `json_type()`, PostgreSQL'de `JSONB` verir.
- `migrations/versions/0002_passages.py` sütunu düz `sa.JSON()` ile oluşturmuş.
- Üretim veritabanında `passages.embedding` ve `passages.metadata` gerçekten `json`.

Sonuçları: JSONB operatörleri (`metadata ? 'anahtar'` gibi) üretimde doğrudan
çalışmaz, `::jsonb` cast gerekir. Ayrıca bu deneyin matrisi tabloyu ORM modelinden
kurduğu için **JSONB üzerinde ölçüm yapmıştır**, üretimdeki `json` üzerinde değil.
Bulk yazımın kazancı ağ gidiş dönüşü azalmasından geldiği için sonucun yönü
etkilenmez, fakat TOAST ve sıkıştırmaya dair gözlemler ile pgvector karşılaştırması
JSONB'ye göredir. Rapora bu çekince eklenmelidir.

## Entegrasyon sonrası bulunan iki regresyon

Entegrasyondan sonra çağıran tarafları tek tek gözden geçirince, testlerin
yakalayamadığı iki davranış farkı çıktı. İkisi de önce başarısız bir testle
üretildi, sonra düzeltildi (`fix(repository): keep two behaviours...`).

**1. Boş listede commit kayboluyordu.** Eski döngü kendisine ne verilirse verilsin
sonunda `commit()` çağırıyordu. `zotero_sync` buna dayanıyor: `save_document`
yalnızca `flush()` yapıyor, dolayısıyla hiç chunk üretmeyen bir kayıtta belge
yazımı kalıcı olmuyor, transaction içinde asılı kalıyordu. Yeni kod erken
dönüyordu. Düzeltme: boş listede de commit ediliyor.

**2. Session önbelleği bayat kalıyordu.** Core seviyesindeki yazım identity map'e
dokunmuyor ve bu session'lar `expire_on_commit=False` ile kurulu. Pipeline bir
koşunun passage'larını listeliyor (satır 1954), retrieval metadata'sını
`save_passages` ile geri yazıyor (1985) ve **aynı session'da** tekrar listeliyor
(2046). O ikinci okuma yazımdan önceki nesneleri döndürüyordu, yani yeni yazılan
metadata görünmüyordu. Eski kod aynı ORM nesnelerini mutasyona uğrattığı için bu
hiç ortaya çıkmamıştı. Düzeltme: yazımdan sonra ilgili `PassageRow` örnekleri
expire ediliyor.

**Ders:** ikisini de mevcut test suite yakalamadı. Sebebi aşağıdaki kapsam boşluğu.

### Test kapsamı boşluğu

Pipeline testleri `save_passages`'ı **yalnızca boş listeyle** çağırıyor (ölçüldü:
`tests/test_pipeline.py` genelinde 1 çağrı, 0 passage). Yani dolu listeyle çalışan
yolun platform tarafında hiç kapsaması yok; tek kapsama
`tests/test_passage_persistence.py` ve `tests/test_passage_persistence_postgres.py`
içinde. `zotero_sync` için hiç test dosyası yok.

## Üretim entegrasyonu: yapıldı

`Repository.save_passages` 1.000 satırlık batch'lerle `INSERT ... ON CONFLICT DO UPDATE`
kullanıyor. Aşağıdaki yedi davranışın hepsi testlerle sabitlendi:

1. `id`, `source_version_id` ve `chunk_index` conflict UPDATE listesine girmez. ✓
2. Tüm diğer fiziksel sütunlar, `metadata` dahil, güncellenir. ✓
3. Aynı çağrıdaki yinelenen chunk'lar ilk `id` ve son içerik semantiğiyle birleşir. ✓
4. Satırlar `(source_version_id, chunk_index)` sırasına dizilir. ✓
5. Batch sınırını aşan girdide `ceil(N / 1000)` statement ve tek commit üretilir. ✓
6. Sonraki batch hata verirse önceki batch'ler de uygulanmamış kalır. ✓
7. SQLite karakterizasyon testleri ve PostgreSQL eşzamanlılık testi geçer. ✓

Altı karakterizasyon testi **değiştirilmeden** geçiyor; davranış sözleşmesi korundu.

### Kilit sırası artık varsayım değil

4. maddenin gerekliliği doğrulandı: `_passage_upsert_rows` içindeki `sorted()` geçici
olarak kaldırıldığında `tests/test_passage_persistence_postgres.py` gerçek PostgreSQL
üzerinde `DeadlockDetectedError` üretiyor. Sıralama geri konduğunda test geçiyor. Yani
bu satır bir stil tercihi değil, kaldırılırsa üretimde deadlock üreten bir önlemdir.

### Rollback sahipliği kararı

`save_passages` hata durumunda **kendisi rollback etmez**, hatayı yükseltir. Gerekçe:
metot session'ın sahibi değil ve sonunda `commit()` çağırıyor, dolayısıyla transaction
çağıranın daha önce yazdıklarını da kapsıyor; içeride rollback etmek onları da silerdi.
`pipeline.py` zaten kendi sınırında rollback ediyor. Garanti edilen şey, batch'lerden
biri hata verirse hiçbirinin uygulanmamış kalmasıdır.

### Kapsanmayanlar

Bağlantı kaybı ve üst katman retry politikası ölçülmedi ve test edilmedi. Eşzamanlı
writer throughput'u da ölçülmedi; test edilen şey doğruluk ve deadlock yokluğu.

## Yeniden çalıştırma

```bash
docker compose -f research/bulk-insert/compose.yml up -d --wait postgres
PYTHONPATH=src .venv311/bin/python scripts/benchmark_bulk_insert.py \
  --sizes 100 1000 5000 --repeats 10 --warmups 1 \
  --dimensions 768 --text-chars 512 --upsert-batch 1000 \
  --output research/bulk-insert/results/postgres_bulk_insert.json
PYTHONPATH=src .venv311/bin/python scripts/benchmark_partial_conflict.py \
  --sizes 100 1000 5000 --repeats 10 --warmups 1 \
  --dimensions 768 --text-chars 512 --upsert-batch 1000 \
  --output research/bulk-insert/results/postgres_bulk_insert_partial.json
PYTHONPATH=src .venv311/bin/python scripts/report_bulk_insert.py
```

Benchmark yalnızca `127.0.0.1:55433/bulk_benchmark` hedefini kabul eder. Başka bir
veritabanı adı, port, host veya SQLite URL'si verilirse çalışmayı reddeder.

## Provenance

Final ana koşu `a82c4b6` taban commit'i üzerinde, izlenen benchmark ve rapor geliştirme
dosyaları henüz commitlenmemişken üretildi; bu nedenle ham veride çalışma ağacı
`Değişiklik içeriyordu` olarak kayıtlıdır. Bu bayrak ölçüm geçerliliği değil, Git
çalışma ağacı durumudur. Ham sonuç dosyası 10 tekrar, 300 koşu ve 300/300 başarı için
programatik olarak doğrulandı.
