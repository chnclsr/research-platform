# MinerU hybrid-engine (VLM, GPU) — aday motor araştırması

<!-- 2026-08-20: PDF_PARSER_V0.1.0_RC1_REPORT.md'nin eski "H" bölümüydü.
Bu bir aday motor değerlendirmesi, kendi hibrit stratejimizin (A-G
bölümleri, o raporda) bir parçası değil — o yüzden ayrı dosyaya taşındı.
Ana rapor kendi stratejimizin özeti olarak kalsın diye. -->

**Kaynak ve sınır:** Bu ölçüm bu depoda/makinede yapılmadı. GPU makinesinde
(PC_6605, RTX 4060, MinerU 3.4.5) çalıştırılıp `mineru_paket_tam.zip`
(54,6 MB) olarak ölçüm alanına (`sude-staj`) yüklendi. Buradaki iş ölçümü
tekrarlamak değil: paketi doğrulamak, `sude-staj/rapor/MINERU_RAPOR_HYBRID_GPU.md`
olarak kaydetmek ve sayfa sayfa görsel bir doğrulama arayüzü kurmaktı
(`sude-staj/src/annot_mineru_uret.py` → `html/annot_mineru_*.html`).
Doğrulama: kendi ürettiğim arayüzün tablo/chart/image sayımı (119/73/50)
paketin kendi raporuyla **birebir örtüştü** — bağımsız hesaplama aynı ham
JSON'dan aynı sonucu verdi.

## 1. Tek cümlelik sonuç

MinerU `hybrid-engine --effort medium`, bu donanımda **Docling GPU'ya hız
alternatifi değil**: 261 sayfada 10.011 ms/sayfa, Docling GPU'nun **18,5
katı** (Docling CPU'sunun bile 6,4 katı). Determinizm testini geçti (3
ardışık koşu, bayt bayt aynı SHA-256) — VLM tabanlı olmasına rağmen
`content_hash` sözleşmesini bozmuyor.

## 2. Neden yavaş — iki ölçülmüş sebep

1. Windows'ta `lmdeploy` yok, VLM motoru yavaş `transformers` yoluna
   düşüyor (hızlı yol **ölçülmedi**).
2. 8 GB VRAM `batch=1`'e zorluyor; `gpt4_uzun_gorsel`'de torch tepe ayırma
   (9.484 MB) kart toplamını (8.188 MB) aştı — OOM yerine sessiz NVIDIA
   sysmem fallback, süreyi şişirmiş olabilir.

## 3. Bizim mimari için değerli olan kısım

- Tablo gövdesi HTML, `rowspan`/`colspan` **korunuyor** — Docling markdown
  tabloda birleşik hücre bilgisini kaybediyordu.
- `chart` ile `image` **ayrı etiketleniyor** (73/50); Docling ikisini de
  `<!-- image -->` ile aynı kefeye koyuyor.
- Her şekil için kırpılmış görsel + bbox diske yazılıyor — ana rapordaki
  G bölümünde tespit edilen "sonraki katman eksik bir şey olduğunu
  bilmiyor" sorununu MinerU'da çözüyor.
- **Lisans düzeltmesi:** MinerU 3.x **Apache-2.0 + ek atıf şartı**;
  projedeki önceki "AGPL-3.0" notu 1.x dönemine ait ve **yanlıştı**.

## 4. Karar için henüz yeterli değil

Hiçbir sayfada altın standarda karşı doğruluk ölçülmedi — "yapı daha
zengin" gözlemlendi, "daha doğru" kanıtlanmadı. `--effort high`'ın şekil
okuma başarısı, süreçler arası determinizm ve büyük VRAM'de davranış
ölçülmedi. Bu nedenle MinerU hybrid **toplu ikinci motor adayı değil**;
olası kullanım, Docling'in `<!-- image -->` bıraktığı veya tablo yoğun
tekil sayfalarda seçici ikinci geçiş — bu da henüz ölçülmedi, yalnız
raporun kendi mentöre sorusu.

## 5. Pipeline (CPU) ile hybrid (GPU) aynı korpusta karşılaştırıldı (2026-08-20)

`out/mineru_sureler.json` (pipeline, 2026-08-14) ve `out/mineru_medium.json`
(hybrid, 2026-08-19) **aynı 9 belge/261 sayfa** üzerinde ölçülmüş —
ilk kez apples-to-apples bir kıyas mümkün oldu.

**Toplamda hybrid 1,87× yavaş** (5.345 ms/sayfa → 10.011 ms/sayfa), **ama
tek yönlü değil**: 14-16 sayfalık orta yoğunluktaki 3 belgede (attention,
bert, vgg) hybrid **daha hızlı** (0,56-0,69×); fark uzun belgede (gpt3,
75 sayfa, 4,03×) ve yoğun/taranmış belgede (sybil, taranmis, 2-2,9×)
açılıyor. gpt3'te GPU bellek tepe noktası (8.102 MB) kart toplamına
(8.188 MB) çok yakın — olası bir sebep, kesinleştirilmedi.

**Adil bir kıyas değil, üç sebep açık:** (1) **farklı donanım, tercih
değil zorunluluk** — pipeline'ın ölçüldüğü makinede (PC_7820) CUDA GPU
**yok** (doğrulandı: `nvidia-smi` yok, `torch.cuda.is_available()` →
`False`). Pipeline hiç GPU'da, hybrid hiç CPU'da ölçülmedi; backend türü
ile donanım iç içe, ayrıştırılamıyor. 3 belgede hybrid'in önde
görünmesinin GPU hızlanmasından mı yoksa hybrid'in kendisinden mi
geldiği **bu veriyle söylenemez** (PC_6605'in CPU'su bile 2,23× hızlı
ölçülmüştü, GPU'nun payı büyük olasılıkla var ama miktarı bilinmiyor).
(2) farklı sürüm (3.4.4 / 3.4.5). (3) pipeline'ın süre ölçümü markdown
yazımını da kapsıyor, hybrid'inki kapsamıyor — ama bu pay önemsiz
(4,8 sn/261 sayfa).

**Doğruluk için ikisini aynı yerde göremiyoruz:** `referans_skorlar.csv`'de
MinerU (pipeline ya da hybrid) hiç yok, 9 belgede resmi skorlama
yapılmadı. Pipeline'ın tek resmi sayısı 200 belgelik **dış** benchmark'tan
(overall 0,857, tablo 0,911) — farklı belgeler. Hybrid'in hiç resmi
skoru yok.

**Sonuç:** GPU'nun bedeli (kurulum, 5 GB model, Windows fallback'i, VRAM
riski) karşılığında sistematik bir hız kazancı yok; uzun/yoğun belgede
pipeline belirgin önde. Doğruluk sorusu resmi ölçüm olmadan **açık**.

Bu kıyas ölçüm arayüzüne de işlendi: `sude-staj/html/olcumler.html`'de
"Hız/sayfa — tüm denenen motorlar (MinerU hybrid ve Docling GPU dahil)"
bölümü, 8 motor ms/sayfa + 261 sayfa ağırlıklı ortalama, donanım
karışıklığı uyarısıyla birlikte (`src/grafik_uret.py`).
