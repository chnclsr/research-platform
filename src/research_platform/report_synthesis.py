"""Evidence-grounded, multi-stage report synthesis for small local models.

The research worker already extracts and audits atomic claims.  This module
turns those atoms into a readable report without asking a local model to hold
the entire corpus in one prompt.  Each thematic section receives a bounded
evidence packet and may cite only stable source labels such as ``[S03]``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

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
    # rewritten or discarded because one of these diagnostics fired.
    validation_warnings: list[str] = field(default_factory=list)


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
        parts: list[str] = []
        for section in self.sections:
            if section.validation_warnings:
                parts.append(
                    "> ⚠ Sentez doğrulama uyarısı: "
                    + ", ".join(section.validation_warnings)
                )
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


_TOKEN_RE = re.compile(r"\[S\d{2,3}\]")
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


def citation_counts(*texts: str) -> Counter[str]:
    """How many times each `Sxx` label is cited across the given prose.

    The counting half of `cited_labels`, kept separate because the report needs both: which
    sources a section stands on, and how heavily the document leans on each one.
    """
    counts: Counter[str] = Counter()
    for text in texts:
        for token in _TOKEN_RE.findall(text or ""):
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
    tail_citations = _TOKEN_RE.findall(tail)
    if tail_citations and tail.endswith(tail_citations[-1]):
        sentences.append(tail)
    return sentences


def _ground_sentence(sentence: str, source_text: str) -> str:
    """Keep a selected fallback sentence tied to the citations of its source field."""
    if _TOKEN_RE.search(sentence):
        return sentence
    citations = list(dict.fromkeys(_TOKEN_RE.findall(source_text)))[:3]
    if not citations:
        return sentence
    punctuation = sentence[-1] if sentence[-1:] in ".!?" else "."
    body = sentence[:-1].rstrip() if sentence[-1:] in ".!?" else sentence.rstrip()
    return f"{body} {' '.join(citations)}{punctuation}"


def _bounded_grounded_join(values: list[str], max_chars: int) -> str:
    """Join only complete, grounded sentences without slicing a visible report field."""
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


def _prompt_excerpt(value: str, max_chars: int) -> str:
    """Make a compact internal-only excerpt, preferring complete sentences."""
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    complete = _bounded_grounded_join([cleaned], max_chars)
    if complete:
        return complete
    boundary = cleaned.rfind(" ", 0, max_chars)
    return cleaned[: boundary if boundary > 0 else max_chars].rstrip()


def _prompt_char_budget(llm: LLMProvider) -> int:
    """Reserve output and fixed-prompt room before filling a prompt with evidence.

    Measured on a live run, this content runs about 2.9 characters per token; the two used
    here is deliberately below that, because being wrong in this direction only wastes a
    little context and being wrong in the other truncates a section.
    """
    settings = getattr(llm, "settings", None)
    context_tokens = int(getattr(settings, "llm_context_tokens", 8192))
    output_tokens = int(getattr(settings, "llm_max_output_tokens", 2048))
    available_tokens = max(2048, context_tokens - output_tokens - 1536)
    return max(6000, min(24000, available_tokens * 2))


def _section_packet_budget(
    llm: LLMProvider, *, question: str, title: str, scope_context: str
) -> int:
    """The room a theme's evidence may occupy once the rest of the prompt is paid for.

    The system prompt sits inside the fixed reserve `_prompt_char_budget` already holds
    back; what is subtracted here is the part that varies per run and per theme, plus room
    for the `[Sxx]` allow-list.
    """
    return max(
        2000,
        _prompt_char_budget(llm) - len(question) - len(title) - len(scope_context) - 600,
    )


def _overview_digest(sections: list[SynthesisSection], max_chars: int) -> str:
    """Create balanced theme cards instead of truncating one monolithic digest."""
    if not sections:
        return ""
    per_theme = max(900, max_chars // len(sections))
    cards: list[str] = []
    for section in sections:
        synthesis_budget = max(360, int(per_theme * 0.46))
        secondary_budget = max(140, int(per_theme * 0.16))
        rows = [
            f"THEME: {_prompt_excerpt(section.title, 240)}",
            f"SYNTHESIS: {_prompt_excerpt(section.synthesis, synthesis_budget)}",
            f"CONSENSUS: {_prompt_excerpt(section.consensus, secondary_budget)}",
            f"DISAGREEMENTS: {_prompt_excerpt(section.disagreements, secondary_budget)}",
            f"IMPLICATIONS: {_prompt_excerpt(section.implications, secondary_budget)}",
        ]
        cards.append("\n".join(rows))
    digest = "\n\n".join(cards)
    if len(digest) <= max_chars:
        return digest
    boundary = digest.rfind("\n\n", 0, max_chars)
    return digest[: boundary if boundary > 0 else max_chars].rstrip()


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
    for link, source in evidence_by_claim.get(str(claim.id), []):
        source_label = source_labels.get(str(source.id))
        quote = " ".join(str(getattr(link, "quote", "")).split())[:650]
        if not source_label or not quote:
            continue
        direction = str(getattr(link, "direction", "supports"))
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
    body = (
        f"status={getattr(claim, 'status', 'qualified')} | {grade_field}"
        f"consensus_eligible={'true' if consensus_eligible else 'false'} | "
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
    citations = set(_TOKEN_RE.findall(value))
    unknown = sorted(citations - allowed)
    if unknown:
        warnings.append(f"{field_name}:unknown_citations:{','.join(unknown)}")
    malformed = sorted(
        {
            match.group(0)
            for match in _BRACKET_RE.finditer(value)
            if "S" in match.group(1).upper() and not _TOKEN_RE.fullmatch(match.group(0))
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
) -> SynthesisSection | None:
    """Accept usable LLM prose and report defects without changing the prose."""
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
    return SynthesisSection(
        title=title,
        synthesis=values["synthesis"],
        consensus=values["consensus"],
        disagreements=values["disagreements"],
        implications=values["implications"],
        source_ids=source_ids,
        claim_ids=claim_ids,
        validation_warnings=list(dict.fromkeys(warnings)),
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


def _merge_sections_into_compact_answer(
    sections: list[SynthesisSection],
    *,
    turkish: bool,
    title: str = "",
    note: str = "merged_for_compact",
) -> list[SynthesisSection]:
    """Fold several drafted sections into one, keeping every word and every id.

    Compact rendering drops `sections` from the reader-visible surface, so a mode change
    that leaves several drafted themes behind deletes them from the report. Merging first
    keeps every theme's prose and provenance in the one section that still gets rendered.

    `title` and `note` also make this the safe landing for a theme drafted over several
    evidence packets whose consolidation call failed: concatenating the passes reads worse
    than one integrated section, but it loses nothing, which is the property that matters
    when the alternative is discarding drafted prose.
    """
    if len(sections) <= 1:
        return sections
    body = " ".join(
        value
        for section in sections
        for value in (
            section.synthesis,
            section.consensus,
            section.disagreements,
            section.implications,
        )
        if value
    ).strip()
    return [
        SynthesisSection(
            title=title or ("Kanıt özeti" if turkish else "Evidence summary"),
            synthesis=body,
            source_ids=list(
                dict.fromkeys(
                    source_id
                    for section in sections
                    for source_id in section.source_ids
                )
            ),
            claim_ids=list(
                dict.fromkeys(
                    claim_id for section in sections for claim_id in section.claim_ids
                )
            ),
            generation_note=";".join(
                dict.fromkeys(
                    [
                        *(
                            section.generation_note
                            for section in sections
                            if section.generation_note
                        ),
                        note,
                    ]
                )
            ),
            validation_warnings=list(
                dict.fromkeys(
                    warning
                    for section in sections
                    for warning in section.validation_warnings
                )
            ),
        )
    ]


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
        synthesis=(
            "LLM sentezi üretilemedi; kanıt kayıtları denetim eklerinde korunmuştur."
            if turkish
            else "LLM synthesis could not be produced; evidence records remain in the audit appendices."
        ),
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
        "in EVIDENCE_PACKET and attach supplied [Sxx] citations to factual sentences. Never "
        "invent a source, number, method, population, result, or URL. Treat status=qualified "
        "and evidence=limited|insufficient as tentative single-study findings. Write consensus "
        "only from claims marked consensus_eligible=true; otherwise leave it empty. Do not "
        "mention prompts, claims, auditing, retrieval, or an evidence packet. Preserve literal "
        "scope boundaries. "
        f"Write in report language '{language}'."
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


async def _consolidate_passes(
    llm: LLMProvider,
    *,
    question: str,
    title: str,
    passes: list[SynthesisSection],
    language: str,
    turkish: bool,
    scope_context: str = "",
) -> tuple[SynthesisSection, bool, str]:
    """Integrate a theme drafted over several evidence packets into one section.

    A theme too large for one prompt is drafted in passes, and concatenating those passes
    would produce exactly the study-by-study listing the section prompt forbids. This is the
    reduce half, built the same way `_draft_overview` reduces themes: compress each pass
    with `_prompt_excerpt`, then ask for one integrated section over the compressed cards.

    Falls back to the deterministic merge rather than to a stitched-claims section: the
    passes are real drafted prose, and losing them to a failed reduce would be a worse
    outcome than a section that reads like two halves.
    """
    preserved = _merge_sections_into_compact_answer(
        passes, turkish=turkish, title=title, note="merged_passes"
    )[0]
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
    per_pass = max(600, budget // max(1, len(passes)))
    cards = "\n\n".join(
        "\n".join(
            [
                f"PASS {number}",
                f"SYNTHESIS: {_prompt_excerpt(section.synthesis, int(per_pass * 0.55))}",
                f"CONSENSUS: {_prompt_excerpt(section.consensus, int(per_pass * 0.15))}",
                f"DISAGREEMENTS: {_prompt_excerpt(section.disagreements, int(per_pass * 0.15))}",
                f"IMPLICATIONS: {_prompt_excerpt(section.implications, int(per_pass * 0.15))}",
            ]
        )
        for number, section in enumerate(passes, 1)
    )
    try:
        data = await llm.complete_json(
            "You are merging several partial drafts of ONE thematic section of a research "
            "report into a single integrated section. Return one JSON object with keys "
            "synthesis, consensus, disagreements, implications. The passes cover different "
            "studies from the same theme: combine them into one argument rather than "
            "reporting them in sequence, and say where the passes agree and where they "
            "diverge. Use only facts present in the passes. Never invent a source, number, "
            "method, population, result, or URL, and never add a citation that is not "
            "already in the passes. Keep at least one supplied [Sxx] citation on every "
            "factual sentence. Do not mention passes, drafts, prompts, or an evidence "
            f"packet. Write in report language '{language}'.",
            f"RESEARCH_QUESTION:\n{question}\n\nTHEME:\n{title}\n\n"
            f"SCOPE_BOUNDARIES:\n{scope_context}\n\n"
            f"ALLOWED_SOURCE_IDS: {', '.join(allowed_ids)}\n\nPASSES:\n{cards}",
        )
        section = _advisory_section_from_data(
            data,
            title=title,
            source_ids=allowed_ids,
            claim_ids=claim_ids,
            language=language,
            consensus_allowed=any(
                section.consensus
                and "consensus:no_multi_source_moderate_evidence"
                not in section.validation_warnings
                for section in passes
            ),
        )
        if section is not None:
            warnings = list(
                dict.fromkeys(
                    [
                        *(warning for item in passes for warning in item.validation_warnings),
                        *section.validation_warnings,
                    ]
                )
            )
            return replace(section, validation_warnings=warnings), True, "consolidated_visible"
    except Exception as exc:  # noqa: BLE001 - a failed reduce must not cost the passes
        return (
            replace(
                preserved,
                validation_warnings=list(
                    dict.fromkeys(
                        [
                            *preserved.validation_warnings,
                            f"consolidation:{type(exc).__name__}",
                        ]
                    )
                ),
            ),
            False,
            f"consolidation_unavailable:{type(exc).__name__}",
        )
    return (
        replace(
            preserved,
            validation_warnings=list(
                dict.fromkeys([*preserved.validation_warnings, "consolidation:unusable_response"])
            ),
        ),
        False,
        "consolidation_unavailable:unusable_response",
    )


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
    unavailable = (
        "LLM sentezi üretilemedi; kanıt kayıtları denetim eklerinde korunmuştur."
        if turkish
        else "LLM synthesis could not be produced; evidence records remain in the audit appendices."
    )
    digest_budget = max(
        3000,
        _prompt_char_budget(llm) - len(question) - (len(allowed) * 8) - 500,
    )
    section_digest = _overview_digest(sections, digest_budget)
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
            "do not repeat a source-by-source inventory. Preserve the supplied [Sxx] citations and "
            "attach citations to factual statements. Use only the section drafts below. Never add "
            "new facts, numbers, sources, URLs, or platform/retrieval metrics. Make uncertainty "
            "specific to comparability, study design, validation, and evidence gaps. "
            "Each field has a distinct role and must not reuse sentences or close paraphrases from "
            "the theme cards or another field. Preserve the original scope boundaries; never replace "
            "a time, condition, population, intervention, or outcome with a neighbouring concept. "
            f"Write in report language '{language}'."
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
        for packet in packets or [EvidencePacket("", [], [])]:
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
        if not drafts:
            section, succeeded, diagnostic = fallback, False, pass_notes[0]
        elif len(drafts) == 1:
            # One usable pass needs no reduce, whether the theme fit in one packet or the
            # other passes failed. Consolidating a single draft would spend a call to
            # rewrite prose that already passed.
            section, succeeded, diagnostic = drafts[0], True, pass_notes[0]
        else:
            section, _consolidated, note = await _consolidate_passes(
                llm,
                question=question,
                title=title,
                passes=drafts,
                language=language,
                turkish=turkish,
                scope_context=scope_context,
            )
            # A failed reduce still yields every pass's prose through the deterministic
            # merge, so the theme counts as model-written either way. `llm_successes` is
            # compared against `len(sections)`, so it must move once per theme and never
            # once per pass.
            succeeded = True
            diagnostic = f"{note}({'+'.join(pass_notes)})"
        theme_coverage.append(
            {
                "theme": title,
                "claims_total": len(theme_claims),
                # Claims that reached a prompt. Not the same as claims the reader's section
                # ends up reflecting: `passes_used` below is what says whether a pass was
                # drafted and then discarded for being ungrounded, which leaves its claims
                # shown to the model but absent from the prose.
                "claims_shown": sum(len(packet.claim_ids) for packet in packets),
                "claims_without_evidence": len(unbacked),
                "passes": len(packets),
                "passes_used": len(drafts),
            }
        )
        # The diagnostic travels with the section as well as in the run-level map. Reading
        # it back by `theme_{index}` means trusting that these two lists stay aligned, and
        # the citation record needs it per section to tell a discarded draft apart from a
        # source the model was offered and passed over.
        sections.append(replace(section, generation_note=diagnostic))
        llm_successes += int(succeeded)
        generation_diagnostics[f"theme_{index}"] = diagnostic
    # Overlap remains observable below, but it no longer deletes model-written sections.
    collapsed_sections: list[dict[str, Any]] = []
    if report_mode == "standard" and len(sections) < 2:
        report_mode = "compact"
        mode_reasons.append("fewer_than_2_viable_themes")
        sections = _merge_sections_into_compact_answer(sections, turkish=turkish)

    if report_mode == "compact":
        overview = {
            "executive_summary": sections[0].synthesis if sections else "",
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
    overlap_rows = (
        [] if report_mode == "compact" else _overview_overlap_rows(overview, sections)
    )
    # Duplicate or overlapping prose is diagnostic only. It must never trigger a rewrite,
    # deletion, compact-mode transition, or replacement with section excerpts.
    relevance_scores = [_question_relevance(claim) for claim in unique_claims]
    maximum_question_relevance = max(relevance_scores, default=0.0)
    contributing_sources = _contributing_sources(unique_claims, synthesis_evidence)
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
    if not unique_claims or not contributing_sources:
        answerability_status = "insufficient"
        answerability_reasons.append("no_reportable_in_scope_evidence")
    else:
        if len(contributing_sources) < 2:
            answerability_reasons.append("fewer_than_2_in_scope_sources")
        if sub_question_coverage < 0.5:
            answerability_reasons.append("sub_question_coverage_below_half")
        if maximum_question_relevance < _DIRECT_ANSWER_RELEVANCE_THRESHOLD:
            answerability_reasons.append("low_question_relevance")
        if answerability_reasons:
            answerability_status = "limited"
    generation_diagnostics["overview"] = overview_diagnostic
    generation_diagnostics["report_mode"] = report_mode
    # Compact rendering shows only `sections[0]`, so more than one section here would be
    # silently deleted from the report. Every path to compact must merge first.
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
    if not sections or (llm_successes == 0 and not overview_succeeded):
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
                "in_scope_contributing_sources": len(contributing_sources),
                "sub_question_coverage": round(sub_question_coverage, 4),
                "reason_codes": answerability_reasons,
            },
        },
    )


def synthesis_manifest(package: SynthesisPackage) -> str:
    return json.dumps(package.as_dict(), ensure_ascii=False, indent=2)
