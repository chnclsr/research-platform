# İptal ve Worker Kurtarma Güvenilirliği

Platform sürümü: `v0.6.3`

Belge sürümü: `1.0`

Tarih: `2026-07-20`

## Olay

İki araştırma `cancel_requested` durumunda kaldı. Worker çalışıyor görünmesine rağmen
SEARCH/ACQUIRE içindeki uzun veya bloklayan dış çağrılar tamamlanmadığı için durum yalnız
düğüm sınırında kontrol edilebildi. Servis yeniden başlatıldığında eski ARQ `in-progress`
kilidinin kalması da checkpoint'li bir işin yeniden alınmasını geciktirebiliyordu.

## Uygulanan güvenlik katmanları

1. SEARCH ve ACQUIRE boyunca PostgreSQL kontrol durumu varsayılan olarak her bir saniyede
   okunur. `pause` veya `cancel` geldiğinde aktif asyncio görevi iptal edilir.
2. SEARCH 600 saniye, ACQUIRE 900 saniye içinde bitmezse görev sonlandırılır,
   `stage_timeout` audit olayı yazılır ve run açık hata ile kapanır.
3. Henüz başlamamış kuyruk işi iptal edildiğinde ara durum beklenmeden doğrudan
   `cancelled` olur.
4. Worker başlangıcında önceki sürece ait ARQ queue/job/in-progress/retry anahtarları
   temizlenir. `running` ve `queued` işler checkpoint'ten devam etmek üzere yeniden
   kuyruğa alınır; `cancel_requested` işler terminal hale getirilir.
5. Canlı kurtarma sırasında görülen `publicationTypes: null` ve `tags: null` akademik
   metadata değerleri boş liste olarak normalize edilerek relevance aşamasının çökmesi
   engellendi.

## Doğrulama

- Sonsuza kadar bekleyen sahte I/O sırasında iptal isteğinin yakalandığı doğrulandı.
- Sonsuza kadar bekleyen düğümün hard-timeout ile kapandığı doğrulandı.
- Worker restart senaryosunda orphan kilit temizliği, yeniden kuyruklama ve bekleyen
  iptalin tamamlanması doğrulandı.
- Ruff: başarılı.
- Tam pytest paketi: `121 passed`, yalnız üçüncü taraf Starlette deprecation uyarısı.
- Canlı worker yeniden başlatıldı; kesilmiş gerçek iş checkpoint'ten `DECOMPOSE` sonrası
  `SEARCH` aşamasına ilerledi.

## Operasyonel sonuç

Bir dış servis süresiz beklese bile run artık sonsuza kadar `cancel_requested` durumunda
kalamaz. Normal iptal en fazla polling gecikmesi ve veritabanı gecikmesi kadar sürer;
kontrol sinyalinin alınamadığı uç durumda düğüm hard-timeout ile kesin olarak sonlanır.
