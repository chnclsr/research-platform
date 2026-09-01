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
