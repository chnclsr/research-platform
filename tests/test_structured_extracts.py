"""
What `18_structured_extracts.json` carries, and why provenance belongs in it.

The artifact holds the tables and code blocks the parsers recovered as structure, so a
consumer that wants the grid does not have to re-parse the markdown. The rows are raw
parser output, not audited evidence -- a malformed cell stays malformed -- which is exactly
why each record names both the connector that found the source and the parser that read it.
Without those two fields a wrong table cannot be traced back to what produced it.
"""

from __future__ import annotations

from types import SimpleNamespace

from research_platform.exporter import structured_extract_rows


def _pair(source_id: str, connector_id: str, provenance: dict) -> tuple:
    return (
        SimpleNamespace(
            id=source_id,
            connector_id=connector_id,
            url=f"https://example.test/{source_id}",
            title=f"Source {source_id}",
        ),
        SimpleNamespace(id=f"{source_id}-v1", provenance=provenance),
    )


def test_a_record_names_the_connector_and_the_parser_behind_the_grid():
    rows = structured_extract_rows(
        [
            _pair(
                "S1",
                "openalex",
                {
                    "parser_id": "smart_pdf",
                    "tables": [{"headers": ["a"], "rows": [["1"]], "section_path": "Page 3"}],
                },
            )
        ]
    )

    assert len(rows) == 1
    assert rows[0]["connector_id"] == "openalex"
    assert rows[0]["parser_id"] == "smart_pdf"
    assert rows[0]["source_version_id"] == "S1-v1"
    assert rows[0]["tables"][0]["section_path"] == "Page 3"
    assert rows[0]["code_blocks"] == []


def test_a_source_whose_parse_found_no_structure_is_left_out():
    # The artifact is skipped entirely when nothing has structure, so carrying empty
    # records would put a source in the file that has nothing to say.
    rows = structured_extract_rows(
        [
            _pair("S1", "arxiv", {"parser_id": "html_structured", "tables": [], "code_blocks": []}),
            _pair("S2", "crossref", {"parser_id": "html_structured"}),
            _pair("S3", "arxiv", {"parser_id": "html_structured", "code_blocks": ["print(1)"]}),
        ]
    )

    assert [row["source_id"] for row in rows] == ["S3"]
    assert rows[0]["connector_id"] == "arxiv"


def test_a_version_recorded_without_provenance_does_not_raise():
    # Rows written before provenance carried parser detail still export.
    assert structured_extract_rows([_pair("S1", "pubmed", {})]) == []
    source, version = _pair("S1", "pubmed", {})
    version.provenance = None
    assert structured_extract_rows([(source, version)]) == []
