# Beş Dakikalık Dört Model Karşılaştırma Raporu

Platform sürümü: `v0.2.7`

Belge sürümü: `1.0`

Tarih: `2026-07-16`

Test protokolü: `FIVE_MINUTE_MODEL_TEST_PROTOCOL.md` sürüm `1.0`

Değerlendirme metodolojisi: `QUALITATIVE_MODEL_EVALUATION_METHODOLOGY.md` sürüm `1.1`

## Yönetici özeti

Bu tek kör vakada mevcut araştırma agentı için en güvenilir model
`qwen3:4b-instruct-2507-q4_K_M` oldu. Model; ilgili kaynakların altısını, kritik kaynakların
üçünü ve karşı-kanıt kaynaklarının ikisini buldu, bütün aşamalarda kullanılabilir native
cevap üretti ve en kısa sürede tamamlandı. Kör değerlendirmede model kimliği bilinmeden
`Açık üstünlük` hükmü verildi.

`qwen3.5:4b`, D02’deki istatistiksel belirsizliği ve ilk analizin aşırı iddialarını iyi
denetledi. Ancak planning cevabı token sınırında kesildiği için parser fallback’e düştü ve
retrieval yalnız D02 ile konu dışı D11’e sıkıştı. Mevcut haliyle ana araştırma modeli değil,
dar evidence/audit rolü için adaydır.

`qwen3.5:9b`, 8 GB RTX 4060 üzerinde yalnız 4096 context ile tam GPU’da çalışabildi.
Thinking çıktısı context’i tükettiği için evidence, audit ve sentez çağrılarında görünür
final cevap üretemedi. Bu profil mevcut agent akışı için kullanılamaz.

`tomng/nanbeige4.1:3b-q8_0`, araştırma bütçesinin neredeyse tamamını kullandı; plan cevabını
tamamen thinking içinde tüketti, audit timeout aldı ve retrieval fallback’e düştü. Nihai
rapor üretti fakat kaynak kapsamı, Türkçe ve claim sınıflandırması güvenilir değildi.

Bu sonuç bir genel zekâ veya model ailesi benchmark’ı değildir. Sonuç; RTX 4060, Ollama
native chat, maksimum tam-GPU profil, thinking açık/kapalı model davranışı ve beş dakikalık
agent araştırma bütçesinin birlikte oluşturduğu operasyonel sonuçtur.

## Çalışma koşulları

- İşletim sistemi: Windows 11 Pro 64 bit, `10.0.26200`
- GPU: NVIDIA GeForce RTX 4060, `8188 MiB`
- NVIDIA sürücüsü: `595.95`
- Ollama: `0.31.2`
- Tekrar sayısı: model başına bir kör holdout koşusu
- Corpus: 16 dondurulmuş belge
- Gold etiketler: 9 ilgili, 5 kritik, 3 karşı-kanıt belgesi
- Retrieval: deterministik BM25, sorgu başına ilk 5, RRF ile ilk 8
- Araştırma bütçesi: model başına en fazla 300 saniye
- Sentez: araştırma bütçesi dışında, tamamlanana kadar
- GPU yürütme: modeller seri; bütün profiller `ollama ps` ile `100% GPU` doğrulandı
- Formatter: kullanılmadı; native içerik esas alındı
- Sampling tohumu: `42`

## Profil ve donanım sonuçları

| Model | Quantization | Context | Thinking | Research | Sentez | Tepe VRAM | Tepe GPU | Aktif ort. GPU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3 4B Instruct 2507 | Q4_K_M | 24.576 | Kapalı | 64,9 sn | 47,2 sn | 6990 MiB | %100 | %90,1 |
| Qwen3.5 4B | Q4_K_M | 73.728 | Açık | 174,7 sn | 58,4 sn | 7210 MiB | %100 | %88,0 |
| Qwen3.5 9B | Q4_K_M | 4096 | Açık | 191,1 sn | 86,5 sn | 7380 MiB | %100 | %91,8 |
| Nanbeige4.1 3B | Q8_0 | 36.864 | Açık | 295,0 sn | 187,1 sn | 6954 MiB | %95 | %91,3 |

Tepe GPU yüzdesi tek başına kalite veya sürekli doygunluk anlamına gelmez. “Aktif ortalama”
yalnız utilization değeri sıfırdan büyük örneklerin ortalamasıdır. Güç ölçümü kurumsal
sürücüde `N/A` döndüğü için raporlanmamıştır.

## Üretim hızı ve tamamlanma

| Model | Research completion token | Research tok/sn | Sentez completion token | Sentez tok/sn | Parser fallback | Timeout |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3 4B Instruct 2507 | 4265 | 71,5 | 2735 | 60,7 | Hayır | 0 |
| Qwen3.5 4B | 11.346 | 67,5 | 3802 | 66,7 | Evet | 0 |
| Qwen3.5 9B | 7720 | 42,1 | 3584 | 41,9 | Evet | 0 |
| Nanbeige4.1 3B Q8 | 12.288 | 53,7 | 9774 | 52,4 | Evet | 1 |

Ollama `eval_count`, thinking ve görünür content tokenlarını birlikte sayar. Bu nedenle
thinking açık modellerde yüksek completion token sayısı uzun ve kullanılabilir cevap
anlamına gelmez.

### Thinking/output davranışının etkisi

- Qwen3 4B planning çağrısı 972 tokenla geçerli ve tam JSON üretti.
- Qwen3.5 4B planning çağrısı 4096 token tavanına ulaştı. 16.544 thinking karakterine
  karşı yalnız 532 görünür karakter üretti ve JSON yarım kaldı.
- Qwen3.5 9B evidence ve audit çağrılarında sırasıyla 3624 ve 2048 completion token
  harcadı, fakat görünür content üretmedi. Sentezde 512 prompt + 3584 completion token,
  4096 context’i tamamen doldurdu; görünür final cevap yine boş kaldı.
- Nanbeige planning çağrısında 4096 token ve 14.152 thinking karakteri üretti, görünür
  content üretmedi. Evidence 8192 token tavanında kesildi; audit kalan araştırma süresinde
  timeout aldı.

Bu davranış Qwen3.5 ve Nanbeige’in muhakeme yeteneğinin yokluğunu kanıtlamaz. Native
thinking ile structured-output isteyen mevcut agent sözleşmesinin, görünür cevaba yeterli
token ayırmadığını gösterir. Agent açısından bu yine gerçek bir entegrasyon başarısızlığıdır.

## Retrieval sonuçları

Paydalar corpus kilitlenirken belirlenmiştir: 9 ilgili, 5 kritik, 3 karşı-kanıt belgesi.
Precision paydası modelin getirdiği benzersiz belge sayısıdır.

| Model | İlgili recall | Kritik recall | Karşı-kanıt recall | Precision | Getirilen belge |
|---|---:|---:|---:|---:|---|
| Qwen3 4B Instruct 2507 | 6/9 | 3/5 | 2/3 | 6/8 | D11, D16, D03, D01, D06, D08, D05, D07 |
| Qwen3.5 4B | 1/9 | 1/5 | 0/3 | 1/2 | D11, D02 |
| Qwen3.5 9B | 1/9 | 1/5 | 0/3 | 1/2 | D11, D02 |
| Nanbeige4.1 3B Q8 | 1/9 | 1/5 | 0/3 | 1/2 | D11, D02 |

Üç thinking modelinin aynı zayıf retrieval sonucunu vermesi sorgu kalitelerinin aynı
olduğunu göstermez. Üçünde de planning JSON’u parse edilemediği için sistem aynı fallback
sorgusunu kullandı. Bu tablo native agent entegrasyon başarısını ölçmektedir.

Qwen3 4B’nin önemli eksikliği D02’yi getirememesidir. D02, matched-firm
difference-in-differences tasarımı ve sıfırı içeren güven aralığıyla corpus’un en güçlü
karşılaştırmalı üretkenlik belgelerinden biridir. Model daha geniş kanıt bulsa da bu kritik
kaçırma nihai raporda mutlaka dikkate alınmalıdır.

## Kör nitel değerlendirme sonucu

Kimlik anahtarı açılmadan önce verilen hükümler:

| Kör etiket | Gerçek model | Kör hüküm |
|---|---|---|
| Model B | Qwen3 4B Instruct 2507 | `Açık üstünlük` |
| Model D | Qwen3.5 4B | `Güçlü fakat farklı rol için uygun` |
| Model A | Nanbeige4.1 3B Q8 | `Kritik hata` |
| Model C | Qwen3.5 9B | `Değerlendirmek için yetersiz çıktı` |

Ayrıntılı ve model kimliği açılmadan commit’lenmiş gözlemler
`FIVE_MINUTE_MODEL_BLIND_ASSESSMENT.md` dosyasındadır.

## Model bazlı yorum

### Qwen3 4B Instruct 2507

Mevcut mimari için ana model olarak kalmalıdır. Planı farklı araştırma risklerini gerçek
sorgulara dönüştürdü; D03, D05, D06, D07 ve D08’deki kritik sınırlamaları sentezde büyük
ölçüde korudu. En önemli riskleri:

- D02’yi kaçırması
- D01 alıntısından bulunmayan turnover sonucunu claim’e eklemesi
- Audit çağrısında JSON yerine düz metin üretmesi
- D08 için bir cümlede “değişiklik yok” bulgusundan yanlışlıkla “artışı doğrular” demesi
- Kaynaksız sentez tarihi üretmesi

Bu nedenle model seçimi, citation/claim doğrulama katmanının gereksiz olduğu anlamına
gelmez.

### Qwen3.5 4B

Ham D02 yorumunda Qwen3 4B’nin sentezinde bulunmayan önemli bir gücü gösterdi: güven
aralığının sıfırı içerdiğini sürekli korudu ve audit aşamasında “istatistiksel belgeli
artış” ifadesini düzeltti. Buna karşılık planning finali token tavanında kesildiği için
retrieval kalitesi değerlendirilemedi.

Mevcut profilde ana model yapılmamalıdır. Ayrı bir deneyde:

1. reasoning ve JSON formatting iki aşamaya ayrılmalı,
2. planning için thinking özeti görünür cevaba taşınmalı,
3. aynı kilitli corpus geliştirme verisi olarak tekrar kullanılmamalı,
4. yeni kör corpus üzerinde audit rolü yeniden sınanmalıdır.

### Qwen3.5 9B

RTX 4060’ın 8 GB belleğinde 9B modelin tam-GPU profili 4096 context ile sınırlıdır. Bu
context; soru, belgeler, thinking ve final cevabı birlikte taşımaya yetmedi. Sentez
çağrısında context bütçesinin tamamı thinking tarafından kullanıldı ve final cevap boş
kaldı.

CPU offload kabul edilmeden, thinking kısılmadan veya context küçültülmüş prompt zinciri
kurulmadan bu model mevcut araştırma mimarisinde kullanılmamalıdır. Kullanıcı kararıyla
9B’den vazgeçilmesi bu test tarafından desteklenmektedir.

### Nanbeige4.1 3B Q8

Parametre sayısı düşük olsa da Q8 ağırlıkları yaklaşık 6,3 GB Ollama model yerleşimi
oluşturdu. Uzun thinking üretimi araştırma bütçesini tüketti. Final cevapta:

- D11’in sıkıştırılmış hemşirelik programını azaltılmış-saatli beyaz yaka düzenine fazla
  genelledi,
- `Contradicted` ile `Uncertain` ayrımını bozdu,
- ciddi Türkçe bozulmaları üretti,
- corpus dışı tarih ekledi.

GPQA gibi tek bir benchmark’taki dikkat çekici sonuç bu agent görevine taşınmamıştır.
Mevcut mimaride kullanılması önerilmez.

## Mimari karar

V1 için önerilen model düzeni:

- Ana planning/query/evidence/synthesis: `qwen3:4b-instruct-2507-q4_K_M`
- Deterministik claim/citation/coverage kontrolleri: model dışı mevcut audit katmanları
- Qwen3.5 4B: üretim yolunda kapalı; yalnız yeni bir kör audit deneyi sonrasında aday
- Qwen3.5 9B ve Nanbeige4.1 3B Q8: mevcut RTX 4060 profilinde devre dışı

Şimdilik çok-model hibrit yapı eklenmemelidir. Qwen3.5 4B’nin dar audit avantajı tek vakada
görülmüştür; kalıcı mimari karmaşıklığını haklı çıkarmak için birden fazla yeni kör vakada
tekrarlanması gerekir.

## Geçerlilik sınırları

- Her model yalnız bir vaka ve bir tekrar üzerinde çalıştırıldı.
- Corpus sentetik ve dondurulmuştur; canlı web connector kalitesi ölçülmedi.
- Retrieval farkı üç modelde parser fallback tarafından belirgin biçimde etkilenmiştir.
- Model profilleri aynı context’e zorlanmadı; her biri cihazdaki en yüksek doğrulanmış
  tam-GPU profilinde çalıştı. Bu kullanıcı tarafından istenen donanım-adil karşılaştırmadır,
  eşit context karşılaştırması değildir.
- Qwen3 4B thinking kapalı instruct modeldir; diğer üçünde native thinking açıktır.
- Değerlendirici önceki model ailelerini görmüştür; kör etiket kullanılsa da yazı
  stilinden kaynaklanan örtük tanıma ihtimali tamamen yok edilemez.
- Bu corpus artık geliştirme verisidir. Gelecek kesin karşılaştırmada yeni, önceden
  kilitlenmiş kör vakalar kullanılmalıdır.
