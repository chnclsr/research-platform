# Açık İşler

`developments-supplementer` branch'inde bilinen, henüz kapatılmamış işler. Ayrıntılı gerekçeler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) içindedir;
burası tek liste hâlinde durum tablosudur.

Son güncelleme: `2026-09-14`

Hiçbiri sistemi bozmuyor; hepsi bilinçli olarak ertelendi. Ölçümler bu oturumda alındı ve
tekrar ölçmeye gerek kalmaması için buraya yazıldı.

## Öncelik özeti

| # | İş | Etki | Aciliyet |
|---|---|---|---|
| 1 | MinIO'da hiç temizlik yok — sınırsız disk büyümesi | Zamanla diski doldurur | **Yüksek** |
| 2 | Yedekler kaynakla aynı diskte | Disk arızasında ikisi de gider | **Yüksek** |
| 4 | Resume sonrası ham veri kaybı | Kesilen koşuda figür analizi çalışmaz | Orta |
| 5 | `raw_content` yedekliliği — geri yükleme yolu yok | Yedek var, kurtarma test edilmemiş | Düşük |
| 6 | MinIO anahtar düzeni tutarsız | Temizlik yazmayı zorlaştırır | Düşük |
| 7 | Teslimat ZIP'leri hiç temizlenmiyor | Yavaş büyüme | Düşük |
| 8 | crawl4ai varsayılan ayarlarla | Lazy-load içerik kaçar | Düşük |
| 9 | `_direct` 400 karakter eşiği | SPA kabuğu "başarılı" sayılabilir | Düşük |
| 10 | Eklenti B — yetenek pazarlığı | Gereksiz ayrıştırma maliyeti | Bekliyor |
| 11 | Eklenti C — `parse_document` MCP aracı | Ajanın teşhis yeteneği | Bekliyor |
| 12 | Panel `native` modda hâlâ zararlı | Yanlış modda çakışma | Belgelendi |
| 13 | Yedekleme çıktısı dosya sistemi düzeyinde ayrılmış değil | Aynı makinedeki kullanıcılar tüm raporları okuyabilir | Orta |
| 14 | Tek bir belgenin kaydı tüm koşuyu düşürüyor | Toplanan her şey kaybolur | **Yüksek** |
| 15 | Kanıt çıkarımında bütçe karakterle ölçülüyor | Latin dışı metinde 0 iddia | **Yüksek** |
| 16 | CPU/GPU aynı PDF'ten farklı `content_hash` üretir | İki kurulumda iki sürüm | Düşük |
| 17 | Docling imajı 11,9 GB, geçişli bağımlılıklar kilitsiz | Disk + build kayması | Orta |
| 18 | Docling + Ollama kartı aynı anda paylaşınca ne olur, denenmedi | Olası VRAM thrash | Orta |
| 19 | Anonim Jina Reader dış servis sınırı | 429 riski + hedef URL üçüncü tarafa gider | Düşük |
| 20 | Metadata'sız GitHub adayında boyut sınırı klon sonrası | Büyük repo geçici ağ/disk tüketebilir | Düşük |
| 21 | Tam-depo Ruff tabanı 1.053 ihlal taşıyor | Yeni lint hataları tarihsel gürültüde saklanabilir | Orta |
| 22 | `_acquire_node` beklenmeyen istisnayı izole etmiyor | Tek bağlayıcı hatası ACQUIRE adımını düşürebilir | Orta |
| 23 | Edinim testi aralıklı düşüyor, tetikleyici bilinmiyor | Commit kapısı sebepsiz kapanabilir | Orta |
| 24 | Kanalsız koşu plan kapısında asılı kalabilir | API/Langflow koşusu tamamlanamaz | Orta |
| 25 | Panelde çağıranı olmayan `POST /api/runs` route'u | Yanıtlanamayan koşu üretebilir | Düşük |
| 26 | `research_runs` sütunları `json`, model `JSONB` türetiyor | Sorgular sessizce üretimde kırılır | Orta |
| 27 | v0.18.0 iki flag'i ölçülmedi | Kapalı kaldıkça kazanç da yok | Orta |
| 28 | Altı sabit probe stratejisi hâlâ duruyor | İki kod yolu birlikte bakılıyor | Düşük |
| 29 | Blueprint arşivi yok | Probe deneyimi koşular arasında birikmiyor | Bekliyor |
| 30 | İddia çevirisinde sayı sırası: 8/31 iddia İngilizce kalıyor | Türkçe raporda İngilizce bulgu başlıkları | Orta |
| 35 | Free-threaded Docling production pinleri `cp314t` zincirinde engelli | Kabul kriteri passed değil, upstream wheel bekliyor | Belgelendi |
| 39 | Duraklatılan koşunun bekleme süresi toplama bütçesine yazılıyor | Preempt edilen koşu bütçesini uyurken tüketir | Orta |
| 40 | Kanıt tabanı 18 kaynağa iniyor: 231 iddianın 230'u tek kaynaklı kalıyor | Kanıt notu tabanda, mutabakat yapısal olarak yazılamıyor | Yüksek |
| 43 | Docker Desktop oturum açılmasını gerektiriyor | Windows sunucu reboot sonrası başsız ayağa kalkamaz | Orta |
| 44 | Session 0'dan kimlik deposuna erişilemiyor | `docker build` ve `git push` uzak oturumdan çalışmıyor | Orta |
| 45 | Testler gerçek `.env`'i okuyordu | Süit artık hermetik; dotenv kapatıldı | Çözüldü |
| 47 | pdf-inspector 1.19.0 — kod hazır, canlıya geçiş bekliyor | Hızlı yol metni iyileşiyor; 152/380 belgenin `content_hash`'i bir kez kayar | Düşük |

---

## 1. MinIO'da hiç temizlik yok

**Durum:** Koşu bazında silme, yaş bazında retention, envanter — hiçbiri yok. `store.delete()`
yalnız `exporter.py`'de tek nesne için, yeniden export sırasında kullanılıyor. `list_objects`
hiç kullanılmıyor.

**Ölçüm:** 10 kaynaklı 12 dakikalık koşu ≈ 45.5 MB MinIO + 9.7 MB Postgres, yani kaynak
başına ~5.5 MB. Günde 3 koşu → ayda ~1.5 GB, hiç azalmadan.

**Neden ertelendi:** Otomatik retention, ürünün provenance/reproducibility vaadiyle çelişiyor;
link rot nedeniyle silinen bir snapshot geri getirilemez. Bilinçli karar.

**Yapılacak:** Önce 6. maddeyi (anahtar düzeni) çöz, sonra `ObjectStore.delete_prefix()` ve
koşu bazında **elle** temizlik ekle. Otomatik retention en son ve varsayılan kapalı.

## 2. Yedekler kaynakla aynı diskte

**Durum:** `scripts/.env` içindeki `RESEARCH_OUTPUT_DIR` şu an `%USERPROFILE%\ResearchBackups`
— kaynakla aynı C: diski.

**Etki:** Kurulum MinIO bozulmasına, container/API sorunlarına ve yanlışlıkla koşu silinmesine
karşı korur; **disk arızasına veya makine kaybına karşı korumaz.**

**Yapılacak:** Asıl sunucuda farklı bir sürücüye veya ağ paylaşımına yönlendir. Mekanizma
hazır, sadece hedef değişmeli. Güncelleme yolu `AGENTS.md`'de yazılı (setup'ı yeniden
çalıştırma — `-InitializeOnly` tuzağı).

## 4. Resume sonrası ham veri kaybı

**Durum:** NORMALIZE checkpoint'inden devam ettirilen koşularda belgelerin ham gövdesi
checkpoint'te bulunmaz (5. bölümdeki temizleme kararının bilinçli bedeli).

**Sonuçları:** MinIO snapshot'ı ham dosya yerine çıkarılmış metni tutar ve **`.pdf` uzantılı
ama içi düz metin olan** bir nesne oluşur; `source_versions.raw_content` boş kalır; PDF figür
analizi o koşuda çalışmaz (`figure_analysis.py` `if not version.raw_content: return []`).

**Tetikleyici:** Worker yeniden başlatma tüm `RUNNING`/`QUEUED` koşuları yeniden kuyruğa
alıyor — geliştirme sırasında her `up -d --build` bunu yapıyor.

**Yapılacak:** Ham gövdeyi `content_hash` anahtarlı ayrı bir staging tablosunda tutup
checkpoint'e hiç sokmamak. Alternatif (snapshot'ı ACQUIRE'a taşımak) elenen belgeler için
çöp snapshot üretir.

## 5. `source_versions.raw_content` — bilinçli yedeklilik, kaldırılmayacak

**Durum:** Ham gövde iki yerde: MinIO snapshot'ı (`provenance.raw_snapshot_key`) ve bu TEXT
sütunu. **Bu bir israf değil, tasarım kararıdır** ve öyle kalmalıdır.

**Neden:** İki kopya farklı ortamda ve farklı formatta duruyor — MinIO host klasöründe
(`data/minio`) erasure-coded düzende, Postgres named volume'de (VHDX içinde) base64/metin
olarak. MinIO kendi on-disk formatını bozarsa (`xl.meta` hasarı) Postgres kopyası
etkilenmez ve arşiv oradan yeniden üretilebilir.

Kopya **kayıpsızdır**: HTML `response.text` olarak, PDF base64 olarak saklanıyor; MinIO'daki
nesne bunun aynen çözülmüş hâli (`pipeline.py`, `snapshot = raw_content or content`).

**Gerekçenin sınırı — önemli:** Bu yedeklilik "MinIO container'ına bir şey olursa" senaryosu
için değildir. Bind mount'a geçildikten sonra (6. bölüm) container zaten kullanılıp
atılabilir; silinmesi, çökmesi veya `docker compose down -v` veriyi kaybettirmez. Koruduğu
gerçek senaryolar: **format bozulması**, klasörün yanlışlıkla silinmesi, fidye yazılımı.

**Kapsamı:** Postgres kopyası yalnız **kaynak snapshot'larını** yedekler. MinIO'daki 235
nesnenin dağılımı:

| Tür | Nesne | Boyut | Postgres yedeği |
|---|---|---|---|
| Kaynak snapshot | 62 | 36.9 MB | ✅ `source_versions.raw_content` |
| Export çıktısı | 142 | 152.7 MB | ❌ `export_artifacts` yalnız ad/anahtar tutuyor |
| Figür görseli | 31 | 4.5 MB | ❌ `figure_observations` yalnız `image_key` tutuyor |

Export çıktıları ve figürler koşu bazlı yedek ZIP'lerinde bulunur (2. madde).

**Açık kalan:** Geri yükleme yolu **yok**. Postgres'ten okuyup MinIO'yu dolduran tek satır
kod bulunmuyor; tüm `store.put` çağrıları ileri yönde. Felaket anında script baskı altında
yazılmak zorunda kalır ve test edilmemiş bir geri yükleme yolu zayıf garantidir. Yazılması
hâlinde hedef anahtar tahmin edilmez — `provenance.raw_snapshot_key` 62/62 kayıtta dolu.

**Yan not:** `raw_snapshot_key` yazılıyor ama hiçbir yerden okunmuyor; MinIO snapshot'ları
şu an salt-yazılır arşiv. Geri yükleme yolu yazılırsa bu alan da işlevsel hâle gelir.

## 6. MinIO anahtar düzeni tutarsız

**Durum:**
```
{run_id}/sources/{hash}.{ext}          ← kaynak snapshot'ları
runs/{run_id}/figures/{sid}/{h}.png    ← figürler
runs/{run_id}/{ad}                     ← export çıktıları
```
Tek bir önek bir koşunun tüm verisini kapsamıyor.

**Neden önemli:** 1. maddedeki temizliği yazan kişi tek prefix ile silmeye kalkarsa diğer
yarısı kalır ve fark edilmez.

**Yapılacak:** `pipeline.py`'de snapshot anahtarını `runs/{run_id}/sources/...` yap; eski
önekli nesneler için tek seferlik süpürme. Risk düşük — `raw_snapshot_key` okunmuyor.

## 7. Teslimat ZIP'leri hiç temizlenmiyor

**Durum:** `gateway-deliveries` named volume'ünde her `/get` ve her eşitleme bir ZIP
bırakıyor; `gateway_client.py`'de `unlink`, `rmtree` veya yaş sınırı yok.

**Etki:** Yavaş ama sürekli büyüme, üstelik VHDX içinde (bind mount değil).

## 8. crawl4ai varsayılan ayarlarla çalışıyor

**Durum:** İstek gövdesi `{"urls": [url], "browser_config": {"headless": True}}` — `wait_for`,
`js_code`, scroll, `delay_before_return_html` yok.

**Etki:** Yüklenme tamamlandığı andaki DOM alınıyor; lazy-load ve sonsuz kaydırma içeriği
kaçıyor.

## 9. `_direct` 400 karakter eşiği SPA kabuğunu geçirebilir

**Durum:** `_direct` ayrıştırılmış metin 400 karakterden kısaysa crawl4ai'ye düşüyor. Nav +
footer + çerez uyarısı bu eşiği geçen bir SPA kabuğu "başarılı" sayılır ve tarayıcı hiç
denenmez — sessizce boş içerik toplanır.

## 10. Eklenti B — protokolden yetenek pazarlığı

Protokol ne istediğini beyan eder (`needs: ["tables"]`), registry o yeteneği sunan
parser'ları seçer/yapılandırır. Deterministik ama hedefe duyarlı.

**Neden bekliyor:** Tasarrufu 3. maddedeki ölçülen 6.7 kat maliyetten geliyor; o maliyet
henüz kodda yok. PDF tablo çıkarımı eklendikten sonra anlamlı.

## 11. Eklenti C — `parse_document` MCP aracı

Ajanın (Claude Code / Codex) bir kaynağı istediği parser'la yeniden ayrıştırıp sonucu
görmesi.

**Neden bekliyor:** Yeni bir yetenek açmıyor — `read_research_raw_data(dataset="sources")`
zaten `raw_content`'i döndürüyor. Kazandırdığı ergonomi ancak **tür başına ikinci parser**
eklendiğinde anlam kazanır; bugün tek parser varken aynı çıktıyı verir.

## 12. Panel `native` modda hâlâ zararlı

**Durum:** `CONTROL_PANEL_DEPLOYMENT=docker` ile çözüldü, ancak ayar `native` bırakılırsa
"Başlat" düğmesi port çakışmasına ve aynı ARQ kuyruğunda ikinci bir worker'a yol açıyor.

**Durum: belgelendi**, kod değişikliği planlanmıyor. `AGENTS.md`'de kritik tuzak olarak
yazılı.

---

## 13. Yedekleme çıktısı dosya sistemi düzeyinde ayrılmış değil

**Kısmen kapandı (v0.10.1).** `scripts/sync-research-reports.ps1` artık paylaşılan jetonla
değil, **adı belli bir yönetici API anahtarıyla** çalışıyor (`yedekleme-senkron`). Kazanç:
erişim iz sürülebilir, tek başına iptal edilebilir ve `list-keys` çıktısında son kullanım
tarihi görünür. Seçenek (b) — "yedeklemeyi açıkça yönetici işlevi saymak" — bilinçli olarak
seçildi.

**Kalan sınır:** yönetici anahtarı olduğu için paketler hâlâ **tüm** koşuları kapsıyor ve
hepsi tek bir `RESEARCH_OUTPUT_DIR` klasörüne iniyor. Zamanlanmış görevi çalıştıran makinede
oturum açan biri, başkalarının raporlarına dosya sistemi üzerinden erişebilir.

Yapılacak: çıktı klasörünü NTFS izinleriyle yalnız o yöneticiye kısıtlamak. Alternatif olarak
kişi başına anahtar + kişi başına klasör, ama o zaman başkalarının raporları yerel yedeğe
hiç inmez — disk arızası senaryosunda (2. madde) kapsam daralır.

Ayrıntı: kökteki raporun 14. bölümü ve
[MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md](MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md)
"Kalan sınırlar".

## 14. Tek bir belgenin kaydı tüm koşuyu düşürüyor

**Durum:** `pipeline.py` NORMALIZE içinde belgeleri sırayla `repo.save_document()` ile
yazıyor ve bu çağrı korumasız. Tek bir belgede veritabanının reddettiği bir şey olması —
19 Ağustos'ta yakalanan `0x00` baytı gibi — o turdaki **bütün** belgeleri götürüyor: görev
düşüyor, koşu `failed` oluyor, o ana kadar toplanan kaynaklar geri alınıyor.

**Ölçüm:** 19 Ağustos 2026, koşu `01M0CEKFE0T6BJ0BK5MM7XXWYS`. Bir DOI'nin JPEG ek dosyasına
çözülmesi tek başına koşuyu FAILED yaptı. Kök neden düzeltildi (raporun 16. bölümü), ama
**kırılganlığın kendisi duruyor** — bir sonraki beklenmedik içerik aynı sonucu verir.

**Neden ertelendi:** Connector hataları bilinçli olarak sessiz (`pipeline.py` try/except),
belge kaydı ise değil. İkisini aynı hizaya getirmek "kaç belge sessizce düştü" sorusunu
doğuruyor; sayaç ve olay olmadan yapılırsa gözlemlenemeyen kayıp üretir.

**Yapılacak:** `save_document()` çağrısını belge başına `try/except` ile sar, düşen belgeyi
`document_save_failed` olayı olarak yaz (url + hata sınıfı) ve koşuyu sürdür. Olay zaten
panelin aşama tablosuna düşer, yani kayıp görünür olur.

## 15. Kanıt çıkarımında bütçe karakterle ölçülüyor

**Durum:** `extract_claims()` istemi karakterle sınırlıyor (`content[:16000]`,
`neighbor_context[:4000]`). Platformun token sayacı Latin dışı metinde ciddi biçimde eksik
sayıyor, dolayısıyla İngilizce'de rahat sığan sınır Türkçe/Kiril metinde `num_ctx`'i
(8192) taşırıyor. Ollama istemi kırpıyor, model bozuk çıktı üretiyor.

**Ölçüm:** Aynı koşuda EXTRACT_EVIDENCE'ın 8 LLM çağrısının 7'si tam `prompt_tokens = 8192`
tavanına dayandı; biri `num_predict` sınırında `length` ile kesildi. Sonuç: `LLM did not
return valid JSON` ve iki turda **0 iddia**. Pasajların kendisi normaldi (ortalama 628,
azami 700 token).

**Not (19 Ağustos):** Araştırma artık İngilizce yürüyor (raporun 19. bölümü), yani soru,
alt sorular ve iddia metni Latin dışı karakter taşımıyor ve tavana dayanma baskısı azaldı.
Sorun **kapanmadı**: pasajlar hâlâ kaynağın kendi dilinde ve Türkçe/Kiril bir kaynakta aynı
taşma yeniden yaşanır. Bütçe hâlâ karakterle ölçülüyor.

**Yapılacak:** İstemi token bütçesiyle kur: `llm_context_tokens` eksi çıktı payı eksi sistem
istemi kadar bütçe ayır, hedef pasaj ile komşu bağlamı bu bütçeye göre kırp. Ölçüm için
gerçek tokenizer yoksa Latin dışı karakter oranına göre düzeltilmiş bir tahmin bile
yeterli. `done_reason = "length"` da bir olay olarak yazılmalı — bugün sessiz.

---

## 16. CPU'lu ve GPU'lu makine aynı PDF'ten farklı `content_hash` üretir

**Durum:** `docling` servisi cihazı beyan edilen parametre olarak alıyor
(`DOCLING_DEVICE`). Aynı belgeyi GPU'lu ve CPU'lu iki kurulum ayrıştırdığında metin birebir
aynı olmuyor, dolayısıyla aynı kaynak iki kurulumda iki ayrı `SourceVersion` satırı
oluyor.

**Ölçüm:** Kendi korpusumuzda, aynı makinede tek değişken cihazken 261 sayfanın 7'si
farklı; 6'sı kozmetik, 1'i gerçek kayıp (`gpt3` s.50'de bir markdown tablosu). Kaynak:
`research/pdf-parser/results/gpu/README.md`. 2026-08-24'te 12 belgelik korpusta da
görüldü: `ornek_4` CPU'da 10 tablo / 61.144 karakter, GPU'da 7 tablo / 62.313 karakter.
Aynı cihazda tekrar **bayt bayt aynı** (3 koşu, tek `content_hash`) — sorun
tekrarlanabilirlik değil, taşınabilirlik.

**Neden ertelendi:** Kaçınılmaz; docling'in CPU ve CUDA çekirdekleri farklı sonuç veriyor.
Gizlenmiyor: hangi cihaz ve hangi build ürettiyse `parse_provenance.engine_devices` ve
`engine_build` içinde duruyor.

**Yapılacak:** Tek makineli kurulumda etkisi yok. Birden çok worker'lı bir kuruluma
geçilirse ya hepsi aynı cihaz olmalı, ya da tekilleştirme cihazı da hesaba katmalı.

## 17. Docling imajı 11,9 GB ve geçişli bağımlılıkları kilitli değil

**Durum:** İki ayrı sorun, aynı dosyada. Biri (mükerrer katman) 2026-08-24'te kapatıldı.

**Ölçüm (cu132 yapısı):** `site-packages` 5,4 GB (`nvidia/` 2,6 · `torch/` 1,2 ·
`triton/` 0,69), model ağırlıkları 1,4 GB. Docker Desktop'ın sanal diski bir kez
büyüdükten sonra küçülmüyor.

**Düzeltildi — mükerrer ağırlık katmanı (~1,4 GB).** `chown -R` ağırlıkların tam bir
kopyasını yeni katmana yazıyordu: overlay2 kopyala-yaz ve alt katmandaki bir dosya için
"yalnız izin değişti" diye bir kaydı yok, sahiplik değişikliği dosyanın tamamını yukarı
kopyalatıyor. Kullanıcı artık indirmeden **önce** oluşturuluyor, indirme `USER docling`
altında koşuyor ve `chown` yalnız iki boş dizine uygulanıyor. `useradd` katmanı
**1,44 GB → 81,9 kB**, imaj **14,6 → 11,9 GB**. Çıktının değişmediği doğrulandı: aynı
belgenin `content_hash`'i rebuild öncesi ve sonrası aynı (`709c8164…`).

**Bilinçli olarak yapılmadı — `CodeFormulaV2` (611 MB).** `DocumentConverter()`
varsayılanında formül/kod zenginleştirme kapalı olduğu için bugün kullanılmıyor, ama
ileride açılma ihtimaline karşı imajda bırakıldı (kullanıcı kararı, 2026-08-24). Not:
`HF_HUB_OFFLINE=1` yüzünden, imajda **olmayan** bir modeli gerektiren bir ayar açılırsa
sonuç sessiz bir indirme değil sert bir hata olur — yani "ne indiriliyor" listesi
davranışın parçası.

**Kilit tarafı hâlâ açık:** Çıktıyı belirleyen paketler (docling ve alt paketleri,
transformers, tokenizers, safetensors, pypdfium2, pillow, opencv, shapely, scipy, numpy,
rapidocr) tam sabitli; kalan geçişli bağımlılıklar build anında çözülüyor, yani iki build
arasında sürüm kayması mümkün. Windows'ta alınan bir `pip freeze` Linux'a taşınamıyor;
doğru kilit kurulan imajın içinden üretilmeli:

```
docker compose run --rm --no-deps --entrypoint pip docling freeze > docker/docling-lock-linux.txt
```

ve sonraki build'lerde `-c` ile geçirilmeli.

## 18. Docling ile Ollama'nın kartı aynı anda paylaşması denenmedi

**Durum:** Rezervasyonun kendisi **ölçüldü ve kondu**. `capacity._gpu_slots()` artık
`docling_vram_reserve_gb`'yi headroom'dan düşüyor; bu makinenin `.env`'inde `1.6`.
Kodda varsayılan `0.0` kalıyor — başka bir kurulumda ölçülmeden bir sayı koymak,
tahmin etmekle aynı şey.

**Ölçüm (2026-08-24, RTX 4060 Laptop, 8188 MiB):**

| Durum | Kartta kullanılan |
|---|---|
| Docling servisi kapalı | 46 MiB |
| Servis ayakta, boşta (modeller yüklü) | 767 MiB |
| 38 sayfalık dönüştürmenin tepesinde | 1673 MiB |

Yani servisin payı boşta ~721 MiB, tepe ~1,6 GB. Rezervasyon tepe değere konuldu.

**Kalan iş:** Ollama'nın modeli yerleşikken eşzamanlı bir dönüştürme denenmedi. 8 GB'lık
kartta LLM + embedding + docling dar bir alan ve `model_lease()` docling'i kapsamıyor;
thrash olup olmadığı ancak ikisi aynı anda çalışırken görülür. Ölçümdeki 46 MiB tabanı,
Ollama'nın o an hiçbir modeli yerleşik tutmadığını da gösteriyor — yani bu ölçüm en iyi
hâli, en kötü hâli değil.

## 19. Anonim Jina Reader dış servis sınırı

**Durum:** Jina Reader anahtarsız kullanılıyor ve yalnız `direct`, AgentSearch ile
Crawl4AI başarısız olduktan sonra çağrılıyor. Jina'nın kendi belgesine göre anonim trafik
en sıkı kota havuzundadır; yoğun kullanımda 429 görülebilir. Ayrıca hedef URL ve Jina'nın
o URL'den aldığı içerik dış bir hizmetin işleme sınırına girer.

**Mevcut koruma:** Hedef URL önce SSRF/public-IP kontrolünden geçer; hedef site çerezleri,
Authorization başlığı veya başka kimlik bilgileri Jina'ya aktarılmaz. Jina hatası koşuyu
düşürmez, Scrapling'e devam eder. Dış çağrı `ENABLE_JINA_READER_FALLBACK=false` ile
kapatılabilir; `JINA_READER_URL` self-host Reader'a çevrilebilir.

**Yapılacak:** Gerçek koşu telemetrisinde anlamlı bir 429 oranı görülmeden credential
eklenmeyecek. Kota sorun olursa önce self-host endpoint, gerekirse ayrıca opsiyonel Jina
API anahtarı desteği değerlendirilecek.

## 20. Metadata'sız GitHub adayında boyut sınırı klon sonrası

**Durum:** GitHub connector'ından gelen adaylarda API'nin `size` alanı kullanılarak
100 MiB sınırı klondan önce uygulanıyor. Başka bir connector'ın bulduğu GitHub URL'sinde
bu metadata yoksa `git clone --depth 1` checkout boyutunu önceden güvenilir biçimde
bilmiyor; sınır klon tamamlandıktan sonra `.git` dahil dizin boyutunda uygulanabiliyor.

**Mevcut koruma:** Klon 90 saniyede kesiliyor, alt modüller alınmıyor, Git LFS smudge
kapalı ve checkout 100 MiB'ı aşınca içerik işlenmeden reddediliyor. Başarı, hata, timeout
ve iptal yollarında geçici dizin temizleniyor. Bu sınır kalıcı veri şişmesine yol açmaz,
ama tek çağrı sırasında ağ ve geçici disk tüketimi yaratabilir.

**Yapılacak:** Gerçek koşularda bu sınıra çarpan repository görülürse klondan önce
GitHub repository metadata'sı sorgulanacak; kimliksiz API kotasını tüketmemek için şu an
her GitHub URL'sine ek bir istek konmadı. Gerekirse object filtering/partial clone ayrıca
ölçülecek.

## 21. Tam-depo Ruff tabanı temiz değil

**Durum:** `ruff check .` 2026-08-24 ölçümünde 1.053 ihlal bildiriyor; 533'ü güvenli
`--fix` adayı. Borç çoğunlukla tarihsel `research/pdf-parser` betikleri, migrations,
Langflow bileşenleri ve eski testlerde. Bu iş kapsamında değişen üretim ve test kodunun
hedefli Ruff kapıları temiz, `acquisition.py` ile `inspect_bundle.py` içindeki önceden
belgelenmiş dar istisnalar açıkça hariç tutuluyor.

**Etki:** Tam-depo Ruff bugün commit kapısı yapılamıyor; doğrudan kullanılırsa her değişiklik
1.000'den fazla alakasız hata içinde başarısız oluyor ve yeni ihlaller gözden kaçabiliyor.

**Yapılacak:** Önce Ruff kapsamını aktif ürün kodu ile tarihsel/deneysel araçlar arasında
`pyproject.toml` üzerinden açıkça ayır; aktif kapsam için sıfır taban oluştur. Kalan borcu
dizin bazında ayrı PR'larla azalt, otomatik düzeltmeleri davranış testleriyle birlikte
uygula. Tam taban sıfıra inene kadar değişen Python dosyalarında hedefli Ruff zorunlu.

## 22. `_acquire_node` beklenmeyen istisnayı izole etmiyor

**Durum:** `pipeline.py` içindeki iki eşzamanlı adım bu konuda simetrik değil.
`_search_node`'un görev gövdesi `except Exception` ile sarılı: bir bağlayıcı patlarsa hata
`connector_errors` listesine yazılıyor, görev boş liste döndürüyor ve diğer bağlayıcılar
etkilenmiyor. `_acquire_node`'un görev gövdesinde (`one()`) böyle bir koruma yok;
`AcquisitionService.acquire()` beklenmeyen bir istisna atarsa istisna `as_completed`
döngüsündeki `await task` üzerinden düğümün dışına çıkıyor ve `finally` bloğu kalan
görevleri iptal ediyor.

**Neden bugün görünmüyor:** Servis normal başarısızlıkları istisna olarak değil,
`AcquiredDocument(success=False)` olarak döndürüyor. Yani bu, bilinen bir hata yolu değil,
kapatılmamış bir dayanıklılık boşluğu. Ölçüm sırasında da tetiklenmedi.

**Nereden çıktı:** Konnektör I/O eşzamanlılık deneyi
(`research/connector-concurrency/REPORT.md`, "Eleştirel hazır olma değerlendirmesi"). Deney
kontrollü hata ve timeout'ların *benchmark* görevlerini birbirinden izole ettiğini doğruladı;
üretimdeki `_acquire_node` görev gövdesi için aynı kanıt yok.

**Yapılacak:** `one()` gövdesini `_search_node`'daki desenle aynı biçimde sarmak, yani
beklenmeyen istisnayı `AcquiredDocument(success=False)` benzeri bir kayda çevirip metriklere
yazmak. Değişiklikle birlikte, `acquire()` istisna attığında diğer indirmelerin tamamlandığını
gösteren bir test eklenmeli. Bu deneyin kapsamı ölçümdü, davranış değişikliği değildi;
bu yüzden burada açık bırakıldı.

## 23. Edinim testi aralıklı düşüyor, tetikleyici bilinmiyor

**Durum:** `tests/test_academic_connectors.py::test_acquisition_preserves_scholarly_abstract_when_full_text_is_blocked`
tam paket koşusunda ara sıra düşüyor. İki kez gözlendi: `2026-08-26`'da telemetri çıktı
seçimi çalışmasının kapı koşusunda (`1 failed, 482 passed`) ve `2026-08-27`'de `04201d6`
alındıktan sonraki merge doğrulamasında (`1 failed, 509 passed`).

**Ölçümler:** Her iki seferde de izole koşuda geçti (`1 passed`, ~1,3–1,9 sn). İlk olaydan
sonra modül tek başına beş kez arka arkaya koşturuldu, beşi de `15 passed`. İkinci olaydan
sonra tam paket üç kez daha koşturuldu: `510 passed`, `510 passed` ve traceback yakalamak
için yapılan koşu — üçünde de tekrarlamadı. Yani gözlenen sıklık iki tam koşu / yaklaşık on
tam koşu.

**Bilinmeyen:** Hangi assert'in düştüğü **kaydedilmedi**. İki olayda da hata özet satırından
görüldü, traceback yakalanmadı; sonraki denemelerde tekrarlamadığı için de alınamadı. Test
üç şey doğruluyor: `success is True`, `acquisition_method == "scholarly_metadata"` ve
`strategies_tried == ["direct", "scholarly_metadata"]`. Bunlardan hangisinin bozulduğu
bilinmeden kök neden aranamaz.

**Elenen açıklamalar:** Test tamamen mock'lu (`httpx.MockTransport`), ağa çıkmıyor.
`Settings(_env_file=None, testing=True)` kullandığı için makinenin `.env` dosyasından
etkilenmiyor — telemetri çalışmasında `.env`'e eklenen anahtarlar sebep değil. İkinci olayla
birlikte gelen `tests/test_bulk_insert_benchmark.py` `os.environ`'a, `monkeypatch`'e veya
`Settings`'e dokunmuyor; o da sebep değil.

**Neden önemli:** Kendi başına bir ürün hatası değil, ama commit/push kapısı tam paketin
sıfır çıkışına bağlı. Aralıklı bir düşüş, ilgisiz bir işin yayınını sebepsiz durdurur ve
"bir daha koştur, geçer" alışkanlığını besler — kapının değerini aşındıran şey tam olarak
budur.

**Yapılacak:** Önce tetikleyiciyi yakalamak: testi `-p no:randomly` yerine tam paket
sırasında tekrarlı koşturup (`pytest --lf` ya da bir döngü içinde tam paket) düştüğü anın
traceback'ini kaydetmek. `strategies_tried` bozuluyorsa `AcquisitionService.acquire`'ın
strateji sırasını belirleyen ayarların testler arası sızıntıyla değişip değişmediğine
bakmak; `success` bozuluyorsa zamanlama/timeout yarışını aramak. Kök neden bulunana kadar
test devre dışı bırakılmamalı — aralıklı da olsa gerçek bir sinyal taşıyor olabilir.

**Traceback yakalandı (`2026-09-04`).** v0.22.0 çalışması sırasında düştü ve bu kez
traceback alındı:

```
assert document.success is True
E   AssertionError: assert False is True
E    +  where False = AcquiredDocument(..., strategies_tried=[],
E                     error='[Errno -3] Temporary failure in name resolution').success
```

Düşen assert `success is True`, ve `strategies_tried=[]` **hiçbir stratejinin
çalışmadığını** söylüyor — yani hata `acquire()` içinde SSRF kapısında, `_direct`'e bile
gelmeden oluşuyor. `validate_public_url` literal olmayan bir hostname için
`socket.getaddrinfo`'yu `asyncio.to_thread` ile çağırıyor; test `example.org` kullandığı
için mock'lu olmasına rağmen **gerçek bir DNS çözümlemesi** yapılıyor. Bu, "test ağa
çıkmıyor" varsayımını çürütüyor: HTTP mock'lu ama ad çözümlemesi değil.

Ardından modül tek başına beş kez koşturuldu, beşi de `15 passed`.

**Kalan iş:** Kök neden hâlâ doğrulanmadı — DNS'in neden ara sıra düştüğü (yerel resolver
yükü, tam paketteki eşzamanlı `to_thread` çağrıları, konteyner ağı) ölçülmedi. Muhtemel
düzeltme, testin `validate_public_url`'ü diğer edinme testleri gibi monkeypatch'lemesi
(`tests/test_open_access.py` bunu `allow_url` ile yapıyor); bu, testi ölçmek istediği şeye
— edinme geri düşüş zincirine — daraltır ve ad çözümlemesini denklemden çıkarır.

## 24. Kanalsız bir koşu plan kapısında asılı kalabilir

**Durum:** Panel artık HITL checkpoint'i yanıtlamıyor (raporun 56. bölümü); karar koşunun
başlatıldığı kanaldan veriliyor. Telegram'ın düğmeleri, MCP'nin `respond_to_research_checkpoint`
aracı var. Ama **API ya da Langflow'dan** başlatılan bir koşuda `plan_review` varsayılan olarak
`true` ([schemas.py:105](src/research_platform/schemas.py#L105)) ve o koşunun insan yüzeyi
olmayabilir.

**Etki:** Koşu plan kapısında bekler. `plan_max_revisions` dolmadığı için kendiliğinden de
kapanmaz. Panelden **iptal** edilebilir — o düğme duruyor — ama tamamlanamaz.

**Neden ertelendi:** Henüz gerçekleşmiş bir vaka yok; bu makinede koşular Telegram'dan
başlatılıyor. Kural basit tutuldu, önce çift başlılık kapatıldı.

**Yapılacak:** Üç yoldan biri. (a) Çağıran kanalı koşuya yazmak ve yalnız o kanalın
yanıtlamasına izin vermek — 25. ve bu maddeyi birlikte çözer. (b) Kanalsız başlatılan koşularda
`plan_review`'ı varsayılan kapalı yapmak. (c) Panele yalnız yönetici için açık bir kaçış kapısı
koymak. (a) doğru olanı; migration yerine `run_events` üzerine kurulabilir.

## 25. Panelde çağıranı olmayan `POST /api/runs` route'u

**Durum:** [control_panel.py](src/research_platform/control_panel.py) koşu başlatma ucu taşıyor
ama panel arayüzündeki sekiz POST çağrısının hiçbiri oraya gitmiyor. Route, panelin koşu
sahipliğini doğrudan kurabilmesi için eklenmişti; arayüzü hiç yazılmadı.

**Etki:** Kaldığı sürece, panelin başlatıp **yanıtlayamayacağı** koşular üretmek mümkün —
56. bölümdeki kuralla tutarsız. Şu an kimse çağırmadığı için pratik bir zarar yok.

**Yapılacak:** Ya route kaldırılmalı, ya da 24. madde (a) yoluyla çözülüp panelden başlatılan
koşuların panelden yanıtlanmasına izin verilmeli. İkisi aynı kararın iki yüzü.

## 26. `research_runs` sütunları `json`, model `JSONB` türetiyor

**Durum:** Model PostgreSQL'de `JSONB` türetiyor ama migration `protocol`, `state`, `coverage`,
`interaction` ve `hitl_history` sütunlarını düz `sa.JSON` yaratmış; üretimde gerçekten `json`
duruyor. Doğrulandı:

```
protocol = json   state = json   coverage = json   interaction = json   hitl_history = json
```

**Etki:** PostgreSQL `json` için eşitlik operatörü tanımlamıyor. Bu sütunları içeren bir satır
üzerinde `DISTINCT`, `GROUP BY` ya da `UNION` **üretimde patlar, testlerde geçer** — paket
SQLite üzerinde koşuyor ve şema modelden kurulunca sütunlar zaten `JSONB` oluyor. Bir kez
gerçekleşti: 55. bölümdeki `list_runs_cancelled_by_event_since` üretimde her poll turunda
`UndefinedFunctionError` verdi, testlerden sorunsuz geçti. JSONB operatörleri de burada cast
ister.

**Neden ertelendi:** Kayma 51. bölümde belgelendi ve bu çalışmadan eski. Taşımak bir migration
ve ayrı bir karar; tek tek sorgular kaçınarak yazılabiliyor.

**Yapılacak:** `ALTER TABLE ... TYPE jsonb USING <col>::jsonb` migration'ı. Tablo boyutuna göre
kilit süresi ölçülmeli. O zamana kadar: bu tabloyu okuyan sorgularda `DISTINCT`/`GROUP BY`
kullanmamak, üyelik testi (`id.in_(...)`) tercih etmek — ve **yeni sorguları canlı veritabanında
doğrulamak**, çünkü test paketi bu sınıf hatayı göremiyor.

## 27. v0.18.0'in iki flag'i henüz ölçülmedi

**Durum:** `PROTOCOL_SOURCE_SYNTHESIS_ENABLED` ve `PROBE_STRATEGY_SELECTION_ENABLED` ikisi de
varsayılan kapalı ve kapalı oldukları sürece hiçbir kazanç sağlamıyorlar. Kod, testler ve
olay sözleşmesi hazır; eksik olan yalnız ölçüm.

**Yapılacak.** Bölüm B için: etiketlenmiş bir soru kümesinde preset doğruluğu · HITL
kullanıcı override oranı · connector çağrısı ve ilgili kaynak oranı. Bölüm A için: probe turu
başına yeni **ve kabul edilmiş** `SourceVersion` · sıfır-yield tur oranı · yeni kaynak başına
connector çağrısı · tur gecikmesi.

Tek bir önce/sonra koşusu yeterli değil — sağlayıcı cevapları turdan tura değişiyor.
Kaydedilmiş cevaplarla replay ya da aynı koşullarda birkaç tekrar gerekir; bunun için
`tests/conftest.py`'ye bir `RecordingLLM`/`ReplayLLM` çifti yazılmalı. Kazanç çıkmazsa
flag'ler kapalı kalır.

## 28. Altı sabit probe stratejisi hâlâ duruyor

**Durum:** `recovery.literature_scan_probe_missions` kaldırılmadı; `PROBE_STRATEGY_SELECTION_ENABLED`
kapalıyken çalışan yol o. Plan kaldırılmasını istiyordu ama planın kendi "flag kapalıyken
davranış birebir aynı" şartıyla çelişiyordu: kaldırılsaydı varsayılan kurulumda recall probe'u
hiç kalmazdı.

**Etki:** Aynı işin iki kod yolu birlikte bakılıyor. Zarar sınırlı — flag'li ayrım net ve iki
yol test edilmiş durumda — ama kalıcı olmamalı.

**Yapılacak:** 27. madde kazanç gösterirse flag varsayılan açılır ve altılı ile
`probe_strategies_exhausted`'in eski dalı birlikte kaldırılır. Kazanç çıkmazsa probe factory
kaldırılır; ikisinin birden kalması istenen son durum değil.

## 29. Blueprint arşivi

**Durum:** Başarılı probe blueprint'leri koşular arasında saklanmıyor. Her koşu sıfırdan
öneri üretiyor.

**Neden bekliyor:** Arşivin işe yaraması için önce A'nın olay verisinin birikmesi gerekiyor —
`probe_candidate_selected` ve `probe_candidate_outcome` hangi taktiğin hangi gap dimension +
family + research mode kombinasyonunda yield verdiğini zaten yazıyor. Veri birikmeden kurulan
bir arşiv, altı elle yazılmış stratejinin daha karmaşık bir kopyası olurdu.

**Yapılacak:** Yeterli koşu biriktiğinde, yüksek yield vermiş blueprint'leri benzer
kombinasyonda modele referans olarak göstermek. JIT-Agent'ın HarnessFactory'sinin karşılığı
budur ve bu işin ikinci aşamasıdır.
## 30. Kapasite ve model kotaları process-local

**Durum:** `capacity.py` içindeki `GATE = CapacityGate()` ve `_MODEL_LEASE =
asyncio.Semaphore(...)` modül seviyesinde, dolayısıyla yalnız bulundukları worker
process'ini koordine ediyor. Tek worker kullanılan mevcut kurulumda davranış doğru;
birden fazla worker veya host açılırsa her replika aynı toplam kotaya tek başına sahip
olduğunu sanır ve Ollama/GPU aşırı abone edilebilir.

**Nereden çıktı:** GIL ve thread ölçeklenmesi incelemesi. Ölçüm, bu makinedeki kapasite
sınırının Python worker değil LLM/GPU tarafında olduğunu gösterdi. Bu nedenle yalnız
worker sayısını artırmak bugün hız kazandırmaz; ancak ikinci makine/GPU ile yatay büyüme
gündeme geldiğinde koordinasyon eksikliği gerçek bir engel olur.

**Yapılacak:** Yatay büyümeden önce admission kotasını ve model lease'ini Redis gibi tüm
replikaların paylaştığı bir mekanizmaya taşımak; lease süresi, worker ölümü ve yeniden
teslim davranışını entegrasyon testleriyle doğrulamak. Tek worker yolunun basitliği ve
mevcut sınırları korunmalı.

## 30. İddia çevirisinde sayı sırası

**Durum:** Rapor dili `tr` olan koşularda iddia metinleri Türkçeye çevriliyor
(`claim_localization`), ama çeviri `numbers_match` kontrolünden geçmek zorunda ve o kontrol
sayıları **sırayla** karşılaştırıyor. Türkçe söz dizimi sayıları doğal olarak taşıdığı için
bir kısım çeviri reddediliyor ve o iddialar İngilizce kalıyor.

**Ölçüm** (`epic_sepsis_model_validation`, 31 çevrilecek iddia):

| | |
|---|---|
| Çevrildi | 23 |
| İngilizce kaldı | **8** (%26) |
| Reddedilen deneme | 16, hepsi `number_mismatch` |

**Kontrol fazla katı değil — ölçüldü.** Şunların hepsi zaten kabul ediliyor:

| Kaynak | Çeviri | Sonuç |
|---|---|---|
| `6,971` | `6.971` (Türkçe binlik ayracı) | ✅ geçer |
| `18%` | `%18` (yüzde konumu) | ✅ geçer |
| `rose from 10 to 20` | `10'dan 20'ye yükseldi` | ✅ geçer |
| `6,971 of 38,455` | `38.455 hastanın 6.971'i` | ❌ hakiki sıra değişimi |

**Denendi ve işe yaramadı: prompt sıkılaştırma.** Sistem talimatına "sayıları aynı sırada
tut" cümlesi eklendi ve `number_mismatch` sonrası onarım promptuna beklenen sıra birebir
gösterildi (`(numbers, in this order: 18%, 6,971, 38,455)`). Sonuç **bit düzeyinde aynı**
çıktı: 23 çevrildi, 8 kaldı, 16 `number_mismatch`. Yerel model sırayı, açıkça söylendiğinde
ve beklenen sıra gösterildiğinde bile korumuyor. Değişiklik geri alındı; **tekrar denemeye
değmez.**

**Neden sıra kontrolü gevşetilmemeli.** Çoklu küme karşılaştırması "10'dan 20'ye yükseldi"
ile "20'den 10'a düştü" arasındaki farkı göremez. Bir tıp raporunda yön hatası, çevrilmemiş
bir cümleden çok daha kötüdür. Reddedilen çeviri okuyucuya İngilizce görünür ve okuyucu
bunun çevrilmediğini anlar; kabul edilen yanlış çeviri ise olgu gibi okunur.

**Yapılacak — hedefli gevşetme.** Çevrilemeyen 8 iddia yönlü ifade içerip içermediğine göre
ayrıldı: **4'ü yönlü** (`AUC drops from 0.83 to 0.63`), **4'ü yönsüz** (`alerts for 18% of
all hospitalized patients (6,971 of 38,455)`). Sıra kontrolü yalnız kaynak metin yönlü ifade
**içermiyorsa** gevşetilirse — `from … to`, `rose`, `fell`, `increased`, `decreased`,
`versus` ve Türkçe karşılıkları — kayıp %26'dan %13'e iner ve yön hatası riski hiç doğmaz.

Çalışacak tek yol bu görünüyor. Uygulanırsa yönlü ifade listesi Türkçe tarafta da
eksiksiz olmalı; eksik bir kelime, gevşetmenin tam da korumak istediği durumda devreye
girmesi demektir.

## 35. Free-threaded Docling production pinleri `cp314t` zincirinde engelli

**Durum:** GIL uyumluluk çalışmasında NumPy 2.5.2 ve PyTorch 2.13.0+cpu CPython 3.14.7
free-threaded ortamında import ve CPU stres kapılarını geçti. Docling production pin
seti ise aynı ortamda kurulamadı: `docling-parse`, `tokenizers`, `safetensors`,
`opencv-python` ve `pyclipper` zincirinde `cp314t` wheel boşlukları ve native packaging
engelleri doğrulandı.

**Neden passed değil:** Bu, testin atlanması değildir; paketleme sınırına kadar götürülen
deneyin sonucudur. Yamalı bir `docling-parse` zinciriyle alınacak sonuç production
uyumluluk kanıtı sayılmaz. Üstelik production mimaride Docling zaten worker thread'i
içinde değil, öldürülebilir ayrı process/service yolunda çalışır; free-threaded worker'a
taşımak güvenli timeout kararını geri alır.

**Ek koşulan kapı:** `.venv-docling` içinde gerçek Docling 2.120.1 ile klasik
Python CPU limited matrix koşuldu. `shared` ve `per_thread` modları 1/2 thread'de geçti;
çökme, timeout veya markdown digest ayrışması görülmedi. Bu sonuç free-threaded Docling
kanıtı değildir; runner'ın gerçek Docling ile çalıştığını ve wheel'ler yayımlanırsa
karşılaştırma kapısının hazır olduğunu gösterir.

**Yapılacak:** Upstream `cp314t` wheel'ler yayımlanana veya production pin seti resmi
free-threaded destekli sürümlere taşınana kadar kabul kriteri **engelli — upstream wheel
bekliyor** durumunda kalmalı. Yeniden açıldığında önce binary wheel kapısı, sonra
free-threaded import/GIL kontrolü, ardından klasik/free-threaded digest karşılaştırması
çalıştırılmalı.

## 36. Kanıt notu raporlanabilirliği kapılamalı mı?

**Durum:** v0.22.0'da eklenen kanıt notu (`claim.audit["appraisal"]["grade"]`) yalnızca
gösteriliyor: çizim prompt'una, bulgular blokuna, denetim raporuna ve Word Ek D'ye giriyor.
`exporter._is_reportable` ve `ordered_reportable` sıralaması **kasten** dokunulmadan
bırakıldı.

**Neden şimdilik böyle:** Kapıya ya da sıralamaya bağlamak hangi iddiaların teslim
edildiğini değiştirir ve hata modu görünmezdir — bir iddiayı sessizce kaybetmiş rapor, o
iddiaya hiç sahip olmamış rapordan ayırt edilemez. Notun raporları iyileştirdiğini
gösteren bir ölçüm olmadan bu takas alınamaz.

**Karar için gereken ölçüm:** Aynı koşu havuzunda not-kapılı ve not-kapısız iki dışa
aktarım üretip (a) kaç iddianın düştüğünü, (b) düşenlerin insan değerlendirmesinde gerçekten
zayıf olup olmadığını, (c) `12_uncertainty_report.md` içindeki dışlanan iddia listesinin
büyüyüp büyümediğini karşılaştırmak. `insufficient` notunun kapı için doğal aday olduğu
varsayılıyor ama doğrulanmadı.

## 37. Açık erişim kapsamı: arama connector'ları ertelendi

**Durum:** v0.22.0 yalnız **çözümleme** yolunu getirdi (Europe PMC JATS + isteğe bağlı
Unpaywall). Şu arama kaynakları bilinçli olarak dışarıda bırakıldı: PubMed E-utilities,
bioRxiv ve medRxiv API'leri, CORE, NCBI efetch JATS.

**Gerekçe:** Europe PMC zaten biyomedikal anahtar kelime araması yapıyor ve
bioRxiv/medRxiv preprint'lerini indeksliyor, dolayısıyla örtüşen recall eklerlerdi. Yeni
bir arama connector'ı ise `recovery.py`'daki `FAMILY_CONNECTORS`, `query_compiler.py`'daki
sorgu şekillendirme, `build_registry`, health raporu ve `coverage.py` aile aritmetiğinde
eşgüdümlü düzenleme ister — yanlış özelliğe bağlanmış ikinci bir artımlık patlama yarıçapı.

**Ne zaman gerekir:** Biyomedikal olmayan tam metin kapsamı sorun olursa CORE, ya da
Europe PMC'nin indekslemediği bir preprint sunucusu hedeflenirse ilgili API. İkisi de
mevcut `_open_access_fulltext` adımına ek hedef fonksiyonu olarak, connector eklemeden
girebilir.

## 38. `structured._flatten_xml` satır içi elemandan sonraki metni düşürüyor

**Durum:** `_flatten_xml` her elemanın `element.tail`'ini yok sayıyor, dolayısıyla
`<p>text <italic>x</italic> more</p>` içinde " more" kayboluyor. Karma içerik taşıyan her
XML kaynağı bundan etkileniyor.

**Neden düzeltilmedi:** `content_hash` ayrıştırılmış metnin sha256'sı ve source-version
dedup'ını, MinIO anahtarlarını ve passage offset'lerini sürüyor. Düzeltmek şu ana kadar
saklanmış her XML kaynağını yeniden hash'ler, aynı kaynağı iki sürüme böler ve mevcut
passage offset'lerini geçersiz kılar. v0.22.0 JATS için ayrı bir ayrıştırıcı ekleyerek
sorunu **o yol için** çözdü; genel XML yolu eski davranışta.

**Yapılacak:** Düzeltme ancak bir yeniden ayrıştırma/yeniden hash'leme göçüyle birlikte
anlamlı. Hangi kaynakların gerçekten karma içerikli XML olduğunu ölçmek ilk adım; sayı
küçükse hedefli yeniden edinme, büyükse göç planı gerekir.

## 39. Duraklatılan koşunun bekleme süresi toplama bütçesine yazılıyor

`collection_round_started_at` checkpoint'te bilinçli olarak saklanıyor — amaç, worker
yeniden başladığında yarım kalan toplama turunun sıfırlanmaması (`PipelineState` üzerindeki
yorum bunu açıkça söylüyor). v0.23.1'e kadar sayaç zaten hiç birikmediği için bu kararın
ters etkisi görünmüyordu.

Sayaç artık işlediğine göre: `ACQUIRE` sırasında preempt edilen ya da duraklatılan bir koşu
resume'da işaretçiyi **eski** zaman damgasıyla geri alır ve `_finish_collection_round()`
duraklama boyunca geçen duvar saatini de toplama süresi sayar. İki saat bekleyen bir koşu,
180 dakikalık bütçesinin tamamını hiçbir şey toplamadan harcamış olur.

Ne yanlış olduğu açık, doğrusunun ne olduğu bir karar: işaretçiyi resume'da şimdiye
yeniden çıpalamak duraklamayı hiç yazmaz ama yarım turun gerçek süresini kaybeder;
`_boundary()` her checkpoint'te kısmi süreyi biriktirirse ikisi de doğru olur, karşılığında
sayaç aşama sınırlarında yazılır.

**Yapılacak:** İki seçenekten biri seçilip `_finish_collection_round()` ile `run()`'daki
resume yolu birlikte güncellenmeli; duraklama üzerinden geçen bir resume testi eklenmeli.

## 40. Kanıt tabanı 18 kaynağa iniyor, kanıt notu bu yüzden tabanda kalıyor

Koşu `01M1NT3VCT2R0G10DFD4BRVVG1` (2026-09-04, 260 kaynak) 231 raporlanabilir iddia üretti
ve denetim şunu yazdı: `strong` 1, `limited` 230, `insufficient` 29 — 230'unun gerekçesi
`single_independent_domain`. Raporun Ek A'sında (bağımsız kaynaklarla desteklenen bulgular)
**1**, Ek B'sinde (tek kaynaklı) **230** başlık var.

**Bu bir notlama hatası değil.** Ölçüm doğruyu söylüyor: 260 iddianın 255'i tek kaynaklı.
Tek kaynaklı bir iddianın bağımsız köken sayısı da birdir; v0.22.0'ın değerlendirme
katmanı elindeki kanıtın inceliğini doğru raporluyor.

### Sebep: kaynak hunisi

```
260 kaynak
  near_scope           222   <- kanita hic girmiyor (40. madde degil, tasarim)
  primary_in_scope      36
  supporting_benchmark   2
        |
  kanit ureten          18
        |
  231 iddia -- her biri tek kaynakli
```

Kanıt üreten havuz **18 kaynak**; kaynak başına ~13 iddia. Bir iddianın doğrulanması için o
18 kaynaktan ikisinin aynı spesifik önermeyi söylemesi gerekiyor. Bu havuz büyüklüğünde tek
kaynaklılık neredeyse aritmetik bir zorunluluk.

Aynı koşunun kapsam raporu ikinci sinyali veriyor: `reserve_false_negative_rate: 0.3`
(eşik 0.1) — kabul kapısının reddettiği kaynakların yaklaşık üçte biri aslında alınmalıydı.
`query_branch_coverage: 0.1429` (hedef 0.9) da aynı yöne bakıyor.

### Bakıldı, sorun burada değil: `_deduplicate_report_claims()`

İlk teşhis "iddialar kaynaklar arası birleşmiyor, o yüzden tek kaynaklı görünüyorlar"
şeklindeydi. **Ölçüldü ve çürütüldü**, tekrar aynı yola girilmesin diye buraya yazılıyor.

Fonksiyon bu koşuda `merged_claim_ids: 0` üretti — hiç birleştirme yapmadı. 231
raporlanabilir iddianın 26.565 çifti tarandı:

| eşik | çift |
|---|---|
| `word_cosine >= 0.68` (bugünkü kapı) | 1 |
| `>= 0.60` | 6 |
| `>= 0.50` | 23 |
| `>= 0.45` | 39 |

Tek 0.68 adayı yanlış eşleşme (bir yöntem cümlesi ile bir arama sorgusu dizesi).
0.45–0.60 aralığındaki çiftler elle bakıldığında **farklı önermeler**; yalnızca alan
kelimelerini paylaşıyorlar ("decoder transformer" ile "GAN mode collapse", "2D VLM" ile
"3D'ye genişletme"). Yani birleşmeyi bekleyen gizli bir yığın yok; eşiği gevşetmek kazanç
değil yanlış birleşme üretir.

Fonksiyondaki `bool(source_ids & other_sources)` şartı da keyfî değil: `word_cosine` bir
kelime torbası ve rol tersliğini ("A, B'yi geçiyor" / "B, A'yı geçiyor") yakalayamıyor —
`claim_guard_compatible` yalnız sayı ve olumsuzluk imzasına bakıyor. Ortak kaynak şartı
bunun ucuz panzehiri. **Dokunulmamalı.**

Çekince: `word_cosine` kelime torbası olduğu için dağarcığı tamamen ayrık bir paraphrase'i
kaçırabilir. Bu dar alanda kelimeler fazlasıyla ortak olduğundan ölçüm yanlış pozitif
üretiyor, yanlış negatif değil; yine de kesin konuşmak için gömü tabanlı bir kontrol
gerekir. Bugünkü kanıt tek yöntemli.

### İkincil bulgu: domain sayımı hostname üzerinden

`audit()` bağımsızlığı hostname ile sayıyor
([pipeline.py](src/research_platform/pipeline.py), `domains = {...s.url...}`). 260 kaynak
yalnız 61 hostname'e düşüyor: `doi.org` 50, `arxiv.org` 37, `www.mdpi.com` 21,
`link.springer.com` 21, `pmc.ncbi.nlm.nih.gov` 20. `doi.org` bir yayıncı değil, yönlendirme
servisi — 50 ayrı dergideki makale tek "domain" sayılıyor.

Ölçüldü: iki veya daha fazla kaynağı olan 5 iddiadan 4'ü aynı hostta eziliyor. Yani bugün
**4 iddiayı** etkiliyor, 230'un sebebi değil. Kanıt tabanı genişlediğinde bağlayıcı hâle
gelir.

### Yapılacak

1. **Kabul kapısı kalibrasyonu — asıl iş.** 222/260 kaynağın `near_scope`'a düşmesi ve
   `reserve_false_negative_rate: 0.3` birlikte okunmalı. Reddedilen kaynaklardan bir
   örneklem elle etiketlenip kapının gerçek yanlış-negatif oranı ölçülmeli; kanıt tabanı
   18'den çıkmadan not merdiveni tabanda kalır.
2. **`doi.org` çözümlemesi.** Hostname yerine DOI registrant ön eki kullanılmalı; veri
   zaten kaynak metadata'sında (`DOI`, `ISSN`, yayıncı `link`'i). Tek başına ölçülebilir
   kazanç vermez (4 iddia), 1. madde ilerledikçe gerekli olur.
3. **arXiv/PMC gibi arşivlerin tek domain sayılması** 1. ve 2. madde sonrası yeniden ele
   alınmalı.

`_deduplicate_report_claims()` bu listede **yok** — ölçüldü, bugün zarar vermiyor.

## 41. Aile adı ham enum değeriyle sağlayıcı sorgusuna sızıyor

**Durum:** `recovery.py:280` boşluk konusunu `f"{family.value} evidence for {primary_question}"`
diye kuruyor. `SourceFamily.CODE_DATA.value` `code_data`, `GREY_LITERATURE` ise
`grey_literature` — yani sağlayıcıya gönderilen sorgu bir alt çizgili enum değeriyle
başlıyor. GitHub facet yoluna geçtiği için orada etkisi kalmadı, ama web ve akademik
dallar bu metni hâlâ alıyor.

**Gerekçe:** 72. bölümdeki doyum sondası iskelesiyle aynı sınıf kusur: kendi iç kayıt
sözlüğümüz arama terimi gibi davranıyor. Çözümü de aynı — kelimeleri kara listeye almak
değil (`web`, `academic`, `company` meşru konu kelimeleri), frazı önekten şeritlemek:
`^(?:<her SourceFamily değeri>) evidence for ` deseni `compile_provider_query`'de,
`_PROBE_SCAFFOLD` ile aynı yerde.

**Ne zaman gerekir:** Bir kapsam boşluğu kurtarma turunun web/akademik dalda beklenenden
az sonuç döndürdüğü ölçüldüğünde. Tek başına ölçülmüş bir kayıp yok; 72. bölümde bilinçli
olarak kapsam dışı bırakıldı.

## 42. `AcquisitionService` HTTP gözlemi yok

**Durum:** 72. bölüm `SourceConnector.observed_get` ile bütün connector çağrılarını kayda
aldı. `AcquisitionService` aynı `httpx.AsyncClient`'ı paylaşıyor ama `SourceConnector`
olmadığı için yardımcıyı miras almıyor; crawl4ai, jina ve agentsearch-read stratejileri
HTTP durumunu kaydetmiyor.

**Gerekçe:** Aynı yardımcıyı oraya bağlamak yanlış olurdu. `CONNECTOR_OBSERVATION` yalnız
`pipeline.one()` içinde kuruluyor, dolayısıyla edinimde kalıcı no-op olur ve "acquisition
enstrümante" diye yanlış güven verirdi. Çağrı şekli de farklı: `acquisition.py:483` elle
yönlendirme döngüsü, orada `attempt` "redirect hop" demek olurdu ve bu bilgi zaten
`redirect_chain` olarak üretiliyor.

**Ne zaman gerekir:** Edinim tarafında "neden bu belge alınamadı" sorusu panelden
cevaplanamadığında. Kendi gözlem sözlüğünü hak ediyor — deneme yerine strateji/hop
ekseninde, `acquisition_call` tanılamasının içine.

## 43. Docker Desktop oturum açılmasını gerektiriyor — Windows sunucu başsız kalkamıyor

**Durum:** Windows sunucusunda (10.0.10.223) Docker Desktop bir Windows servisi değil.
Daemon `HKCU\...\Run` altındaki `Docker Desktop.exe` ile, yani **kullanıcı oturumu
açıldığında** başlıyor; `com.docker.service` yalnızca yardımcı servis (Manual/Stopped).
GUI uygulaması olduğu için Session 0'dan başlatılamıyor — sistem açılışında tetiklenen bir
görev daemon'ı bulamaz. Ölçüldü 2026-09-10, Docker Desktop 29.7.2.

**Etkisi:** Otomatik oturum açma kapalıyken sunucu yeniden başlatmadan sonra kendiliğinden
ayağa kalkmıyor; birinin makineye giriş yapması gerekiyor. `scripts/register_autostart.ps1`
görevi bu yüzden bilinçli olarak `ONSTART` değil `AtLogOn` tetikleyicisiyle kuruluyor.
Ollama istisna: natif ve Docker'a bağlı olmadığı için gerçek bir `ONSTART` görevi olarak
oturumsuz da çalışıyor.

**Geçici çözüm:** Otomatik oturum açma — tercihen Sysinternals Autologon, parolayı LSA
secret'ta tutar ve kayıt defterinde açık metin bırakmaz. Açıldığında zincir tamamlanıyor:
açılış → oturum → Docker Desktop → `restart: unless-stopped` container'lar geri gelir →
görev `start_server.ps1`'i çalıştırır → panel.

**Kalıcı çözümü yok**, Docker Desktop'ın mimarisinden geliyor. Gerçekten başsız bir sunucu
isteniyorsa alternatif, daemon'ın gerçek bir servis olduğu Linux'ta Docker Engine'dir —
Ubuntu kurulumunda bu sorun hiç yoktu.

---

## 44. Session 0'dan kimlik deposuna erişilemiyor — uzak oturumda `docker build` ve `git push` düşüyor

**Durum:** Windows sunucusuna SSH ile bağlanan süreçler **Session 0**'da ve **LogonType 3
(ağ oturumu)** altında çalışıyor. Bu oturum türüne şifre materyali hiç ulaşmadığı için
Credential Manager'ı koruyan DPAPI ana anahtarı açılamıyor. Sonuç, iki ayrı yerde aynı hata:

```
docker: error getting credentials -- err: exit status 1,
        out: `Belirtilen oturum yok. Daha önce kapatılmış olabilir.`   (ERROR_NO_SUCH_LOGON_SESSION, 1312)
git:    fatal: Unable to persist credentials with the 'wincredman' credential store.
```

**Kapsamı:** Yazma ya da kimlik arama gerektiren her işlem. `docker pull`, `docker build`
(BuildKit **ve** klasik builder — ikisi de deneniyor), `git push`. Okuma tarafı etkilenmiyor:
`git fetch` çalışıyor çünkü depo anonim okunabiliyor. Aynı kök sebep GUI/tray uygulamalarını
da öldürüyor (`ollama app.exe`); `ollama serve` headless olarak sorunsuz.

**Yanıltıcı olan:** Hiçbir kimlik doğrulaması aslında yapılmıyor. `~/.docker/config.json`
içinde `auths` boş ve kullanılan imajların hepsi genel. Docker yine de her çekme/derlemeden
önce depoyu yokluyor ve yoklama patlıyor. `credsStore` satırını silmek de kalıcı değil:
**Docker Desktop her açılışta dosyayı geri yazıyor** (ölçüldü 2026-09-10).

**Çalışan geçici çözüm:** Derlemeyi makinenin kendi masaüstündeki bir oturumdan (Session 1)
çalıştırmak. Şifreyi kaldırmak **çözüm değildir** — sorun şifrenin yokluğu değil oturum
türü, üstelik `LimitBlankPasswordUse` varsayılanı boş şifreli hesapların ağ/RDP oturumlarını
engellediği için uzaktan erişimi tamamen kesebilir.

**Kalıcı seçenekler:** (a) `DOCKER_CONFIG` ayrı bir dizini gösterecek şekilde ayarlanıp boş
kimlik döndüren bir credential helper tanımlanması — süreç kapsamında yapılırsa sistemde iz
bırakmaz ve Docker Desktop ezemez, karşılığında özel imaj çekilemez; (b) ajanın/derlemenin
gerçek bir masaüstü oturumunda çalıştırılması, ki bu 43. maddeyle birlikte çözülür.

---

## 45. Panel testi canlı yığını gerçekten durduruyor

**Durum:** `tests/test_control_panel.py::test_stopping_the_stack_is_restricted_to_administrators`
panelin `POST /api/system/stop` ucunu çağırıyor. Panel ayarlarını gerçek `.env`'den
okuduğu için `CONTROL_PANEL_DEPLOYMENT=docker` görüyor ve komutu **gerçekten çalıştırıyor**.
Test `{"message": "stopped"}` bekliyor; sunucu üzerinde koşturulduğunda dönen değer
gerçek compose çıktısı oluyor:

```
Container research-platform-api-1 Stopped
Container research-platform-worker-1 Stopped
Container research-platform-mcp-gateway-1 Stopped
Container research-platform-telegram-bot-1 Exited (137)
```

Yani test hem başarısız oluyor hem de `api`, `worker`, `mcp-gateway` ve `telegram-bot`'u
düşürüyor — panelin `_compose_app_services()` hedefiyle birebir aynı küme. 2026-09-10'da
sunucuda tam takım koşturulurken yaşandı; o sırada aktif koşu yoktu, olsaydı worker'ın
altından çekilirdi.

**Neden bulunması zor:** Geliştirme makinesinde `.env` yok ya da
`CONTROL_PANEL_DEPLOYMENT=native` ve compose çağrısı bir yere varmıyor, test sessizce
geçiyor. Yıkıcı hâle yalnız gerçek dağıtımın yanında çalışınca geliyor — yani tam olarak
"sunucuda bir kez test koşayım" denen anda.

**Kök sebep:** Test `_run_powershell`'i zaten sahteliyordu — ama yalnız onu. Panel
`system_action` içinde ikiye ayrılıyor ([control_panel.py:1579](src/research_platform/control_panel.py#L1579))
ve docker modunda `_run_compose_action`'a gidiyor. Sahteleme natif dönemde yazılmış,
docker modu eklenince genişletilmemiş.

**Durum: çözüldü.** İki katman:
- `tests/conftest.py` `CONTROL_PANEL_DEPLOYMENT=native` sabitliyor. Ortam değişkenleri
  pydantic-settings'te dotenv'i ezer, dolayısıyla dalı bütün testler için birden kapatır.
- Testin kendisi `_run_compose`'u yükselen bir sahteyle bağlıyor, yani sabitleme ileride
  kalksa da gerçek komut çalışmıyor. Mevcut `fail_powershell` korumasının simetriği.

Doğrulama: takım sunucuda yeniden koşturuldu, `docker ps` çıktısı öncesi ve sonrası
birebir aynı; 901 geçti (önceki 900 + düzelen bu test).

**Kökten kapatıldı.** `Settings.model_config` artık dotenv yolunu `RESEARCH_ENV_FILE`
ortam değişkeninden alıyor; boş verilirse dotenv kaynağı tamamen kapanıyor. Dağıtımlar
değişkeni tanımlamaz ve eskisi gibi `.env` okur — ölçüldü, üretim davranışı aynı.
`tests/conftest.py` değişkeni boş bırakıyor, yani süit kendi yapılandırmasını kuruyor ve
üzerinde çalıştığı makine tarafından yönlendirilemiyor.

**Bu düzeltmenin kendi tuzağı, kapatıldı:** Dotenv kapanınca model varsayılanları
devreye giriyor ve onlar `redis://localhost:6379` ile `localhost:9000`. Compose MinIO'yu
tam olarak `127.0.0.1:9000`'de yayınlıyor, dolayısıyla "testler dağıtımın yapılandırmasını
miras almasın" düzeltmesi az kalsın onlara dağıtımın nesne deposunu verecekti. Önceki
`minio:9000` yalnızca çözülemediği için zararsızdı — tasarım değil tesadüf. conftest artık
her dış ucu kapalı bir porta sabitliyor: mock'u unutan bir test bağlantıda gürültüyle
düşer, sessizce gerçek bucket'a yazmaz.

---

## 46. Formül, görsel ve HTML kaçışı — kod hazır, canlıya geçiş bekliyor

**Durum (2026-09-11):** `developments-supplementer` üzerinde kod ve testler tamam
(`1115 passed, 4 skipped`, dalın en güncel haliyle birleşmiş kod); canlı yığına **kurulmadı**. Ayrıntılı ölçümler:
`research/pdf-parser/out/karantina_2026-09-11/FORMUL_HTML_RAPORU.md` ve
`UYGULAMA_ILERLEME.md` (gitignore'lu).

**Ne değişti:**
- Docling sayfaları HTML varlığı taşımıyor (`escape_html=False`, üç yol ortak
  `sayfa_markdown`). `pH &lt; 5.8` artık `pH < 5.8`.
- Passage'a HTML yorumu girmiyor: `<!-- formula-not-decoded -->` → `[formül N]`,
  `<!-- image -->` → `[görsel N]` (20×20 pt altı ikonlar düşer). Kutular
  `parse_provenance.bolgeler`'de. 211 sayfalık doğrulamada işaret = bölge, 211/211.
- Docling'in formül modeli **kapalı kalıyor** (+0,6 GB kalıcı, 3–5 GB anlık VRAM).
  Formüller, ayar açıksa, iddia çıkarmadan önce `qwen3.5:4b` ile kırpıntıdan okunuyor
  (`formula_resolution.py`, önbellek `formula_observations`, göç `0011`) ve `FORMULAS`
  bloğu olarak `TARGET_CONTENT`'in yanında LLM'e gidiyor. Okuma passage metnine ve
  `content_hash`'e girmez.
- Raporda: markdown alıntılarda `$LaTeX$`; Word'de yerel denklem (OMML) — klasik yolda
  alıntı içinde, sentez yolunda "Ek F. Formül okuma kaydı". Denklem kurulamayan ya da
  satıra sığmayan formül kaynak kırpıntısıyla basılır.
- Ayar: `FORMULA_RESOLUTION_ENABLED` (varsayılan **kapalı**), `FORMULA_RESOLUTION_TIMEOUT_S`,
  `FORMULA_MAX_PER_RUN` (80). Kapalıyken yeni tabloya hiç dokunulmaz.

**Canlıya geçiş adımları:** (1) canlı kopya `/home/cezeri/research-platform`
bu branch'in gerisinde — önce güncellenmeli; (2) docling imajı yeniden kurulur
(`regions` + `escape_html`); (3) worker/api imajı yeniden kurulur (`latex2mathml`,
`mathml2omml`); (4) `migrate` servisi `0011`'i uygular; (5) ayar kapalı açılır, bir
koşu izlenir, sonra açılır. Docling ve worker değişikliği Docling'in işlediği
belgelerin `content_hash`'ini **bir kez** kaydırır; yeniden edinilen belge yeni
SourceVersion olur (kabul edildi).

**Açık kalanlar:**
- Word'ün kendisinde görsel doğrulama yapılmadı; basım yalnız LibreOffice ile ölçüldü.
- `mathml2omml` 0.0.2 karekökü şemaya aykırı yazıyor (`<m:rad>` içinde `<m:deg>` yok);
  `formula_render._omml_onar` onarıyor. Paket güncellenirse onarım ve sıkı basım testi
  (`test_every_approved_reading_prints_whole_through_libreoffice`) yeniden koşulmalı.
- Model alıntıyı formülden önceki cümlede kesiyor; Ek F bu yüzden alıntıya değil
  kanıtın passage'ına bakıyor. Bir formülün yanlış okunması (24'te 1) raporda kaynak
  kırpıntısı olmadan fark edilmez.
- ~~pdf-inspector 1.14.1 → 1.19.0 ayrı görev~~ — ölçüldü ve yükseltildi, bkz. 47. madde.
- `figure_analysis` Docling'in görsel bölgelerini (`bolgeler`, `tur=gorsel`, başlıklı)
  aday olarak kullanabilir — PyMuPDF sezgisinin kaçırdıklarını yakalar; sonraki görev.
- Deney imajları `research-platform-docling:gcc-deney` ve `:formul-bolge`, durdurulmuş
  `docling-formul-deney` konteyneri silinebilir.

---

## 47. pdf-inspector 1.14.1 → 1.19.0 — kod hazır, canlıya geçiş bekliyor

**Durum (2026-09-14):** pin `==1.19.0`, `developments-supplementer` üzerinde; testler
`1126 passed, 4 skipped`. Canlı worker hâlâ 1.14.1. Rapor:
[PDF_INSPECTOR_1.19_YUKSELTME_RAPORU.md](PDF_INSPECTOR_1.19_YUKSELTME_RAPORU.md).

**Ölçüm:** 380 belge (opendataloader 200 + OCRTurk 180), aynı kod ve aynı Docling
önbelleği (`out/c1_docling_cache_cuda`), tek fark sürüm; hakem resmi opendataloader
değerlendiricisi. Nihai çıktı overall 0,8780 → 0,8803; hızlı yol 0,8283 → 0,8370 (TEDS
+0,0345). Heavy belge 160 → 154, karantina 3 → 1. 10 sayfa kararı değişti: 7 tablosuz
sayfa Docling'den çıktı, 2 tablosuz sayfa girdi, 1 tablolu sayfa kaçtı. Hız 69 → 87 ms/sayfa.
Koşular: `research/pdf-parser/out/c1_runs/pi114_2026-09-14`, `pi119u_2026-09-14`;
betikler ve belge bazlı sonuçlar `research/pdf-parser/out/pdf_inspector_1.19_2026-09-14/`
(gitignore'lu).

**Ne değişti:**
- 1.18.0'dan beri markdown `<sup>`/`<sub>` yazıyor (52/380 belge). `inspector.py`
  `betik_etiketlerini_coz` gate'ten önce Unicode'a çeviriyor (`cm⁻¹`); karşılığı yoksa
  etiketi söküyor. Etiketler dokunulmadan bırakılınca OCRTurk nihai skoru 1.14.1'in altına
  düşüyordu (referansta etiket yok), Word alıntılarında da etiketler basılırdı.
- `parse_provenance.fast_engine_build` (ve teslimat manifesti): belgeyi ayrıştıran
  pdf-inspector sürümü. `None` = PyMuPDFFallback.
- `test_the_installed_inspector_is_the_measured_pin`: kurulu sürüm ≠ pin ise kırılır.

**Canlıya geçiş:** canlı kopya bu commit'e getirilir, worker ve api imajları yeniden
kurulur (Docling imajında pdf-inspector yok). Hızlı yol metni değişen belgeler yeniden
edinildiğinde yeni SourceVersion olur (bir kez).

**Açık kalanlar:**
- `data_114` (bilanço şeması) artık tablo bayrağı almıyor; tablo recall 82/84 → 81/84.
  Kabul edildi (1.14.1'de de Docling çıktısı karantinaya alınıyordu). Kaçan diğer iki sayfa
  (`01030000000121`, `…122`) iki sürümde de kaçıyor.
- `data_10`'da tablosuz ama yönlendirilen sayfa hızlı yola döndü ve nihai skor 0,943 →
  0,850 düştü (Docling bu sayfada daha iyiydi). Karar tablo sinyalinden değil, yanlış pozitif
  bayrağın kalkmasından; eşiklere dokunulmadı.
- Eşikler (`gate_v2`) 1.14.1 çıktısıyla konmuştu, 1.19.0 için yeniden kalibre edilmedi.
  Ölçülen fark eşiklerin olduğu gibi kalabileceğini gösteriyor.

---

## Kapsam dışı bırakılanlar

**Otomatik retention** — provenance/reproducibility vaadiyle çelişiyor (1. maddeye bakınız).

**LLM'in ingestion'da parser seçmesi** — ölçülen 10.62 sn/çağrı maliyeti ve `content_hash`
bağımlılığı nedeniyle reddedildi; gerekçe raporun 9. bölümünde.

**README / PRODUCT_OVERVIEW güncellemesi** — mimari anlatımı MinIO'yu artefakt deposu olarak
tarif ediyor ve bu hâlâ doğru; parser paketi eklendiği için ileride bir gözden geçirme
gerekebilir.
