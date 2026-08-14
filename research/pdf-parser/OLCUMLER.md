# Ölçüm Sonuçları

Bu belge yalnızca **ölçülen sayıları** içerir. Yorum, değerlendirme ve öneri `RAPOR.md`
dosyasına aittir.

- Kaynak veri: `sonuclar.csv`
- Ham çıktılar: `out/`
- Ölçüm scripti: `compare.py`
- Tarih: 2026-08-12

## Ortam

| | |
|---|---|
| pdf-inspector | 1.14.1 |
| pypdf | 6.15.0 |
| Python | 3.10.10 |
| İşletim sistemi | Windows 11 Pro |

Ölçüm disiplini: her dosya her parser ile 3 koşu, ısınma koşusu atıldı, medyan alındı.

## Test kümesi

| Dosya | Boyut (MB) | Sayfa | Hedeflenen zorluk |
|---|---:|---:|---|
| `bert_2sutun_dipnot` | 0,78 | 16 | İki sütun + dipnot |
| `resnet_2sutun_gorsel` | 0,82 | 12 | İki sütun + görsel |
| `sybil_tip_2sutun` | 0,80 | 17 | Tıp dergisi düzeni |
| `attention_tablo` | 2,22 | 15 | Tablo |
| `vgg_tablo_agirlikli` | 0,20 | 14 | Tablo ağırlıklı |
| `gpt3_uzun_75sayfa` | 6,77 | 75 | Uzun belge |
| `gpt4_uzun_gorsel` | 5,25 | 100 | Uzun + görsel ağırlıklı |
| `taranmis_bert_2sutun_dipnot` | 2,24 | 6 | Taranmış, metin katmanı yok |
| `turkce_makale` | 0,12 | 6 | Türkçe karakter kümesi |

Sayfa sayıları doğrulandı: her dosyada pdf-inspector'ın bildirdiği sayfa sayısı, pypdf'in
okuduğu gerçek sayfa sayısıyla birebir aynı (9/9).

## 1. Hız

| Dosya | Boyut (MB) | pypdf (sn) | pdf-inspector (sn) | Oran |
|---|---:|---:|---:|---:|
| attention_tablo | 2,22 | 0,538 | 0,059 | 9,1× |
| bert_2sutun_dipnot | 0,78 | 0,381 | 0,054 | 7,1× |
| gpt3_uzun_75sayfa | 6,77 | 0,847 | 0,111 | 7,6× |
| gpt4_uzun_gorsel | 5,25 | 1,187 | 0,132 | 9,0× |
| resnet_2sutun_gorsel | 0,82 | 0,302 | 0,039 | 7,7× |
| sybil_tip_2sutun | 0,80 | 0,272 | 0,039 | 7,0× |
| turkce_makale | 0,12 | 0,133 | 0,021 | 6,3× |
| vgg_tablo_agirlikli | 0,20 | 0,477 | 0,042 | 11,4× |
| taranmis_bert (taranmış) | 2,24 | 0,002 | 0,002 | 1,0× |

En büyük dosyada (100 sayfa / 5,25 MB) çökme veya hata gözlenmedi.

## 2. Çıkarılan karakter sayısı

| Dosya | pypdf | pdf-inspector | Fark |
|---|---:|---:|---:|
| attention_tablo | 39.781 | 40.636 | +2,1% |
| bert_2sutun_dipnot | 64.321 | 66.094 | +2,8% |
| gpt3_uzun_75sayfa | 237.638 | 240.286 | +1,1% |
| gpt4_uzun_gorsel | 286.041 | 289.324 | +1,1% |
| resnet_2sutun_gorsel | 59.509 | 60.944 | +2,4% |
| sybil_tip_2sutun | 59.199 | 59.807 | +1,0% |
| turkce_makale | 26.687 | 27.019 | +1,2% |
| vgg_tablo_agirlikli | 55.146 | 55.375 | +0,4% |
| taranmis_bert | 70 | 0 | — |

## 3. Kusur sayımları

Biçim: `pypdf / pdf-inspector`

| Dosya | Ligatür | Tireleme | Dipnot işareti | Sayfa mobilyası |
|---|---|---|---|---|
| attention_tablo | 0 / 0 | 16 / 16 | 6 / 4 | 0 / 0 |
| bert_2sutun_dipnot | 157 / 0 | 332 / 307 | 3 / 24 | 0 / 0 |
| gpt3_uzun_75sayfa | 444 / 0 | 38 / 29 | 165 / 230 | 0 / 3 |
| gpt4_uzun_gorsel | 365 / 0 | 84 / 63 | 78 / 11 | 5 / 8 |
| resnet_2sutun_gorsel | 109 / 0 | 173 / 156 | 16 / 50 | 0 / 0 |
| sybil_tip_2sutun | 63 / 0 | 34 / 31 | 2 / 0 | 17 / 23 |
| turkce_makale | 0 / 0 | 36 / 70 | 5 / 0 | 0 / 0 |
| vgg_tablo_agirlikli | 221 / 0 | 51 / 52 | 71 / 68 | 13 / 14 |
| taranmis_bert | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

**Ölçüm sınırı:** `dipnot_isareti` ve `sayfa_mobilyasi` sütunları regex tabanlıdır. Kullanılan
desenler gerçek kusur ile korunmuş satır içi atıfı ayırt edemez. Bu iki sütun elle
doğrulanmadan yorumlanmamalıdır.

## 4. Başlık ve kaynakça kapısı

| Dosya | pypdf başlık | inspector başlık | pypdf kapı | inspector kapı |
|---|---:|---:|---:|---:|
| attention_tablo | 15 | 38 | 0 | 1 |
| bert_2sutun_dipnot | 16 | 42 | 0 | 2 |
| gpt3_uzun_75sayfa | 75 | 77 | 0 | 2 |
| gpt4_uzun_gorsel | 109 | 142 | 0 | 6 |
| resnet_2sutun_gorsel | 15 | 23 | 0 | 1 |
| sybil_tip_2sutun | 17 | 18 | 0 | 0 |
| turkce_makale | 6 | 13 | 0 | 1 |
| vgg_tablo_agirlikli | 14 | 14 | 0 | 1 |
| taranmis_bert | 6 | 0 | 0 | 0 |

pypdf'in ürettiği başlıkların tamamı `# Page N` biçimindedir; gerçek bölüm başlığı değildir.
Bu nedenle pypdf sütunundaki kapı sayısı 9/9 dosyada 0'dır.

pdf-inspector 9 dosyanın 7'sinde `evidence_quality.is_non_evidence_section()` kapısını
tetikleyen gerçek bir başlık üretmiştir (`References`, `REFERENCES`, `Kaynakça`).

**Ölçüm sınırı:** Başlık sayısı ham sayıdır; başlıkların kaçının gerçek bölüm başlığı olduğu
ölçülmemiştir. Bu değerlendirme `out/basliklar_*.txt` dosyaları üzerinden elle yapılacaktır.

## 5. Türkçe karakter kontrolü

`turkce_makale` dosyasında Türkçe karakter sayısı: pypdf 1.765, pdf-inspector 1.765.
Kayıp yok. `Kaynakça` başlığındaki `ç` karakteri kod noktası düzeyinde doğrulandı (U+00E7).
Her iki parser da bozuk kodlama bayrağı üretmedi.

## 6. Taranmış dosya davranışı

| | pypdf | pdf-inspector |
|---|---|---|
| Çıkarılan karakter | 70 | 0 |
| Sınıflandırma | — | `scanned`, güven 0,95 |
| OCR gerekli sayfa | — | 6 / 6 |

## 7. Alternatif: pypdf `extraction_mode="layout"`

Aynı 9 dosyada ölçüldü.

| Dosya | plain (karakter) | layout (karakter) | Fark | Uyarı sayısı |
|---|---:|---:|---:|---:|
| attention_tablo | 39.781 | 42.844 | +7,7% | 1 |
| bert_2sutun_dipnot | 64.321 | 84.676 | +31,6% | 2 |
| gpt3_uzun_75sayfa | 237.638 | 304.985 | +28,3% | 1 |
| gpt4_uzun_gorsel | 286.041 | 144.630 | **−49,4%** | 1 |
| resnet_2sutun_gorsel | 59.509 | 81.855 | +37,6% | 1 |
| sybil_tip_2sutun | 59.199 | 251.034 | +324,1% | 7 |
| turkce_makale | 26.687 | 146.390 | +448,5% | 0 |
| vgg_tablo_agirlikli | 55.146 | 60.932 | +10,5% | 1 |
| taranmis_bert | 70 | 70 | 0,0% | 0 |

Uyarı metni: `Rotated text discovered. Output will be incomplete.`
9 dosyanın 7'sinde en az bir uyarı üretildi.

Layout modunda kusur sayımları:

| Dosya | Ligatür (plain → layout) | Tireleme (plain → layout) | Kapı (plain → layout) |
|---|---|---|---|
| bert_2sutun_dipnot | 157 → 157 | 332 → 318 | 0 → 0 |
| gpt3_uzun_75sayfa | 444 → 444 | 38 → 38 | 0 → 0 |
| resnet_2sutun_gorsel | 109 → 109 | 173 → 164 | 0 → 0 |
| vgg_tablo_agirlikli | 221 → 221 | 51 → 51 | 0 → 0 |
| gpt4_uzun_gorsel | 365 → 0 | 84 → 50 | 0 → 0 |

`gpt4_uzun_gorsel` satırındaki ligatür düşüşü, aynı dosyada ölçülen %49,4'lük içerik kaybıyla
birlikte okunmalıdır.
