"""OCRTurk uzerinde hizli, agir ve yonlendirilmis PDF ciktilarini karsilastirir."""
from __future__ import annotations

# CODEX-2026-08-18: C1-b/C1-c yeniden baslatilabilir validation runner.

import argparse
import json
import os
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from c1_metrik import METRIC_VERSION, metrikler  # noqa: E402
from korpus_kaynak import (  # noqa: E402
    KORPUS_KOK, METIN_REFERANSI, OPENDATALOADER_KOK, PDF_PARSE,
)
from uretim_yolu import ekle  # noqa: E402
from c1_orneklem import sec as _sec  # noqa: E402

ekle()

from research_platform.parsers.smart_pdf import SmartPdfParser  # noqa: E402
from research_platform.parsers.smart_router import SmartRouterHatti  # noqa: E402
from research_platform.parsers.smart_router.engines import DoclingEngine, EngineResult  # noqa: E402
from research_platform.parsers.smart_router.merge import (  # noqa: E402
    MergedDocument, MergedPage, birlestir, sayfa_basliklariyla,
)

DEFAULT_MANIFEST = os.path.join(BASE, "out", "korpus_envanteri.jsonl")
DEFAULT_OUT = os.path.join(BASE, "out", "c1_runs")


def _oku_jsonl(yol: str) -> list[dict]:
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def _markdown(pages: dict[int, str], engine: str) -> str:
    doc = MergedDocument(pages=[
        MergedPage(page_no=n, text=pages.get(n, ""), engine=engine)
        for n in sorted(pages)
    ])
    return sayfa_basliklariyla(doc)


def _alt_sonuc(result: EngineResult, sayfalar: list[int]) -> EngineResult:
    sec = set(sayfalar)
    return EngineResult(
        engine=result.engine,
        pages={n: text for n, text in result.pages.items() if n in sec},
        tables=[t for t in result.tables if t.get("page") in sec],
        ok=result.ok, error=result.error, degraded=result.degraded,
        duration_ms=result.duration_ms, mode=result.mode,
    )


# CODEX-2026-08-18: Persistent benchmark worker'in SHA-256 cache'ini production
# EngineResult sozlesmesine cevirir.
def _cache_sonucu(cache_dir: str, kayit: dict) -> EngineResult:
    path = os.path.join(cache_dir, kayit["pdf_sha256"] + ".json")
    if not os.path.isfile(path):
        raise FileNotFoundError("Docling cache yok: %s" % path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("pdf_sha256") != kayit.get("pdf_sha256"):
        raise ValueError("Docling cache hash uyusmazligi: %s" % path)
    return EngineResult(
        engine="docling", pages={int(n): text for n, text in (payload.get("pages") or {}).items()},
        tables=list(payload.get("tables") or []), ok=bool(payload.get("ok")),
        error=payload.get("error"), degraded=bool(payload.get("degraded")),
        duration_ms=float(payload.get("duration_ms") or 0.0), mode="persistent-cache",
    )


def _yaz(yol: str, metin: str) -> None:
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="") as f:
        f.write(metin)


def _coz(kayit: dict, relative: str) -> str:
    root = (OPENDATALOADER_KOK
            if kayit.get("yol_koku") == "opendataloader_bench"
            else KORPUS_KOK)
    return os.path.join(root, *relative.split("/"))


def _ozet(rows: list[dict]) -> dict:
    # CODEX-2026-08-18: Resume sonrasi ayni kimligin eski hata satiri varsa
    # son denemeyi esas al; belge ve hata sayisini sisirme.
    son = {r.get("id"): r for r in rows if r.get("id")}
    rows = list(son.values())
    tamam = [r for r in rows if r.get("status") == "ok"]
    routed = [r for r in tamam if r["route"]["routed_heavy"]]
    heavy_wins = [r for r in tamam if r["delta"]["heavy_minus_fast"] >= 0.02]
    dogru = [r for r in routed if r["delta"]["heavy_minus_fast"] >= 0.02]
    return {
        "metric_version": METRIC_VERSION,
        "documents": len(rows), "ok": len(tamam), "errors": len(rows) - len(tamam),
        "routed_heavy": len(routed), "heavy_gain_ge_0_02": len(heavy_wins),
        "route_precision_at_0_02": round(len(dogru) / len(routed), 4) if routed else None,
        "route_recall_at_0_02": round(len(dogru) / len(heavy_wins), 4) if heavy_wins else None,
        "mean_utility": {
            ad: round(sum(r["scores"][ad]["utility"] for r in tamam) / len(tamam), 6)
            if tamam else None for ad in ("fast", "heavy", "routed")
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="C1 OCRTurk validation runner")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--kimlik", action="append")
    p.add_argument("--dataset", action="append",
                   choices=["ocrturk", "opendataloader_bench"])
    p.add_argument("--skip-heavy", action="store_true")
    p.add_argument("--heavy-cache", help="c1_docling_cache.py cikti dizini")
    p.add_argument("--fail-fast", action="store_true")
    args = p.parse_args()
    if args.limit < 0:
        p.error("--limit negatif olamaz")

    records = _sec(_oku_jsonl(args.manifest), args.kimlik, args.limit, args.dataset)
    if not records:
        print("C1'e uygun OCRTurk kaydi bulunamadi.")
        return 2

    engine = DoclingEngine()
    if args.heavy_cache:
        args.heavy_cache = os.path.abspath(args.heavy_cache)
        ready, detail = True, "docling persistent cache (%s)" % args.heavy_cache
    else:
        ready, detail = engine.available()
    if not args.skip_heavy and not ready:
        print("Agir motor hazir degil: %s" % detail)
        print("SMART_ROUTER_DOCLING_PYTHON ayarla veya --skip-heavy kullan.")
        return 2

    run_dir = os.path.join(args.out, args.run_id)
    os.makedirs(run_dir, exist_ok=True)
    predictions = os.path.join(run_dir, "predictions.jsonl")
    mevcut = _oku_jsonl(predictions) if os.path.isfile(predictions) else []
    tamamlanan = {r.get("id") for r in mevcut if r.get("status") == "ok"}
    rows = list(mevcut)
    print("run=%s belge=%d engine=%s" % (args.run_id, len(records), detail), flush=True)

    for sira, kayit in enumerate(records, start=1):
        kimlik = kayit["kimlik"]
        if kimlik in tamamlanan:
            continue
        started = time.perf_counter()
        row = {"id": kimlik, "dataset": kayit["veri_seti"], "status": "error"}
        try:
            pdf = _coz(kayit, kayit["pdf_yolu"])
            ref_yolu = _coz(kayit, kayit["referans"]["yol"])
            with open(ref_yolu, encoding="utf-8-sig") as f:
                reference = f.read()

            decision = SmartRouterHatti().calistir(pdf, metin_dahil=True)
            fast_pages = {int(n): text for n, text in decision["sayfa_metni"].items()}
            page_numbers = sorted(fast_pages)
            if args.skip_heavy:
                heavy = EngineResult(engine="docling", ok=False, degraded=True,
                                     error="--skip-heavy", mode="skipped")
            elif args.heavy_cache:
                heavy = _cache_sonucu(args.heavy_cache, kayit)
            else:
                heavy = engine.extract(pdf, page_numbers)
            routed_pages = [s["sayfa_no"] for s in decision["sayfalar"]
                            if s.get("karar_kaynagi")]
            decisions = {s["sayfa_no"]: s.get("karar_kaynagi") or []
                         for s in decision["sayfalar"]}
            routed_result = _alt_sonuc(heavy, routed_pages)
            merged = birlestir(
                fast_pages, decisions=decisions, results=[routed_result],
                requested={"docling": routed_pages},
                score=SmartPdfParser()._page_scorer(),
            )

            fast_md = _markdown(fast_pages, "pdf-inspector")
            heavy_md = _markdown({n: heavy.pages.get(n, "") for n in page_numbers}, "docling")
            routed_md = sayfa_basliklariyla(merged)
            relative = {}
            for ad, text in (("fast", fast_md), ("heavy", heavy_md), ("routed", routed_md)):
                yol = os.path.join(run_dir, "markdown", ad, kimlik + ".md")
                _yaz(yol, text)
                relative[ad] = os.path.relpath(yol, run_dir).replace("\\", "/")

            scores = {ad: metrikler(reference, text) for ad, text in
                      (("fast", fast_md), ("heavy", heavy_md), ("routed", routed_md))}
            row = {
                "id": kimlik, "dataset": kayit["veri_seti"], "status": "ok",
                "input": {"pdf_sha256": kayit.get("pdf_sha256"),
                          "labels": kayit.get("etiketler"), "metadata": kayit.get("ustveri")},
                "route": {"routed_heavy": bool(routed_pages), "pages": decision["sayfalar"],
                          "summary": decision["ozet"], "router_version": decision["router_version"],
                          "threshold_version": decision["esik_version"]},
                "engine": {"available": ready, "detail": detail, "ok": heavy.ok,
                           "degraded": heavy.degraded, "error": heavy.error,
                           "mode": heavy.mode, "duration_ms": round(heavy.duration_ms, 1)},
                "merge": {"degraded": merged.degraded, "notes": merged.notes,
                          "fallback_pages": merged.fallback_pages,
                          "quarantined_pages": merged.quarantined_pages,
                          "engine_counts": merged.engine_counts},
                "outputs": relative, "scores": scores,
                "delta": {
                    "heavy_minus_fast": round(scores["heavy"]["utility"] - scores["fast"]["utility"], 6),
                    "routed_minus_fast": round(scores["routed"]["utility"] - scores["fast"]["utility"], 6),
                },
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except Exception as exc:
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
            if args.fail_fast:
                raise
        rows.append(row)
        with open(predictions, "a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("[%d/%d] %s %s" % (sira, len(records), kimlik, row["status"]), flush=True)

    summary = _ozet(rows)
    summary.update({"run_id": args.run_id, "engine": detail, "manifest": args.manifest})
    _yaz(os.path.join(run_dir, "summary.json"),
         json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
