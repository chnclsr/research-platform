# v0.24.0 — Panelde adım, hata ve karar ayrıntıları

Tarih: `2026-09-08`. Dal: `developments-supplementer`. Taban commit: `47750ab`.

## Uygulanan değişiklikler

- Aşama → tur görünümü korundu. Ziyaret başlangıç olayının kimliğiyle tanımlanıyor;
  aynı tur numarası/zaman damgası ziyaretleri karıştırmıyor. Araç çağrısı bulunmayan
  audit/coverage gibi adımlar da karar ayrıntısı açıyor.
- Protokol, sorgu planı, connector seçimi, edinim/parser, kaynak kapsam kararları,
  pasaj seçimi, iddia kabul/eleme/birleştirme, audit, coverage, recovery, appraisal ve
  sentez temaları mevcut olay tablosuna tanılama kayıtları ekliyor.
- Audit her iddianın önceki/yeni durumunu, eşiklerini ve kanıt kimlikleri üzerinden
  destek/karşı kanıtı kaydediyor. Appraisal katman gerekçesini, dereceyi, düşürme
  nedenlerini ve reddedilmiş model önerilerini saklıyor.
- Coverage kararı hesaplandığı anda değerler, pay/payda girdileri, etkinlik koşulları,
  eşikler ve toplama bütçesi kaydediliyor. Ana audit'in tüm major iddialarıyla
  coverage'ın alaka ≥ 0,25 ve en fazla 8 major iddia seçimi ayrıştırılıyor.
  Ham çıktı modu ve literatür taramasında kapsam yeterliyken bütçeyle devam edilmesi
  görünür. Hesap ve durma kararları değiştirilmedi.
- Connector çağrıları `call_id` ile eşleştiriliyor. Arama ve citation ayrı işlemler;
  arama süresi/sonuç sayısı citation alt çağrılarından ayrılıyor. Eski metric/error
  olayları uyumluluk için korunuyor; panel aynı hatayı iki kez saymıyor.
  HTTP durumu, hata sınıfı, özgün/derlenmiş/gönderilen/yankılanan sorgu gösteriliyor.
  arXiv ve Semantic Scholar'ın mevcut retry döngülerindeki gerçek denemeler kaydediliyor;
  kaydedilmemiş retry bilgisi tahmin edilmiyor. Sıfır sonuç hata sayılmıyor.
- Kaynak izi düğmeleri mevcut kaynak/kanıt görünümünü açıyor. Kalite kartları audit
  veya coverage aşamasına yönlendiriyor. Teknik JSON açılabiliyor ve kopyalanabiliyor.
- Çalışan koşu 5 saniyede yenileniyor; aşama, açık ziyaret, tanılama filtresi, olay sayfası
  ve çekmece kaydırması korunuyor. Koşu değişiminde eski yanıtlar uygulanmıyor;
  terminal koşuda otomatik ayrıntı sorguları duruyor.

## Veri sözleşmesi ve güvenlik

Şema göçü yok. `EventRow.payload` içindeki `schema_version=1`, `visit_id` ve `round`
alanları mevcut JSON altyapısında saklanıyor. İddia/kaynak kararları en fazla 100 kayıtlık
yazma gruplarıyla kaydediliyor. PDF, tam belge ve yinelenen alıntı metinleri bu kayıtlara
kopyalanmıyor; kanıt, pasaj ve sürüm kimlikleri mevcut veriyle bağlantıyı sağlıyor.

| Yeni panel endpoint'i | İşlev |
|---|---|
| `/api/runs/{run_id}/events` | Tüm geçmiş üzerinde tür/connector/hata-uyarı filtresi ve sayfalama |
| `/api/runs/{run_id}/stages/{stage}/visits/{visit_id}` | Ziyaret olayları ve karar özeti |
| `/api/runs/{run_id}/claims/current` | Geçmiş karar olmadığı etiketlenmiş son iddia durumu |

Ayrıntı sayfası varsayılan 50, azami 200 olaydır. Aşama listesinde 200'den sonraki
ziyaretlere sonraki sayfalarla erişilir. Son kalite olayı doğrudan son ilgili kayıttan
okunur; toplamlar ilgili olayların tamamından sınırlı bellekli toplulaştırmayla hesaplanır.
İlk 5.000 olaya bağımlılık kaldırıldı.

Oturum ve koşu sahipliği kontrolü uygulanır; başkasının koşusu/ziyareti 404 döner.
Yeni yazmalarda ve tarihsel olayların sunumunda kimlik doğrulama başlıkları, token'lar
ve bilinen URL sırları maskelenir. Arayüz olay metnini HTML olarak çalıştırmaz.

Eski koşular değiştirilmedi. Tarihsel snapshot yokluğu açıkça belirtilir; bugünkü iddia
durumu geçmiş turun kararı gibi sunulmaz. Atlanmış, işlenecek verisi olmayan ve ayrıntısı
kaydedilmemiş ziyaretler ayrıca işaretlenir.

## Korunan kararlar ve eşzamanlı değişiklikler

`previous_reports/CONTROL_PANEL_FLOW_V0.6.7_IMPLEMENTATION_REPORT.md` içindeki aşama
akışı ve recovery görünümü korunmuştur. Araç tablosunun bir adımın tek ayrıntısı olması
yaklaşımı genişletilmiştir: deterministik kararlar da bağımsız tarihsel kayıtlardır.

Tanılama değişiklikleri araştırma eşiklerini, kaynak seçimini veya okuyucuya sunulan LLM
metnini değiştirmez ve ek LLM çağrısı yapmaz. Çalışma sırasında ağaca gelen kapsam dışlama
etiketi eşleştirmesi değişiklikleri, ilgili testler ve kullanıcının `OPEN_ITEMS.md`
düzenlemeleri korunmuştur; panel düzeltmesi olarak sahiplenilmemiştir.

## Doğrulama

- Son kod değişikliğinden sonra zorunlu tam paket: **919 passed, 3 skipped, 1 warning**
  (69,18 sn). Komut: `TESTING=true .venv/bin/python -m pytest -q`.
  Bir uyarı mevcut Starlette/httpx deprecation kaydıdır. Tarayıcı testi varsayılan
  pakette opt-in olarak atlanır ve aşağıdaki komutla ayrıca geçirilmiştir.
- Gerçek headless Chromium: **1 passed** (13,33 sn).
  `RUN_PANEL_BROWSER_TESTS=true TESTING=true .venv/bin/python -m pytest -q tests/test_panel_browser.py`.
  205 ziyaret, klavye, hata filtresi, olay sayfası, kaynak izi, güvenli metin,
  canlı yenileme ve terminal durma sınandı. Sabit API verisiyle gerçek panel JavaScript'i
  çalıştırıldı. Yenileme boyunca 205 turun DOM'dan hiç kaybolmadığı ve açık genel bölümün
  kapanmadığı ayrıca doğrulandı. SQLite fixture ortak olduğu için bu komut tam paketle
  paralel çalıştırılmaz.
- 5.511 olay / 205 ziyaret regresyonu: toplamlar, son karar, sayfalama, aynı zaman
  damgasında ziyaret ayrımı ve azami 200 kayıt yanıtı doğrulandı.
- HTTP 429/400/503, timeout, arXiv sorgu reddi/boş sonuç ve gerçek retry geçmişi,
  çağrı eşleştirme/tek hata sayımı, parser degraded alanları, tarihsel audit ayrımı,
  raw coverage ve endpoint sahiplik/sır maskeleme testleri eklendi veya genişletildi.
- Kontrollü uçtan uca pipeline testi sabit dış arama/edinim sağlayıcılarıyla rapor
  çıktılarına kadar ilerledi. Yeni connector, edinim, kaynak, audit, coverage, appraisal
  ve sentez kayıtlarının sürüm/ziyaret sözleşmesi doğrulandı. Benchmark ve dedup
  test doubles yeni toplu kayıt metoduna uyarlandı.
- Üretim verisine salt okunur kontrol: `01M1XDAQXDWZHZY0WQ41WK6DGS` için 190 kaynak,
  8 coverage ziyareti; `01M1XQTGQEFT08K2F0S0YP3665` için 22 kaynak, 3 coverage ziyareti
  doğru okundu. Son karar ikisinde de `recovery_exhausted_no_progress`; tarihsel
  snapshot yokluğu doğru işaretlendi. Eski koşular yeniden çalıştırılmadı/yazılmadı.
- Yeni modüller/testler ve değişen connector/exporter/benchmark dosyalarında Ruff temiz.
  Eski dosyaların taban borcu artırılmadı: panel 33→33, metrics 2→1, pipeline 15→15,
  repository 3→3, Word 1→1, pipeline testleri 1→1. Tam-depo Ruff temizliği iddia edilmiyor.
  `git diff --check` geçti.

## Devreye alma

Uygulama ve Telegram imajları v0.24.0 olarak yeniden oluşturuldu. Aktif/kuyrukta koşu
olmadığı doğrulanarak API, worker, MCP gateway ve zaten çalışan tek Telegram container'ı
yenilendi. Dördünün içinden `VERSION=0.24.0` ve yeni `diagnostic_batch` metodu doğrulandı.
Host panelinin editable paket metadata'sı güncellendi; doğrulanan kendi sürecine TERM
gönderilerek systemd'nin `Restart=always` politikasıyla yeniden başlatıldı.

Panel gerçek portu `1111` üzerinden healthy/v0.24.0 döndü. API bağımlılıkları database,
Redis, Ollama, AgentSearch, Crawl4AI, Docling ve MinIO için `ok`; Docling cihazı `cuda`.
Mevcut tek Telegram örneğinin güncelleme öncesi/sonrası kontrolünde polling çakışması yoktu.
Gerçek üretim panelinde tamamlanmış koşunun 8 coverage turu açıldı; JavaScript hatası yoktu.

Son Türkçe özet/filtre görünümü rötuşlarının imajları da hazırlandı. İkinci container
yenilemesi öncesinde `01M203HHZXZB61YF59AZZQ2YA4` araştırması başlamıştı. Koruma kontrolü
yenilemeyi **hiçbir container'a dokunmadan durdurdu**. Yalnız araştırma worker'ından
bağımsız host paneli son görünüme geçirildi; son container yenilemesi koşu sonrasına
bırakıldı. Çalışan v0.24.0 worker gerçek yeni koşuda 70 connector, 156 edinim, 130 kaynak
kararı ve 1 çıkarım özeti kaydını `schema_version=1` ile üretmişti; salt okunur doğrulandı.
Yeni kaynak koduyla çalışan panel son Türkçe özetleri sunar; aktif worker'ın yalnız bu
son okuyucu-görünümü değişikliklerini içeren imajla yeniden oluşturulması beklemektedir.

Aktif koşu sırasında görülen kendiliğinden açılıp kapanma ayrıca giderildi. Neden,
5 saniyelik sessiz yenilemenin gerçek çekmece gövdesini önce boşaltması ve aşama/tur
istekleri tamamlanana kadar eksik DOM göstermesiydi. Yeni gövde artık bağlantısız bir
hazırlık ağacında tamamen kuruluyor; bütün dinamik aşama ve olay yükleri bittikten sonra
tek `replaceChildren` işlemiyle görünür oluyor. Genel açılır bölümler, açık kaynak izleri
ve kaynak akıbet filtresi de koşu bazında saklanıyor.

Yalnız host `research-control-panel` süreci doğrulanan PID'ye `TERM` gönderilerek
systemd'nin `Restart=always` politikasıyla yenilendi (`716624` → `771117`). Araştırma
container'larına ve worker'a dokunulmadı. `01M203HHZXZB61YF59AZZQ2YA4` koşusu yenileme
öncesi ve sonrası `running` kaldı. Üretim panelindeki salt okunur Chromium ölçümünde 223
örneğin hiçbirinde tur listesi boşalmadı, seçili aşama/açık tur/açık genel bölüm kapanmadı;
gövde yalnız bir kez atomik değişti ve JavaScript hatası oluşmadı.

İkinci kararlılık denetimi atomik değişimin kapsamadığı iç durumları buldu: üst olay kartı
açık kalırken `Teknik olay verisi`, `scope_assessment/gaps` gibi iç içe alanlar ve olay
kartından yüklenen kaynak izi kapanıyordu. Her ayrıntıya olay kimliği ile tam alan yolundan
kararlı bir anahtar verildi. Olay içi kaynak izi aç/kapat davranışı kazandı; aynı koşudaki
kaynak izi yanıtları promise önbelleğinde tutuldu ve koşu/çekmece değişiminde temizlendi.
Ana kaynak tablosu da aynı önbelleği kullanır.

Yeni üretim Chromium kabulünde gerçek 5 saniyelik yenileme boyunca 222 örneğin hiçbirinde
olay kartı, teknik JSON, facet ayrıntısı, olay içi kaynak izi veya ana kaynak satırı
kapanmadı. Bir alt seviye alan da açık kaldı. Kaynak izi GET sayısı yenileme öncesi ve
sonrasında `2 → 2` kaldı; yeniden yükleme/parlama oluşmadı ve JavaScript hatası yoktu.
Yalnız host paneli `771117` PID'sinden `877116` PID'sine yenilendi; aktif araştırma worker'ı
ve container'lar kesilmedi.
