"""The report is written in the language the report says it is written in.

Readers were finding English paragraphs in Turkish Word reports. Measured before this work:
6 of 167 paragraphs across four completed Turkish runs, all body prose. The markdown in the
same bundle was worse -- all 22 atomic-finding headings in Appendix A and B were raw English.

Three separate causes, and a test here for each: a fallback path that printed English claim
statements with no language check at all, a block-level guard that accepted a Turkish
paragraph with an English tail pasted on, and export scaffolding hardcoded to Turkish
whatever `report_language` said.

Source titles and verbatim quotations are the deliberate exception. A translated title cannot
be looked up, so those stay in their own language and are labelled instead.
"""

from __future__ import annotations

import re

import pytest

from research_platform.claim_localization import localize_claim_texts, sweep_foreign_prose
from research_platform.exporter import sweep_synthesis_package
from research_platform.language_guard import (
    foreign_sentences,
    is_attribution,
    language_matches,
)
from research_platform.report_synthesis import (
    SynthesisPackage,
    SynthesisSection,
    _fallback_section,
)

TURKISH = "Bu çalışma bir kanıt sunuyor ve bulgular olumlu görünüyor."
ENGLISH = "The study reports an improved measured outcome for this population."


class TranslatorLLM:
    """Answers with the scripted payloads and counts the asking."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0
        self.prompts: list[str] = []

    async def complete_json(self, system: str, user: str):
        self.calls += 1
        self.prompts.append(user)
        if not self.answers:
            raise AssertionError("asked more times than the test scripted")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def drain_metrics(self):
        return []


class Claim:
    def __init__(self, claim_id: str, text: str):
        self.id = claim_id
        self.text = text


# --------------------------------------------------------------------------- guard


def test_the_guard_reads_both_directions():
    assert language_matches(TURKISH, "tr") is True
    assert language_matches(ENGLISH, "tr") is False
    assert language_matches(ENGLISH, "en") is True
    assert language_matches(TURKISH, "en") is False


def test_ordinary_english_prose_without_marker_words_is_still_english():
    """Turkish announces itself with diacritics; English's evidence is their absence.

    Without that, a sentence using none of the marker words was judged foreign in an English
    report and sent to a translator that could only paraphrase it.
    """
    assert language_matches("Replication is needed before generalisation [S01].", "en")
    assert language_matches("External validation was not demonstrated [S01].", "en")


def test_a_turkish_paragraph_with_an_english_tail_is_caught():
    """The exact shape that reached readers, and the exact shape the old guard passed."""
    mixed = f"{TURKISH} {ENGLISH}"
    # Whole-text check still says yes -- there is plenty of Turkish in it.
    assert language_matches(mixed, "tr") is True
    # The sentence check is what refuses it, and names only the offending sentence.
    foreign = foreign_sentences(mixed, "tr")
    assert len(foreign) == 1
    assert foreign[0].startswith("The study reports")


def test_attribution_lines_are_never_treated_as_leakage():
    """A translated source title cannot be looked up, so these are left alone."""
    assert is_attribution("Kaynak: Free AI Coding Tools Compared — https://example.com/x")
    assert is_attribution("Source: Accuracy of large language models — https://example.com")
    assert foreign_sentences(
        "Kaynak: Accuracy of large language models in head and neck cancers "
        "— https://www.frontiersin.org/articles/12345",
        "tr",
    ) == []


def test_a_short_fragment_is_not_judged():
    """Three words carry too little signal, and a false positive can only make prose worse."""
    assert foreign_sentences("AUC 0.94.", "tr") == []


# --------------------------------------------------------------- claim localization


@pytest.mark.asyncio
async def test_a_claim_already_in_the_report_language_is_not_sent_anywhere():
    llm = TranslatorLLM()  # any call raises
    texts, diagnostics = await localize_claim_texts(llm, [Claim("C1", TURKISH)], "tr")
    assert llm.calls == 0
    assert texts["C1"] == TURKISH
    assert diagnostics["direct"] == 1


@pytest.mark.asyncio
async def test_an_english_claim_is_translated_once():
    llm = TranslatorLLM({"items": [{"id": "C1", "text": TURKISH}]})
    texts, diagnostics = await localize_claim_texts(llm, [Claim("C1", ENGLISH)], "tr")
    assert llm.calls == 1
    assert texts["C1"] == TURKISH
    assert diagnostics["translated"] == 1
    assert diagnostics["failed"] == 0


@pytest.mark.asyncio
async def test_a_translation_that_loses_a_number_is_refused():
    """Showing an invented figure is worse than showing an English one: the reader can see
    that the second is untranslated, but not that the first is wrong.

    The check compares the numbers in order, which is stricter than it has to be -- a
    translation that reorders them is refused too. That is the intended direction of the
    error: a refused translation leaves an English sentence, an accepted wrong one leaves a
    Turkish sentence that reads as fact.
    """
    english = "Accuracy reached 98.5% across 240 documents."
    llm = TranslatorLLM(
        {"items": [{"id": "C1", "text": "Doğruluk 240 belgede yüzde 12 seviyesine ulaştı."}]},
        {"items": [{"id": "C1", "text": "Doğruluk %98.5 seviyesinde, 240 belge üzerinde ölçüldü."}]},
    )
    texts, diagnostics = await localize_claim_texts(llm, [Claim("C1", english)], "tr")
    assert llm.calls == 2
    assert "98.5" in texts["C1"]
    assert "12" not in texts["C1"]
    assert diagnostics["reasons"]["number_mismatch"] == 1
    assert diagnostics["translated"] == 1


@pytest.mark.asyncio
async def test_two_failures_keep_the_original_rather_than_dropping_the_finding():
    llm = TranslatorLLM(
        {"items": [{"id": "C1", "text": ENGLISH}]},
        {"items": [{"id": "C1", "text": ENGLISH}]},
    )
    texts, diagnostics = await localize_claim_texts(llm, [Claim("C1", ENGLISH)], "tr")
    assert llm.calls == 2
    assert texts["C1"] == ENGLISH
    assert diagnostics["failed"] == 1


@pytest.mark.asyncio
async def test_a_translator_outage_leaves_every_claim_standing():
    llm = TranslatorLLM(RuntimeError("provider down"))
    texts, diagnostics = await localize_claim_texts(llm, [Claim("C1", ENGLISH)], "tr")
    assert texts["C1"] == ENGLISH
    assert diagnostics["failed"] == 1


@pytest.mark.asyncio
async def test_a_run_pays_for_one_call_however_many_claims_it_has():
    claims = [Claim(f"C{n}", f"{ENGLISH} Item {n}.") for n in range(6)]
    llm = TranslatorLLM(
        {"items": [{"id": f"C{n}", "text": f"{TURKISH} Öğe {n}."} for n in range(6)]}
    )
    _, diagnostics = await localize_claim_texts(llm, claims, "tr")
    assert llm.calls == 1
    assert diagnostics["translated"] == 6


# ------------------------------------------------------------------- fallback path


def test_the_fallback_section_speaks_the_report_language():
    """The cause of the leak readers reported.

    This path runs whenever the model's own prose is rejected, and it had no language check
    at all -- only the "no narrative" message was ever localized.
    """
    claim = Claim("C1", ENGLISH)
    section = _fallback_section(
        "Tema",
        [claim],
        {"C1": [(object(), type("S", (), {"id": "SRC1"})())]},
        {"SRC1": "S01"},
        turkish=True,
        claim_texts={"C1": TURKISH},
    )
    assert TURKISH in section.synthesis
    assert "The study reports" not in section.synthesis
    # The citation marker survives translation; without it the sentence is ungrounded.
    assert "[S01]" in section.synthesis


def test_the_fallback_section_keeps_the_original_when_nothing_was_translated():
    claim = Claim("C1", ENGLISH)
    section = _fallback_section(
        "Theme",
        [claim],
        {"C1": [(object(), type("S", (), {"id": "SRC1"})())]},
        {"SRC1": "S01"},
        turkish=False,
    )
    assert ENGLISH in section.synthesis


# -------------------------------------------------------------------------- sweep


@pytest.mark.asyncio
async def test_the_sweep_translates_only_the_offending_sentence():
    """Re-translating correct prose costs tokens and can only degrade it."""
    llm = TranslatorLLM({"items": [{"id": "report:0", "text": "Çalışma ölçülen sonucu iyileştiriyor."}]})
    swept, diagnostics = await sweep_foreign_prose(
        llm, {"report": f"{TURKISH} {ENGLISH}"}, "tr"
    )
    assert diagnostics["foreign"] == 1
    assert diagnostics["translated"] == 1
    assert TURKISH in swept["report"]
    assert ENGLISH not in swept["report"]


@pytest.mark.asyncio
async def test_a_clean_report_costs_no_call_at_all():
    """Finding nothing is the point: it is the evidence the upstream repairs held."""
    llm = TranslatorLLM()  # any call raises
    swept, diagnostics = await sweep_foreign_prose(
        llm, {"report": TURKISH, "uncertainty": TURKISH}, "tr"
    )
    assert llm.calls == 0
    assert diagnostics["foreign"] == 0
    assert diagnostics["scanned"] == 2
    assert swept["report"] == TURKISH


@pytest.mark.asyncio
async def test_the_sweep_leaves_attribution_lines_alone():
    llm = TranslatorLLM()  # any call raises
    line = "Kaynak: Accuracy of large language models — https://example.com/article"
    _, diagnostics = await sweep_foreign_prose(llm, {"report": line}, "tr")
    assert llm.calls == 0
    assert diagnostics["foreign"] == 0


@pytest.mark.asyncio
async def test_the_sweep_leaves_prose_it_cannot_fix_rather_than_guessing():
    llm = TranslatorLLM(
        {"items": [{"id": "report:0", "text": ENGLISH}]},
        {"items": [{"id": "report:0", "text": ENGLISH}]},
    )
    swept, diagnostics = await sweep_foreign_prose(llm, {"report": ENGLISH}, "tr")
    assert swept["report"] == ENGLISH
    assert diagnostics["failed"] == 1


# --------------------------------------------------------------------- scaffolding


def test_the_export_scaffolding_follows_the_report_language():
    """The same bug seen from the other end: an English report with Turkish furniture."""
    from research_platform.exporter import _report_labels

    turkish = _report_labels("tr")
    english = _report_labels("en")
    assert turkish["question"] == "Araştırma sorusu"
    assert english["question"] == "Research question"
    assert english["appendix_a"].startswith("Appendix A")
    assert "Ek A" not in english["appendix_a"]
    assert set(turkish) == set(english)


# ------------------------------------------------- provider failure, measured in the wild


@pytest.mark.asyncio
async def test_one_provider_error_no_longer_costs_the_whole_run_its_translations():
    """The regression this closes, seen on run `01M1E06KQSW6HQHNDCGERTKRGW`.

    Its diagnostics read `failed: 31, reasons: {provider_error: 1}, call_count: 1` -- one
    timeout, and every claim in the report kept its English text. The second attempt was
    budgeted for exactly this and was being skipped.
    """
    claims = [Claim("C1", ENGLISH)]
    llm = TranslatorLLM(
        TimeoutError("read timeout"),
        {"items": [{"id": "C1", "text": TURKISH}]},
    )
    texts, diagnostics = await localize_claim_texts(llm, claims, "tr")
    assert llm.calls == 2
    assert texts["C1"] == TURKISH
    assert diagnostics["translated"] == 1
    assert diagnostics["failed"] == 0
    # The message is kept, so the next reader does not have to guess which provider failed.
    assert any("TimeoutError" in error for error in diagnostics["errors"])


@pytest.mark.asyncio
async def test_claims_are_translated_in_batches_so_one_slow_call_is_not_fatal():
    """7 claims in one call succeeded in production; the same call with 31 timed out."""
    claims = [Claim(f"C{n}", f"{ENGLISH} Item {n}.") for n in range(20)]

    class BatchLLM:
        def __init__(self):
            self.calls = 0
            self.sizes: list[int] = []

        async def complete_json(self, system: str, user: str):
            self.calls += 1
            ids = [line.split(":")[0].strip("- ") for line in user.splitlines() if line.startswith("- C")]
            self.sizes.append(len(ids))
            # The first batch times out; the rest answer. Only that batch may be affected.
            if self.calls == 1:
                raise TimeoutError("read timeout")
            return {
                "items": [
                    {"id": item_id, "text": f"{TURKISH} Öğe {item_id[1:]}."}
                    for item_id in ids
                ]
            }

        def drain_metrics(self):
            return []

    llm = BatchLLM()
    texts, diagnostics = await localize_claim_texts(llm, claims, "tr")
    assert max(llm.sizes) <= 8, "a prompt must not grow with the number of findings"
    # Every claim still ends up translated: the timed-out batch is retried, not abandoned.
    assert diagnostics["translated"] == 20
    assert diagnostics["failed"] == 0
    assert all(TURKISH in texts[f"C{n}"] for n in range(20))


@pytest.mark.asyncio
async def test_the_sweep_reaches_the_prose_the_word_report_renders():
    """The .docx renders `package.sections`, not the strings derived from the package.

    Sweeping only `executive_summary` / `narrative` / `uncertainty` corrected the markdown
    and left the Word report showing the pre-sweep English, because `build_word_report`
    reads the section objects directly.
    """
    package = SynthesisPackage(
        executive_summary=TURKISH,
        sections=[SynthesisSection(title="Bulgular", synthesis=ENGLISH)],
        cross_study_assessment="",
        conclusion="",
        uncertainty=TURKISH,
        study_profiles=[],
        generated_by_llm=True,
    )
    llm = TranslatorLLM(
        {"items": [{"id": "section_0_synthesis:0", "text": "Çalışma ölçülen sonucu iyileştiriyor."}]}
    )

    swept, diagnostics = await sweep_synthesis_package(llm, package, "tr")

    assert diagnostics["foreign"] == 1
    assert diagnostics["translated"] == 1
    assert ENGLISH not in swept.sections[0].synthesis
    assert ENGLISH not in swept.narrative
    assert swept.sections[0].title == "Bulgular"
    assert swept.executive_summary == TURKISH

    # The item ids reach the model as "- {key}:{index}: {text}". A key carrying its own
    # colon leaves nothing to say where the id stops, the model answers with a truncated
    # one, and every translation is dropped as `unknown_id` -- a whole run's sweep
    # translating nothing while reporting the foreign sentences it found.
    listed = re.findall(r"^- (\S+): ", llm.prompts[0], flags=re.MULTILINE)
    assert listed
    for item_id in listed:
        assert item_id.count(":") == 1, item_id
