"""
Aşama 2a — bir işin GIL'i ne kadar tuttuğunu ölçer.

SORU. Aşama 1 altı parse adayının thread'lerle ölçeklenmediğini gösterdi. Ama
"ölçeklenmiyor" tek başına "GIL tutuyor" demek değil: kütüphane içi kilit, bellek bant
genişliği, disk ya da kütüphanenin kendi thread havuzu da aynı sonucu verir. Bu script
üçüncü kanıtı üretir.

METRİK.

    gil_ratio = ornek(py-spy --gil) / ornek(py-spy normal)

py-spy `--gil` yalnız GIL'i TUTAN thread'leri örnekler; normal koşu çalışan bütün
thread'leri örnekler. İkisi de aynı sabit işi (`--iterations`) aynı örnekleme hızıyla
koşar, dolayısıyla oran karşılaştırılabilir.

İKİ AYRI KOŞU OLMASININ BEDELİ. py-spy tek koşuda iki profili birden vermiyor, bu yüzden
normal ve `--gil` ayrı koşuluyor. İş sabit (süre değil, yineleme sayısı sabitlenmiş) ama
duvar saati koşudan koşuya oynayabilir; o oynama `wall_delta` olarak kaydediliyor ve
oranın belirsizlik payıdır. Büyükse sonuç şüpheyle okunmalı.

ORANIN YORUMU ÖLÇÜLÜR, VARSAYILMAZ. 0.25 mi 0.9 mı "GIL-bound" demek, teoriden değil
kontrollerden okunur -- Aşama 1'deki aynı ilke. Üç kontrol de aynı ölçümden geçer:

    control_gil_bound      saf-Python  -> GIL tutan isin orani neyse O'dur
    control_gil_releasing  hashlib     -> GIL birakan isin orani neyse O'dur
    control_io_like        sleep       -> hic CPU isi olmayan isin orani

Bir workload'ın oranı `gil_bound`'unkine yakınsa GIL tutuyor; `gil_releasing`'inkine
yakınsa tutmuyor. Arada ise ne olduğu belirsizdir ve öyle raporlanır.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "research" / "gil-scaling"))
sys.path.insert(0, str(KOK / "scripts"))

import gil_env_probe as probe

SEMA = "gil-scaling/gil-ratio/1"
PY = str(KOK / ".venv311" / "bin" / "python")
HARNESS = str(KOK / "scripts" / "benchmark_thread_scaling.py")

#: Her profil koşusunun hedef süresi. Yeterli örnek toplansın diye; daha uzunu
#: ölçümü yavaşlatır, daha kısası örnek sayısını gürültüye açar.
HEDEF_SN = 20.0
#: py-spy örnekleme hızı. İki koşuda da AYNI olmalı, yoksa oran anlamsızlaşır.
HIZ = 200

_ORNEK = re.compile(r"Samples:\s*(\d+)")
_HATA = re.compile(r"Errors:\s*(\d+)")


def _tek_cagri_sn(workload: str) -> float:
    """Bir çağrının kabaca ne kadar sürdüğü; yineleme sayısını buradan türetiyoruz."""
    kod = (
        "import sys,time; sys.path.insert(0,'research/gil-scaling');"
        "from workloads import controls\n"
        "try:\n from workloads import parser_wl\nexcept ImportError: pass\n"
        "from workloads.contract import KAYIT\n"
        f"w=KAYIT.al({workload!r}); sh=w.setup_process(); st=w.setup_worker(sh)\n"
        "w.call(st)\n"
        "t0=time.perf_counter(); w.call(st); print(time.perf_counter()-t0)\n"
    )
    c = subprocess.run([PY, "-c", kod], capture_output=True, text=True,
                       cwd=KOK, timeout=300, check=False)
    try:
        return max(float(c.stdout.strip().splitlines()[-1]), 1e-6)
    except (ValueError, IndexError):
        return 0.001


def _pyspy(workload: str, threads: int, yineleme: int, gil: bool,
           native: bool, cikti: Path) -> dict[str, Any]:
    komut = ["py-spy", "record", "--rate", str(HIZ), "-o", str(cikti),
             "--format", "speedscope"]
    if gil:
        komut.append("--gil")
    if native:
        komut.append("--native")
    komut += ["--", PY, HARNESS, "profile_target",
              "--workload", workload, "--threads", str(threads),
              "--iterations", str(yineleme)]
    t0 = time.perf_counter()
    c = subprocess.run(komut, capture_output=True, text=True, cwd=KOK,
                       timeout=900, check=False)
    duvar = time.perf_counter() - t0
    ciktilar = (c.stderr or "") + (c.stdout or "")
    ornek = _ORNEK.search(ciktilar)
    hata = _HATA.search(ciktilar)
    return {
        "samples": int(ornek.group(1)) if ornek else 0,
        "errors": int(hata.group(1)) if hata else -1,
        "wall_s": round(duvar, 2),
        "returncode": c.returncode,
        "tail": ciktilar.strip()[-200:] if not ornek else "",
    }


def olc(workload: str, threads: int, cikti_dizin: Path,
        native: bool = False) -> dict[str, Any]:
    tek = _tek_cagri_sn(workload)
    # Yineleme: N thread paralel KOSMADIGI varsayimiyla degil, hedef sureye gore.
    # GIL'e takilan is serilestigi icin gercek sure bunun uzerine cikabilir; sorun
    # degil, iki kosu de ayni yinelemeyi yapiyor.
    yineleme = max(1, int(HEDEF_SN / (tek * threads)))
    print(f"  {workload}: tek cagri {tek*1000:.1f} ms -> {yineleme} yineleme x {threads} thread",
          file=sys.stderr)

    normal = _pyspy(workload, threads, yineleme, gil=False, native=False,
                    cikti=cikti_dizin / f"{workload}_normal.json")
    gil = _pyspy(workload, threads, yineleme, gil=True, native=False,
                 cikti=cikti_dizin / f"{workload}_gil.json")

    oran = gil["samples"] / normal["samples"] if normal["samples"] else None
    sonuc: dict[str, Any] = {
        "workload": workload,
        "threads": threads,
        "iterations": yineleme,
        "single_call_s": round(tek, 6),
        "normal": normal,
        "gil": gil,
        "gil_ratio": round(oran, 4) if oran is not None else None,
        # Iki ayri kosunun duvar saati farki: oranin belirsizlik payi.
        "wall_delta_pct": (round(abs(gil["wall_s"] - normal["wall_s"])
                                 / max(normal["wall_s"], 1e-9) * 100, 1)),
    }
    if native:
        sonuc["native"] = _pyspy(workload, threads, yineleme, gil=False, native=True,
                                 cikti=cikti_dizin / f"{workload}_native.json")
    return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workloads", default="")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--native-for", default="",
                    help="virgulle ayrilmis: bunlara ayrica --native profili al")
    ap.add_argument("--out", default="research/gil-scaling/results/gil_ratio.json")
    ap.add_argument("--profiles-dir", default="research/gil-scaling/results/profiles")
    args = ap.parse_args()

    from workloads import controls  # noqa: F401
    from workloads.contract import KAYIT

    try:
        from workloads import parser_wl  # noqa: F401
    except ImportError as exc:
        print(f"not: parser workloadlari yuklenemedi ({exc})", file=sys.stderr)

    adlar = ([a.strip() for a in args.workloads.split(",") if a.strip()]
             or [w.name for w in KAYIT.tumu()])
    native_icin = {a.strip() for a in args.native_for.split(",") if a.strip()}

    dizin = KOK / args.profiles_dir
    dizin.mkdir(parents=True, exist_ok=True)

    sonuc = {
        "schema": SEMA,
        "arm": probe.kol_kimligi("A"),
        "host": probe.makine(),
        "repo": probe.git_durumu(),
        "rate": HIZ,
        "target_s": HEDEF_SN,
        "threads": args.threads,
        "olcumler": [],
    }
    for ad in adlar:
        sonuc["olcumler"].append(
            olc(ad, args.threads, dizin, native=ad in native_icin))

    hedef = KOK / args.out
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"{'workload':<28}{'normal':>9}{'--gil':>9}{'gil_ratio':>11}{'wall_d%':>9}")
    print("-" * 66)
    for m in sonuc["olcumler"]:
        r = m["gil_ratio"]
        print(f"{m['workload']:<28}{m['normal']['samples']:>9}{m['gil']['samples']:>9}"
              f"{(f'{r:.3f}' if r is not None else 'yok'):>11}{m['wall_delta_pct']:>9.1f}")
    print(f"\nyazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
