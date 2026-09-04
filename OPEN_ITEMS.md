# Açık İşler

`developments-supplementer` branch'inde bilinen, henüz kapatılmamış işler. Ayrıntılı gerekçeler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) içindedir;
burası tek liste hâlinde durum tablosudur.

Son güncelleme: `2026-09-03`

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
| 31 | Yanıtlanabilirlik yalnız `max(question_relevance)` ile karar veriyor | Tek yüksek iddia kapıyı açar, dağınık kanıt kapatır | Orta |
| 32 | Bozuk kaynak etiketi (`S1-3`) atıf temizleyicisinden kaçıyor | Okuyucu hiçbir yere gitmeyen atıf görüyor | **Yüksek** |
| 33 | Sentez metnine iç defter dili sızıyor | Rapor kanıt yerine kendi girdisini anlatıyor | Orta |
| 34 | Anahtar kelime satırı `qualified` iddia olarak kabul edilmiş | Rapor gövdesinde kaynak diye alıntılanıyor | Orta |
| 35 | Free-threaded Docling production pinleri `cp314t` zincirinde engelli | Kabul kriteri passed değil, upstream wheel bekliyor | Belgelendi |

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

## 31. Yanıtlanabilirlik tek bir skora dayanıyor

**Durum:** `build_synthesis_package` kompakt bir raporu "yetersiz" ilan ederken yalnız
`max(question_relevance)` değerini `_DIRECT_ANSWER_RELEVANCE_THRESHOLD = 0.35` ile
karşılaştırıyor (`src/research_platform/report_synthesis.py`). Tek bir ölçüt, tek bir
iddiaya dayanıyor.

**Neden yetersiz.** İki yönde de yanılıyor. Soruya çok yakın **tek** bir iddia, geri kalan
kanıt tamamen dağınık olsa bile kapıyı açıyor. Buna karşılık her biri `0.30` civarında
gezinen, farklı kaynaklardan gelen ve alt soruların tümünü kapsayan on iddia — birlikte
soruyu gerçekten yanıtlayan bir küme — kapıya takılıyor.

**Yapılacak.** Karar üç sinyalin birleşimine taşınmalı:

- eşiği geçen **ilgili iddia sayısı** (tek iddia yeterli sayılmamalı),
- bu iddialara **katkı sağlayan ayrı kaynak sayısı** (`_contributing_sources` hazır),
- **araştırma alt amaçlarının kapsanma oranı** — `sub_questions` başına en az bir ilgili
  iddia düşüp düşmediği; `_plan_themes` bu eşleştirmeyi zaten kuruyor, aynı eşleştirme
  yeniden kullanılabilir.

Eşikler ölçümle belirlenmeli; şimdilik tek skor korunuyor. Bu iş, v0.20.1'deki kompakt
çöküş düzeltmesinin kapsamı dışında bırakıldı — o düzeltme rapor **görünürlüğünü** onarır,
bu madde yanıtlanabilirlik **kararının kalitesini** ilgilendirir.

## 32. Bozuk kaynak etiketi atıf temizleyicisinden kaçıyor

**Durum:** `_TOKEN_RE = re.compile(r"\[S\d{2,3}\]")` yalnız köşeli parantezli, iki-üç haneli
etiketi tanıyor. Model `S1-3` yazdığında bu ne geçerli bir atıf sayılıyor ne de
temizleniyor; düz metin olarak okuyucuya gidiyor.

**Ölçüm** (`01M1GXGZW8NP674E80YD6NNM27`, 2026-09-02 re-export): 3.2 bölümünde bir kez —
"Ancak **S1-3**, açık kaynak veya açık ağırlıklar ile ilgili doğrudan bir ifade yapmaz."
Okuyucu bunu atıf sanıyor, Ek C'de karşılığı yok.

**Neden önemli.** Görünür bir kaynak referansının hiçbir kayda bağlanmaması, ürünün
provenance vaadini doğrudan deliyor. Diğer sızıntılardan (33. madde) ayrı tutulmasının
nedeni bu: ötekiler üslup kusuru, bu bir kaynaklandırma kusuru.

**Yapılacak.** İki taraflı: (a) `_clean_cited_text` çıplak `S\d`, `S\d-\d`, `Sxx` benzeri
kaynak-görünümlü ama geçersiz dizgileri de yakalayıp düşürsün; (b) tema ve overview
istemleri yalnız `[Sxx]` biçimini kabul ettiğini açıkça söylesin. (a) tek başına yeterli —
(b) yalnız modelin doğru üretme olasılığını artırır.

## 33. Sentez metnine iç defter dili sızıyor

**Durum:** Model, kanıtı anlatmak yerine kendi görev tanımını ve girdi paketini anlatıyor.
Aynı koşuda ölçülenler:

| Sızıntı | Nerede |
|---|---|
| "İki **yetkilendirilmiş** ifade…" — claim `status` alanı okuyucu metninde | 3.5 |
| "…'Doğrulama ve genellenebilirlik' **temalı ile** doğrudan ilişkilidir" — model kendi tema atamasını anlatıyor | 3.5 |
| "**Veri paketinde** … bilgi yoktur" ×2 | 3.3, Sonuç |
| "**orijinal okuyucu sorusunun** tüm kapsamı" ×2 | Sonuç |
| `C02`, `C03` cümle öznesi olarak | 3.3 |

`C0x` etiketleri Ek D'de tanımlı, yani okuyucu çözebiliyor; yine de sentez paragrafı iddia
defteri satırına değil kaynağa atıf yapmalı. Diğerleri karşılıksız.

**Ölçülen bağlam:** aynı koşuda **5 temanın 5'i de** `repair_forced_grounding` taşıyor —
her temanın ilk taslağı dayanaksız bulunup onarıma gitmiş. Tek seferlik sapma değil;
istemin sistematik olarak yanlış kaydı ürettiğine işaret ediyor. 33. madde çözülürken bu
oran ölçüt alınmalı: onarım payı düşmüyorsa düzeltme yüzeyseldir.

**Yapılacak.** Tema isteminde okuyucu kaydını açıkça tanımla (rapor kanıtı anlatır, kendi
üretim sürecini değil) ve `_clean_cited_text` sonrası deterministik bir kayıt kapısı ekle:
`status`, tema başlığına atıf, "veri paketi", "okuyucu sorusu" gibi meta ifadeler
yakalanırsa fallback'e düş. Eşikler ölçülmeden sabitlenmemeli.

## 34. Anahtar kelime satırı iddia olarak kabul edilmiş

**Durum:** Aynı koşunun Ek D kaydında `C03` şu: *"Keywords: artificial intelligence,
multi…"* — bir makalenin anahtar kelime satırı. Statü `qualified`, güven `0.97`, soru
ilgisi `0.96`. Rapor gövdesinde (3.3) kaynak gibi alıntılanıyor.

**Neden geçti.** Çıkarım bunu cümle sanıyor, denetim de yüksek soru ilgisi veriyor: anahtar
kelime satırı sorunun bütün terimlerini birebir taşıdığı için **ilgi skoru yapay olarak
yükseliyor.** Yani mevcut denetim bu kusuru yakalayamaz, tam tersine ödüllendirir.

**Yapılacak.** Çıkarım aşamasında yapısal öneri kalıplarını (`Keywords:`, `Abstract:`,
`Index Terms:`, `Highlights:` ve başlık/DOI satırları) iddia adayı olmaktan çıkar. Denetim
tarafında da fiil içermeyen, yüklemsiz aday bir iddia sayılmamalı. 31. maddeyle birlikte
bakılmalı: soru ilgisi tek başına kalite ölçüsü değil.

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

## Kapsam dışı bırakılanlar

**Otomatik retention** — provenance/reproducibility vaadiyle çelişiyor (1. maddeye bakınız).

**LLM'in ingestion'da parser seçmesi** — ölçülen 10.62 sn/çağrı maliyeti ve `content_hash`
bağımlılığı nedeniyle reddedildi; gerekçe raporun 9. bölümünde.

**README / PRODUCT_OVERVIEW güncellemesi** — mimari anlatımı MinIO'yu artefakt deposu olarak
tarif ediyor ve bu hâlâ doğru; parser paketi eklendiği için ileride bir gözden geçirme
gerekebilir.
