"""dogrulama_*.md dosyalarindaki isaretleri sayar ve orneklem oranini toplama uygular.

Kullanim: .\.venv\Scripts\python.exe say.py
"""
import io
import re
from pathlib import Path


def main():
    dosyalar = sorted(Path(".").glob("dogrulama_*.md"))
    if not dosyalar:
        print("dogrulama_*.md bulunamadi. Once aday_uret.py calistir.")
        return

    for dosya in dosyalar:
        metin = io.open(dosya, encoding="utf-8").read()
        print(f"\n{'='*66}\n{dosya.name}\n{'='*66}")

        kategori = None
        parser = None
        toplam_aday = 0
        isaretli = kutu = emin_degil = 0

        def dok():
            if parser is None or kutu == 0:
                return
            oran = isaretli / kutu
            tahmin = round(oran * toplam_aday)
            ek = ""
            if toplam_aday > kutu:
                ek = f"  → örneklem oranı %{oran*100:.0f}, tahmini toplam ≈ {tahmin} / {toplam_aday}"
            soru = f"  ({emin_degil} adet '?')" if emin_degil else ""
            print(f"  {parser:10} {isaretli:4} / {kutu:4} hata{ek}{soru}")

        for satir in metin.splitlines():
            if satir.startswith("## ") and "Otomatik" not in satir:
                dok()
                kategori, parser, kutu, isaretli, emin_degil, toplam_aday = (
                    satir[3:].strip(), None, 0, 0, 0, 0)
                print(f"\n{kategori}")
                continue
            if satir.startswith("### "):
                dok()
                parser = satir[4:].split("—")[0].strip()
                kutu = isaretli = emin_degil = toplam_aday = 0
                continue
            m = re.search(r"\*\*(\d+) aday", satir)
            if m:
                toplam_aday = int(m.group(1))
                continue
            if satir.strip().startswith("- ["):
                kutu += 1
                if re.match(r"\s*- \[[xX]\]", satir):
                    isaretli += 1
                if satir.rstrip().endswith("?"):
                    emin_degil += 1
        dok()

        # otomatik sayilan ligatur satirlari
        print("\nOtomatik sayılanlar")
        for m in re.finditer(r"\*\*Ligatür \((\w+)\):\*\* (\d+)", metin):
            print(f"  {m.group(1):10} ligatür: {m.group(2)}")


if __name__ == "__main__":
    main()
