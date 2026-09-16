"""Client for the presentation polisher service (host bridge for agy & LibreOffice)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


async def polish_presentation(
    pptx_bytes: bytes,
    run_id: str | None = None,
    language: str = "tr",
    settings: Settings | None = None,
) -> bytes:
    """Send PPTX bytes to the presentation polisher service.

    If polishing fails or the service is disabled/unreachable, logs a warning
    and safely returns the original pptx_bytes untouched.
    """
    if not settings or not settings.presentation_polisher_enabled:
        return pptx_bytes

    url = settings.presentation_polisher_url.rstrip("/")
    if not url:
        return pptx_bytes

    endpoint = f"{url}/polish"
    params: dict[str, Any] = {"language": language}
    if run_id:
        params["run_id"] = run_id

    try:
        async with httpx.AsyncClient(
            timeout=settings.presentation_polisher_timeout_s
        ) as client:
            resp = await client.post(
                endpoint,
                content=pptx_bytes,
                headers={
                    "Content-Type": (
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
                },
                params=params,
            )
            if resp.status_code == 200 and resp.content:
                logger.info(
                    "Presentation polished successfully for run %s (%d -> %d bytes)",
                    run_id,
                    len(pptx_bytes),
                    len(resp.content),
                )
                return resp.content
            logger.warning(
                "Presentation polisher returned HTTP %s: %s (run %s). Keeping original PPTX.",
                resp.status_code,
                resp.text[:200],
                run_id,
            )
            return pptx_bytes
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Presentation polisher service unreachable or failed: %s (run %s). Keeping original PPTX.",
            exc,
            run_id,
        )
        return pptx_bytes
