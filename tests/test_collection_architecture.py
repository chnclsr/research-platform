from __future__ import annotations

import httpx

from research_platform.acquisition import AcquisitionService
from research_platform.config import get_settings
from research_platform.normalization import (
    canonicalize_url, detect_document_type, detect_language, extract_links,
)
from research_platform.passages import retrieve_passages
from research_platform.schemas import ConnectorCandidate, Passage, SourceFamily


def test_canonical_url_removes_tracking_fragment_and_default_port():
    value = canonicalize_url(
        "HTTPS://Example.COM:443/a//report/?utm_source=x&id=7#results"
    )
    assert value == "https://example.com/a/report?id=7"


def test_html_link_extraction_resolves_and_deduplicates_links():
    html = """
    <link rel="canonical" href="/report?utm_source=newsletter">
    <a href="/evidence?id=1&utm_campaign=x">Evidence</a>
    <a href="https://example.com/evidence?id=1">Duplicate</a>
    """
    links, canonical = extract_links(html, "https://example.com/start")
    assert links == ["https://example.com/evidence?id=1"]
    assert canonical == "https://example.com/report"


def test_document_type_and_language_are_detected_before_chunking():
    assert detect_document_type("application/octet-stream", b"%PDF-1.7") == "pdf"
    assert detect_document_type("text/plain", b"<!doctype html><html>") == "html"
    # Binary payloads must not read as text: acquisition only admits the text-ish types,
    # so "binary" is what keeps a JPEG supplementary file out of the corpus.
    assert detect_document_type("image/jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF") == "binary"
    assert detect_document_type("text/plain", b"PK\x03\x04\x00\x00report.docx") == "binary"
    assert detect_document_type("text/plain", b"A plain sentence with no NUL bytes.") == "text"
    assert detect_language("Bu araştırma için önemli bir yöntem ve sonuç bulunmaktadır.") == "tr"
    assert detect_language("The method and the results are available for review.") == "en"


def test_acquired_raw_content_carries_no_nul_bytes():
    """PostgreSQL rejects 0x00 in a text column, and source_versions stores raw_content
    next to the parsed text -- an unscrubbed byte there fails the insert for the whole
    NORMALIZE batch, not just its own document."""
    service = AcquisitionService(get_settings(), httpx.AsyncClient())
    candidate = ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.WEB,
        title="Supplementary file",
        url="https://example.com/supp",
    )
    document = service._document(
        candidate,
        "Parsed text with a stray \x00 byte.",
        "direct",
        ["direct"],
        "text/plain",
        raw_content="Raw snapshot with a stray \x00 byte.",
    )
    assert "\x00" not in document.content
    assert "\x00" not in document.raw_content


def test_rrf_retrieval_deduplicates_identical_passage_content():
    common = dict(
        chunk_index=0, section_path="Security limitations", start_char=0, end_char=80,
        text="Security redirects are validated and untrusted content is scrubbed before use.",
        token_count=11, content_hash="same", embedding=[1.0, 0.0],
    )
    passages = [
        Passage(source_version_id="version-a", **common),
        Passage(source_version_id="version-b", **common),
        Passage(
            source_version_id="version-c", chunk_index=0, section_path="Install",
            start_char=0, end_char=60, text="Install the service with Docker compose locally.",
            token_count=8, content_hash="different", embedding=[0.0, 1.0],
        ),
    ]
    selected = retrieve_passages(
        passages, ["security limitations and untrusted redirects"], [[1.0, 0.0]],
        per_question=5,
    )
    assert sum(item.content_hash == "same" for item in selected) == 1
    assert selected[0].section_path == "Security limitations"

