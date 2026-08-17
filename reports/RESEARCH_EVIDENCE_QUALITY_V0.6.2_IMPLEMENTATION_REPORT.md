# Research Evidence Quality v0.6.2 Uygulama Raporu

- Belge sürümü: `1.0.0`
- Platform sürümü: `v0.6.2`
- Tarih: `2026-07-17`
- Önceki kalite run'ı: `01KXR0ZRXAKNJ3C6692PE3N2TQ`
- Kabul run'ı: `01KXR39GAA6G1MCR8QR9QW2XGV`

## Sonuç

v0.6.1 stres testinde saptanan citation-shell kaynaklı yanlış kanıt sorunu giderildi. Kaynakça, `How to Cite`, arXiv `Access Paper`, `View PDF` ve navigasyon metinleri artık raporlanabilir kanıt üretemiyor. Zorunlu sentinel kaynak yalnız ölçülmek yerine exact title, persistent ID ve canonical URL ile aranıp ediniliyor.

Kabul run'ı araştırma sorusuna yeterli cevap üretemediği için doğru biçimde `completed_incomplete` tamamlandı. Bununla birlikte artık yetersizliği hayalî veya semantik olarak geçersiz iddialarla kapatmıyor.

## Uygulanan değişiklikler

### Kanıt güvenliği

- `References`, `Bibliography`, `How to Cite`, kaynakça, atıf, footer ve yazar bilgisi bölümleri extraction dışında bırakıldı.
- Bibliyografik kayıt, DOI satırı, kaynak başlığı, soru başlığı ve erişim kabuğu için fail-closed filtre eklendi.
- `Skip to main content`, `Access Paper`, `View PDF`, giriş/kayıt ve benzeri navigasyon metinleri reddediliyor.
- `qualified` veya `supported` raporlaması için en az bir geçerli `supports` kanıtı zorunlu.
- Geçersiz evidence sayısı ve nedenleri claim audit içine yazılıyor.
- Sentez yalnız kalite kapısından geçen claim ve alıntıları alıyor.
- Sentez çıktısındaki bilinmeyen URL ve rapor dili ihlali deterministic fallback'i tetikliyor.
- Hiç raporlanabilir iddia yoksa LLM sentezi çalıştırılmıyor.

### Discovery ve recovery

- Her zorunlu sentinel ayrı query branch ve acquisition kotası alıyor.
- Sentinel görevinde exact title, persistent ID ve canonical URL birlikte kullanılıyor.
- Eksik sentinel, sonraki turda en yüksek öncelikli recovery gap oluyor.
- Sentinel belgesi genel akademik heading filtresi yerine başlık–içerik eşleşmesiyle doğrulanıyor.
- arXiv kimliğinden ay/yıl; açık HTML metadata'sından yayın tarihi enrichment eklendi.
- Sağlıklı citation connector yoksa veya citation çağrıları hata verirse `citation_frontier_degraded` olayı üretiliyor.

### Metrik doğruluğu

- Beşten az discovery observation için `estimated_completeness` artık yanıltıcı `1.0` yerine `null/ölçülmedi`.
- `claim_audit_coverage`, destek yeterliliği değil denetlenen claim oranı olarak korunuyor; raporlanabilirlik ayrıca geçerli destek sayısıyla belirleniyor.

## Önce–sonra karşılaştırması

| Ölçüm | v0.6.1 başlangıç | v0.6.2 kabul | Yorum |
|---|---:|---:|---|
| Sentinel recall | 0,0 | 1,0 | Kritik kaynak artık bulundu |
| Kabul edilmiş kaynak | 2 | 4 | Sentinel ve ek akademik kaynaklar eklendi |
| Toplam claim | 8 | 21 | Daha geniş belge işleme |
| Raporlanabilir claim | 4 yanlış | 2 geçerli, tek kaynaklı | Precision belirgin arttı |
| Citation/navigation-shell claim | 4 | 0 | Kritik regresyon kapandı |
| Tahmini completeness | 1,0 / 2 gözlem | `null` / 4 gözlem | Yanıltıcı tamlık kaldırıldı |
| ZIP artifact | 17 | 17 | Teslim hattı korundu |
| ZIP bütünlüğü | Geçti | Geçti | CRC hatası yok |

## Kabul run'ı

Run: `01KXR39GAA6G1MCR8QR9QW2XGV`

- Süre: yaklaşık 180 saniye.
- Tur: 3.
- Kaynak: 4 akademik kaynak.
- Claim: 21; `19 unresolved`, `2 qualified`, `0 supported`.
- Sentinel recall: `1.0`.
- Kaynak ailesi coverage: `0.30`.
- Query branch coverage: `0.0`.
- Unresolved major claim: `8`.
- Artifact: 17; birleşik ZIP `183.701` bayt ve CRC temiz.
- Nihai raporda `References`, `How to Cite`, `Access Paper`, `View PDF` veya `Skip to main content` kökenli raporlanabilir iddia yok.

Raporlanabilir iki iddianın ikisi de aynı güncel arXiv çalışmasına dayanan tek kaynaklı bulgulardır. Sistem bunları `supported` değil `qualified` olarak göstermiştir. Bağımsız kanıt ve karşı kanıt bulunmadığı için kesin cevap üretmemiştir.

## Test sonucu

- Ruff: temiz.
- Pytest: `115 passed`, `1` üçüncü taraf deprecation warning.
- Gerçek API/worker/Ollama kabul run'ı: tamamlandı.
- Artifact ZIP CRC: başarılı.
- Sentez grounding: doğrulanmamış URL yok; dil/grounding kapısı gerektiğinde deterministic fallback kullandı.

## Kalan araştırma kalitesi açıkları

Bu sürüm yanlış pozitif kanıtları önemli ölçüde azaltmıştır; discovery recall hâlâ yeterli değildir:

- Yalnız akademik kaynak ailesi kabul edildi; web, resmî ve kod/veri hedefleri karşılanmadı.
- Semantic Scholar public erişimi 429 hatalarına açıktır.
- GitHub anahtarsız kullanım rate limit nedeniyle zayıftır.
- Citation frontier operasyonel sağlayıcı eksikliği nedeniyle düşük katkı vermektedir.
- Query branch provenance, recovery ile bulunan kaynakları ilk branch'lere geri bağlamadığı için branch coverage düşük kalmaktadır.
- Güçlü fakat paraphrase edilmiş bazı claim'ler conservative entailment kapısında unresolved kalmaktadır. Bu tercih yanlış iddia yayımlamaktan daha güvenlidir; sonraki sürümde premise-aware NLI ile recall artırılmalıdır.

## Kabul kararı

v0.6.2, v0.6.1'deki kritik yanlış kanıt yayımlama kusurunu kapatmıştır ve ekip içi kaynak toplama/denetim kullanımına uygundur. Araştırma yeterliliği eşikleri gevşetilmemiştir; eksik araştırma hâlâ `completed_incomplete` olarak teslim edilir. Bir sonraki kalite çalışması discovery çeşitliliği, citation provider güvenilirliği ve branch provenance üzerine yapılmalıdır.
