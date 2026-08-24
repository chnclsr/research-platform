"""
What the reproducibility manifest has to say about parsing.

`10_reproducibility_manifest.json` carried `protocol.parsers` -- the caller's parser
overrides -- and nothing about what actually ran. Measured 2026-08-24 on a real run: the
manifest said `{"overrides": {}}` for a run whose PDF went through smart_pdf with 15 of
43 pages re-extracted by Docling on CUDA, and no deliverable outside the raw dump said
so. Since content_hash is the sha256 of the parsed text and CPU and CUDA do not produce
the same text, a manifest missing the engine and the device cannot reproduce its run.
"""

from __future__ import annotations

from types import SimpleNamespace

from research_platform.exporter import _parsing_manifest


def _cift(source_id: str, provenance: dict) -> tuple:
    return (
        SimpleNamespace(id=source_id),
        SimpleNamespace(content_hash="a" * 64, provenance=provenance),
    )


def test_manifest_records_the_engine_and_the_device_that_produced_the_text():
    versions = [
        _cift("src-pdf", {
            "document_type": "pdf",
            "parser_id": "smart_pdf",
            "parse_provenance": {
                "parser_profile": "inspector_v1",
                "engine_counts": {"pdf-inspector": 28, "docling-service": 15},
                "engine_devices": {"docling-service": "cuda"},
                "engine_build": {"docling-service": "docling 2.121.0, torch 2.13.0+cu132"},
                "engine_version": "engines_v2_2026-08-21",
                "esik_version": "gate_v2_kalibre_edilmedi_3a5bb5c9",
                "degraded": False,
                # The per-page breakdown belongs in 13_raw_sources.jsonl, not here.
                "pages": [{"page": 1, "engine": "docling-service"}],
            },
        }),
    ]
    (kayit,) = _parsing_manifest(versions)

    assert kayit["parser_id"] == "smart_pdf"
    assert kayit["engine_devices"] == {"docling-service": "cuda"}
    assert kayit["engine_counts"]["docling-service"] == 15
    assert "2.121.0" in kayit["engine_build"]["docling-service"]
    assert kayit["esik_version"] == "gate_v2_kalibre_edilmedi_3a5bb5c9"
    assert "pages" not in kayit, "the per-page trail belongs in the raw dump, not the manifest"


def test_a_single_extractor_source_stays_a_short_record():
    """Absent keys are dropped, not written as null -- most sources are not PDFs."""
    versions = [_cift("src-html", {
        "document_type": "html",
        "parser_id": "html_structured",
        "parse_provenance": {},
    })]
    (kayit,) = _parsing_manifest(versions)

    assert kayit == {
        "source_id": "src-html",
        "content_hash": "a" * 64,
        "document_type": "html",
        "parser_id": "html_structured",
    }


def test_a_degraded_parse_is_recorded_as_degraded():
    """`degraded` is the one flag that says the heavy engine did not deliver."""
    versions = [_cift("src-pdf", {
        "document_type": "pdf",
        "parser_id": "smart_pdf",
        "parse_provenance": {
            "parser_profile": "inspector_v1_degraded",
            "engine_counts": {"pdf-inspector": 10},
            "degraded": True,
        },
    })]
    (kayit,) = _parsing_manifest(versions)

    assert kayit["degraded"] is True
    assert "engine_devices" not in kayit


def test_a_version_with_no_provenance_at_all_does_not_raise():
    """Older rows predate parse_provenance; the export must not fail on them."""
    (kayit,) = _parsing_manifest([_cift("src-old", {})])

    assert kayit["parser_id"] is None
    assert kayit["source_id"] == "src-old"


def test_the_manifest_says_where_the_parse_time_went():
    """
    Acquisition already times each candidate, but that number is fetch AND parse
    together -- it cannot answer "was this document slow to download or slow to parse".
    The split is the useful part: measured on a real PDF, 7.3 s of parse was 0.4 s of
    routing and 6.3 s of the heavy engine.
    """
    versions = [_cift("src-pdf", {
        "document_type": "pdf",
        "parser_id": "smart_pdf",
        "parse_provenance": {
            "engine_counts": {"docling-service": 6, "pdf-inspector": 4},
            "duration_ms": 7270.4,
            "gate_duration_ms": 355.2,
            "engine_durations_ms": {"docling-service": 6336.5},
        },
    })]
    (kayit,) = _parsing_manifest(versions)

    assert kayit["duration_ms"] == 7270.4
    assert kayit["gate_duration_ms"] == 355.2
    assert kayit["engine_durations_ms"]["docling-service"] == 6336.5


def test_a_record_from_before_timing_was_measured_still_exports():
    """Runs that predate the duration fields must not grow null timing keys."""
    versions = [_cift("src-pdf", {
        "document_type": "pdf",
        "parser_id": "smart_pdf",
        "parse_provenance": {"engine_counts": {"pdf-inspector": 4}},
    })]
    (kayit,) = _parsing_manifest(versions)

    assert "duration_ms" not in kayit
    assert "engine_durations_ms" not in kayit
