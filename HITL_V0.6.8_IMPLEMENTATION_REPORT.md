# Human-in-the-Loop Uygulama Raporu

Belge sürümü: `1.0`

Platform sürümü: `v0.6.8`

Tarih: `2026-07-20`

## Amaç

Valyu DeepResearch HITL yaklaşımındaki dört karar noktasını yerel, denetlenebilir ve
uzun süreli araştırma mimarisine uyarlamak. Valyu servisi bağımlılık olarak eklenmedi;
davranış mevcut FastAPI, PostgreSQL, ARQ, LangGraph, MCP, Telegram ve kontrol paneli
bileşenleri üzerinde yerel olarak uygulandı.

## Akış

```text
DECOMPOSE ── planning_questions ──► BUILD_QUERY_BRANCHES
                                      │
                                  plan_review
                                      ▼
                               SEARCH / ACQUIRE
                                      │
                                  source_review
                                      ▼
                               EVIDENCE / AUDIT
                                      │
                                 outline_review
                                      ▼
                              SYNTHESIZE / EXPORT
```

Her checkpoint protokolde ayrı açılır. Aktif checkpoint `interaction_id`, tür, veri,
oluşturulma ve timeout zamanıyla saklanır. Yanıtın kimliği veya şekli yanlışsa işlem
değiştirilmeden `400/409` döner. Kabul edilen yanıt `hitl_history` içine eklenir.

## Davranış

- `planning_questions`: kapsam ve öncelik yanıtlarını sorgu planına katar.
- `plan_review`: planı onaylatır veya verilen değişikliği yeni sorgu dalına dönüştürür.
- `source_review`: kaynakları domain, sayı ve ortalama relevance ile gösterir; dışlanan
  domainlerin belgeleri evidence aşamasına geçirilmez, ham provenance korunur.
- `outline_review`: rapor yapısını onaylatır veya sentez promptuna yapısal yönlendirme ekler.
- Beş dakika yanıt gelmezse durum `paused` olur; checkpoint ve state kaybolmaz.
- Yanıt sonrası iş tekrar kuyruğa alınır. İnsan bekleme süresi `max_wall_minutes`
  araştırma bütçesine dahil edilmez.

## Erişim yüzeyleri

- REST: run oluşturma/status ve `POST .../respond`.
- Kontrol paneli: tip bazlı form, onay/red ve domain checkbox'ları.
- Telegram: `/research --hitl`, `/status`, `/respond`.
- MCP: dört HITL bayrağı ve `respond_to_research_checkpoint`.

## Doğrulama

- Response schema ve interaction kimliği doğrulaması.
- Checkpoint'in `awaiting_input` üretmesi ve yanıt geçmişini tekrar kullanması.
- Timeout sonrası state korunarak `paused` geçişi.
- Gateway'in kimlik doğrulamalı respond çağrısı.
- Tam regresyon paketi: `134 passed`.

Kaynak yaklaşım: [Valyu Human-in-the-Loop](https://docs.valyu.ai/guides/deepresearch-hitl).
