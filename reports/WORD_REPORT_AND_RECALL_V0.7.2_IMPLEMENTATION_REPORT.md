# Word Raporu ve Literatür Recall İyileştirmesi

**Platform sürümü:** v0.7.2
**Belge sürümü:** 1.0
**Tarih:** 2026-07-29

## Amaç

Araştırma platformunun Word çıktısını basit bir teknik fixture olmaktan çıkarıp
okunabilir, denetlenebilir ve tam literatür envanterini koruyan ana teslimata
dönüştürmek; gerçek sağlıkta yapay zekâ koşusunda ortaya çıkan kaynak kaybı
nedenlerini gidermek.

## Uygulanan değişiklikler

### Word raporu

- Editoryal kapak, çalışma kimliği ve üretim zamanı
- Word TOC alanı ve sayfa numarası
- Yönetici değerlendirmesi ve denetlenmiş metrik özeti
- Araştırma sorusu, alt sorular, tarih kapsamı ve connector çerçevesi
- Coverage tablosu, yayın yılı ve claim audit grafikleri
- Pasaj alıntısı ve kaynak konumuyla ana bulgular
- Kanıt sentezi, çelişkiler, boşluklar ve belirsizlikler
- Connector dağılımı ve kaynak başına kanıt verimi
- Araştırmada korunan bütün kaynakları içeren tam katalog
- Bütün raporlanabilir iddiaları kaynak numaralarıyla eşleyen claim register
- Yöntem ve yeniden üretilebilirlik notu

Sayısal değerler, grafikler, kaynaklar ve atıflar yalnız veritabanındaki run
durumundan deterministik olarak üretilir. LLM yalnız denetimli anlatı alanlarını
yazar.

### Literatür recall ve edinim

- OpenAlex anahtarsız kullanımda devre dışı bırakılmıyor.
- OpenAlex açık PDF ve açık landing page konumlarını yayıncı DOI sayfasından
  önce tercih ediyor.
- Tam metin başarısızlığında akademik özet; başlık, yazar, yayıncı ve kalıcı
  kimlikle birlikte `scholarly_metadata` yöntemiyle korunuyor.
- Abstract-only kayıtlar `content_scope=abstract_and_metadata` ve
  `full_text_available=false` olarak işaretleniyor.
- Reserve adayların turdaki bütün kaynak kontenjanını tüketmesi engellendi.
- Mission balancing yalnız güçlü discovery relevance puanına sahip adayları
  branch kotasıyla öne çıkarıyor.
- Türkçe akciğer kanseri/BT/nodül terimleri İngilizce akademik sorgu
  sözlüğüyle eşleştiriliyor.
- Süre sonuna kadar çalışan literatür taramalarının LangGraph recursion limiti
  zaman bütçesine göre ölçekleniyor.

## Doğrulama

- Ruff statik kontrolü geçti.
- Odaklı connector, acquisition, relevance, recovery, pipeline ve Word testleri
  geçti.
- Tam test paketi: **147 test geçti**, 1 bağımlılık deprecation uyarısı.
- Gerçek koşulda ilk düzeltme öncesi anahtarsız OpenAlex devre dışıydı ve yalnız
  1 kaynak korunuyordu.
- OpenAlex ve metadata fallback sonrasında kaynak edinimi hızlandı; seçim
  düzeltmeleriyle ilk turda doğrudan ilgili akciğer kanseri/BT yayınları
  korunmaya başladı.

## Bilinen sınır

Windows hostta LibreOffice/soffice bulunmadığı için otomatik DOCX→PNG render
kapısı henüz native serviste çalışmıyor. DOCX yapısı ve OOXML testleri
doğrulanmaktadır; görsel render doğrulaması ayrıca bir LibreOffice worker veya
container eklendiğinde otomatikleştirilmelidir.
