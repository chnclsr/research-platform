# Research Platform Yerel Kontrol Paneli

Belge sürümü: `3.3`

Platform sürümü: `v0.15.0`

Tarih: `2026-08-28`

## Amaç

Kontrol paneli, ana araştırma servislerinden bağımsız çalışan yerel bir supervisor'dır. API, worker,
MCP veya Telegram kapatılsa bile panel açık kalır ve sistem yeniden panel üzerinden başlatılabilir.

Panel adresleri:

- Sunucu bilgisayarı: `http://127.0.0.1:1111`
- Aynı ağdaki ekip bilgisayarları: `http://10.0.10.179:1111`

Adres ve port sabit değildir; `.env.office` içindeki `CONTROL_PANEL_HOST` ve
`CONTROL_PANEL_PORT` belirler. Yukarıdakiler bu makinedeki güncel değerlerdir.

Panel `0.0.0.0` üzerinde dinler; uygulama katmanı yalnız yapılandırılmış CIDR'ı ve loopback
istemcilerini kabul eder. Windows Firewall'da da yalnız `LocalSubnet` istemcilerine izin veren
bir kural bulunmalıdır. Panel internet yönlendiricisinde port-forward edilmemelidir.

## Giriş ve yetkiler

**v0.10.0'dan itibaren panel giriş gerektirir.** Adresi açan herkes `/login` sayfasına yönlendirilir
ve giriş yaptıktan sonra **yalnız kendi araştırmalarını** görür.

Panelde **kayıt formu yoktur.** Hesaplar kabuktan açılır; komutlar ve ekip yönetimi akışı
[OFFICE_TEAM_SETUP.md](OFFICE_TEAM_SETUP.md) "Hesap yönetimi" bölümündedir.

İki rol var ve fark, kullanıcı verisiyle kurulum operasyonları arasındadır:

| | `user` | `admin` |
|---|---|---|
| Kendi araştırmaları | ✔ | ✔ |
| **Başkalarının araştırmaları** | ✘ | ✔ |
| Başkalarının **süren** işleri | sansürlü liste | ✔ tam |
| Duraklat/devam/iptal, öncelik | kendi koşularında | tümünde |
| Rapor indirme | kendi koşularında | tümünde |
| Kendi API anahtarlarını üretme/iptal | ✔ | ✔ |
| Bekleyen HITL checkpoint'ini **görme** | kendi koşularında | tümünde |
| HITL sorularını **yanıtlama** | ✘ — koşunun kanalından | ✘ — koşunun kanalından |
| **Başlat / Yeniden başlat / Servisleri durdur** | ✘ | ✔ |
| **Servis logları** | ✘ | ✔ |
| **Connector testi** | ✘ | ✔ |

`user` rolündeki birine yönetici düğmeleri ve log sekmesi hiç gösterilmez; sunucu tarafında da
403 döner.

### Aktif Koşular

Tek GPU paylaşıldığı için kullanıcı, **başkalarının süren araştırmalarını sansürlü olarak**
görür — yoksa kendi koşusu sırada beklerken bomboş bir tablo görür ve sistemi bozuk sanır.

"Aktif Koşular" tablosunda yalnız şunlar vardır: **kimin çalıştırdığı, durum, aşama,
kuyruk sırası ve geçen süre.** Başlık, araştırma sorusu, kaynaklar, iddialar, coverage ve
koşu kimliği **görünmez**; satır tıklanamaz ve üzerinde işlem yapılamaz.

Liste boşken bölüm hiç görünmez. Yöneticide de görünmez — onların ana tablosu zaten her
koşuyu tam gösteriyor.

Ayrımın gerekçesi: bu üç yetki kurulumun tamamını etkiler. Log akışı her kullanıcının koşusunu
birbirine karıştırır, "Servisleri durdur" başkasının süren araştırmasını keser ve connector testi
kurulumun kendi kimlik bilgileriyle dışarıya çağrı yapar.

### Hesabım sekmesi

Her kullanıcı kendi hesabını buradan yönetir; yönetici gerekmez.

- **Parola.** Mevcut parola + yeni parola ile değiştirilir. Mevcut parolanın sorulması
  isteğe bağlı bir adım değil: panel düz HTTP üzerinden ağa açık, dolayısıyla oturum
  çerezini ele geçiren biri sorulmasaydı hesabı kalıcı olarak devralabilirdi.
  Değişiklikten sonra **diğer cihazlardaki oturumlar kapanır**, kullanıcının kendi
  sekmesi açık kalır. API anahtarları etkilenmez — ayrı kimlik bilgileridir ve
  susturulmaları Langflow/MCP bağlantılarını sessizce bozardı.
  Parolasını **unutan** kullanıcı için hâlâ yönetici gerekir
  (`research-admin set-password`), çünkü sıfırlama e-postası yoktur.

- **Telegram bağlantısı.** *Bağlantı kodu al* → **Telegram'da aç** düğmesi ya da bota
  `/baglan <kod>`. Kod 5 dakika geçerli ve tek kullanımlıktır. Bağlandıktan sonra bottan
  başlatılan araştırmalar o hesaba ait olur ve panelde yalnız o kişiye görünür.
  *Bağlantıyı kaldır* ile geri alınır.
- **API anahtarları.** Betik, Langflow ve MCP erişimi için. Anahtar üretildiği anda **bir kez**
  gösterilir, sonra geri alınamaz; kaybedilirse iptal edip yenisi üretilir. İptal edilen anahtar
  anında çalışmaz olur.

### Oturum davranışı

- Oturum çerezi 12 saat geçerlidir (`SESSION_MAX_AGE_SECONDS`).
- Parola değiştirmek veya hesabı kapatmak, o kullanıcının **açık tüm oturumlarını anında düşürür.**
- Panel yeniden başladığında oturumlar korunur — ancak `.env.office` içinde `SESSION_SECRET`
  tanımlıysa. Boş bırakılırsa her yeniden başlatma herkesi çıkışa zorlar.
- Art arda 8 başarısız giriş, o IP adresini 5 dakika kilitler.
- Yanlış parola ile var olmayan hesap **aynı** yanıtı verir; form hesap var mı diye yoklamak için
  kullanılamaz.

Panel düz HTTP üzerinden çalıştığı sürece oturum çerezi ağda açıktır; ofis CIDR sınırı bu yüzden
kaldırılmamalıdır. TLS arkasına alınırsa `.env.office` içinde `CONTROL_PANEL_HTTPS=true`
yapılmalıdır — çerez ancak o zaman `Secure` bayrağını taşır.

## Görünen bilgiler

- API, worker, MCP ve Telegram process/PID durumu.
- PostgreSQL ve Redis erişilebilirliği.
- ARQ queue derinliği, çalışan/bekleyen iş sayısı ve worker heartbeat TTL'i.
- Ollama erişimi ve bellekte yüklü yerel model.
- Aktif ve sıradaki araştırmalar: durum, aşama ilerleme çubuğu, sıra, tur, kaynak ve iddia sayısı.
- Ekipteki diğer kullanıcıların süren işleri, sansürlü: kim, durum, aşama, sıra ve süre.
- Son 20 terminal araştırma: tamamlandı, eksik tamamlandı, iptal veya hata.
- Worker, API, MCP, Telegram ve panel loglarının son bölümü.
- Run bazında pipeline zaman çizelgesi, aşama süreleri, checkpoint ve yapılandırılmış event’ler.
- Run detayında tamamlanan/aktif/bekleyen düğümleri, ziyaret sayılarını ve recovery geri dönüşünü
  gösteren yatay LangGraph flow chart.
- Kaynak hunisi, `accept / reserve / reject` dağılımı ve her eleme aşamasındaki kayıp.
- Sentinel recall, estimated completeness, relative recall, citation novelty ve reserve false-negative ölçümleri.
- Query branch başına connector, sonuç, başarı ve gecikme bilgisi.
- Kaynakların connector, aile, admission, keşif yöntemi, relevance ve provenance bilgisi.
- Connector health, credential eksikleri, çağrı başarı oranı, ortalama/p95 gecikme ve hata sınıfları.
- RTX 4060 kullanım, VRAM, sıcaklık ve güç; CPU, RAM, disk ve model telemetrisi.
- Araştırma çıktı paketlerini panelden güvenli indirme.
- HITL checkpoint geldiğinde bekleyen kararın kartı: sorular ve seçenekleri, planın tamamı,
  taslak ve kaynak domainleri AI önerileriyle. **Kart salt-okunurdur** — yanıt, koşunun
  başlatıldığı kanaldan verilir (Telegram düğmeleri, MCP `respond_to_research_checkpoint`).
  Aynı kapıya iki yerden cevap verilebilmesi, sohbette bekleyen düğmeleri geçersiz kılıyordu.

## Kontroller

- **Başlat** *(yalnız admin)*: PostgreSQL, Redis, MinIO ve Crawl4AI durumunu doğrular; API, worker,
  MCP ve Telegram'ı başlatır.
- **Yeniden başlat** *(yalnız admin)*: Aynı güvenli başlangıç akışını çalıştırarak native servisleri
  yeniler.
- **Servisleri durdur** *(yalnız admin)*: API, worker, MCP ve Telegram'ı durdurur. Panel ile veri
  container'ları açık kalır; PostgreSQL/Redis verisi ve araştırma kayıtları korunur.
- **Duraklat / Devam / İptal:** Run yaşam döngüsü komutlarını Research API'ye gönderir. Aktif LLM veya
  acquisition çağrısı zorla kesilmez; değişiklik güvenli düğüm sınırında uygulanır. Kullanıcılar
  yalnız kendi koşularında uygulayabilir.
- **Çıkış:** Oturumu kapatır ve giriş sayfasına döner.

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
