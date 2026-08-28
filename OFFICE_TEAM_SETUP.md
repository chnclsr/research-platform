# Research Platform Ofis Sunucusu

Belge sürümü: `1.6`

Platform sürümü: `v0.15.0`

Tarih: `2026-08-28`

> **Sunucu Ubuntu'ya taşındı** (`server-cezeri`, `10.0.10.171`). Sunucuda çalışan komutlar
> artık bash'tir; `.ps1` operasyon scriptlerinin yerini [scripts/linux/](scripts/linux/)
> aldı. **Ekip bilgisayarlarındaki istemci kurulumu değişmedi** — `install_codex_client.ps1`
> ve `install_claude_client.ps1` hâlâ Windows'ta çalışır. Taşıma öyküsü
> [UBUNTU_MIGRATION.md](UBUNTU_MIGRATION.md) içindedir.

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
                       AgentSearch + Crawl4AI + Ollama/Quadro RTX 4000
```

Yalnız MCP portu ofis ağına açılır. Research API, PostgreSQL, Redis, MinIO, Crawl4AI,
AgentSearch ve Ollama localhost/container sınırında kalır.

## Sunucu kurulumu

İlk kurulum [UBUNTU_MIGRATION.md](UBUNTU_MIGRATION.md) içinde adım adım anlatılıyor.
Kurulu bir makinede günlük komutlar:

```bash
cd ~/research-platform
./scripts/linux/start_server.sh      # kaldır + sağlık doğrula
./scripts/linux/server_status.sh     # yalnız bak, hiçbir şey başlatma
docker compose logs -f worker
```

Ayarlar tek bir `.env` dosyasındadır; `.env.office` diye bir dosya **yoktur**.

Yığın `docker compose` ile çalışır. Compose'un dışında üç şey vardır: Ollama (host,
systemd — GPU'yu docling ile paylaşır), SearXNG (ayrı compose projesi) ve kontrol paneli
(host, systemd — işi compose'u yönetmek olduğu için kendi yönettiği projenin servisi
olamaz).

## Ağ ve güvenlik duvarı

`setup_ubuntu_server.sh` ufw'yi kurar ve 22 ile panel portunu (1111) LAN'a açar. **Ancak
docker'ın yayınladığı portlar ufw'yi atlar** — MCP 8010 buna dahildir. Bu yüzden sınır iki
katmandadır:

1. **Arayüz sınırı** — `.env` içindeki `MCP_BIND_HOST=10.0.10.171`. Port yalnız LAN
   arayüzünde açılır, loopback'te değil. `curl 127.0.0.1:8010` bu yüzden yanıt vermez;
   doğru adres `http://10.0.10.171:8010/mcp` ve kimliksiz istek `401` döner.
2. **Uygulama sınırı** — `MCP_ALLOWED_NETWORKS` ve kişiye özel `rp_` anahtarları. Asıl kapı
   budur.

Kaynak IP'ye göre kısıtlamak isterseniz `ufw allow/deny` **işe yaramaz**; kural
`DOCKER-USER` zincirine yazılır:

```bash
sudo iptables -I DOCKER-USER -p tcp --dport 8010 ! -s 10.0.10.0/24 -j DROP
sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
```

Container'ların host'taki Ollama'ya erişebilmesi için köprü alt ağının 11434'e izni olmalıdır;
aksi hâlde worker her LLM çağrısında zaman aşımına düşer:

```bash
sudo ufw allow from 172.19.0.0/16 to any port 11434 proto tcp
```

Dışarı **açılmaması gerekenler:** 8000, 5433, 6380, 9000/9001, 7860, 3940, 3941, 11235,
11434. Compose bunları zaten `127.0.0.1`'e bağlar.

## Otomatik başlatma

Ayrı bir iş gerekmez. Compose servisleri `restart: unless-stopped` taşır ve Docker açılışta
başlar; kontrol paneli systemd'de `enable`lidir. Windows'taki "uyku kapatılmalı" sorunu bu
makinede yoktur — sunucu uyumaz.

```bash
systemctl status research-control-panel
sudo journalctl -u research-control-panel -f
```

## Ajan uçları: önce kendi API anahtarınızı alın

**v0.10.1'den itibaren Codex, Claude Code ve Claude Desktop kişiye özel bir API anahtarı
ister.** Paylaşılan `MCP_BEARER_TOKEN` kaldırıldı: onunla başlatılan araştırmanın *sahibi*
olmuyordu, dolayısıyla panelde kimsenin listesine düşmüyordu ve API sahipsiz koşuyu
reddediyordu.

Anahtarı iki yoldan biriyle alırsınız:

```bash
# Kişi kendi alır: panelde Hesabım -> API anahtarları -> Yeni anahtar
# Ya da yönetici verir:
docker compose exec api research-admin issue-key ali@ornek.com --name claude-desktop
```

Anahtar `rp_` ile başlar ve **bir kez** gösterilir. Bu anahtarla başlattığınız her
araştırma sizin hesabınıza ait olur; panelde yalnız siz görürsünüz, ekip yalnız sansürlü
kuyruk satırını görür.

Anahtarı kaybederseniz iptal edip yenisini alın:
`research-admin list-keys --email ali@ornek.com`, sonra `revoke-key <anahtar_id>`.
İptal edilen anahtar **anında** çalışmaz olur.

## Ekip bilgisayarında Codex

Sunucudaki `scripts/install_codex_client.ps1` dosyasını ekip bilgisayarına kopyalayın:

```powershell
.\install_codex_client.ps1
```

Script anahtarınızı sorar (paketle gelen `.env` herkeste aynı olduğu için oradan bir
anahtar kabul edilmez), `RESEARCH_MCP_TOKEN` kullanıcı ortam değişkenini ve
`~/.codex/config.toml` içindeki `mcp_servers.research_platform` kaydını oluşturur. Codex
uygulaması/CLI/IDE tamamen yeniden başlatılmalıdır.

Paket içindeki `.env` sunucu adresini sağlar. Kurucu ayrıca masaüstünde
`can-sagligi-deep-research` klasörünü açar ve tamamlanan yeni işlerin ham+sonuç ZIP paketlerini
arka planda bu klasöre indirir. Ayrıntılar `RESEARCH_SETUP.md` belgesindedir.

## Ekip bilgisayarında Claude Code

```powershell
.\install_claude_client.ps1
```

Bu kurulum Claude Code’un kullanıcı kapsamına HTTP MCP sunucusunu ekler. Yerel ağdaki sunucuya
Claude Code’un çalıştığı ekip bilgisayarı bağlanır. Bu da anahtarınızı sorar.

Elle yapmak isterseniz tek komut:

```powershell
[Environment]::SetEnvironmentVariable("RESEARCH_MCP_TOKEN", "rp_...", "User")
claude mcp add --transport http research-platform "http://10.0.10.171:8010/mcp" `
  --header "Authorization: Bearer `${RESEARCH_MCP_TOKEN}" --scope user
```

Anahtar yapılandırmaya gömülmez; `${RESEARCH_MCP_TOKEN}` olarak yazılır ve Claude Code
çalışma anında ortamdan çözer, böylece `~/.claude.json` içinde düz metin anahtar durmaz.

> **En sık takılınan yer:** ortam değişkenini yazdıktan sonra **yeni bir terminal** açın.
> Zaten açık olan terminaller eski ortam bloğuyla başladıkları için değişkeni görmez ve
> `claude mcp list` çıktısında `✗ Failed to connect` + "Missing environment variables"
> uyarısı alırsınız. Doğrulama:
>
> ```powershell
> claude mcp list        # research-platform: ... - ✓ Connected
> ```

### Claude Desktop

Claude Desktop, Claude Code'dan **ayrı bir üründür** ve yukarıdaki `claude mcp` komutları
onu yapılandırmaz. Uzak (HTTP) bir MCP sunucusunu Claude Desktop'a bağlamak için uygulama
içinden **Settings → Connectors → Add custom connector** akışı kullanılır; bu akış
`http://<sunucu>:8010/mcp` adresini ister. Bağlantı kurulduktan sonra araçlar aynı şekilde
görünür ve başlattığınız araştırma yine anahtarın sahibine ait olur.

### MCP kapısına neden ulaşılabiliyor

8010 portu **yalnız LAN arayüzünde** yayınlanır (`MCP_BIND_HOST=10.0.10.171`), tüm
arayüzlerde değil. Erişim iki katmandan geçer: arayüz sınırı ve `MCP_ALLOWED_NETWORKS` +
kişiye özel `rp_` anahtarı.

> **`MCP_ALLOWED_NETWORKS`'ü ölçmeden daraltmayın.** Windows kurulumunda bu liste gerçek bir
> filtre değildi: Docker Desktop kaynak IP'yi NAT'layıp her istemciyi `172.20.0.1` gösterdiği
> için `172.16.0.0/12` satırı silindiğinde **bütün MCP istemcileri 403 alıyordu**; oradaki
> gerçek kapı Windows Firewall kuralıydı. Bu makinede o kural yok ve docker'ın gerçek kaynak
> IP'yi koruması **beklenir ama henüz ölçülmedi**. Daraltmadan önce LAN'daki bir istemciden
> bağlanıp container'ın gördüğü kaynak IP'yi doğrulayın; o zamana kadar `172.16.0.0/12`
> satırını silmeyin.

Bulut ortamında çalışan Codex görevleri veya Claude.ai web oturumları özel `10.x.x.x` Wi‑Fi
adresine doğrudan ulaşamaz. Bu sürümün hedefi ekip bilgisayarlarında yerel çalışan Codex
uygulaması/CLI/IDE ve Claude Code’dur.

## Telegram

BotFather’dan alınan tokenı kaydedin:

```bash
# .env icinde TELEGRAM_BOT_TOKEN ve TELEGRAM_BOT_USERNAME satirlarini doldurun,
# sonra botu profiliyle birlikte baslatin:
docker compose --profile telegram up -d --build telegram-bot
```

> **Aynı anda tek bot.** Telegram bir token için tek aktif `getUpdates` bağlantısına izin
> verir. Windows kurulumu hâlâ ayaktaysa ve aynı token'ı taşıyorsa iki örnek birbirini keser,
> her mesaj rastgele birine gider ve veritabanları ayrı olduğu için biri "böyle bir koşu yok"
> diyebilir. Devir sırası: önce Windows'ta `docker compose stop telegram-bot`, sonra burada
> yukarıdaki komut.

`TELEGRAM_BOT_USERNAME` boş bırakılırsa paneldeki bağlama akışı kullanıcıya hangi bota
gideceğini söyleyemez.

Telegram’da bota `/whoami` gönderin. Bot kendi `user_id` ve `chat_id` değerlerinizi döndürür;
araştırma yetkisi vermez. Sonra allowlist’i kaydedin:

```bash
# .env: TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
docker compose --profile telegram up -d telegram-bot
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
Adres ve port `.env` içindeki `CONTROL_PANEL_HOST` / `CONTROL_PANEL_PORT` ile belirlenir;
bu makinede sunucuda `http://127.0.0.1:1111`, aynı ağdaki ekip bilgisayarlarında
`http://10.0.10.171:1111`. Panel host üzerinde systemd biriminden çalışır
(`research-control-panel`), compose içinde değil.

> LAN'dan gelen tarayıcı `Host: 10.0.10.171` gönderir; bu ne loopback ne de makinenin
> hostname'idir. Sunucunun kendi adresini otomatik bulma denemesi Ubuntu'da `127.0.1.1`'e
> çözüldüğü için yetmez — `.env` içinde `CONTROL_PANEL_ALLOWED_HOSTS=["10.0.10.171"]`
> bulunmalıdır, yoksa panel `400 Invalid host header` döner. Yanlış
> `CONTROL_PANEL_ALLOWED_NETWORKS` ise `403` verir; ikisi farklı belirtidir. Panel yalnız `CONTROL_PANEL_ALLOWED_NETWORKS`
ile verilen CIDR'ı kabul eder; kullanım ve güvenlik ayrıntıları `CONTROL_PANEL_GUIDE.md`
belgesindedir.

Panelde bir de **"Ekipteki diğer işler"** bölümü var: kullanıcı, başkalarının süren
araştırmalarını *sansürlü* görür — kim, hangi durumda, hangi aşamada, ne süredir. Başlık,
araştırma sorusu ve içerik görünmez. Amacı, tek GPU sırada beklerken kimsenin "sistem
bozuk" sanmaması. Ayrıntı `CONTROL_PANEL_GUIDE.md` içindedir.

## Hesap yönetimi

v0.10.0'dan itibaren her kişinin kendi hesabı var ve **yalnız kendi araştırmalarını görüyor.**
Başkalarının süren işlerinden gördüğü tek şey yukarıda anlatılan sansürlü kuyruk satırıdır.
Panelde kayıt formu yoktur — hesaplar aşağıdaki komutlarla açılır.

### Komutlar nereden çalıştırılır

Hepsi `research-admin` aracının alt komutlarıdır ve aynı veritabanına yazarlar. İki yol var:

```bash
# Docker kurulumunda (bu makinede geçerli olan)
docker compose exec api research-admin <komut> ...

# Panel host üzerinde .venv'den çalıştığı için oradan da olur
.venv/bin/research-admin <komut> ...
```

Aşağıdaki örneklerde Docker biçimi kullanılıyor. Komutlar depo kökünden çalıştırılır.

---

### Mevcut kişilere bakma

```bash
docker compose exec api research-admin list-users
```

```
E-POSTA                   ROL    DURUM   KOSU  ID
kirtekefurkan@gmail.com   admin  aktif      9  01M07V15RGHN6QM4606BA0YT2F
calisircihan21@gmail.com  user   aktif      0  01M0812V17YV030WGJFEY5MC2P
```

| Sütun | Anlamı |
|---|---|
| `E-POSTA` | Girişte kullanılan kimlik |
| `ROL` | `user` ya da `admin` |
| `DURUM` | `aktif` girebilir, `kapali` giremez |
| `KOSU` | O kişiye ait araştırma sayısı |
| `ID` | Diğer komutlarda değil, yalnız veritabanı sorgularında gerekir |

Sahipsiz koşu varsa listenin altında ayrıca belirtilir; bunlar yalnız yöneticilere görünür.

Daha fazla sütun gerekiyorsa (`token_version`, `last_login_at`) doğrudan veritabanına bakın:

```bash
docker compose exec -T postgres psql -U research -d research -c "select email, display_name, role, is_active, token_version, last_login_at from users order by created_at;"
```

`token_version`, o kişinin oturumlarının kaç kez düşürüldüğünü gösterir — her parola
değişiminde ve her hesap kapatmada bir artar. Parola özetleri hiçbir komutta gösterilmez.

---

### Kişi ekleme

```bash
docker compose exec api research-admin create-user ali@ornek.com --display-name "Ali Yilmaz"
```

Parola **sorulur**; `--password` ile komut satırına yazmayın, kabuk geçmişine ve süreç
listesine düşer. Doğrudan yönetici olarak açmak için `--role admin` ekleyin.

Sonra kişiye e-postasını ve geçici parolayı güvenli bir kanaldan iletin. Kişi panele girip
**Hesabım → Parola** ile kendi parolasını koyar. Bu ikinci adım önemli: aksi hâlde geçici
parola sizde kalmaya devam eder.

> **Sıfırdan kurulumda ilk hesap.** Hiç hesap yokken `create-user` yerine `bootstrap`
> kullanılır; ilk yöneticiyi açar **ve** o ana kadarki sahipsiz koşuları ona devreder.
> Bir hesap varken ikinci kez çalışmayı reddeder, yani canlı sistemde yönetici basmanın
> yolu değildir.
>
> ```powershell
> docker compose exec api research-admin bootstrap yonetici@ornek.com
> ```

Kişi giriş yaptığı anda kendi araştırmasını başlatabilir ve yalnız onları görür.
Panel adresi bu makinede **`http://10.0.10.171:1111`**.

---

### Yetki ayarlama

```bash
docker compose exec api research-admin set-role ali@ornek.com admin   # yönetici yap
docker compose exec api research-admin set-role ali@ornek.com user    # geri al
```

İki rol var ve fark, kullanıcı verisiyle kurulum operasyonları arasındadır:

| | `user` | `admin` |
|---|---|---|
| Kendi araştırmaları | ✔ | ✔ |
| **Başkalarının araştırmaları** | ✘ | ✔ |
| Kendi API anahtarları, Telegram bağlantısı, parolası | ✔ | ✔ |
| **Servisleri başlat / durdur** | ✘ | ✔ |
| **Servis logları** | ✘ | ✔ |
| **Connector testi** | ✘ | ✔ |

Sıradan kullanıcıya yönetici düğmeleri ve log sekmesi panelde hiç gösterilmez; sunucu
tarafında da reddedilir. Gerekçe: log akışı herkesin koşusunu karıştırır, "Servisleri durdur"
başkasının süren araştırmasını keser.

Rol değişikliği açık oturumu düşürmez; kişi bir sonraki sayfa yenilemesinde yeni yetkisini
görür.

---

### Kişi çıkarma

```bash
docker compose exec api research-admin deactivate ali@ornek.com
```

Bu tek komut üç kapıyı birden kapatır: panel oturumu **anında** düşer, API anahtarları
kullanılamaz hâle gelir, Telegram erişimi kesilir. Diğer ekip üyeleri etkilenmez — eski
paylaşılan token düzeninde herkesin yeniden yapılandırılması gerekiyordu, artık gerekmiyor.

Geri açmak için:

```bash
docker compose exec api research-admin activate ali@ornek.com
```

Hesap yeniden açılsa bile **eski oturum çerezleri geçersiz kalır**; kişi yeniden giriş yapar.

Son aktif yöneticiyi kapatmak reddedilir — kimsenin içeri giremediği bir kuruluma düşmemek
için. Önce başka birini `set-role ... admin` yapın.

#### Hesap silme neden yok

`deactivate` hesabı kapatır, **silmez**. Silme komutu bilinçli olarak yazılmadı: koşular
`owner_id` ile hesaba bağlı ve satır silinirse o koşular sahipsiz kalır — yalnız
yöneticilere görünür hâle gelir ve provenance kaydındaki "bu araştırmayı kim başlattı"
bilgisi kaybolur.

Bir hesabı gerçekten silmeniz gerekiyorsa (yanlışlıkla açılmış, hiç koşusu olmayan bir test
hesabı gibi) önce koşularının olmadığını doğrulayın, sonra doğrudan veritabanından silin:

```bash
# 1. Koşusu var mı? list-users'daki KOSU sütunu 0 olmalı.
docker compose exec api research-admin list-users

# 2. Koşusu varsa önce devredin
docker compose exec api research-admin assign-runs veli@ornek.com --from-email ali@ornek.com

# 3. Sil
docker compose exec -T postgres psql -U research -d research -c "delete from api_keys where user_id = (select id from users where email='ali@ornek.com'); delete from telegram_identities where user_id = (select id from users where email='ali@ornek.com'); delete from users where email='ali@ornek.com';"
```

Üç tabloyu da temizlemek gerekir; kimlik tablolarında ForeignKey yoktur, dolayısıyla
yalnız `users` satırını silmek arkada anahtar ve Telegram eşlemesi bırakır.

Normal işleyişte **`deactivate` tercih edilmelidir.**

---

### Parola

Parolasını **bilen** kullanıcının yöneticiye ihtiyacı yoktur: panelde **Hesabım → Parola**.

Parolasını **unutan** için sıfırlama e-postası yoktur, bir yönetici koyar:

```bash
docker compose exec api research-admin set-password ali@ornek.com
```

Her iki yol da o kişinin tüm açık oturumlarını düşürür.

---

### API anahtarları

Betik, Langflow ve MCP erişimi için. Kişi bunları panelden kendisi üretip iptal edebilir;
aşağıdakiler yönetici tarafı içindir.

```bash
docker compose exec api research-admin issue-key ali@ornek.com --name langflow
docker compose exec api research-admin list-keys                      # hepsi
docker compose exec api research-admin list-keys --email ali@ornek.com # tek kişi
docker compose exec api research-admin revoke-key 01M07V1VQR6EFX2YVRBDN7387D
```

Anahtar üretildiği anda **bir kez** gösterilir ve geri alınamaz; kaybedilirse iptal edip
yenisi üretilir. `revoke-key` `list-keys` çıktısındaki anahtar kimliğini alır, e-postayı
değil. İptal edilen anahtar anında çalışmaz olur.

---

### Telegram

Normalde **kişi kendisi bağlar**, sizin bir şey yapmanız gerekmez:

1. Panele girer → **Hesabım** → *Bağlantı kodu al*
2. **Telegram'da aç** düğmesine tıklar, ya da bota `/baglan M3H-QES` yazar
3. Bot "Bağlandı: ali@ornek.com" der

Kod 5 dakika geçerli ve **tek kullanımlıktır**: kod sızarsa başkası kendi Telegram hesabını
o kişinin platform hesabına bağlayıp onun adına araştırma başlatabilirdi.

Elle bağlamak gerekirse (kişi bota `/whoami` yazıp kendi ID'sini söyler) ve eşlemeleri
görmek için:

```bash
docker compose exec api research-admin link-telegram ali@ornek.com 123456789
docker compose exec api research-admin list-telegram
```

---

### Koşuların sahipliği

```bash
# Bir kişinin tüm koşularını başkasına devret (ayrılan biri için)
docker compose exec api research-admin assign-runs veli@ornek.com --from-email ali@ornek.com

# Sahipsiz kalan koşuların tümü
docker compose exec api research-admin assign-runs veli@ornek.com --orphaned

# Tek tek belirli koşular
docker compose exec api research-admin assign-runs veli@ornek.com --run-id 01M07BF29WP1YAWNVVN4YYR22R
```

Üç seçenekten biri zorunludur; hiçbiri verilmezse komut ne yapacağını sormadan reddeder.

---

### Komutların tamamı

| Komut | İş |
|---|---|
| `list-users` | Hesaplar, roller, durum ve koşu sayıları |
| `bootstrap <e-posta> [--display-name] [--password]` | İlk yöneticiyi açar ve sahipsiz koşuları devreder. Hesap varken çalışmaz |
| `create-user <e-posta> [--display-name] [--role user\|admin] [--password]` | Hesap açar |
| `set-role <e-posta> user\|admin` | Rol atar |
| `deactivate <e-posta>` | Hesabı kapatır; son aktif yöneticiyi reddeder |
| `activate <e-posta>` | Hesabı yeniden açar |
| `set-password <e-posta> [--password]` | Parola koyar, açık oturumları düşürür |
| `issue-key <e-posta> [--name <etiket>]` | API anahtarı üretir (bir kez gösterilir) |
| `list-keys [--email <e-posta>]` | Anahtarları ve son kullanım tarihlerini listeler |
| `revoke-key <anahtar_id>` | Anahtarı iptal eder |
| `link-telegram <e-posta> <telegram_id>` | Telegram hesabını elle bağlar |
| `list-telegram` | Mevcut eşlemeler |
| `assign-runs <e-posta> --from-email\|--orphaned\|--run-id` | Koşuların sahibini değiştirir |

**Hesap silme komutu yoktur** — gerekçesi ve elle silme yolu yukarıdaki "Hesap silme neden
yok" başlığındadır.

`--password` her yerde isteğe bağlıdır ve verilmezse gizli olarak sorulur; tercih edilen
yol sormaktır.

### Sık karşılaşılanlar

**Parolamı değiştirmek istiyorum.** Mevcut parolanı biliyorsan yöneticiye gerek yok:
panelde **Hesabım → Parola**. Değişiklik diğer cihazlardaki oturumlarını kapatır, kendi
sekmen açık kalır.

**Parolamı unuttum.** Sıfırlama e-postası yok; bir yönetici `set-password` çalıştırır.

**Yönetici parolasını kaybettik.** Komutlar veritabanına erişebilen herkes tarafından
çalıştırılabilir — sunucuda `docker compose exec api research-admin set-password <e-posta>`.

**Herkes sürekli çıkışa zorlanıyor.** `.env` içinde `SESSION_SECRET` boştur. Doldurup paneli
`sudo systemctl restart research-control-panel` ile yeniden başlatın.

**Kişi kendi koşusunu göremiyor.** Koşu başka bir kanaldan (Telegram, Langflow) başlatılmış ve o
kanal onun hesabına bağlı değil olabilir. `list-users` koşu sayılarını gösterir; `assign-runs`
ile düzeltilir.

**Bot "hesabınız bağlı değil" diyor.** Kişi henüz Telegram'ını bağlamamış. Panelden kod alıp
`/baglan <kod>` yazması yeterli; `list-telegram` kimin bağlı olduğunu gösterir.

**Bot `/baglan` komutunu tanımıyor.** Bot container'ı eski kodda. `telegram-bot` servisi
`profiles: ["telegram"]` arkasında olduğu için düz `docker compose up -d --build` ona
dokunmaz. Doğrusu:

```bash
docker compose --profile telegram up -d --build telegram-bot
```

**Telegram izin listesi ne oldu?** `TELEGRAM_ALLOWED_USER_IDS` artık birebir sohbetlerde
kullanılmıyor. Kimliğin olmadığı dönemde kimliğin yerine konmuş bir vekildi; gerçek kimlik
gelince yalnız engel olurdu — kişi kendini bağlar, sonra liste onu reddederdi. Yalnız **grup
sohbetlerinde** geçerliliğini koruyor, çünkü grupta mesajı gönderen kişi ile botun adına
hareket etmesi gereken kişi aynı olmayabilir.

### Değişmeyenler

- `.env` Git'te değildir; bu makineye özgüdür. `.env.office` diye bir dosya yoktur.
- `SERVICE_TOKEN` ve `SESSION_SECRET` Git'e, Telegram grubuna veya normal e-postaya yazılmamalıdır.
- Ağ değişirse `.env` içindeki `MCP_BIND_HOST`, `CONTROL_PANEL_ALLOWED_HOSTS` ve
  `*_ALLOWED_NETWORKS` satırları güncellenmelidir.
- Ofis CIDR sınırı kaldırılmamalıdır: panel düz HTTP üzerinden çalışırken oturum çerezi ağda açıktır.
