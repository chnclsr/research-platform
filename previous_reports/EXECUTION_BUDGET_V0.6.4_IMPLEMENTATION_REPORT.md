# Çalışma Süresi Bütçesi ve Telegram Kuyruk Koruması

Platform sürümü: `v0.6.4`

Belge sürümü: `1.0`

Tarih: `2026-07-20`

## Teşhis

`01KXZSCH10DWKBMZ2XB1N24CGP` numaralı run donmamıştı. İlk turda 60 aday URL
ACQUIRE aşamasına girdi; browser fallback, 403 yanıtları ve yavaş siteler nedeniyle
aşama uzun sürdü. Önceki uygulama yalnız aşama başlangıcı ve bitişinde olay yazdığı için
panel bu süre boyunca ilerleme göstermiyordu.

Telegram protokolü gerçekte varsayılan 45 dakikalık `max_wall_minutes` taşıyordu. Ancak
bu değer yalnız coverage sınırında kontrol ediliyor, worker restartında monoton sayaç
yeniden başlıyor ve kullanıcıya gösterilmiyordu. Dolayısıyla operasyonel olarak güvenilir
bir hard limit değildi.

## Uygulama

- İlk worker başlangıç zamanı `budget_started_at` olarak graph checkpoint'ine yazılır.
- Kalan süre hesaplanarak bütün LangGraph çalışması hard deadline ile çevrelenir.
- Worker restartında checkpoint zamanı korunur; süre yeniden başlamaz.
- Deadline dolarsa aktif graph iptal edilir, run `completed_incomplete` olur ve mevcut
  kaynak/iddialardan çıktı paketi üretilmeye çalışılır.
- ACQUIRE her URL tamamlandığında `acquisition_progress` olayı üretir ve run zamanını
  günceller. Panel/log tüketicileri `completed`, `total`, `successful`, son URL ve edinim
  yöntemini görebilir.
- Telegram varsayılan bütçesi: 20 dakika, 50 kaynak, 3 tur.
- Telegram üst sınırı: 60 dakika ve 150 kaynak.
- Örnek: `/research raw --minutes 30 --sources 80 araştırma sorusu`

Codex/Claude MCP aracında mevcut açık `max_wall_minutes` ve `max_sources` parametreleri
korunmuştur; varsayılanları 45 dakika ve 150 kaynaktır.

## Doğrulama

- Telegram varsayılan ve override parser testleri başarılı.
- Süresi önceki worker oturumunda dolmuş checkpoint'in anında hard deadline'a girdiği ve
  `completed_incomplete` olarak kapandığı doğrulandı.
- Tam pytest: `124 passed`.
- Ruff: başarılı.
