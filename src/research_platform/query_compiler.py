from __future__ import annotations

import re

from .relevance import TERM_ALIASES
from .schemas import ResearchProtocol

_QUESTION_NOISE = re.compile(
    r"\b(what|which|who|when|where|how|are|is|does|do|please|find|search|"
    r"nedir|nelerdir|nasıl|hangi|araştır|bul|lütfen)\b",
    flags=re.IGNORECASE,
)

_ANCHOR_NOISE = {
    "between", "compare", "compared", "evidence", "evaluate", "evaluates",
    "evaluation", "finding", "findings", "from", "latest", "published", "recent",
    "research", "result", "results", "show", "shows", "study", "studies", "using",
    "what", "which", "with", "year", "years",
}


def _compact(query: str, limit: int = 18) -> str:
    tokens = re.findall(r"[\w.+:/-]+", query, flags=re.UNICODE)
    useful = [token for token in tokens if not _QUESTION_NOISE.fullmatch(token)]
    return " ".join(list(dict.fromkeys(useful))[:limit])[:500].strip() or query[:500]


def _primary_anchors(question: str, limit: int = 8) -> str:
    """Keep the subject of the main question in every literature-search branch."""
    tokens = re.findall(r"[\w.+:/-]+", question, flags=re.UNICODE)
    useful = [
        token
        for token in tokens
        if (
            len(token) >= 3
            and not token.isdigit()
            and not _QUESTION_NOISE.fullmatch(token)
            and token.lower() not in _ANCHOR_NOISE
        )
    ]
    return " ".join(list(dict.fromkeys(useful))[:limit])[:240].strip()


def _academic_english_anchors(*values: str, limit: int = 16) -> str:
    """Translate known domain terms before provider truncation.

    Academic APIs work best with concise English concepts.  Keeping translated
    anchors first prevents a long Turkish question or recovery prompt from
    consuming the provider's entire lexical budget before its key concepts.
    """
    preferred = (
        "lung", "cancer", "chest", "ct", "imaging", "ai", "nodule",
        "malignancy", "detection", "screening", "prediction", "validation",
    )
    preference = {token: index for index, token in enumerate(preferred)}
    primary_aliases: list[str] = []
    secondary_aliases: list[str] = []
    literal_anchors: list[str] = []
    for value in values:
        for token in re.findall(r"[\w.+:/-]+", value.lower(), flags=re.UNICODE):
            if token.isdigit() or _QUESTION_NOISE.fullmatch(token):
                continue
            aliases = TERM_ALIASES.get(token)
            if aliases:
                ordered = sorted(
                    aliases,
                    key=lambda alias: (preference.get(alias, len(preference)), alias),
                )
                primary_aliases.append(ordered[0])
                secondary_aliases.extend(ordered[1:])
                continue
            if token.isascii() and len(token) >= 3 and token not in _ANCHOR_NOISE:
                literal_anchors.append(token)
    anchors = list(
        dict.fromkeys([*primary_aliases, *literal_anchors, *secondary_aliases])
    )
    return " ".join(anchors[:limit])


def _arxiv_term(value: str) -> str:
    """Render one literal concept without letting model text become field syntax."""
    cleaned = " ".join(re.findall(r"[A-Za-z0-9.+_-]+", value))[:100]
    if not cleaned:
        return ""
    return f'all:"{cleaned}"' if " " in cleaned else f"all:{cleaned}"


def _arxiv_query(
    query: str,
    protocol: ResearchProtocol,
    concepts: list[str],
) -> str:
    """Compile required concept groups instead of AND-ing the first three words."""
    groups: list[str] = []
    facet_tokens: set[str] = set()
    if protocol.scope_criteria is not None:
        for facet in protocol.scope_criteria.required_facets:
            values = list(dict.fromkeys(value.strip() for value in facet.accepted_values if value.strip()))
            rendered = [item for value in values[:5] if (item := _arxiv_term(value))]
            if rendered:
                groups.append(f"({' OR '.join(rendered)})")
            for value in values:
                facet_tokens.update(re.findall(r"[a-z0-9]+", value.casefold()))

    # Give each sub-question its own branch while retaining every approved mandatory
    # boundary. The primary branch needs no extra term: it is the high-recall route.
    if query.strip().casefold() != protocol.primary_question.strip().casefold():
        branch = [
            token
            for token in _academic_english_anchors(query, " ".join(concepts), limit=8).split()
            if token.casefold() not in facet_tokens
        ][:3]
        rendered = [item for token in branch if (item := _arxiv_term(token))]
        if rendered:
            groups.append(f"({' OR '.join(rendered)})")

    if groups:
        return " AND ".join(groups)
    # Legacy protocols have no approved facets. Prefer a small OR concept group over the
    # old position-dependent first-three-token AND, which made conversational verbs fatal.
    anchors = _academic_english_anchors(
        protocol.primary_question,
        query,
        " ".join(concepts),
        limit=8,
    ).split()
    rendered = [item for token in anchors if (item := _arxiv_term(token))]
    return f"({' OR '.join(rendered)})" if rendered else _arxiv_term(_compact(query, 4))


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
    if protocol.research_mode == "literature_scan":
        primary = _primary_anchors(protocol.primary_question)
        compact = " ".join(dict.fromkeys(f"{compact} {primary}".split()))
    concept_tail = " ".join(_compact(item, 3) for item in (concepts or [])[:2])
    enriched = " ".join(dict.fromkeys(f"{compact} {concept_tail}".split()))
    if connector_id == "arxiv":
        return _arxiv_query(query, protocol, concepts or [])
    if connector_id in {"crossref", "openalex", "semantic_scholar", "europe_pmc"}:
        translated = _academic_english_anchors(
            protocol.primary_question,
            query,
            " ".join(concepts or []),
        )
        return translated or " ".join(enriched.split()[:16])
    if connector_id == "github":
        return " ".join(enriched.split()[:10])
    if connector_id in {"gdelt", "agentsearch_news"}:
        return " ".join(enriched.split()[:12])
    # General web backends are the least tolerant of long natural-language recovery
    # prompts. Preserve exact short title searches, otherwise send concise anchors.
    if '"' in query and len(query) <= 250:
        return query
    return " ".join(enriched.split()[:24])[:500]
