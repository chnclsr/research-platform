# Word Report Export — Uygulama Raporu

**Platform sürümü:** v0.7.1
**Belge sürümü:** 1.0
**Tarih:** 2026-07-29

## Teslim edilen temel sürüm

Tamamlanan her araştırma `16_research_report.docx` artifact'ını üretir. Rapor,
LLM'in doğrudan Word yazmasıyla oluşturulmaz. LLM'den gelen anlatı yalnız mevcut
evidence-gate kurallarından geçmiş sentezdir; tablo, grafik, citation ve kaynak
kataloğu kalıcı araştırma kayıtlarından deterministik olarak üretilir.

## DOCX içeriği

- Başlık, araştırma sorusu, run kimliği ve UTC üretim zamanı
- Yönetici özeti
- Coverage ve audit tablosu
- Kaynak ailesi dağılımı grafiği
- İddia denetim durumu grafiği
- Kaynaklı bulgular ve tıklanabilir source URL'leri
- Sentez ve belirsizlik bölümü
- Bütün kabul edilmiş kaynakları içeren kaynak kataloğu

## Artifact sözleşmesi

- `16_research_report.docx`
- `16a_source_family_distribution.png`
- `16b_claim_status_distribution.png`

Bu artifact'lar sonuç ve tam araştırma ZIP paketlerine dahil edilir. Ham paket
yalnız ham araştırma verisini taşımaya devam eder.

## Doğrulama

- Pipeline acceptance testi DOCX ve iki grafik artifact'ını doğrular.
- DOCX bir Office Open XML paketi olarak incelenir; `word/document.xml` ve iki
  gömülü media dosyası zorunludur.
- Doğrudan exporter testi metin, tablo ve gömülü grafik kontrolü yapar.

LibreOffice bu bilgisayarda bulunmadığından otomatik PDF/PNG görsel render kapısı
henüz production ortamında etkin değildir. Bir sonraki işletim iyileştirmesi,
LibreOffice'i worker image'a ekleyip DOCX render sonucunu ayrı QA artifact'ı olarak
kaydetmektir.

## Sonraki sürüm genişleme noktası

Mevcut exporter tek seferde denetlenmiş rapor modelini işler. Yerel model uzun ve
karmaşık raporlarda yetersiz kalırsa, aynı `WordReportResult` sözleşmesine şu ara
aşamalar eklenebilir: bölüm planlama, claim kümelendirme, bölüm bazlı sentez,
adversarial kontrol ve son editoryal birleştirme. DOCX renderer, citation ve
grafik katmanı değişmeden kalır.
