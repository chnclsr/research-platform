# Graceful Collection Cutoff Düzeltme Raporu

Belge sürümü: `1.0`

Platform sürümü: `v0.6.10`

Tarih: `2026-07-20`

## İncelenen olay

Run `01KXZYGCQQAC497ESRXSJGZF5K`, iki dakikanın sonunda `ACQUIRE` içindeyken global
timeout ile kesildi. 190 adaydan 18 acquisition tamamlanmış olmasına rağmen henüz
`NORMALIZE` çalışmadığı için kaynak ve claim sayısı sıfır kaldı. Timeout aynı AsyncSession
üzerindeki devam eden commit ile rollback'i çakıştırarak `IllegalStateChangeError` üretti.

## Düzeltilen anlam

`max_wall_minutes` artık bütün run için ölüm süresi değil, yalnız bilgi toplama süresidir.

```text
toplama süresi doldu
        │
        ├─ yeni search başlatma
        ├─ tamamlanmamış acquisition görevlerini iptal et
        └─ tamamlanmış belgeleri koru
                     ↓
NORMALIZE → CHUNK/RETRIEVE → EVIDENCE → AUDIT → SYNTHESIS → EXPORT
```

Son aşamalar toplama süresi dolduktan sonra başlayabilir ve tamamlanmaları beklenir.
Coverage yetersiz kalırsa sonuç `completed_incomplete` olabilir; ancak boş bir kısa yol
raporu yerine eldeki kaynaklar tam kalite zincirinden geçirilir.

## Doğrulama

- Süresi geçmiş run yeni discovery başlatmıyor.
- Cutoff sırasında tamamlanan hızlı belge korunuyor, bekleyen yavaş görev iptal ediliyor.
- `collection_budget_exhausted` olayı completed/total/successful sayılarını kaydediyor.
- Düğüm bazlı güvenlik timeout'u ve pause/cancel kontrolleri korunuyor.
- Tam regresyon: `136 passed`.

### Canlı iki dakikalık tekrar testi

Yeni run: `01KXZZ0D6K20E963CJ9VAJVGN9`

- Toplama bütçesi: 2 dakika.
- Acquisition: 177 adaydan 79'u süre içinde tamamlandı, 78'i başarılı oldu.
- Cutoff sonrasında run `NORMALIZE`, `CHUNK_INDEX`, `EXTRACT_EVIDENCE`, audit ve export
  aşamalarına devam etti.
- Kabul edilen kaynak: 33.
- Çıkarılan claim: 32.
- Üretilen artifact: 17; tam rapor boyutu 17.193 bayt.
- Toplam çalışma süresi: 441,3 saniye. Bunun yalnız ilk iki dakikası bilgi toplamaya
  ayrıldı; kalan süre kalite işleme ve raporlamada kullanıldı.
- Sonuç `completed_incomplete`: rapor üretildi, fakat iki dakikalık toplamanın coverage
  eşiklerini karşılamadığı açıkça raporlandı.
- Worker logunda transaction/rollback hatası oluşmadı.
