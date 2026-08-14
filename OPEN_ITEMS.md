# Açık İşler

`developments` branch'inde bilinen, henüz kapatılmamış işler. Ayrıntılı gerekçeler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) içindedir;
burası tek liste hâlinde durum tablosudur.

Son güncelleme: `2026-08-14`

Hiçbiri sistemi bozmuyor; hepsi bilinçli olarak ertelendi. Ölçümler bu oturumda alındı ve
tekrar ölçmeye gerek kalmaması için buraya yazıldı.

## Öncelik özeti

| # | İş | Etki | Aciliyet |
|---|---|---|---|
| 1 | MinIO'da hiç temizlik yok — sınırsız disk büyümesi | Zamanla diski doldurur | **Yüksek** |
| 2 | Yedekler kaynakla aynı diskte | Disk arızasında ikisi de gider | **Yüksek** |
| 3 | PDF tabloları yapısal değil | Sayısal kanıt kaybı | Orta |
| 4 | Resume sonrası ham veri kaybı | Kesilen koşuda figür analizi çalışmaz | Orta |
| 5 | `raw_content` çift depolanıyor | Postgres gereksiz büyür | Düşük |
| 6 | MinIO anahtar düzeni tutarsız | Temizlik yazmayı zorlaştırır | Düşük |
| 7 | Teslimat ZIP'leri hiç temizlenmiyor | Yavaş büyüme | Düşük |
| 8 | crawl4ai varsayılan ayarlarla | Lazy-load içerik kaçar | Düşük |
| 9 | `_direct` 400 karakter eşiği | SPA kabuğu "başarılı" sayılabilir | Düşük |
| 10 | Eklenti B — yetenek pazarlığı | Gereksiz ayrıştırma maliyeti | Bekliyor |
| 11 | Eklenti C — `parse_document` MCP aracı | Ajanın teşhis yeteneği | Bekliyor |
| 12 | Panel `native` modda hâlâ zararlı | Yanlış modda çakışma | Belgelendi |

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

## 5. `source_versions.raw_content` çift depolanıyor

**Durum:** Ham gövde hem MinIO'da (`raw_snapshot_key`) hem bu TEXT sütununda.

**Not:** `raw_snapshot_key` yazılıyor ama **hiçbir yerden okunmuyor** — MinIO snapshot'ları
şu an salt-yazılır arşiv. Bu maddeyi çözmek onları işlevsel hâle de getirir.

**Etki:** Sınır aşımı yaratmaz (TEXT 1 GB, TOAST sıkıştırır) ama `postgres-data` gereksiz
büyür. `13_raw_sources.jsonl` de base64 PDF'leri gömdüğü için büyük koşularda yüzlerce MB.

**Yapılacak:** Export'u `provenance.raw_snapshot_key` üzerinden MinIO'dan **akıtarak**
üretmek; çıktı sözleşmesi değişmez, yalnız Postgres kopyası gider.

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

## Kapsam dışı bırakılanlar

**Otomatik retention** — provenance/reproducibility vaadiyle çelişiyor (1. maddeye bakınız).

**LLM'in ingestion'da parser seçmesi** — ölçülen 10.62 sn/çağrı maliyeti ve `content_hash`
bağımlılığı nedeniyle reddedildi; gerekçe raporun 9. bölümünde.

**README / PRODUCT_OVERVIEW güncellemesi** — mimari anlatımı MinIO'yu artefakt deposu olarak
tarif ediyor ve bu hâlâ doğru; parser paketi eklendiği için ileride bir gözden geçirme
gerekebilir.
