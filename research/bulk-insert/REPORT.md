# PostgreSQL Veritabanı Toplu Yazma Testi

## Amaç

Bu deney, passage kayıtlarının satır başına commit edilmesi, tek transaction içinde yazılması ve toplu yazılması arasındaki süre, throughput, WAL, I/O ve SQL çağrısı farklarını aynı veri üzerinde ölçer. Ayrıca embedding'in JSONB yerine native pgvector sütununda tutulmasının yazma maliyetine etkisini karşılaştırır.

## Test edilen mimari

Üretimdeki `PassageRow.embedding` alanı PostgreSQL `JSONB` olarak tutulmaktadır ve kolların çoğu bu şema üzerinde çalışır. Karşılaştırma için aynı sütunları taşıyan, yalnızca embedding tipi `vector(768)` olan `passages_vector` tablosu oluşturulmuş ve tek bir kol bu tabloya yazmıştır. İki tablo aynı birincil anahtar, aynı tekillik kısıtı ve aynı yardımcı indeksleri taşır, böylece aradaki tek değişken embedding tipidir.

## Deney ortamı

| Alan | Değer |
|---|---|
| Test tarihi (UTC) | 2026-08-27T10:55:17.661851+00:00 |
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
| Benchmark taban commit'i | `3404703adbb9bd3d536e4bd5f259167e5442413f` |
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
| 100 | 56 | 0 - 0 | 100 - 100 | 56/56 |
| 1,000 | 56 | 0 - 0 | 1,000 - 1,000 | 56/56 |
| 5,000 | 56 | 0 - 0 | 5,000 - 5,000 | 56/56 |

## Süre ve throughput sonuçları

| Kayıt | Yöntem | Şema | Ortalama ms | Medyan ms | Min ms | Maks ms | Std sapma ms | Medyan kayıt/sn | Satır commit'e göre | Repository'ye göre |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | `row_commit_each` | JSONB | 240.340 | 236.122 | 219.526 | 262.851 | 15.144 | 423.509 | 1.000x | 0.760x |
| 100 | `row_add_one_transaction` | JSONB | 108.217 | 113.064 | 83.269 | 121.133 | 12.307 | 884.458 | 2.088x | 1.588x |
| 100 | `orm_add_all` | JSONB | 107.543 | 106.955 | 84.473 | 147.997 | 21.031 | 934.973 | 2.208x | 1.679x |
| 100 | `core_executemany` | JSONB | 92.137 | 97.813 | 76.860 | 107.094 | 12.530 | 1,022.362 | 2.414x | 1.836x |
| 100 | `core_upsert_batched` | JSONB | 97.531 | 99.550 | 79.030 | 112.724 | 13.639 | 1,004.524 | 2.372x | 1.804x |
| 100 | `copy_records` | JSONB | 92.434 | 94.899 | 72.083 | 109.328 | 14.974 | 1,053.748 | 2.488x | 1.892x |
| 100 | `repository_save_passages` | JSONB | 275.822 | 179.566 | 173.305 | 463.307 | 128.063 | 556.898 | 1.315x | 1.000x |
| 100 | `vector_executemany` | pgvector | 81.214 | 85.023 | 58.108 | 92.490 | 11.530 | 1,176.159 | 2.777x | 2.112x |
| 1,000 | `row_commit_each` | JSONB | 2,412.796 | 2,460.167 | 2,099.971 | 2,495.457 | 139.157 | 406.476 | 1.000x | 1.862x |
| 1,000 | `row_add_one_transaction` | JSONB | 872.875 | 866.111 | 845.844 | 925.833 | 24.856 | 1,154.587 | 2.840x | 5.289x |
| 1,000 | `orm_add_all` | JSONB | 870.296 | 866.175 | 848.635 | 927.900 | 26.812 | 1,154.501 | 2.840x | 5.289x |
| 1,000 | `core_executemany` | JSONB | 778.571 | 781.984 | 765.539 | 786.320 | 8.634 | 1,278.799 | 3.146x | 5.858x |
| 1,000 | `core_upsert_batched` | JSONB | 794.106 | 790.889 | 773.205 | 832.869 | 18.492 | 1,264.400 | 3.111x | 5.792x |
| 1,000 | `copy_records` | JSONB | 742.573 | 737.086 | 732.712 | 754.193 | 9.801 | 1,356.694 | 3.338x | 6.215x |
| 1,000 | `repository_save_passages` | JSONB | 4,322.470 | 4,580.879 | 2,849.016 | 5,062.589 | 853.897 | 218.299 | 0.537x | 1.000x |
| 1,000 | `vector_executemany` | pgvector | 583.714 | 586.305 | 568.864 | 590.877 | 8.328 | 1,705.597 | 4.196x | 7.813x |
| 5,000 | `row_commit_each` | JSONB | 11,109.105 | 11,186.134 | 9,591.116 | 12,269.219 | 926.275 | 446.982 | 1.000x | 2.191x |
| 5,000 | `row_add_one_transaction` | JSONB | 4,246.551 | 4,249.452 | 4,228.459 | 4,266.821 | 14.941 | 1,176.622 | 2.632x | 5.767x |
| 5,000 | `orm_add_all` | JSONB | 4,222.342 | 4,235.438 | 4,119.256 | 4,258.805 | 46.581 | 1,180.515 | 2.641x | 5.786x |
| 5,000 | `core_executemany` | JSONB | 3,803.496 | 3,761.553 | 3,747.056 | 3,876.369 | 61.950 | 1,329.238 | 2.974x | 6.515x |
| 5,000 | `core_upsert_batched` | JSONB | 3,948.497 | 3,933.403 | 3,913.134 | 4,065.206 | 52.463 | 1,271.164 | 2.844x | 6.230x |
| 5,000 | `copy_records` | JSONB | 3,582.523 | 3,564.735 | 3,546.058 | 3,694.177 | 50.669 | 1,402.629 | 3.138x | 6.874x |
| 5,000 | `repository_save_passages` | JSONB | 24,856.833 | 24,505.568 | 10,428.885 | 38,001.373 | 10,039.637 | 204.035 | 0.456x | 1.000x |
| 5,000 | `vector_executemany` | pgvector | 2,821.386 | 2,824.555 | 2,782.249 | 2,875.508 | 30.402 | 1,770.190 | 3.960x | 8.676x |

`repository_save_passages` idempotent upsert semantiği çalıştırır, ama 1-4. ve 6. yöntemler düz insert yapar. Bu kollara göre hesaplanan hızlanma bu nedenle yöntem farkının yanında semantik farkı da içerir. Semantiği eşit olan tek karşılaştırma `core_upsert_batched` ile `repository_save_passages` arasındakidir.

![Medyan süre](assets/wall_time.svg)

![Medyan throughput](assets/throughput.svg)

![Repository yöntemine göre hızlanma](assets/speedup_vs_repository.svg)

## İstemci tarafı serileştirme tavanı

Her yöntem, PostgreSQL tek bayt görmeden önce embedding'i aktarım biçimine çevirmek zorundadır. Bu maliyet veritabanından bağımsızdır ve hiçbir yazma yöntemi bunu ortadan kaldıramaz, dolayısıyla ulaşılabilir en iyi süreyi sınırlar.

| Kayıt | JSON serileştirme ms | pgvector literal ms | En hızlı JSONB kolu ms | Serileştirmenin payı |
|---:|---:|---:|---:|---:|
| 100 | 26.634 | 35.340 | 94.899 (`copy_records`) | 28.1% |
| 1,000 | 267.935 | 356.196 | 737.086 (`copy_records`) | 36.4% |
| 5,000 | 1,346.758 | 1,800.248 | 3,564.735 (`copy_records`) | 37.8% |

## WAL, boyut ve I/O sonuçları

| Kayıt | Yöntem | Şema | Medyan WAL MiB | Heap artışı MiB | İndeks artışı MiB | TOAST ve yardımcı MiB | Toplam artış MiB | I/O yazma | I/O yazma ms | Extend | Extend ms | Fsync | Fsync ms |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | `row_commit_each` | JSONB | 0.426 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.306 | 63 | 0.734 | 12 | 1.873 |
| 100 | `row_add_one_transaction` | JSONB | 0.421 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.222 | 63 | 0.624 | 12 | 2.017 |
| 100 | `orm_add_all` | JSONB | 0.423 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.221 | 63 | 0.602 | 12 | 1.926 |
| 100 | `core_executemany` | JSONB | 0.420 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.210 | 63 | 0.525 | 12 | 1.812 |
| 100 | `core_upsert_batched` | JSONB | 0.429 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.211 | 63 | 0.665 | 12 | 1.874 |
| 100 | `copy_records` | JSONB | 0.419 | 0.094 | 0.047 | 0.352 | 0.492 | 68 | 0.234 | 63 | 0.285 | 12 | 1.830 |
| 100 | `repository_save_passages` | JSONB | 0.420 | 0.094 | 0.047 | 0.352 | 0.492 | 69 | 0.320 | 63 | 0.676 | 12 | 1.958 |
| 100 | `vector_executemany` | pgvector | 0.446 | 0.094 | 0.047 | 0.445 | 0.586 | 79 | 0.258 | 75 | 1.010 | 12 | 1.957 |
| 1,000 | `row_commit_each` | JSONB | 4.281 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.148 | 532 | 6.991 | 12 | 2.332 |
| 1,000 | `row_add_one_transaction` | JSONB | 4.243 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.088 | 532 | 4.271 | 12 | 2.360 |
| 1,000 | `orm_add_all` | JSONB | 4.244 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.025 | 532 | 4.264 | 12 | 2.286 |
| 1,000 | `core_executemany` | JSONB | 4.242 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.041 | 532 | 4.258 | 12 | 2.279 |
| 1,000 | `core_upsert_batched` | JSONB | 4.290 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.005 | 532 | 4.371 | 12 | 2.253 |
| 1,000 | `copy_records` | JSONB | 4.203 | 1.000 | 0.250 | 3.031 | 4.281 | 539 | 2.365 | 548 | 2.227 | 12 | 2.079 |
| 1,000 | `repository_save_passages` | JSONB | 4.243 | 0.875 | 0.250 | 3.031 | 4.156 | 537 | 2.945 | 532 | 17.457 | 12 | 2.177 |
| 1,000 | `vector_executemany` | pgvector | 4.492 | 0.875 | 0.250 | 4.008 | 5.133 | 661 | 2.483 | 657 | 4.384 | 12 | 2.151 |
| 5,000 | `row_commit_each` | JSONB | 21.399 | 4.344 | 1.086 | 14.922 | 20.352 | 2,610 | 12.640 | 2,605 | 35.175 | 12 | 3.316 |
| 5,000 | `row_add_one_transaction` | JSONB | 21.210 | 4.344 | 1.086 | 14.922 | 20.352 | 2,610 | 13.172 | 2,605 | 20.656 | 12 | 3.706 |
| 5,000 | `orm_add_all` | JSONB | 21.212 | 4.344 | 1.086 | 14.922 | 20.352 | 2,610 | 11.779 | 2,605 | 20.967 | 12 | 4.022 |
| 5,000 | `core_executemany` | JSONB | 21.208 | 4.344 | 1.086 | 14.922 | 20.352 | 2,610 | 13.551 | 2,605 | 20.703 | 12 | 3.528 |
| 5,000 | `core_upsert_batched` | JSONB | 21.440 | 4.344 | 1.086 | 14.922 | 20.352 | 2,610 | 12.485 | 2,605 | 22.049 | 12 | 3.881 |
| 5,000 | `copy_records` | JSONB | 21.005 | 4.500 | 1.086 | 14.922 | 20.508 | 2,612 | 14.289 | 2,625 | 11.079 | 12 | 2.930 |
| 5,000 | `repository_save_passages` | JSONB | 21.268 | 4.344 | 1.086 | 14.930 | 20.359 | 2,620 | 14.091 | 2,605 | 88.503 | 14 | 3.317 |
| 5,000 | `vector_executemany` | pgvector | 22.466 | 4.344 | 1.086 | 19.805 | 25.234 | 3,234 | 17.392 | 3,230 | 20.364 | 12 | 3.271 |

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
| 1,000 | `row_commit_each` | 1,000 | 0 | 1,000 |
| 1,000 | `row_add_one_transaction` | 1 | 1 | 1 |
| 1,000 | `orm_add_all` | 1 | 1 | 1 |
| 1,000 | `core_executemany` | 1 | 1 | 1 |
| 1,000 | `core_upsert_batched` | 1 | 1 | 1 |
| 1,000 | `copy_records` | 1 | 0 | 1 |
| 1,000 | `repository_save_passages` | 2,000 | 0 | 1 |
| 1,000 | `vector_executemany` | 1 | 1 | 1 |
| 5,000 | `row_commit_each` | 5,000 | 0 | 5,000 |
| 5,000 | `row_add_one_transaction` | 1 | 1 | 1 |
| 5,000 | `orm_add_all` | 1 | 1 | 1 |
| 5,000 | `core_executemany` | 1 | 1 | 1 |
| 5,000 | `core_upsert_batched` | 5 | 5 | 1 |
| 5,000 | `copy_records` | 1 | 0 | 1 |
| 5,000 | `repository_save_passages` | 10,000 | 0 | 1 |
| 5,000 | `vector_executemany` | 1 | 1 | 1 |

`copy_records` SQLAlchemy cursor katmanını atladığı için statement sayısı ayrıca sayılmıştır; tek COPY protokol gidiş dönüşü bir statement olarak raporlanır.

## Bulgular

- 100 kayıtta en düşük medyan süre `copy_records` ile 94.899 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 99.550 ms ile mevcut repository yöntemine göre 1.804x, satır başına commit'e göre 2.372x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 1.62 oldu.
- 1,000 kayıtta en düşük medyan süre `copy_records` ile 737.086 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 790.889 ms ile mevcut repository yöntemine göre 5.792x, satır başına commit'e göre 3.111x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 1.83 oldu.
- 5,000 kayıtta en düşük medyan süre `copy_records` ile 3,564.735 ms ölçüldü. Semantiği repository ile eşleşen `core_upsert_batched` 3,933.403 ms ile mevcut repository yöntemine göre 6.230x, satır başına commit'e göre 2.844x hızlandı. En hızlı kolun satır başına commit'e göre medyan WAL azalması yüzde 1.84 oldu.
- `row_add_one_transaction` ile `orm_add_all`, SQLAlchemy'nin PostgreSQL insertmanyvalues/executemany yolunda tek statement ve tek commit üretmesi nedeniyle birbirine yakın sonuç verdi.
- Idempotent olmanın bedeli küçüktür: `core_upsert_batched`, çakışma çözümü yapmayan `core_executemany` ile üç boyutta da +1.8%, +1.1%, +4.6% fark verdi. Bulk yazıma geçerken repository semantiğinden vazgeçmek için ölçülmüş bir gerekçe yoktur.
- COPY protokolü beklendiği kadar ayrışmadı: `copy_records`, `core_executemany` ile arasında 3.0%, 5.7%, 5.2% fark bıraktı. Sebebi, aşağıdaki serileştirme tavanıdır; iki yöntem de aynı istemci tarafı JSON maliyetini öder ve COPY yalnızca sunucu tarafındaki farkı kazanır.
- Ölçülen en büyük tekil kazanç yöntem değil şema değişikliğinden geldi: native `vector` sütununa yazan `vector_executemany`, aynı statement şekliyle JSONB'ye yazan `core_executemany` yöntemine göre 1.15x, 1.33x, 1.33x hızlıydı. Karşılığında tablo 19%, 23%, 24% daha fazla yer kapladı, çünkü pgvector değerleri JSONB gibi TOAST sıkıştırmasından yararlanmaz.
- Satır başına commit WAL'ı yaklaşık yüzde 1 artırdı; asıl fark süre, statement ve commit sayısında oluştu. Bulk yazımın gerekçesi depolama tasarrufu değildir.
- Mevcut repository yöntemi kayıt başına bir SELECT ve autoflush kaynaklı bir INSERT üretti. Bu nedenle statement sayısı `2N`, commit sayısı 1 oldu.
- Repository sürelerinin standart sapması diğer yöntemlerden yüksektir. Bu yöntem için ortalama yerine medyan karar metriği olarak daha dayanıklıdır.

## Mevcut repository yönteminin darboğazı

`save_passages`, her passage için `(source_version_id, chunk_index)` varlık sorgusu çalıştırır. Session autoflush davranışı önceki bekleyen INSERT'i sonraki SELECT öncesinde gönderir. Sonuçta N kayıt için 2N ağ gidiş dönüşü oluşur. Tek commit kullanılması WAL ve commit maliyetini sınırlar, fakat sorgu sayısını sınırlamaz. `INSERT ... ON CONFLICT DO UPDATE` aynı idempotent sonucu batch başına tek statement ile üretir.

## Güvenilirlik sınırları

- Sonuçlar tek bir makine ve tek container üzerinde alınmıştır.
- Her hücrede 7 ölçüm vardır; özellikle repository yönteminde yüksek varyans gözlendi.
- `pg_stat_io` checkpoint ile fiziksel yazmaya zorlanmış ve her okumadan önce flush edilmiştir, ancak kernel ve depolama katmanı zamanlaması tamamen ayrıştırılamaz.
- Deney boş tabloya yazma yolunu ölçer. `core_upsert_batched` idempotent yolu kullanır, fakat çakışan kayıtların bulunduğu bir tabloya yazma senaryosu ayrıca ölçülmemiştir; UPDATE yolu INSERT yolundan pahalıdır.
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

Bu makinede embedding içeren yazma yükü için tek transaction toplu yazım açık biçimde daha hızlıdır. Repository ile aynı idempotent semantiği taşıyan `core_upsert_batched`, mevcut repository yöntemine göre medyan sürede 1.804x, 5.792x, 6.230x hızlanma sağlamıştır. WAL ve nihai tablo boyutu kazancı küçük olduğundan üretim gerekçesi depolama azalması değil, ağ gidiş dönüşü ve transaction maliyetinin azaltılmasıdır. Kazancın bir tavanı vardır: en hızlı kolun süresinin kayda değer bir bölümü istemci tarafı embedding serileştirmesidir ve bunu hiçbir yazma yöntemi düşürmez. Native pgvector sütunu bu tavanı sunucu tarafında düşürür, karşılığında disk kullanımını artırır; bu ayrı bir şema kararıdır ve bu deneyin kapsamı dışındadır. Önerilen karar, idempotent upsert semantiği ve batch sınırları korunarak bulk repository yolu eklemektir.

Bu rapor `postgres_bulk_insert.json` dosyasındaki ölçümlerden yeniden üretilebilir.
