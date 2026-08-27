from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import event, func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import research_platform
from research_platform.auth import Principal
from research_platform.db import PassageRow
from research_platform.repository import Repository
from research_platform.schemas import Passage

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://bulk_benchmark:bulk_benchmark@127.0.0.1:55433/bulk_benchmark"
)
EXPECTED_DATABASE = "bulk_benchmark"
EXPECTED_PORT = 55433
SOURCE_VERSION_ID = "BULKBENCHSOURCEVERSION0000"
EXPECTED_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "research_platform"


def assert_current_worktree_source() -> None:
    imported_root = Path(research_platform.__file__).resolve().parent
    if imported_root != EXPECTED_PACKAGE_ROOT.resolve():
        raise RuntimeError(
            "research_platform was imported from a different checkout: "
            f"{imported_root}. Activate this worktree's environment or set PYTHONPATH=src."
        )


class StatementCounter:
    def __init__(self) -> None:
        self.active = False
        self.statements = 0
        self.executemany_calls = 0

    def reset(self) -> None:
        self.statements = 0
        self.executemany_calls = 0

    def before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if not self.active:
            return
        self.statements += 1
        self.executemany_calls += int(executemany)


def validate_benchmark_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("Benchmark requires the postgresql+asyncpg driver")
    if url.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Benchmark database must be local")
    if url.port != EXPECTED_PORT or url.database != EXPECTED_DATABASE:
        raise ValueError(
            "Refusing to modify a non-benchmark database; expected "
            f"127.0.0.1:{EXPECTED_PORT}/{EXPECTED_DATABASE}"
        )


def deterministic_embedding(row_index: int, dimensions: int) -> list[float]:
    return [
        round(((row_index * 31 + dimension * 17) % 2001 - 1000) / 1000, 6)
        for dimension in range(dimensions)
    ]


def build_passages(count: int, dimensions: int, text_chars: int) -> list[Passage]:
    passages = []
    for index in range(count):
        text_value = (f"Bulk insert benchmark passage {index}. " * 30)[:text_chars]
        passages.append(
            Passage(
                id=f"BULK{index:022d}",
                source_version_id=SOURCE_VERSION_ID,
                chunk_index=index,
                section_path=f"Benchmark/Section/{index % 12}",
                page_number=index // 4 + 1,
                start_char=index * text_chars,
                end_char=(index + 1) * text_chars,
                text=text_value,
                token_count=max(1, len(text_value.split())),
                content_hash=hashlib.sha256(text_value.encode("utf-8")).hexdigest(),
                language="en",
                document_type="text",
                embedding=deterministic_embedding(index, dimensions),
                retrieval_score=round((index % 101) / 100, 2),
                matched_questions=[f"benchmark question {index % 5}"],
            )
        )
    return passages


def passage_row_values(passage: Passage) -> dict[str, Any]:
    return {
        "id": passage.id,
        "source_version_id": passage.source_version_id,
        "chunk_index": passage.chunk_index,
        "section_path": passage.section_path,
        "page_number": passage.page_number,
        "start_char": passage.start_char,
        "end_char": passage.end_char,
        "text": passage.text,
        "token_count": passage.token_count,
        "content_hash": passage.content_hash,
        "embedding": passage.embedding,
        "metadata_json": {
            "retrieval_score": passage.retrieval_score,
            "matched_questions": passage.matched_questions,
            "language": passage.language,
            "document_type": passage.document_type,
        },
    }


async def row_commit_each(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    passages: list[Passage],
) -> int:
    commits = 0
    async with session_factory() as session:
        for values in rows:
            session.add(PassageRow(**values))
            await session.commit()
            commits += 1
    return commits


async def row_add_one_transaction(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    passages: list[Passage],
) -> int:
    async with session_factory() as session:
        for values in rows:
            session.add(PassageRow(**values))
        await session.commit()
    return 1


async def orm_add_all(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    passages: list[Passage],
) -> int:
    async with session_factory() as session:
        session.add_all([PassageRow(**values) for values in rows])
        await session.commit()
    return 1


async def core_executemany(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    passages: list[Passage],
) -> int:
    async with session_factory() as session:
        await session.execute(insert(PassageRow), rows)
        await session.commit()
    return 1


async def repository_save_passages(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    passages: list[Passage],
) -> int:
    async with session_factory() as session:
        repo = Repository(session, actor=Principal.system())
        await repo.save_passages(passages)
    return 1


Strategy = Callable[
    [async_sessionmaker[AsyncSession], list[dict[str, Any]], list[Passage]],
    Awaitable[int],
]

STRATEGIES: list[tuple[str, Strategy]] = [
    ("row_commit_each", row_commit_each),
    ("row_add_one_transaction", row_add_one_transaction),
    ("orm_add_all", orm_add_all),
    ("core_executemany", core_executemany),
    ("repository_save_passages", repository_save_passages),
]


async def prepare_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        database_name = await connection.scalar(text("select current_database()"))
        server_port = await connection.scalar(text("select inet_server_port()"))
        if database_name != EXPECTED_DATABASE or server_port != 5432:
            raise RuntimeError(
                f"Unexpected PostgreSQL target: database={database_name}, port={server_port}"
            )
        await connection.run_sync(PassageRow.__table__.create, checkfirst=True)


async def reset_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("truncate table passages"))


async def stats_snapshot(engine: AsyncEngine) -> dict[str, float]:
    async with engine.connect() as connection:
        await connection.execute(text("select pg_stat_force_next_flush()"))
        row = (
            (
                await connection.execute(
                    text(
                        """
                    select
                      (select wal_bytes::double precision from pg_stat_wal) as wal_bytes,
                      pg_total_relation_size('passages'::regclass)::double precision as table_bytes,
                      coalesce((select sum(writes)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_writes,
                      coalesce((select sum(write_time)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_write_ms,
                      coalesce((select sum(extends)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_extends,
                      coalesce((select sum(extend_time)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_extend_ms,
                      coalesce((select sum(fsyncs)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_fsyncs,
                      coalesce((select sum(fsync_time)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_fsync_ms
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
        return {key: float(value or 0) for key, value in row.items()}


def stats_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {key: round(after[key] - before[key], 3) for key in before}


async def validate_rows(
    engine: AsyncEngine,
    expected_count: int,
    dimensions: int,
) -> dict[str, Any]:
    async with engine.connect() as connection:
        row_count = int(await connection.scalar(select(func.count()).select_from(PassageRow)) or 0)
        dimension_count = int(
            await connection.scalar(
                select(func.count())
                .select_from(PassageRow)
                .where(func.jsonb_array_length(PassageRow.embedding) == dimensions)
            )
            or 0
        )
        hash_count = int(
            await connection.scalar(select(func.count(func.distinct(PassageRow.content_hash)))) or 0
        )
    return {
        "row_count": row_count,
        "embedding_dimension_matches": dimension_count,
        "distinct_content_hashes": hash_count,
        "valid": row_count == expected_count
        and dimension_count == expected_count
        and hash_count == expected_count,
    }


async def run_case(
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    counter: StatementCounter,
    strategy_name: str,
    strategy: Strategy,
    passages: list[Passage],
    rows: list[dict[str, Any]],
    dimensions: int,
    repeat: int,
) -> dict[str, Any]:
    await reset_table(engine)
    before = await stats_snapshot(engine)
    counter.reset()
    counter.active = True
    started = time.perf_counter()
    try:
        commit_count = await strategy(session_factory, rows, passages)
    finally:
        wall_ms = (time.perf_counter() - started) * 1000
        counter.active = False
    after = await stats_snapshot(engine)
    validation = await validate_rows(engine, len(rows), dimensions)
    return {
        "strategy": strategy_name,
        "repeat": repeat,
        "row_count": len(rows),
        "embedding_dimensions": dimensions,
        "wall_ms": round(wall_ms, 3),
        "rows_per_second": round(len(rows) / max(wall_ms / 1000, 1e-9), 3),
        "sql_statement_count": counter.statements,
        "executemany_call_count": counter.executemany_calls,
        "commit_count": commit_count,
        "io_delta": stats_delta(before, after),
        "validation": validation,
    }


def aggregate_runs(runs: list[dict[str, Any]], baseline_ms: float) -> dict[str, Any]:
    wall_values = [run["wall_ms"] for run in runs]
    wall_median = statistics.median(wall_values)
    return {
        "strategy": runs[0]["strategy"],
        "repeats": len(runs),
        "wall_ms_median": round(wall_median, 3),
        "wall_ms_min": min(wall_values),
        "wall_ms_max": max(wall_values),
        "wall_ms_mad": round(
            statistics.median(abs(value - wall_median) for value in wall_values), 3
        ),
        "rows_per_second_median": round(
            statistics.median(run["rows_per_second"] for run in runs), 3
        ),
        "speedup_vs_row_commit_each": round(baseline_ms / max(wall_median, 1e-9), 3),
        "sql_statement_count_median": statistics.median(run["sql_statement_count"] for run in runs),
        "executemany_call_count_median": statistics.median(
            run["executemany_call_count"] for run in runs
        ),
        "commit_count_median": statistics.median(run["commit_count"] for run in runs),
        "wal_bytes_median": round(
            statistics.median(run["io_delta"]["wal_bytes"] for run in runs), 3
        ),
        "table_bytes_median": round(
            statistics.median(run["io_delta"]["table_bytes"] for run in runs), 3
        ),
        "io_write_ms_median": round(
            statistics.median(run["io_delta"]["io_write_ms"] for run in runs), 3
        ),
        "all_valid": all(run["validation"]["valid"] for run in runs),
        "runs": runs,
    }


async def run_benchmark(
    *,
    database_url: str,
    sizes: list[int],
    repeats: int,
    warmups: int,
    dimensions: int,
    text_chars: int,
) -> dict[str, Any]:
    validate_benchmark_url(database_url)
    engine = create_async_engine(database_url, pool_size=5, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    counter = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter.before_cursor_execute)
    try:
        await prepare_database(engine)
        warmup_passages = build_passages(min(sizes), dimensions, text_chars)
        warmup_rows = [passage_row_values(passage) for passage in warmup_passages]
        for _ in range(warmups):
            for _, strategy in STRATEGIES:
                await reset_table(engine)
                await strategy(session_factory, warmup_rows, warmup_passages)

        datasets = []
        for size in sizes:
            passages = build_passages(size, dimensions, text_chars)
            rows = [passage_row_values(passage) for passage in passages]
            runs_by_strategy: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in STRATEGIES}
            for repeat in range(1, repeats + 1):
                ordered = STRATEGIES if repeat % 2 else list(reversed(STRATEGIES))
                for name, strategy in ordered:
                    run = await run_case(
                        engine=engine,
                        session_factory=session_factory,
                        counter=counter,
                        strategy_name=name,
                        strategy=strategy,
                        passages=passages,
                        rows=rows,
                        dimensions=dimensions,
                        repeat=repeat,
                    )
                    runs_by_strategy[name].append(run)
                    print(
                        f"RUN size={size} repeat={repeat} strategy={name} "
                        f"wall_ms={run['wall_ms']:.3f} valid={run['validation']['valid']}",
                        flush=True,
                    )
            baseline_ms = statistics.median(
                run["wall_ms"] for run in runs_by_strategy["row_commit_each"]
            )
            configurations = [
                aggregate_runs(runs_by_strategy[name], baseline_ms) for name, _ in STRATEGIES
            ]
            datasets.append({"row_count": size, "configurations": configurations})
        return {
            "benchmark_version": "postgres_bulk_insert_v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "database_driver": "postgresql+asyncpg",
                "database": EXPECTED_DATABASE,
                "host_port": EXPECTED_PORT,
                "gpu_required": False,
            },
            "methodology": {
                "sizes": sizes,
                "repeats": repeats,
                "warmups": warmups,
                "embedding_storage": "PostgreSQL JSONB (current PassageRow schema)",
                "embedding_dimensions": dimensions,
                "text_chars": text_chars,
                "strategy_order_alternated": True,
                "strategies": [name for name, _ in STRATEGIES],
            },
            "datasets": datasets,
        }
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", counter.before_cursor_execute)
        await engine.dispose()


async def main() -> None:
    assert_current_worktree_source()
    parser = argparse.ArgumentParser(
        description="PostgreSQL row-by-row vs bulk passage/embedding write benchmark"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("BULK_BENCHMARK_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--text-chars", type=int, default=512)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/bulk-insert/results/postgres_bulk_insert.json"),
    )
    args = parser.parse_args()
    payload = await run_benchmark(
        database_url=args.database_url,
        sizes=args.sizes,
        repeats=args.repeats,
        warmups=args.warmups,
        dimensions=args.dimensions,
        text_chars=args.text_chars,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
