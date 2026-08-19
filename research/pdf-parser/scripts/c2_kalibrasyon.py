"""C1 ciktilarindan esik taramasi ve karar raporu uretir; uretim esigini degistirmez."""
from __future__ import annotations

# CODEX-2026-08-18: C2 aday esik analizi. Bu dosya gate.py yazmaz; yalniz
# tekrar uretilebilir CSV/JSON/Markdown kaniti olusturur.

import argparse
import csv
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from uretim_yolu import ekle  # noqa: E402

ekle()
from research_platform.parsers.smart_router.gate import kritik_mi  # noqa: E402


def _jsonl(yol: str) -> list[dict]:
    with open(yol, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return list({row.get("id"): row for row in rows if row.get("id")}.values())


def _sinif(gercek: list[bool], tahmin: list[bool]) -> dict:
    tp = sum(g and t for g, t in zip(gercek, tahmin))
    fp = sum(not g and t for g, t in zip(gercek, tahmin))
    fn = sum(g and not t for g, t in zip(gercek, tahmin))
    tn = sum(not g and not t for g, t in zip(gercek, tahmin))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f2 = 5 * precision * recall / (4 * precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 6), "recall": round(recall, 6),
        "f1": round(f1, 6), "f2": round(f2, 6),
        "positive_rate": round((tp + fp) / max(len(gercek), 1), 6),
    }


def _route(page: dict, kalite_esik: float, tablo_politikasi: str) -> bool:
    table = page.get("has_table", False)
    if tablo_politikasi == "high_tables":
        table = table and page.get("tablo_guven") == "yuksek"
    elif tablo_politikasi == "no_tables":
        table = False
    quality = page.get("quality_score")
    return bool(page.get("needs_ocr") or table
                or (quality is not None and quality < kalite_esik)
                or kritik_mi(page.get("critical_issue")))


def _route_sweep(rows: list[dict], min_gain: float) -> list[dict]:
    gercek = [r["delta"]["heavy_minus_fast"] >= min_gain for r in rows]
    sonuc = []
    for policy in ("all_tables", "high_tables", "no_tables"):
        for step in range(40, 96, 2):
            threshold = float(step)
            tahmin = [_route(r["route"]["pages"][0], threshold, policy) for r in rows]
            stats = _sinif(gercek, tahmin)
            sonuc.append({"min_gain": min_gain, "actual_positives": sum(gercek),
                          "quality_threshold": threshold,
                          "table_policy": policy, "fast_rate": round(1-stats["positive_rate"], 6),
                          **stats})
    return sonuc


def _table_sweep(rows: list[dict]) -> list[dict]:
    gercek = [bool((r.get("input", {}).get("labels") or {}).get("tablo")) for r in rows]
    sonuc = []
    for ort in (2, 4, 6, 8, 10, 12):
        for dolu in (4, 6, 8, 10, 12):
            for sutun in (2, 3, 4):
                for satir in (2, 3, 4, 5, 6):
                    v2, inspector = [], []
                    for r in rows:
                        s = r["route"]["pages"][0].get("gate_signals") or {}
                        v2.append(bool(
                            (s.get("ortogonal_cizgi") or 0) >= ort
                            or (s.get("dolu_dikdortgen") or 0) >= dolu
                            or ((s.get("izgara_sutun") or 0) >= sutun
                                and (s.get("izgara_satir") or 0) >= satir)
                        ))
                        inspector.append(bool(s.get("tablo_inspector")))
                    for policy, pred in (
                        ("inspector_or_v2", [a or b for a, b in zip(inspector, v2)]),
                        ("inspector_and_v2", [a and b for a, b in zip(inspector, v2)]),
                    ):
                        sonuc.append({"policy": policy, "ortogonal_cizgi": ort,
                                      "dolu_dikdortgen": dolu, "izgara_sutun": sutun,
                                      "izgara_satir": satir, **_sinif(gercek, pred)})
    return sonuc


def _figure_sweep(rows: list[dict]) -> list[dict]:
    gercek = [bool((r.get("input", {}).get("labels") or {}).get("sekil")) for r in rows]
    sonuc = []
    for threshold in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15):
        pred = []
        for r in rows:
            s = r["route"]["pages"][0].get("gate_signals") or {}
            kaplama = s.get("kume_kaplama") or 0.0
            pred.append(bool(s.get("sekil_raster")
                             or (kaplama > 0.0 if threshold == 0.0 else kaplama >= threshold)))
        sonuc.append({"kume_kaplama": threshold, **_sinif(gercek, pred)})
    return sonuc


def _csv_yaz(yol: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(yol, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _aday(sweep: list[dict]) -> dict | None:
    if not sweep or not sweep[0].get("actual_positives"):
        return None
    yuksek_recall = [r for r in sweep if r["recall"] >= 0.95]
    if yuksek_recall:
        return max(yuksek_recall, key=lambda r: (r["fast_rate"], r["precision"], -r["quality_threshold"]))
    return max(sweep, key=lambda r: (r["f2"], r["fast_rate"], r["precision"]))


def _kabul_edilen_aday(sweep: list[dict]) -> dict | None:
    """Uretim icin asgari kalite ve maliyet kosullarini ayni anda saglayan nokta."""
    uygun = [r for r in sweep if r["recall"] >= 0.90 and r["precision"] >= 0.60
             and r["fast_rate"] >= 0.30]
    return max(uygun, key=lambda r: (r["fast_rate"], r["f2"])) if uygun else None


def _route_hatalari(rows: list[dict], min_gain: float) -> list[dict]:
    sonuc = []
    for row in rows:
        page = row["route"]["pages"][0]
        actual = row["delta"]["heavy_minus_fast"] >= min_gain
        predicted = bool(row["route"]["routed_heavy"])
        if actual == predicted:
            continue
        meta = row.get("input", {}).get("metadata") or {}
        labels = row.get("input", {}).get("labels") or {}
        sonuc.append({
            "id": row["id"], "error_type": "false_negative" if actual else "false_positive",
            "heavy_minus_fast": row["delta"]["heavy_minus_fast"],
            "quality_score": page.get("quality_score"), "reasons": ",".join(page.get("karar_kaynagi") or []),
            "has_table": page.get("has_table"), "has_figure": page.get("has_figure"),
            "needs_ocr": page.get("needs_ocr"), "critical_issue": page.get("critical_issue"),
            "document_type": meta.get("tur"), "difficulty": meta.get("zorluk"),
            "label_table": labels.get("tablo"), "label_figure": labels.get("sekil"),
            "label_equation": labels.get("denklem"),
        })
    return sonuc


def _dil_kirilimi(rows: list[dict], min_gain: float) -> dict:
    # CODEX-2026-08-18: Aktarim basarisini birlesik ortalamanin gizlememesi icin
    # ayni fayda tanimi ve mevcut route karariyla dil bazinda raporla.
    sonuc = {}
    diller = sorted({
        (r.get("input", {}).get("metadata") or {}).get("dil") or "bilinmiyor"
        for r in rows
    })
    for dil in diller:
        dil_rows = [
            r for r in rows
            if ((r.get("input", {}).get("metadata") or {}).get("dil") or "bilinmiyor") == dil
        ]
        actual = [r["delta"]["heavy_minus_fast"] >= min_gain for r in dil_rows]
        current = [bool(r["route"]["routed_heavy"]) for r in dil_rows]
        stats = _sinif(actual, current)
        stats["fast_rate"] = round(1 - stats["positive_rate"], 6)
        sonuc[dil] = {
            "documents": len(dil_rows),
            "heavy_benefit_positives": sum(actual),
            "mean_utility": {
                engine: round(sum(r["scores"][engine]["utility"] for r in dil_rows)
                              / len(dil_rows), 6)
                for engine in ("fast", "heavy", "routed")
            },
            "current_baseline": stats,
        }
    return sonuc


def main() -> int:
    p = argparse.ArgumentParser(description="C2 threshold sweep report")
    p.add_argument("run_dir", help="C1 run dizini")
    p.add_argument("--min-gain", type=float, default=0.02)
    args = p.parse_args()
    predictions = os.path.join(args.run_dir, "predictions.jsonl")
    all_rows = _jsonl(predictions)
    rows = [r for r in all_rows if r.get("status") == "ok"
            and r.get("engine", {}).get("ok")
            and r.get("scores", {}).get("fast", {}).get("reference_chars", 0) >= 200]
    if not rows:
        print("Kalibrasyona uygun C1 sonucu yok.")
        return 2

    sensitivities = {}
    route_rows = []
    for gain in (0.0, 0.01, 0.02, 0.05):
        sweep = _route_sweep(rows, gain)
        route_rows.extend(sweep)
        sensitivities[str(gain)] = _aday(sweep)
    table_rows = _table_sweep(rows)
    figure_rows = _figure_sweep(rows)
    table_best = max(table_rows, key=lambda r: (r["f1"], r["recall"], r["precision"]))
    figure_best = max(figure_rows, key=lambda r: (r["f1"], r["recall"], r["precision"]))
    primary_sweep = _route_sweep(rows, args.min_gain)
    best_tradeoff = _aday(primary_sweep)
    selected = _kabul_edilen_aday(primary_sweep)
    positives = sum(r["delta"]["heavy_minus_fast"] >= args.min_gain for r in rows)
    sample_ready = len(rows) >= 100 and positives >= 10 and len(rows) - positives >= 10
    if not sample_ready:
        selected = None

    actual = [r["delta"]["heavy_minus_fast"] >= args.min_gain for r in rows]
    current = [bool(r["route"]["routed_heavy"]) for r in rows]
    current_stats = _sinif(actual, current)
    current_stats["fast_rate"] = round(1 - current_stats["positive_rate"], 6)
    language_breakdown = _dil_kirilimi(rows, args.min_gain)
    errors = _route_hatalari(rows, args.min_gain)
    false_negatives = [r for r in errors if r["error_type"] == "false_negative"]

    _csv_yaz(os.path.join(args.run_dir, "route_threshold_sweep.csv"), route_rows)
    _csv_yaz(os.path.join(args.run_dir, "table_threshold_sweep.csv"), table_rows)
    _csv_yaz(os.path.join(args.run_dir, "figure_threshold_sweep.csv"), figure_rows)
    _csv_yaz(os.path.join(args.run_dir, "route_errors.csv"), errors)
    summary = {
        "documents_total": len(all_rows), "documents_used": len(rows),
        "excluded": len(all_rows) - len(rows), "sample_ready": sample_ready,
        "route_target_met": selected is not None,
        "heavy_benefit_positives": positives, "candidate_not_applied": selected,
        "best_tradeoff_not_accepted": best_tradeoff,
        "current_baseline": current_stats,
        "language_breakdown": language_breakdown,
        "false_negative_pattern": {
            "count": len(false_negatives),
            "quality_100": sum(r["quality_score"] == 100.0 for r in false_negatives),
            "has_figure": sum(bool(r["has_figure"]) for r in false_negatives),
            "ids": [r["id"] for r in false_negatives],
        },
        "sensitivity_candidates": sensitivities, "table_candidate_not_applied": table_best,
        "figure_candidate_not_applied": figure_best,
        "limitations": [
            "OCRTurk belgeleri tek sayfali; sayfa siniri davranisi kalibre edilmedi.",
            "OCR icin taranmis/sayisal dengeli bir gercek etiket yok.",
            "Ingilizce aktarim yalniz secilmis OpenDataLoader alt ornekleminde olculdu.",
            "Adaylar gate.py dosyasina uygulanmadi.",
        ],
    }
    with open(os.path.join(args.run_dir, "calibration_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    aday_satirlari = (
        f"- Aday kalite esigi: **{selected['quality_threshold']:.1f}**\n"
        f"- Aday tablo politikasi: **{selected['table_policy']}**\n"
        f"- Agir-yol precision/recall/F2: **{selected['precision']:.3f} / "
        f"{selected['recall']:.3f} / {selected['f2']:.3f}**\n"
        f"- Tahmini hizli-yol orani: **{selected['fast_rate']:.3f}**"
        if selected else
        "- **Kabul edilen aday yok:** mevcut sinyaller precision >= 0.60, recall >= 0.90 "
        "ve hizli-yol >= 0.30 kosullarini birlikte saglamiyor."
    )
    report = f"""# C2 Kalibrasyon Aday Raporu

<!-- CODEX-2026-08-18: Otomatik uretilen aday rapor; production esigi degistirmez. -->

- Kullanilan belge: **{len(rows)} / {len(all_rows)}**
- Ana fayda marji: **{args.min_gain:.2f}**
{aday_satirlari}

Mevcut esiklerin precision/recall/hizli-yol orani:
**{current_stats['precision']:.3f} / {current_stats['recall']:.3f} / {current_stats['fast_rate']:.3f}**.
Kacirilan {len(false_negatives)} faydali agir-motor vakasinin
{sum(r['quality_score'] == 100.0 for r in false_negatives)} tanesi kalite skoru 100 ve
{sum(bool(r['has_figure']) for r in false_negatives)} tanesi sekil iceriyor. Yalniz
esik degistirmek bu vakalari ayiramiyor; `route_errors.csv` belge listesini tasir.

Bu degerler **uretime uygulanmadi**. `0.00`, `0.01`, `0.02` ve `0.05` fayda
marjlarinin adaylari `calibration_summary.json`; tum noktalar CSV dosyalarindadir.

## Dil Kirilimi

```json
{json.dumps(language_breakdown, ensure_ascii=False, indent=2)}
```

## Sinirlar

1. OCRTurk tek sayfalidir; cok sayfali birlestirme ve sayfa sinirlari sinanmadi.
2. OCR esikleri icin taranmis/sayisal dengeli gercek etiket yoktur.
3. Ingilizce aktarim yalniz secilmis OpenDataLoader alt ornekleminde olculdu.
4. Bu rapor karar kanitidir; `gate.py` esiklerini otomatik yazmaz.
"""
    with open(os.path.join(args.run_dir, "calibration_report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
