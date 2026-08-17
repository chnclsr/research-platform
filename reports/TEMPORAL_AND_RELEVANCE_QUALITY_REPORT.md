# Zamansal Kapsam ve Kaynak Kalitesi Düzeltme Raporu

Platform sürümü: `v0.5.1`

Belge sürümü: `1.1`

Tarih: `2026-07-17`

## Olay

Ekip liderinin `01KXNSZAGK5SBQEWFW5CY76385` araştırması, son üç ayda axial chest CT ile akciğer kanseri risk tahmini çalışmalarını aradı. İş `completed_incomplete` sonlandı ve rapor güncel çalışma bulunamadığı izlenimini verdi.

## Kök nedenler

1. `last 3 months` metinde kalmış; protokolde `scope.start_date` ve `scope.end_date` boş bırakılmıştı.
2. Akademik API'lere tarih filtresi gönderilmediği için eski yayınlar ilk sonuç kotasını doldurdu.
3. Core profilindeki dört ailenin tamamı coverage hedefi sayıldı; tıbbi yayın sorusu Federal Register ve kod/veri kaynaklarını gereksiz yere aradı.
4. `risk`, `model`, `deep learning`, `study` gibi genel kelimeler finans ve başka alanlardaki kaynaklara yüksek aday puanı verdi.
5. Kaynak edinildikten sonra tam içeriğe uygulanan ikinci bir semantik kabul kapısı yoktu.
6. Claim alaka hesabı kaynak puanını alt sınır olarak kullanıyor; alakasız pasajlar yüksek puanlı kaynaktan geldiğinde raporlanabilir kalabiliyordu.

## Uygulanan düzeltmeler

- Göreli tarih aralığını UTC başlangıç/bitiş değerlerine çeviren deterministik parser.
- Akademik sağlayıcılara tarih filtresi pushdown ve normalize edilmiş `published_at` provenance alanı.
- Bilimsel yayın niyeti belirgin sorularda yalnız akademik ailenin zorunlu coverage hedefi olması; diğer ailelerin istenirse protokolle açıkça zorlanabilmesi.
- Keşif sonrası tarih filtresi ve edinim sonrası içerik-alaka filtresi.
- Genel araştırma kelimelerini konu çapası saymayan daha sıkı aday/claim alaka hesabı.
- Raw teslimde claim audit metriğinin uygulanamaz (`1.0`) kabul edilmesi; aile, sorgu dalı, otorite ve doygunluk eşiklerinin korunması.

## Statik kabul testleri

- Göreli tarih parser'ı ve akademik coverage profili.
- Crossref, Europe PMC ve arXiv sorgularında tarih filtresi parametreleri.
- Eski ve tarihi bilinmeyen kaynağın sınırlı tarih araştırmasından elenmesi.
- Finansal risk makalesinin akciğer CT sorusundan elenmesi.
- İlgili lung cancer CT çalışmasının korunması.
- Kaynak puanı yüksek olsa bile alakasız claim'in soru alakasını miras alamaması.

## Canlı sağlayıcı probu

Crossref ve Europe PMC, `2026-04-17` ile `2026-07-17` aralığında ilgili akciğer CT/radiomics kayıtları döndürdü. arXiv'in eski uzun `all:` sorgusunun tarih sırasında alakasız sonuç ürettiği ayrıca saptandı ve ayırt edici alan terimlerinin `AND` ile birleştirildiği sorguya geçildi.

## Canlı regresyon sonuçları

### Ekip liderinin hatalı koşusu

`01KXNSZAGK5SBQEWFW5CY76385` koşusunda tarih alanları boştu. Sistem 94 kaynak ve
125 claim kaydetti; aile coverage değeri `0,50` ve çözülmemiş major claim sayısı `8`
oldu. Kaynakların içinde finansal risk çalışmaları, ilgisiz politika belgeleri ve arXiv
sayfa şablonu bulunuyordu. Buna karşılık olay kayıtlarında Nisan-Haziran 2026 tarihli
ilgili tıbbi sonuçlar da vardı; dolayısıyla doğru çıkarım “veri yok” değil, “ilgili veri
gürültünün altında kaldı” olmalıydı.

### Zamansal ve semantik kabul koşusu

Nihai kabul koşusu: `01KXQER1RHDNCRJYJ0MC9GVNBB`.

- Protokol tarih aralığını otomatik olarak `2026-04-17`–`2026-07-17` yaptı.
- Zorunlu aile hedefi yalnız akademik aile oldu.
- Crossref 429 sayısı seri hız sınırlama ve tekrar denemeden sonra `0` oldu.
- İki doğrudan ilgili, tarih aralığı içindeki kaynak kabul edildi: 16 Haziran 2026
  tarihli LDCT/AI sistematik incelemesi ve 7 Mayıs 2026 tarihli ticari CT akciğer
  taraması AI ürünleri/evidence çalışması.
- Kaynak aile coverage değeri `1,0`, claim audit `1,0` oldu. İki tur ve beş dakikalık
  kabul bütçesinde sorgu dalı coverage `0,2` kaldığı için sonuç dürüst biçimde
  `completed_incomplete` sonlandı; artık “veri bulunamadı” sonucu üretmedi.
- Eski tarihli, yalnız chest X-ray kullanan, küçük hücreli akciğer kanserini genel
  olarak ele alan, PET/CT odaklı ve bozuk DOI içerikleri kaydedilmeden reddedildi.

### MCP üzerinden yalnız ilgili ham kaynak teslimi

Nihai ham-kaynak koşusu: `01KXQF8Y0MPR9P72DNXQK3BM7V`.

- Dört kaynak kabul edildi; dördünün merkezi konusu MCP server güvenliği,
  authorization veya zero-trust MCP iletişimiydi.
- Genel “MCP nedir?” sayfası son strict kapıdan geçmedi.
- Ham kipte claim extraction çalışmadı (`0` claim) ve claim audit uygulanamaz olduğu
  için `1,0` kabul edildi.
- MCP `read_research_raw_data` çağrısı normalize kaynak JSONL verisini döndürdü.
- MCP `download_research_delivery(mode=raw)` çağrısı 448.960 baytlık ZIP üretti.
  ZIP yalnız kaynak kataloğu, bibliyografya, protokol, yeniden üretilebilirlik manifesti,
  ham kaynaklar ve ham pasajları içerdi; sentez raporu içermedi.
- Teslim SHA-256 değeri:
  `222f4c2a88c1f514c1c745495eeb90e937203a4883ca17725a3d74da208fc5c8`.

Ham koşunun aile coverage değeri `0,75` kaldı; eksik aile genel web idi. Bu bir kalite
hatası değildir: doğrudan ilgili kaynak bulamayan aileyi alakasız bir sayfayla doldurmak
yerine koşu `completed_incomplete` olarak kapandı.

## Son karar

Düzeltmeler precision ve zamansal doğruluğu belirgin biçimde artırdı. Sistem artık
“son üç ay” ifadesini gerçek tarihlere dönüştürüyor, eski sonuçları API ve kayıt
kapılarında eliyor, yeni yayımlanmış derlemeleri doğru yorumluyor ve yalnız ilgili ham
kaynak talebinde model karar veremezse fail-closed davranıyor. Dar süre/round bütçesinde
coverage eksikliği devam edebilir; bu eksiklik artık alakasız kaynak kabul edilerek
gizlenmiyor.
