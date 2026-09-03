"""NumPy/PyTorch free-threaded CPU stres matrisi.

Her (workload, thread sayısı) vakası ayrı process'te koşar. Parent; timeout'u
`deadlock_suspected`, sinyalle kapanmayı `process_crash`, Python hatasını `error` olarak
ayırır. Child aynı anda başlayan thread'lerin digest ve GIL durumunu doğrular.
"""

from __future__ import annotations

import argparse
import hashlib
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

# Native havuzlar ayrıca paralelleşirse Python thread matrisi oversubscription ölçer.
for _ad in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_ad, "1")


def _gil_etkin_mi() -> bool | None:
    fn = getattr(sys, "_is_gil_enabled", None)
    return bool(fn()) if fn else None


def _digest(deger: bytes) -> str:
    return "sha256:" + hashlib.sha256(deger).hexdigest()


_NUMPY_INPUT: Any | None = None
_NUMPY_LINALG_INPUT: tuple[Any, Any] | None = None


def _numpy_call() -> str:
    import numpy as np

    global _NUMPY_INPUT
    if _NUMPY_INPUT is None:
        _NUMPY_INPUT = np.arange(192 * 192, dtype=np.int64).reshape(192, 192) % 97
    # Salt-okunur ortak girdi + thread'e özel mutable ara dizi.
    ortak = _NUMPY_INPUT
    yerel = ortak.copy()
    yerel ^= 7
    sonuc = yerel @ ortak.T
    return _digest(sonuc.tobytes())


def _numpy_linalg_call() -> str:
    """Paylaşılan float girdilerle LAPACK ve ufunc yolunu birlikte çalıştır."""
    import numpy as np

    global _NUMPY_LINALG_INPUT
    if _NUMPY_LINALG_INPUT is None:
        taban = np.arange(48 * 48, dtype=np.float64).reshape(48, 48) % 31
        matris = taban @ taban.T + np.eye(48, dtype=np.float64) * 1000
        sag = np.linspace(0.25, 4.0, 48, dtype=np.float64)
        _NUMPY_LINALG_INPUT = matris, sag
    matris, sag = _NUMPY_LINALG_INPUT
    cozum = np.linalg.solve(matris, sag)
    sonuc = np.sin(cozum) + np.square(cozum)
    return _digest(sonuc.tobytes())


_TORCH_INPUT: Any | None = None


def _torch_call() -> str:
    import torch

    global _TORCH_INPUT
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # Aynı child içinde daha önce ayarlandıysa PyTorch ikinci çağrıyı reddeder.
        pass
    if _TORCH_INPUT is None:
        _TORCH_INPUT = torch.arange(192 * 192, dtype=torch.int64).reshape(192, 192) % 97
    ortak = _TORCH_INPUT
    yerel = ortak.clone()
    yerel.bitwise_xor_(7)
    sonuc = yerel @ ortak.T
    return _digest(sonuc.numpy().tobytes())


_TORCH_MODEL: tuple[Any, Any] | None = None


def _torch_inference_call() -> str:
    """Thread'ler arasında paylaşılan, salt-okunur modelle gerçek inference çağrısı."""
    global _TORCH_MODEL
    import torch

    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    if _TORCH_MODEL is None:
        torch.manual_seed(20260902)
        model = torch.nn.Sequential(
            torch.nn.Linear(128, 256),
            torch.nn.GELU(),
            torch.nn.Linear(256, 64),
        ).eval()
        girdi = torch.arange(32 * 128, dtype=torch.float32).reshape(32, 128) / 4096
        _TORCH_MODEL = model, girdi
    model, girdi = _TORCH_MODEL
    with torch.inference_mode():
        sonuc = model(girdi)
    return _digest(sonuc.numpy().tobytes())


WORKLOADLAR: dict[str, Callable[[], str]] = {
    "numpy": _numpy_call,
    "numpy_linalg": _numpy_linalg_call,
    "torch": _torch_call,
    "torch_inference": _torch_inference_call,
}


def thread_vakasi(call: Callable[[], str], threads: int, reps: int) -> dict[str, Any]:
    """Tek child içindeki thread güvenliği ve sonuç tutarlılığı."""
    # Tek-thread referansı ve lazy kurulum zamanlama dışında. Thread sonuçları yalnız
    # birbirleriyle değil bu referansla da aynı olmalı.
    referans = call()
    bariyer = threading.Barrier(threads)

    def worker() -> list[str]:
        bariyer.wait(timeout=30)
        return [call() for _ in range(reps)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as havuz:
        sonuclar = [d for future in [havuz.submit(worker) for _ in range(threads)]
                    for d in future.result()]
    digestler = sorted({referans, *sonuclar})
    return {
        "threads": threads,
        "reps_per_thread": reps,
        "operations": len(sonuclar),
        "reference_digest": referans,
        "wall_s": round(time.perf_counter() - t0, 4),
        "digest_count": len(digestler),
        "digest": digestler[0] if len(digestler) == 1 else "",
        "digest_divergence": len(digestler) != 1,
        "gil_enabled_at_end": _gil_etkin_mi(),
    }


def child(workload: str, threads: int, reps: int, expected_gil: bool) -> int:
    try:
        sonuc = thread_vakasi(WORKLOADLAR[workload], threads, reps)
        sonuc.update({"workload": workload, "ok": not sonuc["digest_divergence"]})
    except Exception as exc:  # noqa: BLE001 -- parent'a yapılandırılmış bulgu döner
        sonuc = {
            "workload": workload,
            "threads": threads,
            "reps_per_thread": reps,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "gil_enabled_at_end": _gil_etkin_mi(),
        }
    print(json.dumps(sonuc, ensure_ascii=False))
    return 0 if sonuc["ok"] and sonuc["gil_enabled_at_end"] is expected_gil else 1


def siniflandir(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    """Child sonucunu crash/Python hatası/başarı olarak sınıflandırır."""
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


def parent(workloads: list[str], threads: list[int], reps: int,
           timeout_s: float) -> dict[str, Any]:
    free_threaded = "free-threading build" in sys.version
    expected_gil = not free_threaded
    vakalar = []
    for workload in workloads:
        for n in threads:
            komut = [sys.executable, str(Path(__file__).resolve()), "--child",
                     "--workload", workload, "--threads", str(n), "--reps", str(reps)]
            komut += ["--expect-gil", "enabled" if expected_gil else "disabled"]
            try:
                c = subprocess.run(komut, capture_output=True, text=True,
                                   timeout=timeout_s, check=False)
                sonuc = siniflandir(c.returncode, c.stdout, c.stderr)
            except subprocess.TimeoutExpired as exc:
                sonuc = {
                    "status": "deadlock_suspected",
                    "timeout_s": timeout_s,
                    "stdout_tail": (exc.stdout or "")[-1000:],
                    "stderr_tail": (exc.stderr or "")[-1000:],
                }
            sonuc.update({"workload": workload, "threads": n})
            vakalar.append(sonuc)
    return {
        "schema": "gil-scaling/free-threaded-stress/1",
        "python": sys.version,
        "free_threaded_build": free_threaded,
        "expected_gil_enabled": expected_gil,
        "reps_per_thread": reps,
        "timeout_s": timeout_s,
        "cases": vakalar,
        "passed": all(v["status"] == "passed" for v in vakalar),
    }


def referansla_karsilastir(sonuc: dict[str, Any], referans: dict[str, Any]) -> dict[str, Any]:
    """Aynı workload/thread vakalarının digestlerini klasik kolla karşılaştırır."""
    def digestler(veri: dict[str, Any]) -> dict[tuple[str, int], str]:
        return {
            (v["workload"], int(v["threads"])): str(v.get("result", {}).get("digest", ""))
            for v in veri.get("cases", []) if v.get("status") == "passed"
        }

    mevcut, beklenen = digestler(sonuc), digestler(referans)
    anahtarlar = sorted(set(mevcut) | set(beklenen))
    ayrismalar = [
        {"workload": ad, "threads": n, "current": mevcut.get((ad, n), ""),
         "reference": beklenen.get((ad, n), "")}
        for ad, n in anahtarlar if mevcut.get((ad, n)) != beklenen.get((ad, n))
    ]
    karsilastirma = {
        "reference_python": referans.get("python", ""),
        "case_count": len(anahtarlar),
        "digest_mismatches": ayrismalar,
        "passed": not ayrismalar and bool(anahtarlar),
    }
    sonuc["reference_comparison"] = karsilastirma
    sonuc["passed"] = bool(sonuc.get("passed")) and karsilastirma["passed"]
    return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--workload", choices=sorted(WORKLOADLAR))
    ap.add_argument("--workloads", default="numpy,numpy_linalg,torch,torch_inference")
    ap.add_argument("--threads", default="1,2,4,8")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--expect-gil", choices=("enabled", "disabled"), default="disabled",
                    help=argparse.SUPPRESS)
    ap.add_argument("--out", default="research/gil-scaling/results/free_threaded_stress.json")
    ap.add_argument("--reference", default="",
                    help="aynı Python sürümünün klasik kol sonuç JSON'u")
    args = ap.parse_args()

    if args.child:
        if not args.workload:
            ap.error("--child için --workload gerekli")
        return child(args.workload, int(args.threads), args.reps,
                     expected_gil=args.expect_gil == "enabled")

    workloads = [x.strip() for x in args.workloads.split(",") if x.strip()]
    bilinmeyen = sorted(set(workloads) - set(WORKLOADLAR))
    if bilinmeyen:
        ap.error(f"bilinmeyen workload: {', '.join(bilinmeyen)}")
    sonuc = parent(workloads, [int(x) for x in args.threads.split(",")],
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
