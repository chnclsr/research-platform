"""
Aşama 2b-hafif — gerçek koşuların duvar saatini mevcut telemetriden ayrıştırır.

NEDEN BU VAR. Aşama 2b'nin asıl sorusu "bu CPU işlerinin gerçek bir koşudaki payı ne?",
yani kazanç tavanı. Tam cevabı canlı bir koşuyu profillemek verir; ama payın BÜYÜK
kısmı zaten kayıtlı: platform her koşuda `run_events` tablosuna `stage` geçişlerini ve
`llm_metrics` içinde çağrı başına `wall_seconds` yazıyor. Yani LLM beklemesinin payı
yeni koşu yapmadan, hiçbir yetki gerektirmeden çıkarılabilir.

TAVANIN MANTIGI. Koşu duvar saatinin LLM'de geçen kısmı GIL'den etkilenmez -- o süre
Ollama'ya gitmiş bir HTTP isteğinin dönmesini beklemekle geçer ve
`MODEL_MAX_CONCURRENT_CALLS=1` yüzünden zaten platform genelinde serileşmiştir. Geriye
kalan ("diger") her şeyin ÜST SINIRI, GIL'in etkileyebileceği paydir:

    tavan <= 1 - (LLM payi)

Bu bir üst sınırdır, tahmin değil: "diger" içinde ağ, disk, docling servisi beklemesi ve
GIL bırakan C işi de var. Gerçek pay bundan küçüktür. py-spy profili "diger"i ayrıştırıp
gerçek payı verecek; bu script tavanı verir.

NE OLCMEZ. CPU payını ölçmez, GIL payını ölçmez. Yalnız "LLM beklemesi" ile "geri kalan"
ayrımını yapar ve geri kalanı üst sınır olarak sunar.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from typing import Any

VARSAYILAN_KONTEYNER = "research-platform-postgres-1"
SORGU = """
select r.id, r.status,
       extract(epoch from (max(e.created_at) - min(e.created_at))) as span_s,
       count(*) filter (where e.event_type = 'stage') as stage_events,
       coalesce(sum(
         (select coalesce(sum((c->>'wall_seconds')::float), 0)
          from json_array_elements(e.payload->'calls') c)
       ) filter (where e.event_type = 'llm_metrics'), 0) as llm_s
from research_runs r join run_events e on e.run_id = r.id
group by r.id, r.status
having count(*) filter (where e.event_type = 'stage') > 0
order by span_s desc;
"""


def _psql(konteyner: str, sorgu: str) -> list[list[str]]:
    c = subprocess.run(
        ["docker", "exec", konteyner, "psql", "-U", "research", "-d", "research",
         "-tAF", "\x1f", "-c", sorgu],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if c.returncode != 0:
        raise RuntimeError(f"psql basarisiz: {c.stderr.strip()[:300]}")
    return [s.split("\x1f") for s in c.stdout.strip().splitlines() if s.strip()]


TELEMETRI_SORGU = """
select coalesce(s->>'stage','?'), coalesce(s->>'active_run_count','?'),
       (s->>'worker_cpu_percent')::float, (s->>'system_cpu_percent')::float
from run_events e, json_array_elements(e.payload->'samples') s
where e.event_type = 'hardware_telemetry_samples';
"""


def telemetri(konteyner: str) -> dict[str, Any]:
    """Worker process'inin toplam CPU kullanımı, stage ve eşzamanlılık kırılımıyla.

    `worker_cpu_percent` = psutil.Process.cpu_percent(), yani %100 = BIR TAM CEKIRDEK.
    Bu sayı GIL altında çalışan Python'un yanında GIL bırakan native işi de kapsar;
    dolayısıyla GIL payı değil, onun erişebileceği alan için bir üst sınırdır. Worker
    ortalaması bir çekirdeğin çok altındaysa GIL ortalama CPU kapasitesinin ana sınırı
    olamaz. %100'e yaklaşması ise tek başına GIL kanıtı değildir; profiler gerekir.
    """
    ham = _psql(konteyner, TELEMETRI_SORGU)
    if not ham:
        return {}
    degerler = [float(r[2]) for r in ham]
    per_stage: dict[str, list[float]] = {}
    per_kosu: dict[str, list[float]] = {}
    for stage, aktif, worker, _sistem in ham:
        per_stage.setdefault(stage, []).append(float(worker))
        per_kosu.setdefault(aktif, []).append(float(worker))

    def _ist(v: list[float]) -> dict[str, float]:
        s = sorted(v)
        return {
            "n": len(s),
            "ort": round(sum(s) / len(s), 1),
            "p95": round(s[min(len(s) - 1, int(len(s) * 0.95))], 1),
            "maks": round(s[-1], 1),
        }

    return {
        "birim": "worker_cpu_percent -- %100 = bir tam cekirdek",
        "toplam": _ist(degerler),
        "stage_bazinda": {k: _ist(v) for k, v in
                          sorted(per_stage.items(), key=lambda kv: -len(kv[1]))},
        "eszamanli_kosu_bazinda": {k: _ist(v) for k, v in sorted(per_kosu.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--container", default=VARSAYILAN_KONTEYNER)
    ap.add_argument("--min-span", type=float, default=60.0,
                    help="bu kadar kisa kosular atlanir; anlamli pay tasimazlar")
    ap.add_argument("--out", default="research/gil-scaling/results/run_breakdown.json")
    args = ap.parse_args()

    satirlar = []
    for run_id, status, span, stage_n, llm in _psql(args.container, SORGU):
        span_s, llm_s = float(span or 0), float(llm or 0)
        if span_s < args.min_span:
            continue
        satirlar.append({
            "run_id": run_id,
            "status": status,
            "span_s": round(span_s, 1),
            "stage_events": int(stage_n),
            "llm_s": round(llm_s, 1),
            "llm_pay": round(llm_s / span_s, 4) if span_s else None,
            # Tavan: LLM disinda kalan her sey. Ust SINIR -- icinde ag, disk,
            # docling beklemesi ve GIL birakan C isi de var.
            "gil_tavani_ust_sinir": round(1 - llm_s / span_s, 4) if span_s else None,
        })

    if not satirlar:
        print(f"{args.min_span} sn'den uzun, telemetrisi olan kosu bulunamadi")
        return 1

    paylar = [s["llm_pay"] for s in satirlar if s["llm_pay"] is not None]
    ozet = {
        "kosu_sayisi": len(satirlar),
        "llm_pay_medyan": round(statistics.median(paylar), 4),
        "llm_pay_min": round(min(paylar), 4),
        "llm_pay_max": round(max(paylar), 4),
        "tavan_medyan": round(1 - statistics.median(paylar), 4),
    }

    print(f"{'run_id':<28}{'durum':<22}{'span_s':>9}{'llm_s':>9}{'llm_pay':>9}{'tavan':>8}")
    print("-" * 85)
    for s in satirlar:
        print(f"{s['run_id']:<28}{s['status']:<22}{s['span_s']:>9.1f}{s['llm_s']:>9.1f}"
              f"{s['llm_pay']:>9.1%}{s['gil_tavani_ust_sinir']:>8.1%}")
    print()
    print(f"{ozet['kosu_sayisi']} kosu | LLM payi medyan {ozet['llm_pay_medyan']:.1%} "
          f"(min {ozet['llm_pay_min']:.1%}, maks {ozet['llm_pay_max']:.1%})")
    print(f"GIL'in etkileyebilecegi payin UST SINIRI: medyan {ozet['tavan_medyan']:.1%}")
    print("  (ust sinir -- icinde ag, disk, docling beklemesi ve GIL birakan C isi de var)")

    from pathlib import Path

    hedef = Path(args.out)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    tel = telemetri(args.container)
    if tel:
        top = tel["toplam"]
        print()
        print(f"WORKER CPU (%100 = bir tam cekirdek) -- {top['n']} ornek")
        print(f"  ortalama {top['ort']}%   p95 {top['p95']}%   maks {top['maks']}%")
        print(f"{'stage':<24}{'n':>6}{'ort%':>8}{'p95%':>8}{'maks%':>8}")
        print("-" * 54)
        for ad, v in tel["stage_bazinda"].items():
            print(f"{ad:<24}{v['n']:>6}{v['ort']:>8}{v['p95']:>8}{v['maks']:>8}")

    hedef.write_text(json.dumps({"schema": "gil-scaling/run-breakdown/2",
                                 "ozet": ozet, "kosular": satirlar,
                                 "worker_cpu": tel},
                                indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nyazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
