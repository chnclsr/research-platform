"""
F1.1 -- bir işin thread sayısıyla nasıl ölçeklendiğini ölçer.

NE ÖLÇER, NE ÖLÇMEZ. Bu harness `scaling(N)` üretir: N thread ile birim zamanda kaç iş
bittiği, tek thread'e oranla. `scaling ≈ 1` TEK BAŞINA "GIL tutuyor" demek DEĞİLDİR --
kütüphane içi kilit, bellek bant genişliği, DB havuzu, disk, harici servis ya da
kütüphanenin kendi thread havuzu da aynı sonucu verir. GIL yorumu ancak bu ölçüm,
`cpu_core_equivalent` ve Aşama 2'nin profil verisi birlikte okunduğunda yazılır.
Yöntem ve gerekçe: research/gil-scaling/REPORT.md.

ZAMANLAMA DİSİPLİNİ. Ölçümün doğruluğu üç şeye bağlı ve üçü de burada zorlanıyor:

  1. Thread'ler zamanlamanın DIŞINDA kurulur. Havuz kurma maliyeti işin maliyeti değil.
  2. `setup_worker` zamanlamanın DIŞINDADIR. Ölçülen `call`, kurulum değil.
  3. Sayaç, bariyer bırakılmadan HEMEN ÖNCE başlar. Bunu `Barrier(action=...)` ile
     yapıyoruz: action, son worker bariyere vardığında ve HİÇBİRİ serbest bırakılmadan
     önce koşar. Sayacı ana thread'de `wait()`'ten önce başlatmak yanlış olurdu --
     worker'ların bariyere varma süresini de ölçerdi.

HAM VERİ HAM KALIR. Buradan çıkan JSON yalnız ölçüleni taşır: `wall_ns`,
`thread_time_ns`, `process_cpu_ns`, `child_cpu_ns`, RSS, digest. `scaling`, `throughput`,
`cpu_core_equivalent` gibi türetilmiş her şey report_gil_scaling.py'de hesaplanır --
formül değişince ölçümü tekrarlamak gerekmesin diye.

`process_cpu_ns` ZORUNLUDUR. `thread_time_ns` yalnız bizim açtığımız thread'leri sayar;
bir native uzantının kendi içinde açtığı yardımcı thread'leri ve process-pool child'larını
kaçırır. O işi görebilen tek sayaç process geneli olandır.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import resource
import sys
import threading
import time
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "research" / "gil-scaling"))
sys.path.insert(0, str(KOK / "scripts"))

import gil_env_probe as probe
from workloads.contract import (
    KAYIT,
    Workload,
    dogrula_paylasilan_state,
)

SEMA = "gil-scaling/thread-scaling/2"

#: Kalibrasyon hedefi: N=1'de worker başına bu kadar sürecek bir batch aranır.
#: 200-500 ms bandının ortası. Daha kısası zamanlayıcı ve scheduler gürültüsüne açık,
#: daha uzunu ölçümü gereksiz yavaşlatır.
HEDEF_BATCH_NS = 350_000_000
KALIBRASYON_DENEME = 5

VARSAYILAN_THREADLER = (1, 2, 4, 8, 16)
VARSAYILAN_TEKRAR = 20


def _rss() -> int:
    import psutil

    return int(psutil.Process().memory_info().rss)


def _child_cpu_ns() -> int:
    """Child process'lerin CPU zamanı. E1 (ProcessPool) kolunda tek görünür kaynak."""
    kullanim = resource.getrusage(resource.RUSAGE_CHILDREN)
    return int((kullanim.ru_utime + kullanim.ru_stime) * 1e9)


def olc_bir_kez(workload: Workload, shared: object, threads: int, batch: int) -> dict[str, Any]:
    """Tek bir ölçüm: N thread, her biri `batch` kez `call`.

    Dönen sözlük yalnız ölçüleni taşır; hiçbir oran burada hesaplanmaz.
    """
    # --- zamanlama DIŞINDA: worker state'leri
    if workload.state_scope == "shared":
        tekil = workload.setup_worker(shared)
        dogrula_paylasilan_state(workload, tekil)
        state_listesi = [tekil] * threads
    else:
        state_listesi = [workload.setup_worker(shared) for _ in range(threads)]

    thread_ns = [0] * threads
    basarili = [0] * threads
    digestler: list[str | None] = [None] * threads
    hatalar: list[str | None] = [None] * threads
    baslangic: dict[str, int] = {}

    def _sayaci_baslat() -> None:
        # Bariyerin action'ı: son worker vardı, hiçbiri henüz serbest değil.
        baslangic["rss"] = _rss()
        baslangic["child"] = _child_cpu_ns()
        baslangic["proc"] = time.process_time_ns()
        baslangic["wall"] = time.perf_counter_ns()

    bariyer = threading.Barrier(threads + 1, action=_sayaci_baslat)

    def _worker(idx: int) -> None:
        state = state_listesi[idx]
        try:
            bariyer.wait()
        except threading.BrokenBarrierError:
            return
        t0 = time.thread_time_ns()
        son: object = None
        tamam = 0
        try:
            for _ in range(batch):
                son = workload.call(state)
                tamam += 1
        except Exception as exc:  # noqa: BLE001 -- hata ölçümün parçası, sonuca yazılır
            hatalar[idx] = f"{type(exc).__name__}: {exc}"
        thread_ns[idx] = time.thread_time_ns() - t0
        basarili[idx] = tamam
        if hatalar[idx] is None:
            try:
                digestler[idx] = workload.canonicalize(son)
            except Exception as exc:  # noqa: BLE001
                hatalar[idx] = f"canonicalize: {type(exc).__name__}: {exc}"

    threadler = [threading.Thread(target=_worker, args=(i,), daemon=True)
                 for i in range(threads)]
    for t in threadler:
        t.start()
    bariyer.wait()  # <- action burada koşar, sonra hepsi birlikte salınır
    for t in threadler:
        t.join()

    duvar = time.perf_counter_ns() - baslangic["wall"]
    proc = time.process_time_ns() - baslangic["proc"]
    child = _child_cpu_ns() - baslangic["child"]
    rss_son = _rss()

    # Bütün worker'lar aynı digest'i üretmeli; üretmiyorsa bu bir bulgudur.
    gecerli = [d for d in digestler if d is not None]
    ayrisma = len(set(gecerli)) > 1

    return {
        "workload": workload.name,
        "threads": threads,
        "batch": batch,
        "ops_ok": sum(basarili),
        "ops_failed": threads * batch - sum(basarili),
        "exception": next((h for h in hatalar if h), None),
        "wall_ns": duvar,
        "thread_time_ns_total": sum(thread_ns),
        "per_thread_ns": thread_ns,
        "process_cpu_ns": proc,
        "child_cpu_ns": child,
        "rss_start": baslangic["rss"],
        "rss_end": rss_son,
        "result_digest": gecerli[0] if gecerli else None,
        "digest_divergence": ayrisma,
        "load_at_start": os.getloadavg()[0],
    }


def kalibre_et(workload: Workload, shared: object) -> tuple[int, list[dict[str, Any]]]:
    """N=1'de worker başına ~HEDEF_BATCH_NS sürecek batch'i bulur.

    Seçilen değer bütün N ve bütün kollarda SABİTLENİR: batch'in N ile değişmesi
    ölçeklenme oranını doğrudan bozar. Tek çağrısı zaten hedeften uzun olan bir
    workload'da batch=1 meşru sonuçtur.
    """
    batch = 1
    olcumler: list[dict[str, Any]] = []
    for _ in range(KALIBRASYON_DENEME):
        m = olc_bir_kez(workload, shared, 1, batch)
        olcumler.append({"batch": batch, "wall_ns": m["wall_ns"]})
        if m["exception"]:
            break
        if m["wall_ns"] >= HEDEF_BATCH_NS * 0.6:
            break
        tek_cagri = m["wall_ns"] / max(1, batch)
        if tek_cagri <= 0:
            batch = max(batch * 10, 10)
            continue
        hedef = int(HEDEF_BATCH_NS / tek_cagri)
        # Tek adımda 50 kattan fazla büyütme: kötü bir ilk ölçüm dakikalarca
        # sürecek bir batch üretmesin.
        batch = max(batch + 1, min(hedef, batch * 50))
    return batch, olcumler


def kos(
    workloadlar: list[Workload],
    threadler: tuple[int, ...],
    tekrar: int,
    seed: int,
    kol_id: str,
) -> dict[str, Any]:
    gil_noktalari = {"start": probe.gil_etkin_mi()}

    kol = probe.kol_kimligi(kol_id)
    sonuc: dict[str, Any] = {
        "schema": SEMA,
        "arm": kol,
        "host": probe.makine(),
        "repo": probe.git_durumu(),
        "seed": seed,
        "threads_tested": list(threadler),
        "reps": tekrar,
        "batch_calibration": [],
        "measurements": [],
    }

    # --- process seviyesi kurulum ve kalibrasyon
    paylasilan: dict[str, object] = {}
    batchler: dict[str, int] = {}
    for w in workloadlar:
        paylasilan[w.name] = w.setup_process()
        if w.batch is not None:
            batchler[w.name] = w.batch
            sonuc["batch_calibration"].append(
                {"workload": w.name, "chosen_batch": w.batch, "measured": "sabit"}
            )
            continue
        secilen, olcumler = kalibre_et(w, paylasilan[w.name])
        batchler[w.name] = secilen
        sonuc["batch_calibration"].append(
            {"workload": w.name, "chosen_batch": secilen, "measured": olcumler}
        )
        print(f"  kalibre {w.name}: batch={secilen}", file=sys.stderr)

    gil_noktalari["at_run"] = probe.gil_etkin_mi()

    # --- warm-up: her (workload, N) için bir kez, ATILIR
    for w in workloadlar:
        for n in threadler:
            olc_bir_kez(w, paylasilan[w.name], n, batchler[w.name])

    # --- ölçüm sırası randomize: sıra pozisyonu etkisini dengelemek için
    gorevler = [(w, n, r) for w in workloadlar for n in threadler for r in range(tekrar)]
    random.Random(seed).shuffle(gorevler)

    toplam = len(gorevler)
    for i, (w, n, r) in enumerate(gorevler, 1):
        m = olc_bir_kez(w, paylasilan[w.name], n, batchler[w.name])
        m["rep"] = r
        sonuc["measurements"].append(m)
        if i % 25 == 0 or i == toplam:
            print(f"  {i}/{toplam}", file=sys.stderr)

    gil_noktalari["at_end"] = probe.gil_etkin_mi()
    kol["gil_enabled_at"] = gil_noktalari
    sonuc["loaded_extensions"] = probe.yuklu_uzantilar()
    return sonuc


# --- türetilmişler: YALNIZ self_check ve ekrana basma için. Kanonik hesap
# --- report_gil_scaling.py'de; buradaki kopya rapora girmez.
def _medyan(degerler: list[float]) -> float:
    if not degerler:
        return 0.0
    s = sorted(degerler)
    orta = len(s) // 2
    return s[orta] if len(s) % 2 else (s[orta - 1] + s[orta]) / 2


def olcekleme(sonuc: dict[str, Any], workload: str) -> dict[int, float]:
    """throughput(N)/throughput(1). Yalnız self_check için."""
    per_n: dict[int, list[float]] = {}
    for m in sonuc["measurements"]:
        if m["workload"] != workload or m["wall_ns"] <= 0:
            continue
        per_n.setdefault(m["threads"], []).append(m["ops_ok"] / m["wall_ns"])
    if 1 not in per_n:
        return {}
    taban = _medyan(per_n[1])
    if taban <= 0:
        return {}
    return {n: _medyan(v) / taban for n, v in sorted(per_n.items())}


def self_check(tekrar: int, cikti: str = "") -> int:
    """Üç kontrolü gerçek makinede koşturur ve eşikleri raporlar.

    pytest'te DEĞİL: performans eşikleri CI'da flaky olur. Burası ölçümden hemen önce
    elle koşulan kapı. Geçmezse hiçbir gerçek ölçüm güvenilir değildir.
    """
    from workloads import controls

    workloadlar = KAYIT.kategori("control")
    print(f"self_check: {len(workloadlar)} kontrol, {tekrar} tekrar", file=sys.stderr)
    sonuc = kos(workloadlar, (1, 4), tekrar, seed=1, kol_id="self_check")

    print()
    print(f"{'kontrol':<24} {'scaling(4)':>11}  {'esik':<16} sonuc")
    print("-" * 68)
    basarisiz = 0
    for w in workloadlar:
        olcek = olcekleme(sonuc, w.name)
        s4 = olcek.get(4, 0.0)
        yon, esik = controls.ESIKLER[w.name]
        gecti = s4 >= esik if ">=" in yon else s4 <= esik
        basarisiz += 0 if gecti else 1
        print(f"{w.name:<24} {s4:>11.2f}  {yon} {esik:<6} {'GECTI' if gecti else 'KALDI'}")
    print()
    if basarisiz:
        print(f"{basarisiz} kontrol kaldi -- harness guvenilir degil, olcum yapilmamali",
              file=sys.stderr)
    else:
        print("uc kontrol de gecti -- harness olcum icin hazir", file=sys.stderr)

    # Kontroller kanit zincirinin parcasi: terminal ciktisi olarak kalmamali, ham
    # verisi parser olcumleriyle ayni bicimde saklanmali ki tekrar uretilebilsin.
    if cikti:
        sonuc["thresholds"] = {ad: {"yon": y, "esik": e}
                               for ad, (y, e) in controls.ESIKLER.items()}
        sonuc["verdict"] = {w.name: olcekleme(sonuc, w.name).get(4, 0.0)
                            for w in workloadlar}
        hedef = Path(cikti)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"yazildi: {hedef} ({len(sonuc['measurements'])} olcum)", file=sys.stderr)
    return 1 if basarisiz else 0


def profil_hedefi(workload_adi: str, threads: int, yineleme: int) -> int:
    """py-spy'in sarmalayacagi is: olcum YOK, yalniz calisma.

    Ayri bir alt komut, cunku profil altinda kosan sey benchmark'in kendi
    zamanlama ve kalibrasyon kodunu ICERMEMELI -- yoksa profilde harness'in kendisi
    gorunur. Yineleme sayisi SABITTIR, sure degil: normal ve --gil kosulari ayni isi
    yapmali ki ornek sayilari karsilastirilabilsin.
    """
    from workloads import controls  # noqa: F401

    try:
        from workloads import parser_wl  # noqa: F401
    except ImportError:
        pass

    w = KAYIT.al(workload_adi)
    shared = w.setup_process()
    if w.state_scope == "shared":
        tekil = w.setup_worker(shared)
        state_listesi = [tekil] * threads
    else:
        state_listesi = [w.setup_worker(shared) for _ in range(threads)]

    bariyer = threading.Barrier(threads)

    def _worker(idx: int) -> None:
        state = state_listesi[idx]
        bariyer.wait()
        for _ in range(yineleme):
            w.call(state)

    threadler = [threading.Thread(target=_worker, args=(i,)) for i in range(threads)]
    for th in threadler:
        th.start()
    for th in threadler:
        th.join()
    return 0


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    alt = ayristirici.add_subparsers(dest="komut", required=True)

    sc = alt.add_parser("self_check", help="uc kontrolu kosturur, esikleri raporlar")
    sc.add_argument("--reps", type=int, default=7)
    sc.add_argument("--out", default="", help="ham veriyi bu dosyaya yaz")

    ru = alt.add_parser("run", help="kayitli workload'lari olcer")
    ru.add_argument("--workloads", default="", help="virgulle ayrilmis; bos ise hepsi")
    ru.add_argument("--category", default="", help="yalniz bu kategori")
    ru.add_argument("--threads", default=",".join(str(n) for n in VARSAYILAN_THREADLER))
    ru.add_argument("--reps", type=int, default=VARSAYILAN_TEKRAR)
    ru.add_argument("--seed", type=int, default=1)
    ru.add_argument("--arm", default="A")
    ru.add_argument("--out", default="research/gil-scaling/results/thread_scaling.json")

    pr = alt.add_parser("profile_target", help="py-spy altinda kosmak icin: olcum yok")
    pr.add_argument("--workload", required=True)
    pr.add_argument("--threads", type=int, default=1)
    pr.add_argument("--iterations", type=int, required=True)

    args = ayristirici.parse_args()

    if args.komut == "profile_target":
        return profil_hedefi(args.workload, args.threads, args.iterations)

    if args.komut == "self_check":
        return self_check(args.reps, args.out)

    from workloads import controls  # noqa: F401 -- kayit yan etkisi

    try:
        from workloads import (  # noqa: F401
            parser_wl,
            persistence_wl,
            report_wl,
            validation_wl,
        )
    except ImportError as exc:
        print(f"not: gercek workload'lar henuz yok ({exc})", file=sys.stderr)

    if args.workloads:
        secilen = [KAYIT.al(ad.strip()) for ad in args.workloads.split(",") if ad.strip()]
    elif args.category:
        secilen = KAYIT.kategori(args.category)
    else:
        secilen = KAYIT.tumu()

    threadler = tuple(int(n) for n in args.threads.split(","))
    sonuc = kos(secilen, threadler, args.reps, args.seed, args.arm)

    hedef = Path(args.out)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"yazildi: {hedef} ({len(sonuc['measurements'])} olcum)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
