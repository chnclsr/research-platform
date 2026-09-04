from __future__ import annotations

import asyncio
from xml.sax.saxutils import escape

import httpx
import pytest

from research_platform.config import Settings
from research_platform.connectors.base import ConnectorQueryError
from research_platform.connectors.implementations import ArxivConnector

FEED_OPEN = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
)

ERROR_FEED = (
    FEED_OPEN
    + "<title>arXiv Query: search_query=all:x&amp;start=notanumber</title>"
    + "<opensearch:totalResults>1</opensearch:totalResults>"
    + "<entry><id>http://arxiv.org/api/errors</id><title>Error</title>"
    + "<summary>start must be an integer</summary></entry></feed>"
)

EMPTY_FEED = (
    FEED_OPEN
    + "<title>arXiv Query: search_query=all:zzz</title>"
    + "<opensearch:totalResults>0</opensearch:totalResults></feed>"
)


def paper_feed(echo: str) -> str:
    return (
        FEED_OPEN
        + f"<title>arXiv Query: search_query={escape(echo)}</title>"
        + "<opensearch:totalResults>1</opensearch:totalResults>"
        + "<entry><id>http://arxiv.org/abs/2103.15348v1</id>"
        + "<title>A real paper</title><summary>A real abstract.</summary>"
        + "<published>2021-03-29T00:00:00Z</published>"
        + "<updated>2021-03-30T00:00:00Z</updated>"
        + "<author><name>A. Author</name></author></entry></feed>"
    )


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, testing=True, **overrides)


async def run_search(handler, connector_settings=None, query="graph neural network"):
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        connector = ArxivConnector(connector_settings or settings(), client)
        return await connector.search(query, 5)


@pytest.mark.asyncio
async def test_arxiv_error_entry_is_reported_not_swallowed():
    """The provider rejected the query; the run must not read that as zero results."""
    async def handler(request):
        return httpx.Response(200, request=request, text=ERROR_FEED)

    with pytest.raises(ConnectorQueryError) as caught:
        await run_search(handler)
    assert "start must be an integer" in str(caught.value)
    assert caught.value.connector_id == "arxiv"


@pytest.mark.asyncio
async def test_arxiv_rejected_query_is_not_retried():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, text=ERROR_FEED)

    with pytest.raises(ConnectorQueryError):
        await run_search(handler)
    assert calls == 1


@pytest.mark.asyncio
async def test_arxiv_empty_feed_is_a_clean_no_match():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, text=EMPTY_FEED)

    assert await run_search(handler) == []
    assert calls == 1


@pytest.mark.asyncio
async def test_arxiv_non_xml_body_is_reported_as_a_query_error():
    async def handler(request):
        return httpx.Response(200, request=request, text="Rate exceeded.")

    with pytest.raises(ConnectorQueryError) as caught:
        await run_search(handler)
    assert "non-XML body" in str(caught.value)


@pytest.mark.asyncio
async def test_arxiv_backs_off_on_plain_text_throttle(monkeypatch):
    """Throttling is a 429 with a 14-byte plain-text body, and 1s is below the minimum."""
    calls = 0
    slept: list[float] = []

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429, request=request, text="Rate exceeded.", headers={"Retry-After": "1"}
            )
        return httpx.Response(200, request=request, text=EMPTY_FEED)

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    assert await run_search(handler) == []
    assert calls == 2
    assert slept and min(slept) >= 3.0


@pytest.mark.asyncio
async def test_arxiv_does_not_reconnect_after_a_dropped_connection():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadError("connection dropped")

    with pytest.raises(httpx.ReadError):
        await run_search(handler)
    assert calls == 1


@pytest.mark.asyncio
async def test_arxiv_records_the_query_the_provider_executed():
    """An unmodified query must not be flagged, or the signal is noise."""
    sent = {}

    async def handler(request):
        sent["query"] = request.url.params["search_query"]
        return httpx.Response(
            200, request=request, text=paper_feed(f"{sent['query']}&start=0&max_results=5")
        )

    rows = await run_search(handler)
    assert rows
    assert rows[0].metadata["arxiv_query_echo"].startswith("arXiv Query:")
    assert rows[0].metadata["arxiv_query_rewritten"] is False


@pytest.mark.asyncio
async def test_arxiv_sends_precompiled_facet_groups_without_rewriting_them():
    compiled = (
        '(all:chest OR all:thorax) AND (all:CT OR all:"computed tomography") '
        'AND (all:3D OR all:volumetric) AND all:"radiology report generation"'
    )
    sent = {}

    async def handler(request):
        sent["query"] = request.url.params["search_query"]
        return httpx.Response(
            200,
            request=request,
            text=paper_feed(f"{sent['query']}&start=0&max_results=5"),
        )

    rows = await run_search(handler, query=compiled)

    assert sent["query"] == compiled
    assert rows[0].metadata["arxiv_query_rewritten"] is False


@pytest.mark.asyncio
async def test_arxiv_flags_a_silently_rewritten_field_prefix():
    """An unknown prefix is rewritten to `all:` with no error -- results still stand.

    The rewrite keeps the original prefix as literal text (`ti:x` runs as `all:ti:x`), so
    only comparing the executed query against the sent one reveals it.
    """
    async def handler(request):
        rewritten = f"all:{request.url.params['search_query']}"
        return httpx.Response(
            200, request=request, text=paper_feed(f"{rewritten}&start=0&max_results=5")
        )

    rows = await run_search(handler)
    assert rows, "a rewritten query still returns usable results"
    assert rows[0].metadata["arxiv_query_rewritten"] is True


@pytest.mark.asyncio
async def test_arxiv_pacing_is_shared_across_connector_instances(monkeypatch):
    """Two runs must share one budget, not get one three-second allowance each."""
    slept: list[float] = []

    async def handler(request):
        return httpx.Response(200, request=request, text=EMPTY_FEED)

    async def fake_sleep(seconds):
        slept.append(seconds)

    paced = Settings(_env_file=None, testing=False, arxiv_rps=0.5)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        first = ArxivConnector(paced, client)
        second = ArxivConnector(paced, client)
        assert first._limiter is second._limiter
        await first.search("alpha", 1)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        await second.search("beta", 1)
    assert slept and slept[0] > 0


@pytest.mark.asyncio
async def test_arxiv_error_entry_is_read_even_when_the_status_is_400():
    """Observed live 2026-09-04: `start=notanumber` answers 400 carrying the same entry.

    A bare HTTPStatusError would say only "400"; the entry says what was wrong.
    """
    async def handler(request):
        return httpx.Response(400, request=request, text=ERROR_FEED)

    with pytest.raises(ConnectorQueryError) as caught:
        await run_search(handler)
    assert "start must be an integer" in str(caught.value)
