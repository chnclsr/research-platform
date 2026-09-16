"""Recognising searches and pages that stopped at a bot check, CAPTCHA or login wall.

What is recognised here is only recorded and shown to the user when the run finishes. The
platform never solves a challenge, logs in, or retries on the user's behalf.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Literal
from urllib.parse import quote, quote_plus

import httpx

from .diagnostics import safe_diagnostic
from .normalization import canonicalize_url

AccessIssueReason = Literal["bot_block", "captcha", "login_wall"]

_CAPTCHA_MARKERS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "verify you are human",
)
_BOT_MARKERS = (
    "just a moment",
    "checking your browser",
    "security check required",
    "unusual activity",
    "security verification",
    "enable javascript and cookies",
    "automated queries",
    "bot detection",
    "access denied",
)
_LOGIN_MARKERS = (
    "login required",
    "log in to continue",
    "sign in to access",
    "authentication required",
)


def access_issue_key(kind: str, *, query: str = "", url: str = "", connector_id: str = "") -> str:
    """Stable per-run identity without keeping secrets or provider response bodies."""
    target = canonicalize_url(url) if url else " ".join(query.lower().split())
    value = "\x1f".join((kind, connector_id.lower().strip(), target))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_blocked_response(
    status: int | None,
    text: str,
    headers: Mapping[str, str],
    *,
    echoes: Iterable[str] = (),
) -> AccessIssueReason | None:
    """Name the wall behind an error response, or None for an ordinary failure.

    Only for responses that already failed: nothing here decides whether content is
    usable, so a loose marker costs at most one extra line in the user's list.

    ``cf-ray`` is deliberately not a signal. Cloudflare stamps it on every response it
    proxies, including an API's plain 403 for a bad key; ``cf-mitigated: challenge`` is
    the header it sets on the challenge page itself. JSON bodies are API errors, not
    challenge pages. ``echoes`` are strings the caller sent -- the search query -- which
    an error page may repeat back: on a run researching CAPTCHAs, the query alone would
    otherwise classify every failed search as a CAPTCHA.
    """
    if status in {401, 404, 429}:
        return None
    lowered_headers = {str(k).lower(): str(v).lower() for k, v in headers.items()}
    if "json" in lowered_headers.get("content-type", ""):
        return None
    lowered = text[:4000].lower()
    for echo in echoes:
        echo = echo.strip().lower()
        if echo:
            for form in {echo, quote_plus(echo), quote(echo)}:
                lowered = lowered.replace(form, " ")
    if any(marker in lowered for marker in _CAPTCHA_MARKERS):
        return "captcha"
    if any(marker in lowered for marker in _LOGIN_MARKERS):
        return "login_wall"
    challenged = lowered_headers.get("cf-mitigated") == "challenge"
    if status in {403, 503} and (
        challenged or any(marker in lowered for marker in _BOT_MARKERS)
    ):
        return "bot_block"
    return None


def classify_search_block(
    exc: Exception,
    observation: dict[str, Any],
    *,
    queries: Iterable[str] = (),
) -> AccessIssueReason | None:
    """Return only actionable access walls; rate limits and ordinary HTTP errors stay out.

    With a response in hand only the response speaks: an httpx error's own message
    carries the request URL, and with it the query.
    """
    response = getattr(exc, "response", None)
    status = observation.get("http_status") or getattr(response, "status_code", None)
    if isinstance(response, httpx.Response):
        try:
            text = response.text
        except httpx.ResponseNotRead:
            # Streaming responses may not have been consumed. Headers and status are
            # still enough to classify provider challenges without reading them here.
            text = ""
        return classify_blocked_response(status, text, response.headers, echoes=queries)
    return classify_blocked_response(status, str(exc), {}, echoes=queries)


def safe_issue_detail(exc: Exception | str, *, maximum: int = 500) -> str:
    """Diagnostics may explain the block, but credentials and full challenge pages never persist."""
    cleaned = safe_diagnostic(str(exc))
    return str(cleaned).replace("\x00", "")[:maximum]
