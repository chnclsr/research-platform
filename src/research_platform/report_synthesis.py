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
from typing import Any

from .language_guard import foreign_sentences, language_matches
from .llm import LLMProvider


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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def narrative(self) -> str:
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
    *,
    turkish: bool,
    maximum: int = 5,
) -> list[tuple[str, list[Any]]]:
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
    return rows


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
    return SynthesisSection(
        title=title,
        synthesis=synthesis,
        consensus=_clean_cited_text(data.get("consensus"), allowed),
        disagreements=_clean_cited_text(data.get("disagreements"), allowed),
        implications=_clean_cited_text(data.get("implications"), allowed),
        source_ids=source_ids,
        claim_ids=claim_ids,
    )


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
            f"Write in report language '{language}'.",
            f"RESEARCH_QUESTION:\n{question}\n\nTHEME:\n{title}\n\n"
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
            f"Write in report language '{language}'.",
            f"RESEARCH_QUESTION:\n{question}\n\nALLOWED_SOURCE_IDS: "
            f"{', '.join(sorted(allowed))}\n\nSECTION_DRAFTS:\n{section_digest}",
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
            "citation.",
            f"LANGUAGE: {language}\nALLOWED_SOURCE_IDS: {', '.join(sorted(allowed))}\n"
            f"{repair_source}",
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
) -> SynthesisPackage:
    """Create a bounded, citation-validated synthesis package."""
    turkish = language.lower().startswith("tr")
    source_labels = {str(source.id): f"S{index:02d}" for index, source in enumerate(sources, 1)}
    profiles = build_study_profiles(
        sources,
        reportable_claims,
        evidence_by_claim,
        turkish=turkish,
    )
    theme_plan = _plan_themes(
        reportable_claims,
        sub_questions or [],
        turkish=turkish,
    )
    sections: list[SynthesisSection] = []
    llm_successes = 0
    generation_diagnostics: dict[str, str] = {}
    for index, (title, theme_claims) in enumerate(theme_plan, 1):
        packet, source_ids, claim_ids = _evidence_packet(
            theme_claims,
            evidence_by_claim,
            source_labels,
        )
        fallback = _fallback_section(
            title,
            theme_claims,
            evidence_by_claim,
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
        )
        # The diagnostic travels with the section as well as in the run-level map. Reading
        # it back by `theme_{index}` means trusting that these two lists stay aligned, and
        # the citation record needs it per section to tell a discarded draft apart from a
        # source the model was offered and passed over.
        sections.append(replace(section, generation_note=diagnostic))
        llm_successes += int(succeeded)
        generation_diagnostics[f"theme_{index}"] = diagnostic

    overview, overview_succeeded, overview_diagnostic = await _draft_overview(
        llm,
        question=question,
        sections=sections,
        language=language,
        turkish=turkish,
    )
    generation_diagnostics["overview"] = overview_diagnostic
    return SynthesisPackage(
        executive_summary=overview["executive_summary"],
        sections=sections,
        cross_study_assessment=overview["cross_study_assessment"],
        conclusion=overview["conclusion"],
        uncertainty=overview["uncertainty"],
        study_profiles=profiles,
        generated_by_llm=bool(sections) and llm_successes == len(sections) and overview_succeeded,
        generation_diagnostics=generation_diagnostics,
    )


def synthesis_manifest(package: SynthesisPackage) -> str:
    return json.dumps(package.as_dict(), ensure_ascii=False, indent=2)
