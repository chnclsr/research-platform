# Otomatik araştırma çıktısı kurulumu

Belge sürümü: `2.0`

Platform sürümü: `v0.5.3`

Tarih: `2026-07-17`

Paket içindeki `.env`, sunucu adresini, erişim anahtarını, teslimat biçimini ve hedef klasörü içerir.
Codex için `install_codex_client.ps1`, Claude Code için `install_claude_client.ps1` çalıştırılır;
komut satırı parametresi gerekmez.

Kurulum `%LOCALAPPDATA%\ResearchPlatformClient` içine eşitleyiciyi yerleştirir ve masaüstünde
`can-sagligi-deep-research` klasörünü oluşturur. Kurulumdan önce tamamlanmış işler başlangıç kaydı
sayılır; kurulum anında çalışan ve sonradan açılan işler bittiğinde ZIP ve durum JSON'u indirilir.

Varsayılan `DELIVERY_MODE=both`, ham kaynak/pasaj verisini ve sentezlenmiş raporları birlikte getirir.
Yalnız ham veri için `raw`, yalnız rapor için `result` kullanılabilir.

Eşitleme günlüğü `%LOCALAPPDATA%\ResearchPlatformClient\sync.log`, indirilen iş kimlikleri
`downloaded-runs.txt` dosyasındadır. Token günlüğe veya indirilen rapora yazılmaz.

Belirli bir işi yeniden indirmek için eşitleyici `-RunId <id> -Force` seçenekleriyle bir kez çalıştırılabilir.
