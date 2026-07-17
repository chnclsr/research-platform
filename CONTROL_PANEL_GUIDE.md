# Research Platform Yerel Kontrol Paneli

Belge sürümü: `1.0`

Platform sürümü: `v0.5.0`

Tarih: `2026-07-17`

## Amaç

Kontrol paneli, ana araştırma servislerinden bağımsız çalışan yerel bir supervisor'dır. API, worker,
MCP veya Telegram kapatılsa bile panel açık kalır ve sistem yeniden panel üzerinden başlatılabilir.

Panel adresi: `http://127.0.0.1:8020`

Panel güvenlik nedeniyle yalnız bu bilgisayardan erişilebilir; Wi-Fi/LAN arayüzüne bind edilmez.
Yönetim istekleri her panel açılışında üretilen, yalnız aynı-origin sayfanın okuyabildiği geçici bir
kontrol tokenıyla korunur.

## Görünen bilgiler

- API, worker, MCP ve Telegram process/PID durumu.
- PostgreSQL ve Redis erişilebilirliği.
- ARQ queue derinliği, çalışan/bekleyen iş sayısı ve worker heartbeat TTL'i.
- Ollama erişimi ve bellekte yüklü yerel model.
- Aktif ve sıradaki araştırmalar: durum, aşama, sıra, tur, kaynak ve iddia sayısı.
- Son 20 terminal araştırma: tamamlandı, eksik tamamlandı, iptal veya hata.
- Worker, API, MCP, Telegram ve panel loglarının son bölümü.

## Kontroller

- **Başlat:** PostgreSQL, Redis, MinIO ve Crawl4AI durumunu doğrular; API, worker, MCP ve Telegram'ı
  başlatır.
- **Yeniden başlat:** Aynı güvenli başlangıç akışını çalıştırarak native servisleri yeniler.
- **Servisleri durdur:** API, worker, MCP ve Telegram'ı durdurur. Panel ile veri container'ları açık
  kalır; PostgreSQL/Redis verisi ve araştırma kayıtları korunur.
- **Duraklat / Devam / İptal:** Run yaşam döngüsü komutlarını Research API'ye gönderir. Aktif LLM veya
  acquisition çağrısı zorla kesilmez; değişiklik güvenli düğüm sınırında uygulanır.

## Çalıştırma

Masaüstündeki `Research Platform Control Panel` kısayolu paneli açar. Elle başlatmak için:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\start_control_panel.ps1
```

Yalnız panel sürecini kapatmak için:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\stop_control_panel.ps1
```

Panel kullanıcı oturumu açıldığında `Research Platform Control Panel` Scheduled Task'ı tarafından
arka planda başlatılır. Bu görev ana `Research Platform Office Server` görevinden bağımsızdır.

## İşletim sınırları

- Panel Docker Desktop'ı kurmaz; Docker çalışmıyorsa Başlat işlemi mevcut sunucu betiğinin beş
  dakikalık hazır olma kontrolünü kullanır.
- `Servisleri durdur` Ollama'yı veya veri container'larını kapatmaz. Amaç geliştirme sırasında agent
  erişimini ve GPU kullanan yeni araştırma işlerini güvenle durdurmaktır.
- Panel açıkken tarayıcı sekmesi üç saniyede bir yenilenir; panel kapalıyken araştırma worker'ı normal
  biçimde çalışmaya devam eder.
