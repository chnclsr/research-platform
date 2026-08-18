# Geliştirme Raporları

Önceki milestone'ların uygulama raporları. Bunlar **tarihsel kayıt**tır — o dönemin
kararlarını, gerekçelerini ve doğrulamalarını içerirler; güncel durumu tarif etmezler.

Aktif geliştirme raporu depo kökündedir:
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](../DEVELOPMENTS_IMPLEMENTATION_REPORT.md).
Açık işler [OPEN_ITEMS.md](../OPEN_ITEMS.md) dosyasındadır.

## Yeni değişiklik nereye yazılır

- **Küçük değişiklikler** kökteki `DEVELOPMENTS_IMPLEMENTATION_REPORT.md`'ye **bölüm**
  olarak eklenir.
- **Büyük değişiklikler** — şema göçü içeren veya birden çok servisi kapsayanlar — bu
  klasörde **sürümlü kendi raporunu** alır ve aşağıdaki tabloya işlenir. Kökteki rapora
  yalnız tek satırlık bir işaretçi konur.

İlk örneği v0.10.0 kullanıcı kimliği çalışmasıdır.

## Nasıl kullanılır

Bir alana dokunmadan önce o alanın raporuna göz atın. Raporlar çoğu zaman **neden öyle
yapıldığını** açıklar; kod yalnız ne yapıldığını gösterir. Örneğin iptal davranışını
değiştirecekseniz `CANCELLATION_RELIABILITY_V0.6.3` raporundaki hard-timeout gerekçesini
bilmeden yaptığınız değişiklik o güvenliği geri alabilir.

## Aşılmış bir madde bulursanız: silmeyin, işaretleyin

Bu raporlar zamanla güncel koddan sapar — hem sonraki geliştirmeler hem de bu belgelerin
tanım gereği o günün durumunu anlatması yüzünden. Aşılmış bir iddia gördüğünüzde **metni
silmeyin veya düzeltmeyin.** Tarihsel iddia, raporun değerinin ta kendisidir; bir kararın
neden alındığını ancak o günkü hâliyle anlatabilir.

Bunun yerine ilgili maddenin altına kısa bir not düşün:

```markdown
> **Not (TARİH):** Bu madde artık ... nedeniyle kısmen/tamamen geçerli değil.
> Ayrıntı için DEVELOPMENTS_IMPLEMENTATION_REPORT.md N. bölüm ve OPEN_ITEMS.md M. madde.
```

Böylece okuyan yanılmaz, kayıt bozulmaz. Mevcut örnekler:
[HITL_V0.6.8](HITL_V0.6.8_IMPLEMENTATION_REPORT.md) (checkpoint state'i) ve
[COLLECTION_ARCHITECTURE](COLLECTION_ARCHITECTURE_REPORT.md) (edinim zinciri).

## Sürüme göre

| Sürüm | Rapor | Konu |
|---|---|---|
| v0.2.0 | [QUALITY_IMPROVEMENT_REPORT](QUALITY_IMPROVEMENT_REPORT.md) | Araştırma kalitesi iyileştirmesi |
| v0.3.0 | [ACADEMIC_SOURCE_INTEGRATION_REPORT](ACADEMIC_SOURCE_INTEGRATION_REPORT.md) | Akademik kaynak katmanı |
| v0.3.0 | [COLLECTION_ARCHITECTURE_REPORT](COLLECTION_ARCHITECTURE_REPORT.md) | Bilgi toplama mimarisi |
| v0.4.0 | [V0.4.0_INITIAL_IMPLEMENTATION_REPORT](V0.4.0_INITIAL_IMPLEMENTATION_REPORT.md) | İlk uygulama |
| v0.4.3 | [OFFICE_SERVER_IMPLEMENTATION_REPORT](OFFICE_SERVER_IMPLEMENTATION_REPORT.md) | Ofis sunucusu kurulumu |
| v0.4.3 | [OFFICE_QUEUE_INCIDENT_REPORT](OFFICE_QUEUE_INCIDENT_REPORT.md) | Kuyruk olayı ve düzeltmesi |
| v0.5.1 | [TEMPORAL_AND_RELEVANCE_QUALITY_REPORT](TEMPORAL_AND_RELEVANCE_QUALITY_REPORT.md) | Zamansal kapsam ve kaynak kalitesi |
| v0.5.3 | [RESEARCH_COLLECTION_QUALITY_RESEARCH_REPORT](RESEARCH_COLLECTION_QUALITY_RESEARCH_REPORT.md) | Toplama kalitesi araştırması |
| v0.6.0 | [RESEARCH_QUALITY_V0.6.0_IMPLEMENTATION_REPORT](RESEARCH_QUALITY_V0.6.0_IMPLEMENTATION_REPORT.md) | Kalite paketi |
| v0.6.1 | [CONTROL_PANEL_V0.6.1_IMPLEMENTATION_REPORT](CONTROL_PANEL_V0.6.1_IMPLEMENTATION_REPORT.md) | Kontrol paneli |
| v0.6.2 | [RESEARCH_EVIDENCE_QUALITY_V0.6.2_IMPLEMENTATION_REPORT](RESEARCH_EVIDENCE_QUALITY_V0.6.2_IMPLEMENTATION_REPORT.md) | Kanıt kalitesi |
| v0.6.3 | [CANCELLATION_RELIABILITY_V0.6.3_IMPLEMENTATION_REPORT](CANCELLATION_RELIABILITY_V0.6.3_IMPLEMENTATION_REPORT.md) | İptal ve worker kurtarma |
| v0.6.4 | [EXECUTION_BUDGET_V0.6.4_IMPLEMENTATION_REPORT](EXECUTION_BUDGET_V0.6.4_IMPLEMENTATION_REPORT.md) | Çalışma süresi bütçesi |
| v0.6.5 | [OPTIONAL_SOURCE_LIMIT_V0.6.5_IMPLEMENTATION_REPORT](OPTIONAL_SOURCE_LIMIT_V0.6.5_IMPLEMENTATION_REPORT.md) | Opsiyonel kaynak limiti |
| v0.6.6 | [TELEGRAM_DURATION_PICKER_V0.6.6_IMPLEMENTATION_REPORT](TELEGRAM_DURATION_PICKER_V0.6.6_IMPLEMENTATION_REPORT.md) | Telegram süre seçici |
| v0.6.7 | [CONTROL_PANEL_FLOW_V0.6.7_IMPLEMENTATION_REPORT](CONTROL_PANEL_FLOW_V0.6.7_IMPLEMENTATION_REPORT.md) | Panel pipeline görünümü |
| v0.6.8 | [HITL_V0.6.8_IMPLEMENTATION_REPORT](HITL_V0.6.8_IMPLEMENTATION_REPORT.md) | Human-in-the-loop |
| v0.6.9 | [TELEGRAM_POSITIONAL_DURATION_V0.6.9_REPORT](TELEGRAM_POSITIONAL_DURATION_V0.6.9_REPORT.md) | Telegram pozisyonel süre |
| v0.6.10 | [GRACEFUL_COLLECTION_CUTOFF_V0.6.10_REPORT](GRACEFUL_COLLECTION_CUTOFF_V0.6.10_REPORT.md) | Toplama bütçesi kesimi |
| v0.7.0 | [LITERATURE_RECALL_V0.7.0_IMPLEMENTATION_REPORT](LITERATURE_RECALL_V0.7.0_IMPLEMENTATION_REPORT.md) | Yüksek-recall literatür tarama |
| v0.7.1 | [WORD_REPORT_EXPORT_V0.7.1_IMPLEMENTATION_REPORT](WORD_REPORT_EXPORT_V0.7.1_IMPLEMENTATION_REPORT.md) | Word dışa aktarım |
| v0.7.2 | [WORD_REPORT_AND_RECALL_V0.7.2_IMPLEMENTATION_REPORT](WORD_REPORT_AND_RECALL_V0.7.2_IMPLEMENTATION_REPORT.md) | Word raporu ve recall |
| v0.8.0 | [SYNTHESIS_REPORT_PIPELINE_V0.8.0_IMPLEMENTATION_REPORT](SYNTHESIS_REPORT_PIPELINE_V0.8.0_IMPLEMENTATION_REPORT.md) | LLM sentez pipeline'ı |
| v0.9.0 | [FIGURE_INTELLIGENCE_V0.9.0_IMPLEMENTATION_REPORT](FIGURE_INTELLIGENCE_V0.9.0_IMPLEMENTATION_REPORT.md) | Kaynak figürü anlama |
| v0.9.1 | [SOURCE_FIGURE_EMBEDDING_V0.9.1_IMPLEMENTATION_REPORT](SOURCE_FIGURE_EMBEDDING_V0.9.1_IMPLEMENTATION_REPORT.md) | Figürü Word raporuna yerleştirme |
| v0.10.0 | [MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT](MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md) | Kullanıcı kimliği ve koşu sahipliği |
| — | [AGENT_GATEWAY_ARCHITECTURE_REPORT](AGENT_GATEWAY_ARCHITECTURE_REPORT.md) | Agent gateway mimarisi |
| — | [COVERAGE_RECOVERY_REDESIGN_REPORT](COVERAGE_RECOVERY_REDESIGN_REPORT.md) | Coverage recovery yeniden tasarımı |
| — | [COVERAGE_RECOVERY_IMPLEMENTATION_REPORT](COVERAGE_RECOVERY_IMPLEMENTATION_REPORT.md) | Coverage recovery uygulaması |

## Konuya göre hızlı bakış

| Dokunacağın alan | Önce oku |
|---|---|
| Connector, kaynak ailesi | `ACADEMIC_SOURCE_INTEGRATION`, `COLLECTION_ARCHITECTURE` |
| Toplama, recall, coverage | `RESEARCH_COLLECTION_QUALITY_RESEARCH`, `LITERATURE_RECALL_V0.7.0`, `COVERAGE_RECOVERY_*` |
| İptal, timeout, worker kurtarma | `CANCELLATION_RELIABILITY_V0.6.3`, `EXECUTION_BUDGET_V0.6.4`, `GRACEFUL_COLLECTION_CUTOFF_V0.6.10` |
| Kontrol paneli | `CONTROL_PANEL_V0.6.1`, `CONTROL_PANEL_FLOW_V0.6.7` |
| Telegram | `TELEGRAM_DURATION_PICKER_V0.6.6`, `TELEGRAM_POSITIONAL_DURATION_V0.6.9` |
| HITL checkpoint'leri | `HITL_V0.6.8` |
| MCP gateway, ajan erişimi | `AGENT_GATEWAY_ARCHITECTURE` |
| Sentez, Word raporu | `SYNTHESIS_REPORT_PIPELINE_V0.8.0`, `WORD_REPORT_*` |
| Figür analizi | `FIGURE_INTELLIGENCE_V0.9.0`, `SOURCE_FIGURE_EMBEDDING_V0.9.1` |
| Kanıt, iddia denetimi | `RESEARCH_EVIDENCE_QUALITY_V0.6.2`, `RESEARCH_QUALITY_V0.6.0` |
| Ofis sunucusu işletimi | `OFFICE_SERVER_IMPLEMENTATION`, `OFFICE_QUEUE_INCIDENT` |

## [benchmarks/](benchmarks/)

Model karşılaştırmaları, donanım ölçümleri, değerlendirme metodolojileri ve uçtan uca stres
testi. Bunlar geliştirme raporu değil, **ölçüm kayıtları**dır; model veya donanım seçimi
tartışılırken bakılır.
