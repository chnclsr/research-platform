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


@dataclass(frozen=True)
class SynthesisPackage:
    executive_summary: str
    sections: list[SynthesisSection]
    cross_study_assessment: str
    conclusion: str
    uncertainty: str
    study_profiles: list[StudyProfile]
    generated_by_llm: bool
    generation_diagnostics: dict[str, str] = field(default_factory=dict)
    report_mode: str = "standard"
    quality_diagnostics: dict[str, Any] = field(default_factory=dict)
    answerability_status: Literal["answerable", "insufficient"] = "answerable"

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


def _insufficient_answerability_overview(*, turkish: bool) -> dict[str, str]:
    if turkish:
        return {
            "executive_summary": (
                "Mevcut kaynaklandırılmış kanıt, araştırma sorusuna güvenilir bir yanıt "
                "vermek için yeterli değildir. Düşük soru ilgisine sahip komşu konu "
                "bulguları ana yanıta dahil edilmemiştir."
            ),
            "cross_study_assessment": "",
            "conclusion": "",
            "uncertainty": (
                "Doğrudan ilgili en az bir kaynaklandırılmış bulgu elde edilmeden güvenilir "
                "bir öneri veya sonuç sunulamaz. Düşük ilgili iddialar yalnız denetim "
                "eklerinde korunmuştur."
            ),
        }
    return {
        "executive_summary": (
            "The available sourced evidence is insufficient to answer the research question "
            "reliably. Findings about neighbouring topics with low question relevance were "
            "not included in the main answer."
        ),
        "cross_study_assessment": "",
        "conclusion": "",
        "uncertainty": (
            "No reliable recommendation or conclusion can be provided until at least one "
            "directly relevant sourced finding is available. Low-relevance claims are retained "
            "only in the audit appendices."
        ),
    }


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


def _normalise_text_value(value: Any) -> str:
    """Accept prose or a flat JSON string list without leaking Python syntax.

    Small structured-output models sometimes return a list where the schema requests a
    string.  ``str(value)`` rendered that list as ``['first', 'second']`` in the report.
    A flat list is still unambiguous prose and can be joined safely; every other shape is
    rejected so the caller can repair or fall back instead of publishing serialization
    syntax.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " ".join(item.strip() for item in value if item.strip())
    return ""


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


def _overview_digest_budget(llm: LLMProvider) -> int:
    """Reserve output and fixed-prompt room before constructing the overview digest."""
    settings = getattr(llm, "settings", None)
    context_tokens = int(getattr(settings, "llm_context_tokens", 8192))
    output_tokens = int(getattr(settings, "llm_max_output_tokens", 2048))
    available_tokens = max(2048, context_tokens - output_tokens - 1536)
    # Two characters per token is conservative for mixed Turkish/English medical prose.
    return max(6000, min(24000, available_tokens * 2))


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
    """Extract run-specific wording without a domain or season lookup table."""
    quoted = [
        next(value for value in match.groups() if value)
        for match in re.finditer(r'"([^"\n]+)"|“([^”\n]+)”|\'([^\'\n]+)\'', question or "")
    ]
    acronyms = re.findall(r"\b[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9-]{1,}\b", question or "")
    content = sorted(word for word in _words(question) if len(word) >= 4)
    return list(dict.fromkeys([*quoted, *acronyms, *content]))[:24]


def _anchor_present(anchor: str, text: str) -> bool:
    anchor_words = normalise_text(anchor).split()
    text_words = normalise_text(text).split()
    if not anchor_words:
        return True
    if len(anchor_words) > 1:
        return normalise_text(anchor) in normalise_text(text)
    stem = anchor_words[0][:5]
    return any(word.startswith(stem) for word in text_words)


def _theme_scope_anchors(
    anchors: list[str], claims: list[Any], claim_texts: dict[str, str] | None
) -> list[str]:
    claim_prose = " ".join(
        (claim_texts or {}).get(str(claim.id), str(getattr(claim, "text", "")))
        for claim in claims
    )
    return [anchor for anchor in anchors if _anchor_present(anchor, claim_prose)]


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


# Reasons that mean the corpus itself cannot support a thematic report. All of them are
# settled before the themes are drafted, which is what makes a compact report an actually
# integrated answer rather than a hidden set of themes.
_CAPACITY_MODE_REASONS = frozenset(
    {
        "fewer_than_8_unique_claims",
        "fewer_than_4_contributing_sources",
        "estimated_completeness_below_0_5",
        "fewer_than_2_viable_themes",
    }
)


def _report_mode(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    coverage: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if len(claims) < 8:
        reasons.append("fewer_than_8_unique_claims")
    if len(_contributing_sources(claims, evidence_by_claim)) < 4:
        reasons.append("fewer_than_4_contributing_sources")
    completeness = float((coverage or {}).get("estimated_completeness", 1.0) or 0.0)
    if completeness < 0.5:
        reasons.append("estimated_completeness_below_0_5")
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
    turkish: bool,
    report_mode: str,
    maximum: int = 5,
) -> list[tuple[str, list[Any]]]:
    if report_mode == "compact":
        title = "Kanıt özeti" if turkish else "Evidence summary"
        return [(title, list(claims))] if claims else []
    usable_sub_questions = [str(item).strip() for item in sub_questions if str(item).strip()][:maximum]
    buckets: dict[str, list[Any]] = {title: [] for title in usable_sub_questions}
    generic: dict[str, list[Any]] = {}
    for claim in claims:
        claim_text = str(getattr(claim, "text", ""))
        claim_words = _words(claim_text)
        best_title = ""
        best_score = 0
        for title in usable_sub_questions:
            score = len(claim_words & _words(title))
            if score > best_score:
                best_title, best_score = title, score
        if best_title and best_score >= 2:
            buckets[best_title].append(claim)
        else:
            generic.setdefault(_generic_theme(claim_text, turkish), []).append(claim)
    rows = [(title, values) for title, values in buckets.items() if values]
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


def _evidence_packet(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    source_labels: dict[str, str],
    *,
    max_claims: int = 12,
    max_chars: int = 14000,
) -> tuple[str, list[str], list[str]]:
    blocks: list[str] = []
    used_sources: list[str] = []
    used_claims: list[str] = []
    for index, claim in enumerate(claims[:max_claims], 1):
        claim_id = str(claim.id)
        lines: list[str] = []
        for link, source in evidence_by_claim.get(claim_id, []):
            source_label = source_labels.get(str(source.id))
            quote = " ".join(str(getattr(link, "quote", "")).split())[:650]
            if not source_label or not quote:
                continue
            direction = str(getattr(link, "direction", "supports"))
            lines.append(f"{source_label} {direction}: {quote}")
            if source_label not in used_sources:
                used_sources.append(source_label)
        if not lines:
            continue
        block = (
            f"C{index:02d} | status={getattr(claim, 'status', 'qualified')} | "
            f"claim={str(getattr(claim, 'text', ''))[:900]}\n" + "\n".join(lines[:4])
        )
        if len("\n\n".join([*blocks, block])) > max_chars:
            break
        blocks.append(block)
        used_claims.append(claim_id)
    return "\n\n".join(blocks), used_sources, used_claims


def _clean_cited_text(value: Any, allowed_sources: set[str]) -> str:
    text = " ".join(_normalise_text_value(value).replace("\x00", "").split())
    if not text:
        return ""
    invalid_source = False

    def normalise_citation(match: re.Match[str]) -> str:
        nonlocal invalid_source
        source_ids = re.findall(r"\bS\d{2,3}\b", match.group(1))
        if not source_ids:
            # Models often echo claim labels such as [C03] or bibliography
            # numbers such as [2,3]. They are not report citations.
            return ""
        rendered = [f"[{source_id}]" for source_id in source_ids]
        if set(rendered) - allowed_sources:
            invalid_source = True
            return ""
        return " ".join(dict.fromkeys(rendered))

    text = _BRACKET_RE.sub(normalise_citation, text)
    citations = set(_TOKEN_RE.findall(text))
    if invalid_source or citations - allowed_sources:
        return ""
    if allowed_sources and not citations:
        return ""
    if re.search(r"https?://", text):
        return ""
    text = re.sub(
        r"\b(?:Evidans|Kanıt) paketi içindeki kaynaklar\b",
        "İncelenen çalışmalar",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:Evidans|Kanıt) paketi\b",
        "İncelenen kanıtlar",
        text,
        flags=re.I,
    )
    return text


def _section_from_data(
    data: Any,
    *,
    title: str,
    source_ids: list[str],
    claim_ids: list[str],
    allowed: set[str],
    language: str,
) -> SynthesisSection | None:
    if not isinstance(data, dict):
        return None
    synthesis = _clean_cited_text(data.get("synthesis"), allowed)
    # Two checks, because they catch different failures. The whole-text one rejects a section
    # written in the wrong language outright; the sentence one rejects a section that is
    # mostly right but carries source text pasted onto the end, which is what readers were
    # finding in the Word reports and what the old block-level heuristic waved through.
    if not synthesis or not language_matches(synthesis, language):
        return None
    if foreign_sentences(synthesis, language):
        return None
    section = SynthesisSection(
        title=title,
        synthesis=synthesis,
        consensus=_clean_cited_text(data.get("consensus"), allowed),
        disagreements=_clean_cited_text(data.get("disagreements"), allowed),
        implications=_clean_cited_text(data.get("implications"), allowed),
        source_ids=source_ids,
        claim_ids=claim_ids,
    )
    values = {
        "consensus": section.consensus,
        "disagreements": section.disagreements,
        "implications": section.implications,
    }
    kept: list[str] = [section.synthesis]
    for key, value in values.items():
        if value and any(prose_overlaps(value, previous) for previous in kept):
            values[key] = ""
        elif value:
            kept.append(value)
    return replace(section, **values)


def _collapse_overlapping_sections(
    sections: list[SynthesisSection],
) -> tuple[list[SynthesisSection], list[dict[str, Any]]]:
    kept: list[SynthesisSection] = []
    diagnostics: list[dict[str, Any]] = []
    for section in sections:
        duplicate_index = next(
            (
                index
                for index, other in enumerate(kept)
                if prose_overlaps(section.synthesis, other.synthesis)
            ),
            None,
        )
        if duplicate_index is None:
            kept.append(section)
            continue
        other = kept[duplicate_index]
        diagnostics.append(
            {
                "kept": other.title,
                "removed": section.title,
                "word_cosine": round(word_cosine(other.synthesis, section.synthesis), 3),
                "trigram_jaccard": round(
                    ngram_jaccard(other.synthesis, section.synthesis), 3
                ),
            }
        )
        kept[duplicate_index] = replace(
            other,
            source_ids=list(dict.fromkeys([*other.source_ids, *section.source_ids])),
            claim_ids=list(dict.fromkeys([*other.claim_ids, *section.claim_ids])),
            generation_note=f"{other.generation_note};merged_overlap",
        )
    return kept, diagnostics


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


def _summary_overlaps_a_theme(summary: str, sections: list[SynthesisSection]) -> bool:
    return bool(summary) and any(
        prose_overlaps(summary, section.synthesis) for section in sections
    )


def _deduplicated_executive_summary(
    summary: str, sections: list[SynthesisSection], *, turkish: bool
) -> tuple[str, str]:
    """Repair a summary that repeats a theme, rather than hiding the themes.

    An overview that echoes a theme is a defect of the overview, not evidence that the
    report lacks the capacity for themes. Returns the summary to render and a diagnostic
    naming which rung produced it.
    """
    if not _summary_overlaps_a_theme(summary, sections):
        return summary, "llm"
    leads = [
        lead
        for section in sections
        for lead in _sentences(section.synthesis)[:1]
    ]
    rebuilt = _bounded_grounded_join(leads, _OVERVIEW_FIELD_LIMITS["executive_summary"])
    if rebuilt and not _summary_overlaps_a_theme(rebuilt, sections):
        return rebuilt, "rebuilt_from_theme_leads"
    pointer = (
        "Kanıt tek bir genel hükümle özetlenemeyecek kadar tema bağımlıdır; "
        "kaynaklandırılmış bulgular aşağıdaki tematik bölümlerde sunulmuştur."
        if turkish
        else "The evidence is too theme-dependent for a single overall statement; the "
        "sourced findings are presented in the thematic sections below."
    )
    return pointer, "fallback:scoped_pointer"


def _merge_sections_into_compact_answer(
    sections: list[SynthesisSection], *, turkish: bool
) -> list[SynthesisSection]:
    """Fold every theme into one integrated answer before a compact report hides them.

    Compact rendering drops `sections` from the reader-visible surface, so a mode change
    that leaves several drafted themes behind deletes them from the report. Merging first
    keeps every theme's prose and provenance in the one section that still gets rendered.
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
            title="Kanıt özeti" if turkish else "Evidence summary",
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
                        "merged_for_compact",
                    ]
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
    """The section used when the model's own prose is unusable.

    `claim_texts` is what stops this being an English paragraph in a Turkish report. The
    statements are English whatever language the run was asked in, and this path had no
    language check at all -- only the "no narrative" message was ever localized -- so every
    rejected section arrived in the reader's report in the wrong language.
    """
    statements: list[str] = []
    sources: list[str] = []
    claim_ids: list[str] = []
    for claim in claims[:6]:
        refs: list[str] = []
        for _, source in evidence_by_claim.get(str(claim.id), []):
            label = source_labels.get(str(source.id))
            if label and label not in refs:
                refs.append(label)
            if label and label not in sources:
                sources.append(label)
        if refs:
            text = (claim_texts or {}).get(
                str(claim.id), str(getattr(claim, "text", ""))
            )
            statements.append(f"{text} {' '.join(f'[{ref}]' for ref in refs[:3])}")
            claim_ids.append(str(claim.id))
    synthesis = " ".join(statements)
    if not synthesis:
        synthesis = (
            "Bu tema için kaynaklandırılabilir anlatı üretilemedi."
            if turkish
            else "No source-grounded narrative could be produced for this theme."
        )
    return SynthesisSection(
        title=title,
        synthesis=synthesis,
        source_ids=sources,
        claim_ids=claim_ids,
    )


def _force_ground_text(value: Any, source_ids: list[str], language: str) -> str:
    """Ground a repair-only translation when the small model drops citation syntax.

    This is never used for an original draft.  The repair prompt is constrained
    to translation/reformatting of an already evidence-bounded draft, so the
    deterministic citation suffix restores provenance without expanding facts.
    """
    text = " ".join(_normalise_text_value(value).replace("\x00", "").split())
    text = _BRACKET_RE.sub("", text).strip()
    text = re.sub(
        r"\b(?:Evidans|Kanıt) paketi içindeki kaynaklar\b",
        "İncelenen çalışmalar",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:Evidans|Kanıt) paketi\b",
        "İncelenen kanıtlar",
        text,
        flags=re.I,
    )
    if not text or re.search(r"https?://", text) or not language_matches(text, language):
        return ""
    citations = " ".join(f"[{source_id}]" for source_id in source_ids[:6])
    return f"{text} {citations}".strip()


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
        return fallback, False, "fallback:no_evidence_packet"
    allowed = {f"[{source_id}]" for source_id in source_ids}
    try:
        data = await llm.complete_json(
            "You are writing one evidence-grounded thematic section of a research report. "
            "Return one JSON object with keys synthesis, consensus, disagreements, implications. "
            "SYNTHESIS must integrate multiple studies instead of listing them one by one: explain "
            "what the body of evidence collectively indicates, where studies differ, and why. "
            "Use only facts in EVIDENCE_PACKET. Attach one or more supplied [Sxx] citations to every "
            "factual sentence. Never invent a source, number, method, population, result, or URL. "
            "Do not describe platform metrics, source counts, retrieval, claims, prompts, or auditing. "
            "Do not mention an evidence packet; write directly about the studies and their evidence. "
            "Treat the supplied original wording and scope anchors as literal boundaries: do not "
            "replace a time, condition, population, intervention, or outcome with a neighbouring "
            "concept unless the evidence packet explicitly states that relationship. "
            f"Write in report language '{language}'.",
            f"RESEARCH_QUESTION:\n{question}\n\nTHEME:\n{title}\n\n"
            f"SCOPE_BOUNDARIES:\n{scope_context}\n\n"
            f"ALLOWED_SOURCE_IDS: {', '.join(source_ids)}\n\nEVIDENCE_PACKET:\n{packet}",
        )
        section = _section_from_data(
            data,
            title=title,
            source_ids=source_ids,
            claim_ids=claim_ids,
            allowed=allowed,
            language=language,
        )
        if section is not None:
            return section, True, "initial_passed"
        repair = await llm.complete_json(
            "Repair the supplied draft as a research synthesis section. Return JSON with keys "
            "synthesis, consensus, disagreements, implications. Write entirely in the requested "
            "language. Keep only the allowed [Sxx] citations; remove [Cxx] and numeric bibliography "
            "markers. Do not add a fact, number, source, URL, or conclusion that is absent from the "
            "draft. Do not mention a prompt or evidence packet. Every factual field must retain at "
            "least one allowed [Sxx] citation.",
            f"LANGUAGE: {language}\nALLOWED_SOURCE_IDS: {', '.join(source_ids)}\n"
            f"DRAFT:\n{json.dumps(data, ensure_ascii=False)[:18000]}",
        )
        repaired = _section_from_data(
            repair,
            title=title,
            source_ids=source_ids,
            claim_ids=claim_ids,
            allowed=allowed,
            language=language,
        )
        if repaired is not None:
            return repaired, True, "repair_passed"
        if isinstance(repair, dict):
            repair_text = " ".join(
                _normalise_text_value(value) for value in repair.values()
            )
            repair_citations = set(_TOKEN_RE.findall(repair_text))
            # Forced grounding may restore citations a translation dropped, but it must
            # never launder an invented [Sxx] into an allowed one.
            forced_synthesis = ""
            if not (repair_citations - allowed):
                forced_synthesis = _force_ground_text(
                    repair.get("synthesis"),
                    source_ids,
                    language,
                )
            if forced_synthesis:
                return (
                    SynthesisSection(
                        title=title,
                        synthesis=forced_synthesis,
                        consensus=_force_ground_text(
                            repair.get("consensus"), source_ids, language
                        ),
                        disagreements=_force_ground_text(
                            repair.get("disagreements"), source_ids, language
                        ),
                        implications=_force_ground_text(
                            repair.get("implications"), source_ids, language
                        ),
                        source_ids=source_ids,
                        claim_ids=claim_ids,
                    ),
                    True,
                    "repair_forced_grounding",
                )
        return fallback, False, "fallback:invalid_repair"
    except Exception as exc:  # noqa: BLE001 - provider failures must use the safe fallback
        return fallback, False, f"fallback:{type(exc).__name__}"


async def _draft_overview(
    llm: LLMProvider,
    *,
    question: str,
    sections: list[SynthesisSection],
    language: str,
    turkish: bool,
    scope_context: str = "",
) -> tuple[dict[str, str], bool, str]:
    allowed = {
        f"[{source_id}]"
        for section in sections
        for source_id in section.source_ids
    }
    prefix = (
        "Kanıt, tek bir genel hükümden çok tema bazında değerlendirilmelidir. "
        if turkish
        else "The evidence is best interpreted by theme rather than as one universal conclusion. "
    )
    executive_body = _bounded_grounded_join(
        [section.synthesis for section in sections[:3]],
        _OVERVIEW_FIELD_LIMITS["executive_summary"] - len(prefix),
    )
    cross_study = _bounded_grounded_join(
        [
            value
            for section in sections
            for value in (section.consensus, section.disagreements)
            if value
        ],
        _OVERVIEW_FIELD_LIMITS["cross_study_assessment"],
    )
    conclusion = _bounded_grounded_join(
        [section.implications or section.synthesis for section in sections[-2:]],
        _OVERVIEW_FIELD_LIMITS["conclusion"],
    )
    fallback = {
        "executive_summary": f"{prefix}{executive_body}".strip(),
        "cross_study_assessment": cross_study,
        "conclusion": conclusion,
        "uncertainty": (
            "Bulgular yalnız raporda kaynaklandırılan çalışma bağlamlarında geçerlidir; "
            "aynı sonlanımı ölçmeyen çalışmaların sayısal sonuçları doğrudan karşılaştırılmamalıdır."
            if turkish
            else "Findings apply only to the cited study contexts; numerical results from studies "
            "that do not measure the same endpoint should not be compared directly."
        ),
    }
    digest_budget = max(
        3000,
        _overview_digest_budget(llm) - len(question) - (len(allowed) * 8) - 500,
    )
    section_digest = _overview_digest(sections, digest_budget)
    if not section_digest or not allowed:
        return fallback, False, "fallback:no_grounded_sections"

    def candidate(data: Any) -> tuple[dict[str, str] | None, list[str]]:
        if not isinstance(data, dict):
            return None, ["response_not_object"]
        cleaned: dict[str, str] = {}
        errors: list[str] = []
        for key, fallback_value in fallback.items():
            raw = data.get(key)
            normalised = _normalise_text_value(raw)
            value = _clean_cited_text(raw, allowed)
            if not normalised:
                reason = "missing" if raw is None or raw == "" else "invalid_type"
                errors.append(f"{key}:{reason}")
            elif not value:
                errors.append(f"{key}:invalid_or_ungrounded")
            if value and len(value) > _OVERVIEW_FIELD_LIMITS[key]:
                value = _bounded_grounded_join(
                    [value],
                    _OVERVIEW_FIELD_LIMITS[key],
                )
                if not value:
                    errors.append(f"{key}:no_complete_sentence_within_limit")
            if value and not language_matches(value, language):
                errors.append(f"{key}:language_mismatch")
                value = ""
            cleaned[key] = value or fallback_value
        for overlap in _overview_overlap_rows(cleaned, sections):
            if overlap["left"].startswith("theme:") and overlap["right"].startswith(
                "theme:"
            ):
                continue
            errors.append(
                f"{overlap['left']}:overlap_with_{overlap['right']}"
            )
        required_errors = [
            error
            for error in errors
            if error.startswith(("executive_summary:", "conclusion:"))
        ]
        return (None if required_errors else cleaned), errors

    initial_data: Any = None
    initial_candidate: dict[str, str] | None = None
    initial_errors: list[str] = []
    try:
        initial_data = await llm.complete_json(
            "Write the integrative layer of a research report as one JSON object with keys "
            "executive_summary, cross_study_assessment, conclusion, uncertainty. Synthesize themes; "
            "do not repeat a source-by-source inventory. Preserve the supplied [Sxx] citations and "
            "attach citations to factual statements. Use only the section drafts below. Never add "
            "new facts, numbers, sources, URLs, or platform/retrieval metrics. Make uncertainty "
            "specific to comparability, study design, validation, and evidence gaps. "
            "Each field has a distinct role and must not reuse sentences or close paraphrases from "
            "the theme cards or another field. Preserve the original scope boundaries; never replace "
            "a time, condition, population, intervention, or outcome with a neighbouring concept. "
            f"Write in report language '{language}'.",
            f"RESEARCH_QUESTION:\n{question}\n\nALLOWED_SOURCE_IDS: "
            f"{', '.join(sorted(allowed))}\n\nSCOPE_BOUNDARIES:\n{scope_context}\n\n"
            f"SECTION_DRAFTS:\n{section_digest}",
        )
        initial_candidate, initial_errors = candidate(initial_data)
        if initial_candidate is not None and not initial_errors:
            return initial_candidate, True, "initial_passed"
    except Exception as exc:  # noqa: BLE001 - retry any provider/decoder failure once
        initial_errors = [f"initial:{type(exc).__name__}"]

    try:
        repair_budget = max(
            3000,
            _overview_digest_budget(llm) - (len(allowed) * 8) - 500,
        )
        serialised_draft = json.dumps(initial_data, ensure_ascii=False)
        draft_boundary = serialised_draft.rfind(" ", 0, repair_budget)
        bounded_draft = serialised_draft[
            : draft_boundary if draft_boundary > 0 else repair_budget
        ].rstrip()
        repair_source = (
            f"DRAFT:\n{bounded_draft}"
            if initial_data is not None
            else f"SECTION_DRAFTS:\n{section_digest}"
        )
        repaired_data = await llm.complete_json(
            "Repair or regenerate the integrative layer of a research report. Return one JSON "
            "object with string fields executive_summary, cross_study_assessment, conclusion, "
            "uncertainty. Flat arrays of sentences are allowed only when they can be joined as "
            "prose. Write entirely in the requested language. Keep only the allowed [Sxx] "
            "citations. Do not add facts, numbers, sources, URLs, or conclusions absent from the "
            "supplied draft or theme cards. Every factual field must retain at least one allowed "
            "citation. Remove sentence reuse and close paraphrases between fields while preserving "
            "their distinct roles and the supplied scope boundaries.",
            f"LANGUAGE: {language}\nALLOWED_SOURCE_IDS: {', '.join(sorted(allowed))}\n"
            f"SCOPE_BOUNDARIES:\n{scope_context}\n{repair_source}",
        )
        repaired_candidate, repair_errors = candidate(repaired_data)
        if repaired_candidate is not None and not repair_errors:
            return repaired_candidate, True, "repair_passed"
        if repaired_candidate is not None:
            return (
                repaired_candidate,
                False,
                f"repair_partial:{','.join(repair_errors)}",
            )
        if initial_candidate is not None:
            return (
                initial_candidate,
                False,
                f"initial_partial:{','.join(initial_errors)};repair_invalid",
            )
        return fallback, False, f"fallback:{','.join(repair_errors)}"
    except Exception as exc:  # noqa: BLE001 - preserve a bounded fallback on provider failure
        if initial_candidate is not None:
            return (
                initial_candidate,
                False,
                f"initial_partial:{','.join(initial_errors)};repair:{type(exc).__name__}",
            )
        return fallback, False, f"fallback:repair_{type(exc).__name__}"


async def build_synthesis_package(
    *,
    llm: LLMProvider,
    question: str,
    language: str,
    sources: list[Any],
    reportable_claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    sub_questions: list[str] | None = None,
    claim_texts: dict[str, str] | None = None,
    display_question: str = "",
    coverage: dict[str, Any] | None = None,
) -> SynthesisPackage:
    """Create a bounded, citation-validated synthesis package."""
    turkish = language.lower().startswith("tr")
    unique_claims, synthesis_evidence, merged_claim_ids = _deduplicate_report_claims(
        reportable_claims, evidence_by_claim
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
        turkish=turkish,
        report_mode=report_mode,
    )
    sections: list[SynthesisSection] = []
    llm_successes = 0
    generation_diagnostics: dict[str, str] = {}
    for index, (title, theme_claims) in enumerate(theme_plan, 1):
        packet, source_ids, claim_ids = _evidence_packet(
            theme_claims,
            synthesis_evidence,
            source_labels,
        )
        fallback = _fallback_section(
            title,
            theme_claims,
            synthesis_evidence,
            source_labels,
            turkish=turkish,
            claim_texts=claim_texts,
        )
        section, succeeded, diagnostic = await _draft_section(
            llm,
            question=question,
            title=title,
            packet=packet,
            source_ids=source_ids,
            claim_ids=claim_ids,
            language=language,
            fallback=fallback,
            scope_context=scope_context,
        )
        required_anchors = _theme_scope_anchors(
            anchors, theme_claims, claim_texts
        )
        visible_section_text = (
            f"{section.synthesis} {section.consensus} "
            f"{section.disagreements} {section.implications}"
        )
        missing_anchors = [
            anchor
            for anchor in required_anchors
            if not _anchor_present(anchor, visible_section_text)
        ]
        if missing_anchors:
            section = fallback
            succeeded = False
            diagnostic = "fallback:scope_anchor_drift"
        # The diagnostic travels with the section as well as in the run-level map. Reading
        # it back by `theme_{index}` means trusting that these two lists stay aligned, and
        # the citation record needs it per section to tell a discarded draft apart from a
        # source the model was offered and passed over.
        sections.append(replace(section, generation_note=diagnostic))
        llm_successes += int(succeeded)
        generation_diagnostics[f"theme_{index}"] = diagnostic
    sections, collapsed_sections = _collapse_overlapping_sections(sections)
    if report_mode == "standard" and len(sections) < 2:
        report_mode = "compact"
        mode_reasons.append("fewer_than_2_viable_themes")
        sections = _merge_sections_into_compact_answer(sections, turkish=turkish)

    if report_mode == "compact":
        overview = {
            "executive_summary": sections[0].synthesis if sections else "",
            "cross_study_assessment": "",
            "conclusion": "",
            "uncertainty": (
                "Kanıt hacmi ayrıntılı ve birbirinden bağımsız temalar kurmak için sınırlıdır; "
                "sonuçlar yalnız kaynaklandırılan çalışma bağlamlarında yorumlanmalıdır."
                if turkish
                else "The evidence volume is too limited for multiple independent themes; "
                "findings should be interpreted only in the cited study contexts."
            ),
        }
        overview_succeeded = True
        overview_diagnostic = "compact_not_run"
    else:
        overview, overview_succeeded, overview_diagnostic = await _draft_overview(
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
    if report_mode == "standard":
        # An overview that repeats a theme is repaired in the overview. It must not switch
        # the report to compact: the themes are already drafted as separate sections by
        # this point, and compact rendering would drop every one of them from the report
        # instead of removing the one field that duplicates.
        summary, summary_diagnostic = _deduplicated_executive_summary(
            overview["executive_summary"], sections, turkish=turkish
        )
        overview["executive_summary"] = summary
        generation_diagnostics["executive_summary"] = summary_diagnostic
        if any("cross_study_assessment" in (row["left"], row["right"]) for row in overlap_rows):
            overview["cross_study_assessment"] = ""
        if any("conclusion" in (row["left"], row["right"]) for row in overlap_rows):
            overview["conclusion"] = ""
    relevance_scores = [_question_relevance(claim) for claim in unique_claims]
    maximum_question_relevance = max(relevance_scores, default=0.0)
    answerability_status: Literal["answerable", "insufficient"] = "answerable"
    answerability_reasons: list[str] = []
    # This gate replaces the whole report with a sufficiency notice, so it is tied to the
    # evidence-capacity reasons that are decided before any theme is drafted. A compact
    # report reached some other way has not been shown to lack the evidence to answer.
    if (
        report_mode == "compact"
        and any(reason in _CAPACITY_MODE_REASONS for reason in mode_reasons)
        and bool(unique_claims)
        and maximum_question_relevance < _DIRECT_ANSWER_RELEVANCE_THRESHOLD
    ):
        answerability_status = "insufficient"
        answerability_reasons.append("compact_low_question_relevance")
        overview = _insufficient_answerability_overview(turkish=turkish)
    invalid_repair_layers = [
        layer
        for layer, diagnostic in generation_diagnostics.items()
        if diagnostic == "fallback:invalid_repair"
    ]
    generation_diagnostics["overview"] = overview_diagnostic
    generation_diagnostics["report_mode"] = report_mode
    # Compact rendering shows only `sections[0]`, so more than one section here would be
    # silently deleted from the report. Every path to compact must merge first.
    assert not (report_mode == "compact" and len(sections) > 1), (
        "compact reports must carry a single integrated section"
    )
    return SynthesisPackage(
        executive_summary=overview["executive_summary"],
        sections=sections,
        cross_study_assessment=overview["cross_study_assessment"],
        conclusion=overview["conclusion"],
        uncertainty=overview["uncertainty"],
        study_profiles=profiles,
        generated_by_llm=bool(sections) and llm_successes == len(sections) and overview_succeeded,
        generation_diagnostics=generation_diagnostics,
        report_mode=report_mode,
        answerability_status=answerability_status,
        quality_diagnostics={
            "mode_reasons": list(dict.fromkeys(mode_reasons)),
            "input_claim_count": len(reportable_claims),
            "unique_claim_count": len(unique_claims),
            "contributing_source_count": len(
                _contributing_sources(unique_claims, synthesis_evidence)
            ),
            "merged_claim_ids": merged_claim_ids,
            "collapsed_sections": collapsed_sections,
            "field_overlaps": overlap_rows,
            "scope_anchors": anchors,
            "answerability": {
                "status": answerability_status,
                "threshold": _DIRECT_ANSWER_RELEVANCE_THRESHOLD,
                "maximum_question_relevance": round(maximum_question_relevance, 4),
                "reason_codes": answerability_reasons,
                "invalid_repair_layers": invalid_repair_layers,
            },
        },
    )


def synthesis_manifest(package: SynthesisPackage) -> str:
    return json.dumps(package.as_dict(), ensure_ascii=False, indent=2)
