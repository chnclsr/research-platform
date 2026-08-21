"""
9 belgelik kendi korpusumuzun ve ölçüm çıktılarının yerini çözer.

`korpus_kaynak.py` C1'in dış korpuslarını (OCRTurk, DocLayNet, OmniDocBench,
OpenDataLoader bench) çözüyor. Bu modül ondan ayrı duruyor çünkü 9 belgelik
korpus farklı bir şey: dışarıdan indirilen bir veri seti değil, bu çalışma için
elle seçilmiş bir örnekleme — iki sütunlu makale, tablo ağırlıklı, uzun belge,
taranmış belge, Türkçe belge. Ölçümlerin çoğu buna dayanıyor.

PDF'ler depoya girmez (telif). Varsayılan yerleri `research/pdf-parser/corpus/kendi`;
başka yerdeyse `KENDI_KORPUS` ile gösterilir.
"""
from __future__ import annotations

import os

CALIBRATION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(CALIBRATION_ROOT))

#: 9 PDF'in bulundugu dizin.
KENDI_KORPUS = os.path.abspath(os.environ.get(
    "KENDI_KORPUS", os.path.join(CALIBRATION_ROOT, "corpus", "kendi")))

#: Olcum ciktilarinin yazildigi dizin. Git'e girmez (.gitignore).
CIKTI = os.path.abspath(os.environ.get(
    "PDF_PARSER_OUT", os.path.join(CALIBRATION_ROOT, "out")))

#: Korpusun belgeleri, SABIT SIRADA. Sira olcum ciktilarinda tekrarlanabilirlik
#: demek; alfabetik degil, kisa belgeden uzuna dogru diziliyor ki kismi kosular
#: (--only, kesilen kosu) once ucuz belgeleri bitirsin.
BELGELER = ["turkce_makale", "resnet_2sutun_gorsel", "vgg_tablo_agirlikli",
            "attention_tablo", "bert_2sutun_dipnot", "sybil_tip_2sutun",
            "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
            "taranmis_bert_2sutun_dipnot"]


def pdf(stem: str) -> str:
    return os.path.join(KENDI_KORPUS, stem + ".pdf")


def dogrula(hedef: list[str]) -> None:
    """Korpus yoksa ölçüme başlamadan, ne yapılacağını söyleyerek dur.

    Yarım koşup sonunda "0 belge işlendi" demek, kullanıcıyı hangi ortam
    değişkenini ayarlayacağını aramaya bırakır.
    """
    eksik = [s for s in hedef if not os.path.isfile(pdf(s))]
    if not eksik:
        return
    raise SystemExit(
        "Korpus bulunamadi: %s\n"
        "Eksik: %s\n"
        "PDF'ler depoya girmiyor; dizini olustur ya da KENDI_KORPUS ortam "
        "degiskeniyle yerini goster." % (KENDI_KORPUS, ", ".join(eksik)))
