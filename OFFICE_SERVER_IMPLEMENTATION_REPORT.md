# Ofis Sunucusu Uygulama ve Doğrulama Raporu

Belge sürümü: `1.0`

Platform sürümü: `v0.4.2`

Tarih: `2026-07-16`

## Sonuç

Research Platform bu bilgisayarda sürekli çalışan, aynı Wi‑Fi ağındaki ekip üyelerinin kendi
Codex veya Claude Code istemcilerinden kullanabildiği yerel araştırma sunucusuna dönüştürüldü.

Aktif erişim:

- MCP gateway: `http://10.0.10.109:8010/mcp`
- İzinli istemci ağı: `10.0.10.0/24`
- Research API: yalnız `127.0.0.1:8000`
- PostgreSQL, Redis, MinIO, Crawl4AI, AgentSearch ve Ollama: yalnız localhost/container ağı

## Uygulanan güvenlik sınırları

- Non-loopback MCP açılışında en az 32 karakter rastgele bearer token zorunlu.
- İstemci IP adresi `MCP_ALLOWED_NETWORKS` CIDR listesine göre doğrulanıyor.
- Bearer token sabit-zaman karşılaştırmasıyla kontrol ediliyor.
- Tarayıcı Origin başlığı varsa allowlist uygulanıyor.
- Kimlik doğrulamalı `/health` endpoint'i eklendi.
- API'nin eski `0.0.0.0:8000` native bind'i `127.0.0.1:8000` olarak düzeltildi.
- Telegram araştırma komutları allowlist arkasında; `/whoami` yalnız kimlik keşfi sağlıyor.

## İşletim katmanı

- Wi‑Fi IP/CIDR keşfi ve token üretimi.
- Gizli `.env.office` ve `data/office-access/TEAM_ACCESS.txt`.
- Başlatma, durdurma, durum ve MinIO/servis bağımlılığı yönetimi.
- Kullanıcı oturumunda Windows Scheduled Task ile otomatik başlatma.
- Prize bağlıyken uyku ve hazırda bekletmenin kapatılması.
- Codex ve Claude Code istemci kurulum scriptleri.
- Token içeren, güvenli paylaşılması gereken ekip istemci ZIP paketi.
- Büyük ZIP teslimatlarının uzak ajan tarafından yeniden oluşturulabilmesi için base64 chunk MCP
  aracı.

## Doğrulama sonuçları

- `65` Python testi başarılı.
- Ruff statik kontrolü başarılı.
- Bütün PowerShell scriptleri parser kontrolünden geçti.
- MCP: yetkisiz istek `401`, yanlış token `401`, doğru token `200`.
- LAN adresinden gerçek MCP initialize/list-tools oturumu başarılı.
- MCP üzerinde `8` araç listelendi.
- Tamamlanmış bir run için `research_status` gerçek araç çağrısı başarılı.
- `5.091.673` baytlık birleşik araştırma paketinin ilk binary chunk'ı MCP üzerinden okundu.
- MinIO put/get roundtrip başarılı.
- API'nin Wi‑Fi adresindeki `8000` portuna erişim kapalı.
- Scheduled Task kaydı `Ready`.
- AC uyku ve hibernate süreleri `0` (devre dışı).

## Firewall durumu

Bilgisayarda Anaconda `python.exe` için önceden tanımlanmış Public/Any inbound kuralları vardır;
bu nedenle MCP portuna ağ seviyesinde ulaşılabilir. MCP yine bearer token ve `/24` CIDR kontrolüyle
korunur.

Portu Windows Firewall seviyesinde de yalnız `LocalSubnet:8010` ile sınırlamak için hazırlanan
`scripts/configure_office_firewall.ps1` yönetici yetkisi ister. Mevcut oturum yönetici olmadığı
için bu son sistem kuralı otomatik uygulanamamıştır.

## Açık kalan kullanıcı girdisi

Telegram kanalı kod ve işletim olarak hazır, fakat gerçek bot başlatma için BotFather tokenı ve
ekip üyelerinin allowlist `user_id`/`chat_id` değerleri gereklidir. Token girilene kadar Telegram
süreci bilerek kapalıdır.
