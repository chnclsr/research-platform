from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from research_platform.db import PassageRow

if __package__:
    from scripts.benchmark_bulk_insert import (
        DEFAULT_DATABASE_URL,
        DEFAULT_UPSERT_BATCH,
        PASSAGE_TABLE,
        StatementCounter,
        StrategyContext,
        assert_current_worktree_source,
        build_passages,
        core_upsert_batched,
        passage_row_values,
        prepare_database,
        repository_save_passages,
        reset_table,
        seed_variant,
        validate_benchmark_url,
        validate_rows,
    )
else:
    from benchmark_bulk_insert import (
        DEFAULT_DATABASE_URL,
        DEFAULT_UPSERT_BATCH,
        PASSAGE_TABLE,
        StatementCounter,
        StrategyContext,
        assert_current_worktree_source,
        build_passages,
        core_upsert_batched,
        passage_row_values,
        prepare_database,
        repository_save_passages,
        reset_table,
        seed_variant,
        validate_benchmark_url,
        validate_rows,
    )

DEFAULT_OUTPUT = Path("research/bulk-insert/results/postgres_bulk_insert_partial.json")


def mixed_seed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seed alternating chunks for an exact 50% UPDATE and 50% INSERT workload."""
    return [seed_variant(values) for index, values in enumerate(rows) if index % 2 == 0]


async def preseed_mixed(context: StrategyContext) -> None:
    async with context.session_factory() as session:
        await session.execute(insert(PassageRow), context.seed_rows)
        await session.commit()


async def run_partial_benchmark(
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
    if not sizes or any(size <= 1 or size % 2 for size in sizes):
        raise ValueError("Partial-conflict sizes must be even integers greater than one")
    if repeats <= 0 or warmups < 0 or dimensions <= 0 or text_chars <= 0 or upsert_batch <= 0:
        raise ValueError("Parameters must be positive; warmups may be zero")

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    counter = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter.before_cursor_execute)
    strategies = [
        ("bulk_upsert", core_upsert_batched),
        ("legacy_repository", repository_save_passages),
    ]
    try:
        await prepare_database(engine, dimensions)
        datasets = []
        for size in sizes:
            passages = build_passages(size, dimensions, text_chars)
            rows = [passage_row_values(passage) for passage in passages]
            context = StrategyContext(
                engine=engine,
                session_factory=session_factory,
                rows=rows,
                seed_rows=mixed_seed_rows(rows),
                passages=passages,
                upsert_batch=upsert_batch,
                dimensions=dimensions,
            )
            for _ in range(warmups):
                for _, strategy in strategies:
                    await reset_table(engine)
                    await preseed_mixed(context)
                    await strategy(context)

            runs: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in strategies}
            for repeat in range(1, repeats + 1):
                ordered = strategies if repeat % 2 else list(reversed(strategies))
                for name, strategy in ordered:
                    await reset_table(engine)
                    await preseed_mixed(context)
                    counter.reset()
                    counter.active = True
                    started = time.perf_counter()
                    result = await strategy(context)
                    wall_ms = (time.perf_counter() - started) * 1000
                    counter.active = False
                    validation = await validate_rows(engine, PASSAGE_TABLE, size, dimensions)
                    run = {
                        "repeat": repeat,
                        "wall_ms": round(wall_ms, 3),
                        "rows_per_second": round(size / (wall_ms / 1000), 3),
                        "sql_statement_count": counter.statements,
                        "executemany_call_count": counter.executemany_calls,
                        "commit_count": result.commits,
                        "start_row_count": len(context.seed_rows),
                        "end_row_count": validation["row_count"],
                        "validation": validation,
                        "success": validation["valid"],
                    }
                    runs[name].append(run)
                    print(
                        f"PARTIAL size={size} repeat={repeat} strategy={name} "
                        f"wall_ms={wall_ms:.3f} success={run['success']}",
                        flush=True,
                    )

            summaries = {}
            for name, samples in runs.items():
                wall_values = [sample["wall_ms"] for sample in samples]
                summaries[name] = {
                    "wall_ms_median": round(statistics.median(wall_values), 3),
                    "wall_ms_mean": round(statistics.mean(wall_values), 3),
                    "wall_ms_min": min(wall_values),
                    "wall_ms_max": max(wall_values),
                    "wall_ms_stdev": round(statistics.stdev(wall_values), 3),
                    "sql_statement_count_median": statistics.median(
                        sample["sql_statement_count"] for sample in samples
                    ),
                    "all_valid": all(sample["success"] for sample in samples),
                    "runs": samples,
                }
            summaries["bulk_upsert"]["speedup_vs_legacy"] = round(
                summaries["legacy_repository"]["wall_ms_median"]
                / summaries["bulk_upsert"]["wall_ms_median"],
                3,
            )
            datasets.append(
                {
                    "row_count": size,
                    "preseeded_rows": len(context.seed_rows),
                    "new_rows": size - len(context.seed_rows),
                    "strategies": summaries,
                }
            )
        return {
            "benchmark_version": "postgres_partial_conflict_v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "methodology": {
                "sizes": sizes,
                "repeats": repeats,
                "warmups": warmups,
                "embedding_dimensions": dimensions,
                "text_chars": text_chars,
                "upsert_batch": upsert_batch,
                "conflict_ratio": 0.5,
                "strategy_order": "alternating pair order",
            },
            "datasets": datasets,
        }
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", counter.before_cursor_execute)
        await engine.dispose()


async def main() -> None:
    assert_current_worktree_source()
    parser = argparse.ArgumentParser(description="PostgreSQL mixed INSERT/UPDATE benchmark")
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--text-chars", type=int, default=512)
    parser.add_argument("--upsert-batch", type=int, default=DEFAULT_UPSERT_BATCH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = await run_partial_benchmark(
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
