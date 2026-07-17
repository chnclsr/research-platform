from __future__ import annotations

import httpx
import pytest

from research_platform.acquisition import AcquisitionService
from research_platform.config import Settings
from research_platform.connectors.implementations import (
    ArxivConnector, CrossrefConnector, EuropePmcConnector, OpenAlexConnector,
    SemanticScholarConnector,
)
from research_platform.connectors.zotero import ZoteroConnector
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument, ConnectorCandidate, ResearchProtocol, ResearchScope, SourceFamily,
)
from research_platform.scholarly import (
    candidate_dedupe_key, normalize_doi, reconstruct_abstract,
)


def response(request: httpx.Request, payload, headers=None):
    return httpx.Response(
        200, request=request, json=payload, headers=headers or {},
    )


def test_scholarly_normalization_and_abstract_reconstruction():
    assert normalize_doi("https://doi.org/10.1000/Example.1") == "10.1000/example.1"
    assert reconstruct_abstract({"second": [1], "first": [0], "again": [2]}) == (
        "first second again"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connector_type", "response_body", "parameter", "expected"),
    [
        (
            CrossrefConnector, {"message": {"items": []}},
            "filter", "from-pub-date:2026-04-17",
        ),
        (
            EuropePmcConnector, {"resultList": {"result": []}},
            "query", "FIRST_PDATE:[2026-04-17 TO 2026-07-17]",
        ),
        (
            ArxivConnector,
            '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
            "search_query",
            "submittedDate:[202604170000 TO 202607172359]",
        ),
    ],
)
async def test_academic_connectors_push_date_scope_into_provider_query(
    connector_type, response_body, parameter, expected,
):
    seen = {}

    async def handler(request):
        nonlocal seen
        seen = dict(request.url.params)
        if isinstance(response_body, str):
            return httpx.Response(200, request=request, text=response_body)
        return response(request, response_body)

    scope = ResearchScope(
        start_date="2026-04-17T00:00:00Z",
        end_date="2026-07-17T23:59:00Z",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = connector_type(Settings(_env_file=None, testing=True), client)
        await connector.search_scoped("lung cancer CT radiomics", 5, scope)
    assert expected in seen[parameter]


@pytest.mark.asyncio
async def test_openalex_reconstructs_abstract_and_normalizes_identity():
    payload = {
        "results": [{
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1000/ABC",
            "display_name": "A controlled study",
            "authorships": [{"author": {"display_name": "Ada Researcher"}}],
            "primary_location": {
                "landing_page_url": "https://example.org/article",
                "source": {"display_name": "Journal"},
            },
            "abstract_inverted_index": {"Controlled": [0], "result": [1]},
            "referenced_works": ["https://openalex.org/W100"],
            "locations": [],
            "cited_by_count": 3,
            "is_retracted": False,
        }]
    }

    async def handler(request):
        assert request.url.params["api_key"] == "openalex-key"
        return response(request, payload)

    settings = Settings(_env_file=None, openalex_api_key="openalex-key", testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await OpenAlexConnector(settings, client).search("controlled", 5)
    assert rows[0].snippet == "Controlled result"
    assert rows[0].persistent_id == "10.1000/abc"
    assert rows[0].metadata["scholarly_ids"]["openalex_id"] == "W123"
    assert rows[0].metadata["citation_relations"][0]["relation_type"] == "cites"
    assert candidate_dedupe_key(rows[0]) == "doi:10.1000/abc"


@pytest.mark.asyncio
async def test_semantic_scholar_search_and_citation_relations():
    async def handler(request):
        if request.url.path.endswith("/paper/search"):
            return response(request, {"data": [{
                "paperId": "S2-1",
                "corpusId": 11,
                "externalIds": {"DOI": "10.1000/ABC"},
                "url": "https://semanticscholar.org/paper/S2-1",
                "title": "A controlled study",
                "abstract": "Result text",
                "venue": "Journal",
                "year": 2025,
                "authors": [{"name": "Ada Researcher"}],
                "openAccessPdf": {"url": "https://example.org/paper.pdf"},
            }]})
        relation = "references" if request.url.path.endswith("/references") else "citations"
        key = "citedPaper" if relation == "references" else "citingPaper"
        return response(request, {"data": [{
            key: {
                "paperId": f"{relation}-1",
                "externalIds": {"DOI": f"10.1000/{relation}"},
                "title": relation,
            }
        }]})

    settings = Settings(
        _env_file=None, semantic_scholar_api_key="s2-key",
        semantic_scholar_rps=100, testing=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = SemanticScholarConnector(settings, client)
        rows = await connector.search("controlled", 5)
        relations = await connector.fetch_citations(rows[0])
    assert rows[0].persistent_id == "10.1000/abc"
    assert {row["relation_type"] for row in relations} == {"cites", "cited_by"}
    assert all(row["target_persistent_id"].startswith("10.1000/") for row in relations)


@pytest.mark.asyncio
async def test_semantic_scholar_retries_rate_limit():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429, request=request, headers={"Retry-After": "0"}
            )
        return response(request, {"data": []})

    settings = Settings(
        _env_file=None, semantic_scholar_api_key="s2-key",
        semantic_scholar_rps=100, testing=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await SemanticScholarConnector(settings, client).search("test", 1)
    assert rows == []
    assert calls == 2


@pytest.mark.asyncio
async def test_crossref_serializes_and_retries_rate_limit():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429, request=request, headers={"Retry-After": "0"},
            )
        return response(request, {"message": {"items": []}})

    settings = Settings(_env_file=None, crossref_rps=50, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await CrossrefConnector(settings, client).search("lung CT", 1)
    assert rows == []
    assert calls == 2


@pytest.mark.asyncio
async def test_zotero_local_fulltext_is_acquired_without_general_ssrf_bypass():
    item = {
        "key": "ITEM1",
        "data": {
            "key": "ITEM1", "itemType": "journalArticle", "title": "Local paper",
            "DOI": "10.1000/local", "url": "https://example.org/local",
            "creators": [{"firstName": "Ada", "lastName": "Researcher"}],
            "tags": [{"tag": "priority"}], "collections": ["COLL1"],
        },
        "links": {},
    }

    async def handler(request):
        path = request.url.path
        if path.endswith("/items") and request.url.params.get("limit") == "1":
            return response(request, [item])
        if path.endswith("/items"):
            return response(
                request, [item], {"Last-Modified-Version": "42"},
            )
        if path.endswith("/ITEM1/children"):
            return response(request, [{
                "data": {"key": "ATT1", "itemType": "attachment"}
            }])
        if path.endswith("/ATT1/fulltext"):
            return response(request, {
                "content": "This is indexed Zotero full text with sufficient evidence. " * 10,
                "indexedPages": 2, "totalPages": 2,
            })
        raise AssertionError(str(request.url))

    settings = Settings(_env_file=None, testing=True, zotero_local_enabled=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = ZoteroConnector(settings, client, mode="local")
        health = await connector.health()
        rows = await connector.search("local", 5)
        document = await AcquisitionService(settings, client).acquire(rows[0])
    assert health.healthy is True
    assert rows[0].metadata["zotero_library_version"] == 42
    assert rows[0].metadata["scholarly_ids"]["zotero_item_key"] == "ITEM1"
    assert document.success is True
    assert document.acquisition_method == "zotero_fulltext"
    assert document.strategies_tried == ["zotero_fulltext"]


@pytest.mark.asyncio
async def test_zotero_notes_are_marked_non_evidence():
    note = {
        "key": "NOTE1",
        "data": {
            "key": "NOTE1", "itemType": "note", "note": "<p>My interpretation</p>",
            "tags": [], "collections": [],
        },
        "links": {"alternate": {"href": "https://example.org/note"}},
    }

    async def handler(request):
        return response(
            request, [note], {"Last-Modified-Version": "7"},
        )

    settings = Settings(_env_file=None, testing=True, zotero_include_notes=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await ZoteroConnector(settings, client, mode="local").search("", 5)
    assert rows[0].metadata["user_annotation"] is True
    assert rows[0].metadata["evidence_eligible"] is False


@pytest.mark.asyncio
async def test_zotero_metadata_only_item_is_preserved_without_public_url_fetch():
    candidate = ConnectorCandidate(
        connector_id="zotero_local", family=SourceFamily.ACADEMIC,
        title="Metadata-only paper", url="http://localhost:23119/api/items/ITEM2",
        snippet="An abstract stored in Zotero.", persistent_id="10.1000/metadata",
        authors=["Ada Researcher"], metadata={"inline_fulltext": ""},
    )
    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient() as client:
        document = await AcquisitionService(settings, client).acquire(candidate)
    assert document.success is True
    assert document.acquisition_method == "zotero_metadata"
    assert document.candidate.metadata["evidence_eligible"] is False


@pytest.mark.asyncio
async def test_repository_merges_provider_snapshots_by_doi_and_saves_relations():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session)
        run = await repo.create_run(ResearchProtocol(
            title="Academic dedupe",
            primary_question="Does provider deduplication preserve provenance?",
        ))
        for connector, url in (
            ("openalex", "https://openalex.org/W1"),
            ("semantic_scholar", "https://semanticscholar.org/paper/S1"),
        ):
            candidate = ConnectorCandidate(
                connector_id=connector, family=SourceFamily.ACADEMIC,
                title="The same paper", url=url, persistent_id="10.1000/SAME",
                authors=["Ada Researcher"],
                metadata={
                    "provider_snapshots": {connector: {"id": connector}},
                    "scholarly_ids": {"doi": "10.1000/same"},
                    "citation_relations": [{
                        "relation_type": "cites",
                        "target_persistent_id": "10.1000/reference",
                        "provider": connector,
                    }],
                },
            )
            await repo.save_document(run.id, AcquiredDocument(
                candidate=candidate, success=True, access_status="open",
                content="Full text", content_hash="a" * 64,
                acquisition_method="fixture",
            ))
        sources = await repo.list_sources(run.id)
        relations = await repo.list_source_relations(run.id)
        assert len(sources) == 1
        assert set(sources[0].metadata_json["provider_snapshots"]) == {
            "openalex", "semantic_scholar",
        }
        assert len(relations) == 2
