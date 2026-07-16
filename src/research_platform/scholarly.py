from __future__ import annotations

import re
import unicodedata
from typing import Any

from .schemas import ConnectorCandidate, ScholarlyIdentity, SourceFamily


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_PATTERN.search(value.strip())
    return match.group(0).lower().rstrip(".,;)") if match else None


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    cleaned = cleaned.removeprefix("arxiv:").split("v", 1)[0]
    return cleaned or None


def reconstruct_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return str(inverted_index or "").strip()
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        if not isinstance(indexes, list):
            continue
        positions.extend((int(index), str(word)) for index in indexes)
    return " ".join(word for _, word in sorted(positions))


def scholarly_identity(metadata: dict[str, Any], persistent_id: str | None = None) -> ScholarlyIdentity:
    ids = metadata.get("scholarly_ids") or {}
    external = metadata.get("externalIds") or metadata.get("ids") or {}
    doi = normalize_doi(
        ids.get("doi") or external.get("DOI") or metadata.get("doi") or persistent_id
    )
    arxiv = normalize_arxiv_id(ids.get("arxiv_id") or external.get("ArXiv"))
    return ScholarlyIdentity(
        doi=doi,
        openalex_id=ids.get("openalex_id") or metadata.get("openalex_id"),
        semantic_scholar_id=(
            ids.get("semantic_scholar_id") or metadata.get("paperId")
        ),
        corpus_id=str(ids.get("corpus_id") or metadata.get("corpusId") or "") or None,
        arxiv_id=arxiv,
        pmid=str(ids.get("pmid") or external.get("PubMed") or "") or None,
        pmcid=str(ids.get("pmcid") or external.get("PubMedCentral") or "") or None,
        isbn=ids.get("isbn"),
        zotero_item_key=ids.get("zotero_item_key") or metadata.get("zotero_item_key"),
    )


def candidate_dedupe_key(candidate: ConnectorCandidate) -> str:
    if candidate.family == SourceFamily.ACADEMIC:
        identity = scholarly_identity(candidate.metadata, candidate.persistent_id)
        for prefix, value in (
            ("doi", identity.doi),
            ("pmid", identity.pmid),
            ("pmcid", identity.pmcid),
            ("arxiv", identity.arxiv_id),
            ("openalex", identity.openalex_id),
            ("s2", identity.semantic_scholar_id),
        ):
            if value:
                return f"{prefix}:{value}".lower()
    return (candidate.persistent_id or str(candidate.url)).lower()


def title_fingerprint(title: str, authors: list[str], year: str | int | None) -> str:
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(character for character in text if not unicodedata.combining(character))
    words = " ".join(re.findall(r"[a-z0-9]+", text))
    first_author = authors[0].lower().strip() if authors else ""
    return f"title:{words}|author:{first_author}|year:{year or ''}"


def provider_snapshot(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"provider": provider, "payload": payload}
