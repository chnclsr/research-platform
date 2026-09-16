"""Client for the presentation polisher service (host bridge for agy & LibreOffice).

Polishing never fails an export: the caller always gets a deck back -- the agent's or the
original -- together with a status and a reason, which ``polish_and_record`` writes onto
the run so a deck that was not polished says why.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pptx

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)

POLISH_EVENT = "presentation_polish"
_PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_HEADER = "X-Presentation-Polisher-"


@dataclass(frozen=True)
class PolishResult:
    data: bytes
    #: polished | unchanged (the service kept the original) | skipped (not attempted)
    #: | failed (the service could not be used)
    status: str
    reason: str
    agy_status: str = ""
    duration_s: float | None = None
    turns: int | None = None


def _valid_pptx(data: bytes) -> bool:
    """Reject a successful HTTP response that is not actually an OOXML presentation."""
    try:
        presentation = pptx.Presentation(io.BytesIO(data))
        # A report deck always has a slide.  Requiring one also rejects an otherwise
        # syntactically valid but useless empty package.
        return len(presentation.slides) > 0
    except Exception:  # noqa: BLE001 - python-pptx exposes several parser exceptions
        return False


def _number(value: str | None, kind: type) -> Any:
    try:
        return kind(value) if value else None
    except ValueError:
        return None


async def polish_presentation(
    pptx_bytes: bytes,
    run_id: str | None = None,
    language: str = "tr",
    settings: Any | None = None,
) -> PolishResult:
    """Send the deck to the polisher service; any failure returns the original deck."""

    def keep(status: str, reason: str) -> PolishResult:
        return PolishResult(data=pptx_bytes, status=status, reason=reason)

    if settings is None or not getattr(settings, "presentation_polisher_enabled", False):
        return keep("skipped", "disabled")
    url = str(getattr(settings, "presentation_polisher_url", "") or "").rstrip("/")
    if not url:
        return keep("skipped", "no-url")
    # The service lets an agent run commands on the host, so it accepts only its own
    # token; the shared SERVICE_TOKEN is deliberately not a fallback.
    token = str(getattr(settings, "presentation_polisher_token", "") or "").strip()
    if not token:
        logger.warning(
            "Presentation polisher is enabled but PRESENTATION_POLISHER_TOKEN is empty "
            "(run %s). Keeping original PPTX.",
            run_id,
        )
        return keep("skipped", "no-token")

    params: dict[str, Any] = {"language": language}
    if run_id:
        params["run_id"] = run_id
    try:
        async with httpx.AsyncClient(timeout=settings.presentation_polisher_timeout_s) as client:
            resp = await client.post(
                f"{url}/polish",
                content=pptx_bytes,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": _PPTX_MEDIA_TYPE,
                },
                params=params,
            )
    except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout):
        # Connected, but no answer in time. A connect timeout is an unreachable service
        # (on Windows a closed port times out instead of refusing) and falls through.
        logger.warning("Presentation polisher timed out (run %s). Keeping original PPTX.", run_id)
        return keep("failed", "timeout")
    except Exception as exc:  # noqa: BLE001 - polishing must never fail the export
        logger.warning(
            "Presentation polisher unreachable: %s (run %s). Keeping original PPTX.", exc, run_id
        )
        return keep("failed", f"unreachable:{type(exc).__name__}")

    if resp.status_code != 200:
        logger.warning(
            "Presentation polisher returned HTTP %s: %s (run %s). Keeping original PPTX.",
            resp.status_code,
            resp.text[:200],
            run_id,
        )
        return keep("failed", f"http-{resp.status_code}")

    outcome = resp.headers.get(f"{_HEADER}Status", "").lower()
    reason = resp.headers.get(f"{_HEADER}Reason", "")[:120] or "unspecified"
    details = {
        "agy_status": resp.headers.get(f"{_HEADER}Agy-Status", "")[:40],
        "duration_s": _number(resp.headers.get(f"{_HEADER}Duration-S"), float),
        "turns": _number(resp.headers.get(f"{_HEADER}Turns"), int),
    }
    if outcome == "unchanged":
        logger.info("Presentation polisher kept the original deck for run %s: %s", run_id, reason)
        return PolishResult(data=pptx_bytes, status="unchanged", reason=reason, **details)
    response_type = resp.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if outcome == "polished" and response_type == _PPTX_MEDIA_TYPE and _valid_pptx(resp.content):
        logger.info(
            "Presentation polished for run %s (%s, %d -> %d bytes)",
            run_id,
            reason,
            len(pptx_bytes),
            len(resp.content),
        )
        return PolishResult(data=resp.content, status="polished", reason=reason, **details)
    logger.warning(
        "Presentation polisher returned an untrusted or invalid PPTX response "
        "(status=%s, content_type=%s, run=%s). Keeping original PPTX.",
        outcome or "missing",
        response_type or "missing",
        run_id,
    )
    return PolishResult(data=pptx_bytes, status="failed", reason="invalid-response", **details)


async def polish_and_record(
    repo: Repository,
    run_id: str,
    pptx_bytes: bytes,
    *,
    language: str,
    settings: Any,
    stage: str,
    revision_id: str | None = None,
) -> bytes:
    """Polish the deck, record the outcome on the run and return the deck to deliver.

    Nothing is recorded while the feature is switched off, so a deployment without the
    bridge does not carry an event on every export.
    """
    result = await polish_presentation(
        pptx_bytes, run_id=run_id, language=language, settings=settings
    )
    if result.status == "skipped" and result.reason == "disabled":
        return result.data
    payload: dict[str, Any] = {
        "stage": stage,
        "status": result.status,
        "reason": result.reason,
        "agy_status": result.agy_status,
        "duration_s": result.duration_s,
        "turns": result.turns,
        "original_bytes": len(pptx_bytes),
        "output_bytes": len(result.data),
    }
    if revision_id:
        payload["revision_id"] = revision_id
    await repo.event(run_id, POLISH_EVENT, payload)
    return result.data
