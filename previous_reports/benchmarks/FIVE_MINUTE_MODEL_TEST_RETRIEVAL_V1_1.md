# Beş dakikalık model testi: retrieval sözleşmesi 1.1

Tarih: 2026-09-15

Bu ek yalnız gelecekteki test koşularına uygulanır. `FIVE_MINUTE_MODEL_TEST_PROTOCOL.md`
ve `FIVE_MINUTE_MODEL_COMPARISON_REPORT.md` 2026-07-16 tarihli kilitli 1.0 koşusunu
belgeler; eski sonuçlar yeniden hesaplanmadı. Dondurulmuş korpus ve gold relevance
etiketleri değiştirilmedi. 1.0 ile 1.1 retrieval metrikleri doğrudan karşılaştırılmamalı.

## Düzeltmeler

- Tokenizer Unicode kelime karakterlerini korur. `çalışanların` ve `yoğunlaştırma`
  parçalanmaz; `iş`, İngilizce `is` tokenına dönüşmez. İngilizce bağlaç/yardımcı sözcükler
  tek başına BM25 konu eşleşmesi yaratmaz.
- Plan istemi, Türkçe soru ve rapora karşın korpusun İngilizce olduğunu açıkça söyler ve
  yalnız İngilizce sorgu ister. Açık Türkçe harf içeren sorgular İngilizce-korpus
  sözleşmesine aykırı kabul edilir. Bu denetim genel bir dil çevirmeni değildir;
  aksansız Türkçe sorgu varsa yalnız gerçek leksik eşleşmeler dönebilir.
- Plan JSON'u eksik/hatalı, sorgu listesi kusurlu veya dili uyumsuzsa tam Türkçe soru
  fallback sorgusu yapılmaz. `queries=[]`, `retrieval_status=skipped_unusable_plan` ve
  sıfır retrieval metrikleri kaydedilir. Kanıt/çelişki çağrıları boş belgeyle yapılmaz;
  sentez kanıt yokluğunu belirtmekle yükümlüdür.
- Yeni çıktılar `retrieval_contract_version=1.1` ve `search_language=en` taşır; kör
  değerlendirme dosyası da retrieval durumunu taşır. Manifest, kilitli temel protokolün
  yanında bu ekin yolunu ayrıca kaydeder.

Regresyon testleri dondurulmuş sorunun eski D02/D11 sahte eşleşmelerini, Türkçe kelime
bütünlüğünü, bozuk planın retrieval atlanmasını ve boş kanıt analizinin çağrılmamasını
sabitler. Bu değişiklik modellerin yeni beş dakikalık koşusunu başlatmaz.
