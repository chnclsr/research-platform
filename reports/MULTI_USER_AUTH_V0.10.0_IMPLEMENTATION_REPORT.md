# Kullanıcı Kimliği ve Koşu Sahipliği

Platform sürümü: `v0.10.0`

Belge sürümü: `1.1`

Tarih: `2026-08-18`

## Gerekçe

Kontrol paneli tüm geçmiş araştırmaları ayrım gözetmeksizin gösteriyordu. Sistem ekibe
açıldığında her kullanıcının kendi hesabıyla girmesi ve yalnız kendi koşularını görmesi
gerekiyor.

Değişiklik öncesi durum ölçüldü:

| Katman | Koruma | Kimlik |
|---|---|---|
| Panel (8020) | ağ CIDR + süreç ömürlü `CONTROL_TOKEN` | yok |
| API (8000) | tek paylaşılan bearer, `TESTING` iken **devre dışı** | yok |
| MCP (8010) | tek `MCP_BEARER_TOKEN` | yok |
| Telegram | `TELEGRAM_ALLOWED_USER_IDS` | var, ama koşuya bağlanmıyor |
| `research_runs` | — | sahiplik sütunu yok |

`CONTROL_TOKEN` süreç başına üretilip HTML'e gömülüyordu; sayfayı açabilen herkes tam
yetki alıyordu — koşu verisi, tüm servis logları ve container başlat/durdur dahil.

Panel dışarı açık değildi (`CONTROL_PANEL_HOST=127.0.0.1`, `ALLOWED_NETWORKS=[]`), yani
fiilen sızan veri yoktu. Bu iş, paneli açmadan önceki hazırlıktır.

## Kararlar

Kullanıcı onayıyla: yerel hesaplar (kurumsal SSO değil); katı özel görünürlük (sahip +
yönetici, paylaşım yok); dört yüzeyde de kimlik (panel, Telegram, Langflow, doğrudan
API/MCP).

## Mimari

### Tek kavram: `Principal`

Üç kimlik bilgisi türü aynı `Principal`'a (`user_id` + `role`) çözülür. Yeni bir kimlik
bilgisi türü eklemek `resolve_principal` içine bir dal eklemek demektir; aşağı akıştaki
hiçbir şey değişmez.

| Kimlik bilgisi | Kullanan | Çözüm |
|---|---|---|
| Oturum çerezi (HMAC imzalı) | Panel kullanıcısı | çerez → `user_id` → DB'den rol, `is_active`, `token_version` |
| Kullanıcı API anahtarı `rp_<prefix>.<secret>` | Betikler, MCP, Langflow | `prefix` ile indeksli arama, `secret` scrypt ile doğrulanır |
| Servis token + `X-Actor-User` | Panel→API, Telegram botu | servis token doğrulanır, ancak o zaman başlıktaki kullanıcı üstlenilir |

Üçüncüsü, kendi kullanıcılarını *kendileri* doğrulayan güvenilir aracılar için. Başlık
tek başına hiçbir şey kanıtlamaz.

Parola ve anahtar özeti için stdlib `hashlib.scrypt` — yeni bağımlılık yok. Panel host
üzerinde `.venv`'den, servisler container'da çalıştığı için wheel gerektiren bir derleme
bağımlılığı tam olarak ikisinden birini bozardı. Kayıt biçimi kendini tanımlıyor
(`scrypt$n$r$p$salt$hash`), parametreler kayıtta taşındığı için iş faktörü ileride
yükseltilebilir. Ölçüm: tek doğrulama ~62 ms.

### Zorlama noktası: `Repository`, route değil

Panelin **iki okuma yolu** var — doğrudan DB ve API proxy. Route'ta filtrelemek diğerini
sızdırır. Filtre bu yüzden veri katmanında.

`Repository(session, *, actor)` **fail-closed**: actor yokken koşuya bağlı okumalar
`ActorRequired` fırlatır. `settings.testing` bu filtreyi etkilemez — kapanabilen bir
filtre test altında hiçbir şey kanıtlamaz.

### Neden metasınıf

`Repository`'de `run_id` alan **25 metot** var. Her birine elle iki satırlık koruma
eklemenin başarısızlık biçimi sessizdir: 26. metot korumasız eklenir ve hiçbir yerde hata
üretmeden başkasının verisini okur.

`_OwnershipEnforced` metasınıfı kuralı sınıf oluşturulurken uygular. `run_id` parametresi
alan yeni bir metot, kimse bir şey yapmadan korunur; muafiyet `_UNGUARDED_RUN_METHODS`
içinde adlandırmayı gerektirir ve o küme testte beklenen değerle karşılaştırılır. Muafiyet
iki metot: `create_run` (henüz kontrol edilecek koşu yok) ve `_guard_run` (kendini
çağırırsa sonlanmaz).

Doğrulandı: metasınıflı bir sınıfa sonradan eklenen `export_everything(run_id)` metodu
çağrıldığında `RunAccessDenied` aldı — hiçbir ek kod yazılmadan.

### Yabancı koşu 404 döner, 403 değil

403 koşunun var olduğunu doğrular. Eksik koşu ile yabancı koşu bilerek ayırt edilemez.
API'de merkezî bir istisna işleyicisiyle uygulanır — 20'den fazla koşu uçlu route'ta
route başına `try/except` bir unutulmuş blok uzaklıktadır.

## Şema — migration `0007_user_identity`

```
users               id · email(unique) · display_name · password_hash · role
                    is_active · token_version · created_at · last_login_at
api_keys            id · user_id · name · prefix(unique) · secret_hash
                    created_at · last_used_at · revoked_at
telegram_identities telegram_user_id(PK) · user_id · linked_at
research_runs       + owner_id (indeksli)
users (0008)        + telegram_link_code_hash · telegram_link_expires_at
```

`token_version` artırmak kullanıcının tüm çerezlerini düşürür — sunucu tarafı oturum
tablosu olmadan iptal yolu. Parola değişimi ve hesap kapatma bunu artırır.

`owner_id` nullable bırakıldı ve öyle kalıyor. Sahipsiz koşu **yalnız yöneticiye**
görünür; sütun bu yüzden açık değil, kapalı tarafa düşer. NOT NULL koymak, koşu barındıran
bir veritabanında migration'ı çökertirdi.

Depodaki 14 tablonun hiçbirinde ForeignKey yok; kimlik tabloları da bu biçime uydu.
Hesaplar silinmez, kapatılır (`is_active=False`) — silinen bir satır, koşularını kimsenin
elinde olmayan bir kimliğe bırakırdı.

## Yüzey yüzey kimlik damgalama

**Panel.** Oturum çerezi (HttpOnly, SameSite=Lax, TLS arkasında Secure). `CONTROL_TOKEN`
yerine oturuma bağlı türetilmiş CSRF jetonu — saklanmaz, farklı bir hesap altında
tekrar oynatılamaz. Giriş denemesi adres başına sınırlı (8 deneme / 5 dakika).

Panelde daha önce **koşu oluşturma ucu yoktu**; koşular API, bot, Langflow ve Zotero
üzerinden doğuyordu. Bu, panelin gösterdiği hiçbir şey için "bu kimin?" sorusunu
cevaplayamaması demekti. Uç eklendi; sahip doğrudan oturum kullanıcısı.

Yetki ayrımı — hepsi aynı token'ın arkasındaydı:

| Uç | Yeni kural |
|---|---|
| `/api/status`, `/api/runs/*` | sahibine ait veriyle sınırlı |
| `/api/system/{action}` | **yalnız yönetici** — container başlat/durdur |
| `/api/logs/{service}` | **yalnız yönetici** — loglar her kullanıcının koşusunu karıştırır |
| `/api/connectors/{id}/test` | yalnız yönetici — dış servise kurulum kimlik bilgisiyle çağrı |

Bu ayrım olmadan login koymak, giriş yapan her kullanıcıya worker'ı durdurma düğmesini
vermek olurdu.

**Telegram.** İzin listesi kimin botu kullanabileceğini söyler; koşunun kime ait olacağını
söylemez. `telegram_identities` eşlemesi eklendi. Eşlenmemiş ama izinli bir kullanıcı,
sessizce sahipsiz koşu üretmek yerine bağlanma komutunu görür.

> **Not (2026-08-18):** Bu paragraftaki iki kapılı düzen kısmen aşıldı. İzin listesi
> birebir sohbetlerde emekli edildi ve eşleme self-servis hâle geldi; ayrıntı için
> aşağıdaki "Telegram: self-servis bağlama ve izin listesinin emekliliği" bölümüne bakın.

**Langflow / MCP / betikler.** Kullanıcı başına API anahtarı. Panelde üretilir ve iptal
edilir; kabuktan `research-admin issue-key` / `revoke-key`.

**Zotero.** Plan bir `ZOTERO_SYNC_OWNER_EMAIL` ayarı öngörüyordu. Uygulama sırasında
zamanlanmış Zotero işi olmadığı doğrulandı — sync her zaman API isteğiyle tetikleniyor,
dolayısıyla her zaman bir istek sahibi var. Ayar gereksizdi, eklenmedi.

## Telegram: self-servis bağlama ve izin listesinin emekliliği

*(Belge sürümü 1.1 — ilk sürümden sonra eklendi.)*

İlk uygulamada eşleme yalnız yöneticiyle kuruluyordu: her kişi için
`research-admin link-telegram`. İki sorunu vardı — ölçeklenmiyordu ve kullanıcının kendi
`telegram_user_id` değerini bulup yöneticiye iletmesini gerektiriyordu.

Şimdi kullanıcı kendi bağlıyor: panelde **Hesabım → Bağlantı kodu al**, sonra bota
`/baglan <kod>` ya da `t.me/<bot>?start=<kod>` derin bağlantısı. Panel oturumu kişinin kim
olduğunu zaten kanıtladığı için kod yalnız o kanıtı Telegram tarafına taşır.

Kod `users` satırında **hash'lenmiş** durur (migration `0008`), 5 dakika geçerlidir ve
**tek kullanımlıktır**. Tek kullanım şart: kod sızarsa, başkası *kendi* Telegram hesabını
kurbanın platform hesabına bağlayıp onun adına araştırma başlatıp okuyabilirdi. Kısa ömür
tek başına yeterli değil.

Kodu ayrı bir tablo yerine kullanıcı satırında tutmak bilinçli: bir kullanıcının aynı anda
tek bekleyen kodu olabilir, yeni kod eskisini ezer ve tüketim iki sütunu da temizler. Böylece
tek kullanım, tüketen kodun hatırlaması gereken bir davranış değil, **şemanın özelliği** olur.

Kod alfabesi ekrandan okunup telefona yazıldığı için karıştırılan glifleri (`O/0`, `I/1/L`)
dışarıda bırakır; panel `M3H-QES` biçiminde gösterir, bot tire, boşluk ve küçük harfi kabul eder.

### İzin listesi neden emekli edildi

`TELEGRAM_ALLOWED_USER_IDS`, kimliğin olmadığı dönemde **kimliğin yerine konmuş bir vekildi.**
Gerçek kimlik gelince vekil yalnız engel olur: kullanıcı kendini başarıyla bağlar, sonra liste
onu reddeder — çünkü ID'si `.env`'de yazılı değildir.

Yeni kural: **bağlı olmak yetkili olmak demektir.** Birebir sohbetler açıktır; bağlanmamış
birine yalnız `/start`, `/yardim`, `/whoami` ve `/baglan` çalışır.

Liste **grup sohbetlerinde** korundu, çünkü orada soru farklıdır: bir grupta mesajı gönderen
kişi ile botun adına hareket etmesi gereken kişi aynı olmayabilir. `_authorized()` yerine gelen
`_chat_allowed()` adı bu ayrımı taşıyor — "bu sohbet uygun mu", "bu kişi kim" değil.

### Doğrulama

Canlı kurulumda geçici bir hesapla: kod üretildi, panelin gösterdiği biçimde (`ufr-ajq`, küçük
harf ve tireli) tüketildi, eşleme kuruldu; **aynı kod ikinci bir Telegram hesabıyla denendiğinde
reddedildi** ve o hesap bağlanmadı. Ayrıca 6 birim testi: derin bağlantı yolu, süresi geçmiş kod,
yanlış kod, biçimli kod ve tek kullanım.

Uygulama sırasında bir aksama fark edildi: sahiplik zorunluluğu eklendiğinde eşleme tablosu boştu,
dolayısıyla bot **fiilen kilitlenmişti** — izinli tek kullanıcı bile "hesabınız bağlı değil"
yanıtı alıyordu. Şema değişikliğinin veri gerektirdiği durumlarda göç adımının kendisi de
doğrulanmalı; migration'ın geçmesi özelliğin çalıştığı anlamına gelmiyor.

## Ortak korpus: sessiz sızıntı yolu

`list_corpus_passages` deposundaki **tek kasıtlı koşular arası okuma**. Geçmiş
araştırmaların pasajları yeni koşuyu besler. Kapsamlandırılmazsa, bir kullanıcının yeni
koşusu başkasının hesabı altında toplanmış metinle beslenirdi — aynı sızıntı, arka
kapıdan.

Kritik ayrıntı: kapsam **çağıranı değil, kurulan koşunun sahibini** izler. Pipeline
koşuları sistem asli olarak yürütür; çağırana göre kapsamlamak her kullanıcının metnini
her koşuya verirdi. `CORPUS_SCOPE=owner` varsayılan; `global` eski davranışı bilinçli ve
belgelenmiş bir paylaşım olarak geri getirir.

## Uçtan uca doğrulama

Canlı kurulumda, iki gerçek hesapla:

| # | Senaryo | Sonuç |
|---|---|---|
| 1 | Öğrenci koşu listesi | 0 koşu |
| 2 | Yönetici koşu listesi | 9 koşu |
| 3 | Öğrenci → yöneticinin koşusu (`/`, `/sources`, `/claims`, `/coverage`, `/events`) | hepsi **404** |
| 4 | Yönetici → aynı uçlar | hepsi 200 |
| 5 | Öğrenci → yöneticinin rapor dosyası | **404** (yönetici 200) |
| 6 | Öğrenci → yöneticinin koşusunu iptal | **404** |
| 7 | Kimlik bilgisi yok / uydurma anahtar | 401 |
| 8 | Korpus araması: öğrenci 0 sonuç, yönetici 10 | kapsamlı |
| 9 | Panel oturumsuz: `/` → `/login`, `/api/status` → 401 | ✓ |
| 10 | Yanlış parola ve bilinmeyen hesap aynı yanıt | ✓ |
| 11 | Öğrenci + **geçerli CSRF** → `/api/system/stop` | **403** "yönetici yetkisi gerektirir" |
| 12 | Yönetici → `/api/logs/worker` | 200 |
| 13 | Geçerli oturum, CSRF yok/yanlış | 403 |
| 14 | Hesap kapatıldı → eski çerez | 401; yeniden açıldıktan sonra da 401 |
| 15 | Panelden koşu oluşturma | sahip = oturum kullanıcısı |
| 16 | İptal edilen API anahtarı | 401 |

11. senaryo iki kez çalıştırıldı. İlk turda CSRF jetonu kabuk komutunda bozulmuştu ve 403
yanlış nedenle geliyordu — bozuk jeton da 403 verir. Jeton doğru çıkarılıp tekrarlandı;
yanıt gövdesi "Bu işlem yönetici yetkisi gerektirir" olduğu için reddin yetki
kontrolünden geldiği doğrulandı. Bir güvenlik testinde doğru durum kodu, doğru gerekçe
demek değildir.

Ek olarak: `ruff check` yeni dosyalarda temiz, **217 test** geçiyor (öncesi 195; 16'sı
sahiplik uygunluk paketi, kalanı panel oturumu ve Telegram eşlemesi).

## Göç

1. Migration öncesi `pg_dump` alındı (132 MB).
2. `docker compose up -d --build` — migration `0007` uygulandı.
3. `research-admin bootstrap` ile ilk yönetici oluşturuldu; **9 mevcut koşu** ona
   devredildi. Komut, hesap varken ikinci kez çalışmayı reddediyor — aksi hâlde canlı
   sistemde yönetici basmanın yolu olurdu.
4. `SERVICE_TOKEN`, `SESSION_SECRET`, `CORPUS_SCOPE` `.env` ve `.env.office` dosyalarına
   üretildi. Bunlar gitignore'da; başka bir makinede elle üretilmeleri gerekir.
5. Panel `scripts/start_control_panel.ps1` ile yeniden başlatıldı ve `/health` 0.10.0
   döndürdüğü doğrulandı.

## Yan bulgu: 8010 portu

`mcp-gateway` portu **tüm arayüzlere** bağlıydı (`"8010:8010"`), diğer tüm servisler
`127.0.0.1` kullanıyordu. Tek paylaşılan bearer token tutan bir ajan geçidini yerel ağa
açıyordu. `127.0.0.1:8010:8010` yapıldı.

## Kalan sınırlar

- **Yedekleme scripti sahiplik sınırının dışında.** `scripts/sync-research-reports.ps1`
  paylaşılan token'la *tüm* koşuların paketini indiriyor. `OPEN_ITEMS.md`'ye madde olarak
  eklendi.
- **Denetim kayıtları log dosyasında**, tabloda değil. `events` tablosu `run_id` ile
  anahtarlı; bir giriş hiçbir koşuya ait değil. Giriş, yetki reddi ve anahtar üretimi
  `research_platform.audit` logger'ına yazılır.
- **Giriş hız sınırı süreç içi.** Panel tek uvicorn süreci olduğu için yeterli; paylaşımlı
  bir depo bu kurulumun başka türlü ihtiyaç duymadığı altyapı olurdu.
- **Parola sıfırlama e-postası yok** — `research-admin set-password` ile yapılır.
- **Koşu paylaşımı yok.** Katı özel seçildi; gerekirse `run_members` tablosu eklenir.
- **Panel `0.0.0.0`'a ancak TLS arkasında bağlanmalı.** Çerez `Secure` bayrağı
  `CONTROL_PANEL_HTTPS` ile açılır; düz HTTP'de açılırsa çerez kullanılamaz hâle gelir.
