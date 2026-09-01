# Adaptif harness katmanı — v0.18.0

Platform sürümü: `v0.18.0`

Belge sürümü: `1.0`

Tarih: `2026-09-01`

## Kapsam

JIT-Agent değerlendirmesi deponun alınmayacağı ama iki fikrinin alınacağı sonucuna varmıştı.
Alınan fikir şudur: **sabit bir protokol ve kapalı bir yetenek kataloğu altında göreve özgü
yapı kurmak.** Ortak arayüz, doğrulama ve yürütme semantiği sabit kalır; değişen yalnız
içerideki operasyonel seçimlerdir.

Model hiçbir yerde Python veya çalışma akışı üretmez; yalnız kapalı, tipli bir blueprint
üretir. Yeni bir çalışma zamanı yüzeyi açılmaz.

İki bölüm var. **Bölüm B — kaynak seçimi sentezi** bu belgede anlatılıyor. **Bölüm A —
just-in-time probe factory** ikinci aşamadır ve olay/provenance sözleşmesini B'den devralır.

Her iki bölüm de varsayılan **kapalı** bir flag'in arkasındadır. Ölçülmemiş bir iyileştirme
varsayılan yapılmaz.

---

## Bölüm B — Kaynak seçimi sentezi

### Sorun

Her koşu `CORE_FAMILIES` varsayılanıyla başlıyordu — web, academic, official_legal,
code_data — soru ne olursa olsun. İçtihat soran bir soru ile eğitim tarifi soran bir soru
aynı dört aileyi ve aynı connector yelpazesini alıyordu; cevap vermeyecek ailelere çağrı
harcanıyordu.

### Çözüm

`VALIDATE_PROTOCOL` içinde, `_name_run`'dan sonra tek bir LLM çağrısı. Modele birincil soru
ve **önceden doğrulanmış kapalı bir katalog** verilir: `academic`, `official`, `code_data`,
`core` — her birinin yanında ne zaman kullanılacağını söyleyen bir cümle
(`scoping.FAMILY_PRESET_GUIDE`). Model yalnız bir anahtar ve gerekçe döndürür; serbest aile
listesi üretmez, dolayısıyla çıktı uzayında geçersiz cevap yoktur.

Sonuç `scoping.apply_families()` ile uygulanır — `_apply_families` bu iş için dışa açıldı.
Aynı fonksiyonun kullanılması bilinçli: `included_families`, `profile` ve
`family_targets = {}` üçlüsünü doğru yazan tek yer orası, ikinci bir uygulama o üçlüden
birini unutacak ikinci bir yer olurdu.

Katalog dışı anahtar, bozuk JSON, çağrı hatası ya da ikinci kez doğrulanamayan sonuç →
sentez yok, protokol aynen kalır. Deterministik fallback bugünkü varsayılandır, yani
başarısızlık zaten mevcut davranıştan başka bir şeye mal olmaz.

### Kapı — dört koşul

```python
self.settings.protocol_source_synthesis_enabled
and protocol.connectors.selection_source == "default"
and protocol.hitl.planning_questions is False
and state.get("synthesis_done") is not True
```

Her koşul, zaten verilmiş bir kararın üzerine yazmanın bir yolunu kapatıyor.

**`selection_source` neden gerekliydi.** `_apply_families`, `core` preset'inde
`profile = "core"` ve `included_families = CORE_FAMILIES` yazıyor — yani **hiç dokunulmamış
bir protokolle bit düzeyinde aynı**. Alanları karşılaştırmak, verilmiş bir kararı kararsızlıktan
ayıramaz. Bu yüzden `ConnectorSelection`'a provenance alanı eklendi:
`default | caller | scoping | synthesis`.

Alan varsayılanlı olduğu için migration gerekmedi; protokol veritabanında JSON ve Pydantic
eksik alanı dolduruyor.

**Çağıran tespiti `model_fields_set` ile yapılamaz.** Protokol her kalıcılaştırma
aşamasında `model_dump` → `model_validate` turu atıyor ve turdan sonra *bütün* alanlar "set"
görünüyor; bu yolla yapılan bir tespit ilk turdan sonra her protokolü "caller" ilan ederdi.
Bunun yerine değerlerden çıkarım yapılıyor: varsayılandan farklı bir seçim tesadüfen
oluşamaz, dolayısıyla `caller` olarak işaretlenir. Varsayılana **eşit** açık bir seçim
ayırt edilemez kalır ve sentezin üzerine yazabileceği tek durum odur.

**`planning_questions` neden kapıda.** Kapsam soruları `DECOMPOSE` içinde, yani
`VALIDATE_PROTOCOL`'den *sonra* çalışıyor ve `apply_planning_answers` aile listesini üzerine
yazıyor. Telegram varsayılanı bu kapıyı açık bırakıyor. Sentez orada çalışsaydı, birazdan
değiştirilecek bir değere çağrı harcanırdı.

**`synthesis_done` neden var.** `VALIDATE_PROTOCOL`, checkpoint dönüşlerinde yeniden
girilebilen bir düğüm. Bayrak `PipelineState`'e yazılıyor ve iş koşu başına bir kez yapılıyor.

### Onarım — planın gerekçesi yanlıştı, mekanizma doğru

Plan, dar bütçeli bir koşuda `official` preset'inin (üç aile) `max_sources` doğrulamasını
tetikleyeceğini varsayıyordu. **Bu imkânsız:** her preset varsayılan `core`'dan daha az aile
içeriyor (academic 2, code_data 2, official 3, core 4) ve protokol zaten `core` ile
doğrulanmış durumda. Preset değiştirmek gereken minimum kaynak sayısını yalnız *düşürebilir*.

Onarım yolu yine de erişilebilir, ama başka bir kapıdan: çağıran varsayılan aileleri koruyup
dar bir `family_targets` haritası ve küçük bir `max_sources` verdiğinde. `apply_families` o
haritayı temizliyor, doğrulayıcı aile başına birer hedefle yeniden kuruyor ve toplam bütçeyi
aşabiliyor. Ölçülen örnek: `max_sources = 2`, `family_targets = {web: 1}` protokolü geçerli;
`official` preset'i uygulandığında üç aile × 1 = 3 > 2 → `ValueError`.

Tek onarım çağrısı yapılır ve modele **doğrulayıcının kendi hata metni** verilir, parafraz
değil. İkinci başarısızlıkta orijinal protokol döner.

### Olay

`protocol_synthesis`: `{preset, reason, families, repaired, call_count}`. Sentez
yapılmadıysa olay yazılmaz. Bu, `scoping.py`'deki *"a guess nobody sees"* itirazının
karşılığıdır: HITL plan kapısı protokolü zaten gösteriyor, olay ise onun nasıl o hâle
geldiğini açıklıyor.

### Doğrulama

On beş yeni test. Modül düzeyinde: katalogdan preset uygulanması ve `family_targets`'ın yeni
ailelere göre yeniden kurulması · katalog dışı anahtarın reddi · bozuk cevabın ve sağlayıcı
arızasının varsayılanı ayakta bırakması · dar bütçenin bir onarım doğurması · ikinci hatada
vazgeçilmesi · açık `core` seçiminin varsayılandan ayrılması · aileleri daraltan çağıranın
`caller` olarak kaydı ve varsayılanın tur atışında `default` kalması · kataloğun preset
listesini birebir kapsaması.

Kapı düzeyinde, gerçek bir `ResearchPipeline` üzerinde: flag kapalıyken **sıfır çağrı** ve
bit düzeyinde değişmemiş protokol · flag açıkken preset'in uygulanıp **satıra
kalıcılaştırılması** · `planning_questions` açıkken çağrının hiç yapılmaması · zaten seçim
yapılmış protokole dokunulmaması · checkpoint dönüşünde ikinci kez ödenmemesi · olayın
yazılması.

Tam kapı: taban **621 passed** → **636 passed**. Hedefli Ruff: `protocol_synthesis.py` ve
`tests/test_protocol_synthesis.py` temiz; `pipeline.py` 21/21, `schemas.py` 3/3,
`scoping.py` 0/0, `config.py` 0/0 — hiçbirinde artış yok.

Ruff bir hatayı testlerden önce yakaladı: kapıda `get_settings()` çağrılmıştı ama
`pipeline.py` onu import etmiyor. Flag varsayılan kapalı olduğu için hiçbir test o satıra
girmezdi; canlıda flag açılınca `NameError` verirdi. `self.settings`'e çevrildi.

### Dosyalar

`config.py` (iki flag) · `schemas.py` (`selection_source` + çıkarım) ·
`scoping.py` (`apply_families` dışa açıldı, `FAMILY_PRESET_GUIDE`) ·
`protocol_synthesis.py` (yeni) · `pipeline.py` (`validate_protocol`, `_synthesize_sources`,
`PipelineState.synthesis_done`) · `tests/test_protocol_synthesis.py` (yeni) ·
`docs/ARCHITECTURE.md` · `.env.example`

### Ölçüm — henüz yapılmadı

Flag açılmadan önce ölçülecekler: etiketlenmiş soru kümesinde preset doğruluğu · HITL
kullanıcı override oranı (kullanıcı kapsam sorusunda sentezin seçtiğinden farklısını seçiyor
mu) · connector çağrısı ve ilgili kaynak oranı. Kazanç çıkmazsa flag kapalı kalır.

---

## Bölüm A — Just-in-Time Probe Factory

### Sorun

Sıradan gap mission'ları tükendiğinde `literature_scan_probe_missions` altı elle yazılmış
strateji son ekini `(tur − 1) % 6` ile döndürüyordu. Rotasyon hangi gap'lerin açık olduğunu,
nelerin denendiğini ve hangi connector'ların hâlâ cevap verdiğini bilmiyordu.

Ölçülen arıza: `01M14A8RP5ZD36NEX889AXRKSP` koşusu 28 turda 215 connector çağrısı yapıp
**sıfır** sonuç aldı. Aynı altı son eki döndürmek o koşuyu kurtarmazdı.

### Modelin karar verdiği şey ne kadar küçük

`ProbeCandidate` bilinçli olarak ince: taktik, odak ifadesi, hedef gap ve connector kısa
listesi. `extra="forbid"`. Domain, URL, bütçe, kaynak ailesi, `result_limit` ve tarih
kapsamı blueprint'te **yok** — bunları adlandırabilen bir model, koşuyu protokolün izin
vermediği bir yere de gönderebilirdi.

Taktikler sekiz sabit primitiften oluşuyor (`ProbeTactic`) ve model bunları birleştiriyor,
mission üretmiyor. Tek çağrıda en fazla üç aday: ek çağrı harcamayan bir best-of-N.

### Derleyici — her operasyonel değer burada

`compile_probe_candidate` modelin connector listesini protokolün izin verdikleriyle **ve**
hâlâ cevap verenlerle kesiştiriyor; güvenmiyor. Limitler bütçeden, sorgu gerçek soruya
demirlenip `constrain_text_to_scope` ile tarih kapsamına sokuluyor. İmzası zaten denenmiş
bir mission **reddediliyor** — koşunun sorduğu soruyu yeniden sormasını durduran şey bu.

Bir ayrıntı testten çıktı: model hiçbir gap adlandırmazsa aday hedefsiz kalıyordu. Derleyici
artık en yüksek öncelikli gap'e bağlıyor. Gap'siz bir probe'un var olma sebebi yok ve hangi
gap'e hizmet ettiği tahmine bırakılamaz.

### Skorlayıcı ve carryover

Sıralama deterministik: hedeflenen gap'in önceliği · aile hedefi olup olmadığı · taktiğin
daha önce harcanıp harcanmadığı · connector'ın önceki turda sıfır aday verip vermediği.
Modelin kendi sırası `suggested_rank` olarak, seçici ile aynı olayda ayrı kaydediliyor —
`disagreed_with_model` ile birlikte. Kimsenin itiraz edemeyeceği bir seçicinin işe yaradığı
gösterilemez.

Kalan adaylar `probe_candidates_pending` içinde bekliyor; sonuçsuz bir tur **yeni LLM çağrısı
yapmadan** sıradakini kullanıyor. Yeniden üretim en fazla bir kez.

### Fail-open — rotasyona dönüş yok

Üretim başarısız olursa tek deterministik fallback: en yüksek öncelikli gap + gap topic +
ana soru + gap'in kendi `preferred_connectors` listesi. O da denenmişse **boş liste** döner
ve v0.16.1'in `completed_incomplete` yolu çalışır. Sonsuz ya da anlamsız rotasyon olmaz.

### Veri sınırı

Probe üreteci **yalnız `self.llm`** (yerel model) kullanır, `_preparation_provider()`
kullanmaz: prompt gap topic'leri ve deneme özetleri taşıyor, bunlar korpustan geliyor ve
kurulumun mevcut veri paylaşım sınırı genişletilmiyor. Ham trajectory hiç gönderilmiyor,
yalnız sayı özetleri. Bu bir testle sabitlendi.

### Planın "altılıyı kaldır" maddesi uygulanmadı — gerekçe

Plan hem `literature_scan_probe_missions`'ın kaldırılmasını hem de "her iki flag kapalıyken
davranış bugünküyle birebir aynı olmalı" şartını istiyordu. **İkisi aynı anda sağlanamaz:**
fonksiyon kaldırılırsa, flag varsayılan kapalı olduğu için varsayılan kurulumda recall
probe'u hiç kalmaz ve bugünkü davranış korunmaz — varsayılan yapılandırma bugünkünden
kötüleşir.

Flag değişmezi korundu: flag kapalıyken eski rotasyon aynen çalışıyor, flag açıkken probe
factory devreye giriyor ve rotasyona **hiç** dönülmüyor. Altılının kaldırılması, flag
ölçümle kanıtlandıktan sonraki adımdır; planın kendi ölçüm bölümü zaten bu sırayı ima ediyor.

### v0.16.1 semantiği

`probe_strategies_exhausted` flag açıkken anlamını yitirdi: tükenecek bir liste yok, bunun
yerine son denemenin bildirdiği neden okunuyor (`probe_candidates_exhausted` ·
`no_valid_novel_probe` · `probe_generation_failed`). Terminal davranış **değişmedi**:
`stop_reason=recovery_exhausted_no_progress` → `completed_incomplete`. Korunan güvenlik
değişmezleri: `max_consecutive_empty_recovery_rounds` · aynı mission imzası tekrar
çalışmaz · bütçe sınırları · model arızası koşuyu düşürmez.

### Doğrulama

On beş yeni test. Derleyici: connector kesişimi · protokolde olmayan ailenin reddi · denenmiş
imzanın reddi · `result_limit`'in modelden alınmaması · sorgunun tarih kapsamına sokulması.
Üretim: üç adayın tek çağrıya mal olması · bozuk/erişilemez modelin bundle üretmemesi.
Skorlayıcı: harcanmamış taktiğin tercihi · sonuçsuz connector'ın düşürülmesi.
Pipeline: bir adayın çalışıp kalanın saklanması · carryover turunun **sıfır çağrı** harcaması ·
üretim hatasında tek deterministik fallback ve rotasyona dönülmemesi · fallback de
denenmişse boş liste ve `completed_incomplete` yolu · flag kapalıyken eski rotasyonun aynen
çalışması · probe bağlamının `_preparation_provider()`'a **gitmemesi**.

Tam kapı: **636 passed** → **651 passed**. Hedefli Ruff: `probe_factory.py` ve
`tests/test_probe_factory.py` temiz, `pipeline.py` 21/21.

`ruff --fix` bu arada `pipeline.py`'de ilgisiz altı `timezone.utc` → `UTC` düzeltmesi
yapmıştı; commit'i konusuna sadık tutmak için geri alındılar. Tam-depo lint borcu açık iş
#21'in konusudur.

### Dosyalar

`config.py` · `schemas.py` (`ProbeTactic`, `ProbeCandidate`, `ProbeBundle`) ·
`probe_factory.py` (yeni) · `pipeline.py` (`_probe_missions`, `_healthy_connectors`,
`_fallback_probe_mission`, `_probe_attempt_summaries`, `plan_recovery`, `check_coverage`,
üç `PipelineState` alanı) · `tests/test_probe_factory.py` (yeni) · `docs/ARCHITECTURE.md`

### Ölçüm — henüz yapılmadı

Probe turu başına yeni **ve kabul edilmiş** `SourceVersion` · sıfır-yield tur oranı · yeni
kaynak başına connector çağrısı · tur gecikmesi. Tek bir önce/sonra koşusu yeterli değil;
kaydedilmiş sağlayıcı cevaplarıyla replay ya da aynı koşullarda birkaç tekrar gerekir.
Kazanç çıkmazsa flag kapalı kalır ve altılı yerinde durmaya devam eder.

