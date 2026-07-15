from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import io
import socket
import time
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader

from .config import Settings
from .passages import html_to_markdown
from .normalization import (
    canonicalize_url, detect_document_type, detect_language, extract_links,
)
from .schemas import AcquiredDocument, ConnectorCandidate


PAYWALL_MARKERS = (
    "subscribe to continue", "subscription required", "become a subscriber",
    "abone olarak", "abonelik gereklidir", "sign in to continue reading",
)


class UnsafeUrlError(ValueError):
    pass


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


class AcquisitionService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.limiter = DomainLimiter(settings.domain_delay_s)

    async def acquire(self, candidate: ConnectorCandidate) -> AcquiredDocument:
        url = str(candidate.url)
        tried: list[str] = []
        try:
            await validate_public_url(url, self.settings.allow_private_networks)
        except Exception as exc:
            return AcquiredDocument(candidate=candidate, success=False, error=str(exc), strategies_tried=tried)

        direct = await self._direct(url, candidate, tried)
        if direct and direct.success:
            return direct

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

    def _document(
        self, candidate: ConnectorCandidate, content: str, method: str, tried: list[str],
        content_type: str, *, raw_content: str = "", document_type: str = "text",
        final_url: str | None = None, redirect_chain: list[str] | None = None,
        outgoing_links: list[str] | None = None, canonical_url: str | None = None,
    ) -> AcquiredDocument:
        normalized = content.replace("\x00", "").strip()
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
                links: list[str] = []
                canonical: str | None = None
                if document_type == "pdf":
                    reader = PdfReader(io.BytesIO(response.content))
                    text = "\n\n".join(
                        f"# Page {index}\n\n{page.extract_text() or ''}"
                        for index, page in enumerate(reader.pages, start=1)
                    )
                elif document_type == "html":
                    links, canonical = extract_links(raw, current)
                    text = html_to_markdown(raw)
                else:
                    text = response.text
                if len(text.strip()) < 400:
                    return None
                return self._document(
                    candidate, text, "direct", tried, ctype or "text/plain",
                    raw_content=raw, document_type=document_type, final_url=current,
                    redirect_chain=redirects, outgoing_links=links, canonical_url=canonical,
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
            markdown = row.get("markdown") or row.get("fit_markdown") or ""
            if isinstance(markdown, dict):
                markdown = markdown.get("fit_markdown") or markdown.get("raw_markdown") or ""
            links_data = row.get("links") or {}
            if isinstance(links_data, dict):
                link_rows = [*(links_data.get("internal") or []), *(links_data.get("external") or [])]
            else:
                link_rows = links_data if isinstance(links_data, list) else []
            links = [
                item.get("href") if isinstance(item, dict) else item for item in link_rows
            ]
            return self._document(
                candidate, markdown, "crawl4ai", tried, "text/markdown",
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
            links, canonical = extract_links(raw, url)
            text = html_to_markdown(raw)
            if len(text.strip()) < 400:
                return None
            return self._document(
                candidate, text, "scrapling", tried, "text/html", raw_content=raw,
                document_type="html", final_url=url, outgoing_links=links,
                canonical_url=canonical,
            )
        except Exception as exc:
            return AcquiredDocument(
                candidate=candidate, success=False, strategies_tried=tried, error=str(exc),
            )
