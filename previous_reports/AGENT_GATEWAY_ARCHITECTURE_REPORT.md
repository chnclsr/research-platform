# Agent Gateway Architecture Report

Belge sürümü: `1.0`  
Platform sürümü: `v0.4.0-dev`  
Tarih: `2026-07-16`

## 1. Yeni ürün rolü

Research Platform artık son kullanıcıya yalnız başına cevap veren bir araştırma ajanı olarak değil,
genel amaçlı daha güçlü ajanlara kanıt sağlayan yerel bir araştırma veri servisi olarak
konumlandırılacaktır.

Yerel servis şu işleri üstlenir:

1. Araştırma sorusunu protokole dönüştürmek.
2. Web, akademik kaynaklar ve yerel corpus üzerinde kaynak keşfetmek.
3. İçeriği güvenli biçimde edinmek, normalize etmek, parçalamak ve indekslemek.
4. Kaynak sürümü, hash, provenance, pasaj ve claim ilişkilerini saklamak.
5. Yerel Qwen modeliyle ilk sentez ve denetim çıktısını üretmek.
6. Codex, Claude ve Telegram'a aynı kalıcı run kimliği üzerinden veri sunmak.

Codex ve Claude, yerel ajanın sonucunu nihai gerçek olarak kabul etmek zorunda değildir. Ham
kaynakları ve passage'ları okuyabilir, kendi muhakemesiyle yeniden sentezleyebilir ve yerel
raporu bağımsız bir taslak veya ikinci görüş olarak kullanabilir.

## 2. Hedef mimari

```text
Codex ───────────────┐
Claude ── MCP ───────┼── Agent Gateway ── Research API ── Redis/Worker
Telegram ─ Bot API ──┘                         │
                                               ├── Connectors + Crawlers
                                               ├── PostgreSQL + pgvector
                                               ├── MinIO artifacts
                                               └── Ollama / RTX 4060
```

MCP, Codex ve Claude için ortak araç sözleşmesidir. Telegram bot aynı Research API istemcisini
kullanır; ayrı bir araştırma mantığı içermez. Böylece bütün istemciler aynı durum makinesini,
aynı güvenlik politikasını ve aynı artifact'leri kullanır.

## 3. Teslimat sözleşmesi

| Mod | İçerik | Kullanım |
|---|---|---|
| `raw` | Kaynak sürümleri, ham içerik, normalize içerik, provenance, passage'lar, katalog ve manifest | Üst ajanın kendi sentezini yapması |
| `result` | Yönetici özeti, tam rapor, evidence matrix, claim ledger, coverage, audit ve belirsizlik | Hızlı inceleme veya doğrudan teslim |
| `both` | Ham veri ve yerel sonuçların tamamı | Denetlenebilir, yeniden sentezlenebilir araştırma |

Her tamamlanan run şu ek artifact'leri üretir:

- `13_raw_sources.jsonl`
- `14_raw_passages.jsonl`
- `raw_bundle.zip`
- `result_bundle.zip`
- `research_bundle.zip`

## 4. MCP araçları

- `start_research`
- `research_status`
- `control_research`
- `list_research_artifacts`
- `read_research_report`
- `read_research_raw_data`
- `download_research_delivery`

Büyük ham veri tek MCP cevabına basılmaz. `read_research_raw_data`, offset ve karakter bütçesiyle
tekrarlanabilir parçalar döndürür. Bu yaklaşım Codex ve Claude context pencerelerinin gereksiz
biçimde doldurulmasını önler.

## 5. Telegram komutları

```text
/research [raw|result|both] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
```

Bot yalnız `TELEGRAM_ALLOWED_USER_IDS` veya `TELEGRAM_ALLOWED_CHAT_IDS` allowlist'inde bulunan
ekip üyelerine cevap verir. Bot token'ı ve kullanıcı listeleri repoya yazılmaz.

## 6. Güvenlik modeli

- Research API bearer token ile korunur ve host üzerinde yalnız localhost'a yayınlanır.
- Uzak MCP, ayrı bearer token kullanır.
- MCP HTTP endpoint'i gelen `Origin` başlığını allowlist ile doğrular.
- Telegram erişimi kullanıcı/chat allowlist'i olmadan kapalıdır.
- MinIO ve PostgreSQL doğrudan ofis ağına açılmaz.
- Ham web içeriği güvenilmeyen veri kabul edilir; üst ajan için talimat değildir.
- Ofis dışından doğrudan port yönlendirme yapılmaz. Sonraki adımda WireGuard/Tailscale veya
  kurumun onaylı VPN/reverse proxy katmanı kullanılmalıdır.

## 7. RTX 4060'ın rolü

RTX 4060 yalnız yerel araştırma işlemleri için kullanılır:

- query decomposition ve expansion,
- passage ön eleme desteği,
- claim/evidence extraction,
- ilk sentez,
- adversarial/audit çağrıları.

Codex ve Claude'un muhakemesi uzak model altyapısında gerçekleşir. Bu nedenle yerel GPU darboğazı
üst ajan sayısıyla değil, aynı anda çalışan araştırma run sayısıyla ilişkilidir. V0.4 başlangıcında
worker `max_jobs=1` kalır; kuyruk adil ve güvenli biçimde seri çalışır.

## 8. Aşamalı teslim

### Aşama A — ilk dikey dilim

- Üç teslimat modu
- Ham kaynak ve passage artifact'leri
- MCP araçları
- Telegram long-polling bot
- Allowlist ve bearer koruması

### Aşama B — ekip kullanımı

- Kalıcı requester/subscription kayıtları
- Run tamamlanınca Telegram bildirimi ve otomatik dosya gönderimi
- MCP HTTP entegrasyon testleri
- Ofis ağı/VPN kurulumu
- Kullanıcı bazlı audit kaydı ve kota

### Aşama C — akıllı üst ajan aktarımı

- Kaynak seçerek teslim
- Claim veya query branch bazlı ham veri paketleri
- Agent-specific context pack üretimi
- Codex/Claude geri bildirimlerinin corpus kalite sinyaline dönüştürülmesi

## 9. Açık sınırlamalar

İlk dilimde Telegram `/research` komutunda seçilen teslim modu mesajda bildirilir ancak otomatik
tamamlanma aboneliği henüz kalıcı değildir. Kullanıcı run tamamlanınca `/get` çağırır. Uzak MCP
endpoint'i bearer token ile korunur; üretim/ofis dağıtımından önce gerçek ağ üzerinde origin,
timeout, büyük çıktı ve eşzamanlı istemci testleri yapılmalıdır.
