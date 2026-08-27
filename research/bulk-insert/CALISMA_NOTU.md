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
- `src/research_platform/repository.py` değiştirilmedi. Üretim entegrasyonu için henüz
  karar, commit, PR veya merge yapılmadı.

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
| `tests/test_passage_persistence.py` | Mevcut `save_passages` davranışını sabitleyen karakterizasyon testleri. |
| `research/bulk-insert/REPORT.md` | İncelenecek teknik rapor. |

## Üretim kararı verilirse gerekenler

Ölçümlerin işaret ettiği aday, 1.000 satırlık batch'lerle PostgreSQL/SQLite uyumlu
`INSERT ... ON CONFLICT DO UPDATE` yoludur. Uygulama yapılmadan önce aşağıdaki davranışlar
testlerle sabitlenmelidir:

1. `id`, `source_version_id` ve `chunk_index` conflict UPDATE listesine girmez.
2. Tüm diğer fiziksel sütunlar, `metadata` dahil, güncellenir.
3. Aynı çağrıdaki yinelenen chunk'lar ilk `id` ve son içerik semantiğiyle birleştirilir.
4. Satırlar `(source_version_id, chunk_index)` sırasına dizilerek eşzamanlı kilit alma
   sırası kararlı tutulur.
5. Batch sınırını aşan girdide `ceil(N / 1000)` statement ve tek commit üretilir.
6. Sonraki batch hata verirse önceki batch'ler de rollback edilir.
7. SQLite karakterizasyon testleri ile PostgreSQL eşzamanlı writer/deadlock testi geçer.

Eşzamanlı writer contention throughput'u, bağlantı kaybı ve üst katman retry politikası
performans matrisinde ölçülmedi. Bunlar entegrasyon PR'ının ayrı risk başlıklarıdır.

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
