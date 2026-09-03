"""
Bir kolun (arm) kimliği: yorumlayıcı, GIL durumu, yüklenen uzantılar, paket sürümleri.

NEDEN. Free-threading uyumlu olduğunu bildirmeyen tek bir C extension import edildiğinde
CPython GIL'i geri açar ve bir uyarı basar. Uyarı loglarda kaybolabilir; dahası lazy
import yüzünden tek bir kontrol yetmez -- sonradan import edilen bir modül GIL'i koşunun
ortasında geri açabilir. O yüzden `gil_durumu()` koşu boyunca DÖRT noktada çağrılır ve
dördü de sonuca yazılır. D kolunda herhangi biri True ise o koşu geçersizdir.

`abi3` olmak free-threading uyumluluğu anlamına GELMEZ; bu yüzden yüklenen `.so`
envanteri de kaydedilir -- bir kol beklenmedik şekilde GIL'e dönerse suçluyu aramaya
oradan başlanır.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import sysconfig


def gil_etkin_mi() -> bool | None:
    """`sys._is_gil_enabled()`; API yoksa None (free-threading öncesi yorumlayıcı)."""
    fn = getattr(sys, "_is_gil_enabled", None)
    if fn is None:
        return None
    try:
        return bool(fn())
    except Exception:  # noqa: BLE001 -- probe olcumu cokertmemeli; bilinmeyen, hata degildir
        return None


def serbest_thread_build_mi() -> bool:
    """Yorumlayıcı free-threaded build mi (GIL açık olsa bile)."""
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def yuklu_uzantilar() -> list[str]:
    """Şu an yüklü olan C uzantı modüllerinin dosya yolları, sıralı."""
    yollar = []
    for ad, modul in list(sys.modules.items()):
        dosya = getattr(modul, "__file__", None) or ""
        if dosya.endswith((".so", ".pyd", ".dylib")):
            yollar.append(f"{ad}={dosya}")
    return sorted(yollar)


def paket_surumleri(paketler: list[str]) -> dict[str, str]:
    import importlib.metadata as md

    sonuc = {}
    for ad in paketler:
        try:
            sonuc[ad] = md.version(ad)
        except Exception:  # noqa: BLE001 -- probe olcumu cokertmemeli; bilinmeyen, hata degildir
            sonuc[ad] = "(kurulu degil)"
    return sonuc


def git_durumu() -> dict[str, object]:
    def kos(*args: str) -> str:
        try:
            return subprocess.run(
                args, capture_output=True, text=True, timeout=10, check=False,
            ).stdout.strip()
        except Exception:  # noqa: BLE001 -- probe olcumu cokertmemeli; bilinmeyen, hata degildir
            return ""

    return {
        "commit": kos("git", "rev-parse", "HEAD"),
        "dirty": bool(kos("git", "status", "--porcelain")),
    }


def makine() -> dict[str, object]:
    import psutil

    model = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for satir in fh:
                if satir.startswith("model name"):
                    model = satir.split(":", 1)[1].strip()
                    break
    except Exception:  # noqa: BLE001,S110 -- cpuinfo yoksa model adi bos kalir
        pass
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except Exception:  # noqa: BLE001 -- probe olcumu cokertmemeli; bilinmeyen, hata degildir
        affinity = []
    return {
        "cpu_model": model,
        "cpu_count": psutil.cpu_count() or 0,
        "os": platform.platform(),
        "kernel": platform.release(),
        "affinity": affinity,
        "load_before": os.getloadavg()[0],
    }


#: Kol kimliğine yazılan paketler. Sıcak olanlarla sınırlı DEĞİL: import edildiğinde
#: GIL'i geri açabilecek her native paket burada olmalı.
IZLENEN_PAKETLER = [
    "pdf-inspector", "pymupdf", "pypdf", "pydantic", "pydantic-core", "sqlalchemy",
    "asyncpg", "greenlet", "orjson", "ormsgpack", "msgspec", "PyYAML", "psutil",
    "hiredis", "uvloop", "rapidfuzz", "xxhash", "lxml", "pillow", "python-docx",
    "langgraph", "langchain-core", "httpx", "cffi", "rpds-py", "zstandard",
]


def kol_kimligi(kol_id: str = "A") -> dict[str, object]:
    """Sonuç JSON'unun `arm` bloğu. `gil_enabled_at` sonradan doldurulur."""
    return {
        "id": kol_id,
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "free_threaded_build": serbest_thread_build_mi(),
        "flags": sys.orig_argv[1:-1] if len(sys.orig_argv) > 2 else [],
        "gil_enabled_at": {},
        "packages": paket_surumleri(IZLENEN_PAKETLER),
    }


if __name__ == "__main__":
    print(json.dumps({
        "arm": kol_kimligi(os.environ.get("GIL_ARM_ID", "A")),
        "host": makine(),
        "repo": git_durumu(),
        "gil_enabled": gil_etkin_mi(),
        "loaded_extensions": yuklu_uzantilar(),
    }, indent=2, ensure_ascii=False))
