# `.env` Yönetimli Uygulama Yapılandırması — v0.15.0

Platform sürümü: `v0.15.0`

Belge sürümü: `1.1`

Tarih: `2026-08-25`

## Amaç ve kapsam

Uygulama davranışını değiştirmek için kaynak kod düzenleme ve image üretme gerektiren,
dağıtıma bağlı sabitler tarandı. Amaç fallback mekanizmalarını kaldırmak değil; fallback
değerlerini korurken çalışan kurulumun bütün seçili davranış değerlerini `.env` üzerinden
yönetebilmesidir.

Bu sürüm güvenlik/kapasite, worker/veritabanı/kuyruk, donanım telemetrisi, API/istemci ve
pipeline çalışma bütçilerini kapsar. Connector'a özgü yapılandırmalar, Telegram davranışı
ve Docker/Compose/Dockerfile değerleri bilinçli olarak kapsam dışındadır.

## Korunan değerler ve yeni çevre anahtarları

Kaynak koddaki mevcut değerlerin tamamı gerçek `.env` dosyasına ve paylaşılabilir
`.env.example` şablonuna aynı değerlerle taşındı.

| Alan | Çevre anahtarları | Korunan değerler |
|---|---|---|
| Giriş güvenliği | `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` | `8`, `300` sn |
| Kapasite/model | `CAPACITY_ABSOLUTE_GUARD`, `CAPACITY_PROBE_TIMEOUT_S`, `MODEL_MAX_CONCURRENT_CALLS` | `8`, `5` sn, `1` |
| Checkpoint | `CHECKPOINT_MAX_BYTES` | `209715200` bayt |
| Worker HTTP/ARQ | `HTTP_TRANSPORT_RETRIES`, `WORKER_JOB_TIMEOUT_S`, `WORKER_KEEP_RESULT_S`, `WORKER_HEALTH_CHECK_INTERVAL_S` | `3`, `86400`, `60`, `30` sn |
| Veritabanı havuzu | `DB_POOL_MIN_SIZE`, `DB_POOL_PER_RUN`, `DB_OVERFLOW_MIN_SIZE`, `DB_OVERFLOW_PER_RUN` | `10`, `5`, `10`, `3` |
| Öncelik kuyruğu | `QUEUE_PRIORITY_SHIFT_DAYS`, `QUEUE_JOB_EXPIRY_S` | `3650` gün, `86400` sn |
| Telemetri | `HARDWARE_TELEMETRY_FLUSH_S`, `HARDWARE_TELEMETRY_MAX_BUFFERED_SAMPLES` | `60` sn, `720` örnek |
| Redis bağlantısı | `REDIS_STARTUP_CONNECT_ATTEMPTS`, `REDIS_OPERATION_CONNECT_ATTEMPTS`, `REDIS_PROBE_CONNECT_ATTEMPTS`, `REDIS_CONNECT_DELAY_S` | `30`, `3`, `1`, `1` sn |
| Servis/gateway | `SERVICE_HEALTH_TIMEOUT_S`, `GATEWAY_CLIENT_TIMEOUT_S`, `GATEWAY_ARTIFACT_MAX_CHARS` | `3` sn, `60` sn, `100000` karakter |
| Embedding | `EMBEDDING_BATCH_SIZE`, `EMBEDDING_TIMEOUT_S` | `32`, `180` sn |
| Edinim istemcileri | `ACQUISITION_MAX_REDIRECTS`, `AGENTSEARCH_READ_MAX_CHARS`, `CRAWL4AI_TIMEOUT_S` | `5`, `100000`, `90` sn |
| Pipeline paralelliği | `SEARCH_CONCURRENCY`, `EVIDENCE_EXTRACTION_CONCURRENCY` | `8`, `2` |
| Citation/relevance | `CITATION_SEED_MIN`, `CITATION_SEED_MAX`, `RELEVANCE_RETRY_ATTEMPTS` | `4`, `12`, `2` |
| LangGraph | `GRAPH_RECURSION_MIN`, `GRAPH_RECURSION_MAX`, `GRAPH_RECURSION_PER_WALL_MINUTE` | `80`, `5000`, `20` |
| Tur başına kaynak | `FIRST_ROUND_SOURCE_FRACTION`, `LATER_ROUND_SOURCE_FRACTION` | `0.40`, `0.30` |

`Settings` içindeki tip ve aralık doğrulamaları korunmuştur. Bir anahtar `.env` içinde
bulunmazsa kod varsayılanı önceki davranışı sürdürür; geçersiz değer ise süreç başlarken
Pydantic doğrulamasıyla görünür biçimde reddedilir.

## Daha önce etkisiz olan iki anahtar

`ACQUISITION_CONCURRENCY` ve `FRONTIER_MAX_DEPTH` ayar modelinde bulunmasına rağmen yeni
koşuların protokol varsayılanlarını belirlemiyordu. `ResearchBudget.acquisition_concurrency`
doğrudan `4`, `ConnectorSelection.citation_depth` doğrudan `1` kullanıyordu.

Yeni protokol oluşturulurken varsayılanlar artık sırasıyla:

- `ACQUISITION_CONCURRENCY=4`,
- `FRONTIER_MAX_DEPTH=2`

değerlerinden okunur. İstemci protokol içinde açık bir değer gönderirse Pydantic'in olağan
önceliği nedeniyle o koşu-bazlı değer kullanılmaya devam eder. Böylece `.env` kurulum
varsayılanını, protokol ise tek koşunun bilinçli istisnasını temsil eder.

## Mimari notlar

- Redis bağlantısındaki üç farklı deneme sayısı tek değerde birleştirilmedi. API açılışı
  servislerin gelmesini beklemek için `30`, olağan mutasyonlar `3`, sağlık/probe yolları
  `1` deneme kullanmaya devam eder.
- Veritabanı havuzu donanımdan hesaplanan koşu tavanıyla büyür; taban değerleri ve koşu
  başına çarpanlar artık ayrı ayrı ayarlanabilir.
- Queue sabitleri modül yüklenirken, ARQ worker sınıf değerleri worker süreci kurulurken
  okunur. Bu anahtarların değişmesi çalışan süreci kendiliğinden mutasyona uğratmaz;
  olağan image/container yeniden başlatması gerekir.
- Gateway artifact limiti istemciye açık `max_chars` verilmediğinde uygulanır; açık araç
  parametresi tek çağrı için üstün gelmeye devam eder.

## Güvenli dağıtım ve doğrulama

Kaynak kod image içine kopyalandığı için canlıya alma `docker compose up -d --build` ile
yapılır. Çalışan araştırmaların checkpoint sınırında duraklatılması, worker yeniden
oluşturulduktan sonra kaldıkları checkpoint'ten devam ettirilmesi gerekir. Bu çalışmada
yerel düzenleme ve testler mevcut konteynerlere dokunmadan yürütülmüştür.

Doğrulama kapıları:

- yeni `.env` bağlantıları için hedefli birim testleri,
- etkilenen API, pipeline, gateway, kapasite, kuyruk ve telemetri testleri,
- değişen Python satırlarında hedefli Ruff,
- son kod değişikliğinden sonra `$env:TESTING="true"` ile tam `python -m pytest -q`,
- yeniden oluşturulan konteynerlerde sağlık denetimi ve 15 dakikalık gerçek araştırma
  koşusu.

### Gerçek koşu sonuçları

#### Kısa smoke

- Koşu: `01M0WMG07FQ92SV14NC7S63XB0`
- Protokol bütçesi: `max_wall_minutes=15`
- `.env` varsayılanlarının kalıcı protokol kaydı: `acquisition_concurrency=4`,
  `citation_depth=2`
- Son durum: `completed_incomplete`, `COMPLETE`; uygulama hatası yok
- Çıktı: `0` kaynak, `0` iddia, `25` artifact

Arama ve acquisition çalıştı; event kaydında doğrudan, Crawl4AI ve Scrapling üzerinden
başarıyla edinilmiş adaylar vardır. Ancak adaylar soruyla ilgili bulunmadığı için relevance
kapısından sonra kalıcı kaynak kalmadı. Koşu teknik olarak terminal duruma ve export'a
ulaşsa da sıfır kaynaklı sonuç yayın kapısı için başarılı kabul edilmedi.

#### 15 dakikalık exhaustive koşu

- Koşu: `01M0WMZZQMQ81VHMNXM70MDEN5`
- Protokol: `literature_scan`, `max_wall_minutes=15`,
  `exhaustive_until_budget=true`, kaynak üst sınırı yok
- `.env` varsayılanlarının kalıcı protokol kaydı: `acquisition_concurrency=4`,
  `citation_depth=2`
- 15 dakikalık wall-clock eşiği aşıldı; koşu yarıda kesilmeden güvenli `NORMALIZE`
  aşamasını tamamlamaya devam etti ve uygulama hatası üretmedi.

Kullanıcı, uzun normalize işleminin devam etmesini sorun olarak görmediğini belirterek
remote eşitliği, test, commit ve push talimatı verdi. Yayın kapısı bu açık kabul ve aşağıdaki
tam test sonucu üzerinden açıldı; koşu worker üzerinde çalışmaya devam ederken commit
işlemi araştırma durumuna veya checkpoint'ine dokunmadı.

Yerel hedefli paket `96 passed`, commit öncesi son zorunlu tam paket ise
`481 passed, 2 warnings` sonucunu verdi. Uyarılar mevcut Starlette/httpx geçişi ve Pydantic
settings forward-reference uyarısıdır. Git fetch sonrasında yerel `HEAD` ile
`origin/developments-supplementer` ileri/geri sayımı `0 / 0` olarak doğrulandı.

Canlı dağıtımda API, worker ve MCP gateway yeniden oluşturuldu; container içi sürüm
`0.15.0`, API sağlığı `healthy`, Docling `ok (cuda)` olarak doğrulandı. Telegram container'ı
bilinçli olarak yeniden oluşturulmadı. Host kontrol paneli yerel editable paket
`0.15.0` olarak yenilenip `.env.office` içindeki 1111 portunda sağlıklı başlatıldı.

Dağıtım öncesinde çalışan iki koşu API üzerinden duraklatıldı. İkisinin de kalıcı
checkpoint'i doğrulandı; yeni worker başladıktan sonra aynı kimliklerle yeniden kuyruğa
alınıp çalışma durumuna döndükleri görüldü.
