# Beş Dakikalık Model Araştırma Test Protokolü

Platform sürümü: `v0.2.7`

Belge sürümü: `1.0`

Durum: `Çalıştırma öncesi kilitli`

Tarih: `2026-07-16`

## Amaç

Dört yerel modeli aynı dondurulmuş araştırma görevi üzerinde, model başına en fazla 300
saniyelik araştırma bütçesiyle karşılaştırmak. Nihai sentez araştırma bütçesi sona erdikten
sonra başlar ve tamamlanması beklenir.

Semantik kalite bileşik sayısal puana dönüştürülmez. Ham çıktılar
`QUALITATIVE_MODEL_EVALUATION_METHODOLOGY.md` uyarınca kör ve vaka-temelli incelenir.

## Modeller

- Qwen3 4B Instruct 2507 Q4_K_M
- Qwen3.5 9B Q4_K_M
- Qwen3.5 4B Q4_K_M
- Nanbeige4.1 3B Q8_0

Her model RTX 4060 üzerinde daha önce doğrulanan en yüksek tam-GPU context profilini
kullanır. Başka GPU işi eşzamanlı çalıştırılmaz ve model değişimleri arasında Ollama
belleği boşaltılır.

## Araştırma bütçesi

Araştırma zamanlayıcısı ilk model çağrısı gönderilmeden hemen önce başlar. Aşağıdaki
aşamaların toplamı 300 saniyeyi aşamaz:

1. Araştırma planı ve arama sorguları
2. Dondurulmuş corpus üzerinde deterministik BM25 retrieval
3. Getirilen belgelerin kanıt analizi ve çelişki denetimi

Yeni bir araştırma çağrısı yalnız kalan bütçe çağrının belirlenmiş azami süresini
karşılayabiliyorsa başlatılır. Timeout veya eksik cevap bütçeye dahil edilir.

## Sentez

Araştırma bütçesi durduktan sonra model; kendi planı, sorguları, retrieval sonuçları ve
kanıt notlarından nihai Türkçe rapor üretir. Sentez süresi 300 saniyelik araştırma
bütçesine dahil edilmez ve modelin cevabı tamamlaması beklenir. Sentez başlangıç/bitiş
süreleri ayrıca kaydedilir.

## Dondurulmuş corpus ve retrieval

Corpus: `data/qualitative_v1_corpus.json`

Modelin ürettiği sorgular aynı BM25 uygulamasına verilir. Her sorgunun ilk sonuçları
birleştirilir ve modelden bağımsız deterministic sıralama uygulanır.

Sayısal retrieval metrikleri:

- Relevant recall
- Critical-document recall
- Counter-evidence recall
- Precision
- İlk ilgili belge sırası ve reciprocal rank
- Yinelenmeyen getirilen belge sayısı

Relevance etiketleri model çıktıları görülmeden corpus dosyasında kilitlenmiştir.

## Nesnel çalışma metrikleri

- Araştırma süresi
- Sentez süresi
- Prompt/completion/reasoning tokenları
- Token/saniye
- Tepe VRAM ve GPU kullanımı
- Ollama GPU/CPU yerleşimi
- Context ve reasoning/output tavanları
- Timeout, parser ve formatter sayıları

## Nitel değerlendirme

Model adları çıktı dosyalarından kaldırılır ve sabit tohumla karıştırılarak `Model A–D`
etiketleri verilir. Kimlik anahtarı nitel hükümler yazılana kadar açılmaz.

İncelenecek alanlar:

- Planın nedensellik ve alternatif açıklamaları kapsaması
- Sorguların kaynak ve karşı-kanıt stratejisi
- Getirilen belgelerin doğru yorumlanması
- Null sonuç, belirsizlik ve iş yoğunlaştırmanın korunması
- Sentezin kaynaklardan daha güçlü iddia üretmemesi
- Türkçe açıklığın ve kaynak izlenebilirliğinin yeterliliği

## Geçersizlik koşulları

- Corpus veya relevance etiketlerinin model çıktıları görüldükten sonra değiştirilmesi
- Bir model için farklı araştırma sorusu kullanılması
- Araştırma bütçesine sentez süresinin yanlışlıkla dahil edilmesi
- CPU offload kullanan profilin tam-GPU profil diye raporlanması
- Formatter cevabının native cevap olarak sunulması
- Kimlik anahtarının nitel değerlendirmeden önce açılması
