"""Every connector request must record what happened on the wire.

Before this, only arXiv and Semantic Scholar recorded anything, so a panel reading any
other connector's call showed "HTTP durumu: Kaydedilmemiş" -- and a zero-result GitHub
search was indistinguishable from a rejected one.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import pytest

from research_platform.config import Settings
from research_platform.connectors.implementations import (
    AgentSearchConnector,
    CrossrefConnector,
    DataCiteConnector,
    EuropePmcConnector,
    FederalRegisterConnector,
    GdeltConnector,
    GitHubConnector,
    HuggingFaceConnector,
    IetfConnector,
    OpenAlexConnector,
    OpenLibraryConnector,
    SecEdgarConnector,
    WaybackConnector,
    ZenodoConnector,
)
from research_platform.connectors.zotero import ZoteroConnector
from research_platform.diagnostics import CONNECTOR_OBSERVATION
from research_platform.schemas import ConnectorCandidate, SourceFamily

CONNECTOR_MODULES = (
    Path("src/research_platform/connectors/implementations.py"),
    Path("src/research_platform/connectors/zotero.py"),
)

# (connector, empty 200 body, the phase it tags its search request with -- only the
# connectors that issue more than one request per search name their phases).
EMPTY_BODIES = [
    (AgentSearchConnector, {"results": []}, None),
    (OpenAlexConnector, {"results": []}, None),
    (CrossrefConnector, {"message": {"items": []}}, None),
    (EuropePmcConnector, {"resultList": {"result": []}}, None),
    (OpenLibraryConnector, {"docs": []}, None),
    (IetfConnector, {"objects": []}, None),
    (FederalRegisterConnector, {"results": []}, None),
    (GdeltConnector, {"articles": []}, None),
    (WaybackConnector, [], None),
    (GitHubConnector, {"items": []}, "search"),
    (HuggingFaceConnector, [], None),
    (ZenodoConnector, {"hits": {"hits": []}}, None),
    (DataCiteConnector, {"data": []}, None),
    (SecEdgarConnector, {"hits": {"hits": []}}, None),
]


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, testing=True, **overrides)


async def observe(connector, coroutine_factory):
    """Run one connector call inside a fresh observation context and return it."""
    observation: dict = {}
    token = CONNECTOR_OBSERVATION.set(observation)
    try:
        await coroutine_factory(connector)
    finally:
        CONNECTOR_OBSERVATION.reset(token)
    return observation


async def run(handler, connector_type, connector_settings=None, **connector_kwargs):
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = connector_type(
            connector_settings or settings(), client, **connector_kwargs
        )
        return await observe(connector, lambda c: c.search("chest ct report", 5))


@pytest.mark.asyncio
@pytest.mark.parametrize(("connector_type", "body", "phase"), EMPTY_BODIES)
async def test_every_connector_search_records_its_http_status(
    connector_type, body, phase,
):
    """A connector that answers 200 with nothing must still say it answered 200."""

    async def handler(request):
        return httpx.Response(200, request=request, json=body)

    observation = await run(handler, connector_type)
    assert observation["http_status"] == 200
    assert observation["attempts"][0]["attempt"] == 1
    assert observation["attempts"][0]["http_status"] == 200
    # A one-request search carries no phase; naming it would read as a retry sequence.
    assert observation["attempts"][0].get("phase") == phase


@pytest.mark.asyncio
async def test_zotero_search_records_its_http_status():
    async def handler(request):
        return httpx.Response(200, request=request, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = ZoteroConnector(
            settings(zotero_user_id="123", zotero_api_key="k"), client, mode="web"
        )
        observation = await observe(connector, lambda c: c.search("chest ct", 5))
    assert observation["http_status"] == 200
    assert len(observation["attempts"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_type", [OpenAlexConnector, CrossrefConnector])
async def test_connector_transport_failure_is_recorded_before_it_propagates(
    connector_type,
):
    """The record has to survive the exception; a failed call is the one worth seeing.

    Crossref retries a 429 but not a dropped connection, so both connectors record
    exactly one attempt here.
    """

    async def handler(request):
        raise httpx.ReadError("connection dropped")

    observation: dict = {}
    token = CONNECTOR_OBSERVATION.set(observation)
    transport = httpx.MockTransport(handler)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            connector = connector_type(settings(), client)
            with pytest.raises(httpx.ReadError):
                await connector.search("chest ct", 5)
    finally:
        CONNECTOR_OBSERVATION.reset(token)

    assert observation["attempts"] == [
        {"attempt": 1, "http_status": None, "error_type": "ReadError"}
    ]
    assert observation["http_status"] is None


@pytest.mark.asyncio
async def test_crossref_retry_is_visible_as_two_attempts(monkeypatch):
    """Crossref has had a four-attempt retry loop all along and recorded none of it."""
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429, request=request, json={}, headers={"Retry-After": "1"}
            )
        return httpx.Response(200, request=request, json={"message": {"items": []}})

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    observation = await run(handler, CrossrefConnector)

    assert [a["http_status"] for a in observation["attempts"]] == [429, 200]
    assert [a["attempt"] for a in observation["attempts"]] == [1, 2]
    assert observation["attempts"][0]["retry_after"] == "1"
    assert observation["http_status"] == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_two_requests_in_one_search_are_not_reported_as_retries():
    """GitHub looks a repository up before searching. Those are two requests, not two tries."""

    async def handler(request):
        if "/repos/" in str(request.url):
            return httpx.Response(404, request=request, json={"message": "Not Found"})
        return httpx.Response(200, request=request, json={"items": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = GitHubConnector(settings(), client)
        observation = await observe(
            connector, lambda c: c.search("owner/repo chest ct", 5)
        )

    assert [
        (a["attempt"], a["phase"], a["http_status"]) for a in observation["attempts"]
    ] == [(1, "repository", 404), (1, "search", 200)]


@pytest.mark.asyncio
async def test_citation_fetch_records_both_openalex_requests():
    async def handler(request):
        return httpx.Response(200, request=request, json={"results": []})

    candidate = ConnectorCandidate(
        connector_id="openalex", family=SourceFamily.ACADEMIC,
        title="A paper", url="https://openalex.org/W1", persistent_id="W1",
        metadata={"referenced_works": ["https://openalex.org/W2"]},
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = OpenAlexConnector(settings(), client)
        observation = await observe(connector, lambda c: c.fetch_citations(candidate))

    assert [a["phase"] for a in observation["attempts"]] == ["references", "cited_by"]


@pytest.mark.asyncio
async def test_zotero_records_the_search_not_one_row_per_attachment():
    """Per-item attachment fetches stay unobserved on purpose; they would bury the search.

    Pins the decision so a later "every request should be recorded" sweep does not quietly
    turn one informative row into forty uninformative ones.
    """
    item = {"data": {"key": "ITEM1", "itemType": "journalArticle", "title": "A paper"}}
    attachment = {"data": {"key": "ATT1", "itemType": "attachment"}}

    async def handler(request):
        url = str(request.url)
        if "/children" in url:
            return httpx.Response(200, request=request, json=[attachment])
        if "/fulltext" in url:
            return httpx.Response(200, request=request, json={"content": "body text"})
        return httpx.Response(200, request=request, json=[item])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = ZoteroConnector(
            settings(
                zotero_user_id="123", zotero_api_key="k", zotero_include_attachments=True
            ),
            client,
            mode="web",
        )
        observation = await observe(connector, lambda c: c.search("chest ct", 5))

    assert len(observation["attempts"]) == 1


def test_every_connector_request_goes_through_the_observed_helper():
    """The durable guard: 24 call sites cannot be kept in sync by review.

    A direct `self.client.get` records nothing, and the omission is invisible until a panel
    shows "not recorded" months later. Deliberate exemptions carry an `# unobserved` marker
    on the call line so that skipping the recorder is a decision someone wrote down.
    """
    direct_call = re.compile(r"self\.client\.(get|post|put|request|stream)\(")
    offenders = [
        f"{path}:{number}: {line.strip()}"
        for path in CONNECTOR_MODULES
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if direct_call.search(line) and "# unobserved" not in line
    ]
    assert offenders == []
