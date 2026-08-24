from __future__ import annotations

import httpx
import pytest

import research_platform.acquisition as acquisition_module
from research_platform.acquisition import ACQUISITION_STRATEGY_ORDER, AcquisitionService
from research_platform.config import Settings
from research_platform.schemas import ConnectorCandidate, SourceFamily


def _candidate() -> ConnectorCandidate:
    return ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.WEB,
        title="Client-rendered article",
        url="https://example.com/article?section=results",
    )


@pytest.mark.asyncio
async def test_jina_reader_forces_browser_and_returns_markdown():
    body = "# Rendered article\n\n" + ("Evidence recovered from JavaScript. " * 20)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://r.jina.ai/https://example.com/article?section=results"
        )
        assert request.headers["x-engine"] == "browser"
        assert "authorization" not in request.headers
        return httpx.Response(200, text=body, headers={"content-type": "text/plain"})

    settings = Settings(
        enable_jina_reader_fallback=True,
        jina_reader_url="https://r.jina.ai/",
        jina_reader_timeout_s=45,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        document = await AcquisitionService(settings, client)._jina_reader(
            str(_candidate().url), _candidate(), []
        )

    assert document is not None and document.success
    assert document.acquisition_method == "jina_reader"
    assert document.strategies_tried == ["jina_reader"]
    assert document.content.startswith("# Rendered article")


@pytest.mark.asyncio
async def test_disabled_jina_reader_is_not_recorded_as_tried():
    settings = Settings(enable_jina_reader_fallback=False)
    tried: list[str] = []
    async with httpx.AsyncClient() as client:
        document = await AcquisitionService(settings, client)._jina_reader(
            str(_candidate().url), _candidate(), tried
        )

    assert document is None
    assert tried == []


@pytest.mark.asyncio
async def test_acquire_uses_jina_before_scrapling(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def allow_url(url: str, allow_private: bool = False) -> None:
        pass

    class OrderedFallbackService(AcquisitionService):
        async def _direct(self, url, candidate, tried):
            calls.append("direct")
            tried.append("direct")

        async def _agentsearch(self, url, candidate, tried):
            calls.append("agentsearch_read")
            tried.append("agentsearch_read")

        async def _crawl4ai(self, url, candidate, tried):
            calls.append("crawl4ai")
            tried.append("crawl4ai")

        async def _jina_reader(self, url, candidate, tried):
            calls.append("jina_reader")
            tried.append("jina_reader")
            return self._document(
                candidate,
                "# Recovered\n\n" + ("Substantive rendered content. " * 20),
                "jina_reader",
                tried,
                "text/plain",
                final_url=url,
            )

        async def _scrapling(self, url, candidate, tried):
            raise AssertionError("Scrapling must not run after Jina Reader succeeds")

    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    async with httpx.AsyncClient() as client:
        document = await OrderedFallbackService(Settings(), client).acquire(_candidate())

    assert document.success
    assert calls == ["direct", "agentsearch_read", "crawl4ai", "jina_reader"]
    assert ACQUISITION_STRATEGY_ORDER[-2:] == ("jina_reader", "scrapling")
