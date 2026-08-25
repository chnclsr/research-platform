"""C1 icin Docling modelini bir kez yukleyip PDF ciktilarini SHA-256 ile cache'ler."""
from __future__ import annotations

# CODEX-2026-08-18: Uretimdeki belge-basi timeout/izolasyon bridge'ini
# degistirmeden, benchmarkta 180 kez model yukleme maliyetini kaldirir.

import argparse
import importlib.util
import json
import os
import sys
import time

from c1_orneklem import sec
from korpus_kaynak import KORPUS_KOK, OPENDATALOADER_KOK
from uretim_yolu import URETIM_SRC

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(BASE, "out", "korpus_envanteri.jsonl")
DEFAULT_OUT = os.path.join(BASE, "out", "c1_docling_cache")
PDF_PARSE = "pdf_parse"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _uretim_worker():
    """Uretimdeki _docling_worker modulunu yukler.

    Ayni modulden hem `_table_grid` hem `cihaz()` aliniyor; ikinci bir yol
    acmak ikisinin farkli surumlerden gelmesine izin verirdi.

    `cihaz()` payload'a yaziliyor cunku cache dosyalari yalniz `pdf_sha256` ile
    adlandiriliyor -- cihaz adi anahtarda YOK. Payload'da da durmazsa bir cache
    dosyasina bakip CPU'da mi GPU'da mi uretildigini soylemek imkansiz olur.
    """
    path = os.path.join(
        URETIM_SRC, "research_platform", "parsers", "smart_router", "_docling_worker.py"
    )
    spec = importlib.util.spec_from_file_location("c1_production_docling_worker", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Production Docling worker yuklenemedi: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _atomic_json(path: str, payload: dict) -> None:
    temp = path + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _resolve(record: dict) -> str:
    root = (OPENDATALOADER_KOK
            if record.get("yol_koku") == "opendataloader_bench"
            else KORPUS_KOK)
    return os.path.join(root, *record["pdf_yolu"].split("/"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent Docling C1 cache")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--skip-predictions", help="status=ok kimlikleri yeniden isleme")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dataset", action="append",
                        help="Yalniz bu veri seti; birden fazla kez verilebilir")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    skipped_ids = set()
    if args.skip_predictions and os.path.isfile(args.skip_predictions):
        skipped_ids = {r.get("id") for r in _rows(args.skip_predictions) if r.get("status") == "ok"}
    # CODEX-2026-08-18: Dogrulayici ile ayni dengeli/deterministik ilk-N secimi.
    records = sec(_rows(args.manifest), None, args.limit, args.dataset)
    records = [r for r in records
               if r.get("pdf_sha256") and r.get("kimlik") not in skipped_ids]

    pending = []
    for record in records:
        cache_path = os.path.join(args.out, record["pdf_sha256"] + ".json")
        if not os.path.isfile(cache_path):
            pending.append((record, cache_path))
    if not pending:
        print("Cache tamam; islenecek belge yok.")
        return 0

    print("Docling modeli yukleniyor; belge=%d" % len(pending), flush=True)
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    worker = _uretim_worker()
    table_grid = worker._table_grid
    device = worker.cihaz()
    print("Model hazir; cihaz=%s" % device, flush=True)

    errors = 0
    for index, (record, cache_path) in enumerate(pending, start=1):
        started = time.perf_counter()
        pages, tables, error = {}, [], None
        try:
            pdf = _resolve(record)
            page_count = int(record.get("sayfa_sayisi") or 1)
            result = converter.convert(pdf, page_range=(1, page_count))
            for page_no in range(1, page_count + 1):
                pages[page_no] = result.document.export_to_markdown(page_no=page_no)
            for table in getattr(result.document, "tables", None) or []:
                flattened = table_grid(table)
                if flattened:
                    tables.append(flattened)
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
            errors += 1
        payload = {
            "id": record["kimlik"], "pdf_sha256": record["pdf_sha256"],
            "pages": pages, "tables": tables, "ok": error is None,
            "degraded": error is not None, "error": error, "mode": "persistent-cache",
            # Cihaz anahtarda yok; provenance yalniz burada duruyor.
            "device": device,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        _atomic_json(cache_path, payload)
        print("[%d/%d] %s %s %.1fs" % (
            index, len(pending), record["kimlik"], "ok" if error is None else "error",
            payload["duration_ms"] / 1000,
        ), flush=True)
    print("Cache=%s errors=%d" % (args.out, errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
