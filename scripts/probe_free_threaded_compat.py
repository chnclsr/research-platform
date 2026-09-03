"""Free-threaded uyumluluk deneyinin ucuz ve zorunlu ön kontrolü.

Bu araç performans veya thread-safety ölçmez. Yorumlayıcının gerçekten free-threaded
olduğunu, NumPy/PyTorch/Docling importlarının başarılı olduğunu ve hiçbir importun GIL'i
yeniden açmadığını kanıtlar. Bu kapı geçmeden stres matrisi çalıştırılmaz.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import platform
import sys
import sysconfig
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

PAKETLER = (("numpy", "numpy"), ("torch", "torch"), ("docling", "docling"))


def gil_etkin_mi() -> bool | None:
    denetle = getattr(sys, "_is_gil_enabled", None)
    return bool(denetle()) if denetle is not None else None


def free_threaded_build_mi() -> bool:
    return sysconfig.get_config_var("Py_GIL_DISABLED") == 1


def _uzantilar() -> list[str]:
    """Yüklü native modüllerin taşınabilir adları; yerel dosya yollarını kaydetmez."""
    return sorted(
        ad for ad, modul in sys.modules.items()
        if str(getattr(modul, "__file__", "")).endswith((".so", ".pyd", ".dylib"))
    )


def ortam_kapisi(
    import_module: Callable[[str], object] = importlib.import_module,
    version: Callable[[str], str] = importlib.metadata.version,
) -> dict[str, Any]:
    """Importları sırayla yapar; her birinden sonra GIL durumunu ayrı kaydeder."""
    baslangic_gil = gil_etkin_mi()
    paketler = []
    for modul_adi, dagitim_adi in PAKETLER:
        kayit: dict[str, Any] = {"module": modul_adi, "distribution": dagitim_adi}
        with warnings.catch_warnings(record=True) as yakalanan:
            warnings.simplefilter("always")
            try:
                import_module(modul_adi)
                kayit["import_ok"] = True
                kayit["version"] = version(dagitim_adi)
                kayit["error"] = ""
            except Exception as exc:  # noqa: BLE001 -- uyumluluk bulgusu olarak kaydedilir
                kayit["import_ok"] = False
                kayit["version"] = ""
                kayit["error"] = f"{type(exc).__name__}: {exc}"
            kayit["warnings"] = [str(w.message) for w in yakalanan]
        kayit["gil_enabled_after_import"] = gil_etkin_mi()
        paketler.append(kayit)

    build = free_threaded_build_mi()
    son_gil = gil_etkin_mi()
    giller = [baslangic_gil, *(p["gil_enabled_after_import"] for p in paketler), son_gil]
    gecti = (
        build
        and all(g is False for g in giller)
        and all(p["import_ok"] for p in paketler)
    )
    return {
        "schema": "gil-scaling/free-threaded-compat-probe/1",
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "free_threaded_build": build,
        "gil_enabled_at_start": baslangic_gil,
        "packages": paketler,
        "gil_enabled_at_end": son_gil,
        "loaded_native_modules": _uzantilar(),
        "passed": gecti,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="research/gil-scaling/results/free_threaded_probe.json")
    args = ap.parse_args()

    sonuc = ortam_kapisi()
    hedef = Path(args.out)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(sonuc, indent=2, ensure_ascii=False))
    return 0 if sonuc["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
