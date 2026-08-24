"""Selection and reporting tests for the one-command PDF inspection tool."""

from __future__ import annotations

import sys
import tempfile
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts import inspect_bundle


def _args(**overrides) -> Namespace:
    values = {
        "page": None,
        "heavy": False,
        "fast": False,
        "all": False,
        "out": None,
        "pdf": None,
        "refresh": False,
        "md": None,
    }
    values.update(overrides)
    return Namespace(**values)


def _pages() -> tuple[dict[int, str], dict[int, dict]]:
    markdown = {1: "untouched", 2: "heavy", 3: "fallback", 4: "quarantined"}
    provenance = {
        1: {"page": 1, "engine": "pdf-inspector", "decision": [], "fell_back": False},
        2: {
            "page": 2,
            "engine": "docling-service",
            "decision": ["has_table_yuksek"],
            "fell_back": False,
        },
        3: {
            "page": 3,
            "engine": "pdf-inspector",
            "decision": ["needs_ocr"],
            "fell_back": True,
        },
        4: {
            "page": 4,
            "engine": "pdf-inspector",
            "decision": ["low_quality"],
            "fell_back": False,
            "karar_gerekcesi": "heavy_buyuk_icerik_kaybi",
        },
    }
    return markdown, provenance


def test_fast_selects_every_page_whose_final_engine_is_inspector():
    markdown, provenance = _pages()

    selected = inspect_bundle._wanted(markdown, provenance, _args(fast=True))

    assert selected == [1, 3, 4]
    assert inspect_bundle._fast_state(provenance[1]) == "untouched"
    assert inspect_bundle._fast_state(provenance[3]) == "fallback"
    assert inspect_bundle._fast_state(provenance[4]) == "quarantined"
    assert inspect_bundle._fast_state(provenance[2]) is None


def test_existing_heavy_selection_still_means_every_routed_page():
    markdown, provenance = _pages()

    assert inspect_bundle._wanted(markdown, provenance, _args(heavy=True)) == [2, 3, 4]


def test_all_selects_every_available_markdown_page():
    markdown, provenance = _pages()

    assert inspect_bundle._wanted(markdown, provenance, _args(all=True)) == [1, 2, 3, 4]


def _record() -> dict:
    markdown, provenance = _pages()
    content = "\n".join(f"# Page {number}\n{text}" for number, text in markdown.items())
    return {
        "source": {"id": "source-1", "url": "https://example.test/document.pdf"},
        "version": {
            "content_hash": "abc",
            "content": content,
            "provenance": {
                "document_type": "pdf",
                "parser_id": "smart_pdf",
                "parse_provenance": {
                    "pages": list(provenance.values()),
                    "engine_counts": {"pdf-inspector": 3, "docling-service": 1},
                },
            },
        },
    }


def test_fast_markdown_names_untouched_fallback_and_quarantined_pages():
    record = _record()

    report = "\n".join(inspect_bundle._markdown_report(record, _args(fast=True)))

    assert "retained fast: 3 · untouched: 1 · fallback: 1 · quarantined: 1" in report
    assert "Page 1 — pdf-inspector (untouched · fast path)" in report
    assert "Page 3 — pdf-inspector (fallback · needs_ocr)" in report
    assert (
        "Page 4 — pdf-inspector "
        "(quarantined · low_quality · heavy_buyuk_icerik_kaybi)" in report
    )
    assert "Page 2 —" not in report


def test_fast_cli_prints_only_inspector_retained_pages():
    output = StringIO()
    with (
        patch.object(sys, "argv", ["inspect_bundle.py", "bundle.zip", "--fast", "--md", "-"]),
        patch.object(inspect_bundle, "_resolve", lambda target, refresh=False: target),
        patch.object(inspect_bundle, "_records", lambda path: [_record()]),
        redirect_stdout(output),
    ):
        inspect_bundle.main()

    report = output.getvalue()
    assert "Page 1 — pdf-inspector (untouched · fast path)" in report
    assert "Page 3 — pdf-inspector (fallback · needs_ocr)" in report
    assert "Page 4 — pdf-inspector (quarantined" in report
    assert "Page 2 —" not in report


def test_fast_and_heavy_reports_get_distinct_automatic_filenames():
    run_id = "01M0SBTA6MQ07ETFHPKAJQH9HZ"
    with tempfile.TemporaryDirectory() as directory:
        fast = inspect_bundle._md_target(directory, run_id, _args(fast=True))
        heavy = inspect_bundle._md_target(directory, run_id, _args(heavy=True))

    assert fast.endswith(f"{run_id}_fast.md")
    assert heavy.endswith(f"{run_id}_heavy.md")
    assert fast != heavy


def test_mode_suffix_is_added_to_an_explicit_filename_and_not_duplicated():
    assert inspect_bundle._md_target("report.md", "bundle.zip", _args(fast=True)) == (
        "report_fast.md"
    )
    assert inspect_bundle._md_target("report_fast.md", "bundle.zip", _args(fast=True)) == (
        "report_fast.md"
    )
    assert inspect_bundle._md_target("report.md", "bundle.zip", _args(heavy=True)) == (
        "report_heavy.md"
    )


def test_all_and_page_reports_also_avoid_selection_collisions():
    assert inspect_bundle._md_target("report.md", "bundle.zip", _args(all=True)) == (
        "report_all.md"
    )
    assert inspect_bundle._md_target(
        "report.md", "bundle.zip", _args(page=[8, 3, 8])
    ) == "report_page-3-8.md"
