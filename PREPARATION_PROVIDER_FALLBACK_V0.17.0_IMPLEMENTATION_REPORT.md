# Hazırlık Sağlayıcı Zinciri — v0.17.0

**Tarih:** 2026-08-31
**Dal:** `developments-supplementer`

## Amaç ve sınır

v0.16.0 Telegram koşularının hazırlık evresini tek bir dış sağlayıcıya, Gemini Developer
API'ye bağladı. Tek sağlayıcı tek arıza noktasıdır: Free Tier kotası dolduğunda dönen
`HTTP 429` hazırlığı — dolayısıyla koşuyu — kullanıcı beklerken durduruyordu. Bu çalışma
hazırlık çağrılarını sıralı bir sağlayıcı zincirine taşır; bir sağlayıcı çağrıyı geri
çevirdiğinde aynı çağrı sıradakine gider.

Sınır değişmedi: zincir yalnız hazırlık çağrılarını taşır (çeviri, koşu etiketi, ayrıştırma,
kapsam soruları, sorgu dalları, plan gösterimi ve stratejisi). Kanıt toplama, değerlendirme
ve sentez yerel Qwen'de kalır.

## Zincir ve devretme kuralı

`PREPARATION_LLM_CHAIN` sağlayıcıları sırayla dener. Bilinen adlar `gemini`, `openrouter`,
`groq`, `deepseek` ve `local`; ad listede yoksa o sağlayıcı hiç kurulmaz.

`local` yerel Qwen'dir ve yalnız açıkça yazıldığında devreye girer. v0.16.0'ın "zorunlu
hazırlık Qwen'e sessizce düşmez" kuralı böyle korunur: düşüş bir varsayılan değil, operatörün
listeye yazdığı bir tercihtir. Ayrı bir `PREPARATION_FALLBACK_TO_LOCAL` bayrağı yerine sıranın
kendisi kullanıldı; iki ayarın birbiriyle çelişebileceği bir durum kalmıyor.

Devretmeyi `ProviderUnavailable` tetikler; sağlayıcı bunu şu durumlarda yükseltir:

- Yeniden denenebilir durumlar (`408, 409, 429, 500, 502, 503, 504`),
- İstek servise hiç ulaşmadığında (transport hatası, zaman aşımı),
- Diğer bütün HTTP hata durumları.

Ayrıştırılamayan yanıt (`ValueError`) da sıradaki sağlayıcıya geçer — JSON dönmemek uç
noktanın değil o modelin başarısızlığıdır — ama sağlayıcıyı sağlıksız saymaz.
`ProviderUnavailable`, `RuntimeError` alt sınıfıdır: tek sağlayıcılı kurulum zincir
öncesindeki gibi hata verir.

## Bekleme yerine geçiş, ve cooldown

Gemini sağlayıcısı 429'u kendi içinde `Retry-After` ile yeniden deniyordu. Zincir varken bu
ters etki yapar: 60 saniyelik bir kota penceresinde uyumak, bir sonraki sağlayıcıya geçmenin
maliyetinden pahalıdır. Yerinde bekleme artık `PREPARATION_RETRY_INLINE_MAX_S` (varsayılan 5
sn) ile sınırlıdır; daha uzun bir `Retry-After` beklenmez, çağrı devredilir.

Çağrıyı geri çeviren sağlayıcı `PREPARATION_PROVIDER_COOLDOWN_S` (varsayılan 300 sn) boyunca
atlanır; sağlayıcı `Retry-After` bildirmişse onun süresi kullanılır, tavan 900 saniyedir.
Hazırlık evresi koşu başına yaklaşık yedi çağrı yapar, cooldown olmasa tükenmiş bir günlük
kota her çağrıda yeniden — tam gecikmeyle — keşfedilirdi.

`401`, `403` ve `404` kalıcı sayılır: yanlış anahtar, kapatılmış proje veya emekliye
ayrılmış model kendiliğinden düzelmez, o yüzden sağlayıcı cooldown'a değil süresiz bloğa
alınır. Bu bloğun ömrü zincir nesnesi kadardır; ölçülen kapsamı ve tasarlanandan farkı
"Kalıcı devre dışı bırakmanın kapsamı" bölümündedir.

## Sağlayıcılar

`OpenAICompatibleProvider` artık uç noktayı, anahtarı, modeli ve zaman aşımını parametre alır;
`Settings` üzerinden tek uç noktaya bağlı değildir. Aynı sınıf bu sayede zincirde iki kez, iki
farklı anahtar ve modelle görünebilir. DeepSeek ve OpenRouter aynı `chat/completions`
sözleşmesini konuştuğu için yeni sağlayıcı sınıfı yazılmadı.

OpenRouter yalnız ücretsiz modellerle kullanılır ve bu belgeyle değil doğrulayıcıyla
zorlanır: `:free` ile bitmeyen bir model kimliği ayar hatası olarak reddedilir. Zincirin
amacı kotayı atlatmak, sessizce harcamaya başlamak değildir. Varsayılan
`z-ai/glm-5.2:free`; canlı model listesinde `response_format` ve structured output
destekleyen ücretsiz modellerden biridir — ücretsiz modellerin çoğu bu bayrağı almaz ve JSON
sözleşmesini `_json_from_text`'in toparlamasına bırakır. Ücretsiz katmanda istemlerin
sağlayıcı tarafından eğitim için kullanılabileceği, Gemini Free Tier için düşülen uyarının
aynısıdır.

Groq ücretsiz katmanda çalışır ve `chat/completions` sözleşmesini konuştuğu için aynı
parametrik sınıfla eklendi; varsayılan model `openai/gpt-oss-120b`. Kotası dakikalık ve
günlük istek sayısıyla sınırlıdır, dolduğunda `429` döner ve zincir bir sonraki sağlayıcıya
geçer.

DeepSeek ücretlidir. Zincirde yer alıyorsa ücretsiz sağlayıcıların kotaları bittiğinde
faturalanan çağrılar başlar; bu, zinciri kuran operatörün bilerek verdiği karardır.

## Görünürlük ve hata davranışı

Zincir, cevaplayan sağlayıcının kullanım metriklerini kendi `drain_metrics()` çağrısında
toplar; koşunun `llm_metrics` olayı hangi modelin cevapladığını göstermeye devam eder.
Devretmenin kendisi ayrı bir `preparation_provider_fallback` olayına yazılır (`stage`,
`served_by`, atlanan sağlayıcılar ve nedenleri). İkinci tercih modelle planlanmış bir koşu
bunu kendi geçmişinde söyler.

Zincirdeki her sağlayıcı çağrıyı geri çevirirse hata yükselir ve koşu görünür biçimde
başarısız olur; `BUILD_QUERY_BRANCHES` içindeki "Telegram hazırlığı sessizce Qwen'e düşmez"
kuralı olduğu gibi durur. Hata metni sağlayıcı adlarını ve durum kodlarını taşır, yanıt
gövdesini taşımaz.

Zincirde adı geçen ama anahtarı olmayan bir sağlayıcı worker açılışında hata verir.
Atlanmaz: operatör onu isteyerek yazmıştır ve koşuları sessizce bir sonraki sağlayıcıda
planlamak, yanlış yapılandırmayı çalışan bir sistemin arkasına saklardı.

## Hazırlık çağrı bütçesi

Zincir kotayı atlatır, ama asıl ucuz kazanç kotayı daha az tüketmektir. Ölçüm: 13 koşuluk
kayıtta hazırlık evresi koşu başına ortalama **10.85** LLM çağrısı harcıyordu (medyan 11,
en az 3, en çok 22). Dağılım aşama başına DECOMPOSE 3.1, BUILD_QUERY_BRANCHES 2.9, PLAN 2
(render başına), VALIDATE_PROTOCOL 2, PLANNING_QUESTIONS 1'di.

Sebep mimaridir: HITL kapısı koşuyu `PipelineHalted` ile durduruyor, kullanıcı yanıtlayınca
graf `DECOMPOSE`'dan yeniden giriyor. Ayrıştırma ve sorgu üretimi böylece her tur yeniden
çalışıyordu — kullanıcının onayladığı plandan sonraki turda, girdiler hiç değişmemişken bile.

İki değişiklik yapıldı:

**Değişmemiş turda yeniden hesaplama yok.** `DECOMPOSE` ve `BUILD_QUERY_BRANCHES`, çağrının
okuduğu her şeyin parmak izini (`preparation_signature`: soru, kullanıcı yönlendirmesi,
plan geri bildirimi, tarih kapsamı) state'e yazıyor. Parmak izi aynıysa önceki çıktı
kullanılıyor, model hiç aranmıyor. Reddedilen turda geri bildirim parmak izi değiştirdiği
için yeniden hesaplama olduğu gibi sürüyor; yalnız onay turu bedavaya geçiyor. Başarısız
sorgu üretimi bilerek hatırlanmıyor: boş liste bir cevap değil, bir arızadır ve sonraki tur
yeniden denemeyi hak eder.

**Aynı girdiyi okuyan çağrılar birleşti.** Koşu etiketi artık çeviri çağrısının içinde
isteniyor (`label` alanı); ikisi de yalnız soruyu okuyordu. Model etiketi vermezse eski
`research_label()` çağrısı yedek olarak duruyor, yani birleşme modele yeni bir zorunluluk
getirmiyor. Onay ekranının iki yarısı — alt soruların okuma çevirisi ve strateji notu — tek
`plan_display_and_strategy()` çağrısında isteniyor; ikisi de aynı planı aynı dilde anlatıyor.
Her yarı ayrı ayrı fail-open kalıyor: hizalanamayan çeviri listesi düşüyor ve İngilizce liste
gösteriliyor, eksik not planı notsuz bırakıyor, hiçbiri kapıyı kapatmıyor.

Beklenen etki: revizyonsuz bir koşuda 10 → 6 çağrı, tek revizyonlu tipik koşuda 14 → 9.
Ölçülen medyan 11'in yeni karşılığı 7 civarındadır. Kullanıcıya görünen davranış aynıdır;
tasarruf yalnız tekrar eden ve ikiye bölünmüş isteklerden gelir.

`translate_for_display()` bu birleşmeden sonra çağrısız kaldığı için kaldırıldı; kullandığı
liste normalleştirici `display_items()` adıyla ortak hale geldi ve birleşik çağrı onu
kullanıyor.

## Kurulum

```env
PREPARATION_LLM_CHAIN=gemini,groq,openrouter
PREPARATION_PROVIDER_COOLDOWN_S=300
PREPARATION_RETRY_INLINE_MAX_S=5
GEMINI_PREPARATION_MODEL=gemini-3.6-flash
OPENROUTER_API_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=<secret>
OPENROUTER_PREPARATION_MODEL=z-ai/glm-5.2:free
OPENROUTER_PREPARATION_TIMEOUT_S=60
GROQ_API_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=<secret>
GROQ_PREPARATION_MODEL=openai/gpt-oss-120b
GROQ_PREPARATION_TIMEOUT_S=60
DEEPSEEK_API_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=<secret>
DEEPSEEK_PREPARATION_MODEL=deepseek-chat
DEEPSEEK_PREPARATION_TIMEOUT_S=60
```

Varsayılan zincir tek sağlayıcıdır (`gemini`), yani ayar dosyasına dokunmayan bir kurulum
v0.16.0 davranışını aynen sürdürür. Bu dalın çalışan kurulumunda zincir, anahtarlar
girildikten sonra `gemini, groq, openrouter` olarak açıldı; doğrulayıcı boşlukları
temizlediği için değer `gemini,groq,openrouter` olarak okunur. Groq'un OpenRouter'dan önce
gelmesinin nedeni aşağıdaki canlı ölçümdür.

## Emekliye ayrılan model ve zincirin ilk gerçek sınavı

Zincir üretime alındıktan sonraki ilk koşuda Gemini hiçbir çağrıyı karşılamadı: devretme
olayları `gemini:404` gösterdi, birincil sağlayıcı devre dışı kaldı ve bütün hazırlık
Groq'a düştü. Neden yapılandırmadaydı — çalışan kurulumun `.env` dosyası, Google'ın yeni
anahtarlara kapattığı `gemini-2.5-flash` modelini sabitliyordu:

```
This model models/gemini-2.5-flash is no longer available to new users.
Please update your code to use models/gemini-3.6-flash
```

Modelin `models.list` çıktısında görünmeye ve `supportedGenerationMethods` içinde
`generateContent` bildirmeye devam etmesi yanıltıcıdır: liste model kaydını gösterir, o
anahtarın çağırma hakkını değil. Raporun ilk sürümündeki "Gemini `HTTP 200` verdi" ölçümü
bu yüzden tutmadı; `generateContent` üzerinde tekrarlandığında `404` döndü. Doğrulamanın
gerçek çağrı yüzeyinde yapılması gerekir, model listesinde değil.

`config.py` varsayılanı ve `.env.example` zaten `gemini-3.6-flash` idi; geride kalan tek
yer çalışan kurulumun `.env` dosyasıydı. Düzeltildi ve worker ile telegram-bot yeniden
yaratıldı. `docker compose restart` bunun için yetmez: container'ı mevcut ortamıyla
yeniden başlatır, `.env`'i yeniden okumaz. Kalıcı devre dışı bırakma bellekte tutulduğu
için yeniden başlatma zaten gerekliydi.

Sonucun kendisi zincirin lehinedir: birincil sağlayıcı sessizce ve tamamen kayboldu, koşu
yine de planını üretip tamamlandı. Aynı arıza v0.16.0'da koşuyu düşürürdü. Ama ders tek
yönlü değil — zincir arızayı öyle iyi soğurdu ki dışarıdan sistem sağlıklı görünüyordu.
Yanlış model yalnızca `preparation_provider_fallback` olayına bakınca fark edildi. Zincir,
sağlayıcı kaybını bir kesinti olmaktan çıkarıp bir kayıt satırına dönüştürür; o satır
okunmazsa birincil sağlayıcı süresiz ölü kalabilir.

## Kalıcı devre dışı bırakmanın kapsamı

Aynı koşunun olay kaydı, belgelenen davranışla uyuşmayan bir nokta gösterdi.
`FallbackProvider` `401/403/404` alan sağlayıcıyı `math.inf` ile bloke eder ve bu
raporun ilk sürümü bunu "süreç yeniden başlatılana kadar hiç denenmez" diye tarif etti.
Ölçülen davranış farklı:

```
VALIDATE_PROTOCOL     gemini:404      -> groq
DECOMPOSE             gemini:cooling  -> groq
PLANNING_QUESTIONS    gemini:cooling  -> groq
DECOMPOSE             gemini:404      -> groq
BUILD_QUERY_BRANCHES  gemini:cooling  -> groq
PLAN                  gemini:cooling  -> groq
DECOMPOSE             gemini:404      -> groq
BUILD_QUERY_BRANCHES  gemini:cooling  -> groq
PLAN                  gemini:cooling  -> groq
```

`404` bir kez değil üç kez görünüyor. Nedeni `build_preparation_llm`'in
`ResearchPipeline.__init__` içinde çağrılması: blok listesi zincir nesnesinin alanıdır,
süreç değil. HITL kapısı koşuyu durdurup kullanıcı yanıtlayınca yeni bir `ResearchPipeline`
kuruluyor, yeni bir zincir ve boş bir blok listesi geliyor. Yani kalıcılık süreç ömrü
boyunca değil, checkpoint'ler arasındaki her koşu parçası boyunca geçerli.

Etkisi sınırlıdır: ölü sağlayıcı, koşunun her yeniden girişinde bir kez daha — tam
gecikmeyle — yoklanır. Ölçülen koşuda bu, dokuz hazırlık çağrısına karşılık üç boşa giden
Gemini gidiş-dönüşü demekti. Kota tüketmez, çünkü çağrı zaten reddediliyor. Yine de
tarif edilen davranış bu değildir ve iki seçenek var: blok listesini süreç ömrüne taşımak,
ya da belgeyi ölçülene uydurmak. Karar verilmedi; bu bölüm bulguyu kapatmak için değil,
kaydetmek için duruyor.

## Doğrulama

Zincir testleri: 429'da bir sonraki sağlayıcıya geçiş, uzun `Retry-After`'ın uyku değil
cooldown olması, `403` alan sağlayıcının bir daha denenmemesi, ayrıştırılamayan yanıtın
sağlayıcıyı cezalandırmadan devretmesi, her sağlayıcının kendi anahtarını `Authorization`
başlığında taşıyıp URL'ye koymaması, JSON modunun ve ücretsiz modelin istenmesi, tükenen
zincirin istemi ve anahtarı sızdırmaması, anahtarsız zincir üyesinin açılışta hata vermesi,
bilinmeyen/tekrarlı sağlayıcı adının ve ücretli OpenRouter modelinin reddedilmesi, devretmenin
koşu olayına yazılması.

Çağrı bütçesi testleri `tests/test_preparation_call_budget.py`: değişmemiş turun yeniden
ayrıştırmaması ve yeniden sorgu üretmemesi, reddedilen turun yeniden hesaplaması, başarısız
sorgu üretiminin hatırlanmaması, çevrilen isteğin ikinci çağrı olmadan adlandırılması,
etiketsiz çeviride yedek çağrının sürmesi, onay ekranının iki yarısının tek istekte gelmesi
ve her yarının ayrı ayrı fail-open kalması.

Hedefli paketler `tests/test_gemini_preparation.py` ve `tests/test_preparation_call_budget.py`:
`14 passed` ve `7 passed`. Tam kapı: `621 passed, 1 warning`; uyarı bu çalışmadan eski
Starlette/httpx deprecation uyarısıdır. Sürüm yüzeyleri artık hizalı: editable kurulum,
worker, API ve kontrol paneli `0.17.0` bildiriyor. Değişen satırlarda yeni Ruff ihlali
yoktur; `llm.py` içindeki iki geniş `except` ihlali bu çalışmadan eskidir ve temiz taban
varmış gibi raporlanmamıştır — depo geneli taban için açık iş #21.

Canlı uç noktalar operatörün anahtarlarıyla ayrı ayrı yoklandı. Groq `openai/gpt-oss-120b`,
hazırlık istemlerinden biriyle (`sub_questions` + `concepts`) `response_format: json_object`
altında geçerli ve İngilizce JSON döndürdü. OpenRouter'ın `z-ai/glm-5.2:free` modeli ilk
denemede `HTTP 429` + `Retry-After: 5` verdi: ücretsiz havuz yukarı akışta paylaşımlıdır ve
bu yanıt istisna değil olağan durumdur — zincirin tam olarak karşıladığı hâl. Bu nedenle
sıralamada Groq OpenRouter'dan önce gelir. Gemini'nin durumu iki bölüm yukarıdadır;
düzeltmeden sonra `gemini-3.6-flash` `HTTP 200` veriyor.

Uçtan uca canlı doğrulama yapıldı. `01M1BC0B0HFCBAET0EH7ZK9YMM` koşusu dokuz
`preparation_provider_fallback` olayı yazdı; devretme `VALIDATE_PROTOCOL`, `DECOMPOSE`,
`PLANNING_QUESTIONS`, `BUILD_QUERY_BRANCHES` ve `PLAN` aşamalarında ayrı ayrı gözlendi ve
hepsinde `served_by: groq` oldu. Koşu planını üretti ve dışa aktarımla kapandı. Yani zincir,
birincil sağlayıcının tam kaybı altında hazırlık evresini taşıdı; bu, tasarımın hedeflediği
senaryonun ta kendisidir ve sentetik değil gerçek bir arızayla doğrulanmıştır.

Ücretsiz model listeleri zamanla değişir: `:free` doğrulayıcısı kimliğin ücretsiz olduğunu
garanti eder, modelin var olmaya devam ettiğini etmez. Aynı kırılganlık ücretli olmayan her
katmanda vardır ve bu çalışmada Gemini'de somut olarak gerçekleşti — model kimlikleri
zincirin en oynak parçasıdır ve `404`'ler olay kaydından düzenli olarak okunmalıdır.
