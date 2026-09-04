# Kanıt bütünlüğü — v0.22.0

Platform sürümü: `v0.22.0`

Belge sürümü: `1.0`

Tarih: `2026-09-04`

---

## Kapsam

Üç artım, tek tema: **kanıt iyi görünüyordu ama değildi.**

1. arXiv'in reddettiği sorgu koşuya "0 sonuç" olarak geçiyordu.
2. Akademik adayın açık erişim tam metni elde olduğu hâlde yayıncı HTML'i kazınıyordu.
3. İddialar sayılıyordu ama değerlendirilmiyordu.

Üçü aynı raporu paylaşıyor çünkü tek bir kaynaktan hasat edildiler, tek sürümde
çıkıyorlar ve aynı hata sınıfını kapatıyorlar: sistemin doğru çalıştığını sandığı yerde
sessizce bilgi kaybetmesi. Kendi raporu var çünkü üç modül, iki yeni bileşen (JATS
parser, süreç genelinde limiter) ve servisler arası edinme + dışa aktarım değişikliği
içeriyor; şema göçü **yok** — not `claim.audit` içindeki şemasız JSON'a yazılıyor.

### Kaynak ve atıf

Bilgi, MIT lisanslı [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)
deposundaki `paper-lookup` ve `scientific-critical-thinking` skill'lerinden **port
edildi**. Hiçbir kod kopyalanmadı, vendor dizini açılmadı; depoya üçüncü taraf dosyası
girmedi. Referans belgelerdeki API hazard bilgisi ve değerlendirme rubriği okundu, kendi
async httpx / LangGraph mimarimize uygun kod bizim tarafımızdan yazıldı. Deponun istediği
akademik atıf: arXiv:2609.00065.

---

## Kritik ayrım: sessiz sıfır ≠ sonuç yok

Raporun omurgası bu. Bir sağlayıcı üç farklı şey söyleyebilir ve ikisi dışarıdan aynı
görünür:

| Sağlayıcının dediği | Bizim gördüğümüz (önce) | Doğru okuma |
|---|---|---|
| "Sorgun bozuk" | 0 sonuç | Hata — düzelt, tekrarlama |
| "Eşleşme yok" | 0 sonuç | Bilgi — kapsam boşluğu |
| "Yavaşla" | 0 sonuç / bozuk XML | Bekle, daha sert deneme |

`ArxivConnector` üçünü de `[]`'e indiriyordu. Aynı kalıp edinmede de vardı: bir yayıncı
özet sayfası 400 karakteri geçtiği için "başarı" sayılıyor, tam metnin hiç alınmadığı
kaybolıyordu. Ve denetimde: üç zayıf çalışmayla bir güçlü çalışma aynı `supported`
etiketini alıyordu.

---

## arXiv: reddedilen sorgu

`ArxivConnector.search_scoped` her `<entry>`'yi makale sayıyordu
([implementations.py](src/research_platform/connectors/implementations.py)). arXiv bozuk
bir parametreye tek bir `<entry><title>Error</title></entry>` ile yanıt veriyor; o
girdinin `<id>`'si çözülebilir bir URL değil, dolayısıyla `candidate()`
([base.py:64-98](src/research_platform/connectors/base.py#L64-L98)) `HttpUrl`
doğrulamasında düşüyor ve `None` dönüyordu. Veri zehirlenmiyordu — teşhis kayboluyordu.

### Yeni `ConnectorQueryError`

`pipeline.py`'daki arama düğümü connector çağrısını zaten `except Exception` ile sarıp
`connector_errors` ve `connector_error` event'i üretiyor. Yani sessizliğe yol açan şey
`[]` döndürmekti; **fırlatmak mevcut kanaldır**, yeni altyapı gerekmedi. Bu, AGENTS.md'de
"connector hataları sessiz" diye kaydedilen tuzağın teşhis yarısını kapatıyor;
OPEN_ITEMS #22 (`_acquire_node` izolasyonu) komşu ama dokunulmadı, açık kalıyor.

### Üç vaka, üç politika

| Durum | Davranış | Gerekçe |
|---|---|---|
| 200 veya 400 + `<title>Error</title>` | Anında `ConnectorQueryError`, **sıfır deneme** | Reddedilen sorguyu tekrarlamak yarım saatlik throttle satın alıyor |
| 429, gövde düz metin `Rate exceeded.` | Geri çekil, en çok 3 deneme, `min(30, max(3, delay))` | Diğer connector'lardaki `1.0` taban arXiv'in kendi minimumunun altında |
| `httpx.TransportError` | Fırlat, **sıfır deneme** | Aktif throttle'a yeniden bağlanmak onu sürdürüyor |
| `totalResults == 0` | `[]`, istisna yok | Gerçek eşleşme yokluğu; metrikler bunu `success: True, result_count: 0` olarak ayırıyor |

**Canlı ölçüm 2026-09-04.** Bugünkü arXiv `start=notanumber` için 200 değil **400**
döndürdü — ama gövde referansta anlatılan hata girdisinin aynısını taşıyordu. Bu yüzden
hata girdisi kontrolü `raise_for_status()`'un **önüne** alındı: her iki durumda da
"start must be an integer" çıkıyor, çıplak bir `HTTPStatusError` değil.

### Pacing: neden paylaşımlı limiter

`SemanticScholarConnector._get` ve Crossref'teki kalıp **örnek başına** kilit kullanıyor.
`build_registry` her koşuda yeni connector kurduğu için `search_concurrency=8` altında N
koşu N bağımsız 3 saniye bütçesi alıyor. Edinme katmanı bu hatayı daha önce
`shared_domain_limiter` ile çözmüştü ve gerekçe zaten oraya yazılmıştı. Fark şu:
`wait()` yalnız istek *başlangıçlarını* seyreltiyor, kilidi istekten önce bırakıyor.
arXiv tek bağlantı istediği için `hold()` eklendi — slot istek boyunca tutuluyor ve saat
çıkışta damgalanıyor, böylece yavaş bir yanıt gerçek aralığı yemiyor.

`DomainLimiter`, `_SHARED_LIMITERS` ve `shared_domain_limiter`
[rate_limits.py](src/research_platform/rate_limits.py) dosyasına birebir taşındı. Bir
connector'ın `acquisition.py`'yi import etmesi döngü yaratmazdı ama 25 satırlık bir
yardımcı için `github_repository`, `parsers` ve tüm servisi connector import yoluna
sokardı.

Yeni ayar `arxiv_rps: float = Field(0.33, gt=0, le=1.0)` — üst sınır 1, hiçbir kurulum
sağlayıcının ilan ettiği limitin üstüne çıkamıyor. Testte `settings.testing` ile aralık
sıfırlanıyor; limiter süreç geneli olduğu için aksi hâlde ikinci arXiv testi 3 saniye
gerçekten uyurdu.

---

## Açık erişim tam metni

### Ekleme noktası: `_direct`'ten **önce**

Planın ilk hâli "`_direct` ile `_scholarly_metadata_document` arasına" diyordu. Bu
yanlıştı. `_direct` ayrıştırılmış metin ≥ 400 karakter olan her yanıtı başarı sayıyor
([acquisition.py](src/research_platform/acquisition.py)) ve bir yayıncı özet sayfası bunu
rahatça geçiyor. `_direct`'ten sonraki bir adım yalnızca `_direct` zaten başarısız
olduğunda çalışırdı — yani açık erişim çözümlemesinin hedeflediği adayların **azınlığında**.
Özellik yazılır, hedef kitlesinin küçük bir kısmında tetiklenirdi.

Doğru yer `_github_repository` ile `_direct` arasında (indeks 1), akademik + hedef-var
guard'ıyla. `_direct` geri düşüş olarak kalıyor, kapı bekçisi olmuyor.

Bu, test kırılganlığını da çözdü: `ACQUISITION_STRATEGY_ORDER[0]` ve `[-2:]` iddiaları
değişmedi, ve `strategies_tried == ["direct", "scholarly_metadata"]` iddiası da yeşil
kaldı — çünkü adım hedefi olmayan adayda `tried`'a **hiçbir şey yazmadan** dönüyor. Bu
sessizlik sözleşmenin kendisi: paketteki her tam-liste iddiası aksi hâlde bakım vergisine
dönerdi. Planın öngörmediği dördüncü bir iddia
([test_research_plan.py](tests/test_research_plan.py)) koşu öncesi plan kartının strateji
sırasını doğruluyordu; o meşru şekilde güncellendi.

### NCBI değil, Europe PMC

Planın ilk hâli NCBI/PMC + `api_key` diyordu. Europe PMC — **zaten kayıtlı connector** —
aynı JATS'i anahtarsız veriyor. Doğrulandı 2026-09-04:

```
$ curl -s -o /tmp/jats.xml -w "http=%{http_code} bytes=%{size_download}\n" \
    https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7029759/fullTextXML
http=200 bytes=134481
```

`ncbi_api_key`, ayrı bir limiter ve ayrı bir `.env` bloğu artımdan tamamen düştü.

### JATS parser ve `element.tail`

`structured._flatten_xml` her elemanın `tail`'ini düşürüyor: `<p>text <italic>x</italic>
more</p>` → " more" kayboluyor. JATS gövdesi baştan sona karma içerik olduğu için bu bir
kenar durum değil, kuralın kendisi. **Mevcut hata düzeltilmedi**: `content_hash`
ayrıştırılmış metnin sha256'sı ve source-version dedup'ı, MinIO anahtarlarını ve passage
offset'lerini sürüyor; düzeltmek saklanmış her XML kaynağını yeniden hash'lerdi. Bunun
yerine [jats.py](src/research_platform/parsers/jats.py) yazıldı, öncelik 10 ile
priority-0 `plain_text` fallback'inin önüne geçiyor ve `can_parse` JATS kökünü
kokluyor — genel XML eski yolunda kalıyor.

Ayrıştırma yalnız belge sırasında dolaşıyor; çıktıya ulaşan hiçbir `set`/`dict`
iterasyonu yok. Bölüm başlıkları bir kez yazılıyor (ilk sürümde `<title>` hem başlık hem
paragraf olarak iki kez çıkıyordu, düzeltildi). `<ref-list>` ve `<back>` metinden
düşürülüp `parse_provenance` içinde sayılıyor.

### Kalite kapısı

`open_access_min_chars` varsayılanı **2000** — `_direct`'in 400'ünün çok üstünde.
Gerekçe: 400 eşiği bozulmuş bir ayrıştırmanın sessizce kaybolmasını engellemek için var;
burada bir sağlayıcıdan tam metin **istedik**, kısa bir gövde çözümlemenin ıskaladığı
anlamına geliyor. Iskalarsa `open_access_rejected` yazılıp `_direct`'e geri düşülüyor.
Bu, OPEN_ITEMS #9'u (SPA kabuğunun 400 eşiğini geçmesi) yalnız OA yolu için kapatıyor;
`_direct` için açık kalıyor.

`_direct`'in fetch döngüsü **bilinçli olarak** ortak yardımcıya çıkarılmadı. O döngü
400-karakter merdivenini, alternatif-parser denemesini ve redirect zincirini taşıyor;
çıkarmak paketteki en flake-şüpheli yola 100 satırlık değişiklik olurdu. ~40 satır tekrar
daha ucuz risk.

### Bilinçli dışarıda bırakılanlar

PubMed E-utilities araması, bioRxiv/medRxiv API'leri, CORE, NCBI efetch JATS ve ikisi de
varken PDF-JATS uzlaştırması. Europe PMC zaten biyomedikal anahtar kelime araması yapıyor
ve bioRxiv/medRxiv preprint'lerini indeksliyor; yeni bir arama connector'ı ise
`recovery.py`, `query_compiler.py`, `build_registry`, health raporu ve `coverage.py`
aritmetiğinde eşgüdümlü düzenleme isterdi — yanlış özelliğe bağlanmış ikinci bir artımlık
patlama yarıçapı. OPEN_ITEMS'a madde olarak yazıldı.

---

## İki katmanlı kanıt değerlendirmesi

`audit()` sayarak karar veriyor. Bu bir iddianın **doğrulandığını** söylüyor; doğrulayan
çalışmaların o iddiayı **taşıyıp taşıyamayacağını** söylemiyor.
`adversarial_review()` ise adının vaat ettiğini yapmıyordu: claim status'larını sayıp
kimsenin okumadığı bir event yazıyor, sabit Türkçe bir outline üretiyor ve varsayılan
kapalı bir HITL çağırıyordu.

### Hibrit: model önerir, kod karar verir

[claim_appraisal.py](src/research_platform/claim_appraisal.py), `probe_factory` desenini
izliyor. İki kural öneriyi güvenli kılıyor:

- Model sinyali notu **yalnızca düşürebilir**, asla yükseltemez. Kendinden emin bir model
  ince bir iddiayı yukarı konuşamaz.
- Her sinyal `claim.audit`'te zaten duran bir olguyla **doğrulanmak zorunda**:
  `contradicted` için `counter_evidence > 0`, `single_source_dependence` için
  `independent_domains <= 1`. Doğrulanmayan sinyal düşürülüp run event'ine yazılıyor —
  modelin ne dediği ve neden reddedildiği kayıtta kalıyor.

Model çökerse deterministik nota iniliyor, koşu düşmüyor. Prompt `self.llm` ile
gidiyor, `_preparation_provider()` ile değil: iddia metni korpustan geliyor ve kurulumun
veri sınırı içinde kalmalı.

`generated_by` iddia başına yazılıyor, koşu başına değil. Çalışma seviyesinde tek bir
"model" değeri, modelin hiç bahsetmediği ya da bütün sinyalleri reddedilen bir iddiayı
model türevi diye etiketlerdi — köken alanının tam olarak bir adım fazla iddia etmesi.
Bir iddia ancak doğrulanmış bir model sinyali notunu düşürdüyse `model` etiketi alıyor.

### Not merdiveni ve klinik tavan

| Not | Koşul |
|---|---|
| `strong` | destekleyici ≥ minimum, bağımsız domain ≥ minimum, çelişen kanıt yok |
| `moderate` | `supported` ama yukarıdakilerden biri sağlanmıyor |
| `limited` | `qualified`, ya da tek bağımsız domain |
| `insufficient` | geçerli destekleyici kanıt yok |

Klinik katman **tavan** uyguluyor, yeniden sıralamıyor. "İyi güçlendirilmiş tek bir RCT
üç n=12'yi geçer" hiçbir sıralama anahtarına dokunmadan böyle ifade ediliyor: en iyi
destekleyici tasarım gözlemsel/retrospektif ise tavan `moderate`, yalnız anlatısal derleme
ise `limited`, ve çelişen bir kaynağın tasarımı tüm destekleyicileri geçiyorsa bir basamak
düşülüp `contradicted_by_stronger_design` gerekçesi yazılıyor.

### Katman puanla seçiliyor

`ResearchProtocol` ekstra alan yasaklıyor ve bir domain alanı yok, dolayısıyla çıkarım
gerekiyordu. Tek tetikleyici yerine puan-eşik kullanıldı, çünkü `europe_pmc ⇒ clinical`
bir yarı iletken tedarik zinciri koşusuna — tek bir biyomedikal kayda değdiği için —
kanıtının güçsüz olduğunu söylerdi; `akademik aile ⇒ clinical` ise her arXiv ML koşusuna.

| Ağırlık | Koşul |
|---|---|
| +2 | kaynaklarda `europe_pmc` |
| +1 | `SourceFamily.ACADEMIC` seçili ailelerde |
| +1 | `is_academic_publication_query(primary_question)` |
| +2 | ≥3 kaynak klinik tasarıma sınıflanıyor |
| −2 | `epo_ops`/`sec_edgar` var ve `europe_pmc` yok |

**clinical ⟺ puan ≥ 3.** Patent koşusundaki tek başına bir `europe_pmc` kaynağı
2 − 2 = 0 → universal. Yalnız OpenAlex/Crossref'li ama klinik tasarımlı bir onkoloji
koşusu 1 + 2 = 3 → clinical; connector adına bakan bir kural bunu kaçırırdı. Karar
kanıtı event'e yazılıyor, böylece yanlış ateşleme gizemli değil teşhis edilebilir.

Tasarım etiketleri `report_synthesis._classify_design` tablosundan okunuyor. Alt çizgili
adı import etmek ya da regex tablosunu kopyalamak yerine ince bir public sarmalayıcı
(`source_design_labels`) eklendi — böylece katman kararı ile raporun bastığı tasarım
sütunu asla ayrışamıyor. Bir test bu sözleşmeyi gelecekteki kopyala-yapıştıra karşı
koruyor.

### Not raporlanabilirliği **değiştirmiyor**

`exporter._is_reportable` tek raporlanabilirlik kapısı ve `ordered_reportable`
sıralaması okurun ne göreceğine karar veriyor. İkisine dokunmak hangi iddiaların teslim
edildiğini sessizce değiştirirdi ve hata modu görünmezdir: **bir iddiayı sessizce
kaybetmiş rapor, o iddiaya hiç sahip olmamış rapordan ayırt edilemez.** Bunun yerine
amaçlanan sonuç düzyazıyla alınıyor — not `_claim_evidence_block` üzerinden çizim
modeline geçiyor ve model "üç küçük tek merkezli seri, bir çok merkezli çalışmaya karşı"
yazabiliyor. Bu, okurun sayfada denetleyebileceği bir çıktı; sessiz bir yeniden dizme
değil. "Değerlendirme raporlanabilirliği kapılamalı mı?" sorusu, gerektirdiği ölçümle
birlikte OPEN_ITEMS'a yazıldı.

Gösterim yüzeyleri: `_claim_evidence_block` (modele giden tek yer), `render_findings`,
`11_audit_report.md` (not histogramı + katman + karar kanıtı), Word Ek D (mevcut durum
hücresinde, yedinci sütun açmadan), ve bedava olarak `04_claim_ledger.jsonl` ile
`GET /claims`. **Yeni artefakt üretilmedi** — bu bilinçli bir kısıt, `len(artifacts) == 21`
iddiası korunuyor.

### `report_outline_guidance` silindi

Üç yönden de ölüydü: yalnız varsayılan kapalı bir HITL reddedildiğinde yazılıyordu;
incelediği outline sabit bir Türkçe listeydi; ve `build_exports` parametreyi tanımlayıp
gövdede hiç okumuyordu. Bildirilmiş-ama-kullanılmayan bir parametre, parametresizlikten
kötüdür — özellik gibi okunur. HITL çağrısı kaldı ama gerçek bir yük aldı: katman, not
histogramı ve düşürülen iddialar.

---

## Doğrulama

**Tam kapı: 866 passed** (`TESTING=true .venv/bin/python -m pytest -q`, 67 sn), sürüm
`pyproject.toml` içinde 0.22.0'a yükseltilip `uv pip install -e ".[dev]"` ile yeniden
kurulduktan sonra. Başlangıç 813, artımlar sırasıyla +13 / +23 / +30 test ekledi.

| Dosya | Yeni test |
|---|---|
| `tests/test_arxiv_connector.py` | 10 |
| `tests/test_rate_limits.py` | 4 |
| `tests/test_open_access.py` | 13 |
| `tests/test_parsers.py` | 7 + JatsParser konformans paketine eklendi |
| `tests/test_claim_appraisal.py` | 22 |
| `tests/test_pipeline.py` | 3 (`adversarial_review()`'un ilk doğrudan çağrıları) |
| `tests/test_report_synthesis.py` | 3 |

**Hedefli Ruff — taban değişmedi.** Düzenlemeden önce kaydedilen sayılar karşısında:
`acquisition.py` 7 → 7, `connectors/implementations.py` 1 → 1, `connectors/base.py`
1 → 1, `config.py` 0 → 0, `pipeline.py` 21 → 21, `report_synthesis.py` 7 → 7,
`word_report.py` 1 → 1, `parsers/registry.py` 1 → 1, `tests/test_parsers.py` 5 → 5,
`tests/test_pipeline.py` 5 → 5. Yeni dosyaların hepsi temiz. İki yeni blind except
deponun yerleşik `# noqa: BLE001 - gerekçe` desenine uyduruldu. Tam depo Ruff'ı temiz
**değildir** ve öyle raporlanmıyor.

**Göç yok.** Not `claim.audit` içindeki şemasız JSON'a yazılıyor; anahtar bütünüyle
yeniden atanıyor (`claim.audit = {**claim.audit, "appraisal": ...}`) çünkü düz bir `JSON`
sütununda SQLAlchemy yerinde mutasyonu görmez. AUDIT'in yazdığı sekiz üst düzey anahtar
dokunulmadan kalıyor ve bir test bunu doğruluyor.

**Canlı doğrulama.** Europe PMC üzerinden gerçek bir makale, kazıyıcıya hiç düşmeden:

```
success: True
method: open_access
strategies: ['open_access']
parser: jats_structured
chars: 37909
scope: full_text
resolved_by: europe_pmc
kind: pmc_jats
provenance: {'engine': 'jats', 'sections': 17, 'references_dropped': 74}
head: # Therapeutic strategies in an outbreak scenario to treat the novel coronavirus
      originating in Wuhan, China  ## Abstract  A novel coronavirus (2019-nC
```

134 KB JATS → 37.909 karakter yapısal düzyazı, 17 bölüm, 74 referans metinden düşürülmüş.

Canlı arXiv:

```
valid query -> 3 results
  echo: arXiv Query: search_query=all:graph AND all:neural AND all:network&id_list=&start=0...
  rewritten: False
http: 400
error detail detected: start must be an integer
```

### Kurulumda dikkat edilecek

`src/` değişiklikleri `api` ve `worker` imajlarına ancak yeniden derlemeyle ulaşır;
kontrol paneli host-native olduğu için yeni kodu anında görür. Bu asimetri dışa aktarım
değişikliklerinde ısırıyor:

```bash
docker compose up -d --build api worker
```

### OPEN_ITEMS #23 hakkında bir bulgu

Kararsız test bu çalışma sırasında bir kez düştü. Hata `strategies_tried=[]` ve
`[Errno -3] Temporary failure in name resolution` — yani hiçbir strateji çalışmadan SSRF
kapısında, `validate_public_url` içindeki `socket.getaddrinfo` çağrısında. Aynı modül
ardından 5/5 geçti. Maddenin "tetikleyici bilinmiyor" notu bu yönde daraltıldı; kök neden
hâlâ doğrulanmadı.
