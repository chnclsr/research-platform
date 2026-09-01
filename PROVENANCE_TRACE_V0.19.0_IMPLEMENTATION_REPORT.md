# Kaynak → referans izi — v0.19.0

Platform sürümü: `v0.19.0`

Belge sürümü: `1.0`

Tarih: `2026-09-01`

## Kapsam

Ham bir kaynağın docx'teki bir referansa dönüşene kadar izlediği yol veritabanında vardı —
ama sonuna kadar değil. Bu iş eksik son halkayı kaydediyor ve zincirin tamamını panelde
görünür kılıyor.

Şema göçü (`0010_report_citations`) ve üç servisi birden kapsadığı için kendi raporu var;
kökteki geliştirme raporunda tek satırlık işaretçisi bulunuyor.

---

## Sorun

Zincirin ilk altı halkası ilişkiseldi ve sorgulanabiliyordu:

```
sources → source_versions → passages → evidence_links → claims → export
```

Yedincisi hiçbir yerde durmuyordu. `[S03]` etiketleri
[`word_report.py`](src/research_platform/word_report.py) içinde `enumerate(sources, 1)` ile
**belge yazılırken** üretiliyor, hangi sentez bölümünün hangi kaynağı andığı ise
`SynthesisPackage.sections[].source_ids` içinde bellekte yaşıyordu. `build_exports` dönünce
ikisi de kayboluyordu.

Eksik olan bir istatistik değildi. **Kanıtı olan bir kaynak rapordan dört ayrı sebeple
düşebiliyor** ve dışarıdan dördü de aynı görünüyordu — katalogda olan, başka hiçbir yerde
olmayan bir kaynak:

1. Hiç kanıt çıkmaması.
2. Kanıtın rapor eşiğini (`_is_reportable`) geçmemesi.
3. Bölüm taslağının atıf denetiminde elenmesi.
4. Modelin, kendisine sunulan kaynağı hiç anmaması.

Üçüncüsü özellikle sessizdi.
[`report_synthesis.py`](src/research_platform/report_synthesis.py) içindeki
`_clean_cited_text`, izinli küme dışında **tek bir** atıf görünce bölümün tamamını boş
string'e çeviriyor; kaynak kimseye söylenmeden rapordan çıkıyordu.

Panel tarafında da zincir yarıda kesiliyordu: mevcut huni `final_sources` basamağında
bitiyor, pasaj/kanıt/iddia/atıf basamakları hiç yoktu. Koşu çekmecesinde tek bir alıntı bile
görünmüyordu.

---

## Kritik ayrım: sunulan ≠ anılan

İşin dayandığı tespit bu. `SynthesisSection.source_ids`, o temanın kanıt paketinin modele
**sunduğu** etiketleri tutar — modelin **andığı** etiketleri değil. İkisi rutin olarak
farklıdır: paket bir temanın claim'lerinin arkasındaki her kaynağı taşır, model ise anmaya
değer bulduğu altkümeyi anar.

Bu yüzden yeni bir saf fonksiyon eklendi:

```python
def cited_labels(section: SynthesisSection) -> set[str]:
    """Bölümün prose'unda gerçekten geçen [Sxx] etiketleri."""
```

`synthesis`, `consensus`, `disagreements` ve `implications` alanlarının hepsi taranır —
yalnız "Ayrışmalar" altında anılan bir kaynak da anılmıştır.

**Yönetici özeti, çalışmalar arası değerlendirme ve sonuç birer sözde-bölüm olarak
taranıyor.** Bunlar da belgenin parçası; yalnız temalı bölümlere bakmak, sadece özette anılan
bir kaynağı `offered_not_cited` diye kaydeder ve birini olmayan bir hatayı aramaya gönderirdi.

### Yan bulgu — tema-kanıt haritası fazla kapsam iddia ediyordu

Aynı karışıklık docx'teki figürde de vardı. `_theme_evidence_map` hücrelerini
`profile.source_label in section.source_ids` ile boyuyordu, yani **pakete girmiş ama atıf
almamış** bir çalışmayı temaya katkı yapmış gibi gösteriyordu. Figür, belgenin verdiğinden
fazla kapsam iddia ediyordu. Aynı `cited_labels` yardımcısıyla düzeltildi.

---

## Kayıt: `report_citations`

Koşu başına, **kaynak başına bir satır** — rapora giren de girmeyen de. Yalnız anılanları
tutan bir tablo sorunun kolay yarısını cevaplardı.

| Sütun | Anlamı |
|---|---|
| `label`, `number` | Prose'un andığı `S03` ve kataloğun sırası |
| `cited_sections` | Prose'u bu etiketi **gerçekten** anan bölümler |
| `offered_sections` | Kanıt paketi bu kaynağı **sunan** bölümler |
| `citation_count` | Belgedeki toplam `[Sxx]` geçişi |
| `claim_ids`, `evidence_ids` | Atıfın arkasındaki denetlenmiş kayıtlar |
| `drop_reason` | `NULL` = rapora girdi; aksi hâlde nerede durduğu |

`drop_reason`'ın nullable olması ve `NULL`'un başarı hâli olması bilinçli: tersi, asıl önemli
sonuç için bir sentinel string gerektirirdi.

`(run_id, source_id)` tekil. Export iki kez koşabildiği için yazım **sil-yeniden yaz**
biçiminde: yeniden koşan bir export etiketleri yeniden numaralar ve ikinci geçişte düşen bir
kaynak, aksi hâlde ilk geçişin yazdığı satırı üstünde taşırdı.

`purge_run` listesine eklendi — bu tabloda da foreign key yok, adlandırılmazsa tarif ettiği
her şeyden sonra hayatta kalırdı.

### Geriye dönük doldurma yapılmadı

Bilinçli. Mevcut bir koşu için bu satırları yeniden üretmek LLM sentezini baştan koşturmak
demek, o da teslim edilenden **başka** bir rapor üretir. Gönderilen belgeyi tarif etmeyen bir
atıf kaydı, boş olandan kötüdür. Eski koşular panelde "rapor henüz üretilmedi" görünür.

---

## Panel

### Zincir şeridi ve akıbet

`_run_detail` içine beş koşu kapsamlı toplu sorgu eklendi. Tek join yerine beş sorgu, çünkü
zincir dört farklı granülariteli tabloya yayılıyor — bir kaynağın sürümleri, bir sürümün
pasajları, bir pasajın kanıtı — ve tek sorgu satırları çarpar, sonra distinct ile geri
toplamak gerekirdi.

Pasaj basamağı Python'da toplanıyor: `retrieval_score` pasajın JSON metadata'sının içinde ve
onu SQL'de çıkarmak SQLite ile PostgreSQL'de farklı yazılıyor. Yalnız iki sütun okunuyor,
ikisi de `text` veya `embedding` değil; çekmece elle yenileniyor, 4 saniyelik yoklamada
değil.

Şerit **yalnız bir hücreyi** `stop` işaretler. Edinilemeyen bir kaynak ayrıca "retrieval'da
başarısız" değildir; ikisini birden söylemek, satırın geri kalanını açıklayan tek olguyu
gömerdi. Sonraki basamaklar `off` olur.

| Basamak | Koşul |
|---|---|
| `discover` | `SourceRow` var |
| `acquire` | Sürüm var ve `access_status != "unavailable"` |
| `parse` | Pasaj sayısı > 0 |
| `retrieve` | Herhangi bir pasajın `retrieval_score` > 0 |
| `evidence` | `evidence_links` > 0 |
| `claim` | Bağlı claim `supported` veya `qualified` |
| `report` | Atıf satırı var ve `drop_reason is None` |

`claim` basamağında `_is_reportable`'ın ince eşiği (alaka ve destekleyici kanıt tabanları)
**uygulanmıyor**. Denetimi geçen ama o tabanı geçmeyen bir claim rapor basamağında duruyor;
sebebi orada export'un kendi `not_reportable` kaydı söylüyor.

Atıf kaydı hiç yoksa `no_export` ile `offered_not_cited` ayrılıyor: birincisi henüz oraya
gelmemiş bir koşu, ikincisi raporun gerçekten düşürdüğü bir kaynak. Ayırmamak olmayan bir
başarısızlık uydururdu.

### Dikey iz

Yeni `GET /api/runs/{run_id}/sources/{source_id}/trace`. Koşu detayından ayrıldı, aşama
dökümüyle aynı gerekçeyle: pasaj ve alıntı **metni** okuyor, koşu detayı bunu hiç yapmıyor ve
500 kaynak için karşılayamazdı. `_may_see` guard'ı aynı; başkasının koşusu 404 döner —
ayrı bir 403, kimliği yoklayan bir çağırana kimliğin var olduğunu doğrulardı.

Ham kopya karakter sayısı 0 olabildiğinde bunun **checkpoint'te bilerek boşaltıldığı**
ayrıca yazılıyor. Yoksa sıfır, kayıp bir indirme gibi okunuyor ve birini olmayan bir dosyayı
aramaya gönderiyordu.

Kurtarma turu çalışmışsa (`recovered_run_corpus` / `recovered_versions > 0`) ize rozet
düşüyor: aksi hâlde tur kaydında `no_new_source_versions` görülüp pasajların nereden geldiği
çözülemiyor.

### Koşu düzeyi uyarı

Kaynak toplayıp kanıt çıkaramayan koşu bunu tablonun üstünde **bir kez** söylüyor
(`empty_synthesis_with_corpus`). v0.18.2'de rapora düşen notun panel karşılığı; onsuz ekran,
sebebi yazmayan altmış kırmızı satır oluyordu.

---

## Doğrulama

**Tam kapı: 709 passed.** Yeni testler: `tests/test_report_citations.py` (11 — dört
`drop_reason` dalının her biri, sunulan/anılan ayrımı, yedek bölümün atıflıysa düşüş
sayılmaması), zincir mantığı (6), panel endpoint'leri (6), Word raporu kaydı (2), `purge_run`
cascade'i ve boru hattı ucundan uca atıf yazımı.

Hedefli Ruff: yeni dosyalar temiz; değişen dosyalarda taban ihlal sayısı artmadı —
`control_panel_ui.py` dışında hiçbirinde değişiklik yok, orada eklenen 44 ihlalin tamamı o
dosyanın mevcut 182'siyle aynı sınıf (E501, tek satırlık yoğun JS).

Migration ileri/geri: `0009 → 0010 → 0009 → 0010` temiz.

**Canlı doğrulama.** Gerçek bir boru hattı koşusunda kayıt yazıldı:

```
S01 n=1 count=8 drop=None
   cited=['Bulgular ve karşılaştırmalı sonuçlar', 'Sınırlılıklar ve riskler',
          'Yönetici Özeti', 'Sonuç']
   offered=['Bulgular ve karşılaştırmalı sonuçlar', 'Sınırlılıklar ve riskler']
```

Sözde-bölüm taraması tasarlandığı gibi çalışıyor: kaynak iki temada anılıyor, ayrıca özet ve
sonuçta.

Canlı veritabanındaki sepsis koşusu (`01M1E06KQSW6HQHNDCGERTKRGW`, 57 kaynak) panelde:

```
not_retrieved 44 · no_export 11 · claim_below_threshold 1 · no_evidence 1
```

Bir kaynağın dikey izi `raw_cleared: True`, `recovered: True`, 23 pasaj, 0 getirilen,
0 kanıt gösteriyor — yani v0.18.2'de düzeltilen kesinti hatasının parmak izi artık panelde
okunabiliyor. İzleme katmanının ilk işi, kendisinden önceki turun düzelttiği hatayı
görünür kılmak oldu.

### Kurulumda atlanan adım

Panel bir tur boyunca 500 döndü: `relation "report_citations" does not exist`. Migration
geçici bir SQLite dosyasında doğrulanmış, **canlı PostgreSQL'e uygulanmamıştı**. Kod
dağıtımı ile şema göçü ayrı adımlar; birinciyi yapıp ikinciyi rapor etmemek panelin tamamını
düşürüyor.

Ayrıca `api` ve `worker` derlenmiş imajlardan koşuyor ve `src` bind-mount edilmiyor — atıf
yazan taraf export'ta olduğu için `docker compose up -d --build api worker` yapılmadan yeni
export'lar kayıt üretmiyor. Panel (host'ta editable kurulu) yeni kodu hemen görüyor; bu
asimetri şema veya export davranışı değiştiren her işte geçerli.
