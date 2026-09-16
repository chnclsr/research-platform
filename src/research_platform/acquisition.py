from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse, urlsplit

import httpx

from .access_escalation import classify_blocked_response
from .config import Settings
from .github_repository import (
    GitHubRepositoryError,
    clone_and_render_repository,
    parse_github_repository_url,
)
from .normalization import canonicalize_url, detect_document_type, detect_language
from .open_access import candidate_doi, oa_targets_from_metadata, resolve_unpaywall
from .parsers import ParsedDocument, ParserRegistry, build_parser_registry
from .rate_limits import shared_domain_limiter
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

#: Bot-check interstitials, which a paywall marker does not catch and a length gate cannot:
#: measured 2026-09-08 over 467 acquired sources from three scoped runs, all 45 such pages
#: cleared the old 400-character floor, their median length being 602 characters.
#:
#: These are separated from PAYWALL_MARKERS because the outcome differs. A paywall means the
#: document exists and is withheld -- access_status "restricted". A bot check means we never
#: reached the document at all, so the honest status is "unavailable"; recording it as
#: restricted would claim knowledge of a paywall nobody saw.
#:
#: Rejecting these is safe in a way that rejecting boilerplate is not. In the same
#: measurement none of the 45 carried any trace of article text (no abstract, no
#: "we propose/present", no introduction), whereas 83% of the navigation-wrapped pages did
#: -- so chrome must be stripped rather than dropped, and is deliberately not handled here.
BLOCKED_MARKERS = (
    "just a moment", "security check required", "checking your browser",
    "verify you are human", "please make sure you are authorized",
    "we've detected unusual activity", "performing security verification",
    "enable javascript and cookies to continue",
)

#: These two only *name* a block that BLOCKED_MARKERS or a login redirect already found.
#: They must not decide one: a Wikipedia article on CAPTCHAs or an API reference saying
#: "authentication required" opens with them and is a perfectly good source.
CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha")
LOGIN_WALL_MARKERS = (
    "login required", "log in to continue", "sign in to access", "authentication required",
)

_ACCESS_WALL_ERRORS = {
    "bot_block": "Bot check interstitial",
    "captcha": "CAPTCHA challenge",
    "login_wall": "Login required",
}

#: Whole path segments, not substrings: "/auth" inside "/authors/..." is not a login page.
LOGIN_PATH_SEGMENTS = frozenset({"login", "log-in", "signin", "sign-in", "auth"})


def _redirected_to_login(original_url: str, final_url: str) -> bool:
    original = [part for part in urlparse(original_url).path.lower().split("/") if part]
    final = [part for part in urlparse(final_url).path.lower().split("/") if part]
    return (
        final != original
        and not LOGIN_PATH_SEGMENTS.intersection(original)
        and bool(LOGIN_PATH_SEGMENTS.intersection(final))
    )


#: What an interstitial never has and a paper always does. A marker alone cannot decide:
#: a paper *about* bot detection quotes the same phrases, and rejecting it would be
#: rejecting a source for its subject matter. In the 2026-09-08 measurement none of the 45
#: interstitials carried any of these, so requiring their absence costs nothing there while
#: protecting the paper that discusses them.
ARTICLE_TEXT_MARKERS = (
    "## abstract", "abstract:", "we propose", "we present", "we introduce",
    "in this paper", "in this study", "in this work", "## introduction",
    "our method", "experimental results",
)

#: The shortest parsed body treated as a document. Raised from 400 on 2026-09-08: over the
#: same 467 sources, 400 rejected 2% of the unusable pages and 900 rejects 27% of them while
#: still rejecting none of the 254 usable ones. The ladder stops here on purpose -- 2500
#: would only reach 30% of the unusable while discarding 19% of the usable, because
#: navigation-heavy pages are long, not short (their median body is 5,902 characters against
#: 6,933 for clean ones). Length cannot separate those; only shape can.
MIN_USABLE_TEXT_CHARS = 900


class UnsafeUrlError(ValueError):
    pass


# The order AcquisitionService.acquire() falls through, named so the pre-run plan can state
# it without restating it. Zotero candidates short-circuit before any of these.
ACQUISITION_STRATEGY_ORDER = (
    "github_repository",
    "open_access",
    "direct",
    "scholarly_metadata",
    "agentsearch_read",
    "crawl4ai",
    "jina_reader",
    "scrapling",
)


# getaddrinfo answers that mean "no answer right now" as often as "no such name". Measured
# 2026-09-14, run 01M2FGWHWKW1GCRXVWTC97B94H: 100 of 258 candidates failed with "[Errno -2]
# Name or service not known" -- all 27 of round 2 inside three seconds, none of round 3 thirty
# seconds later, every connector alike. Docker Desktop's resolver had timed out upstream; the
# names were fine. A name that really does not exist now costs the delays below before it
# fails, which is cheap next to losing a round to a resolver hiccup.
_TRANSIENT_DNS_ERRORS = frozenset(
    code
    for code in (
        getattr(socket, "EAI_AGAIN", None),
        getattr(socket, "EAI_NONAME", None),
        getattr(socket, "EAI_NODATA", None),
    )
    if code is not None
)
_DNS_RETRY_DELAYS_S: tuple[float, ...] = (1.0, 4.0)


async def _resolve(hostname: str) -> tuple[list, int]:
    """getaddrinfo, retried through a resolver outage. Returns the answer and the retries."""
    for retries, delay in enumerate((*_DNS_RETRY_DELAYS_S, None)):
        try:
            return await asyncio.to_thread(socket.getaddrinfo, hostname, None), retries
        except socket.gaierror as exc:
            if delay is None or exc.errno not in _TRANSIENT_DNS_ERRORS:
                raise
            await asyncio.sleep(delay)
    raise AssertionError("unreachable: the last delay is None")


async def validate_public_url(url: str, allow_private: bool = False) -> int:
    """Refuse a URL that is not public HTTP(S). Returns how many DNS retries resolving it took."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only absolute HTTP/HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in URLs are not allowed")
    if parsed.port and parsed.port not in {80, 443}:
        raise UnsafeUrlError("Non-standard URL ports are not allowed")
    retries = 0
    try:
        literal = ipaddress.ip_address(parsed.hostname)
        addresses = [literal]
    except ValueError:
        infos, retries = await _resolve(parsed.hostname)
        addresses = list({ipaddress.ip_address(info[4][0]) for info in infos})
    if allow_private:
        return retries
    for address in addresses:
        if not address.is_global:
            raise UnsafeUrlError(f"Non-public destination is blocked: {address}")
    return retries


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
            dns_retries = await validate_public_url(url, self.settings.allow_private_networks)
        except Exception as exc:
            return AcquiredDocument(candidate=candidate, success=False, error=str(exc), strategies_tried=tried)
        if dns_retries:
            # Where acquisition_metrics already reads, so a run shows the resolver outages it
            # rode out as well as the ones it lost to.
            tried.append(f"dns_retry:{dns_retries}")

        github = await self._github_repository(url, candidate, tried)
        if github and github.success:
            return github

        # Ahead of _direct, not behind it. _direct calls any response yielding 400 parsed
        # characters a success, and a publisher abstract landing page clears that easily,
        # so a step placed after it would only ever run for candidates whose publisher page
        # already failed -- the minority of exactly the population this is written for.
        open_access = await self._open_access_fulltext(candidate, tried)
        if open_access and open_access.success:
            return open_access

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

        jina = await self._jina_reader(url, candidate, tried)
        if jina and jina.success:
            return jina

        scrapling = await self._scrapling(url, candidate, tried)
        if scrapling and scrapling.success:
            return scrapling

        failures = [github, open_access, direct, agent, crawl, jina, scrapling]
        access_failure = next(
            (
                item for item in failures
                if item is not None
                and item.failure_reason in {"bot_block", "captcha", "login_wall"}
            ),
            None,
        )
        last_failure = next((item for item in reversed(failures) if item is not None), None)
        error = (
            access_failure.error
            if access_failure is not None
            else last_failure.error if last_failure is not None
            else "No strategy succeeded"
        )
        return AcquiredDocument(
            candidate=candidate, success=False, access_status="unavailable",
            strategies_tried=tried, error=error,
            failure_reason=access_failure.failure_reason if access_failure else None,
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
        lowered = normalized.lower()
        restricted = any(marker in lowered for marker in PAYWALL_MARKERS)
        # Two conditions, because either alone is wrong. The marker must open the body --
        # an interstitial announces itself immediately -- and the body must carry no trace
        # of article text, which is what separates a real block from a paper that merely
        # discusses one. Measured: interstitials satisfy both, papers about bot detection
        # satisfy only the first.
        head = lowered[:1500]
        interstitial = any(marker in head for marker in BLOCKED_MARKERS)
        # Being sent to a sign-in page is a block whatever that page says; the article
        # text check below still keeps a real document that happens to live there.
        login_redirect = _redirected_to_login(str(candidate.url), final_url or str(candidate.url))
        blocked = (
            not restricted
            and (interstitial or login_redirect)
            and not any(marker in lowered for marker in ARTICLE_TEXT_MARKERS)
        )
        failure_reason = None
        if restricted:
            failure_reason = "paywall"
        elif blocked and login_redirect:
            failure_reason = "login_wall"
        elif blocked and any(marker in head for marker in CAPTCHA_MARKERS):
            failure_reason = "captcha"
        elif blocked and any(marker in head for marker in LOGIN_WALL_MARKERS):
            failure_reason = "login_wall"
        elif blocked:
            failure_reason = "bot_block"
        withheld = restricted or blocked
        error = (
            "Paywall detected" if restricted
            else "Bot check interstitial" if interstitial and blocked
            else "Redirected to a login page" if blocked
            else None
        )
        return AcquiredDocument(
            candidate=candidate, success=bool(normalized) and not withheld,
            access_status=(
                "unavailable" if blocked
                else "restricted" if restricted
                else ("open" if normalized else "unavailable")
            ),
            content="" if withheld else normalized,
            raw_content="" if withheld else raw_content,
            content_type=content_type, document_type=document_type,
            language=detect_language(normalized), acquisition_method=method,
            canonical_url=canonical_url or canonicalize_url(final_url or str(candidate.url)),
            final_url=final_url or str(candidate.url), redirect_chain=redirect_chain or [],
            outgoing_links=outgoing_links or [],
            parser_id=parsed.parser_id if parsed else "",
            parse_provenance=parsed.parse_provenance if parsed else {},
            tables=[] if withheld else [t.model_dump(mode="json") for t in parsed.tables] if parsed else [],
            code_blocks=[] if withheld else (parsed.code_blocks if parsed else []),
            content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None,
            strategies_tried=tried.copy(), error=error,
            failure_reason=failure_reason,
        )

    async def _github_repository(
        self, url: str, candidate: ConnectorCandidate, tried: list[str],
    ) -> AcquiredDocument | None:
        ref = parse_github_repository_url(url)
        if ref is None or not self.settings.enable_github_repository_handler:
            return None
        tried.append("github_repository")
        try:
            reported_size = candidate.metadata.get("size")
            if reported_size is not None:
                try:
                    reported_bytes = int(reported_size) * 1024
                except (TypeError, ValueError):
                    reported_bytes = 0
                if reported_bytes > self.settings.github_repository_max_bytes:
                    raise GitHubRepositoryError(
                        "GitHub reports a repository size above the clone limit"
                    )
            snapshot = await clone_and_render_repository(
                ref,
                timeout_s=self.settings.github_clone_timeout_s,
                max_repository_bytes=self.settings.github_repository_max_bytes,
                max_files=self.settings.github_repository_max_files,
                max_file_bytes=self.settings.github_repository_max_file_bytes,
                max_chars=self.settings.github_repository_max_chars,
            )
            candidate.metadata.update(
                {
                    "content_scope": "repository_readme_manifests_and_source",
                    "repository_commit": snapshot.commit,
                    "repository_files_included": list(snapshot.included_files),
                    "repository_files_skipped": snapshot.skipped_files,
                    "repository_snapshot_truncated": snapshot.truncated,
                }
            )
            parsed = ParsedDocument(
                text=snapshot.markdown,
                document_type="text",
                parser_id="github_repository_structured",
                canonical_url=ref.web_url,
                parse_provenance={
                    "engine": "git",
                    "clone_depth": 1,
                    "commit": snapshot.commit,
                    "checkout_bytes": snapshot.checkout_bytes,
                    "files_included": len(snapshot.included_files),
                    "files_skipped": snapshot.skipped_files,
                    "truncated": snapshot.truncated,
                    "cleanup_confirmed": snapshot.cleanup_confirmed,
                },
            )
            return self._document(
                candidate,
                snapshot.markdown,
                "github_repository",
                tried,
                "text/markdown",
                document_type="text",
                final_url=ref.web_url,
                canonical_url=ref.web_url,
                parsed=parsed,
            )
        except (GitHubRepositoryError, OSError) as exc:
            logger.warning("GitHub repository acquisition failed for %s: %s", ref.web_url, exc)
            return AcquiredDocument(
                candidate=candidate,
                success=False,
                strategies_tried=tried.copy(),
                error=str(exc),
            )

    async def _open_access_fulltext(
        self, candidate: ConnectorCandidate, tried: list[str],
    ) -> AcquiredDocument | None:
        """Fetch the open-access full text when one is already identified.

        Returns None *without recording a strategy* when there is nothing to fetch. That
        silence is the contract: `strategies_tried` is asserted as an exact list in several
        tests, and a step that announced itself on every candidate it never acted on would
        turn each of those into a maintenance tax for no diagnostic gain.

        The fetch loop below duplicates about forty lines of `_direct` on purpose. `_direct`
        also carries the 400-character ladder, the alternate-parser retry and the redirect
        chain; extracting a shared helper would be a hundred-line change to the single most
        flake-suspect path in the suite, which is a worse trade than the duplication.
        """
        if not self.settings.enable_open_access_fulltext:
            return None
        if candidate.family.value != "academic":
            return None

        targets = oa_targets_from_metadata(candidate)
        if not targets and self.settings.enable_unpaywall and self.settings.unpaywall_mailto:
            doi = candidate_doi(candidate)
            if doi:
                resolved = await resolve_unpaywall(
                    self.client, doi,
                    mailto=self.settings.unpaywall_mailto,
                    timeout_s=self.settings.open_access_timeout_s,
                    limiter=self.limiter,
                )
                if resolved is not None:
                    targets = [resolved]
        if not targets:
            return None

        tried.append("open_access")
        target = targets[0]
        try:
            await validate_public_url(target.url, self.settings.allow_private_networks)
            await self.limiter.wait(target.url)
            response = await self.client.get(
                target.url, follow_redirects=True,
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.open_access_timeout_s,
            )
            response.raise_for_status()
            if len(response.content) > self.settings.max_download_bytes:
                raise ValueError("Response exceeds download limit")
            ctype = response.headers.get("content-type", "").lower()
            document_type = detect_document_type(ctype, response.content)
            if document_type not in {"text", "html", "json", "xml", "pdf"}:
                return None
            parser = self.parsers.select(
                document_type, ctype, response.content, self.parser_overrides
            )
            if parser is None:
                return None
            parsed = await asyncio.to_thread(
                parser.parse, response.content, url=target.url, content_type=ctype
            )
        except Exception as exc:  # noqa: BLE001 - a resolution miss falls through to _direct
            logger.info("open-access fetch failed for %s: %s", target.url, exc)
            candidate.metadata["open_access_rejected"] = "fetch_failed"
            return None

        if len(parsed.text.strip()) < self.settings.open_access_min_chars:
            # We asked a provider for full text and got something short, so this is a miss,
            # not a degraded parse. Say so and let _direct have the candidate back.
            candidate.metadata["open_access_rejected"] = "too_short"
            logger.info(
                "open-access body for %s was %d chars, below the %d minimum",
                target.url, len(parsed.text.strip()), self.settings.open_access_min_chars,
            )
            return None

        candidate.metadata["content_scope"] = "full_text"
        candidate.metadata["full_text_available"] = True
        candidate.metadata["open_access_resolved_by"] = target.source
        candidate.metadata["open_access_kind"] = target.kind
        candidate.metadata["open_access_license"] = target.license
        candidate.metadata["open_access_version"] = target.version
        return self._document(
            candidate, parsed.text, "open_access", tried,
            ctype or "application/xml",
            document_type=parsed.document_type,
            final_url=str(response.url),
            canonical_url=parsed.canonical_url,
            parsed=parsed,
        )

    async def _direct(self, url: str, candidate: ConnectorCandidate, tried: list[str]) -> AcquiredDocument | None:
        tried.append("direct")
        try:
            await self.limiter.wait(url)
            current = url
            redirects: list[str] = []
            for _ in range(self.settings.acquisition_max_redirects):
                response = await self.client.get(
                    current, follow_redirects=False, headers={"User-Agent": self.settings.user_agent},
                    timeout=self.settings.request_timeout_s,
                )
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    await validate_public_url(current, self.settings.allow_private_networks)
                    redirects.append(current)
                    continue
                if response.status_code in {401, 403, 503}:
                    # Named here because raise_for_status() below would turn the wall
                    # into an anonymous failure. A 401 on a document page is a login
                    # wall; unlike a search API's 401, it is not a missing key of ours.
                    reason = (
                        "login_wall" if response.status_code == 401
                        else classify_blocked_response(
                            response.status_code, response.text, response.headers
                        )
                    )
                    if reason is not None:
                        return AcquiredDocument(
                            candidate=candidate, success=False, access_status="unavailable",
                            acquisition_method="direct", final_url=current,
                            redirect_chain=redirects, strategies_tried=tried.copy(),
                            error=f"HTTP {response.status_code}: {_ACCESS_WALL_ERRORS[reason]}",
                            failure_reason=reason,
                        )
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
                if len(parsed.text.strip()) < MIN_USABLE_TEXT_CHARS:
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
                                if len(alt_parsed.text.strip()) >= MIN_USABLE_TEXT_CHARS:
                                    parsed = alt_parsed
                                    break
                            except Exception:
                                pass
                if len(parsed.text.strip()) < MIN_USABLE_TEXT_CHARS:
                    # A parser that had to degrade -- no OCR engine available for a
                    # scanned PDF, say -- produces almost nothing, which is
                    # indistinguishable here from a genuinely empty document. Say so,
                    # or the document disappears with no trace of why.
                    provenance = parsed.parse_provenance or {}
                    if provenance.get("degraded"):
                        logger.warning(
                            "dropping %s on the minimum-text check after a degraded "
                            "parse (parser=%s profile=%s notes=%s)",
                            current, parsed.parser_id,
                            provenance.get("parser_profile"), provenance.get("notes"),
                        )
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
                params={"url": url, "max_chars": self.settings.agentsearch_read_max_chars},
                timeout=self.settings.request_timeout_s,
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
                headers=headers,
                json={"urls": [url], "browser_config": {"headless": True}},
                timeout=self.settings.crawl4ai_timeout_s,
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
                    parsed = await asyncio.to_thread(
                        parser.parse, payload, url=url, content_type="text/html"
                    )
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

    async def _jina_reader(
        self, url: str, candidate: ConnectorCandidate, tried: list[str],
    ) -> AcquiredDocument | None:
        if not self.settings.enable_jina_reader_fallback:
            return None
        tried.append("jina_reader")
        try:
            # The target URL has already passed validate_public_url() in acquire(). Reader
            # is a fixed intermediary: never forward target-site credentials or cookies.
            endpoint = f"{self.settings.jina_reader_url.rstrip('/')}/{url}"
            response = await self.client.get(
                endpoint,
                headers={
                    "User-Agent": self.settings.user_agent,
                    # Jina's default auto mode may choose its non-JS curl engine. This
                    # fallback specifically exists for bot-protected and client-rendered
                    # pages left empty by the preceding strategies.
                    "X-Engine": "browser",
                },
                timeout=self.settings.jina_reader_timeout_s,
            )
            response.raise_for_status()
            if len(response.content) > self.settings.max_download_bytes:
                raise ValueError("Jina Reader response exceeds download limit")
            markdown = response.text.strip()
            if len(markdown) < MIN_USABLE_TEXT_CHARS:
                return None
            return self._document(
                candidate,
                markdown,
                "jina_reader",
                tried,
                response.headers.get("content-type", "text/plain"),
                document_type="text",
                final_url=url,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return AcquiredDocument(
                candidate=candidate, success=False, strategies_tried=tried, error=str(exc),
            )

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
            parsed = await asyncio.to_thread(
                parser.parse, payload, url=url, content_type="text/html"
            )
            if len(parsed.text.strip()) < MIN_USABLE_TEXT_CHARS:
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
