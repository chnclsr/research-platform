"""
Bir araştırma koşusu sırasında CPU'nun hangi konteynerde harcandığını ölçer.

NEDEN. GIL çalışması şunu buldu: bir koşu makineden ~2.9 çekirdek alıyor, ama worker
process'i bunun yalnız ~0.06'sını. Geri kalan ~2.8 çekirdeğin NEREDE harcandığı
ölçülmedi -- docling mi, Ollama mı, veritabanı mı, bağlantılar mı. Kapasiteyi artırmanın
tek yolu o 2.8 çekirdeği küçültmek olduğuna göre, önce nereye gittiğini bilmek gerekiyor.
Yanlış bileşene dokunmak işe yaramaz.

NEDEN `docker stats` DEĞİL. `docker stats` çağrı başına saniyeler sürüyor ve kendi CPU'sunu
ölçüme katıyor. cgroup v2 `cpu.stat` dosyası kümülatif `usage_usec` veriyor; iki okuma
arasındaki farkı aralığa bölmek, ihmal edilebilir maliyetle tam çekirdek karşılığını
veriyor.

ÇIKTI. Zaman serisi: her örnekte konteyner başına çekirdek karşılığı, artı sistem geneli.
Koşunun stage'leriyle sonradan `run_events.created_at` üzerinden eşleştirilebilir.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

CGROUP_KOK = Path("/sys/fs/cgroup/system.slice")


def konteynerler(desen: str) -> dict[str, Path]:
    """Ad -> cpu.stat yolu. Yalnız cgroup'u okunabilen konteynerler döner."""
    c = subprocess.run(["docker", "ps", "--format", "{{.Names}}\t{{.ID}}"],
                       capture_output=True, text=True, timeout=30, check=False)
    bulunan: dict[str, Path] = {}
    for satir in c.stdout.strip().splitlines():
        if "\t" not in satir:
            continue
        ad, kisa = satir.split("\t", 1)
        if desen and desen not in ad:
            continue
        tam = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", kisa],
                             capture_output=True, text=True, timeout=30, check=False)
        uzun = tam.stdout.strip()
        yol = CGROUP_KOK / f"docker-{uzun}.scope" / "cpu.stat"
        if yol.exists():
            bulunan[ad] = yol
    return bulunan


def host_pidleri(desenler: list[str]) -> dict[str, list[int]]:
    """Ad deseni -> eslesen TUM PID'ler.

    ISIM BAZLI, agac bazli DEGIL -- ve bunun somut bir sebebi var. Ilk surum
    `ollama serve`in PID'ini bulup `/proc/<pid>/task/<pid>/children` ile torunlarini
    topluyordu. Ollama bir Go programi ve cikarim process'lerini ANA THREAD'DEN
    DEGIL baska bir thread'den fork ediyor; o dosya bos donuyordu. Sonuc: olcum
    Ollama'yi 0.006 cekirdek gosterirken gercekte `llama-server` 2.8 cekirdek
    yiyordu. Isim eslestirmesi bu tuzagi tamamen atlatiyor.
    """
    bulunan: dict[str, list[int]] = {}
    # PID'ler desenler arasinda TEKILLESTIRILIR. `pgrep -f ollama` llama-server'i da
    # yakaliyor, cunku onun komut satirinda ollama'nin kurulum yolu geciyor; ayni
    # process iki grupta sayilinca izlenen toplam sistemi asip "izlenmeyen"i negatife
    # dusurmustu. Ilk eslesen desen PID'i sahiplenir, sirasi cagiranin verdigi sira.
    sahiplenen: set[int] = set()
    for desen in desenler:
        c = subprocess.run(["pgrep", "-f", desen], capture_output=True, text=True,
                           timeout=15, check=False)
        pidler = [int(x) for x in c.stdout.split()
                  if x.isdigit() and int(x) not in sahiplenen]
        if pidler:
            sahiplenen.update(pidler)
            bulunan[f"host:{desen}"] = pidler
    return bulunan


def _tek_process_usec(pid: int) -> int:
    """Tek bir process'in kumulatif CPU'su, mikrosaniye. Bulunamazsa -1."""
    try:
        alanlar = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        # /proc/pid/stat: utime alan 14, stime alan 15 (1-tabanli). Komut adi
        # parantez icinde ve bosluk icerebildigi icin once ") " ile ayriliyor;
        # o ayrimdan sonra indisler 11 ve 12.
        jiffy = int(alanlar[11]) + int(alanlar[12])
        return int(jiffy / os.sysconf("SC_CLK_TCK") * 1e6)
    except (OSError, IndexError, ValueError):
        return -1


def _grup_usec(pidler: list[int]) -> int:
    """Bir desene uyan butun process'lerin toplam CPU'su."""
    toplam = 0
    for pid in pidler:
        v = _tek_process_usec(pid)
        if v > 0:
            toplam += v
    return toplam


def _usec(yol: Path) -> int:
    try:
        for satir in yol.read_text().splitlines():
            if satir.startswith("usage_usec"):
                return int(satir.split()[1])
    except OSError:
        pass
    return -1


def _sistem_jiffies() -> tuple[int, int]:
    """(bosta olmayan, toplam) -- /proc/stat ilk satiri."""
    alanlar = [int(x) for x in Path("/proc/stat").read_text().split("\n")[0].split()[1:]]
    toplam = sum(alanlar)
    bosta = alanlar[3] + (alanlar[4] if len(alanlar) > 4 else 0)
    return toplam - bosta, toplam


def _ozetle(ornekler: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Bileşen zaman serisini karşılaştırılabilir ortalama/p95/zirve özetine çevirir."""
    adlar = sorted({a for o in ornekler for a in o["konteyner_cekirdek"]})
    ozet: dict[str, dict[str, float]] = {}
    for ad in adlar:
        # Bir bileşenin örnekte bulunmaması o aralıkta ölçülmüş CPU'sunun sıfır
        # olmasıdır. Yalnız göründüğü aralıkları almak ortalamayı yapay biçimde büyütür.
        sirali = sorted(o["konteyner_cekirdek"].get(ad, 0.0) for o in ornekler)
        ozet[ad] = {
            "ort": round(sum(sirali) / len(sirali), 3),
            "p95": round(sirali[min(len(sirali) - 1, int(len(sirali) * 0.95))], 3),
            "maks": round(sirali[-1], 3),
        }
    return ozet


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pattern", default="",
                    help="ad filtresi; BOS = butun konteynerler. Varsayilan bilincli "
                         "olarak bos: ilk kosuda 'research-platform' filtresi searxng'i "
                         "disarida birakti ve zirvede 8 cekirdeklik kor nokta olustu")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--duration", type=float, default=900.0)
    ap.add_argument("--host-procs", default="ollama,llama-server,chrome-headless",
                    help="virgulle ayrilmis; konteynerde olmayan process ADI DESENLERI")
    ap.add_argument("--out", default="research/gil-scaling/results/container_cpu.json")
    args = ap.parse_args()

    hedefler = konteynerler(args.pattern)
    if not hedefler:
        print(f"'{args.pattern}' desenine uyan, cgroup'u okunabilen konteyner yok")
        return 1
    print(f"{len(hedefler)} konteyner izleniyor, {args.interval}s araliksa, "
          f"{args.duration:.0f}s boyunca:")
    for ad in sorted(hedefler):
        print(f"  {ad}")

    desenler = [d.strip() for d in args.host_procs.split(",") if d.strip()]
    hostlar = host_pidleri(desenler)
    for ad, pidler in hostlar.items():
        print(f"  {ad} ({len(pidler)} process)")
    if not hostlar and args.host_procs:
        print(f"  UYARI: '{args.host_procs}' host process'i bulunamadi")

    onceki = {ad: _usec(yol) for ad, yol in hedefler.items()}
    onceki_host = {ad: _grup_usec(pidler) for ad, pidler in hostlar.items()}
    sis_once = _sistem_jiffies()
    t_once = time.monotonic()
    baslangic = time.time()

    ornekler: list[dict[str, Any]] = []
    bitis = time.monotonic() + args.duration
    try:
        while time.monotonic() < bitis:
            time.sleep(args.interval)
            simdi = time.monotonic()
            gecen = simdi - t_once
            if gecen <= 0:
                continue
            cekirdek: dict[str, float] = {}
            for ad, yol in hedefler.items():
                su_an = _usec(yol)
                if su_an < 0 or onceki[ad] < 0:
                    onceki[ad] = su_an
                    continue
                # usage_usec mikrosaniye cinsinden kumulatif CPU; gecen sureye
                # bolununce dogrudan "kac cekirdek mesguldu" cikiyor.
                cekirdek[ad] = round((su_an - onceki[ad]) / 1e6 / gecen, 3)
                onceki[ad] = su_an

            # PID'ler her turda YENIDEN aranir: kosu sirasinda yeni llama-server
            # ya da chrome process'i dogabilir, ilk taramada olmayanlar kacmasin.
            hostlar = host_pidleri(desenler)
            for ad, pidler in hostlar.items():
                su_an = _grup_usec(pidler)
                onceki_deger = onceki_host.get(ad, -1)
                if su_an <= 0 or onceki_deger < 0:
                    onceki_host[ad] = su_an
                    continue
                fark = su_an - onceki_deger
                # Bir process oldugunde toplam DUSEBILIR; negatif farki 0 sayiyoruz
                # ki olcum saçmalamasin, ama bu bir belirsizlik kaynagi.
                cekirdek[ad] = round(max(0.0, fark) / 1e6 / gecen, 3)
                onceki_host[ad] = su_an

            sis_su_an = _sistem_jiffies()
            sis_cekirdek = None
            if sis_su_an[1] > sis_once[1]:
                oran = (sis_su_an[0] - sis_once[0]) / (sis_su_an[1] - sis_once[1])
                sis_cekirdek = round(oran * (os.cpu_count() or 1), 3)
            sis_once = sis_su_an
            t_once = simdi

            izlenen = round(sum(cekirdek.values()), 3)
            ornekler.append({
                "t": round(time.time() - baslangic, 1),
                "sistem_cekirdek": sis_cekirdek,
                "konteyner_cekirdek": cekirdek,
                "toplam_izlenen": izlenen,
                # HESABI KAPATAN KALEM. Izlenen ile sistem arasindaki fark. Buyukse
                # bir kor nokta var demektir ve sonuc oyle okunmalidir -- ilk surumde
                # tam boyle bir kor nokta vardi (llama-server) ve sessizce gecmisti.
                "izlenmeyen": (round(sis_cekirdek - izlenen, 3)
                               if sis_cekirdek is not None else None),
            })
            son = ornekler[-1]
            enb = sorted(cekirdek.items(), key=lambda kv: -kv[1])[:3]
            print(f"  t={son['t']:>6.0f}s  sistem={son['sistem_cekirdek']:>6}  "
                  f"izlenen={son['toplam_izlenen']:>6}  izlenmeyen={son['izlenmeyen']:>6}  "
                  f"en yuklu: {', '.join(f'{a}={c}' for a, c in enb)}")
    except KeyboardInterrupt:
        print("\nkesildi, toplanan ornekler yaziliyor")

    if not ornekler:
        print("ornek toplanamadi")
        return 1

    ozet = _ozetle(ornekler)

    kayip = [o["izlenmeyen"] for o in ornekler if o.get("izlenmeyen") is not None]
    sis = [o["sistem_cekirdek"] for o in ornekler if o["sistem_cekirdek"] is not None]
    sonuc = {
        "schema": "gil-scaling/container-cpu/2",
        # Mutlak baslangic: orneklerin `t` alani buna gore RELATIF. Bu kaydedilmeden
        # ornekler run_events'teki stage gecisleriyle eslestirilemiyor -- ilk kosuda
        # eksikti ve asama kirilimi yapilamadi.
        "baslangic_epoch": round(baslangic, 3),
        "birim": "cekirdek karsiligi (1.0 = bir tam cekirdek)",
        "interval_s": args.interval,
        "ornek_sayisi": len(ornekler),
        "sistem": {"ort": round(sum(sis) / len(sis), 3), "maks": round(max(sis), 3)} if sis else {},
        "izlenmeyen": ({"ort": round(sum(kayip) / len(kayip), 3),
                        "maks": round(max(kayip), 3)} if kayip else {}),
        "konteyner_ozet": ozet,
        "ornekler": ornekler,
    }
    hedef = Path(args.out)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"{'konteyner':<44}{'ort':>8}{'p95':>8}{'maks':>8}")
    print("-" * 68)
    for ad, v in sorted(ozet.items(), key=lambda kv: -kv[1]["ort"]):
        print(f"{ad:<44}{v['ort']:>8}{v['p95']:>8}{v['maks']:>8}")
    if sis:
        print(f"\nsistem geneli : ort {sonuc['sistem']['ort']} cekirdek, "
              f"maks {sonuc['sistem']['maks']}")
    if kayip:
        print(f"IZLENMEYEN    : ort {sonuc['izlenmeyen']['ort']} cekirdek, "
              f"maks {sonuc['izlenmeyen']['maks']}")
        print("  (buyukse kor nokta var -- izlenen listeye eklenmesi gereken bir sey)")
    print(f"yazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
