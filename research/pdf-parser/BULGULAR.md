# Elle İnceleme Bulguları

Yöntem: orijinal PDF sayfası **hakem** alınır. İki parser çıktısı aynı sayfa aralığında
karşılaştırılır, hatalar aşağıdaki sabit tanımlara göre sayılır.
Hata tanımları inceleme başlamadan önce sabitlenmiştir.

Karşılaştırılan çıktılar:
- `out/<dosya>__pypdf_plain.md` — sistemde şu an kullanılan
- `out/<dosya>__inspector.md` — değerlendirilen aday

---

## Hata tanımları (referans — doldururken buraya bak)

| Hata türü | Ne demek | Örnek |
|---|---|---|
| **Okuma sırası bozukluğu** | Cümle başlıyor, ortasına başka sütundan/bloktan metin giriyor | `...we use a masked language [başka sütVun metni] model objective` |
| **Dipnot sızması** | Sayfa altındaki dipnot metni gövde paragrafının içine girmiş | `...the results showed [1. Smith et al 2019] a significant...` |
| **Sayfa mobilyası sızması** | Dergi adı, sayfa numarası, üst/alt bilgi gövde metnine karışmış | `original reportsSybil: A Validated...` |
| **Bölünmüş kelime** | Kelime ortasından boşlukla ikiye ayrılmış | `informa tion` |
| **Birleşmemiş tireleme** | Satır sonu tiresi birleştirilmemiş | `evalu- ation` |
| **Ligatür** | `ﬁ ﬂ ﬀ` tek karakter olarak kalmış, normal harflere çevrilmemiş | `ofﬁcial`, `ﬁne-tuned` |
| **Çapraz referans boşluğu** | "Figure 1" gibi referanslarda boşluk kaybolmuş | `Figure1will` |
| **Kayıp içerik** | PDF'te olan bir paragraf/bölüm çıktıda yok | — |
| **Tekrarlanmış içerik** | Aynı paragraf iki kez çıkmış | — |
| **Tablo çözülmesi** | Sayı, satır/sütun etiketinden kopmuş; hangi hücreye ait belirsiz | — |
| **Uydurma başlık** | Başlık olmayan metin `#` ile işaretlenmiş | `### AB C` (şekil etiketi) |
| **Kaçırılan başlık** | Gerçek bölüm başlığı işaretlenmemiş | `REFERENCES` başlık olarak çıkmamış |
| **Bozuk karakter** | Türkçe karakter, matematik sembolü veya benzeri bozulmuş | `Kaynak?a` |

**Hata sayılmaz:** fazladan boş satır · girinti farkı · madde işareti stili ·
taranmış dosyada metin çıkmaması · Markdown biçim tercihleri (kalın/italik/bağlantı)

**Sayarken:** iki parser için de **aynı sayfa aralığını** kullan. inspector'ın kusurlarını da
aynı titizlikle say — tabloda inspector sütunu hep 0 çıkarsa rapor taraflı görünür.
Emin olamadığın şeye `?` yaz, sonra karar ver.

---

# 1. sybil_tip_2sutun.pdf

- Sayfa sayısı: 17
- Üretici yazılım: Arbortext Advanced Print Publisher + Acrobat Distiller (LaTeX **değil**)
- İnceleme: 2026-08-13, tüm belge

**Bu dosya korpusun en kötü sonucunu veriyor.** bert ve turkce'de ayrı ayrı görülen kusurların
neredeyse tamamı burada bir arada ve daha yoğun.

## 1.1 bert / turkce ile AYNI çıkanlar

- **Ligatür:** inspector 0, pypdf 63. inspector kazanıyor, fark yok.
- **Birleşmemiş tireleme:** her iki parser da satır sonu tiresini birleştirmiyor
  (`in- stance`, `pro- cesses`, `repre- senting`). Fark yok.
- **Görseller:** ikisi de görseli atıyor, sadece içindeki metni gövdeye gömüyor. Şekil 2'nin
  eksen etiketleri (`0.75`, `Year 1 (AUC = 0.92)`) düz metin olarak akışa karışıyor.
- **Tablo cümle arasına giriyor:** tablo/şekil bir paragrafın ortasına denk geldiğinde ikisi de
  cümleyi tamamlamadan araya alıyor. bert ve turkce'deki ile aynı davranış.

## 1.2 bert / turkce'den FARKLI, daha ağır çıkanlar

### A. Sayfa mobilyası gövde metnine giriyor — 13 / 17 sayfa, ama hepsi aynı ağırlıkta değil

Ölçüm (dergi künyesi + sayfa altbilgisi + "Downloaded from…" satırları):

| | Saf altbilgi satırı | Gövde satırına karışmış |
|---|---:|---:|
| pypdf | 43 | **0** |
| inspector | 30 | 20 (13 sayfada) |

*(pypdf'te bulunan tek "karışık" satır `J Clin Oncol 41:2191-2200. © 2023 by ASCO` — bu
makalenin kendi künye satırı, hata değil. Sayıya katılmadı.)*

**20 vakanın kırılımı — etkilerine göre:**

| Nereye düşmüş | Adet | Sayfalar | Etki |
|---|---:|---|---|
| Kelimenin ortasına | 1 | s.4 | **Kademe 1** — alıntı eşleşmez |
| Cümlenin ortasına | 3 | s.7, s.13 | **Kademe 1** — alıntı eşleşmez |
| Tablo hücresinin içine | 6 | s.6, s.13, s.14, s.17 | Kademe 2 — tablo hücresi kirlenmiş |
| İki blok arasına | 10 | s.1, 2, 3, 8, 9, 10, 12, 14 | Kademe 3 — akışı bozuyor, cümle bölmüyor |

Ayrıca mobilya **kendi satırında olduğu hâlde** bir cümleyi ikiye bölen 3 vaka daha var
(s.4 ve s.8'de iki kez). Bunları da sayarsak **cümle bütünlüğünü bozan toplam 7 vaka.**
pypdf'te bu türden **0** vaka var.

**Örnek — s.4, kelimenin ortası (en ağır):**
```
inspector:  ... LDCTs that fit neither the true-positive nor true-
            Copyright © 2026 American Society of Clinical Oncology. All rights reserved.
            negative definition were excluded ...
```

**Örnek — s.2, cümlenin ortası (senin bulduğun):**
```
inspector:  ... LDCTs from participants included in the
            2192 © 2023 by American Society of Clinical Oncology     ← araya girmiş
            Ardila et al²⁸ test set were assigned to our test set ...

pypdf:      ... LDCTs from participants included in the
            Ardila et al 18 test set were assigned to our test set ...   ← bütün
```

**Örnek — s.13/s.14, tablo hücresi (daha hafif):**
```
inspector:  |. 100 Copyright © 2026 American Society of Clinical Oncology. All rights
            reserved.|1,670 (5.9)|142 (9.8)|447 (6.5)|...
```
Burada cümle bölünmüyor; altbilgi bir tablo hücresinin içine giriyor. Sayısal veri
bozulmuyor ama hücre metni kirleniyor.

> **Kademe 1 olan 7 vaka:** s.2, s.4 (×2), s.7, s.8 (×2), s.13.
> Diğer 13'ü Kademe 2–3.

### B. Sütun karışması — s.3 (senin tespitin, doğrulandı ve daha kötü)

pypdf s.3 tamamen düzgün, tek sütun akışı bozulmamış. inspector'da tek bir cümle **üç parçaya
bölünmüş, sırası bozulmuş ve bir parçası başlığa çevrilmiş**:

Orijinal cümle:
> To assess Sybil's performance, we computed Uno's concordance (C)–index²⁷ and area under the
> receiver operating characteristic (ROC) curve for each year…

inspector çıktısı (satır sırasıyla):
```
satır 32:  Fig A1, online only). A detailed description of data cordance (C)–index²⁷
satır 38:  #### and area under the receiver operating        ← cümle parçası, BAŞLIK olmuş
satır 47:  To assess Sybil's performance, we computed Uno'scon-
```
Cümlenin başı 47. satırda, ortası 32. satırda, sonu 38. satırda ve **`####`** etiketli
*(düzeltildi — önceki sürümde `##` yazıyordu; `process_pdf()` çıktısında `##` ile
başlayan 1 satır var, `####` ile başlayan 13)*.
Ayrıca 32. satırda sol sütundan gelen `…description of data` ile sağ sütundan gelen
`cordance (C)–index` birbirine yapışmış.

> **Seviye neden önemli:** `passages.py:_sections()` bölüm yolunu başlık
> **seviyesine** göre iç içe geçiriyor. `####` bir cümle parçası, üstünde `##`/`###`
> bir ana bölüm olmadığı için doğrudan kök seviyeye asılıyor ve o sayfadaki bütün
> pasajların `section_path`'ini kirletiyor.

Aynı sayfada FIG 1 açıklaması da ikiye bölünmüş: sonu (`National Lung Screening Trial.`)
24. satırda, başı 40–41. satırda.

> **Kademe 1.** turkce_makale'de gördüğümüz sütun karışmasının aynısı — ve bu da LaTeX
> olmayan bir dosya (Arbortext). Hipotezi destekliyor.

### C. Büyük harfli bölüm başlıkları — inspector pypdf'ten **geride**

Makalede insan gözüne başlık olarak görünen 12 büyük harfli bölüm başlığı var. Her ikisinde de
nasıl çıktıklarını tek tek kontrol ettim:

| Başlık | pypdf | inspector |
|---|---|---|
| `INTRODUCTION` | kendi satırında | kendi satırında |
| `MATERIALS AND METHODS` | kendi satırında | **`####` markdown başlık** |
| `RESULTS` | kendi satırında | kendi satırında |
| `DISCUSSION` | kendi satırında | kendi satırında |
| `AFFILIATIONS` | kendi satırında | gövdeye yapışık |
| `CORRESPONDING AUTHOR` | kendi satırında | gövdeye yapışık |
| `EQUAL CONTRIBUTION` | kendi satırında | kendi satırında |
| `SUPPORT` | kendi satırında | **paragraf ortasına gömülü** |
| `DATA SHARING STATEMENT` | kendi satırında | gövdeye yapışık |
| `AUTHOR CONTRIBUTIONS` | kendi satırında | gövdeye yapışık |
| `ACKNOWLEDGMENT` | kendi satırında | **paragraf ortasına gömülü** |
| `REFERENCES` | kendi satırında | kendi satırında |

**Özet:**

| | markdown başlık | kendi satırında | gövdeye yapışık | paragraf içine gömülü |
|---|---:|---:|---:|---:|
| pypdf | 0 | **12** | 0 | 0 |
| inspector | 1 | 5 | 4 | 2 |

Bu iki sonucu doğurur:

**1) Kaynakça kapısı bu dosyada hiç çalışmıyor.** `olcumler.md` §4'te sybil, inspector kapısı
**0** olan tek dosya. Sebebi bu — `REFERENCES` markdown başlığı olarak çıkmadığı için
`_sections()` `section_path` üretmiyor, `is_non_evidence_section()` tetiklenmiyor,
**kaynakça iddiaları kanıt olarak kabul edilebilir hâle geliyor.**

**2) Basit bir düzeltme kuralı bile inspector'da işe yaramaz.** "Satır başındaki büyük harfli
kısa satırı başlık say" gibi bir sonradan-düzeltme heuristiği pypdf'ten **12/12** başlığı
kurtarır, inspector'dan yalnızca **5/12**. Yani inspector'ın çıktısı bu yönden pypdf'ten daha
zor onarılır.

Somut örnekler (s.9):
```
pypdf:      AFFILIATIONS
            1Department of Electrical Engineering and Computer Science,
            Massachusetts Institute of Technology, Cambridge, MA

inspector:  AFFILIATIONS 1 Department of Electrical Engineering and Computer Science,
            Massachusetts Institute of Technology, Cambridge, MA 2 Jameel Clinic, ...
```
```
pypdf:      SUPPORT
            Supported by the Bridge Project, a partnership between ...

inspector:  ... contributed equally to this work as joint senior authors. SUPPORT Supported
            by the Bridge Project, a partnership between ...
```

> **Kademe 1 — raporun en önemli maddesi.** inspector'ın diğer 7 dosyada sağladığı tek gerçek
> kazanım (kaynakça kapısı) burada çalışmıyor; üstelik başlık bilgisi pypdf'te korunmuşken
> inspector'da silinmiş oluyor.

### C-2. `AUTHOR CONTRIBUTIONS` bölümü karışmış (s.9, yalnızca inspector)

```
pypdf (doğru):
  Conception and design: Peter G. Mikhael, Jeremy Wohlwend, Adam Yala,
  Lecia V. Sequist, Florian J. Fintelmann, Regina Barzilay
  Financial support: Lecia V. Sequist, Florian J. Fintelmann, Regina Barzilay
  Administrative support: PuiYee Chan, Gigin Lin, Lecia V. Sequist, Florian
  J. Fintelmann
  Provision of study materials or patients: Angelo K. Takigami, ...

inspector (karışık):
  AUTHOR CONTRIBUTIONS Conception and design: ... Financial support: Lecia V. Sequist, Floria
  J. Fintelmann                                        ← sahipsiz parça
  PuiYee Chan, Gigin Lin, Lecia V. Sequist, Florian    ← "Administrative support:" etiketi yok
  Provision of study materials or patients: ...
  J. Fintelmann Data analysis and interpretation: Adam Yala, ...
  Peter G. Mikhael, Jeremy Wohlwend,                   ← sahipsiz parça
```
`Administrative support:` etiketi tamamen kaybolmuş, yazar adları yanlış katkı türlerine
bağlanmış. Aynı sayfada sütun karışmasının ikinci örneği.

> **Kademe 1.** Yanlış atıf üretebilecek türde bir bozulma.

### D. Uydurma başlık oranı korpusun en yükseği

18 başlığın 8'i uydurma (%44). bert'te 8/43 (%19), turkce'de 3/13 (%23) idi.

Uydurma olanlar:
- `original reportsSybil: A Validated Deep Learning Model to` — sayfa üstü künyesi
  ("original reports") makale başlığına yapışmış, başlık ayrıca ikiye bölünmüş
- `Predict Future Lung Cancer Risk From a Single Low-Dose Chest Computed Tomography` — aynı
  başlığın ikinci yarısı, ayrı `#` olarak
- `model and annotations are publicly available.` — abstract'ın son cümlesinin kuyruğu
- `and area under the receiver operating` — B maddesindeki cümle parçası
- `prospective clinical trials.` — cümle kuyruğu
- `AB C` · `AB CD` · `EF GH` — şekil panel harfleri

`AB C` · `AB CD` · `EF GH` **gözle doğrulandı:** PDF'te şeklin içindeki panel harfleri
(A, B, C…). Metin değil, görsel etiketi. Uydurma başlık sayılır.

Gerçek olanlar (10): `MATERIALS AND METHODS`, `NLST Data`, `NLST Training, Development, and
Test Sets`, `Independent External Validation Data Sets`, `Algorithm Development`,
`Future Lung Cancer Prediction` (×2), `Additional Analyses` (×2),
`Examples of Clinical Application`.

**Tekrarlar gözle doğrulandı:** `Future Lung Cancer Prediction` ve `Additional Analyses`
PDF'te gerçekten ikişer kez var — biri Methods, biri Results altında. Tekrarlanmış içerik
hatası **değil**, JCO düzeninin normali. inspector burada doğru davranmış.

> Ama şu ayrı bir sorun: bu ikisi `####` (seviye 4) olarak etiketlenmiş; üst bölümleri olan
> `RESULTS` ve `DISCUSSION` hiç başlık olmadığı için ikisi de aynı `section_path` altına
> düşüyor. Yani sistem "Methods'taki Additional Analyses" ile "Results'taki Additional
> Analyses"i ayırt edemez.

### D-2. Tablo yapısı bozuk — **hücre eşleşmesi güvenilmez** (yalnızca inspector)

Gözle doğrulandı. TABLE 1, makalenin ana sonuç tablosu (yıl bazında AUC değerleri).

**Orijinal PDF:** 3 satır (NLST / MGH / CGMH) × 7 sütun (1–6 yıl AUC + C-index).

**pypdf (yapı yok, ama sıra doğru):**
```
NLST 0.92 (0.88 to 0.95) 0.86 (0.82 to 0.90) 0.80 (0.77 to 0.84) 0.77 (0.73 to 0.81) ...
MGH  0.86 (0.82 to 0.90) 0.82 (0.77 to 0.86) 0.79 (0.75 to 0.84) 0.79 (0.74 to 0.83) ...
CGMH 0.94 (0.91 to 1.00) 0.87 (0.81 to 0.95) 0.81 (0.75 to 0.88) 0.79 (0.73 to 0.87) ...
```
Boru işareti yok, ama her satır bir veri setine ait ve değerler soldan sağa doğru sırada.
Hangi değerin hangi yıla ait olduğu okuma sırasından çıkarılabilir.

**inspector (yapı var, ama yanlış):** tablo **üç ayrı bloğa** bölünmüş —
```
blok 1 (4 sütun başlık):
  |Data Set 1-Year Risk...|2-Year Risk...|3-Year Risk...|4-Year Risk... 5-Year Risk...|
  |NLST|0.92 (0.88 to 0.95) 0.86 (0.82 to 0.90)|0.80 (0.77 to 0.84)|0.77 ... 0.75 ...|
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 1. ve 2. yıl aynı hücrede

blok 2 (6 sütun — başlığı yok):
  |MGH|0.86 (0.82 to 0.90)|0.82 (0.77 to 0.86)|0.79 ...|0.79 ...|0.78 ...|
  |CGMH|0.94 (0.91 to 1.00)|0.87 (0.81 to 0.95)|0.81 ...|0.79 ...|0.77 ...|

blok 3 (satır etiketleri kaybolmuş):
  ||6-Year Risk, AUC (95% CI)|C-Index (95% CI)|
  ||0.75 (0.72 to 0.78) NA 0.74 (0.66 to 0.81)|0.75 (0.72 to 0.78) 0.81 (...) 0.80 (...)|
     ^^^^ üç veri setinin 6 yıllık değeri tek hücrede, NLST/MGH/CGMH etiketleri yok
```

Yani:
- Başlık satırı 4 sütun ilan ediyor, veri satırları 6 sütun içeriyor
- 1. ve 2. yıl değerleri aynı hücreye sıkışmış
- 6 yıllık AUC ve C-index değerleri satır etiketlerinden kopmuş — hangi değerin NLST'ye,
  hangisinin MGH'ye ait olduğu çıkarılamıyor

TABLE 2 daha kötü: **altı ayrı bloğa** bölünmüş, aralarda sahipsiz hücreler
(`|13,18,20|||||`) ve bir sayfa altbilgisi tablo hücresinin içine girmiş.

> **Kademe 1 — ve pypdf'ten daha tehlikeli.** pypdf tablo yapısı üretmiyor; sonuç
> yapısız ama yanıltıcı değil. inspector **kendinden emin ama yanlış** bir yapı üretiyor:
> markdown tablosu olarak okunabilir görünüyor, hücre eşleşmesi hatalı. Kanıta dayalı bir
> sistemde yanlış yapı, yapısızlıktan daha risklidir — bir AUC değeri yanlış veri setine
> atfedilebilir.

### E. Kaynakça listesi parçalanmış (yalnızca inspector)

```
inspector:
  satır 338:  395-409, 2011                    ← 1 numaralı kaynağın DEVAMI
  satır 340:  JAMA 325:962-970, 2021           ← 2 numaralı kaynağın DEVAMI
  ...
  satır 346:  1. The National Lung Screening Trial Research Team: ... N Engl J Med 365:
  satır 347:  2. US Preventive Services Task Force, ... recommendation statement.

pypdf:
  satır 786:  1. The National Lung Screening Trial Research Team: ... N Engl J Med 365:
  satır 787:  395-409, 2011                    ← doğru yerde
  satır 788:  2. US Preventive Services Task Force, ... recommendation statement.
  satır 789:  JAMA 325:962-970, 2021           ← doğru yerde
```

Kaynakçadaki ikinci sütun parçaları, ait oldukları girdilerin **8 satır öncesine** taşınmış.
pypdf'te sorun yok. turkce_makale'de gördüğün kaynakça bozukluğunun aynısı.

### F. CONTEXT kutusu (mavi kutu) — **düzeltme: bunu ikisi de bozuyor**

Sen "inspector bozdu" dedin; kontrol ettim, **pypdf de aynı yerde bozuyor**:

```
pypdf s.2:   ... at CGMH, any adult
             CONTEXT / Key Objective / ... (kutu tamamı)
             (devamı s.3'te: "without a personal cancer history can obtain an LDCT")

inspector:   ... Others showed improved risk
             CONTEXT / Key Objective ... (kutu)
             predictions when combining PLCOm2012 ...
```
İkisi de kutuyu bir cümlenin ortasına yerleştiriyor. **Hata ikisinde de var.**

**Gerçek fark, kutunun İÇİ:**

| | Kutu içi alt başlıklar |
|---|---|
| pypdf | `CONTEXT` / `Key Objective` / `Knowledge Generated` / `Relevance (T.E. Stinchcombe)` — dördü de ayrı satırda korunmuş |
| inspector | `CONTEXT` ayrı, ama diğer **üçü tek bir paragrafa eritilmiş**; alt başlıklar cümle içinde kaybolmuş |

Yani senin "context içindeki başlıkları tespit etmemiş" gözlemin doğru — üstelik pypdf'ten geri.

### G. Üst simge (dipnot işareti) — inspector'ın avantajı, burada net görünüyor

Bu, "dipnotu ayrı token olarak koyduğunu nereden biliyorsun" sorusunun somut cevabı:

- inspector 15 adet **gerçek Unicode üst simge karakteri** üretiyor (`²⁷`, `⁵`, `²⁸` — U+2070–U+2079)
- pypdf 0 adet; hepsini normal rakam olarak yazıyor

Ayrıca yerleşim de farklı — s.1:
```
inspector:  ... National Lung Screening Trial (NLST) 1 and the NELSON trial ...   ← doğru yer
pypdf:      ... National Lung Screening Trial (NLST)
            and the NELSON trial, respectively.
            1 Hence, the US ...                                        ← yanlış yere kaymış
```
pypdf dipnot numarasını bir sonraki cümlenin başına taşıyor. inspector doğru yerde bırakıyor.

> Bu, inspector'ın sybil'deki tek net üstünlüğü.

## 1.3 Entegrasyon notu — sayfa numarası tabanı

`extract_pages_markdown()` sayfaları **0'dan** numaralandırıyor (`min=0, max=16`), pypdf ve PDF
okuyucular 1'den. Karşılaştırma yaparken bu kaydırma hesaba katılmalı; `hizala.py` ve
`compare.py` bunu tolere ediyor ama entegrasyonda atlanırsa tüm sayfa referansları bir kayar.

## 1.4 Sybil özeti

| Kusur | pypdf | inspector | Kazanan |
|---|---|---|---|
| Mobilyanın cümleyi bölmesi | 0 | **7 vaka** | pypdf |
| Mobilyanın gövde satırına karışması (toplam) | 0 | 20 vaka / 13 sayfa | pypdf |
| Sütun karışması | yok | s.3, s.9 | pypdf |
| Kaynakça listesi bütünlüğü | bozulmamış | parçalanmış | pypdf |
| Büyük harfli bölüm başlığı kurtarılabilirliği | **12 / 12** | 6 / 12 | pypdf |
| `REFERENCES` başlığı → kaynakça kapısı | çalışmıyor | **çalışmıyor** | berabere (ikisi de başarısız) |
| `AUTHOR CONTRIBUTIONS` bütünlüğü | doğru | etiket kaybı + karışma | pypdf |
| Tablo hücre eşleşmesi | yapı yok, sıra doğru | yapı var, eşleşme yanlış | pypdf |
| Uydurma başlık | — (hiç başlık yok) | 8 / 18 (%44) | — |
| Bozuk karakter | 0 | 0 | berabere |
| Tekrarlanmış içerik | 0 | 0 | berabere |
| Çapraz referans boşluğu | 0 | 0 | berabere |
| Kayıp içerik | — | yok (+%1,0 karakter) | berabere |
| CONTEXT kutusu yerleşimi | bozuk | bozuk | berabere |
| CONTEXT kutusu alt başlıkları | korunmuş | eritilmiş | pypdf |
| Ligatür | 63 | **0** | inspector |
| Üst simge / dipnot yerleşimi | yanlış yerde, düz rakam | doğru yerde, üst simge | inspector |
| Hız | 0,272 sn | **0,039 sn** | inspector |

**Sonuç:** bert'te inspector açık ara öndeydi, turkce'de başa baştı, sybil'de **pypdf önde**.
Ayırt edici değişken üretici yazılım gibi görünüyor: LaTeX ile dizilmiş dosyalarda inspector
kazanıyor, DTP yazılımıyla dizilmiş dosyalarda (InDesign / Arbortext) kaybediyor.

---

# 2. bert_2sutun_dipnot.pdf

- Sayfa sayısı: 16
- İncelenen sayfalar: 1–16 (tam belge taraması), ayrıntılı inceleme s.1, s.3, s.4, s.6, s.14
- İnceleme tarihi: 2026-08-12

Kaynak etiketleri: **(ö)** = otomatik ölçüm · **(g)** = gözle inceleme · **(a)** = henüz açık

## 2.1 Kusur durumu

| Hata türü | pypdf | inspector | Kaynak | Kademe |
|---|---|---|---|---|
| Okuma sırası bozukluğu | **Yok** — cümleler bütün | **Yok** — cümleler bütün | (g) | 1 |
| Dipnot sızması / ayrımı | **Ayırmıyor** — dipnot metni sayfa sonunda gövde akışına giriyor | **Ayırmıyor** — aynı | (g) | 1 |
| Tablo çözülmesi | **Var** — sütun başlıkları ve sayılar ayrışıyor | **Yok** — `\|` ile sütun yapısı korunuyor | (g) | 1 |
| Kaçırılan başlık (References) | Hiç gerçek başlık yok, sadece `# Page N` | `References` yakalandı, kapı tetikleniyor | (ö) | 1 |
| Ligatür | **157** | **0** | (ö) | 2 |
| Şekil içi yazı gömülmesi | **Var** | **Var** | (g) | 2 |
| Sayfa mobilyası (arXiv damgası) | **Var** (1 kez) | **Var** (1 kez) | (g) | 2 |
| Uydurma başlık | — (başlık üretmiyor) | **8 / 43** (isabet ~%81) | (g) | 2 |
| Bölünmüş başlık | — | **Var** — 3 adet (`Language Understanding"`, `Tasks`, `Benchmark Experiments.`) | (g) | 2 |
| Görsel işleme | Yok | Yok | (ö) | — |
| Çapraz referans boşluğu | **1** | **27** | (ö) | 3 |
| Birleşmemiş tireleme | **Var** — satır sonunda (`repre-` / `sentation`) | **Var** — satır içinde (`representa- tion`) | (g)+(ö) | 3 |
| Dipnot işareti yapışması | **1 gerçek** (`leaderboard10`) | **0** | (ö) | 3 |
| Bozuk karakter | Yok | Yok | (ö) | — |
| Kayıp içerik | Yok (karakter sayısı benzer) | Yok | (ö) | 1 |

### Çapraz referans ayrıntısı (ö)

| Kelime | pypdf doğru / bitişik | inspector doğru / bitişik |
|---|---|---|
| `Figure` | 14 / **0** | 5 / **9** |
| `Table` | 17 / **1** | 8 / **10** |
| `Section` | 8 / **0** | 0 / **8** |

inspector `Table`'ı yarı yarıya doğru yazıyor, `Section`'da istisnasız bitişik yazıyor.

## 2.2 Cevaplanan sorular

**S1. Dipnot işareti sayımı inspector'da neden 8 kat yüksekti (3 → 24)?**

> **Ölçüm artefaktıydı.** Kullanılan regex `Figure1`, `Table1` gibi çapraz referansları da
> yakalıyordu; bunlar zaten ayrı kategoride sayılıyordu. Desen düzeltilip çapraz referans
> kelimeleri hariç tutulunca gerçek durum ortaya çıktı: pypdf 2 aday (1'i gerçek dipnot
> yapışması: `leaderboard10`), inspector 1 aday (o da `CVPR09`, hata değil).
> **Sonuç: gerçek dipnot işareti yapışmasında pypdf 1, inspector 0. Fark kayda değer değil.**

**S2. Sayfa 7'de üç kusur bir arada (pypdf)**

> `On the ofﬁcial GLUE leaderboard10, BERTLARGE obtains` — ligatür (`ofﬁcial`) +
> dipnot işareti yapışması (`leaderboard10`) + alt simge yapışması (`BERTLARGE`).
> inspector aynı yeri Markdown bağlantısına çevirmiş, ligatür üretmemiş.

**S3. Sayfa 3'te inspector kusuru — `Figure1will`**

> Tekrarlıyor. `Figure` 9/14, `Table` 10/18, `Section` 8/8 bitişik.
> Daha kötü bir örnek de var: `Section5.1that` — üç token birleşmiş.
> Sebebi tasarımsal: inspector satırları birleştirip akıcı metin üretiyor ve birleştirme
> noktasında boşluğu düşürüyor. pypdf satır sonlarını koruduğu için bu sorunu yaşamıyor.

**S4. Okuma sırası — asıl şikâyet konusu**

> İki sütunlu sayfalarda **her iki parser da cümleleri bütün bırakıyor.** Sütun karışması
> gözlenmedi. Yani "paragraflar karışıyor" şikâyetinin bu bileşeni mevcut sistemde de yok.

**S5. Dipnot ayrımı — asıl şikâyetin gerçek kaynağı**

> **Hiçbiri dipnotu gövdeden ayırmıyor.** İkisi de dipnot metnini sayfa bloğunun sonuna
> koyuyor; sayfalar birleştirilince dipnot metni iki gövde paragrafının arasına giriyor.
> Dipnot cümlesi sayfa sınırında yarım kalıyor ve devamı sonraki sayfanın dipnot alanında
> geliyor (örn. `...bidirectional Trans-` → sonraki sayfa).
>
> Biçim farkı: pypdf dipnot işaretini önceki kelimeye yapıştırıyor (`left.4`),
> inspector ayrı token olarak cümle içine koyuyor (` 5 `).
>
> **Olumlu nokta:** yerleşim tutarlı görünüyor (dipnot metni sayfa sonunda). Tutarlıysa
> sonradan filtrelenebilir ve inspector'ın `extract_pages_markdown()` sayfa bazlı API'si
> bu filtreyi yazmayı pypdf'in düz çıktısından kolaylaştırır.

## 2.3 Açık kalan

**A1. Dipnot yerleşimi her sayfada tutarlı mı?** (s.5, s.7, s.9 kontrol edilecek)
Sayfa 3'te sonda olduğu doğrulandı. Diğer sayfalarda da sonda mı, yoksa bazen paragraf
ortasına mı giriyor? Bu, "filtrelenebilir" önerisinin geçerliliğini belirler.

> Cevap: `______`

**A2. Başlık isabet oranı** — `out/basliklar_bert_2sutun_dipnot.txt` etiketlenecek.

> Cevap: `______`

## 2.4 Örnekler

### Örnek 1 — Ligatür (sayfa 1)
- **Orijinal PDF:** the pre-trained BERT model can be fine-tuned
- **pypdf:** `the pre-trained BERT model can be ﬁne-tuned`  ← `ﬁ` tek karakter (U+FB01)
- **inspector:** `fine-tuning`  ← normal harfler

### Örnek 2 — Birleşmemiş tireleme, iki farklı biçim (sayfa 1)
- **Orijinal PDF:** representation
- **pypdf:** `repre-` / satır sonu / `sentation`  ← satır atlıyor, tire duruyor
- **inspector:** `representa- tion`  ← satırı birleştiriyor ama tireyi silmiyor

### Örnek 3 — Çapraz referans boşluğu, inspector kusuru (sayfa 4)
- **Orijinal PDF:** we demonstrate in Section 5.1 that pre-training...
- **pypdf:** `Section 5.1 that`  ← doğru
- **inspector:** `Section5.1that`  ← üç token birleşmiş

### Örnek 4 — Tablo yapısı (SQuAD sonuçları)
- **Orijinal PDF:** System / Dev(EM,F1) / Test(EM,F1) sütunlu tablo
- **pypdf:**
  ```
  System Dev Test
  EM F1 EM F1
  Human - - 82.3 91.2
  ```
  ← sütun başlıkları ayrı satırlara düşmüş, 82.3'ün hangi metriğe ait olduğu belirsiz
- **inspector:** `|` ile sütun yapısı korunmuş, sayı-etiket ilişkisi ayakta

### Örnek 5 — Dipnot sayfa sınırında kesilmesi (sayfa 3 → 4)
- **Orijinal PDF:** 4. dipnot sayfa 3'ün altında başlıyor, sayfa 4'ün dipnot alanında devam ediyor
- **pypdf:**
  ```
  ...token can only attend to context to its left.4
  1https://github.com/tensorﬂow/tensor2tensor
  ...
  4We note that in the literature the bidirectional Trans-
  ```
  ← ardından sayfa 4'ün gövde metni başlıyor
- **inspector:** aynı davranış; dipnot metni sayfa sonunda, sonra sayfa 4 gövdesi

### Örnek 6 — Sayfa mobilyası (arXiv kenar damgası)
- **Orijinal PDF:** sol kenara dikey basılmış arXiv künyesi
- **pypdf:** `arXiv:1810.04805v2 [cs.CL] 24 May 2019` metin akışının arasına girmiş
- **inspector:** aynı; ayrıca bunu **başlık** olarak da işaretlemiş

## 2.5 Başlık isabeti

Toplam **43 başlık**. Uydurma olarak tespit edilen **8** başlık:

| # | Başlık | Sayfa | Tür |
|---|---|---|---|
| 1 | `Jacob Devlin Ming-Wei Chang` | 1 | Yazar adı |
| 2 | `Kenton Lee Kristina Toutanova` | 1 | Yazar adı |
| 3 | `arXiv:1810.04805v2 [cs.CL] 24 May 2019` | 1 | Kenar damgası (hem gövdeye sızmış hem başlık yapılmış) |
| 4 | `Input =` (×2) | 13 | Örnek kutusu içeriği |
| 5 | `Label =` (×2) | 13 | Örnek kutusu içeriği |
| 6 | `Language Understanding"` | 12 | **Bölünmüş** — `Appendix for "BERT: ...for` ile tek başlıktı |
| 7 | `Tasks` | 14 | **Bölünmüş** — `A.5 Illustrations of Fine-tuning on Different` ile tek başlıktı |
| 8 | `Benchmark Experiments.` | 14 | **Bölünmüş** — `B.1 Detailed Descriptions for the GLUE` ile tek başlıktı |

**Sınırda:** `Task #2: Next Sentence Prediction (NSP)` — makalede kalın satır içi etiket,
numaralı bölüm değil. İlgili tutarsızlık: `Task #1: Masked LM` başlık yapılmamış, kalın
bırakılmış.

- Gerçek: **35**
- Uydurma: **8** (3'ü tek bir mekanizmadan: iki satıra taşan başlığın ikiye bölünmesi)
- **İsabet oranı: 35 / 43 ≈ %81**

Karşılaştırma için: pypdf **0** gerçek bölüm başlığı üretiyor (yalnız `# Page N`).
Doğru ifade "inspector 8 uydurma başlık üretiyor" değil, **"inspector 43 başlığın 35'ini
doğru buluyor, pypdf hiç bulmuyor; uydurma başlıklar bu kazancın yan etkisidir."**

### API farkı — raporda belirtilmeli

İki farklı pdf-inspector API'si farklı başlık sayısı veriyor:

| API | Başlık sayısı |
|---|---|
| `process_pdf()` | 42 |
| `extract_pages_markdown()` | 44 |

Başlık sayısı raporlanırken hangi API'nin kullanıldığı belirtilmelidir.

## 2.6 Serbest notlar

- inspector'ın çapraz referans kusuru ile satır birleştirme kazancı aynı mekanizmadan
  doğuyor: satırları birleştirdiği için hem akıcı metin üretiyor hem de boşluk düşürüyor.
- `bolunmus_kelime` metriği `compare.py` yeniden yazılırken düştüğü için sayısal veri yok;
  gözle de sistematik bir bölünmüş kelime sorunu gözlenmedi.
- Otomatik `sayfa_mobilyasi` sayacı bert için 0/0 verdi, çünkü sayaç yalnız 3+ sayfada
  tekrar eden satırları arıyor. arXiv damgası bir kez geçtiği için yakalanamadı, elle
  tespit edildi. Bu, sayacın sınırıdır.

### Görsel işleme

Her iki parser da yalnızca metin çıkarır:

- pdf-inspector'ın API'sinde görselle ilgili hiçbir fonksiyon yok; markdown çıktısında
  `![...]` görsel sözdizimi hiç üretilmiyor (görsel ağırlıklı iki dosyada da 0).
- pypdf'in `extract_text()` fonksiyonu görselleri atlıyor. (pypdf'in ayrı bir `page.images`
  API'si var — `gpt4_uzun_gorsel` dosyasında 10 gömülü görsel buldu — ancak
  research-platform bunu kullanmıyor.)
- `resnet_2sutun_gorsel` dosyasında gömülü raster görsel sayısı 0 çıktı; şekiller vektör
  çizim olarak gömülü, dolayısıyla hiçbir raster çıkarıcı onları bulamaz.

**Entegrasyon açısından önemli:** research-platform'da şekil analizi `figure_analysis.py`
içinde PyMuPDF (`fitz`) ve yerel bir görsel modeli ile **ayrı bir hat** üzerinden yürüyor.
Bu hat `acquisition.py`'deki metin çıkarma yolundan bağımsızdır, dolayısıyla
pypdf → pdf-inspector değişimi görsel işlemeye dokunmaz.

Buna karşılık şekil **içi** etiket metinleri her iki parser'da da metin akışına karışıyor ve
şekil bağlamı olmadan anlamsız pasajlar üretiyor. Bu, parser değişimiyle çözülmeyen ortak
bir kusurdur; çözümü sonradan filtrelemedir.

`is_complex_layout` bayrağı her iki görsel ağırlıklı dosyada da `True` döndü. Bu sinyal
entegrasyonda karmaşık düzenli sayfalardan gelen pasajlara temkinli davranmak için
kullanılabilir.

### pdf-inspector'ın iddiaları — karşılama durumu

| İddia | Durum |
|---|---|
| Sınıflandırma (text/scanned/image/mixed) + güven + sayfa bazlı OCR yönlendirme | Karşılıyor |
| Metin tabanlı PDF'ler için <200 ms | Aşıyor (21–132 ms) |
| Konum farkındalıklı çıkarma, çok sütunlu okuma sırası | Karşılıyor |
| Markdown dönüşümü (başlık, liste, tablo, biçim) | Büyük ölçüde — başlık isabeti %81 |
| Tablo tespiti | Karşılıyor |
| CID font / kodlama desteği | Karşılıyor |
| "...footnotes..." (tablo tespiti maddesi içinde) | **Karşılamıyor** — belge dipnotları gövdeden ayrılmıyor. Not: ifade tablo dipnotlarını kastediyor olabilir, belirsiz |
| Bozuk kodlama tespiti | Test edilmedi (korpusta uygun dosya yok) |
| "%54 PDF için OCR servisini atlayın" | Kapsam dışı (bu hatta OCR servisi yok) |

---

# 3. turkce_makale.pdf

- Sayfa sayısı: 6 · İki sütunlu dergi makalesi (Research in Sports Science, 2019)
- İncelenen sayfalar: 1–6 (tam belge)
- İnceleme tarihi: 2026-08-12

## 3.1 bert ile aynı çıkanlar

- Her ikisi de tabloyu cümlelerin arasına alıyor (Tablo 7 dahil).
- Her ikisi de dergi künyesini metne alıyor (`Research in Sports Science 2019; 9(1); 5-10`,
  `Demirel ve ark. Muay-Thai Hakemleri`). bert'te bu arXiv kenar damgasıydı.
- pypdf yine hiç gerçek bölüm başlığı üretmiyor, sadece `# Page N`.
- inspector yine gerçek bölüm başlıklarını buluyor ve `Kaynakça` ile kaynakça kapısını
  tetikliyor.
- inspector yine daha hızlı: 6,3× (0,133 sn → 0,021 sn). bert'te 7,1×.
- Her ikisi de görsel işlemiyor.
- Her ikisi de Türkçe karakterleri koruyor: 1765 = 1765, bozuk kodlama bayrağı temiz.

## 3.2 bert'ten FARKLI çıkanlar

**Sütun okuma sırası — en ciddi bulgu**

inspector 6 sayfanın **3'ünde** sütunları satır satır birbirine geçiriyor. pypdf hepsinde
doğru okuyor. bert'te her ikisi de sorunsuzdu.

| Sayfa | Durum |
|---|---|
| s.1 | **Sütun karışması** |
| s.2 | Temiz |
| s.3 | Neredeyse tamamı tablo — ayrı sorun (aşağıda) |
| s.4 | **Sütun karışması** |
| s.5 | Temiz |
| s.6 | **Sütun karışması** (kaynakça) |

Örnek (s.4) — sol ve sağ sütun satır satır iç içe girmiş:

```
0.05 düzeyinde anlamlı farklılık ortaya çıkmıştır. Göksel ve ark.
Tablo 6'da Katılımcıların hakemlik kademelerine göre .05 anlamlı- Tarafından yapılan
çalışmada ise futbol hakemlerinde cinsiyete lık düzeyinde antrenörlüğe ilişkin karar
verme stillerinin belirlen- göre karar verme esnasında bocalama, sorumluluğu başkasına
mesi için yapılan Kruskal Wallis testi sonuçlarına göre,.05 düzeyin- yükleme, karar
geciktirme özellikleri cinsiye göre farklılık gös- de anlamlı farklılık ortaya çıkmamıştır.
termemiştir (Göksel ve ark. 2016).
```

Sütunlar sayfada görsel olarak apaçık ayrık; belirsizlik içermiyor.

Kaynakça sayfasında (s.6) da aynı davranış: `...Ankara: Savas Ya-` **Yılmaz, A., S. (2011).**
`Üniversite Öğrencilerinin... Özsay-` `yınları.` — `Savas Yayınları` ikiye bölünüp araya
başka bir kaynak girmiş.

**Tablolar — bert'in tersi**

- inspector yan yana duran tabloları **tek ızgaraya birleştiriyor**: s.3'te Tablo 1–4,
  s.4'te Tablo 5 ve Tablo 7.
- Tablo başlıkları bile tek satırda iç içe giriyor:
  `**Tablo 5.** Katılımcıların Refah Düzeylerine Göre Ölçek Puanlarının **Tablo 7.**
  Katılımcıların Hakemlik Yıllarına Göre Ölçek Puanlarının Dağılımı Dağılımı`
- Birleşik ızgarada Tablo 5'in sütunları (`Refah`, `Sıra Değer`) ile Tablo 7'nin sütunları
  (`Yaş`, `N Sıra Değer`) yan yana; hangi sayının hangi tabloya ait olduğu kayboluyor.
- **pypdf bu dosyada daha okunaklı:** `Karar Vermede Öz Saygı Normal 64 58.63 7.027 .172` —
  satır etiketi ve değerleri bir arada kalmış.
- Dergi künyesi s.3'te tablonun **ilk satırı** olmuş.

bert'teki SQuAD tablosunda inspector açık ara iyiydi. Yani tablo tespiti düzene bağlı:
metin genişliğini kaplayan tek tabloda başarılı, iki sütunlu sayfada yan yana duran
tablolarda başarısız.

**Ligatür avantajı bu dosyada yok**

Her ikisi de 0 — bu makalede ligatür bulunmuyor. bert'teki 157 → 0 kazancı belgeye bağlıdır.

**Yapı ağacı var ama işe yaramıyor**

749 eleman: 739 `Span`, 9 `P`, 1 `Figure`. `Table`, `TR`, `H1` gibi anlamlı rol yok.
6 sayfalık makalede 9 paragraf etiketi olması gerçek paragrafların işaretlenmediğini
gösteriyor. bert ve sybil'de yapı ağacı hiç yok (0 eleman).

**Sonuç:** etiket bulunması, kullanılabilir mantıksal yapı bulunması demek değil.

## 3.3 Sadece bu makalede çıkanlar

**Sayfa numaralarında inspector KAYBEDİYOR** *(düzeltildi — önceki sürümde tersi yazıyordu)*

Orijinalde sayfa numaraları bir sağa bir sola konumlanmış (altta ortalı değil).

- pypdf hepsini metne alıyor: her sayfada **tek başına bir satır** olarak `5`, `6`, `7`,
  `8`, `9`, `10`.
- inspector da **almıyor değil** — `<u>5</u>` biçiminde basıyor. Toplam 5 tane, ve
  **3'ü kelimenin ortasına giriyor**:

| bağlam | sonuç |
|---|---|
| `yönte-<u>5</u> miyle` | "yöntemiyle" ikiye bölünmüş |
| `içinde <u>6</u>etkin` | "etkin" kelimesine yapışmış |
| `*Football*<u>9</u> *Referees` | kaynakça girdisi bölünmüş |
| `\n\n<u>8</u>\n\n` | tek başına — zararsız |

**Sistem açısından bu pypdf'ten daha kötü.** pypdf'in ürettiği başıboş rakam kendi
satırında durduğu için basit bir kuralla temizlenebilir. inspector'ınki kelimenin
içinde olduğu için temizlenemez: `<u>` etiketini silsen "yönte5 miyle" kalır,
etiketle beraber silsen kelime yine bozuk kalır. Yani kusur **daha sinsi**.

Ölçüm: `out/turkce_makale__inspector.md` içinde `<u>\d+</u>` deseni 5 kez geçiyor,
tek başına satırda rakam 0 kez.

**Kaçırılan başlık**

`Giriş` başlık olarak işaretlenmemiş, kalın metin olarak kalmış.

**Uydurma başlık az**

13 başlığın 3'ü savunulamaz: `Research in`, `RISSSports Science`, `DOI: 10.5152/rss.2019.0002`
— dergi künyesi parçaları. `Orijinal Araştırma / Original Article` dergilerde gerçek bir
yapısal etiket olduğu için sahte sayılmadı. Gerisi (Özet, Abstract, Yöntem ve Araçlar,
Bulgular, Tartışma, Sonuç, Kaynakça, iki dilli başlık) gerçek.

**Tireleme artışı bağımsız bir kusur değil**

`sonuclar.csv`'de tireleme 36 → 70 görünüyor. Bu ayrı bir sorun değil, sütun karışmasının
sonucu: satır sonu tiresi yanlış devamla birleşiyor (`karar ver- Karar kelimesi`).
Raporda bağımsız kusur olarak sunulmamalı.

## 3.4 Ölçüm dışı — entegrasyon uyarısı

`pdf_inspector.extract_text()` fonksiyonu Türkçe karakterleri **siliyor**:

| API | Türkçe karakter |
|---|---:|
| `process_pdf()` | 1765 |
| `extract_pages_markdown()` | 1765 |
| `pypdf.extract_text()` | 1765 |
| **`pdf_inspector.extract_text()`** | **0** |

`Orijinal Araştırma` → `Orijinal Aratrma`. Karakterler değiştirilmiyor, atılıyor; uyarı
verilmiyor, `has_encoding_issues` bayrağı `False` kalıyor.

**Bu, bu çalışmada ölçülen çıktılarda görülmez** — karşılaştırmada `process_pdf()`
kullanıldı. Ancak entegrasyonda en bariz görünen fonksiyon `extract_text()` olduğu için
uyarı olarak kaydedilmiştir: **entegrasyonda `extract_text()` kullanılmamalıdır.**

---

# 4. vgg_tablo_agirlikli.pdf

- Sayfa sayısı: 14 · Tek sütun, tablo ağırlıklı (ICLR 2015 konferans makalesi)
- Üretici yazılım: dvips + Ghostscript (LaTeX zinciri)
- İnceleme tarihi: 2026-08-13

## 4.1 Önceki dosyalarla aynı çıkanlar

- Ligatür: inspector 0, pypdf 221. inspector kazanıyor.
- Birleşmemiş tireleme: ikisi de birleştirmiyor (51 / 52).
- Görsel: ikisi de atıyor, içindeki metni gövdeye gömüyor.
- Hız: 11,4× (0,477 sn → 0,042 sn) — korpustaki en yüksek oran.
- `REFERENCES` başlığı yakalanmış → **kaynakça kapısı çalışıyor.** (sybil'de çalışmıyordu)

## 4.2 Tekrarlanan sayfa damgası — burada inspector kazanıyor

`Published as a conference paper at ICLR 2015` damgası her sayfanın üstünde.

| | Damga kaç kez çıkmış |
|---|---:|
| pypdf | **14** (her sayfada bir kez, kendi satırında) |
| pdf-inspector | **1** (yalnızca belge başında) |

inspector tekrarı temizliyor. Bu, araştırma platformu için **istenen davranış** — aksi hâlde
14 adet gürültü satırı passage'lara karışır.

> **Ama tutarsız:** sybil'de aynı temizlik yapılmamış, `Downloaded from ascopubs.org…`
> damgası 17 sayfanın 17'sinde de duruyor. Yani tekrar temizleme davranışı belgeden belgeye
> değişiyor, güvenilir bir özellik olarak sayılamaz.

## 4.3 Numaralı alt bölüm başlıkları — hepsi gövdeye yapışmış

VGG makalesinde 13 numaralı alt bölüm başlığı var (`2.1 ARCHITECTURE` … `A.2 LOCALISATION
EXPERIMENTS`). **inspector hiçbirini başlık olarak çıkarmamış**, hepsini kendi paragrafının
ilk cümlesine yapıştırmış:

```
inspector:  2.1 ARCHITECTURE During training, the input to our ConvNets is a ...
            2.3 DISCUSSION Our ConvNet configurations are quite different fro...
            3.1 TRAINING The ConvNet training procedure generally follows Kri...
            4.5 COMPARISON WITH THE STATE OF THE ART Finally, we compare our ...

pypdf:      2.1 A RCHITECTURE
            During training, the input to our ConvNets is a fixed-size ...
```
pypdf'te küçük kapital dizgisinden gelen bir boşluk artefaktı var (`A RCHITECTURE`) ama
**satır kendi başına duruyor** — sonradan düzeltilebilir. inspector'da başlık bilgisi yok
olmuş.

*(Gözle doğrulandı: bu 13 satır PDF'te gerçekten başlık biçiminde — koyu, kendi satırında.)*

> Sybil'de gördüğümüz "başlık gövdeye yapışıyor" kusuru burada da var. **Ve bu bir LaTeX
> dosyası** — yani kusur üretici yazılımla açıklanamıyor (bkz. §5.2).

## 4.4 Uydurma başlıklar (3 / 14)

- `VERY DEEP CONVOLUTIONAL NETWORKS` + `FOR LARGE-SCALE IMAGE RECOGNITION` — tek makale
  başlığı ikiye bölünüp iki ayrı başlık olmuş (sybil'de de aynısı olmuştu)
- `Karen Simonyan` — yazar adı başlık sanılmış
- `arXiv:1409.1556v6 [cs.CV] 10 Apr 2015` — kenar damgası **`#` (seviye 1) başlık** olmuş

## 4.5 Tablo kusurları

Senin gözlemin: "bozukluklar var ama aşırı anlaşılmaz değil — tablolar karışık olmadığı için."
Doğrulandı; VGG'nin tabloları basit yapıda olduğu için sonuç sybil'den okunaklı, ama üç ayrı
kusur var:

**a) Tüm sütunlara yayılan satırlar bir hücreye sıkışmış.** Table 1'de `input (224 × 224 RGB
image)` ve `maxpool` satırları orijinalde tüm sütunları kaplar:
```
|11 weight|11 weight|13 weight|16 weight|16 weight|19 weight|
|layers|layers|layers input (224 × 224 RGB image)|layers|layers|layers|
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^ C sütununun hücresine girmiş
|conv3-64|conv3-64 LRN|conv3-64 conv3-64|conv3-64 conv3-64 maxpool|...|
                                          ^^^^^^^ maxpool satiri hucreye erimis
```

**b) Sütun adları kaybolmuş.** *(gözle doğrulandı)* Table 3–4'te değerlerin **sırası doğru**,
ama `top-1 val. error (%)` ve `top-5 val. error (%)` başlıkları düşmüş. Veri satırlarında
sayılar var, hangi metriğe ait olduğu yazmıyor:
```
|ConvNet config. (Table 1)|smallest image side||||     ← iki sutun adi bos
|A|256|256|29.6|10.4|                                  ← 29.6 ve 10.4 hangi metrik?
```

**c) Düz paragraf tabloya çevrilmiş — yeni kusur türü.** *(gözle doğrulandı: PDF'te burası
normal bir paragraf, tabloya benzeyen hiçbir öge yok.)* 2.3 DISCUSSION bölümündeki akan metin
keyfi kelime sınırlarından hücrelere bölünmüş:
```
inspector:
  |are significantly|less|deep than|ours, and|they did|not evaluate|on the large-scale|ILSVRC||
  |---|---|---|---|---|---|---|---|---|
  |dataset.|Goodfellow et al.|(2014)|applied|deep ConvNets|(11|weight layers)|to the task|of|
  |street number|recognition,|and|showed|that the increased|depth|led to better|performance.||

pypdf (doğru):
  are significantly less deep than ours, and they did not evaluate on the large-scale ILSVRC
  dataset. Goodfellow et al. (2014) applied deep ConvNets (11 weight layers) to the task of
  street number recognition, and showed that the increased depth led to better performance.
```
Korpusta bu türden 5 vaka var (attention 1, bert 2, gpt3 1, vgg 1). Diğer dördü şekil
içeriğinden geliyor; **vgg'deki tek net gövde paragrafı örneği.**

> **Kademe 1.** Paragraf artık paragraf değil; alıntı doğrulama eşleşme bulamaz.

---

# 5. Korpus geneli ölçümler

Tek belgeye değil, dokuz belgenin tamamına bakan ölçümler.

## 5.1 Tablo yapısı — kusur her dosyada var

inspector'ın ürettiği tüm markdown tablo bloklarında üç kusur arandı:

- **boş sütun adı:** başlık satırında en az bir hücre boş (sütun adı kaybolmuş)
- **sütun uyuşmazlığı:** veri satırının hücre sayısı, ayraç satırının ilan ettiği sütun
  sayısına eşit değil (değerler yanlış sütuna kayar)
- **birleşmiş başlık:** iki sütun adı tek hücrede toplanmış

| Dosya | Tablo bloğu | Boş sütun adı | Sütun uyuşmazlığı | Birleşmiş başlık |
|---|---:|---:|---:|---:|
| attention_tablo | 4 | 2 | 3 | 0 |
| bert_2sutun_dipnot | 16 | 6 | 11 | 1 |
| gpt3_uzun_75sayfa | 17 | 1 | 11 | 0 |
| gpt4_uzun_gorsel | 14 | 2 | 13 | 0 |
| resnet_2sutun_gorsel | 6 | 3 | 3 | 0 |
| sybil_tip_2sutun | 24 | 2 | 12 | 2 |
| turkce_makale | 2 | 2 | 2 | 0 |
| vgg_tablo_agirlikli | 9 | 2 | 7 | 0 |
| **TOPLAM** | **92** | **20** | **62** | **3** |

**92 tablo bloğunun 62'sinde (%67) sütun hizası bozuk; 20'sinde (%22) en az bir sütun adı
kayıp.** Kusur dokuz dosyanın dokuzunda da var — belgeye özel değil.

pypdf hiç tablo bloğu üretmiyor (0), düz metin veriyor.

> **Kademe 1 — ve pypdf'ten daha riskli.** pypdf yapısız ama yanıltıcı olmayan çıktı veriyor;
> değerlerin okuma sırası korunuyor. inspector **kendinden emin ama yanlış** bir yapı üretiyor:
> geçerli markdown tablosu gibi görünüyor, hücre eşleşmesi hatalı. Bir AUC değerinin yanlış
> veri setine, bir hata oranının yanlış metriğe atfedilmesi mümkün.

## 5.2 Başlık tespiti tutarsız — üretici yazılımla açıklanamıyor

pypdf çıktısında kendi satırında duran numaralı bölüm başlıkları (`2.1 ARCHITECTURE` gibi)
referans alındı; inspector'da bunlara ne olduğu sayıldı.

| Dosya | Üretici | pypdf'te başlık | inspector md başlık | İsabet |
|---|---|---:|---:|---:|
| attention_tablo | LaTeX | 22 | 22 | **%100** |
| bert_2sutun_dipnot | LaTeX | 20 | 18 | %90 |
| resnet_2sutun_gorsel | LaTeX | 13 | 10 | %77 |
| gpt4_uzun_gorsel | LaTeX | 57 | 29 | %51 |
| gpt3_uzun_75sayfa | LaTeX | 49 | 17 | %35 |
| vgg_tablo_agirlikli | LaTeX | 16 | 5 | **%31** |

*(sybil ve turkce numaralı başlık kullanmıyor, bu ölçüme girmiyor.)*

**Sonuç:** isabet %31 ile %100 arasında değişiyor ve **listedeki dosyaların hepsi LaTeX.**
Yani başlık tespitindeki tutarsızlık üretici yazılımla açıklanamıyor — başka bir değişkene
bağlı ve öngörülemez.

> Bu, §1'de kurduğumuz "LaTeX / DTP" hipotezini **sınırlıyor**: hipotez sütun okuma sırası
> için hâlâ geçerli görünüyor (karışma yalnızca turkce ve sybil'de, ikisi de DTP), ama
> **başlık tespiti ve tablo yapısı için geçerli değil** — o kusurlar LaTeX dosyalarında da
> var.

## 5.3 API seçimi çıktıyı değiştiriyor — entegrasyon uyarısı

pdf-inspector üç ayrı metin çıkarma yolu sunuyor. Aynı dosyada üçü farklı sonuç veriyor:

| Dosya | `process_pdf().markdown` | `extract_pages_markdown()` | `extract_text()` |
|---|---:|---:|---:|
| attention_tablo | 40.636 | 40.692 | 38.675 |
| bert_2sutun_dipnot | 66.094 | 66.033 | 63.465 |
| gpt3_uzun_75sayfa | 240.286 | 236.591 | 238.524 |
| **gpt4_uzun_gorsel** | 289.324 | 288.848 | **111.046** |
| resnet_2sutun_gorsel | 60.944 | 60.908 | 58.257 |
| sybil_tip_2sutun | 59.807 | 59.818 | 49.506 |
| turkce_makale | 27.019 | 27.002 | 24.411 |
| vgg_tablo_agirlikli | 55.375 | 55.944 | 48.688 |

**İki ciddi sorun `extract_text()`'te:**

**a) Sessiz içerik kaybı.** `gpt4_uzun_gorsel` 100 sayfa; `extract_text()` yaklaşık 40. sayfada
duruyor ve geri kalanı (System Card eki) hiç çıkarmıyor. Sayfa bazında doğrulandı — 43.
sayfadan sonraki hiçbir sayfanın içeriği yok. **İçeriğin ~%60'ı kayıp, hata veya uyarı yok.**

**b) Kelime sınırlarının yok olması.** sybil ve vgg'de kelimeler birbirine yapışıyor:
```
extract_text (sybil):  originalreports Sybil:AValidatedDeepLearningModelto
                       PredictFutureLungCancer RiskFromaSingle Low-DoseChest...
```
Boşluk oranı ölçüldü (normal İngilizce düzyazı ~%14–16):

| Dosya | pypdf | `process_pdf` | `extract_text` |
|---|---:|---:|---:|
| sybil_tip_2sutun | %15,5 | %14,4 | **%6,0** |
| vgg_tablo_agirlikli | %15,1 | %14,9 | **%4,6** |
| diğer 6 dosya | %13–15 | %12–15 | %15–18 (normal) |

> **Entegrasyon uyarısı — rapora mutlaka girmeli.** Sistemdeki mevcut çağrı
> `page.extract_text()` (pypdf). İsim benzerliği yüzünden en doğal geçiş
> `pdf_inspector.extract_text()` görünüyor, ama **yanlış seçim budur**: iki dosyada kelime
> sınırlarını yok ediyor, bir dosyada içeriğin %60'ını sessizce kaybediyor.
> Kullanılması gereken `process_pdf().markdown`'dır — bu belgedeki tüm ölçümler onunla
> yapıldı.

## 5.4 Sütun karışması otomatik tespit edilemedi — ölçüm sınırı

Sütun karışmasını gözle değil ölçerek bulmak için üç yöntem denendi. **Üçü de başarısız oldu.**

1. Sayfa bazlı metin benzerliği (`difflib`) — karışan sayfalarla temiz sayfaları ayıramadı
2. Eşleşen parça sayısı ve ortalama parça uzunluğu — turkce'de ayırdı, bert'e taşınmadı
3. "Aynı kelimeler var mı" (çoklu küme) − "sıra korunmuş mu" (dizi) farkı — bantlar örtüştü

**Neden:** satır düzeyinde iç içe geçen iki sütun, yerel kelime dizilerini büyük ölçüde
koruyor. Dizi tabanlı ölçütler bunu "çoğunlukla eşleşiyor" olarak görüyor. Ayrıca ayrışmanın
tek nedeni sütun karışması değil — tablo yeri, künye, dipnot işareti de ayrışma üretiyor.

Ölçüt **sıralama** için kullanılabilir, **sınıflandırma** için değil:

| Dosya | Üretici | Bakılan sayfa | Sıra korunma (medyan) | Sıra < 0,80 olan sayfa |
|---|---|---:|---:|---|
| gpt4_uzun_gorsel | LaTeX | 87 | 0,97 | 15 / 87 (%17) |
| gpt3_uzun_75sayfa | LaTeX | 64 | 0,96 | 11 / 64 (%17) |
| attention_tablo | LaTeX | 12 | 0,95 | 3 / 12 (%25) |
| resnet_2sutun_gorsel | LaTeX | 12 | 0,92 | 4 / 12 (%33) |
| bert_2sutun_dipnot | LaTeX | 16 | 0,89 | 2 / 16 (%13) |
| turkce_makale | InDesign | 4 | 0,89 | 2 / 4 (%50) |
| vgg_tablo_agirlikli | LaTeX | 14 | 0,87 | 3 / 14 (%21) |
| **sybil_tip_2sutun** | **Arbortext** | 10 | **0,76** | **6 / 10 (%60)** |

Sıralama gözle bulduklarımızla tutarlı — sütun karışması saptadığımız iki dosya (sybil, turkce)
listenin en kötü iki oranına sahip. Ama bantlar örtüşüyor (resnet %33 > turkce'ye yakın), bu
yüzden **tek başına kanıt sayılamaz.**

> **Rapora yazılacak hâli:** "Sütun okuma sırası bozukluğu elle inceleme ile iki dosyada
> (turkce_makale, sybil_tip_2sutun) tespit edildi; her ikisi de masaüstü yayıncılık yazılımıyla
> dizilmiş. LaTeX ile dizilmiş dört dosyada elle inceleme sırasında bu kusura rastlanmadı.
> Otomatik tespit denendi, güvenilir sonuç vermedi."

## 5.5 Sayfa numarası tabanı

`extract_pages_markdown()` sayfaları **0'dan** numaralandırıyor, pypdf ve PDF okuyucular 1'den.
Entegrasyonda atlanırsa tüm sayfa referansları bir kayar.

---

# Genel değerlendirme

*(tüm dosyalar bitince tamamlanacak — şu an bert ve turkce_makale'ye dayanıyor)*

**İki parserın ortak zayıflıkları**
- Dipnot gövdeden ayrılmıyor (bert)
- Tireleme çözülmüyor
- Şekil içi yazı metne gömülüyor
- Sayfa üst/alt künyesi metne sızıyor
- Paragraf ortasına denk gelen tablo cümleyi bölüyor
- Etiketsiz PDF'te mantıksal okuma sırası kaynakta bulunmadığı için hiçbiri kesin olarak
  yeniden kuramıyor

**Yalnız pypdf'te**
- Ligatür bırakıyor (bert: 157)
- Tablo yapısı çözülüyor (bert)
- Hiç gerçek bölüm başlığı üretmiyor → kaynakça kapısı hiç tetiklenmiyor
- Sayfa numaralarını metne alıyor (turkce)
- Dipnot işaretini kelimeye yapıştırıyor (bert)

**Yalnız inspector'da**
- Çapraz referans boşluğu (bert: Figure 9/14, Table 10/18, Section 8/8)
- Uydurma ve bölünmüş başlık (bert: 8/43, turkce: 3/13)
- **Sütun karışması (turkce: 6 sayfanın 3'ünde)**
- **Yan yana tabloları tek ızgaraya birleştirme (turkce)**
- Kaçırılan başlık (turkce: `Giriş`)

**Belgeye bağlı olduğu görülen davranışlar**
- Tablo tespiti: bert'te başarılı, turkce'de başarısız
- Sütun okuma sırası: bert'te başarılı, turkce'de 3/6 başarısız
- Ligatür kazancı: bert'te 157 → 0, turkce'de her ikisi de 0

- Gözle bakınca sayılara yansımayan: `______`
