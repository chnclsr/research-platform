from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import research_platform
from research_platform.config import get_settings
from research_platform.pipeline import ResearchPipeline
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ResearchProtocol,
    SearchMission,
    SourceFamily,
)

PIPELINE_DELAYS_MS = [60, 80, 100, 120, 70, 90, 110, 130]
EXPECTED_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "research_platform"


def assert_current_worktree_source() -> None:
    imported_root = Path(research_platform.__file__).resolve().parent
    if imported_root != EXPECTED_PACKAGE_ROOT.resolve():
        raise RuntimeError(
            "research_platform was imported from a different checkout: "
            f"{imported_root}. Activate this worktree's environment or set PYTHONPATH=src."
        )


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AsyncInFlightCounter:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0
        self._lock = asyncio.Lock()

    async def enter(self) -> None:
        async with self._lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)

    async def exit(self) -> None:
        async with self._lock:
            self.active -= 1


class ThreadInFlightCounter:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0
        self._lock = threading.Lock()

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


class BenchmarkRepo:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.updates = 0

    async def event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))

    async def update_run(self, run_id: str, **values: Any) -> None:
        self.updates += 1

    async def list_sources(self, run_id: str) -> list[Any]:
        return []

    async def filter_novel_candidates(
        self,
        run_id: str,
        candidates: list[ConnectorCandidate],
    ) -> tuple[list[ConnectorCandidate], list[dict[str, Any]]]:
        return candidates, []


class DelayedPipelineConnector:
    id = "pipeline_fixture"
    family = SourceFamily.WEB
    capabilities = ("search", "metadata")

    def __init__(self, counter: AsyncInFlightCounter) -> None:
        self.counter = counter

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        match = re.search(r"pipeline query (\d+)", query)
        if match is None:
            raise ValueError(f"fixture query index missing: {query}")
        index = int(match.group(1))
        await self.counter.enter()
        try:
            await asyncio.sleep(PIPELINE_DELAYS_MS[index] / 1000)
        finally:
            await self.counter.exit()
        return [
            ConnectorCandidate(
                connector_id=self.id,
                family=self.family,
                title=f"Pipeline search result {index}",
                url=f"https://example.test/search/{index}",
                snippet=f"Controlled search payload {index}",
                persistent_id=f"pipeline-search:{index}",
            )
        ]


class FixtureRegistry:
    def __init__(self, connector: DelayedPipelineConnector) -> None:
        self.connector = connector

    def selected(self, selection: Any) -> list[DelayedPipelineConnector]:
        return [self.connector]


class DelayedPipelineAcquisition:
    def __init__(self, counter: AsyncInFlightCounter) -> None:
        self.counter = counter
        self.parser_overrides: dict[str, str] = {}

    async def acquire(self, candidate: ConnectorCandidate) -> AcquiredDocument:
        delay_ms = int(candidate.metadata["delay_ms"])
        await self.counter.enter()
        try:
            await asyncio.sleep(delay_ms / 1000)
        finally:
            await self.counter.exit()
        content = f"Controlled acquisition payload for {candidate.url}"
        return AcquiredDocument(
            candidate=candidate,
            success=True,
            access_status="open",
            content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            acquisition_method="pipeline_fixture",
        )


def _protocol(concurrency: int) -> ResearchProtocol:
    return ResearchProtocol(
        title="Pipeline connector I/O benchmark",
        primary_question="How does bounded connector concurrency affect wall time?",
        connectors={
            "profile": "custom",
            "included_families": ["web"],
            "included_connectors": ["pipeline_fixture"],
            "citation_depth": 0,
        },
        budget={
            "max_sources": 32,
            "results_per_connector": 2,
            "max_wall_minutes": 5,
            "acquisition_concurrency": concurrency,
        },
    )


def _pipeline(concurrency: int) -> ResearchPipeline:
    pipeline = object.__new__(ResearchPipeline)
    pipeline.settings = get_settings().model_copy(
        update={
            "testing": True,
            "search_concurrency": concurrency,
            "local_corpus_results": 0,
        }
    )
    pipeline.repo = BenchmarkRepo()
    return pipeline


async def run_pipeline_search_once(concurrency: int) -> dict[str, Any]:
    protocol = _protocol(concurrency)
    counter = AsyncInFlightCounter()
    pipeline = _pipeline(concurrency)
    pipeline.registry = FixtureRegistry(DelayedPipelineConnector(counter))
    missions = [
        SearchMission(
            branch_id=f"pipeline:{index}",
            query=f"pipeline query {index}",
            connector_ids=["pipeline_fixture"],
            result_limit=2,
        )
        for index in range(len(PIPELINE_DELAYS_MS))
    ]
    started = time.perf_counter()
    result = await pipeline._search_node(
        {
            "run_id": "pipeline-search-benchmark",
            "protocol": protocol.model_dump(mode="json"),
            "missions": [mission.model_dump(mode="json") for mission in missions],
            "queries": [mission.query for mission in missions],
            "round_number": 1,
        }
    )
    wall_ms = (time.perf_counter() - started) * 1000
    identities = sorted(
        str(candidate["persistent_id"] or candidate["url"]) for candidate in result["candidates"]
    )
    return {
        "stage": "pipeline_search",
        "mode": "asyncio_pipeline",
        "concurrency": concurrency,
        "operation_count": len(PIPELINE_DELAYS_MS),
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(len(PIPELINE_DELAYS_MS) / max(wall_ms / 1000, 1e-9), 3),
        "max_in_flight": counter.maximum,
        "result_count": len(identities),
        "result_fingerprint": _fingerprint(identities),
        "event_count": len(pipeline.repo.events),
    }


async def run_pipeline_acquisition_once(concurrency: int) -> dict[str, Any]:
    protocol = _protocol(concurrency)
    counter = AsyncInFlightCounter()
    pipeline = _pipeline(concurrency)
    pipeline.acquisition = DelayedPipelineAcquisition(counter)
    candidates = [
        ConnectorCandidate(
            connector_id="pipeline_fixture",
            family=SourceFamily.WEB,
            title=f"Pipeline acquisition source {index}",
            url=f"https://example.test/acquisition/{index}",
            metadata={"delay_ms": delay_ms},
        )
        for index, delay_ms in enumerate(PIPELINE_DELAYS_MS)
    ]
    started = time.perf_counter()
    result = await pipeline._acquire_node(
        {
            "run_id": "pipeline-acquisition-benchmark",
            "protocol": protocol.model_dump(mode="json"),
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "budget_started_at": datetime.now(UTC).isoformat(),
        }
    )
    wall_ms = (time.perf_counter() - started) * 1000
    documents = sorted(
        (
            document["candidate"]["url"],
            document["content_hash"],
            document["success"],
        )
        for document in result["documents"]
    )
    return {
        "stage": "pipeline_acquisition",
        "mode": "asyncio_pipeline",
        "concurrency": concurrency,
        "operation_count": len(PIPELINE_DELAYS_MS),
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(len(PIPELINE_DELAYS_MS) / max(wall_ms / 1000, 1e-9), 3),
        "max_in_flight": counter.maximum,
        "result_count": len(documents),
        "result_fingerprint": _fingerprint(documents),
        "event_count": len(pipeline.repo.events),
        "update_count": pipeline.repo.updates,
    }


@dataclass(frozen=True)
class BlockingOperation:
    operation_id: str
    delay_ms: int


def _blocking_operation(
    operation: BlockingOperation,
    counter: ThreadInFlightCounter,
) -> tuple[str, str]:
    counter.enter()
    try:
        time.sleep(operation.delay_ms / 1000)
        payload = f"blocking-io:{operation.operation_id}:{operation.delay_ms}"
        return operation.operation_id, hashlib.sha256(payload.encode("utf-8")).hexdigest()
    finally:
        counter.exit()


def run_threadpool_once(concurrency: int) -> dict[str, Any]:
    operations = [
        BlockingOperation(f"blocking-{index}", delay_ms)
        for index, delay_ms in enumerate(PIPELINE_DELAYS_MS)
    ]
    counter = ThreadInFlightCounter()
    started = time.perf_counter()
    if concurrency == 1:
        results = [_blocking_operation(operation, counter) for operation in operations]
        mode = "blocking_serial"
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(
                executor.map(
                    lambda operation: _blocking_operation(operation, counter),
                    operations,
                )
            )
        mode = "threadpool"
    wall_ms = (time.perf_counter() - started) * 1000
    return {
        "stage": "blocking_io_reference",
        "mode": mode,
        "concurrency": concurrency,
        "operation_count": len(operations),
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(len(operations) / max(wall_ms / 1000, 1e-9), 3),
        "max_in_flight": counter.maximum,
        "result_count": len(results),
        "result_fingerprint": _fingerprint(sorted(results)),
    }


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    wall_values = [run["wall_ms"] for run in runs]
    wall_median = statistics.median(wall_values)
    return {
        "stage": runs[0]["stage"],
        "mode": runs[0]["mode"],
        "concurrency": runs[0]["concurrency"],
        "repeats": len(runs),
        "wall_ms_median": round(wall_median, 3),
        "wall_ms_min": min(wall_values),
        "wall_ms_max": max(wall_values),
        "wall_ms_mad": round(
            statistics.median(abs(value - wall_median) for value in wall_values), 3
        ),
        "throughput_per_second_median": round(
            statistics.median(run["throughput_per_second"] for run in runs), 3
        ),
        "max_in_flight": max(run["max_in_flight"] for run in runs),
        "result_count": min(run["result_count"] for run in runs),
        "result_fingerprints": sorted({run["result_fingerprint"] for run in runs}),
        "deterministic_results": len({run["result_fingerprint"] for run in runs}) == 1,
        "runs": runs,
    }


async def run_pipeline_benchmark(
    *,
    repeats: int,
    warmups: int,
    concurrencies: list[int],
) -> dict[str, Any]:
    stage_functions = {
        "pipeline_search": run_pipeline_search_once,
        "pipeline_acquisition": run_pipeline_acquisition_once,
    }
    stages = []
    for stage, function in stage_functions.items():
        for _ in range(warmups):
            for concurrency in concurrencies:
                await function(concurrency)
        aggregates = []
        for concurrency in concurrencies:
            runs = [await function(concurrency) for _ in range(repeats)]
            aggregates.append(_aggregate(runs))
        baseline_ms = aggregates[0]["wall_ms_median"]
        baseline_fingerprint = aggregates[0]["result_fingerprints"]
        for aggregate in aggregates:
            aggregate["speedup_vs_c1"] = round(
                baseline_ms / max(aggregate["wall_ms_median"], 1e-9), 3
            )
            aggregate["equivalent_to_c1"] = aggregate["result_fingerprints"] == baseline_fingerprint
        stages.append({"stage": stage, "configurations": aggregates})

    for _ in range(warmups):
        for concurrency in concurrencies:
            await asyncio.to_thread(run_threadpool_once, concurrency)
    threadpool_aggregates = []
    for concurrency in concurrencies:
        runs = [await asyncio.to_thread(run_threadpool_once, concurrency) for _ in range(repeats)]
        threadpool_aggregates.append(_aggregate(runs))
    baseline_ms = threadpool_aggregates[0]["wall_ms_median"]
    baseline_fingerprint = threadpool_aggregates[0]["result_fingerprints"]
    for aggregate in threadpool_aggregates:
        aggregate["speedup_vs_serial"] = round(
            baseline_ms / max(aggregate["wall_ms_median"], 1e-9), 3
        )
        aggregate["equivalent_to_serial"] = aggregate["result_fingerprints"] == baseline_fingerprint

    return {
        "benchmark_version": "pipeline_connector_io_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "gpu_required": False,
            "network_required": False,
        },
        "methodology": {
            "repeats": repeats,
            "warmups": warmups,
            "concurrencies": concurrencies,
            "operations_per_stage": len(PIPELINE_DELAYS_MS),
            "controlled_delays_ms": PIPELINE_DELAYS_MS,
            "pipeline_methods": ["_search_node", "_acquire_node"],
            "threadpool_scope": "blocking synchronous I/O reference only",
        },
        "stages": stages,
        "threadpool_reference": {
            "applicability": (
                "Reference for blocking synchronous I/O; production connectors are async and "
                "are not executed inside ThreadPoolExecutor."
            ),
            "configurations": threadpool_aggregates,
        },
    }


def _print_summary(payload: dict[str, Any]) -> None:
    for stage in payload["stages"]:
        print(f"\n{stage['stage'].upper()}")
        for aggregate in stage["configurations"]:
            print(
                f"  c={aggregate['concurrency']:<2} "
                f"median={aggregate['wall_ms_median']:>8.3f} ms "
                f"speedup={aggregate['speedup_vs_c1']:>5.2f}x "
                f"max_in_flight={aggregate['max_in_flight']} "
                f"equivalent={aggregate['equivalent_to_c1']}"
            )
    print("\nTHREADPOOL BLOCKING I/O REFERENCE")
    for aggregate in payload["threadpool_reference"]["configurations"]:
        print(
            f"  c={aggregate['concurrency']:<2} "
            f"median={aggregate['wall_ms_median']:>8.3f} ms "
            f"speedup={aggregate['speedup_vs_serial']:>5.2f}x "
            f"max_in_flight={aggregate['max_in_flight']} "
            f"equivalent={aggregate['equivalent_to_serial']}"
        )


async def main() -> None:
    assert_current_worktree_source()
    parser = argparse.ArgumentParser(
        description="Benchmark actual pipeline connector nodes and blocking ThreadPool I/O"
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/connector-concurrency/results/pipeline_benchmark.json"),
    )
    args = parser.parse_args()
    payload = await run_pipeline_benchmark(
        repeats=args.repeats,
        warmups=args.warmups,
        concurrencies=args.concurrency,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}")
    _print_summary(payload)


if __name__ == "__main__":
    asyncio.run(main())
