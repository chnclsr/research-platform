# PDF Parser A-B-C Uçtan Uca Çalışma Raporu

<!-- CODEX-2026-08-18: A, B ve C kollarındaki kodu, ölçüm kanıtlarını,
başarısız sonuçları ve açık işleri tek güncel kaynakta birleştiren ana rapor. -->

**Tarih:** 18 Ağustos 2026
**Üretim deposu:** bu `research-platform` klonu
**Dal:** `pdf-parser-degerlendirme`
**Sürümlenen ölçüm alanı:** `research/pdf-parser`

Bu belge A, B ve C kollarında ne yapıldığını baştan sona tek yerde anlatır.
Eski `A_KOLU_OZET.md`, `A_B_KOLU_SONUC.md` ve `C_KOLU_SONUC.md` dosyaları
ayrıntı/tarihsel kayıt olarak durur; güncel genel durum için ana kaynak bu
belgedir.

## 1. Yönetici Özeti

Başlangıçta sistem bir PDF için tek parser seçiyor ve belgenin tamamını o
parser'a veriyordu. Ayrıca ilk smart-router prototipinde gerçek pdf-inspector
yerine PyMuPDF tabanlı bir mock kullanıldığı için kalite kararı yanlış girdiye
bakıyordu.

Bugün ulaşılan akış:

```text
PDF bytes
  -> SmartPdfParser
  -> pdf-inspector ile tüm sayfaların hızlı çıkarımı
  -> sayfa başına OCR / tablo / şekil / kalite sinyalleri
  -> yalnız işaretlenen sayfalar için Docling
  -> fast/heavy sayfa karşılaştırması ve karantina
  -> sayfaları sırayla birleştirme
  -> Markdown + tablolar + sayfa/engine provenance
  -> acquisition -> passages -> repository
```

| Kol | Amaç | Güncel durum |
|---|---|---|
| A | Yönlendirme mantığını gerçek parser ve sayfa düzeyinde kurmak | Tamamlandı ve ölçüldü |
| B | Mantığı production parser/acquisition sözleşmesine bağlamak | Temel zincir çalışıyor; A/B commitleri GitHub dalında |
| C1 | Fast, heavy ve routed çıktıyı referansa karşı ölçmek | 180 TR + 50 EN, 230/230 çıktı |
| C2 | Route ve algılama eşiklerini kalibre etmek | Tarama tamam; kabul edilen production route eşiği yok |
| C3 | Merge, fallback ve karantina güvenliği | Temel koruma tamam; semantik denetim eksik |

**Dürüst sonuç:** Çıktı veren ve parser katmanında uçtan uca çalışan bir teknik
RC var. Ancak ortak route kararı İngilizcede kötü genelliyor, çok sayfalı ve
gerçek taranmış PDF doğrulaması yok, production Docling köprüsü yavaş ve tüm
deep-research servisi canlı API/kuyruk/veritabanı ile uçtan uca sınanmadı.

## 2. Başlangıç Araştırması: Neden Hibrit Parser

Önce 9 yerel PDF ve OpenDataLoader'ın 200 belgeli resmi benchmark'ında parserlar
karşılaştırıldı. Resmi benchmark'ın PDF, referans ve metrik kodu değiştirilmeden
kullanıldı.

| Motor | Overall | Okuma sırası | Tablo | Başlık |
|---|---:|---:|---:|---:|
| Docling | **0,894** | 0,910 | **0,934** | **0,827** |
| pdf-inspector | 0,876 | **0,915** | 0,814 | 0,788 |
| PyMuPDF4LLM | 0,869 | 0,907 | 0,790 | 0,783 |
| MinerU | 0,857 | 0,871 | 0,911 | 0,800 |
| OpenDataLoader | 0,838 | 0,913 | 0,427 | 0,760 |
| pypdf | 0,576 | 0,870 | 0,000 | 0,000 |

Bu sonuç tek motor seçmek yerine şu tasarımı destekledi:

- pdf-inspector hızlı yol ve okuma sırası için güçlü.
- Docling tablo ve karmaşık düzen için en yüksek genel sonucu verdi.
- Taranmış PDF'de text-layer motorları başarısız; OCR motoru gerekiyor.
- Ağır motor saniyeler, yönlendirme sinyalleri milisaniyeler sürüyor.

Kanıt: `out/_resmi_benchmark_tum.log` ve `resmi_benchmark_sonuc.json`.

## 3. A Kolu: Yönlendirme Mantığı

### 3.1 A1: Mock kaldırıldı, canonical çıktı sabitlendi

**Sorun:** `inspector.py` gerçek pdf-inspector Markdown'ı yerine PyMuPDF düz
metni veriyordu. Her fiziksel satır ayrı paragraf gibi göründüğü için critic
belgeyi olduğundan kötü sayıyordu.

**Yapılan:** Gerçek `pdf_inspector.process_pdf().markdown` canonical hızlı çıktı
oldu. Mock ve üretim davranışı ayrıldı.

**Ölçülen sonuç:**

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Hızlı yolu kullanabilen belge | 0/9 | 3/9 |
| `table_irregularity` çalışan belge | 0/9 | 8/9 |
| `heading_incoherence` çalışan belge | 0/9 | 6/9 |

Bu, ilk kararların bir kısmının PDF kalitesini değil mock biçimini ölçtüğünü
kanıtladı.

### 3.2 A2: Critic sayfa düzeyine indirildi

Belgeye tek puan vermek yerine her sayfa ayrı değerlendirildi. Belge puanı sayfa
puanlarından türetildi; boş/ölçülemeyen sayfa otomatik olarak en kötü sayfa
sayılmadı.

Ölçülen critic maliyeti yaklaşık `0,42-0,92 ms/sayfa`. Sayfa bazlı skorlar 9/9
belgede eski belge skorundan `+9,9` ile `+23,4` daha yüksek çıktı. Bu aynı zamanda
eski `75` eşiğinin yeni ölçek için doğrudan kullanılamayacağını gösterdi.

### 3.3 A3: Critic giriş kararından çıkış denetimine taşındı

Eski düşünce "PDF'e bak, parser seç" idi. Yeni sıra "önce ucuz çıkarım yap,
çıktıyı değerlendir, gerekirse ağır motor kullan" oldu. Böylece temiz sayfalar
gereksiz yere ağır motora gitmiyor.

Sınırlama: İlk post-critic yalnız bozuk karakter, tekrar, kırık satır gibi
motorlar arasında karşılaştırılabilir bozulma sinyallerini görebiliyor. Formül
anlamı ve yanlış kelime gibi semantik kayıpları güvenilir biçimde göremiyor.

### 3.4 A4: Giriş kapısı ve sayfa seçici

Kapı sayfa başına `needs_ocr`, `has_table`, `has_figure`, tablo güveni ve kalite
sinyali üretiyor. Tek yapısal skor artık yol seçmiyor.

| Sinyal | Recall, yerel / bench | Precision, yerel / bench |
|---|---:|---:|
| Tablo | 0,93 / 0,98 | 0,55 / 0,51 |
| Yüksek güven tablo | 0,60 / 0,79 | 0,75 / 0,87 |
| Şekil | 0,99 / 0,99 | 0,69 / 0,62 |
| Vektörel şekil | 0,97 / 0,93 | 0,48 / 0,23 |

Şekil recall'ı eski kuraldaki `0,63` seviyesinden `0,99` seviyesine çıktı.
Precision'ın düşük olması daha sonra C'de gerçek maliyet/kalite problemi olarak
doğrulandı; bu yalnız teorik bir risk olarak kalmadı.

### 3.5 A5: Sayfa tabanı ve ardışık ağır çağrılar

Farklı araçların 0/1 tabanlı sayfa numaraları tek yerde normalize edildi.
İşaretlenen sayfalar ardışık bloklara bölündü; örneğin 3-5 tek Docling çağrısı,
8 ayrı çağrı oluyor.

Ölçüm:

| Koşu | Toplam | Sayfa başına |
|---|---:|---:|
| 12 ardışık sayfa, tek sıcak çağrı | 18,56 sn | 1,55 sn |
| 12 dağınık sayfa, 12 çağrı | 29,28 sn | 2,44 sn |

Production süreç köprüsünde ayrıca yaklaşık `5,2 sn/çağrı` başlangıç maliyeti
ölçüldü. Bu nedenle bloklama production'da daha da önemli.

### 3.6 A6: Metrik ve sinyal onarımları

- `char_drop_ratio` gerçek karşılaştırma tabanına bağlandı.
- Eski `vector_table_drop` yerine ölçülmüş `has_table` sinyali kullanıldı.
- Unicode gürültüsü yanlış ölçeklenmek yerine görünürlük sinyaline çevrildi.
- Belge anlamı gerektiren running-header/repetition metrikleri belge düzeyinde kaldı.
- OCR hedefi ölçülmemiş `miner-VL` iddiasından Docling/MinerU gerçek sonuçlarına taşındı.
- `has_figure` raster ve vektör sinyallerini birleştirecek şekilde düzeltildi.

### 3.7 A7: Yapısal skor yalnız kuyruk önceliği oldu

17 farklı özelliğin aynı `0-100` aralığıyla normalize edilmesi skoru anlamsız
hale getiriyordu; örneğin taranmış belge yalnız `4,3` puanla en düşük skoru
alıyordu. Bu skor parser seçmekten çıkarıldı, yalnız iş sırasını belirliyor.

### 3.8 A8-A10: Devralınan borçlar

| İş | Yapılan | Sonuç |
|---|---|---|
| A8 legacy giriş | `router.py` legacy, `pipeline.py` uyumluluk katmanı olarak işaretlendi | Mentör benchmark'ı bozulmadı |
| A9 çift inspector | Kapı hazır inspector sonucunu kullanıyor | Karar aynı; 8/9 belgede kapı %27-37 ucuzladı |
| A10 `critical_issue` | Kritik ve uyarı ayrımı sayfa seçiciye bağlandı | 261 sayfada 0 yol değişimi; yanlış alarm olabilecek 60 ek ağır sayfa engellendi |

### 3.9 A kolu toplam sonucu

9 belge ve 261 sayfada:

| Yol | Sayfa | Oran |
|---|---:|---:|
| Hızlı | 114 | %44 |
| Ağır | 139 | %53 |
| OCR | 8 | %3 |

Kontrol maliyeti belgeye göre `0,65-14,84 ms/sayfa`; ağır motor maliyeti
saniye düzeyinde. A kolu "sayfa seçmek ucuz" tezini kanıtladı. Fakat bu aşamada
"seçilen sayfada Docling gerçekten daha iyi mi" sorusu henüz ölçülmemişti; C1
bu boşluk için yazıldı.

Kanıtlar: `out/a_kolu_kosu.json`, `out/kapi_korpus.json`,
`out/kapi_bench.json`, `out/critic_olcum.json`.

## 4. B Kolu: Production Sözleşmesine Entegrasyon

### 4.1 SmartPdfParser ve tek production kaynak

Router kodu `research-platform/src/research_platform/parsers/smart_router/`
altına taşındı. `SmartPdfParser`, mevcut `DocumentParser` sözleşmesine uydu ve
registry'de PDF için öncelikli parser oldu.

İlk production commit: `432eb06`.

### 4.2 Registry ve sayfa numaralarının korunması

`priority = 10` ile deterministik registry seçimi sağlandı. Markdown birleşirken
`# Page N` başlığı bir kez ekleniyor, sayfanın kendi H1 başlıkları bir seviye
indiriliyor. `passages.py` iç içe bölüm yolunda da `Page N` buluyor.

Ölçülen sonuç: Metin katmanı olan 8/9 belgede sayfa numarası taşıyan pasaj oranı
eski `%22-52` aralığından `%100`'e çıktı.

Commit: `0d02465`.

### 4.3 Ağır motor gerçekten bağlandı

Router daha önce yalnız karar veriyor, Docling'i çağırmıyordu. Docling için iki
çalışma şekli eklendi:

- Aynı process içinde import.
- `SMART_ROUTER_DOCLING_PYTHON` ile ayrı Python köprüsü ve gerçek timeout.

Eksik/timeout olan sayfa kaybolmuyor; fast metin korunuyor ve degraded/fallback
provenance yazılıyor.

Taranmış sentetik belgede çıktı `68` karakterden `25.036` karaktere çıktı ve
acquisition'ın `<400` filtresinden geçer hale geldi.

Commit: `bb1d277`.

### 4.4 Provenance uçtan uca taşındı

`ParsedDocument -> AcquiredDocument -> SourceVersion.provenance` zincirine şu
bilgiler eklendi:

- Parser profili.
- Router/eşik/engine sürümü.
- Her sayfanın motoru ve yönlendirme nedeni.
- Fallback, degraded ve karantina durumu.

Mevcut JSON alanı kullanıldığı için veritabanı migration'ı gerekmedi. Content
hash yalnız metinden üretilmeye devam ediyor.

Commit: `314a3df`.

### 4.5 Async acquisition ve ağır iş sınırı

Senkron parser çağrıları `asyncio.to_thread` ile event loop dışına alındı.
`SMART_ROUTER_MAX_CONCURRENT_HEAVY` ile ağır motor eşzamanlılığı varsayılan 1'e
sınırlandı; 300 saniye kuyruk bekleme sonunda görünür degraded sonuç dönüyor.

Commit: `f2141b3`.

### 4.6 Tablolar prose dışında grid olarak taşındı

Docling'in hücre grid'i `headers` ve `rows` biçiminde `ParsedTable` alanına
taşındı. Markdown tablo da korunuyor.

Türkçe makalede 7 tablo alındı; başlık/satırlar dolu, Türkçe karakter bozulması
ve replacement character yoktu.

Commit: `b71f613`.

### 4.7 Health, karantina ve bozulmanın görünür olması

- Health ağır motorun gerçekten erişilebilir olup olmadığını raporluyor.
- Parse exception boş belge gibi görünmek yerine traceback/provenance taşıyor.
- Heavy metin corruption skorunda fast'ten düşükse fast sayfa korunuyor.
- Content hash aynı olsa bile parse provenance güncelleniyor.
- Docling sonrası MinerU için sıralı fallback zinciri hazırlandı.

MinerU motor sınıfı bugün bilinçli olarak `unavailable` dönüyor; CLI yolu gerçek
production akışında denenmedi. Bu nedenle iki çalışan ağır motor varmış gibi
iddia edilemez.

Commit: `8e661a8`.

### 4.8 C sırasında bulunan production güvenlik düzeltmeleri

Codex işaretli güncel değişiklikler:

- Router paketi import edilemiyorsa registry plain `PdfParser`'a düşüyor.
- Engine çağrısının beklenmedik exception'ı belgeyi çökertmeden degraded oluyor.
- Geçici PDF yazma hatasında dosya temizleniyor.
- Gate ham tablo/grid sinyallerini calibration için provenance'a taşıyor.
- Karantinaya alınan heavy sayfanın tablo grid'i merged sonuca sızmıyor.

Bu değişiklikler `CODEX-2026-08-18` yorumuyla işaretli ve RC1 hazırlığında
ayrı bir hardening commitine alınmıştır.

### 4.9 B kolu test durumu

- A/B commitli aşamanın tarihsel sonucu: `36 passed`.
- C güvenlik düzeltmeleriyle güncel parser hedef testi: `39 passed`.
- Python 3.10/3.11 aynı yönlendirmeyi verdiği ve parser'ın paralel kullanımda
  durumsuz kaldığı ayrıca sınandı.
- Tam repository test takımı mevcut ortamda bağımlılık/Python koleksiyon
  sorunları nedeniyle tamamlanmadı. Bu yüzden "tüm platform testleri geçti"
  denemez.

## 5. C Kolu: Korpus, Doğrulama ve Kalibrasyon

### 5.1 Korpus envanteri

Dört kaynak tek schema v2 manifestoya bağlandı:

| Kaynak | Kayıt | PDF | Metin referansı | Sayfa etiketi | C1 uygun |
|---|---:|---:|---:|---:|---:|
| OCRTurk | 180 | 180 | 180 | 180 | 180 |
| DocLayNet ICDAR | 1.016 | 0 | 0 | 498 | 0 |
| OmniDocBench | 1.651 | 0 | 0 | 1.651 | 0 |
| OpenDataLoader benchmark | 200 | 200 | 200 | 200 | 200 |
| **Toplam** | **3.047** | **380** | **380** | **2.529** | **380** |

Önemli bulgular:

- C1'e uygun 380 PDF'nin tamamı tek sayfa.
- 10 referans 200 karakterden kısa.
- DocLayNet'te public/groundtruth arasında 498 kopya görüntü var.
- DocLayNet ve OmniDocBench PDF içermediği için PDF parser kalite koşusuna
  doğrudan giremiyor.
- OCRTurk'te 107 `source.json` UTF-8 BOM taşıyor; adaptör `utf-8-sig` kullanıyor.
- OCRTurk'ün kendi eval kodunda tablo ikame maliyetinin yönü güvenilir bulunmadı;
  bağımsız C1 metriği kullanıldı.

### 5.2 Yazılan C altyapısı

| Dosya | Görev |
|---|---|
| `research/pdf-parser/scripts/korpus_kaynak.py` | Dört kaynak için ortak adaptör |
| `research/pdf-parser/scripts/korpus_envanteri.py` | Atomic manifest, özet ve otomatik uyarılar |
| `research/pdf-parser/scripts/c1_orneklem.py` | Cache/doğrulama için ortak deterministik örneklem |
| `research/pdf-parser/scripts/c1_docling_cache.py` | Docling modelini bir kez yükleyen SHA-256 cache |
| `research/pdf-parser/scripts/c1_metrik.py` | Karakter, token, uzunluk ve yapı utility metriği |
| `research/pdf-parser/scripts/c1_dogrulama.py` | Fast/heavy/routed çıktı ve puan üretimi |
| `research/pdf-parser/scripts/c2_kalibrasyon.py` | Route/table/figure eşik taraması ve karar raporu |
| `research/pdf-parser/tests/test_calibration.py` | Manifest, metrik, örneklem ve calibration testleri |

Cache ile doğrulayıcı başlangıçta farklı ilk 50 İngilizce belgeyi seçti ve 22
cache-miss oluştu. Bu hata gizlenmedi: ortak `c1_orneklem.py` yazıldı, 22 eksik
çıktı yeniden üretildi ve son koşu `230/230`, hata 0 oldu.

### 5.3 C1 kalite koşusu

Koşulan küme:

- OCRTurk: 180/180 Türkçe belge.
- OpenDataLoader: deterministik seçilmiş 50/200 İngilizce belge.
- Toplam: 230/230 başarılı parse ve üç çıktı türü.
- Her belge için `fast`, `heavy`, `routed` Markdown: 230'ar dosya.

Tüm belgelerde ortalama utility:

| Dil | Fast | Heavy | Routed |
|---|---:|---:|---:|
| Türkçe, 180 | 0,8028 | 0,8336 | **0,8354** |
| İngilizce, 50 | **0,8906** | 0,8685 | 0,8700 |

Routed çıktının bileşenleri:

| Dil | Karakter benzerliği | Token F1 | Yapı benzerliği | Utility |
|---|---:|---:|---:|---:|
| Türkçe | %83,1 | %88,9 | %61,5 | %83,5 |
| İngilizce | %81,8 | %96,8 | %70,0 | %87,0 |

Bu oranlar anlamsal doğruluk değildir. Referans Markdown'a göre karakter sırası,
token kapsamı ve yapıyı ölçer. Tablo hücresinin doğru sütuna ait olması, formül
anlamı ve alıntı sadakati için ayrı ölçüm gerekir.

Heavy motor Türkçede ortalamayı artırdı. İngilizcede fast motor ortalamada hem
heavy hem routed çıktıdan daha iyi. Tek route politikasının iki dile genellenmesi
başarılı olmadı.

### 5.4 C2 calibration sonucu

Referansı 200 karakterden kısa 9 koşu dışlandı; 221 belge kullanıldı. "Heavy
faydalı" tanımı `heavy utility - fast utility >= 0.02`.

| Ölçüm | Sonuç |
|---|---:|
| Heavy'nin faydalı olduğu belge | 74/221 |
| Mevcut route TP / FP / FN / TN | 55 / 79 / 19 / 68 |
| Route precision | 0,410 |
| Route recall | 0,743 |
| Fast-path oranı | 0,394 |

Dil kırılımı:

| Dil | Belge | Faydalı heavy | Precision | Recall | Fast oranı |
|---|---:|---:|---:|---:|---:|
| Türkçe | 172 | 68 | 0,520 | 0,765 | 0,419 |
| İngilizce | 49 | 6 | **0,088** | **0,500** | 0,306 |

Kabul kapısı `precision >= 0.60`, `recall >= 0.90`, `fast_rate >= 0.30` idi.
336 route adayı tarandı; hiçbiri üç koşulu birlikte sağlamadı. Bu nedenle:

- `candidate_not_applied = null`.
- `route_target_met = false`.
- Production `gate.py` eşikleri değiştirilmedi.

19 false-negative vakanın 18'inde şekil var; 16'sında kalite skoru 100. Yalnız
kalite eşiğini artırmak bu belgeleri ayıramıyor.

Tablo sinyali için en iyi tarama adayı:

- `inspector AND v2`.
- Precision `0,833`, recall `0,896`, F1 `0,863`.
- Holdout doğrulaması olmadığı için uygulanmadı.

Şekil adayı recall `1,0` verdi fakat precision `0,416` ve ağır-yol oranı yaklaşık
`%91,4`; maliyet açısından kabul edilmedi.

### 5.5 C3 merge ve karantina sonucu

Çalışan korumalar:

- Ağır motor sayfa üretmezse fast sayfa korunuyor.
- Ağır metin corruption skorunda daha kötüyse karantinaya alınıyor.
- Karantinadaki ağır sayfanın table grid'i structured çıktıya sızmıyor.
- Engine yok/exception olduğunda degraded provenance oluşuyor.
- Router import edilemiyorsa registry plain PDF parser'a düşüyor.

Kalan sınır: corruption critic yanlış kelimeyi, formülün anlam değişimini veya
okuma sırası bozulmasını her zaman anlayamıyor. Örneğin `data_130` fast utility
`0,5080`, heavy/routed `0,3223`; heavy çıktı semantik/yapısal olarak kötüleştiği
halde mevcut karantina bunu engelleyemedi. Buna karşılık `data_4` fast `0,5099`,
heavy/routed `0,9410`; ağır motorun büyük kazancı da gerçek.

### 5.6 C performans sonucu

Kalıcı değerlendirme worker'ında Docling:

| Dil | Ortalama | Medyan | p95 |
|---|---:|---:|---:|
| Türkçe | 5,27 sn | 4,23 sn | 13,27 sn |
| İngilizce | 2,41 sn | 1,60 sn | 6,86 sn |
| Birleşik | 4,65 sn | - | 13,14 sn |

230 belgenin toplam Docling çıkarım süresi 17,83 CPU-dakika. Bu worker modeli
bir kez yükler. Production bridge ise belge başına process/model açabildiği için
tek sayfalık çağrıda yaklaşık `8-13 sn` görülebiliyor. Benchmark hızlandırıldı,
production worker henüz hızlandırılmadı.

### 5.7 C test sonucu

- C ölçüm testleri: `11 passed`.
- Production parser hedef testleri: `39 passed`, bir `pytest-asyncio` config
  uyarısı; test hatası değil.
- `py_compile` C betiklerinde başarılı.

## 6. Bugün Sistem Gerçekte Ne Yapabiliyor

**Yapabiliyor:**

- PDF bytes alıp SmartPdfParser ile parse etmek.
- Metin katmanlı sayfaları hızlı çıkarıp sayfa bazında yönlendirmek.
- Docling erişilebiliyorsa seçili sayfalarda ağır çıkarım/OCR yapmak.
- Ağır motor yoksa veya hata verirse sayfayı kaybetmeden fast metni korumak.
- Sayfa numaralarını Markdown/passage içinde taşımak.
- Docling tablolarını Markdown ve grid olarak taşımak.
- Her sayfanın motorunu, kararı ve degradation durumunu kaydetmek.
- Acquisition zincirine parser çıktısını vermek.

**Henüz kanıtlanmadı veya yapılamıyor:**

- Ortak production route eşiğinin Türkçe ve İngilizcede güvenilir olması.
- Çok sayfalı referanslı belgelerde sayfa sınırı/merge doğruluğu.
- Gerçek taranmış, dengeli OCR korpusunda recall/precision.
- Formül, tablo hücresi ve alıntı doğruluğunun semantik olarak denetlenmesi.
- MinerU'nun production fallback olarak gerçekten çalışması.
- Tüm deep-research API, queue, DB ve worker deployment'ının canlı E2E testi.
- Production köprüsünde kalıcı model ve kabul edilebilir throughput.
- Tam repository test takımının temiz ortamda geçmesi.

## 7. Çıktılar Nerede ve Hangi Sırayla Okunmalı

1. **Bu rapor:** `reports/PDF_PARSER_V0.1.0_RC1_REPORT.md`.
2. **İnsan okunur calibration:**
   `research/pdf-parser/results/c1_rc1/calibration_report.md`.
3. **Koşu özeti:** `research/pdf-parser/results/c1_rc1/summary.json`.
4. **Tüm karar ve adaylar:**
   `research/pdf-parser/results/c1_rc1/calibration_summary.json`.
5. **Yanlış route vakaları:**
   `research/pdf-parser/results/c1_rc1/route_errors.csv`.
6. **336 route adayı:**
   `research/pdf-parser/results/c1_rc1/route_threshold_sweep.csv`.
7. **900 tablo adayı:**
   `research/pdf-parser/results/c1_rc1/table_threshold_sweep.csv`.
8. **A kolu kararları:**
   `research/pdf-parser/results/a_b_evidence/a_kolu_kosu.json`.
9. **Kapı ve critic ölçümleri:** `research/pdf-parser/results/a_b_evidence/`.
10. **İlk parser benchmark:**
    `research/pdf-parser/results/resmi_benchmark_sonuc.json`.
11. **Belge bazında tahminler ve yan yana fast/heavy/routed Markdown:** yeniden üretim sırasında
    `research/pdf-parser/out/c1_runs/<run-id>/markdown/` altında oluşur; boyutu
    gereksiz büyütmemek ve yerel yolları sürümlememek için Git'e eklenmedi.

`route_errors.csv` içindeki 98 satır "98 parse tamamen bozuk" anlamına gelmez.
Bunlar 79 gereksiz heavy yönlendirme ve 19 faydalı heavy motoru kaçırma vakasıdır.
İçerik kalitesi için yeniden üretilen Markdown ve belge bazındaki skorlar birlikte okunmalı.

## 8. Kod Nerede

### Production ve Git'te olan A/B kodu

`research-platform/src/research_platform/parsers/smart_pdf.py`
`research-platform/src/research_platform/parsers/smart_router/`
`research-platform/src/research_platform/parsers/registry.py`
`research-platform/src/research_platform/passages.py`
`research-platform/src/research_platform/acquisition.py`
`research-platform/src/research_platform/repository.py`

A/B tabanı `8e661a8` commitidir; RC1 commitleri bu tabanın üzerindedir.

### Sürümlenen C ölçüm kodu

`research/pdf-parser/scripts/korpus_*.py`
`research/pdf-parser/scripts/c1_*.py`
`research/pdf-parser/scripts/c2_kalibrasyon.py`
`research/pdf-parser/tests/test_calibration.py`

### RC1 production C güvenlik düzeltmeleri

`smart_pdf.py`, `gate.py`, `orchestrator.py`, `merge.py`, `tests/test_parsers.py`.
Bu bloklar `CODEX-2026-08-18` yorumuyla işaretlidir.

## 9. Kalan Kod ve Araştırma İşleri

### RC doğrulama durumu

1. Parser sürümü platform paket sürümünden ayrılarak `pdf-parser-v0.1.0-rc1`
   etiketiyle adlandırıldı; mevcut global sürüm uyumsuzluğu ayrı iştir.
2. C güvenlik düzeltmelerinin hedefli testleri geçti.
3. Production Docling köprüsüyle bir text-layer ve bir taranmış PDF smoke testi geçti.
4. Bilinen sınırlamalar bu raporda açıklandı.

### Kalite için P0/P1

1. İngilizce aşırı yönlendirmeyi azaltan dil/belge-tipi duyarlı sinyal.
2. Kalite 100 + şekil içeren false-negative grubunu ayıran okuma sırası/layout sinyali.
3. Geliştirme örneklerinden bağımsız holdout ile route/table doğrulaması.
4. Çok sayfalı referanslı PDF seti.
5. Gerçek taranmış Türkçe/İngilizce OCR seti.

### Production performansı ve dayanıklılık

1. Docling'i belge başına başlatmak yerine kalıcı worker/process havuzu.
2. Worker crash/timeout/restart ve memory sınırı testleri.
3. Gerçek production concurrency altında throughput ve p95 ölçümü.
4. MinerU fallback yolunu gerçekten bağlamak veya iddiadan çıkarmak.

### Deep-research kalite katmanı

1. Formül ve tablo hücre doğruluğu metriği.
2. Okuma sırası ve alıntı sadakati denetimi.
3. Semantik post-critic veya seçici ikinci değerlendirme.
4. Parser provenance'ın claim/citation çıktısında denetlenmesi.

## 10. Sürüm Kararı

İç test sürümü **`pdf-parser-v0.1.0-rc1`** etiketiyle hazırlanmıştır. Dürüst tanımı:

> Çalışan sayfa-yönlendirmeli PDF parser teknik RC; production route eşikleri
> kalibre edilmemiştir ve İngilizce genelleme başarısızdır.

Şu an production-ready etiketi dürüst olmaz. RC'nin amacı platform geliştiricisinin
gerçek PDF'lerle sistemi kullanması, provenance/fallback davranışını görmesi ve
kalan kalite çalışmalarının aynı kod tabanı üzerinde ilerlemesidir.

## 11. Yeniden Üretim Komutları

```powershell
# A/C ölçüm testleri
cd <research-platform-klonu>
$env:PYTHONPATH='src'
python -m pytest -q research\pdf-parser\tests\test_calibration.py

# Manifest
python research\pdf-parser\scripts\korpus_envanteri.py

# Docling cache
<docling-python> research\pdf-parser\scripts\c1_docling_cache.py --dataset ocrturk --limit 180
<docling-python> research\pdf-parser\scripts\c1_docling_cache.py --dataset opendataloader_bench --limit 50

# C1 ve C2
python research\pdf-parser\scripts\c1_dogrulama.py --run-id rc1 --heavy-cache research\pdf-parser\out\c1_docling_cache --dataset ocrturk
python research\pdf-parser\scripts\c1_dogrulama.py --run-id rc1 --heavy-cache research\pdf-parser\out\c1_docling_cache --dataset opendataloader_bench --limit 50
python research\pdf-parser\scripts\c2_kalibrasyon.py research\pdf-parser\out\c1_runs\rc1

# Production parser hedef testleri
python -m pytest -q tests\test_parsers.py
```

## 12. Son Cümle

Bu çalışma yalnız bir parser karşılaştırması olarak kalmadı. Gerçek production
sözleşmesine bağlı, sayfa bazında yönlendiren, ağır motoru çağıran, tabloları ve
provenance'ı taşıyan çalışan bir hat ortaya çıktı. C koşusu bu hattın Türkçede
ortalama fayda sağladığını, İngilizcede ise mevcut route kararının zarar verdiğini
gösterdi. Bu nedenle sistem **çalışıyor**, fakat calibration sonucu "eşikleri
yayınla" değil, "route sinyalini geliştir ve yeniden doğrula" oldu.
