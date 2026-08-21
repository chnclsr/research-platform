from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import logging
import socket
import time
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urlsplit

import httpx

from .config import Settings
from .normalization import canonicalize_url, detect_document_type, detect_language
from .parsers import ParsedDocument, ParserRegistry, build_parser_registry
from .schemas import AcquiredDocument, ConnectorCandidate

logger = logging.getLogger(__name__)


def _provenance_note(parsed: ParsedDocument) -> str:
    """Whatever the parser said about its own run, for the fallback log line.

    Read defensively: `parse_provenance` is not a field every parser build carries, and a
    diagnostic must never be the thing that raises.
    """
    provenance = getattr(parsed, "parse_provenance", None)
    if not isinstance(provenance, dict):
        return ""
    interesting = {
        key: provenance[key]
        for key in ("degraded", "notes", "engine", "pages_routed")
        if provenance.get(key)
    }
    return f" provenance={interesting}" if interesting else ""


PAYWALL_MARKERS = (
    "subscribe to continue", "subscription required", "become a subscriber",
    "abone olarak", "abonelik gereklidir", "sign in to continue reading",
)


class UnsafeUrlError(ValueError):
    pass


# The order AcquisitionService.acquire() falls through, named so the pre-run plan can state
# it without restating it. Zotero candidates short-circuit before any of these.
ACQUISITION_STRATEGY_ORDER = (
    "direct",
    "scholarly_metadata",
    "agentsearch_read",
    "crawl4ai",
    "scrapling",
)


async def validate_public_url(url: str, allow_private: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only absolute HTTP/HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in URLs are not allowed")
    if parsed.port and parsed.port not in {80, 443}:
        raise UnsafeUrlError("Non-standard URL ports are not allowed")
    try:
        literal = ipaddress.ip_address(parsed.hostname)
        addresses = [literal]
    except ValueError:
        infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
        addresses = list({ipaddress.ip_address(info[4][0]) for info in infos})
    if allow_private:
        return
    for address in addresses:
        if not address.is_global:
            raise UnsafeUrlError(f"Non-public destination is blocked: {address}")


class DomainLimiter:
    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        self.last_access: dict[str, float] = defaultdict(float)
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, url: str) -> None:
        domain = urlparse(url).hostname or ""
        async with self.locks[domain]:
            wait_for = self.delay_s - (time.monotonic() - self.last_access[domain])
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self.last_access[domain] = time.monotonic()


# Politeness is a property of the machine, not of a run. One limiter per AcquisitionService
# meant that with N runs in flight the same publisher was hit N times faster -- domain_delay_s
# silently became domain_delay_s / N. The reactive 429 backoff in the connectors is not a
# substitute: by the time it fires, the requests have already gone out.
_SHARED_LIMITERS: dict[float, DomainLimiter] = {}


def shared_domain_limiter(delay_s: float) -> DomainLimiter:
    """The process-wide limiter for this delay, created once."""
    limiter = _SHARED_LIMITERS.get(delay_s)
    if limiter is None:
        limiter = DomainLimiter(delay_s)
        _SHARED_LIMITERS[delay_s] = limiter
    return limiter


class AcquisitionService:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient,
        parsers: ParserRegistry | None = None,
    ):
        self.settings, self.client = settings, client
        self.limiter = shared_domain_limiter(settings.domain_delay_s)
        self.parsers = parsers or build_parser_registry()
        # Filled from the protocol's ParserSelection; empty means fully deterministic.
        self.parser_overrides: dict[str, str] = {}

    async def acquire(self, candidate: ConnectorCandidate) -> AcquiredDocument:
        url = str(candidate.url)
        tried: list[str] = []
        inline = candidate.metadata.get("inline_fulltext")
        if isinstance(inline, str) and inline.strip() and candidate.connector_id.startswith("zotero_"):
            tried.append("zotero_fulltext")
            return self._document(
                candidate, inline, "zotero_fulltext", tried,
                candidate.metadata.get("inline_content_type", "text/plain"),
                document_type="html"
                if candidate.metadata.get("inline_content_type") == "text/html" else "text",
                final_url=url,
            )
        if candidate.connector_id.startswith("zotero_"):
            tried.append("zotero_metadata")
            candidate.metadata["evidence_eligible"] = False
            content = "\n".join(filter(None, [
                f"# {candidate.title}",
                candidate.snippet,
                f"Authors: {', '.join(candidate.authors)}" if candidate.authors else "",
                f"Publisher: {candidate.publisher}" if candidate.publisher else "",
                f"Persistent ID: {candidate.persistent_id}" if candidate.persistent_id else "",
            ]))
            return self._document(
                candidate, content, "zotero_metadata", tried, "text/plain",
                document_type="text", final_url=url,
            )
        try:
            await validate_public_url(url, self.settings.allow_private_networks)
        except Exception as exc:
            return AcquiredDocument(candidate=candidate, success=False, error=str(exc), strategies_tried=tried)

        direct = await self._direct(url, candidate, tried)
        if direct and direct.success:
            return direct

        metadata_document = self._scholarly_metadata_document(candidate, tried)
        if metadata_document is not None:
            return metadata_document

        agent = await self._agentsearch(url, candidate, tried)
        if agent and agent.success:
            return agent

        crawl = await self._crawl4ai(url, candidate, tried)
        if crawl and crawl.success:
            return crawl

        scrapling = await self._scrapling(url, candidate, tried)
        if scrapling and scrapling.success:
            return scrapling

        error = (scrapling or crawl or agent or direct).error if (
            scrapling or crawl or agent or direct
        ) else "No strategy succeeded"
        return AcquiredDocument(
            candidate=candidate, success=False, access_status="unavailable",
            strategies_tried=tried, error=error,
        )

    def _scholarly_metadata_document(
        self,
        candidate: ConnectorCandidate,
        tried: list[str],
    ) -> AcquiredDocument | None:
        if candidate.family.value != "academic":
            return None
        abstract = candidate.metadata.get("abstract") or candidate.snippet
        if isinstance(abstract, list):
            abstract = " ".join(str(item) for item in abstract)
        abstract = " ".join(str(abstract or "").split())
        if len(abstract) < 240 or not candidate.title or not candidate.authors:
            return None
        tried.append("scholarly_metadata")
        candidate.metadata["content_scope"] = "abstract_and_metadata"
        candidate.metadata["full_text_available"] = False
        content = "\n\n".join(
            filter(
                None,
                [
                    f"# {candidate.title}",
                    f"## Abstract\n\n{abstract}",
                    (
                        f"## Authors\n\n{', '.join(candidate.authors)}"
                        if candidate.authors
                        else ""
                    ),
                    (
                        f"## Publisher\n\n{candidate.publisher}"
                        if candidate.publisher
                        else ""
                    ),
                    (
                        f"## Persistent identifier\n\n{candidate.persistent_id}"
                        if candidate.persistent_id
                        else ""
                    ),
                ],
            )
        )
        return self._document(
            candidate,
            content,
            "scholarly_metadata",
            tried,
            "text/plain",
            document_type="text",
            final_url=str(candidate.url),
        )

    def _document(
        self, candidate: ConnectorCandidate, content: str, method: str, tried: list[str],
        content_type: str, *, raw_content: str = "", document_type: str = "text",
        final_url: str | None = None, redirect_chain: list[str] | None = None,
        outgoing_links: list[str] | None = None, canonical_url: str | None = None,
        parsed: ParsedDocument | None = None,
    ) -> AcquiredDocument:
        normalized = content.replace("\x00", "").strip()
        # raw_content lands in a PostgreSQL text column too, so it needs the same scrub as
        # the parsed text. Base64 for PDFs is unaffected; a stray NUL from any other
        # strategy would otherwise reject the insert and fail the run.
        raw_content = raw_content.replace("\x00", "")
        restricted = any(marker in normalized.lower() for marker in PAYWALL_MARKERS)
        return AcquiredDocument(
            candidate=candidate, success=bool(normalized) and not restricted,
            access_status="restricted" if restricted else ("open" if normalized else "unavailable"),
            content="" if restricted else normalized,
            raw_content="" if restricted else raw_content,
            content_type=content_type, document_type=document_type,
            language=detect_language(normalized), acquisition_method=method,
            canonical_url=canonical_url or canonicalize_url(final_url or str(candidate.url)),
            final_url=final_url or str(candidate.url), redirect_chain=redirect_chain or [],
            outgoing_links=outgoing_links or [],
            parser_id=parsed.parser_id if parsed else "",
            tables=[] if restricted else [t.model_dump(mode="json") for t in parsed.tables] if parsed else [],
            code_blocks=[] if restricted else (parsed.code_blocks if parsed else []),
            content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None,
            strategies_tried=tried.copy(), error="Paywall detected" if restricted else None,
        )

    async def _direct(self, url: str, candidate: ConnectorCandidate, tried: list[str]) -> AcquiredDocument | None:
        tried.append("direct")
        try:
            await self.limiter.wait(url)
            current = url
            redirects: list[str] = []
            for _ in range(5):
                response = await self.client.get(
                    current, follow_redirects=False, headers={"User-Agent": self.settings.user_agent},
                    timeout=self.settings.request_timeout_s,
                )
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    await validate_public_url(current, self.settings.allow_private_networks)
                    redirects.append(current)
                    continue
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length > self.settings.max_download_bytes or len(response.content) > self.settings.max_download_bytes:
                    raise ValueError("Response exceeds download limit")
                ctype = response.headers.get("content-type", "").lower()
                document_type = detect_document_type(ctype, response.content)
                if document_type not in {"text", "html", "json", "xml", "pdf"}:
                    return None
                raw = (
                    response.text if document_type != "pdf"
                    else base64.b64encode(response.content).decode("ascii")
                )
                parser = self.parsers.select(
                    document_type, ctype, response.content, self.parser_overrides
                )
                if parser is None:
                    return None
                # Parsing is synchronous and can be expensive -- a page router or an OCR
                # pass costs seconds per page. _direct() runs acquisition_concurrency of
                # these at once, so doing it on the event loop stalls every other download
                # in flight, not just this one.
                parsed = await asyncio.to_thread(
                    parser.parse, response.content, url=current, content_type=ctype
                )
                if len(parsed.text.strip()) < 400:
                    # Said once, here: the fallback ladder replaces `parsed`, and the
                    # alternatives carry no provenance of their own, so if the document is
                    # dropped further down there is otherwise nothing left explaining why
                    # the parser that should have handled it did not.
                    logger.info(
                        "parser %s returned %d chars for %s (%s); trying alternatives%s",
                        parser.id,
                        len(parsed.text.strip()),
                        current,
                        document_type,
                        _provenance_note(parsed),
                    )
                    for alt in self.parsers.candidates(document_type, ctype, response.content):
                        if alt.id != parser.id:
                            try:
                                alt_parsed = await asyncio.to_thread(
                                    alt.parse, response.content, url=current, content_type=ctype
                                )
                                if len(alt_parsed.text.strip()) >= 400:
                                    parsed = alt_parsed
                                    break
                            except Exception:
                                pass
                if len(parsed.text.strip()) < 400:
                    return None
                return self._document(
                    candidate, parsed.text, "direct", tried, ctype or "text/plain",
                    raw_content=raw, document_type=document_type, final_url=current,
                    redirect_chain=redirects, outgoing_links=parsed.outgoing_links,
                    canonical_url=parsed.canonical_url, parsed=parsed,
                )
            raise ValueError("Too many redirects")
        except Exception:
            return None

    async def _agentsearch(self, url: str, candidate: ConnectorCandidate, tried: list[str]) -> AcquiredDocument | None:
        tried.append("agentsearch_read")
        try:
            response = await self.client.get(
                f"{self.settings.agentsearch_url}/read",
                params={"url": url, "max_chars": 100000}, timeout=self.settings.request_timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                return None
            return self._document(
                candidate, data.get("content", ""), "agentsearch_read", tried, "text/plain",
                final_url=data.get("final_url") or url,
                outgoing_links=[link for link in data.get("links", []) if isinstance(link, str)],
            )
        except Exception:
            return None

    async def _crawl4ai(self, url: str, candidate: ConnectorCandidate, tried: list[str]) -> AcquiredDocument | None:
        tried.append("crawl4ai")
        try:
            headers = {}
            if self.settings.crawl4ai_api_token:
                headers["Authorization"] = f"Bearer {self.settings.crawl4ai_api_token}"
            response = await self.client.post(
                f"{self.settings.crawl4ai_url}/crawl",
                headers=headers, json={"urls": [url], "browser_config": {"headless": True}}, timeout=90,
            )
            response.raise_for_status()
            data = response.json()
            rows = data.get("results") or []
            if not rows:
                return None
            row = rows[0]
            # Prefer crawl4ai's rendered HTML and run it through our own parser so every
            # acquisition strategy produces the same structure. Its markdown is only a
            # fallback: it is generated by a different converter, so tables and code would
            # come out shaped differently from the direct and scrapling paths.
            rendered = row.get("cleaned_html") or row.get("html") or ""
            markdown = ""
            parsed: ParsedDocument | None = None
            if isinstance(rendered, str) and rendered.strip():
                payload = rendered.encode("utf-8", "replace")
                parser = self.parsers.select("html", "text/html", payload, self.parser_overrides)
                if parser is not None:
                    parsed = parser.parse(payload, url=url, content_type="text/html")
                    markdown = parsed.text
            if not markdown.strip():
                parsed = None
            if not markdown.strip():
                markdown = row.get("markdown") or row.get("fit_markdown") or ""
                if isinstance(markdown, dict):
                    markdown = markdown.get("fit_markdown") or markdown.get("raw_markdown") or ""
            links_data = row.get("links") or {}
            if isinstance(links_data, dict):
                link_rows = [*(links_data.get("internal") or []), *(links_data.get("external") or [])]
            else:
                link_rows = links_data if isinstance(links_data, list) else []
            # crawl4ai reports mailto:, javascript: and fragment hrefs too. extract_links()
            # filters those on the other acquisition paths; without the same filter here a
            # hostless URL reaches the frontier and breaks its same-domain comparison.
            links = [
                item.get("href") if isinstance(item, dict) else item for item in link_rows
            ]
            links = [
                link for link in links
                if isinstance(link, str) and urlsplit(link).scheme in {"http", "https"}
            ]
            return self._document(
                candidate, markdown, "crawl4ai", tried, "text/markdown", parsed=parsed,
                document_type="html", final_url=row.get("url") or url,
                outgoing_links=[canonicalize_url(link) for link in links if isinstance(link, str)],
            )
        except Exception as exc:
            return AcquiredDocument(candidate=candidate, success=False, strategies_tried=tried, error=str(exc))

    async def _scrapling(
        self, url: str, candidate: ConnectorCandidate, tried: list[str],
    ) -> AcquiredDocument | None:
        if not self.settings.enable_scrapling_fallback:
            return None
        tried.append("scrapling")
        try:
            from scrapling.fetchers import Fetcher

            page = await asyncio.to_thread(
                Fetcher.get, url, stealthy_headers=False,
                timeout=int(self.settings.request_timeout_s * 1000),
            )
            if int(getattr(page, "status", 0) or 0) >= 400:
                return None
            raw = getattr(page, "html_content", None) or str(page)
            payload = raw.encode("utf-8", "replace")
            parser = self.parsers.select("html", "text/html", payload, self.parser_overrides)
            if parser is None:
                return None
            parsed = parser.parse(payload, url=url, content_type="text/html")
            if len(parsed.text.strip()) < 400:
                return None
            return self._document(
                candidate, parsed.text, "scrapling", tried, "text/html", raw_content=raw,
                document_type="html", final_url=url, outgoing_links=parsed.outgoing_links,
                canonical_url=parsed.canonical_url, parsed=parsed,
            )
        except Exception as exc:
            return AcquiredDocument(
                candidate=candidate, success=False, strategies_tried=tried, error=str(exc),
            )
