"""GitHub's answers, told apart.

A rejected query, a search that timed out and a genuine no-match all used to arrive as
`success=true, result_count=0`, which is how a ten-word sentence that no repository could
match looked exactly like an exhausted topic.
"""
from __future__ import annotations

import httpx
import pytest

from research_platform.config import Settings
from research_platform.connectors.base import ConnectorQueryError
from research_platform.connectors.implementations import GitHubConnector
from research_platform.diagnostics import CONNECTOR_OBSERVATION


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, testing=True, **overrides)


async def run_search(handler, query="chest ct report generation"):
    """Search inside a fresh observation context; returns (result_or_exception, observation)."""
    observation: dict = {}
    token = CONNECTOR_OBSERVATION.set(observation)
    transport = httpx.MockTransport(handler)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            connector = GitHubConnector(settings(), client)
            return await connector.search(query, 5), observation
    finally:
        CONNECTOR_OBSERVATION.reset(token)


@pytest.mark.asyncio
async def test_github_rejected_query_is_reported_not_read_as_zero_results():
    """422 means the provider read the query and refused it -- not that nothing matched."""

    async def handler(request):
        return httpx.Response(
            422, request=request, json={"message": "Validation Failed"}
        )

    observation: dict = {}
    token = CONNECTOR_OBSERVATION.set(observation)
    transport = httpx.MockTransport(handler)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            connector = GitHubConnector(settings(), client)
            with pytest.raises(ConnectorQueryError) as raised:
                await connector.search("chest ct in:bogus", 5)
    finally:
        CONNECTOR_OBSERVATION.reset(token)

    assert "Validation Failed" in str(raised.value)
    assert raised.value.query == "chest ct in:bogus"
    # ConnectorQueryError carries no response, so the status reaches the panel only
    # because the request was recorded before the raise.
    assert observation["http_status"] == 422


@pytest.mark.asyncio
async def test_github_records_the_query_and_the_provider_total():
    """`incomplete_results` with no items means the search timed out, not that it found nothing."""

    async def handler(request):
        return httpx.Response(
            200,
            request=request,
            json={"total_count": 0, "incomplete_results": True, "items": []},
        )

    results, observation = await run_search(handler)
    assert results == []
    assert observation["provider_query"] == "chest ct report generation"
    assert observation["provider_result_total"] == 0
    assert observation["provider_incomplete_results"] is True


@pytest.mark.asyncio
async def test_github_missing_repository_falls_through_to_search():
    """A 404 on the exact-repository lookup is a routing answer, not a failure."""
    repository = {
        "id": 7, "full_name": "openai/codex", "html_url": "https://github.com/openai/codex",
        "description": "A repository",
    }

    async def handler(request):
        if "/repos/" in str(request.url):
            return httpx.Response(404, request=request, json={"message": "Not Found"})
        return httpx.Response(
            200, request=request,
            json={"total_count": 1, "incomplete_results": False, "items": [repository]},
        )

    results, observation = await run_search(handler, query="openai/codex")
    assert [item.title for item in results] == ["openai/codex"]
    assert [(a["phase"], a["http_status"]) for a in observation["attempts"]] == [
        ("repository", 404), ("search", 200),
    ]


@pytest.mark.asyncio
async def test_github_exact_repository_hit_never_reaches_the_search_endpoint():
    repository = {
        "id": 7, "full_name": "openai/codex", "html_url": "https://github.com/openai/codex",
        "description": "A repository",
    }
    seen: list[str] = []

    async def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, request=request, json=repository)

    results, observation = await run_search(handler, query="openai/codex")
    assert [item.metadata["exact_repository"] for item in results] == [True]
    assert all("/search/" not in url for url in seen)
    assert [a["phase"] for a in observation["attempts"]] == ["repository"]
