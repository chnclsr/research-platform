"""
Speedscope profillerinden GIL-tutma oranını ve native kırılımı okur.

NEDEN AYRI BIR SCRIPT. `profile_gil_ratio.py` örnek sayılarını py-spy'in stderr
çıktısından okuyordu; koşu yarıda kesilirse o sayılar kaybolur ama diske yazılan
profiller durur. Buradaki okuma profil dosyalarının kendisinden yapılıyor, dolayısıyla
kesilen bir koşu tekrar edilmeden değerlendirilebilir ve sayı py-spy'in özet satırına
değil ham veriye dayanır.

ORAN. gil_ratio = ornek(--gil profili) / ornek(normal profil). Yorumu kontrollerden
okunur, teoriden degil: saf-Python 0.698, GIL-birakan hashlib 0.088 olctuk.

ORAN TEK BASINA YETMEZ. `control_io_like` bu metrikte 1.01 veriyor -- sleep GIL
tutmadigi halde. Sebep py-spy'in bosta thread'leri dislamasi: geriye yalniz ana thread
kaliyor. Ele veren sey MUTLAK ornek sayisi (380, digerinin 17848'ine karsi). O yuzden
oran ile ornek yogunlugu HER ZAMAN birlikte raporlanir.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parents[1]


def _ornek_sayisi(yol: Path) -> tuple[int, int]:
    """(toplam ornek, profil/thread sayisi)."""
    if not yol.exists():
        return 0, 0
    veri = json.loads(yol.read_text(encoding="utf-8"))
    profiller = veri.get("profiles") or []
    return sum(len(p.get("samples") or []) for p in profiller), len(profiller)


def _cerceve_dagilimi(yol: Path, ilk: int = 12) -> list[tuple[str, int]]:
    """En cok ornekte GORULEN yaprak cerceveler -- zamanin nerede gectigi."""
    if not yol.exists():
        return []
    veri = json.loads(yol.read_text(encoding="utf-8"))
    adlar = [f.get("name", "?") for f in (veri.get("shared") or {}).get("frames") or []]
    sayac: Counter[str] = Counter()
    for p in veri.get("profiles") or []:
        for ornek in p.get("samples") or []:
            if ornek:
                idx = ornek[-1]
                sayac[adlar[idx] if 0 <= idx < len(adlar) else "?"] += 1
    return sayac.most_common(ilk)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profiles-dir", default="research/gil-scaling/results/profiles")
    ap.add_argument("--out", default="research/gil-scaling/results/gil_ratio.json")
    ap.add_argument("--native-frames", default="",
                    help="bu workload icin native cerceve dagilimini da yaz")
    args = ap.parse_args()

    dizin = KOK / args.profiles_dir
    adlar = sorted({p.name.rsplit("_", 1)[0] for p in dizin.glob("*_normal.json")})

    satirlar: list[dict[str, Any]] = []
    for ad in adlar:
        n, n_thread = _ornek_sayisi(dizin / f"{ad}_normal.json")
        g, _ = _ornek_sayisi(dizin / f"{ad}_gil.json")
        satirlar.append({
            "workload": ad,
            "normal_samples": n,
            "gil_samples": g,
            "profiles_in_normal": n_thread,
            "gil_ratio": round(g / n, 4) if n else None,
        })

    sonuc: dict[str, Any] = {
        "schema": "gil-scaling/gil-ratio/2",
        "kaynak": "speedscope profillerinden okundu",
        "satirlar": satirlar,
    }
    if args.native_frames:
        sonuc["native_frames"] = {
            args.native_frames:
                _cerceve_dagilimi(dizin / f"{args.native_frames}_native.json")
        }

    hedef = KOK / args.out
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'workload':<30}{'normal':>9}{'--gil':>9}{'gil_ratio':>11}")
    print("-" * 59)
    for s in satirlar:
        r = s["gil_ratio"]
        print(f"{s['workload']:<30}{s['normal_samples']:>9}{s['gil_samples']:>9}"
              f"{(f'{r:.3f}' if r is not None else 'yok'):>11}")
    if args.native_frames:
        print(f"\n--- {args.native_frames} native yaprak cerceveler ---")
        for ad, n in sonuc["native_frames"][args.native_frames]:
            print(f"  {n:>7}  {ad[:70]}")
    print(f"\nyazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
