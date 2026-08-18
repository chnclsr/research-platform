# Ölçüm ve Değerlendirme Kayıtları

Model karşılaştırmaları, donanım ölçümleri ve değerlendirme metodolojileri. Bunlar
geliştirme raporu değildir — bir özelliğin nasıl yapıldığını değil, bir seçimin hangi
ölçüme dayandığını anlatırlar.

Model veya donanım seçimi tartışılırken buraya bakılır; kod değişikliği yaparken genellikle
[../](../) altındaki geliştirme raporları daha ilgilidir.

| Belge | Konu |
|---|---|
| [BENCHMARK_REPORT](BENCHMARK_REPORT.md) | Genel model karşılaştırması |
| [MODEL_HARD_BENCHMARK_REPORT](MODEL_HARD_BENCHMARK_REPORT.md) | Zorlu görev seti |
| [MODEL_HARDWARE_OPTIMIZED_BENCHMARK_REPORT](MODEL_HARDWARE_OPTIMIZED_BENCHMARK_REPORT.md) | RTX 4060 / 8 GB VRAM'e göre optimize karşılaştırma |
| [QWEN_4B_GENERATION_BENCHMARK_REPORT](QWEN_4B_GENERATION_BENCHMARK_REPORT.md) | Qwen 4B üretim ölçümü |
| [NANBEIGE41_3B_BENCHMARK_REPORT](NANBEIGE41_3B_BENCHMARK_REPORT.md) | Nanbeige 3B ölçümü |
| [FIVE_MINUTE_MODEL_TEST_PROTOCOL](FIVE_MINUTE_MODEL_TEST_PROTOCOL.md) | Beş dakikalık testin protokolü |
| [FIVE_MINUTE_MODEL_BLIND_ASSESSMENT](FIVE_MINUTE_MODEL_BLIND_ASSESSMENT.md) | Kör değerlendirme sonuçları |
| [FIVE_MINUTE_MODEL_COMPARISON_REPORT](FIVE_MINUTE_MODEL_COMPARISON_REPORT.md) | Karşılaştırma raporu |
| [QUALITATIVE_MODEL_EVALUATION_METHODOLOGY](QUALITATIVE_MODEL_EVALUATION_METHODOLOGY.md) | Niteliksel değerlendirme metodolojisi |
| [E2E_RESEARCH_STRESS_TEST_REPORT_V1.0.0](E2E_RESEARCH_STRESS_TEST_REPORT_V1.0.0.md) | Uçtan uca stres testi |

**Not:** `scripts/run_five_minute_model_test.py` ürettiği manifest'te
`FIVE_MINUTE_MODEL_TEST_PROTOCOL.md` yoluna atıf yapar; bu dosya taşınırsa oradaki yol da
güncellenmelidir.
