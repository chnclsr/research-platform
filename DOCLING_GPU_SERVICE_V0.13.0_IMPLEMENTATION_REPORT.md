# Ağır PDF Yolu: Docling'in GPU'lu Servis Olarak Ayrılması

Platform sürümü: `v0.13.0`

Belge sürümü: `1.1`

Tarih: `2026-08-24`

## Gerekçe

`SmartPdfParser` PDF sayfalarını inceleyip yalnız gerekenleri ağır bir motora (Docling)
yolluyor. Yönlendirme çalışıyordu; **ağır motorun kendisi hiçbir yerde koşmuyordu.**

Ölçüm, bu kurulumun MinIO'sundaki gerçek koşu PDF'leri üzerinde alındı — 12 belge,
372 sayfa:

| | docling yok | docling var (köprülü, CPU) |
|---|---|---|
| ağır yönlendirilen sayfa | 138 (%37) | 138 (%37) |
| ağır motorca üretilen | **0** | **138 / 138** |
| kurtarılan tablo | 0 | **120** |
| toplam metin | 1.273.050 karakter | **1.436.106** (+%12,8) |
| `degraded` belge | 12 / 12 | **0 / 12** |
| süre | 8,3 sn | 671,4 sn |

Yani docling'siz bir koşu "smart_pdf ile tamamlandı" diyor, provenance'a 138 kaçırılmış
sayfa yazıyor ve pratikte `pymupdf_fast`'ten tek farkı yönlendirme kaydını tutmak oluyor.

Üç somut engel vardı:

1. **Docling'e ulaşmanın iki yolu vardı, ikisi de kapsayıcıdan çıkamıyordu.** Aynı süreçte
   `import docling` ya da `subprocess.run` ile **yerel** bir yorumlayıcı. Uygulama imajı
   ise docling taşımıyor: `Dockerfile` `pip install .` çalıştırıyor, docling `[parsing]`
   ekstrasında. Üstelik `api`, `worker`, `mcp-gateway` ve `telegram-bot` compose'daki
   `*app` çıpasıyla **aynı imajı** paylaşıyor — torch'u oraya koymak dört servisi birden
   şişirirdi.
2. **Sürenin %43'ü işe hazırlanmakla geçiyordu.** Köprülü modda belge başına ~24 sn süreç
   başlatma + model yükleme; 12 belgede ~288 sn. Kalıcı bir servis bunu bir kez öder.
3. **Cihaz tespit ediliyordu, garanti edilmiyordu.** `_docling_worker.cihaz()`
   `decide_device(AcceleratorDevice.AUTO)` çağırıyordu. Deponun kendi ölçümü
   ([research/pdf-parser/results/gpu/README.md](research/pdf-parser/results/gpu/README.md))
   CPU↔GPU eşdeğerliğinin **geçmediğini** söylüyor: 261 sayfanın 7'si farklı, biri bir
   markdown tablosunu tamamen kaybediyor. `content_hash` bu metnin sha256'sı olduğundan,
   sessiz bir CPU'ya düşüş her belgenin kimliğini değiştirir.

## Kararlar

Kullanıcı onayıyla alınan üç karar:

1. **Ayrı servis** (worker imajına gömmek değil). Ağır imaj tek serviste kalır, modeller
   yerleşik durur, zaman aşımı gerçekten uygulanabilir ve GPU'yu tek bir kapsayıcı
   rezerve eder.
2. **Profil değil, overlay dosyası.** Sistem hem GPU'lu hem GPU'suz makinede çalışmalı.
3. **In-process yol açık opt-in'e çevrildi.**

## Cihaz bir dağıtım parametresidir, tespit değil

CPU ve GPU çıktısı aynı değil ve bunu "düzeltmek" mümkün değil. Reproducibility bu yüzden
şöyle tanımlandı: **kaydedilmiş cihaz ve build verildiğinde çıktı tekrarlanabilirdir.**

Bu tanımın GPU tarafı zaten ölçülmüş: `gpu_docling_cuda_step3_determinizm.json`, aynı
belgeyi CUDA'da 3 kez koşturup üç çıktının da `0f51d4ac...` olduğunu gösteriyor
(`hepsi_ayni: true`).

Uygulama sonuçları:

- Servis `DOCLING_DEVICE` ile **açıkça** yapılandırılır. `cuda` istenmiş ama CUDA yoksa
  servis **başlamaz** — sessizce CPU'ya düşmez.
- Hangi cihazın ve hangi build'in ürettiği belge başına provenance'a yazılır.
  `engine_devices` zaten vardı; `engine_build` bu işte eklendi. Gerekçe: cihaz tek başına
  çıktıyı sabitlemiyor — aynı kartta bir docling yükseltmesi metni değiştirir.

## GPU'lu ve GPU'suz makine

Profil (`--profile docling`) kullanılmadı: AGENTS.md'de yazılı `telegram-bot` tuzağının
aynısını üretirdi — düz `docker compose up -d --build` servise dokunmaz, servis eski
imajla ayakta kalır ve hata vermediği için fark edilmez.

Bunun yerine:

- `docker-compose.yml` `docling` servisini **CPU varsayılanıyla** tanımlar. GPU
  rezervasyonu yoktur; her makinede ayağa kalkar.
- `docker-compose.gpu.yml` yalnız üç şeyi ekler: `TORCH_VARIANT=cu132`,
  `DOCLING_DEVICE=cuda`, ve `deploy.resources.reservations.devices`.
- GPU'lu makinede `.env`'e **iki** satır konur:

  ```
  COMPOSE_PATH_SEPARATOR=:
  COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
  ```

  İkisi de gerekli. `COMPOSE_FILE`'ın ayracı Windows'ta `;`, diğerlerinde `:`; tek satır
  `:` ile yazılırsa Windows'ta *"cannot find the file docker-compose.yml:docker-compose.gpu.yml"*
  hatası verir (2026-08-21'de doğrulandı). Ayracı açıkça yazmak aynı iki satırı iki
  platformda da çalıştırır.

  Compose `COMPOSE_FILE`'ı proje `.env`'inden okuduğu için **her zamanki komutlar**
  (`docker compose up -d --build`, `ps`, `logs`) overlay'i kendiliğinden kapsar.
  Hatırlanması gereken bir `-f`, unutulacak bir `-f`'tir — ve unutulduğunda hata sessiz
  olurdu: servis CPU'da geri gelir ve sessizce farklı metin üretir.

Bu makinede GPU geçişi doğrulandı: `nvidia-container-runtime` kayıtlı,
`docker run --rm --gpus all python:3.12-slim nvidia-smi` RTX 4060'ı gösteriyor
(8188 MiB, sürücü 595.79, CUDA 13.2).

## CPU'lu makinede ne olur

CPU'da koşmak **fallback değildir**, beyan edilmiş bir cihaz seçimidir: servis ayaktadır,
ağır yol çalışır, sayfalar üretilir, tablolar kurtarılır, belge `degraded` olmaz.

Fallback bundan ayrı bir emniyet ağıdır ve iki makinede de aynıdır: motor ulaşılamaz,
hata verir ya da zaman aşımına uğrarsa sayfa hızlı yol metnini korur, `fell_back`
işaretlenir, `notes` sebebi söyler. Sayfa hiçbir durumda kaybolmaz.

**Ama CPU dağıtımı GPU'nunkiyle aynı bütçelerle koşamaz.** 671,4 sn'nin ~288 sn'si
belge başına başlatma maliyetiydi; kalıcı servis onu sıfırlıyor ve gerçek ağır iş
~383 sn'ye iniyor — `ACQUISITION_STAGE_TIMEOUT_S=900`'e sığar. Sıkışan yer kuyruk:
eski sabit `KUYRUK_BEKLEME_SN=300` ile 383 sn'lik seri işte sona kalan belgeler yuva
bulamaz ve `queue-timeout` ile degraded döner. Metin PDF'inde bu kazanç kaybıdır;
**taranmış** PDF'te hızlı yol metni yok denecek kadar az olduğu için belge acquisition'ın
400 karakter kapısında düşer.

Bu yüzden iki bütçe cihaza bağlandı. Sabit sayı olarak kalıyorlar — `engines.py`'nin
determinizm notu ("yükten, kuyruk derinliğinden ya da bütçeden türetilmez") korunuyor;
cihaz gibi bunlar da dağıtım parametresi:

| Değişken | CPU | GPU | Ne |
|---|---|---|---|
| `SMART_ROUTER_QUEUE_WAIT_S` | 900 | 300 | Belgenin yuva için bekleyeceği süre |
| `SMART_ROUTER_HEAVY_TIMEOUT_S` | 1800 | 900 | Tek belgenin ağır yolda harcayabileceği süre |

Değerleri compose veriyor: base dosya CPU'yu, overlay GPU'yu. Elle ayar gerekmez.
Yalnız `worker`'a konuyor, çünkü ağır motoru çağıran tek servis o.

## Değişiklikler

### Yeni: `docling` servisi

| Dosya | Ne |
|---|---|
| `Dockerfile.docling` | `python:3.12-slim` + `ARG TORCH_VARIANT` ile torch, sonra sabitlenmiş docling; ağırlıklar build'de imaja iniyor |
| `docker/docling-requirements.txt` | Çıktıyı belirleyen paketlerin tam sabitlemesi |
| `scripts/docling_service.py` | FastAPI + uvicorn; `POST /extract`, `GET /health` |
| `docker-compose.yml` → `docling` | CPU varsayılanı, sağlık kontrolü, 3941 |
| `docker-compose.gpu.yml` | CUDA yapısı, cihaz beyanı, kart rezervasyonu |

Servisin sözleşmesi `_docling_worker.run()`'ın bugünkü JSON çıktısının aynısı
(`{"pages", "tables", "device", "build"}`), böylece HTTP ve köprülü yollar istemci
tarafında **aynı kodla** ayrıştırılıyor. `_table_grid()` yeniden yazılmadı; servis
`_docling_worker`'ı içe aktarıyor — o modül zaten paketten bağımsız çalışacak şekilde
yazılmıştı (`_bridged`'in "invoked by file path, not `-m`" notu).

Üç uygulama kararı:

- **`DocumentConverter` modül düzeyinde bir kez** kuruluyor ve
  `AcceleratorOptions(device=...)` ile cihaz zorlanıyor. Açılışta
  `initialize_pipeline(InputFormat.PDF)` çağrılıyor: modeller ilk isteği bekletmesin.
- **Sunucu tarafında `threading.BoundedSemaphore(1)`.** Tek kart, tek dönüştürme. Gerçek
  sınır burası; istemci tarafındaki `_AGIR_KAPI` sırt basıncı.
- **`/extract` senkron uç.** uvicorn onu bir iş parçacığında koşturuyor, böylece semaforda
  beklemek olay döngüsünü değil o iş parçacığını tutuyor ve dönüştürme sürerken
  `/health` cevap vermeye devam ediyor.
- **Ağırlıklar imajda**, `HF_HUB_OFFLINE=1` ile. Aksi hâlde ilk dönüştürme ~0,5 GB'ı hiçbir
  şeyin kalıcılaştırmadığı bir katmana indirirdi: her kapsayıcı yeniden oluşturmada
  yeniden inerdi ve o gün HuggingFace ne sunuyorsa koşu onu alırdı.

### `engines.py` — üçüncü mod

- Yeni `HttpDoclingEngine`. Adı bilerek `docling` değil **`docling-service`**: provenance
  motor sayımlarını ve cihazlarını isme göre tutuyor, `_run_heavy_pages` de `requested`
  haritasını isimle anahtarlıyor — bir belge için hem servis hem yerel motor koşarsa
  ikisinin ayırt edilebilir kalması gerekiyor.
- `/health` yoklaması 30 sn önbellekleniyor; belge başına bir tur atmamak için.
- PDF baytları HTTP ile gidiyor, paylaşılan volume yok: worker zaten PDF'i kendi geçici
  dosyasına döküyor (`smart_pdf._spill_to_disk`) ve bir mount iki kapsayıcının dosya
  sistemlerini boşuna birbirine bağlardı.
- `EngineResult.build` eklendi ve her iki yerel yol da taşıyor
  (`_docling_worker.yapi()`).
- `ENGINE_VERSION` → `engines_v2_2026-08-21`.

### `smart_pdf.py` — tek sıralama

`_heavy_engines()` motor sırasını **tek yerde** tutuyor: `HttpDoclingEngine` →
`DoclingEngine` → `MinerUEngine`. Hem `available()` hem `_run_heavy_pages` onu okuyor.
Ne yaptığıyla uyuşmayan bir health satırı, hiç health olmamasından kötüdür.

`available()` artık ağır yol yokken **her üç gerekçeyi birden** yazıyor; eskiden yalnız
sonuncusu görünüyordu.

### `capacity.py` — docling'in VRAM'i planlayıcıya görünür

Bu makinedeki en keskin risk. v0.12.0 GPU'yu `model_lease()` ile tek sıraya sokuyor ve
`_gpu_slots()` yalnız **Ollama'nın** yerleşik VRAM'ini ölçüyor. GPU'lu bir docling servisi
o kuyruğu baypas eden **ikinci bir GPU tüketicisi**: 8 GB'lık kartta planlayıcı paralel
koşulara yeşil ışık yakarken docling 1-2 GB tutuyor olabilir.

Çözüm kilitleme değil, rezervasyon: `docling_vram_reserve_gb` ayarı headroom hesabından
düşülüyor.

`model_lease()`'e sokmak **reddedildi**: `parse()` bir worker iş parçacığında koşuyor,
`model_lease()` ise asyncio semaforu — iş parçacığından güvenle beklenemez, ve bir koşunun
acquisition'ı ile diğerinin LLM aşamasını gereksizce karşılıklı dışlardı (paralel
koşuların bütün amacı o örtüşme). Servis modelleri yerleşik tuttuğu için VRAM'i bir sabit,
bir tepe değil — düz rezervasyon dürüst model.

**Varsayılan 0,0.** Ölçülmeden konmamalı; tahmin edilen bir rezervasyon ya kartı boşa
harcar ya da korumaz.

### `api.py` — `/health`

`checks["docling"]` eklendi ve değeri cihazı taşıyor (`ok (cuda)`). `unconfigured`
kasıtlı bir dağıtımdır, arıza değil.

## Bilinçli olarak değiştirilen eski kararlar

AGENTS.md gereği açıkça yazılıyor:

| Nerede | Eski karar | Yeni | Neden |
|---|---|---|---|
| `engines.py` modül docstring'i | "Docling'e ulaşmanın **iki** yolu" | üç yol, servis ilk | Kapsayıcıdan çıkabilen tek yol |
| `DoclingEngine.available()` | in-process **ilk** tercih | in-process **son** ve opt-in | Yalnız köprülü yol zaman aşımına uğratılabiliyor |
| `available()`/`extract()` | modu **ayrı ayrı** çözüyorlardı | tek `_mode()` | İkisi aynı çağrı için farklı mod söyleyebiliyordu |
| `KUYRUK_BEKLEME_SN`, `VARSAYILAN_ZAMAN_ASIMI_SN` | kodda sabit | ortamdan, cihaza göre | Tek sayı CPU ve GPU'ya birden hizmet edemiyor |

In-process yolun neden opt-in'e çevrildiği: `_bridged` `timeout_s` uyguluyor, `_in_process`
uygulamıyor. `parse()` `asyncio.to_thread` ile bir iş parçacığında koşuyor;
`ACQUISITION_STAGE_TIMEOUT_S` dolduğunda pipeline coroutine'i iptal ediyor ama **iş
parçacığı iptal edilemiyor** — docling koşmaya devam ediyor ve tek olan `_AGIR_KAPI`
yuvasını tutmayı sürdürüyor. Bugün docling uygulama imajında olmadığı için bu yola
girilmiyor; yarın biri `[parsing]` ekstrasını imaja koyduğu anda kimse seçmeden
erişilebilir hâle gelirdi.

## Bilinen sınırlar

- **CPU'lu ve GPU'lu makine aynı PDF'ten farklı `content_hash` üretir.** Kaçınılmaz
  (ölçüldü: 261 sayfanın 7'si). Gizlenmiyor, provenance'a yazılıyor. Aynı belgenin iki
  makinede iki `SourceVersion` satırı olur.
- **`docker/docling-requirements.txt` tam bir kilit değil.** Çıktıyı belirleyen paketler
  tam sabitli; kalan geçişli bağımlılıklar build anında çözülüyor. Linux kilidi kurulan
  imajdan üretilmeli (dosyanın sonundaki not) — tahmin edilerek değil.
- **8 GB VRAM Ollama ile paylaşılıyor.** `docling_vram_reserve_gb` ölçülene kadar 0,0.
- **RC1 ölçümleri docling 2.120.3 ile alınmıştı**, sabitlenen sürüm 2.121.0.

## Ölçümler

Hepsi bu kurulumun MinIO'sundaki 12 gerçek koşu PDF'i üzerinde, 372 sayfa.
Ham sayılar: `research-platform-docling:latest`, RTX 4060 Laptop, CUDA 13.2,
torch 2.13.0+cu132, docling 2.121.0.

### Ağır yolun üç hâli

| | motor yok | köprülü, CPU | **servis, CUDA** |
|---|---|---|---|
| ağır yönlendirilen | 138 | 138 | 138 |
| ağır motorca üretilen | **0** | 138 | **138** |
| kurtarılan tablo | 0 | 120 | 117 |
| toplam metin | 1.273.050 | 1.436.106 | 1.436.550 |
| `degraded` belge | 12 / 12 | 0 / 12 | **0 / 12** |
| süre | 8,3 sn | 671,4 sn | **285,8 sn** |
| en yavaş tek belge | — | 130,9 sn | 79,3 sn |

Servis, köprülü CPU'ya göre **2,35 kat** hızlı. Kazanç iki kaynaktan: GPU, ve belge başına
~24 sn'lik süreç başlatma + model yükleme maliyetinin ortadan kalkması.

`ACQUISITION_STAGE_TIMEOUT_S=900` karşısında 285,8 sn rahat; GPU kuyruk bütçesi
(`SMART_ROUTER_QUEUE_WAIT_S=300`) sona kalan belge için sınıra yakın ama altında.

### Determinizm — geçti

`ornek_11.pdf`, servise üç kez:

| Koşu | Süre | Karakter | `content_hash` (ilk 16) |
|---|---|---|---|
| 1 | 9,6 sn | 56.117 | `709c8164ee375c8d` |
| 2 | 4,8 sn | 56.117 | `709c8164ee375c8d` |
| 3 | 6,0 sn | 56.117 | `709c8164ee375c8d` |

`engine_devices` üçünde de `{'docling-service': 'cuda'}`.

### CPU ile GPU aynı metni üretmiyor — bir kez daha doğrulandı

Bu korpusta da göründü: `ornek_4` CPU'da 10 tablo / 61.144 karakter, GPU'da 7 tablo /
62.313 karakter; `ornek_2` 46.031 → 45.243. Yani cihazı beyan edilen parametre yapma
kararı teoride değil, bu kurulumun kendi verisinde karşılığı olan bir karar.
(Uyarı: bu iki koşuda cihazla birlikte taşıma da değişti — köprülü ile servis. Cihaz
farkının kendisi `research/pdf-parser/results/gpu/` altında tek değişkenli ölçülmüştür.)

### Servis kapalıyken — sayfa kaybı yok

`docker compose stop docling`, sonra aynı belge:

- 10 sayfanın 10'u duruyor, altısı `fell_back=True` ile hızlı yol metnini korumuş
- 54.267 karakter → acquisition'ın 400 karakter kapısını **geçiyor**
- `degraded: True`, ve `notes` üç motorun her birinin gerekçesini ayrı ayrı yazıyor

### İmaj boyutu

| Ne | Boyut |
|---|---|
| toplam imaj | **11,9 GB** (düzeltme öncesi 14,6) |
| `site-packages` | 5,4 GB (`nvidia/` 2,6 · `torch/` 1,2 · `triton/` 0,69) |
| model ağırlıkları | 1,4 GB (`CodeFormulaV2` 0,61 · tableformer 0,34 · layout 0,33) |

**Mükerrer ağırlık katmanı düzeltildi.** İlk yapıda `useradd` satırının katmanı 1,44 GB
çıktı — tam olarak üstündeki model indirme katmanı kadar. Sebep `chown -R`: overlay2
kopyala-yaz ve alt katmandaki bir dosya için "yalnız izin değişti" diye bir kaydı yok,
sahiplik değişikliği dosyanın **tamamını** yukarı kopyalatıyor. Katmanlar değişmez
olduğu için de her iki kopya imajda kalıcı olarak duruyordu.

Kullanıcı artık indirmeden önce oluşturuluyor, indirme `USER docling` altında koşuyor ve
`chown` yalnız iki boş dizine uygulanıyor:

| Katman | Önce | Sonra |
|---|---|---|
| `RUN useradd … && chown` | 1,44 GB | **81,9 kB** |
| `RUN docling-tools models download` | 1,44 GB | 1,44 GB |
| imaj toplamı | 14,6 GB | **11,9 GB** |

Çıktının değişmediği doğrulandı: `ornek_11.pdf`'in `content_hash`'i rebuild öncesi ve
sonrası aynı (`709c8164…`).

`CodeFormulaV2`'nin 611 MB'ı bugün kullanılmıyor (`DocumentConverter()` varsayılanında
formül/kod zenginleştirme kapalı) ama ileride açılma ihtimaline karşı **bilerek**
imajda bırakıldı. Kalan boyut ve bağımlılık kilidi `OPEN_ITEMS.md` 17. maddede.

## Kapanan açık iş

`OPEN_ITEMS.md`'nin **3. maddesi** ("PDF tabloları yapısal değil") bu işle kapandı ve
listeden çıkarıldı. Oradaki ölçüm PyMuPDF'in `find_tables()`'ıyla alınmıştı ve o yolun
neden seçilmediğini açıklıyor: 177 sayfalık bir raporda 138 ham tespitin medyan boş hücre
oranı %55 (yarısından fazlası düzen ızgarası), yoğunluk filtresinden sonra 37 tablo
kalıyordu ve maliyet yalnız metne göre **6,7 kat**tı. Docling aynı işi yönlendirilen
sayfalarda yapıyor: bu korpusta 117 tablo, `ParsedTable` ızgarası olarak, sayfa başına
karar maliyeti 0,65-14,84 ms.

### VRAM — ölçüldü ve rezervasyon konuldu

RTX 4060 Laptop, 8188 MiB:

| Durum | Kartta kullanılan |
|---|---|
| Docling servisi kapalı | 46 MiB |
| Servis ayakta, boşta (modeller yüklü) | 767 MiB |
| 38 sayfalık dönüştürmenin tepesinde | 1673 MiB |

Servisin payı boşta ~721 MiB, tepe **~1,6 GB**. Bu makinenin `.env`'ine
`DOCLING_VRAM_RESERVE_GB=1.6` yazıldı; `capacity._gpu_slots()` bunu headroom'dan
düşüyor. Koddaki varsayılan `0.0` kalıyor — başka bir kurulumda ölçülmeden bir sayı
koymak tahmin etmekle aynı şey.

Tabandaki 46 MiB, ölçüm sırasında Ollama'nın hiçbir modeli yerleşik tutmadığını da
gösteriyor: bu, en iyi hâlin ölçümü. İkisi aynı anda kartı kullanırken ne olduğu
`OPEN_ITEMS.md` 18'de açık iş olarak duruyor.

## Uçtan uca doğrulama

Yığın `docker compose up -d --build` ile yeniden kuruldu (`.env`'deki `COMPOSE_FILE`
sayesinde overlay kendiliğinden kapsandı) ve canlı kurulumdan doğrulandı:

```
GET /health  →  "docling": "ok (cuda)"

worker içinden ParserRegistry.health():
{'id': 'smart_pdf', 'priority': 20, 'available': True,
 'detail': 'smart_router, profile gate_v2_kalibre_edilmedi_3a5bb5c9,
            fast path via pdf-inspector 1.14.1,
            heavy path via docling service at http://docling:3941
            (docling 2.121.0, torch 2.13.0+cu132, NVIDIA GeForce RTX 4060 Laptop GPU)'}
```

Yani `smart_pdf` PDF'leri alıyor, hızlı yolu gerçek pdf-inspector koşuyor, ağır yolu
kapsayıcıdaki GPU'lu docling servisi karşılıyor.

## Henüz yapılmayan doğrulamalar

- **CPU varyantı ölçülmedi.** `TORCH_VARIANT=cpu` ile ayrı bir imaj kurulup aynı 12
  belgede `queue-timeout` sıfır mı, taranmış bir PDF 400 karakter kapısını geçiyor mu
  bakılmalı. Kod yolu aynı; ölçülmemiş olan süre bütçelerinin CPU'da yettiği.
- **Panelden gerçek bir araştırma koşusu yapılmadı.** Parser ve servis tarafı canlı
  kurulumdan doğrulandı, ama `source_versions.provenance` içindeki `engine_build` bir
  gerçek koşuda görülmedi.

## Üretilebilirlik manifestosu artık ayrıştırmayı da yazıyor

Uçtan uca koşudan sonra sorulan soru şuydu: "üretilen docx'ten `smart_pdf`'in çalıştığını
doğrulayabilir miyiz?" Cevap hayırdı, ve aramak eksik bir yer daha ortaya çıkardı.

Ölçüm (`01M0SBTA6MQ07ETFHPKAJQH9HZ` teslimatı):

| Dosya | Ayrıştırma bilgisi |
|---|---|
| `16_research_report.docx` | **yok** — `docling`, `pdf-inspector`, `cuda`, "parser" hiç geçmiyor |
| `10_reproducibility_manifest.json` | yalnız `protocol.parsers = {"overrides": {}}` |
| `05_source_catalog.csv` | parser sütunu yok |
| `13_raw_sources.jsonl` | **var** — `version.provenance.parse_provenance`'ın tamamı |

Docx'in taşımaması doğru: o bir sentez belgesi. Ama `protocol.parsers` bir **istek**
kaydı, sonuç kaydı değil — kullanıcının koyduğu override'ları söylüyor, fiilen ne
koştuğunu değil. O koşuda `{"overrides": {}}` yazıyordu; gerçekte 43 sayfalık PDF'in 15
sayfası CUDA'da Docling'e gitmişti.

Bu, bu sürümün kendi öncülüyle çelişiyordu: cihaz sözleşmenin parçası, çünkü
`content_hash` ona bağlı. Adı "üretilebilirlik manifestosu" olan dosya, koşuyu yeniden
üretmek için gereken üç şeyi (hangi parser, hangi motor, hangi cihaz) taşımıyorsa
adını karşılamıyor.

`exporter._parsing_manifest()` eklendi ve manifeste `parsing` alanı olarak kaynak başına
yazılıyor. Yalnız çıktıyı belirleyen anahtarlar kopyalanıyor; sayfa sayfa döküm
`13_raw_sources.jsonl`'de kalıyor — manifesto "bunu ne üretti"yi cevaplar, ham döküm
denetim izini taşır. Parser'ın koymadığı anahtarlar `null` yazılmak yerine düşürülüyor,
böylece tek motorlu bir kaynak dört satırlık kayıt olarak kalıyor.

Canlı koşunun kayıtları üzerinde doğrulandı:

```json
{ "source_id": "01M0SC30WAPGYYVVDW9BFV2VPF",
  "document_type": "pdf", "parser_id": "smart_pdf",
  "parser_profile": "inspector_v1",
  "engine_counts":  { "pdf-inspector": 28, "docling-service": 15 },
  "engine_devices": { "docling-service": "cuda" },
  "engine_build":   { "docling-service": "docling 2.121.0, torch 2.13.0+cu132,
                       NVIDIA GeForce RTX 4060 Laptop GPU" },
  "esik_version": "gate_v2_kalibre_edilmedi_3a5bb5c9", "degraded": false }
```

HTML kaynakları aynı listede dört satır kalıyor. `tests/test_export_manifest.py` dört
davranışı çiviliyor: motor ve cihazın yazılması, sayfa dökümünün manifeste sızmaması,
tek motorlu kaydın kısa kalması, ve `parse_provenance`'tan önceki eski satırların
export'u düşürmemesi.

`repo.list_source_versions()` zaten `13_raw_sources.jsonl` için çağrılıyordu; çağrı
yukarı taşındı ve ikisi paylaşıyor — ek veritabanı turu yok.
