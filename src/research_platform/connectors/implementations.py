from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .base import ConnectorQueryError, CredentialOnlyConnector, SourceConnector
from ..rate_limits import shared_domain_limiter
from ..relevance import github_repositories, topic_terms
from ..schemas import ConnectorCandidate, ResearchScope, SourceFamily
from ..scholarly import normalize_doi, reconstruct_abstract
from ..temporal import parse_datetime

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"<[^>]+>", " ", html.unescape(str(value))).strip()


class AgentSearchConnector(SourceConnector):
    id = "agentsearch_web"
    family = SourceFamily.WEB
    capabilities = ("search", "metadata", "content")

    def __init__(self, *args, mode: str = "general", domain: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.domain = domain

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_with_domain(query, limit, self.domain)

    async def search_with_domain(
        self, query: str, limit: int = 20, domain: str | None = None,
    ) -> list[ConnectorCandidate]:
        params: dict[str, Any] = {"q": query, "count": min(limit, 50), "mode": self.mode}
        if domain:
            params["domain"] = domain
        response = await self.client.get(f"{self.settings.agentsearch_url}/search", params=params)
        response.raise_for_status()
        output = []
        for row in response.json().get("results", []):
            item = self.candidate(
                title=row.get("title", ""), url=row.get("url", ""),
                snippet=row.get("snippet", ""), metadata={
                    "engines": row.get("engines", []),
                    "authority": "official" if domain else "unknown",
                    "searched_domain": domain,
                },
            )
            if item:
                output.append(item)
        return output


class OpenAlexConnector(SourceConnector):
    id = "openalex"
    family = SourceFamily.ACADEMIC
    # OpenAlex supports unauthenticated requests.  An API key raises the
    # available credit budget but must not disable the connector when absent.
    requires_credentials = ()
    capabilities = ("search", "metadata", "citations", "versions")

    def __init__(self, *args, work_type: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.work_type = work_type
        if work_type == "dissertation":
            self.id = "openalex_dissertations"
            self.family = SourceFamily.BOOKS_THESES

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_scoped(query, limit)

    async def search_scoped(
        self, query: str, limit: int = 20, scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        params = {
            "search": query,
            "per-page": min(limit, 100),
            "select": (
                "id,doi,display_name,publication_year,publication_date,type,authorships,"
                "primary_location,best_oa_location,locations,abstract_inverted_index,"
                "cited_by_count,referenced_works,related_works,is_retracted"
            ),
        }
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        if self.settings.openalex_mailto:
            params["mailto"] = self.settings.openalex_mailto
        filters = []
        if self.work_type:
            filters.append(f"type:{self.work_type}")
        if scope and scope.start_date:
            filters.append(f"from_publication_date:{scope.start_date.date().isoformat()}")
        if scope and scope.end_date:
            filters.append(f"to_publication_date:{scope.end_date.date().isoformat()}")
        if filters:
            params["filter"] = ",".join(filters)
        response = await self.client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        output = []
        for row in response.json().get("results", []):
            primary = row.get("primary_location") or {}
            best_oa = row.get("best_oa_location") or {}
            url = (
                best_oa.get("pdf_url")
                or best_oa.get("landing_page_url")
                or primary.get("landing_page_url")
                or row.get("doi")
                or row.get("id")
            )
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in row.get("authorships", []) if a.get("author")
            ]
            doi = normalize_doi(row.get("doi"))
            openalex_id = str(row.get("id", "")).rsplit("/", 1)[-1] or None
            abstract = reconstruct_abstract(row.get("abstract_inverted_index"))
            metadata = {
                **row,
                "provider": "openalex",
                "provider_snapshots": {"openalex": row},
                "scholarly_ids": {"doi": doi, "openalex_id": openalex_id},
                "abstract": abstract,
                "citation_relations": [
                    {
                        "relation_type": "cites",
                        "target_persistent_id": str(reference),
                        "provider": "openalex",
                    }
                    for reference in row.get("referenced_works", [])
                ],
                "version_locations": row.get("locations", []),
                "open_access_location": row.get("best_oa_location"),
                "is_retracted": bool(row.get("is_retracted")),
            }
            item = self.candidate(
                title=row.get("display_name", ""), url=url or "",
                snippet=abstract,
                persistent_id=doi or openalex_id, authors=authors,
                publisher=(primary.get("source") or {}).get("display_name"), metadata=metadata,
            )
            if item:
                output.append(item)
        return output

    async def fetch_citations(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        openalex_id = (candidate.metadata.get("scholarly_ids") or {}).get(
            "openalex_id"
        )
        if not openalex_id:
            value = candidate.persistent_id or ""
            if str(value).startswith("W"):
                openalex_id = value
        if not openalex_id:
            return []
        relation_limit = min(20, self.settings.semantic_scholar_citation_limit)
        params_base = {
            "per-page": max(1, relation_limit),
            "select": "id,doi,display_name,publication_date,abstract_inverted_index",
        }
        if self.settings.openalex_api_key:
            params_base["api_key"] = self.settings.openalex_api_key
        if self.settings.openalex_mailto:
            params_base["mailto"] = self.settings.openalex_mailto
        responses: list[tuple[str, list[dict[str, Any]]]] = []
        references = [
            str(item).rsplit("/", 1)[-1]
            for item in candidate.metadata.get("referenced_works", [])[:relation_limit]
        ]
        if references:
            params = {**params_base, "filter": f"openalex_id:{'|'.join(references)}"}
            response = await self.client.get("https://api.openalex.org/works", params=params)
            response.raise_for_status()
            responses.append(("cites", response.json().get("results", [])))
        params = {**params_base, "filter": f"cites:{openalex_id}"}
        response = await self.client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        responses.append(("cited_by", response.json().get("results", [])))
        relations: list[dict[str, Any]] = []
        for relation_type, rows in responses:
            for row in rows:
                doi = normalize_doi(row.get("doi"))
                target_id = str(row.get("id", "")).rsplit("/", 1)[-1]
                relations.append({
                    "relation_type": relation_type,
                    "target_persistent_id": doi or target_id,
                    "provider": "openalex",
                    "metadata": {
                        **row,
                        "title": row.get("display_name", ""),
                        "abstract": reconstruct_abstract(row.get("abstract_inverted_index")),
                        "scholarly_ids": {"doi": doi, "openalex_id": target_id},
                    },
                })
        return relations

    async def fetch_versions(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        return candidate.metadata.get("locations", [])


class SemanticScholarConnector(SourceConnector):
    id = "semantic_scholar"
    family = SourceFamily.ACADEMIC
    capabilities = ("search", "metadata", "citations", "versions", "recommendations")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0

    def _headers(self) -> dict[str, str]:
        return (
            {"x-api-key": self.settings.semantic_scholar_api_key}
            if self.settings.semantic_scholar_api_key else {}
        )

    async def _get(self, url: str, **kwargs):
        for attempt in range(3):
            async with self._rate_lock:
                minimum_interval = 1 / self.settings.semantic_scholar_rps
                wait = minimum_interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await self.client.get(url, headers=self._headers(), **kwargs)
                self._last_request = time.monotonic()
            if response.status_code != 429 or attempt == 2:
                return response
            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 1.0
            await asyncio.sleep(min(10.0, max(1.0, delay)))
        return response

    async def health(self):
        health = await super().health()
        # Semantic Scholar supports unauthenticated public traffic. It is slower and
        # more heavily throttled, but marking it unhealthy removed an entire academic
        # discovery method from the research pool.
        health.healthy = True
        health.detail = (
            "configured with API key"
            if self.settings.semantic_scholar_api_key
            else "public access active (degraded throughput; shared throttling applies)"
        )
        return health

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_scoped(query, limit)

    async def search_scoped(
        self, query: str, limit: int = 20, scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        fields = (
            "paperId,corpusId,externalIds,url,title,abstract,venue,year,authors,"
            "citationCount,influentialCitationCount,referenceCount,openAccessPdf,"
            "publicationTypes,publicationDate,journal,isOpenAccess"
        )
        params = {"query": query, "limit": min(limit, 100), "fields": fields}
        if scope and (scope.start_date or scope.end_date):
            start = scope.start_date.date().isoformat() if scope.start_date else ""
            end = scope.end_date.date().isoformat() if scope.end_date else ""
            params["publicationDateOrYear"] = f"{start}:{end}"
        response = await self._get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("data", []):
            external = row.get("externalIds") or {}
            doi = normalize_doi(external.get("DOI"))
            paper_id = row.get("paperId")
            open_pdf = row.get("openAccessPdf") or {}
            url = open_pdf.get("url") or row.get("url")
            metadata = {
                **row,
                "provider": "semantic_scholar",
                "provider_snapshots": {"semantic_scholar": row},
                "scholarly_ids": {
                    "doi": doi,
                    "semantic_scholar_id": paper_id,
                    "corpus_id": row.get("corpusId"),
                    "arxiv_id": external.get("ArXiv"),
                    "pmid": external.get("PubMed"),
                    "pmcid": external.get("PubMedCentral"),
                },
                "abstract": row.get("abstract") or "",
                "open_access_location": open_pdf or None,
                "is_retracted": "Retracted" in (row.get("publicationTypes") or []),
            }
            item = self.candidate(
                title=row.get("title", ""),
                url=url or f"https://www.semanticscholar.org/paper/{paper_id}",
                snippet=row.get("abstract") or "",
                persistent_id=doi or paper_id,
                authors=[author.get("name", "") for author in row.get("authors", [])],
                publisher=row.get("venue") or (row.get("journal") or {}).get("name"),
                metadata=metadata,
            )
            if item:
                output.append(item)
        return output

    async def fetch_citations(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        paper_id = (candidate.metadata.get("scholarly_ids") or {}).get(
            "semantic_scholar_id"
        )
        if not paper_id:
            return []
        limit = self.settings.semantic_scholar_citation_limit
        relations: list[dict[str, Any]] = []
        for endpoint, relation_type, key in (
            ("references", "cites", "citedPaper"),
            ("citations", "cited_by", "citingPaper"),
        ):
            response = await self._get(
                f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/{endpoint}",
                params={"limit": limit, "fields": "paperId,externalIds,title,year"},
            )
            response.raise_for_status()
            for row in response.json().get("data", []):
                paper = row.get(key) or {}
                external = paper.get("externalIds") or {}
                relations.append({
                    "relation_type": relation_type,
                    "target_persistent_id": (
                        normalize_doi(external.get("DOI")) or paper.get("paperId")
                    ),
                    "provider": "semantic_scholar",
                    "metadata": paper,
                })
        return relations


class CrossrefConnector(SourceConnector):
    id = "crossref"
    family = SourceFamily.ACADEMIC

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0

    async def _get(self, url: str, **kwargs):
        for attempt in range(4):
            async with self._rate_lock:
                minimum_interval = 1 / self.settings.crossref_rps
                wait = minimum_interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await self.client.get(url, **kwargs)
                self._last_request = time.monotonic()
            if response.status_code != 429 or attempt == 3:
                return response
            try:
                delay = float(response.headers.get("Retry-After", "2"))
            except ValueError:
                delay = 2.0
            await asyncio.sleep(min(15.0, max(1.0, delay)))
        return response

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_scoped(query, limit)

    async def search_scoped(
        self, query: str, limit: int = 20, scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        params = {"query": query, "rows": min(limit, 100)}
        filters = []
        if scope and scope.start_date:
            filters.append(f"from-pub-date:{scope.start_date.date().isoformat()}")
        if scope and scope.end_date:
            filters.append(f"until-pub-date:{scope.end_date.date().isoformat()}")
        if filters:
            params["filter"] = ",".join(filters)
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        response = await self._get(
            "https://api.crossref.org/works", params=params,
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("message", {}).get("items", []):
            title = (row.get("title") or [""])[0]
            doi = row.get("DOI")
            item = self.candidate(
                title=title, url=row.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                snippet=_text(row.get("abstract")), persistent_id=doi,
                authors=[" ".join(filter(None, [a.get("given"), a.get("family")])) for a in row.get("author", [])],
                publisher=row.get("publisher"), metadata=row,
            )
            if item:
                output.append(item)
        return output


_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}
_ARXIV_ECHO_QUERY = re.compile(
    r"search_query=(.*?)(?:&(?:id_list|start|max_results|sortBy|sortOrder)=|$)"
)


def _arxiv_error_detail(root: ET.Element) -> str | None:
    """The `<summary>` of arXiv's HTTP-200 error feed, or None for a real feed.

    A malformed parameter is answered with status 200, `totalResults` 1, and a single
    entry whose `<title>` is exactly "Error". Its `<id>` is a placeholder that fails
    `HttpUrl` validation, so `candidate()` drops it and the run reports zero results for
    a query the provider actually rejected.
    """
    entries = root.findall("a:entry", _ARXIV_NS)
    if len(entries) != 1:
        return None
    entry = entries[0]
    if (entry.findtext("a:title", "", _ARXIV_NS) or "").strip() != "Error":
        return None
    return (entry.findtext("a:summary", "", _ARXIV_NS) or "unspecified error").strip()


def _arxiv_query_echo(root: ET.Element) -> str:
    """The feed `<title>`, which echoes the whole request as arXiv executed it."""
    return (root.findtext("a:title", "", _ARXIV_NS) or "").strip()


def _arxiv_executed_query(echo: str) -> str:
    """The `search_query` arXiv actually ran, taken out of the feed title echo."""
    match = _ARXIV_ECHO_QUERY.search(echo)
    return match.group(1).strip() if match else ""


def _arxiv_comparable(query: str) -> str:
    """Normalise for comparison: the echo spells spaces as `+` and may re-space terms."""
    return " ".join(query.replace("+", " ").split())


class ArxivConnector(SourceConnector):
    id = "arxiv"
    family = SourceFamily.ACADEMIC

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # arXiv's limit is a budget for the whole machine on a single connection, not a
        # budget per run. The per-instance lock the other connectors use would give each
        # concurrent run its own three-second allowance, so this takes the process-wide
        # limiter and holds the slot across the request rather than only spacing starts.
        self._limiter = shared_domain_limiter(
            0.0 if self.settings.testing else 1 / self.settings.arxiv_rps
        )

    async def _get(self, params: dict[str, Any]) -> httpx.Response:
        """Paced arXiv fetch. Retries throttling; never retries a rejected query.

        Throttling arrives as HTTP 429 with a bare `Rate exceeded.` body -- 14 bytes, no
        Atom envelope -- and under sustained throttling the connection is dropped outright.
        Neither a dropped connection nor a rejected query is retried here: reconnecting
        into an active throttle sustains it, and a repeated malformed request is what earns
        a throttle measured in half-hours.
        """
        for attempt in range(3):
            async with self._limiter.hold(_ARXIV_API):
                response = await self.client.get(_ARXIV_API, params=params)
            if response.status_code != 429 or attempt == 2:
                return response
            retry_after = response.headers.get("Retry-After", "3")
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 3.0
            # Floor at the provider's own interval: the 1.0s the other connectors use is
            # below arXiv's minimum and would retry straight back into the throttle.
            await asyncio.sleep(min(30.0, max(3.0, delay)))
        return response

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_scoped(query, limit)

    async def search_scoped(
        self, query: str, limit: int = 20, scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        distinctive = topic_terms(query)
        ordered_terms = []
        for token in re.findall(r"[A-Za-zÀ-ž0-9_-]+", query.lower()):
            normalized = token.replace("-", "").replace("_", "")
            if normalized in distinctive and normalized not in ordered_terms:
                ordered_terms.append(normalized)
        # arXiv treats every field term as mandatory. Three distinctive anchors keep
        # precision high without turning natural-language questions into zero-hit queries.
        selected_terms = ordered_terms[:3]
        search_query = (
            " AND ".join(f"all:{term}" for term in selected_terms)
            if selected_terms
            else f'all:"{query}"'
        )
        if scope and (scope.start_date or scope.end_date):
            start = scope.start_date or parse_datetime("1900-01-01")
            end = scope.end_date or parse_datetime("2999-12-31")
            start_text = start.strftime("%Y%m%d%H%M")
            end_text = end.strftime("%Y%m%d%H%M")
            search_query = (
                f"({search_query}) AND submittedDate:[{start_text} TO {end_text}]"
            )
        response = await self._get(
            {
                "search_query": search_query,
                "start": 0,
                "max_results": min(limit, 100),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        response.raise_for_status()
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise ConnectorQueryError(
                self.id, f"non-XML body ({exc}): {response.text[:120]!r}", query=search_query
            ) from exc
        error_detail = _arxiv_error_detail(root)
        if error_detail is not None:
            raise ConnectorQueryError(self.id, error_detail, query=search_query)
        # arXiv rewrites an unknown field prefix to `all:` -- `ti:x` is run as `all:ti:x`
        # -- and says so only in the feed title, which echoes the query as executed. A
        # rewritten query still returns usable results, so this is recorded rather than
        # raised: dropping the results to report the warning would cost more than the
        # warning is worth. Comparing the executed query against the sent one is the only
        # way to see it, since the rewrite keeps the original prefix as literal text.
        echo = _arxiv_query_echo(root)
        executed = _arxiv_executed_query(echo)
        rewritten = bool(executed) and _arxiv_comparable(executed) != _arxiv_comparable(
            search_query
        )
        if rewritten:
            logger.warning(
                "arxiv executed a different query than requested: sent=%r executed=%r",
                search_query, echo,
            )
        ns = _ARXIV_NS
        output = []
        for entry in root.findall("a:entry", ns):
            url = entry.findtext("a:id", "", ns)
            pid = url.rsplit("/", 1)[-1]
            published = parse_datetime(entry.findtext("a:published", "", ns))
            updated = entry.findtext("a:updated", "", ns)
            item = self.candidate(
                title=entry.findtext("a:title", "", ns), url=url,
                snippet=entry.findtext("a:summary", "", ns), persistent_id=f"arxiv:{pid}",
                authors=[a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)],
                publisher="arXiv",
                published_at=published,
                metadata={
                    "published": published.isoformat() if published else None,
                    "updated": updated,
                    "arxiv_query_echo": echo,
                    "arxiv_query_rewritten": rewritten,
                },
            )
            if item:
                output.append(item)
        return output


class EuropePmcConnector(SourceConnector):
    id = "europe_pmc"
    family = SourceFamily.ACADEMIC

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_scoped(query, limit)

    async def search_scoped(
        self, query: str, limit: int = 20, scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        scoped_query = query
        if scope and (scope.start_date or scope.end_date):
            start = scope.start_date.date().isoformat() if scope.start_date else "1900-01-01"
            end = scope.end_date.date().isoformat() if scope.end_date else "2999-12-31"
            scoped_query = f"({query}) AND FIRST_PDATE:[{start} TO {end}] sort_date:y"
        response = await self.client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": scoped_query, "pageSize": min(limit, 100), "format": "json"},
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("resultList", {}).get("result", []):
            pid = row.get("doi") or row.get("pmcid") or row.get("pmid")
            url = f"https://europepmc.org/article/{row.get('source', 'MED')}/{row.get('id', pid)}"
            item = self.candidate(
                title=row.get("title", ""), url=url, snippet=row.get("authorString", ""),
                persistent_id=pid, publisher=row.get("journalTitle"), metadata=row,
            )
            if item:
                output.append(item)
        return output


class OpenLibraryConnector(SourceConnector):
    id = "open_library"
    family = SourceFamily.BOOKS_THESES

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://openlibrary.org/search.json", params={"q": query, "limit": min(limit, 100)}
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("docs", []):
            key = row.get("key", "")
            item = self.candidate(
                title=row.get("title", ""), url=f"https://openlibrary.org{key}",
                snippet=", ".join(row.get("subject", [])[:5]),
                persistent_id=(row.get("isbn") or [key])[0], authors=row.get("author_name", []), metadata=row,
            )
            if item:
                output.append(item)
        return output


class IetfConnector(SourceConnector):
    id = "ietf_datatracker"
    family = SourceFamily.PATENTS_STANDARDS

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://datatracker.ietf.org/api/v1/doc/document/",
            params={"name__contains": query.lower().replace(" ", "-"), "limit": min(limit, 100), "format": "json"},
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("objects", []):
            name = row.get("name", "")
            item = self.candidate(
                title=row.get("title") or name, url=f"https://datatracker.ietf.org/doc/{name}/",
                snippet=row.get("abstract", ""), persistent_id=name, publisher="IETF", metadata=row,
            )
            if item:
                output.append(item)
        return output


class EpoOpsConnector(CredentialOnlyConnector):
    id = "epo_ops"
    family = SourceFamily.PATENTS_STANDARDS
    requires_credentials = ("epo_ops_key", "epo_ops_secret")


class FederalRegisterConnector(SourceConnector):
    id = "federal_register"
    family = SourceFamily.OFFICIAL_LEGAL

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://www.federalregister.gov/api/v1/documents.json",
            params={"conditions[term]": query, "per_page": min(limit, 100)},
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("results", []):
            item = self.candidate(
                title=row.get("title", ""), url=row.get("html_url") or row.get("pdf_url") or "",
                snippet=row.get("abstract", ""), persistent_id=row.get("document_number"),
                publisher=", ".join(a.get("name", "") for a in row.get("agencies", [])), metadata=row,
            )
            if item:
                output.append(item)
        return output


class GdeltConnector(SourceConnector):
    id = "gdelt"
    family = SourceFamily.NEWS_ARCHIVES

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "ArtList", "format": "json", "maxrecords": min(limit, 250)},
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("articles", []):
            item = self.candidate(
                title=row.get("title", ""), url=row.get("url", ""), snippet=row.get("seendate", ""),
                publisher=row.get("domain"), metadata=row,
            )
            if item:
                output.append(item)
        return output


class WaybackConnector(SourceConnector):
    id = "internet_archive_cdx"
    family = SourceFamily.NEWS_ARCHIVES

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        domain = query.strip() if "." in query and " " not in query else "*"
        response = await self.client.get(
            "https://web.archive.org/cdx/search/cdx",
            params={"url": domain, "output": "json", "filter": "statuscode:200", "limit": min(limit, 100)},
        )
        response.raise_for_status()
        rows = response.json()
        output = []
        for row in rows[1:] if rows else []:
            timestamp, original = row[1], row[2]
            item = self.candidate(
                title=f"Archived: {original}",
                url=f"https://web.archive.org/web/{timestamp}/{original}",
                persistent_id=f"wayback:{timestamp}:{original}", metadata={"timestamp": timestamp},
            )
            if item:
                output.append(item)
        return output


class GitHubConnector(SourceConnector):
    id = "github"
    family = SourceFamily.CODE_DATA

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        repositories = github_repositories(query)
        if repositories:
            owner, repo = repositories[0]
            response = await self.client.get(
                f"https://api.github.com/repos/{owner}/{repo}", headers=headers,
            )
            if response.status_code == 200:
                row = response.json()
                item = self.candidate(
                    title=row.get("full_name", f"{owner}/{repo}"), url=row.get("html_url", ""),
                    snippet=row.get("description") or "", persistent_id=f"github:{row.get('id')}",
                    metadata={**row, "exact_repository": True},
                )
                return [item] if item else []
        response = await self.client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": min(limit, 100)}, headers=headers,
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("items", []):
            item = self.candidate(
                title=row.get("full_name", ""), url=row.get("html_url", ""),
                snippet=row.get("description") or "", persistent_id=f"github:{row.get('id')}", metadata=row,
            )
            if item:
                output.append(item)
        return output


class HuggingFaceConnector(SourceConnector):
    id = "huggingface"
    family = SourceFamily.CODE_DATA

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://huggingface.co/api/models", params={"search": query, "limit": min(limit, 100)}
        )
        response.raise_for_status()
        output = []
        for row in response.json():
            model_id = row.get("modelId") or row.get("id")
            item = self.candidate(
                title=model_id or "", url=f"https://huggingface.co/{model_id}",
                snippet=", ".join(row.get("tags", [])[:10]), persistent_id=f"hf:{model_id}", metadata=row,
            )
            if item:
                output.append(item)
        return output


class ZenodoConnector(SourceConnector):
    id = "zenodo"
    family = SourceFamily.CODE_DATA

    def __init__(self, *args, family: SourceFamily | None = None, connector_id: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            self.family = family
        if connector_id:
            self.id = connector_id

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://zenodo.org/api/records", params={"q": query, "size": min(limit, 100)}
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("hits", {}).get("hits", []):
            meta = row.get("metadata", {})
            item = self.candidate(
                title=meta.get("title", ""), url=(row.get("links") or {}).get("html", ""),
                snippet=_text(meta.get("description")), persistent_id=meta.get("doi") or str(row.get("id")),
                authors=[c.get("name", "") for c in meta.get("creators", [])],
                publisher=meta.get("publisher", "Zenodo"), metadata=row,
            )
            if item:
                output.append(item)
        return output


class DataCiteConnector(SourceConnector):
    id = "datacite"
    family = SourceFamily.CODE_DATA

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://api.datacite.org/dois", params={"query": query, "page[size]": min(limit, 100)}
        )
        response.raise_for_status()
        output = []
        for row in response.json().get("data", []):
            attr = row.get("attributes", {})
            title = ((attr.get("titles") or [{}])[0]).get("title", "")
            doi = attr.get("doi") or row.get("id")
            item = self.candidate(
                title=title, url=attr.get("url") or f"https://doi.org/{doi}",
                snippet=_text(attr.get("descriptions", "")), persistent_id=doi,
                publisher=attr.get("publisher"), metadata=row,
            )
            if item:
                output.append(item)
        return output


class SecEdgarConnector(SourceConnector):
    id = "sec_edgar"
    family = SourceFamily.COMPANY

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": query, "from": 0, "size": min(limit, 100)},
            headers={"User-Agent": self.settings.user_agent},
        )
        response.raise_for_status()
        output = []
        for hit in response.json().get("hits", {}).get("hits", []):
            row = hit.get("_source", {})
            file_num = row.get("file_num", "")
            url = row.get("linkToHtml") or "https://www.sec.gov/edgar/search/"
            item = self.candidate(
                title=row.get("display_names", [query])[0], url=url,
                snippet=f"Forms: {row.get('root_forms', [])}", persistent_id=file_num or hit.get("_id"),
                publisher="U.S. SEC", metadata=row,
            )
            if item:
                output.append(item)
        return output


class DomainAgentSearchConnector(AgentSearchConnector):
    def __init__(self, *args, connector_id: str, family: SourceFamily, domain: str | None = None, **kwargs):
        super().__init__(*args, domain=domain, **kwargs)
        self.id = connector_id
        self.family = family
