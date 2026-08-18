# Research Platform Ofis Sunucusu

Belge sürümü: `1.5`

Platform sürümü: `v0.6.6`

Tarih: `2026-07-20`

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
.\install_codex_client.ps1
```

Script `RESEARCH_MCP_TOKEN` kullanıcı ortam değişkenini ve
`~/.codex/config.toml` içindeki `mcp_servers.research_platform` kaydını oluşturur. Codex
uygulaması/CLI/IDE tamamen yeniden başlatılmalıdır.

Paket içindeki `.env` sunucu ve token değerlerini otomatik sağlar. Kurucu ayrıca masaüstünde
`can-sagligi-deep-research` klasörünü açar ve tamamlanan yeni işlerin ham+sonuç ZIP paketlerini
arka planda bu klasöre indirir. Ayrıntılar `RESEARCH_SETUP.md` belgesindedir.

## Ekip bilgisayarında Claude Code

```powershell
.\install_claude_client.ps1
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
/research [raw|result|both] [--minutes N] [--sources N] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
```

`--minutes` verilmezse bot dört buton gösterir: **Hızlı (10 dk)**,
**Standart (30 dk)**, **Derin (120 dk)** ve **Maksimum (180 dk)**. Araştırma yalnız
kullanıcı bir süre düğmesine bastıktan sonra kuyruğa alınır. `--minutes N` verilirse bu
ekran atlanarak iş doğrudan başlatılır.

`--sources` verilmezse kaynak sayısı için global tavan uygulanmaz; araştırma süre,
coverage, saturation veya tur kriteriyle durur. Örnek kullanıcı limiti:

```text
/research raw --minutes 30 --sources 500 araştırma sorusu
```

## Yerel kontrol paneli

Sunucu bilgisayarındaki servis, kuyruk, aktif run ve log yönetimi bağımsız panelden yapılır.
Sunucuda `http://127.0.0.1:8020`, aynı ofis ağındaki ekip bilgisayarlarında
`http://10.0.10.109:8020` kullanılır. Panel yalnız yapılandırılmış ofis CIDR'ını kabul eder; kullanım
ve güvenlik ayrıntıları `CONTROL_PANEL_GUIDE.md` belgesindedir.

## Hesap yönetimi

v0.10.0'dan itibaren her kişinin kendi hesabı var ve **yalnız kendi araştırmalarını görüyor.**
Panelde kayıt formu yoktur; hesaplar aşağıdaki komutlarla açılır. Komutlar sunucu bilgisayarında,
depo kökünde çalıştırılır.

> Docker kurulumunda komutların önüne `docker compose exec api` gelir. Host `.venv`'inden
> çalıştırıyorsanız doğrudan `research-admin ...` yazın.

### Yeni kişi ekleme

```powershell
# 1. Hesabı aç. Parola --password verilmezse gizli olarak sorulur; tercih edilen yol budur,
#    çünkü komut satırına yazılan parola kabuk geçmişine ve süreç listesine düşer.
docker compose exec api research-admin create-user ali@ornek.com --display-name "Ali Yilmaz"

# 2. Kişi panele kendi parolasıyla girer: http://10.0.10.109:8020
```

Bu kadar. Kişi giriş yaptığı anda kendi araştırmalarını başlatabilir ve yalnız onları görür.

**Yönetici yapmak** gerekiyorsa — kurulumu başlatıp durdurabilmesi, logları okuyabilmesi ve
**herkesin** araştırmalarını görebilmesi demektir:

```powershell
docker compose exec api research-admin set-role ali@ornek.com admin
```

**Betik, Langflow veya MCP erişimi** gerekiyorsa kişiye kendi API anahtarını üret. Anahtar yalnız
bir kez gösterilir:

```powershell
docker compose exec api research-admin issue-key ali@ornek.com --name langflow
```

Kişi bu anahtarları panelden de kendisi üretip iptal edebilir; yöneticiye ihtiyaç yoktur.

**Telegram'dan araştırma başlatmak** için senin bir şey yapmana gerek yok — kişi kendisi bağlar:

1. Panele girer → **Hesabım** sekmesi → *Bağlantı kodu al*
2. **Telegram'da aç** düğmesine tıklar, ya da bota `/baglan M3H-QES` yazar
3. Bot "Bağlandı: ali@ornek.com" der; bundan sonraki araştırmalar o hesaba ait olur

Kod 5 dakika geçerli ve **tek kullanımlıktır**. Bu önemli: kod sızarsa, başkası kendi Telegram
hesabını o kişinin platform hesabına bağlayıp onun adına araştırma başlatabilir ve okuyabilirdi.
Tüketilen kod veritabanından silinir.

Gerekirse hâlâ elle de bağlayabilirsin (kişi bota `/whoami` yazıp kendi ID'sini söyler):

```powershell
docker compose exec api research-admin link-telegram ali@ornek.com 123456789
```

`TELEGRAM_BOT_USERNAME` ayarlanmamışsa panel derin bağlantı yerine yalnız kodu gösterir; akış
yine çalışır, kişi kodu elle yazar.

### Kişi ayrıldığında

Eskiden tek paylaşılan bir token vardı ve biri ayrıldığında token döndürülüp **bütün** istemciler
yeniden yapılandırılıyordu. Artık gerekmez — yalnız o hesabı kapat:

```powershell
docker compose exec api research-admin deactivate ali@ornek.com
```

Bu tek komut: panel oturumunu anında düşürür, API anahtarlarını kullanılamaz hâle getirir ve
Telegram erişimini keser. Diğer ekip üyeleri etkilenmez.

Hesap silinmez, kapatılır — araştırmaları ve provenance kaydı yerinde kalır. Koşularını devretmek
isterseniz:

```powershell
docker compose exec api research-admin assign-runs veli@ornek.com --from-email ali@ornek.com
```

### Komutların tamamı

| Komut | İş |
|---|---|
| `bootstrap <e-posta>` | İlk yöneticiyi açar ve sahipsiz koşuları ona devreder. Hesap varken çalışmaz. |
| `create-user <e-posta> [--role user\|admin]` | Hesap açar |
| `list-users` | Hesaplar, roller, durum ve koşu sayıları |
| `set-password <e-posta>` | Parola değiştirir, açık oturumları düşürür |
| `set-role <e-posta> user\|admin` | Rol atar |
| `deactivate <e-posta>` | Hesabı kapatır; son aktif yöneticiyi kapatmayı reddeder |
| `activate <e-posta>` | Hesabı yeniden açar |
| `issue-key <e-posta> --name <etiket>` | API anahtarı üretir (bir kez gösterilir) |
| `list-keys [--email <e-posta>]` | Anahtarları ve son kullanım tarihlerini listeler |
| `revoke-key <anahtar_id>` | Anahtarı iptal eder |
| `link-telegram <e-posta> <telegram_id>` | Telegram hesabını elle bağlar (normalde kişi kendisi bağlar) |
| `list-telegram` | Mevcut eşlemeler |
| `assign-runs <e-posta> --from-email\|--orphaned\|--run-id` | Koşuların sahibini değiştirir |

### Sık karşılaşılanlar

**Parolamı unuttum.** Sıfırlama e-postası yok; bir yönetici `set-password` çalıştırır.

**Yönetici parolasını kaybettik.** Komutlar veritabanına erişebilen herkes tarafından
çalıştırılabilir — sunucuda `docker compose exec api research-admin set-password <e-posta>`.

**Herkes sürekli çıkışa zorlanıyor.** `.env.office` içinde `SESSION_SECRET` boştur. Doldurup paneli
yeniden başlatın.

**Kişi kendi koşusunu göremiyor.** Koşu başka bir kanaldan (Telegram, Langflow) başlatılmış ve o
kanal onun hesabına bağlı değil olabilir. `list-users` koşu sayılarını gösterir; `assign-runs`
ile düzeltilir.

**Bot "hesabınız bağlı değil" diyor.** Kişi henüz Telegram'ını bağlamamış. Panelden kod alıp
`/baglan <kod>` yazması yeterli; `list-telegram` kimin bağlı olduğunu gösterir.

**Bot `/baglan` komutunu tanımıyor.** Bot container'ı eski kodda. `telegram-bot` servisi
`profiles: ["telegram"]` arkasında olduğu için düz `docker compose up -d --build` ona
dokunmaz. Doğrusu:

```powershell
docker compose --profile telegram up -d --build telegram-bot
```

**Telegram izin listesi ne oldu?** `TELEGRAM_ALLOWED_USER_IDS` artık birebir sohbetlerde
kullanılmıyor. Kimliğin olmadığı dönemde kimliğin yerine konmuş bir vekildi; gerçek kimlik
gelince yalnız engel olurdu — kişi kendini bağlar, sonra liste onu reddederdi. Yalnız **grup
sohbetlerinde** geçerliliğini koruyor, çünkü grupta mesajı gönderen kişi ile botun adına
hareket etmesi gereken kişi aynı olmayabilir.

### Değişmeyenler

- `.env.office` ve `.env` Git'te değildir; bu makineye özgüdür.
- `SERVICE_TOKEN` ve `SESSION_SECRET` Git'e, Telegram grubuna veya normal e-postaya yazılmamalıdır.
- Ağ değişirse `.env.office` yeniden üretilmeli ve firewall kuralı güncellenmelidir.
- Ofis CIDR sınırı kaldırılmamalıdır: panel düz HTTP üzerinden çalışırken oturum çerezi ağda açıktır.
