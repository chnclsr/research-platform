# Research Platform V1

Platform sürümü: `v0.2.2`

Belge sürümü: `1.3`

Son güncelleme: `2026-07-15`

Bilgi toplama katmanının güncel özeti: `COLLECTION_ARCHITECTURE_REPORT.md`.

RTX 4060'a göre optimize edilmiş model karşılaştırması: `MODEL_HARDWARE_OPTIMIZED_BENCHMARK_REPORT.md`.

İlk sabit-ayar karşılaştırması: `MODEL_HARD_BENCHMARK_REPORT.md`.

Yerel çalışan, çok kaynaklı ve kanıt merkezli derin araştırma platformu. LangGraph araştırma döngüsünü; AgentSearch keşfi; Crawl4AI ise zor sayfalarda içerik edinmeyi yürütür. PostgreSQL araştırma durumu ve kanıt ilişkilerini, MinIO ham/üretilmiş dosyaları, Redis iş kuyruğunu saklar.

## Özellikler

- Protokol kontrollü ve bütçeli araştırma işleri.
- Dokuz kaynak ailesi ve credential-aware connector registry.
- PostgreSQL düğüm checkpoint'leriyle pause/resume/cancel.
- URL/redirect SSRF koruması ve ayrı Crawl4AI browser container'ı.
- Uzun belgelerde yapı-duyarlı passage üretimi; bölüm ve özgün karakter konumu korunur.
- Alt soru bazlı hybrid lexical+dense retrieval, passage reranking ve komşu bağlam.
- `embeddinggemma:300m-qat-q4_0` ile yerel embedding; model yoksa lexical fallback.
- Passage seviyesinde claim extraction ve claim–quote entailment doğrulaması.
- Kaynak sürümü, SHA-256, acquisition zinciri ve provenance.
- Claim/evidence ledger, coverage döngüsü, audit ve adversarial review.
- 12 denetlenebilir çıktı ve tek ZIP paketi.
- Ollama varsayılanı ve OpenAI-compatible alternatif.
- Ollama JSON çağrılarında yapılandırılabilir thinking, context ve output sınırları.
- Langflow için dört sabit kontrol bileşeni.

Paywall aşma, shadow-library erişimi, port tarama veya exploit çalıştırma bilerek desteklenmez.

## Ön koşullar

- Windows 10/11 ve Docker Desktop
- Ollama 0.31+; `qwen3:4b-instruct-2507-q4_K_M`
- Çalışan AgentSearch: varsayılan `http://localhost:3939`
- En az 12 GB boş RAM ve 10 GB disk önerilir

## Hızlı kurulum

Önce mevcut AgentSearch'i başlatın. Ardından PowerShell'de:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

Docker Hub sertifika doğrulaması başarısız olursa kurulum otomatik olarak PostgreSQL/Redis/MinIO'yu Docker'da, API ve worker'ı `.venv` içinde çalıştıran native fallback'e geçer. Bu mod için portlar yalnız loopback üzerinde `5433`, `6380` ve `9000` olarak açılır. Native süreçleri durdurmak için `scripts\stop_native.ps1` kullanılır.

İlk çalıştırmadan önce `.env` içindeki `API_TOKEN` ve `MINIO_SECRET_KEY` değerlerini değiştirin. Servisler:

- API/OpenAPI: `http://localhost:8000/docs`
- Langflow: `http://localhost:7860`
- MinIO Console: `http://localhost:9001`

## API ile araştırma başlatma

```powershell
$token = (Get-Content .env | Select-String '^API_TOKEN=').ToString().Split('=',2)[1]
$protocol = Get-Content .\examples\protocol_core.yaml -Raw
# YAML'ı uygulamada JSON'a dönüştürün veya Swagger UI üzerinden protokolü gönderin.
Invoke-RestMethod http://localhost:8000/v1/connectors `
  -Headers @{ Authorization = "Bearer $token" }
```

Örnek JSON isteği:

```json
{
  "protocol": {
    "title": "Kaynak güvenilirliği araştırması",
    "primary_question": "Araştırma ajanlarında kaynak güvenilirliği nasıl ölçülür?",
    "languages": ["tr", "en"],
    "report_language": "tr",
    "connectors": {
      "profile": "core",
      "included_families": ["web", "academic", "official_legal", "code_data"]
    }
  }
}
```

## Connector profilleri

`core`: web, academic, official/legal ve code/data. `all`: bütün aileler. EPO OPS gibi credential isteyen connector'lar anahtar yoksa `/v1/connectors` sonucunda disabled görünür; araştırmayı durdurmaz.

## Geliştirme

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"
$env:TESTING="true"
.\.venv\Scripts\pytest.exe -q
```

Şema geliştirme ortamında API açılışında oluşturulur. Dağıtım migration'ı:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

## İş durumları

`queued → running → completed|completed_incomplete|failed`. Pause ve cancel istekleri düğüm sınırında uygulanır. Coverage eşiği sağlanmadan bütçe biterse sonuç `completed_incomplete` olur ve eksikler coverage/uncertainty raporunda korunur.

## Güvenlik notları

- API yalnız loopback'e publish edilir ve bearer token ister.
- Acquisition yalnız standart portlardaki HTTP/HTTPS hedeflerini kabul eder.
- DNS ve her redirect sonrasında public-IP kontrolü yapılır.
- Crawl4AI düşük yetkili, read-only container'da çalışır.
- Kaynak metni güvenilmeyen veri olarak prompt'a alınır.
- Üretimde `.env`, MinIO ve connector anahtarlarını repoya eklemeyin.
