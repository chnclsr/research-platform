# Telegram Pozisyonel Süre Düzeltme Raporu

Belge sürümü: `1.0`

Platform sürümü: `v0.6.9`

Tarih: `2026-07-20`

## Sorun

`/research both 2 <soru>` komutundaki `2`, araştırma sorusunun ilk kelimesi kabul
ediliyor ve bot süre seçim menüsünü yeniden gösteriyordu.

## Düzeltme

- Teslim modundan hemen sonraki tam sayı pozisyonel dakika olarak yorumlanır.
- `1-180` dakika doğrulaması aynen uygulanır.
- Pozisyonel veya `--minutes` süresi varsa araştırma doğrudan başlar.
- Süre yoksa mevcut dört butonlu seçim akışı devam eder.
- Sayıyla başlayan gerçek bir soru için bütün soru tırnak içine alınabilir veya açık
  `--minutes` biçimi kullanılabilir.

## Doğrulama

- `/research both 2 lung cancer detection by CT` → `2 dakika`, soru metni sayı olmadan.
- Süre seçim menüsü açılmadan gateway çağrısı yapılıyor.
- Telegram testleri: `13 passed`.
- Tam regresyon: `135 passed`.
