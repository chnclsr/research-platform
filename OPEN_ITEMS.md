# Açık İşler

`developments` branch'inde bilinen, henüz kapatılmamış işler. Ayrıntılı gerekçeler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) içindedir;
burası tek liste hâlinde durum tablosudur.

Son güncelleme: `2026-08-19`

Hiçbiri sistemi bozmuyor; hepsi bilinçli olarak ertelendi. Ölçümler bu oturumda alındı ve
tekrar ölçmeye gerek kalmaması için buraya yazıldı.

## Öncelik özeti

| # | İş | Etki | Aciliyet |
|---|---|---|---|
| 1 | MinIO'da hiç temizlik yok — sınırsız disk büyümesi | Zamanla diski doldurur | **Yüksek** |
| 2 | Yedekler kaynakla aynı diskte | Disk arızasında ikisi de gider | **Yüksek** |
| 3 | PDF tabloları yapısal değil | Sayısal kanıt kaybı | Orta |
| 4 | Resume sonrası ham veri kaybı | Kesilen koşuda figür analizi çalışmaz | Orta |
| 5 | `raw_content` yedekliliği — geri yükleme yolu yok | Yedek var, kurtarma test edilmemiş | Düşük |
| 6 | MinIO anahtar düzeni tutarsız | Temizlik yazmayı zorlaştırır | Düşük |
| 7 | Teslimat ZIP'leri hiç temizlenmiyor | Yavaş büyüme | Düşük |
| 8 | crawl4ai varsayılan ayarlarla | Lazy-load içerik kaçar | Düşük |
| 9 | `_direct` 400 karakter eşiği | SPA kabuğu "başarılı" sayılabilir | Düşük |
| 10 | Eklenti B — yetenek pazarlığı | Gereksiz ayrıştırma maliyeti | Bekliyor |
| 11 | Eklenti C — `parse_document` MCP aracı | Ajanın teşhis yeteneği | Bekliyor |
| 12 | Panel `native` modda hâlâ zararlı | Yanlış modda çakışma | Belgelendi |
| 13 | Tek bir belgenin kaydı tüm koşuyu düşürüyor | Toplanan her şey kaybolur | **Yüksek** |
| 14 | Sorgu derleyicisi tek dilde kalıyor | Türkçe soru → akademik kaynak yok | **Yüksek** |
| 15 | Kanıt çıkarımında bütçe karakterle ölçülüyor | Latin dışı metinde 0 iddia | **Yüksek** |

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
hazır, sadece hedef değişmeli. Güncelleme yolu `CLAUDE.md`'de yazılı (setup'ı yeniden
çalıştırma — `-InitializeOnly` tuzağı).

## 3. PDF tabloları yapısal değil

**Durum:** HTML tabloları markdown boru ayracıyla çıkıyor (birim testleriyle kanıtlı), ancak
PDF tabloları hâlâ boşlukla hizalanmış metin. `fitz.get_text("text", sort=True)` mekânsal
düzeni koruyor ama tabloyu yapıya çevirmiyor.

**Ölçüm (PyMuPDF 1.28.2, `find_tables()` mevcut, 177 sayfalık INL raporu):**

| Ölçüm | Değer |
|---|---|
| Ham tespit | 138 tablo |
| Medyan boş hücre oranı | %55 — yarısından fazlası düzen ızgarası |
| Boş ≤%30 ve ≥2×2 filtresiyle kalan | 37 |
| Maliyet: yalnız metin | 2.62 sn |
| Maliyet: + tablo tespiti | 17.54 sn (**6.7 kat**, sayfa başına ~99 ms) |

Gerçek bir maliyet tablosunu doğru çıkardı: `Large Reactor / BOAK OCC ($/kWe) / 5,250 /
5,750 / 7,750` (Advanced / Moderate / Conservative).

**Zorluklar:** (a) aşırı tespit — yoğunluk filtresi şart; (b) **çifte sayım** —
`get_text()` tablo metnini zaten içeriyor, markdown tabloyu da eklersek aynı rakam iki kez
geçer ve iki ayrı "yerden" iddia çıkarılabilir; `table.bbox` ile o bölgeyi akıştan çıkarmak
gerekiyor; (c) çok satırlı başlıklar ve birleşik hücrelerden gelen boş sütunlar.

**Yapılacak:** `PDF_TABLE_EXTRACTION` ayarı (kapatılabilir), `PDF_TABLE_MAX_PAGES` sınırı,
yoğunluk filtresi, bbox tabanlı değiştirme. `ParsedTable` ve `to_markdown()` hazır; asıl iş
bbox değiştirme.

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

**Durum: belgelendi**, kod değişikliği planlanmıyor. `CLAUDE.md`'de kritik tuzak olarak
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
[reports/MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md](reports/MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md)
"Kalan sınırlar".

## 13. Tek bir belgenin kaydı tüm koşuyu düşürüyor

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

## 14. Sorgu derleyicisi tek dilde kalıyor

**Durum:** `protocol.languages = ["tr", "en"]` olmasına rağmen üretilen sorgu dallarının
**hepsi** soru hangi dilde yazıldıysa o dilde kalıyor. `query_compiler.py` dalları soru
metninden türetiyor ve çeviri adımı yok.

**Ölçüm:** 19 Ağustos 2026, koşu `01M0CFGYWNZBJC4WQNA5KWXY66` (Türkçe soru, akciğer BT +
yapay zeka). `arxiv`, `crossref`, `openalex`, `europe_pmc` Türkçe dizgelerle arandı ve
neredeyse tamamı 0 sonuç döndürdü; `agentsearch_web` 14 çağrının yalnız birinde 20 sonuç
verdi. Kabul edilen 5 kaynağın 3'ü çok dilli meta veri tutan tek bir Rus dergisinden, biri
878 karakterlik bir paywall sayfasıydı. Aynı soru İngilizce sorulduğunda sorun ortadan
kalkıyor — yani sınır dil desteğinde, konuda değil.

**Etki:** Türkçe soru soran kullanıcı, sistem çalışıyor görünürken sessizce boş bir korpus
alıyor. Hata yok, uyarı yok; yalnız kaynak sayısı düşük.

**Not (19 Ağustos):** Sorun kapanmadı, ama artık **koşu başlamadan görülebiliyor** — plan
onayı ekranı sorgu dallarını olduğu gibi listeliyor, dolayısıyla hepsinin tek dilde olduğu
onaydan önce fark edilip düzeltme istenebiliyor.

**Yapılacak:** `languages` listesindeki her dil için sorgu dalı üret — en ucuzu, soru
İngilizce değilse `DECOMPOSE` çıktısına İngilizce bir dal seti eklemek (tek LLM çağrısı,
aşama başına bir kez). Alternatif olarak connector başına dil tercihi: akademik
connector'lara İngilizce, web connector'larına yerel dil.

## 15. Kanıt çıkarımında bütçe karakterle ölçülüyor

**Durum:** `extract_claims()` istemi karakterle sınırlıyor (`content[:16000]`,
`neighbor_context[:4000]`). Platformun token sayacı Latin dışı metinde ciddi biçimde eksik
sayıyor, dolayısıyla İngilizce'de rahat sığan sınır Türkçe/Kiril metinde `num_ctx`'i
(8192) taşırıyor. Ollama istemi kırpıyor, model bozuk çıktı üretiyor.

**Ölçüm:** Aynı koşuda EXTRACT_EVIDENCE'ın 8 LLM çağrısının 7'si tam `prompt_tokens = 8192`
tavanına dayandı; biri `num_predict` sınırında `length` ile kesildi. Sonuç: `LLM did not
return valid JSON` ve iki turda **0 iddia**. Pasajların kendisi normaldi (ortalama 628,
azami 700 token).

**Yapılacak:** İstemi token bütçesiyle kur: `llm_context_tokens` eksi çıktı payı eksi sistem
istemi kadar bütçe ayır, hedef pasaj ile komşu bağlamı bu bütçeye göre kırp. Ölçüm için
gerçek tokenizer yoksa Latin dışı karakter oranına göre düzeltilmiş bir tahmin bile
yeterli. `done_reason = "length"` da bir olay olarak yazılmalı — bugün sessiz.

---

## Kapsam dışı bırakılanlar

**Otomatik retention** — provenance/reproducibility vaadiyle çelişiyor (1. maddeye bakınız).

**LLM'in ingestion'da parser seçmesi** — ölçülen 10.62 sn/çağrı maliyeti ve `content_hash`
bağımlılığı nedeniyle reddedildi; gerekçe raporun 9. bölümünde.

**README / PRODUCT_OVERVIEW güncellemesi** — mimari anlatımı MinIO'yu artefakt deposu olarak
tarif ediyor ve bu hâlâ doğru; parser paketi eklendiği için ileride bir gözden geçirme
gerekebilir.
