# Telegram Araştırma Süresi Seçici

Platform sürümü: `v0.6.6`

Belge sürümü: `1.0`

Tarih: `2026-07-20`

## Kullanıcı akışı

Kullanıcı süre belirtmeden `/research [raw|result|both] <soru>` gönderdiğinde run henüz
oluşturulmaz. Bot aşağıdaki Telegram inline keyboard seçeneklerini gösterir:

| Mod | Süre | Kullanım |
|---|---:|---|
| Hızlı | 10 dk | Hızlı tarama ve dar sorular |
| Standart | 30 dk | Dengeli genel araştırma |
| Derin | 120 dk | Geniş ve zor doğrulama işleri |
| Maksimum | 180 dk | En kapsamlı yerel araştırma |

Kullanıcı bir düğmeye bastığında callback doğrulanır, düğmeler kaldırılır ve seçilen süre
ile run oluşturulur. Kaynak sayısı ayrıca belirtilmediyse süreye bağlı sınırsız kalır.

## Güvenlik ve yarış koşulları

- Seçim yalnız komutu yazan Telegram kullanıcısı ve aynı chat tarafından yapılabilir.
- Bekleyen seçim 15 dakika sonra geçersiz olur.
- Pending kayıt seçim anında atomik olarak kaldırılır; çift tıklama ikinci run oluşturmaz.
- Telegram callback 64 byte sınırına uygun kısa, rastgele request kimliği taşır.
- Yetkisiz, süresi geçmiş veya değiştirilmiş callback run başlatmaz.

## Geriye uyumluluk

`/research raw --minutes 45 <soru>` biçimi seçim ekranını atlayarak doğrudan run başlatır.
`--sources N` süre seçimiyle beraber korunur.

## Doğrulama

- Dört butonun callback payload'ları doğrulandı.
- `/research` sonrasında seçim yapılmadan gateway çağrılmadığı doğrulandı.
- Standart düğmesinin 30 dakikalık ve kaynak tavanı olmayan protokol oluşturduğu doğrulandı.
- Tam pytest: `127 passed`.
- Ruff: başarılı.
