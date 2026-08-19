from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


TRACKING_PARAMETERS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode([
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
    ])
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == "a" and values.get("href"):
            absolute = urljoin(self.base_url, values["href"])
            if urlsplit(absolute).scheme in {"http", "https"}:
                self.links.append(canonicalize_url(absolute))
        if tag.lower() == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = canonicalize_url(urljoin(self.base_url, values.get("href", "")))


def extract_links(html: str, base_url: str, *, limit: int = 500) -> tuple[list[str], str | None]:
    parser = LinkExtractor(base_url)
    parser.feed(html)
    return list(dict.fromkeys(parser.links))[:limit], parser.canonical


def detect_document_type(content_type: str, content: bytes) -> str:
    header = content[:32].lstrip().lower()
    mime = content_type.lower()
    if content.startswith(b"%PDF-") or "application/pdf" in mime:
        return "pdf"
    if "json" in mime or header.startswith((b"{", b"[")):
        return "json"
    if "html" in mime or header.startswith((b"<!doctype html", b"<html")):
        return "html"
    if "xml" in mime or header.startswith(b"<?xml"):
        return "xml"
    # Everything unrecognised used to fall through to "text", so a DOI resolving to a
    # JPEG supplementary file was decoded with errors="replace", passed the 400-character
    # gate as mojibake and was admitted as a source -- and its NUL bytes then failed the
    # source_versions insert, which fails the whole run. A NUL never appears in text worth
    # parsing but appears in every image, archive and office document.
    if mime.startswith(("image/", "audio/", "video/")) or b"\x00" in content[:8192]:
        return "binary"
    return "text"


def detect_language(text: str) -> str:
    sample = f" {text[:12000].lower()} "
    if re.search(r"[çğıöşü]", sample):
        return "tr"
    turkish = sum(sample.count(f" {word} ") for word in ("ve", "bir", "için", "ile", "olarak"))
    english = sum(sample.count(f" {word} ") for word in ("the", "and", "for", "with", "from"))
    if turkish > english and turkish >= 2:
        return "tr"
    if english >= 2:
        return "en"
    return "und"

