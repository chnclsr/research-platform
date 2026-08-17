# Ofis Sunucusu Kuyruk Olayı ve Düzeltme Raporu

Belge sürümü: `1.1`

Platform sürümü: `v0.4.3`

Tarih: `2026-07-16`

## Olay

Uzak Codex istemcisi MCP bağlantısını kurmuş ve bir araştırma kaydı oluşturmuş, ancak run
`queued / INIT` durumunda kalmıştır. İptal isteği de `cancel_requested` durumundan ilerlememiştir.

Etkilenen run: `01KXNNS9AJNRVKK23VFE13EC1X`

## Kök neden

Ofis başlatma betiği PostgreSQL, Redis, MinIO ve Crawl4AI container'larını başlattıktan hemen sonra
native API ve worker süreçlerini açıyordu. Redis container'ı henüz bağlantı kabul etmiyorsa API'nin
ilk ARQ bağlantısı başarısız oluyor, fakat API çalışmaya devam ediyordu.

API bu durumda araştırma kaydını PostgreSQL'e `queued` olarak yazmasına rağmen Redis'e iş
eklemiyordu. HTTP isteği de başarılı döndüğü için uzak istemci gerçek kuyruk arızasını göremiyordu.
Worker çalışıyor, ancak kuyruğa hiç yazılmamış işi doğal olarak işleyemiyordu.

İlk canlı düzeltme testinde ikinci bir hata da ortaya çıkarıldı: worker araştırmayı işlerken kullandığı
uzun ömürlü SQLAlchemy session'ında run nesnesini identity map üzerinden eski haliyle okuyordu.
API'nin ayrı session'da yazdığı `cancel_requested` değişikliği bu nedenle düğüm sınırında
görülmüyordu.

## Uygulanan düzeltmeler

- Docker Compose başlangıcına `--wait` ve sağlık zaman aşımı eklendi.
- API Redis bağlantısına kontrollü yeniden deneme ve çalışma sırasında yeniden bağlanma eklendi.
- Mevcut Redis pool'u kullanılmadan önce `PING` ile doğrulanıyor; kopmuş pool yeniden kuruluyor.
- Redis yoksa yeni run artık oluşturulmuyor; API açık bir `503` hatası döndürüyor.
- Redis enqueue başarısızsa run `failed` durumuna alınarak sessiz orphan kayıt engelleniyor.
- Resume enqueue başarısızsa run tekrar `paused` durumuna döndürülüyor.
- API açılışında eski `queued` işler yeniden kuyruğa ekleniyor.
- Eski `cancel_requested` kayıtları `cancelled` durumuna uzlaştırılıyor.
- Terminal run'lara ait yarım kalmış ARQ queue/job/in-progress anahtarları açılışta temizleniyor.
- API `/health`, Redis olmadan artık yanlış biçimde `healthy` dönmüyor.
- Worker heartbeat aralığı 30 saniyeye indirildi.
- Durum betiğine Redis sağlığı, worker heartbeat TTL'i ve `worker_operational` alanı eklendi.
- Worker kısmi startup hatasında shutdown sırasında oluşan ikincil `KeyError` giderildi.
- Pipeline, başlamadan önce iptal edilmiş run'ı tekrar `running` durumuna çevirmiyor.
- Run durum sorguları `populate_existing` ile her sınırda veritabanından yenileniyor; ayrı API
  session'ından gelen pause/cancel değişiklikleri worker tarafından görülüyor.

## Kabul ölçütü

Gerçek MCP isteği oluşturulduktan sonra run'ın `queued / INIT` durumundan çıkması, worker heartbeat
TTL'inin pozitif kalması ve iptal komutunun en geç bir düğüm sınırında `cancelled` durumuna ulaşması
gerekir.

## Doğrulama sonucu

- Otomatik testler: `68 passed`.
- Ruff: başarılı.
- PowerShell parser kontrolü: başarılı.
- API sağlık durumu: `healthy`; Redis: `ok`.
- Worker heartbeat TTL: 30 saniyelik periyotta pozitif.
- Eski run `01KXNNS9AJNRVKK23VFE13EC1X`: `cancelled`.
- MCP üzerinden oluşturulan `01KXNPF6Q4GDKJPMDA5CYG0HGF`, worker tarafından alınarak
  `DECOMPOSE` aşamasına geçti; bu test SQLAlchemy stale-state hatasını görünür hale getirdi.
- Son düzeltmeden sonra MCP üzerinden oluşturulan `01KXNPQTQGFEET2TT1G95HDZ3M`,
  `queued → cancel_requested → cancelled` akışını başarıyla tamamladı.
