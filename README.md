# Research Platform — Agent Gateway

Platform sürümü: `v0.6.9`

Belge sürümü: `3.3`

Son güncelleme: `2026-07-20`

Bilgi toplama katmanının güncel özeti: `COLLECTION_ARCHITECTURE_REPORT.md`.

Recall güvencesi ve citation-frontier kalite paketi: `RESEARCH_QUALITY_V0.6.0_IMPLEMENTATION_REPORT.md`.

Zamansal kapsam ve kaynak kalitesi düzeltmeleri:
`TEMPORAL_AND_RELEVANCE_QUALITY_REPORT.md`.

Codex, Claude ve Telegram erişim mimarisi: `AGENT_GATEWAY_ARCHITECTURE_REPORT.md`.

Ofis ağı kurulumu ve ekip istemci adımları: `OFFICE_TEAM_SETUP.md`.

Ofis sunucusu canlı uygulama ve doğrulama sonuçları:
`OFFICE_SERVER_IMPLEMENTATION_REPORT.md`.

Yerel kontrol paneli kullanımı: `CONTROL_PANEL_GUIDE.md`.

Kontrol paneli operasyon merkezi uygulama raporu:
`CONTROL_PANEL_V0.6.1_IMPLEMENTATION_REPORT.md`.

Coverage recovery uygulaması ve canlı doğrulaması:
`COVERAGE_RECOVERY_IMPLEMENTATION_REPORT.md`.

Güncel Qwen 4B nesil karşılaştırması: `QWEN_4B_GENERATION_BENCHMARK_REPORT.md`.

Nanbeige4.1-3B RTX 4060 kalite tavanı: `NANBEIGE41_3B_BENCHMARK_REPORT.md`.

Model çıktılarının puansız ve vaka-temelli değerlendirme yöntemi:
`QUALITATIVE_MODEL_EVALUATION_METHODOLOGY.md`.

Tarihsel 4B–9B donanım karşılaştırması: `MODEL_HARDWARE_OPTIMIZED_BENCHMARK_REPORT.md`.

İlk sabit-ayar karşılaştırması: `MODEL_HARD_BENCHMARK_REPORT.md`.

Yerel çalışan, çok kaynaklı ve kanıt merkezli derin araştırma platformu. LangGraph araştırma döngüsünü; AgentSearch keşfi; Crawl4AI ise zor sayfalarda içerik edinmeyi yürütür. PostgreSQL araştırma durumu ve kanıt ilişkilerini, MinIO ham/üretilmiş dosyaları, Redis iş kuyruğunu saklar.

## Özellikler

- Protokol kontrollü ve bütçeli araştırma işleri.
- Dokuz kaynak ailesi ve credential-aware connector registry.
- OpenAlex + Semantic Scholar federated akademik keşfi ve DOI-temelli tekilleştirme.
- Zotero Local/Web API üzerinden koleksiyon, attachment ve tam-metin corpus aktarımı.
- PostgreSQL citation graph, provider snapshot ve incremental Zotero sync cursor kayıtları.
- PaperQA2 için varsayılan kapalı, opsiyonel shadow evidence backend'i.
- PostgreSQL düğüm checkpoint'leriyle pause/resume/cancel.
- URL/redirect SSRF koruması ve ayrı Crawl4AI browser container'ı.
- Uzun belgelerde yapı-duyarlı passage üretimi; bölüm ve özgün karakter konumu korunur.
- Alt soru bazlı hybrid lexical+dense retrieval, passage reranking ve komşu bağlam.
- `embeddinggemma:300m-qat-q4_0` ile yerel embedding; model yoksa lexical fallback.
- Passage seviyesinde claim extraction ve claim–quote entailment doğrulaması.
- Kaynak sürümü, SHA-256, acquisition zinciri ve provenance.
- Yapısal coverage gap teşhisi, görev-temelli recovery, acquisition öncesi novelty filtresi,
  resmî-domain doğrulaması ve doygunluk kontrollü çok turlu toplama.
- Claim/evidence ledger, audit ve adversarial review.
- 14 denetlenebilir çıktı; ham veri, sonuç ve birleşik ZIP teslimatları.
- Codex ve Claude için MCP araç katmanı.
- Wi-Fi CIDR allowlist, güçlü bearer token ve yalnız MCP portunu açan ofis sunucusu modu.
- Allowlist korumalı Telegram araştırma botu.
- Servis, kuyruk, aktif run ve log yönetimi için ofis CIDR allowlist korumalı kontrol paneli.
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
- MCP Gateway: `http://localhost:8010/mcp`
- Kontrol Paneli: yerel `http://127.0.0.1:8020`, ofis ağı `http://<sunucu-ip>:8020`

## Ofis ağına açma

API ve veri servislerini dışarı açmadan kimlik doğrulamalı MCP gateway'i ve CIDR korumalı kontrol
panelini mevcut Wi-Fi ağına bağlamak için:

```powershell
.\scripts\initialize_office_server.ps1
.\scripts\start_office_server.ps1
.\scripts\office_server_status.ps1
```

Windows Firewall kuralı yönetici yetkisiyle bir kez eklenir:

```powershell
.\scripts\configure_office_firewall.ps1
```

Ekip istemci kurulumu, otomatik başlatma ve Telegram allowlist akışı
`OFFICE_TEAM_SETUP.md` belgesindedir.

## Agent Gateway

Üç teslimat modu desteklenir:

- `raw`: kaynak sürümleri, provenance ve passage verileri.
- `result`: yerel sentez, claim ledger, evidence matrix ve audit raporları.
- `both`: ham veri ve sonuçların birlikte bulunduğu denetlenebilir paket.

Codex için örnek ayar `examples/codex_mcp_config.toml`, Claude için örnek ayar
`examples/claude_mcp.json` dosyasındadır. MCP token'ı yapılandırma dosyasına açık metin olarak
yazılmamalı, `RESEARCH_MCP_TOKEN` ortam değişkeninden okunmalıdır.

Telegram botu yalnız allowlist yapılandırıldıktan sonra başlatılır:

```powershell
docker compose --profile telegram up -d telegram-bot
```

Bot komutları:

```text
/research [raw|result|both] [dakika] [--hitl] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
```

## Human-in-the-loop (HITL)

Bir run için dört checkpoint bağımsız olarak açılabilir: `planning_questions`,
`plan_review`, `source_review` ve `outline_review`. Checkpoint geldiğinde durum
`awaiting_input` olur. Beş dakika içinde yanıt gelmezse worker belleği tutulmaz;
state PostgreSQL'de korunarak durum `paused` olur. Aynı interaction daha sonra
yanıtlandığında araştırma yeniden kuyruğa alınır ve kullanıcı bekleme süresi çalışma
bütçesinden düşülmez.

API protokol örneği:

```json
"hitl": {
  "planning_questions": true,
  "plan_review": true,
  "source_review": true,
  "outline_review": true
}
```

Yanıt uç noktası `POST /v1/research-runs/{id}/respond` olup gövdede güncel
`interaction_id` ve checkpoint türüne uygun `response` ister. Telegram'da bütün
checkpoint'leri açmak için `/research --hitl <soru>`; bağlı Codex/Claude için MCP
`start_research` HITL bayrakları ve `respond_to_research_checkpoint` aracı kullanılır.

Telegram'da süre hem `/research both --minutes 2 <soru>` hem de kısa biçimde
`/research both 2 <soru>` olarak verilebilir. Süre yazılmazsa bot seçim menüsünü gösterir.

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

Akademik connector'lar:

- `openalex`: Güncel API anahtarı gerektirir; DOI, abstract, OA location, version ve
  reference metadata sağlar.
- `semantic_scholar`: Anahtarsız çalışabilir; üretim için API key ve 1 RPS başlangıç
  profili önerilir.
- `zotero_local`: Zotero masaüstünün `localhost:23119/api` arayüzünü kullanır.
- `zotero_web`: `ZOTERO_USER_ID` veya `ZOTERO_GROUP_ID`; özel kütüphane için API key ister.

Zotero corpus aktarımı:

```powershell
Invoke-RestMethod http://localhost:8000/v1/zotero/sync `
  -Method Post `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"mode":"local","collections":[],"tags":["high-priority"],"limit":100}'
```

PaperQA2 kurulumu opsiyoneldir:

```powershell
.\.venv\Scripts\pip.exe install -e ".[academic]"
```

`PAPERQA2_ENABLED=true` ve `PAPERQA2_SHADOW_MODE=true` olduğunda sonuçları native
pipeline'ın yerine geçmeden `paperqa2_shadow` audit event'i olarak kaydeder.

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
- Ofis modunda yalnız MCP portu Wi-Fi IP'sinde dinler; bearer token ve CIDR allowlist zorunludur.
- Acquisition yalnız standart portlardaki HTTP/HTTPS hedeflerini kabul eder.
- DNS ve her redirect sonrasında public-IP kontrolü yapılır.
- Crawl4AI düşük yetkili, read-only container'da çalışır.
- Kaynak metni güvenilmeyen veri olarak prompt'a alınır.
- Üretimde `.env`, MinIO ve connector anahtarlarını repoya eklemeyin.
