"""Evidence-grounded, multi-stage report synthesis for small local models.

The research worker already extracts and audits atomic claims.  This module
turns those atoms into a readable report without asking a local model to hold
the entire corpus in one prompt.  Each thematic section receives a bounded
evidence packet and may cite only stable source labels such as ``[S03]``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal
from urllib.parse import urlparse

from .language_guard import foreign_sentences, language_matches
from .llm import LLMProvider
from .text_similarity import (
    claim_guard_compatible,
    ngram_jaccard,
    normalise_text,
    prose_overlaps,
    sequence_ratio,
    word_cosine,
)


@dataclass(frozen=True)
class StudyProfile:
    source_id: str
    source_label: str
    title: str
    contribution: str
    evidence_design: str


@dataclass(frozen=True)
class SynthesisSection:
    title: str
    synthesis: str
    consensus: str = ""
    disagreements: str = ""
    implications: str = ""
    # The sources this section's evidence packet OFFERED the model. Not the ones it went on
    # to cite -- see `cited_labels`, which reads the prose. Anything that reasons about
    # what actually reached the reader has to use that one.
    source_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    # How this section was produced: the LLM draft, or the fallback and why. Carried on the
    # section rather than looked up by position in `generation_diagnostics`, because the
    # index alignment between the two lists is an invariant nothing enforced.
    generation_note: str = ""
    # Validation is advisory for reader-facing LLM prose. The original text above is never
    # rewritten because one of these diagnostics fired; the one field ever held back whole is
    # `disagreements` -- see `withheld_disagreements`.
    validation_warnings: list[str] = field(default_factory=list)
    # A plain-language line shown to the reader above this section when how it was produced
    # changes how it should be read -- drafts presented unmerged, for one. Never a diagnostic
    # code: those stay in `validation_warnings` and never reach Word or PowerPoint.
    reader_note: str = ""
    # Disagreements the model wrote with no conflicting evidence behind them: no claim in the
    # section carries counter-evidence or a contradicting quote. Kept verbatim for the audit
    # record, never rendered. Measured on run 01M2FGWHWKW1GCRXVWTC97B94H: a draft turned "the
    # sources give no formula for layer normalization" into "so there is disagreement", the
    # merge carried it into the theme, and the overview repeated it as a cross-study finding,
    # while one claim of 73 had counter-evidence. A merge prompt told to report only
    # conflicting sources returned the same paragraph word for word.
    withheld_disagreements: str = ""


@dataclass(frozen=True)
class SynthesisPackage:
    executive_summary: str
    sections: list[SynthesisSection]
    cross_study_assessment: str
    conclusion: str
    uncertainty: str
    study_profiles: list[StudyProfile]
    generated_by_llm: bool
    generation_status: Literal[
        "complete", "complete_with_warnings", "partial", "failed"
    ] = "complete"
    generation_diagnostics: dict[str, str] = field(default_factory=dict)
    validation_warnings: dict[str, list[str]] = field(default_factory=dict)
    report_mode: str = "standard"
    quality_diagnostics: dict[str, Any] = field(default_factory=dict)
    answerability_status: Literal["answerable", "limited", "insufficient"] = "answerable"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def narrative(self) -> str:
        # Compact reports render their integrated answer once in the summary surface. The
        # internal section is retained for provenance and figures, but repeating it here
        # would recreate the exact defect this mode is designed to avoid.
        if self.report_mode == "compact":
            return ""
        # No validation codes in the reader's text. `synthesis:missing_citation` and its kind
        # are diagnostics for whoever audits the run: they stay on the section records, in the
        # synthesis events and in the export manifest, where they can be queried. Printed
        # above every section they read as a broken document to the person it was written for.
        parts: list[str] = []
        for section in self.sections:
            parts.append(f"## {section.title}\n\n{section.synthesis}")
            for label, value in (
                ("Ortak yön", section.consensus),
                ("Ayrışmalar", section.disagreements),
                ("Anlamı", section.implications),
            ):
                if value:
                    parts.append(f"**{label}:** {value}")
        if self.cross_study_assessment:
            parts.append(f"## Çalışmalar arası değerlendirme\n\n{self.cross_study_assessment}")
        if self.conclusion:
            parts.append(f"## Sonuç\n\n{self.conclusion}")
        return "\n\n".join(parts)


#: The canonical citation: exactly one label in its own brackets. Stays single-label --
#: the cut points and sentence boundaries below are defined in terms of it.
_TOKEN_RE = re.compile(r"\[S\d{2,3}\]")
#: One label, with or without brackets around it.
_LABEL_RE = re.compile(r"S\d{2,3}")
#: A citation as models actually write it: canonical, or several labels sharing one pair of
#: brackets. Measured on run 01M27RKQFHR80WNHEQVF2AF2DS, the model wrote `[S142, S209]` four
#: times; every one of them counted as zero citations and as a malformed bracket, and one of
#: them made `_grounded_excerpt` drop the sentence carrying it while reporting the excerpt as
#: still grounded. Recognising the form is what makes the citation counters mean anything.
_CITATION_RE = re.compile(r"\[S\d{2,3}(?:\s*,\s*S\d{2,3})*\]")
_BRACKET_RE = re.compile(r"\[([^\]]{1,80})\]")
_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_SENTENCE_END_RE = re.compile(
    r"[.!?](?:\s*(?:\[S\d{2,3}\]\s*)*)?(?=\s|$)",
    flags=re.UNICODE,
)
_OVERVIEW_FIELD_LIMITS = {
    "executive_summary": 2600,
    "cross_study_assessment": 3500,
    "conclusion": 2400,
    "uncertainty": 2400,
}
_DIRECT_ANSWER_RELEVANCE_THRESHOLD = 0.35
_STRONG_CONCLUSION_RE = re.compile(
    r"\b(?:proves?|proven|definitive(?:ly)?|conclusive(?:ly)?|establish(?:es|ed)?|"
    r"clear consensus|robust consensus|kanıtlar|kesin(?:dir|likle)?|tartışmasız|"
    r"güçlü uzlaşı)\b",
    re.IGNORECASE,
)
_SUPPORTING_TOPIC_RE = re.compile(
    r"\b(?:benchmark|dataset|data set|metric|evaluation|evaluate|bleu|rouge|radgraph|"
    r"veri seti|veri kümesi|metrik|değerlendir)\w*\b",
    re.IGNORECASE,
)


def _question_relevance(claim: Any) -> float:
    """Read an audited relevance score defensively for report-level decisions."""
    try:
        return max(
            0.0,
            min(
                1.0,
                float(
                    (getattr(claim, "audit", {}) or {}).get(
                        "question_relevance", 0.0
                    )
                    or 0.0
                ),
            ),
        )
    except (TypeError, ValueError):
        return 0.0


def citation_tokens(text: str) -> list[str]:
    """Every source label the prose cites, each written back as its own `[Sxx]`.

    `[S142, S209]` yields two tokens. Every consumer that counts, validates or re-attaches a
    citation needs labels; none of them can do anything with the raw grouped string, which is
    why the group form is normalised here once rather than handled at each call site.
    """
    return [
        f"[{label}]"
        for match in _CITATION_RE.finditer(text or "")
        for label in _LABEL_RE.findall(match.group(0))
    ]


def citation_counts(*texts: str) -> Counter[str]:
    """How many times each `Sxx` label is cited across the given prose.

    The counting half of `cited_labels`, kept separate because the report needs both: which
    sources a section stands on, and how heavily the document leans on each one.
    """
    counts: Counter[str] = Counter()
    for text in texts:
        for token in citation_tokens(text):
            counts[token.strip("[]")] += 1
    return counts


def cited_labels(section: SynthesisSection) -> set[str]:
    """The `Sxx` labels this section's prose actually cites.

    Distinct from `section.source_ids`, which is what the evidence packet offered the model.
    The two are routinely different -- a packet carries every source behind a theme's claims
    and the model cites the subset it found worth citing -- and conflating them overstates
    what the report rests on. Every reader-facing field is scanned, because a source cited
    only under "Ayrışmalar" is still cited.
    """
    return set(
        citation_counts(
            section.synthesis,
            section.consensus,
            section.disagreements,
            section.implications,
        )
    )


def _sentences(text: str) -> list[str]:
    """Split report prose at complete sentence boundaries, keeping citation suffixes."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(cleaned):
        sentence = cleaned[start:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    tail = cleaned[start:].strip()
    # A trailing clause is kept only when it ends on its citation, so a fragment never
    # arrives stripped of the source behind it. Grouped form counts here too -- a tail ending
    # `[S142, S209]` is as attributed as one ending `[S142]`.
    tail_citations = _CITATION_RE.findall(tail)
    if tail_citations and tail.endswith(tail_citations[-1]):
        sentences.append(tail)
    return sentences


def _ground_sentence(sentence: str, source_text: str) -> str:
    """Keep a selected fallback sentence tied to the citations of its source field.

    Re-attaching stays deliberately WITHIN one field: the labels come from the very text the
    sentence was taken out of, so the source is already standing behind this prose. Widening
    it -- to a neighbouring field, or to the tail a budget just cut away -- would be claiming
    support that was never given, which is a different thing from keeping support intact.
    """
    if _CITATION_RE.search(sentence):
        return sentence
    # Written back canonically, one label per pair of brackets: a sentence that is being
    # repaired should not inherit the grouped form that made the repair necessary.
    citations = list(dict.fromkeys(citation_tokens(source_text)))[:3]
    if not citations:
        return sentence
    punctuation = sentence[-1] if sentence[-1:] in ".!?" else "."
    body = sentence[:-1].rstrip() if sentence[-1:] in ".!?" else sentence.rstrip()
    return f"{body} {' '.join(citations)}{punctuation}"


def _bounded_grounded_join(values: list[str], max_chars: int) -> str:
    """Join only complete, grounded sentences, dropping any that will not fit.

    Greedy packing: a sentence too long for the remaining room is skipped and the next one
    tried. Returning "" when nothing fits is expected -- `_grounded_excerpt` carries the
    tighter budgets from there, and it is the one that must not drop the provenance.
    """
    selected: list[str] = []
    size = 0
    for value in values:
        for sentence in _sentences(value):
            grounded = _ground_sentence(sentence, value)
            projected = size + len(grounded) + int(bool(selected))
            if projected > max_chars:
                continue
            selected.append(grounded)
            size = projected
    return " ".join(selected)


def _grounded_excerpt(value: str, max_chars: int) -> tuple[str, bool]:
    """A compact internal excerpt, and whether it kept the source's provenance.

    The last layer cuts at the last `[Sxx]` that fits rather than at the last space. It only
    ever REMOVES a tail: every citation that survives was attached by the model to the prose
    that survives with it. Nothing is moved, copied or re-attached -- a citation lifted out
    of the deleted tail would be asserting that a source backs a clause it never saw.

    Measured on run 01M25XYS6ETQVXMPY24HXVKNXG: a 17-packet theme gave each card field 90
    characters, no whole sentence fit, and the plain word-boundary slice handed the merge
    model citation-free fragments. Its own prompt then forbids inventing a citation, so four
    of five report sections reached the reader with no provenance at all.

    The flag is the measurement that was missing: a caller can count the fields whose
    citations did not survive instead of discovering it in the finished report.

    Grouped citations count as citations throughout. Reading them with the single-label
    pattern was worse than not counting them: `had_citation` came out False, so prose whose
    only attribution was `[S142, S209]` could be cut away wholesale and still be reported as
    grounded -- the flag said the budget had cost nothing precisely where it had cost
    everything.
    """
    cleaned = " ".join(value.split())
    had_citation = bool(_CITATION_RE.search(cleaned))

    def result(text: str) -> tuple[str, bool]:
        return text, (not had_citation) or bool(_CITATION_RE.search(text))

    if len(cleaned) <= max_chars:
        return result(cleaned)
    complete = _bounded_grounded_join([cleaned], max_chars)
    if complete:
        return result(complete)
    fitting = [match for match in _CITATION_RE.finditer(cleaned) if match.end() <= max_chars]
    if fitting:
        return result(cleaned[: fitting[-1].end()])
    boundary = cleaned.rfind(" ", 0, max_chars)
    cut = cleaned[: boundary if boundary > 0 else max_chars].rstrip()
    # A grouped citation is wide enough that a word boundary can fall inside it, leaving
    # `[S142,` at the end. That half-bracket is not a citation and reads like one, so a model
    # shown the excerpt could copy the broken shape. Drop the opener and whatever follows it.
    opener = cut.rfind("[")
    if opener >= 0 and "]" not in cut[opener:]:
        cut = cut[:opener].rstrip()
    return result(cut)


def _prompt_excerpt(value: str, max_chars: int) -> str:
    """Make a compact internal-only excerpt, preferring complete sentences."""
    return _grounded_excerpt(value, max_chars)[0]


#: How a consolidation card divides its room between the four prose fields.
_CARD_FIELD_WEIGHTS = {
    "synthesis": 0.55,
    "consensus": 0.15,
    "disagreements": 0.15,
    "implications": 0.15,
}
#: Measured on run 01M25XYS6ETQVXMPY24HXVKNXG: a 407-character secondary field kept every
#: citation, a 237-character one kept none. The floor sits just under the width that worked.
#: Being too high costs one more reduction round; being too low costs the report's entire
#: provenance, which is what happened.
_CARD_MIN_SECONDARY_CHARS = 400
#: "PASS n" plus the four field labels.
_CARD_LABEL_CHARS = 60
#: Derived from the weights so that changing them moves the floor with them.
_CONSOLIDATION_PASS_FLOOR = int(_CARD_MIN_SECONDARY_CHARS / min(_CARD_FIELD_WEIGHTS.values()))


def _consolidation_fan_in(budget: int) -> int:
    """How many drafts one merge call may carry and still show each its citations.

    A fan-in of 1 would never reduce anything, so two is the floor: the tree always makes
    progress, even on a budget too small to honour `_CONSOLIDATION_PASS_FLOOR`.
    """
    return max(2, budget // (_CONSOLIDATION_PASS_FLOOR + _CARD_LABEL_CHARS))


def _balanced_chunks(count: int, fan_in: int) -> list[int]:
    """Split `count` items into near-equal groups of at most `fan_in`.

    Balanced rather than greedy on purpose. Greedy packing of 17 at a fan-in of 8 gives
    [8, 8, 1], and that lone draft then competes in the next round against nodes that each
    compressed eight -- a real asymmetry in how much of the evidence survived. [6, 6, 5]
    keeps the passes comparable, and never produces a one-member group that would have to
    be carried rather than merged.
    """
    if count <= 0:
        return []
    groups = math.ceil(count / fan_in)
    base, extra = divmod(count, groups)
    return [base + 1] * extra + [base] * (groups - extra)


#: report_language is Literal["tr", "en"], so this stays a closed map rather than a
#: lookup that could silently fall through to a language nothing enforces.
_LANGUAGE_NAMES = {"tr": "Turkish", "en": "English"}
#: A closing line in the target language, for a deliverable whose language is not the
#: evidence's. English gets none: the whole prompt already is English.
_LANGUAGE_CLOSERS = {"tr": " Son kural: cevabın tamamı Türkçe olacak."}
#: The language claims and quotes are stored in. The packet is built from them verbatim,
#: so this is the language the model is reading no matter what it is asked to write.
_EVIDENCE_LANGUAGE = "en"


def _language_directive(language: str) -> str:
    """Name the output language, and when it differs from the evidence's, forbid copying.

    The old instruction was `Write in report language 'tr'.` -- an ISO code, in English, at
    the tail of an English prompt whose EVIDENCE_PACKET is entirely English because claims
    are stored in the research language. Measured 2026-09-07 on qwen3:4b-instruct against
    real packets from run 01M1NT3VCT2R0G10DFD4BRVVG1: with the English RESEARCH_QUESTION
    the drafting call produced English in 0/9 fields; naming the language and forbidding
    sentence copying took it to 10/10. Malformed `[S1, S2]` citations fell from 3 to 1 over
    the same four packets -- a model that has slipped into copying its English evidence
    copies that evidence's citation habits too -- so this reduces that failure without
    fixing it; the citation format needs its own guard.

    The translate-don't-copy clause is conditional because it is nonsense when the report
    language is the evidence language: telling a model to write English, translate, and
    never copy an English sentence is three instructions that disagree.

    The constraint body stays English on purpose. Translating the whole prompt also fixes
    the language, but in the same measurement it dropped the synthesis field entirely in
    one run of three; the rules that keep the model from inventing sources are worth more
    than the symmetry.
    """
    # Resolved once: a value outside the schema must fall back whole, not pick up the
    # default's name while losing its closing line.
    resolved = language if language in _LANGUAGE_NAMES else "tr"
    name = _LANGUAGE_NAMES[resolved]
    if resolved == _EVIDENCE_LANGUAGE:
        return f"OUTPUT LANGUAGE: {name}."
    evidence_name = _LANGUAGE_NAMES[_EVIDENCE_LANGUAGE]
    return (
        f"OUTPUT LANGUAGE: {name}. The evidence below is in {evidence_name}, but every "
        f"sentence of every field MUST be written in {name}. Translate the findings; never "
        f"copy an {evidence_name} sentence."
        f"{_LANGUAGE_CLOSERS.get(resolved, '')}"
    )


def _prompt_char_budget(llm: LLMProvider) -> int:
    """Reserve output and fixed-prompt room before filling a prompt with evidence.

    Measured on a live run, this content runs about 2.9 characters per token; the two used
    here is deliberately below that, because being wrong in this direction only wastes a
    little context and being wrong in the other truncates a section.

    The 24000 ceiling saturates at `llm_context_tokens == 15584`, so raising the setting
    past 16384 buys nothing here and only enlarges the KV cache. If a bigger window is ever
    genuinely needed, this ceiling is the thing to revisit -- not the setting.

    What the full budget is FOR is the merge and overview layers, which read many drafts at
    once. The drafting layer takes its evidence share from `_PACKET_TARGET_CHARS` instead --
    see `_section_packet_budget`.
    """
    # A provider that knows its own window says so. `settings` describe the local model only,
    # and an API provider has none -- which used to shrink its budgets to the 8192/2048 defaults.
    token_limits = getattr(llm, "token_limits", None)
    limits = token_limits() if callable(token_limits) else None
    if limits:
        context_tokens, output_tokens = limits
    else:
        settings = getattr(llm, "settings", None)
        context_tokens = int(getattr(settings, "llm_context_tokens", 8192))
        output_tokens = int(getattr(settings, "llm_max_output_tokens", 2048))
    available_tokens = max(2048, context_tokens - output_tokens - 1536)
    return max(6000, min(24000, available_tokens * 2))


#: The most evidence one drafting prompt may carry, whatever the context window allows.
#: This is the budget run 01M25XYS6ETQVXMPY24HXVKNXG drafted under, at roughly 15 claims per
#: packet.
_PACKET_TARGET_CHARS = 9216


def _section_packet_budget(
    llm: LLMProvider, *, question: str, title: str, scope_context: str
) -> int:
    """The room a theme's evidence may occupy once the rest of the prompt is paid for.

    The system prompt sits inside the fixed reserve `_prompt_char_budget` already holds
    back; what is subtracted here is the part that varies per run and per theme, plus room
    for the `[Sxx]` allow-list.

    Capped independently of the context window, because packet size and citation density
    turned out to trade against each other. Measured directly against the live model on one
    theme's real evidence: 60 claims in a single 28.8k-character packet produced prose with
    ZERO citations, while the same claims at 17 per packet produced 14. The model has the
    same 2048 output tokens either way, so a denser packet buys abstraction, and abstraction
    drops the attributions first.

    A window smaller than the cap still shrinks the packet -- `min` only stops it growing.
    Raising `llm_context_tokens` therefore widens the merge and overview prompts, which is
    what lifts `_consolidation_fan_in` from 2 to 8, without touching what a draft is asked
    to read.
    """
    return max(
        2000,
        min(_prompt_char_budget(llm), _PACKET_TARGET_CHARS)
        - len(question)
        - len(title)
        - len(scope_context)
        - 600,
    )


def _overview_digest(sections: list[SynthesisSection], max_chars: int) -> tuple[str, int]:
    """Create balanced theme cards instead of truncating one monolithic digest.

    Returns the digest and the number of card fields whose citations the budget cut away.
    This divides one budget by the theme count exactly the way `_consolidate_passes` does,
    so it fails the same way at scale: with five themes and 205 sources the secondary fields
    come to roughly 220 characters, under the 400 that was measured to keep a citation.
    """
    if not sections:
        return "", 0
    per_theme = max(900, max_chars // len(sections))
    cards: list[str] = []
    ungrounded = 0
    for section in sections:
        synthesis_budget = max(360, int(per_theme * 0.46))
        secondary_budget = max(140, int(per_theme * 0.16))
        rows = [f"THEME: {_prompt_excerpt(section.title, 240)}"]
        for label, value, budget in (
            ("SYNTHESIS", section.synthesis, synthesis_budget),
            ("CONSENSUS", section.consensus, secondary_budget),
            ("DISAGREEMENTS", section.disagreements, secondary_budget),
            ("IMPLICATIONS", section.implications, secondary_budget),
        ):
            excerpt, grounded = _grounded_excerpt(value, budget)
            ungrounded += int(not grounded)
            rows.append(f"{label}: {excerpt}")
        cards.append("\n".join(rows))
    digest = "\n\n".join(cards)
    if len(digest) <= max_chars:
        return digest, ungrounded
    boundary = digest.rfind("\n\n", 0, max_chars)
    return digest[: boundary if boundary > 0 else max_chars].rstrip(), ungrounded


def _metadata(source: Any) -> dict[str, Any]:
    value = getattr(source, "metadata_json", None)
    if not isinstance(value, dict):
        value = getattr(source, "metadata", None)
    return value if isinstance(value, dict) else {}


def _source_text(source: Any, claims: list[Any]) -> str:
    metadata = _metadata(source)
    values: list[str] = [
        str(getattr(source, "title", "")),
        str(metadata.get("abstract") or ""),
        str(metadata.get("snippet") or ""),
        str(metadata.get("publication_type") or metadata.get("type") or ""),
    ]
    values.extend(str(getattr(claim, "text", "")) for claim in claims)
    return " ".join(values).lower()


def _classify_contribution(text: str, turkish: bool) -> str:
    patterns = (
        (r"\b(systematic review|meta-analysis|scoping review|literature review)\b", "Sentez / derleme", "Synthesis / review"),
        (r"\b(guideline|consensus|policy|regulation|recommendation)\b", "Kılavuz / politika", "Guidance / policy"),
        (r"\b(dataset|database|registry|benchmark|challenge)\b", "Veri seti / benchmark", "Dataset / benchmark"),
        (r"\b(external validation|validation cohort|multicentre|multicenter|replication)\b", "Dış doğrulama", "External validation"),
        (r"\b(implementation|workflow|deployment|clinical practice|real.world)\b", "Uygulama / iş akışı", "Implementation / workflow"),
        (r"\b(detect|diagnos|classif|screen|triage|segment)\w*\b", "Tespit / tanı", "Detection / diagnosis"),
        (r"\b(predict|prognos|risk|survival|outcome)\w*\b", "Tahmin / risk", "Prediction / risk"),
        (r"\b(model|method|algorithm|architecture|framework|network)\w*\b", "Yöntem geliştirme", "Method development"),
    )
    for pattern, tr_label, en_label in patterns:
        if re.search(pattern, text, flags=re.I):
            return tr_label if turkish else en_label
    return "Diğer katkı" if turkish else "Other contribution"


def _classify_design(text: str, turkish: bool) -> str:
    patterns = (
        (r"\b(systematic review|meta-analysis|scoping review)\b", "Sistematik sentez", "Systematic synthesis"),
        (r"\b(randomi[sz]ed|controlled trial|rct)\b", "Kontrollü çalışma", "Controlled study"),
        (r"\b(prospective)\b", "Prospektif", "Prospective"),
        (r"\b(external validation|independent validation)\b", "Dış doğrulama", "External validation"),
        (r"\b(multicentre|multicenter|multi-institution)\b", "Çok merkezli", "Multicentre"),
        (r"\b(retrospective)\b", "Retrospektif", "Retrospective"),
        (r"\b(cohort|case.control|cross-sectional)\b", "Gözlemsel", "Observational"),
        (r"\b(dataset|benchmark|challenge)\b", "Benchmark / veri seti", "Benchmark / dataset"),
        (r"\b(review|perspective|commentary)\b", "Anlatısal derleme", "Narrative review"),
    )
    for pattern, tr_label, en_label in patterns:
        if re.search(pattern, text, flags=re.I):
            return tr_label if turkish else en_label
    return "Tasarım belirtilmemiş" if turkish else "Design not reported"


def source_design_labels(sources: list[Any], *, turkish: bool = True) -> dict[str, str]:
    """The `_classify_design` label per source id, without building full StudyProfiles.

    Same table the report prints in its study-profile block, so a tier decision made from
    these labels and the design column a reader sees can never disagree. Exposed rather
    than copied because the alternative -- a second regex table elsewhere -- drifts.
    """
    return {
        str(source.id): _classify_design(_source_text(source, []), turkish)
        for source in sources
    }


def build_study_profiles(
    sources: list[Any],
    reportable_claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    *,
    turkish: bool,
) -> list[StudyProfile]:
    claims_by_source: dict[str, list[Any]] = {}
    for claim in reportable_claims:
        for _, source in evidence_by_claim.get(str(claim.id), []):
            claims_by_source.setdefault(str(source.id), []).append(claim)
    profiles: list[StudyProfile] = []
    for index, source in enumerate(sources, 1):
        role = str(_metadata(source).get("research_scope_role") or "primary_in_scope")
        if role not in {"primary_in_scope", "supporting_benchmark"}:
            continue
        text = _source_text(source, claims_by_source.get(str(source.id), []))
        profiles.append(
            StudyProfile(
                source_id=str(source.id),
                source_label=f"S{index:02d}",
                title=str(getattr(source, "title", "")),
                contribution=_classify_contribution(text, turkish),
                evidence_design=_classify_design(text, turkish),
            )
        )
    return profiles


def _words(text: str) -> set[str]:
    stop = {
        "about", "after", "also", "among", "and", "are", "but", "for", "from", "have",
        "into", "not", "that", "the", "their", "this", "using", "with", "olan", "olarak",
        "ve", "ile", "bir", "bu", "için", "gibi", "daha", "üzerine", "araştırma",
    }
    return {match.group(0).lower() for match in _WORD_RE.finditer(text) if match.group(0).lower() not in stop}


def _scope_anchors(question: str) -> list[str]:
    """Extract run-specific wording without a domain or season lookup table.

    These reach the model as `SCOPE_BOUNDARIES` guidance and nothing else. A section is
    never discarded for failing to echo them: measured across live runs, every draft that
    the old literal-match guard rejected had stayed on the run's subject and merely reached
    for a synonym -- "AI" for "yapay zeka", "medikal görüntüleme" for "radyoloji" -- and the
    stitched claim sentences that replaced it read far worse than the draft it threw away.
    """
    quoted = [
        next(value for value in match.groups() if value)
        for match in re.finditer(r'"([^"\n]+)"|“([^”\n]+)”|\'([^\'\n]+)\'', question or "")
    ]
    acronyms = re.findall(r"\b[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9-]{1,}\b", question or "")
    content = sorted(word for word in _words(question) if len(word) >= 4)
    anchors: list[str] = []
    seen_stems: set[str] = set()
    for anchor in dict.fromkeys([*quoted, *acronyms, *content]):
        words = normalise_text(anchor).split()
        if len(words) > 1:
            anchors.append(anchor)
            continue
        if not words:
            continue
        # Inflections of one word are one boundary. Turkish reaches this constantly:
        # "çalışmaları" and "çalışmalarını" say the same thing, and listing both spends
        # prompt room repeating a boundary the model has already been given.
        stem = words[0][:5]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        anchors.append(anchor)
    return anchors[:24]


def _deduplicate_report_claims(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
) -> tuple[list[Any], dict[str, list[tuple[Any, Any]]], dict[str, str]]:
    """Conservatively collapse historical paraphrases before theme assignment."""
    representatives: list[Any] = []
    merged_evidence: dict[str, list[tuple[Any, Any]]] = {}
    merged_ids: dict[str, str] = {}
    for claim in claims:
        claim_id = str(claim.id)
        text = str(getattr(claim, "text", ""))
        source_ids = {
            str(source.id) for _, source in evidence_by_claim.get(claim_id, [])
        }
        representative = None
        for other in representatives:
            other_id = str(other.id)
            other_text = str(getattr(other, "text", ""))
            other_sources = {
                str(source.id) for _, source in merged_evidence.get(other_id, [])
            }
            if not claim_guard_compatible(text, other_text):
                continue
            if sequence_ratio(text, other_text) >= 0.92 or (
                bool(source_ids & other_sources) and word_cosine(text, other_text) >= 0.68
            ):
                representative = other
                break
        target_id = str(representative.id) if representative is not None else claim_id
        if representative is None:
            representatives.append(claim)
            merged_evidence[target_id] = []
        else:
            merged_ids[claim_id] = target_id
        known = {
            (str(source.id), str(getattr(link, "quote", "")))
            for link, source in merged_evidence[target_id]
        }
        for link, source in evidence_by_claim.get(claim_id, []):
            key = (str(source.id), str(getattr(link, "quote", "")))
            if key not in known:
                merged_evidence[target_id].append((link, source))
                known.add(key)
    return representatives, merged_evidence, merged_ids


def _contributing_sources(
    claims: list[Any], evidence_by_claim: dict[str, list[tuple[Any, Any]]]
) -> set[str]:
    return {
        str(source.id)
        for claim in claims
        for _, source in evidence_by_claim.get(str(claim.id), [])
    }


def _independent_contributors(
    claims: list[Any], evidence_by_claim: dict[str, list[tuple[Any, Any]]]
) -> set[str]:
    """Return independent evidence origins, using the audit layer's domain convention."""
    identities: set[str] = set()
    for claim in claims:
        for _, source in evidence_by_claim.get(str(claim.id), []):
            host = (urlparse(str(getattr(source, "url", ""))).hostname or "").lower()
            host = re.sub(r"^www\.", "", host)
            identities.add(f"domain:{host}" if host else f"source:{source.id}")
    return identities


def _report_mode(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    coverage: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Decide the report shape from what the audited corpus actually holds.

    `estimated_completeness` deliberately does not appear here. It is a Chao1 incidence
    estimator over provider overlap, and its unseen term is `q1 ** 2 / (2 * q2)`: a corpus
    whose connectors happen not to rediscover each other's sources lands one or two
    doubletons, the estimate collapses towards zero, and a run with dozens of audited
    claims from dozens of sources would be rendered as a single stitched paragraph. It
    measures discovery overlap, not whether these claims can carry themes, and it is a
    diagnostic rather than a recall guarantee -- so it stays in the coverage report and
    out of the report shape.
    """
    reasons: list[str] = []
    if len(claims) < 8:
        reasons.append("fewer_than_8_unique_claims")
    if len(_contributing_sources(claims, evidence_by_claim)) < 4:
        reasons.append("fewer_than_4_contributing_sources")
    return ("compact" if reasons else "standard"), reasons


def _generic_theme(claim_text: str, turkish: bool) -> str:
    text = claim_text.lower()
    rows = (
        (r"\b(limit|bias|uncertain|harm|failure|weak|caution)\w*\b", "Sınırlılıklar ve riskler", "Limitations and risks"),
        (r"\b(valid|external|generaliz|replic|prospective|multicent)\w*\b", "Doğrulama ve genellenebilirlik", "Validation and generalisability"),
        (r"\b(implement|workflow|clinical|practice|cost|deploy)\w*\b", "Uygulama ve klinik anlam", "Implementation and practical meaning"),
        (r"\b(performance|accuracy|auc|sensitiv|specific|improv|outperform|effect)\w*\b", "Bulgular ve karşılaştırmalı sonuçlar", "Findings and comparative outcomes"),
        (r"\b(method|model|algorithm|architect|dataset|feature|train)\w*\b", "Yaklaşımlar ve yöntemler", "Approaches and methods"),
    )
    for pattern, tr_label, en_label in rows:
        if re.search(pattern, text, flags=re.I):
            return tr_label if turkish else en_label
    return "Temel bulgular" if turkish else "Core findings"


def _plan_themes(
    claims: list[Any],
    sub_questions: list[str],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    *,
    display_sub_questions: list[str] | None = None,
    turkish: bool,
    report_mode: str,
    maximum: int = 5,
) -> list[tuple[str, list[Any]]]:
    if report_mode == "compact":
        title = "Kanıt özeti" if turkish else "Evidence summary"
        return [(title, list(claims))] if claims else []
    usable_sub_questions = [str(item).strip() for item in sub_questions if str(item).strip()][:maximum]
    display = [str(item).strip() for item in (display_sub_questions or [])]
    display_by_question = {
        question: (display[index] if index < len(display) and display[index] else question)
        for index, question in enumerate(usable_sub_questions)
    }
    buckets: dict[str, list[Any]] = {question: [] for question in usable_sub_questions}
    generic: dict[str, list[Any]] = {}
    for claim in claims:
        claim_text = str(getattr(claim, "text", ""))
        claim_words = _words(claim_text)
        links = evidence_by_claim.get(str(claim.id), [])
        supporting_only = bool(links) and all(
            str(_metadata(source).get("research_scope_role") or "primary_in_scope")
            == "supporting_benchmark"
            for _, source in links
        )
        best_title = ""
        best_score = 0
        for title in usable_sub_questions:
            if supporting_only and not re.search(
                r"\b(benchmark|dataset|metric|evaluation|evaluate|veri|metrik|değerlendir)",
                title,
                re.IGNORECASE,
            ):
                continue
            score = len(claim_words & _words(title))
            if score > best_score:
                best_title, best_score = title, score
        if best_title and best_score >= 2:
            buckets[best_title].append(claim)
        else:
            generic_title = (
                "Değerlendirme kaynakları ve benchmarklar"
                if turkish
                else "Evaluation resources and benchmarks"
            ) if supporting_only else _generic_theme(claim_text, turkish)
            generic.setdefault(generic_title, []).append(claim)
    rows = [
        (display_by_question[question], values)
        for question, values in buckets.items()
        if values
    ]
    rows.extend(sorted(generic.items(), key=lambda item: len(item[1]), reverse=True))
    if not rows and claims:
        rows = [(("Temel bulgular" if turkish else "Core findings"), claims)]
    rows = sorted(rows, key=lambda item: len(item[1]), reverse=True)[:maximum]
    assigned = {str(claim.id) for _, values in rows for claim in values}
    leftovers = [claim for claim in claims if str(claim.id) not in assigned]
    if leftovers and rows:
        rows[0][1].extend(leftovers)
    viable: list[tuple[str, list[Any]]] = []
    sparse: list[Any] = []
    for title, values in rows:
        if len(values) >= 2 and len(_contributing_sources(values, evidence_by_claim)) >= 2:
            viable.append((title, values))
        else:
            sparse.extend(values)
    if sparse:
        if viable:
            viable[0][1].extend(sparse)
        else:
            viable = [("Temel bulgular" if turkish else "Core findings", sparse)]
    return viable


@dataclass(frozen=True)
class EvidencePacket:
    """One prompt's worth of a theme's evidence."""

    text: str
    source_ids: list[str]
    claim_ids: list[str]


# "C01 | " today, "C100 | " once a theme passes a hundred claims. Budgeted at the wider
# value because over-reserving costs a little prompt room and under-reserving costs the
# context guarantee this whole path exists to keep.
_BLOCK_LABEL_CHARS = 7


def _claim_evidence_block(
    claim: Any,
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    source_labels: dict[str, str],
) -> tuple[str, list[str]]:
    """One claim's block body and the sources it is allowed to be cited from.

    Empty body when nothing citable backs the claim. The per-claim caps here -- 900
    characters of statement, 650 per quote, four quotes -- bound how much of a packet a
    single claim can occupy. They shorten a claim; they never drop one.
    """
    lines: list[str] = []
    sources: list[str] = []
    primary_sources: set[str] = set()
    contradicted = False
    for link, source in evidence_by_claim.get(str(claim.id), []):
        source_label = source_labels.get(str(source.id))
        quote = " ".join(str(getattr(link, "quote", "")).split())[:650]
        if not source_label or not quote:
            continue
        direction = str(getattr(link, "direction", "supports"))
        contradicted = contradicted or direction == "contradicts"
        lines.append(f"{source_label} {direction}: {quote}")
        if source_label not in sources:
            sources.append(source_label)
        if str(_metadata(source).get("research_scope_role") or "primary_in_scope") == (
            "primary_in_scope"
        ):
            primary_sources.add(str(source.id))
    if not lines:
        return "", []
    # The evidence grade rides in here rather than into a sort key: the drafting model can
    # write "three small series against one multicentre trial", which a reader can check,
    # where a reordering would have moved claims around with nothing on the page saying so.
    appraisal = (getattr(claim, "audit", None) or {}).get("appraisal") or {}
    grade = str(appraisal.get("grade") or "")[:28]
    grade_field = f"evidence={grade} | " if grade else ""
    consensus_eligible = (
        str(getattr(claim, "status", "")) == "supported"
        and grade in {"strong", "moderate"}
        and len(primary_sources) >= 2
    )
    # A disagreement needs evidence that conflicts, not evidence that is missing.
    counter_evidence = int((getattr(claim, "audit", None) or {}).get("counter_evidence", 0) or 0)
    disagreement_eligible = contradicted or counter_evidence > 0
    body = (
        f"status={getattr(claim, 'status', 'qualified')} | {grade_field}"
        f"consensus_eligible={'true' if consensus_eligible else 'false'} | "
        f"disagreement_eligible={'true' if disagreement_eligible else 'false'} | "
        f"claim={str(getattr(claim, 'text', ''))[:900]}\n" + "\n".join(lines[:4])
    )
    return body, sources


def _evidence_packets(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    source_labels: dict[str, str],
    *,
    char_budget: int,
) -> tuple[list[EvidencePacket], list[str]]:
    """Split a theme's evidence into packets that each fit the prompt, dropping nothing.

    This replaced a flat `max_claims=12` cap. Measured on run 01M1K0KBNMYV3RF8TB20JZ333P,
    that cap hid 38 of 86 audited claims from the model -- 44% of the evidence -- while the
    largest prompt the run ever sent was 2695 of 8192 context tokens and not one of its 671
    calls stopped on `length`. The evidence was being discarded into free space.

    Every claim with a citable quote lands in exactly one packet. A claim whose block alone
    exceeds the budget still gets a packet of its own rather than being skipped: the caps in
    `_claim_evidence_block` keep a single block near 3.6k characters against a budget that
    does not go below 2000, so this stays a guarantee rather than a hope.

    Returns the packets and the ids of claims nothing citable backed -- counted rather than
    silently passed over, because "the model saw all of it" is only honest with that number
    beside it.
    """
    prepared: list[tuple[str, str, list[str]]] = []
    unbacked: list[str] = []
    for claim in claims:
        body, sources = _claim_evidence_block(claim, evidence_by_claim, source_labels)
        if not body:
            unbacked.append(str(claim.id))
            continue
        prepared.append((str(claim.id), body, sources))

    def pack(rows: list[tuple[str, str, list[str]]]) -> EvidencePacket:
        # Numbering restarts per packet because each packet is its own prompt, and a first
        # block labelled C13 would be describing a C01..C12 the model was never shown.
        text = "\n\n".join(
            f"C{number:02d} | {body}" for number, (_, body, _) in enumerate(rows, 1)
        )
        source_ids: list[str] = []
        for _, _, sources in rows:
            for label in sources:
                if label not in source_ids:
                    source_ids.append(label)
        return EvidencePacket(text, source_ids, [claim_id for claim_id, _, _ in rows])

    packets: list[EvidencePacket] = []
    current: list[tuple[str, str, list[str]]] = []
    length = 0
    for row in prepared:
        cost = len(row[1]) + _BLOCK_LABEL_CHARS + (2 if current else 0)
        if current and length + cost > char_budget:
            packets.append(pack(current))
            current, length = [], 0
            cost = len(row[1]) + _BLOCK_LABEL_CHARS
        current.append(row)
        length += cost
    if current:
        packets.append(pack(current))
    return packets, unbacked


def _reader_text(value: Any) -> str:
    """Extract model prose without normalising or otherwise rewriting string output."""
    return value if isinstance(value, str) else ""


def _text_warnings(
    value: str,
    *,
    field_name: str,
    allowed: set[str],
    language: str,
) -> list[str]:
    if not value:
        return [f"{field_name}:missing"]
    warnings: list[str] = []
    citations = set(citation_tokens(value))
    unknown = sorted(citations - allowed)
    if unknown:
        warnings.append(f"{field_name}:unknown_citations:{','.join(unknown)}")
    # Sharing one pair of brackets is a format the model reaches for, not a broken citation:
    # the labels are real and the source is named. It gets its own code so `missing_citation`
    # stops firing on attributed prose, while the preference for one label per pair stays
    # visible -- this counter is what says whether the prompt rule is landing.
    grouped = sorted(
        {
            match.group(0)
            for match in _CITATION_RE.finditer(value)
            if not _TOKEN_RE.fullmatch(match.group(0))
        }
    )
    if grouped:
        warnings.append(f"{field_name}:grouped_citations:{','.join(grouped)}")
    malformed = sorted(
        {
            match.group(0)
            for match in _BRACKET_RE.finditer(value)
            if "S" in match.group(1).upper()
            and not _TOKEN_RE.fullmatch(match.group(0))
            and not _CITATION_RE.fullmatch(match.group(0))
        }
    )
    if malformed:
        warnings.append(f"{field_name}:malformed_citations:{','.join(malformed)}")
    if allowed and not citations:
        warnings.append(f"{field_name}:missing_citation")
    if re.search(r"https?://", value):
        warnings.append(f"{field_name}:raw_url")
    if not language_matches(value, language) or foreign_sentences(value, language):
        warnings.append(f"{field_name}:language_mismatch")
    return warnings


def _advisory_section_from_data(
    data: Any,
    *,
    title: str,
    source_ids: list[str],
    claim_ids: list[str],
    language: str,
    consensus_allowed: bool,
    limited_evidence_only: bool = False,
    disagreements_allowed: bool = True,
) -> SynthesisSection | None:
    """Accept usable LLM prose and report defects without changing the prose.

    The exception is `disagreements` written with no conflicting evidence behind it, which
    is held back whole rather than shown -- see `SynthesisSection.withheld_disagreements`.
    """
    if not isinstance(data, dict):
        return None
    synthesis = _reader_text(data.get("synthesis"))
    if not synthesis:
        return None
    allowed = {f"[{source_id}]" for source_id in source_ids}
    values = {
        "synthesis": synthesis,
        "consensus": _reader_text(data.get("consensus")),
        "disagreements": _reader_text(data.get("disagreements")),
        "implications": _reader_text(data.get("implications")),
    }
    warnings = [
        warning
        for field_name, value in values.items()
        if value
        for warning in _text_warnings(
            value,
            field_name=field_name,
            allowed=allowed,
            language=language,
        )
    ]
    if values["consensus"] and not consensus_allowed:
        warnings.append("consensus:no_multi_source_moderate_evidence")
    if limited_evidence_only:
        for field_name, value in values.items():
            if value and _STRONG_CONCLUSION_RE.search(value):
                warnings.append(f"{field_name}:stronger_than_available_evidence")
    withheld = ""
    if values["disagreements"] and not disagreements_allowed:
        warnings.append("disagreements:no_conflicting_evidence")
        withheld, values["disagreements"] = values["disagreements"], ""
    return SynthesisSection(
        title=title,
        synthesis=values["synthesis"],
        consensus=values["consensus"],
        disagreements=values["disagreements"],
        implications=values["implications"],
        source_ids=source_ids,
        claim_ids=claim_ids,
        validation_warnings=list(dict.fromkeys(warnings)),
        withheld_disagreements=withheld,
    )


def _overview_overlap_rows(
    overview: dict[str, str], sections: list[SynthesisSection]
) -> list[dict[str, Any]]:
    fields = [
        ("executive_summary", overview.get("executive_summary", "")),
        *[(f"theme:{section.title}", section.synthesis) for section in sections],
        ("cross_study_assessment", overview.get("cross_study_assessment", "")),
        ("conclusion", overview.get("conclusion", "")),
    ]
    overlaps: list[dict[str, Any]] = []
    for index, (left_name, left) in enumerate(fields):
        if not left:
            continue
        for right_name, right in fields[index + 1:]:
            if not right or not prose_overlaps(left, right):
                continue
            overlaps.append(
                {
                    "left": left_name,
                    "right": right_name,
                    "word_cosine": round(word_cosine(left, right), 3),
                    "trigram_jaccard": round(ngram_jaccard(left, right), 3),
                }
            )
    return overlaps


#: What a reader sees for a theme that has no usable draft at all. Plain language, no mention
#: of a model, and it says where the findings are: the audited claim register, which every
#: report format carries under a different appendix number, so no letter is named.
_THEME_WITHOUT_NARRATIVE = {
    True: (
        "Bu tema için özet anlatı oluşturulamadı; ilgili denetlenmiş bulgular rapor "
        "eklerindeki iddia kaydında yer alıyor."
    ),
    False: (
        "No narrative summary could be produced for this theme; the related audited findings "
        "are listed in the claim register in the report appendices."
    ),
}


def _fallback_section(
    title: str,
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    source_labels: dict[str, str],
    *,
    turkish: bool,
    claim_texts: dict[str, str] | None = None,
) -> SynthesisSection:
    sources: list[str] = []
    claim_ids: list[str] = []
    for claim in claims:
        for _, source in evidence_by_claim.get(str(claim.id), []):
            label = source_labels.get(str(source.id))
            if label and label not in sources:
                sources.append(label)
        claim_ids.append(str(claim.id))
    return SynthesisSection(
        title=title,
        synthesis=_THEME_WITHOUT_NARRATIVE[turkish],
        source_ids=sources,
        claim_ids=claim_ids,
        validation_warnings=["llm_synthesis_unavailable"],
    )


async def _draft_section(
    llm: LLMProvider,
    *,
    question: str,
    title: str,
    packet: str,
    source_ids: list[str],
    claim_ids: list[str],
    language: str,
    fallback: SynthesisSection,
    scope_context: str = "",
) -> tuple[SynthesisSection, bool, str]:
    if not packet:
        return fallback, False, "unavailable:no_evidence_packet"
    system = (
        "You are writing one evidence-grounded thematic section of a research report. "
        "Return one JSON object with keys synthesis, consensus, disagreements, implications. "
        "SYNTHESIS must integrate studies instead of listing them one by one. Use only facts "
        "in EVIDENCE_PACKET. Keep at least one supplied [Sxx] citation on every factual "
        "sentence, and write each citation in its own brackets: [S12] [S27], never "
        "[S12, S27]. Never "
        "invent a source, number, method, population, result, or URL. Treat status=qualified "
        "and evidence=limited|insufficient as tentative single-study findings. Write consensus "
        "only from claims marked consensus_eligible=true; otherwise leave it empty. Write "
        "disagreements only from claims marked disagreement_eligible=true, where the evidence "
        "itself conflicts; evidence that does not cover a point is a gap, not a disagreement, "
        "so otherwise leave it empty. Do not "
        "mention prompts, claims, auditing, retrieval, or an evidence packet. Preserve literal "
        "scope boundaries. "
        + _language_directive(language)
    )
    user = (
        f"RESEARCH_QUESTION:\n{question}\n\nTHEME:\n{title}\n\n"
        f"SCOPE_BOUNDARIES:\n{scope_context}\n\n"
        f"ALLOWED_SOURCE_IDS: {', '.join(source_ids)}\n\nEVIDENCE_PACKET:\n{packet}"
    )
    errors: list[str] = []
    for attempt in range(2):
        try:
            data = await llm.complete_json(system, user)
        except Exception as exc:  # noqa: BLE001 - one transport/decoder retry is intentional
            errors.append(type(exc).__name__)
            continue
        section = _advisory_section_from_data(
            data,
            title=title,
            source_ids=source_ids,
            claim_ids=claim_ids,
            language=language,
            consensus_allowed="consensus_eligible=true" in packet,
            limited_evidence_only=(
                "consensus_eligible=true" not in packet
                and not re.search(r"evidence=(?:strong|moderate)", packet)
            ),
            disagreements_allowed="disagreement_eligible=true" in packet,
        )
        if section is not None:
            note = "initial_visible" if attempt == 0 else "retry_visible"
            if section.validation_warnings:
                note += ":warnings"
            return section, True, note
        errors.append("unusable_response")
    failed = replace(
        fallback,
        validation_warnings=list(
            dict.fromkeys([*fallback.validation_warnings, *[f"llm:{error}" for error in errors]])
        ),
    )
    return failed, False, f"unavailable:{'+'.join(errors) or 'unknown'}"


#: Shown above a theme whose drafts all succeeded but could not be merged into one text.
_UNMERGED_THEME_NOTE = {
    True: (
        "Bu tema tek bir metinde birleştirilemedi; bulgular, kanıt paketlerinden üretilen "
        "bölümler hâlinde ve değiştirilmeden sunulmuştur."
    ),
    False: (
        "This theme could not be merged into a single text; its findings are presented "
        "unchanged, in the parts drafted from each evidence packet."
    ),
}


#: Shown above a theme some of whose evidence packets produced no draft.
_PARTIAL_THEME_NOTE = {
    True: (
        "Bu temanın bazı bulguları bu metne dahil edilemedi; bu bulgular yalnız rapor "
        "eklerindeki iddia kaydında yer alıyor."
    ),
    False: (
        "Some of this theme's findings could not be included in this text; they appear only "
        "in the claim register in the report appendices."
    ),
}


def _unmerged_section(
    title: str, drafts: list[SynthesisSection], *, turkish: bool
) -> SynthesisSection:
    """Every successful draft of a theme, shown as written, when the merge failed.

    Measured on run 01M289BAGG7CDC34HQF3GYK5ZZ: four of four drafts of "Bulgular ve
    karşılaştırmalı sonuçlar" succeeded, the merge ran into the output ceiling twice, and the
    report printed "LLM sentezi üretilemedi" over cited prose it already had. When some
    packets failed as well, `_partial_theme_section` puts its own note in front of this one.

    Fields are joined, never edited, so the verbatim-prose contract holds.
    """

    def joined(name: str) -> str:
        return "\n\n".join(
            value
            for draft in drafts
            if (value := str(getattr(draft, name) or "")).strip()
        )

    return SynthesisSection(
        title=title,
        synthesis=joined("synthesis"),
        consensus=joined("consensus"),
        disagreements=joined("disagreements"),
        implications=joined("implications"),
        source_ids=list(
            dict.fromkeys(source_id for draft in drafts for source_id in draft.source_ids)
        ),
        claim_ids=list(dict.fromkeys(claim_id for draft in drafts for claim_id in draft.claim_ids)),
        validation_warnings=list(
            dict.fromkeys(
                [
                    *(warning for draft in drafts for warning in draft.validation_warnings),
                    "llm_synthesis_unmerged",
                ]
            )
        ),
        reader_note=_UNMERGED_THEME_NOTE[turkish],
        withheld_disagreements=joined("withheld_disagreements"),
    )


def _partial_theme_section(
    section: SynthesisSection, pass_notes: list[str], *, turkish: bool
) -> SynthesisSection:
    """A theme built from the packets that drafted, saying that the rest are missing.

    One failed call out of sixteen used to discard the other fifteen drafts and leave the
    theme empty. Showing the surviving prose is only honest with the note: without it the
    reader would take part of a theme for all of it. The claims of the failed packets stay in
    the claim register, and the run status keeps reporting the theme as partial.
    """
    return replace(
        section,
        validation_warnings=list(
            dict.fromkeys(
                [
                    *section.validation_warnings,
                    "llm_synthesis_partial_packet_failure",
                    *[f"packet:{note}" for note in pass_notes if note.startswith("unavailable:")],
                ]
            )
        ),
        reader_note=f"{_PARTIAL_THEME_NOTE[turkish]} {section.reader_note}".strip(),
    )


def _pass_cards(passes: list[SynthesisSection], budget: int) -> tuple[str, int]:
    """Render one merge prompt's DRAFTS block, and count the fields that lost citations.

    The cards carry no number or name. They used to open with "PASS 1", "PASS 2", and a merge
    of run 01M2FGWHWKW1GCRXVWTC97B94H wrote "Pass 2 states the formula as ... while Pass 1
    ..." into the report -- two wordings of one formula presented as a disagreement.

    The floor is `_CONSOLIDATION_PASS_FLOOR` rather than the old 600: below it the card
    fields are too narrow to carry an `[Sxx]`, and a merge model that is shown no citation
    is forbidden by its own prompt from writing one. `_consolidation_fan_in` normally keeps
    the division above the floor, so this only binds on a context too small to honour it --
    and there, overflowing the budget by a little beats handing over unattributable prose.
    """
    per_pass = max(_CONSOLIDATION_PASS_FLOOR, budget // max(1, len(passes)))
    cards: list[str] = []
    ungrounded = 0
    for section in passes:
        rows: list[str] = []
        for label, value in (
            ("SYNTHESIS", section.synthesis),
            ("CONSENSUS", section.consensus),
            ("DISAGREEMENTS", section.disagreements),
            ("IMPLICATIONS", section.implications),
        ):
            excerpt, grounded = _grounded_excerpt(
                value, int(per_pass * _CARD_FIELD_WEIGHTS[label.lower()])
            )
            ungrounded += int(not grounded)
            rows.append(f"{label}: {excerpt}")
        cards.append("\n".join(rows))
    return "\n\n---\n\n".join(cards), ungrounded


async def _reduce_group(
    llm: LLMProvider,
    *,
    question: str,
    title: str,
    group: list[SynthesisSection],
    budget: int,
    language: str,
    scope_context: str,
) -> tuple[SynthesisSection | None, str, list[str], int]:
    """Merge one group of drafts, retrying only unusable/transport failures.

    A node's `source_ids` is its own group's union, not the theme's: it was only ever shown
    its group's cards, so a label from another group appearing in its prose really would be
    invented, and `unknown_citations` should say so.
    """
    allowed_ids = list(
        dict.fromkeys(source_id for section in group for source_id in section.source_ids)
    )
    claim_ids = list(
        dict.fromkeys(claim_id for section in group for claim_id in section.claim_ids)
    )
    cards, ungrounded = _pass_cards(group, budget)
    errors: list[str] = []
    for attempt in range(2):
        try:
            data = await llm.complete_json(
                "You are merging several partial drafts of ONE thematic section of a research "
                "report into a single integrated section. Return one JSON object with keys "
                "synthesis, consensus, disagreements, implications. The drafts below, separated "
                "by ---, were cut from one theme only so that each fit the context window; they "
                "are not studies. Combine them into one argument rather than reporting them in "
                "sequence. Disagreements are between the cited studies, never between the "
                "drafts: carry over only disagreements the drafts already state, and add none. "
                "Use only facts present in the drafts. Never invent a source, number, method, "
                "population, result, or URL, and never add a citation that is not already in "
                "the drafts. Keep at least one supplied [Sxx] citation on every factual "
                "sentence, and write each citation in its own brackets: [S12] [S27], never "
                "[S12, S27]. Do not mention drafts, parts, passes, prompts, or an evidence "
                "packet. " + _language_directive(language),
                f"RESEARCH_QUESTION:\n{question}\n\nTHEME:\n{title}\n\n"
                f"SCOPE_BOUNDARIES:\n{scope_context}\n\n"
                f"ALLOWED_SOURCE_IDS: {', '.join(allowed_ids)}\n\nDRAFTS:\n{cards}",
            )
        except Exception as exc:  # noqa: BLE001 - one transport retry is intentional
            errors.append(type(exc).__name__)
            continue
        section = _advisory_section_from_data(
            data,
            title=title,
            source_ids=allowed_ids,
            claim_ids=claim_ids,
            language=language,
            consensus_allowed=any(
                item.consensus
                and "consensus:no_multi_source_moderate_evidence"
                not in item.validation_warnings
                for item in group
            ),
            # The drafts were gated on the evidence already; a merge may keep what they
            # state, and has nothing to ground a disagreement of its own on.
            disagreements_allowed=any(item.disagreements for item in group),
        )
        if section is None:
            errors.append("unusable_response")
            continue
        warnings = list(
            dict.fromkeys(
                [
                    *(warning for item in group for warning in item.validation_warnings),
                    *section.validation_warnings,
                ]
            )
        )
        withheld = "\n\n".join(
            value
            for value in (
                *(item.withheld_disagreements for item in group),
                section.withheld_disagreements,
            )
            if value
        )
        return (
            replace(section, validation_warnings=warnings, withheld_disagreements=withheld),
            "initial" if attempt == 0 else "retry",
            errors,
            ungrounded,
        )
    return None, "unavailable", errors, ungrounded


async def _consolidate_passes(
    llm: LLMProvider,
    *,
    question: str,
    title: str,
    passes: list[SynthesisSection],
    language: str,
    turkish: bool,
    scope_context: str = "",
) -> tuple[SynthesisSection, bool, str, dict[str, Any]]:
    """Integrate multiple model passes, reducing in rounds when there are too many.

    One prompt budget used to be divided by however many drafts a theme produced, with only
    a 600-character floor under it. Measured on run 01M25XYS6ETQVXMPY24HXVKNXG: a 17-packet
    theme drove each card field to 90 characters, the citations were cut off, and four of
    the report's five sections reached the reader carrying no `[Sxx]` at all. The one theme
    that stayed under the fan-in cited every source it was offered.

    So the division is bounded instead of floored: at most `_consolidation_fan_in(budget)`
    drafts per merge, reduced round by round until one section remains. That makes
    "every pass is shown its citations" an invariant of the tree rather than a property of
    how big the theme happened to be.
    """
    allowed_ids = list(
        dict.fromkeys(source_id for section in passes for source_id in section.source_ids)
    )
    claim_ids = list(
        dict.fromkeys(claim_id for section in passes for claim_id in section.claim_ids)
    )
    budget = max(
        1500,
        _prompt_char_budget(llm)
        - len(question)
        - len(title)
        - len(scope_context)
        - (len(allowed_ids) * 8)
        - 500,
    )
    # Sized once from the whole theme's label list, so every level shares one fan-in and the
    # shape of the tree is predictable. Intermediate nodes carry shorter lists, which only
    # makes the estimate conservative.
    fan_in = _consolidation_fan_in(budget)
    topology: dict[str, Any] = {
        "fan_in": fan_in,
        "rounds": 0,
        "group_sizes": [],
        "calls": 0,
        "pass_cards_ungrounded": 0,
        "trace": "",
    }
    unavailable = SynthesisSection(
        title=title,
        synthesis=(
            "LLM sentezi üretilemedi; kanıt kayıtları denetim eklerinde korunmuştur."
            if turkish
            else "LLM synthesis could not be produced; evidence records remain in the audit appendices."
        ),
        source_ids=allowed_ids,
        claim_ids=claim_ids,
    )

    current = list(passes)
    round_traces: list[str] = []
    any_retry = False
    while True:
        sizes = _balanced_chunks(len(current), fan_in)
        topology["rounds"] += 1
        topology["group_sizes"].append(sizes)
        merged: list[SynthesisSection] = []
        notes: list[str] = []
        offset = 0
        for size in sizes:
            group = current[offset : offset + size]
            offset += size
            if size == 1:
                # An odd count at a small fan-in leaves one draft over. Merging it with
                # itself would spend a call to rewrite prose that is already final, and
                # every rewrite is another chance to drop a citation. Carry it instead.
                merged.append(group[0])
                notes.append("1=carried")
                continue
            section, note, errors, ungrounded = await _reduce_group(
                llm,
                question=question,
                title=title,
                group=group,
                budget=budget,
                language=language,
                scope_context=scope_context,
            )
            topology["calls"] += 1
            topology["pass_cards_ungrounded"] += ungrounded
            notes.append(f"{size}={note}")
            if section is None:
                # A failure at any level fails the merge, and the caller shows every draft
                # unmerged. Carrying only the surviving branches forward would publish part
                # of the theme's merge as if it were the whole.
                round_traces.append("+".join(notes))
                topology["trace"] = "|".join(
                    f"r{index}:{trace}" for index, trace in enumerate(round_traces, 1)
                )
                return (
                    replace(
                        unavailable,
                        validation_warnings=[
                            "llm_synthesis_unavailable",
                            *[f"consolidation:{error}" for error in errors],
                        ],
                    ),
                    False,
                    f"consolidation_unavailable:{'+'.join(errors) or 'unknown'}",
                    topology,
                )
            any_retry = any_retry or note == "retry"
            merged.append(section)
        round_traces.append("+".join(notes))
        current = merged
        if len(current) == 1:
            break

    topology["trace"] = "|".join(
        f"r{index}:{trace}" for index, trace in enumerate(round_traces, 1)
    )
    # The theme's full union is forced onto the root: `source_ids` means "offered to the
    # model" (see SynthesisSection), and every packet's sources were offered even where a
    # branch cited none of them. Warnings reach the root transitively, each node having
    # merged its group's.
    root = replace(current[0], source_ids=allowed_ids, claim_ids=claim_ids)
    note = "consolidated_retry_visible" if any_retry else "consolidated_visible"
    if topology["rounds"] > 1:
        note += f":r{topology['rounds']}"
    if root.validation_warnings:
        note += ":warnings"
    return root, True, note, topology


#: What `_draft_overview` puts in a field it could not produce. The build step compares
#: against it to find the fields it has to compile from the themes instead; it is never
#: meant to reach a reader.
_OVERVIEW_UNAVAILABLE = {
    True: "LLM sentezi üretilemedi; kanıt kayıtları denetim eklerinde korunmuştur.",
    False: (
        "LLM synthesis could not be produced; evidence records remain in the audit appendices."
    ),
}
#: Shown in place of a summary when there is no model prose anywhere to compile one from.
_REPORT_WITHOUT_SUMMARY = {
    True: (
        "Bu rapor için özet oluşturulamadı; ilgili denetlenmiş bulgular rapor eklerindeki "
        "iddia kaydında yer alıyor."
    ),
    False: (
        "No summary could be produced for this report; the related audited findings are "
        "listed in the claim register in the report appendices."
    ),
}
#: Heads every overview field compiled from the themes, so the reader knows it is a selection
#: of the theme sections' own sentences and not an integration written for this slot.
_COMPILED_FROM_THEMES = {
    True: "Bu bölüm, tema bölümlerindeki bulgulardan derlenmiştir.",
    False: "This section is compiled from the findings in the theme sections.",
}


def _compiled_overview(sections: list[SynthesisSection], *, turkish: bool) -> dict[str, str]:
    """Overview fields assembled from the themes' own sentences, for when the layer failed.

    Each field takes the first complete sentence of one field of every theme that has model
    prose -- synthesis for the summary, implications for the conclusion, disagreements for
    the uncertainty -- word for word, citations included. Nothing reaches the reader that a
    theme section did not already say, and the label says the text is a compilation.

    Measured on run 01M289BAGG7CDC34HQF3GYK5ZZ: the overview call ran into the output ceiling
    twice, and the executive summary, conclusion and uncertainty all read "LLM sentezi
    üretilemedi" -- the first thing in the report -- over four themes of cited prose.
    """
    written = [
        section
        for section in sections
        if "llm_synthesis_unavailable" not in section.validation_warnings
        and str(section.synthesis or "").strip()
    ]

    def first_sentences(name: str) -> str:
        picked: list[str] = []
        for section in written:
            value = str(getattr(section, name) or "")
            if not value.strip():
                continue
            sentences = _sentences(value)
            picked.append(sentences[0] if sentences else " ".join(value.split()))
        return " ".join(picked)

    def labelled(text: str) -> str:
        return f"{_COMPILED_FROM_THEMES[turkish]}\n\n{text}" if text else ""

    return {
        "executive_summary": labelled(first_sentences("synthesis"))
        or _REPORT_WITHOUT_SUMMARY[turkish],
        "conclusion": labelled(first_sentences("implications")),
        "uncertainty": labelled(first_sentences("disagreements")),
    }


async def _draft_overview(
    llm: LLMProvider,
    *,
    question: str,
    sections: list[SynthesisSection],
    language: str,
    turkish: bool,
    scope_context: str = "",
) -> tuple[dict[str, str], bool, str, dict[str, list[str]]]:
    allowed = {
        f"[{source_id}]"
        for section in sections
        for source_id in section.source_ids
    }
    unavailable = _OVERVIEW_UNAVAILABLE[turkish]
    digest_budget = max(
        3000,
        _prompt_char_budget(llm) - len(question) - (len(allowed) * 8) - 500,
    )
    section_digest, digest_ungrounded = _overview_digest(sections, digest_budget)
    if not section_digest or not allowed:
        values = {
            "executive_summary": unavailable,
            "cross_study_assessment": "",
            "conclusion": unavailable,
            "uncertainty": unavailable,
        }
        return values, False, "unavailable:no_grounded_sections", {
            "overview": ["llm_synthesis_unavailable"]
        }

    system = (
            "Write the integrative layer of a research report as one JSON object with keys "
            "executive_summary, cross_study_assessment, conclusion, uncertainty. Synthesize themes; "
            "do not repeat a source-by-source inventory. Preserve the supplied [Sxx] citations, "
            "each in its own brackets ([S12] [S27], never [S12, S27]), and "
            "attach citations to factual statements. Use only the section drafts below. Never add "
            "new facts, numbers, sources, URLs, or platform/retrieval metrics. Make uncertainty "
            "specific to comparability, study design, validation, and evidence gaps. "
            "Each field has a distinct role and must not reuse sentences or close paraphrases from "
            "the theme cards or another field. Preserve the original scope boundaries; never replace "
            "a time, condition, population, intervention, or outcome with a neighbouring concept. "
            + _language_directive(language)
    )
    user = (
        f"RESEARCH_QUESTION:\n{question}\n\nALLOWED_SOURCE_IDS: "
        f"{', '.join(sorted(allowed))}\n\nSCOPE_BOUNDARIES:\n{scope_context}\n\n"
        f"SECTION_DRAFTS:\n{section_digest}"
    )
    errors: list[str] = []
    for attempt in range(2):
        try:
            data = await llm.complete_json(system, user)
        except Exception as exc:  # noqa: BLE001 - one transport/decoder retry is intentional
            errors.append(type(exc).__name__)
            continue
        if not isinstance(data, dict) or not any(
            _reader_text(data.get(key))
            for key in _OVERVIEW_FIELD_LIMITS
        ):
            errors.append("unusable_response")
            continue
        values: dict[str, str] = {}
        warnings: dict[str, list[str]] = {}
        complete = True
        for key in _OVERVIEW_FIELD_LIMITS:
            value = _reader_text(data.get(key))
            complete = complete and bool(value)
            values[key] = value or unavailable
            field_warnings = _text_warnings(
                value,
                field_name=key,
                allowed=allowed,
                language=language,
            )
            if field_warnings:
                warnings[key] = field_warnings
        for overlap in _overview_overlap_rows(values, sections):
            if overlap["left"].startswith("theme:") and overlap["right"].startswith("theme:"):
                continue
            warnings.setdefault("overlap", []).append(
                f"{overlap['left']}:overlap_with_{overlap['right']}"
            )
        note = "initial_visible" if attempt == 0 else "retry_visible"
        # Before `:warnings`, so the suffix that consumers already look for stays last.
        # A non-zero count means the digest handed this layer prose whose citations the
        # budget had cut off -- the overview can then only be as grounded as what it saw.
        if digest_ungrounded:
            note += f":ungrounded={digest_ungrounded}"
        if warnings:
            note += ":warnings"
        return values, complete, note, warnings
    values = {
        "executive_summary": unavailable,
        "cross_study_assessment": "",
        "conclusion": unavailable,
        "uncertainty": unavailable,
    }
    return values, False, f"unavailable:{'+'.join(errors) or 'unknown'}", {
        "overview": ["llm_synthesis_unavailable", *[f"llm:{error}" for error in errors]]
    }


async def build_synthesis_package(
    *,
    llm: LLMProvider,
    question: str,
    language: str,
    sources: list[Any],
    reportable_claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    sub_questions: list[str] | None = None,
    sub_question_titles: list[str] | None = None,
    claim_texts: dict[str, str] | None = None,
    display_question: str = "",
    coverage: dict[str, Any] | None = None,
) -> SynthesisPackage:
    """Create a bounded synthesis package whose model prose is never rewritten."""
    turkish = language.lower().startswith("tr")
    primary_source_ids = {
        str(source.id)
        for source in sources
        if str(_metadata(source).get("research_scope_role") or "primary_in_scope")
        == "primary_in_scope"
    }
    supporting_source_ids = {
        str(source.id)
        for source in sources
        if str(_metadata(source).get("research_scope_role") or "primary_in_scope")
        == "supporting_benchmark"
    }
    eligible_evidence: dict[str, list[tuple[Any, Any]]] = {}
    eligible_claims: list[Any] = []
    for claim in reportable_claims:
        claim_id = str(claim.id)
        claim_text = str(getattr(claim, "text", ""))
        supporting_allowed = bool(_SUPPORTING_TOPIC_RE.search(claim_text))
        links = [
            (link, source)
            for link, source in evidence_by_claim.get(claim_id, [])
            if str(source.id) in primary_source_ids
            or (supporting_allowed and str(source.id) in supporting_source_ids)
        ]
        if links:
            eligible_claims.append(claim)
            eligible_evidence[claim_id] = links
    unique_claims, synthesis_evidence, merged_claim_ids = _deduplicate_report_claims(
        eligible_claims, eligible_evidence
    )
    report_mode, mode_reasons = _report_mode(unique_claims, synthesis_evidence, coverage)
    visible_question = display_question.strip() or question
    anchors = _scope_anchors(visible_question)
    scope_context = (
        f"ORIGINAL_READER_QUESTION: {visible_question}\n"
        f"LITERAL_SCOPE_ANCHORS: {', '.join(anchors) if anchors else '(none)'}"
    )
    source_labels = {str(source.id): f"S{index:02d}" for index, source in enumerate(sources, 1)}
    profiles = build_study_profiles(
        sources,
        unique_claims,
        synthesis_evidence,
        turkish=turkish,
    )
    theme_plan = _plan_themes(
        unique_claims,
        sub_questions or [],
        synthesis_evidence,
        display_sub_questions=sub_question_titles,
        turkish=turkish,
        report_mode=report_mode,
    )
    sections: list[SynthesisSection] = []
    llm_successes = 0
    generation_diagnostics: dict[str, str] = {}
    theme_coverage: list[dict[str, Any]] = []
    claims_without_evidence: list[str] = []
    for index, (title, theme_claims) in enumerate(theme_plan, 1):
        packets, unbacked = _evidence_packets(
            theme_claims,
            synthesis_evidence,
            source_labels,
            char_budget=_section_packet_budget(
                llm, question=question, title=title, scope_context=scope_context
            ),
        )
        claims_without_evidence.extend(unbacked)
        fallback = _fallback_section(
            title,
            theme_claims,
            synthesis_evidence,
            source_labels,
            turkish=turkish,
            claim_texts=claim_texts,
        )
        drafts: list[SynthesisSection] = []
        pass_notes: list[str] = []
        drafted_claim_ids: list[str] = []
        # Stays None for a theme that never reached consolidation -- one packet, or a packet
        # failure. Absent rather than zeroed, so "no reduce happened" and "a reduce happened
        # in one round" stay distinguishable in the record.
        reduce_topology: dict[str, Any] | None = None
        attempted_packets = packets or [EvidencePacket("", [], [])]
        for packet in attempted_packets:
            drafted, drafted_ok, note = await _draft_section(
                llm,
                question=question,
                title=title,
                packet=packet.text,
                source_ids=packet.source_ids,
                claim_ids=packet.claim_ids,
                language=language,
                fallback=fallback,
                scope_context=scope_context,
            )
            pass_notes.append(note)
            if drafted_ok:
                drafts.append(drafted)
                drafted_claim_ids.extend(packet.claim_ids)
        if not drafts:
            section, succeeded = fallback, False
            diagnostic = f"all_passes_unavailable:{'+'.join(pass_notes)}"
        else:
            if len(drafts) == 1:
                section, succeeded, diagnostic = drafts[0], True, "+".join(pass_notes)
            else:
                section, succeeded, note, reduce_topology = await _consolidate_passes(
                    llm,
                    question=question,
                    title=title,
                    passes=drafts,
                    language=language,
                    turkish=turkish,
                    scope_context=scope_context,
                )
                diagnostic = f"{note}({'+'.join(pass_notes)})"
                if not succeeded:
                    # The merge failed. Show the drafts rather than a failure line -- see
                    # `_unmerged_section`. `succeeded` stays False: the integration layer
                    # did fail, and the run status keeps saying so.
                    section = _unmerged_section(title, drafts, turkish=turkish)
                    diagnostic = f"unmerged_drafts_visible:{diagnostic}"
            if len(drafts) != len(attempted_packets):
                section = _partial_theme_section(section, pass_notes, turkish=turkish)
                succeeded = False
                diagnostic = f"partial_packet_failure:{diagnostic}"
        if any(str(getattr(claim, "status", "")) == "qualified" for claim in theme_claims):
            section = replace(
                section,
                validation_warnings=list(
                    dict.fromkeys(
                        [*section.validation_warnings, "qualified:single_study_findings"]
                    )
                ),
            )
        theme_coverage.append(
            {
                "theme": title,
                "claims_total": len(theme_claims),
                "claims_offered": sum(len(packet.claim_ids) for packet in packets),
                # Every draft that came out is shown -- merged, unmerged, or under the
                # partial note -- and a failed packet's claims never are.
                "claims_shown": len(set(drafted_claim_ids)),
                "claims_without_evidence": len(unbacked),
                "passes": len(packets),
                # The variable that decides whether a draft cites at all. Derivable from the
                # two numbers above, but not derivable while the run is still going, which is
                # exactly when it is worth knowing.
                "claims_per_packet": round(
                    sum(len(packet.claim_ids) for packet in packets) / max(1, len(packets)), 1
                ),
                "passes_drafted": len(drafts),
                "passes_used": len(drafts),
                # `passes*` above stay leaf counts; the reduce record describes the tree that
                # merged them. `pass_cards_ungrounded > 0` means a card field still lost its
                # citations, which is the signal that the fan-in floor is mis-derived.
                **({"reduce": reduce_topology} if reduce_topology else {}),
            }
        )
        # The diagnostic travels with the section as well as in the run-level map. Reading
        # it back by `theme_{index}` means trusting that these two lists stay aligned, and
        # the citation record needs it per section to tell a discarded draft apart from a
        # source the model was offered and passed over.
        sections.append(replace(section, generation_note=diagnostic))
        llm_successes += int(succeeded)
        generation_diagnostics[f"theme_{index}"] = diagnostic
        # A separate key: `theme_{index}` has readers that parse its shape, and the reduce
        # trace is a different question ("how was it merged", not "did it come out").
        if reduce_topology:
            generation_diagnostics[f"theme_{index}_reduce"] = reduce_topology["trace"]
    # Overlap remains observable below, but it no longer deletes model-written sections.
    collapsed_sections: list[dict[str, Any]] = []
    if report_mode == "standard" and len(sections) < 2:
        report_mode = "compact"
        mode_reasons.append("fewer_than_2_viable_themes")

    compiled_fields: list[str] = []
    if report_mode == "compact":
        if not sections:
            compact_summary = ""
        elif "llm_synthesis_unavailable" in sections[0].validation_warnings:
            # The one theme has no model prose, so there is no summary to show; its own
            # theme-level note ("for this theme") would read wrong in the summary slot.
            compact_summary = _REPORT_WITHOUT_SUMMARY[turkish]
        else:
            compact_summary = sections[0].synthesis
        overview = {
            "executive_summary": compact_summary,
            "cross_study_assessment": "",
            "conclusion": "",
            "uncertainty": sections[0].disagreements if sections else "",
        }
        overview_succeeded = bool(sections) and llm_successes == len(sections)
        overview_diagnostic = "compact_uses_visible_theme"
        overview_warnings = (
            {"executive_summary": list(sections[0].validation_warnings)}
            if sections and sections[0].validation_warnings
            else {}
        )
    else:
        overview, overview_succeeded, overview_diagnostic, overview_warnings = await _draft_overview(
            llm,
            question=question,
            sections=sections,
            language=language,
            turkish=turkish,
            scope_context=scope_context,
        )
        # A field the overview layer could not produce is compiled from the themes' own
        # sentences rather than shown as a failure line (see `_compiled_overview`). This is
        # not the section-excerpt replacement ruled out below: that would overwrite model
        # prose because it overlapped; here there is no model prose in the field to keep.
        compiled_fields = [
            key
            for key in ("executive_summary", "conclusion", "uncertainty")
            if not str(overview.get(key) or "").strip()
            or overview.get(key) == _OVERVIEW_UNAVAILABLE[turkish]
        ]
        if compiled_fields:
            compiled = _compiled_overview(sections, turkish=turkish)
            overview = {**overview, **{key: compiled[key] for key in compiled_fields}}
            overview_diagnostic = f"{overview_diagnostic}:compiled={'+'.join(compiled_fields)}"
            overview_warnings.setdefault("overview", []).append("overview:compiled_from_themes")
    if any(str(getattr(claim, "status", "")) == "qualified" for claim in unique_claims):
        overview_warnings.setdefault("executive_summary", []).append(
            "qualified:single_study_findings"
        )
        overview_warnings["executive_summary"] = list(
            dict.fromkeys(overview_warnings["executive_summary"])
        )
    # Compiled fields are theme sentences by construction; comparing them with the themes would
    # report the compilation itself as duplicated prose.
    overlap_rows = (
        []
        if report_mode == "compact"
        else _overview_overlap_rows(
            {key: ("" if key in compiled_fields else value) for key, value in overview.items()},
            sections,
        )
    )
    # Duplicate or overlapping prose is diagnostic only. It must never trigger a rewrite,
    # deletion, compact-mode transition, or replacement with section excerpts.
    relevance_scores = [_question_relevance(claim) for claim in unique_claims]
    maximum_question_relevance = max(relevance_scores, default=0.0)
    contributing_sources = _contributing_sources(unique_claims, synthesis_evidence)
    primary_synthesis_evidence = {
        claim_id: [
            (link, source)
            for link, source in links
            if str(source.id) in primary_source_ids
        ]
        for claim_id, links in synthesis_evidence.items()
    }
    primary_contributing_sources = _contributing_sources(
        unique_claims, primary_synthesis_evidence
    )
    independent_contributors = _independent_contributors(
        unique_claims, primary_synthesis_evidence
    )
    questions = [item for item in (sub_questions or []) if item.strip()]
    covered_questions = sum(
        any(
            len(_words(str(getattr(claim, "text", ""))) & _words(item)) >= 2
            for claim in unique_claims
        )
        for item in questions
    )
    sub_question_coverage = covered_questions / len(questions) if questions else 1.0
    answerability_status: Literal["answerable", "limited", "insufficient"] = "answerable"
    answerability_reasons: list[str] = []
    if not unique_claims or not primary_contributing_sources:
        answerability_status = "insufficient"
        answerability_reasons.append("no_reportable_in_scope_evidence")
    else:
        if len(independent_contributors) < 2:
            answerability_reasons.append(
                "fewer_than_2_independent_in_scope_sources"
            )
        if sub_question_coverage < 0.5:
            answerability_reasons.append("sub_question_coverage_below_half")
        if maximum_question_relevance < _DIRECT_ANSWER_RELEVANCE_THRESHOLD:
            answerability_reasons.append("low_question_relevance")
        if answerability_reasons:
            answerability_status = "limited"
    generation_diagnostics["overview"] = overview_diagnostic
    generation_diagnostics["report_mode"] = report_mode
    # Compact rendering shows only `sections[0]`; theme planning must therefore have
    # selected one integrated model call, never a deterministic merge of several drafts.
    assert not (report_mode == "compact" and len(sections) > 1), (
        "compact reports must carry a single integrated section"
    )
    validation_warnings = {
        **{
            f"theme_{index}": list(section.validation_warnings)
            for index, section in enumerate(sections, 1)
            if section.validation_warnings
        },
        **overview_warnings,
    }
    all_model_layers_succeeded = (
        bool(sections)
        and llm_successes == len(sections)
        and overview_succeeded
    )
    # "failed" means the reader has no model prose at all. A theme shown unmerged or under the
    # partial note is not a success, but it is not nothing either.
    themes_with_prose = sum(
        1 for section in sections if "llm_synthesis_unavailable" not in section.validation_warnings
    )
    if not sections or (themes_with_prose == 0 and not overview_succeeded):
        generation_status = "failed"
    elif not all_model_layers_succeeded:
        generation_status = "partial"
    elif validation_warnings:
        generation_status = "complete_with_warnings"
    else:
        generation_status = "complete"
    return SynthesisPackage(
        executive_summary=overview["executive_summary"],
        sections=sections,
        cross_study_assessment=overview["cross_study_assessment"],
        conclusion=overview["conclusion"],
        uncertainty=overview["uncertainty"],
        study_profiles=profiles,
        generated_by_llm=all_model_layers_succeeded,
        generation_status=generation_status,
        generation_diagnostics=generation_diagnostics,
        validation_warnings=validation_warnings,
        report_mode=report_mode,
        answerability_status=answerability_status,
        quality_diagnostics={
            "mode_reasons": list(dict.fromkeys(mode_reasons)),
            "input_claim_count": len(reportable_claims),
            "scope_eligible_claim_count": len(eligible_claims),
            "unique_claim_count": len(unique_claims),
            "contributing_source_count": len(contributing_sources),
            "merged_claim_ids": merged_claim_ids,
            "collapsed_sections": collapsed_sections,
            "field_overlaps": overlap_rows,
            "scope_anchors": anchors,
            # Layers lost to the output ceiling rather than to anything about the evidence.
            # A non-zero count means the packets are still asking for more prose than the
            # model has room to write, and no retry can recover it at temperature 0.
            "output_truncated_layers": sum(
                1 for note in generation_diagnostics.values()
                if "OutputTruncated" in str(note)
            ),
            # What the model was actually shown. "Every claim reached the prompt" is a
            # claim about the run, so the run has to carry the numbers that settle it:
            # `evidence_claims_shown` must equal `unique_claim_count` minus the claims
            # nothing citable backed.
            "theme_coverage": theme_coverage,
            "evidence_claims_shown": sum(
                int(row["claims_shown"]) for row in theme_coverage
            ),
            "claims_without_evidence": len(claims_without_evidence),
            "answerability": {
                "status": answerability_status,
                "threshold": _DIRECT_ANSWER_RELEVANCE_THRESHOLD,
                "maximum_question_relevance": round(maximum_question_relevance, 4),
                "in_scope_contributing_sources": len(primary_contributing_sources),
                "independent_in_scope_contributors": len(independent_contributors),
                "sub_question_coverage": round(sub_question_coverage, 4),
                "reason_codes": answerability_reasons,
            },
        },
    )
