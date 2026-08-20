# Beş Dakikalık Model Testi — Kör Nitel Değerlendirme

Platform sürümü: `v0.2.7`

Belge sürümü: `1.0`

Durum: `Model anahtarı açılmadan önce kilitlenmiş değerlendirme`

Tarih: `2026-07-16`

Metodoloji: `QUALITATIVE_MODEL_EVALUATION_METHODOLOGY.md` sürüm `1.1`

## Kapsam ve sınırlama

Bu değerlendirme yalnız `Model_A`–`Model_D` adıyla anonimleştirilmiş native çıktılar ve
önceden kilitlenmiş `qualitative-research-v1` corpus’u üzerinden yapılmıştır. Model kimlik
anahtarı incelenmemiştir. Değerlendirici önceki günlerde aynı model ailelerinin başka
çıktılarını gördüğü için körleştirme kusursuz değildir; yazı tarzından kimlik tahmini
yapılmamış ve kararlar yalnız bu dosyalardaki somut davranışlara dayandırılmıştır.

Bu tek araştırma vakasından genel zekâ sıralaması çıkarılmaz. Semantik kalite için sayısal
puan veya ağırlıklı toplam kullanılmamıştır.

## Model A

### Güçlü yönler

- D02’deki `%3,1` tahmini ile sıfırı içeren güven aralığının belirsizliğini fark eder.
- D11’in beyaz yaka popülasyonuna doğrudan uygulanamayacağını söyler.
- Nihai hükümde mevcut iki belgenin nedensel sonucu kanıtlamadığını korur.

### Kritik sorunlar

- Planlama cevabı boştur; sistem bütün araştırma sorusunu tek fallback sorgusu olarak
  kullanmıştır. Bunun sonucunda yalnız D11 ve D02 getirilmiş, kilitli corpus’taki D01,
  D03–D09 kanıtlarının tamamı kaçırılmıştır.
- Evidence çıktısı yarım kalmıştır. D02 kaydı cümlenin ortasında kesilir.
- D11’i önce “irrelevant” olarak doğruya yakın sınıflandırırken nihai raporda bunu beyaz
  yaka azaltılmış-saat düzenine karşı kanıt gibi kullanır. Oysa D11 hem hemşirelik
  popülasyonudur hem de toplam saati azaltmayan `4x10` sıkıştırılmış düzendir.
- “Üretkenlik artışı” ve “refah iyileştirmesi” için `Contradicted` etiketi verir. Elde
  bulunan belgeler iddiaları doğrudan çürütmekten çok yetersiz veya belirsiz bırakır.
- Türkçe ciddi ölçüde bozulmuştur: “tehlikel bir belirsizlik”, “gözetli sektör”,
  “toplum gözlem hatları” ve “özgürün korunması” gibi ifadeler anlamı zorlaştırır.
- Corpus’ta bulunmayan `Analiz tarihi: 2024` bilgisini üretir.

### Hüküm

`Kritik hata`. D02’nin istatistiksel belirsizliğini kavrasa da retrieval çöküşü, yarım
evidence cevabı, yanlış çelişki etiketleri ve bozuk dil güvenilir araştırma sentezini
engeller.

## Model B

### Güçlü yönler

- Plan; nedensellik, objektif/öz-bildirim ölçümü, seçilim, iş yoğunlaştırma, attrition,
  uzun dönem takip ve karşı kanıtı ayrı araştırma dalları yapar.
- On sorgu yüzeysel tekrar değildir. RCT, null/negative outcomes, workload intensity,
  attrition, selection bias, şirket KPI’ı ve uzun dönem sürdürülebilirlik için farklı
  retrieval yolları açar.
- D03’teki yüksek iş yüküne bağlı differential attrition’ı, D06’daki survivorship bias’ı,
  D08’deki hafta sonuna kayan işi, D05’teki fazla mesai/backlog sorununu ve D07’deki yayın
  yanlılığı/heterojenliği görünür tutar.
- Nihai sentez üretkenlik ve refahı ayrı değerlendirir; “refah bulguları daha tutarlı,
  üretkenlik bulguları daha zayıf” biçimindeki corpus örüntüsünü büyük ölçüde korur.
- D11 ve D16’nın asıl araştırma sorusuna doğrudan kanıt olmadığını audit bölümünde ayırır.

### Sorunlar ve riskler

- D01 için claim “işten çıkışı artmamıştır” derken verdiği alıntıda turnover yoktur.
- D07’yi `supports` olarak etiketlemek hedef claim açık olmadığı için muğlaktır; belge
  esas olarak üretkenlik kanıtını sınırlar ve refah örüntüsünü nitelendirir.
- Audit JSON istenmesine rağmen düz metin üretmiş ve çıktı kesilmiştir. Semantik analiz
  yararlı olsa da structured-output entegrasyonu güvenilir değildir.
- “D08 ... bu, üretkenliğin arttığını doğrular” cümlesi, hemen öncesindeki “önemli değişiklik
  yoktur” bulgusuyla çelişen bir yazım/mantık hatasıdır.
- D05 üretim işletmesidir; beyaz yaka popülasyonuna doğrudan genelleme sınırı daha görünür
  olmalıydı.
- Objektif refah kanıtı için EKG ve kan testi istemesi corpus’tan çıkmayan gereksiz bir
  yöntem dayatmasıdır.
- `Sentez yapıldı: 2025-04-05` tarihi kaynaksız ve yanlıştır.

### Hüküm

Bu vaka için `Açık üstünlük`. Üstünlük hatasızlıktan değil, araştırma sorusunun kritik
boyutlarını kapsayan retrieval ve çok-kaynaklı sentezden gelir. Structured-output ve bazı
yorum hataları nedeniyle tek başına denetimsiz kullanılmamalıdır.

## Model C

### Güçlü yönler

- Görülebilen plan parçası kontrollü tasarım, objektif ölçüm, seçilim ve uzun dönem takip
  ihtiyacını tanır.

### Kritik sorunlar

- Planning JSON’u cümlenin ortasında kesildiği için parser fallback’e düşmüştür.
- Yalnız D11 ve D02 retrieval edilmiştir.
- Evidence, audit ve final cevap yoktur.

### Hüküm

`Değerlendirmek için yetersiz çıktı`. Operasyonel bakımdan bu koşu başarısızdır ve agent’ın
nihai sentez rolünde kullanılamaz.

## Model D

### Güçlü yönler

- D02’deki güven aralığının sıfırı içerdiğini doğru korur ve sonucu “sıfır veya küçük fayda
  ile uyumlu” biçiminde sınırlar.
- Evidence ve audit istenen JSON yapısına uyar.
- Audit, ilk claim’deki “istatistiksel belgeli artış” ifadesini düzeltir.
- D11’in toplam saat azaltımı değil sıkıştırılmış program olduğunu fark eder.
- Nihai rapor yalnız verilen iki belgeye dayanır ve dış kaynak uydurmaz.

### Sorunlar ve riskler

- Plan JSON’u tamamlanamadığı için sorgular fallback’e düşmüş ve yalnız D11+D02
  getirilmiştir. Bu nedenle corpus’taki refah, attrition, iş yoğunlaştırma, uzun dönem,
  sistematik derleme ve yazılım verisi kanıtlarını kaçırır.
- D11’i açıklamada sıkıştırılmış/hemşirelik bağlamı olarak tanısa da nihai sentezde
  azaltılmış-saatli beyaz yaka uygulamasına karşı kanıt gibi fazla ağırlıklandırır.
- Turnover düşüşünü `Supported` refah kanıtı sayması fazla güçlüdür; turnover refah için
  dolaylı ve çok nedenli bir göstergedir.
- “4x8’den 4x10’a” der; kaynak gerçekte `5x8`den `4x10`a geçiştir.
- Türkçe “ünituenlik”, “işten dönüşüm”, “emdيرli/evranı” benzeri bozuk ifadeler nedeniyle
  profesyonel rapor kalitesine ulaşmaz.

### Hüküm

`Güçlü fakat farklı rol için uygun`. Dar kaynak setinde D02’nin istatistiksel yorumunu ve
adversarial düzeltmeyi Model A’dan daha güvenilir yapar; ancak retrieval/parser sorunu ve
dil bozukluğu nedeniyle uçtan uca araştırma modeli olarak Model B’nin gerisindedir.

## Görev bazlı karşılaştırma

### Planlama ve query üretimi

- Model B: `Açık üstünlük`.
- Model D: Plan kavramsal olarak iyi, fakat tamamlanamadığı için operasyonel üstünlük yok.
- Model A: Boş plan.
- Model C: Yarım plan ve parser fallback.

### Retrieval

Önceden etiketli dokuz ilgili, beş kritik ve üç karşı-kanıt belgesi üzerinden:

- Model B: sekiz belge getirir; bunların altısı ilgili, üçü kritik ve ikisi karşı-kanıttır.
- Model A, C ve D: ikişer belge getirir; yalnız D02 ilgilidir, D11 distractor’dır. Kritik
  belgelerden yalnız D02 bulunur ve hiçbir önceden etiketli karşı-kanıt belgesi bulunmaz.

Bu ölçüm sorgu kalitesinin tamamı değildir; fakat bu vakada downstream sentez farkının ana
nedeni retrieval kapsamıdır.

### Evidence ve adversarial audit

- Model B: `Sınırlı üstünlük`; en geniş kritik bulgu kapsamı vardır, fakat audit formatı
  bozulur ve bazı claim yorumları hatalıdır.
- Model D: `Güçlü fakat farklı rol için uygun`; iki belgeyle sınırlı olmasına rağmen D02
  belirsizliğini iyi denetler ve JSON uyumu daha iyidir.
- Model A: yarım evidence nedeniyle `Kritik hata`.
- Model C: `Değerlendirmek için yetersiz çıktı`.

### Nihai sentez

- Model B: `Açık üstünlük`; kapsam ve soru boyutlarını ayırma en iyidir.
- Model D: `Sınırlı üstünlük` Model A’ya karşı; ana istatistiksel belirsizliği korur, fakat
  kaynak kapsamı ve dil zayıftır.
- Model A: kaynak kapsamı, etiketleme ve dil sorunları kritiktir.
- Model C: final cevap yoktur.

## Kör genel sonuç

Bu tek vaka için tercih sırası:

1. Model B — ana araştırma planlama, retrieval ve sentez adayı.
2. Model D — dar evidence/audit görevinde yardımcı aday; tek başına araştırma için değil.
3. Model A — mevcut profilde güvenilir değil.
4. Model C — çıktı tamamlamadığı için kullanılamaz.

Hibrit kullanım ancak Model B’nin geniş retrieval/sentezi ile Model D’nin dar istatistik
denetiminin başka kör vakalarda da tamamlayıcı olduğu görülürse önerilebilir. Bu tek vaka,
kalıcı bir hibrit mimari kararı için yeterli değildir.
