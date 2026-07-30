# LLM Sentez Raporu Pipeline'ı — Uygulama Raporu

Platform sürümü: `v0.8.0`

Belge sürümü: `1.0`

Tarih: `2026-07-29`

## 1. Amaç

Önceki Word çıktısı denetlenebilir olmasına rağmen ana gövdede kaynak, claim ve
coverage envanterini öne çıkarıyordu. Bu sürümün amacı; ham literatürü kaybetmeden,
ana teslimatı kaynaklar arasındaki ortak sonuçları, ayrışmaları, sınırlılıkları ve
araştırma boşluklarını açıklayan bir LLM sentez raporuna dönüştürmektir.

Grafikler de platformun kaç kaynak topladığını veya kaç claim doğruladığını göstermek
yerine, araştırma konusunu ve raporun mantığını açıklayacak şekilde değiştirilmiştir.

## 2. Yeni çalışma akışı

```text
Denetlenmiş claim + passage + source
            │
            ▼
Deterministik tema planı (en fazla 5 tema)
            │
            ▼
Tema başına sınırlı kanıt paketi (en fazla 12 claim)
            │
            ▼
LLM tematik sentezi
  ├─ ortak yön
  ├─ ayrışma / çelişki
  └─ araştırma açısından anlam
            │
            ▼
Kaynak allow-list ve dil doğrulaması
  ├─ geçerli → kabul
  └─ bozuk → yalnız çeviri/format onarımı
            │
            ▼
Temalar arası yönetici sentezi ve sonuç
            │
            ▼
Sentez-öncelikli DOCX + denetim ekleri
```

Yerel Qwen 4B bütün corpus'u tek promptta tutmak zorunda değildir. Her bölüm yalnız
ilgili kanıt paketini görür. Modelin kullanabileceği kaynak kimlikleri `[S01]`,
`[S02]` biçiminde önceden sınırlandırılır; bilinmeyen bir `[Sxx]`, yeni URL veya
bozuk kaynak işareti kabul edilmez.

## 3. Word raporunun yeni yapısı

Ana gövde:

1. Yönetici sentezi ve sonuç cümlesi
2. Araştırma sorusu ve kapsam
3. Literatürün konu haritası
4. Tematik kanıt sentezi
5. Çalışmalar arası değerlendirme, sonuç ve araştırma boşlukları

Denetim ekleri:

- Ek A: yöntem, coverage ve yeniden üretilebilirlik
- Ek B: tam kaynak kataloğu
- Ek C: denetlenmiş claim register

Bu ayrım sayesinde okuyucu önce araştırmanın anlamını görür; kaynak envanteri ve
platform ölçümleri kaybolmadan geriye dönük denetim için korunur.

## 4. Konu odaklı grafikler

`16a_research_contribution_landscape.png`, çalışmaların araştırma katkısını
gösterir. Örnek kategoriler; tespit/tanı, tahmin/risk, dış doğrulama,
uygulama/iş akışı, sentez/derleme ve veri seti/benchmark'tır.

`16b_theme_evidence_map.png`, her çalışmanın rapordaki hangi sentez temasına kanıt
sağladığını gösterir. Böylece okuyucu bir temanın tek bir çalışmaya mı dayandığını,
yoksa farklı çalışmalar tarafından mı beslendiğini görür.

Grafikler yalnız kaynaklarda bulunan metin ve metadata üzerinden üretilir. Ortak
sonlanımı ölçmeyen çalışmaların AUC, doğruluk, duyarlılık veya benzeri sayıları
tek bir performans grafiğinde karşılaştırılmaz.

## 5. Canlı doğrulama

Doğrulama run'ı: `01KYPBWB45RSQ0EFCC5FVRKGCZ`

Konu: 2024–2026 döneminde toraks/BT görüntülerinden yapay zekâ ile akciğer kanseri
risk tahmini, erken saptama, nodül sınıflandırması ve tarama triyajı.

Kullanılan mevcut corpus:

- 16 korunan kaynak
- 62 atomik claim
- 44 raporlanabilir claim
- 5 sentez teması

Yeni çıktı:

- `16_research_report.docx`
- `16a_research_contribution_landscape.png`
- `16b_theme_evidence_map.png`
- sentez-öncelikli `01_executive_summary.md`
- sentez-öncelikli `02_full_research_report.md`

Doğrulamalar:

- Ruff: geçti
- Regresyon paketi: `149 passed`
- DOCX içindeki kaynak atıfları: yalnız mevcut `S01–S16`
- Bilinmeyen citation: `0`
- Gömülü görsel: `2`; ikisinde de title ve alternatif açıklama mevcut
- Word tablo genişlikleri: tamamı sabit `9360 DXA`
- Üretilen artifact sözleşmesi: `21`

## 6. Dürüst kalite değerlendirmesi

Yeni çıktı önceki kaynak/claim derlemesinden belirgin biçimde daha iyi bir rapor
yapısına sahiptir: bulguları tema içinde birleştirir, yanlış pozitif–duyarlılık
gerilimini, doğrulama sorunlarını ve klinik anlamı birlikte tartışır.

Yerel Qwen 4B her tema çağrısında citation ve rapor dili kurallarına kusursuz
uymamıştır. Sistem bu durumları yakalamış; bazı katmanlarda yalnız çeviri/format
onarımı veya deterministik güvenli dönüş kullanmıştır. Bu nedenle v0.8.0,
“otonom yayıma hazır bilimsel makale yazarı” değil; kaynak uydurmayan ve okunabilir
bir ilk sentez taslağı üreten denetlenebilir rapor pipeline'ıdır. Özellikle yüksek
riskli klinik yorumlar insan uzman incelemesinden geçmelidir.

## 7. Görsel QA sınırlaması

DOCX yapısı, tablo geometrisi, citation allow-list'i ve görsel alternatif metinleri
programatik olarak doğrulanmıştır. Bu bilgisayarda LibreOffice/`soffice` bulunmadığı
için `render_docx.py` ile sayfa PNG/PDF rasterizasyonu yapılamamıştır. İki bağımsız
PNG grafik doğrudan görsel olarak incelenmiş ve okunabilir bulunmuştur.
