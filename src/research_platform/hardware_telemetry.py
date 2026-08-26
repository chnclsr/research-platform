"""Run-window hardware telemetry without pretending it is per-run attribution.

One worker process can execute several research runs at once.  CPU, memory and NVML
counters describe the shared Docker/WSL environment and GPU, not one asyncio task, so a
single process-wide sampler reads them once and copies the same observation into every
active run's window.  Each copy carries that run's stage plus an anonymous active-run
count; no other run id or research detail crosses an ownership boundary.

Samples are flushed to ordinary run events.  This deliberately avoids a telemetry table
and migration while still surviving a normal pause/resume or pipeline failure.  Final
artifacts are built from those events after the run reaches a terminal state.
"""

from __future__ import annotations

import asyncio
import csv
import html
import io
import json
import logging
import math
import statistics
import time
import zipfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psutil

try:  # The wheel is portable; the driver library is optional on CPU deployments.
    import pynvml
except ImportError:  # pragma: no cover - exercised through the injected-module tests
    pynvml = None

from .auth import Principal
from .config import Settings, get_settings
from .db import SessionLocal
from .repository import Repository
from .schemas import RunStatus, new_id
from .storage import ObjectStore

logger = logging.getLogger(__name__)

SAMPLE_EVENT = "hardware_telemetry_samples"
SEGMENT_EVENT = "hardware_telemetry_segment"
SCHEMA_VERSION = 1
SCOPE = "docker_wsl_system_window"
TERMINAL_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.COMPLETED_INCOMPLETE.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
}
CSV_FILE = "18_hardware_utilization.csv"
SUMMARY_FILE = "19_hardware_utilization_summary.json"
SVG_FILE = "20_hardware_utilization.svg"
TELEMETRY_FILES = {CSV_FILE, SUMMARY_FILE, SVG_FILE}

EventWriter = Callable[[str, str, dict[str, Any]], Awaitable[None]]


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class HardwareSampler:
    """Read psutil and NVML counters, degrading field by field on unsupported hosts."""

    def __init__(self, psutil_module=psutil, nvml_module=pynvml) -> None:
        self.psutil = psutil_module
        self.nvml = nvml_module
        self.process = psutil_module.Process()
        self._gpu_handles: list[tuple[int, Any, str]] = []
        self._gpu_error: str | None = None
        self._nvml_started = False
        self._last_nvml_attempt = 0.0

    def start(self) -> None:
        # Both APIs define the first non-blocking percentage as a baseline rather than a
        # useful observation.  Warm them before any run receives a sample.
        self.psutil.cpu_percent(interval=None)
        self.process.cpu_percent(interval=None)
        self._init_nvml(force=True)

    def stop(self) -> None:
        if self._nvml_started and self.nvml is not None:
            try:
                self.nvml.nvmlShutdown()
            except Exception as exc:  # noqa: BLE001 - shutdown must never stop the worker
                logger.debug("NVML shutdown failed: %s", exc)
        self._nvml_started = False
        self._gpu_handles = []

    def _init_nvml(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if self._nvml_started or (not force and now - self._last_nvml_attempt < 60.0):
            return
        self._last_nvml_attempt = now
        if self.nvml is None:
            self._gpu_error = "pynvml module is not installed"
            return
        try:
            self.nvml.nvmlInit()
            handles = []
            for index in range(int(self.nvml.nvmlDeviceGetCount())):
                handle = self.nvml.nvmlDeviceGetHandleByIndex(index)
                handles.append((index, handle, _text(self.nvml.nvmlDeviceGetName(handle))))
            self._gpu_handles = handles
            self._gpu_error = None if handles else "NVML reports no visible GPU"
            self._nvml_started = True
        except Exception as exc:  # noqa: BLE001 - CPU-only deployments are supported
            self._gpu_handles = []
            self._gpu_error = f"{type(exc).__name__}: {exc}"
            self._nvml_started = False

    @staticmethod
    def _optional(call: Callable[[], Any], divisor: float = 1.0) -> float | None:
        try:
            value = call()
            return round(float(value) / divisor, 4)
        except Exception:  # noqa: BLE001 - individual NVML fields vary by device
            return None

    def _gpus(self) -> list[dict[str, Any]]:
        self._init_nvml()
        if not self._nvml_started or self.nvml is None:
            return []
        rows = []
        for index, handle, name in self._gpu_handles:
            try:
                utilization = self.nvml.nvmlDeviceGetUtilizationRates(handle)
            except Exception:  # noqa: BLE001 - keep memory data if utilization is absent
                utilization = None
            try:
                memory = self.nvml.nvmlDeviceGetMemoryInfo(handle)
            except Exception:  # noqa: BLE001
                memory = None
            rows.append(
                {
                    "index": index,
                    "name": name,
                    "utilization_percent": (
                        float(utilization.gpu) if utilization is not None else None
                    ),
                    "memory_utilization_percent": (
                        float(utilization.memory) if utilization is not None else None
                    ),
                    "memory_used_gb": (
                        round(float(memory.used) / 1024**3, 4) if memory is not None else None
                    ),
                    "memory_total_gb": (
                        round(float(memory.total) / 1024**3, 4) if memory is not None else None
                    ),
                    "temperature_c": self._optional(
                        lambda handle=handle: self.nvml.nvmlDeviceGetTemperature(
                            handle, self.nvml.NVML_TEMPERATURE_GPU
                        )
                    ),
                    "power_w": self._optional(
                        lambda handle=handle: self.nvml.nvmlDeviceGetPowerUsage(handle), 1000.0
                    ),
                }
            )
        return rows

    def sample(self) -> dict[str, Any]:
        memory = self.psutil.virtual_memory()
        process_memory = self.process.memory_info()
        return {
            "timestamp": _utc_iso(),
            "scope": SCOPE,
            "system_cpu_percent": round(float(self.psutil.cpu_percent(interval=None)), 4),
            "system_memory_percent": round(float(memory.percent), 4),
            "system_memory_available_gb": round(float(memory.available) / 1024**3, 4),
            "worker_cpu_percent": round(float(self.process.cpu_percent(interval=None)), 4),
            "worker_rss_gb": round(float(process_memory.rss) / 1024**3, 4),
            "gpus": self._gpus(),
            "gpu_status": "ok" if self._gpu_handles else (self._gpu_error or "unavailable"),
        }


@dataclass
class _ActiveRun:
    segment_id: str
    stage: str = "INIT"
    buffer: list[dict[str, Any]] = field(default_factory=list)
    last_flush: float = field(default_factory=time.monotonic)


async def _database_event(run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        await Repository(session, actor=Principal.system()).event(run_id, event_type, payload)


class TelemetryHub:
    """One sampler shared by every run admitted into this worker process."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sampler: HardwareSampler | None = None,
        event_writer: EventWriter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sampler = sampler or HardwareSampler()
        self.event_writer = event_writer or _database_event
        self._active: dict[str, _ActiveRun] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._collect_lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return len(self._active)

    async def start(self) -> None:
        if not self.settings.hardware_telemetry_enabled or self._task is not None:
            return
        await asyncio.to_thread(self.sampler.start)
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="hardware-telemetry")

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for run_id in list(self._active):
            await self._flush(run_id)
        await asyncio.to_thread(self.sampler.stop)

    async def begin(self, run_id: str) -> str | None:
        if not self.settings.hardware_telemetry_enabled:
            return None
        if self._task is None:
            await self.start()
        segment_id = new_id()
        async with self._collect_lock:
            self._active[run_id] = _ActiveRun(segment_id=segment_id)
        await self._write_event(
            run_id,
            SEGMENT_EVENT,
            {"schema_version": SCHEMA_VERSION, "action": "start", "segment_id": segment_id,
             "timestamp": _utc_iso(), "scope": SCOPE},
        )
        return segment_id

    def set_stage(self, run_id: str, stage: str) -> None:
        active = self._active.get(run_id)
        if active is not None:
            active.stage = stage

    async def end(self, run_id: str) -> None:
        if run_id not in self._active:
            return
        # A final observation makes even a sub-interval run diagnosable.
        await self.collect_once()
        async with self._collect_lock:
            active = self._active.get(run_id)
            if active is None:
                return
            await self._flush(run_id)
            self._active.pop(run_id, None)
        await self._write_event(
            run_id,
            SEGMENT_EVENT,
            {"schema_version": SCHEMA_VERSION, "action": "end",
             "segment_id": active.segment_id, "timestamp": _utc_iso(), "scope": SCOPE},
        )

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                if self._active:
                    await self.collect_once()
                await asyncio.sleep(self.settings.hardware_telemetry_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("hardware telemetry sampling failed")
                await asyncio.sleep(self.settings.hardware_telemetry_interval_s)

    async def collect_once(self) -> None:
        async with self._collect_lock:
            if not self._active:
                return
            sample = await asyncio.to_thread(self.sampler.sample)
            active_count = len(self._active)
            now = time.monotonic()
            due = []
            for run_id, active in list(self._active.items()):
                active.buffer.append(
                    {
                        **sample,
                        "segment_id": active.segment_id,
                        "stage": active.stage,
                        "active_run_count": active_count,
                    }
                )
                max_samples = self.settings.hardware_telemetry_max_buffered_samples
                if len(active.buffer) > max_samples:
                    del active.buffer[: len(active.buffer) - max_samples]
                if now - active.last_flush >= self.settings.hardware_telemetry_flush_s:
                    due.append(run_id)
            for run_id in due:
                await self._flush(run_id)

    async def _flush(self, run_id: str) -> None:
        active = self._active.get(run_id)
        if active is None or not active.buffer:
            return
        samples, active.buffer = active.buffer, []
        payload = {
            "schema_version": SCHEMA_VERSION,
            "scope": SCOPE,
            "interval_seconds": self.settings.hardware_telemetry_interval_s,
            "samples": samples,
        }
        try:
            await self.event_writer(run_id, SAMPLE_EVENT, payload)
            active.last_flush = time.monotonic()
        except Exception:
            logger.exception("hardware telemetry flush failed for run %s", run_id)
            max_samples = self.settings.hardware_telemetry_max_buffered_samples
            active.buffer = (samples + active.buffer)[-max_samples:]

    async def _write_event(
        self, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        try:
            await self.event_writer(run_id, event_type, payload)
        except Exception:
            logger.exception("hardware telemetry event failed for run %s", run_id)


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _numeric(values: Iterable[Any]) -> list[float]:
    result = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def _stats(values: Iterable[Any]) -> dict[str, float | None]:
    rows = sorted(_numeric(values))
    if not rows:
        return {"mean": None, "p95": None, "max": None}
    p95_index = max(0, math.ceil(len(rows) * 0.95) - 1)
    return {
        "mean": round(statistics.fmean(rows), 4),
        "p95": round(rows[p95_index], 4),
        "max": round(rows[-1], 4),
    }


def _segment_duration(events: list[dict[str, Any]], samples: list[dict[str, Any]]) -> float:
    bounds: dict[str, dict[str, datetime]] = {}
    for event in events:
        segment = str(event.get("segment_id") or "")
        timestamp = _parse_time(event.get("timestamp"))
        action = event.get("action")
        if segment and timestamp is not None and action in {"start", "end"}:
            bounds.setdefault(segment, {})[str(action)] = timestamp
    total = 0.0
    for segment, pair in bounds.items():
        if "start" in pair and "end" in pair:
            total += max(0.0, (pair["end"] - pair["start"]).total_seconds())
            continue
        times = [
            parsed
            for sample in samples
            if sample.get("segment_id") == segment
            and (parsed := _parse_time(sample.get("timestamp"))) is not None
        ]
        if times:
            total += max(0.0, (max(times) - min(times)).total_seconds())
    return round(total, 3)


def telemetry_summary(
    samples: list[dict[str, Any]],
    segment_events: list[dict[str, Any]],
    *,
    status: str,
    interval_seconds: float,
) -> dict[str, Any]:
    gpu_indices = sorted(
        {int(gpu["index"]) for sample in samples for gpu in sample.get("gpus", [])}
    )
    active_seconds = _segment_duration(segment_events, samples)
    segment_count = len({sample.get("segment_id") for sample in samples})
    expected = (
        math.ceil(active_seconds / interval_seconds) + segment_count
        if active_seconds and interval_seconds
        else len(samples)
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "scope_note": (
            "CPU/RAM are the shared Docker/WSL environment; GPU counters are the total "
            "visible device load. Values are not attributed to one research run."
        ),
        "status": status,
        "interval_seconds": interval_seconds,
        "sample_count": len(samples),
        "segment_count": segment_count,
        "active_seconds": active_seconds,
        "estimated_missing_samples": max(0, expected - len(samples)),
        "max_active_run_count": max(
            (int(sample.get("active_run_count") or 0) for sample in samples), default=0
        ),
        "system_cpu_percent": _stats(s.get("system_cpu_percent") for s in samples),
        "system_memory_percent": _stats(s.get("system_memory_percent") for s in samples),
        "system_memory_available_gb": _stats(
            s.get("system_memory_available_gb") for s in samples
        ),
        "worker_cpu_percent": _stats(s.get("worker_cpu_percent") for s in samples),
        "worker_rss_gb": _stats(s.get("worker_rss_gb") for s in samples),
        "gpu_statuses": sorted({str(s.get("gpu_status")) for s in samples}),
        "gpus": [],
    }
    for index in gpu_indices:
        rows = [
            gpu
            for sample in samples
            for gpu in sample.get("gpus", [])
            if int(gpu.get("index", -1)) == index
        ]
        summary["gpus"].append(
            {
                "index": index,
                "name": next((row.get("name") for row in rows if row.get("name")), "GPU"),
                "utilization_percent": _stats(r.get("utilization_percent") for r in rows),
                "memory_used_gb": _stats(r.get("memory_used_gb") for r in rows),
                "temperature_c": _stats(r.get("temperature_c") for r in rows),
                "power_w": _stats(r.get("power_w") for r in rows),
            }
        )
    return summary


def telemetry_csv(samples: list[dict[str, Any]]) -> bytes:
    headers = [
        "timestamp", "segment_id", "stage", "active_run_count", "scope",
        "system_cpu_percent", "system_memory_percent", "system_memory_available_gb",
        "worker_cpu_percent", "worker_rss_gb", "gpu_status", "gpu_index", "gpu_name",
        "gpu_utilization_percent", "gpu_memory_utilization_percent", "gpu_memory_used_gb",
        "gpu_memory_total_gb", "gpu_temperature_c", "gpu_power_w",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    for sample in samples:
        base = {key: sample.get(key) for key in headers[:11]}
        gpus = sample.get("gpus") or [None]
        for gpu in gpus:
            row = dict(base)
            if gpu is not None:
                row.update(
                    {
                        "gpu_index": gpu.get("index"),
                        "gpu_name": gpu.get("name"),
                        "gpu_utilization_percent": gpu.get("utilization_percent"),
                        "gpu_memory_utilization_percent": gpu.get(
                            "memory_utilization_percent"
                        ),
                        "gpu_memory_used_gb": gpu.get("memory_used_gb"),
                        "gpu_memory_total_gb": gpu.get("memory_total_gb"),
                        "gpu_temperature_c": gpu.get("temperature_c"),
                        "gpu_power_w": gpu.get("power_w"),
                    }
                )
            writer.writerow(row)
    return stream.getvalue().encode("utf-8-sig")


def _gpu_value(sample: dict[str, Any], index: int, key: str) -> Any:
    return next(
        (gpu.get(key) for gpu in sample.get("gpus", []) if int(gpu.get("index", -1)) == index),
        None,
    )


def telemetry_svg(samples: list[dict[str, Any]], summary: dict[str, Any]) -> bytes:
    width, height = 1200, 930
    left, plot_width = 84, width - 84 - 32
    top, panel_height, gap = 126, 126, 30
    panel_header_height = 36
    plot_height = panel_height - panel_header_height
    colors = ["#2f81f7", "#f0883e", "#3fb950", "#d2a8ff", "#f85149", "#39c5cf"]
    parsed = [(sample, _parse_time(sample.get("timestamp"))) for sample in samples]
    parsed = [(sample, stamp) for sample, stamp in parsed if stamp is not None]
    if parsed:
        start = min(stamp for _, stamp in parsed)
        end = max(stamp for _, stamp in parsed)
        span = max(1.0, (end - start).total_seconds())
    else:
        start = end = datetime.now(UTC)
        span = 1.0

    def x(stamp: datetime) -> float:
        return left + (stamp - start).total_seconds() / span * plot_width

    gpu_indices = sorted(
        {int(gpu["index"]) for sample, _ in parsed for gpu in sample.get("gpus", [])}
    )
    panels: list[tuple[str, str, float, list[tuple[str, str, list[Any]]]]] = [
        ("CPU kullanımı", "%", 100.0, [
            ("Sistem", colors[0], [s.get("system_cpu_percent") for s, _ in parsed]),
            ("Worker", colors[1], [s.get("worker_cpu_percent") for s, _ in parsed]),
        ]),
        ("RAM kullanımı", "%", 100.0, [
            ("Docker/WSL", colors[2], [s.get("system_memory_percent") for s, _ in parsed]),
        ]),
        ("Worker RSS", "GiB", max(1.0, max(_numeric(
            s.get("worker_rss_gb") for s, _ in parsed
        ), default=1.0) * 1.1), [
            ("Worker", colors[3], [s.get("worker_rss_gb") for s, _ in parsed]),
        ]),
        ("GPU kullanımı", "%", 100.0, [
            (f"GPU {index}", colors[index % len(colors)], [
                _gpu_value(s, index, "utilization_percent") for s, _ in parsed
            ]) for index in gpu_indices
        ]),
        ("VRAM kullanımı", "GiB", max(1.0, max(_numeric(
            _gpu_value(s, index, "memory_total_gb")
            for s, _ in parsed for index in gpu_indices
        ), default=1.0)), [
            (f"GPU {index}", colors[index % len(colors)], [
                _gpu_value(s, index, "memory_used_gb") for s, _ in parsed
            ]) for index in gpu_indices
        ]),
    ]
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        ),
        "<title id=\"title\">Koşu donanım kullanımı</title>",
        "<desc id=\"desc\">Koşu penceresindeki ortak Docker WSL ve GPU kullanımı.</desc>",
        '<rect width="100%" height="100%" fill="#0d1117"/>',
        (
            '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#c9d1d9}'
            '.grid{stroke:#30363d;stroke-width:1}.axis{stroke:#8b949e;stroke-width:1}'
            '.note{fill:#8b949e;font-size:13px}.label{font-size:14px}'
            '.title{font-size:24px;font-weight:700}'
            '.panel{font-size:16px;font-weight:600}</style>'
        ),
        '<text x="32" y="38" class="title">Koşu donanım kullanımı</text>',
        (
            '<text x="32" y="64" class="note">Ortak sistem penceresi — tek bir koşuya '
            'atfedilmiş tüketim değildir.</text>'
        ),
        (
            f'<text x="32" y="86" class="note">Örnek: {summary["sample_count"]} · etkin: '
            f'{summary["active_seconds"]:.1f} sn · en fazla paralel koşu: '
            f'{summary["max_active_run_count"]}</text>'
        ),
    ]

    # Anonymous concurrency shading is drawn behind every panel.
    for sample, stamp in parsed:
        if int(sample.get("active_run_count") or 0) <= 1:
            continue
        shade_x = x(stamp)
        shade_width = max(2.0, plot_width * summary.get("interval_seconds", 5) / span)
        out.append(
            f'<rect x="{shade_x:.2f}" y="{top - 16}" width="{shade_width:.2f}" '
            f'height="{len(panels) * (panel_height + gap) - gap + 16}" fill="#6e40c9" '
            'opacity="0.10"/>'
        )

    # The run-specific stage strip remains meaningful even though the counters are shared.
    stage_y = 102
    palette = ["#1f6feb", "#238636", "#9e6a03", "#8957e5", "#da3633", "#0f6f78"]
    for index, (sample, stamp) in enumerate(parsed):
        next_stamp = parsed[index + 1][1] if index + 1 < len(parsed) else end
        x1, x2 = x(stamp), x(next_stamp)
        stage = str(sample.get("stage") or "INIT")
        color = palette[sum(ord(char) for char in stage) % len(palette)]
        out.append(
            f'<rect x="{x1:.2f}" y="{stage_y}" width="{max(1.0, x2 - x1):.2f}" '
            f'height="10" fill="{color}"/>'
        )

    for panel_index, (title, unit, y_max, series) in enumerate(panels):
        y0 = top + panel_index * (panel_height + gap)
        plot_y0 = y0 + panel_header_height
        plot_bottom = plot_y0 + plot_height
        out.extend(
            [
                f'<text x="32" y="{y0 + 16}" class="panel">{html.escape(title)}</text>',
                (
                    f'<line x1="{left}" y1="{plot_bottom}" '
                    f'x2="{left + plot_width}" y2="{plot_bottom}" class="axis"/>'
                ),
                (
                    f'<line x1="{left}" y1="{plot_y0}" x2="{left}" '
                    f'y2="{plot_bottom}" class="axis"/>'
                ),
            ]
        )
        for fraction in (0.0, 0.5, 1.0):
            grid_y = plot_y0 + plot_height * (1.0 - fraction)
            out.append(
                f'<line x1="{left}" y1="{grid_y:.2f}" x2="{left + plot_width}" '
                f'y2="{grid_y:.2f}" class="grid"/>'
            )
            out.append(
                f'<text x="{left - 10}" y="{grid_y + 4:.2f}" text-anchor="end" '
                f'class="note">{y_max * fraction:.1f}{html.escape(unit)}</text>'
            )
        if not series:
            reason = next((s.get("gpu_status") for s, _ in parsed if s.get("gpu_status")),
                          "GPU telemetry unavailable")
            out.append(
                f'<text x="{left + 18}" y="{plot_y0 + plot_height / 2}" class="note">'
                f'{html.escape(str(reason))}</text>'
            )
            continue
        legend_x = left + 150
        for series_index, (label, color, values) in enumerate(series):
            out.append(
                f'<line x1="{legend_x}" y1="{y0 + 15}" x2="{legend_x + 18}" '
                f'y2="{y0 + 15}" stroke="{color}" stroke-width="3"/>'
            )
            out.append(
                f'<text x="{legend_x + 24}" y="{y0 + 19}" class="note legend">'
                f'{html.escape(label)}</text>'
            )
            legend_x += 105
            grouped: dict[str, list[str]] = {}
            for (sample, stamp), value in zip(parsed, values, strict=True):
                numbers = _numeric([value])
                if not numbers:
                    continue
                point_y = plot_y0 + plot_height * (
                    1.0 - min(y_max, max(0.0, numbers[0])) / y_max
                )
                grouped.setdefault(str(sample.get("segment_id") or ""), []).append(
                    f"{x(stamp):.2f},{point_y:.2f}"
                )
            for points in grouped.values():
                if points:
                    out.append(
                        f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
                        'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
                    )
    out.append(
        f'<text x="{left}" y="{height - 18}" class="note">'
        f'{html.escape(start.isoformat())} — {html.escape(end.isoformat())}</text>'
    )
    out.append(
        f'<rect x="{width - 286}" y="{height - 31}" width="14" height="14" '
        'fill="#6e40c9" opacity="0.35"/><text x="{width - 266}" y="{height - 19}" '
        'class="note">paralel koşu etkindi</text>'
    )
    out.append("</svg>")
    return "".join(out).encode("utf-8")


def build_telemetry_files(
    samples: list[dict[str, Any]],
    segment_events: list[dict[str, Any]],
    *,
    status: str,
    interval_seconds: float,
    output_type: str = "all",
) -> dict[str, tuple[str, bytes]]:
    samples = sorted(samples, key=lambda item: str(item.get("timestamp") or ""))
    summary = telemetry_summary(
        samples, segment_events, status=status, interval_seconds=interval_seconds
    )
    files = {
        CSV_FILE: ("text/csv; charset=utf-8", telemetry_csv(samples)),
        SUMMARY_FILE: (
            "application/json",
            json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
        ),
    }
    # Plotting walks every sample to place coordinates, so "csv" skips the call outright
    # rather than rendering a chart it would discard.
    if output_type == "all":
        files[SVG_FILE] = ("image/svg+xml", telemetry_svg(samples, summary))
    return files


def _select(files: dict[str, bytes], names: Iterable[str]) -> dict[str, bytes]:
    """Keep the requested members that this output type actually produced."""
    return {name: files[name] for name in names if name in files}


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return stream.getvalue()


def merge_zip(bundle: bytes, additions: dict[str, bytes]) -> bytes:
    """Replace named members without accumulating duplicate ZIP entries."""
    existing: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
        for name in archive.namelist():
            if name not in additions:
                existing[name] = archive.read(name)
    existing.update(additions)
    return _zip_bytes(existing)


async def finalize_hardware_telemetry(
    run_id: str,
    settings: Settings | None = None,
    *,
    store: ObjectStore | None = None,
) -> list[str]:
    """Create idempotent artifacts for a terminal run and enrich existing bundles."""
    settings = settings or get_settings()
    if not settings.hardware_telemetry_enabled:
        return []
    store = store or ObjectStore(settings)
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        run = await repo.get_run(run_id)
        if run is None or run.status not in TERMINAL_STATUSES:
            return []
        events = await repo.events_by_types(run_id, {SAMPLE_EVENT, SEGMENT_EVENT})
        samples = [
            sample
            for event in events
            if event.event_type == SAMPLE_EVENT
            for sample in (event.payload or {}).get("samples", [])
        ]
        segment_events = [
            event.payload or {} for event in events if event.event_type == SEGMENT_EVENT
        ]
        # A run cancelled before admission has no run window and therefore no telemetry
        # claim to make.  Admitted sub-interval runs still have segment events and get an
        # explicit, possibly one-sample artifact set.
        if not samples and not segment_events:
            return []
        files = build_telemetry_files(
            samples,
            segment_events,
            status=run.status,
            interval_seconds=settings.hardware_telemetry_interval_s,
            output_type=settings.hardware_telemetry_output_type,
        )
        raw_bytes = {name: data for name, (_, data) in files.items()}
        saved = []
        for name, (media_type, data) in files.items():
            key = f"runs/{run_id}/{name}"
            await store.put(key, data, media_type)
            await repo.save_artifact(run_id, name, media_type, key, len(data))
            saved.append(name)

        telemetry_bundle_name = "hardware_utilization_bundle.zip"
        telemetry_bundle = _zip_bytes(raw_bytes)
        telemetry_bundle_key = f"runs/{run_id}/{telemetry_bundle_name}"
        await store.put(telemetry_bundle_key, telemetry_bundle, "application/zip")
        await repo.save_artifact(
            run_id,
            telemetry_bundle_name,
            "application/zip",
            telemetry_bundle_key,
            len(telemetry_bundle),
        )
        saved.append(telemetry_bundle_name)

        artifacts = {artifact.name: artifact for artifact in await repo.list_artifacts(run_id)}
        # The output type decides which names exist, so every bundle selects from what was
        # actually built instead of indexing a file it assumes is there.
        bundle_additions = {
            "raw_bundle.zip": _select(raw_bytes, (CSV_FILE,)),
            "result_bundle.zip": _select(raw_bytes, (SUMMARY_FILE, SVG_FILE)),
            "research_bundle.zip": dict(raw_bytes),
        }
        for bundle_name, additions in bundle_additions.items():
            artifact = artifacts.get(bundle_name)
            if artifact is None or not additions:
                continue
            patched = merge_zip(await store.get(artifact.object_key), additions)
            await store.put(artifact.object_key, patched, "application/zip")
            await repo.save_artifact(
                run_id, bundle_name, "application/zip", artifact.object_key, len(patched)
            )
        return saved


HUB = TelemetryHub()
