"""
Formula readings reaching claim extraction.

Two promises: with no readings the extraction prompt is exactly what it was, and with
readings the LaTeX sits beside TARGET_CONTENT -- never in it, because quotes are
verified against the passage. Plus the pipeline step that decides which passages get
their formulas read (ResearchPipeline._read_formulas).
"""

from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace

import fitz

from research_platform.llm import extract_claims
from research_platform.pipeline import ResearchPipeline
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    Passage,
    SourceFamily,
)

ICERIK = "The horizontal distance traveled by jet (x) in time (t) is equal to: [formül 1] here."


class _KayitliSaglayici:
    """Records the prompt; answers with one claim quoting the placeholder."""

    def __init__(self):
        self.istemler: list[tuple[str, str]] = []

    async def complete_json(self, system, prompt, **_kwargs):
        self.istemler.append((system, prompt))
        return {"claims": [{
            "text": "Horizontal distance is velocity times time.",
            "quote": "is equal to: [formül 1]",
            "direction": "supports", "importance": "major", "confidence": 0.8,
        }]}


def _belge() -> AcquiredDocument:
    return AcquiredDocument(
        candidate=ConnectorCandidate(connector_id="fixture", family=SourceFamily.WEB,
                                     title="Orifice", url="https://example.com/orifice.pdf"),
        success=True, access_status="open", content=ICERIK,
        content_hash=hashlib.sha256(ICERIK.encode()).hexdigest(), acquisition_method="fixture",
    )


async def test_without_readings_the_prompt_is_what_it_was():
    saglayici = _KayitliSaglayici()
    await extract_claims(saglayici, _belge(), content_override=ICERIK, neighbor_context="komsu")
    await extract_claims(saglayici, _belge(), content_override=ICERIK, neighbor_context="komsu",
                         formula_notes="")
    (sistem, istem), ikinci = saglayici.istemler
    assert ikinci == (sistem, istem)
    assert "FORMULAS" not in sistem and "FORMULAS" not in istem
    assert istem.endswith(f"NEIGHBOR_CONTEXT:\nkomsu\nTARGET_CONTENT:\n{ICERIK}")


async def test_readings_ride_beside_the_passage_and_a_placeholder_quote_still_verifies():
    saglayici = _KayitliSaglayici()
    claims = await extract_claims(
        saglayici, _belge(), content_override=ICERIK, neighbor_context="komsu",
        formula_notes="[formül 1] = x = v . t",
    )
    sistem, istem = saglayici.istemler[0]
    assert "never quote from it" in sistem
    assert "NEIGHBOR_CONTEXT:\nkomsu\nFORMULAS:\n[formül 1] = x = v . t\nTARGET_CONTENT:\n" in istem
    assert claims[0].quote == "is equal to: [formül 1]"
    assert ICERIK[claims[0].start_char:claims[0].end_char] == claims[0].quote


# --- which passages get their formulas read ----------------------------------------

def _pdf_b64() -> str:
    belge = fitz.open()
    sayfa = belge.new_page(width=200, height=200)
    sayfa.insert_text((60, 75), "x = v t", fontsize=12)
    return base64.b64encode(belge.tobytes()).decode("ascii")


PROVENANCE = {"bolgeler": [{"tur": "formul", "page": 1, "bbox": [50, 60, 150, 80], "sira": 1}]}


def _passage(version: str, text: str, section: str = "Results") -> Passage:
    return Passage(source_version_id=version, chunk_index=0, section_path=section,
                   start_char=0, end_char=len(text), text=text, token_count=len(text.split()),
                   content_hash=hashlib.sha256(text.encode()).hexdigest())


class _Depo:
    def __init__(self):
        self.olaylar: list[tuple[str, dict]] = []
        self.satirlar: dict = {}
        self.surum_istendi = 0

    async def list_source_versions(self, run_id):
        self.surum_istendi += 1
        surum = SimpleNamespace(id="v1", raw_content=_pdf_b64(),
                                provenance={"parse_provenance": PROVENANCE})
        return [(SimpleNamespace(id="s1"), surum)]

    async def event(self, run_id, name, payload):
        self.olaylar.append((name, payload))

    async def get_formula_observation(self, source_version_id, image_hash, vision_model):
        return self.satirlar.get((source_version_id, image_hash, vision_model))

    async def save_formula_observation(self, **alanlar):
        self.satirlar[(alanlar["source_version_id"], alanlar["image_hash"],
                       alanlar["vision_model"])] = SimpleNamespace(**alanlar)


class _NesneDeposu:
    async def put(self, key, data, content_type):
        return key


def _hat(depo, acik=True):
    return SimpleNamespace(
        settings=SimpleNamespace(
            formula_resolution_enabled=acik, ollama_url="http://ollama.test",
            vision_model="qwen3.5:4b", formula_resolution_timeout_s=30.0,
            formula_max_per_run=80,
        ),
        repo=depo, store=_NesneDeposu(),
    )


DOCUMENTS = {
    "v1": {"candidate": {"metadata": {}}},
    "v2": {"candidate": {"metadata": {"evidence_eligible": False}}},
}


async def test_formulas_are_not_read_and_the_database_untouched_when_off(monkeypatch):
    depo = _Depo()
    notlar = await ResearchPipeline._read_formulas(
        _hat(depo, acik=False), "r1", [_passage("v1", "a [formül 1] b")], DOCUMENTS
    )
    assert notlar == {}
    assert depo.surum_istendi == 0 and depo.olaylar == []


async def test_only_passages_extraction_will_see_get_their_formulas_read(monkeypatch):
    from research_platform import formula_resolution

    cagrilar: list[bytes] = []

    async def sahte_oku(client, settings, png):
        cagrilar.append(png)
        return "x = v . t", "ok"

    monkeypatch.setattr(formula_resolution, "oku", sahte_oku)
    okunacak = _passage("v1", "The distance is [formül 1] in general.")
    ayni_formul = _passage("v1", "Restated: [formül 1] again.")
    passages = [
        okunacak,
        ayni_formul,
        _passage("v1", "No formula in this passage at all."),
        _passage("v2", "Ineligible source [formül 1]."),
        _passage("v1", "Smith, J. [formül 1]", section="References"),
    ]
    depo = _Depo()
    notlar = await ResearchPipeline._read_formulas(_hat(depo), "r1", passages, DOCUMENTS)

    assert notlar == {okunacak.id: "[formül 1] = x = v . t",
                      ayni_formul.id: "[formül 1] = x = v . t"}
    assert len(cagrilar) == 1
    ((ad, olay),) = depo.olaylar
    assert ad == "formula_resolution"
    assert olay["passage_count"] == 2 and olay["passages_with_notes"] == 2
    assert olay["durumlar"] == {"ok": 1}
