from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import research_platform

Stage = Literal["search", "acquisition"]

EXPECTED_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "research_platform"


def assert_current_worktree_source() -> None:
    imported_root = Path(research_platform.__file__).resolve().parent
    if imported_root != EXPECTED_PACKAGE_ROOT.resolve():
        raise RuntimeError(
            "research_platform was imported from a different checkout: "
            f"{imported_root}. Activate this worktree's environment or set PYTHONPATH=src."
        )


Outcome = Literal["success", "error"]


@dataclass(frozen=True)
class OperationSpec:
    """One deterministic I/O-shaped call used by both execution strategies."""

    operation_id: str
    stage: Stage
    delay_ms: float
    outcome: Outcome = "success"


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    status: Literal["success", "error", "timeout"]
    latency_ms: float
    payload_fingerprint: str = ""
    error: str = ""


class InFlightCounter:
    """Observe real overlap without relying on fragile wall-clock assertions."""

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


def _payload(spec: OperationSpec) -> dict[str, Any]:
    if spec.stage == "search":
        return {
            "connector": spec.operation_id.split(":", 1)[0],
            "results": [
                {
                    "id": f"candidate:{spec.operation_id}",
                    "url": f"https://benchmark.invalid/{spec.operation_id}",
                }
            ],
        }
    content = f"Deterministic acquired content for {spec.operation_id}."
    return {
        "candidate": spec.operation_id,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _execute(
    spec: OperationSpec,
    counter: InFlightCounter,
    *,
    timeout_ms: float,
) -> OperationResult:
    started = time.perf_counter()
    await counter.enter()
    try:
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                await asyncio.sleep(spec.delay_ms / 1000)
                if spec.outcome == "error":
                    raise RuntimeError(f"controlled failure: {spec.operation_id}")
                payload = _payload(spec)
            return OperationResult(
                operation_id=spec.operation_id,
                status="success",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                payload_fingerprint=_fingerprint(payload),
            )
        except TimeoutError:
            return OperationResult(
                operation_id=spec.operation_id,
                status="timeout",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error="operation timeout",
            )
        except Exception as exc:  # noqa: BLE001 - one failed call must not abort the batch
            return OperationResult(
                operation_id=spec.operation_id,
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error=f"{type(exc).__name__}: {exc}",
            )
    finally:
        await counter.exit()


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile, including sensible behaviour for one sample."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def result_fingerprint(results: list[OperationResult]) -> str:
    """Order-independent proof that serial and scatter-gather kept the same outputs."""

    rows = [
        {
            "operation_id": result.operation_id,
            "status": result.status,
            "payload_fingerprint": result.payload_fingerprint,
            "error": result.error,
        }
        for result in sorted(results, key=lambda item: item.operation_id)
    ]
    return _fingerprint(rows)


async def run_once(
    specs: list[OperationSpec],
    *,
    mode: Literal["serial", "asyncio"],
    concurrency: int,
    timeout_ms: float,
) -> dict[str, Any]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    counter = InFlightCounter()
    started = time.perf_counter()

    if mode == "serial":
        results = [await _execute(spec, counter, timeout_ms=timeout_ms) for spec in specs]
        effective_concurrency = 1
    elif mode == "asyncio":
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded(spec: OperationSpec) -> OperationResult:
            async with semaphore:
                return await _execute(spec, counter, timeout_ms=timeout_ms)

        results = list(await asyncio.gather(*(bounded(spec) for spec in specs)))
        effective_concurrency = concurrency
    else:
        raise ValueError(f"unsupported mode: {mode}")

    wall_ms = (time.perf_counter() - started) * 1000
    latencies = [result.latency_ms for result in results]
    counts = {
        status: sum(result.status == status for result in results)
        for status in ("success", "error", "timeout")
    }
    return {
        "mode": mode,
        "concurrency": effective_concurrency,
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(len(results) / max(wall_ms / 1000, 1e-9), 3),
        "latency_p50_ms": round(percentile(latencies, 0.50), 3),
        "latency_p95_ms": round(percentile(latencies, 0.95), 3),
        "max_in_flight": counter.maximum,
        "counts": counts,
        "result_fingerprint": result_fingerprint(results),
        "results": [asdict(result) for result in results],
    }


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one run is required")
    fingerprints = sorted({str(run["result_fingerprint"]) for run in runs})
    wall_values = [run["wall_ms"] for run in runs]
    wall_median = statistics.median(wall_values)
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
        "latency_p50_ms_median": round(statistics.median(run["latency_p50_ms"] for run in runs), 3),
        "latency_p95_ms_median": round(statistics.median(run["latency_p95_ms"] for run in runs), 3),
        "max_in_flight": max(run["max_in_flight"] for run in runs),
        "counts": runs[0]["counts"],
        "result_fingerprints": fingerprints,
        "deterministic_results": len(fingerprints) == 1,
        "runs": runs,
    }


async def benchmark_stage(
    specs: list[OperationSpec],
    *,
    concurrencies: list[int],
    repeats: int,
    warmups: int,
    timeout_ms: float,
) -> dict[str, Any]:
    if not specs:
        raise ValueError("a stage needs at least one operation")
    if repeats < 1 or warmups < 0:
        raise ValueError("repeats must be positive and warmups cannot be negative")

    configurations = [("serial", 1), *[("asyncio", value) for value in concurrencies]]
    aggregates = []
    for mode, concurrency in configurations:
        for _ in range(warmups):
            await run_once(specs, mode=mode, concurrency=concurrency, timeout_ms=timeout_ms)
        runs = [
            await run_once(specs, mode=mode, concurrency=concurrency, timeout_ms=timeout_ms)
            for _ in range(repeats)
        ]
        aggregates.append(aggregate_runs(runs))

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
        aggregate["equivalent_to_serial"] = (
            aggregate["result_fingerprints"] == aggregates[0]["result_fingerprints"]
        )
        aggregate["speedup_vs_asyncio_c1"] = round(
            asyncio_one_ms / max(aggregate["wall_ms_median"], 1e-9), 3
        )
        if aggregate["mode"] == "asyncio":
            aggregate["marginal_reduction_vs_previous_asyncio_percent"] = (
                None
                if previous_asyncio_ms is None
                else round(
                    (previous_asyncio_ms - aggregate["wall_ms_median"]) / previous_asyncio_ms * 100,
                    2,
                )
            )
            previous_asyncio_ms = aggregate["wall_ms_median"]
    return {
        "stage": specs[0].stage,
        "operation_count": len(specs),
        "total_simulated_delay_ms": sum(spec.delay_ms for spec in specs),
        "configurations": aggregates,
    }


def default_workloads(delay_scale: float = 1.0) -> dict[Stage, list[OperationSpec]]:
    if delay_scale <= 0:
        raise ValueError("delay_scale must be positive")
    delays = {
        "search": [60, 90, 120, 150, 75, 105, 135, 165],
        "acquisition": [80, 120, 160, 200, 100, 140, 180, 220],
    }
    return {
        stage: [
            OperationSpec(
                operation_id=f"{stage}-{index:02d}",
                stage=stage,
                delay_ms=value * delay_scale,
            )
            for index, value in enumerate(stage_delays, start=1)
        ]
        for stage, stage_delays in delays.items()
    }


def fault_workload(stage: Stage, delay_scale: float = 1.0) -> list[OperationSpec]:
    return [
        OperationSpec(f"{stage}-ok-1", stage, 50 * delay_scale),
        OperationSpec(f"{stage}-error", stage, 70 * delay_scale, outcome="error"),
        OperationSpec(f"{stage}-timeout", stage, 1_000 * delay_scale),
        OperationSpec(f"{stage}-ok-2", stage, 80 * delay_scale),
    ]


async def run_local_benchmark(
    *,
    concurrencies: list[int],
    repeats: int,
    warmups: int,
    delay_scale: float,
) -> dict[str, Any]:
    workloads = default_workloads(delay_scale)
    stages = [
        await benchmark_stage(
            workloads[stage],
            concurrencies=concurrencies,
            repeats=repeats,
            warmups=warmups,
            timeout_ms=1_000 * delay_scale,
        )
        for stage in ("search", "acquisition")
    ]
    fault_checks = []
    for stage in ("search", "acquisition"):
        specs = fault_workload(stage, delay_scale)
        timeout_ms = 300 * delay_scale
        serial = await run_once(specs, mode="serial", concurrency=1, timeout_ms=timeout_ms)
        concurrent = await run_once(
            specs,
            mode="asyncio",
            concurrency=max(concurrencies),
            timeout_ms=timeout_ms,
        )
        fault_checks.append(
            {
                "stage": stage,
                "serial": serial,
                "asyncio": concurrent,
                "equivalent_results": (
                    serial["result_fingerprint"] == concurrent["result_fingerprint"]
                ),
            }
        )
    return {
        "benchmark_version": "connector_io_local_v1",
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
            "delay_scale": delay_scale,
            "strategies": ["serial", "asyncio.gather + Semaphore"],
        },
        "stages": stages,
        "fault_checks": fault_checks,
    }


async def main() -> None:
    assert_current_worktree_source()
    parser = argparse.ArgumentParser(
        description="Deterministic serial vs asyncio connector I/O benchmark"
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--delay-scale", type=float, default=1.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/connector-concurrency/results/local_benchmark.json"),
    )
    args = parser.parse_args()
    if any(value < 1 for value in args.concurrency):
        parser.error("all concurrency values must be at least 1")

    payload = await run_local_benchmark(
        concurrencies=list(dict.fromkeys(args.concurrency)),
        repeats=args.repeats,
        warmups=args.warmups,
        delay_scale=args.delay_scale,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}")
    for stage in payload["stages"]:
        print(f"\n{stage['stage'].upper()} ({stage['operation_count']} operations)")
        for row in stage["configurations"]:
            print(
                f"  {row['mode']:<7} c={row['concurrency']:<2} "
                f"median={row['wall_ms_median']:>8.3f} ms "
                f"speedup={row['speedup_vs_serial']:>5.2f}x "
                f"max_in_flight={row['max_in_flight']} "
                f"equivalent={row['equivalent_to_serial']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
