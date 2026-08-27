# Windows'tan Ubuntu Sunucuya Taşıma

Belge sürümü: `1.0` · Platform sürümü: `v0.15.0` · Tarih: `2026-08-27`

Bu belge, şu an Windows 11 + Docker Desktop üzerinde çalışan kurulumun GPU'lu bir Ubuntu
sunucuya SSH ile taşınmasını anlatır. Hedef: **temiz veritabanı + taşınmış hesaplar**,
erişim **ofis LAN'ı** ile sınırlı.

## Ne taşınıyor, ne taşınmıyor

| | Durum |
|---|---|
| Kod | GitHub'dan `git clone` |
| Bağlayıcı kimlik bilgileri (`.env`) | `scp` ile kopyalanır, birkaç satırı Ubuntu'ya göre değişir |
| Kullanıcılar, parolalar, API anahtarları, Telegram eşlemeleri | `accounts.sql` ile taşınır — **dağıtılmış `rp_` anahtarları geçerli kalır** |
| Geçmiş koşular, kanıtlar, pasajlar | **Taşınmıyor.** Sunucuda boş veritabanı |
| MinIO anlık görüntüleri (681 MB) | **Taşınmıyor** |
| Ollama modelleri | Sunucuda yeniden indirilir (~5 GB) |
| Operasyon scriptleri (`.ps1`) | Windows'ta kalır; Linux karşılıkları `scripts/linux/` altında yeni yazıldı |

Parola ve API anahtarı hash'leri `scrypt$n$r$p$tuz$hash` biçiminde, tuzu kaydın içinde
taşır ([auth.py:84](src/research_platform/auth.py#L84)). Dışarıda bir gizli anahtara
bağlı olmadığı için satırlar başka makineye taşındığında parolalar da dağıtılmış `rp_`
anahtarları da aynen çalışır. Değişen tek şey: açık panel oturumları düşer, herkes bir
kez yeniden giriş yapar.

---

## Mimarinin Linux'ta değişen tarafı

Windows kurulumunda `api`, `worker` ve `mcp` **natif süreçlerdi**
([start_native.ps1](scripts/start_native.ps1), PID dosyaları). Ubuntu'da hepsi compose
içinde çalışır. Compose'un dışında kalan üç şey var:

| Bileşen | Nerede | Neden dışarıda |
|---|---|---|
| Ollama | host, systemd | GPU'yu docling ile paylaşır; model önbelleği host'ta kalsın |
| SearXNG | ayrı compose projesi | Ayrı yaşam döngüsü; ana yığın yeniden kurulunca kaybolmasın |
| Kontrol paneli | host, systemd | İşi compose'u yönetmek. Kendisi de o projenin servisi olsaydı, kendini yeniden başlatması gereken durumda kilitlenirdi |

---

## Adım 0 — Windows tarafında commit edilmemiş işi hallet

`git clone` yoluyla gideceğimiz için sunucuya yalnızca push edilmiş kod ulaşır. Şu an
çalışma ağacında bekleyen değişiklikler var:

```
M src/research_platform/figure_analysis.py
M src/research_platform/word_report.py
M tests/test_figure_analysis.py
M tests/test_word_report.py
```

Bunları taşımadan önce commit'leyip push edin:

```powershell
git status
git add -A
git commit -m "..."
git push origin developments-supplementer
```

> `scripts/_qa_figure_language_reports.py` ve `output/` klasörü de takipsiz durumda.
> Sunucuda gerekmeyecekse bırakın.

## Adım 1 — Hesapları dışa aktar (Windows)

Windows sunucusunda, yığın **ayaktayken**:

```powershell
.\scripts\export_accounts.ps1
```

Proje kökünde `accounts.sql` oluşur ve kaç kullanıcı/anahtar çıkarıldığını yazar.
Dosya parola ve anahtar hash'leri içerir; aktarım bitince Windows tarafından silin.

## Adım 2 — SSH erişimi

```powershell
# Anahtar yoksa üretin
ssh-keygen -t ed25519 -C "research-platform"

# Sunucuya kopyalayın
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh kullanici@SUNUCU_IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

ssh kullanici@SUNUCU_IP
```

Sunucuda parola girişini kapatmak isterseniz `/etc/ssh/sshd_config` içinde
`PasswordAuthentication no` + `sudo systemctl restart ssh`. **Önce anahtarla
girebildiğinizi doğrulayın**, aksi halde kendinizi dışarıda bırakırsınız.

## Adım 3 — Sunucu ön hazırlığı

Önce NVIDIA sürücüsü (yoksa):

```bash
sudo ubuntu-drivers install
sudo reboot
nvidia-smi          # kart ve sürücü sürümü görünmeli
```

Sonra Docker, NVIDIA container runtime, Ollama ve modeller:

```bash
git clone https://github.com/chnclsr/research-platform.git
cd research-platform
git checkout developments-supplementer

./scripts/linux/setup_ubuntu_server.sh 192.168.1.0/24     # kendi LAN CIDR'iniz
```

Script sonunda **sürücü sürümünüze uygun `TORCH_VARIANT` değerini yazar** — not edin,
`.env`'e gireceksiniz. Kullanıcı `docker` grubuna eklenirse **oturumu kapatıp açın**.

> Script Ollama'yı `OLLAMA_HOST=0.0.0.0:11434` ile yapılandırır. Bu, Linux'a özgü ve
> atlanması kolay bir zorunluluk: Ollama varsayılan olarak yalnız `127.0.0.1`'i dinler,
> `host.docker.internal` ise Linux'ta docker köprüsünün IP'sine çözülür — loopback'e
> bağlı bir Ollama'ya container'lardan **erişilemez** ve worker her LLM çağrısında
> sessizce hata alır.

## Adım 4 — `.env` dosyası

Windows'taki `.env`'i kopyalayın (bağlayıcı anahtarlarını yeniden toplamamak için):

```powershell
scp .env kullanici@SUNUCU_IP:~/research-platform/.env
```

Sunucuda önce satır sonlarını düzeltin, sonra Ubuntu'ya özgü satırları ekleyin:

```bash
cd ~/research-platform
sed -i 's/\r$//' .env      # Windows'tan gelen CRLF

printf '%s\n' '' \
  '# ------------------------------------------------------------ Ubuntu sunucu' \
  '# GPU overlay. IKI satir da gerekli: COMPOSE_FILE ayiraci platform' \
  '# varsayilanidir, tek satirlik ":" yazimi Windows tarafinda calismaz.' \
  'COMPOSE_PATH_SEPARATOR=:' \
  'COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml' \
  '# setup_ubuntu_server.sh in onerdigi deger (surucu >= 580 ise cu132)' \
  'TORCH_VARIANT=cu132' >> .env
```

Sonra şu satırları **düzenleyin**:

| Değişken | Windows'taki | Ubuntu'da olması gereken | Neden |
|---|---|---|---|
| `SEARXNG_URL` | `http://host.docker.internal:3939` | `http://searxng:8080` | SearXNG artık aynı docker ağında; host portu yayınlamaya gerek yok |
| `ZOTERO_LOCAL_ENABLED` | `true` | `false` | Başsız sunucuda Zotero masaüstü yok; `true` kalırsa her koşuda boşuna zaman aşımı bekler |
| `CONTROL_PANEL_ALLOWED_NETWORKS` | `["10.0.10.0/24"]` | sunucunun LAN CIDR'i | Yanlış CIDR = panelde 403 |
| `MCP_ALLOWED_NETWORKS` | eski liste | sunucunun LAN CIDR'i | Uygulama katmanı erişim listesi |
| `MCP_BIND_HOST` | (yok) | sunucunun LAN IP'si | ufw docker portlarını atlar — Adım 8 |
| `SERVICE_TOKEN`, `SESSION_SECRET`, `API_TOKEN`, `MINIO_SECRET_KEY` | mevcut | `openssl rand -hex 32` ile yenile | Eski makine devre dışı kalacaksa hijyen. Ekibin `rp_` anahtarlarını **etkilemez** |

`OLLAMA_URL=http://host.docker.internal:11434` **değişmez** — compose zaten
`extra_hosts: host-gateway` tanımlıyor ve Ollama artık tüm arayüzleri dinliyor.

`MCP_HOST` ve `MCP_PORT` de değişmez: [docker-compose.yml](docker-compose.yml) bunları
servis düzeyinde `0.0.0.0:8010` olarak zaten eziyor, `.env`'deki değer container'a
ulaşmıyor.

## Adım 5 — İlk kalkış

```bash
# Ana yığın (docling imajı CUDA tekerlekleriyle derlenir, ilk sefer uzun sürer)
docker compose up -d --build

# SearXNG (ana yığının ağı oluştuktan SONRA)
export SEARXNG_SECRET="$(openssl rand -hex 32)"
echo "export SEARXNG_SECRET=$SEARXNG_SECRET" >> ~/.bashrc
docker compose -f scripts/linux/searxng/docker-compose.searxng.yml up -d
```

`docling` servisinin gerçekten GPU'ya bağlandığını doğrulayın — taşımanın sessizce
yanlış gidebileceği asıl yer burası:

```bash
curl -s http://127.0.0.1:3941/health
```

Yanıttaki cihaz `cuda` olmalı. `cpu` görünüyorsa GPU overlay devrede değildir;
`COMPOSE_FILE` satırlarını kontrol edin. Servis hiç kalkmıyorsa `TORCH_VARIANT`
sürücünüzle uyumsuzdur — docling kart bulamayınca **kasten** ölür, çünkü CPU ve GPU
aynı metni üretmez ve `content_hash` o metnin sha256'sıdır.

## Adım 6 — Hesapları içe aktar

```powershell
scp accounts.sql kullanici@SUNUCU_IP:~/research-platform/
```

```bash
cd ~/research-platform
./scripts/linux/import_accounts.sh accounts.sql
```

Script hedef `users` tablosunun boş olduğunu doğrular, yükler ve kullanıcı listesini
aktif anahtar sayılarıyla birlikte basar. Ardından `accounts.sql`'i her iki makineden
de silin.

> Hesap taşımak yerine sıfırdan başlamak isterseniz:
> `docker compose exec api research-admin bootstrap siz@ornek.com`

## Adım 7 — Kontrol paneli (systemd)

Panel compose dışında, host üzerinde çalışır ve kendi venv'ini ister:

```bash
sudo apt-get install -y python3-venv
python3 -m venv .venv
.venv/bin/pip install -e .
mkdir -p logs

sudo cp scripts/linux/research-control-panel.service /etc/systemd/system/
sudo sed -i "s|__KULLANICI__|$USER|g; s|__KOK__|$PWD|g" \
    /etc/systemd/system/research-control-panel.service
sudo systemctl daemon-reload
sudo systemctl enable --now research-control-panel
systemctl status research-control-panel
```

Birim dosyası `.env`'i systemd'ye okutmaz, bilerek: ayarları zaten pydantic-settings
çalışma dizininden okuyor ve `MCP_ALLOWED_NETWORKS=["10.0.10.0/24"]` gibi JSON
listelerini doğru ayrıştırıyor; systemd'nin kendi ayrıştırıcısı aynı satırdaki
tırnakları yiyip listeyi bozardı. Buna karşılık birim, veritabanı/Redis/MinIO
adreslerini **ezer**: `.env` container'lar için yazılmıştır, oradaki `postgres:5432`
adını host üzerindeki bir süreç çözemez.

## Adım 8 — Ağ ve güvenlik duvarı

`setup_ubuntu_server.sh` ufw'yi kurup 22 ve panel portunu (1111) LAN'a açar. **Ancak
docker'ın yayınladığı portlar ufw'yi atlar** — MCP 8010 buna dahildir. İki katmanı da
uygulayın:

1. **Arayüz sınırı:** `.env` içinde `MCP_BIND_HOST=<sunucunun LAN IP'si>`. Böylece port
   yalnız LAN arayüzünde açılır.
2. **Uygulama sınırı:** `MCP_ALLOWED_NETWORKS` + kişiye özel `rp_` bearer anahtarları.
   Asıl kapı budur.

Kaynak IP'ye göre de kısıtlamak isterseniz (isteğe bağlı sertleştirme):

```bash
sudo iptables -I DOCKER-USER -p tcp --dport 8010 ! -s 192.168.1.0/24 -j DROP
sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
```

Dışarı **açılmaması gerekenler:** 8000 (API), 5433, 6380, 9000/9001, 7860, 3940, 3941, 11235,
11434. Compose bunları zaten `127.0.0.1`'e bağlıyor; Ollama'yı ufw kapatır.

## Adım 9 — Doğrulama

```bash
./scripts/linux/server_status.sh
```

Görmeniz gerekenler: tüm container'lar `Up (healthy)`, API/MCP/Docling/Panel/Ollama
uçları yanıtlıyor, **worker kalp atışı ttl > 0**, docling cihazı `cuda`.

Kalp atışı yoksa kuyruk sağlıklı görünse bile hiçbir iş alınmaz — bu ikisini ayıran
tek sinyal odur.

Uçtan uca test: panele girip küçük bir koşu başlatın, `docker compose logs -f worker`
ile izleyin. İlk koşu modelleri ısıtacağı için yavaştır.

## Adım 10 — Ekip istemcilerini yönlendirme

Sunucu adresi değişti; herkesin MCP kaydındaki host güncellenmeli. Yeni adres:
`http://<SUNUCU_LAN_IP>:8010/mcp`

- **Codex:** `~/.codex/config.toml` → `mcp_servers.research_platform` URL'i
- **Claude Code:** kaydı silip yeni URL ile ekleyin
- **Claude Desktop:** ayarlardan bağlayıcı URL'i

`rp_` anahtarları değişmediği için kimsenin yeni anahtar almasına gerek yok.
[OFFICE_TEAM_SETUP.md](OFFICE_TEAM_SETUP.md) hâlâ geçerli; yalnız sunucu tarafındaki
PowerShell komutlarının yerini `scripts/linux/` karşılıkları alır.

Telegram botu için `.env`'de `TELEGRAM_BOT_TOKEN` doluysa:

```bash
docker compose --profile telegram up -d telegram-bot
```

> Bot tek token'la tek yerden çalışır. **Windows'taki botu önce durdurun**, yoksa iki
> örnek aynı güncellemeler için yarışır.

---

## Günlük kullanım

```bash
./scripts/linux/start_server.sh     # start_office_server.ps1 karşılığı
./scripts/linux/server_status.sh    # office_server_status.ps1 karşılığı
docker compose down                 # durdur
docker compose logs -f worker       # log
docker compose exec api research-admin list-users
```

Otomatik başlatma için ayrı bir iş gerekmez: compose servisleri
`restart: unless-stopped`, panel systemd'de `enable`li. Docker açılışta başlar.

## Bilinen tuzaklar

| Belirti | Sebep | Çözüm |
|---|---|---|
| Worker her LLM çağrısında hata alıyor | Ollama `127.0.0.1`'e bağlı | `OLLAMA_HOST=0.0.0.0:11434` systemd override + `systemctl restart ollama` |
| Arama hiç sonuç dönmüyor (hata da yok) | SearXNG `json` biçimi kapalı; adapter istisnayı yutuyor | `scripts/linux/searxng/settings.yml` mount edilmiş mi |
| `docling` sürekli yeniden başlıyor | `TORCH_VARIANT` sürücüyle uyumsuz | `nvidia-smi` sürümü → uygun `cu*` değeri → `docker compose build docling` |
| Belgeler `degraded` işaretleniyor | docling erişilemiyor, yönlendirici hızlı yol metniyle devam ediyor | `curl 127.0.0.1:3941/health` |
| Panelde durdur/başlat düğmeleri hata veriyor | `CONTROL_PANEL_DEPLOYMENT=native` kalmış | systemd biriminde `docker` olarak eziliyor; birim gerçekten kurulu mu |
| Panel açılıyor ama 403 | `CONTROL_PANEL_ALLOWED_NETWORKS` yanlış CIDR | Sunucunun gerçek LAN bloğunu yazın |
| `docker` komutu izin hatası | Grup üyeliği oturuma yansımadı | Oturumu kapatıp açın |
| `.env` değerleri tuhaf davranıyor | Windows'tan gelen CRLF | `sed -i 's/\r$//' .env` |

## Geri dönüş

Windows makinesine dokunulmuyor. Ubuntu'da bir sorun çıkarsa Windows yığınını
`start_office_server.ps1` ile geri açmak yeterli; ekip istemcilerinin MCP adresini eski
IP'ye çevirmesi gerekir. Bu yüzden **Ubuntu doğrulanana kadar Windows kurulumunu
silmeyin**.
