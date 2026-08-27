# Açık İşler

`developments-supplementer` branch'inde bilinen, henüz kapatılmamış işler. Ayrıntılı gerekçeler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) içindedir;
burası tek liste hâlinde durum tablosudur.

Son güncelleme: `2026-08-27`

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

## Kapsam dışı bırakılanlar

**Otomatik retention** — provenance/reproducibility vaadiyle çelişiyor (1. maddeye bakınız).

**LLM'in ingestion'da parser seçmesi** — ölçülen 10.62 sn/çağrı maliyeti ve `content_hash`
bağımlılığı nedeniyle reddedildi; gerekçe raporun 9. bölümünde.

**README / PRODUCT_OVERVIEW güncellemesi** — mimari anlatımı MinIO'yu artefakt deposu olarak
tarif ediyor ve bu hâlâ doğru; parser paketi eklendiği için ileride bir gözden geçirme
gerekebilir.
