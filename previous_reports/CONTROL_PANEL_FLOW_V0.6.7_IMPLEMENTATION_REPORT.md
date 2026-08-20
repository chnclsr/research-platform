# Kontrol Paneli Pipeline Flow ve İlerleme Görünümü

Platform sürümü: `v0.6.7`

Belge sürümü: `1.0`

Tarih: `2026-07-20`

## Eklenen görünümler

Aktif ve geçmiş run tablolarındaki aşama hücresi artık mevcut düğüm adının altında kompakt
bir ilerleme çubuğu gösterir. Tamamlanan işler yüzde 100, kuyruktaki işler yüzde 0 görünür;
çalışan işler ana pipeline sırasındaki düğüm konumuna göre gösterilir.

Run detay çekmecesine 17 düğümlü LangGraph flow chart eklendi:

```text
INIT → VALIDATE → DECOMPOSE → QUERY PLAN → SEARCH → ACQUIRE → NORMALIZE
→ CHUNK/INDEX → RETRIEVE → EXTRACT → CLAIM ANALYSIS → AUDIT → COVERAGE
→ ADVERSARIAL REVIEW → SYNTHESIZE/EXPORT → COMPLETE
                         ↘ PLAN_RECOVERY ↺ SEARCH
```

## Görsel durumlar

- Yeşil: tamamlanmış düğüm.
- Mavi ve ışıklı nokta: halen çalışan düğüm.
- Sarı: duraklatılmış düğüm.
- Kırmızı: hata veya iptalin gerçekleştiği son düğüm.
- Soluk: henüz çalışmamış veya terminal run'da atlanmış düğüm.

Her düğüm toplam ziyaret sayısını ve geçirilen süreyi gösterir. Böylece coverage recovery
nedeniyle SEARCH/ACQUIRE tekrarlandıysa yalnız son aşama değil, döngü de görünür olur.

## Mobil ve erişilebilirlik

Flow chart dar ekranlarda küçültülmek yerine yatay kaydırılır; düğüm metinleri okunabilir
kalır. Aktif düğüm `aria-current="step"` ile işaretlenir. Run tablosundaki kompakt çubuk
mevcut tablo kolonunu büyütmeden aşama sinyali verir.

## Doğrulama

- Stage→yüzde eşlemesi, terminal yüzde 100 ve queue yüzde 0 test edildi.
- İki kez SEARCH ziyaret edilen recovery senaryosunda ziyaret sayısı ve recovery sinyali test edildi.
- Backend run detail payload'ında aktif flow düğümü doğrulandı.
- Tam pytest: `129 passed`.
- Ruff: başarılı.
