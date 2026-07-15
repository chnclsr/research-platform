from __future__ import annotations

from research_platform.normalization import (
    canonicalize_url, detect_document_type, detect_language, extract_links,
)
from research_platform.passages import retrieve_passages
from research_platform.schemas import Passage


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
    assert detect_language("Bu araştırma için önemli bir yöntem ve sonuç bulunmaktadır.") == "tr"
    assert detect_language("The method and the results are available for review.") == "en"


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

