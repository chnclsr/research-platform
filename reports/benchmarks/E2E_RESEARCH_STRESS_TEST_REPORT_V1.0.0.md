# Uçtan Uca Araştırma Stres Testi Raporu

- Rapor sürümü: `1.0.0`
- Tarih: `2026-07-17`
- Test edilen platform: `research-platform v0.6.1`
- Git etiketi: `v0.6.1`
- Run kimliği: `01KXR0ZRXAKNJ3C6692PE3N2TQ`
- Son durum: `completed_incomplete`

## Yönetici kararı

Platformun uçtan uca işletim hattı çalışmaktadır: iş oluşturulmuş, kuyruktan alınmış, üç araştırma turu yürütülmüş, kaynaklar edinilmiş, içerik normalize edilmiş, iddialar çıkarılmış, coverage denetlenmiş ve 17 artifact üretilmiştir. ZIP paketi bütünlük kontrolünden geçmiştir.

Araştırma kalitesi bu zor testte kabul seviyesine ulaşmamıştır. Sistem yetersizliği doğru tespit edip başarılıymış gibi davranmamış; ancak sonraki iki tur eksikleri giderememiştir. Daha önemlisi, raporlanabilir dört iddiada kullanılan alıntılar makalenin bulgu metninden değil, `References` ve `How to Cite` bölümlerinden seçilmiştir. Bu nedenle altyapı testi **geçti**, araştırma sonucu testi **kaldı**, kanıt doğruluğu testi ise **kritik kusurla kaldı**.

## Test sorusu ve bilinçli zorluklar

**Soru:** 2021–2026 kanıtlarına göre yapay zekâ kodlama asistanları yazılım güvenliğini iyileştiriyor mu, yoksa geliştiricilerin daha fazla zafiyet üretmesine mi neden oluyor? Kontrollü deneyler, gerçek açık kaynak depo çalışmaları, benchmark veri setleri ve üretici güvenlik iddiaları karşılaştırılsın.

Test, basit bir web özeti yerine şu koşullarla zorlaştırılmıştır:

- Akademik, açık web, resmî ve kod/veri olmak üzere dört kaynak ailesi zorunlu tutuldu.
- Altı ayrı araştırma dalı tanımlandı.
- En az iki bağımsız kaynak ve karşı kanıt istendi.
- `Asleep at the Keyboard?` makalesi zorunlu sentinel kaynak olarak tanımlandı.
- Tarih aralığı 2021-01-01–2026-07-17 ile sınırlandı.
- Üç tur, 25 kabul edilmiş kaynak, 25 dakika ve connector başına altı sonuç bütçesi verildi.
- Citation frontier derinliği iki olarak ayarlandı.

## Uçtan uca sonuç

| Ölçüm | Sonuç | Yorum |
|---|---:|---|
| Toplam süre | 168,45 sn | İş akışı beklenen sürede tamamlandı |
| Araştırma turu | 3 | Eksik coverage iki recovery turu başlattı |
| Ham provider sonucu | 429 | Discovery hacmi yüksek |
| Acquisition denemesi / başarı | 26 / 26 | Edinim hattı teknik olarak başarılı |
| Kabul edilmiş kaynak | 2 | Discovery hacmi sonuca dönüşmedi |
| Çıkarılan iddia | 8 | 4 qualified, 4 unresolved |
| Artifact | 17 | Raw, result ve birleşik paketler üretildi |
| ZIP bütünlüğü | Başarılı | CRC hatası yok |
| LLM | `qwen3:4b-instruct-2507-q4_K_M` | 15 çağrı |
| LLM token | 15.388 giriş / 3.084 çıkış | Yaklaşık 78,99 token/sn |

### Coverage sonucu

| Ölçüt | Sonuç | Hedef | Durum |
|---|---:|---:|---|
| Kaynak ailesi coverage | 0,15 | 0,80 | Kaldı |
| Query branch coverage | 0,125 | 0,80 | Kaldı |
| Claim audit coverage | 1,00 | 0,80 | Biçimsel olarak geçti; destek kalitesini ölçmüyor |
| Sentinel recall | 0,00 | 1,00 | Kaldı |
| Unresolved major claim | 5 | en çok 4 | Kaldı |
| Saturation round | 0 | 1 | Kaldı |
| Authority coverage | 0,00 | — | Zayıf |

`estimated_completeness=1.0` yalnız iki discovery observation üzerinden hesaplanmıştır ve bu test için anlamlı bir tamlık göstergesi değildir.

## Connector gözlemleri

| Connector | Çağrı | Sonuç | Sorun |
|---|---:|---:|---|
| arXiv | 18/18 başarılı | 97 | Sentinel yine bulunamadı |
| AgentSearch web | 18/18 başarılı | 108 | Kabul edilmiş kaynak üretmedi |
| Crossref | 18/18 başarılı | 108 | Kabul edilen iki kaynağın ikisini de üretti |
| Official registry | 18/18 başarılı | 108 | Resmî kabul edilmiş kaynak üretmedi |
| Semantic Scholar public | 1/6 başarılı | 7 | Beş adet HTTP 429 |
| GitHub | 13/18 başarılı | 1 | Beş adet HTTP 403/rate limit |
| Hugging Face | 18/18 başarılı | 0 | Faydalı sonuç yok |
| DataCite | 18/18 başarılı | 0 | Faydalı sonuç yok |
| Zenodo | 17/18 başarılı | 0 | Bir HTTP 500, faydalı sonuç yok |

Bu tablo, connector sağlık/başarı oranının araştırmaya katkıyla aynı şey olmadığını gösterir. Örneğin `official_registry` teknik olarak yüzde 100 başarılı olduğu hâlde hedef aileye kabul edilmiş kaynak kazandırmamıştır.

## Kabul edilen kaynaklar

1. *AI ASSISTANTS IN SOFTWARE DEVELOPMENT: ANALYSIS OF SECURITY RISKS IN GENERATED CODE* — Crossref, DOI `10.36074/grail-of-science.01.05.2026.077`.
2. *Security Weaknesses in LLM-Generated Source Code: An Empirical Vulnerability Analysis of Iterative AI-Assisted Development* — Crossref, DOI `10.2139/ssrn.6958668`.

İkinci kaynak kabul edilmiş olmasına rağmen rapordaki qualified iddialara kanıt sağlamamıştır. Nihai anlatı fiilen tek kaynağa dayanmaktadır.

## Kanıt denetimi

Konumlandırma mekanizması teknik olarak çalışmıştır: rapor kaynak, bölüm ve karakter aralığı göstermektedir. Fakat semantik doğruluk başarısızdır:

- “Kullanıcılar AI asistanlarıyla daha güvensiz kod yazıyor” iddiası, makalenin kaynakçasındaki **başka bir çalışmanın soru biçimindeki başlığıyla** desteklenmiştir.
- Poisoning zafiyeti iddiası, yine yalnızca kaynakçadaki bir çalışma başlığıyla desteklenmiştir.
- Bir makale başlığı ve hazır bibliyografik atıf, ayrı ayrı major claim olarak kabul edilmiştir.
- Dört qualified iddianın tamamı aynı kaynaktan gelmiştir; bağımsız destek ve karşı kanıt yoktur.
- `claim_audit_coverage=1.0`, iddiaların denetlendiğini ifade etmekte; doğru ve yeterli desteklendiğini ifade etmemektedir. Panelde ve raporda bu ayrım açık etiketlenmelidir.

Sonuç olarak “alıntı kaynak pasajında bulunuyor mu?” kontrolü geçmekte, “alıntı iddiayı gerçekten doğruluyor mu?” kontrolü kalmaktadır.

## Recovery döngüsü değerlendirmesi

Birinci turda 187 provider sonucu ve 10 başarılı acquisition olmasına rağmen nihai kaynak oluşmamıştır. Sistem bunu doğru tespit edip ikinci ve üçüncü turları başlatmıştır. Ancak recovery sorguları genel ifadeleri genişletmiş, eksik araştırma dallarını ve sentinel kaynağı deterministik şekilde hedeflememiştir.

Citation frontier de fiilen çalışmamıştır: seed expansion ve citation candidate sayıları sıfır kalmıştır. Citation sağlayabilecek Semantic Scholar bağlantısının 429 hataları ve diğer connector'ların citation graph sağlamaması bu özelliği operasyonel olarak etkisiz bırakmıştır.

## Başarılı alanlar

- API, Redis kuyruğu, worker ve LLM birlikte uçtan uca çalıştı.
- Üç tur ve coverage tabanlı recovery yürütüldü.
- Yetersiz araştırma `completed_incomplete` olarak dürüstçe işaretlendi.
- Ham kaynaklar ve ham pasajlar ayrı paketlenebildi.
- Artifact seti eksiksiz üretildi ve ZIP CRC doğrulandı.
- Kaynak URL'si, connector, DOI, pasaj bölümü ve karakter aralığı korunabildi.
- API istekleri LLM çalışırken bloke olmadı.

## Öncelikli düzeltme paketi

### P0 — Yanlış kanıtın rapora girmesini durdur

1. `References`, `Bibliography`, `How to Cite`, navigasyon, footer ve metadata bölümlerini varsayılan claim extraction alanından çıkar.
2. Başlık, bibliyografik kayıt, soru cümlesi ve yalnız çalışma adından oluşan metinler için deterministic `non-claim` filtresi ekle.
3. Evidence entailment denetimini `claim + quote + çevre pasaj + bölüm türü` üzerinde yeniden çalıştır; yalnız başlık eşleşmesini kabul etme.
4. Major claim için `supports` evidence sayısı sıfırsa `qualified` statüsünü yasakla.
5. Synthesis aşamasında yalnız audit-passed evidence kullanılmasını zorunlu kıl.

### P1 — Recovery'yi hedef odaklı yap

1. Zorunlu sentinel'ları yalnız metrik olarak izleme; persistent ID, exact title ve canonical URL ile ayrı arama görevleri oluştur.
2. Eksik branch/family için ayrı recovery mission üret ve her mission'a connector kotası ayır.
3. Arama sonucu bütçesini global sıralama yerine branch × family matrisine dağıt.
4. Citation-capable connector çalışmıyorsa citation frontier'ı sessizce sıfır göstermek yerine `degraded` olarak raporla.
5. Bilinmeyen tarihli akademik URL'leri doğrudan elemek yerine DOI/arXiv metadata enrichment kuyruğuna al.

### P1 — Provider erişimini güvenilir yap

1. Semantic Scholar için anahtar, backoff, cache ve düşük eşzamanlılık uygula.
2. GitHub token tanımla ve rate-limit telemetry'sini panele getir.
3. Official registry sorgularını konuya göre doğrulanmış üretici/domain listelerine yönelt.
4. `successful request`, `raw result`, `acquired`, `accepted` ve `evidence-contributing` metriklerini ayrı göster.

### P2 — Kalite göstergelerini düzelt

1. `estimated_completeness`, asgari observation sayısı oluşmadan `N/A` olsun.
2. `claim_audit_coverage` adını/yardım metnini “denetlenen iddia oranı” olarak açıkla; kanıt yeterliliğini ayrı ölç.
3. Rapor dili Türkçe seçilmişse model sentezi ve yönetici özeti için dil uygunluğu testi uygula.
4. Funnel metriklerini tek bir cardinality tanımıyla üret; tekrar işlenen yerel corpus kayıtlarını ayrı göster.

## Nihai kabul kararı

| Katman | Karar |
|---|---|
| Servislerin ayağa kalkması | Geçti |
| Kuyruk ve worker | Geçti |
| Çok turlu recovery | Çalıştı, etkisiz kaldı |
| Artifact/raw teslimi | Geçti |
| Coverage dürüstlüğü | Büyük ölçüde geçti |
| En iyi kaynakları bulma | Kaldı |
| Kaynak ailesi çeşitliliği | Kaldı |
| Sentinel recall | Kaldı |
| Claim–evidence doğruluğu | Kritik kusurla kaldı |
| Nihai araştırma cevabı | Kullanıma uygun değil |

Bu sürüm ekip içi deney ve altyapı doğrulaması için değerlidir; “mükemmel araştırma kalitesi” hedefiyle üretim kullanımına alınmamalıdır. Bir sonraki doğrulama, önce P0 kanıt filtresi ve entailment kapısı uygulanarak aynı protokol ve aynı sentinel ile tekrarlanmalıdır.
