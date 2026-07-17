from __future__ import annotations

import re

from .schemas import ResearchProtocol


_QUESTION_NOISE = re.compile(
    r"\b(what|which|who|when|where|how|are|is|does|do|please|find|search|"
    r"nedir|nelerdir|nasıl|hangi|araştır|bul|lütfen)\b",
    flags=re.IGNORECASE,
)


def _compact(query: str, limit: int = 18) -> str:
    tokens = re.findall(r"[\w.+:/-]+", query, flags=re.UNICODE)
    useful = [token for token in tokens if not _QUESTION_NOISE.fullmatch(token)]
    return " ".join(list(dict.fromkeys(useful))[:limit])[:500].strip() or query[:500]


def compile_provider_query(
    connector_id: str,
    query: str,
    protocol: ResearchProtocol,
    concepts: list[str] | None = None,
) -> str:
    """Compile one research branch into conservative provider-native syntax.

    Date filters remain the connector's responsibility so they are sent as API fields,
    not brittle free text. The compiler only removes conversational noise and applies
    syntax that the target provider documents and accepts.
    """
    compact = _compact(query)
    concept_tail = " ".join(_compact(item, 3) for item in (concepts or [])[:2])
    enriched = " ".join(dict.fromkeys(f"{compact} {concept_tail}".split()))
    if connector_id == "arxiv":
        terms = [term for term in enriched.split() if len(term) > 2][:12]
        # ArxivConnector owns field/date syntax; pass concise lexical anchors here.
        return " ".join(terms) or compact
    if connector_id in {"crossref", "openalex", "semantic_scholar", "europe_pmc"}:
        return " ".join(enriched.split()[:16])
    if connector_id == "github":
        return " ".join(enriched.split()[:10])
    if connector_id in {"gdelt", "agentsearch_news"}:
        return " ".join(enriched.split()[:12])
    return query[:1000]
