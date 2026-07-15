from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from typing import Any
from .base import CredentialOnlyConnector, SourceConnector
from ..relevance import github_repositories
from ..schemas import ConnectorCandidate, SourceFamily


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
        params: dict[str, Any] = {"q": query, "count": min(limit, 50), "mode": self.mode}
        if self.domain:
            params["domain"] = self.domain
        response = await self.client.get(f"{self.settings.agentsearch_url}/search", params=params)
        response.raise_for_status()
        output = []
        for row in response.json().get("results", []):
            item = self.candidate(
                title=row.get("title", ""), url=row.get("url", ""),
                snippet=row.get("snippet", ""), metadata={"engines": row.get("engines", [])},
            )
            if item:
                output.append(item)
        return output


class OpenAlexConnector(SourceConnector):
    id = "openalex"
    family = SourceFamily.ACADEMIC
    capabilities = ("search", "metadata", "citations", "versions")

    def __init__(self, *args, work_type: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.work_type = work_type
        if work_type == "dissertation":
            self.id = "openalex_dissertations"
            self.family = SourceFamily.BOOKS_THESES

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        params = {"search": query, "per-page": min(limit, 100), "mailto": "local@example.invalid"}
        if self.work_type:
            params["filter"] = f"type:{self.work_type}"
        response = await self.client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        output = []
        for row in response.json().get("results", []):
            primary = row.get("primary_location") or {}
            url = primary.get("landing_page_url") or row.get("doi") or row.get("id")
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in row.get("authorships", []) if a.get("author")
            ]
            item = self.candidate(
                title=row.get("display_name", ""), url=url or "",
                snippet=_text(row.get("abstract_inverted_index", "")),
                persistent_id=row.get("doi") or row.get("id"), authors=authors,
                publisher=(primary.get("source") or {}).get("display_name"), metadata=row,
            )
            if item:
                output.append(item)
        return output

    async def fetch_citations(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        return [{"cited_by_count": candidate.metadata.get("cited_by_count", 0)}]

    async def fetch_versions(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        return candidate.metadata.get("locations", [])


class CrossrefConnector(SourceConnector):
    id = "crossref"
    family = SourceFamily.ACADEMIC

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://api.crossref.org/works", params={"query": query, "rows": min(limit, 100)}
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


class ArxivConnector(SourceConnector):
    id = "arxiv"
    family = SourceFamily.ACADEMIC

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 100)},
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        output = []
        for entry in root.findall("a:entry", ns):
            url = entry.findtext("a:id", "", ns)
            pid = url.rsplit("/", 1)[-1]
            item = self.candidate(
                title=entry.findtext("a:title", "", ns), url=url,
                snippet=entry.findtext("a:summary", "", ns), persistent_id=f"arxiv:{pid}",
                authors=[a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)],
                publisher="arXiv",
            )
            if item:
                output.append(item)
        return output


class EuropePmcConnector(SourceConnector):
    id = "europe_pmc"
    family = SourceFamily.ACADEMIC

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        response = await self.client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "pageSize": min(limit, 100), "format": "json"},
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
