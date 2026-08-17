# Coverage Recovery Uygulama ve Canlı Doğrulama Raporu

Belge sürümü: `1.1`

Platform sürümü: `v0.4.1-dev`

Tarih: `2026-07-16`

Temel doğrulama run'ı: `01KXNFSF8B53543WY39NGJNNE4`

Kalite doğrulama run'ı: `01KXNGQ1CMNZ0NWETV9C54B53Z`

Güvenlik smoke run'ı: `01KXNH1DQ8EY82BW786T6Q2119`

## Sonuç

İlk turun yetersizliğini doğru teşhis edip sonraki turda aynı aramayı tekrarlama sorunu
giderildi. Yeni döngü eksikliği yapılandırılmış boşluklara çeviriyor, her boşluk için
hedefli görev üretiyor, mevcut URL'leri acquisition öncesinde eliyor ve yalnız gerçek yeni
kaynaklar üzerinden coverage hesaplıyor.

İlk canlı ham-veri koşusu üç turda `completed` oldu:

| Ölçüm | İlk tur | İkinci tur | Son durum |
|---|---:|---:|---:|
| Kaynak | 9 | 14 | 14 |
| Kaynak ailesi coverage | 0.90 | 1.00 | 1.00 |
| Sorgu dalı coverage | 0.5833 | 0.9167 | 0.9167 |
| Resmî varlık coverage | 1.00 | 1.00 | 1.00 |
| Yeni kaynak oranı | 1.00 | 0.3571 | 0.00 |
| Doygun tur | 0 | 0 | 1 |
| Durum | yetersiz | yalnız doygunluk eksik | `completed` |

Önceki dayanak koşu `01KXNDKV20RK81PGWSRWS33YR7`, dört tur sonunda 11 kaynak,
`0.40` kaynak ailesi coverage ve 23 çözülmemiş major claim ile
`completed_incomplete` durumunda kalmıştı. Yeni doğrulama claim/sentez kalitesini değil,
bilgi toplama ve recovery davranışını izole etmek için `raw` modunda yapıldı.

Sonraki kalite koşusunda coverage eligibility sıkılaştırıldı. İlk tur 9, ikinci tur 12,
üçüncü tur 16 kaynağa çıktı; aile coverage `1.0`, sorgu dalı coverage `0.8333` ve resmî
varlık coverage `1.0` oldu. Üçüncü tur hâlâ yeni kaynak ürettiği ve 16 kaynaklık test
bütçesi dolduğu için sistem doğru biçimde `completed_incomplete` kaldı; tek eksik
`query_saturation` idi. Bu, bütçe biterken sahte doygunluk ilan edilmediğini gösterir.

Güvenlik smoke koşusunda prompt-injection benzeri Zenodo kaydı
`untrusted_instruction_pattern` nedeniyle acquisition öncesinde reddedildi. Aynı koşuda
0.31–0.33 bandındaki genel kelime çakışmalı akademik sonuçlar da düşük ilgi nedeniyle
elenmiş, ilk tur kabul edilen kaynak sayısı 9'dan 6'ya düşmüştür.

## Uygulanan mimari

```text
CHECK_COVERAGE
  └─ DIAGNOSE_GAPS
       ├─ eksik kaynak ailesi
       ├─ eksik resmî/primary otorite
       ├─ zayıf major claim
       └─ cevapsız sorgu dalı
            ↓
       PLAN_RECOVERY_MISSIONS
            ↓
  domain/connector/seed/quota kısıtlı SEARCH
            ↓
  persistent novelty filter
            ↓
  yalnız yeni source version'ları ACQUIRE → NORMALIZE → INDEX
            ↓
  AUDIT → CHECK_COVERAGE
```

Temel değişiklikler:

- Protokole ağırlıklı `family_targets`, `authority_policy` ve gerçek `output_mode` eklendi.
- `CoverageGap` ve `SearchMission` şemaları eklendi.
- İlk tur kaynak bütçesinin tamamını tüketmiyor; sonraki turlara pay bırakılıyor.
- Adaylar DOI/persistent ID, canonical URL ve dedupe key ile mevcut run corpus'una karşı
  acquisition öncesinde eleniyor.
- Tekrar bulunan URL yeniden indirilmeden yeni query branch ve doğrulanmış authority
  metadata'sıyla zenginleştiriliyor.
- Görev kotasıyla aday seçimi yapıldığı için tek connector veya tek sorgu dalı bütçeyi
  tek başına tüketemiyor.
- Resmî-domain aramasında dönen URL'nin hostname'i allowlist ile yeniden doğrulanıyor.
- Named-product araştırmasında `official_legal` sonuç ya tanınan resmî domaine ait olmalı
  ya da hedef varlığı açıkça anmalıdır.
- Prompt-injection/jailbreak benzeri discovery başlıkları kanıt değil, güvenilmeyen veri
  olarak karantinaya alınır.
- Arama motoru başarısız olsa bile kritik resmî köklerden başlanabilmesi için genişletilebilir
  seed registry eklendi:
  - MCP authorization dokümanı
  - Codex MCP ve security dokümanları
  - Claude Code MCP ve security dokümanları
  - Telegram Bot API ve FAQ
  - MCP, Codex ve Claude Code resmî kaynak depoları
- Recovery görevleri coverage paydasına yeni zorunlu araştırma dalı olarak eklenmiyor.
- `raw` modunda claim extraction ve synthesis LLM çağrıları yapılmıyor.
- Ulaşılamayan Zotero ve anahtarsız/degraded connector'lar health preflight ile atlanıyor.
- Claim modunda extraction promptu artık araştırma sorusunu açıkça içeriyor ve yalnız en
  ilgili major claim'ler coverage audit kümesine giriyor.

## Canlı kaynak dağılımı

| Aile | Connector | Adet |
|---|---|---:|
| Akademik | arXiv, Crossref, local corpus | 4 |
| Kod/veri | DataCite, source seed | 3 |
| Resmî/hukuki | official seed, official registry, EUR-Lex | 5 |
| Web | local corpus | 2 |

Üçüncü turda yeni kaynak bulunmadı; `new_source_rate=0.0` olduğu için doygunluk koşulu
sağlandı. Bu, boş aramayı başarı sanmak yerine önce coverage'ı tamamlayıp sonra marginal
yield düşüşüyle durduğunu gösterir.

## Test kanıtı

- Ruff: başarılı.
- Compileall: başarılı.
- Pytest: `64 passed`, bir Starlette deprecation uyarısı.
- RTX 4060 canlı kontrolde Qwen3 4B modeli tamamen VRAM'de çalıştı; ham koşuda claim ve
  sentez bilinçli olarak atlandığı için LLM yalnız decomposition/query üretiminde kullanıldı.
- Temel doğrulama ham çıktısı:
  - `13_raw_sources.jsonl`: yaklaşık 9.4 MB
  - `14_raw_passages.jsonl`: yaklaşık 10.0 MB
  - `raw_bundle.zip`: yaklaşık 5.1 MB

- Kalite koşusu ham çıktısı:
  - `13_raw_sources.jsonl`: yaklaşık 21.9 MB
  - `14_raw_passages.jsonl`: yaklaşık 15.9 MB
  - `raw_bundle.zip`: yaklaşık 10.4 MB

## Kalan riskler

1. Semantic Scholar anahtarsız kullanımda 429 verebilir; artık health preflight ile
   atlanır. API anahtarı sağlanırsa yeniden etkinleşir.
2. GitHub API anahtarsızken rate limit/422 üretebilir; resmî repo seed'leri kritik başlangıcı
   korur, fakat geniş kod araması için token önerilir.
3. Seed registry genel web'in yerine geçmez; yalnız bilinen yüksek değerli varlıklara
   deterministik başlangıç sağlar ve yapılandırılabilir registry'ye taşınmalıdır.
4. Bu doğrulama bilgi toplama katmanını ölçer. `result`/`both` modunda claim clustering,
   independent-source eşleme ve sentez kalitesi ayrı golden araştırma setiyle tekrar
   doğrulanmalıdır.

## Üretilen doğrulama dosyaları

Yerel çalışma kanıtları:
[`logs/recovery-verified`](logs/recovery-verified),
[`logs/recovery-final-quality`](logs/recovery-final-quality) ve
[`logs/recovery-security-smoke`](logs/recovery-security-smoke).
