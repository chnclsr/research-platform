# `developments` Branch Değişiklik Raporu

Platform sürümü: `v0.9.1`

Belge sürümü: `5.0`

Son güncelleme: `2026-08-13`

## Kapsam

Bu belge `developments` branch'inde yapılan tüm değişiklikleri tutar. Yeni iş yapıldıkça
yeni bölüm olarak buraya eklenir; ayrı rapor dosyası açılmaz.

| # | İş | Commit |
|---|---|---|
| 1 | AgentSearch adaptörü | `fdbfbff` |
| 2 | NORMALIZE checkpoint boyut hatası | `5f0ac23` |
| 3 | Adaptörün compose'a taşınması | `09ea1b6` |
| 4 | Kontrol panelinin Docker uyumluluğu | `8bc484c` |
| 5 | Checkpoint temizleme ve boyut koruması | `d55455d` |
| 6 | MinIO verisinin bind mount'a taşınması | `c5408de` |

> **Not:** 2. bölümdeki düzeltmenin yetersiz olduğu sonradan anlaşıldı. Gerekçe ve asıl
> çözüm 5. bölümdedir.

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

## Bilinen açık işler

**Resume sonrası ham veri.** 5. bölümün sonundaki sınır: NORMALIZE checkpoint'inden devam
ettirilen koşular ham gövdeyi kaybeder ve o koşuda PDF figür analizi çalışmaz.

**`source_versions.raw_content` kopyası.** Ham gövde hem MinIO'da hem bu TEXT sütununda
duruyor. Sınır aşımı yaratmaz (TEXT 1 GB'a kadar, TOAST sıkıştırır) ama `postgres-data`
volume'ünü gereksiz büyütür. Dışa aktarım bu sütunu okuduğu için kaldırmak, `13_raw_sources`
üretimini MinIO'dan okuyacak şekilde değiştirmeyi gerektirir.

**MinIO anahtar düzeni tutarsız.** Kaynak snapshot'ları `{run_id}/sources/...` altında,
figür ve export çıktıları `runs/{run_id}/...` altında. Tek bir önek altında toplanmalı.
