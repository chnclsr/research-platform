from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import psutil
import sqlalchemy
from sqlalchemy import event, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
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
PASSAGE_TABLE = "passages"
VECTOR_TABLE = "passages_vector"
DEFAULT_UPSERT_BATCH = 1000
# Physical column names, in the order COPY expects them.
COPY_COLUMNS = [
    "id",
    "source_version_id",
    "chunk_index",
    "section_path",
    "page_number",
    "start_char",
    "end_char",
    "text",
    "token_count",
    "content_hash",
    "embedding",
    "metadata",
]
# Everything the repository overwrites on a conflicting (source_version_id, chunk_index).
# These are physical column names, which is how `excluded` is keyed.
UPDATABLE_COLUMNS = [
    "section_path",
    "page_number",
    "start_char",
    "end_char",
    "text",
    "token_count",
    "content_hash",
    "embedding",
    "metadata",
]
# pg_stat_io counters live in backend-local memory and only reach shared memory on a
# flush that PostgreSQL rate limits to once per second. Without forcing the flush, any
# measurement window shorter than that second reports another window's I/O.
FORCE_STATS_FLUSH = "select pg_stat_force_next_flush()"
DIMENSION_EXPRESSIONS = {
    PASSAGE_TABLE: "jsonb_array_length(embedding)",
    VECTOR_TABLE: "vector_dims(embedding)",
}


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


@dataclass(frozen=True)
class StrategyContext:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    rows: list[dict[str, Any]]
    passages: list[Passage]
    upsert_batch: int
    dimensions: int


@dataclass(frozen=True)
class StrategyResult:
    commits: int
    # COPY bypasses the SQLAlchemy cursor hook, so its round trip is counted here instead.
    extra_statements: int = 0


def vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(value) for value in embedding) + "]"


def copy_record(values: dict[str, Any]) -> tuple[Any, ...]:
    return (
        values["id"],
        values["source_version_id"],
        values["chunk_index"],
        values["section_path"],
        values["page_number"],
        values["start_char"],
        values["end_char"],
        values["text"],
        values["token_count"],
        values["content_hash"],
        json.dumps(values["embedding"]),
        json.dumps(values["metadata_json"]),
    )


def vector_parameters(values: dict[str, Any]) -> dict[str, Any]:
    parameters = {
        key: value for key, value in values.items() if key not in {"embedding", "metadata_json"}
    }
    parameters["embedding"] = vector_literal(values["embedding"])
    parameters["metadata"] = json.dumps(values["metadata_json"])
    return parameters


VECTOR_INSERT = text(
    f"insert into {VECTOR_TABLE} ("
    + ", ".join(COPY_COLUMNS)
    + ") values (:id, :source_version_id, :chunk_index, :section_path, :page_number, "
    ":start_char, :end_char, :text, :token_count, :content_hash, "
    "cast(:embedding as vector), cast(:metadata as jsonb))"
)


async def driver_connection(connection: Any) -> Any:
    raw = await connection.get_raw_connection()
    return raw.driver_connection


async def row_commit_each(ctx: StrategyContext) -> StrategyResult:
    commits = 0
    async with ctx.session_factory() as session:
        for values in ctx.rows:
            session.add(PassageRow(**values))
            await session.commit()
            commits += 1
    return StrategyResult(commits=commits)


async def row_add_one_transaction(ctx: StrategyContext) -> StrategyResult:
    async with ctx.session_factory() as session:
        for values in ctx.rows:
            session.add(PassageRow(**values))
        await session.commit()
    return StrategyResult(commits=1)


async def orm_add_all(ctx: StrategyContext) -> StrategyResult:
    async with ctx.session_factory() as session:
        session.add_all([PassageRow(**values) for values in ctx.rows])
        await session.commit()
    return StrategyResult(commits=1)


async def core_executemany(ctx: StrategyContext) -> StrategyResult:
    async with ctx.session_factory() as session:
        await session.execute(insert(PassageRow), ctx.rows)
        await session.commit()
    return StrategyResult(commits=1)


async def core_upsert_batched(ctx: StrategyContext) -> StrategyResult:
    """The candidate production path: idempotent upsert in bounded batches."""
    statement = pg_insert(PassageRow)
    upsert = statement.on_conflict_do_update(
        constraint="uq_passage_version_chunk",
        set_={name: statement.excluded[name] for name in UPDATABLE_COLUMNS},
    )
    async with ctx.session_factory() as session:
        for start in range(0, len(ctx.rows), ctx.upsert_batch):
            await session.execute(upsert, ctx.rows[start : start + ctx.upsert_batch])
        await session.commit()
    return StrategyResult(commits=1)


async def copy_records(ctx: StrategyContext) -> StrategyResult:
    async with ctx.engine.begin() as connection:
        driver = await driver_connection(connection)
        # Serialisation stays inside the timed section so this is comparable to the
        # ORM strategies, which serialise while binding parameters.
        records = [copy_record(values) for values in ctx.rows]
        await driver.copy_records_to_table(PASSAGE_TABLE, records=records, columns=COPY_COLUMNS)
    return StrategyResult(commits=1, extra_statements=1)


async def vector_executemany(ctx: StrategyContext) -> StrategyResult:
    """Same statement shape as core_executemany against a native pgvector column."""
    async with ctx.session_factory() as session:
        await session.execute(VECTOR_INSERT, [vector_parameters(v) for v in ctx.rows])
        await session.commit()
    return StrategyResult(commits=1)


async def repository_save_passages(ctx: StrategyContext) -> StrategyResult:
    async with ctx.session_factory() as session:
        repo = Repository(session, actor=Principal.system())
        await repo.save_passages(ctx.passages)
    return StrategyResult(commits=1)


Strategy = Callable[[StrategyContext], Awaitable[StrategyResult]]


@dataclass(frozen=True)
class StrategySpec:
    name: str
    run: Strategy
    table: str


STRATEGIES: list[StrategySpec] = [
    StrategySpec("row_commit_each", row_commit_each, PASSAGE_TABLE),
    StrategySpec("row_add_one_transaction", row_add_one_transaction, PASSAGE_TABLE),
    StrategySpec("orm_add_all", orm_add_all, PASSAGE_TABLE),
    StrategySpec("core_executemany", core_executemany, PASSAGE_TABLE),
    StrategySpec("core_upsert_batched", core_upsert_batched, PASSAGE_TABLE),
    StrategySpec("copy_records", copy_records, PASSAGE_TABLE),
    StrategySpec("repository_save_passages", repository_save_passages, PASSAGE_TABLE),
    StrategySpec("vector_executemany", vector_executemany, VECTOR_TABLE),
]


def rotated_strategies(repeat: int) -> list[StrategySpec]:
    """Use a deterministic Latin rotation so every strategy occupies every position."""
    offset = (repeat - 1) % len(STRATEGIES)
    return STRATEGIES[offset:] + STRATEGIES[:offset]


def validate_parameters(
    *,
    sizes: list[int],
    repeats: int,
    warmups: int,
    dimensions: int,
    text_chars: int,
    upsert_batch: int = DEFAULT_UPSERT_BATCH,
) -> None:
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("Benchmark sizes must contain only positive integers")
    if repeats <= 0:
        raise ValueError("Benchmark repeats must be positive")
    if warmups < 0:
        raise ValueError("Benchmark warmups cannot be negative")
    if dimensions <= 0 or text_chars <= 0:
        raise ValueError("Embedding dimensions and text characters must be positive")
    if upsert_batch <= 0:
        raise ValueError("Upsert batch size must be positive")


async def prepare_database(engine: AsyncEngine, dimensions: int) -> None:
    async with engine.begin() as connection:
        database_name = await connection.scalar(text("select current_database()"))
        server_port = await connection.scalar(text("select inet_server_port()"))
        if database_name != EXPECTED_DATABASE or server_port != 5432:
            raise RuntimeError(
                f"Unexpected PostgreSQL target: database={database_name}, port={server_port}"
            )
        await connection.run_sync(PassageRow.__table__.create, checkfirst=True)
        await connection.execute(text("create extension if not exists vector"))
        await connection.execute(text(f"drop table if exists {VECTOR_TABLE}"))
        # Mirrors the passages table exactly except for the embedding column type, so the
        # JSONB and pgvector arms differ in one variable only.
        await connection.execute(
            text(
                f"""
                create table {VECTOR_TABLE} (
                  id varchar(26) primary key,
                  source_version_id varchar(26) not null,
                  chunk_index integer not null,
                  section_path text not null,
                  page_number integer,
                  start_char integer not null,
                  end_char integer not null,
                  text text not null,
                  token_count integer not null,
                  content_hash varchar(64) not null,
                  embedding vector({dimensions}) not null,
                  metadata jsonb not null,
                  constraint uq_vector_version_chunk unique (source_version_id, chunk_index)
                )
                """
            )
        )
        await connection.execute(
            text(f"create index ix_{VECTOR_TABLE}_version on {VECTOR_TABLE} (source_version_id)")
        )
        await connection.execute(
            text(f"create index ix_{VECTOR_TABLE}_hash on {VECTOR_TABLE} (content_hash)")
        )


async def reset_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f"truncate table {PASSAGE_TABLE}, {VECTOR_TABLE}"))


async def flush_backend_stats(engine: AsyncEngine) -> None:
    """Publish this backend's pending pg_stat_io counters before they are read.

    PostgreSQL only writes backend-local I/O counters into shared memory on a flush it
    rate limits to one per second, so a sub-second measurement window would otherwise
    report zero and leak its I/O into the next window. The pool is capped at a single
    connection so the backend flushed here is the backend that did the writing.
    """
    async with engine.begin() as connection:
        await connection.execute(text(FORCE_STATS_FLUSH))


async def stats_snapshot(engine: AsyncEngine, table: str) -> dict[str, float]:
    await flush_backend_stats(engine)
    async with engine.begin() as connection:
        # Force dirty buffers to storage outside the timed write section so pg_stat_io
        # captures work attributable to this case as closely as PostgreSQL permits.
        await connection.execute(text("checkpoint"))
        await connection.execute(text("select pg_stat_clear_snapshot()"))
        row = (
            (
                await connection.execute(
                    text(
                        f"""
                    select
                      pg_relation_size('{table}'::regclass)::double precision as heap_bytes,
                      pg_indexes_size('{table}'::regclass)::double precision as index_bytes,
                      pg_total_relation_size('{table}'::regclass)::double precision
                        as total_relation_bytes,
                      coalesce((select sum(writes)::double precision from pg_stat_io
                                where backend_type in ('client backend', 'checkpointer',
                                                       'background writer')), 0) as io_writes,
                      coalesce((select sum(write_time)::double precision from pg_stat_io
                                where backend_type in ('client backend', 'checkpointer',
                                                       'background writer')), 0) as io_write_ms,
                      coalesce((select sum(extends)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_extends,
                      coalesce((select sum(extend_time)::double precision from pg_stat_io
                                where backend_type = 'client backend'), 0) as io_extend_ms,
                      coalesce((select sum(fsyncs)::double precision from pg_stat_io
                                where backend_type in ('client backend', 'checkpointer',
                                                       'background writer')), 0) as io_fsyncs,
                      coalesce((select sum(fsync_time)::double precision from pg_stat_io
                                where backend_type in ('client backend', 'checkpointer',
                                                       'background writer')), 0) as io_fsync_ms
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
        return {key: float(value or 0) for key, value in row.items()}


async def wal_position(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                text("select pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')::bigint")
            )
            or 0
        )


async def row_count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(text(f"select count(*) from {table}")) or 0)


def stats_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {key: round(after[key] - before[key], 3) for key in before}


async def validate_rows(
    engine: AsyncEngine,
    table: str,
    expected_count: int,
    dimensions: int,
) -> dict[str, Any]:
    dimension_expression = DIMENSION_EXPRESSIONS[table]
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        f"""
                    select
                      count(*) as row_count,
                      count(*) filter (where {dimension_expression} = :dimensions)
                        as embedding_dimension_matches,
                      count(distinct content_hash) as distinct_content_hashes,
                      count(distinct id) as distinct_ids,
                      count(distinct chunk_index) as distinct_chunk_indexes,
                      count(*) filter (where embedding is null) as null_embeddings
                    from {table}
                    """
                    ),
                    {"dimensions": dimensions},
                )
            )
            .mappings()
            .one()
        )
    validation = {key: int(value) for key, value in row.items()}
    validation["valid"] = (
        validation["row_count"] == expected_count
        and validation["embedding_dimension_matches"] == expected_count
        and validation["distinct_content_hashes"] == expected_count
        and validation["distinct_ids"] == expected_count
        and validation["distinct_chunk_indexes"] == expected_count
        and validation["null_embeddings"] == 0
    )
    return validation


async def run_case(
    *,
    engine: AsyncEngine,
    context: StrategyContext,
    counter: StatementCounter,
    spec: StrategySpec,
    repeat: int,
) -> dict[str, Any]:
    rows = context.rows
    await reset_table(engine)
    before = await stats_snapshot(engine, spec.table)
    start_row_count = await row_count(engine, spec.table)
    wal_before = await wal_position(engine)
    counter.reset()
    counter.active = True
    started = time.perf_counter()
    error: dict[str, str] | None = None
    result: StrategyResult | None = None
    try:
        result = await strategy_call(spec, context)
    except SQLAlchemyError as exc:  # A failed DB case must remain in raw output.
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        wall_ms = (time.perf_counter() - started) * 1000
        counter.active = False
    wal_after = await wal_position(engine)
    after = await stats_snapshot(engine, spec.table)
    validation = await validate_rows(engine, spec.table, len(rows), context.dimensions)
    end_row_count = validation["row_count"]
    extra_statements = result.extra_statements if result else 0
    return {
        "strategy": spec.name,
        "table": spec.table,
        "repeat": repeat,
        "row_count": len(rows),
        "embedding_dimensions": context.dimensions,
        "start_row_count": start_row_count,
        "end_row_count": end_row_count,
        "wall_ms": round(wall_ms, 3),
        "rows_per_second": round(len(rows) / max(wall_ms / 1000, 1e-9), 3),
        "sql_statement_count": counter.statements + extra_statements,
        "executemany_call_count": counter.executemany_calls,
        "commit_count": result.commits if result else None,
        "io_delta": {
            "wal_bytes": float(wal_after - wal_before),
            **stats_delta(before, after),
        },
        "validation": validation,
        "success": error is None
        and start_row_count == 0
        and end_row_count == len(rows)
        and validation["valid"],
        "error": error,
    }


async def strategy_call(spec: StrategySpec, context: StrategyContext) -> StrategyResult:
    return await spec.run(context)


def aggregate_runs(runs: list[dict[str, Any]], baseline_ms: float) -> dict[str, Any]:
    successful_runs = [run for run in runs if run.get("success", run["validation"]["valid"])]
    if not successful_runs:
        return {
            "strategy": runs[0]["strategy"],
            "table": runs[0]["table"],
            "repeats": len(runs),
            "successful_repeats": 0,
            "failed_repeats": len(runs),
            "all_valid": False,
            "runs": runs,
        }
    wall_values = [run["wall_ms"] for run in successful_runs]
    throughput_values = [run["rows_per_second"] for run in successful_runs]
    wall_median = statistics.median(wall_values)
    io_keys = successful_runs[0]["io_delta"]
    return {
        "strategy": runs[0]["strategy"],
        "table": runs[0]["table"],
        "repeats": len(runs),
        "successful_repeats": len(successful_runs),
        "failed_repeats": len(runs) - len(successful_runs),
        "wall_ms_mean": round(statistics.mean(wall_values), 3),
        "wall_ms_median": round(wall_median, 3),
        "wall_ms_min": min(wall_values),
        "wall_ms_max": max(wall_values),
        "wall_ms_stdev": round(statistics.stdev(wall_values), 3) if len(wall_values) > 1 else 0.0,
        "wall_ms_mad": round(
            statistics.median(abs(value - wall_median) for value in wall_values), 3
        ),
        "rows_per_second_mean": round(statistics.mean(throughput_values), 3),
        "rows_per_second_median": round(statistics.median(throughput_values), 3),
        "rows_per_second_min": min(throughput_values),
        "rows_per_second_max": max(throughput_values),
        "rows_per_second_stdev": round(statistics.stdev(throughput_values), 3)
        if len(throughput_values) > 1
        else 0.0,
        "speedup_vs_row_commit_each": round(baseline_ms / max(wall_median, 1e-9), 3),
        "sql_statement_count_median": statistics.median(
            run["sql_statement_count"] for run in successful_runs
        ),
        "executemany_call_count_median": statistics.median(
            run["executemany_call_count"] for run in successful_runs
        ),
        "commit_count_median": statistics.median(run["commit_count"] for run in successful_runs),
        **{
            f"{key}_median": round(
                statistics.median(run["io_delta"][key] for run in successful_runs), 3
            )
            for key in io_keys
        },
        "all_valid": len(successful_runs) == len(runs),
        "runs": runs,
    }


def command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if completed.returncode == 0 and output else None


def git_commit() -> str | None:
    return command_version(["git", "rev-parse", "HEAD"])


def git_is_dirty() -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(completed.stdout.strip()) if completed.returncode == 0 else None


def cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def client_serialization_ms(rows: list[dict[str, Any]], repeats: int = 3) -> dict[str, float]:
    """Cost of turning embeddings into wire payloads, with no database involved.

    Every strategy pays this before PostgreSQL sees a byte, so it bounds how much any
    write path can gain.
    """
    json_samples = []
    vector_samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        for values in rows:
            json.dumps(values["embedding"])
        json_samples.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        for values in rows:
            vector_literal(values["embedding"])
        vector_samples.append((time.perf_counter() - started) * 1000)
    return {
        "embedding_json_dumps_ms": round(statistics.median(json_samples), 3),
        "embedding_vector_literal_ms": round(statistics.median(vector_samples), 3),
    }


async def run_benchmark(
    *,
    database_url: str,
    sizes: list[int],
    repeats: int,
    warmups: int,
    dimensions: int,
    text_chars: int,
    upsert_batch: int,
) -> dict[str, Any]:
    validate_benchmark_url(database_url)
    validate_parameters(
        sizes=sizes,
        repeats=repeats,
        warmups=warmups,
        dimensions=dimensions,
        text_chars=text_chars,
        upsert_batch=upsert_batch,
    )
    # A single pooled connection keeps every write on one backend, which is what makes
    # the forced pg_stat_io flush attribute I/O to the case that caused it.
    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    counter = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter.before_cursor_execute)
    try:
        await prepare_database(engine, dimensions)
        async with engine.connect() as connection:
            postgres_version = str(await connection.scalar(text("select version()")))

        datasets = []
        for size in sizes:
            passages = build_passages(size, dimensions, text_chars)
            rows = [passage_row_values(passage) for passage in passages]
            context = StrategyContext(
                engine=engine,
                session_factory=session_factory,
                rows=rows,
                passages=passages,
                upsert_batch=upsert_batch,
                dimensions=dimensions,
            )
            serialization = client_serialization_ms(rows)
            for warmup in range(1, warmups + 1):
                for spec in rotated_strategies(warmup):
                    await reset_table(engine)
                    await strategy_call(spec, context)
            runs_by_strategy: dict[str, list[dict[str, Any]]] = {
                spec.name: [] for spec in STRATEGIES
            }
            for repeat in range(1, repeats + 1):
                for spec in rotated_strategies(repeat):
                    run = await run_case(
                        engine=engine,
                        context=context,
                        counter=counter,
                        spec=spec,
                        repeat=repeat,
                    )
                    runs_by_strategy[spec.name].append(run)
                    print(
                        f"RUN size={size} repeat={repeat} strategy={spec.name} "
                        f"wall_ms={run['wall_ms']:.3f} success={run['success']}",
                        flush=True,
                    )
            baseline_ms = statistics.median(
                run["wall_ms"] for run in runs_by_strategy["row_commit_each"]
            )
            configurations = [
                aggregate_runs(runs_by_strategy[spec.name], baseline_ms) for spec in STRATEGIES
            ]
            datasets.append(
                {
                    "row_count": size,
                    "client_serialization": serialization,
                    "configurations": configurations,
                }
            )
        return {
            "benchmark_version": "postgres_bulk_insert_v2",
            "generated_at": datetime.now(UTC).isoformat(),
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "operating_system": platform.freedesktop_os_release().get("PRETTY_NAME"),
                "cpu_model": cpu_model(),
                "logical_cpu_count": psutil.cpu_count(logical=True),
                "physical_cpu_count": psutil.cpu_count(logical=False),
                "ram_bytes": psutil.virtual_memory().total,
                "postgresql": postgres_version,
                "sqlalchemy": sqlalchemy.__version__,
                "asyncpg": asyncpg.__version__,
                "docker": command_version(["docker", "--version"]),
                "docker_compose": command_version(["docker", "compose", "version"]),
                "container_image": "pgvector/pgvector:pg16",
                "benchmark_commit": git_commit(),
                "benchmark_git_dirty": git_is_dirty(),
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
                "vector_storage": f"pgvector vector({dimensions}) in {VECTOR_TABLE}",
                "embedding_dimensions": dimensions,
                "text_chars": text_chars,
                "upsert_batch": upsert_batch,
                "strategy_order": "deterministic Latin rotation",
                "strategies": [spec.name for spec in STRATEGIES],
                "stats_flush": "pg_stat_force_next_flush before every pg_stat_io snapshot",
                "pool_size": 1,
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
    parser.add_argument("--upsert-batch", type=int, default=DEFAULT_UPSERT_BATCH)
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
        upsert_batch=args.upsert_batch,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
