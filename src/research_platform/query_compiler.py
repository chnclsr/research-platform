from __future__ import annotations

import re

from .recovery import SATURATION_PROBE_SCAFFOLD
from .relevance import TERM_ALIASES, github_repositories
from .schemas import ResearchProtocol

# The saturation probe's bookkeeping tail, removed here rather than at the source: the
# mission signature is the query verbatim, so recovery needs the counter to keep each
# round's probe a distinct mission. Stripping it downstream of the signature gives the
# provider the question and recovery its identity.
_PROBE_SCAFFOLD = re.compile(
    rf"\s*{re.escape(SATURATION_PROBE_SCAFFOLD)}\s+\d+", flags=re.IGNORECASE
)

_QUESTION_NOISE = re.compile(
    r"\b(a|an|and|as|at|by|for|in|of|on|or|than|the|to|what|which|who|"
    r"when|where|how|are|is|does|do|please|find|search|"
    r"nedir|nelerdir|nasıl|hangi|araştır|bul|lütfen)\b",
    flags=re.IGNORECASE,
)

_ANCHOR_NOISE = {
    "a", "an", "and", "as", "at", "between", "by", "compare", "compared",
    "evidence", "evaluate", "evaluates", "for", "in", "of", "on", "or", "the", "to",
    "evaluation", "finding", "findings", "from", "latest", "published", "recent",
    "research", "result", "results", "show", "shows", "study", "studies", "using",
    "what", "which", "with", "year", "years",
    # Research-prompt verbs. They say how the question was asked, never what it is about,
    # and against a provider that ANDs its terms they can only subtract matches. Kept out
    # deliberately: `review` ("systematic review" is a real search term) and
    # `report`/`reports`, which are the subject of entire research questions here.
    "analyse", "analyze", "assess", "describe", "determine", "examine", "examines",
    "explore", "explores", "identify", "investigate", "investigates", "investigating",
    "summarise", "summarize",
}

# Short but load-bearing: modality and method acronyms are the terms a provider indexes,
# and the >= 3 rule below would drop every one of them. Mirrors `relevance.terms()`.
_SHORT_ANCHORS = {"ai", "bt", "ct"}

_TOKEN = re.compile(r"[\w.+:/-]+", flags=re.UNICODE)
# Only the edges. Inside a token these characters carry meaning -- `v1.2`, `SARS-CoV-2`,
# `owner/repo`, `in:name` -- but a sentence's full stop travelling with the last word makes
# `images.` a term no index holds, and it reached the providers exactly that way. `+` is
# never trimmed: `C++` and `g++` are things people search for.
_TOKEN_EDGE = re.compile(r"^[.:/-]+|[.:/-]+$")


def _tokens(value: str) -> list[str]:
    return [token for raw in _TOKEN.findall(value) if (token := _TOKEN_EDGE.sub("", raw))]


def _compact(query: str, limit: int = 18) -> str:
    useful = [token for token in _tokens(query) if not _QUESTION_NOISE.fullmatch(token)]
    return " ".join(list(dict.fromkeys(useful))[:limit])[:500].strip() or query[:500]


def _primary_anchors(question: str, limit: int = 8) -> str:
    """Keep the subject of the main question in every literature-search branch."""
    useful = [
        token
        for token in _tokens(question)
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
        for token in _tokens(value.lower()):
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
            if (
                token.isascii()
                and (len(token) >= 3 or token in _SHORT_ANCHORS)
                and token not in _ANCHOR_NOISE
            ):
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


# A GitHub term may not carry `/` or `:`: the first makes the connector fetch a repository
# instead of searching, the second is read as a qualifier.
_GITHUB_TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]*")
_GITHUB_TERM_LIMIT = 3
_GITHUB_ANCHOR_LIMIT = 4
# Without this, repository search reads name, description and topics only -- roughly one
# sentence -- and ANDs every term against it, which is how a ten-word sentence came back
# HTTP 200 with zero items. The qualifier widens the text surface enough for a small AND
# to be satisfiable. It carries no `/`, so it cannot trip the exact-repository lookup.
_GITHUB_FIELDS = "in:name,description,topics,readme"


def _github_query(
    query: str, enriched: str, protocol: ResearchProtocol, concepts: list[str],
) -> str:
    """Few terms, translated, and never a stray slash or colon.

    GitHub ANDs free-text terms, so miss probability compounds with every word: the fix for
    a zero-result sentence is a shorter query, not a better-ordered one. Terms come from the
    approved scope facets rather than from where a word happened to sit in the question --
    `_arxiv_query` learned the same lesson, and its comment says why: the old
    position-dependent first-three-token AND made conversational verbs fatal.
    """
    repositories = github_repositories(enriched)
    if repositories and "github" in enriched.casefold():
        # An explicit target, made deliberate. GitHubConnector fetches this repository
        # directly instead of searching. Requiring the word `github` keeps incidental
        # slashes -- `2024/01`, `and/or` -- out of this branch.
        owner, repo = repositories[0]
        return f"{owner}/{repo}"

    facets = getattr(protocol.scope_criteria, "required_facets", None) or []
    picked: list[tuple[int, int, str]] = []
    for order, facet in enumerate(facets):
        value = next(
            (
                candidate
                for raw in facet.accepted_values
                if (candidate := raw.strip()) and _GITHUB_TERM.fullmatch(candidate)
            ),
            None,
        )
        if value:
            # Most specific first: a facet whose approved value is a phrase says more than
            # one that is a single word, and protocol order is not a ranking -- taking it
            # literally spent the budget on `chest CT 3D` and dropped the task facet.
            picked.append((-len(value.split()), order, value))
    picked.sort()
    terms = [
        f'"{value}"' if " " in value else value
        for _, _, value in picked[:_GITHUB_TERM_LIMIT]
    ]

    if not terms:
        # Legacy protocols approved no facets. Anchors are ordered by position, so allow one
        # more term than the facet path: measured on the incident question, the first three
        # were `artificial intelligence writing` and the subject word came fourth.
        terms = [
            token
            for token in _academic_english_anchors(
                protocol.primary_question, query, " ".join(concepts), limit=12
            ).split()
            if _GITHUB_TERM.fullmatch(token)
        ][:_GITHUB_ANCHOR_LIMIT]
    if not terms:
        terms = [token for token in _tokens(query) if _GITHUB_TERM.fullmatch(token)][
            :_GITHUB_ANCHOR_LIMIT
        ]
    if not terms:
        # GitHub answers an empty `q` with 422; send the old shape rather than nothing.
        return " ".join(enriched.split()[:10])
    return " ".join([*terms, _GITHUB_FIELDS])


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
    query = _PROBE_SCAFFOLD.sub("", query).strip() or query
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
        return _github_query(query, enriched, protocol, concepts or [])
    if connector_id in {"gdelt", "agentsearch_news"}:
        return " ".join(enriched.split()[:12])
    # General web backends are the least tolerant of long natural-language recovery
    # prompts. Preserve exact short title searches, otherwise send concise anchors.
    if '"' in query and len(query) <= 250:
        return query
    return " ".join(enriched.split()[:24])[:500]
