from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .rate_limits import DomainLimiter
from .schemas import ConnectorCandidate

logger = logging.getLogger(__name__)

EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"


@dataclass(frozen=True)
class OpenAccessTarget:
    url: str
    kind: Literal["pmc_jats", "oa_pdf", "oa_landing"]
    source: Literal["metadata", "europe_pmc", "unpaywall"]
    license: str | None = None
    version: str | None = None


def europe_pmc_jats_url(pmcid: str) -> str:
    """Europe PMC serves the same JATS as NCBI, unauthenticated and without a key."""
    value = str(pmcid).strip().upper()
    if not value:
        return ""
    if not value.startswith("PMC"):
        value = f"PMC{value}"
    return EUROPE_PMC_FULLTEXT.format(pmcid=value)


def _clean(value: Any) -> str:
    return str(value).strip() if value else ""


def oa_targets_from_metadata(candidate: ConnectorCandidate) -> list[OpenAccessTarget]:
    """Targets already in hand, best first. Pure; issues no requests.

    OpenAlex writes `best_oa_location` and Semantic Scholar writes `openAccessPdf` into the
    same `open_access_location` key with different shapes (`pdf_url`/`landing_page_url` vs
    `url`), and PMCIDs arrive under `scholarly_ids.pmcid`. Ordering is JATS, then PDF, then
    landing page: JATS is structured text, a PDF needs extraction that can silently degrade,
    and a landing page is HTML that `_direct` would have reached anyway.
    """
    metadata = candidate.metadata or {}
    ids = metadata.get("scholarly_ids") or {}
    location = metadata.get("open_access_location") or {}
    if not isinstance(location, dict):
        location = {}
    licence = _clean(location.get("license")) or None
    version = _clean(location.get("version")) or None

    targets: list[OpenAccessTarget] = []
    jats = europe_pmc_jats_url(_clean(ids.get("pmcid")))
    if jats:
        targets.append(OpenAccessTarget(jats, "pmc_jats", "europe_pmc", licence, version))

    pdf = _clean(location.get("pdf_url")) or _clean(location.get("url"))
    if pdf:
        targets.append(OpenAccessTarget(pdf, "oa_pdf", "metadata", licence, version))

    landing = _clean(location.get("landing_page_url"))
    if landing and landing != pdf:
        targets.append(OpenAccessTarget(landing, "oa_landing", "metadata", licence, version))
    return targets


async def resolve_unpaywall(
    client: httpx.AsyncClient,
    doi: str,
    *,
    mailto: str,
    timeout_s: float,
    limiter: DomainLimiter,
) -> OpenAccessTarget | None:
    """Ask Unpaywall only when metadata carried nothing. None on any failure.

    A resolution miss must never fail acquisition: the caller still has `_direct` and the
    whole scraper ladder behind it, so every error here is a fallthrough, not a raise.
    """
    doi = _clean(doi).lower().removeprefix("https://doi.org/")
    if not doi or not mailto:
        return None
    url = UNPAYWALL_API.format(doi=doi)
    try:
        await limiter.wait(url)
        response = await client.get(url, params={"email": mailto}, timeout=timeout_s)
        if response.status_code != 200:
            return None
        location = (response.json() or {}).get("best_oa_location") or {}
    except Exception as exc:  # noqa: BLE001 - a lookup miss falls through, it does not raise
        logger.info("unpaywall lookup failed for %s: %s", doi, exc)
        return None
    if not isinstance(location, dict):
        return None
    licence = _clean(location.get("license")) or None
    version = _clean(location.get("version")) or None
    pdf = _clean(location.get("url_for_pdf"))
    if pdf:
        return OpenAccessTarget(pdf, "oa_pdf", "unpaywall", licence, version)
    landing = _clean(location.get("url_for_landing_page")) or _clean(location.get("url"))
    if landing:
        return OpenAccessTarget(landing, "oa_landing", "unpaywall", licence, version)
    return None


def candidate_doi(candidate: ConnectorCandidate) -> str:
    metadata = candidate.metadata or {}
    ids = metadata.get("scholarly_ids") or {}
    doi = _clean(ids.get("doi")) or _clean(metadata.get("doi"))
    if not doi:
        persistent = _clean(candidate.persistent_id)
        if persistent.startswith("10."):
            doi = persistent
    return doi.lower().removeprefix("https://doi.org/")
