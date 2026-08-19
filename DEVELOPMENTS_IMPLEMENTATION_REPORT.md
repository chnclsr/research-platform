# `developments` Branch Değişiklik Raporu

Platform sürümü: `v0.10.0`

Belge sürümü: `12.1`

Son güncelleme: `2026-08-19`

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
| 7 | Teslimat izin hatası ve koşu bazında yerel yedekleme | `7caa407` |
| 8 | Parser mimarisinin servisleştirilmesi | `a58874a` |
| 9 | Parser seçim kararı: deterministik + açık override | `ec88283` |
| 10 | Word raporunda kaynak çapraz referansları | `63b74ed` |
| 11 | Kullanıcı kimliği ve koşu sahipliği (kendi raporu var) | `3f9a191` … `84cddde` |
| 12 | Panelden parola değiştirme | `fc3199d` |
| 13 | Ekip kuyruğunun sansürlü görünürlüğü | `fc3199d` |
| 14 | MCP'de kişisel kimlik | `d88a32a` |
| 15 | Aşama başına araç dökümü (panel) | commit bekliyor |
| 16 | İkili içerik ve NUL baytı koşuyu düşürüyordu | commit bekliyor |

> **Not:** 2. bölümdeki düzeltmenin yetersiz olduğu sonradan anlaşıldı. Gerekçe ve asıl
> çözüm 5. bölümdedir.
>
> **Not:** 13. bölüm, 11. bölümdeki izolasyon kararını bilinçli olarak gevşetir —
> hangi yönüyle olduğu o bölümde tablo hâlinde yazılıdır.

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
**[reports/MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md](reports/MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md)**.

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

`reports/MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md` "kullanıcı yalnız kendi
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

## Bilinen açık işler

Tek liste hâlinde [OPEN_ITEMS.md](OPEN_ITEMS.md) dosyasında tutuluyor: öncelik tablosu, her
madde için ölçümler ve yapılacak iş. Bu raporda bölüm bölüm dağılmış "bilinen sınır"
notlarının toplandığı yer orası; yeni bir sınır tespit edildiğinde oraya eklenmeli.

Bu bölümü burada çoğaltmıyoruz — iki listenin zamanla birbirinden ayrışması kaçınılmazdı.
