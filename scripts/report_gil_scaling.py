"""
Ölçüm JSON'undan tablo, rapor ve grafik üretir.

TÜRETİLMİŞ HER ŞEY BURADA. Benchmark yalnız ölçtüğünü yazar (`wall_ns`,
`thread_time_ns`, `process_cpu_ns`, ...); `scaling`, `throughput`,
`cpu_core_equivalent` ve yük filtresi bu dosyada hesaplanır. Formül değişince ölçümü
tekrarlamak gerekmesin diye.

İKİ SAYI BİRLİKTE OKUNUR, TEK BAŞINA DEĞİL:

    scaling(N)           N thread ile birim zamanda kaç iş bitiyor, N=1'e oranla
    cpu_core_equivalent  aynı anda kaç çekirdek meşgul (thread_time / wall)

`scaling ≈ 1` TEK BAŞINA "GIL tutuyor" DEMEK DEĞİLDİR -- kütüphane içi kilit, bellek
bant genişliği, DB havuzu, disk, harici servis ya da kütüphanenin kendi thread havuzu
da aynı sonucu verir. `cpu_core_equivalent ≈ 1` ikinci kanıttır: iş CPU'da ve tek
çekirdekte. Üçüncüsü (GIL-tutma oranı) Aşama 2'nin profilinden gelir; o gelmeden
buradaki hiçbir satıra "GIL" etiketi yapıştırılmaz.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

#: Bu yükün üstünde başlayan ölçümler elenir. Koşu sırasında makinede başka bir iş
#: başlamışsa o ölçüm kirlidir. Elenen sayısı rapora yazılır -- sessizce atılmaz.
YUK_ESIGI_CARPAN = 2.5


def _yukle(yol: Path) -> dict[str, Any]:
    return json.loads(yol.read_text(encoding="utf-8"))


def _filtrele(veri: dict[str, Any]) -> tuple[list[dict], int, float]:
    """Yükü anormal yüksek olan ölçümleri eler."""
    olcumler = [m for m in veri["measurements"] if m["wall_ns"] > 0 and not m["exception"]]
    yukler = [m["load_at_start"] for m in olcumler]
    taban = statistics.median(yukler) if yukler else 0.0
    esik = max(taban * YUK_ESIGI_CARPAN, taban + 2.0)
    temiz = [m for m in olcumler if m["load_at_start"] <= esik]
    return temiz, len(olcumler) - len(temiz), esik


def ozet(veri: dict[str, Any]) -> dict[str, Any]:
    temiz, elenen, esik = _filtrele(veri)
    threadler = sorted({m["threads"] for m in temiz})

    satirlar: dict[str, dict[str, Any]] = {}
    for m in temiz:
        w = satirlar.setdefault(m["workload"], {"throughput": {}, "cpu_eq": {},
                                                "proc_eq": {}, "digest": set(),
                                                "ayrisma": False})
        w["throughput"].setdefault(m["threads"], []).append(m["ops_ok"] / m["wall_ns"])
        w["cpu_eq"].setdefault(m["threads"], []).append(
            m["thread_time_ns_total"] / m["wall_ns"])
        # process_cpu ayri tutulur: thread_time YALNIZ bizim actigimiz thread'leri
        # sayar, bir native uzantinin kendi yardimci thread'lerini gormez. Ikisi
        # ayrisiyorsa fark tam olarak o gorunmeyen istir.
        w["proc_eq"].setdefault(m["threads"], []).append(
            m["process_cpu_ns"] / m["wall_ns"])
        if m["result_digest"]:
            w["digest"].add(m["result_digest"])
        w["ayrisma"] = w["ayrisma"] or m["digest_divergence"]

    sonuc = []
    for ad, w in sorted(satirlar.items()):
        tp = {n: statistics.median(v) for n, v in w["throughput"].items()}
        taban = tp.get(1, 0.0)
        sonuc.append({
            "workload": ad,
            "scaling": {n: (tp[n] / taban if taban > 0 else 0.0) for n in sorted(tp)},
            "cpu_eq": {n: statistics.median(v) for n, v in sorted(w["cpu_eq"].items())},
            "proc_eq": {n: statistics.median(v) for n, v in sorted(w["proc_eq"].items())},
            "p95_wall_ns": {},
            "digest_sayisi": len(w["digest"]),
            "digest_ayrismasi": w["ayrisma"],
        })

    # p95: pahalı ölçümlerde p95 raporlanmaz; burada n>=20 olduğu için raporlanır.
    for satir in sonuc:
        for n in threadler:
            duvarlar = sorted(m["wall_ns"] for m in temiz
                              if m["workload"] == satir["workload"] and m["threads"] == n)
            if len(duvarlar) >= 20:
                satir["p95_wall_ns"][n] = duvarlar[int(len(duvarlar) * 0.95) - 1]

    # Yuk filtresi duyarliligi. Load average deneyin KENDI thread'lerinden de
    # etkilenir, dolayisiyla dis gurultu filtresi olarak zayiftir. Filtreyi tamamen
    # kaldirip ayni hesabi yapiyoruz: sonuc degismiyorsa filtre sonucu tasimiyor
    # demektir ve bu acikca raporlanmali.
    filtresiz: dict[str, dict[int, float]] = {}
    ham = [m for m in veri["measurements"] if m["wall_ns"] > 0 and not m["exception"]]
    for ad in {m["workload"] for m in ham}:
        tp: dict[int, list[float]] = {}
        for m in [x for x in ham if x["workload"] == ad]:
            tp.setdefault(m["threads"], []).append(m["ops_ok"] / m["wall_ns"])
        taban = statistics.median(tp[1]) if 1 in tp else 0.0
        if taban > 0:
            filtresiz[ad] = {n: statistics.median(v) / taban for n, v in sorted(tp.items())}
    en_buyuk_fark = 0.0
    for satir in sonuc:
        ref = filtresiz.get(satir["workload"], {})
        for n, deger in satir["scaling"].items():
            if n in ref:
                en_buyuk_fark = max(en_buyuk_fark, abs(deger - ref[n]))

    return {
        "arm": veri["arm"],
        "host": veri["host"],
        "repo": veri.get("repo", {}),
        "threads": threadler,
        "reps": veri.get("reps"),
        "elenen_olcum": elenen,
        "yuk_esigi": round(esik, 2),
        "yuk_araligi": {
            "min": round(min(m["load_at_start"] for m in ham), 2),
            "medyan": round(statistics.median([m["load_at_start"] for m in ham]), 2),
            "max": round(max(m["load_at_start"] for m in ham), 2),
        },
        "filtre_duyarliligi_en_buyuk_fark": round(en_buyuk_fark, 4),
        "satirlar": sonuc,
    }


def tablo(o: dict[str, Any]) -> str:
    threadler = o["threads"]
    basliklar = "".join(f"{'s(' + str(n) + ')':>8}" for n in threadler)
    satirlar = [
        f"{'workload':<28}{basliklar}   |{'thread_eq':>11}{'process_eq':>12}",
        "-" * (28 + 8 * len(threadler) + 4 + 23),
    ]
    enb = max(threadler)
    for s in o["satirlar"]:
        olcek = "".join(f"{s['scaling'].get(n, 0):>8.2f}" for n in threadler)
        te = s["cpu_eq"].get(enb, 0)
        pe = s.get("proc_eq", {}).get(enb, 0)
        isaret = "  <-- ayrisma" if abs(pe - te) > 0.1 else ""
        satirlar.append(f"{s['workload']:<28}{olcek}   |{te:>11.2f}{pe:>12.2f}{isaret}")
    satirlar.append("")
    satirlar.append(f"s(N) = throughput(N)/throughput(1)  |  N={enb} icin cekirdek esdegeri")
    satirlar.append("thread_eq  = bizim actigimiz thread'lerin CPU zamani / duvar saati")
    satirlar.append("process_eq = process'in TUM CPU zamani / duvar saati (native yardimci")
    satirlar.append("             thread'ler dahil). Ikisi ayrisiyorsa fark gorunmeyen istir.")
    return "\n".join(satirlar)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="research/gil-scaling/results/thread_scaling.json")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    veri = _yukle(Path(args.input))
    o = ozet(veri)

    print(f"kol      : {o['arm']['id']}  python {o['arm']['python']}  "
          f"free-threaded build: {o['arm']['free_threaded_build']}")
    print(f"gil      : {o['arm']['gil_enabled_at']}")
    print(f"makine   : {o['host']['cpu_count']} cekirdek  {o['host']['cpu_model'][:44]}")
    ya = o["yuk_araligi"]
    print(f"tekrar   : {o['reps']}   elenen olcum: {o['elenen_olcum']} "
          f"(yuk esigi {o['yuk_esigi']})")
    print(f"yuk      : min {ya['min']}  medyan {ya['medyan']}  max {ya['max']}")
    print(f"duyarlilik: filtre kaldirilinca en buyuk scaling farki "
          f"{o['filtre_duyarliligi_en_buyuk_fark']}")
    print()
    print(tablo(o))

    ayrisan = [s["workload"] for s in o["satirlar"] if s["digest_ayrismasi"]]
    if ayrisan:
        print(f"\nDIKKAT digest ayrismasi: {ayrisan}")
    coklu = [(s["workload"], s["digest_sayisi"]) for s in o["satirlar"]
             if s["digest_sayisi"] > 1]
    if coklu:
        print(f"\nDIKKAT ayni girdi birden fazla digest uretti: {coklu}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(o, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
