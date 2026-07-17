from __future__ import annotations

import re
from collections import defaultdict, deque
from urllib.parse import urlparse

from .recovery import matches_target_entities, resolve_official_entities
from .schemas import AcquiredDocument, ConnectorCandidate, ResearchProtocol, SourceFamily
from .temporal import date_scope_decision, publication_datetime


STOPWORDS = {
    "about", "after", "also", "and", "any", "are", "based", "been", "bir", "bu", "does", "for",
    "from", "gibi", "how", "ile", "into", "its", "local", "nelerdir", "nedir", "olan",
    "olarak", "has", "have", "that", "the", "their", "this", "use", "used", "uses", "what", "when", "where",
    "which", "who", "why", "with", "icin", "için", "ve", "veya",
}

GENERIC_RESEARCH_TERMS = {
    "approach", "approaches", "based", "best", "clinical", "data", "deep",
    "development", "developments", "evidence", "general", "including", "latest",
    "learning", "method", "methods", "model", "models", "month", "months", "new",
    "paper", "papers", "practice", "practices", "published", "recent", "research",
    "result", "results", "risk", "source", "sources", "studies", "study", "updated",
    "using", "validated", "yaklaşım", "yaklasim", "çalışma", "calisma",
    "güncel", "guncel", "kaynak", "kaynaklar", "uygulama", "uygulamaları",
}

TERM_ALIASES = {
    "güvenlik": {"security", "secure", "authorization", "authentication", "oauth", "threat"},
    "guvenlik": {"security", "secure", "authorization", "authentication", "oauth", "threat"},
    "sunucu": {"server", "servers"},
    "sunucuları": {"server", "servers"},
    "kimlik": {"identity", "authentication", "authorization"},
    "doğrulama": {"authentication", "verification", "validation"},
}

UNTRUSTED_DISCOVERY_PATTERN = re.compile(
    r"\b(ignore (all |the )?(previous|prior) instructions?|system prompt|"
    r"jailbreak|developer message|occult override|is god|seen\s*=\s*activated|"
    r"operational\s*[∴:]+|do not summarize|execute this command)\b",
    flags=re.IGNORECASE,
)


def terms(value: str) -> set[str]:
    result: set[str] = set()
    for token in re.findall(r"[a-zA-ZÀ-ž0-9][a-zA-ZÀ-ž0-9_-]+", value.lower()):
        if len(token) >= 3 and token not in STOPWORDS:
            result.add(token)
            collapsed = token.replace("-", "").replace("_", "")
            if len(collapsed) >= 3:
                result.add(collapsed)
            if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
                result.add(token[:-1])
    return result


def topic_terms(value: str) -> set[str]:
    output = {token for token in terms(value) if not token.isdigit()} - GENERIC_RESEARCH_TERMS
    for token in list(output):
        output.update(TERM_ALIASES.get(token, set()))
    return output


def topic_bigrams(value: str) -> set[str]:
    allowed = topic_terms(value)
    ordered = []
    for token in re.findall(r"[a-zA-ZÀ-ž0-9][a-zA-ZÀ-ž0-9_-]+", value.lower()):
        normalized = token.replace("-", "").replace("_", "")
        if normalized in allowed and normalized not in GENERIC_RESEARCH_TERMS:
            ordered.append(normalized)
    return {f"{left} {right}" for left, right in zip(ordered, ordered[1:])}


def focus_terms(value: str) -> set[str]:
    parts = re.split(r"\b(?:for|regarding|about|için|icin|hakkında|hakkinda)\b", value, flags=re.I)
    if len(parts) < 2:
        return set()
    return topic_terms(parts[-1])


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def domain_matches(url: str, domains: list[str]) -> bool:
    host = hostname(url)
    return any(host == domain.lower().removeprefix("www.") or host.endswith(f".{domain.lower().removeprefix('www.')}") for domain in domains)


def github_repositories(value: str) -> list[tuple[str, str]]:
    matches = re.findall(
        r"(?:https?://github\.com/|(?<![\w.-]))([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
        value,
        flags=re.IGNORECASE,
    )
    excluded = {"api", "search", "features", "topics", "marketplace"}
    result = []
    for owner, repo in matches:
        repo = repo.rstrip(".,;:!?/#")
        if owner.lower() not in excluded and repo.lower() not in excluded:
            result.append((owner, repo))
    return list(dict.fromkeys(result))


def candidate_relevance(candidate: ConnectorCandidate, protocol: ResearchProtocol) -> tuple[float, list[str]]:
    question = " ".join([protocol.primary_question, *protocol.sub_questions])
    question_terms = topic_terms(question)
    candidate_text = f"{candidate.title} {candidate.snippet} {candidate.url}"
    candidate_terms = topic_terms(candidate_text)
    overlap = question_terms & candidate_terms
    lexical = len(overlap) / max(1, min(len(question_terms), 8))
    score = min(0.65, lexical * 1.2)
    reasons = [f"term_overlap:{','.join(sorted(overlap)[:8])}"] if overlap else []

    targets = github_repositories(question)
    candidate_value = f"{candidate.title} {candidate.url}".lower()
    if any(f"{owner}/{repo}".lower() in candidate_value for owner, repo in targets):
        score = 1.0
        reasons.append("exact_github_repository")

    trusted = protocol.connectors.trusted_domains
    if trusted and domain_matches(str(candidate.url), trusted):
        score = min(1.0, score + 0.35)
        reasons.append("trusted_domain")
    if candidate.metadata.get("authority") == "official":
        score = min(1.0, score + 0.40)
        reasons.append("official_authority")
    if candidate.metadata.get("authority") == "primary":
        score = min(1.0, score + 0.40)
        reasons.append("primary_authority")
    if candidate.family == SourceFamily.ACADEMIC:
        metadata = candidate.metadata
        if metadata.get("is_retracted"):
            score = max(0.0, score - 0.30)
            reasons.append("retracted_demoted")
        if metadata.get("open_access_location") or metadata.get("inline_fulltext"):
            score = min(1.0, score + 0.05)
            reasons.append("full_text_available")
        publication_types = {
            str(value).lower() for value in metadata.get("publicationTypes", [])
        }
        work_type = str(metadata.get("type") or "").lower()
        if work_type in {"review", "systematic-review", "meta-analysis"} or (
            publication_types & {"review", "meta-analysis"}
        ):
            score = min(1.0, score + 0.05)
            reasons.append("evidence_synthesis_type")
        if set(protocol.connectors.zotero_tags).intersection(metadata.get("tags", [])):
            score = min(1.0, score + 0.10)
            reasons.append("zotero_priority_tag")
        rrf_score = float(metadata.get("federated_rrf_score", 0.0))
        if rrf_score:
            score = min(1.0, score + min(0.10, rrf_score))
            reasons.append("federated_rrf")
    return round(score, 4), reasons


def filter_and_rank_candidates(
    candidates: list[ConnectorCandidate],
    protocol: ResearchProtocol,
    limit: int,
    *,
    minimum_score: float = 0.35,
) -> tuple[list[ConnectorCandidate], list[dict[str, str | float]]]:
    accepted: list[ConnectorCandidate] = []
    rejected: list[dict[str, str | float]] = []
    trusted = protocol.connectors.trusted_domains
    target_repositories = {
        f"{owner}/{repo}".lower() for owner, repo in github_repositories(
            " ".join([protocol.primary_question, *protocol.sub_questions])
        )
    }
    official_entities = resolve_official_entities(protocol.primary_question)
    official_entity_names = [entity["entity"] for entity in official_entities]
    official_entity_domains = [
        domain for entity in official_entities for domain in entity["domains"]
    ]
    for candidate in candidates:
        score, reasons = candidate_relevance(candidate, protocol)
        candidate.metadata["relevance_score"] = score
        candidate.metadata["relevance_reasons"] = reasons
        candidate_path = urlparse(str(candidate.url)).path.strip("/").lower().split("/")
        candidate_repository = "/".join(candidate_path[:2]) if len(candidate_path) >= 2 else ""
        repository_mismatch = (
            bool(target_repositories) and hostname(str(candidate.url)) == "github.com"
            and candidate_repository not in target_repositories
        )
        authority_entity_mismatch = (
            candidate.family == SourceFamily.OFFICIAL_LEGAL
            and bool(official_entity_names)
            and not domain_matches(str(candidate.url), official_entity_domains)
            and not matches_target_entities(
                f"{candidate.title} {candidate.snippet} {candidate.url}",
                official_entity_names,
            )
        )
        if UNTRUSTED_DISCOVERY_PATTERN.search(
            f"{candidate.title} {candidate.snippet}"
        ):
            rejected.append({
                "url": str(candidate.url), "score": score,
                "reason": "untrusted_instruction_pattern",
            })
            continue
        elif authority_entity_mismatch:
            rejected.append({
                "url": str(candidate.url), "score": score,
                "reason": "official_entity_mismatch",
            })
            continue
        elif repository_mismatch:
            rejected.append({
                "url": str(candidate.url), "score": score,
                "reason": "github_repository_mismatch",
            })
            continue
        elif trusted and not domain_matches(str(candidate.url), trusted):
            rejected.append({"url": str(candidate.url), "score": score, "reason": "trusted_domain"})
            continue
        # Academic discovery metadata is often title-only. Preserve recall here;
        # acquired content still has deterministic and LLM admission gates.
        effective_minimum = (
            min(minimum_score, 0.25)
            if candidate.family == SourceFamily.ACADEMIC
            else minimum_score
        )
        if score < effective_minimum:
            rejected.append({"url": str(candidate.url), "score": score, "reason": "low_relevance"})
        else:
            accepted.append(candidate)

    groups: dict[str, deque[ConnectorCandidate]] = defaultdict(deque)
    for candidate in sorted(accepted, key=lambda item: item.metadata["relevance_score"], reverse=True):
        groups[candidate.connector_id].append(candidate)
    selected: list[ConnectorCandidate] = []
    while groups and len(selected) < limit:
        for connector_id in list(groups):
            if groups[connector_id]:
                selected.append(groups[connector_id].popleft())
                if len(selected) >= limit:
                    break
            if not groups[connector_id]:
                del groups[connector_id]
    return selected, rejected


def claim_relevance(text: str, question: str, source_score: float = 0.0) -> float:
    question_terms = topic_terms(question)
    claim_terms = topic_terms(text)
    overlap_count = len(question_terms & claim_terms)
    if overlap_count == 0:
        return 0.0
    lexical = overlap_count / max(1, min(len(question_terms), 8))
    lexical_score = lexical * 1.35 if overlap_count >= 2 else 0.08
    source_bonus = min(0.12, max(0.0, source_score) * 0.12)
    return round(min(1.0, lexical_score + source_bonus), 4)


def document_relevance(
    document: AcquiredDocument,
    protocol: ResearchProtocol,
    questions: list[str] | None = None,
) -> tuple[bool, float, list[str]]:
    """Validate acquired content, not only discovery metadata, against research intent."""
    candidate = document.candidate
    heading = "" if candidate.metadata.get("seeded") else f"{candidate.title} {candidate.snippet}"
    body = document.content[:80_000]
    normalized_heading = " ".join(heading.lower().replace("-", " ").split())
    heading_terms = topic_terms(heading)
    body_terms = topic_terms(body)
    primary_heading_phrases = {
        phrase for phrase in topic_bigrams(protocol.primary_question)
        if phrase in normalized_heading
    }
    best_score = 0.0
    best_reasons: list[str] = []
    best_topic_count = 0
    best_focus_required = False
    best_focus_count = 0
    for question in questions or [protocol.primary_question, *protocol.sub_questions]:
        anchors = topic_terms(question)
        if not anchors:
            continue
        heading_hits = anchors & heading_terms
        body_hits = anchors & body_terms
        all_hits = heading_hits | body_hits
        focus = focus_terms(question)
        focus_hits = focus & (heading_terms | body_terms)
        heading_phrases = {
            phrase for phrase in topic_bigrams(question)
            if phrase in normalized_heading
        }
        heading_coverage = len(heading_hits) / max(1, min(len(anchors), 8))
        body_coverage = len(body_hits) / max(1, min(len(anchors), 8))
        focus_coverage = len(focus_hits) / max(1, min(len(focus), 3)) if focus else 1.0
        score = min(1.0, heading_coverage * 0.55 + body_coverage * 0.30 + focus_coverage * 0.15)
        reasons = [
            f"topic_hits:{','.join(sorted(all_hits)[:10])}",
            f"focus_hits:{','.join(sorted(focus_hits)[:6])}" if focus else "focus:not_explicit",
            f"heading_phrases:{','.join(sorted(heading_phrases)[:5])}",
        ]
        if score > best_score:
            best_score, best_reasons = score, reasons
            best_topic_count = len(all_hits)
            best_focus_required = bool(focus)
            best_focus_count = len(focus_hits)
    has_enough_topic = best_topic_count >= 2
    focus_satisfied = not best_focus_required or best_focus_count > 0
    academic_heading_satisfied = (
        candidate.family != SourceFamily.ACADEMIC
        or bool(primary_heading_phrases)
    )
    accepted = (
        best_score >= 0.35
        and has_enough_topic
        and focus_satisfied
        and academic_heading_satisfied
    )
    candidate.metadata["content_relevance_score"] = round(best_score, 4)
    candidate.metadata["content_relevance_reasons"] = best_reasons
    return accepted, round(best_score, 4), best_reasons


def temporal_relevance(
    candidate: ConnectorCandidate,
    protocol: ResearchProtocol,
    *,
    reject_unknown: bool,
) -> tuple[bool, str]:
    published_at = candidate.published_at
    if published_at is None:
        published_at, basis = publication_datetime(candidate.metadata)
        if published_at is not None:
            candidate.published_at = published_at
            candidate.metadata["published_at"] = published_at.isoformat()
            candidate.metadata["publication_date_basis"] = basis
    accepted, reason = date_scope_decision(
        published_at, protocol.scope.start_date, protocol.scope.end_date,
    )
    if reason == "publication_date_unknown" and not reject_unknown:
        return True, "publication_date_pending"
    return accepted, reason


def evidence_entailment(claim: str, quote: str, model_confidence: float) -> float:
    claim_terms = terms(claim)
    quote_terms = terms(quote)
    coverage = len(claim_terms & quote_terms) / max(1, min(len(claim_terms), 12))
    lexical_ceiling = min(1.0, coverage * 1.5)
    return round(min(model_confidence, lexical_ceiling), 4)
