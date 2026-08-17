# Opsiyonel Kaynak Limiti

Platform sürümü: `v0.6.5`

Belge sürümü: `1.0`

Tarih: `2026-07-20`

## Davranış

Kaynak sayısı artık zorunlu bir bütçe değildir. `max_sources: null` olduğunda araştırma,
kaynak adedine ulaştığı için durmaz. Coverage, saturation, tur sayısı veya hard süre
bütçesinden biri araştırmayı bitirene kadar yeni kaynak adaylarını toplamaya devam eder.

Pozitif herhangi bir sayı verilirse bu değer kullanıcı tarafından seçilmiş kaynak tavanı
olarak uygulanır. Şema üzerindeki eski 2.000 ve Telegram üzerindeki eski 150 kaynak üst
sınırları kaldırılmıştır.

## Arayüzler

Telegram varsayılanı kaynak bakımından sınırsızdır:

```text
/research raw araştırma sorusu
```

İsteğe bağlı kullanıcı limiti:

```text
/research raw --minutes 30 --sources 500 araştırma sorusu
```

MCP `start_research` aracında `max_sources` opsiyoneldir. Alan gönderilmez veya `null`
gönderilirse kaynak tavanı uygulanmaz.

## Korunan güvenlik sınırları

- Telegram varsayılan süre bütçesi 20 dakika, üst süre 60 dakikadır.
- Hard wall-clock deadline worker restartlarında sıfırlanmaz.
- Connector başına sonuç sayısı, acquisition eşzamanlılığı ve tur sınırı korunur.
- Coverage yeterli hale gelirse sistem sürenin tamamını gereksiz yere tüketmeden durabilir.

## Doğrulama

- Sınırsız varsayılan protokol ve yüksek kullanıcı limiti test edildi.
- Family target doğrulamasının sınırsız modda yanlış hata üretmediği doğrulandı.
- Tam pytest: `125 passed`.
- Ruff: başarılı.
