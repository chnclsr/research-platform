"""
Reads a formula Docling found but did not decode, off the page image.

Docling's layout model boxes a formula even with formula enrichment off. Enrichment
itself is off on purpose: on this card it costs +0.6 GB resident and 3-5 GB transient
VRAM while decoding (measured 2026-09-11), next to Ollama on an 8 GB GPU. What the text
carries instead is "[formül N]", and parse_provenance carries the box
(`_docling_worker.sayfa_bolgeleri`, numbered by `merge._yer_tutuculari_koy`). This
module crops that box out of the PDF and asks `settings.vision_model` -- the model
figure analysis already keeps resident -- to transcribe it.

THE READING IS CONTEXT, NOT TEXT. It never enters passages or content_hash: the model
can change under us, and evidence verification checks quotes against the passage, which
the placeholder keeps stable. Readings are cached in formula_observations, keyed by the
crop's hash and the model, so one formula is read once across runs.

Measured 2026-09-11 on the 24 formulas of the quarantine review: 23/24 read correctly,
~1.45 s each on a warm model. The one miss was plausible-looking and wrong (data_12
eq. 1 lost a term), which is why a report shows the crop next to the reading. A crop
that is not a formula at all gets "transcribed" anyway -- a Turkish sentence came back
as \\mathrm{B i r i n c i ...} -- which is what `red_nedeni` is for.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The placeholder merge.py writes for a numbered, undecoded formula.
FORMUL_YER_TUTUCU = re.compile(r"\[formül (\d+)\]")

#: Part of the cache key next to the model name. Bump it when the prompt or the
#: acceptance rules change, so readings made under the old ones are not reused.
ONBELLEK_SURUMU = "formul1"

#: Same scale figure_analysis crops at; 3 pt of margin keeps a tight Docling box from
#: clipping a subscript. Both were the settings of the 24-formula measurement.
KIRPMA_OLCEK = 2.2
KIRPMA_PAY_PT = 3.0

#: The prompt of the measurement, word for word: a different one is an unmeasured one.
ISTEM = (
    "Transcribe the mathematical formula in this image to LaTeX. "
    "Output only the LaTeX, no $ delimiters, no explanation."
)

_METIN_GRUBU = re.compile(r"\\(?:text|mathrm|textrm|textit|textbf|operatorname|mbox)\s*\{")
#: What a formula has and a line of prose does not, once text groups are removed.
_MATEMATIK = re.compile(
    r"[=+<>^_|]|(?<![A-Za-z])-|\\(?:frac|dfrac|tfrac|sqrt|sum|int|oint|prod|lim|log|ln|"
    r"exp|sin|cos|tan|times|cdot|div|pm|mp|le|leq|ge|geq|ne|neq|approx|sim|equiv|propto|"
    r"rightarrow|leftarrow|to|partial|nabla|infty|alpha|beta|gamma|delta|varepsilon|"
    r"epsilon|zeta|eta|theta|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|phi|varphi|chi|psi|"
    r"omega|Delta|Gamma|Sigma|Omega|Phi|Pi|Lambda|Theta)(?![A-Za-z])"
)


@dataclass(frozen=True)
class FormulaReading:
    formula_no: int
    latex: str
    status: str
    page_number: int | None = None
    image_key: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def formula_numbers(text: str) -> list[int]:
    """The numbered formula placeholders in a passage, in order, without repeats."""
    return list(dict.fromkeys(int(n) for n in FORMUL_YER_TUTUCU.findall(text or "")))


def formula_regions(parse_provenance: Mapping[str, Any] | None) -> dict[int, dict]:
    """formula number -> its region, from what smart_pdf wrote to provenance."""
    bolgeler = (parse_provenance or {}).get("bolgeler") or []
    return {
        int(b["sira"]): b
        for b in bolgeler
        if b.get("tur") == "formul" and b.get("sira") is not None and b.get("bbox")
    }


def kirp(pdf: bytes, bolge: Mapping[str, Any]) -> bytes:
    """PNG of one region: PDF points, top-left origin -- how sayfa_bolgeleri stores it."""
    import fitz

    with fitz.open(stream=pdf, filetype="pdf") as belge:
        sayfa = belge[int(bolge["page"]) - 1]
        sol, ust, sag, alt = (float(v) for v in bolge["bbox"])
        alan = fitz.Rect(sol - KIRPMA_PAY_PT, ust - KIRPMA_PAY_PT,
                         sag + KIRPMA_PAY_PT, alt + KIRPMA_PAY_PT) & sayfa.rect
        pixmap = sayfa.get_pixmap(clip=alan, matrix=fitz.Matrix(KIRPMA_OLCEK, KIRPMA_OLCEK),
                                  alpha=False)
        return pixmap.tobytes("png")


def temizle(yanit: str) -> str:
    """Strip what models wrap LaTeX in: code fences, $ / $$, \\[ \\]."""
    metin = (yanit or "").strip()
    metin = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", metin).strip()
    if metin.startswith("\\[") and metin.endswith("\\]"):
        metin = metin[2:-2].strip()
    return metin.strip("$").strip()


def metin_gruplarini_at(latex: str) -> str:
    """Remove \\text{...}-style groups, contents included (braces balanced)."""
    parcalar: list[str] = []
    i = 0
    while True:
        eslesme = _METIN_GRUBU.search(latex, i)
        if eslesme is None:
            parcalar.append(latex[i:])
            return "".join(parcalar)
        parcalar.append(latex[i:eslesme.start()])
        j, derinlik = eslesme.end(), 1
        while j < len(latex) and derinlik:
            derinlik += {"{": 1, "}": -1}.get(latex[j], 0)
            j += 1
        i = j


def red_nedeni(latex: str) -> str | None:
    """
    Why a reading is not accepted, or None when it is.

    "matematik_isareti_yok" is the case that matters: with text groups removed, nothing
    of a formula is left. That is what a crop of prose comes back as, and also what a
    box that caught only the equation number comes back as ("(15.19)" on 01030000000129)
    -- neither is worth putting next to a claim.
    """
    if not latex:
        return "bos"
    if len(latex) > 2000:
        return "cok_uzun"
    duz = latex.replace("\\{", "").replace("\\}", "")
    if duz.count("{") != duz.count("}"):
        return "dengesiz_suslu_parantez"
    if not _MATEMATIK.search(metin_gruplarini_at(latex)):
        return "matematik_isareti_yok"
    return None


async def oku(client: Any, settings: Any, png: bytes) -> tuple[str, str]:
    """One vision call. Returns (latex, status); latex is empty unless status is "ok"."""
    try:
        yanit = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.vision_model,
                "stream": False,
                "think": False,
                "messages": [{
                    "role": "user",
                    "content": ISTEM,
                    "images": [base64.b64encode(png).decode("ascii")],
                }],
                "options": {"temperature": 0, "seed": 1, "num_predict": 512},
            },
            timeout=settings.formula_resolution_timeout_s,
        )
        yanit.raise_for_status()
        ham = yanit.json()["message"]["content"]
    except Exception as exc:  # noqa: BLE001 - a failed read leaves the placeholder
        return "", f"hata:{type(exc).__name__}"
    latex = temizle(str(ham))
    neden = red_nedeni(latex)
    return ("", f"reddedildi:{neden}") if neden else (latex, "ok")


class FormulaReader:
    """
    Reads formulas for one run: one HTTP client, one budget, the shared cache.

    Called sequentially, before claim extraction fans out. The repository holds a single
    AsyncSession, which must not be used from concurrent coroutines; and the vision model
    serves one request at a time anyway, so reading formulas in parallel buys nothing
    while forcing the writing and the vision model to sit in VRAM together.
    """

    def __init__(self, *, client: Any, settings: Any, repo: Any, store: Any, run_id: str):
        self.client = client
        self.settings = settings
        self.repo = repo
        self.store = store
        self.run_id = run_id
        self.cache_model = f"{settings.vision_model}#{ONBELLEK_SURUMU}"
        self.kalan = int(settings.formula_max_per_run)
        self.durumlar: Counter[str] = Counter()
        self.model_sure_s = 0.0
        self._okunan: dict[tuple[str, int], FormulaReading] = {}

    async def read(
        self, *, source_version_id: str, pdf: bytes, parse_provenance: Mapping[str, Any],
        numbers: Sequence[int],
    ) -> dict[int, FormulaReading]:
        """
        `pdf` is the document's bytes, as the caller could get them: the pipeline's
        checkpointed document payload has its raw_content emptied on purpose, so the
        bytes come from the stored source version, not from the passage's document.
        """
        bolgeler = formula_regions(parse_provenance)
        sonuc: dict[int, FormulaReading] = {}
        for numara in numbers:
            anahtar = (source_version_id, numara)
            if anahtar in self._okunan:
                sonuc[numara] = self._okunan[anahtar]
                continue
            bolge = bolgeler.get(numara)
            if bolge is None:
                okuma = FormulaReading(numara, "", "bolge_yok")
            elif not pdf:
                okuma = FormulaReading(numara, "", "pdf_yok")
            else:
                okuma = await self._bolgeyi_oku(source_version_id, numara, bolge, pdf)
            self.durumlar[okuma.status.split(":")[0]] += 1
            self._okunan[anahtar] = okuma
            sonuc[numara] = okuma
        return sonuc

    async def _bolgeyi_oku(
        self, source_version_id: str, numara: int, bolge: Mapping[str, Any], pdf: bytes,
    ) -> FormulaReading:
        sayfa = int(bolge["page"]) if bolge.get("page") is not None else None
        try:
            png = kirp(pdf, bolge)
        except Exception as exc:  # noqa: BLE001 - a bad box leaves the placeholder
            return FormulaReading(numara, "", f"hata:kirpma_{type(exc).__name__}", sayfa)
        image_hash = hashlib.sha256(png).hexdigest()
        onceki = await self.repo.get_formula_observation(
            source_version_id, image_hash, self.cache_model
        )
        if onceki is not None:
            return FormulaReading(numara, onceki.latex, onceki.status, sayfa, onceki.image_key)
        if self.kalan <= 0:
            return FormulaReading(numara, "", "butce_doldu", sayfa)
        self.kalan -= 1

        baslangic = time.perf_counter()
        latex, durum = await oku(self.client, self.settings, png)
        self.model_sure_s += time.perf_counter() - baslangic
        if durum.startswith("hata:"):
            # Not cached: a timeout or a stopped Ollama says nothing about this formula.
            return FormulaReading(numara, "", durum, sayfa)

        image_key = f"runs/{self.run_id}/formulas/{image_hash}.png"
        try:
            await self.store.put(image_key, png, "image/png")
        except Exception:  # noqa: BLE001 - the reading is still worth keeping
            image_key = ""
        await self.repo.save_formula_observation(
            run_id=self.run_id, source_version_id=source_version_id, formula_no=numara,
            page_number=sayfa, image_hash=image_hash, image_key=image_key,
            vision_model=self.cache_model, latex=latex, status=durum,
        )
        return FormulaReading(numara, latex, durum, sayfa, image_key)

    def ozet(self) -> dict[str, Any]:
        """For the run's event log: how many, how they ended, how long the model took."""
        return {
            "durumlar": dict(self.durumlar),
            "model_sure_s": round(self.model_sure_s, 2),
            "kalan_butce": self.kalan,
            "vision_model": self.cache_model,
        }


def formula_notes(readings: Mapping[int, FormulaReading]) -> str:
    """The FORMULAS block handed to claim extraction: accepted readings only."""
    return "\n".join(
        f"[formül {numara}] = {okuma.latex}"
        for numara, okuma in sorted(readings.items())
        if okuma.ok
    )
