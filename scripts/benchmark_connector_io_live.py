from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

import research_platform
from research_platform.acquisition import AcquisitionService
from research_platform.config import Settings
from research_platform.connectors.implementations import (
    ArxivConnector,
    CrossrefConnector,
    EuropePmcConnector,
    OpenAlexConnector,
)
from research_platform.schemas import ConnectorCandidate, SourceFamily

Mode = Literal["serial", "asyncio"]

EXPECTED_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "research_platform"


def assert_current_worktree_source() -> None:
    imported_root = Path(research_platform.__file__).resolve().parent
    if imported_root != EXPECTED_PACKAGE_ROOT.resolve():
        raise RuntimeError(
            "research_platform was imported from a different checkout: "
            f"{imported_root}. Activate this worktree's environment or set PYTHONPATH=src."
        )


@dataclass(frozen=True)
class LiveResult:
    operation_id: str
    success: bool
    latency_ms: float
    result_count: int
    payload_fingerprint: str = ""
    method: str = ""
    error: str = ""


class InFlightCounter:
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


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_fingerprint(results: list[LiveResult]) -> str:
    rows = [
        {
            "operation_id": result.operation_id,
            "success": result.success,
            "result_count": result.result_count,
            "payload_fingerprint": result.payload_fingerprint,
            "method": result.method,
            "error_type": result.error.split(":", 1)[0],
        }
        for result in sorted(results, key=lambda item: item.operation_id)
    ]
    return _fingerprint(rows)


async def _run_calls(
    calls: list[tuple[str, Callable[[], Awaitable[tuple[int, str, str]]]]],
    *,
    mode: Mode,
    concurrency: int,
    timeout_s: float,
) -> dict[str, Any]:
    counter = InFlightCounter()

    async def one(
        operation_id: str,
        call: Callable[[], Awaitable[tuple[int, str, str]]],
    ) -> LiveResult:
        started = time.perf_counter()
        await counter.enter()
        try:
            try:
                async with asyncio.timeout(timeout_s):
                    count, fingerprint, method = await call()
                return LiveResult(
                    operation_id=operation_id,
                    success=True,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    result_count=count,
                    payload_fingerprint=fingerprint,
                    method=method,
                )
            except Exception as exc:  # noqa: BLE001 - record provider errors per call
                return LiveResult(
                    operation_id=operation_id,
                    success=False,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    result_count=0,
                    error=f"{type(exc).__name__}: {str(exc)[:300]}",
                )
        finally:
            await counter.exit()

    started = time.perf_counter()
    if mode == "serial":
        results = [await one(operation_id, call) for operation_id, call in calls]
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded(
            operation_id: str,
            call: Callable[[], Awaitable[tuple[int, str, str]]],
        ) -> LiveResult:
            async with semaphore:
                return await one(operation_id, call)

        results = list(
            await asyncio.gather(*(bounded(operation_id, call) for operation_id, call in calls))
        )
    wall_ms = (time.perf_counter() - started) * 1000
    return {
        "mode": mode,
        "concurrency": 1 if mode == "serial" else concurrency,
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(len(results) / max(wall_ms / 1000, 1e-9), 3),
        "max_in_flight": counter.maximum,
        "successes": sum(result.success for result in results),
        "errors": sum(not result.success for result in results),
        "result_fingerprint": _run_fingerprint(results),
        "results": [asdict(result) for result in results],
    }


def _settings() -> Settings:
    return Settings(
        domain_delay_s=0,
        request_timeout_s=30,
        enable_jina_reader_fallback=False,
        enable_scrapling_fallback=False,
    )


async def run_search(
    *, mode: Mode, concurrency: int, timeout_s: float, query: str, limit: int
) -> dict[str, Any]:
    settings = _settings()
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
        timeout=settings.request_timeout_s,
    ) as client:
        connectors = [
            OpenAlexConnector(settings, client),
            CrossrefConnector(settings, client),
            ArxivConnector(settings, client),
            EuropePmcConnector(settings, client),
        ]
        calls = []
        for connector in connectors:

            async def call(connector=connector) -> tuple[int, str, str]:
                candidates = await connector.search(query, limit)
                identities = sorted(
                    str(candidate.persistent_id or candidate.url) for candidate in candidates
                )
                return len(candidates), _fingerprint(identities), connector.id

            calls.append((connector.id, call))
        return await _run_calls(calls, mode=mode, concurrency=concurrency, timeout_s=timeout_s)


ACQUISITION_TARGETS = [
    ("rfc9110", "https://www.rfc-editor.org/rfc/rfc9110.html"),
    ("iana-reserved", "https://www.iana.org/help/example-domains"),
    ("python-about", "https://www.python.org/about/"),
    ("wcag22", "https://www.w3.org/TR/WCAG22/"),
]


async def run_acquisition(*, mode: Mode, concurrency: int, timeout_s: float) -> dict[str, Any]:
    settings = _settings()
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        follow_redirects=False,
        timeout=settings.request_timeout_s,
    ) as client:
        service = AcquisitionService(settings, client)
        calls = []
        for identity, url in ACQUISITION_TARGETS:
            candidate = ConnectorCandidate(
                connector_id="live_benchmark",
                family=SourceFamily.WEB,
                title=f"Live acquisition target {identity}",
                url=url,
            )

            async def call(candidate=candidate) -> tuple[int, str, str]:
                document = await service.acquire(candidate)
                if not document.success:
                    raise RuntimeError(document.error or "acquisition failed")
                return 1, str(document.content_hash or ""), document.acquisition_method

            calls.append((identity, call))
        return await _run_calls(calls, mode=mode, concurrency=concurrency, timeout_s=timeout_s)


def _aggregate(
    runs: list[dict[str, Any]],
    *,
    serial_by_repeat: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    wall_values = [run["wall_ms"] for run in runs]
    wall_median = statistics.median(wall_values)
    paired_speedups = [
        serial_by_repeat[run["repeat"]]["wall_ms"] / max(run["wall_ms"], 1e-9) for run in runs
    ]
    paired = [
        run["result_fingerprint"] == serial_by_repeat[run["repeat"]]["result_fingerprint"]
        for run in runs
    ]
    operation_ids = sorted({result["operation_id"] for run in runs for result in run["results"]})
    operation_latency_ms = {}
    for operation_id in operation_ids:
        operation_results = [
            result
            for run in runs
            for result in run["results"]
            if result["operation_id"] == operation_id
        ]
        latencies = [result["latency_ms"] for result in operation_results]
        operation_latency_ms[operation_id] = {
            "median": round(statistics.median(latencies), 3),
            "min": min(latencies),
            "max": max(latencies),
            "successes": sum(result["success"] for result in operation_results),
            "errors": sum(not result["success"] for result in operation_results),
        }
    return {
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
        "successes_min": min(run["successes"] for run in runs),
        "errors_total": sum(run["errors"] for run in runs),
        "max_in_flight": max(run["max_in_flight"] for run in runs),
        "paired_equivalence_rate": round(sum(paired) / len(paired), 3),
        "paired_speedup_median": round(statistics.median(paired_speedups), 3),
        "paired_speedup_min": round(min(paired_speedups), 3),
        "paired_speedup_max": round(max(paired_speedups), 3),
        "operation_latency_ms": operation_latency_ms,
        "runs": runs,
    }


async def run_live_benchmark(
    *, repeats: int, timeout_s: float, query: str, limit: int
) -> dict[str, Any]:
    configurations: list[tuple[Mode, int]] = [
        ("serial", 1),
        ("asyncio", 1),
        ("asyncio", 2),
        ("asyncio", 4),
    ]
    stage_runs: dict[str, list[dict[str, Any]]] = {"search": [], "acquisition": []}
    for repeat in range(1, repeats + 1):
        order = configurations if repeat % 2 else list(reversed(configurations))
        for mode, concurrency in order:
            print(
                f"RUN_START repeat={repeat} stage=search mode={mode} c={concurrency}",
                flush=True,
            )
            search = await run_search(
                mode=mode,
                concurrency=concurrency,
                timeout_s=timeout_s,
                query=query,
                limit=limit,
            )
            search["repeat"] = repeat
            stage_runs["search"].append(search)
            print(
                f"RUN_DONE repeat={repeat} stage=search mode={mode} c={concurrency} "
                f"seconds={search['wall_ms'] / 1000:.3f} errors={search['errors']}",
                flush=True,
            )
        for mode, concurrency in order:
            print(
                f"RUN_START repeat={repeat} stage=acquisition mode={mode} c={concurrency}",
                flush=True,
            )
            acquisition = await run_acquisition(
                mode=mode, concurrency=concurrency, timeout_s=timeout_s
            )
            acquisition["repeat"] = repeat
            stage_runs["acquisition"].append(acquisition)
            print(
                f"RUN_DONE repeat={repeat} stage=acquisition mode={mode} c={concurrency} "
                f"seconds={acquisition['wall_ms'] / 1000:.3f} "
                f"errors={acquisition['errors']}",
                flush=True,
            )

    stages = []
    for stage, runs in stage_runs.items():
        serial_by_repeat = {run["repeat"]: run for run in runs if run["mode"] == "serial"}
        aggregates = []
        for mode, concurrency in configurations:
            selected = [
                run for run in runs if run["mode"] == mode and run["concurrency"] == concurrency
            ]
            aggregates.append(_aggregate(selected, serial_by_repeat=serial_by_repeat))
        serial_ms = aggregates[0]["wall_ms_median"]
        asyncio_one_ms = next(
            aggregate["wall_ms_median"]
            for aggregate in aggregates
            if aggregate["mode"] == "asyncio" and aggregate["concurrency"] == 1
        )
        previous_asyncio_ms: float | None = None
        for aggregate in aggregates:
            aggregate["speedup_vs_serial"] = round(
                serial_ms / max(aggregate["wall_ms_median"], 1e-9), 3
            )
            aggregate["speedup_vs_asyncio_c1"] = round(
                asyncio_one_ms / max(aggregate["wall_ms_median"], 1e-9), 3
            )
            if aggregate["mode"] == "asyncio":
                aggregate["marginal_reduction_vs_previous_asyncio_percent"] = (
                    None
                    if previous_asyncio_ms is None
                    else round(
                        (previous_asyncio_ms - aggregate["wall_ms_median"])
                        / previous_asyncio_ms
                        * 100,
                        2,
                    )
                )
                previous_asyncio_ms = aggregate["wall_ms_median"]
        stages.append({"stage": stage, "configurations": aggregates})
    return {
        "benchmark_version": "connector_io_live_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "gpu_required": False,
            "network_required": True,
        },
        "methodology": {
            "repeats": repeats,
            "timeout_s": timeout_s,
            "query": query,
            "result_limit": limit,
            "order_alternated": True,
            "search_connectors": ["openalex", "crossref", "arxiv", "europe_pmc"],
            "acquisition_targets": [url for _, url in ACQUISITION_TARGETS],
        },
        "stages": stages,
    }


async def main() -> None:
    assert_current_worktree_source()
    parser = argparse.ArgumentParser(
        description="Small live-network validation for connector I/O concurrency"
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--query", default="retrieval augmented generation evaluation")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/connector-concurrency/results/live_benchmark.json"),
    )
    args = parser.parse_args()
    payload = await run_live_benchmark(
        repeats=args.repeats,
        timeout_s=args.timeout,
        query=args.query,
        limit=args.limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
