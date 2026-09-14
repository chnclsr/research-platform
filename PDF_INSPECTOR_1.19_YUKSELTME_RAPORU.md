# pdf-inspector 1.14.1 → 1.19.0 yükseltmesi

Tarih: `2026-09-14`. Dal: `developments-supplementer`. Taban commit: `8b50b86`.
Durum: kod, testler ve ölçüm tamam.

## Neden

PDF'lerin çoğu sayfası hızlı yoldan, yani pdf-inspector'dan geçiyor. Hangi sayfanın
Docling'e gideceğine karar veren tablo, şekil ve OCR sinyalleri de ondan geliyor. Bizim
sabitlediğimiz sürüm 1.14.1'di; güncel sürüm 1.19.0. Arada metin çıkarma tarafında bir
dizi düzeltme var: satır sonu tirelemesi, üst/alt simgeler, küçük büyük harfler, kalın
yazı, font eşlemeleri.

Sürüm yükseltmesi hızlı yolun metnini ve yönlendirme girdilerini değiştirdiği için
doğrudan pin'i değiştirmedik; önce 380 belgelik korpusta iki sürümü karşılaştırdık.

## Nasıl ölçtük

- **Aynı koşullar, tek fark sürüm.** Aynı kod, aynı 380 belge (opendataloader-bench 200 +
  OCRTurk 180), aynı Docling çıktıları (24 Ağustos GPU koşusunun önbelleği). İki koşu
  arasında yalnız pdf-inspector sürümü değişti.
- **Hakem: resmi opendataloader değerlendiricisi.** Okuma sırası (NID), tablo (TEDS),
  başlık yapısı (MHS) ve bunların ortalaması (overall). C1 ölçütü de raporlandı, ama karar
  resmi ölçüte göre verildi.
- İki çıktı ayrı puanlandı: **hızlı yol çıktısı** (her sayfa pdf-inspector'dan) ve
  **nihai çıktı** (yönlendirme + Docling + karantina sonrası kullanıcının gördüğü metin).

## Sonuç

### Nihai çıktı (kullanıcının gördüğü metin)

| Ölçüt | 1.14.1 | 1.19.0 | Fark |
|---|---:|---:|---:|
| Overall | 0,8780 | 0,8803 | **+0,0023** |
| Okuma sırası (NID) | 0,8965 | 0,8983 | +0,0018 |
| Tablo (TEDS, 84 belge) | 0,8482 | 0,8463 | −0,0020 |
| Başlık (MHS, 109 belge) | 0,7902 | 0,7981 | +0,0078 |

Belge bazında: 6 belge iyileşiyor, 4 belge kötüleşiyor (±0,02 eşiği), 370 belge aynı.
Tablo skorundaki küçük düşüşün tamamı tek bir belgeden (`data_114`) geliyor, aşağıda
açıklandı.

### Hızlı yol çıktısı

| Ölçüt | 1.14.1 | 1.19.0 | Fark |
|---|---:|---:|---:|
| Overall | 0,8283 | 0,8370 | **+0,0086** |
| Okuma sırası (NID) | 0,8626 | 0,8678 | +0,0052 |
| Tablo (TEDS) | 0,6720 | 0,7065 | **+0,0345** |
| Başlık (MHS) | 0,7502 | 0,7668 | +0,0165 |

Belge bazında 26 belge iyileşiyor, 8 belge kötüleşiyor. En büyük kazanç
`01030000000071`: 0,534 → 0,988.

### Yönlendirme

| | 1.14.1 | 1.19.0 |
|---|---:|---:|
| Docling'e giden belge | 160 | **154** |
| Karantinaya alınan sayfa | 3 | 1 |
| Tablo recall (tablolu 84 sayfadan Docling'e giden) | 82 | 81 |
| Tablo bayrağı alan sayfa / gerçekten tablolu olan | 147 / 81 | 141 / 80 |

380 sayfanın 10'unda karar değişti:

- **7 sayfa** artık Docling'e gitmiyor. Referansta tablo yok; 1.14.1 yanlışlıkla tablo
  sanıyordu. Nihai skor 3'ünde artıyor (`01030000000171`: 0,795 → 0,988), 2'sinde aynı
  kalıyor, 2'sinde düşüyor. Düşüşlerin büyüğü `data_10` (0,943 → 0,850): tablo olmasa da
  Docling bu sayfayı daha iyi okuyordu.
- **2 sayfa** yeni Docling'e gidiyor, referansta tablo yok. İkisinde de nihai skor artıyor
  (`data_122`: 0,802 → 0,972).
- **1 tablolu sayfa kaçıyor: `data_114`.** Sayfa bir bilanço şeması. 1.14.1 onu tablo
  olarak okuyup Docling'e gönderiyordu, ama Docling çıktısı karantinaya alındığı için
  kullanıcıya zaten hızlı yol metni gidiyordu. 1.19.0 şemayı başlık ve liste olarak
  okuyor ve sayfa hızlı yolda kalıyor. Bu kaçak kabul edildi.

### Hız

Aynı 380 PDF, sırayla, 3 tekrar:

| | ms / sayfa |
|---|---:|
| 1.14.1 | 69 |
| 1.19.0 | 87 |

1.19.0 sayfa başına ~17 ms daha yavaş. Buna karşılık 6 gereksiz Docling çağrısı kalkıyor
(sayfa başına ~1,5 sn), dolayısıyla toplam süre pratikte değişmiyor.

## Yolda çıkan sorun: `<sup>` / `<sub>` etiketleri

1.18.0'dan beri pdf-inspector üst ve alt simgeleri HTML etiketiyle yazıyor:
`3400 cm<sup>-1</sup>`, `(CN)<sub>6</sub>`. 380 belgenin 52'sinde görüldü.

- İçerik aslında daha doğru: 1.14.1'de `-1` satırdan kopup yanlış yere düşüyordu.
- Ama Docling aynı yeri düz metin yazıyor, Word raporu passage metnini olduğu gibi
  basıyor. Etiketler dokunulmadan bırakılsaydı rapordaki alıntılarda `<sup>` görünecekti.
- Referans metinlerde de etiket yok. Etiketler dokunulmadan puanlandığında OCRTurk'ün nihai
  skoru 1.14.1'in altına düşüyordu (−0,0006, 8 belge kötüleşiyordu).

**Çözüm:** Etiketler pdf-inspector adaptöründe, yönlendirme kararından önce Unicode'a
çevriliyor. Unicode karşılığı olmayan içerikte etiket kaldırılıyor, metin kalıyor.

| pdf-inspector'ın yazdığı | Passage'a giren |
|---|---|
| `3400 cm<sup>-1</sup>` | `3400 cm⁻¹` |
| `10<sup>–15</sup>` | `10⁻¹⁵` (düz `10–15` bir aralık gibi okunurdu) |
| `(μ-CN)<sub>6</sub>` | `(μ-CN)₆` |
| `Kim<sup>∗†</sup>` | `Kim∗†` |
| `V<sub>f</sub>` | `Vf` |

Çevirmeyle birlikte OCRTurk nihai skoru da artıya döndü; yukarıdaki sonuç tabloları bu
haliyle ölçüldü ve 380 belgenin hiçbirinde etiket kalmadı.

## Ne değişti

| Dosya | Değişiklik |
|---|---|
| `pyproject.toml` | `pdf-inspector==1.14.1` → `==1.19.0` |
| `parsers/smart_router/inspector.py` | `<sup>`/`<sub>` → Unicode çevirisi (`betik_etiketlerini_coz`); 1.19.0'da sayfa numarası tabanı yeniden doğrulandı, değişmedi |
| `parsers/smart_pdf.py` | Parse provenance'a `fast_engine_build` eklendi. Docling için sürüm zaten kaydediliyordu (`engine_build`), hızlı yolun sürümü kaydedilmiyordu. Artık bir belgenin hangi pdf-inspector sürümüyle ayrıştırıldığı görülebiliyor. |
| `exporter.py` | `fast_engine_build` teslimat manifestine giriyor |
| `tests/test_parsers.py` | 11 yeni test (aşağıda) |
| `tests/test_export_manifest.py` | Manifestte `fast_engine_build` kontrolü |

## Doğrulama

| Kontrol | Sonuç |
|---|---|
| Tam test paketi | **1126 passed, 4 skipped** (önceki taban 1115 + 11 yeni test) |
| Yeni testler 1.14.1 ile | Pin testi ve uçtan uca `<sup>` testi **kırılıyor**. Testler gerçekten sürümü yakalıyor. |
| API sözleşmesi | `extract_pages_markdown` imzası, 0 tabanlı `page`, 1 tabanlı tablo/OCR/sütun listeleri 1.19.0'da aynı |
| OCR | 1.15'te eklenen OCR yalnız ayrı bir çağrıda (`process_pdf_with_ocr`) çalışıyor; bizim çağrımız model indirmiyor, davranış değişmiyor |
| Worker imajı | Yeni pin'le derlendi (`research-platform-worker:pi119-deneme`); imajda 1.19.0 yüklü, health `fast path via pdf-inspector 1.19.0` diyor |
| Uçtan uca, canlı Docling ile | Yeni imaj canlı Docling servisine bağlanıp 4 korpus PDF'i ayrıştırdı. Tablolu sayfa Docling'e gidip tablo ızgarasıyla döndü, `data_114` ölçüldüğü gibi hızlı yolda kaldı. Hiçbir çıktıda etiket yok, hata veya bozulma yok. Veritabanına dokunulmadı. |
| 380 belgelik korpus | Hata 0 / 380 |

Yeni testler:

- Kurulu pdf-inspector sürümü `pyproject.toml`'daki pin'le aynı mı? Eski sürümde kalan bir
  ortam artık sessizce geçmiyor.
- `<sup>`/`<sub>` çevirisi: korpustan alınmış 9 örnek (birim, kimyasal formül, yazar
  işaretleri, matematik fontu, satır sonlu etiket, tek başına kalmış etiket, etiketsiz
  metin).
- Uçtan uca: üst simgeli bir PDF üretilip `SmartPdfParser`'dan geçiriliyor; metinde
  `cm⁻¹` var, `<sup>` yok, provenance'ta sürüm yazıyor.
