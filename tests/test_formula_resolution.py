"""
Reading "[formül N]" placeholders off the page image (formula_resolution.py).

Everything except the last test runs without Ollama: the vision model is an
httpx.MockTransport, the repository and object store are in-memory stand-ins. The last
test replays the 24 crops of the 2026-09-11 measurement against a live model and only
runs when FORMULA_OLLAMA_TEST=1.
"""

from __future__ import annotations

import base64
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace

import fitz
import httpx
import pytest

from research_platform.formula_resolution import (
    ISTEM,
    KIRPMA_OLCEK,
    KIRPMA_PAY_PT,
    FormulaReader,
    FormulaReading,
    formula_notes,
    formula_numbers,
    formula_regions,
    kirp,
    oku,
    red_nedeni,
    temizle,
)

FIKSTUR = Path(__file__).parent / "fixtures" / "formul_kirpintilari"
BEKLENEN = json.loads((FIKSTUR / "beklenen.json").read_text(encoding="utf-8"))["kirpintilar"]


def _ayarlar(**degisen):
    ayar = {"ollama_url": "http://ollama.test", "vision_model": "qwen3.5:4b",
            "formula_resolution_timeout_s": 30.0, "formula_max_per_run": 80}
    ayar.update(degisen)
    return SimpleNamespace(**ayar)


def _pdf() -> bytes:
    belge = fitz.open()
    sayfa = belge.new_page(width=200, height=200)
    sayfa.insert_text((60, 75), "x = v t", fontsize=12)
    return belge.tobytes()


BOLGE = {"tur": "formul", "page": 1, "bbox": [50.0, 60.0, 150.0, 80.0], "sira": 1}
PROVENANCE = {"bolgeler": [BOLGE, {"tur": "gorsel", "page": 1, "bbox": [0, 0, 9, 9], "sira": 1}]}


def _istemci(yanitlar, cagrilar):
    """A vision model that answers from a list and records what it was sent."""
    def handler(request: httpx.Request) -> httpx.Response:
        cagrilar.append(json.loads(request.content))
        durum, icerik = yanitlar[min(len(cagrilar), len(yanitlar)) - 1]
        return httpx.Response(durum, json={"message": {"content": icerik}})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class _Depo:
    def __init__(self):
        self.satirlar: dict[tuple, SimpleNamespace] = {}

    async def get_formula_observation(self, source_version_id, image_hash, vision_model):
        return self.satirlar.get((source_version_id, image_hash, vision_model))

    async def save_formula_observation(self, **alanlar):
        satir = SimpleNamespace(**alanlar)
        self.satirlar[(alanlar["source_version_id"], alanlar["image_hash"],
                       alanlar["vision_model"])] = satir
        return satir


class _NesneDeposu:
    def __init__(self):
        self.yazilan: dict[str, bytes] = {}

    async def put(self, key, data, content_type):
        self.yazilan[key] = data
        return key


# --- pure helpers ------------------------------------------------------------------

def test_placeholder_numbers_keep_order_and_drop_repeats():
    assert formula_numbers("a [formül 3] b [formül 1] c [formül 3] [formül] [görsel 2]") == [3, 1]


def test_regions_come_from_provenance_formulas_only():
    assert formula_regions(PROVENANCE) == {1: BOLGE}
    assert formula_regions({}) == {}
    assert formula_regions({"bolgeler": [{"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]}]}) == {}


@pytest.mark.parametrize("ham, beklenen", [
    ("```latex\nx = 1\n```", "x = 1"),
    ("$$x = 1$$", "x = 1"),
    ("\\[ x = 1 \\]", "x = 1"),
    ("  y = 2  ", "y = 2"),
])
def test_wrappers_are_stripped(ham, beklenen):
    assert temizle(ham) == beklenen


def test_every_approved_reading_of_the_measurement_is_accepted():
    onayli = [k["beklenen"] for k in BEKLENEN if k["tur"] == "formul"]
    assert len(onayli) == 19
    assert [red_nedeni(latex) for latex in onayli] == [None] * 19


@pytest.mark.parametrize("latex, neden", [
    # A crop of prose, "transcribed" anyway (first attempt of 2026-09-11).
    (r"\mathrm { B i r i n c i - d e r e c e d e n ~ D e b y e ~ m o d e l i ~ a \hbar a }",
     "matematik_isareti_yok"),
    # A box that caught only the equation number (01030000000129).
    ("(15.19)", "matematik_isareti_yok"),
    ("", "bos"),
    (r"\frac{a}{b", "dengesiz_suslu_parantez"),
])
def test_readings_that_are_not_formulas_are_rejected(latex, neden):
    assert red_nedeni(latex) == neden


def test_the_crop_is_the_box_plus_margin_at_the_measured_scale():
    import io

    from PIL import Image

    goruntu = Image.open(io.BytesIO(kirp(_pdf(), BOLGE)))
    genislik = (100 + 2 * KIRPMA_PAY_PT) * KIRPMA_OLCEK
    yukseklik = (20 + 2 * KIRPMA_PAY_PT) * KIRPMA_OLCEK
    assert abs(goruntu.width - genislik) <= 1.5
    assert abs(goruntu.height - yukseklik) <= 1.5


def test_notes_carry_accepted_readings_only():
    notlar = formula_notes({
        2: FormulaReading(2, r"y = \frac{1}{2} g t^2", "ok"),
        1: FormulaReading(1, "x = v . t", "ok"),
        3: FormulaReading(3, "", "reddedildi:matematik_isareti_yok"),
    })
    assert notlar == "[formül 1] = x = v . t\n[formül 2] = y = \\frac{1}{2} g t^2"


# --- one vision call ---------------------------------------------------------------

async def test_the_crop_goes_to_the_vision_model_with_the_measured_prompt():
    cagrilar: list[dict] = []
    png = kirp(_pdf(), BOLGE)
    async with _istemci([(200, "$$x = v . t \\qquad ( 7 )$$")], cagrilar) as client:
        assert await oku(client, _ayarlar(), png) == ("x = v . t \\qquad ( 7 )", "ok")

    istek = cagrilar[0]
    assert istek["model"] == "qwen3.5:4b"
    assert istek["think"] is False
    assert istek["options"]["temperature"] == 0
    assert istek["messages"][0]["content"] == ISTEM
    assert istek["messages"][0]["images"] == [base64.b64encode(png).decode("ascii")]


async def test_a_reading_of_prose_is_rejected_and_an_http_error_is_reported():
    png = kirp(_pdf(), BOLGE)
    async with _istemci([(200, r"\mathrm{B i r i n c i}")], []) as client:
        assert await oku(client, _ayarlar(), png) == ("", "reddedildi:matematik_isareti_yok")
    async with _istemci([(500, "")], []) as client:
        assert await oku(client, _ayarlar(), png) == ("", "hata:HTTPStatusError")


# --- the reader: cache, budget, failures -------------------------------------------

def _okuyucu(client, depo, nesne, **ayar):
    return FormulaReader(client=client, settings=_ayarlar(**ayar), repo=depo, store=nesne,
                         run_id="r1")


async def _oku(okuyucu, numbers=(1,), pdf=None):
    return await okuyucu.read(source_version_id="v1", pdf=_pdf() if pdf is None else pdf,
                              parse_provenance=PROVENANCE, numbers=list(numbers))


async def test_a_formula_is_read_once_and_then_served_from_the_cache():
    depo, nesne = _Depo(), _NesneDeposu()
    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        ilk = await _oku(_okuyucu(client, depo, nesne))
        ikinci = await _oku(_okuyucu(client, depo, nesne))   # a later run

    assert len(cagrilar) == 1
    assert ilk[1].latex == ikinci[1].latex == "x = v . t"
    satir = next(iter(depo.satirlar.values()))
    assert satir.vision_model == "qwen3.5:4b#formul1"
    assert satir.formula_no == 1 and satir.page_number == 1 and satir.status == "ok"
    assert list(nesne.yazilan) == [satir.image_key]
    assert re.fullmatch(r"runs/r1/formulas/[0-9a-f]{64}\.png", satir.image_key)


async def test_the_same_formula_in_two_passages_costs_one_call():
    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        okuyucu = _okuyucu(client, _Depo(), _NesneDeposu())
        await _oku(okuyucu)
        await _oku(okuyucu)
    assert len(cagrilar) == 1


async def test_the_budget_stops_new_calls_but_not_cache_hits():
    depo = _Depo()
    async with _istemci([(200, "x = v . t")], []) as client:
        await _oku(_okuyucu(client, depo, _NesneDeposu()))
    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        onbellekten = await _oku(_okuyucu(client, depo, _NesneDeposu(), formula_max_per_run=0))
        bos_depo = await _oku(_okuyucu(client, _Depo(), _NesneDeposu(), formula_max_per_run=0))
    assert cagrilar == []
    assert onbellekten[1].ok
    assert bos_depo[1].status == "butce_doldu"


async def test_a_failed_call_is_not_cached():
    depo = _Depo()
    async with _istemci([(500, "")], []) as client:
        hatali = await _oku(_okuyucu(client, depo, _NesneDeposu()))
    assert hatali[1].status == "hata:HTTPStatusError"
    assert depo.satirlar == {}

    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        tekrar = await _oku(_okuyucu(client, depo, _NesneDeposu()))
    assert len(cagrilar) == 1 and tekrar[1].ok


async def test_a_placeholder_without_a_region_is_left_alone():
    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        okuyucu = _okuyucu(client, _Depo(), _NesneDeposu())
        sonuc = await _oku(okuyucu, numbers=(7,))
    assert sonuc[7].status == "bolge_yok"
    assert cagrilar == []
    assert okuyucu.ozet()["durumlar"] == {"bolge_yok": 1}


async def test_without_the_pdf_bytes_nothing_is_cropped_or_sent():
    cagrilar: list[dict] = []
    async with _istemci([(200, "x = v . t")], cagrilar) as client:
        sonuc = await _oku(_okuyucu(client, _Depo(), _NesneDeposu()), pdf=b"")
    assert sonuc[1].status == "pdf_yok"
    assert cagrilar == []


# --- the real table ----------------------------------------------------------------

async def test_the_repository_keeps_one_row_per_crop_and_model():
    from research_platform.auth import Principal
    from research_platform.db import SessionLocal, create_schema
    from research_platform.repository import Repository

    await create_schema()
    alanlar = {"run_id": "r-formul", "source_version_id": "v-formul", "formula_no": 1,
               "page_number": 1, "image_hash": "a" * 64, "image_key": "k",
               "vision_model": "qwen3.5:4b#formul1", "latex": "x = 1", "status": "ok"}
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        await repo.save_formula_observation(**alanlar)
        await repo.save_formula_observation(**{**alanlar, "latex": "x = 2"})
        satirlar = await repo.list_formula_observations(["v-formul"])
        bulunan = await repo.get_formula_observation("v-formul", "a" * 64, "qwen3.5:4b#formul1")
    assert [s.latex for s in satirlar] == ["x = 2"]
    assert bulunan is not None and bulunan.status == "ok"


# --- live regression, opt-in -------------------------------------------------------

def _duz(latex: str) -> str:
    latex = re.sub(r"\\(?:left|right|q?quad|mathrm|text|operatorname)\b|\\[ ,;!]|~", "", latex)
    return re.sub(r"[\s{}]", "", latex)


@pytest.mark.skipif(os.environ.get("FORMULA_OLLAMA_TEST") != "1",
                    reason="live vision model; set FORMULA_OLLAMA_TEST=1")
async def test_live_model_still_reads_the_measured_crops():
    ayar = _ayarlar(ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                    formula_resolution_timeout_s=180.0)
    eslesen, reddedilen, sonuclar = 0, 0, []
    async with httpx.AsyncClient() as client:
        for kirpinti in BEKLENEN:
            latex, durum = await oku(client, ayar, (FIKSTUR / kirpinti["dosya"]).read_bytes())
            benzerlik = SequenceMatcher(None, _duz(latex), _duz(kirpinti["beklenen"])).ratio()
            sonuclar.append((kirpinti["dosya"], kirpinti["tur"], durum, round(benzerlik, 2)))
            if kirpinti["tur"] == "formul" and durum == "ok" and benzerlik >= 0.85:
                eslesen += 1
            if kirpinti["tur"] == "numara" and durum.startswith("reddedildi"):
                reddedilen += 1
    assert eslesen >= 17, sonuclar      # 19 approved readings; allow two to drift
    assert reddedilen == 4, sonuclar    # number-only boxes must never pass as formulas
