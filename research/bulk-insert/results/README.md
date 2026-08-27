# Bulk insert sonuç dosyaları

Rapor ve grafikler yalnızca `postgres_bulk_insert.json` dosyasından üretilir.

## Kanonik

- `postgres_bulk_insert.json`: Nihai deneyin ham verisi. Sekiz yöntem, üç veri boyutu,
  boyut başına kendi warm-up'ı ve 7 tekrar; toplam 168 ölçüm koşusu. Şema sürümü
  `postgres_bulk_insert_v2`.
- `postgres_bulk_insert_summary.csv`: Kanonik ham veriden yeniden üretilen 24 satırlık
  özet.

## Smoke

- `smoke.json`: 10 kayıt ve 8 embedding boyutuyla ilk bağlantı ve şema smoke testi.
- `smoke_100.json`: 100 kayıt ve 768 embedding boyutuyla ilk WAL ve I/O düzeltmesi
  sonrası smoke testi.

## Terk edilmiş koşular

Aşağıdaki iki dosya `postgres_bulk_insert_v1` düzeneğinden gelir ve **I/O sütunları
geçerli değildir.** O düzenek `pg_stat_io` sayaçlarını okumadan önce flush etmiyordu, bu
yüzden bir saniyeden kısa süren koşuların I/O'su kendi ölçüm penceresine yazılmıyordu;
ayrıntısı `../CALISMA_NOTU.md` içinde. Süre ve throughput sütunları etkilenmemiştir.
Karşılaştırma ve iz kaydı için tutuluyorlar, alıntılanmamalıdırlar.

- `postgres_bulk_insert_pre_per_size_warmup.json`: İlk tam koşu. Warm-up yalnızca en
  küçük veri setiyle yapıldığı için metodoloji kontrolünde ayrıca reddedildi.
- `postgres_bulk_insert_pre_explicit_size_metrics.json`: Her boyuta özel warm-up içeren
  ara koşu. Başlangıç/bitiş satır sayısı ile heap ve indeks artışı henüz ayrı alanlarda
  değildi.
