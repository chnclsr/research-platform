from __future__ import annotations

from collections import Counter
from typing import Any

from .schemas import (
    AuthorityLevel,
    ConnectorCandidate,
    CoverageGap,
    CoverageMetrics,
    ResearchProtocol,
    SearchMission,
    SourceFamily,
)


OFFICIAL_ENTITY_REGISTRY: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = (
    (("model context protocol", " mcp ", "mcp taban"), "Model Context Protocol", ("modelcontextprotocol.io",)),
    (
        ("codex", "openai"),
        "OpenAI Codex",
        ("developers.openai.com", "learn.chatgpt.com", "openai.com"),
    ),
    (("claude code", "anthropic"), "Claude Code", ("code.claude.com", "docs.anthropic.com", "anthropic.com")),
    (("telegram", "bot api"), "Telegram Bot API", ("core.telegram.org",)),
)

OFFICIAL_SEED_URLS: dict[str, list[str]] = {
    "Model Context Protocol": [
        "https://modelcontextprotocol.io/docs/tutorials/security/authorization",
    ],
    "OpenAI Codex": [
        "https://developers.openai.com/codex/mcp/",
        "https://developers.openai.com/codex/security/",
    ],
    "Claude Code": [
        "https://code.claude.com/docs/en/mcp",
        "https://code.claude.com/docs/en/security",
    ],
    "Telegram Bot API": [
        "https://core.telegram.org/bots/api",
        "https://core.telegram.org/bots/faq",
    ],
}

CODE_SEED_URLS: dict[str, list[str]] = {
    "Model Context Protocol": [
        "https://github.com/modelcontextprotocol/modelcontextprotocol",
    ],
    "OpenAI Codex": ["https://github.com/openai/codex"],
    "Claude Code": ["https://github.com/anthropics/claude-code"],
}

ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Model Context Protocol": ("model context protocol", "mcp"),
    "OpenAI Codex": ("openai codex", "codex"),
    "Claude Code": ("claude code",),
    "Telegram Bot API": ("telegram bot api", "telegram"),
}


FAMILY_CONNECTORS: dict[SourceFamily, list[str]] = {
    SourceFamily.WEB: ["agentsearch_web"],
    SourceFamily.ACADEMIC: [
        "openalex", "semantic_scholar", "arxiv", "crossref", "europe_pmc",
        "zotero_local", "zotero_web",
    ],
    SourceFamily.OFFICIAL_LEGAL: ["official_registry", "eur_lex", "federal_register"],
    SourceFamily.CODE_DATA: ["github", "huggingface", "zenodo", "datacite"],
    SourceFamily.BOOKS_THESES: ["open_library", "openalex_dissertations"],
    SourceFamily.PATENTS_STANDARDS: ["ietf_datatracker", "standards_web", "epo_ops"],
    SourceFamily.NEWS_ARCHIVES: ["agentsearch_news", "gdelt", "internet_archive_cdx"],
    SourceFamily.COMPANY: ["sec_edgar", "company_domains"],
    SourceFamily.GREY_LITERATURE: ["zenodo_grey", "institutional_grey"],
}


def resolve_official_entities(question: str) -> list[dict[str, Any]]:
    normalized = f" {question.lower()} "
    output = []
    for triggers, entity, domains in OFFICIAL_ENTITY_REGISTRY:
        if any(trigger in normalized for trigger in triggers):
            output.append({"entity": entity, "domains": list(domains)})
    return output


def initial_missions(
    protocol: ResearchProtocol,
    queries: list[str],
) -> list[SearchMission]:
    missions: list[SearchMission] = []
    included = set(protocol.connectors.included_connectors)
    for index, sentinel in enumerate(
        item for item in protocol.sentinel_sources if item.required
    ):
        identity = sentinel.persistent_id or sentinel.title
        academic = bool(
            (sentinel.persistent_id or "").lower().startswith(("arxiv:", "10."))
            or "arxiv.org" in str(sentinel.url or "")
            or "doi.org" in str(sentinel.url or "")
        )
        family = SourceFamily.ACADEMIC if academic else SourceFamily.WEB
        connector_ids = list(FAMILY_CONNECTORS[family])
        if included:
            connector_ids = [item for item in connector_ids if item in included]
        if "agentsearch_web" in included and "agentsearch_web" not in connector_ids:
            connector_ids.append("agentsearch_web")
        missions.append(SearchMission(
            branch_id=f"sentinel:{index}",
            query=f'"{sentinel.title}" {identity}',
            connector_ids=connector_ids,
            seed_urls=[sentinel.url] if sentinel.url else [],
            required_family=family,
            required_authority=AuthorityLevel.PRIMARY,
            result_limit=min(10, protocol.budget.results_per_connector),
            acquisition_slots=1,
        ))
    entities = resolve_official_entities(protocol.primary_question)
    if protocol.authority_policy.minimum_authority == AuthorityLevel.OFFICIAL:
        for entity in entities:
            for domain in entity["domains"][:1]:
                seed_urls = [
                    url for url in OFFICIAL_SEED_URLS.get(entity["entity"], [])
                    if domain in url
                ]
                missions.append(SearchMission(
                    branch_id=f"official:{entity['entity']}",
                    query=f"{entity['entity']} {protocol.primary_question}",
                    connector_ids=["official_registry"],
                    seed_urls=seed_urls,
                    target_entities=[entity["entity"]],
                    domain_allowlist=[domain],
                    required_family=SourceFamily.OFFICIAL_LEGAL,
                    required_authority=AuthorityLevel.OFFICIAL,
                    result_limit=min(10, protocol.budget.results_per_connector),
                    acquisition_slots=1,
                ))
    if SourceFamily.CODE_DATA in protocol.connectors.included_families:
        for entity in entities:
            seed_urls = CODE_SEED_URLS.get(entity["entity"], [])
            if not seed_urls:
                continue
            missions.append(SearchMission(
                branch_id=f"code:{entity['entity']}",
                query=f"{entity['entity']} official source repository security",
                connector_ids=["github"],
                seed_urls=seed_urls,
                target_entities=[entity["entity"]],
                required_family=SourceFamily.CODE_DATA,
                required_authority=AuthorityLevel.PRIMARY,
                result_limit=min(10, protocol.budget.results_per_connector),
                acquisition_slots=1,
            ))
    targeted_families = [
        family for family, target in protocol.family_targets.items()
        if target.minimum_sources > 0
    ] or protocol.connectors.included_families
    connector_ids = list(dict.fromkeys(
        connector
        for family in targeted_families
        for connector in FAMILY_CONNECTORS.get(family, [])
    ))
    acquisition_slots = 5 if protocol.research_mode == "literature_scan" else 2
    for index, query in enumerate(queries[:8]):
        missions.append(SearchMission(
            branch_id=f"query:{index}",
            query=query,
            connector_ids=connector_ids,
            result_limit=protocol.budget.results_per_connector,
            acquisition_slots=acquisition_slots,
        ))
    return missions


def literature_scan_probe_missions(
    protocol: ResearchProtocol,
    round_number: int,
    attempted_signatures: set[str] | None = None,
) -> list[SearchMission]:
    """Create diversified recall probes when ordinary gap missions are exhausted.

    Literature scans should use their collection budget to try a genuinely different
    search strategy instead of declaring completion after the same gap query was seen.
    """
    strategies = (
        "systematic review meta-analysis scoping review",
        "prospective cohort trial external validation multicenter",
        "negative results limitations failure bias safety",
        "guideline consensus regulatory real-world implementation",
        "dataset benchmark replication independent evaluation",
        "citation review related work references",
    )
    attempted_signatures = attempted_signatures or set()
    first_strategy = (max(1, round_number) - 1) % len(strategies)
    families = [
        family
        for family, target in protocol.family_targets.items()
        if target.minimum_sources > 0
    ] or list(protocol.connectors.included_families)
    for offset in range(len(strategies)):
        strategy = strategies[(first_strategy + offset) % len(strategies)]
        missions: list[SearchMission] = []
        for family in families:
            connector_ids = FAMILY_CONNECTORS.get(family, [])
            if protocol.connectors.included_connectors:
                connector_ids = [
                    connector_id
                    for connector_id in connector_ids
                    if connector_id in protocol.connectors.included_connectors
                ]
            if not connector_ids:
                continue
            mission = SearchMission(
                branch_id=f"literature:{family.value}:{round_number}",
                query=f"{protocol.primary_question} {strategy}",
                connector_ids=connector_ids,
                required_family=family,
                result_limit=protocol.budget.results_per_connector,
                acquisition_slots=min(10, protocol.budget.results_per_connector),
                novelty_required=True,
            )
            if mission_signature(mission) not in attempted_signatures:
                missions.append(mission)
        if missions:
            return missions
    return []


def targeted_connector_ids(protocol: ResearchProtocol) -> list[str]:
    families = [
        family for family, target in protocol.family_targets.items()
        if target.minimum_sources > 0
    ] or protocol.connectors.included_families
    return list(dict.fromkeys(
        connector
        for family in families
        for connector in FAMILY_CONNECTORS.get(family, [])
    ))


def diagnose_gaps(
    protocol: ResearchProtocol,
    coverage: CoverageMetrics,
    source_families: list[str],
    unresolved_claims: list[dict[str, str]],
    branch_result_counts: dict[str, int] | None = None,
    branch_queries: dict[str, str] | None = None,
    missed_sentinels: list[str] | None = None,
) -> list[CoverageGap]:
    gaps: list[CoverageGap] = []
    branch_result_counts = branch_result_counts or {}
    branch_queries = branch_queries or {}
    counts = Counter(source_families)
    for title in missed_sentinels or []:
        gaps.append(CoverageGap(
            dimension="sentinel",
            topic=title,
            branch_id=f"sentinel:{title}",
            missing_family=SourceFamily.ACADEMIC,
            preferred_connectors=FAMILY_CONNECTORS[SourceFamily.ACADEMIC],
            minimum_novel_sources=1,
            priority=1.0,
        ))
    for family, target in protocol.family_targets.items():
        missing = max(0, target.minimum_sources - counts.get(family.value, 0))
        if missing:
            gaps.append(CoverageGap(
                dimension="source_family",
                topic=f"{family.value} evidence for {protocol.primary_question}",
                missing_family=family,
                target_entities=(
                    [
                        entity["entity"]
                        for entity in resolve_official_entities(protocol.primary_question)
                    ]
                    if family in {
                        SourceFamily.CODE_DATA,
                        SourceFamily.OFFICIAL_LEGAL,
                    }
                    else []
                ),
                preferred_connectors=FAMILY_CONNECTORS.get(family, []),
                minimum_novel_sources=missing,
                priority=0.85,
            ))
    if (
        protocol.authority_policy.minimum_authority == AuthorityLevel.OFFICIAL
        and coverage.authority_coverage < 1.0
    ):
        for entity in resolve_official_entities(protocol.primary_question):
            gaps.append(CoverageGap(
                dimension="authority",
                topic=f"Official documentation for {entity['entity']}",
                required_authority=AuthorityLevel.OFFICIAL,
                target_entities=[entity["entity"]],
                target_domains=entity["domains"],
                preferred_connectors=["official_registry"],
                priority=1.0,
            ))
    for claim in unresolved_claims[:3]:
        gaps.append(CoverageGap(
            dimension="claim_support",
            topic=claim["text"],
            claim_ids=[claim["id"]],
            required_authority=protocol.authority_policy.minimum_authority,
            preferred_connectors=targeted_connector_ids(protocol),
            priority=0.75,
        ))
    for branch_id, count in branch_result_counts.items():
        if count > 0:
            continue
        query = branch_queries.get(branch_id)
        if not query:
            continue
        target_entities: list[str] = []
        missing_family = None
        required_authority = AuthorityLevel.ANY
        target_domains: list[str] = []
        preferred_connectors = targeted_connector_ids(protocol)
        if branch_id.startswith("code:"):
            target_entities = [branch_id.split(":", 1)[1]]
            missing_family = SourceFamily.CODE_DATA
            required_authority = AuthorityLevel.PRIMARY
            preferred_connectors = FAMILY_CONNECTORS[SourceFamily.CODE_DATA]
        elif branch_id.startswith("official:"):
            target_entities = [branch_id.split(":", 1)[1]]
            missing_family = SourceFamily.OFFICIAL_LEGAL
            required_authority = AuthorityLevel.OFFICIAL
            preferred_connectors = ["official_registry"]
            target_domains = [
                domain
                for entity in resolve_official_entities(protocol.primary_question)
                if entity["entity"] in target_entities
                for domain in entity["domains"]
            ]
        gaps.append(CoverageGap(
            dimension="query_branch",
            topic=query,
            branch_id=branch_id,
            missing_family=missing_family,
            required_authority=required_authority,
            target_entities=target_entities,
            target_domains=target_domains,
            preferred_connectors=preferred_connectors,
            minimum_novel_sources=1,
            priority=0.70,
        ))
    if (
        coverage.saturated_rounds < protocol.stopping_criteria.saturation_rounds
        and (
            coverage.query_branch_coverage
            >= protocol.stopping_criteria.minimum_query_branch_coverage
            or not any(gap.dimension == "query_branch" for gap in gaps)
        )
    ):
        best_branch = next(iter(branch_result_counts), None)
        gaps.append(CoverageGap(
            dimension="query_branch",
            topic=(
                f"{protocol.primary_question} independent recent evidence "
                f"saturation probe {coverage.saturated_rounds + 1}"
            ),
            branch_id=best_branch,
            preferred_connectors=targeted_connector_ids(protocol),
            minimum_novel_sources=1,
            priority=0.55,
        ))
    return gaps


def recovery_missions(
    protocol: ResearchProtocol,
    gaps: list[CoverageGap],
    attempted_signatures: set[str],
) -> list[SearchMission]:
    missions: list[SearchMission] = []
    for gap in sorted(gaps, key=lambda item: item.priority, reverse=True):
        domains = gap.target_domains or [""]
        for domain in domains[:2]:
            connector_ids = gap.preferred_connectors or ["agentsearch_web"]
            seed_registry = (
                CODE_SEED_URLS
                if gap.missing_family == SourceFamily.CODE_DATA
                else (
                    OFFICIAL_SEED_URLS
                    if gap.missing_family == SourceFamily.OFFICIAL_LEGAL
                    or gap.dimension == "authority"
                    else {}
                )
            )
            seed_urls = [
                url
                for entity in gap.target_entities
                for url in seed_registry.get(entity, [])
                if not domain or domain in url
            ]
            query_suffix = {
                "authority": "official documentation security authentication",
                "source_family": "primary source evidence",
                "claim_support": "independent evidence limitations",
                "counterevidence": "counter evidence",
                "query_branch": "evidence",
                "version": "latest version",
                "sentinel": "exact title persistent identifier",
            }[gap.dimension]
            sentinel = next(
                (
                    item for item in protocol.sentinel_sources
                    if item.title == gap.topic
                ),
                None,
            )
            if sentinel is not None:
                identity = sentinel.persistent_id or sentinel.title
                query = f'"{sentinel.title}" {identity}'
                seed_urls = [sentinel.url] if sentinel.url else []
            else:
                query = f"{gap.topic} {query_suffix}"
            acquisition_slots = (
                min(
                    protocol.budget.results_per_connector,
                    max(5, gap.minimum_novel_sources),
                )
                if protocol.research_mode == "literature_scan"
                else min(2, gap.minimum_novel_sources)
            )
            mission = SearchMission(
                gap_id=gap.id,
                branch_id=gap.branch_id or f"gap:{gap.id}",
                query=query,
                connector_ids=connector_ids,
                seed_urls=seed_urls,
                target_entities=gap.target_entities,
                domain_allowlist=[domain] if domain else [],
                required_family=gap.missing_family,
                required_authority=(
                    AuthorityLevel.PRIMARY
                    if gap.missing_family == SourceFamily.CODE_DATA
                    and gap.required_authority == AuthorityLevel.ANY
                    else gap.required_authority
                ),
                result_limit=min(10, protocol.budget.results_per_connector),
                acquisition_slots=acquisition_slots,
            )
            signature = mission_signature(mission)
            if signature in attempted_signatures:
                continue
            missions.append(mission)
            attempted_signatures.add(signature)
    return missions[:20] if protocol.research_mode == "literature_scan" else missions[:10]


def mission_signature(mission: SearchMission) -> str:
    return (
        f"{mission.query}|"
        f"{','.join(mission.domain_allowlist)}|{','.join(mission.connector_ids)}|"
        f"{','.join(str(url) for url in mission.seed_urls)}|"
        f"{','.join(mission.target_entities)}"
    )


def matches_target_entities(value: str, target_entities: list[str]) -> bool:
    normalized = " ".join(value.lower().replace("-", " ").replace("_", " ").split())
    return any(
        alias in normalized
        for entity in target_entities
        for alias in ENTITY_ALIASES.get(entity, (entity.lower(),))
    )


def select_mission_balanced_candidates(
    candidates: list[ConnectorCandidate],
    missions: list[SearchMission],
    limit: int,
) -> list[ConnectorCandidate]:
    """Reserve acquisition capacity across missions before filling by global rank."""
    if limit <= 0:
        return []
    selected: list[ConnectorCandidate] = []
    selected_ids: set[str] = set()
    for mission in missions:
        taken = 0
        for candidate in candidates:
            if candidate.id in selected_ids:
                continue
            # Mission diversity must not spend scarce acquisition slots on a
            # weak title-only match merely because that branch produced no
            # strong result.  Weak candidates remain available to the global
            # fill and reserve audit paths.
            if (
                "relevance_score" in candidate.metadata
                and float(candidate.metadata["relevance_score"]) < 0.45
            ):
                continue
            if mission.branch_id not in candidate.metadata.get("query_branches", []):
                continue
            selected.append(candidate)
            selected_ids.add(candidate.id)
            taken += 1
            if len(selected) >= limit:
                return selected
            if taken >= mission.acquisition_slots:
                break
    for candidate in candidates:
        if candidate.id in selected_ids:
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected
