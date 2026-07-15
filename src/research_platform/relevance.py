from __future__ import annotations

import re
from collections import defaultdict, deque
from urllib.parse import urlparse

from .schemas import ConnectorCandidate, ResearchProtocol


STOPWORDS = {
    "about", "after", "also", "and", "are", "based", "bir", "bu", "does", "for",
    "from", "gibi", "how", "ile", "into", "its", "local", "nelerdir", "nedir", "olan",
    "olarak", "the", "their", "this", "use", "used", "uses", "what", "when", "where",
    "which", "who", "why", "with", "icin", "için", "ve", "veya",
}


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
    question_terms = terms(question)
    candidate_text = f"{candidate.title} {candidate.snippet} {candidate.url}"
    candidate_terms = terms(candidate_text)
    overlap = question_terms & candidate_terms
    lexical = len(overlap) / max(1, min(len(question_terms), 10))
    score = min(0.65, lexical * 1.5)
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
    return round(score, 4), reasons


def filter_and_rank_candidates(
    candidates: list[ConnectorCandidate],
    protocol: ResearchProtocol,
    limit: int,
    *,
    minimum_score: float = 0.20,
) -> tuple[list[ConnectorCandidate], list[dict[str, str | float]]]:
    accepted: list[ConnectorCandidate] = []
    rejected: list[dict[str, str | float]] = []
    trusted = protocol.connectors.trusted_domains
    target_repositories = {
        f"{owner}/{repo}".lower() for owner, repo in github_repositories(
            " ".join([protocol.primary_question, *protocol.sub_questions])
        )
    }
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
        if repository_mismatch:
            rejected.append({
                "url": str(candidate.url), "score": score,
                "reason": "github_repository_mismatch",
            })
        elif trusted and not domain_matches(str(candidate.url), trusted):
            rejected.append({"url": str(candidate.url), "score": score, "reason": "trusted_domain"})
        elif score < minimum_score:
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
    question_terms = terms(question)
    claim_terms = terms(text)
    overlap_count = len(question_terms & claim_terms)
    lexical = overlap_count / max(1, min(len(question_terms), 10))
    lexical_score = lexical * 1.5 if overlap_count >= 2 else overlap_count * 0.15
    return round(min(1.0, max(source_score * 0.9, lexical_score)), 4)


def evidence_entailment(claim: str, quote: str, model_confidence: float) -> float:
    claim_terms = terms(claim)
    quote_terms = terms(quote)
    coverage = len(claim_terms & quote_terms) / max(1, min(len(claim_terms), 12))
    lexical_ceiling = min(1.0, coverage * 1.5)
    return round(min(model_confidence, lexical_ceiling), 4)
