# `developments-supplementer` Branch Değişiklik Raporu

Platform sürümü: `v0.15.0`

Belge sürümü: `12.32`

Son güncelleme: `2026-08-27`

## Kapsam

Bu belge `developments-supplementer` branch'inde yapılan tüm değişiklikleri tutar. Yeni iş yapıldıkça
yeni bölüm olarak buraya eklenir; ayrı rapor dosyası açılmaz.

| # | İş | Commit |
|---|---|---|
| 1 | AgentSearch adaptörü | `fdbfbff` |
| 2 | NORMALIZE checkpoint boyut hatası | `5f0ac23` |
| 3 | Adaptörün compose'a taşınması | `09ea1b6` |
| 4 | Kontrol panelinin Docker uyumluluğu | `8bc484c` |
| 5 | Checkpoint temizleme ve boyut koruması | `d55455d` |
| 6 | MinIO verisinin bind mount'a taşınması | `c5408de` |
| 7 | Teslimat izin hatası ve koşu bazında yerel yedekleme | `7caa407` |
| 8 | Parser mimarisinin servisleştirilmesi | `a58874a` |
| 9 | Parser seçim kararı: deterministik + açık override | `ec88283` |
| 10 | Word raporunda kaynak çapraz referansları | `63b74ed` |
| 11 | Kullanıcı kimliği ve koşu sahipliği (kendi raporu var) | `3f9a191` … `84cddde` |
| 12 | Panelden parola değiştirme | `fc3199d` |
| 13 | Ekip kuyruğunun sansürlü görünürlüğü | `fc3199d` |
| 14 | MCP'de kişisel kimlik | `d88a32a` |
| 15 | Aşama başına araç dökümü (panel) | `b8ec33b` |
| 16 | İkili içerik ve NUL baytı koşuyu düşürüyordu | `b8ec33b` |
| 17 | Zorunlu plan onayı ve zorunlu araştırma süresi | `496a6ac` |
| 18 | Telegram botu SERVICE_TOKEN ve granüler parser motorları | `496a6ac` |
| 19 | Araştırma İngilizce yürüyor, rapor istenen dilde | `210dca6` |
| 20 | Plan ekranı sorunun geldiği dilde | `210dca6` |
| 21 | Telegram: dil seçimi, şıklı planlama söyleşisi | `3f3077e` |
| 22 | Bağlayıcı kapsam soruları, plan düğmeleri, koşu adı | `3f3077e` |
| 23 | Koşu adı kimliğin yerini tutuyor, `/kosular` | `3f3077e` |
| 24 | Öncelikli koşu kuyruğu (kendi raporu var) | `9b1c887` |
| 25 | Donanıma göre paralel koşular (kendi raporu var) | `9b1c887` |
| 26 | Koşuyu izsiz silme: `research-admin purge-runs` | `9b1c887` |
| 27 | Ağır PDF yolu: docling GPU servisi (kendi raporu var) | `e102cd3` |
| 28 | Akış diyagramlarının güncel mimariye uyarlanması | `f330659` |
| 29 | PDF ayrıştırma teşhis raporu ve süre kaydı | `dbb7e43` |
| 30 | Ajan yönergelerinin `AGENTS.md` altında tekleştirilmesi | `dc9b544` |
| 31 | PDF raporunda sayfa seçimleri ve çakışmayan mod adları | `aa62f49` |
| 32 | Jina Reader browser fallback'i | `aa62f49` |
| 33 | GitHub URL akıllı repository işleyicisi | `aa62f49` |
| 34 | Sistem mimarisi diyagramının güncel mimari ve Cezeri derisiyle yenilenmesi | `aa62f49` |
| 35 | Commit/push öncesi zorunlu tam-test kapısı | `22b75c1` |
| 36 | Connector görünümünde SERVICE_TOKEN kimlik doğrulaması | `22b75c1` |
| 37 | Koşu donanım telemetrisi (kendi raporu var) | `22b75c1` |
| 38 | Tek çalışma zamanı sürümü ve telemetri SVG yerleşimi | `22b75c1` |
| 39 | Uygulama sabitlerinin `.env` yönetimine alınması (kendi raporu var) | `22b75c1` |
| 40 | Telemetri çıktı seçimi: `HARDWARE_TELEMETRY_OUTPUT_TYPE` | _çalışma ağacı_ |
| 41 | Bağlam güvenli özet sentezi ve rapor kalite kapısı | _çalışma ağacı_ |
| 42 | Dile göre özet başlığı ve panel ayrıntı düzeni | _çalışma ağacı_ |
| 43 | Panel aydınlık modu ve alaka sıralı kaynaklar | _çalışma ağacı_ |
| 44 | Pipeline zaman çizelgesinin Araştırma Akışı'na birleşmesi | `fe6eb42` |
| 45 | Kaynak figürü caption'ının rapor diline yerelleştirilmesi | `7f47abf` |
| 46 | Literatür konu haritasının Ek B'ye taşınması | `e8788f5` |
| 47 | Word raporunun koşu etiketiyle adlandırılması | `ca56390` |
| 48 | Yapısal çıkarımlarda kaynağı bulan connector | `ca56390` |
| 49 | Düşen koşunun sahibine Telegram bildirimi | _çalışma ağacı_ |

> **Not:** 2. bölümdeki düzeltmenin yetersiz olduğu sonradan anlaşıldı. Gerekçe ve asıl
> çözüm 5. bölümdedir.
>
> **Not:** 27. bölümün ayrıntıları
> [DOCLING_GPU_SERVICE_V0.13.0_IMPLEMENTATION_REPORT.md](DOCLING_GPU_SERVICE_V0.13.0_IMPLEMENTATION_REPORT.md)
> dosyasındadır. O iş, `engines.py`'nin "Docling'e iki yol" kararını ve in-process
> yolun birinci tercih olmasını bilinçli olarak değiştirir; gerekçe orada tablo
> hâlindedir.
>
> **Not:** 13. bölüm, 11. bölümdeki izolasyon kararını bilinçli olarak gevşetir —
> hangi yönüyle olduğu o bölümde tablo hâlinde yazılıdır.
>
> **Not:** 37. bölümün ayrıntıları
> [HARDWARE_TELEMETRY_V0.14.0_IMPLEMENTATION_REPORT.md](HARDWARE_TELEMETRY_V0.14.0_IMPLEMENTATION_REPORT.md)
> dosyasındadır.
>
> **Not:** 39. bölümün ayrıntıları
> [ENV_MANAGED_CONFIGURATION_V0.15.0_IMPLEMENTATION_REPORT.md](ENV_MANAGED_CONFIGURATION_V0.15.0_IMPLEMENTATION_REPORT.md)
> dosyasındadır.

---

## 1. AgentSearch adaptörü

### Olay

Connector kayıt defteri, `/search`, `/read` ve `/health` uçlarını sunan bir AgentSearch
servisi bekler. Bu kurulumda 3939 portunda böyle bir servis yok; orada çıplak bir SearXNG
örneği çalışıyor (`agentsearch-searxng` container'ı, bu compose projesinin dışında yönetiliyor).

Sözleşme uyuşmazlığı ölçüldü:

| Uç nokta | SearXNG yanıtı |
|---|---|
| `/health` | `404` |
| `/search?format=json` | `403 Forbidden` (JSON formatı kapalı) |
| `/read` | Mevcut değil |

Sonuç olarak `/health` çıktısında `agentsearch: degraded` görünüyordu ve AgentSearch
tabanlı yedi connector sonuç döndürmüyordu: `agentsearch_web`, `standards_web`, `eur_lex`,
`official_registry`, `agentsearch_news`, `company_domains`, `institutional_grey`.

Platform bu durumda çökmüyordu; `pipeline.py` içindeki connector çağrıları `try/except` ile
sarılı olduğu için hata yalnızca sonuçsuz arama olarak yansıyordu.

### Uygulanan çözüm

`scripts/agentsearch_adapter.py`, SearXNG API'sini beklenen sözleşmeye çeviren ince bir
FastAPI servisidir. 3940 portunda çalışır.

| Uç nokta | Davranış |
|---|---|
| `/search` | SearXNG JSON yanıtını eşler. `mode=news` → `news` kategorisi, `domain` → `site:` operatörü, `count` karşılanana kadar sayfalama (en fazla 5 sayfa), URL bazında tekilleştirme |
| `/health` | Adaptörün ve upstream SearXNG'nin durumu |
| `/read` | Bilinçli olarak `{"success": false}` döndürür |

`/read` uç noktasının başarısızlık bildirmesi bir eksiklik değil, tasarım kararıdır:
SearXNG'nin içerik okuma API'si yoktur ve platformun kendi doğrudan HTTP çekimi zaten
denenmiştir. Açık başarısızlık, edinim zincirinin JS/yapısal sayfaları işleyebilen
crawl4ai'ye gecikmeden düşmesini sağlar.

Adaptör, `src/` altındaki connector kodu değiştirilmeden yazıldı.

### SearXNG tarafındaki yapılandırma

SearXNG varsayılan olarak JSON çıktısını kapalı sunar. `/etc/searxng/settings.yml` dosyasına
eklendi:

```yaml
search:
  formats:
    - html
    - json
```

Özgün dosyanın yedeği aynı volume içinde `settings.yml.bak` olarak bırakıldı. Örnekte
`limiter: false` olduğu için ek bir hız sınırı önlemi gerekmedi.

**Dikkat:** Bu düzenleme, bu repo tarafından yönetilmeyen bir container'ın anonim Docker
volume'undadır. SearXNG container'ı sıfırdan yeniden oluşturulursa ayar kaybolur ve
`agentsearch` yeniden `degraded` durumuna düşer.

### Doğrulama

- Genel arama: 8 istekte 8 sonuç.
- `mode=news`: haber sonuçları döndü.
- `domain=eur-lex.europa.eu`: dönen tüm URL'ler bu alan adına ait.
- Ruff: başarılı.

---

## 2. NORMALIZE checkpoint boyut hatası

### Olay

`01KZWZKYDV3D686W9PDTFXCQJB` numaralı araştırma (`küçük modüler reaktörlerin maliyet ve
takvim riskleri`, `literature_scan`, 30 dakika bütçe) `FAILED` durumuyla kapandı.

Yüzeydeki belirti acquisition hatası gibi görünüyordu, ancak olay kaydı acquisition'ın
**başarıyla tamamlandığını** gösterdi: 85 adaydan 85'i işlendi, 68'i başarılı oldu ve
`acquisition_metrics` olayı normal biçimde yayınlandı.

Çöküş bir sonraki aşamada, NORMALIZE checkpoint'i PostgreSQL'e yazılırken oldu:

```
asyncpg.exceptions.ProgramLimitExceededError:
total size of jsonb array elements exceeds the maximum of 268435455 bytes
[SQL: INSERT INTO run_checkpoints (run_id, stage, state) VALUES (...)]
[parameters: (... 340207582 characters truncated ...)]
```

PostgreSQL jsonb üst sınırı 256 MiB'dir. Yazılmak istenen state ~324 MiB idi.

### Kök sebep

`AcquiredDocument` iki içerik alanı taşır: `content` (çıkarılmış metin) ve `raw_content`
(dokunulmamış anlık görüntü). PDF'ler için `raw_content`, dosyanın tamamının base64
kodlanmış hâlidir:

```python
raw = (
    response.text if document_type != "pdf"
    else base64.b64encode(response.content).decode("ascii")
)
```

Belge başına indirme sınırı 25 MB'dir (`max_download_bytes`) ve base64 bunu yaklaşık %33
büyütür. NORMALIZE, kaydedilen belgeleri `output["documents"]` içine olduğu gibi koyduğu
için 68 belgenin ham gövdesi LangGraph state'inde taşınıyordu. `Repository.checkpoint()`
ise state'i hiçbir boyut denetimi olmadan jsonb'ye yazar.

Bu koşuda sınırın aşılmasının nedeni, Türkçe sorgunun büyük kurumsal PDF raporlarını
getirmesiydi (`enerji.gov.tr` faaliyet raporu, Sabancı sürdürülebilirlik raporu, kalkınma
kütüphanesi strateji belgeleri).

Checkpoint boyutlarının aşama aşama büyümesi:

| Aşama | State boyutu |
|---|---|
| VALIDATE_PROTOCOL | 2.4 kB |
| DECOMPOSE | 2.4 kB |
| BUILD_QUERY_BRANCHES | 3.1 kB |
| SEARCH | 9.3 kB |
| ACQUIRE | 458 kB |
| NORMALIZE | ~324 MiB — reddedildi |

### Veri kaybı

Toplanan 68 belgenin hiçbiri kalıcılaşmadı. Hata sonrası veritabanı durumu: `sources = 0`,
`source_versions = 0`, yalnızca ACQUIRE'a kadarki 5 checkpoint.

*(Düzeltme: bu bölüm önce "transaction geri alındı" diyordu. Gerçekte belgeler hiç
yazılmamıştı — aşağıdaki nedenle NORMALIZE'ın gövdesi hiç çalışmadı. `save_document`
zaten belge başına ayrı `commit` yapar, dolayısıyla kaydedilmiş belgeler geri alınmaz.)*

### Uygulanan düzeltme

`ResearchPipeline.normalize()` içinde, belge yükü state'e eklenmeden önce `raw_content`
boşaltılır:

```python
payload = document.model_dump(mode="json")
payload["raw_content"] = ""
payload["source_id"] = source.id
payload["source_version_id"] = version.id
saved_docs.append(payload)
```

Bu satıra gelindiğinde ham içerik zaten kalıcıdır:

- MinIO'ya `raw_snapshot_key` altında yazılmıştır,
- `repo.save_document()` ile `source_versions.raw_content` sütununa kaydedilmiştir.

### Neden güvenli

`raw_content`'i state'ten çıkarmanın hiçbir aşamayı bozmadığı, tüm okuma noktaları
izlenerek doğrulandı:

| Kullanım | Konum | Kaynak |
|---|---|---|
| `enrich_publication_date` | `pipeline.py:1258` | NORMALIZE içi, boşaltmadan önce |
| MinIO anlık görüntüsü | `pipeline.py:1355` | NORMALIZE içi, boşaltmadan önce |
| PDF base64 çözme | `pipeline.py:1366` | NORMALIZE içi, boşaltmadan önce |
| Figür analizi | `figure_analysis.py:220,225,406` | `repo.list_source_versions()` — veritabanı |
| Dışa aktarım | `exporter.py:471` | `version.raw_content` — veritabanı |

NORMALIZE'dan sonra `raw_content`'e ihtiyaç duyan her tüketici onu veritabanından okur;
hiçbiri pipeline state'ine bakmaz. `content` alanı state'te korunur, çünkü `chunk_index()`
pasajları doğrudan ondan üretir.

### Doğrulama

- Ruff: başarılı.
- Tam pytest paketi: `155 passed`, yalnız üçüncü taraf Starlette deprecation uyarısı.
- Yeniden derlenen worker image'ı içinde düzeltmenin bulunduğu doğrulandı.

### Bu düzeltme raporlanan hatayı çözmüyordu

`_boundary()` checkpoint'i düğümün **başında** yazar ve `normalize()`'ın ilk satırı budur.
Yani `checkpoint(stage="NORMALIZE")`, NORMALIZE'a *giren* state'i tutar — bu da ACQUIRE'ın
çıktısıdır. Veritabanı bunu doğruluyor: ACQUIRE checkpoint'inde `candidates` var,
`documents` yok.

Sıra şuydu: ACQUIRE 68 belgeyi `raw_content` ile state'e koydu → NORMALIZE başladı → ilk iş
checkpoint → 324 MiB → patladı. **NORMALIZE'ın gövdesi hiç çalışmadı.**

Üç bağımsız kanıt: 5 `stage` olayı ve 5 checkpoint var (altıncısı olay yayınlayamadan öldü),
MinIO'da hiç bucket yoktu (`store.put()` bir kez bile çalışmamış), `sources = 0`.

Yukarıdaki düzeltme `normalize()` gövdesindedir, yani patlayan checkpoint'ten *sonra*
çalışır. NORMALIZE sonrası checkpoint'lerin `raw_content` taşımasını engeller — bu yönüyle
işe yarar — ancak raporlanan çöküşü önlemez. Asıl çözüm 5. bölümdedir.

---

## 3. Adaptörün compose'a taşınması

Adaptör ilk aşamada `.gitignore`'lanmış bir `docker-compose.override.yml` dosyasında
tutulmuştu; amaç takip edilen compose dosyasını upstream ile birebir aynı bırakmaktı. Bu
kısıt kaldırıldığı için servis ve `AGENTSEARCH_URL` bağlantısı `docker-compose.yml` içine
alındı, override dosyası silindi.

`AGENTSEARCH_URL` varsayılanı iki yerde güncellendi:

- `x-app` anchor'ı — `worker` ve `migrate` buradan devralır. Connector'ları çalıştıran
  bileşen `worker` olduğu için asıl etkili olan budur.
- `api` servisi — kendi `environment` bloğu anchor'ı tamamen ezdiği için ayrıca gerekli.

`mcp-gateway` ve `telegram-bot` connector çalıştırmadıkları için değiştirilmedi.

### Doğrulama

Taşıma öncesi ve sonrası `docker compose config` çıktıları karşılaştırıldı. Tek fark
sürücü harfinin büyük/küçük yazımıdır (`c:` / `C:`), bu da Compose'un yol çözümleme
artefaktıdır; anlamsal fark yoktur. Çalışan `worker` container'ında
`AGENTSEARCH_URL=http://agentsearch-adapter:3940` doğrulandı.

---

## 4. Kontrol panelinin Docker uyumluluğu

### Olay

Panel yalnız native kurulum varsayımıyla yazılmıştı. Docker kurulumunda üç sonucu vardı:

1. Servis durumu `logs/*.pid` dosyalarından okunuyordu. Container kurulumunda bu dosyalar
   hiç oluşmadığı için panel API, worker, MCP ve Telegram'ı "kapalı" gösteriyor, üstteki
   genel durum rozeti her şey çalışırken bile `stopped` diyordu.
2. "Başlat" ve "Yeniden başlat" düğmeleri `start_office_server.ps1` çalıştırıyordu. Bu
   betik native süreçler başlatır: `research-api.exe` ve `research-mcp.exe` 8000 ile 8010
   portları Docker container'larında bağlı olduğu için çöker, `research-worker.exe` ise
   port bağlamadığından **başarıyla başlar** ve aynı ARQ kuyruğunda ikinci bir tüketici
   olarak GPU için Docker worker'ı ile yarışır.
3. Log görüntüleyici `logs/<servis>.stderr.log` dosyalarını okuyordu; container logları
   erişilemezdi.

### Uygulanan çözüm

`CONTROL_PANEL_DEPLOYMENT` ayarı eklendi (`native` | `docker`). Varsayılan `native`'dir,
böylece mevcut ofis sunucularının davranışı değişmez.

`docker` modunda:

| Panel işlevi | Native | Docker |
|---|---|---|
| Servis durumu | `logs/*.pid` + PID canlılık kontrolü | `docker compose ps --format json` |
| Başlat | `start_office_server.ps1` | `docker compose up -d` |
| Durdur | `stop_native.ps1` | `docker compose stop api worker mcp-gateway telegram-bot` |
| Yeniden başlat | `start_office_server.ps1` | `docker compose restart <aynı servisler>` |
| Log | `logs/<servis>.{stdout,stderr}.log` | `docker compose logs --tail 400 <servis>` |

Panelin kendi servis adları (`api`, `worker`, `mcp`, `telegram`) compose'daki adlarla birebir
örtüşmediği için `DOCKER_SERVICES` eşlemesi eklendi (`mcp` → `mcp-gateway`,
`telegram` → `telegram-bot`). Arayüz etiketleri ve log rotaları değişmedi.

`telegram-bot` bir compose profili arkasındadır. Panel bu servisi yalnız
`TELEGRAM_BOT_TOKEN` tanımlıysa hedefler; bu, `start_native.ps1`'in native tarafta
uyguladığı koşulun aynısıdır.

Arayüzde çalışan servis için gösterilen metin `PID <n>` yerine artık `detail` alanından
gelir; native modda `PID <n>`, Docker modunda `Up 26 seconds` gibi container durumudur.

### Ortam sızıntısı hatası

İlk canlı denemede "Başlat" düğmesi `migrate` servisini şu hatayla düşürdü:

```
ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5433)
```

Sebep: `start_control_panel.ps1`, panelin **process ortamına** `.env.office` içeriğini
yükler. O dosya native kurulum için yazıldığından `DATABASE_URL` yayınlanmış host portunu
(`127.0.0.1:5433`) gösterir. Compose ise `${VAR}` çözümlemesinde kabuk ortamını proje
`.env` dosyasından **önce** kullanır. Panel `docker compose` çağırınca native adresler
container'ların içine enjekte oldu ve migration container ağı yerine host'a bağlanmaya
çalıştı.

Çözüm olarak `_compose_environment()` eklendi: proje `.env` dosyasının tanımladığı her
anahtar, compose alt sürecine geçirilen ortamdan çıkarılır. Böylece compose bu değerleri
kendi `.env` dosyasından çözer.

### Doğrulama

- Ruff: başarılı.
- Tam pytest paketi: `158 passed` (üç yeni test: compose durum ayrıştırma, telegram profil
  koşulu, ortam sızıntısı koruması).
- Canlı panel üzerinden `Başlat` → HTTP 200, tüm servisler ayağa kalktı, `migrate` temiz
  çıktı.
- Container içinde `DATABASE_URL=postgresql+asyncpg://research:research@postgres:5432/research`
  doğrulandı; native adres sızmadı.
- Canlı panel üzerinden `Durdur` → HTTP 200, dört uygulama servisi durdu, veri
  container'ları ayakta kaldı.
- `api` container logu panel üzerinden okundu.
- Panel genel durumu artık `running`; dördü de `Up <süre>` olarak görünüyor.

---

## 5. Checkpoint temizleme ve boyut koruması

### Yaklaşım

İki tamamlayıcı değişiklik `Repository.checkpoint()` içine eklendi.

**Temizleme.** `checkpoint_payload()`, kalıcılaştırılacak state'ten belge `raw_content`
alanlarını boşaltır. Çağıranın state'i **değiştirilmez**: `_boundary()` state'i `dict(state)`
ile sığ kopyalar, yani belge sözlükleri paylaşılır. Yerinde değiştirme yapılsaydı bellekteki
canlı state de silinir, NORMALIZE ham gövdeyi bulamaz ve MinIO snapshot'ı ile
`source_versions.raw_content` boş kalırdı. Bu yüzden temizleme sözlükleri kopyalayarak
yapılır ve bunu sabitleyen ayrı bir test vardır.

**Koruma.** `_assert_checkpoint_fits()`, serileştirilmiş state 200 MiB'ı aşarsa
`CheckpointTooLarge` fırlatır. Kontrol veritabanına dokunmadan **önce** yapılır; sürücü
kaynaklı bir boyut hatası transaction'ı ve aynı oturumdaki sonraki tüm yazımları — hata
olayının kendisi dahil — geçersiz kılardı. Hata mesajı aşamayı, boyutu ve en büyük üç state
anahtarını listeler.

Sınır neden 200 MiB: PostgreSQL jsonb tavanı 256 MiB'dir; aradaki pay, `checkpoint()`
state'i iki yere birden yazdığı için bırakılmıştır (`run_checkpoints.state` ve
`research_runs.state`).

### Neden bu yol seçildi

Snapshot'ı ACQUIRE'a taşıyıp state'te yalnız anahtar tutmak da değerlendirildi. Üç maliyeti
vardı: NORMALIZE elediği belgeleri de diske yazdıracağı için çöp snapshot (belge başına
25 MB'a kadar), `source_versions.raw_content` kopyasını hiç azaltmaması ve NORMALIZE'a belge
başına bir MinIO `GET` eklemesi. Ayrıca asıl sorunu — checkpoint'in sınırsız büyüyebilmesini
— çözmüyordu; yeterince büyük metin toplandığında yalnız `content` alanları da aynı sınırı
zorlar. Koruma bu ikinci senaryoyu da kapsar.

### Uçtan uca doğrulama

`01KZXHCDRGB3604Q8DVB6P1S6S` numaralı gerçek koşu (`literature_scan`, 12 dakika bütçe,
İngilizce) `completed_incomplete` ile tamamlandı: 10 kaynak, 130 iddia, 7 tur, 23 çıktı.

| Ölçüm | Önceki koşu | Bu koşu |
|---|---|---|
| En büyük checkpoint | ~324 MiB (reddedildi) | 834 kB |
| NORMALIZE checkpoint | yazılamadı | 671 kB |
| MinIO ham snapshot | 0 (bucket bile yok) | 10 nesne, 3.2 MB'lık PDF dahil |
| `source_versions` | 0 | 10 |

Ham veri erişilebilirliği ayrıca doğrulandı:

- `13_raw_sources.jsonl` API üzerinden indirildi: 11.5 MB, 10 kayıt, beşinde ham gövde dolu
  (888 kB / 744 kB / 1553 kB …).
- Boş olan beş kayıt `scholarly_metadata` yöntemiyle edinilmiştir; bu yol akademik API'den
  yalnız üstveri çeker ve zaten hiç ham gövde taşımaz. `direct` ile edinilen beş belgenin
  **beşinde de** ham gövde doludur.
- Figür analizi çıktı üretti (`17a_source_figure_excerpt.png`, `17_figure_observations.json`).
  Bu yol PDF'ler için `version.raw_content` şart koştuğundan, ham PDF baytlarının uçtan uca
  korunduğunun bağımsız kanıtıdır.

- Ruff: başarılı.
- Tam pytest paketi: `161 passed` (üç yeni test: canlı state'in korunması, belgesiz state'te
  işlemsizlik, boyut sınırının açık hata üretmesi ve oturumun kullanılabilir kalması).

### Bilinen sınır

Bir koşu duraklatılıp NORMALIZE checkpoint'inden devam ettirilirse belgelerin ham gövdesi
checkpoint'te bulunmaz. O koşuda MinIO snapshot'ı ham dosya yerine çıkarılmış metni tutar,
`source_versions.raw_content` boş kalır ve PDF figür analizi çalışmaz. Normal koşular
etkilenmez. Tam dayanıklılık için snapshot'ın ACQUIRE aşamasında yazılması gerekir; bu,
yukarıda sayılan çöp snapshot maliyetiyle birlikte gelir.

---

## 6. MinIO verisinin bind mount'a taşınması

### Gerekçe

Ham araştırma verisi (kaynak snapshot'ları, figür görselleri, export çıktıları) sınırsız
büyüyen tek bileşendir. Ölçüm: 10 kaynaklı 12 dakikalık bir koşu ≈ 45.5 MB MinIO + 9.7 MB
Postgres, yani kaynak başına ~5.5 MB.

Named volume'ler kalıcıdır ve container'ları şişirmez; oradaki yaygın endişe yersizdir.
Sorun Windows'a özgüdür: Docker Desktop tüm volume'leri tek bir `docker_data.vhdx`
dosyasında tutar ve bu dosya büyür ama içinden veri silinse bile **kendiliğinden küçülmez**.

Otomatik retention alternatifi değerlendirildi ve **reddedildi**: ürünün provenance ve
reproducibility vaadi, kanıt tabanını otomatik silen bir mekanizmayla çelişir. Link rot
nedeniyle silinen bir snapshot geri getirilemez. Bunun yerine veri, VHDX dışına normal
dosya sistemine alındı; silinince alan gerçekten geri döner, klasör doğrudan incelenebilir
ve yedeklenebilir.

Ölçülen bağlam: `docker_data.vhdx` 69.6 GB, C:'de 30.4 GB boş. Ancak `docker system df`
şişkinliğin **image ve build cache** kaynaklı olduğunu gösterdi (63.5 GB + 9.9 GB); tüm
volume'ler toplamda yalnız 2.16 GB. Yani bu taşıma acil bir alan sorununu değil, uzun
vadeli büyüme yönetimini çözer.

### Değişiklik

`minio` servisinin volume tanımı yapılandırılabilir bir host yoluna bağlandı ve
`minio-data` named volume tanımı kaldırıldı:

```yaml
    volumes:
      - ${MINIO_DATA_DIR:-./data/minio}:/data
```

`MINIO_DATA_DIR` ayarı `.env.example` ve `.env.native.example` dosyalarına eklendi. Asıl
sunucuda geniş diskteki bir yola işaret ettirilebilir.

Kapsam yalnız MinIO'dur. `postgres-data` named volume'de kaldı: Windows bind mount'larında
sahiplik/izin sorunları yüzünden postgres sık sık başlamayı reddeder. MinIO'nun container
içinde **root** (`uid=0`) çalışması, bu riski MinIO tarafında ortadan kaldırır.

### Taşıma

Servisler durduruldu, veri geçici bir container aracılığıyla kopyalandı (named volume
içeriğine host'tan doğrudan erişim Windows'ta güvenilir değildir), compose düzenlendi ve
servisler yeniden başlatıldı. Eski named volume doğrulama tamamlanana kadar silinmedi.

### Doğrulama

- **Veri bütünlüğü:** taşıma öncesi ve sonrası nesne envanteri anahtar bazında
  karşılaştırıldı — 41 nesne, 45.54 MB, **eksik veya fazla anahtar yok**.
- **Servis sağlığı:** `/health` altı bileşende `ok`, MinIO container'ı `healthy`.
- **Okuma yolu:** `13_raw_sources.jsonl` API üzerinden indirildi — HTTP 200, 11 527 166
  bayt, taşıma öncesiyle bayt bayt aynı.
- **Yazma yolu:** yeni bir koşu (`01KZXNZVKBXKTV4C22DT0WYNYB`) `completed_incomplete` ile
  tamamlandı: 5 kaynak, 88 iddia, 25 çıktı. Host klasöründe koşuya ait PDF snapshot'ları ve
  export dizini oluştu; bind mount'un yazılabilir olduğunun doğrudan kanıtı budur.
- **Performans:** belirgin bir yavaşlama gözlenmedi. Bu kontrollü bir ölçüm değildir —
  koşular farklı içeriğe sahiptir — ancak drvfs katmanının kullanımı engelleyecek bir
  maliyet getirmediği görülmüştür.
- Ruff: başarılı. Tam pytest paketi: `161 passed`.

### Davranış değişikliği

`docker compose down -v` artık MinIO verisini **silmez**; bind mount'lar `-v` ile
kaldırılmaz. Bu istenen bir korumadır ancak alışkanlık değişikliği gerektirir.

### Yan bulgu

Taşıma sonrası anahtar düzeni tutarsızlığı host klasöründe gözle görünür hale geldi: kaynak
snapshot'ları bucket kökünde `{run_id}/sources/...` altında, figür ve export çıktıları ise
`runs/{run_id}/...` altında duruyor. Tek bir önek bir koşunun tüm verisini kapsamıyor. Bu,
aşağıdaki açık işler arasında kalmaya devam ediyor.

---

## 7. Teslimat izin hatası ve koşu bazında yerel yedekleme

### Olay

Teslimat uç noktası HTTP 500 dönüyordu:

```
PermissionError: [Errno 13] Permission denied:
'/data/deliveries/01KZXNZVKBXKTV4C22DT0WYNYB_result.zip'
```

`mcp-gateway` ve `telegram-bot` container'ları `uid=10001 (research)` ile çalışıyor, ancak
`gateway-deliveries` named volume'ünün bağlandığı `/data/deliveries` dizini `root` (uid 0,
mod 755) sahipliğindeydi.

Kök sebep: `Dockerfile` bu dizini oluşturmuyordu. Docker, image'da bulunmayan bir mount
noktası için dizini root sahipliğinde yaratır.

`mcp_server.py:292` → `gateway_client.download()` paketi bu dizine yazıp oradan
streamlediği için, yazamayınca istek çöküyordu. Bu **iki özelliği birden** bozuyordu: MCP
client teslimat uç noktası (dolayısıyla `scripts/sync-research-reports.ps1` rapor
eşitleyicisi) ve Telegram'ın `/get` komutu.

### Düzeltme

`Dockerfile`'da mount noktası doğru sahiplikle önceden oluşturuluyor:

```dockerfile
RUN useradd --create-home --uid 10001 research \
    && mkdir -p /data/deliveries \
    && chown -R research:research /data
USER research
```

Docker, **boş** bir named volume'ü ilk bağladığında image'daki dizinin sahipliğini kopyalar.
Mevcut volume root sahipliğinde olduğu için rebuild sonrası bir kez silindi (o sırada boştu,
veri kaybı yok).

### Yedekleme yaklaşımı

Amaç, araştırma verisinin MinIO'dan bağımsız, geri yüklenebilir bir kopyasını yerelde
tutmak.

Önce bir yanlış anlaşılma giderildi: 6. bölümdeki bind mount'tan sonra MinIO container'ı
kullanılıp atılabilir durumda. Container'ın silinmesi, çökmesi, `docker compose down -v`,
image'ın yeniden derlenmesi veya Docker Desktop'ın kaldırılması veriye zarar vermiyor.
Bind mount'un **korumadığı** riskler: disk arızası veya makine kaybı, klasörün yanlışlıkla
silinmesi, MinIO'nun kendi on-disk formatını bozması (bind mount bozulmayı sadakatle
saklar), fidye yazılımı, API üzerinden koşu silinmesi.

Bunlar için bağımsız formatta ikinci bir kopya gerekiyor. `research_bundle.zip` bunu
karşılıyor: bir koşunun **tüm** çıktılarını içeriyor ve ham kaynak PDF'leri
`13_raw_sources.jsonl` içinde base64 olarak dahil (`exporter.py`, `bundle_specs`).

Yeni kod yazılmadı; depoda zaten bulunan `scripts/sync-research-reports.ps1` ve
`scripts/setup-research-output.ps1` kullanıldı. Yapılandırma `scripts/.env` (gitignore
kapsamında): `DELIVERY_MODE=both`, `POLL_SECONDS=300` (script varsayılanı 10 saniyedir ve
canlı teslimat için tasarlanmıştır), `RESEARCH_OUTPUT_DIR` ile hedef klasör.

Kurulum, oturum açılışında `-Loop` ile başlayan bir Scheduled Task kaydeder.

### `-InitializeOnly` tuzağı

`setup-research-output.ps1`, eşitleyiciyi bir kez `-InitializeOnly` ile çalıştırır. Bu,
**mevcut tamamlanmış koşuları "indirilmiş" sayıp** `downloaded-runs.txt`'ye yazar; yani
kurulum öncesindeki koşular hiç yedeklenmez. Kurulumdan sonra eşitleyicinin bir kez `-Force`
ile çalıştırılması gerekir.

İkinci bir incelik: script `Local\ResearchPlatformReportSync` adlı bir mutex kullanır ve
başka bir örnek çalışıyorsa sessizce çıkar. `-Force` çalıştırmasından önce zamanlanmış
görev durdurulmalıdır.

### Yapılandırmayı güvenle güncelleme

`setup-research-output.ps1` hem `.env`'i hem eşitleyici script'ini
`%LOCALAPPDATA%\ResearchPlatformClient` altına kopyalar ve zamanlanmış görev **kopyayı**
çalıştırır. Dolayısıyla `scripts/.env`'i düzenlemek tek başına hiçbir şeyi değiştirmez.

Bu ikili yapı bir kusur değil: script'ler bir dağıtılabilir istemci paketi olarak
tasarlanmıştır (`build_team_access_bundle.ps1`, `install_codex_client.ps1`), o senaryoda
kaynak paket geçicidir ve kurulu kopyanın bağımsız olması istenir. Sunucunun kendisinde
depodan çalıştırıldığında sürtünme yaratan da bu varsayım farkıdır.

Görevi doğrudan depodaki script'e bağlamak (tek kaynak) değerlendirildi ve **tercih
edilmedi**: depo yolu taşıyıcı hale gelir, klasör taşındığında veya branch değiştiğinde
yedekleme sessizce durur. Bir yedek mekanizması için bu kötü bir takas.

Güncellemenin doğru yolu setup'ı yeniden çalıştırmak **değildir** — o, koşulsuz
`-InitializeOnly` çağırdığı için henüz yedeklenmemiş koşuları kalıcı olarak kaçırtır.
Yalnız yapılandırma kopyalanır ve görev yeniden başlatılır:

```powershell
Copy-Item .\scripts\.env "$env:LOCALAPPDATA\ResearchPlatformClient\.env" -Force
Restart-ScheduledTask -TaskName "Research Platform Report Sync"
```

Teşhis notu: `Get-CimInstance Win32_Process | Where-Object CommandLine -like
"*sync-research-reports*"` sorgusu **kendi komut satırını da** yakalar, çünkü filtre dizesi
sorgunun kendisinde geçer. Süreç sayarken `$_.ProcessId -eq $PID` ile kendini ayıklamak
gerekir; aksi halde olmayan ikinci bir örnek görünür.

### Doğrulama

- **İzin:** `/data/deliveries` artık `10001:10001` sahipliğinde ve container içinden
  yazılabilir (önce `Permission denied`).
- **Teslimat uç noktası:** `GET /client/v1/research-runs/{run_id}/delivery/both` → HTTP 200,
  19 164 832 bayt, geçerli ZIP, 22 dosya (önce HTTP 500).
- **Yedeğin geri yüklenebilirliği:** ZIP içinden `16_research_report.docx` çıkarıldı —
  483 505 bayt, doğrudan indirilen referansla birebir aynı, geçerli OOXML
  (`[Content_Types].xml` ve `word/document.xml` mevcut). `13_raw_sources.jsonl` içindeki üç
  ham gövde base64'ten çözüldü ve `%PDF` imzasıyla gerçek PDF oldukları doğrulandı. Yani
  paket MinIO olmadan eksiksiz geri yüklenebiliyor.
- **Mevcut koşular:** `-Force` sonrası üç tamamlanmış koşu ZIP olarak indi (9.85 / 18.28 /
  3.82 MB). Başarısız koşu için doğru şekilde yalnız `_status.json` yazıldı.
- **Otomatik yakalama:** yeni bir koşu 08:31:44'te tamamlandı, zamanlanmış görev onu
  08:33:21'de yedekledi — hiçbir müdahale olmadan, `POLL_SECONDS` sınırının çok altında.
  Paket 18 dosya içeriyor ve `16_research_report.docx` geçerli OOXML olarak çıkarılabildi.
  (Bu koşuda ham gövde yok; dört kaynağın tamamı `scholarly_metadata` yoluyla, yani akademik
  API'den yalnız üstveri olarak alınmış. Paketin 127 kB olmasının nedeni budur.)
- Ruff: başarılı. Tam pytest paketi: `161 passed`.

### Sınırlar

- **Aynı disk zayıf korumadır.** Bu kurulum MinIO bozulmasına, container/API sorunlarına ve
  yanlışlıkla koşu silinmesine karşı korur; disk arızasına veya makine kaybına karşı
  korumaz. Bu makinede tek disk (C:) bulunuyor; asıl sunucuda `RESEARCH_OUTPUT_DIR` farklı
  bir sürücüye veya ağ paylaşımına yönlendirilmelidir.
- **Yalnız tamamlanan koşular yedeklenir.** Devam eden veya `failed` koşular için ZIP
  üretilmez; verileri `data/minio` bind mount'unda kalır.
- **Yedek ZIP'leri üçüncü kopyadır.** Ham veri zaten MinIO ve Postgres'te duruyor; bu
  bilinçli bir dayanıklılık takasıdır.

---

## 8. Parser mimarisinin servisleştirilmesi

### Gerekçe

Ayrıştırma dağınıktı ve genişletilemiyordu: `html_to_markdown` chunking modülünde
(`passages.py`) durup edinim modülünden çağrılıyordu — katman ihlali; PDF çıkarımı
`acquisition.py` içinde satır içiydi; JSON/XML için ayrıştırma yoktu. Yeni parser eklemek
`acquisition.py`'a girmeyi gerektiriyordu, bu da birden fazla katkıcıyla çakışma üretirdi.

Ölçülen kalite sorunları (test edilerek doğrulandı):

| Girdi | Önceki çıktı |
|---|---|
| `<table>` satırı | `Reactor Cost (USD/kW) Year` — sütun ayracı yok, hangi sayının hangi sütuna ait olduğu belirsiz |
| `<pre><code>` bloğu | `def total(rows): s = 0 for r in rows: ...` — girinti ve satır sonları düzleşmiş |
| Akademik PDF | `pypdf` ile sütun farkındalığı olmadan; iki sütunlu makalelerde metin karışabiliyor |

Ayrıca crawl4ai hem fetcher hem parser'dı: kendi `fit_markdown`'ını döndürdüğü için aynı
sayfa `direct` ile gelirse bizim ayrıştırıcımızdan, crawl4ai ile gelirse onunkinden
geçiyordu — çıktı tutarsızdı.

### Mimari

Depoda bu desenin çalışan bir örneği zaten vardı (connector'lar), aynen izlendi:

```
connectors/base.py       →  parsers/base.py       (DocumentParser ABC, ParsedDocument)
connectors/registry.py   →  parsers/registry.py   (ParserRegistry, deterministik seçim)
implementations.py       →  parsers/html.py, parsers/pdf.py, parsers/structured.py
```

`AcquisitionService.__init__` registry'yi opsiyonel parametre olarak alıyor; `_direct`,
`_scrapling` ve `_crawl4ai` artık satır içi ayrıştırma yapmıyor. `/v1/parsers` uç noktası
`/v1/connectors` kalıbıyla kayıtlı parser'ları ve yeteneklerini raporluyor.

### Aşama A — davranış değiştirmeyen taşıma

Mevcut mantık birebir aynı çıktıyı üretecek şekilde taşındı. Kanıt: **161 testin tamamı,
tek bir test dosyası bile değiştirilmeden geçti.** `passages.py`, `html_to_markdown`'ı
geriye dönük uyumluluk için yeniden dışa aktarıyor, bu yüzden mevcut import'lar da kırılmadı.

### Aşama B — parser iyileştirmeleri

- **Tablolar:** `td`/`th` işleniyor, çıktı markdown boru ayraçlı. Başlık hücresi yoksa ilk
  satır başlığa yükseltiliyor. Tablolar ayrıca `ParsedDocument.tables` içinde yapısal
  olarak da veriliyor.
- **Kod blokları:** `pre`/`code` içinde boşluk düzleştirme atlanıyor, çıktı ``` çitli.
- **PDF:** PyMuPDF (`fitz`) `get_text("text", sort=True)` ile okuma sırasına duyarlı
  çıkarım; kütüphane yoksa `pypdf`'e düşüyor. `# Page N` başlıkları korundu, dolayısıyla
  pasajların `page_number` alanı bozulmadı.
- **JSON/XML:** ham metin yerine `anahtar.yolu: değer` satırlarına düzleştirme. Gerekçe:
  chunk sınırı bir değeri anahtarından ayırabiliyordu; satır başına bir yaprak bunu önlüyor.

### Aşama C — crawl4ai tutarlılığı

crawl4ai'den artık `cleaned_html`/`html` alınıp kendi parser'ımızdan geçiriliyor; kendi
markdown'ı yalnızca fallback. Böylece üç edinim yolu da aynı yapıyı üretiyor.

### Uygunluk paketi

`tests/test_parsers.py` — katkıcılar bağımsız çalışacağı için sözleşme her parser'ın kendi
testinde değil ortak pakette. Kimlik/yetenek beyanı, bozuk girdide istisna fırlatmama,
registry'nin deterministik seçimi, başlık korunumu ve yeni yetenekler kapsanıyor.

**Paket ilk çalıştırmada gerçek bir kırılganlık buldu:** `PdfParser` bozuk veya yanlış
etiketlenmiş girdide istisna fırlatıyordu. Eskiden bu, `_direct`'in geniş `try/except`'i
içinde yutuluyordu; parser ayrı bir servis olunca kendi başına sağlam olması gerekiyor.
Hem belge hem sayfa düzeyinde korumaya alındı — tek bozuk sayfa artık belgenin kalanını
kaybettirmiyor.

### Doğrulama

- Aşama A: `161 passed`, test dosyalarında değişiklik yok.
- Aşama A+B+C sonrası: `ruff` temiz, `187 passed` (26 yeni test).
- `/v1/parsers` çalışan sistemde üç parser'ı listeliyor; PDF parser'ı container içinde
  `PyMuPDF` backend'ini raporluyor.

**Uçtan uca koşu** (`01KZZWCTFT761V478E2S00SGHC`, `literature_scan`, 12 dakika):
`completed_incomplete` ile tamamlandı — 7 kaynak, 100 iddia, 7 tur, 27 çıktı. Dört edinim
yolu da çalıştı: `direct` (2), `crawl4ai` (2), `local_corpus` (3), `scholarly_metadata` (1).

Pasaj konum bilgisi korundu: 377 pasajın 256'sında `page_number` dolu — PDF sayfa
başlıklarının bozulmadığının kanıtı. PDF çıkarımının gerçekten `fitz` üzerinden geçtiği
çıktının mekânsal hizalamasından görülüyor (sağa yaslanmış "Revision 2" satırı gibi düzen
`pypdf` çıktısında oluşmuyor).

### Bilinen sınır: PDF tabloları hâlâ yapısal değil

Doğrulama koşusunda hiçbir kaynakta markdown tablosu oluşmadı. HTML tablo desteği birim
testleriyle kanıtlı, ancak bu koşuda toplanan HTML kaynaklarında tablo yoktu; asıl tablo
içeren belge bir PDF'ti (INL ileri reaktör maliyet meta-analizi).

`fitz`'in `get_text("text", sort=True)` çağrısı mekânsal düzeni koruyor ama tabloyu
**yapısal olarak** çıkarmıyor — sütunlar boşlukla hizalanmış metin olarak geliyor. PyMuPDF
yeni sürümlerinde `find_tables()` sunuyor; PDF tablolarını `ParsedTable`'a çevirmek ayrı bir
iş olarak duruyor. Altyapı hazır: `ParsedDocument.tables` alanı ve `to_markdown()` mevcut,
yalnız PDF parser'ının bunu doldurması gerekiyor.

### Karar bekleyen: LLM'in parser seçimindeki rolü

Görseldeki 4. aşama bilinçli olarak uygulanmadı. Kısıt: `content_hash` ayrıştırılmış
metinden hesaplanıyor (`acquisition.py`) ve sürüm tekilleştirmesinde kullanılıyor
(`repository.py`); MinIO anahtarı da bu hash'i içeriyor. Parser seçimi koşudan koşuya
değişirse aynı URL farklı hash üretir, dedup kırılır ve pasaj offsetleri kayar — bu,
`10_reproducibility_manifest.json` üreten bir sistemin vaadiyle çelişir.

Registry şu an deterministik seçim yapıyor ve seçim mantığı tek noktada toplandığı için
karar sonradan uygulanabilir. Seçenekler: (a) deterministik seçim + çoklu tipli çıktı —
altyapısı bu commit'te hazır, `ParsedDocument.tables` ve `code_blocks` alanları mevcut;
(b) LLM'in ingestion'da seçmesi — `content_hash`'in ham baytlardan hesaplanmasına geçilmesi
şart; (c) deterministik varsayılan + provenance'a yazılan override. Ayrıca her seçenekte
`parse_document(source_version_id, parser_id)` MCP aracı additive olarak eklenebilir.

---

## 9. Parser seçim kararı: deterministik + açık override

### Karar

8. bölümde açık bırakılan soru — "LLM parser'ı seçsin mi" — **hayır** olarak karara bağlandı.
Yerine iki şey uygulandı: deterministik seçim + protokolden gelen açık override
(*Seçenek 3*), ve parser'ların yapısal çıktısının kalıcılaştırılması (*Eklenti A*).

Kararı üç ölçüm belirledi:

| Ölçüm | Değer | Sonuç |
|---|---|---|
| LLM çağrısı (son koşu, 75 çağrı) | ort. **10.62 sn**, maks 24.63 | Belge başına seçim çağrısı 68-85 belgede 12-15 dk; `max_wall_minutes` 12 olan koşularda bütçenin tamamı |
| `content_hash` kaynağı | Ayrıştırılmış metin | Seçim değişkense dedup kırılır, MinIO anahtarları ve pasaj offsetleri kayar |
| GPU | Tek, 8 GB | Seçime harcanan saniye kanıt çıkarımından çalınır |

LLM'in ingestion'da seçmesi bu üç nedenle reddedildi. Asıl ihtiyaç — "araştırma hedefine
göre doğru içerik gelsin" — Eklenti A ile determinizm bozulmadan karşılanıyor: LLM zaten
retrieval aşamasında seçim yapıyor, orada yapmasının ek maliyeti yok.

### Seçenek 3 — açık override

`ParserSelection` şeması `ConnectorSelection` modelinde eklendi ve `ResearchProtocol.parsers`
alanı olarak bağlandı. Varsayılan boş, yani davranış tamamen deterministik.

```python
ResearchProtocol(..., parsers={"overrides": {"pdf": "plain_text"}})
```

`ParserRegistry.select()` opsiyonel `overrides` alıyor. Override iki koşulu birden
sağlamalı: id kayıtlı olmalı **ve** `can_parse()` o belge türünü kabul etmeli. İkisinden
biri tutmazsa koşu düşmüyor, deterministik seçime geri dönülüyor.

İkinci koşul sonradan eklendi: ilk sürüm override'ı doğrulamadan döndürüyordu, dolayısıyla
`{"pdf": "html"}` gibi uyumsuz bir ayar PDF baytlarını HTML parser'ına verip sessizce çöp
metin üretebiliyordu. Bilinmeyen id güvenle geri dönerken uyumsuz id'nin sessizce bozması
tutarsızdı; ikisi artık aynı davranıyor.

Seçilen parser
`source_versions.provenance.parser_id` alanına yazılıyor — bir denetim, koşunun varsayılanı
mı yoksa override'ı mı kullandığını görebiliyor.

Tasarım gereği override bir **insan/protokol kararı**, koşu içinde belge başına verilen bir
tahmin değil. Hash sapması yalnız bilinçli olarak ve kayıtla oluşuyor.

### Eklenti A — yapısal çıktının kalıcılaştırılması

`AcquiredDocument` `parser_id`, `tables` ve `code_blocks` alanlarını taşıyor; bunlar
`provenance` içinde saklanıyor (JSON sütunu, migration gerekmedi).

Aynı içerik `content` alanında markdown olarak da gömülü kalıyor — pasajlar kendi kendine
yeterli olsun diye. Kalıcılaştırma, ızgarayı isteyen bir tüketicinin markdown'ı yeniden
ayrıştırmak zorunda kalmaması için.

Erişilebilir olması için yeni bir çıktı eklendi: **`18_structured_extracts.json`** — kaynak
başına parser id'si, tablolar (başlık + satır) ve kod blokları. Yalnız yapısal içerik
bulunan koşularda üretiliyor.

### Doğrulama

- Ruff temiz, **190 test** (3 yeni override testi).
- Çalışan worker image'ında doğrulandı: varsayılan seçim `html`, `{"html": "plain_text"}`
  override'ı `plain_text`, bilinmeyen id `html`'e geri dönüyor.
- Protokol `parsers` alanını kabul ediyor; API'den açılan koşuda varsayılan `{}` geliyor.

**Kararlılık koşusu** (`01M003RY3MS8F4B2F139QFF80J`, düzeltme sonrası): `completed_incomplete`
— 6 kaynak, 39 iddia, 7 tur, 21 çıktı. Frontier'a 21 bağlantı sorunsuz eklendi; çöken kod
yolu tam olarak buydu.

`parser_id` beklendiği gibi kaydedildi:

| parser_id | Edinim yolu | Adet |
|---|---|---|
| `html` | crawl4ai | 2 |
| `pdf` | direct | 1 |
| *(boş)* | local_corpus | 2 |
| *(boş)* | scholarly_metadata | 1 |

Son iki yol parser'dan geçmiyor (biri yerel corpus, diğeri akademik API üstverisi), bu yüzden
alan boş — doğru davranış.

### Kararlılık testinde ortaya çıkan mevcut hata

İlk kararlılık koşusu `failed` ile bitti:

```
File "research_platform/repository.py", line 681, in add_frontier_links
    same_domain = canonical.split("/", 3)[2] == source_host
IndexError: list index out of range
```

**Bu bir regresyon değil.** `git log -L 681,681` o satırın `2907ed7` (HITL checkpoint'leri)
commit'inden geldiğini gösteriyor; bu bölümdeki değişikliklerden önce var olan gizli bir
hataydı ve tetiklenmesi toplanan sayfaların bağlantı içeriğine bağlıydı.

Kök sebep: `extract_links()` (`normalization.py`) bağlantıları `http`/`https` şemalarıyla
sınırlıyor, ancak **crawl4ai yolu bu filtreyi uygulamıyordu**. crawl4ai `mailto:`,
`javascript:` ve parça bağlantılarını da bildiriyor; bunlar `canonicalize_url()`'den host'suz
çıkıyor ve `split("/", 3)[2]` indeksi patlıyor. Koşu o anda ne toplamışsa onunla ölüyor.

İki katmanlı düzeltildi:

- **Kök sebep:** crawl4ai bağlantıları da `urlsplit(link).scheme in {"http","https"}` ile
  süzülüyor, diğer edinim yollarıyla aynı davranış.
- **Savunma:** `add_frontier_links` artık host karşılaştırmasını dize bölmek yerine
  `urlsplit(...).hostname` ile yapıyor ve host'suz bağlantıyı koşuyu düşürmek yerine
  atlıyor.

Regresyon testi eklendi (`tests/test_pipeline.py`): `mailto:` ve `javascript:` bağlantıları
içeren bir liste artık yalnız iki geçerli bağlantıyı ekliyor ve istisna fırlatmıyor.

### Ertelenen: Eklenti B ve C

**Eklenti B (protokolden yetenek pazarlığı)** — tasarrufu ölçülen 6.7 kat PDF tablo
maliyetinden geliyor; o maliyet henüz kodda olmadığı için değeri PDF tablo çıkarımı
eklendikten sonra doğar.

**Eklenti C (`parse_document` MCP aracı)** — yeni bir yetenek açmıyor:
`read_research_raw_data(dataset="sources")` zaten `raw_content`'i, yani base64 PDF'i
döndürüyor. Kazandırdığı ergonomi (tek belge hedefleme, bizim parser'ımızın çıktısı) ancak
tür başına ikinci parser eklendiğinde anlam kazanıyor; bugün tek parser varken çağırmak aynı
çıktıyı verir. Arkadaşlar rakip parser eklediğinde tekrar değerlendirilecek.

---

## 10. Word raporunda kaynak çapraz referansları

### Gerekçe

Word raporunda kaynaklar `S01`, `S02` … etiketleriyle anılıyor; etiketler sentez
paragraflarının içinde (`[S03]`), literatür konu haritası tablosunda, figür gözlem
tablosunda ve figür yorum kutusunda geçiyor. Okuyucu bir iddiayı okurken "S03 hangi
kaynaktı?" diye sorduğunda raporun sonundaki kataloğa elle kaydırmak zorundaydı.

### Uygulama

Üç yardımcı eklendi (`word_report.py`): `source_anchor()` etiketten yer imi adı üretir
(`src_S01`); `_add_bookmarked_text()` katalog satırındaki etiketi `w:bookmarkStart` /
`w:bookmarkEnd` ile sarar; `_add_internal_link()` ise mevcut `_add_hyperlink()`'in ikizidir,
tek farkı ilişki (`r:id`) yerine `w:anchor` kullanması ve bu yüzden `part.relate_to`
çağırmamasıdır.

Zemin uygundu: `OxmlElement` ve `qn` zaten import ediliyordu ve `_add_cited_paragraph()`
sentez metnini `re.split(r"(\[S\d{2,3}\])", ...)` ile parçalayıp her atıfı **ayrı bir run**
olarak ekliyordu. Yani atıflar zaten izoleydi; yapılan şey o run'ı köprüye çevirmek oldu.

Bağlanan yerler: sentez paragrafları, literatür konu haritası tablosu, figür gözlem tablosu
ve figür yorum kutusu. Tema kanıt haritası bir PNG olduğu için kapsam dışı.

Figür yorum kutusu tek `cell.text` ataması yerine run run kuruldu — tek atama metni
hedeflenemeyen tek bir run'a çökertiyordu.

### Sarkan bağlantıya karşı koruma

Geçerli etiket kümesi (`linkable_labels`) kaynak listesinden türetiliyor ve bağlantı yalnız
etiket o kümedeyse kuruluyor; değilse eskisi gibi düz mavi metin kalıyor. Word'de var
olmayan bir yer imine bağlantı **sessizce hiçbir şey yapmaz** — kullanıcı tıklar, tepki
alamaz; bu bağlantı olmamasından kötüdür.

### İki şablon ayrı ayrı

`build_word_report()` `synthesis_package` doluysa `_build_synthesis_word_report()`'a
yönlendiriyor. İki şablonun **ayrı katalog tabloları** var, dolayısıyla birini düzeltmek
diğerini düzeltmiyor; ikisi de ayrı ayrı işaretlendi ve ayrı test edildi.

### Doğrulama

- Ruff temiz, **195 test** (5 yeni): bağlantının kurulduğu, ikinci şablonun da kataloğunu
  işaretlediği ve katalogda karşılığı olmayan bir etiketin (`[S07]`) düz metin kaldığı.
- **Gerçek koşu çıktısı** (`01M07BF29WP1YAWNVVN4YYR22R`, 4 kaynak): indirilen
  `16_research_report.docx` açıldı ve `word/document.xml` incelendi —

  | Ölçüm | Sonuç |
  |---|---|
  | Yer imi | `src_S01` … `src_S04` (kaynak sayısıyla birebir) |
  | Benzersiz bağlantı hedefi | `src_S01` … `src_S04` |
  | Toplam iç bağlantı | 11 |
  | Sarkan bağlantı | **yok** |

**Not:** OXML doğru olsa bile Word'ün bağlantıyı atlaması teorik olarak mümkün; dosyanın
Word'de açılıp bir `[S0x]` bağlantısına tıklanarak katalog satırına gittiğinin gözle
doğrulanması önerilir.

### Kapsam dışı

Markdown raporu (`02_full_research_report.md`) değiştirilmedi. Aynı etkiyi orada kurmak
başlık slug'ları ve `[S03](#...)` biçimi gerektirir; ayrı bir iş.

### Yan bulgu

`f"S{index:02d}"` etiketi hem `report_synthesis.py` hem `word_report.py` içinde ayrı ayrı
üretiliyor ve **sıralamanın aynı olduğu varsayılıyor** (ikisi de `enumerate(sources, 1)`).
Varsayım bugün doğru, ancak sessiz bir bağımlılık. Bağlantılar eklendiği için artık bir
uyuşmazlık sarkan bağlantı olarak görünür hâle geldi; doğrulamadaki küme farkı kontrolü
bunu yakalar.

---

## Operasyonel notlar

### `src/` değişiklikleri image rebuild ister

`Dockerfile`, kaynağı image'a gömer (`COPY src` ardından `pip install .`). Bu nedenle
`src/` altındaki bir düzeltme, yalnızca `docker compose up -d` çalıştırıldığında **canlıya
geçmez**; container eski kodu içeren image ile ayağa kalkar.

Bu durum checkpoint düzeltmesi uygulanırken bizzat gözlendi: kod diskte doğruydu, çalışan
worker'da yoktu. Doğru komut:

```powershell
docker compose up -d --build
```

### Panel Docker kurulumunda `CONTROL_PANEL_DEPLOYMENT=docker` ister

Bölüm 4'teki düzeltmeden önce panelin "Başlat" düğmesi Docker kurulumunda zararlıydı.
Ayar `native` (varsayılan) bırakılırsa bu davranış **hâlâ geçerlidir**: panel
`start_office_server.ps1` çalıştırır, `research-api.exe` ve `research-mcp.exe` port
çakışmasından çöker, `research-worker.exe` ise sessizce başarılı olup aynı ARQ kuyruğunda
Docker worker'ı ile GPU için yarışır. PID dosyaları çöken süreçler için de yazıldığından
panel bunları "çalışıyor" gösterir ve betik en sonda konuyla ilgisiz bir Wi-Fi IP hatası
fırlatır.

Bu senaryo kurulum sırasında bir kez gerçekleşti; başıboş `research-worker.exe` ve
`research-mcp.exe` süreçleri `stop_native.ps1` ile durduruldu.

Docker kurulumunda panelin okuduğu ortam dosyasında (`.env.office`, yoksa
`.env.native.example`) `CONTROL_PANEL_DEPLOYMENT=docker` bulunmalıdır.

Panelin izleme tarafı (koşu listesi, kuyruk, GPU telemetrisi, HITL kartları, çıktı indirme)
ve Duraklat / Devam / İptal düğmeleri Research API üzerinden çalıştığı için her iki modda
da sorunsuzdur.

---

## 11. Kullanıcı kimliği ve koşu sahipliği (v0.10.0)

Bu değişiklik şema göçü içerdiği ve dört servisi kapsadığı için kendi raporunu aldı:
**[MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md](MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md)**.

Özet: panel artık oturum açmayı gerektiriyor ve her kullanıcı yalnız kendi koşularını
görüyor. Sahiplik `Repository` katmanında zorlanıyor — panelin hem doğrudan veritabanı hem
API üzerinden okuduğu için route düzeyinde filtre yetersizdi. Panel yetkileri kullanıcı
verisi ve kurulum operasyonları olarak ikiye ayrıldı.

---

## 12. Panelden parola değiştirme

Parola yalnız kabuktan değiştirilebiliyordu (`research-admin set-password`), yani her
değişiklik bir yöneticiye ve sunucuya erişime bağlıydı. Panel ağa açıldıktan ve gerçek
kullanıcılar geldikten sonra bu pratik bir engel hâline geldi.

`POST /api/account/password` eklendi; Hesabım sekmesinde mevcut parola, yeni parola ve
tekrar alanlarından oluşan bir kart var.

**Şema değişikliği gerekmedi.** `password_hash` ve `token_version` sütunları
`0007_user_identity` ile gelmişti ve `identity.set_password()` zaten hem özeti yeniliyor
hem sürümü artırıyordu; uç bu fonksiyonu çağırıyor, mantığı tekrarlamıyor.

### Mevcut parola neden zorunlu

Uç, mevcut parolayı doğrulamadan çalışsaydı güvenliği artırmak yerine **azaltırdı**. Panel
düz HTTP üzerinden LAN'a açık; oturum çerezini yakalayan biri, tek istekle ödünç aldığı
oturumu kalıcı hesap devralmaya çevirebilirdi. Yanlış mevcut parola 403 döner ve giriş
formuyla aynı hız sınırı deposunu kullanır — aynı adresten kimlik bilgisi denemesi aynı
sorundur. Denetim satırı `password change failed` olarak ayrı yazılır, yoksa log girişle
karışır.

Canlı doğrulamada yanlış parola denemesinden sonra `password_hash`'in bit bazında
değişmediği kontrol edildi.

### Çerez neden yeniden veriliyor

`set_password` `token_version`'ı artırıyor ve bu, kullanıcının **kendi** sekmesindeki
çerezi de geçersiz kılıyor. Uç bu yüzden yanıtta çerezi yeni sürümle yeniden veriyor.
Sonuç, insanların beklediği davranış: diğer cihazlardaki oturumlar kapanır, işlemi yapan
sekme açık kalır. Bu adım atlanırsa parola değiştirmek "kendini dışarı atmak" gibi
davranır ve kullanıcı ikinci bir kez giriş yapmak zorunda kalır.

### API anahtarları neden iptal edilmiyor

Anahtarlar ayrı kimlik bilgileridir. Parola değişiminde susturulmaları kullanıcı için
sürpriz olur ve Langflow ile MCP bağlantılarını sessizce bozardı. Bir anahtarın sızdığından
şüpheleniliyorsa doğru işlem onu tek tek iptal etmektir; panelde ve
`research-admin revoke-key` ile mümkün.

### Kapsam kararları

Parola karmaşıklık kuralı **konmadı** — tek kural boş olmaması. Yöneticinin başkasının
parolasını sıfırlaması kabukta kaldı; panelde yönetici ekranı yapılmadı. İkisi de
kullanıcı kararıdır.

`tests/test_control_panel.py` dört yeni vaka: parola değişiyor ve oturum sürüyor, yanlış
mevcut parola hiçbir şey değiştirmiyor, diğer cihazlar düşüyor, oturumsuz ve CSRF'siz
istekler reddediliyor. 226 test geçiyor.

---

## 13. Ekip kuyruğunun sansürlü görünürlüğü

### Sorun: doğru izolasyon, yanlış izlenim

11. bölümdeki izolasyon çalışıyor ama tek GPU'yu paylaşan bir ekipte yanıltıcı bir panel
üretiyordu. Koşusu `queued`de bekleyen kişi bomboş bir tablo ve hareket etmeyen tek bir
satır görüyor, sistemin bozuk olduğunu düşünüyordu. Aslında başkasının araştırması
RTX 4060'ı tutuyordu — ama bunu gösteren hiçbir şey yoktu.

Sonuç, gizliliğin kendisi değil **gizliliğin okunamaması** sorunuydu: beklemenin nedeni
kullanıcıdan da saklanıyordu.

### v0.10.0 kararının hangi yönü değişti

`MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md` "kullanıcı yalnız kendi
koşularını görür" diyor. Bu bölüm o kararı **içerik için koruyup varlık için gevşetiyor**:

| | v0.10.0 | Şimdi |
|---|---|---|
| Başkasının araştırma başlığı, sorusu, kaynakları, iddiaları | Gizli | **Gizli** |
| Başkasının koşu kimliği | Gizli | **Gizli** |
| Başkasının koşusunun **var olduğu** | Gizli | Görünür |
| Kimin çalıştırdığı, hangi durumda, hangi aşamada, ne süredir | Gizli | Görünür |

Gevşeyen tek şey budur. Koşu detayı, rapor indirme, duraklat/iptal ve HITL yanıtlama
eskisi gibi yalnız sahibine ve yöneticiye açıktır.

### Neden alan silmek yerine yeni bir tip

İlk akla gelen yol, tam satırı çekip hassas alanları silmekti. Bu yaklaşımın hata biçimi
sessizdir: unutulan tek alan sızıntıdır ve `research_runs` tablosuna ileride eklenecek bir
sütun kimse fark etmeden görünür hâle gelir.

Onun yerine `repository.py` içine **taşıyamayacağı için sızdıramayan** bir projeksiyon
kondu:

```python
@dataclass(frozen=True)
class TeamActivity:
    owner_name: str | None
    status: str
    current_stage: str
    queue_position: int | None
    elapsed_seconds: float
```

**Koşu kimliği bilinçli olarak yok.** İki sonucu var: panel satırı yanlışlıkla tıklanabilir
yapamaz, ve listeyi alan biri onu `/api/runs/<id>` yoklayacak bir kimlik kümesine
çeviremez. Kuyruk sırası Redis'ten gelen eşlemeyle **metodun içinde** çözülüyor; koşu
kimliği dönüş sınırını hiç geçmiyor.

### Korumanın nereye konduğu

`Repository`'deki metasınıf `run_id` alan her metodu otomatik koruyor. `list_team_activity`
tanımı gereği `run_id` almıyor ve başkasının satırlarını okuyor — yani metasınıfın
kapsamı dışında. Bu boşluğu kapatmak için koruma **döndürülebilecek şeyin biçimine**
taşındı; `tests/test_run_ownership.py` alan kümesini birebir doğruluyor:

```python
assert {field.name for field in fields(TeamActivity)} == {
    "owner_name", "status", "current_stage", "queue_position", "elapsed_seconds",
}
```

Alan eklemek bu testi düzenlemeyi, yani birinin "bu alan araştırma hakkında bir şey
söylüyor mu?" sorusunu sormasını zorunlu kılar.

Panel bu okumayı kendi sorgusunu yazarak değil, `Repository` üzerinden yapıyor. Panelin
veritabanına iki kapıdan ulaşması 11. bölümün çıkış noktasıydı; sansürün ikinci bir
kopyasını yazmak, eninde sonunda başlık döndüren kopyayı üretmenin yoludur.

### Üç kenar durum kararı

**Yönetici boş liste alır.** Yöneticinin ana tablosu zaten her koşuyu tam gösteriyor; aynı
koşunun bir de sansürlü kopyasını basmak bilgi eklemez, karıştırır.

**Sahipsiz koşular listeye girer**, "Bilinmeyen kullanıcı" etiketiyle. Sahipsiz koşu da
GPU tutar; yükü gizlemek kullanıcıyı tam da bu bölümün düzeltmek istediği biçimde
yanıltır, üstelik sızacak bir kimliği zaten yoktur. SQL'de bu, `owner_id != :id`
karşılaştırmasının NULL için `true` değil `NULL` vermesi yüzünden açıkça yazılmak
zorundadır — düz karşılaştırma tam da bu satırları düşürürdü.

**Yalnız aktif durumlar.** Tamamlanmış koşu beklemeyi açıklamaz.

### Yanında kapatılan bir sızıntı

`_queue_snapshot()` ARQ kuyruğunu okurken `jobs[].run_id` alanında **herkesin** koşu
kimliğini döndürüyor ve `build_status` bunu olduğu gibi yayınlıyordu. Arayüz bu alanı hiç
okumuyor. `TeamActivity`'nin özenle vermediği şeyi yan kapıdan dağıtmak tutarsız olurdu;
`_publishable_queue()` admin olmayanlar için `job_id` ve `run_id` alanlarını düşürüyor.
Derinlik ve bekleyen sayısı olduğu gibi kalıyor — kuyruk kartının anlamı odur ve zaten
ekip görünümünün bildirdiği yükün aynısıdır.

Sansür **çıkışta** uygulanıyor: `_run_snapshot` ham kuyruğu kullanıyor, çünkü daha erken
uygulamak her kullanıcının **kendi** kuyruk sırasını da yok ederdi.

### Arayüz

"Aktif ve sıradaki istekler" tablosu değişmedi; altına "Ekipteki diğer işler" başlıklı
ikinci bir tablo geldi. Liste boşken bölüm tamamen gizleniyor — tek kişilik kullanımda
sürekli boş bir tablo durmasın.

Satırlar `renderRuns()` ile değil ayrı bir `renderTeamRuns()` ile basılıyor: mevcut
fonksiyon satıra `openRun(run.id)` bağlıyor ve duraklat/iptal düğmesi ekliyor. Bu satırlar
tıklanamaz, `tabIndex` almaz, düğme taşımaz. Başlığın yanında "Başlık ve soru gizlidir;
yalnız kuyruk yükü gösterilir" notu var — eksik sütunlar açıklanmazsa bozuk görünür.

"Aktif işler" kartının notu ekip listesi doluyken "Ekipte N iş daha" oluyor; kullanıcının
aradığı asıl sinyal budur.

### Doğrulama

Canlı kurulumda iki geçici hesap ve tek bir `queued` koşu ile denendi. Sıradan kullanıcı
`/api/status` yanıtında yalnız şunu gördü:

```json
{"owner_name": "Mesgul Arkadas", "status": "queued",
 "current_stage": "INIT", "queue_position": null, "elapsed_seconds": 0.0}
```

Koşu kimliği, başlık ve birincil soru yanıtın **hiçbir yerinde** geçmedi. Aynı koşu
yönetici için `team` listesinde değil, ana tabloda gerçek başlığıyla göründü. Geçici
hesaplar ve koşu doğrulamadan sonra silindi.

`tests/test_run_ownership.py` altı, `tests/test_control_panel.py` üç yeni vaka aldı;
mevcut sahiplik testinin iddiası da güçlendirildi — artık başkasının koşusunun yalnız
tablolarda değil, **yanıtın tamamında** geçmediğini doğruluyor. 235 test geçiyor.

### Kapsam dışı bırakılanlar

Telegram botu (kullanıcı kararı), API'ye ayrı bir uç (panel dışında tüketicisi yok), ekip
kuyruğunun geçmişi, başkasının işine müdahale ve görünürlüğü kapatan bir yapılandırma
bayrağı. Bayrak eklenmedi çünkü açıklanan bilgi kurgusu gereği asgari, boş liste zaten
gizleniyor ve hiç çalıştırılmayacak bir kod yolu bedava değil.

---

## 14. MCP'de kişisel kimlik: ajan uçları kullanıcı adına çalışıyor

### Sessizce kırılan şey

11. bölümde `SERVICE_TOKEN` devreye alınırken MCP kapısı fark edilmeden kesildi.
`api.py` kimlik bilgisini `service_token or api_token` diye çözüyor; `SERVICE_TOKEN`
tanımlanınca `API_TOKEN` yedeği devre dışı kaldı ve `mcp_server.py` tam da onu
gönderiyordu.

Belirti yanıltıcıydı: `initialize` ve `tools/list` **200 dönüyor**, araçlar Claude
Desktop'ta listede görünüyor, yalnız araç *çağrısı* ölüyordu. Yani "bağlantı yok" gibi
değil, "çalışıyor ama hiçbir şey olmuyor" gibi duruyordu.

Aynı kök neden **yedeklemeyi de durdurmuş**: `sync-research-reports.ps1` de gateway'in
`/client/v1/` ucundan geçiyor. `sync.log`'daki son başarılı satır `2026-08-14`, sonrası
hata. Dört gün boyunca hiçbir araştırma paketi yerel yedeğe inmemiş.

### Jetonu düzeltmek yetmezdi

İkinci bir duvar daha vardı. Paylaşılan jeton API'de `Principal.system()`'a eşleniyor,
onun da `user_id`'si `None`; `create_run` sahipsiz koşuyu reddediyor. Ölçüldü:

```
SERVICE_TOKEN, aktör yok -> 400
"This credential cannot own a run; use a user API key or send X-Actor-User"
```

Bu bir hata değil, 11. bölümün bilinçli kararıydı — sahipsiz koşu yalnız yöneticiye
görünür olurdu. Dolayısıyla MCP'nin *biri* olarak davranması gerekiyordu.

### Çözüm: gelen kimlik bilgisi kişisel API anahtarı

`BearerProtectedMCP` artık tek bir paylaşılan jetonla `compare_digest` yapmıyor; sunulan
`rp_<prefix>.<secret>` anahtarını `identity.principal_from_api_key` ile çözüyor. O fonksiyon
zaten prefix aramasını, scrypt doğrulamasını, iptal kontrolünü, hesabın aktifliğini ve
`last_used_at` güncellemesini yapıyordu — yeniden yazılmadı.

Bozuk, bilinmeyen, iptal edilmiş ve kapalı hesaba ait anahtar **aynı 401'i** döndürür;
ayırt etmek hangi anahtar prefix'lerinin var olduğunu sızdırırdı.

### ContextVar: tasarımın can alıcı noktası

Araç fonksiyonları HTTP isteğini görmüyor, dolayısıyla kimliğin middleware'den araca
taşınması gerekiyordu. Sorun şu ki MCP 1.29 stateless modda aracı **uzun ömürlü** bir task
group'tan başlatıyor:

```python
assert self._task_group is not None
await self._task_group.start(run_stateless_server)
```

Task group lifespan bağlamında kuruluyor, yani ilk bakışta istek başına durum kaybolur.
Kaybolmuyor: anyio `start()` çağrısı sırasında **çağıranın** context'ini kopyalıyor ve
çağıran istek görevidir. Bunu varsaymak yerine, aynı yapıyı birebir kuran bir deneyle
ölçtüm:

```
araca ulasan degerler: ['rp_ALICE', 'rp_BOB']
SONUC: contextvar TASINIYOR
```

İki isteğin birbirine karışmadığı ayrıca teste bağlandı — sızıntı olsaydı biri diğerinin
adına araştırma başlatırdı, bu işteki en ciddi başarısızlık biçimi budur.

### Anahtar neden API'ye iletilmiyor

Gateway anahtarı zaten doğruladı. Yukarı akışa olduğu gibi iletmek, API'nin scrypt
doğrulamasını **tekrar** yapması demekti — her araç çağrısında ~60 ms. Onun yerine
`SERVICE_TOKEN + X-Actor-User` kullanılıyor; bu, Telegram botunun zaten yaptığı desen ve
`ResearchGatewayClient.for_actor()` bunun için vardı.

### `/health` kimlik bilgisi istemiyor, ama çevre içinde

Sıra önemli: **ağ ve Origin kontrolleri önce**, sonra `/health`, sonra kimlik doğrulama.
Çevrenin dışındaki bir çağıran canlılık yanıtı bile alamaz; çevrenin içindeki ops
betikleri (`office_server_status.ps1`, `start_office_server.ps1`) ise kimlik bilgisi
olmadan yoklamaya devam eder — canlılık probunun önüne kimlik bilgisi koymak probu
yalancı yapar.

### `263487f`'in geri alınması

O commit 8010 portunu loopback'e bağlamıştı; gerekçesi "ağda paylaşılan tek bir bearer
jeton taşıyan ajan kapısı" idi. Paylaşılan jeton kalktığı için gerekçe de kalktı ve port
LAN'a yeniden açıldı. Ekip bilgisayarlarındaki Claude Code ve Codex kurulumu yeniden
çalışır durumda.

### Ölçülen bulgu: `MCP_ALLOWED_NETWORKS` bu kurulumda filtre değil

Port açılırken uygulama katmanındaki CIDR kontrolünün gerçekten çalışıp çalışmadığı
ölçüldü. **Çalışmıyor.** Docker Desktop yayınlanan portta kaynak IP'yi NAT'lıyor;
`10.0.10.179` üzerinden gelen istek bile container'a şöyle görünüyor:

```
INFO:  172.20.0.1:52310 - "GET /health HTTP/1.1" 200 OK
```

Yani her istemci listedeki `172.16.0.0/12` sayesinde geçiyor ve CIDR listesi hiçbir şeyi
elemiyor. **Gerçek ağ kapısı Windows Firewall'daki "Docker Desktop Backend" kuralıdır.**
`.env` içine bu bulgu ve `172.16.0.0/12` satırının silinmemesi gerektiği uyarısı yazıldı —
silinirse bütün MCP istemcileri 403 alır.

Kimlik doğrulamanın kendisi bundan etkilenmiyor: kapıya ulaşan herkes yine geçerli bir
kişisel anahtar sunmak zorunda. Kaba kuvvet de bir sorun değil — bilinmeyen prefix scrypt'e
hiç ulaşmadan reddediliyor, dolayısıyla ucuz bir CPU tüketme yolu da yok.

### Doğrulama

Canlı kurulumda ölçülenler:

| Test | Sonuç |
|---|---|
| Eski paylaşılan jeton | 401 |
| Kimlik bilgisi yok | 401 |
| İptal edilmiş anahtar | 401 (anında) |
| Kişisel anahtar | 200 |
| `/health` kimlik bilgisiz | 200 |
| MCP'den başlatılan koşunun sahibi | `kirtekefurkan@gmail.com` |
| Başka kullanıcının anahtarıyla o koşuyu okuma | 404 |

Koşu gerçekten başladı (`running`, NORMALIZE aşamasına kadar geldi) ve test bittiğinde
`control_research` ile iptal edildi. Yedekleme yönetici anahtarına geçirildikten sonra 14
Ağustos'tan beri biriken üç paket indi.

`tests/test_agent_gateway.py` beş vaka aldı (kişisel anahtar + Origin, her kötü kimlik
bilgisinin aynı görünmesi, iki anahtarın birbirine karışmaması, kimlik bilgisiz `/health`
ama kapalı `/mcp`, aktörün doğru geçmesi), `tests/test_run_ownership.py` bir vaka
(kişisel anahtarla başlatılan koşu sahiplenilir ve başkasına görünmez). 239 test geçiyor.

### İstemci kurulumunda çıkan iki ayrı hata

Gerçek bir istemci bağlanırken iki şey daha ortaya çıktı.

**`install_claude_client.ps1` eskimişti.** Betik `claude mcp add-json` ile `{"type":"http"}`
gönderiyordu; güncel Claude Code bunu `Invalid configuration: : Invalid input` diyerek
reddediyor. Belgelenen yol `claude mcp add --transport http ... --header "..."`. Betik buna
geçirildi. Anahtar yapılandırmaya gömülmüyor — `${RESEARCH_MCP_TOKEN}` olarak yazılıyor ve
Claude Code çalışma anında ortamdan çözüyor, böylece `~/.claude.json` içinde düz metin
anahtar durmuyor.

**Ortam değişkeni zamanlaması.** `SetEnvironmentVariable(..., "User")` yalnız *yeni* süreçlere
yansır; zaten açık bir terminalden çalıştırılan Claude Code değişkeni göremez ve
`✗ Failed to connect` + "Missing environment variables: RESEARCH_MCP_TOKEN" verir. Bu,
sunucu tarafı tamamen doğruyken alınan bir hata olduğu için yanıltıcıdır; hem betiğe hem
`OFFICE_TEAM_SETUP.md`'ye açık uyarı kondu.

**Claude Desktop bu makinede kurulu değil** (`%APPDATA%\Claude` yok). Kurulu olan Claude
Code CLI'dir ve depodaki kurucu da onu hedefler; Claude Desktop uzak MCP sunucusunu
uygulama içindeki *Custom connector* akışıyla bağlar. İkisinin farkı belgeye yazıldı.

---

## 15. Aşama başına araç dökümü (panel)

### Sorun

Bir koşunun hangi aşamada hangi aracı çalıştırdığı üç ayrı yere dağılmıştı ve hiçbiri
aşama kırılımı vermiyordu:

| Bilgi | Nerede | Aşama kırılımı |
|---|---|---|
| Connector'lar | Panelde "Sorgu dalları" tablosu | yok, dal bazında |
| LLM modelleri | Panelde tek "LLM özeti" kartı | yok, koşu toplamı |
| Parser'lar | `source_versions.provenance` ve `13_raw_sources.jsonl` | arayüzde hiç yok |

Ham `run_events` akışında veri zaten vardı, ama panel yalnız son 150 olayı listeliyor ve
bu koşularda `acquisition_progress` olayları listeyi doldurduğu için erken aşamaların
ölçüm olayları görünmüyordu.

### Çözüm: olayları aşama penceresine atfetmek

`stage_timeline()` artık her aşama **ziyaretine** bir `tools` listesi ekliyor. Atıf kuralı:
`_boundary` her aşamanın *başında* bir `stage` olayı yayınlıyor, dolayısıyla bir ölçüm
olayı, kendisinden önceki son `stage` olayının açtığı pencereye aittir. Bu kural aynı
aşamanın turlar arası tekrarlarını da kendiliğinden ayırıyor — tur 1'in SEARCH'ü ile tur
2'nin SEARCH'ü ayrı tablolar.

`llm_metrics` ve `embedding_metrics` payload'unda bir `stage` alanı var, ama bu alan
**pipeline aşaması değil, daha ince bir faz etiketi**: `CONTENT_RELEVANCE` aslında NORMALIZE
penceresinde yayınlanıyor ve `PIPELINE_STAGES` içinde yer almıyor. Bu etiketle yerleştirme
yapılsaydı satır hiçbir karta düşmezdi; bu yüzden yerleştirme her zaman pencereye göre
yapılıyor, etiket satırın "Not" sütununda faz olarak gösteriliyor.

Toplanan satır türleri: `connector` (çağrı, başarı, sonuç, gecikme, `connector_error`'dan
hata sayısı), `method` (`direct` / `crawl4ai` / `scholarly_metadata` / `none`), `parser`,
`model` ve `embedding` (çağrı, token, süre, faz).

### Parser'ın olay akışına eklenmesi

`acquisition_metrics` olayının çağrı kayıtlarına `parser_id` eklendi
([pipeline.py](src/research_platform/pipeline.py)). Böylece panel `source_versions` ile
birleştirme yapmadan, tek olaydan aşamayı araca bölebiliyor.

**Bu bilinçli olarak geriye dönük değildir.** `retrieved_at` zaman damgasıyla
`source_versions.provenance`'ı aşama penceresine eşleyerek eski koşularda da parser
gösterilebilirdi; iki veri yolu ve bir sezgisel eşleme pahasına. Tercih tek veri yolu
oldu: mevcut koşularda parser satırı **görünmez**, connector / yöntem / model satırları
görünür. Parser'ı olmayan çağrı için "unknown" satırı da üretilmiyor — olmayan ölçümü
uydurmak yerine satır hiç açılmıyor.

### Panel davranışı

Zaman çizelgesindeki aşama kartları tıklanabilir (`role="button"`, Tab + Enter/Space).
Seçilen kart vurgulanıyor ve tablo şeridin **altında** açılıyor; aynı karta tekrar tıklamak
kapatıyor. Seçim modül düzeyinde tutulduğu için çekmece yenilendiğinde okunan aşama açık
kalıyor, 90+ kartlık şeridin başına dönülmüyor.

### Ölçüm: mevcut bir koşuda ne görünür oldu

`01M0AMSVG3TPD75NXVJGY0RXEM` koşusunun 177 ölçüm olayı 96 aşama ziyaretine dağıldı.
Panelde bugüne kadar hiç görünmemiş kırılımlar:

| Ziyaret | Satır |
|---|---|
| SEARCH · tur 1 | `zenodo` 8 çağrı / 2 başarı / **6 hata** / 170.8 sn — tek başına aşamanın gecikmesini domine ediyor |
| SEARCH · tur 1 | `crossref` 8 çağrı / 160 sonuç / 7.4 sn |
| ACQUIRE · tur 1 | `direct` 26, `crawl4ai` 8, `none` 18 (başarısız edinimler), `scholarly_metadata` 1 |
| NORMALIZE · tur 1 | `qwen3:4b-instruct` 37 çağrı / 85.3k token / faz `CONTENT_RELEVANCE` |
| CHUNK_INDEX · tur 1 | `embeddinggemma:300m` 10 çağrı / 101.1k token |

Bir uyarı: satırdaki süre, o araca yapılan çağrıların **toplamıdır** ve çağrılar paralel
koştuğu için ziyaretin duvar saati süresini aşabilir (EXTRACT_EVIDENCE'ta 298 sn çağrı
toplamı / 154 sn ziyaret). Bu bir hata değil, eşzamanlılığın göstergesidir.

### Doğrulama

- `tests/test_control_panel_metrics.py`: pencere atıfı, tekrarlanan ziyaretlerin
  karışmaması, `parser_id` taşımayan eski payload'ların satır üretmemesi, faz etiketinin
  yerleştirmeyi değiştirmemesi.
- `tests/test_control_panel.py`: `_run_detail` çıktısının `timeline[].tools` taşıdığı.
- `tests/test_pipeline.py`: `acquisition_metrics` olayının parser'ı taşıdığı.
- Panelin satır içi JavaScript'i `node --check` ile ayrıştırıldı — bu dosyada sözdizimi
  hatası çekmecenin tamamını sessizce bozar.
- 244 test geçiyor.

---

## 16. İkili içeriğin metin sanılması ve koşuyu düşüren NUL baytı

### Belirti

19 Ağustos'ta başlatılan bir koşu NORMALIZE aşamasında düştü:

```
asyncpg.exceptions.CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00
[SQL: INSERT INTO source_versions (... content, raw_content, provenance ...)]
```

### Zincir

1. Bir DOI (`10.17816/dd569388-4203407`) makaleye değil, **ek dosyaya** çözüldü:
   `downloadSuppFile/...` — içerik bir JPEG (`\xff\xd8\xff\xe0..JFIF`).
2. `detect_document_type()` tanımadığı her şeyi `"text"` sayıyordu; JPEG "metin" oldu ve
   `_direct`'in `{"text","html","json","xml","pdf"}` beyaz listesinden geçti.
3. `PlainTextParser` baytları `errors="replace"` ile çözdü. Ortaya çıkan mojibake 400
   karakterlik asgari uzunluk eşiğini rahatça geçti, yani kaynak **kabul edildi**.
4. `_document()` `content`'ten NUL baytlarını temizliyordu ama `raw_content`'ten
   temizlemiyordu. PostgreSQL text sütununda `0x00` kabul etmez.
5. INSERT reddedildi → NORMALIZE görevi çöktü → koşu `failed`. O turda toplanan her şey
   gitti.

### Düzeltme

**Filtre —** `detect_document_type()` artık ikili içeriği tanıyor: MIME `image/`, `audio/`
veya `video/` ile başlıyorsa ya da ilk 8 KB'de `0x00` varsa `"binary"` döndürüyor. Bu tür
beyaz listede olmadığı için aday sessizce atlanıyor ve korpusa hiç girmiyor.

**Değişmez —** `_document()` artık `raw_content`'i de temizliyor. PDF'lerin base64 gövdesi
etkilenmiyor; başka bir stratejiden gelecek tek bir NUL da artık INSERT'i reddettiremez.

İkisi birlikte gerekiyor: filtre çöpü korpustan uzak tutar, temizlik ise "metin sütununa
NUL yazılmaz" değişmezini strateji sayısından bağımsız hâle getirir.

### Kalan kırılganlık

Kök neden kapandı ama **kaydedilemeyen tek bir belgenin tüm turu düşürmesi** duruyor:
`save_document()` çağrısı korumasız. [OPEN_ITEMS.md](OPEN_ITEMS.md) 13. madde olarak
eklendi — belge başına `try/except` + `document_save_failed` olayı, böylece kayıp panelin
aşama tablosunda görünür olur.

### Doğrulama

`tests/test_collection_architecture.py`: JPEG ve ZIP başlıklarının `"binary"` döndüğü, düz
metnin hâlâ `"text"` olduğu, ve `_document()` çıktısının hiçbir alanında NUL kalmadığı.
245 test geçiyor. Düzeltme worker container'ında doğrulandı.

---

## 17. Koşu öncesi zorunlu plan onayı ve zorunlu araştırma süresi

### Sorun

Bir koşu "başlat" denildiği anda aramaya başlıyordu ve ne yapacağının önemli bir kısmı o
ana kadar hiçbir yerde görünmüyordu: sorunun metninden **otomatik çıkarılan tarih
aralığı**, `max_rounds`'un `literature_scan` modunda yok sayılması, hangi modellerin
kullanılacağı, hangi çıktıların üretileceği. Bunlar ancak koşu bittikten sonra olay
akışından geriye dönük anlaşılıyordu. Süre de sessiz bir varsayılandı: `max_wall_minutes`
verilmezse 45 dakika kabul ediliyor ve kullanıcı bunu hiç görmüyordu.

### Süre: zorunluluk modelde, istek sınırında değil

`ResearchBudget.max_wall_minutes` ve `ResearchProtocol.budget` varsayılansız hâle geldi.
Zorunluluğu istek doğrulayıcısına koymak daha ucuzdu — 42 çağrı yerine dokunmadan — ama
o zaman `zotero_sync`, Telegram varsayılanları ya da ileride eklenecek herhangi bir iç yol
sessizce 45 dakikalık bir bütçe kurmaya devam edebilirdi. Modelde zorunlu olunca **süresi
belirtilmemiş bir protokol hiçbir yolda kurulamıyor**, ve API tarafında ayrı bir
doğrulayıcı yazmaya da gerek kalmıyor: FastAPI 422 ile
`loc: ["body","protocol","budget","max_wall_minutes"]` döndürüyor.

Bedeli 42 çağrı yerinin açık süre alması oldu (40'ı test fixture'ı). `zotero_sync` bir
araştırma koşusu değil ve duvar saati bütçesi orada hiç okunmuyor; oraya açık bir değer ve
gerekçesi yazıldı — görünmez 45 dakika yerine görünür ve açıklanmış bir sayı.

Yüzeyler: MCP `start_research`'te `max_wall_minutes` varsayılanını kaybetti ve araç
şemasında artık `required: question, max_wall_minutes` görünüyor; Langflow bileşenine
zorunlu girdi eklendi; Telegram zaten `has_explicit_duration` ile süre sormadan koşu
başlatmıyordu ve bu davranış artık testle korunuyor.

### Telegram: varsayılanı ezen bayrak

İlk sürüm Telegram'ı "değişiklik gerekmiyor" diye geçmişti; **yanlıştı.** Bot koşuyu
açarken dört HITL bayrağını da `--hitl` anahtarına bağlıyordu:

```python
hitl=HitlConfig(planning_questions=hitl_enabled, plan_review=hitl_enabled, ...)
```

Yani `--hitl` yazılmayan her `/research`, `plan_review=false` **göndererek** yeni
varsayılanı eziyordu. Bottan başlatılan ilk örnek koşu (`01M0D2BMN6FC051VKA4VQS5121`)
planlama aşaması olmadan çalıştı ve hata böyle görüldü. Varsayılanı bir yerde değiştirmek,
onu açıkça gönderen çağıranları düzeltmez — bu iş sınıfında aranacak ilk şey budur.

Düzeltme: `plan_review` artık `--hitl`'den bağımsız ve varsayılan açık; atlamak için
`--plansiz` bayrağı var (atlama yetkisinin koşuyu açanda olması kararıyla tutarlı).

### Telegram'da plan onayı görünür hâle geldi

Kapıyı zorunlu yapmak tek başına yetmiyordu: bot koşularını izlemiyordu, yani koşu
`awaiting_input`'ta sessizce bekliyor ve kullanıcının `/status` yazmayı akıl etmesi
gerekiyordu. Ayrıca `/status` planın **içeriğini** göstermiyordu, dolayısıyla onay körlemesine
verilecekti.

Bot artık başlattığı koşuları hafızasında tutuyor ve her long-poll turunda (en fazla ~1
dakika gecikmeyle) durumlarını yokluyor; `plan_review` beklemeye düşen koşunun plan özetini
ve `/respond <id> approve|reject <gerekçe>` komutlarını sohbete yazıyor. Özet
`plan_summary()` ile üretiliyor: Telegram'ın 4096 karakter sınırına sığacak şekilde soru,
alt sorular, ilk sorgu dalları, bütçe, **bağlayıcı olmayan sınırlar**, tarih kapsamı
(sorudan çıkarıldıysa notuyla) ve strateji notu.

İzleme listesi süreçte tutuluyor; bot yeniden başlarsa unutulur ve kullanıcı `/status`'a
düşer. Bilinçli: bu bir bildirim kolaylığı, koşunun durumu değil — koşu ve planı
veritabanında duruyor.

### Plan kapısı

`hitl.plan_review` varsayılanı `True` oldu. Atlama yetkisi **koşuyu açanda**: `false`
gönderen bir çağıran kapıyı atlar ve bu karar `plan_skipped` olayı olarak yazılır. Kurulum
düzeyinde bir yasak konmadı; başsız otomasyonun tıkanmaması bunu gerektiriyordu.

Kapı `build_query_branches` sonunda, SEARCH'ten hemen önce duruyor — plan ancak
ayrıştırma ve sorgu üretimi bittikten sonra kurulabilir. Reddedilirse koşu **DECOMPOSE'a
geri sarılır**, geri bildirim alt sorulara katılır ve sorgular yeniden üretilir; en fazla
`plan_max_revisions` (3) tur, sonra koşu iptal edilir.

`_maybe_hitl` ikiye ayrıldı. Diğer üç kapı geçmişte bir yanıt bulduğunda hep onu döndürür;
plan kapısı bunun tersini ister, bu yüzden durdurma kısmı `_request_input` olarak ayrıldı
ve kapı kendi döngüsünü yönetiyor.

**Yakalanan sıralama hatası:** geri bildirim ilk yazılışta checkpoint'lenmiş state'ten
okunuyordu. Checkpoint, beklediği reddedilmeden **önce** yazıldığı için state bir tur
geride kalıyor ve yeniden kurulan plan reddedilen planın aynısı çıkıyordu. Kaynak
`hitl_history`'ye çevrildi (`_plan_feedback`); canlı doğrulamada ikinci turda
`FDA regulatory clearance...` ve `CE marking status...` dalları üretildi.

### Plan belgesi

Yeni `research_plan.py`, ağ çağrısı yapmayan saf bir modül. İçeriği: sorular, sorgu
dalları, kaynak seçimi ayarları, tarih kapsamı, bütçe, **etkin sınırlar**, durdurma
ölçütleri, modeller, edinim strateji sırası ve parser'lar, çıktılar, kalan onay noktaları,
önceki geri bildirimler ve LLM'in yazdığı kısa strateji notu. Not ayrı bir alanda durur ve
üretilemezse boş kalır — plan onsuz da eksiksizdir.

**Connector listesi bilinçli olarak plana konmadı.** Hangi connector'ın çağrılabildiği
çalışma anına ait, zamanla değişen bir olgudur; plan saatlerce onay bekleyebileceği için
orada tutamayacağı bir söz vermiş olurdu. Bu bilgi `connectors_skipped` olayında ve panelin
aşama × araç tablosunda kalıyor.

"Etkin sınırlar" bölümü hangi sınırın gerçekten durdurucu olduğunu söylüyor. Canlı
doğrulamada üretilen plan, `max_rounds=4` için `bağlayıcı=hayır` ve gerekçesini yazdı —
bu tam olarak 19 Ağustos'ta bir koşuyu izlerken şaşırdığımız davranıştı.

**Tarih çıkarımı kaydediliyor, yeniden hesaplanmıyor.** İlk sürüm çıkarımı plan anında
tekrar çalıştırıp karşılaştırıyordu; zaman damgaları saniyeler kaydığı için sonuç her
zaman "çıkarım yok" çıkıyordu. `ResearchScope.dates_inferred` alanı eklendi ve çıkarımı
yapan doğrulayıcı onu işaretliyor.

### Zaman aşımı

Diğer kapılar 5 dakikada sönüyor; insan onayı bekleyen bir plan için bu çok kısaydı.
`hitl_plan_timeout_minutes` (varsayılan 1440) eklendi. Süre dolması veri kaybı değil —
`respond` ucu `paused` koşuları da kabul ediyor — ama gereksiz "duraklatıldı" gürültüsü
üretmiyor.

### Doğrulama

Canlı kurulumda ölçülenler (koşu `01M0D0N89XRBS36PPGPRXSSYKV`):

| Adım | Sonuç |
|---|---|
| Süresiz `POST /v1/research-runs` | 422 |
| Süreli koşu | `awaiting_input`, `research_plan` olayı yazıldı |
| Plan onaylanmadan SEARCH | `connector_metrics` sayısı **0** |
| Red + gerekçe | Yeni plan, revizyon 1 |
| İkinci red | Revizyon 2; sorgulara FDA/CE dalları eklendi |
| Onay + süre 20 → 12 | Koşu SEARCH'e geçti, `protocol.budget.max_wall_minutes = 12`, `plan_duration_changed` olayı |
| MCP `tools/list` | `required: question, max_wall_minutes` |
| Telegram `/research` (bayraksız) | Plan kapısı açık; bot plan özetini sohbete yazıyor |

265 test geçiyor. Panelin plan kartı bölümlere ayrıldı (sorular, sorgu dalları, kaynak
seçimi, etkin sınırlar, modeller, çıktılar, strateji notu), süre girdisi eklendi ve
"Değişiklik iste" artık gerekçesiz gönderilemiyor — gerekçe yeniden planlamanın tek girdisi.

---

## 18. Telegram botu SERVICE_TOKEN düzeltmesi ve granüler parser motorları

### 1. Telegram Botu `SERVICE_TOKEN` Uyuşmazlığı (`401 Unauthorized`)

**Olay:** Kullanıcı Telegram botu üzerinden `/research` komutunu başlattığında ve süre butonunu seçtiğinde API'ye `POST /v1/research-runs` isteği atılıyor, ancak istek `401 Unauthorized: Invalid bearer credential` ile reddediliyordu.

**Kök Neden:** `v0.10.0` ile çok kullanıcılı güvenlik modelinde `SERVICE_TOKEN` ayrılmıştı. `api.py`, aracı servislerden `X-Actor-User` ile gelen çağrılarda `settings.service_token or settings.api_token` beklerken, `telegram_bot.py` içerisindeki `ResearchGatewayClient` istemcisi `self.settings.api_token` ile başlatılmıştı. `.env` içinde `SERVICE_TOKEN` ve `API_TOKEN` farklı değerler taşıdığından API isteği yetkisiz sayıyordu.

**Uygulanan Çözüm:** `telegram_bot.py` içindeki gateway istemcisi `self.settings.service_token or self.settings.api_token` olarak güncellendi.

---

### 2. Granüler Parser Motorları (`pymupdf_fast`, `pypdf`, `html_structured`, `plain_text`)

**Olay:** Web Kontrol Paneli `ACQUIRE` aşamasındaki telemetri tablosunda ayrıştırıcı araç isimleri jenerik (`pdf`, `html`) olarak gösteriliyordu. Arkada PyMuPDF mi yoksa pypdf mi çalıştığı belirsiz kalıyor, gelecekte eklenecek yeni parser motorlarının (örn. `docling_pdf`, `marker_ocr`) ayırt edilmesi mümkün olmuyordu.

**Uygulanan Çözüm:**
1. **`PyMuPdfParser` (`pymupdf_fast`):** PyMuPDF / `fitz` tabanlı, iki sütunlu akademik makaleleri doğru okuma sırasında süper hızlı işleyen birincil PDF motoru (`priority = 10`).
2. **`PyPdfParser` (`pypdf`):** Saf Python tabanlı güvenilir yedek PDF motoru (`priority = 0`).
3. **`HtmlParser` (`html_structured`):** Tabloları Markdown'a dönüştüren ve kod bloklarını koruyan yapılandırılmış HTML motoru (`priority = 10`).
4. **`PlainTextParser` (`plain_text`):** Düz metin, JSON ve XML anahtar-değer ayrıştırıcısı.
5. **Otomatik Fallback ve Seçim:** `ParserRegistry` sınıfına `candidates()` metodu eklendi. Birincil motor (`pymupdf_fast`) bozuk veya hasarlı bir PDF ile karşılaştığında, `acquisition.py` edinim sürecini düşürmeden otomatik olarak sıradaki motora (`pypdf`) düşer.
6. **Denetlenebilirlik (Provenance):** Hangi motor çalıştıysa veritabanına (`source_versions.provenance`), teslimat dosyalarına (`13_raw_sources.jsonl`, `18_structured_extracts.json`) ve kontrol paneli arayüzüne tam motor adıyla yazılır.

---

### 3. Kontrol Paneli Başlık Güncellemesi

* Web Kontrol Panelinde (`control_panel_ui.py` ve `CONTROL_PANEL_GUIDE.md`) "Ekipteki diğer işler" başlığı, netlik ve kullanıcı deneyimi için **"Aktif Koşular"** olarak güncellendi.

---

### Doğrulama

* `tests/test_parsers.py` (34 test), `tests/test_research_plan.py` (5 test), `tests/test_pipeline.py` (19 test) ve tüm test paketi (269 test) çalıştırılarak tam doğrulama sağlandı.
* Docker container'ları yeniden derlenip canlı ortamda doğrulandı.

---

## 19. Araştırma İngilizce yürüyor, rapor istenen dilde

### Sorun: dil yalnız sorguları değil, kapıları da bağlıyordu

Türkçe bir soruyla açılan koşu, sorunun dilini bütün alt aşamalara taşıyordu. 19 Ağustos'ta
ölçülen: `arxiv`, `crossref`, `openalex`, `europe_pmc` Türkçe dizgelerle arandı ve dördü de
**0** sonuç döndürdü.

Ama asıl mesele arama değildi. [relevance.py](src/research_platform/relevance.py) sözcük
tabanlı kapılar içeriyor — `topic_terms`, `topic_bigrams`, `canonical_topic_terms` — ve
soru ile belge metni arasında terim örtüşmesi arıyor. Türkçe soru ile İngilizce makale
arasında bu örtüşme sıfıra yakındır: **değerli makaleler LLM'e hiç ulaşmadan, sessizce
eleniyordu.** Arama düzeltilse bile bu kapı kapalı kalırdı.

Kök neden tek bir dize: `protocol.primary_question`. Ayrıştırma girdisi, sorgu üretimi,
alaka yargısı, kurtarma misyonları, boşluk başlıkları ve sentez — hepsi onu okuyor.

### Çözüm: soruyu yerinde çevir

`VALIDATE_PROTOCOL` aşamasında `primary_question` ve `sub_questions` İngilizce'ye çevriliyor;
kullanıcının yazdığı metin `original_question`, `original_sub_questions` ve
`original_language` alanlarında kalıyor.

**Neden yerinde:** araştırma tarafındaki ~35 çağrı yerinin hiçbiri değişmiyor, dolayısıyla
bir tanesini atlayıp sessizce eski davranışı sürdürme riski yok. Alternatif — ayrı bir
`research_question` alanı — her çağrı yerini tek tek çevirmeyi ve unutulan birinin fark
edilmemesini göze almayı gerektirirdi. Bedeli, sorunun kullanıcıya gösterildiği birkaç
yerin (`panel listesi`, çekmece başlığı, rapor başlıkları) özgün metne çevrilmesiydi;
bunlar sayılabilir ve gözle görülür.

Çeviri `VALIDATE_PROTOCOL`'de yapılıyor, çünkü plan onayı ekranına düşmesi gerekiyor:
**yanlış çeviri, bütün koşuyu sessizce başka bir soruya yönlendirecek tek hatadır**, ve
onay ekranı onu bütçe harcanmadan önce yakalar. Panel ve Telegram özeti İngilizce sorunun
altında kullanıcının kendi cümlesini gösteriyor.

### Üç ayrıntı

**Çeviri başarısız olursa koşu düşmez.** Özgün metin korunur, `research_language_fallback`
olayı yazılır. Türkçe araştırmak İngilizce araştırmaktan kötüdür, ama koşuyu bir çeviri
yüzünden iptal etmekten iyidir. Doğrulama sırasında bu yol gerçekten çalıştı: Docker yeni
başladığı için worker host'taki Ollama'ya ulaşamadı, koşu çökmek yerine Türkçe devam etti.

**Alıntılar asla çevrilmiyor.** İddia metni (`text`) İngilizce, ama `quote` kaynağın kendi
dilinden birebir kopyalanır — `evidence_quality_gate` alıntının pasajda geçtiğini doğruluyor
ve çevrilmiş bir alıntı bu denetimi geçemeyip iddiayı sessizce düşürürdü. Prompt'a bu ayrım
açıkça yazıldı.

**Kapılar iki dille birden eşleşiyor.** `research_questions()` ve `primary_questions()`
yardımcıları hem İngilizce hem özgün metni döndürüyor; böylece Türkiye'ye özgü bir konuda
Türkçe resmî belge, çevirinin ters etkisiyle elenmiyor. Öznel kapsam skoru dillerin
**birleşimi** değil **en iyisi** üzerinden hesaplanıyor: terimleri havuzlamak paydayı
büyütür ve kapıyı eskisinden katı hâle getirirdi.

### Rapor tarafı

Ayrım netleşti: **akıl yürütme İngilizce, basılan metin rapor dilinde.**

| Yer | Ne alır |
|---|---|
| Sentez prompt'ları (`RESEARCH_QUESTION`) | İngilizce soru — iddialar da İngilizce |
| Word raporundaki "Ana soru" / "Alt sorular" | `question_for_report()` / `sub_questions_for_report()` |
| `02_full_research_report.md` başlığı | `question_for_report()` |
| `10_reproducibility_manifest.json` | protokolün tamamı, yani her iki soru ve çeviri bilgisi |

`question_for_report()` geri çeviri yapmaz: Türkçe rapor isteyen ama İngilizce soran
kullanıcı sorusunu İngilizce görür. Uydurulmuş bir çeviriden dürüsttür.

`report_language` artık `Literal["tr", "en"]`. Serbest dizeydi ve sentezdeki
`_language_matches` yalnız Türkçe'yi denetlediği için `"de"` yazan biri hiçbir şeyin
doğrulanmadığı bir rapor alıyordu.

### Doğrulama

Aynı Türkçe soru, koşu `01M0F0G44KMQAXRB17973SDHT8`:

| Ölçüm | 19 Ağustos (Türkçe) | Şimdi (Türkçe soru, İngilizce araştırma) |
|---|---|---|
| openalex | 0 | **320** |
| crossref | 0 | **160** |
| europe_pmc | 0 | **155** |
| arxiv | 0 | **120** |
| Sorgu dilleri | hepsi Türkçe | hepsi İngilizce |

Plan onayında hem İngilizce araştırma sorusu hem kullanıcının Türkçe cümlesi göründü.
279 test geçiyor.

---

## 20. Plan onay ekranı sorunun geldiği dilde okunuyor

### Sorun

Araştırmanın İngilizce yürümesi doğru (19. bölüm), ama kullanıcının **karar verdiği** ekran
o çeviriyi olduğu gibi yansıtıyordu: Türkçe soru soran biri planda İngilizce sorular ve
İngilizce bir strateji notu görüyordu.

İki ayrı kusur vardı:

**Strateji notu yanlış dilde çıkıyordu.** `STRATEGY_SYSTEM` "in the requested language"
diyordu ama dil yalnız JSON yükünün içindeydi (`{"language": "tr"}`), etrafı İngilizce plan
içeriğiyle çevrili. 4B model içeriği taklit edip İngilizce yazıyordu. Dil adı sistem
istemine taşındı ("Write it in Turkish."); tek satırlık yer değişikliği, ölçülen sonuç:
strateji notu artık Türkçe geliyor.

**Plan metinleri sabit Türkçe'ydi.** `effective_limits` ve `deliverables` içindeki beş
açıklama koda gömülü Türkçe'ydi, yani İngilizce soru soran kullanıcı tersinden aynı sorunu
yaşıyordu: İngilizce sorular, Türkçe açıklamalar.

### Gösterim dili sorunun dilidir, rapor dili değil

`ResearchProtocol.display_language()` `original_language`'i okur. Rapor dili farklı bir
karardır — teslimatla ilgilidir; planı ise soruyu yazan kişi okur. Türkçe sorup İngilizce
rapor isteyen biri planı yine Türkçe görür.

Bunun çalışması için sorunun dilinin güvenilir olması gerekiyordu. `detect_language()` iki
İngilizce durak sözcüğü göremezse `"und"` döndürüyor ve kısa sorularda bu çok sık.
`translate_research_request` artık kaynak dili de döndürüyor — model zaten çeviriyi yaparken
biliyor. `original_language` çevrilen, zaten İngilizce olan ve çevirinin patladığı **her**
yolda `tr`/`en` olarak yazılıyor.

Bu, yan üründe sessiz bir kusuru da kapattı: `question_for_report()`
`original_language == report_language` karşılaştırması yapıyor ve `"und"` hiçbir zaman
eşleşmediği için **kısa Türkçe soruların raporu, kullanıcının sorusu yerine İngilizce
çeviriyi basıyordu.**

### Ne çevriliyor, ne çevrilmiyor

| İçerik | Karar |
|---|---|
| Birincil soru | Kullanıcının cümlesi önde; İngilizce araştırma sorusu altında soluk kalır |
| Alt sorular | Gösterim için çevrilir (`sub_questions_display`); operasyonel İngilizce liste yerinde durur |
| **Sorgu dalları** | **Çevrilmez** — connector'lara birebir bu dizeler gidiyor; çevirmek planın yalan söylemesi olurdu |
| Connector/parser/model adları | Çevrilmez; bunlar çalışan sistemin adları |
| Sınır ve teslimat açıklamaları | Sunucuda yerelleşir |
| Düğme, sütun ve bölüm başlıkları | Her yüzeyde kendi sözlüğünde |

Plan **verisinin** düzyazısı sunucuda, **arayüz çerçevesi** yüzeyde yerelleşiyor: sunucunun
düğme metni göndermesi yanlış olurdu ve panelde düğme, Telegram'da komut satırı var.

### Modelin döndürdüğü şekli kabul etmek

Gösterim çevirisi ilk denemede sessizce boş kaldı. Neden: istem `{"items": [...]}` istiyor,
model ise **kaynak → çeviri eşlemesi** döndürüyor:

```json
{"What is the diagnostic accuracy...?": "Derin öğrenme modellerinin ... doğruluk ne kadardır?"}
```

`_display_items` artık üç şekli de okuyor (istenen dizi, çıplak dizi, eşleme) ve girdiyle
bire bir hizalanamayan her yanıtı **atıyor** — yanlış uzunlukta bir liste, yanlış metni
yanlış sorunun yanına koyardı.

### Doğrulama

| Ölçüm | Türkçe soru | İngilizce soru |
|---|---|---|
| `display_language` | `tr` | `en` |
| PLAN aşamasındaki LLM çağrısı | 2 (gösterim çevirisi + strateji) | **1** (yalnız strateji) |
| Sınır açıklamaları | Türkçe | İngilizce |
| Strateji notu | Türkçe | İngilizce |
| Alt sorular | Türkçe gösterim + İngilizce operasyonel | yalnız İngilizce |
| Sorgu dalları | İngilizce | İngilizce |

287 test geçiyor. Arka planda hiçbir şey değişmedi: sorgular, edinim, kanıt çıkarımı ve
rapor üretimi aynı.

---

## 21. Telegram: dil seçimi, şıklı planlama söyleşisi ve tek dilde konuşan bot

### Sorun

İngilizce başlatılan bir araştırmada plan onaylandıktan sonra gelen yanıt şuydu:

```
01M0...: yanıt alındı, durum queued
```

Tek cümlede iki dil. 20. bölümde yalnız **plan özeti** iki dilli yapılmıştı; botun geri
kalan metinleri koda gömülü Türkçe kalmıştı — `PLAN_TEXT` dışında 52 satır, ~40 mesaj.

İkinci eksik: soru alınıp doğrudan ayrıştırmaya giriyordu. Kullanıcının "şunu değil bunu
kastediyorum" diyebileceği bir an yoktu. `planning_questions` kapısı bunun için vardı ama
varsayılan kapalıydı, soruları koda gömülü üç genel cümleydi ve yanıt yalnız serbest
metindi.

### Dilin kaynağı

`ResearchProtocol.interaction_language` eklendi ve `display_language()` sırası şu oldu:
**açık seçim → sorunun yazıldığı dil → tr**. `original_language`'in anlamı korundu; o alan
"soru hangi dilde yazılmıştı" bilgisidir ve `question_for_report()`'u besler, tercih değil.

Botta `reply_language()` aynı sırayı izleyip sonuna iki basamak ekler: Telegram istemci
dili (`from.language_code`) ve varsayılan Türkçe. `detect_language()` yalnız `tr`/`en`
dediğinde oy kullanır — kısa metinde `"und"` döndürüyor ve bunu İngilizce saymak,
düzeltmeye çalıştığımız hatanın aynısını ters yönde üretirdi.

Koşuya dair yanıtlar için ek sorgu gerekmiyor: `/status` ve `/respond` yanıtları zaten
protokolü taşıyor (`RunView.protocol`).

### Şıklı sorular: yanıt sözleşmesi değişmeden

Kapının **soru** yükü genişledi, **yanıt** biçimi aynı kaldı:

```
{"questions": [{"question": "...", "options": ["...", "..."]}]}   ← options yeni
{"answers":   [{"question": "...", "answer": "..."}]}             ← değişmedi
```

Bu yüzden `_validate_hitl_response` hiç değişmedi ve panel de aynı soruları kazandı:
`options` varsa radyo düğmeleri + "başka" alanı, yoksa bugünkü serbest metin.

Kapı zaten `DECOMPOSE` sonunda, plan kapısından önce duruyordu; istenen sıra (önce
söyleşi, sonra plan) yeni bir aşama gerektirmedi.

### Yinelenen şıklar bir seçim değildir

Canlı ölçümde 4B model bir soruyu **beş kez aynı şıkla** döndürdü ("Klinik deneyim
raporları" ×5) ve başka bir soru ilk sorunun şık kümesini tekrarladı. Böyle bir soru
kullanıcıya hiçbir şey sormaz. `_choice_questions` artık şıkları büyük/küçük harf duyarsız
tekilleştiriyor, iki farklı şıkkı kalmayan soruyu atıyor ve şık kümesi öncekiyle aynı olan
soruyu düşürüyor. Düzeltmeden sonra aynı soruda dört soru yerine üç soru kaldı, hepsinin
beş farklı şıkkı var.

### Cevaplar alt soru değil, yönlendirme

Kapı bugüne kadar cevapları doğrudan `sub_questions` listesine ekliyordu. Şık cevapları
kısa ifadeler olduğu için ("Klinik") bu, kendi başına bir sorgu dalı üretirdi. Cevaplar
artık `planning_answers` olarak durur ve `plan_feedback` ile aynı yolu izler:
`decompose` ve `generate_search_queries` onları **guidance** olarak alır.

Canlı doğrulamada "AI'nın iş yükü üzerindeki etkisi" seçildiğinde üretilen alt soru
`How does AI-assisted reading affect radiologist **workload** in lung CT imaging?` oldu ve
sorgu dallarına da yansıdı; ham Türkçe cevap metni hiçbir yerde sorgu olarak görünmedi.

### Yol boyunca çıkan bir çökme hatası

`_link_hint()` parametresiz tanımlıyken süre seçimi geri çağrısında bir argümanla
çağrılıyordu. O yol — süre düğmesine basan ama hesabı bağlı olmayan kullanıcı —
`TypeError` üretir, `_handle_callback` bunu yakalamaz ve `serve()` döngüsünden dışarı
çıkarak **botu düşürürdü**. İşlev artık dil parametresi alıyor.

### Doğrulama

| Ölçüm | Sonuç |
|---|---|
| Şıklı sorular (Türkçe koşu) | 3 soru, her birinde 5 farklı şık |
| Söyleşi sırası | Kapı `awaiting_input`, plan **kurulmadan** önce |
| Cevabın etkisi | Alt sorularda ve sorgu dallarında "workload" |
| Ham cevap metni | `sub_questions`'ta **yok** |
| Mesaj tablosu | `MESSAGES["tr"]` ve `MESSAGES["en"]` aynı anahtar kümesinde (test) |

295 test geçiyor. Araştırma dili değişmedi: arama, edinim ve kanıt çıkarımı İngilizce
yürümeye devam ediyor.

---

## 22. Bağlayıcı kapsam soruları, plan düğmeleri ve okunabilir koşu adı

### Sorun

21. bölüm kapsam sorularını şıklı hâle getirdi ama cevapların ne yaptığını değiştirmedi.
Canlı kullanımda dört eksik çıktı; hepsi kullanıcının planı okuyup karar verdiği ana ait.

**Şıklar ayar gibi görünüyor, ayar değildi.** Cevaplar yalnız `decompose` ve
`generate_search_queries` istemlerine ek metin olarak giriyordu. "Resmî kaynaklara öncelik
ver" seçildiğinde `connectors.included_families` değişmiyor, koşu aynı aileleri tarıyordu
ve 4B model yönlendirmeyi görmezden gelebiliyordu. Şıkları model uydurduğu için "Klinik
deneyim raporları" gibi sistemin sözlüğünde karşılığı olmayan seçenekler de çıkıyordu —
model talimatı harfiyen uygulasa bile eşlenecek bir alan yoktu. Doğrulanabilir de değildi:
plan "Verdiğiniz yanıtlar: 2" diyor, koşunun onlara uyup uymadığı görünmüyordu. Süreyi
karşılaştırın — `budget.max_wall_minutes` diye bir alan var, değişip değişmediğine
bakılabiliyor.

**Onay bir komut yazmayı gerektiriyordu.** Sohbetin geri kalanı düğmeyle ilerlerken tek
karar anı 26 karakterlik bir ULID'i elle yazmaya bağlıydı.

**Mesajlar koşuyu ULID ile adlandırıyor ve dil karıştırıyordu.**
`01M0FG…: yanıt alındı, durum queued`. Cümle iki dilli tablodaydı, içine gömülen **değer**
değildi: `queued`, `DECOMPOSE`, `plan_review`, `both` ham enum token'ı olarak basılıyordu.
21. bölümde kapatılan dil karışıklığının kalan yarısı buydu.

**Plan mesajı düz metin ve uzundu.** Alt sorular, sorgu dalları ve bütçe aynı blokta;
kararın dayandığı satırlar duvarın içinde kayboluyordu.

### Bağlayıcı sorular: iki yol, bilerek

Yeni `src/research_platform/scoping.py` saf modülü iki sabit soru tanımı ve
`apply_planning_answers` barındırıyor. Sabit soruların şıkları gerçek enum değerleri
taşıyor; modelin ürettiği sorular bugünkü gibi yönlendirme kalıyor.

| Soru (`id`) | Yazdığı alan | `value` |
|---|---|---|
| `date_scope` | `scope.start_date` / `end_date` / `dates_inferred` / `dates_chosen` | `keep` · `last_1y` · `last_3y` · `last_5y` · `any` |
| `source_families` | `connectors.included_families`, `connectors.profile`, `family_targets` | `academic` · `official` · `code_data` · `core` |

Her şeyi alana bağlamak istemedik: modelin uydurduğu bir şıkkın karşılığı yok, ve zorla
eşleştirmek sessizce yanlış alanı yazmak demek olurdu. İki soru bağlayıcı, ikisi serbest.

**Yanıt sözleşmesi bozulmadı.** Soru yüküne `id` ve `values`, yanıt maddesine `id` ve
`value` eklendi; ikisi de isteğe bağlı. Düğmeye basılınca dolar, kullanıcı kendi cevabını
yazarsa boş kalır ve o cevap yönlendirmeye düşer. `_validate_hitl_response` cevapları
artık alan alan yeniden kuruyor — eskiden listeyi olduğu gibi geçiriyordu, yani çağıranın
gönderdiği her anahtar `hitl_history`'ye denetlenmeden iniyordu.

**Neden `DECOMPOSE` başında uygulanıyor.** `BUILD_QUERY_BRANCHES` kaynak ailelerini
protokolden okuyor. Cevap `repo.update_run(protocol=…)` ile satıra da yazılıyor
(`_apply_plan_duration` emsali): devam eden koşu protokolünü satırdan okuyor, panel de
oradan okuyor.

**`family_targets` filtrelenmiyor, temizleniyor.** Protokol doğrulayıcısı mevcut hedef
haritasını yalnız daraltıyor; aile listesi genişlediğinde yeni aileler için hedef
üretemezdi. Temizleyip yeniden kurdurmak tek doğru yol.

**Bir kapsam cevabı koşuyu düşüremez.** Aile minimumları `max_sources`'u aşınca doğrulayıcı
`ValueError` atıyor; bu durumda protokol **değiştirilmeden** bırakılıyor ve
`scoping_not_applied` olayı yazılıyor. Cevap koşudan daha az değerli.

**`ResearchScope.dates_chosen` neden gerekti.** "Tarih sınırı olmasın" seçimi pencereyi
temizliyor, ama doğrulayıcı `start_date is None` görünce aralığı aynı sorudan hemen geri
çıkarıyordu — cevap bir sonraki doğrulamada kendiliğinden geri alınıyordu. `dates_chosen`
çıkarımı kapatıyor. `dates_inferred` ile karıştırılmamalı: o, pencerenin nereden geldiğini
kaydeder; bu, kullanıcının karar verdiğini kaydeder.

### Plan düğmeleri

Plan mesajının altında `plan_review:<run_id>:approve|reject` geri çağrılı iki düğme
(~46 bayt, Telegram'ın 64 bayt sınırının altında).

**Gerekçesiz reddetme yasak.** `{"approved": false}` gerekçesiz gönderilirse
`_plan_feedback` boş notu atlıyor, plan aynen yeniden kuruluyor ve koşu
`plan_max_revisions` dolana kadar dönüyor. Bot bu yüzden önce "neyi değiştirelim?" diye
soruyor, serbest metni bekliyor, sonra `modifications` ile gönderiyor.

**`/respond` kaldı ve `/help`'te duruyor.** `watched_runs` süreç hafızasında; bot yeniden
başlarsa düğmeler ölür. Düğme o durumda "geçersiz" diyip komut satırını tekrarlıyor —
yeniden başlatmayı atlatan tek yol o.

**Serbest metin yönlendirmesi tek kapıda.** Reddetme gerekçesi ikinci bir bekleyen metin
türü getirdi. İki ayrı sözlüğe sırayla bakmak, cevabın hangisine önce bakıldığına bağlı
kalması demekti; oturumlara `kind` alanı eklendi ve yönlendirici tek yerde ayırıyor.

**Yetki.** `watched_runs` artık `user_id` de tutuyor ve geri çağrı `chat_id` ile birlikte
onu da doğruluyor (`_claim_pending` ile aynı kontrol) — grup sohbetinde gönderenin
başkasının koşusunu onaylaması engelleniyor.

### Okunabilir koşu adı

`llm.research_label` koşu başına bir kısa çağrıyla İngilizce `snake_case` bir ad üretiyor;
`scoping.slugify` temizliyor ve tarih kapsamı varsa `_last_3m` gibi bir son ek ekleniyor.
`ResearchProtocol.label` alanına yazılıyor — protokol jsonb, göç gerekmedi.

**Neden çeviri çağrısına iliştirilmedi.** `_to_research_language` İngilizce sorularda hiç
model çağırmadan dönüyor; iliştirmek yalnız Türkçe yolu kapsardı. Ayrı çağrı iki yolda da
aynı çalışıyor ve tek yerde test ediliyor.

**Kimliğin yerine geçmiyor.** İki koşu aynı adı alabilir, bu yüzden ULID her mesajda
`<code>` olarak duruyor (Telegram'da dokunulunca kopyalanıyor) ve `/status`, `/respond`
gibi komutların argümanı hâlâ ULID.

> **Not:** Bu karar 23. bölümde bilinçli olarak değiştirildi. Etiketi gösterip kabul
> etmemek, kullanıcıyı ULID'i eski mesajlarda aramaya geri gönderiyordu. Komutlar artık
> etiketi de kabul ediyor; çakışma tahminle değil listelemeyle çözülüyor.

**Türkçe `ı` elle eşleniyor.** NFKD onu ayrıştırmıyor, ASCII süzgeci de düşürüyor;
`scholarly.py` `title_fingerprint`'teki kalıp tek başına "ısı" kelimesini yutuyor.

**Bilinen sınır:** "Run başlatıldı" mesajı koşu boru hattına girmeden gönderiliyor, o anda
ad henüz yok; o tek mesaj ULID'i gösteriyor. Adı API'de üretmek bunu çözerdi ama API'nin
LLM istemcisi yok.

### Enum değerleri ve zengin metin

`MESSAGES` tablosuna `status`, `stage`, `interaction`, `mode` alt sözlükleri eklendi, iki
dilde birden. Çeviri `label_of(strings, kind, value)` üzerinden yapılıyor ve **bilinmeyen
değer ham hâliyle basılıyor** — yeni bir `RunStatus` üyesi boş dize ya da `KeyError`
üretmiyor. Test botun anahtar kümesini `RunStatus`, `DeliveryMode` ve `PIPELINE_STAGES` ile
eşliyor; panel katmanından içe aktarmak yerine test ile eşlemenin sebebi paneldeki tablonun
yalnız Türkçe olması.

`plan_summary` artık HTML dönüyor. **MarkdownV2 yerine HTML**, çünkü mesaja giren her şey
kullanıcı metni ve HTML üç karakter kaçırmayı gerektiriyor (`& < >`), MarkdownV2 on sekiz.
Uzun listeler `<blockquote expandable>` içinde: mesaj kapalıyken kısa, dokununca açılıyor.

**`parse_mode` geri düşüşü.** Bozuk ya da desteklenmeyen tek bir varlık mesajın tamamını
düşürüyor ve bu bugüne kadar sessizdi — kullanıcı planı hiç görmüyordu. `_send_message`
Telegram hata dönerse etiketleri sıyırıp düz metin olarak bir kez daha gönderiyor.
Kırpma sınırları (8 alt soru × 140, 10 dal × 120, strateji 500) 4096 karakterin altında
kalacak şekilde seçildi: Telegram uzun mesajı kırpmaz, reddeder.

### Dil sorusu kendi cevabını İngilizce sormuyor

"Hangi dilde ilerleyelim?" sorusu Telegram istemcisinin dil ayarından geliyordu, yani
Türkçe bir istek İngilizce bir soruyla karşılanabiliyordu. `/research` artık dili **istek
metninden** çözüyor (`reply_language(question=…)`), ve aynı değer ayrıştırma hata
mesajlarında da kullanılıyor.

İstemci ayarına geri düşüş kaldı: `detect_language` kısa metne "und" diyor ve orada karar
istemciye geçiyor. Bilerek böyle — diyakritiksiz yazılmış Türkçe ("akciger BT") de Türkçe
işareti taşımıyor, ona İngilizce demek aynı hatanın ters yönü olurdu.

### Doğrulama

| Ne | Sonuç |
|---|---|
| Test | 315 geçiyor |
| Dil sorusu | İstek Türkçeyse Türkçe, İngilizceyse İngilizce |

---

## 23. Koşu adı kimliğin yerini tam olarak tutuyor

### Sorun

22. bölüm mesajlarda ULID yerine konuya bağlı bir ad göstermeye başladı ama komutlar o adı
tanımıyordu:

```
Cezeri: Research_artificial_intelligence_studies_that_last_3m: yanıt alındı, durum sırada
Furkan: /cancel Research_artificial_intelligence_studies_that_last_3m
        → bot anlamıyor
```

Bot adı gösterip kabul etmeyince kullanıcı ULID'i eski mesajlarda aramaya dönüyordu —
etiketin çözdüğü sorunun aynısı, bir adım ötede. Ada bakıp "bu ne işe yarıyor" dedirten
bir arayüz, hiç ad göstermemekten daha kötü.

İkinci eksik adın kendisiydi: 50 karakter ve konuyu adlandıran kısmı yalnız iki kelime.
Okumak için sorun değildi; **yazmak** için sorun.

### Çözümleme neden botta, API'de değil

API'de `run_id` alan ~15 route var ve hepsi yol parametresini `_required_run`'dan **sonra
da** doğrudan kullanıyor (`repo.list_sources(run_id)`; `download_artifact` `_required_run`'ı
hiç çağırmıyor). Etiketi orada kabul etmek her route'un çözülmüş kimliği kullandığını tek
tek kanıtlamayı gerektirirdi ve kaçırılan bir yer sessizce yanlış koşuyu okurdu.
Çözümlemeyi `Repository`'nin sahiplik gardiyanına koymak ise yetkilendirme sarmalayıcısına
kimlik çözümleme karıştırmak olurdu — güvenlik açısından kritik tek noktayı iki işe
birden bakar hâle getirir.

Bot, kimliğin **elle yazıldığı tek yüzey**: panelde tıklanıyor, MCP/Langflow ajanları
kimliği zaten API'den alıyor. Orada çözmek tek noktada kalıyor ve sahiplik filtresini
bedavaya devralıyor — `GET /v1/research-runs` çağıranın kendi koşularını döndürdüğü için
arama başkasının koşusunu hiç göremiyor.

### Kurallar

**ULID görünümlü argüman aramayı atlıyor.** `looks_like_run_id` (26 karakter, tümü büyük
harf/rakam) doğruysa token olduğu gibi geçiyor, ağ çağrısı yok. Etiketler `slugify`
çıktısı olduğu için alt çizgi ya da küçük harf taşıyor; yanlış tahminin bedeli bir
listeleme çağrısı ve bir hata mesajı, gerçek kimlik yine çalışıyor.

**Karşılaştırma `run_label` üzerinden ve casefold.** Aynı yardımcı hem mesajı yazarken hem
ararken kullanılıyor, dolayısıyla ikisi ayrışamıyor: etiketi olmayan eski koşular da
`run_label`'ın sorudan türettiği adla bulunuyor.

**Çakışmada tahmin yok.** Aynı ada uyan birden çok koşu varsa kimlikleri, durumları ve
tarihleriyle listeleniyor ve **hiçbir şey yapılmıyor**. `/cancel` geri alınamıyor; "en
yenisini seç" kuralı yanlış koşuyu iptal edebilirdi.

**Tekillik zorlanmıyor.** Etiketi üretirken sahibin koşularını sorgulamak gerekirdi ve boru
hattı `Principal.system()` ile çalıştığı için o sorgu sahiple değil bütün koşularla
eşleşirdi. Çakışma yukarıdaki listeleme ile çözülüyor.

**Hata dili istemci dilinden.** Çözümleme koşuyu bulmadan önce çalışıyor, yani koşunun dili
henüz bilinmiyor. Bulunduktan sonrası bugünkü gibi koşunun dilinde.

### Ad yazılabilecek uzunlukta

Üç düzeltme: `research_label` istemi en çok dört kelime istiyor ve "araştırma eylemini
değil konuyu adlandır" diyor; `_SLUG_STOPWORDS`'e dolgu kelimeler eklendi (`research`,
`studies`, `study`, `that`, `about`, `using`, `based`, `review`, …); etiket
`LABEL_MAX_LENGTH = 32` ile kırpılıyor (tarih son eki bunun dışında).

Aynı girdi artık `artificial_intelligence_write` veriyor. Yalnız **yeni** koşuları
etkiliyor; kayıtlı etiketler protokolde duruyor ve aynen çalışmaya devam ediyor.

### `/kosular`

Son 10 koşuyu adı, durumu, aşaması ve tarihiyle listeliyor (`/runs` eş adı).

**Komut satırı `<code>` içinde, çünkü Telegram argümanı taşımıyor.** Bir `/komut` metni
bağlantı olarak görünüyor ama dokunulduğunda yalnız komutun kendisi girdi kutusuna gidiyor;
argüman düşüyor. `<code>` ise dokunulduğunda tamamını panoya kopyalıyor — bir dokunuş
kopyala, bir yapıştır. Önerilen komut duruma göre seçiliyor: biten koşuda `/get`, diğerinde
`/status`.

### Doğrulama

| Ne | Sonuç |
|---|---|
| Test | 324 geçiyor |
| `/cancel <ad>` | Doğru ULID ile iptal ediliyor, büyük/küçük harf fark etmiyor |
| `/cancel <ULID>` | Listeleme çağrısı **yapılmıyor** |
| Bilinmeyen ad | Hiçbir şey iptal edilmiyor, `/kosular` öneriliyor |
| İki eşleşme | Hiçbir şey iptal edilmiyor, iki kimlik de listeleniyor |
| Etiketsiz eski koşu | Türetilen adla bulunuyor |
| Yeni etiket | 32 karakterin altında, dolgu kelime yok |
| Şıkka basınca | `included_families` ve `scope` protokolde **ve** satırda değişiyor |
| Yazınca | Alan değişmiyor, cevap yönlendirmeye düşüyor |
| Geçersiz `value` | Protokol bozulmuyor, `scoping_not_applied` yazılıyor |
| Aile minimumu > `max_sources` | Protokol değişmiyor, koşu ilerliyor |
| Onay düğmesi | `{"approved": true}`, tek dilde ve koşu adıyla yanıt |
| Reddet düğmesi | Gerekçe gelmeden **hiçbir şey** gönderilmiyor |
| Başkasının düğmesi | Reddediliyor |
| Bot yeniden başlamışsa | Düğme `/respond` komutunu tekrarlıyor |
| HTML reddedilirse | Aynı mesaj düz metin olarak yeniden gidiyor |

---

## 24. Öncelikli koşu kuyruğu (v0.11.0)

Kuyruk ilk gelen ilk hizmet alır düzenindeydi; acil bir soru 180 dakikalık bir koşunun
arkasında bekliyordu. Tek arq kuyruğunun içinde iki skor bandı açıldı, çalışan normal koşu
acil bir koşu için duraklatılıyor ve acil iş bitince kendiliğinden devam ediyor. Aciliyet
Telegram, MCP, Langflow ve panelden alınıyor.

Şema göçü içerdiği ve birden çok servisi kapsadığı için ayrıntı ve gerekçeler kendi
raporunda: [PRIORITY_QUEUE_V0.11.0_IMPLEMENTATION_REPORT.md](PRIORITY_QUEUE_V0.11.0_IMPLEMENTATION_REPORT.md).

> **Not:** Bu bölüm 13. bölümdeki redaksiyon kararını bilinçli olarak genişletir — ekip
> görünümüne `priority` eklendi. Gerekçe kendi raporundadır.

---

## 25. Donanıma göre paralel koşular (v0.12.0)

Worker `max_jobs = 1` ile çalışıyordu; bir koşunun duvar saatinin büyük kısmı ağ ve CPU
işinde geçtiği için bu, GPU'nun ihtiyaç duyduğundan çok daha geniş bir sınırdı. Paralel
koşu sayısı artık elle seçilmiyor, her kabulde canlı ölçümden hesaplanıyor: uygun RAM,
o anki CPU yükü ve Ollama'nın bildirdiği yerleşik VRAM. Model çağrıları süreç genelinde
tek sıraya alındı, böylece paralellik tek GPU'yu darboğaza sokmuyor ve karta aynı anda
birden fazla model yüklenmiyor. Eşzamanlı olan **koşulardır, koşunun içi değil**: tek bir
araştırma bu sürümde daha hızlı bitmiyor.

Paralelliğin ortaya çıkardığı üç kusur da kapatıldı: koşu başına kurulan `DomainLimiter`
(nezaket sınırını koşu sayısına bölüyordu), varsayılan veritabanı havuzu ve cron işlerinin
`max_jobs` yüzünden bir koşu çalışırken hiç çalışmaması.

Ayrıntı ve gerekçeler kendi raporunda:
[PARALLEL_RUNS_V0.12.0_IMPLEMENTATION_REPORT.md](PARALLEL_RUNS_V0.12.0_IMPLEMENTATION_REPORT.md).

> **Not:** 24. bölümdeki önceleme kuralları bu bölümde güncellendi — acil koşu artık yalnız
> boş slot yokken bir koşuyu duraklatıyor.

---

## 26. Koşuyu izsiz silme: `research-admin purge-runs`

Panel deneme amaçlı başlatılıp iptal edilen koşularla dolmuştu. İptal etmek koşuyu
bitiriyor ama **silmiyor**: satır panelde durmaya, pasajları corpus havuzunda kalmaya ve
anlık görüntüleri nesne deposunda yer kaplamaya devam ediyor.

**Neden elle SQL değil.** `research_runs` ile çocuk tabloları arasında yabancı anahtar
yok — `run_id` yalnız indekslenmiş bir kolon, dolayısıyla veritabanı seviyesinde cascade
yok. Koşu satırını elle silmek, hiçbir şeyin bir daha ulaşamayacağı binlerce satır bırakır.
Ölçülen: 19 iptal koşusu için 17 494 kaynak ilişkisi, 4 011 frontier, 2 657 olay, 2 315
pasaj, 575 kanıt bağı, 561 iddia, 355 kaynak sürümü, 352 kaynak, 103 checkpoint.

`Repository.purge_run` bunların hepsini adıyla siliyor, çocuklardan ebeveynlere doğru;
`ObjectStore.list_keys` ise `<run_id>/sources/` altındaki anlık görüntüleri buluyor —
bunlar içerik özetiyle adlandırıldığı için veritabanında adları geçmiyor.

**Pasajlar da gidiyor.** Onlar sonraki koşuları tohumlayan corpus havuzu
(`list_corpus_passages`), yani bir koşuyu silmek metnini o havuzdan da çekiyor. Terk
edilmiş bir koşu için istenen tam da bu; tamamlanmış bir koşu için iki kez düşünmeli.

Komut varsayılan olarak **silmiyor**: eşleşenleri listeleyip `--yes` bekliyor. Elle
yazılmış bir kimlik, on dokuz yanlış koşunun gittiğini sonradan öğrenmek için kötü bir yol.

```powershell
docker compose exec api research-admin purge-runs --status cancelled
docker compose exec api research-admin purge-runs --status cancelled --yes
docker compose exec api research-admin purge-runs --run-id 01M0... --yes
```

`purge_run` bir `run_id` aldığı için sahiplik metasınıfı onu da otomatik koruyor;
başkasının koşusunu silmek reddediliyor (`tests/test_run_ownership.py`).

**Uygulandı:** 19 iptal koşusu silindi, nesne deposundan 317 nesne kalktı, artık hiçbir
tabloda sahipsiz satır yok.

---

## 28. Akış diyagramlarının güncel mimariye uyarlanması

README ile mimari belgelerdeki akış çizimleri, çalışan sistemin güncel bileşenleriyle
eşitlendi. Uçtan uca sistem akışı ve LangGraph durum makinesi hem SVG hem etkileşimli HTML
olarak yenilendi; diyagramlar Smart PDF Router, karantina kararı ve ayrı Docling servisini
aynı adlarla gösteriyor. Diyagram giriş noktaları `docs/diagrams/README.md` altında
toplandı ve kök README güncel çizimlere bağlandı.

Bu değişiklik yalnız belgelemedir; çalışma zamanı davranışını değiştirmez.

---

## 29. PDF ayrıştırma teşhis raporu ve süre kaydı

Bir koşunun PDF'lerinin neden ağır yola yönlendirildiğini yalnız veritabanı ve manifestoyu
elle birleştirerek anlamak gerekiyordu. `scripts/inspect_bundle.py <run_id> --heavy --md
<dizin>` artık yönlendirme gerekçelerini, motor sonuçlarını, cihaz/build bilgisini ve
belge başına süreleri tek raporda topluyor.

Ayrıştırma provenance'ına toplam süre, yönlendirme süresi ve ağır motor süresi eklendi;
teslimat manifestosu bu alanları dışa aktarıyor. Böylece edinim süresindeki yavaşlığın
indirmeden mi yoksa ayrıştırmadan mı geldiği koşu sonrasında ölçülebiliyor. Değişiklik
`tests/test_parsers.py` ve `tests/test_export_manifest.py` kapsamıyla doğrulandı.

---

## 30. Ajan yönergelerinin `AGENTS.md` altında tekleştirilmesi

Depo işletim ve geliştirme kuralları daha önce ajana özgü ikinci bir dosyayla
ayrışabiliyordu. `AGENTS.md` artık tek kalıcı kaynak; eski ikinci kopya kaldırıldı ve
gitignore, yerel ajan çalışma dosyalarını kaynak kontrolüne almadan bu tek kaynağı
izleyecek biçimde güncellendi.

Aktif dal, Docker rebuild zorunluluğu, profilli Telegram botu, GPU'lu Docling dağıtımı,
kişisel MCP anahtarları ve güvenli yedekleme yolu aynı belgede tutuluyor. Bu değişiklik
çalışma zamanı davranışını değiştirmez; sonraki geliştirmelerde yanlış işletim adımı
riskini azaltır.

---

## 31. PDF raporunda Inspector'da kalan sayfaların gösterilmesi

`inspect_bundle.py --heavy` ağır motora yönlendirilen sayfaları gösteriyordu; nihai metni
`pdf-inspector` tarafından üretilen sayfaları tek seçimle rapora alma yolu yoktu. `--out`
bütün sayfaları ayrı dosyalara çıkarabiliyordu, ancak okunabilir stdout/Markdown raporunda
aynı seçimi yapmıyordu.

Yeni `--fast`, nihai motoru `pdf-inspector` olan bütün sayfaları seçiyor ve neden orada
kaldıklarını üç durumla ayırıyor:

| Durum | Anlamı |
|---|---|
| `untouched` | Sayfa ağır motora hiç yönlendirilmedi |
| `fallback` | Ağır motor çağrıldı ama kullanılabilir sayfa döndürmedi |
| `quarantined` | Ağır çıktı geldi, kalite kontrolü reddetti ve hızlı metin korundu |

`--all` bütün PDF sayfalarını aynı rapor biçiminde gösteriyor. `--page`, `--heavy`,
`--fast` ve `--all` birbirini dışlayan açık seçimler; eski `--out`-tek-başına davranışı
bütün sayfaları yazmaya devam ediyor. Sayfa başlığında yönlendirme gerekçesinin yanında
birleştirme kararının `karar_gerekcesi` alanı da gösteriliyor.

`--md` hedefinde seçim modu dosya adına otomatik ekleniyor. Hem dizin hedefinde hem açık
dosya adında `--fast` → `_fast.md`, `--heavy` → `_heavy.md`, `--all` → `_all.md` ve
`--page 3 --page 8` → `_page-3-8.md`. Kullanıcı son eki zaten yazdıysa yinelenmiyor.
Seçimsiz özet raporunun eski adı korunuyor. Böylece aynı taban hedefle art arda üretilen
görünümler birbirini sessizce ezmiyor.

Doğrulama `tests/test_inspect_bundle.py` içindedir: final motor seçimi, üç Inspector
durumu, mevcut `--heavy` anlamının korunması, `--all`, Markdown içeriği, dizin ve açık
dosya hedeflerinin farklı ad üretmesi ve hazır son eklerin yinelenmemesi ayrı ayrı
denetlenir.

---

## 32. Jina Reader browser fallback'i

Doğrudan HTTP, AgentSearch `/read` ve Crawl4AI'nin boş ya da başarısız döndüğü sayfalar
artık son yerel HTTP yolu olan Scrapling'den önce Jina Reader ile deneniyor. Güncel sıra:

```text
direct → scholarly_metadata → agentsearch_read → crawl4ai → jina_reader → scrapling
```

Reader çağrısı hedef URL'yi `JINA_READER_URL` altına ekliyor ve `X-Engine: browser`
başlığıyla JavaScript çalıştıran motoru açıkça istiyor. API anahtarı veya hedef siteye ait
çerez/kimlik bilgisi gönderilmiyor. Hedef URL, zincire girmeden önce mevcut public-IP,
şema, port ve URL-credential denetiminden geçmiş oluyor.

Koruma sınırları diğer edinim yollarıyla aynı tutuldu: 25 MiB indirme sınırı uygulanıyor,
400 karakterin altındaki yanıt belge sayılmıyor ve HTTP/zaman aşımı hatası koşuyu
düşürmeden Scrapling'e geçiriliyor. Dış servis istenmezse
`ENABLE_JINA_READER_FALLBACK=false`; self-host kurulum için `JINA_READER_URL`
değiştirilebilir. Varsayılan dış çağrı bütçesi 90 saniye ve
`JINA_READER_TIMEOUT_S` ile ayarlanabilir.

Bu değişiklik, tarihsel `COLLECTION_ARCHITECTURE_REPORT` içindeki güncel-zincir notunu
bilinçli olarak aşar; tarihsel metin değiştirilmedi, altına yeni tarihli not eklendi.

**Doğrulama:**

- Jina isteğinin tam URL'yi koruduğu, browser motorunu zorladığı, `Authorization`
  göndermediği, kapalı ayarın deneme kaydı üretmediği ve başarıdan sonra Scrapling'in
  çalışmadığı üç yeni testle doğrulandı.
- Hedefli paket: `18 passed`; tam paket: `437 passed`.
- Değiştirilen Python dosyaları için hedefli Ruff temiz.
- `docker compose up -d --build` tamamlandı; worker container'ı altı basamaklı sırayı ve
  etkin `https://r.jina.ai` ayarını okuyor.
- Anahtarsız gerçek smoke testinde browser-forced Wikipedia isteği `HTTP 200`,
  `195476` karakter ve `text/plain` döndürdü.

---

## 33. GitHub URL akıllı repository işleyicisi

GitHub repository URL'leri artık genel web sayfası gibi kazınmıyor. Edinim katmanı
`github.com/<owner>/<repo>` biçimini ve aynı repository altındaki `tree`, `blob`, `issues`
gibi yolları repository köküne çözüyor; ardından geçici dizine aşağıdaki sınırlı klonu
alıyor:

```text
git clone --depth 1 --single-branch --no-tags
```

İşleyici önce README'leri, sonra bilinen manifest/yapılandırma dosyalarını, ardından
izlenen kaynak dosyalarını seçiyor. Yalnız `git ls-files` çıktısındaki düzenli metin
dosyaları okunuyor; symlink'ler, binary içerik, vendor/build/cache dizinleri, dosya başına
ve toplam metin sınırını aşan içerik atlanıyor. Çıktı; repository URL'si, kesin commit
kimliği, seçilen dosya listesi ve dosya sınırlarıyla deterministik Markdown'a dönüşüyor.
Acquisition provenance'ı commit'i, checkout boyutunu, eklenen/atlanan dosyaları,
kırpılma durumunu ve temizliğin doğrulandığını kaydediyor.

Yeni edinim sırası şöyledir:

```text
github_repository → direct → scholarly_metadata → agentsearch_read → crawl4ai → jina_reader → scrapling
```

GitHub işleyicisi yalnız tanınan repository URL'lerinde sıraya giriyor. Klonlama veya
metin üretimi başarısız olursa koşu düşmüyor; mevcut doğrudan HTTP zinciri devam ediyor.
Varsayılan sınırlar 90 saniye, 100 MiB checkout, 200 dosya, dosya başına 512 KiB ve toplam
2.000.000 karakterdir. GitHub connector'ının verdiği repository `size` metadata'sı varsa
100 MiB sınırı indirmeden önce de uygulanıyor. Gerekli `git` istemcisi uygulama imajına
eklendi.

### Temizleme garantisi

Her klon için ayrı `research-github-*` geçici dizini açılıyor ve başarı, hata, timeout ile
async iptal yollarının tamamı `finally` bloğunda temizleniyor. Timeout veya iptalde çalışan
Git süreci önce öldürülüp bekleniyor; salt-okunur dosyalar izin düzeltmeli `rmtree` ile üç
kez deneniyor. Temizleme ayrıca cancellation'dan korunuyor ve ancak başarıyla bittikten
sonra belge `cleanup_confirmed=true` ile dönebiliyor. Alt modüller klonlanmıyor ve Git LFS
smudge kapalı tutuluyor.

**Doğrulama:**

- URL ayrıştırma, seçim/biçimlendirme, klon hatası, async iptal, süreç öldürme, geçici
  dizin temizliği, acquisition önceliği ve HTTP fallback'i yeni testlerle kapsandı.
- GitHub/Jina/relevance/plan hedefli paketi: `39 passed`; tam paket: `447 passed`.
- Yeni kod ve hedef değişiklikler için Ruff (acquisition'ın mevcut `BLE001`/`S110`
  borcu hariç), `docker compose config --quiet` ve `git diff --check` temiz.
- `docker compose up -d --build` tamamlandı. Worker içinde `/usr/bin/git`, etkin ayarlar
  ve yedi basamaklı edinim sırası doğrulandı; tüm servisler ayakta, Docling dahil health
  taşıyan servisler sağlıklı.
- Gerçek `brcrusoe72/agent-search` smoke testinde `--depth 1` klonundan commit
  `7830af0efded9dfe0d632c461d7b919de8726f5d`, 57 dosya ve 466.461 karakter üretildi.
  `cleanup_confirmed=True`; işlem öncesi/sonrası `research-github-*` dizin farkı `[]`.

Bu değişiklik, tarihsel `COLLECTION_ARCHITECTURE_REPORT` içindeki edinim zinciri kararını
GitHub repository URL'leri için bilinçli olarak özelleştirir. Tarihsel akış korunmuş,
altına yeni tarihli not eklenmiştir. Metadata'sız adaylarda boyutun ancak klondan sonra
kesinleşmesi sınırı [OPEN_ITEMS.md](OPEN_ITEMS.md) 20. maddede izleniyor.

---

## 34. Sistem mimarisi diyagramının güncel mimari ve Cezeri derisiyle yenilenmesi

Kök README'deki “One Workstation, an Office-Wide Research Service” bölümünde kullanılan
sistem mimarisi diyagramı güncel compose ve host kurulumunu gösterecek biçimde yeniden
çizildi; bölümün açıklama metni de aynı mimariye eşitlendi. Önce Türkçe HTML kaynak
güncellendi, ardından aynı geometri İngilizce bağımsız SVG'ye aktarıldı. Eski diyagramdaki
"koşular sırayla işlenir" notu kaldırıldı; v0.12.0'daki canlı kapasite kapısı altında
paralel koşular ve süreç genelinde serileştirilen model çağrıları birlikte gösteriliyor.

Güncel görünüm ayrıca operasyon yüzeylerinde panel ile Langflow'u, Repository katmanındaki
sahiplik korumasını, Redis'in acil/normal önceliklerini, Git/Jina dahil edinim kümesini ve
v0.13.0'da eklenen ayrı Docling GPU servisini kapsıyor. Panelin API'yi atlayan doğrudan
veritabanı okuması ile Ollama'nın compose dışındaki host yerleşimi korunuyor.

Görsel dil, depo kökündeki `.diagram-design` işaretçisinin seçtiği `cezeri` profiline
taşındı. Koyu tuvalde Cezeri'nin kömür rengi zemin, açık mürekkep, camgöbeği vurgu ve açık
mavi bağlantı karşılıkları; düğüm adlarında Raleway, teknik etiketlerde Geist Mono
kullanılıyor. Çalışma yalnız belge ve diyagram dosyalarını değiştiriyor; çalışan servislere
etkisi yoktur.

**Doğrulama:** Eklentinin erişilebilirlik/güvenlik self-check'i HTML ve SVG için temiz;
geometri denetimi sıfır kırpılmış etiket bildiriyor. SVG sıkı XML olarak ayrıştırıldı,
ilk çocuklarının `title`/`desc` olduğu ve Türkçe kaynakla dışa aktarılan İngilizce sürümün
geometrisinin eş olduğu doğrulandı. Son görünüm 1280×720 başsız Chrome render'ında elle
incelendi.

---

## 35. Commit/push öncesi zorunlu tam-test kapısı

`AGENTS.md` commit kuralı, son kod değişikliğinden sonra tam pytest paketi sıfır çıkışla
bitmeden commit veya push'ı yasaklayacak biçimde kesinleştirildi. Test ortamı erişim veya
yorumlayıcı hatasıyla başlatılamıyorsa önceki rapor sonucu kullanılamıyor; ortam çözülene
kadar yayın duruyor. Yalnız testten sonra gelen belge değişikliği kodu değiştirmediğinde
paketin yeniden koşması gerekmiyor.

Bu oturumda `.venv` başlatıcısının verdiği hata gerçek ortam bozulması değildi: Codex
sandbox'ı, `pyvenv.cfg` içindeki `%LOCALAPPDATA%` Python 3.12 tabanını çalıştırmayı
engelliyordu. Yetkili yürütmede aynı ortam Python 3.12.7, pytest 8.4.2 ve Ruff 0.16.2 ile
sağlıklı açıldı. Yanlışlıkla yeniden kurulum yapılmaması için teşhis yolu kalıcı notlara
eklendi. Bu makineye özgü `AGENTS.md` bilinçli olarak gitignore'da tutulduğu için kapı bu
kurulumda doğrudan etkindir; paylaşılan tarihsel kayıt bu bölüm ve CHANGELOG'dur.

Tam paket son kod değişikliğinden sonra `447 passed, 2 warnings` sonucuyla 62,42 saniyede
geçti. Tam-depo Ruff'ın 1.053 tarihsel ihlal taşıdığı ayrıca görünür kılındı; committe
eklenen Inspector satırlarındaki iki yeni `ISC004` ihlali düzeltildi. Yeni/değişen kod
için hedefli Ruff kapısı korunurken tarihsel borç temizmiş gibi raporlanmıyor.

---

## 36. Connector görünümünde SERVICE_TOKEN kimlik doğrulaması

Çok kullanıcılı kimlik geçişinde API'nin güvenilir aracılar için kabul ettiği kimlik
bilgisi `SERVICE_TOKEN + X-Actor-User` olarak değiştirilmişti. Panelin genel API proxy
yolu bu seçimi `service_token or api_token` ile uygularken connector sağlık snapshot'ı
eski `API_TOKEN` değerini göndermeye devam ediyordu. İki değer farklı olduğunda API
`/v1/connectors` isteğini 401 ile reddediyor; panel boş sağlık cevabını geçmiş operasyon
kayıtlarıyla birleştirirken connector'ları varsayılan olarak `enabled=false` gösteriyordu.
Canlı API'de 28 connector'ın 24'ü çalışır durumdayken paneldeki toplu “disabled” görünümü
bu nedenle oluştu.

Snapshot isteği artık diğer panel API çağrılarıyla aynı seçim kuralını kullanıyor:
`SERVICE_TOKEN` tanımlıysa onu, geriye dönük kurulumlarda yoksa `API_TOKEN` değerini
gönderiyor. Değerler hiçbir yanıta veya loga yazılmıyor. Bu değişiklik
`MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md` içindeki servis-token kararını
değiştirmiyor; gözden kaçmış tek çağrı yolunu o kararla yeniden uyumlu hâle getiriyor.

Regresyon testi iki token farklıyken connector snapshot isteğinin yalnız
`SERVICE_TOKEN` taşıdığını ve dönen sağlıklı connector'ın etkin kaldığını doğruluyor.
Hedefli Ruff, dosyalardaki önceden var olan ve `OPEN_ITEMS.md` 21. maddede izlenen kural
borcu hariç temiz; kontrol paneli paketi `21 passed, 1 warning` sonucuyla geçti. Dağıtım
yalnız host üzerindeki kontrol paneli sürecinin yeniden başlatılmasını gerektirir; Docker
API ve worker servisleri ile çalışan araştırmalar yeniden başlatılmaz.

Son kod değişikliği üzerinde zorunlu tam paket de `448 passed, 2 warnings` sonucuyla
76,12 saniyede tamamlandı.

Canlı dağıtımda yalnız host paneli yeniden başlatıldı (PID `19184` → `26204`) ve sağlık
ucu `healthy` döndü. Panelin kullandığı `SERVICE_TOKEN` ile `/v1/connectors` 28 kayıt
döndürdü: 24'ü etkin ve sağlıklı, üçü gerçek yapılandırma/opsiyonel bağımlılık nedeniyle
disabled, biri etkin fakat yerel Zotero bağlantısı olmadığı için unhealthy. Yeniden
başlatma sonrasında iki aktif araştırma `running` ve hatasız kalmaya devam etti; daha önce
ACQUIRE güvenlik timeout'uyla düşmüş üçüncü koşunun durumu bu değişiklikle ilişkili değil.

---

## 38. Tek çalışma zamanı sürümü ve telemetri SVG yerleşimi

Paket metadata'sı, API, panel health/status, MCP health ve footer daha önce birbirinden
bağımsız sabit sürüm metinleri taşıyordu. `pyproject.toml` beyanı kurulu dağıtım metadata'sına
dönüşüyor; `research_platform.version.VERSION` bütün çalışma zamanı yüzeylerinin tek okuma
noktasıdır. Panel HTML'i sunulurken aynı değer footer yer tutucusuna yazılır. Sürüm eşitliği
ile health ve footer çıktıları regresyon testleriyle korunur; OPEN_ITEMS 22. madde
kapatılmıştır.

Donanım SVG'sinde her metrik paneli için başlık bandı ile veri alanı ayrıldı. Legend'ler
başlığın sağına, eksen ve grid çizgileri başlık bandının altına taşındı. Koordinat testi
başlık/legend yatay mesafesini ve üst eksen etiketinin dikey mesafesini doğruluyor. Terminal
smoke koşusunun artifact'leri idempotent finalizer ile yenilendi; Chrome'da doğal 1200×930
boyut, panel `v0.14.0` footer'ı ve çakışmasız görünüm doğrulandı.

Değişen Python dosyalarında hedefli Ruff temizdir. Son hedefli test paketi `55 passed`, son kod
değişikliğinden sonraki zorunlu tam kapı `461 passed, 2 warnings` sonucuyla tamamlandı.
Canlı iki araştırma boyunca worker ve API yeniden oluşturulmadı; yalnız host paneli
yenilendi ve koşular `running` kalmaya devam etti.

---

## 40. Telemetri çıktı seçimi: `HARDWARE_TELEMETRY_OUTPUT_TYPE`

Koşu terminal duruma geldiğinde donanım telemetrisi üç artifact üretiyordu ve üçü de
koşulsuzdu: ham ölçümlerin `18_hardware_utilization.csv` dosyası, `mean`/`p95`/`max` ile
aktif süre ve eksik ölçüm tahminini taşıyan `19_hardware_utilization_summary.json`, ve
çizilmiş `20_hardware_utilization.svg` grafiği. Grafiği istemeyen bir kurulumun kapatma
yolu yoktu; `telemetry_svg` her ölçüm için koordinat ürettiğinden bu yalnız depolama değil
hesap maliyetiydi.

`HARDWARE_TELEMETRY_OUTPUT_TYPE` bu seçimi `.env`'e taşıyor. `csv` veri dosyalarını üretip
grafiği atlıyor, `all` üçünü de üretiyor. Varsayılan `all` olduğu için anahtarı
tanımlamayan kurulum bugünkü davranışını aynen sürdürüyor. Bu, 39. bölümdeki "dağıtıma
bağlı davranış `.env`'den yönetilir" kararının devamıdır; v0.15.0 raporunun anahtar
tablosuna dokunulmadı, o tablo v0.15.0'ın tarihsel kaydıdır.

JSON özeti bilinçli olarak `csv` modunda da üretiliyor. Bir görselleştirme değil veridir:
`p95` ve tepe değerleri yalnız orada bulunuyor, CSV'de yok. Atılsaydı 8 GB VRAM'li kartta
asıl kritik olan tepe bilgisi geri döndürülemez biçimde kaybolurdu. Testte iki modun CSV ve
JSON çıktılarının bayt bayt aynı olduğu doğrulanıyor — `csv` grafiği düşürüyor, ölçümü
veya özeti bozmuyor.

`csv` modunda `telemetry_svg()` hiç çağrılmıyor; üretilip atılmıyor. Bundle birleştirme de
üretilen ada göre seçim yapıyor: eski kod `raw_bytes["20_hardware_utilization.svg"]` diye
doğrudan indekslediği için `csv` modunda `KeyError` verirdi. Artık `_select` yardımcısı
yalnız gerçekten üretilmiş üyeleri alıyor ve additions'ı boş kalan bundle yeniden
zip'lenmeden atlanıyor. Bugüne kadar hiçbir yerde kullanılmayan `TELEMETRY_FILES` sabiti de
dosya adlarının tek kaynağı hâline getirildi.

Testte ortaya çıkan asıl kırılganlık şuydu: `Settings`, `env_file=".env"` ile
yapılandırılmış ve finalizer testi `get_settings()` çağırıyordu — yani test paketi koştuğu
makinenin gerçek `.env`'ini okuyordu. Doğrulandı: test ortamında `interval_s` `60.0`
dönüyor, bu değer ne kod varsayılanında (`5.0`) ne `.env.example`'da (`5`) var. `.env`'e
`OUTPUT_TYPE=csv` yazılır yazılmaz o test kırılacaktı. Testler artık beklediği modu açıkça
sabitliyor (`model_copy`), varsayılan doğrulaması ise deponun mevcut
`Settings(_env_file=None, ...)` kalıbını kullanıyor.

Panelde değişiklik gerekmedi: SVG önizlemesi `data.artifacts.find(...)` sonucunu
`if(telemetryGraphic)` ile koruyor, dosya yoksa bölüm sessizce render edilmiyor.

**Bilinçli sınır.** `all` ile finalize edilmiş bir koşu sonradan `csv` ile yeniden finalize
edilirse, `merge_zip` additions'ta olmayan üyeleri koruduğu için bundle'lardaki eski SVG
yerinde kalır ve standalone SVG artifact satırı silinmez. Finalizer koşu başına bir kez
çalıştığından bu yalnız retry yolunda görülür; geçmiş artifact'i silmemek daha güvenli
olduğu için davranış korundu.

Değişen Python dosyalarında hedefli Ruff temizdir. Hedefli telemetri paketi `11 passed`
yerine `13 passed`, son kod değişikliğinden sonraki zorunlu tam kapı `483 passed,
2 warnings` sonucuyla tamamlandı. Kapının ilk koşusunda `test_academic_connectors.py`
içindeki tamamen mock'lu bir edinim testi bir kez düştü; izole koşuda, modülün beş ardışık
koşusunda ve sonraki tam koşularda tekrarlamadı. O test `Settings(_env_file=None)`
kullandığı için bu bölümün `.env` değişikliğini görmüyor — ilgisiz, aralıklı bir kırılganlık
olarak not edildi.

---

## 41. Bağlam güvenli özet sentezi ve rapor kalite kapısı

24 saatlik `01M0T4XATMYJVK0XT433EAXTG1` koşusunun Word raporunda özet kutusu
`hastalıkların takip edilmesi, tahmin edilmesi v`, çalışmalar arası değerlendirme ise
`klinik karar verme veya ha` sözcük parçalarıyla bitiyordu. Koşu zaman bütçesi veya DOCX
yazıcısı metni kesmemişti: son integratif LLM çağrısı `done_reason=stop` ile tamamlanmış,
fakat doğrulama kapısından geçemeyince `_draft_overview()` deterministik geri dönüşe
geçmişti. Çıktılar geri dönüşteki ham `[:2600]` ve `[:3500]` karakter dilimleriyle birebir
aynıydı. Son çağrının `prompt_tokens=8192` değeri etkin 8K bağlamın tamamının dolduğunu da
gösteriyordu.

Tarihsel `SYNTHESIS_REPORT_PIPELINE_V0.8.0` raporunun küçük yerel model için kaynak
allow-list'i ve deterministik güvenli geri dönüş kararı korunmuştur. Değiştirilen karar,
geri dönüşün doğrulanmış tema metinlerini görünür raporda ham karakter sınırında kesebilmesi
ve overview katmanının tema katmanlarından farklı olarak onarım şansı taşımamasıydı.

### Uygulanan çözüm

- Overview istemi artık context, 2.048-token çıktı payı ve sabit istem payından türetilen
  bir bütçeyle kuruluyor. Beş temadan birini ham toplam dilimin sonunda kaybetmek yerine her
  tema için dengeli sentez/ortak yön/ayrışma/anlam kartı hazırlanıyor. Etkin 8K profilde
  tema özeti bütçesi 9.216 karakter; araştırma sorusu ve kaynak kimlikleri ayrıca bu
  bütçeden düşülüyor.
- İlk integratif yanıt geçersizse tek bir sınırlı onarım çağrısı yapılıyor. Onarım da
  kaynak, dil ve alan sözleşmesini geçemezse deterministik yol devreye giriyor.
- Görünür geri dönüş metni artık yalnız tam cümleleri seçiyor, gerektiğinde kaynak alanının
  `[Sxx]` atıflarını cümleye bağlıyor ve hiçbir sözcüğü veya atfı ortadan kesmiyor. Kabul
  edilen model alanları da özet için 2.600, çalışmalar arası değerlendirme için 3.500,
  sonuç ve belirsizlik için 2.400 karakterlik tam-cümle sınırlarına bağlı.
- Modelin string yerine `list[str]` döndürmesi güvenli biçimde düzyazıya birleşiyor.
  Sözlük, iç içe liste ve sayısal biçimler reddediliyor; böylece Python'ın
  `['birinci', 'ikinci']` gösterimi artık Word veya Markdown raporuna sızmıyor.
- Tema ve overview katmanlarının `initial_passed`, `repair_passed`, kısmi veya fallback
  durumu `synthesis_generation` olayına, yeniden üretilebilirlik manifestine ve Word yöntem
  ekine yazılıyor. Ham model cevabı kaydedilmiyor.
- Türkçe Word ve Markdown ana bölüm başlığı `Yönetici sentezi` / `Yönetici Özeti` yerine
  **Özet** oldu. Rapor pipeline sürümü `v0.15.0` olarak ilerletildi; iç artifact/API alan
  adı olan `executive_summary` geriye dönük sözleşme için korunuyor.

Bu düzeltme context değerini büyütmüyor. Temmuz ayındaki tek-model benchmark'ı Qwen 3 4B
için 24.576 tokenı tam GPU'da doğrulamış olsa da güncel kurulum GPU'yu ayrı Docling
servisiyle de paylaşıyor. Kodun önce ilan edilen 8K sınırında güvenli çalışması sağlandı;
context artışı ancak ortak GPU yük testiyle ayrı bir karar olabilir. `OPEN_ITEMS.md` 15.
maddedeki çok dilli kanıt çıkarımı bütçesi overview dışında bir yol olduğu için açık
kalmaya devam ediyor.

**Doğrulama:** Sentez, Word, exporter ve pipeline hedefli paketi `36 passed`; son kod
değişikliğinden sonraki zorunlu tam kapı `487 passed, 2 warnings` sonucuyla tamamlandı.
Değiştirilen dosyalardaki hedefli Ruff taramasında yeni ihlal yok; rapor sentezi ve Word
dosyalarında önceden var olan 20 ihlal temizmiş gibi raporlanmadı. `docker compose up -d
--build` tamamlandı; worker container'ı `v0.15.0` rapor sürümünü, `1. Özet` başlığını,
listeyi `Birinci. İkinci.` biçiminde normalleştirdiğini ve 8K profil için 9.216 karakterlik
overview bütçesini doğruladı. Rebuild öncesinde etkin veya kuyrukta araştırma yoktu.

---

## 42. Dile göre özet başlığı ve panel ayrıntı düzeni

41. bölümde Türkçe raporun ilk sentez bölümü **Özet** yapılmıştı; İngilizce Word yolu
tarihsel **Executive synthesis** metnini, Markdown teslimleri ise rapor dilinden bağımsız
olarak Türkçe **Özet** metnini taşımaya devam ediyordu. Başlık artık rapor diliyle aynı
kapıdan seçiliyor: Türkçe için **Özet**, İngilizce için **Summary**. İç artifact adı
`01_executive_summary.md` ve veri alanı `executive_summary` geriye dönük sözleşme olarak
korundu.

Araştırma ayrıntı çekmecesindeki başlıklar Türkçe başlık düzenine getirildi. İçerik
kelimelerinin ilk harfi büyütülürken **ve** bağlacı küçük bırakılıyor; örneğin **Kalite ve
Kapsam**, **Sorgu Dalları**, **Kaynak Hunisi**, **LLM ve Kanıt Özeti**. Kart etiketleri ile
ilgili tablo kolonları da aynı görsel düzene uyarlandı. `CONTROL_PANEL_V0.6.1` raporundaki
ayrıntıların yalnız araştırma açıldığında yüklenmesi ve kaynak ham içeriğinin panelde
gösterilmemesi kararları değişmedi.

Uzun kaynak tabloları ayrıntı çekmecesini gereksiz büyüttüğü için **Kabul Edilen
Kaynaklar (N)** bölümü yerel HTML `details/summary` yapısına taşındı. Bölüm varsayılan
olarak kapalıdır, klavye odağı alabilir ve başlıktaki göstergeyle açılıp kapanır; tablo ve
bağlantılar açıldığında önceki işlevini korur.

**Doğrulama:** Word, rapor dili, kontrol paneli ve telemetri hedefli paketi `54 passed`;
son kod değişikliğinden sonraki zorunlu tam kapı `490 passed, 2 warnings` sonucuyla
tamamlandı. Hedefli Ruff taramasında yeni ihlal yok; Word ve kontrol paneli testindeki
tarihsel 11 ihlal temizmiş gibi raporlanmadı. Canlı Chrome kontrolünde 61 kaynaklı bir
koşunun başlık listesi okundu; kaynak bölümü kapalı → açık → kapalı geçişinde tablo
görünürlüğü sırasıyla `false → true → false` oldu. Host paneli yeniden başlatıldı,
Docker imajları etkin koşu yokken yeniden oluşturuldu ve worker içinde `tr=Özet`,
`en=Summary`, rapor pipeline sürümü `0.15.0` doğrulandı.

---

## 43. Panel aydınlık modu ve alaka sıralı kaynaklar

Araştırma ayrıntısındaki **Kaynak Hunisi** başlığı, içeriğin arama ve kabul sürecindeki
referans dağılımını gösterdiğini daha açık anlatan **Referans Haritası** adıyla
değiştirildi. Veri ve huni hesapları değişmedi; yalnız kullanıcıya görünen ad güncellendi.

Panel üst çubuğuna **Aydınlık Mod / Karanlık Mod** düğmesi eklendi. Aydınlık palet yalnız
ana arka planı ters çevirmiyor; kart, tablo, çekmece, akış düğümü, durum rozeti, HITL
kutusu, telemetri alanı ve bildirim yüzeylerinin kontrastları da ayrı açık renklerle
tanımlandı. Seçim `research-platform-theme` anahtarıyla tarayıcıda korunuyor ve sayfa
yenilenmeden önce uygulandığı için belirgin koyu tema parlaması oluşmuyor. Varsayılan ve
mevcut kullanıcı tercihi koyu mod olarak korundu.

**Kabul Edilen Kaynaklar** tablosu artık `relevance_score` değerine göre yüksekten düşüğe
sıralanıyor. Sıralama API cevabının kopyası üzerinde yapılıyor; backend kayıt sırası ve
başka tüketicilerin aldığı kaynak listesi değiştirilmiyor. Puanı eksik kaynaklar sıfır
kabul edilerek listenin sonuna taşınıyor.

**Doğrulama:** Hedefli panel/telemetri paketi `36 passed`; son kod değişikliğinden sonraki
zorunlu tam kapı `491 passed, 2 warnings` sonucuyla tamamlandı. Hedefli Ruff taramasında
yeni ihlal yok; `test_control_panel.py` içindeki önceden var olan tek `ISC004` ihlali
temizmiş gibi raporlanmadı. Canlı Chrome kontrolünde aydınlık palet
`rgb(243, 246, 250)` arka plan, `rgb(23, 33, 43)` metin ve beyaz kart üretti; düğme ve
`aria-pressed` durumu doğru değişti, tercih yenilemede korundu. 61 kaynaklı koşuda görünen
alaka yüzdelerinin tamamı azalan sıradaydı; son beş değer `%46, %45, %45, %42, %39`
olarak okundu. Dağıtım öncesinde etkin ve kuyrukta koşu sayısı sıfırdı.

---

## 44. Pipeline zaman çizelgesinin Araştırma Akışı'na birleşmesi

Koşu çekmecesinde aynı veriyi iki ayrı bölüm gösteriyordu. Araştırma Akışı `PIPELINE_STAGES`
sırasına göre her aşamanın toplam ziyaret sayısını ve süresini veriyor ama kutuları
tıklanmıyordu; Pipeline Zaman Çizelgesi ise her ziyareti ayrı kart olarak kronolojik
diziyordu. Aradaki bağ kurulamıyordu: bir aşamanın kaç turu olduğu üstte yazıyor, o turların
dökümüne inmek için alttaki şeritte elle avlanmak gerekiyordu. 205 turluk koşuda o şerit
2.069 kart uzunluğundaydı ve pratikte kullanılamıyordu.

Zaman çizelgesi bölümü kaldırıldı, işlevi akışın içine alındı. Ziyareti olan aşama kutuları
tıklanabilir; tıklanınca o aşamanın bütün turları tur numarası, başlangıç, süre ve tek
satırlık özetle listeleniyor, satır açılınca mevcut `renderStageTools` araç tablosu altında
görünüyor. Akış kutucuğuna tam ekran düğmesi eklendi; tam ekranda düğüm şeridi yatay kaydırma
yerine sarılıyor. Escape tuşu artık en içteki katmanı kapatıyor — tam ekran açıkken önce onu
kapatıyor, koşu çekmecesini değil.

**Yol boyunca çıkan asıl hata bu değildi.** Detay uç noktası olayları `limit(5000)` ile ve en
eskiden çekiyor. 205 turluk koşu 16.563 olay yazmıştı, yani panel bu koşunun ilk üçte birini
görüyordu ve zaman çizelgesi sessizce kesiliyordu. Ölçüldü: veritabanında 207 `ACQUIRE`
ziyareti varken eski yol **63** tanesini üretiyordu. Aşama sınırları ayrı ve tavansız çekilir
hâle getirildi (o koşuda 2.069 satır, ucuz); yeni yol 207'nin tamamını üretiyor.

Araç dökümü, ziyaret listesinden ayrıldı ve talep üzerine gelen
`GET /api/runs/{id}/stages/{stage}` uç noktasına taşındı. `stage_timeline` ziyaret bulmayı ve
araç toplamayı tek geçişte yapıyordu; ortak sınır yürüyüşü `_walk_stage_boundaries` altında
tekleştirilip `stage_visits` (araçsız, tavansız) ve `stage_visit_details` (tek aşama, araçlı)
ayrıldı. `stage_timeline` bu ikisinin bileşimi olarak imzası değişmeden duruyor, mevcut
testleri regresyon kapısı olarak koruyor. `pipeline_flow` da araç toplamayan ucuz yola geçti.

Uç noktanın ilk hâli ziyaret aralıklarını tek bir `ilk..son` aralığı olarak sorguluyordu.
Bir aşamanın 200 ziyareti koşunun tamamına yayıldığı için bu, diğer aşamaların olaylarını da
okuyor ve kuyruğu tavana kaptırıyordu: 200 turun yalnız 63'ünde araç görünüyordu — kesilmenin
aynısı. Sorgu ziyaret başına ayrı aralığa çevrildi; artık 200 turun 199'u araç dökümüyle
geliyor ve gerçek veride 141–484 ms sürüyor.

Bu bölüme, aynı alanın işi olduğu için saniye altı süre biçimi de dahildir. Kurtarma turunda
hiçbir şey edinmeyen aşamalar milisaniyelerde dönüyor; `Math.round` bunların hepsini `0 sn`
yapıyor ve çalışan bir aşama ile hiç iş yapmadan dönen aşama ayırt edilemiyordu. Bir saniyenin
altında gerçek değer iki ondalıkla gösteriliyor (`0,01 sn`, `0,31 sn`); tam sıfır `0 sn`
olarak bırakıldı, saniye ve üstü biçimler değişmedi. Tek ondalık yeterli değildi: ölçülen
değerlerin çoğu 0,01–0,05 aralığında ve hepsi `0,0 sn` çıkardı.

Değişen Python dosyalarında hedefli Ruff, `control_panel.py`'deki **tek** yeni `B008` dışında
temizdir; o da yeni rotanın `Depends(require_user)` kullanmasından geliyor ve dosyadaki 21
rotanın tamamıyla aynı kalıptır. Panel JS'i `node --check` ile doğrulandı. Son kod
değişikliğinden sonraki zorunlu tam kapı `494 passed, 2 warnings` sonucuyla tamamlandı.

---

## 45. Kaynak figürü caption'ının rapor diline yerelleştirilmesi

24 saatlik `01M0T4XATMYJVK0XT433EAXTG1` koşusunun Türkçe Word raporunda kaynak figürü
etiketi ve sayfa gösterimi Türkçe olduğu hâlde aradaki yayın caption'ı İngilizce kalıyordu:
`Kaynak figürü: FIGURE 2. The analysis of ILDs ... [S30, s. 3].` Koşunun
`17_figure_observations.json` kaydı aynı figürün `title`, `main_findings` ve `limitations`
alanlarının Türkçe, `caption` alanının ise özgün İngilizce metin olduğunu doğruladı.

Tarihsel `SOURCE_FIGURE_EMBEDDING_V0.9.1` raporu kaynak caption'ını attribution ile birlikte
Word'e koymayı bilinçli olarak seçmişti. Bu kararın provenance tarafı korunuyor:
`FigureObservation.caption`, veritabanı gözlemi ve figür manifestindeki özgün kayıt
değiştirilmiyor. Değiştirilen karar, aynı ham alanın okuyucuya gösterilecek caption olarak
da doğrudan kullanılmasıdır.

Figür gözlemleri — önbellekten yüklenenler dahil — hazırlandıktan sonra kaynak caption'ları
tek sınırlı çağrıda rapor diline çevriliyor. Çeviri istemi caption metnini güvenilmeyen veri
olarak tanımlıyor; özetleme ve yeni bilgi eklemeyi yasaklıyor; figür numarası, sayılar,
kısaltmalar ve teknik terimleri koruyor. Dönen metnin hedef dile uyumu ile sayı dizisi
doğrulanmadan rapora alınmıyor. Çeviri geçici olarak başarısız olursa İngilizce metni Türkçe
caption içine sessizce karıştırmak yerine figür analizinin zaten yerelleştirilmiş başlığı
kullanılıyor. İngilizce kaynak caption'ı İngilizce raporda yeniden yazılmıyor.

Yerelleştirilmiş değer yalnız `GeneratedResearchFigure.caption` üretiminde kullanılıyor;
Word katmanı önceki gibi kendisine verilen görünür caption'ı yazıyor. Özgün figür kırpımı ve
görselin içindeki `Data Acquisition` gibi yayın etiketleri bu işin kapsamı dışında bırakıldı
ve baytları değiştirilmedi. Veritabanı şeması veya göç gerekmedi.

**Doğrulama:** Türkçe yerelleştirme, özgün provenance'ın değişmemesi, model hatasında
Türkçe başlığa güvenli dönüş ve İngilizce caption'ın İngilizce raporda yeniden yazılmaması
senaryolarını içeren figür paketi `8 passed`; son kod değişikliğinden sonraki zorunlu tam
kapı `497 passed, 2 warnings` sonucuyla tamamlandı. Hedefli Ruff taramasında eklenen
satırlarda yeni ihlal yok; `figure_analysis.py` ve mevcut testteki tarihsel ihlaller temizmiş
gibi raporlanmadı. Etkin veya kuyrukta koşu yokken `docker compose up -d --build`
tamamlandı; worker imajında yerelleştirici doğrulandı. Rapor sorunundaki gerçek caption
container içinden yerel modele verildi ve `ŞEKİL 2. ILD'lerin analizi farklı aşamalara
ayrılmıştır...` biçiminde Türkçe döndü; kaynak figür verisi değiştirilmedi.

---

## 46. Literatür konu haritasının Ek B'ye taşınması

Tarihsel `SYNTHESIS_REPORT_PIPELINE_V0.8.0` raporu konu haritasını ana gövdenin üçüncü
bölümü olarak konumlandırmıştı. Okuyucunun önce sentez ve sonuçlara ulaşması gerektiği için
bu yerleşim kararı değiştirildi: konu haritasının açıklaması, iki görseli ve çalışma
profilleri tablosu birlikte **Ek B**'ye taşındı. `16a_research_contribution_landscape.png`
ve `16b_theme_evidence_map.png` artifact adları, üretim verileri ve alternatif metinleri
değişmedi.

Ana gövde artık kesintisiz olarak **1. Özet**, **2. Araştırma çerçevesi**, **3. Tematik
kanıt sentezi** ve **4. Çalışmalar arası değerlendirme ve sonuç** sırasını izliyor. Ek A
yöntem bölümünün sunum açıklaması da konu haritasının artık Ek B'de olduğunu söylüyor.
Yeni başlık Türkçede **Ek B. Literatürün Konu Haritası**, İngilizcede **Appendix B.
Thematic Literature Landscape**; görsel caption'ları dile göre **Şekil/Figure B.1** ve
**B.2** biçiminde üretiliyor.

Eski Ek B kaynak kataloğu **Ek C**, eski Ek C iddia kaydı **Ek D** oldu. Tarihsel
`FIGURE_INTELLIGENCE_V0.9.0` raporunun Ek D olarak tanımladığı koşullu kaynak figürü
inceleme kaydı ise harf çakışmasını önlemek için **Ek E**'ye kaydı. `Sxx` kaynak yer
imleri ve iç bağlantı hedefleri korunuyor; İçindekiler alanı Heading 1 başlıklarından
yenileniyor. Odaklanmış geri dönüş Word şablonundaki ayrı literatür görünümü ile görsel
içermeyen Markdown rapor ekleri bu değişikliğin dışında bırakıldı.

**Doğrulama:** Türkçe/İngilizce başlık sırası, Ek E'nin koşullu üretimi, B.1/B.2
caption'ları, gömülü görseller ve kaynak bağlantıları için hedefli Word paketi `7 passed`;
son kod değişikliğinden sonraki zorunlu tam kapı `503 passed, 2 warnings` sonucuyla
tamamlandı. Hedefli Ruff taramasında yeni ihlal yok; `word_report.py` içindeki önceden var
olan 10 ihlal temizmiş gibi raporlanmadı. LibreOffice bulunmadığı için paketli
`render_docx.py` çalışamadı; bunun yerine Türkçe ve İngilizce yedişer sayfalık örnekler
Microsoft Word ile PDF/PNG'ye dönüştürüldü ve 14 sayfanın tamamı görsel olarak incelendi.
İki DOCX'in erişilebilirlik denetimi ayrı ayrı `high=0`, `medium=0`, `low=0` verdi. Etkin
veya kuyrukta araştırma yokken `docker compose up -d --build` tamamlandı; yeni worker
imajı örnek Türkçe DOCX üretip beklenen ana bölüm ve Ek A/B/C/D sırasını doğruladı.

---

## 47. Word raporunun koşu etiketiyle adlandırılması

Her koşu Word raporunu sabit `16_research_report.docx` adıyla üretiyordu. İki koşunun
raporu aynı klasöre çıkarıldığında hangisinin ne olduğu ad'dan anlaşılmıyordu.

Depoda bu sorunu çözecek alan zaten vardı: `protocol.label`. `VALIDATE_PROTOCOL` sırasında
`_name_run` konunun `snake_case` tutamağını LLM'e ürettiriyor, `slugify` ile sadeleştiriyor
ve Telegram bunu ULID yerine basıyor. Rapor artık o tutamağı taşıyor:
`16_ai_in_lung_ct_report.docx`. Etiket üretilemeyen koşularda — model erişilemez **ve**
sorunun slug'ı boş çıkarsa `_name_run` etiketsiz dönüyor — bugünkü `16_research_report.docx`
adı korunuyor.

`16_` öneki bilinçli olarak kaldı. Bundle üyeleri `sorted(selected_names)` ile yazılıyor ve
ASCII'de rakam harften önce geldiği için öneksiz bir ad, 01–20 dizisindeki 16. sırasını
kaybedip listenin sonuna düşerdi.

**Güvenlik bulgusu.** `ResearchProtocol.label` istemciden gelebiliyor: şema alanı yalnız
`max_length=64` ile doğrulanıyor, desen kısıtı yok, API koşu gövdesindeki protokolü olduğu
gibi alıyor ve `_name_run` protokol zaten etiket taşıyorsa erkenden dönüyor — yani istemci
etiketi hiç `slugify`'dan geçmiyor. Artifact anahtarı `runs/{run_id}/{name}` biçiminde
kurulduğu için `../` içeren bir etiket koşunun öneki dışına yazabilirdi. Ad kurulurken
etikete güvenilmiyor.

Ancak koşulsuz `slugify` de doğru değildi: ilk uygulamada test, `ai_in_lung_ct` etiketinin
dosya adında `ai_lung_ct` olduğunu gösterdi — `slugify` durak kelimeleri atıyor, dolayısıyla
zaten slug olan bir etiketi yeniden işlemek koşuyu sessizce yeniden adlandırıyor ve dosya
adı Telegram'ın bastığı tutamakla eşleşmiyordu. Kural ikiye ayrıldı: anahtar-güvenli
biçimdeki (`[A-Za-z0-9_]{1,64}`) etiket olduğu gibi korunuyor, bu biçimin dışındaki her şey
`slugify`'dan geçiriliyor. Sonuç iki durumda da yalnız `[A-Za-z0-9_]` içeriyor.

Ad koşuya göre değiştiği için, daha önce dışa aktarılmış bir koşu yeniden aktarıldığında
eski docx artifact'i geride kalır ve koşu iki Word raporlu görünürdü. Aynı fonksiyondaki
mevcut bayat-figür temizliği (`17[a-z]_source_figure_.*\.png`) ikinci bir desenle
genişletildi; ayrı bir mekanizma kurulmadı.

Kapsam yalnız Word raporu: `02_full_research_report.md` ve diğer çıktılar adlarını koruyor.
Etiketin benzersiz olmaması bilinçli bir karardır (`schemas.py`: *"two runs on one topic
share a label, so it never replaces the id"*); aynı konudaki iki koşu aynı dosya adını
üretir. Depolamada sorun değil, anahtar `runs/{run_id}/` ile ayrışıyor.

Değişen dosyalarda hedefli Ruff temizdir ve mevcut ihlaller artmadı. Adlandırma kuralı altı
birim testiyle korunuyor; bunlardan biri düşmanca etiketin (`../../etc/passwd`, `a/b`, `..`)
ad'a sızmadığını doğruluyor. Son kod değişikliğinden sonraki zorunlu tam kapı
`516 passed, 2 warnings` sonucuyla tamamlandı.

---

## 48. Yapısal çıkarımlarda kaynağı bulan connector

`18_structured_extracts.json` her kayıtta metni okuyan parser'ı (`parser_id`) yazıyordu ama
kaynağı bulan connector'ı yazmıyordu. Dosya denetlenmiş kanıt değil, parser çıktısının ham
hâli — bozuk bir hücre bozuk kaydediliyor — dolayısıyla yanlış görünen bir tablonun izini
sürmek için "bunu kim getirdi, kim okudu" ikilisinin ikisine de ihtiyaç var. Kayıtlara
`connector_id` eklendi.

Ek sorgu gerekmedi: dışa aktarım zaten `list_source_versions`'ın döndürdüğü
`(SourceRow, SourceVersionRow)` çiftleri üzerinde yürüyor ve `SourceRow.connector_id` o
satırda duruyor.

Kayıt üretimi `export_run` içinde gömülü bir liste kavrayışıydı ve bu artifact'in hiç testi
yoktu. Mantık `structured_extract_rows()` fonksiyonuna çıkarıldı; davranış değişmedi, yalnız
test edilebilir hâle geldi. Üç test eklendi: kaydın connector ve parser'ı birlikte adlandırdığı,
yapısal içerik bulunmayan kaynağın boş kayıtla taşınmak yerine tamamen dışarıda bırakıldığı ve
provenance'ı hiç olmayan eski bir sürümün hata vermediği.

Gerçek veriyle doğrulandı: `01M0YJH3CWTHD40BE171AWNTGS` koşusunun 36 kaydı, 104 tablosu ve 13
kod bloğu değişmeden üretildi, `connector_id` alanı `agentsearch_web` 18, `arxiv` 12,
`openalex` 4, `crossref` 2 dağılımıyla doldu. Son kod değişikliğinden sonraki zorunlu tam kapı
`519 passed, 2 warnings` sonucuyla tamamlandı; hedefli Ruff temiz.

**Geriye dönük değil.** Alan yalnız bundan sonra dışa aktarılan koşularda görünür; mevcut
artifact'ler yeniden üretilmiyor.

---

## 49. Düşen koşunun sahibine Telegram bildirimi

Bir koşu `failed` olduğunda kimse haber almıyordu; koşuyu başlatan kişi ya paneli açıp
bakıyor ya da saatler sonra fark ediyordu. Oysa hata metinleri eyleme dönük bilgi taşıyor:
`PipelineStageTimeout: ACQUIRE exceeded its 900 second safety limit` ve
`GraphRecursionError: Recursion limit of 380 reached...`.

Boşluk kodda görünürdü. Bot'un yoklama döngüsü koşuları zaten izliyordu ama terminal duruma
gelen koşuyu **sessizce izleme listesinden çıkarıyordu** — `failed` dâhil, tek kelime
etmeden.

**Neden mevcut izleme listesi kullanılmadı.** `watched_runs` bellekte tutuluyor ve yalnız
bot üzerinden başlatılan koşular oraya giriyor. MCP, API veya kontrol panelinden başlatılan
koşular hiç izlenmiyor, bot yeniden başlarsa liste de kayboluyordu. Bildirim bu yüzden
sahiplik üzerinden kuruldu: her koşunun `owner_id`'si var ve `telegram_ids_for` bunu
sohbetlere çeviriyor. Böylece hangi kapıdan başlatılmış olursa olsun sahibine ulaşıyor.

**Bir kez duyurulması** `telegram_failure_notified` adlı olağan bir koşu olayıyla sağlanıyor;
sütun veya göç gerektirmiyor ve bot yeniden başlasa da kimseye iki kez söylenmiyor. İşaret,
**gönderim olmasa bile** yazılıyor: sahibinin bağlı Telegram'ı yoksa liste boş döner ve
işaret yazılmazsa aynı koşu her yoklama turunda yeniden denenirdi. Ulaşılamayan sahip
loglanıyor.

**Pencere.** `TELEGRAM_FAILURE_NOTICE_WINDOW_H` (varsayılan 24 saat) hem sorguyu sınırlıyor
hem de "yalnız bundan sonrakiler" kararını ayrı bir tohumlama adımı olmadan sağlıyor:
özellik açıldığında 24 Ağustos'ta düşmüş iki koşu pencerenin dışında kalıp sessizleşiyor,
ama bot bir süre kapalı kalırsa o aralıkta düşen koşu hâlâ yakalanıyor — sabit bir "açılış
anı" damgasının kaybedeceği şey buydu. `list_runs_by_statuses` zaman filtresi taşımadığı ve
bugüne kadarki bütün hataları döndüreceği için yanına aynı admin muhafazasını taşıyan
`list_failed_runs_since` eklendi.

Yalnız `failed` bildiriliyor. `cancelled` kullanıcının kendi iptali; `completed_incomplete`
ise 17 koşunun 13'ü ve bir kapsam teşhisi, arıza değil — bildirim göndermek bildirimlerin
ciddiye alınmamasına yol açardı.

Çağrı, mevcut plan bildiriminin yanına **kendi ayrı `try/except`'i** içinde konuldu; biri
patlarsa diğeri ve komut döngüsü ayakta kalmalı. Gecikme uzun yoklama turu kadar, en fazla
bir dakika.

Beş test eklendi; ikisi kazayla bozulması kolay olan garantileri sabitliyor: bir koşunun iki
kez duyurulmaması ve pencereden eski bir hatanın hiç duyurulmaması.

**Doğrulama.** Canlı veritabanında mesaj göndermeden çalıştırıldığında 0 bildirim üretti —
eski iki hata pencere dışında kaldı ve hiçbir işaret yazılmadı. Ardından tek kullanımlık bir
`failed` koşu üretilip gerçek bildirim gönderildi (`chat_count: 1`), ikinci turda
tekrarlamadığı doğrulandı, sonra o koşu ve olayı silindi; mevcut 17 koşuya dokunulmadı. Son
kod değişikliğinden sonraki zorunlu tam kapı `524 passed, 2 warnings` sonucuyla tamamlandı,
hedefli Ruff dört dosyada da temiz.

**Kapsamda olmayan.** Sunucu çökmesi veya elektrik kesintisi bildirimi bilinçli olarak
ertelendi. Aynı makinede çalışan hiçbir bileşen kendi ölümünü haber veremez; bu ancak makine
dışı bir izleyiciyle mümkün ve izleyicinin nerede yaşayacağı donanım kararıdır.

---

## Bilinen açık işler

Tek liste hâlinde [OPEN_ITEMS.md](OPEN_ITEMS.md) dosyasında tutuluyor: öncelik tablosu, her
madde için ölçümler ve yapılacak iş. Bu raporda bölüm bölüm dağılmış "bilinen sınır"
notlarının toplandığı yer orası; yeni bir sınır tespit edildiğinde oraya eklenmeli.

Bu bölümü burada çoğaltmıyoruz — iki listenin zamanla birbirinden ayrışması kaçınılmazdı.
