# Telegram Gemini Hazırlık Yolu — v0.16.0

**Tarih:** 2026-08-28
**Dal:** `developments-supplementer`

## Amaç ve sınır

Telegram'dan açılan bir araştırmanın kullanıcıyla konuşulan hazırlık kısmı dış Gemini
Developer API üzerinden yürür; kanıt toplama, değerlendirme ve sentez yerel Qwen'de kalır.
Gemini yalnız şu çağrıları alır: araştırma diline çeviri, kısa koşu etiketi, alt soru ve
kavram ayrıştırması, kapsam soruları, sorgu dalları, plan gösterim çevirisi ve strateji
notu. Plan reddi `DECOMPOSE`'a döndüğü için revizyonlar da aynı yolu izler.

İstenen `gemini-1.5-flash` 29 Eylül 2025'te Google tarafından kapatıldı. İlk uygulama
hedefi `gemini-2.5-flash` idi; canlı anahtar doğrulamasında Google bu modeli yeni
kullanıcılara kapattığını ve `gemini-3.6-flash` kullanılmasını istediğini bildirdi. Bu
nedenle sabit varsayılan `gemini-3.6-flash` seçildi. Kimlik ortamdan
`GEMINI_PREPARATION_MODEL` ile değiştirilebilir; `latest` gibi sessizce değişen bir alias
kullanılmaz.

## Mimari ve güvenlik

`ResearchRunCreate.invocation_source` geriye uyumlu bir enumdur; alanı göndermeyen mevcut
istemciler `api` sayılır. Telegram gateway'i `telegram` gönderir ve `for_actor()` kopyası bu
değeri korur. Repository değeri `research_runs.state` içine yazar; checkpoint ve plan
revizyonları boyunca yaşar, yeni kolon veya migration gerektirmez.

Telegram kaynağı ayrı bir dış kotayı seçtiğinden API bunu yalnız servis token'ı ile birlikte
`X-Actor-User` gönderen çağrıdan kabul eder. Kullanıcı API anahtarının yalnız payload'a
`telegram` yazarak Gemini kotasını tüketmesine izin verilmez.

Pipeline iki sağlayıcı taşır: genel `llm` mevcut Ollama/Qwen sağlayıcısıdır;
`preparation_llm` yalnız özellik açık, koşu kaynağı Telegram olduğunda seçilir. Gemini
anahtarı `x-goog-api-key` başlığındadır; URL'ye, metriğe veya hata metnine girmez. Yanıt
`application/json` istenir ve ortak JSON ayrıştırıcısından geçer.

## Hata ve işletim davranışı

Özellik varsayılan kapalıdır. Açıkken eksik anahtar worker pipeline'ı kurulurken açık hata
verir. `429` ile geçici `5xx` yanıtları `Retry-After` veya sınırlı üstel gecikmeyle yeniden
denenir. Etiket başarısızlığı deterministik soru slug'ına, çeviri mevcut dil geri dönüşüne,
kapsam sorusu sabit seçeneklere dönebilir; bunlar başka bir LLM çağrısı değildir. Zorunlu
ayrıştırma ve sorgu üretimi Qwen'e sessizce aktarılmaz.

Kurulum anahtarları:

```env
TELEGRAM_PREPARATION_LLM_ENABLED=true
GEMINI_API_KEY=<secret>
GEMINI_API_URL=https://generativelanguage.googleapis.com
GEMINI_PREPARATION_MODEL=gemini-3.6-flash
GEMINI_PREPARATION_TIMEOUT_S=60
GEMINI_PREPARATION_MAX_RETRIES=2
```

Free Tier girdilerinin Google ürünlerini geliştirmek için kullanılabileceği `.env.example`
yanında belirtilmiştir. Gizli veya ticari veri için veri kullanım koşulları ayrıca
değerlendirilmeden özellik açılmamalıdır.

## Doğrulama

Sağlayıcı testleri JSON sözleşmesini, anahtarın URL dışında kalmasını, kullanım metriklerini,
`Retry-After` yeniden denemesini, hata metni redaksiyonunu ve eksik anahtar kapısını kapsar.
API/gateway testleri kaynak kaydını, protokole karışmamasını ve actor kopyasında korunmasını;
pipeline/HITL testleri mevcut plan davranışının korunmasını doğrular.

Hedefli saf paket `33 passed`; son kod değişikliğinden sonraki zorunlu tam kapı
`599 passed, 1 warning` sonucunu verdi. Uyarı bu değişiklikten eski Starlette/httpx
deprecation uyarısıdır. Değişen satırlarda yeni Ruff ihlali yoktur; `llm.py` içinde bu
çalışmadan eski iki geniş `except` ihlali durur ve temiz taban varmış gibi raporlanmamıştır.

Canlı anahtar eklendikten sonra model listesi `HTTP 200` ile okundu. İlk
`gemini-2.5-flash` üretim denemesi Google'ın “new users” için modelin kapalı olduğunu
bildiren `404 NOT_FOUND` yanıtını verdi; varsayılan bu kanıtla `gemini-3.6-flash` olarak
değiştirildi. Yeni model hosttan ve worker containerından ayrı ayrı `HTTP 200` üretti.
Model değişikliğinin hedefli regresyon paketi `66 passed, 1 warning` sonucunu verdi.

`api`, `worker` ve profil arkasındaki `telegram-bot` rebuild edildi. Container içi doğrulama
üçünde de v0.16.0 gösterdi; API ve worker Gemini ayarını açık, anahtarı mevcut ve modeli
`gemini-3.6-flash` okudu, worker `GeminiProvider` kurdu, Telegram gateway'i kaynağı
`telegram` taşıdı. `/health` bütün bağımlılıkları `ok`, Docling cihazını `cuda` bildirdi;
başlangıç loglarında hata görülmedi.
