"""Docling'i gerçek PDF ile free-threaded süreçlerde stres et.

İki kullanım biçimi ayrı ayrı sınanır: production servisindeki gibi paylaşılan tek
converter ve thread başına ayrı converter. Her (mod, thread sayısı) vakası parent
tarafından ayrı child process'te timeout ve sinyal denetimiyle çalıştırılır.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

for _ad in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_ad, "1")

# Production Docling worker disables torch.compile/inductor because a missing
# host C++ compiler should not take PDF conversion down. Keep the stress runner
# on the same contract; this test is about Docling thread behaviour, not local
# compiler availability.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")


def _gil_etkin_mi() -> bool | None:
    fn = getattr(sys, "_is_gil_enabled", None)
    return bool(fn()) if fn else None


def _cevirici_uret() -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CPU, num_threads=1,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def _cevir(converter: Any, pdf: Path) -> str:
    result = converter.convert(pdf)
    markdown = result.document.export_to_markdown()
    return "sha256:" + hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def thread_vakasi(factory: Callable[[], Any], pdf: Path, mode: str,
                  threads: int, reps: int) -> dict[str, Any]:
    """Converter paylaşımı ve çıktı tutarlılığını tek child içinde denetle."""
    ortak = factory() if mode == "shared" else None
    referans_converter = ortak or factory()
    referans = _cevir(referans_converter, pdf)
    bariyer = threading.Barrier(threads)

    def worker() -> list[str]:
        converter = ortak or factory()
        bariyer.wait(timeout=60)
        return [_cevir(converter, pdf) for _ in range(reps)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as havuz:
        sonuclar = [d for future in [havuz.submit(worker) for _ in range(threads)]
                    for d in future.result()]
    digestler = sorted({referans, *sonuclar})
    return {
        "mode": mode,
        "threads": threads,
        "reps_per_thread": reps,
        "operations": len(sonuclar),
        "wall_s": round(time.perf_counter() - t0, 4),
        "digest_count": len(digestler),
        "digest": digestler[0] if len(digestler) == 1 else "",
        "digest_divergence": len(digestler) != 1,
        "gil_enabled_at_end": _gil_etkin_mi(),
    }


def child(pdf: Path, mode: str, threads: int, reps: int, expected_gil: bool) -> int:
    try:
        sonuc = thread_vakasi(_cevirici_uret, pdf, mode, threads, reps)
        sonuc.update({
            "ok": not sonuc["digest_divergence"],
            "docling_version": importlib.metadata.version("docling"),
        })
    except Exception as exc:  # noqa: BLE001 -- uyumluluk bulgusu olarak kaydedilir
        sonuc = {
            "mode": mode,
            "threads": threads,
            "reps_per_thread": reps,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "gil_enabled_at_end": _gil_etkin_mi(),
        }
    gil_durumu = sonuc.get("gil_enabled_at_end")
    gil_kapisi_gecer = (
        gil_durumu is expected_gil
        or (gil_durumu is None and expected_gil)
    )
    sonuc["gil_status_api_available"] = gil_durumu is not None
    print(json.dumps(sonuc, ensure_ascii=False))
    return 0 if sonuc["ok"] and gil_kapisi_gecer else 1


def _siniflandir(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    if returncode < 0:
        return {"status": "process_crash", "signal": -returncode,
                "returncode": returncode, "stderr_tail": stderr[-1000:]}
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"status": "invalid_child_output", "returncode": returncode,
                "stdout_tail": stdout[-1000:], "stderr_tail": stderr[-1000:]}
    status = "passed" if returncode == 0 and payload.get("ok") else "error"
    return {"status": status, "returncode": returncode, "result": payload,
            "stderr_tail": stderr[-1000:]}


def parent(pdf: Path, modes: list[str], threads: list[int], reps: int,
           timeout_s: float) -> dict[str, Any]:
    free_threaded = "free-threading build" in sys.version
    expected_gil = not free_threaded
    vakalar = []
    for mode in modes:
        for n in threads:
            komut = [sys.executable, str(Path(__file__).resolve()), "--child",
                     "--pdf", str(pdf), "--mode", mode, "--threads", str(n),
                     "--reps", str(reps), "--expect-gil",
                     "enabled" if expected_gil else "disabled"]
            try:
                c = subprocess.run(komut, capture_output=True, text=True,
                                   timeout=timeout_s, check=False)
                sonuc = _siniflandir(c.returncode, c.stdout, c.stderr)
            except subprocess.TimeoutExpired as exc:
                sonuc = {
                    "status": "deadlock_suspected",
                    "timeout_s": timeout_s,
                    "stdout_tail": (exc.stdout or "")[-1000:],
                    "stderr_tail": (exc.stderr or "")[-1000:],
                }
            sonuc.update({"mode": mode, "threads": n})
            vakalar.append(sonuc)
    return {
        "schema": "gil-scaling/free-threaded-docling-stress/1",
        "python": sys.version,
        "free_threaded_build": free_threaded,
        "expected_gil_enabled": expected_gil,
        "input_name": pdf.name,
        "input_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "reps_per_thread": reps,
        "timeout_s": timeout_s,
        "cases": vakalar,
        "passed": all(v["status"] == "passed" for v in vakalar),
    }


def referansla_karsilastir(sonuc: dict[str, Any], referans: dict[str, Any]) -> dict[str, Any]:
    """Aynı PDF ve vakaların markdown digestlerini klasik kolla karşılaştır."""
    def digestler(veri: dict[str, Any]) -> dict[tuple[str, int], str]:
        return {
            (v["mode"], int(v["threads"])): str(v.get("result", {}).get("digest", ""))
            for v in veri.get("cases", []) if v.get("status") == "passed"
        }

    mevcut, beklenen = digestler(sonuc), digestler(referans)
    anahtarlar = sorted(set(mevcut) | set(beklenen))
    ayrismalar = [
        {"mode": mode, "threads": n, "current": mevcut.get((mode, n), ""),
         "reference": beklenen.get((mode, n), "")}
        for mode, n in anahtarlar if mevcut.get((mode, n)) != beklenen.get((mode, n))
    ]
    ayni_girdi = sonuc.get("input_sha256") == referans.get("input_sha256")
    karsilastirma = {
        "reference_python": referans.get("python", ""),
        "same_input": ayni_girdi,
        "case_count": len(anahtarlar),
        "digest_mismatches": ayrismalar,
        "passed": ayni_girdi and not ayrismalar and bool(anahtarlar),
    }
    sonuc["reference_comparison"] = karsilastirma
    sonuc["passed"] = bool(sonuc.get("passed")) and karsilastirma["passed"]
    return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--mode", choices=("shared", "per_thread"))
    ap.add_argument("--modes", default="shared,per_thread")
    ap.add_argument("--threads", default="1,2,4,8")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--expect-gil", choices=("enabled", "disabled"),
                    default="disabled", help=argparse.SUPPRESS)
    ap.add_argument("--out", default=(
        "research/gil-scaling/results/free_threaded_docling_stress.json"))
    ap.add_argument("--reference", default="",
                    help="aynı PDF'nin klasik Python sonuç JSON'u")
    args = ap.parse_args()
    if not args.pdf.is_file():
        ap.error(f"PDF bulunamadı: {args.pdf}")
    if args.child:
        if not args.mode:
            ap.error("--child için --mode gerekli")
        return child(args.pdf, args.mode, int(args.threads), args.reps,
                     args.expect_gil == "enabled")

    modes = [x.strip() for x in args.modes.split(",") if x.strip()]
    sonuc = parent(args.pdf, modes, [int(x) for x in args.threads.split(",")],
                   args.reps, args.timeout)
    if args.reference:
        referans = json.loads(Path(args.reference).read_text(encoding="utf-8"))
        referansla_karsilastir(sonuc, referans)
    hedef = Path(args.out)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(sonuc, indent=2, ensure_ascii=False))
    return 0 if sonuc["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
