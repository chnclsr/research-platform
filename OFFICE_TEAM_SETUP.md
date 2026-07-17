# Research Platform Ofis Sunucusu

Belge sürümü: `1.1`

Platform sürümü: `v0.5.0`

Tarih: `2026-07-17`

## Amaç

Bu bilgisayar araştırma toplama ve kanıt paketleme sunucusu olarak açık kalır. Aynı Wi‑Fi
ağındaki ekip üyeleri, kendi bilgisayarlarında çalışan Codex veya Claude Code içinden MCP
araçlarını kullanır. Telegram botu aynı araştırma işlerini başlatır, izler ve ham/sonuç/birleşik
paketleri gönderir.

```text
Codex / Claude Code ── Wi‑Fi + Bearer token ──> MCP :8010
                                                  │
Telegram ── Telegram API long polling ────────────┤
                                                  ▼
                                     Local Research API :8000
                                                  │
                         Worker + Redis + PostgreSQL + MinIO
                                                  │
                          AgentSearch + Crawl4AI + Ollama/RTX 4060
```

Yalnız MCP portu ofis ağına açılır. Research API, PostgreSQL, Redis, MinIO, Crawl4AI,
AgentSearch ve Ollama localhost/container sınırında kalır.

## Sunucu kurulumu

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\initialize_office_server.ps1
.\scripts\start_office_server.ps1
.\scripts\office_server_status.ps1
```

İlk komut:

- Wi‑Fi IPv4 adresini ve `/24` ağı belirler.
- Güçlü API/MCP/MinIO anahtarları üretir.
- `.env.office` dosyasını oluşturur.
- Paylaşılacak adres ve tokenı `data/office-access/TEAM_ACCESS.txt` içine yazar.

## Windows firewall

Bu bilgisayarda Wi‑Fi profili `Public` olduğundan inbound TCP 8010 için LocalSubnet kapsamlı
bir Windows Firewall kuralı gerekir. İşlem yönetici yetkisiyle yapılmalıdır:

```powershell
.\scripts\configure_office_firewall.ps1
```

Kural yalnız mevcut Wi‑Fi IP’sinin `8010` portunu ve `LocalSubnet` kaynaklarını kabul eder.
MCP ayrıca bearer token ve uygulama katmanı CIDR allowlist uygular.

## Otomatik başlatma

```powershell
.\scripts\register_office_autostart.ps1
```

Görev kullanıcı oturum açtığında çalışır, Docker Desktop hazır olana kadar bekler ve servisleri
başlatır. Bilgisayar uykuya girerse ekip erişimi kesilir; Windows güç planında uyku kapatılmalıdır.

Prize bağlı kullanımda uyku ve hazırda bekletmeyi kapatmak için:

```powershell
.\scripts\configure_office_power.ps1
```

## Ekip bilgisayarında Codex

Sunucudaki `scripts/install_codex_client.ps1` dosyasını ekip bilgisayarına kopyalayın:

```powershell
.\install_codex_client.ps1 -ServerIp "10.0.10.109" -Token "<TEAM_ACCESS token>"
```

Script `RESEARCH_MCP_TOKEN` kullanıcı ortam değişkenini ve
`~/.codex/config.toml` içindeki `mcp_servers.research_platform` kaydını oluşturur. Codex
uygulaması/CLI/IDE tamamen yeniden başlatılmalıdır.

## Ekip bilgisayarında Claude Code

```powershell
.\install_claude_client.ps1 -ServerIp "10.0.10.109" -Token "<TEAM_ACCESS token>"
```

Bu kurulum Claude Code’un kullanıcı kapsamına HTTP MCP sunucusunu ekler. Yerel ağdaki sunucuya
Claude Code’un çalıştığı ekip bilgisayarı bağlanır.

Bulut ortamında çalışan Codex görevleri veya Claude.ai web oturumları özel `10.x.x.x` Wi‑Fi
adresine doğrudan ulaşamaz. Bu sürümün hedefi ekip bilgisayarlarında yerel çalışan Codex
uygulaması/CLI/IDE ve Claude Code’dur.

## Telegram

BotFather’dan alınan tokenı kaydedin:

```powershell
.\scripts\configure_telegram.ps1 -BotToken "<BOT_TOKEN>"
.\scripts\start_office_server.ps1
```

Telegram’da bota `/whoami` gönderin. Bot kendi `user_id` ve `chat_id` değerlerinizi döndürür;
araştırma yetkisi vermez. Sonra allowlist’i kaydedin:

```powershell
.\scripts\configure_telegram.ps1 `
  -BotToken "<BOT_TOKEN>" `
  -AllowedUserIds 123456789,987654321
.\scripts\start_office_server.ps1
```

Komutlar:

```text
/research [raw|result|both] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
```

## Yerel kontrol paneli

Sunucu bilgisayarındaki servis, kuyruk, aktif run ve log yönetimi
`http://127.0.0.1:8020` adresindeki bağımsız panelden yapılır. Panel yalnız localhost'a açıktır ve
ekip bilgisayarlarından erişilemez. Kullanım ve güvenlik ayrıntıları `CONTROL_PANEL_GUIDE.md`
belgesindedir.

## Erişim anahtarı yönetimi

- `TEAM_ACCESS.txt` yalnız yetkili ekip üyeleriyle güvenli kanaldan paylaşılmalıdır.
- Bir ekip üyesi ayrılırsa `initialize_office_server.ps1 -Force` ile token döndürülmeli ve bütün
  istemciler yeniden yapılandırılmalıdır.
- Token Git’e, Telegram grubuna veya normal e-postaya yazılmamalıdır.
- Ağ değişirse `.env.office` yeniden üretilmeli ve firewall kuralı güncellenmelidir.
