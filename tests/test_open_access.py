from __future__ import annotations

import httpx
import pytest

from research_platform import acquisition as acquisition_module
from research_platform.acquisition import ACQUISITION_STRATEGY_ORDER, AcquisitionService
from research_platform.config import Settings
from research_platform.open_access import (
    candidate_doi,
    europe_pmc_jats_url,
    oa_targets_from_metadata,
    resolve_unpaywall,
)
from research_platform.rate_limits import DomainLimiter
from research_platform.schemas import ConnectorCandidate, SourceFamily

JATS_BODY = "".join(
    f"<p>Sentence {n} of a full-text article body that is long enough to clear the "
    f"open-access minimum without repeating a single paragraph.</p>"
    for n in range(60)
)
JATS = (
    '<?xml version="1.0" encoding="UTF-8"?><article><front><article-meta>'
    "<title-group><article-title>A full-text article</article-title></title-group>"
    "<abstract><title>Abstract</title><p>An abstract.</p></abstract>"
    f"</article-meta></front><body><sec><title>Methods</title>{JATS_BODY}</sec></body>"
    "<back><ref-list><ref><label>1</label></ref></ref-list></back></article>"
)

LANDING_PAGE = "<html><body>" + ("<p>Publisher abstract page. </p>" * 40) + "</body></html>"


async def allow_url(url, allow_private=False):
    return None


def academic(metadata=None, url="https://example.org/paper") -> ConnectorCandidate:
    return ConnectorCandidate(
        connector_id="openalex",
        family=SourceFamily.ACADEMIC,
        title="A full-text article",
        url=url,
        snippet="",
        persistent_id="10.1000/paper",
        authors=["Ada Researcher"],
        metadata=metadata if metadata is not None else {},
    )


def test_metadata_targets_prefer_jats_then_pdf_then_landing():
    """OpenAlex and Semantic Scholar write different shapes into the same key."""
    openalex = academic({
        "scholarly_ids": {"pmcid": "PMC7029759"},
        "open_access_location": {
            "pdf_url": "https://example.org/a.pdf",
            "landing_page_url": "https://example.org/a",
            "license": "cc-by",
            "version": "publishedVersion",
        },
    })
    kinds = [target.kind for target in oa_targets_from_metadata(openalex)]
    assert kinds == ["pmc_jats", "oa_pdf", "oa_landing"]

    semantic_scholar = academic({
        "scholarly_ids": {"pmcid": None},
        "open_access_location": {"url": "https://example.org/s2.pdf"},
    })
    targets = oa_targets_from_metadata(semantic_scholar)
    assert [target.kind for target in targets] == ["oa_pdf"]
    assert targets[0].url == "https://example.org/s2.pdf"

    assert oa_targets_from_metadata(academic()) == []


def test_pmcid_is_normalised_into_a_europe_pmc_url():
    assert europe_pmc_jats_url("7029759").endswith("/PMC7029759/fullTextXML")
    assert europe_pmc_jats_url("PMC7029759").endswith("/PMC7029759/fullTextXML")
    assert europe_pmc_jats_url("") == ""


def test_candidate_doi_reads_every_place_a_doi_is_written():
    assert candidate_doi(academic({"scholarly_ids": {"doi": "10.1/A"}})) == "10.1/a"
    assert candidate_doi(academic({"doi": "https://doi.org/10.2/B"})) == "10.2/b"
    assert candidate_doi(academic()) == "10.1000/paper"


@pytest.mark.asyncio
async def test_unpaywall_is_called_only_when_metadata_is_empty():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, request=request,
            json={"best_oa_location": {"url_for_pdf": "https://example.org/oa.pdf"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        target = await resolve_unpaywall(
            client, "10.1/x", mailto="a@b.c", timeout_s=5, limiter=DomainLimiter(0.0),
        )
    assert calls == 1
    assert target is not None and target.kind == "oa_pdf" and target.source == "unpaywall"


@pytest.mark.asyncio
async def test_unpaywall_is_inert_without_a_mailto():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        target = await resolve_unpaywall(
            client, "10.1/x", mailto="", timeout_s=5, limiter=DomainLimiter(0.0),
        )
    assert target is None
    assert calls == 0


@pytest.mark.asyncio
async def test_unpaywall_failure_is_a_fallthrough_not_a_raise():
    async def handler(request):
        return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await resolve_unpaywall(
            client, "10.1/x", mailto="a@b.c", timeout_s=5, limiter=DomainLimiter(0.0),
        ) is None


@pytest.mark.asyncio
async def test_open_access_step_is_silent_when_there_is_no_target(monkeypatch):
    """No target means no entry in strategies_tried -- the exact-list assertions depend on it."""
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    tried: list[str] = []

    async def handler(request):
        raise AssertionError("no request should be made")

    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AcquisitionService(settings, client)
        assert await service._open_access_fulltext(academic(), tried) is None
    assert tried == []


@pytest.mark.asyncio
async def test_open_access_step_does_not_run_for_web_candidates(monkeypatch):
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    tried: list[str] = []
    candidate = ConnectorCandidate(
        connector_id="agentsearch_web",
        family=SourceFamily.WEB,
        title="A blog post",
        url="https://example.org/post",
        metadata={"scholarly_ids": {"pmcid": "PMC7029759"}},
    )

    async def handler(request):
        raise AssertionError("no request should be made")

    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AcquisitionService(settings, client)
        assert await service._open_access_fulltext(candidate, tried) is None
    assert tried == []


@pytest.mark.asyncio
async def test_open_access_full_text_beats_the_publisher_landing_page(monkeypatch):
    """The whole point: structured full text instead of a scraped abstract page."""
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    seen: list[str] = []

    async def handler(request):
        seen.append(str(request.url))
        if "fullTextXML" in str(request.url):
            return httpx.Response(
                200, request=request, text=JATS,
                headers={"content-type": "application/xml"},
            )
        return httpx.Response(
            200, request=request, text=LANDING_PAGE, headers={"content-type": "text/html"},
        )

    candidate = academic({"scholarly_ids": {"pmcid": "PMC7029759"}})
    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        document = await AcquisitionService(settings, client).acquire(candidate)

    assert document.success is True
    assert document.acquisition_method == "open_access"
    assert document.strategies_tried == ["open_access"]
    assert document.parser_id == "jats_structured"
    assert document.candidate.metadata["content_scope"] == "full_text"
    assert document.candidate.metadata["full_text_available"] is True
    assert document.candidate.metadata["open_access_resolved_by"] == "europe_pmc"
    assert document.candidate.metadata["open_access_kind"] == "pmc_jats"
    assert all("fullTextXML" in url for url in seen), "the publisher page was never fetched"


@pytest.mark.asyncio
async def test_short_open_access_body_falls_through_to_direct(monkeypatch):
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)

    async def handler(request):
        if "fullTextXML" in str(request.url):
            return httpx.Response(
                200, request=request,
                text="<article><body><sec><p>Too short.</p></sec></body></article>",
                headers={"content-type": "application/xml"},
            )
        return httpx.Response(
            200, request=request, text=LANDING_PAGE, headers={"content-type": "text/html"},
        )

    candidate = academic({"scholarly_ids": {"pmcid": "PMC7029759"}})
    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        document = await AcquisitionService(settings, client).acquire(candidate)

    assert document.strategies_tried == ["open_access", "direct"]
    assert document.candidate.metadata["open_access_rejected"] == "too_short"
    assert document.acquisition_method == "direct"


@pytest.mark.asyncio
async def test_open_access_fetch_failure_falls_through_to_direct(monkeypatch):
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)

    async def handler(request):
        if "fullTextXML" in str(request.url):
            return httpx.Response(500, request=request)
        return httpx.Response(
            200, request=request, text=LANDING_PAGE, headers={"content-type": "text/html"},
        )

    candidate = academic({"scholarly_ids": {"pmcid": "PMC7029759"}})
    settings = Settings(_env_file=None, testing=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        document = await AcquisitionService(settings, client).acquire(candidate)

    assert document.strategies_tried == ["open_access", "direct"]
    assert document.candidate.metadata["open_access_rejected"] == "fetch_failed"


@pytest.mark.asyncio
async def test_open_access_step_is_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    tried: list[str] = []

    async def handler(request):
        raise AssertionError("no request should be made")

    settings = Settings(_env_file=None, testing=True, enable_open_access_fulltext=False)
    candidate = academic({"scholarly_ids": {"pmcid": "PMC7029759"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AcquisitionService(settings, client)
        assert await service._open_access_fulltext(candidate, tried) is None
    assert tried == []


def test_open_access_sits_ahead_of_direct_in_the_declared_order():
    order = list(ACQUISITION_STRATEGY_ORDER)
    assert order.index("open_access") < order.index("direct")
    assert order[0] == "github_repository"
