# Koşu Donanım Telemetrisi — v0.14.0

Platform sürümü: `v0.14.0`

Belge sürümü: `1.1`

Tarih: `2026-08-25`

## Amaç ve ölçümün anlamı

Platform aynı worker sürecinde birden fazla araştırmayı paralel yürütebilir. `psutil` ve
NVML sayaçları bir asyncio görevinin payını değil ortak çalışma ortamını ölçer. Bu nedenle
çıktı bilinçli olarak **koşuya atfedilmiş tüketim** değil, **koşu penceresinde görülen ortak
Docker/WSL ve GPU yükü** olarak tanımlandı.

Bir koşu devam ederken ikincisi başlarsa tek donanım örneği iki koşunun penceresine de
yazılır. Her kopya kendi koşusunun aşamasını ve kimlik açıklamayan `active_run_count`
değerini taşır. Grafik paralel çalışma aralığını gölgeler; başka kullanıcının run kimliği,
sorusu veya konusu hiçbir telemetri kaydına girmez.

CPU/RAM worker kapsayıcısının gördüğü Docker Desktop/WSL ortamıdır; Windows host'un tamamı
değildir. GPU ise worker'a görünür kartın toplam sayacıdır: host Ollama, Docling, masaüstü
ve platform dışı GPU işi aynı toplamda yer alabilir.

## Mimari

`hardware_telemetry.TelemetryHub` worker sürecinde tek örnektir. Kapasite kapısı bir koşuyu
kabul ettikten sonra segment açılır; kuyrukta bekleme ölçülmez. Hub varsayılan beş saniyede
bir donanımı tek kez okur ve sonucu etkin koşuların tamponlarına dağıtır.

Ölçülen alanlar:

- sistem CPU yüzdesi, RAM yüzdesi ve uygun RAM,
- worker CPU yüzdesi ve RSS,
- görünür her GPU için kullanım, bellek kullanımı/toplamı, sıcaklık ve destekleniyorsa güç.

Pipeline `_boundary()` her aşamanın başında yalnız o koşunun stage etiketini günceller.
Pause/preemption/HITL segmenti kapatır; resume yeni segment açar ve bekleme süresi aktif
süreye katılmaz.

Örnekler yaklaşık dakikalık `hardware_telemetry_samples` event partilerine yazılır;
segment başlangıç/bitişi `hardware_telemetry_segment` olayıdır. Yeni tablo veya migration
yoktur. Tampon 720 örnekle sınırlıdır; veritabanı geçici olarak yazılamazsa bellek sınırsız
büyümez. Ham telemetri event'leri kontrol panelinin genel olay/zaman çizelgesi sorgusundan
çıkarılmıştır; uzun koşular panelin 5.000 olay kotasını telemetriyle tüketmez.

## NVML ve GPU erişimi

Kurulan paketin adı `nvidia-ml-py>=13.610,<14`, içe aktarılan modül `pynvml`'dir. GPU
overlay'i worker'a `NVIDIA_DRIVER_CAPABILITIES=utility` ile hosttaki tüm görünür GPU'ları
verir. Worker CUDA işi çalıştırmaz; bu erişim yalnız NVML okuması içindir ve
Docling/Ollama kilitlerine dokunmaz.

NVML modülü, sürücü kütüphanesi, cihaz veya tekil sensör bulunamazsa hata ilgili GPU
alanına indirgenir. CPU/RAM ölçümü ve araştırma devam eder; telemetri hiçbir zaman kabul
kapısı veya araştırma başarı koşulu değildir.

## Artifact ve teslimat

Admitted bir koşu `completed`, `completed_incomplete`, `failed` veya `cancelled` olduğunda:

| Artifact | İçerik |
|---|---|
| `18_hardware_utilization.csv` | Ham örnekler, segment, stage ve anonim paralellik sayısı |
| `19_hardware_utilization_summary.json` | Ortalama, p95, tepe, aktif süre ve eksik örnek tahmini |
| `20_hardware_utilization.svg` | CPU, RAM, worker RSS, GPU, VRAM, stage ve paralellik şeritleri |
| `hardware_utilization_bundle.zip` | Üç dosyanın terminal durumdan bağımsız paketi |

SVG dış grafik bağımlılığı olmadan üretilir ve dinamik metin XML-escape edilir. Panel SVG'yi
mevcut sahiplik korumalı, aynı-origin artifact URL'sini doğrudan `<img>` kaynağı yaparak
yükler; yeni, korumasız bir indirme yolu açılmaz. Canlı smoke sırasında ilk blob URL
uygulamasının panel CSP'sindeki `img-src 'self' data:` kuralıyla engellendiği görüldü.
CSP'yi genişletmek yerine blob katmanı kaldırıldı ve render tarayıcıda gerçek doğal
boyutlarla doğrulandı.

Tamamlanan koşularda CSV `raw_bundle.zip`'e, JSON+SVG `result_bundle.zip`'e, üçü birden
`research_bundle.zip`'e eklenir. ZIP yeniden yazımı aynı adlı eski üyeyi önce çıkarır;
finalizer tekrar çalışsa duplicate entry oluşmaz. Başarısız/iptal koşularda araştırma
paketleri hiç üretilmemiş olsa bile bağımsız donanım paketi vardır.

## Hata ve kurtarma davranışı

- Telemetri başlatma, durdurma veya finalization hatası araştırma sonucunu değiştirmez.
- Pipeline hatası ile telemetri hatası aynı anda oluşursa özgün pipeline hatası yeniden
  yükseltilir ve kapasite slotu `finally` içinde bırakılır.
- Normal pause/resume ve worker recovery'de kalıcı partiler korunur; yeni çalışma yeni
  segment olarak devam eder.
- Worker'ın zorla öldürülmesi yalnız son yazılmamış tamponu kaybedebilir; önceki event'ler
  ve araştırma checkpoint'leri değişmez.
- Kapasite, model lease, Docling semaforu ve parser determinizmi kararları değiştirilmedi.

## Değiştirilen eski kararlarla ilişki

`PARALLEL_RUNS_V0.12.0_IMPLEMENTATION_REPORT.md`, `psutil` ölçümünün WSL2 sanal makinesini
gördüğünü ve koşu başına RAM bütçesinin henüz ölçülmediğini kaydediyordu. Bu iş o kapsamı
değiştirmiyor; görünür kılıyor ve worker RSS zaman serisiyle bütçeyi ölçmeye veri sağlıyor.

`DOCLING_GPU_SERVICE_V0.13.0_IMPLEMENTATION_REPORT.md`, worker'da `nvidia-smi` bulunmadığı
için kapasitenin Ollama `/api/ps` verisini kullandığını söylüyordu. Kapasite hesabı hâlâ
aynı yolu kullanır. NVML erişimi yalnız raporlama içindir; masaüstü dahil toplam GPU yükünü
kapasite girdisi yaparak eski kararı sessizce değiştirmez.

`CANCELLATION_RELIABILITY_V0.6.3_IMPLEMENTATION_REPORT.md` içindeki checkpoint'ten kurtarma
ve hard-timeout güvenliği aynen korunur. Worker rebuild'i çalışan koşuyu kesip checkpoint'ten
yeniden başlatabileceği için canlı kurulum `running=0` kapısına bağlanmıştır.

## Doğrulama

- Sahte psutil/NVML ile ilk yüzde örneğinin ısınması, iki GPU ve CPU-only degradation.
- Tek ortak örneğin iki koşuya farklı stage ve aynı `active_run_count` ile yazılması.
- Pause/resume segment ayrımı; failed/cancelled bağımsız artifact paketi.
- CSV/JSON/SVG içeriği, XML escape, ZIP üyelikleri ve idempotent finalizer.
- Telemetri hatalarının pipeline hatasını maskelememesi ve kapasite slotunun bırakılması.
- Sahiplik, panel, worker ve pipeline regresyonları: `78 passed, 1 warning`.
- Son panel entegrasyon düzeltmesi üzerinde zorunlu tam paket: `460 passed, 2 warnings`,
  68,56 saniye.

Hedefli Ruff ve compose yapı doğrulaması temizdir.

## Canlı dağıtım ve smoke doğrulaması

- İki çalışan koşu API üzerinden duraklatıldı; her ikisinin `CHUNK_INDEX` güvenli sınırında
  `paused` olayı yazması ve ARQ in-progress anahtarlarının kalkması beklendi.
- Veritabanında `running=0` doğrulandıktan sonra yalnız worker `--no-deps --build
  --force-recreate` ile yeniden oluşturuldu.
- Container `research-platform=0.14.0`, `psutil=7.2.2` ve
  `nvidia-ml-py=13.610.43` yükledi; NVML, RTX 4060 Laptop GPU'yu gördü. Enjekte edilen
  CPU-only yol CPU/RAM örneği ve açık `pynvml module is not installed` gerekçesi üretti.
- Smoke koşusu `01M0VXSCKZ1F0VH8BFM330GK6C`, 19,5 saniyelik tek segmentte dört örnek
  yazdı ve `completed_incomplete` oldu. Dört telemetri artifact'i, raw/result/research
  ZIP üyelikleri ve 5 saniyeye yakın örnekleme doğrulandı.
- Host panel v0.14 kaynak koduyla yeniden başlatıldı. Chrome'da SVG önizlemesi
  `naturalWidth=1200`, `naturalHeight=930` ve görünür `1093×847` boyutla, console hatası
  olmadan render edildi.
- Eski iki koşu yeniden kuyruğa alındı. Her ikisi için ayrı segment açıldı; ilk ortak
  örnek aynı timestamp, `active_run_count=2`, `gpu_status=ok` ve bir görünür GPU taşıdı.
  Dakikalık ilk partilerde koşuya özgü DECOMPOSE/BUILD_QUERY_BRANCHES/SEARCH/ACQUIRE
  aşama etiketleri kalıcı olarak görüldü.

## Sürüm tekilleştirme ve SVG yerleşim düzeltmesi

Telemetri smoke doğrulamasında paket, API ve panelin farklı sabit sürüm metinleri
gösterdiği görüldü. `pyproject.toml` kurulu dağıtımın tek sürüm beyanı olarak bırakıldı;
yeni `research_platform.version.VERSION` değeri bunu `importlib.metadata` üzerinden
okuyor. Paket `__version__`, API ve panel FastAPI metadata'sı, panel health yanıtı,
kapsayıcı MCP health yanıtı, sistem durum yanıtı ve footer aynı değeri kullanıyor. Böylece OPEN_ITEMS 22. madde
kapatıldı; eşitlik ayrı bir regresyon testiyle korunuyor.

İlk SVG'de panel başlıkları, legend'ler ve üst eksen etiketleri aynı dikey alanda
çiziliyordu. Her panel için 36 piksellik ayrı başlık bandı ayrıldı; çizim alanı ve eksen
etiketleri bu bandın altına taşındı, legend başlangıcı başlıktan 150 piksel uzağa alındı.
Koordinat regresyon testi ile gerçek smoke artifact'i birlikte doğrulandı. Host panel
yeniden başlatıldı ve Chrome'da `v0.14.0` footer ile 1200×930 SVG'nin çakışmasız render'ı
görüldü. Son kod değişikliğinde hedefli Ruff temiz, hedefli paket `33 passed`, zorunlu tam
paket `461 passed, 2 warnings` sonucuyla geçti. MCP health kapsamı eklendikten sonraki
hedefli paket ayrıca `55 passed, 2 warnings` sonucunu verdi.

İki araştırma bu düzeltme boyunca `running` kaldı. Worker/API imajları yeniden
oluşturulmadı; yalnız host panel süreci yenilendi. Bu nedenle aktif koşular kesilmedi.
