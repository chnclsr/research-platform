from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from .schemas import ConnectorCandidate, SentinelSource, SourceFamily


def relation_to_candidate(
    relation: dict[str, Any],
    *,
    connector_id: str,
    family: SourceFamily,
    parent: ConnectorCandidate,
    depth: int,
) -> ConnectorCandidate | None:
    metadata = dict(relation.get("metadata") or {})
    persistent_id = str(relation.get("target_persistent_id") or "").strip()
    paper_id = str(metadata.get("paperId") or "").strip()
    external = metadata.get("externalIds") or {}
    doi = str(external.get("DOI") or "").lower().removeprefix("https://doi.org/")
    openalex_id = persistent_id.rsplit("/", 1)[-1] if "openalex.org/" in persistent_id else ""
    if persistent_id.startswith("10."):
        doi = persistent_id.lower()
    if doi:
        url = f"https://doi.org/{doi}"
    elif paper_id or connector_id == "semantic_scholar":
        paper_id = paper_id or persistent_id
        url = f"https://www.semanticscholar.org/paper/{paper_id}"
    elif openalex_id or persistent_id.startswith("W"):
        openalex_id = openalex_id or persistent_id
        url = f"https://openalex.org/{openalex_id}"
    elif persistent_id.startswith(("http://", "https://")):
        url = persistent_id
    else:
        return None
    title = str(metadata.get("title") or metadata.get("display_name") or persistent_id or url)
    scholarly_ids = {
        **(metadata.get("scholarly_ids") or {}),
        "doi": doi or None,
        "semantic_scholar_id": paper_id or (
            metadata.get("scholarly_ids") or {}
        ).get("semantic_scholar_id"),
        "openalex_id": openalex_id or (
            metadata.get("scholarly_ids") or {}
        ).get("openalex_id"),
    }
    return ConnectorCandidate(
        connector_id=connector_id,
        family=family,
        title=title,
        url=url,
        snippet=str(metadata.get("abstract") or ""),
        persistent_id=doi or paper_id or openalex_id or persistent_id,
        published_at=metadata.get("publicationDate") or None,
        metadata={
            **metadata,
            "scholarly_ids": scholarly_ids,
            "discovery_method": "citation_frontier",
            "citation_depth": depth,
            "citation_parent_id": parent.id,
            "citation_parent_persistent_id": parent.persistent_id,
            "citation_relation_type": relation.get("relation_type"),
            "provider_snapshots": {connector_id: metadata},
        },
    )


def estimated_completeness(provider_incidence: list[list[str]]) -> tuple[float | None, int]:
    """Bias-corrected incidence estimator over the pooled relevant source set.

    This is a diagnostic, not an absolute recall guarantee. Singleton-heavy pools signal
    that more independent discovery methods are likely to find unseen sources.
    """
    incidence = [len(set(row)) for row in provider_incidence if row]
    observed = len(incidence)
    if observed < 5:
        return None, observed
    frequencies = Counter(incidence)
    q1, q2 = frequencies.get(1, 0), frequencies.get(2, 0)
    unseen = (q1 * q1) / (2 * q2) if q2 else (q1 * max(0, q1 - 1)) / 2
    return round(observed / max(1.0, observed + unseen), 4), observed


def _normal(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower(), flags=re.UNICODE).strip()


def sentinel_recall(
    sentinels: list[SentinelSource],
    discovered_sources: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    required = [item for item in sentinels if item.required]
    if not required:
        return 1.0, []
    missed: list[str] = []
    for sentinel in required:
        found = False
        wanted_pid = _normal(sentinel.persistent_id or "")
        wanted_url = (sentinel.url or "").rstrip("/").lower()
        names = [_normal(sentinel.title), *(_normal(alias) for alias in sentinel.aliases)]
        for source in discovered_sources:
            source_pid = _normal(str(source.get("persistent_id") or ""))
            source_url = str(source.get("url") or "").rstrip("/").lower()
            source_title = _normal(str(source.get("title") or ""))
            if wanted_pid and source_pid == wanted_pid:
                found = True
            elif wanted_url and source_url == wanted_url:
                found = True
            elif any(
                name and SequenceMatcher(None, name, source_title).ratio() >= 0.90
                for name in names
            ):
                found = True
            if found:
                break
        if not found:
            missed.append(sentinel.title)
    return round((len(required) - len(missed)) / len(required), 4), missed
