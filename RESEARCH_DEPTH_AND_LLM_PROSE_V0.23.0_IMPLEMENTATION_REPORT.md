# Araştırma derinliği ve LLM metnini koruma — v0.23.0

Platform sürümü: `v0.23.0`

Belge sürümü: `1.0`

Tarih: `2026-09-04`

Commit: `_çalışma ağacı_`

---

## Kapsam

Bu sürüm, tek bir koşuda birlikte görünür hâle gelen dört yapısal sorunu kapatır:

1. araştırma kapsamı serbest metindi; kaynağın neden içeride veya dışarıda olduğu
   denetlenemiyordu,
2. arXiv sorguları bütün konu facet'lerini her dalda korumuyor ve seçilen 16 pasaj alt
   sorular arasında dengeli dağılmıyordu,
3. sentez doğrulaması geçerli model metnini değiştirebiliyor, başarısız olduğunda iddia
   kayıtlarını okuyucu metni gibi birbirine ekleyebiliyordu,
4. kullanıcıya verilen toplama süresi arama ve edinme dışındaki işlem sürelerini de
   tüketiyordu.

Değişiklik şema göçü içermez. Yeni alanlar protokol, kaynak metadata'sı, koşu state'i ve
manifest içindeki geriye uyumlu JSON alanlarıdır. Eski koşular değiştirilmez; kapsam rolü
olmayan eski kaynaklar açık bir yeniden oynatmada eski geniş kabul davranışını korur.

---

## Başlangıç kanıtı

İncelenen koşu: `01M1KKJPQ0CARBG2EMGB4X6EYN`.

| Ölçüm | Gözlenen değer |
|---|---:|
| Durum | `completed_incomplete` |
| Kaynak | 232 |
| İddia | 42 |
| Raporlanabilir iddia | 28 |
| Aday pasaj | 4.253 |
| Seçilen pasaj | 16 |
| Soru dalı | 6 |
| Sentez teması | 5 |
| Zorunlu onarıma düşen tema | 5/5 |

Karşılaştırılabilir önceki koşu 123 kaynak ve 161 iddia üretmişti. Semantic Scholar 429
yanıtları ve iddia çıkarımındaki JSON hataları kayıpta pay sahibiydi; fakat ana sınırlar
sağlayıcı arızası değildi: 4.253 pasajdan yalnız 16'sının seçilmesi, soru dalları arasında
dengesiz dağılım, kapsamı gevşeten sorgular ve geçerli model metninin onarım/fallback
yollarında kaybolmasıydı.

---

## Yapılandırılmış kapsam sözleşmesi

`ResearchScopeCriteria`, plan onayından önce aşağıdaki sınırları ayrı alanlarda tutar:

- zorunlu konu, anatomi/modalite, görev ve çıktı facet'leri,
- açık dışlama ölçütleri,
- birincil kanıt ile yalnız benchmark/değerlendirme desteği arasındaki rol ayrımı.

Kaynak rolleri:

| Rol | Okuyucu raporundaki kullanım |
|---|---|
| `primary_in_scope` | Ana bulgu, uzlaşı ve sonuçlarda kullanılabilir |
| `supporting_benchmark` | Yalnız metrik, benchmark ve değerlendirme bağlamında kullanılabilir |
| `near_scope` | Katalog ve denetimde görünür; sentezi beslemez |
| `excluded` | Neden dışlandığıyla kaydedilir; sentezi beslemez |

Model rolü tek başına karar değildir. Kod, her zorunlu facet için metinde doğrulanabilir
kanıt ve her dışlama için tamamlanmış karar arar. Eksik veya doğrulanamayan değerlendirme
`near_scope` olur; kanıtlanmış dışlama her zaman `excluded` üstünlüğü taşır. Supporting
benchmark rolü yalnız görev facet'ini atlayabilir. Böylece modelin kendinden emin bir
etiketi kapsam kapısını açamaz.

Gerçekçi göğüs BT regresyon fixture'ı 17 örnek taşır: 11 birincil, 2 supporting, 2 açık
dışlama (PET/CT ve 2D), 2 eksik anatomi nedeniyle near-scope. Sonuç testte birebir bu
dağılımla doğrulandı.

Alt sorular artık `SQ01`, `SQ02`, ... kimlikleriyle; araştırma metni, eşleştirme metni ve
rapor başlığı ayrı roller olarak saklanır. Plan reddedilirse onaylanmamış alt sorular
yeniden ayrıştırılır; eski taslağın yanlışlıkla kullanıcı girdisi sayılması engellendi.

---

## Sorgu ve pasaj derinliği

### arXiv facet dalları

Sorgu derleyicisi anatomi/modalite, görev ve çıktı facet gruplarını önceden derler.
`ArxivConnector` bu grupları değiştirmeden her sorgu dalına taşır; gönderilen sorgunun
echo'su kaynak metadata'sında kalır. Göğüs BT örneğinde bütün arXiv dallarının bütün
zorunlu facet'leri koruduğu test edildi.

### Dengeli seçim

Global pasaj sınırı 16'dan 48'e çıkarıldı; kaynak başına üst sınır 2'dir. Seçim önce soru
dalları arasında round-robin kota uygular, ardından kalan kapasiteyi skor sırasıyla ve
kaynak çeşitliliğini koruyarak doldurur. Küçük korpusta kapasite boş kalırsa çeşitlilik
sınırı ancak bütün kaynaklara fırsat verildikten sonra gevşetilir.

Sentetik regresyon testi 48 pasajı, bütün soru dallarını ve kaynak başına 2 tavanını
doğrular. Sabit gerçek veri yeniden oynatmasının sonucu ayrıca aşağıdadır.

---

## Sentez: metni koru, kusuru görünür kıl

Okuyucuya gösterilen model metni artık doğrulama tarafından yeniden yazılmaz. Kaynak
allow-list'i, citation, dil, alan örtüşmesi ve güçlü iddia kontrolleri uyarı üretir;
geçerli JSON içindeki dizeler karakter karakter korunur. `generation_status` ve
`validation_warnings` koşu olayına, manifest'e, panel/Telegram yüzeylerine ve Word yöntem
ekine taşınır.

Model sağlayıcısı bütünüyle kullanılamazsa sistem bunu açıkça söyler. Claim ledger
satırları deterministik olarak birbirine eklenip model senteziymiş gibi ana anlatıya
dönüştürülmez. Denetlenmiş iddia ve kanıt kayıtları eklerde varlığını sürdürür.

Uzlaşı için en az iki bağımsız `primary_in_scope` kaynak gerekir; supporting benchmark
kaynakları uzlaşı sayısını yükseltemez. Supporting kanıt yalnız metrik/değerlendirme
temalarına girebilir. Yalnız anahtar sözcük taşıyan, yüklemsiz liste parçaları raporlanabilir
iddia sayılmaz.

### Bilinçli olarak geçersiz kılınan eski kararlar

- `previous_reports/SYNTHESIS_REPORT_PIPELINE_V0.8.0_IMPLEMENTATION_REPORT.md` içindeki
  “bozuk çıktı → onarım → deterministik güvenli dönüş” okuyucu metni için kaldırıldı.
- v0.20.1'deki özet/tema onarımı ve v0.21.0'daki dil süpürmesinin metni değiştiren kısmı
  kaldırıldı.

Yeni karar: doğrulama ve kanıt kapıları kalır, fakat modelin okuyucu metni uyarıyla birlikte
aynen korunur. Deterministik hesaplar coverage, seçim, iddia uygunluğu ve denetim kayıtları
için kullanılmaya devam eder; anlatı üretme görevi üstlenmez.

---

## Toplama bütçesi

`max_wall_minutes` artık yalnız dış kaynak bekleme süresini ölçer: `SEARCH` başlangıcında
aktif sayaç açılır, `ACQUIRE` sonunda süre biriktirilir. Planlama, normalize etme,
embedding, iddia çıkarımı, denetim, sentez ve export bu bütçeyi tüketmez. Sayaç state'te
saklandığı için checkpoint sonrası devamda aynı toplam korunur.

---

## Sabit veri yeniden oynatması

Eski koşu ve artifact'ları değiştirilmedi. Aynı 4.253 saklı pasaj ve aynı 28
raporlanabilir iddia, çalışan worker kapsayıcısında yeni kodla bellekte yeniden oynatıldı.
Dense + lexical seçim kullanıldı.

| Ölçüm | Önce | v0.23.0 yeniden oynatma |
|---|---:|---:|
| Seçilen pasaj | 16 | 48 |
| Temsil edilen soru dalı | seçilen listede dengesiz | 6/6 |
| Farklı kaynak sürümü | — | 32 |
| Bir kaynaktan en çok pasaj | — | 2 |
| Temalara gösterilen iddia | 28/28 | 28/28 |
| Tema üretim kökeni | 5/5 `repair_forced_grounding` | LLM metni korundu |
| `generated_by_llm` | `false` | `true` |
| Üretim durumu | eski alanda yok | `complete_with_warnings` |
| Doğrulama uyarısı | eski alanda yok | 27 |

Altı dalda eşleşen pasaj sayıları sırasıyla 10, 9, 9, 8, 10 ve 8 oldu. Aynı pasaj birden
fazla dala eşleşebildiği için toplam dal eşleşmesi 48'den büyük olabilir. Eski koşudaki 232
kaynak v0.23.0 öncesi olduğu için rol metadata'sı taşımaz; bu nedenle eski koşudan anlamlı
bir in-scope oranı türetilmedi. Kapsam rolü oranı uydurmak yerine yukarıdaki 17 vakalık
etiketli fixture ile doğrulandı.

Uyarı sayısı başarısızlık değildir: yeni sözleşmenin amacı model metnindeki şüpheli dil,
atıf veya biçim özelliklerini görünür kılarken metni gizlice değiştirmemektir.

---

## Doğrulama

| Kapı | Sonuç |
|---|---|
| Hedefli regresyon paketi | `154 passed in 13.60s` |
| Ubuntu tam paket (`TESTING=true`) | `876 passed, 1 warning in 67.91s` |
| Ruff, değişen dosyalar | yeni ihlal yok; 54 taban → 34 güncel |
| Docker build | başarılı |
| API image doğrulaması | `0.23.0`, pasaj sınırı `48`, kaynak sınırı `2` |
| Worker image doğrulaması | `0.23.0`, pasaj sınırı `48` |
| Telegram image doğrulaması | `0.23.0` |

Tek pytest uyarısı `tests/test_agent_gateway.py` içindeki mevcut Starlette deprecation
uyarısıdır. Windows'taki tam toplama, Unix'e özgü `resource` modülünü doğrudan import eden
`scripts/benchmark_thread_scaling.py` nedeniyle başlamadı; zorunlu kapı Linux/Ubuntu
makinesinde eksiksiz geçti.

Son kod değişikliğinden sonra tam paket çalıştırıldı. Bu rapor ve changelog yalnız belge
değişikliği olduğundan test paketi yeniden çalıştırılmadı.

---

## İşletim notları

- `docker compose up -d --build` ile API, worker, MCP gateway ve ortak uygulama image'ları
  yenilendi.
- Profil arkasındaki bot ayrıca
  `docker compose --profile telegram up -d --build telegram-bot` ile yenilendi.
- Container içinden sürüm ve ayarlar doğrulandı.
- Branch `developments-supplementer` olarak kaldı.
- Commit ve push yapılmadı.
