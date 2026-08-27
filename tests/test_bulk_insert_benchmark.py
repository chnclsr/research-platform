from __future__ import annotations

import pytest

from scripts.benchmark_bulk_insert import (
    aggregate_runs,
    build_passages,
    passage_row_values,
    validate_benchmark_url,
)


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
    assert aggregate["wall_ms_mad"] == 10
    assert aggregate["speedup_vs_row_commit_each"] == 5
    assert aggregate["sql_statement_count_median"] == 1
    assert aggregate["all_valid"] is True
