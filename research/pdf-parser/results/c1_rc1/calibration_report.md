# C2 Kalibrasyon Aday Raporu

<!-- CODEX-2026-08-18: Otomatik uretilen aday rapor; production esigi degistirmez. -->

- Kullanilan belge: **221 / 230**
- Ana fayda marji: **0.02**
- **Kabul edilen aday yok:** mevcut sinyaller precision >= 0.60, recall >= 0.90 ve hizli-yol >= 0.30 kosullarini birlikte saglamiyor.

Mevcut esiklerin precision/recall/hizli-yol orani:
**0.410 / 0.743 / 0.394**.
Kacirilan 19 faydali agir-motor vakasinin
16 tanesi kalite skoru 100 ve
18 tanesi sekil iceriyor. Yalniz
esik degistirmek bu vakalari ayiramiyor; `route_errors.csv` belge listesini tasir.

Bu degerler **uretime uygulanmadi**. `0.00`, `0.01`, `0.02` ve `0.05` fayda
marjlarinin adaylari `calibration_summary.json`; tum noktalar CSV dosyalarindadir.

## Dil Kirilimi

```json
{
  "en": {
    "documents": 49,
    "heavy_benefit_positives": 6,
    "mean_utility": {
      "fast": 0.889773,
      "heavy": 0.868219,
      "routed": 0.868654
    },
    "current_baseline": {
      "tp": 3,
      "fp": 31,
      "fn": 3,
      "tn": 12,
      "precision": 0.088235,
      "recall": 0.5,
      "f1": 0.15,
      "f2": 0.258621,
      "positive_rate": 0.693878,
      "fast_rate": 0.306122
    }
  },
  "tr": {
    "documents": 172,
    "heavy_benefit_positives": 68,
    "mean_utility": {
      "fast": 0.808129,
      "heavy": 0.838368,
      "routed": 0.840329
    },
    "current_baseline": {
      "tp": 52,
      "fp": 48,
      "fn": 16,
      "tn": 56,
      "precision": 0.52,
      "recall": 0.764706,
      "f1": 0.619048,
      "f2": 0.698925,
      "positive_rate": 0.581395,
      "fast_rate": 0.418605
    }
  }
}
```

## Sinirlar

1. OCRTurk tek sayfalidir; cok sayfali birlestirme ve sayfa sinirlari sinanmadi.
2. OCR esikleri icin taranmis/sayisal dengeli gercek etiket yoktur.
3. Ingilizce aktarim yalniz secilmis OpenDataLoader alt ornekleminde olculdu.
4. Bu rapor karar kanitidir; `gate.py` esiklerini otomatik yazmaz.
