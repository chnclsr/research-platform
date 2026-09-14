"""Disagreements need conflicting evidence, not missing evidence.

Run 01M2FGWHWKW1GCRXVWTC97B94H: a draft wrote "the sources give no formula for layer
normalization, so there is disagreement", the merge carried it into the theme, and the
overview repeated it as a cross-study finding -- with one claim of 73 carrying counter-evidence.
A merge also wrote "Pass 2 ... while Pass 1 ..." into the report from the card labels.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from research_platform.llm import LLMProvider
from research_platform.report_synthesis import (
    SynthesisSection,
    _advisory_section_from_data,
    _claim_evidence_block,
    _pass_cards,
    _reduce_group,
)

_GAP_AS_DISAGREEMENT = (
    "Kaynaklar layer normalization için doğrudan formül vermez; bu nedenle bu konuda bir "
    "anlaşmazlık vardır [S01]."
)


def _claim(counter_evidence: int = 0):
    return SimpleNamespace(
        id="c1",
        text="Layer normalization rescales each token's activations.",
        status="qualified",
        audit={"counter_evidence": counter_evidence},
    )


@pytest.mark.parametrize(
    ("counter_evidence", "direction", "eligible"),
    [(0, "supports", "false"), (2, "supports", "true"), (0, "contradicts", "true")],
)
def test_a_claim_is_disagreement_eligible_only_on_conflicting_evidence(
    counter_evidence, direction, eligible
):
    source = SimpleNamespace(id="src1", metadata_json={"research_scope_role": "primary_in_scope"})
    block, _ = _claim_evidence_block(
        _claim(counter_evidence),
        {"c1": [(SimpleNamespace(quote="LN rescales each token.", direction=direction), source)]},
        {"src1": "S01"},
    )

    assert f"disagreement_eligible={eligible}" in block


def _advisory(disagreements_allowed: bool) -> SynthesisSection:
    section = _advisory_section_from_data(
        {"synthesis": "Layer normalization rescales activations [S01].",
         "disagreements": _GAP_AS_DISAGREEMENT},
        title="Layer normalization",
        source_ids=["S01"],
        claim_ids=["c1"],
        language="tr",
        consensus_allowed=False,
        disagreements_allowed=disagreements_allowed,
    )
    assert section is not None
    return section


def test_disagreements_without_conflicting_evidence_are_held_back_whole():
    section = _advisory(disagreements_allowed=False)

    assert section.disagreements == ""
    assert section.withheld_disagreements == _GAP_AS_DISAGREEMENT
    assert "disagreements:no_conflicting_evidence" in section.validation_warnings
    assert section.synthesis == "Layer normalization rescales activations [S01]."


def test_disagreements_with_conflicting_evidence_are_shown_as_written():
    section = _advisory(disagreements_allowed=True)

    assert section.disagreements == _GAP_AS_DISAGREEMENT
    assert section.withheld_disagreements == ""


def _draft(text: str, label: str, **fields) -> SynthesisSection:
    return SynthesisSection(title="Attention", synthesis=text, source_ids=[label], **fields)


def test_merge_cards_carry_no_pass_numbers_to_repeat():
    cards, _ = _pass_cards(
        [_draft("Alpha holds [S01].", "S01"), _draft("Beta holds [S02].", "S02")], 4000
    )

    assert "PASS" not in cards.upper().replace("PASSES", "")
    assert cards.count("SYNTHESIS:") == 2
    assert "\n---\n" in cards


class DisagreementInventingMerge(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {
            "synthesis": "Alpha and beta hold [S01] [S02].",
            "consensus": "",
            "disagreements": "Pass 2 states the formula differently from Pass 1 [S01].",
            "implications": "",
        }


@pytest.mark.asyncio
async def test_a_merge_cannot_add_a_disagreement_its_drafts_did_not_state():
    drafts = [
        _draft("Alpha holds [S01].", "S01", withheld_disagreements="Held back earlier [S01]."),
        _draft("Beta holds [S02].", "S02"),
    ]

    section, _note, _errors, _ungrounded = await _reduce_group(
        DisagreementInventingMerge(),
        question="How is attention formulated?",
        title="Attention",
        group=drafts,
        budget=4000,
        language="en",
        scope_context="",
    )

    assert section is not None
    assert section.disagreements == ""
    assert "Held back earlier [S01]." in section.withheld_disagreements
    assert "Pass 2 states the formula" in section.withheld_disagreements
