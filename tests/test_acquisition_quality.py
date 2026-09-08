"""Edinim içerik kalitesi kapıları.

Ölçüldü 2026-09-08, üç kapsamlı koşudan 467 edinilmiş kaynak üzerinde: %46'sı gerçek
içerik değildi ve 45 bot-engeli sayfasının 45'i de eski 400 karakterlik tabanı geçiyordu.
Buradaki testler iki kapıyı da, gerçek engel metinleriyle koruyor.
"""

from __future__ import annotations

import httpx
import pytest

from research_platform.acquisition import (
    BLOCKED_MARKERS,
    MIN_USABLE_TEXT_CHARS,
    PAYWALL_MARKERS,
    AcquisitionService,
)
from research_platform.config import get_settings
from research_platform.schemas import ConnectorCandidate, SourceFamily

# Koşu 01M1XQTGQEFT08K2F0S0YP3665'ten alınan gerçek gövdeler.
RESEARCHGATE_ENGELI = (
    "Title: Just a moment... URL Source: https://www.researchgate.net/publication/394823357 "
    "Warning: This page maybe requiring CAPTCHA, please make sure you are authorized to "
    "access this page. Markdown Content: ## Security check required We've detected unusual "
    "activity from your network. To continue, complete the security check below. "
    "Ray ID: a37420c26ea60132 Client IP: 2600:1900:0:2105::1c00 "
    "© 2008-2026 ResearchGate GmbH. All rights reserved."
)
RSNA_ENGELI = (
    "Drafting the Future: The Dawn of AI Report Generation in Radiology | Radiology "
    "Title: Just a moment... URL Source: https://pubs.rsna.org/doi/10.1148/radiol.243378 "
    "Markdown Content: ## pubs.rsna.org ## Performing security verification This website "
    "uses a security service to protect against malicious bots. This page is displayed "
    "while the website verifies you are not a bot."
)


def _servis() -> AcquisitionService:
    return AcquisitionService(get_settings(), httpx.AsyncClient())


def _aday() -> ConnectorCandidate:
    return ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.ACADEMIC,
        title="Fixture publication",
        url="https://example.com/publication",
    )


@pytest.mark.parametrize("govde", [RESEARCHGATE_ENGELI, RSNA_ENGELI])
def test_bot_check_page_is_not_acquired_as_a_document(govde: str) -> None:
    document = _servis()._document(_aday(), govde, "crawl4ai", [], "text/html")

    assert document.success is False
    assert document.access_status == "unavailable"
    assert document.content == ""
    assert document.error == "Bot check interstitial"


def test_bot_check_is_unavailable_not_restricted() -> None:
    """A paywall means the document exists and is withheld; a bot check means we never saw it."""
    engel = _servis()._document(_aday(), RSNA_ENGELI, "crawl4ai", [], "text/html")
    duvar = _servis()._document(
        _aday(),
        "Subscription required to continue reading this article. " * 30,
        "direct", [], "text/html",
    )

    assert engel.access_status == "unavailable"
    assert engel.error == "Bot check interstitial"
    assert duvar.access_status == "restricted"
    assert duvar.error == "Paywall detected"


def test_a_paper_that_discusses_bot_detection_is_still_acquired() -> None:
    """Only the head is scanned, so the subject matter of a real paper cannot reject it."""
    makale = (
        "## Abstract We present a study of automated traffic on scholarly platforms. "
        "In this paper we analyse how publishers deploy interstitials. "
    ) + (
        "Our method inspects whether a site asks the visitor to verify you are human "
        "before serving content, and we measure how often a security check required "
        "banner appears in crawled corpora. " * 12
    )
    assert len(makale) > MIN_USABLE_TEXT_CHARS

    document = _servis()._document(_aday(), makale, "direct", [], "text/html")

    assert document.success is True
    assert document.access_status == "open"
    assert document.content


def test_marker_families_stay_separate() -> None:
    """The two lists answer different questions and must not drift into each other."""
    assert not set(BLOCKED_MARKERS) & set(PAYWALL_MARKERS)
    assert all(marker == marker.lower() for marker in BLOCKED_MARKERS)


def test_usable_text_floor_matches_the_measurement() -> None:
    """900 rejected 27% of unusable bodies and 0% of usable ones; 400 rejected 2%."""
    assert MIN_USABLE_TEXT_CHARS == 900
