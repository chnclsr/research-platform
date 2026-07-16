# Coverage Recovery ve Çok Turlu Bilgi Toplama Yeniden Tasarımı

Belge sürümü: `1.0`  
Platform sürümü: `v0.4.0-dev`  
Tarih: `2026-07-16`  
Dayanak run: `01KXNDKV20RK81PGWSRWS33YR7`

## 1. Yönetici kararı

Mevcut sistem eksikliği doğru tespit etmekte, fakat eksikliği yeni ve hedefli bilgi toplama
görevlerine dönüştürememektedir. Sorun yalnız query expansion prompt'u değildir. Birbiriyle
bağlantılı altı mimari hata bulunmaktadır:

1. Coverage sonucu yapılandırılmış bir `gap` nesnesine çevrilmiyor.
2. İlk tur neredeyse bütün kaynak bütçesini tüketiyor.
3. Adaylar mevcut corpus'a karşı acquisition öncesinde elenmiyor.
4. Coverage, edinilmiş yeni kanıt yerine arama adaylarını sayıyor.
5. Yeni kaynak gelmediğinde eski dokümanlar tekrar chunk ve extraction işlemlerinden geçiyor.
6. Audit yalnız bütün arama turları bittikten sonra yapıldığı için ara turlarda audit coverage
   sürekli sıfır kalıyor.

Çözüm, `EXPAND_QUERIES` düğümünü büyütmek değil; onu `DIAGNOSE_GAPS → PLAN_RECOVERY_MISSIONS`
şeklinde iki aşamalı bir recovery planner ile değiştirmektir.

## 2. Canlı run kanıtları

### Tur davranışı

| Tur | Connector çağrısı | Arama sonucu | Acquisition | Yeni kaynak | İşlenen passage |
|---|---:|---:|---:|---:|---:|
| 1 | 112 | 524 | 12 | 11 | 127 |
| 2 | 98 | 420 | 1 | 0 | 9 |
| 3 | 98 | 420 | 1 | 0 | 9 |
| 4 | 98 | 380 | 1 | 0 | 9 |

İkinci, üçüncü ve dördüncü turlarda edinilen URL aynıydı:

```text
http://arxiv.org/abs/2606.30317v1
```

Bu nedenle sonraki turlar yeni bilgi toplamadı. Aynı kaynak yeniden acquisition, chunking,
embedding, retrieval ve claim extraction aşamalarından geçti.

### Corpus dağılımı

```text
academic: 8
web:      3
official: 0
code/data:0
```

`official_registry` arama sonuçları üretmiş olmasına rağmen connector herhangi bir domain
kısıtına sahip değildir. Genel AgentSearch ile aynı URL'leri döndürmüş, deduplication sırasında
ilk görülen `agentsearch_web` kaydı korunmuştur.

### Matematiksel coverage hatası

Mevcut aile coverage formülü:

```python
family_score = min(1.0, family_source_count / 5.0)
coverage = average(family_scores)
```

Canlı testte dört aile ve `max_sources=12` kullanıldı. Her kaynak yalnız bir aileye ait olduğundan
ulaşılabilecek teorik maksimum:

```text
12 / (4 aile × 5 kaynak) = 0.60
```

Hedef `0.80` olduğundan run başlamadan önce bile başarı matematiksel olarak imkânsızdı.

## 3. Yeni kontrol döngüsü

```text
SEARCH_MISSIONS
→ NOVELTY_PREFILTER
→ ACQUIRE_NEW_ONLY
→ NORMALIZE_AND_INDEX_NEW_ONLY
→ RETRIEVE_FOR_OPEN_GAPS
→ EXTRACT_BOUNDED_EVIDENCE
→ INCREMENTAL_AUDIT
→ DIAGNOSE_GAPS
    ├─ çözülebilir gap → PLAN_RECOVERY_MISSIONS → SEARCH_MISSIONS
    ├─ exhausted gap  → kayda geçir
    └─ yeterli/bütçe → SYNTHESIZE
```

Temel değişiklik: Bir sonraki tur “daha fazla ara” komutu almaz. Her tur yalnız açık bir gap'i
kapatmak üzere tanımlanmış görevlerden oluşur.

## 4. Yeni veri modelleri

### `CoverageGap`

```python
class CoverageGap(BaseModel):
    id: str
    dimension: Literal[
        "source_family", "authority", "query_branch",
        "claim_support", "counterevidence", "version"
    ]
    topic: str
    branch_id: str | None
    claim_ids: list[str]
    missing_family: SourceFamily | None
    required_authority: Literal[
        "official", "primary", "peer_reviewed", "independent", "any"
    ]
    evidence_direction: Literal["supports", "contradicts", "either"]
    target_entities: list[str]
    target_domains: list[str]
    preferred_connectors: list[str]
    minimum_novel_sources: int
    priority: float
    attempts: int
    status: Literal["open", "satisfied", "exhausted", "blocked"]
    failure_reasons: list[str]
```

### `SearchMission`

```python
class SearchMission(BaseModel):
    id: str
    gap_id: str
    query: str
    connector_ids: list[str]
    domain_allowlist: list[str]
    domain_denylist: list[str]
    required_family: SourceFamily | None
    required_authority: str
    result_limit: int
    acquisition_slots: int
    novelty_required: bool = True
```

### `RoundLedger`

Her tur için aşağıdaki değerler kalıcı tutulmalıdır:

- planlanan mission'lar,
- aranan query/connector/domain kombinasyonları,
- bulunan toplam aday,
- daha önce görülen aday,
- yeni aday,
- acquisition başarısı,
- yeni `Source` ve `SourceVersion` sayısı,
- gap kapanma miktarı,
- harcanan süre ve LLM token'ı.

Bu kayıt, aynı başarısız stratejinin tekrar edilmesini engeller.

## 5. Gap teşhisi

Coverage yalnız tek bir toplam oran üretmemelidir. Ayrı gap'ler çıkarılmalıdır.

### Kaynak ailesi gap'i

```text
İstenen: official_legal
Mevcut: 0
Gap: en az 2 resmî/primary kaynak
```

### Otorite gap'i

Kullanıcı “resmî dokümantasyona göre” dediğinde bu ifade protokol seviyesinde bir constraint'e
dönüşmelidir:

```yaml
authority_policy:
  minimum_authority: official
  strict_for_major_claims: true
  discovery_sources_may_be_non_authoritative: true
```

Bloglar yeni query veya domain keşfetmek için kullanılabilir; major claim evidence'i olamaz.

### Claim support gap'i

Her major claim için:

- destekleyen bağımsız kaynak sayısı,
- çelişen kaynak sayısı,
- kaynak otoritesi,
- claim'in hangi query branch'e ait olduğu

hesaplanır. “Destek az” bilgisi genel sorguya değil ilgili claim/topic mission'ına dönüşür.

## 6. Entity ve resmî domain çözümleme

`official_registry` mevcut haliyle genel web aramasının ikinci kopyasıdır. Bunun yerine
`OfficialDomainResolver` eklenmelidir.

### Deterministik kayıt

```yaml
known_entities:
  model_context_protocol:
    domains: [modelcontextprotocol.io]
  openai_codex:
    domains: [developers.openai.com, openai.com]
  anthropic_claude_code:
    domains: [docs.anthropic.com, code.claude.com, anthropic.com]
  telegram_bot_api:
    domains: [core.telegram.org]
```

### Genel konular

Bilinen kayıt yoksa:

1. Sorudan kurum/ürün/standart varlıkları çıkarılır.
2. Kurumun doğrulanmış ana domain'i bulunur.
3. Domain redirect ve sertifika bilgisi kontrol edilir.
4. Domain kullanıcı tanımlı allowlist veya doğrulanmış registry'ye kaydedilir.
5. Recovery mission yalnız ilgili domainlerde çalıştırılır.

LLM domain önerebilir fakat tek başına domain'i güvenilir ilan edemez.

## 7. Query expansion yerine mission planning

Mevcut:

```text
sub-question + "counter evidence"
sub-question + "primary source"
```

Yeni örnek:

```yaml
- gap: mcp_transport_security
  connector: agentsearch_web
  domain: modelcontextprotocol.io
  query: Streamable HTTP security Origin authentication

- gap: codex_mcp_configuration
  connector: agentsearch_web
  domain: developers.openai.com
  query: Codex MCP server config.toml bearer token

- gap: claude_mcp_authentication
  connector: agentsearch_web
  domain: code.claude.com
  query: Claude Code remote MCP HTTP Authorization header

- gap: telegram_bot_security
  connector: agentsearch_web
  domain: core.telegram.org
  query: Telegram Bot API webhook secret token getUpdates security
```

Mission planner önce deterministik şablonlar uygular. LLM yalnız query varyantı ve eşanlamlı
üretiminde kullanılır.

## 8. Connector seçimini daraltma

Mevcut sistem her query'yi bütün etkin connector'lara gönderiyor. Canlı run ilk turda 112,
sonraki turlarda 98 çağrı yaptı.

Yeni router:

| Mission türü | Connector |
|---|---|
| Resmî ürün/standart dokümanı | domain-filtered AgentSearch |
| Akademik güvenlik çalışması | OpenAlex, Semantic Scholar, arXiv |
| Kod/repository | GitHub exact repository/code search |
| Mevzuat | ilgili hukuki API/domain |
| Karşı kanıt | aynı aile + bağımsız domain |

Bir mission varsayılan olarak en fazla iki veya üç connector kullanmalıdır.

## 9. Kaynak bütçesi yeniden tasarımı

### İlk tur sınırı

İlk tur bütün bütçeyi kullanamaz:

```python
round_1_cap = min(
    ceil(max_sources * 0.40),
    configured_round_cap,
)
```

`max_sources=12` için ilk tur en fazla beş yeni kaynak alır.

### Recovery rezervi

```text
%40 discovery
%40 gap recovery
%20 adversarial/counterevidence
```

Kullanılmayan rezerv sonraki bölüme aktarılabilir.

### Aile ve otorite kotası

Mission slotları toplam skora göre tek havuzdan seçilmez. Örneğin:

```yaml
round_1:
  web: 2
  academic: 2
  official: 1
round_2:
  official: 2
  code_data: 1
  open_claim_support: 2
```

### Feasibility validation

Run başlamadan önce coverage hedefinin bütçeyle mümkün olup olmadığı doğrulanmalıdır.

```python
required_sources = sum(target.minimum_sources for target in family_targets)
if required_sources > max_sources:
    reject_or_normalize_protocol()
```

## 10. Acquisition öncesi gerçek novelty filtresi

Yeni adaylar yalnız tur içi değil, bütün corpus'a karşı karşılaştırılmalıdır:

1. DOI/PMID/arXiv/patent/ISBN
2. canonical URL
3. resolved final URL
4. content hash biliniyorsa hash
5. title-author-year fingerprint

Mevcut bir kaynağa karşılık gelen aday acquisition slotu tüketmez.

```python
novel_candidates = await repo.filter_novel_candidates(run_id, candidates)
```

Eğer mission sıfır yeni aday üretirse:

- acquisition/chunk/extraction çalıştırılmaz,
- mission failure ledger'a yazılır,
- farklı domain/query/connector stratejisi denenir,
- aynı strateji aynı run içinde tekrar edilmez.

## 11. Yalnız yeni veriyi işleme

Pipeline state şu kimlikleri taşımalıdır:

- `new_source_ids`
- `new_source_version_ids`
- `new_passage_ids`
- `processed_passage_ids`
- `audited_claim_ids`

`CHUNK_INDEX`, yalnız yeni source version'ları işler.  
`EXTRACT_EVIDENCE`, yalnız daha önce işlenmemiş passage'ları işler.

Yeni kaynak yoksa akış:

```text
SEARCH → NOVELTY_PREFILTER → GAP_REPLAN
```

olmalıdır; `ACQUIRE → CHUNK → EXTRACT` zinciri çalışmamalıdır.

## 12. Claim üretiminin sınırlandırılması

172 claim, yalnız 16 ilk-tur passage için aşırı yüksektir.

### Extraction sözleşmesi

- Passage başına en fazla 2 major ve 2 minor claim.
- Yalnız açık query branch'lerden birini doğrudan cevaplayan claim.
- Navigasyon, öneri, pazarlama, içerik listesi ve “şunu kurun” türü cümleler dışlanır.
- Claim'in bağlı olduğu `branch_id` zorunludur.
- Claim quote ile aynı anlama sahip olmalı fakat salt cümle kopyası olmamalıdır.

### Pre-save relevance

Claim veritabanına yazılmadan önce deterministik eşik uygulanır:

```python
if branch_relevance < 0.35:
    reject
```

### Deduplication

- normalize metin benzerliği,
- embedding cosine similarity,
- aynı passage/quote,
- aynı subject-predicate-object yapısı

birlikte kullanılmalıdır. Benzer claim'ler yeni claim yerine mevcut claim'e yeni evidence link
olarak eklenmelidir.

## 13. Audit'in döngü içine alınması

Mevcut akışta `AUDIT` yalnız arama bitince çalışır. Bu nedenle ara turlarda
`claim_audit_coverage=0` kaçınılmazdır ve coverage bu sıfırı yeni arama gerekçesi sayar.

Yeni akış:

```text
ANALYZE_CLAIMS → INCREMENTAL_AUDIT → DIAGNOSE_GAPS
```

Audit her tur yalnız yeni/değişen claim'leri işler. Coverage bundan sonra hesaplanır.

## 14. Coverage metriklerinin düzeltilmesi

### Aile coverage

Sabit “aile başına beş kaynak” yerine protokolde açık hedef:

```yaml
family_targets:
  official_legal:
    minimum_sources: 2
    weight: 0.35
  web:
    minimum_sources: 1
    weight: 0.10
  academic:
    minimum_sources: 2
    weight: 0.30
  code_data:
    minimum_sources: 1
    weight: 0.25
```

Coverage yalnız ilgili, edinilmiş ve kalite eşiğini geçen kaynakları sayar.

### Query branch coverage

Şu anda arama adayları sayılıyor. Yeni tanım:

```text
Bir branch covered sayılırsa:
- en az bir yeni edinilmiş source version,
- en az bir ilgili passage,
- en az bir audit edilmiş evidence link
bulunmalıdır.
```

### Authority coverage

“Resmî kaynak” sorularında ayrı metrik:

```text
official_evidence_major_claims / all_major_claims
```

### Saturation

Saturation toplam kaynak sayısına değil mission bazında ölçülür:

- yeni aday oranı,
- yeni source version oranı,
- yeni evidence oranı.

Aynı mission iki farklı stratejide sonuç üretmezse `exhausted` olabilir. Bu başarısızlık
“araştırma yeterli” anlamına gelmez.

## 15. Çıktı modlarının pipeline davranışını değiştirmesi

Yeni ürün rolü nedeniyle teslimat modu yalnız ZIP seçimi olmamalıdır.

| Mod | Çalışacak aşamalar |
|---|---|
| `raw` | discovery, acquisition, normalization, chunk/index, provenance |
| `result` | bütün aşamalar |
| `both` | bütün aşamalar + ham paket |

`raw` modunda claim extraction ve synthesis zorunlu değildir. Böylece üst ajan yalnız güvenilir
ham veri istediğinde RTX 4060 gereksiz yere yüzlerce extraction çağrısı yapmaz.

## 16. Synthesis context güvenliği

Canlı run synthesis çağrısı `HTTPStatusError` ile başarısız oldu. Exporter 8K context modeline
50.000 karaktere kadar claim metni gönderebiliyor.

Çözüm:

1. Karakter değil gerçek token bütçesi kullan.
2. Yalnız supported ve yüksek öncelikli qualified claim'leri seç.
3. Claim'leri topic/branch bazında cluster et.
4. Önce cluster özeti, sonra final synthesis üret.
5. Context taşarsa otomatik olarak map-reduce senteze geç.

## 17. Uygulama sırası

### Aşama 1 — tekrar ve bütçe hatasını kapat

- Corpus-level novelty prefilter
- `max_new_sources_per_round`
- Recovery budget reserve
- Yalnız yeni source version/passage işleme
- Yeni kaynak yoksa extraction'ı atlama

Bu aşama en fazla maliyet ve tekrar sorununu çözer.

### Aşama 2 — gap planner

- `CoverageGap`
- `SearchMission`
- `RoundLedger`
- Mission-based connector router
- Resmî domain resolver

### Aşama 3 — evidence kalitesi

- Bounded claim extraction
- Pre-save branch relevance
- Semantic claim clustering
- Incremental audit

### Aşama 4 — coverage ve sentez

- Feasible family targets
- Acquired-evidence branch coverage
- Authority coverage
- Token-budgeted synthesis

## 18. Kabul testleri

### Resmî dokümantasyon golden testi

Soru:

```text
Codex, Claude Code ve Telegram için güvenli MCP gateway nasıl kurulmalıdır?
```

Zorunlu sonuç:

- `modelcontextprotocol.io`
- `developers.openai.com`
- `code.claude.com` veya `docs.anthropic.com`
- `core.telegram.org`

Her biri corpus'a girmeli; üçüncü taraf bloglar major evidence olarak kullanılmamalıdır.

### Novelty testi

Aynı arama sonucu ikinci turda gelirse:

- acquisition çağrısı yapılmamalı,
- passage sayısı artmamalı,
- LLM extraction çağrısı yapılmamalı.

### Budget testi

`max_sources=12`, dört aile hedefi ve coverage `0.80` verildiğinde sistem:

- hedefi normalize etmeli veya
- protokolü “ulaşılamaz coverage hedefi” hatasıyla reddetmelidir.

### Recovery testi

İlk turda official kaynak yoksa ikinci tur:

- yalnız official gap mission'larını çalıştırmalı,
- domain-filtered query üretmeli,
- en az bir novel official kaynak edinmelidir.

### Claim testi

16 passage için:

- varsayılan major claim sayısı 32'yi geçmemeli,
- pazarlama/navigasyon ifadeleri claim olmamalı,
- tekrar turunda yeni passage yoksa claim sayısı değişmemelidir.

## 19. Başarı ölçütü

Bu yeniden tasarım başarılı sayılacaktır, eğer:

- ikinci tur ilk turdaki belirli gap'i hedefliyorsa,
- her acquisition slotu novel aday için kullanılıyorsa,
- aynı source version yeniden işlenmiyorsa,
- coverage değerleri yalnız edinilmiş ve audit edilmiş evidence'a dayanıyorsa,
- resmî kaynak talebi resmî domain evidence'ı olmadan başarılı sayılmıyorsa,
- sonuç üretilemediğinde sistem “hangi gap neden kapatılamadı” bilgisini açıkça raporluyorsa.
