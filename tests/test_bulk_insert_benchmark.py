from __future__ import annotations

import json

import pytest

from research_platform.db import PassageRow
from scripts.benchmark_bulk_insert import (
    COPY_COLUMNS,
    STRATEGIES,
    UPDATABLE_COLUMNS,
    aggregate_runs,
    build_passages,
    client_serialization_ms,
    copy_record,
    passage_row_values,
    rotated_strategies,
    seed_variant,
    validate_benchmark_url,
    validate_parameters,
    vector_literal,
    vector_parameters,
)
from scripts.report_bulk_insert import grouped_bar_svg, speedup_payload


def test_bulk_benchmark_data_matches_passage_row_schema() -> None:
    passages = build_passages(count=3, dimensions=8, text_chars=120)
    rows = [passage_row_values(passage) for passage in passages]

    assert len(rows) == 3
    assert len({row["id"] for row in rows}) == 3
    assert len({row["content_hash"] for row in rows}) == 3
    assert all(len(row["id"]) == 26 for row in rows)
    assert all(len(row["source_version_id"]) == 26 for row in rows)
    assert all(len(row["embedding"]) == 8 for row in rows)
    assert rows[0]["metadata_json"]["document_type"] == "text"


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+aiosqlite:///benchmark.db",
        "postgresql+asyncpg://bulk_benchmark:bulk_benchmark@example.com:55433/bulk_benchmark",
        "postgresql+asyncpg://bulk_benchmark:bulk_benchmark@127.0.0.1:5432/bulk_benchmark",
        "postgresql+asyncpg://bulk_benchmark:bulk_benchmark@127.0.0.1:55433/research",
    ],
)
def test_bulk_benchmark_refuses_non_isolated_database(database_url: str) -> None:
    with pytest.raises(ValueError):
        validate_benchmark_url(database_url)


def test_bulk_benchmark_accepts_only_dedicated_local_database() -> None:
    validate_benchmark_url(
        "postgresql+asyncpg://bulk_benchmark:bulk_benchmark@127.0.0.1:55433/bulk_benchmark"
    )


def test_bulk_benchmark_aggregate_reports_speed_and_validity() -> None:
    runs = [
        {
            "strategy": "core_executemany",
            "table": "passages",
            "preseeded": False,
            "wall_ms": wall_ms,
            "rows_per_second": 1000 / (wall_ms / 1000),
            "sql_statement_count": 1,
            "executemany_call_count": 1,
            "commit_count": 1,
            "io_delta": {
                "wal_bytes": 2048,
                "table_bytes": 1024,
                "io_write_ms": 2.5,
            },
            "validation": {"valid": True},
        }
        for wall_ms in [100, 110, 120, 130, 140]
    ]

    aggregate = aggregate_runs(runs, baseline_ms=600)

    assert aggregate["wall_ms_median"] == 120
    assert aggregate["wall_ms_mean"] == 120
    assert aggregate["wall_ms_stdev"] == pytest.approx(15.811, abs=0.001)
    assert aggregate["wall_ms_mad"] == 10
    assert aggregate["speedup_vs_row_commit_each"] == 5
    assert aggregate["sql_statement_count_median"] == 1
    assert aggregate["all_valid"] is True


def test_bulk_benchmark_uses_balanced_strategy_rotation() -> None:
    count = len(STRATEGIES)
    orders = [[spec.name for spec in rotated_strategies(repeat)] for repeat in range(1, count + 1)]

    assert len({tuple(order) for order in orders}) == count
    for position in range(count):
        assert {order[position] for order in orders} == {spec.name for spec in STRATEGIES}


@pytest.mark.parametrize(
    "parameters",
    [
        {"sizes": [], "repeats": 5, "warmups": 1, "dimensions": 768, "text_chars": 512},
        {"sizes": [0], "repeats": 5, "warmups": 1, "dimensions": 768, "text_chars": 512},
        {"sizes": [100], "repeats": 0, "warmups": 1, "dimensions": 768, "text_chars": 512},
        {"sizes": [100], "repeats": 5, "warmups": -1, "dimensions": 768, "text_chars": 512},
        {"sizes": [100], "repeats": 5, "warmups": 1, "dimensions": 0, "text_chars": 512},
        {
            "sizes": [100],
            "repeats": 5,
            "warmups": 1,
            "dimensions": 768,
            "text_chars": 512,
            "upsert_batch": 0,
        },
    ],
)
def test_bulk_benchmark_rejects_invalid_parameters(parameters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        validate_parameters(**parameters)  # type: ignore[arg-type]


def test_bulk_report_computes_repository_speedup_and_valid_svg() -> None:
    payload = {
        "datasets": [
            {
                "row_count": 100,
                "configurations": [
                    {
                        "strategy": "row_commit_each",
                        "wall_ms_median": 200.0,
                        "rows_per_second_median": 500.0,
                    },
                    {
                        "strategy": "row_add_one_transaction",
                        "wall_ms_median": 100.0,
                        "rows_per_second_median": 1000.0,
                    },
                    {
                        "strategy": "orm_add_all",
                        "wall_ms_median": 90.0,
                        "rows_per_second_median": 1111.0,
                    },
                    {
                        "strategy": "core_executemany",
                        "wall_ms_median": 80.0,
                        "rows_per_second_median": 1250.0,
                    },
                    {
                        "strategy": "repository_save_passages",
                        "wall_ms_median": 400.0,
                        "rows_per_second_median": 250.0,
                    },
                ],
            }
        ]
    }

    enriched = speedup_payload(payload)
    core = enriched["datasets"][0]["configurations"][3]
    svg = grouped_bar_svg(
        payload,
        metric="wall_ms_median",
        title="Test & kontrol",
        y_label="Milisaniye",
    )

    assert core["speedup_vs_repository"] == 5
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "Test &amp; kontrol" in svg
    assert svg.endswith("</svg>\n")


def test_bulk_benchmark_copy_record_matches_physical_columns() -> None:
    row = passage_row_values(build_passages(count=1, dimensions=4, text_chars=64)[0])

    record = copy_record(row)

    assert len(record) == len(COPY_COLUMNS)
    assert record[COPY_COLUMNS.index("id")] == row["id"]
    # COPY takes JSON columns as text, so both JSON fields must already be serialised.
    assert json.loads(record[COPY_COLUMNS.index("embedding")]) == row["embedding"]
    assert json.loads(record[COPY_COLUMNS.index("metadata")]) == row["metadata_json"]


def test_bulk_benchmark_vector_parameters_use_pgvector_literal() -> None:
    row = passage_row_values(build_passages(count=1, dimensions=4, text_chars=64)[0])

    parameters = vector_parameters(row)

    assert parameters["embedding"] == vector_literal(row["embedding"])
    assert parameters["embedding"].startswith("[") and parameters["embedding"].endswith("]")
    assert parameters["embedding"].count(",") == 3
    assert json.loads(parameters["metadata"]) == row["metadata_json"]
    assert "metadata_json" not in parameters


def test_bulk_benchmark_upsert_updates_every_mutable_column() -> None:
    """A missed column would silently keep a stale value on re-ingest."""
    identity = {"id", "source_version_id", "chunk_index"}
    physical = {
        column.name
        for column in PassageRow.__table__.columns  # type: ignore[attr-defined]
    }

    assert set(UPDATABLE_COLUMNS) == physical - identity


def test_bulk_benchmark_measures_client_serialization_without_a_database() -> None:
    rows = [passage_row_values(passage) for passage in build_passages(20, 64, 128)]

    measured = client_serialization_ms(rows, repeats=1)

    assert measured["embedding_json_dumps_ms"] > 0
    assert measured["embedding_vector_literal_ms"] > 0


def test_bulk_benchmark_seed_variant_changes_content_but_not_identity() -> None:
    """Re-ingest arms only measure the UPDATE branch if the seed really differs."""
    row = passage_row_values(build_passages(count=1, dimensions=4, text_chars=64)[0])

    seeded = seed_variant(row)

    assert seeded["id"] == row["id"]
    assert seeded["source_version_id"] == row["source_version_id"]
    assert seeded["chunk_index"] == row["chunk_index"]
    assert seeded["text"] != row["text"]
    assert seeded["content_hash"] != row["content_hash"]
    assert seeded["embedding"] != row["embedding"]
    assert row is not seeded and row["embedding"] != seeded["embedding"]


def test_bulk_benchmark_reingest_arms_are_preseeded() -> None:
    preseeded = {spec.name for spec in STRATEGIES if spec.preseed}

    assert preseeded == {"core_upsert_batched_reingest", "repository_save_passages_reingest"}
    # Each re-ingest arm must pair with an insert arm running the same code.
    for name in preseeded:
        assert name.removesuffix("_reingest") in {spec.name for spec in STRATEGIES}
