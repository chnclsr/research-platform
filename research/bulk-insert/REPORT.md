# PostgreSQL Veritabanı Toplu Yazma Testi

## Amaç

Bu deney, passage kayıtlarının satır başına commit edilmesi, tek transaction içinde yazılması ve toplu yazılması arasındaki süre, throughput, WAL, I/O ve SQL çağrısı farklarını aynı veri üzerinde ölçer. Ayrıca embedding'in JSONB yerine native pgvector sütununda tutulmasının yazma maliyetine etkisini karşılaştırır.

## Test edilen mimari

Üretimdeki `PassageRow.embedding` alanı PostgreSQL `JSONB` olarak tutulmaktadır ve kolların çoğu bu şema üzerinde çalışır. Karşılaştırma için aynı sütunları taşıyan, yalnızca embedding tipi `vector(768)` olan `passages_vector` tablosu oluşturulmuş ve tek bir kol bu tabloya yazmıştır. İki tablo aynı birincil anahtar, aynı tekillik kısıtı ve aynı yardımcı indeksleri taşır, böylece aradaki tek değişken embedding tipidir.

## Deney ortamı

| Alan | Değer |
|---|---|
| Test tarihi (UTC) | 2026-08-27T11:27:43.020297+00:00 |
| İşletim sistemi | Ubuntu 22.04.5 LTS |
| CPU | Intel(R) Xeon(R) W-2145 CPU @ 3.70GHz |
| Çekirdek | 8 fiziksel, 16 mantıksal |
| RAM | 125.5 GiB |
| Python | 3.11.16 |
| PostgreSQL | PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) |
| SQLAlchemy | 2.0.52 |
| asyncpg | 0.31.0 |
| Docker | Docker version 29.7.2, build a7dcaa6 |
| Docker Compose | Docker Compose version v5.5.0 |
| Container image | `pgvector/pgvector:pg16` |
| Benchmark taban commit'i | `cc7e299e893eb6d55935a724abf33e143c23d58e` |
| Ölçüm sırasında çalışma ağacı | Değişiklik içeriyordu |
| İzole hedef | `127.0.0.1:55433/bulk_benchmark` |

Sonuçlar bu makinenin CPU, disk, kernel, Docker ve PostgreSQL koşullarına özeldir.

## Karşılaştırılan yöntemler

1. `row_commit_each`: Her satır için INSERT ve commit.
2. `row_add_one_transaction`: ORM satır eklemeleri, tek transaction ve commit.
3. `orm_add_all`: SQLAlchemy `add_all`, tek transaction ve commit.
4. `core_executemany`: SQLAlchemy Core executemany, tek transaction ve commit.
5. `core_upsert_batched`: `INSERT ... ON CONFLICT DO UPDATE`, 1,000 satırlık batch'ler, tek transaction ve commit. Repository ile aynı idempotent semantiği taşıyan tek bulk yöntem.
6. `copy_records`: asyncpg `copy_records_to_table` ile PostgreSQL COPY protokolü.
7. `repository_save_passages`: Mevcut repository yöntemi; her passage için varlık sorgusu, ORM yazımı ve sonda tek commit.
8. `vector_executemany`: 4. yöntemle aynı statement şekli, ama native pgvector sütununa yazar. Şema karşılaştırması içindir, yöntem karşılaştırması değil.
9. `core_upsert_batched_reingest`: 5. yöntemle aynı kod, ama tablo bu chunk'ları zaten tutarken çalışır. Upsert'in UPDATE dalını ölçer.
10. `repository_save_passages_reingest`: 7. yöntemle aynı kod, aynı dolu tablo üzerinde. 9. yöntemin karşılaştırma tabanı budur.

## Veri seti ve ölçüm yöntemi

Kayıt sayıları 100, 1,000, 5,000; her kayıt 512 metin karakteri ve 768 elemanlı embedding içerir. Her veri boyutu ve yöntem için 1 warm-up ile 7 ölçüm tekrarı yapılmıştır. Süre yalnızca yazma yöntemini ve commit işlemini kapsar; TRUNCATE, checkpoint, istatistik sorguları ve doğrulama ölçüm dışındadır.

## Adil karşılaştırma önlemleri

- Her yöntem ve boyutta aynı deterministik passage ve embedding verisi kullanıldı.
- Her koşudan önce her iki tablo da TRUNCATE ile aynı başlangıç durumuna getirildi, böylece JSONB kolları ile pgvector kolu aynı veritabanı durumundan başladı.
- Aynı engine, bağlantı havuzu ve session factory kullanıldı.
- 7 tekrarda yöntem sırası Latin rotasyonuyla dengelendi.
- Her veri boyutu kendi tam veri setiyle ayrıca warm-up edildi.
- Payload serileştirmesi her kolda ölçüm penceresinin içinde bırakıldı. ORM kolları parametre bağlarken serileştirir; COPY ve pgvector kolları da kendi payload'ını ölçülen bölümde üretir.
- Başarılı sayılmak için kayıt, embedding boyutu, içerik hash'i, kimlik, chunk ve NULL kontrollerinin tamamının geçmesi istendi.
- WAL doğrudan başlangıç ve bitiş LSN farkından; I/O ise ölçüm dışı checkpoint sonrası `pg_stat_io` farkından hesaplandı.
- Her `pg_stat_io` okumasından önce `pg_stat_force_next_flush()` çağrıldı ve bağlantı havuzu tek bağlantıya sabitlendi. Gerekçesi aşağıdaki ölçüm notunda açıklanmıştır.

## Ölçüm notu: pg_stat_io tahsisi

PostgreSQL backend'e özel I/O sayaçlarını paylaşılan belleğe saniyede en fazla bir kez yazar. `pg_stat_clear_snapshot()` yalnızca okuyucunun görünümünü tazeler, backend'in bekleyen sayaçlarını yayımlamaz. Bu nedenle bir saniyeden kısa süren ölçüm pencereleri kendi I/O'sunu sıfır olarak raporlar ve yükü bir sonraki pencereye taşır. Bu deneyin ilk sürümünde tam olarak bu olmuştu: bir saniyenin altında biten koşuların büyük bölümü sıfır `extends` bildirmişti, ki boş tabloya yazarken bu fiziksel olarak imkansızdır. Ölçüm penceresinin ardından aynı backend'de `pg_stat_force_next_flush()` çağrılarak ve tüm yazma işi tek bağlantıya sabitlenerek düzeltildi. Aşağıdaki I/O tablosu bu düzeltmeden sonra üretilmiştir.

## Başlangıç, bitiş ve veri bütünlüğü

| Kayıt hedefi | Ham koşu | Başlangıç aralığı | Bitiş aralığı | Geçerli koşu |
|---:|---:|---:|---:|---:|
| 100 | 70 | 0 - 100 | 100 - 100 | 70/70 |
| 1,000 | 70 | 0 - 1000 | 1,000 - 1,000 | 70/70 |
| 5,000 | 70 | 0 - 5000 | 5,000 - 5,000 | 70/70 |

## Süre ve throughput sonuçları

| Kayıt | Yöntem | Şema | Yol | Ortalama ms | Medyan ms | Min ms | Maks ms | Std sapma ms | Medyan kayıt/sn | Satır commit'e göre | Repository'ye göre |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | `row_commit_each` | JSONB | Insert | 238.103 | 253.536 | 190.695 | 264.915 | 31.827 | 394.421 | 1.000x | 1.937x |
| 100 | `row_add_one_transaction` | JSONB | Insert | 107.066 | 112.298 | 88.583 | 122.038 | 12.863 | 890.485 | 2.258x | 4.374x |
| 100 | `orm_add_all` | JSONB | Insert | 115.766 | 114.347 | 102.512 | 126.623 | 8.496 | 874.529 | 2.217x | 4.296x |
| 100 | `core_executemany` | JSONB | Insert | 107.451 | 112.180 | 92.437 | 115.055 | 9.150 | 891.428 | 2.260x | 4.379x |
| 100 | `core_upsert_batched` | JSONB | Insert | 106.309 | 106.923 | 97.711 | 116.353 | 7.164 | 935.256 | 2.371x | 4.594x |
| 100 | `copy_records` | JSONB | Insert | 98.715 | 100.012 | 83.497 | 111.848 | 10.336 | 999.880 | 2.535x | 4.911x |
| 100 | `repository_save_passages` | JSONB | Insert | 429.908 | 491.194 | 293.634 | 509.683 | 97.088 | 203.585 | 0.516x | 1.000x |
| 100 | `vector_executemany` | pgvector | Insert | 83.199 | 82.496 | 75.684 | 95.611 | 8.161 | 1,212.186 | 3.073x | 5.954x |
| 100 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 116.284 | 115.173 | 101.267 | 141.923 | 12.898 | 868.259 | - | 5.288x |
| 100 | `repository_save_passages_reingest` | JSONB | Re-ingest | 574.177 | 609.010 | 354.458 | 655.172 | 106.555 | 164.201 | - | 1.000x |
| 1,000 | `row_commit_each` | JSONB | Insert | 2,261.919 | 2,380.706 | 1,780.286 | 2,472.628 | 273.467 | 420.044 | 1.000x | 1.359x |
| 1,000 | `row_add_one_transaction` | JSONB | Insert | 865.644 | 866.592 | 822.000 | 923.308 | 30.291 | 1,153.946 | 2.747x | 3.733x |
| 1,000 | `orm_add_all` | JSONB | Insert | 856.783 | 866.127 | 825.130 | 869.045 | 15.931 | 1,154.565 | 2.749x | 3.735x |
| 1,000 | `core_executemany` | JSONB | Insert | 785.955 | 772.868 | 768.971 | 850.061 | 29.143 | 1,293.882 | 3.080x | 4.186x |
| 1,000 | `core_upsert_batched` | JSONB | Insert | 795.710 | 792.243 | 768.841 | 844.245 | 23.782 | 1,262.238 | 3.005x | 4.084x |
| 1,000 | `copy_records` | JSONB | Insert | 750.688 | 754.176 | 736.133 | 766.097 | 10.757 | 1,325.951 | 3.157x | 4.290x |
| 1,000 | `repository_save_passages` | JSONB | Insert | 3,768.656 | 3,235.369 | 2,852.185 | 5,192.719 | 1,001.251 | 309.084 | 0.736x | 1.000x |
| 1,000 | `vector_executemany` | pgvector | Insert | 578.536 | 588.236 | 556.490 | 591.008 | 14.933 | 1,699.997 | 4.047x | 5.500x |
| 1,000 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 843.242 | 835.666 | 818.971 | 909.071 | 29.797 | 1,196.650 | - | 6.907x |
| 1,000 | `repository_save_passages_reingest` | JSONB | Re-ingest | 5,318.963 | 5,771.933 | 3,310.082 | 6,650.231 | 1,239.437 | 173.252 | - | 1.000x |
| 5,000 | `row_commit_each` | JSONB | Insert | 10,948.454 | 10,923.033 | 10,355.523 | 11,907.614 | 595.233 | 457.748 | 1.000x | 2.087x |
| 5,000 | `row_add_one_transaction` | JSONB | Insert | 4,327.242 | 4,330.915 | 4,293.068 | 4,348.574 | 16.835 | 1,154.490 | 2.522x | 5.264x |
| 5,000 | `orm_add_all` | JSONB | Insert | 4,267.815 | 4,304.707 | 4,120.191 | 4,343.174 | 91.620 | 1,161.519 | 2.537x | 5.297x |
| 5,000 | `core_executemany` | JSONB | Insert | 3,842.591 | 3,775.694 | 3,735.012 | 3,963.023 | 105.676 | 1,324.260 | 2.893x | 6.039x |
| 5,000 | `core_upsert_batched` | JSONB | Insert | 3,966.289 | 3,936.481 | 3,758.742 | 4,144.477 | 133.436 | 1,270.170 | 2.775x | 5.792x |
| 5,000 | `copy_records` | JSONB | Insert | 3,563.138 | 3,567.338 | 3,527.737 | 3,580.650 | 16.718 | 1,401.605 | 3.062x | 6.391x |
| 5,000 | `repository_save_passages` | JSONB | Insert | 20,331.177 | 22,799.903 | 9,348.459 | 24,847.420 | 5,627.530 | 219.299 | 0.479x | 1.000x |
| 5,000 | `vector_executemany` | pgvector | Insert | 2,799.515 | 2,802.743 | 2,767.087 | 2,828.430 | 23.541 | 1,783.967 | 3.897x | 8.135x |
| 5,000 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 4,168.727 | 4,113.714 | 4,090.527 | 4,277.912 | 84.985 | 1,215.447 | - | 6.584x |
| 5,000 | `repository_save_passages_reingest` | JSONB | Re-ingest | 25,573.251 | 27,084.744 | 18,833.642 | 31,580.626 | 5,072.823 | 184.606 | - | 1.000x |

`repository_save_passages` idempotent upsert semantiği çalıştırır, ama 1-4. ve 6. yöntemler düz insert yapar. Bu kollara göre hesaplanan hızlanma bu nedenle yöntem farkının yanında semantik farkı da içerir. Semantiği eşit olan tek karşılaştırma `core_upsert_batched` ile `repository_save_passages` arasındakidir.

![Medyan süre](assets/wall_time.svg)

![Medyan throughput](assets/throughput.svg)

![Repository yöntemine göre hızlanma](assets/speedup_vs_repository.svg)

## İstemci tarafı serileştirme tavanı

Her yöntem, PostgreSQL tek bayt görmeden önce embedding'i aktarım biçimine çevirmek zorundadır. Bu maliyet veritabanından bağımsızdır ve hiçbir yazma yöntemi bunu ortadan kaldıramaz, dolayısıyla ulaşılabilir en iyi süreyi sınırlar.

| Kayıt | JSON serileştirme ms | pgvector literal ms | En hızlı JSONB kolu ms | Serileştirmenin payı |
|---:|---:|---:|---:|---:|
| 100 | 26.524 | 35.373 | 100.012 (`copy_records`) | 26.5% |
| 1,000 | 267.901 | 357.793 | 754.176 (`copy_records`) | 35.5% |
| 5,000 | 1,351.067 | 1,797.602 | 3,567.338 (`copy_records`) | 37.9% |

## Re-ingest: upsert'in UPDATE dalı

Yukarıdaki kolların tamamı boş tabloya yazar. Üretimde bir belge yeniden işlendiğinde aynı `(source_version_id, chunk_index)` çiftleri tabloda zaten vardır ve `ON CONFLICT DO UPDATE` INSERT dalını değil UPDATE dalını çalıştırır. Bu bölümdeki iki kol, tablo bu chunk'ları farklı içerikle tutarken çalışır; önceden doldurma ölçüm dışındadır. Her koşuda satırların gerçekten üzerine yazıldığı doğrulanır.

| Kayıt | Medyan ms, mevcut yöntem | Medyan ms, batch upsert | Hızlanma | Insert yoluna göre upsert maliyeti | WAL MiB, mevcut | WAL MiB, upsert |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 609.010 | 115.173 | 5.288x | +7.7% | 0.831 | 0.836 |
| 1,000 | 5,771.933 | 835.666 | 6.907x | +5.5% | 8.269 | 8.323 |
| 5,000 | 27,084.744 | 4,113.714 | 6.584x | +4.5% | 41.330 | 41.597 |

## WAL, boyut ve I/O sonuçları

| Kayıt | Yöntem | Şema | Yol | Medyan WAL MiB | Heap artışı MiB | İndeks artışı MiB | TOAST ve yardımcı MiB | Toplam artış MiB | I/O yazma | I/O yazma ms | Extend | Extend ms | Fsync | Fsync ms |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | `row_commit_each` | JSONB | Insert | 0.428 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.371 | 63 | 0.828 | 12 | 1.723 |
| 100 | `row_add_one_transaction` | JSONB | Insert | 0.422 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.331 | 63 | 0.726 | 12 | 1.870 |
| 100 | `orm_add_all` | JSONB | Insert | 0.423 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.331 | 63 | 0.732 | 12 | 2.042 |
| 100 | `core_executemany` | JSONB | Insert | 0.422 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.326 | 63 | 0.717 | 12 | 1.869 |
| 100 | `core_upsert_batched` | JSONB | Insert | 0.427 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.318 | 63 | 0.710 | 12 | 1.843 |
| 100 | `copy_records` | JSONB | Insert | 0.419 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.361 | 63 | 0.296 | 12 | 1.877 |
| 100 | `repository_save_passages` | JSONB | Insert | 0.422 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.474 | 63 | 1.866 | 12 | 1.799 |
| 100 | `vector_executemany` | pgvector | Insert | 0.444 | 0.094 | 0.047 | 0.445 | 0.586 | 80 | 0.396 | 75 | 1.003 | 12 | 1.835 |
| 100 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 0.836 | 0.086 | 0.016 | 0.289 | 0.391 | 109 | 0.476 | 50 | 0.595 | 9 | 2.339 |
| 100 | `repository_save_passages_reingest` | JSONB | Re-ingest | 0.831 | 0.086 | 0.016 | 0.289 | 0.391 | 109 | 0.633 | 50 | 1.810 | 9 | 2.079 |
| 1,000 | `row_commit_each` | JSONB | Insert | 4.281 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.311 | 532 | 7.256 | 12 | 2.288 |
| 1,000 | `row_add_one_transaction` | JSONB | Insert | 4.243 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.043 | 532 | 4.354 | 12 | 2.077 |
| 1,000 | `orm_add_all` | JSONB | Insert | 4.244 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.027 | 532 | 4.354 | 12 | 2.274 |
| 1,000 | `core_executemany` | JSONB | Insert | 4.245 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.018 | 532 | 4.323 | 12 | 2.395 |
| 1,000 | `core_upsert_batched` | JSONB | Insert | 4.288 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.029 | 532 | 4.507 | 12 | 2.327 |
| 1,000 | `copy_records` | JSONB | Insert | 4.203 | 1.000 | 0.250 | 3.031 | 4.281 | 539 | 2.373 | 548 | 2.205 | 12 | 2.011 |
| 1,000 | `repository_save_passages` | JSONB | Insert | 4.243 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.888 | 532 | 14.301 | 12 | 2.325 |
| 1,000 | `vector_executemany` | pgvector | Insert | 4.493 | 0.875 | 0.250 | 4.008 | 5.133 | 661 | 2.533 | 657 | 4.417 | 12 | 2.136 |
| 1,000 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 8.323 | 0.867 | 0.242 | 2.969 | 4.078 | 1,046 | 4.542 | 522 | 4.843 | 9 | 1.571 |
| 1,000 | `repository_save_passages_reingest` | JSONB | Re-ingest | 8.269 | 0.867 | 0.242 | 2.969 | 4.078 | 1,046 | 5.862 | 522 | 18.880 | 9 | 1.632 |
| 5,000 | `row_commit_each` | JSONB | Insert | 21.402 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 13.584 | 2,605 | 33.297 | 12 | 2.581 |
| 5,000 | `row_add_one_transaction` | JSONB | Insert | 21.210 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 12.790 | 2,605 | 21.336 | 12 | 2.440 |
| 5,000 | `orm_add_all` | JSONB | Insert | 21.211 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 11.824 | 2,605 | 20.923 | 12 | 2.619 |
| 5,000 | `core_executemany` | JSONB | Insert | 21.211 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 11.729 | 2,605 | 21.125 | 12 | 2.427 |
| 5,000 | `core_upsert_batched` | JSONB | Insert | 21.440 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 12.156 | 2,605 | 22.183 | 12 | 2.496 |
| 5,000 | `copy_records` | JSONB | Insert | 21.009 | 4.500 | 1.086 | 14.922 | 20.508 | 2,613 | 13.262 | 2,625 | 10.854 | 12 | 2.016 |
| 5,000 | `repository_save_passages` | JSONB | Insert | 21.210 | 4.344 | 1.086 | 14.922 | 20.352 | 2,611 | 13.277 | 2,605 | 73.367 | 12 | 2.954 |
| 5,000 | `vector_executemany` | pgvector | Insert | 22.466 | 4.344 | 1.086 | 19.805 | 25.234 | 3,234 | 16.217 | 3,230 | 20.413 | 12 | 3.416 |
| 5,000 | `core_upsert_batched_reingest` | JSONB | Re-ingest | 41.597 | 4.344 | 1.164 | 14.859 | 20.367 | 5,184 | 29.813 | 2,607 | 24.541 | 9 | 2.767 |
| 5,000 | `repository_save_passages_reingest` | JSONB | Re-ingest | 41.330 | 4.344 | 1.164 | 14.859 | 20.367 | 5,184 | 30.184 | 2,607 | 85.002 | 9 | 2.203 |

![Medyan WAL](assets/wal_bytes.svg)

Aynı tabloya yazan kollarda kayıt içeriği aynı olduğu için heap, indeks ve toplam relation artışı da aynıdır; yöntemlerden hiçbiri daha az kalıcı veri yazmaz. Boyut ve I/O sütunları her kolun kendi hedef tablosundan okunur, bu yüzden pgvector kolunun değerleri JSONB kollarıyla doğrudan değil şema karşılaştırması olarak okunmalıdır. TOAST ve yardımcı alan, toplam relation artışından ana heap ve ana indeks artışının çıkarılmasıyla hesaplanmıştır; büyük JSONB embedding değerlerinin önemli bölümü bu alandadır.

## SQL statement ve commit sayıları

| Kayıt | Yöntem | Medyan SQL statement | Executemany | Commit |
|---:|---|---:|---:|---:|
| 100 | `row_commit_each` | 100 | 0 | 100 |
| 100 | `row_add_one_transaction` | 1 | 1 | 1 |
| 100 | `orm_add_all` | 1 | 1 | 1 |
| 100 | `core_executemany` | 1 | 1 | 1 |
| 100 | `core_upsert_batched` | 1 | 1 | 1 |
| 100 | `copy_records` | 1 | 0 | 1 |
| 100 | `repository_save_passages` | 200 | 0 | 1 |
| 100 | `vector_executemany` | 1 | 1 | 1 |
| 100 | `core_upsert_batched_reingest` | 1 | 1 | 1 |
| 100 | `repository_save_passages_reingest` | 200 | 0 | 1 |
| 1,000 | `row_commit_each` | 1,000 | 0 | 1,000 |
| 1,000 | `row_add_one_transaction` | 1 | 1 | 1 |
| 1,000 | `orm_add_all` | 1 | 1 | 1 |
| 1,000 | `core_executemany` | 1 | 1 | 1 |
| 1,000 | `core_upsert_batched` | 1 | 1 | 1 |
| 1,000 | `copy_records` | 1 | 0 | 1 |
| 1,000 | `repository_save_passages` | 2,000 | 0 | 1 |
| 1,000 | `vector_executemany` | 1 | 1 | 1 |
| 1,000 | `core_upsert_batched_reingest` | 1 | 1 | 1 |
| 1,000 | `repository_save_passages_reingest` | 2,000 | 0 | 1 |
| 5,000 | `row_commit_each` | 5,000 | 0 | 5,000 |
| 5,000 | `row_add_one_transaction` | 1 | 1 | 1 |
| 5,000 | `orm_add_all` | 1 | 1 | 1 |
| 5,000 | `core_executemany` | 1 | 1 | 1 |
| 5,000 | `core_upsert_batched` | 5 | 5 | 1 |
| 5,000 | `copy_records` | 1 | 0 | 1 |
| 5,000 | `repository_save_passages` | 10,000 | 0 | 1 |
| 5,000 | `vector_executemany` | 1 | 1 | 1 |
| 5,000 | `core_upsert_batched_reingest` | 5 | 5 | 1 |
| 5,000 | `repository_save_passages_reingest` | 10,000 | 0 | 1 |

`copy_records` SQLAlchemy cursor katmanını atladığı için statement sayısı ayrıca sayılmıştır; tek COPY protokol gidiş dönüşü bir statement olarak raporlanır.

## Bulgular

- 100 kayıtta en düşük medyan süre `copy_records` ile 100.012 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 106.923 ms ile mevcut repository yöntemine göre 4.594x, satır başına commit'e göre 2.371x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 2.19 oldu.
- 1,000 kayıtta en düşük medyan süre `copy_records` ile 754.176 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 792.243 ms ile mevcut repository yöntemine göre 4.084x, satır başına commit'e göre 3.005x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 1.83 oldu.
- 5,000 kayıtta en düşük medyan süre `copy_records` ile 3,567.338 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 3,936.481 ms ile mevcut repository yöntemine göre 5.792x, satır başına commit'e göre 2.775x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 1.84 oldu.
- `row_add_one_transaction` ile `orm_add_all`, SQLAlchemy'nin PostgreSQL insertmanyvalues/executemany yolunda tek statement ve tek commit üretmesi nedeniyle birbirine yakın sonuç verdi.
- Idempotent olmanın bedeli küçüktür: `core_upsert_batched`, çakışma çözümü yapmayan `core_executemany` ile üç boyutta da -4.7%, +2.5%, +4.3% fark verdi. Bulk yazıma geçerken repository semantiğinden vazgeçmek için ölçülmüş bir gerekçe yoktur.
- COPY protokolü beklendiği kadar ayrışmadı: `copy_records`, `core_executemany` ile arasında 10.8%, 2.4%, 5.5% fark bıraktı. Sebebi, aşağıdaki serileştirme tavanıdır; iki yöntem de aynı istemci tarafı JSON maliyetini öder ve COPY yalnızca sunucu tarafındaki farkı kazanır.
- Re-ingest yolunda kazanç korunuyor: dolu tabloya yazarken batch upsert, mevcut yönteme göre 5.29x, 6.91x, 6.58x hızlıydı. UPDATE dalı INSERT dalından pahalı (+7.7%, +5.5%, +4.5%), ama bu maliyet iki yöntemde de ortaya çıkar ve aradaki farkı kapatmıyor.
- Ölçülen en büyük tekil kazanç yöntem değil şema değişikliğinden geldi: native `vector` sütununa yazan `vector_executemany`, aynı statement şekliyle JSONB'ye yazan `core_executemany` yöntemine göre 1.36x, 1.31x, 1.35x hızlıydı. Karşılığında tablo 19%, 23%, 24% daha fazla yer kapladı, çünkü pgvector değerleri JSONB gibi TOAST sıkıştırmasından yararlanmaz.
- Satır başına commit WAL'ı yaklaşık yüzde 1 artırdı; asıl fark süre, statement ve commit sayısında oluştu. Bulk yazımın gerekçesi depolama tasarrufu değildir.
- Mevcut repository yöntemi kayıt başına bir SELECT ve autoflush kaynaklı bir INSERT üretti. Bu nedenle statement sayısı `2N`, commit sayısı 1 oldu.
- Repository sürelerinin standart sapması diğer yöntemlerden yüksektir. Bu yöntem için ortalama yerine medyan karar metriği olarak daha dayanıklıdır.

## Mevcut repository yönteminin darboğazı

`save_passages`, her passage için `(source_version_id, chunk_index)` varlık sorgusu çalıştırır. Session autoflush davranışı önceki bekleyen INSERT'i sonraki SELECT öncesinde gönderir. Sonuçta N kayıt için 2N ağ gidiş dönüşü oluşur. Tek commit kullanılması WAL ve commit maliyetini sınırlar, fakat sorgu sayısını sınırlamaz. `INSERT ... ON CONFLICT DO UPDATE` aynı idempotent sonucu batch başına tek statement ile üretir.

## Güvenilirlik sınırları

- Sonuçlar tek bir makine ve tek container üzerinde alınmıştır.
- Re-ingest kollarında tablo, ölçüm dışında kalan bir dolum adımıyla hazırlanır. Bu satırlar taze yazıldığı için üretimdeki bir tablonun parçalanma ve autovacuum durumunu birebir temsil etmez.
- Her hücrede 7 ölçüm vardır; özellikle repository yönteminde yüksek varyans gözlendi.
- `pg_stat_io` checkpoint ile fiziksel yazmaya zorlanmış ve her okumadan önce flush edilmiştir, ancak kernel ve depolama katmanı zamanlaması tamamen ayrıştırılamaz.
- Re-ingest kolları tek geçişte tüm satırların çakıştığı durumu ölçer. Kısmen çakışan bir batch, yani bir belgenin bazı chunk'larının değişip bazılarının eklendiği durum, ayrıca ölçülmemiştir.
- Eşzamanlı yazarlar, lock contention, bağlantı kaybı ve transaction retry davranışı bu matriste yoktur.
- pgvector kolu yalnızca yazma maliyetini ölçer. HNSW veya IVFFlat vektör indeksi oluşturulmamıştır; indeksli bir tabloda yazma maliyeti belirgin biçimde artar.
- pgvector'e COPY protokolüyle yazmak asyncpg için binary codec gerektirdiğinden bu matriste yoktur.

## Üretim önerisi

Ölçülen yazma yolu için bulk yazım uygulanması gerekçelidir ve önerilen yöntem `core_upsert_batched`, yani 1,000 satırlık batch'lerle `INSERT ... ON CONFLICT DO UPDATE`. Bu yöntem repository'nin idempotent güncelleme semantiğini korur ve ölçülen tek eşdeğer semantikli bulk yoldur. `copy_records` daha hızlı olabilir fakat çakışma çözümü sunmaz; upsert gerektiren bir yolda ancak geçici tabloya COPY ve ardından tek MERGE ile kullanılabilir, bu da bu deneyin dışındadır.

Uygulama öncesinde şu regresyon ve güvenlik kontrolleri gereklidir:

- Yeni ve mevcut passage karışımında alanların doğru insert/update edilmesi.
- Tekrarlanan kimlik ile `(source_version_id, chunk_index)` çakışmalarının davranışı.
- Batch ortasında hata olduğunda transaction rollback ve tekrar deneme güvenliği.
- Büyük batch'lerde statement boyutu, bellek kullanımı ve PostgreSQL parametre sınırı.
- Eşzamanlı writer, deadlock ve lock süresi testleri.
- SQLite kullanılan test ortamı ile PostgreSQL davranış farkları.
- Mevcut repository yetkilendirme ve audit beklentilerinin korunması.

## Yeniden çalıştırma

```bash
docker compose -f research/bulk-insert/compose.yml up -d --wait postgres
PYTHONPATH=src .venv311/bin/python scripts/benchmark_bulk_insert.py \
  --sizes 100 1000 5000 --repeats 7 --warmups 1 \
  --dimensions 768 --text-chars 512 --upsert-batch 1000 \
  --output research/bulk-insert/results/postgres_bulk_insert.json
PYTHONPATH=src .venv311/bin/python scripts/report_bulk_insert.py
```

Ham sonuç: `results/postgres_bulk_insert.json`

Özet CSV: `results/postgres_bulk_insert_summary.csv`

## Sonuç ve karar

Bu makinede embedding içeren yazma yükü için tek transaction toplu yazım açık biçimde daha hızlıdır. Repository ile aynı idempotent semantiği taşıyan `core_upsert_batched`, mevcut repository yöntemine göre medyan sürede 4.594x, 4.084x, 5.792x hızlanma sağlamıştır. WAL ve nihai tablo boyutu kazancı küçük olduğundan üretim gerekçesi depolama azalması değil, ağ gidiş dönüşü ve transaction maliyetinin azaltılmasıdır. Kazancın bir tavanı vardır: en hızlı kolun süresinin kayda değer bir bölümü istemci tarafı embedding serileştirmesidir ve bunu hiçbir yazma yöntemi düşürmez. Native pgvector sütunu bu tavanı sunucu tarafında düşürür, karşılığında disk kullanımını artırır; bu ayrı bir şema kararıdır ve bu deneyin kapsamı dışındadır. Önerilen karar, idempotent upsert semantiği ve batch sınırları korunarak bulk repository yolu eklemektir.

Bu rapor `postgres_bulk_insert.json` dosyasındaki ölçümlerden yeniden üretilebilir.
