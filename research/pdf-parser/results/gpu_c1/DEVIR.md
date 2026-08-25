# DEVİR — GPU koşusu, diğer makinedeki ajana

Bu paket, `smart_router` PDF ayrıştırma mimarisinin **GPU'lu bir makinede**
koşulmuş tam ölçüm setidir. Önceki bütün ölçümler yalnız CPU'da alınmıştı.

**Önce oku:** `results/gpu_c1/RAPOR_GPU.md` — bulgular, tablolar, her iddianın
altında hangi dosyanın hangi alanından geldiği.
**Sonra aç:** `html/gpu_panosu.html` — çift tıkla, sunucu gerekmez.

---

## 1. Bir paragrafta ne oldu

Depo `485a4b5` commit'inde klonlandı, korpus paketten açıldı (380 + 9 PDF,
sha256 doğrulandı), iki venv kuruldu, Adım 0–10 koşuldu. **Adım 6 hariç hepsi
tamamlandı.** Koşu sırasında makine bir kez yeniden başladı; sistem kendi
kendine kaldığı yerden devam etti.

**Değiştirilen kod: sadece 2 dosya.** `c1_docling_cache.py` (Adım 2 — cihaz
provenance, tam farkı `degisen_kod/c1_docling_cache.patch`) ve yeni
`gpu_panosu.py` (Adım 9). `config/smart_router.yaml` GitHub'daki orijinaliyle
**birebir aynı** (diff ile doğrulandı) — `esik_version` değişmedi.

## 2. Dört sorunun cevabı

| soru | cevap | kaynak |
|---|---|---|
| Hız / maliyet oranı | Ağır/kapı oranı CPU'da 203–285×, GPU'da **60–103×**. "~300×" varsayımı GPU'da geçersiz. Ama "hepsi ağır" GPU'da bile **2,22×** pahalı → sayfa seçmek hâlâ haklı. | `gpu_docling_*.json`, `hata_arayuzu_veri.json` |
| Determinizm | **Bozulmuyor.** GPU'da 3 koşu, 6 ve 75 sayfalık belgede bayt bayt aynı. | `*_determinizm_*.json` |
| Cihaz eşdeğerliği | **Fark yok** — 261 sayfa + 65 belge, tablo yapıları dahil. Önceki RTX 4060'ın 7 sayfalık farkı tekrarlanmadı. | `esdegerlik_farklari.md` |
| C1 faydası | Aynı 201 belgede **hiçbir metrik değişmedi**. 380'in tamamında precision 0,4713 → **0,4000**; `opendataloader_bench`'te NET **−1,57**. | `summary_gpu_tam_380.json` |

**Kapanan kanıt boşluğu:** 380 belgenin tamamı işlendi, 0 hata. CPU'da 201/380
işlenebilmişti (179 "Docling cache yok" hatası).

## 3. Ortam — sayılar bunun üzerinde alındı

| | |
|---|---|
| GPU | **Quadro RTX 4000**, 8 GB, sürücü 595.84, CUDA 13.2, sm_75 (Turing) |
| işlemci | Intel Xeon W-2145 @ 3.70 GHz, 8c/16t, 125 GB RAM |
| OS | Ubuntu 22.04.5, kernel 6.8.0-138 |
| ağır motor venv | Python 3.10.12, torch 2.6.0+cu124, **docling 2.120.1** |
| metrik venv | Python 3.11.16, rapidfuzz 3.14.5 |
| metric_fingerprint | `c1_metrics_v1_2026-08-18+rapidfuzz` |
| depo | `chnclsr/research-platform` @ `485a4b5` |

> Önceki GPU ölçümü **RTX 4060 + docling 2.120.3** idi. İki değişken birden
> farklı; o makinenin 7 sayfalık eşdeğerlik farkının GPU mimarisinden mi docling
> sürümünden mi geldiği bu koşuyla **ayrılamaz**.

---

## 4. TUZAKLAR — bunlar zaman kaybettirir, önce oku

### 4.1 `hata_arayuzu.py` (Adım 6) bu pakette koşmaz

İki girdi istiyor, **ikisi de pakette yok ve depoda üreten betik de yok**:

- `out/docling_annot/<belge>.json` — referans tablo/şekil etiketleri
- `out/mineru/<belge>/auto/<belge>_middle.json` — tablo referansının MinerU yarısı

İkincisi **sessiz bozulma** üretiyor: kod `if os.path.exists` ile koruyor, dosya
yoksa `mineru` boş küme kalıyor ve `mineru & docling_tablo` **her zaman boş**
çıkıyor — tablo hükümleri hata vermeden anlamsız olur. Bu, projenin daha önce
yaşadığı "hiç var olmayan sayı" hatasının aynısı.

Ayrıca `hata_arayuzu.py:55` içinde `OUT = os.path.join(BASE, "out")` **sabit
yazılı**; `PDF_PARSER_OUT` dinlenmiyor. Promptun Adım 6 tarifi
(`$env:PDF_PARSER_OUT = "...out_gpu"`) bu sürümle **çalışmaz**.

### 4.2 `gpu_docling_olc.py` — her koşu aynı dosyanın üzerine yazar

Çıktı yolu cihazdan türüyor: `out/gpu_docling_<device>.json`. Yani
`--determinizm` koşusu, hız koşusunun sonucunu **ezer**. Her koşudan hemen sonra
kopyalanmalı. Ayrıca `out/gpu_docling_json_<device>/<belge>_sayfalar.json`
dosyaları da ezilir — Adım 6 için dondurulmuş kopya şart
(`out/gpu/a3_cuda_sayfalar/` bu yüzden var).

**Ayrıca bir hata:** `--karsilastir` göreli yol verilirse tanımsız `BASE`
değişkenine bakıyor ve `NameError` atıyor. **Mutlak yol ver.**

Ve **yeniden başlatılabilir değil**: yarıda kesilirse süre verileri tamamen
kaybolur (sayfa metinleri belge belge yazıldığı için onlar kalır).

### 4.3 `src/` ile `scripts/` ayrışmış — hangisinin yüklendiğine dikkat

`c1_dogrulama.py` başında `sys.path.insert(0, BASE/"src")` yapıyor, yani
`c1_metrik` ve `c1_orneklem` **`src/`'ten** geliyor. Ama `c1_docling_cache.py`
bunu yapmıyor, **`scripts/`'ten** yüklüyor.

- `src/c1_metrik.py` **yeni** sürüm: `METRIC_FINGERPRINT`, `ALGORITMA`,
  `kati_dogrula()` var.
- `scripts/c1_metrik.py` **eski**: bunların hiçbiri yok, `rapidfuzz` yoksa
  sessizce `difflib`'e düşüyor.

İyi haber: `c1_orneklem.py` ikisinde **birebir aynı**, yani cache ve doğrulayıcı
aynı `sec()` sırasını kullanıyor (`--limit 60` ikisinde de aynı 60 belge).

### 4.4 Envanterdeki `yol_koku` şeması

`korpus_envanteri.py` de `src/korpus_kaynak.py`'yi yüklüyor (kendi
`sys.path.insert`'i yüzünden), o yüzden `opendataloader_bench` kayıtları
`yol_koku: "staj"` ve `pdf_yolu: "../../corpus/raw/..."` şeklinde çıkıyor.
Bu, hem `c1_dogrulama._coz` hem `c1_docling_cache._resolve` ile **doğru
çözülüyor** — ama `scripts/korpus_kaynak.py` yüklenseydi `yol_koku:
"opendataloader_bench"` + `pdf_yolu: "pdfs/x.pdf"` çıkardı ve `c1_dogrulama._coz`
bunu **yanlış** çözerdi (200 belgenin hepsi `FileNotFoundError`).

`OPENDATALOADER_BENCH` ortam değişkenini korpusun gerçek yerine ayarla:
`corpus/raw/opendataloader_bench` (varsayılan
`research/pdf-parser/corpus/opendataloader-bench`, orada değil).

### 4.5 Cache dosya adında cihaz YOK

`c1_docling_cache.py` dosyaları yalnız `pdf_sha256` ile adlandırıyor. İki cihazı
aynı dizine yazarsan **sessizce üzerine yazar** ve karşılaştırma imkânsız olur.
Ayrı dizin kullan (`_cuda`, `_cpu`). Adım 2'de eklenen `"device"` alanı sayesinde
artık bir cache dosyasına bakıp hangi cihazda üretildiği görülebiliyor —
**varsayma, o alanı oku.**

### 4.6 `pgrep`/`pkill -f` kendi kabuğunu yakalar

`pkill -f 'telemetri.sh'` çalıştıran kabuğun **kendi komut satırı** o metni
içerdiği için kendini öldürür. Bu koşuda üç kez yaşandı. Ya deseni dar tut
(yorumlayıcı yolu + betik yolu birlikte), ya PID ile öldür, ya da komutu bir
dosyaya yazıp çalıştır.

### 4.7 Koşan bir bash betiğini `cat >` ile yeniden yazma

bash betiği kademeli okur; `cat > dosya` aynı inode'u kırpar ve koşan kopya
saçma yerden devam eder. **`mv` kullan** (yeni inode) — koşan kopya eski
inode'u okumaya devam eder. Bu da bir kez yaşandı.

### 4.8 OCRTurk `source.json` dosyalarının 107'si BOM'lu

Düz `utf-8` ile okursan ilk anahtar `﻿difficulty` olur, `.get()` sessizce
`None` döner, dağılım **hata vermeden** boş çıkar. Kod `utf-8-sig` kullanıyor;
kendi yardımcı betiğini yazarsan sen de kullan.

---

## 5. ÖLÇÜM GEÇERLİLİĞİ — bunlar rapora girdi, atlanmasın

### 5.1 Hız bu makinede tekrarlanabilir değil

Aynı ölçüm iki kez koşuldu (`gpu_docling_*_tekrar.json`):

| | 1. ölçüm | 2. ölçüm | oran |
|---|---|---|---|
| CPU | 1757,0 ms/sayfa | 2464,0 ms/sayfa | 1,40× |
| GPU | 516,4 ms/sayfa | 887,4 ms/sayfa | 1,72× |
| hızlanma | **3,40×** | **2,78×** | — |

Bu yüzden hızlanma **tek sayı değil, 2,78×–3,40× aralığı** olarak raporlandı.
Çapraz eşleme (1. CPU / 2. GPU) iki farklı makine durumunu böler, **kullanma**.

Sebep doğrulanmadı. PROCHOT sayacı 0, rakip süreç yok (>%92 boşta), governor
(`powersave`/`intel_pstate`) ve EPP (`balance_performance`) değişmedi.
**Hipotez (kanıt değil):** 1. ölçüm ~45 dk sürekli GPU yükünden önce, 2. ölçüm
sonra koştu; sıcak kasada turbo binleri PROCHOT bayrağı kaldırmadan düşer.

### 5.2 GPU termal kısılma yaptı

`telemetri.jsonl`: 166 örneğin 16'sında kısılma (SW Thermal Slowdown + güç
limiti), en yüksek **91 °C**, SM saati 2100 → 1005 MHz.
**GPU hızlanma katsayısı bir ALT SINIRDIR.**

### 5.3 Süreler kesintiden etkilenmedi

Bütün süreler ölçülen sürecin içinde `time.perf_counter()` ile alındı, kabuk
duvar saatinden değil. Kesilen belgenin cache dosyası atomik yazım sayesinde
**hiç yazılmıyor**, yani yarım ölçülmüş belge oluşamaz. `durum/<adım>.ok`
içindeki saniye kabuk saatidir ve devam koşusunda model yükleme + atlanan
belgeleri içerir — **rapora girmedi, sadece bilgi.**

---

## 6. Pakette ne var

| yol | ne |
|---|---|
| `results/gpu_c1/` | **Teslim edilen sonuç seti** — RAPOR_GPU.md, README.md, 17 kanıt dosyası |
| `html/gpu_panosu.html` | Adım 9 panosu — tek dosya, dış bağımlılık yok, basılabilir |
| `html/c1_arayuz_gpu.html` | Adım 8 — C1 belge belge inceleme + iki koşu kıyası |
| `degisen_kod/` | Adım 2'nin `.patch`'i + iki değişen/yeni betik |
| `out/gpu/` | Ara kanıtlar: ortam, envanter karşılaştırma, eşdeğerlik, atıf, hız kararlılığı, dondurulmuş sayfa metinleri |
| `out/c1_runs/` | Üç doğrulama koşusu: `summary.json`, `predictions.jsonl`, belge belge markdown |
| `out/c1_docling_cache_*/` | Docling cache'leri (`device` alanı dahil) — CUDA 380, CPU 60, CPU ek 5 |
| `out/gpu_docling_json_*/` | 9 belgenin sayfa markdown'ı, CPU ve CUDA ayrı |
| `out/korpus_envanteri.jsonl` | Bu makinede üretilen envanter (380 kayıt) |
| `kosum/` | Koşum altyapısı: `kos.sh`, `ortam.sh`, yardımcı betikler, `NASIL_DEVAM.md` |
| `kosum/durum/` | Adım adım durum dosyaları — hangi adım ne zaman bitti |
| `loglar/` | `kos.log` (kesinti kanıtı), adım logları, `telemetri.jsonl` |

**Pakette YOK:** korpus PDF'leri (`gpu_paket_gonder` içinde zaten var, 130 MB) ve
iki venv (yeniden kurulmalı).

---

## 7. Devam edilirse — açık kalanlar

1. **Adım 6 ölçülemedi.** `docling_annot/` ve `mineru/` çıktıları üretilirse
   koşulabilir. `hata_arayuzu.py:55`'teki sabit `OUT` da düzeltilmeli.
2. **Önceki makinenin 7 sayfalık farkı açıklanmadı.** Ayırmak için **aynı
   makinede docling 2.120.3** koşulmalı; o zaman tek değişken sürüm olur.
3. **Hız kararsızlığı çözülmedi.** Soğuk makinede, GPU yükü olmadan, 3+ tekrarla
   ölçülürse aralık daralır.
4. **`opendataloader_bench`'te NET negatif (−1,57).** Yönlendirme o ailede fayda
   kaybettiriyor. Bu koşunun kapsamı dışıydı; eşik kalibrasyonu gerektirir ve
   `config/smart_router.yaml` bu koşuda **kasten ellenmedi**.
5. **`doclaynet` ve `omnidocbench` gönderilmedi** (ikisinde de PDF yok) —
   envanter onları eksik görür, sorun değil.

## 8. Yeniden koşmak istersen

`kosum/kos.sh` kesintiye dayanıklı bir sürücü: her adım ya tamamen biter ve
`durum/<adım>.ok` yazılır, ya da hiç bitmemiş sayılır. Kaç kez çalıştırdığın
önemli değil, biten adım tekrar koşmaz. SSH kopması, oturum ölümü ve reboot'a
dayanıklı (crontab `@reboot` + 5 dakikalık watchdog). Ayrıntı:
`kosum/NASIL_DEVAM.md`.

Kurulum notu: bu makinede **sudo, git, pip ve Python 3.11 yoktu**. Çözüm:
`uv`'nin bağımsız kurucusu (`curl -LsSf https://astral.sh/uv/install.sh | sh`,
sudo gerekmez) hem Python 3.10/3.11'i hem paketleri kurdu; depo `git clone`
yerine `codeload.github.com` tarball'ı olarak indirildi ve commit sha'sı GitHub
API'den doğrulandı. Hiçbir betik `git` çağırmıyor, tarball yeterli.
