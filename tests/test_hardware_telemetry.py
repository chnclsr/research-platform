from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from conftest import acting_principal
from pydantic import ValidationError

from research_platform.config import Settings, get_settings
from research_platform.control_panel_ui import CONTROL_PANEL_HTML
from research_platform.db import SessionLocal, create_schema
from research_platform.hardware_telemetry import (
    CSV_FILE,
    SAMPLE_EVENT,
    SEGMENT_EVENT,
    SUMMARY_FILE,
    SVG_FILE,
    HardwareSampler,
    TelemetryHub,
    build_telemetry_files,
    finalize_hardware_telemetry,
    merge_zip,
)
from research_platform.pipeline import ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.storage import ObjectStore


class FakeProcess:
    def __init__(self) -> None:
        self.cpu_values = iter([0.0, 17.5])

    def cpu_percent(self, interval=None):
        assert interval is None
        return next(self.cpu_values)

    @staticmethod
    def memory_info():
        return SimpleNamespace(rss=3 * 1024**3)


class FakePsutil:
    def __init__(self) -> None:
        self.cpu_values = iter([0.0, 42.5])
        self.process = FakeProcess()

    def Process(self):
        return self.process

    def cpu_percent(self, interval=None):
        assert interval is None
        return next(self.cpu_values)

    @staticmethod
    def virtual_memory():
        return SimpleNamespace(percent=62.5, available=8 * 1024**3)


class FakeNvml:
    NVML_TEMPERATURE_GPU = 0

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def nvmlInit(self):
        self.started = True

    @staticmethod
    def nvmlDeviceGetCount():
        return 2

    @staticmethod
    def nvmlDeviceGetHandleByIndex(index):
        return f"handle-{index}"

    @staticmethod
    def nvmlDeviceGetName(handle):
        return f"GPU {handle[-1]}".encode()

    @staticmethod
    def nvmlDeviceGetUtilizationRates(handle):
        index = int(handle[-1])
        return SimpleNamespace(gpu=40 + index, memory=20 + index)

    @staticmethod
    def nvmlDeviceGetMemoryInfo(handle):
        index = int(handle[-1])
        return SimpleNamespace(used=(index + 1) * 1024**3, total=8 * 1024**3)

    @staticmethod
    def nvmlDeviceGetTemperature(handle, sensor):
        assert sensor == 0
        return 60 + int(handle[-1])

    @staticmethod
    def nvmlDeviceGetPowerUsage(handle):
        return 55000 + int(handle[-1]) * 1000

    def nvmlShutdown(self):
        self.stopped = True


def sample(timestamp: str, *, count: int = 1, stage: str = "SEARCH") -> dict:
    return {
        "timestamp": timestamp,
        "scope": "docker_wsl_system_window",
        "segment_id": "segment-1",
        "stage": stage,
        "active_run_count": count,
        "system_cpu_percent": 50.0,
        "system_memory_percent": 60.0,
        "system_memory_available_gb": 8.0,
        "worker_cpu_percent": 20.0,
        "worker_rss_gb": 2.0,
        "gpu_status": "ok",
        "gpus": [
            {
                "index": 0,
                "name": "Test GPU",
                "utilization_percent": 70.0,
                "memory_utilization_percent": 40.0,
                "memory_used_gb": 3.0,
                "memory_total_gb": 8.0,
                "temperature_c": 65.0,
                "power_w": 80.0,
            }
        ],
    }


def zip_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def test_sampler_warms_percentages_and_reads_multiple_gpus():
    fake_psutil, fake_nvml = FakePsutil(), FakeNvml()
    sampler = HardwareSampler(fake_psutil, fake_nvml)

    sampler.start()
    result = sampler.sample()
    sampler.stop()

    assert result["system_cpu_percent"] == 42.5
    assert result["worker_cpu_percent"] == 17.5
    assert result["system_memory_available_gb"] == 8.0
    assert result["worker_rss_gb"] == 3.0
    assert [gpu["index"] for gpu in result["gpus"]] == [0, 1]
    assert result["gpus"][1]["power_w"] == 56.0
    assert result["gpu_status"] == "ok"
    assert fake_nvml.started and fake_nvml.stopped


def test_sampler_keeps_cpu_metrics_when_nvml_is_unavailable():
    fake_psutil = FakePsutil()
    sampler = HardwareSampler(fake_psutil, None)

    sampler.start()
    result = sampler.sample()

    assert result["system_cpu_percent"] == 42.5
    assert result["gpus"] == []
    assert "pynvml" in result["gpu_status"]


@pytest.mark.asyncio
async def test_one_hub_sample_is_shared_with_run_specific_stages():
    events: list[tuple[str, str, dict]] = []

    class Sampler:
        def start(self):
            pass

        def stop(self):
            pass

        @staticmethod
        def sample():
            return sample("2026-08-25T10:00:00+00:00")

    async def write(run_id: str, event_type: str, payload: dict):
        events.append((run_id, event_type, payload))

    settings = Settings(hardware_telemetry_enabled=True, hardware_telemetry_interval_s=60)
    hub = TelemetryHub(settings, sampler=Sampler(), event_writer=write)
    await hub.start()
    try:
        await hub.begin("run-a")
        await hub.begin("run-b")
        hub.set_stage("run-a", "NORMALIZE")
        hub.set_stage("run-b", "SEARCH")
        await hub.collect_once()
        await hub._flush("run-a")
        await hub._flush("run-b")
    finally:
        await hub.stop()

    batches = {
        run_id: payload["samples"][0]
        for run_id, event_type, payload in events
        if event_type == SAMPLE_EVENT
    }
    assert batches["run-a"]["active_run_count"] == 2
    assert batches["run-b"]["active_run_count"] == 2
    assert batches["run-a"]["stage"] == "NORMALIZE"
    assert batches["run-b"]["stage"] == "SEARCH"
    assert batches["run-a"]["timestamp"] == batches["run-b"]["timestamp"]


@pytest.mark.asyncio
async def test_pause_resume_creates_distinct_segments():
    events: list[tuple[str, str, dict]] = []

    class Sampler:
        def start(self):
            pass

        def stop(self):
            pass

        @staticmethod
        def sample():
            return sample("2026-08-25T10:00:00+00:00")

    async def write(run_id: str, event_type: str, payload: dict):
        events.append((run_id, event_type, payload))

    hub = TelemetryHub(
        Settings(hardware_telemetry_interval_s=60), sampler=Sampler(), event_writer=write
    )
    await hub.start()
    try:
        first = await hub.begin("run-a")
        await hub.end("run-a")
        second = await hub.begin("run-a")
        await hub.end("run-a")
    finally:
        await hub.stop()

    assert first != second
    segments = [
        payload for _, event_type, payload in events if event_type == SEGMENT_EVENT
    ]
    assert [event["action"] for event in segments] == ["start", "end", "start", "end"]


def test_artifacts_report_concurrency_and_escape_unavailable_gpu_text():
    samples = [
        sample("2026-08-25T10:00:00+00:00"),
        sample("2026-08-25T10:00:05+00:00", count=2, stage="NORMALIZE"),
    ]
    events = [
        {"action": "start", "segment_id": "segment-1", "timestamp": samples[0]["timestamp"]},
        {"action": "end", "segment_id": "segment-1", "timestamp": samples[1]["timestamp"]},
    ]

    files = build_telemetry_files(
        samples, events, status=RunStatus.COMPLETED.value, interval_seconds=5
    )
    summary = json.loads(files["19_hardware_utilization_summary.json"][1])
    csv_text = files["18_hardware_utilization.csv"][1].decode("utf-8-sig")
    svg = files["20_hardware_utilization.svg"][1].decode()

    assert summary["max_active_run_count"] == 2
    assert summary["active_seconds"] == 5.0
    assert summary["gpus"][0]["utilization_percent"]["max"] == 70.0
    assert "active_run_count" in csv_text
    assert "paralel koşu etkindi" in svg

    root = ElementTree.fromstring(svg)
    texts = root.findall("{http://www.w3.org/2000/svg}text")
    cpu_title = next(item for item in texts if item.text == "CPU kullanımı")
    cpu_legend = next(
        item
        for item in texts
        if item.text == "Sistem" and "legend" in item.attrib.get("class", "").split()
    )
    cpu_top_tick = next(item for item in texts if item.text == "100.0%")
    assert float(cpu_legend.attrib["x"]) >= float(cpu_title.attrib["x"]) + 150
    assert float(cpu_top_tick.attrib["y"]) >= float(cpu_title.attrib["y"]) + 20

    no_gpu = sample("2026-08-25T10:00:00+00:00")
    no_gpu["gpus"] = []
    no_gpu["gpu_status"] = "missing <driver> & utility"
    escaped_svg = build_telemetry_files(
        [no_gpu], events[:1], status=RunStatus.FAILED.value, interval_seconds=5
    )["20_hardware_utilization.svg"][1].decode()
    assert "missing &lt;driver&gt; &amp; utility" in escaped_svg
    assert "missing <driver>" not in escaped_svg


def test_merge_zip_replaces_members_without_duplicates():
    original = zip_bytes({"old.txt": b"old", "20_hardware_utilization.svg": b"stale"})

    merged = merge_zip(original, {"20_hardware_utilization.svg": b"fresh"})

    with zipfile.ZipFile(io.BytesIO(merged)) as archive:
        assert archive.namelist().count("20_hardware_utilization.svg") == 1
        assert archive.read("20_hardware_utilization.svg") == b"fresh"
        assert archive.read("old.txt") == b"old"


@pytest.mark.asyncio
async def test_terminal_finalizer_saves_artifacts_and_enriches_existing_bundles():
    await create_schema()
    # Settings read the deployment's own .env, so the output type is pinned here instead of
    # letting the machine that runs the suite decide which artifacts this test expects.
    settings = get_settings().model_copy(update={"hardware_telemetry_output_type": "all"})
    store = ObjectStore(settings)
    protocol = ResearchProtocol(
        title="Telemetry finalizer",
        primary_question="How is shared hardware load recorded?",
        budget={"max_wall_minutes": 5},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol)
        await repo.event(
            run.id,
            SEGMENT_EVENT,
            {"action": "start", "segment_id": "segment-1",
             "timestamp": "2026-08-25T10:00:00+00:00"},
        )
        await repo.event(
            run.id,
            SAMPLE_EVENT,
            {"samples": [sample("2026-08-25T10:00:00+00:00")], "schema_version": 1},
        )
        await repo.event(
            run.id,
            SEGMENT_EVENT,
            {"action": "end", "segment_id": "segment-1",
             "timestamp": "2026-08-25T10:00:05+00:00"},
        )
        await repo.update_run(run.id, status=RunStatus.COMPLETED.value)
        for bundle_name in ("raw_bundle.zip", "result_bundle.zip", "research_bundle.zip"):
            key = f"runs/{run.id}/{bundle_name}"
            data = zip_bytes({"existing.txt": b"kept"})
            await store.put(key, data, "application/zip")
            await repo.save_artifact(run.id, bundle_name, "application/zip", key, len(data))

    saved = await finalize_hardware_telemetry(run.id, settings, store=store)
    await finalize_hardware_telemetry(run.id, settings, store=store)

    assert set(saved) == {
        "18_hardware_utilization.csv",
        "19_hardware_utilization_summary.json",
        "20_hardware_utilization.svg",
        "hardware_utilization_bundle.zip",
    }
    async with SessionLocal() as session:
        artifacts = {
            artifact.name: artifact
            for artifact in await Repository(
                session, actor=acting_principal()
            ).list_artifacts(run.id)
        }
    for bundle_name, expected in {
        "raw_bundle.zip": {"18_hardware_utilization.csv"},
        "result_bundle.zip": {
            "19_hardware_utilization_summary.json",
            "20_hardware_utilization.svg",
        },
        "research_bundle.zip": {
            "18_hardware_utilization.csv",
            "19_hardware_utilization_summary.json",
            "20_hardware_utilization.svg",
        },
    }.items():
        bundle = await store.get(artifacts[bundle_name].object_key)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            assert expected <= set(archive.namelist())
            assert archive.namelist().count("20_hardware_utilization.svg") <= 1
            assert archive.read("existing.txt") == b"kept"


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.CANCELLED])
@pytest.mark.asyncio
async def test_failed_and_cancelled_runs_get_a_standalone_bundle(status: RunStatus):
    await create_schema()
    protocol = ResearchProtocol(
        title=f"Telemetry {status.value}",
        primary_question="Does terminal telemetry survive?",
        budget={"max_wall_minutes": 5},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol)
        await repo.event(
            run.id,
            SEGMENT_EVENT,
            {"action": "start", "segment_id": "segment-1",
             "timestamp": "2026-08-25T10:00:00+00:00"},
        )
        await repo.event(
            run.id,
            SAMPLE_EVENT,
            {"samples": [sample("2026-08-25T10:00:00+00:00")]},
        )
        await repo.update_run(run.id, status=status.value)

    await finalize_hardware_telemetry(run.id)

    async with SessionLocal() as session:
        names = {
            artifact.name
            for artifact in await Repository(
                session, actor=acting_principal()
            ).list_artifacts(run.id)
        }
    assert "hardware_utilization_bundle.zip" in names


def test_csv_output_type_builds_the_data_files_without_rendering_a_chart():
    samples = [sample("2026-08-25T10:00:00+00:00")]
    events = [
        {"action": "start", "segment_id": "segment-1", "timestamp": samples[0]["timestamp"]},
    ]
    def build(output_type: str):
        return build_telemetry_files(
            samples,
            events,
            status=RunStatus.COMPLETED.value,
            interval_seconds=60,
            output_type=output_type,
        )

    assert set(build("csv")) == {CSV_FILE, SUMMARY_FILE}
    assert set(build("all")) == {CSV_FILE, SUMMARY_FILE, SVG_FILE}
    # The data files must stay byte-identical: "csv" drops the chart, it does not degrade
    # the measurements or the summary behind it.
    assert build("csv")[CSV_FILE] == build("all")[CSV_FILE]
    assert build("csv")[SUMMARY_FILE] == build("all")[SUMMARY_FILE]


@pytest.mark.asyncio
async def test_csv_output_type_keeps_the_svg_out_of_artifacts_and_bundles():
    await create_schema()
    settings = get_settings().model_copy(update={"hardware_telemetry_output_type": "csv"})
    store = ObjectStore(settings)
    protocol = ResearchProtocol(
        title="Telemetry csv output",
        primary_question="Does the output type gate the chart?",
        budget={"max_wall_minutes": 5},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol)
        await repo.event(
            run.id,
            SEGMENT_EVENT,
            {"action": "start", "segment_id": "segment-1",
             "timestamp": "2026-08-25T10:00:00+00:00"},
        )
        await repo.event(
            run.id,
            SAMPLE_EVENT,
            {"samples": [sample("2026-08-25T10:00:00+00:00")], "schema_version": 1},
        )
        await repo.update_run(run.id, status=RunStatus.COMPLETED.value)
        for bundle_name in ("raw_bundle.zip", "result_bundle.zip", "research_bundle.zip"):
            key = f"runs/{run.id}/{bundle_name}"
            data = zip_bytes({"existing.txt": b"kept"})
            await store.put(key, data, "application/zip")
            await repo.save_artifact(run.id, bundle_name, "application/zip", key, len(data))

    saved = await finalize_hardware_telemetry(run.id, settings, store=store)

    assert set(saved) == {CSV_FILE, SUMMARY_FILE, "hardware_utilization_bundle.zip"}
    assert SVG_FILE not in saved
    async with SessionLocal() as session:
        artifacts = {
            artifact.name: artifact
            for artifact in await Repository(
                session, actor=acting_principal()
            ).list_artifacts(run.id)
        }
    assert SVG_FILE not in artifacts
    for bundle_name, expected in {
        "hardware_utilization_bundle.zip": {CSV_FILE, SUMMARY_FILE},
        "raw_bundle.zip": {CSV_FILE},
        "result_bundle.zip": {SUMMARY_FILE},
        "research_bundle.zip": {CSV_FILE, SUMMARY_FILE},
    }.items():
        bundle = await store.get(artifacts[bundle_name].object_key)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names = set(archive.namelist())
        assert expected <= names
        assert SVG_FILE not in names


def test_settings_validate_the_sampling_interval_and_panel_has_preview_support():
    with pytest.raises(ValidationError):
        Settings(hardware_telemetry_interval_s=0.5)
    with pytest.raises(ValidationError):
        Settings(hardware_telemetry_output_type="svg")
    # _env_file=None reads the code default rather than whatever this deployment's .env says.
    assert Settings(_env_file=None).hardware_telemetry_output_type == "all"
    assert "20_hardware_utilization.svg" in CONTROL_PANEL_HTML
    assert "Donanım Kullanımı" in CONTROL_PANEL_HTML
    assert "URL.createObjectURL(blob),img=document.createElement('img')" not in CONTROL_PANEL_HTML
    assert "img.src=`/api/runs/${runId}/artifacts/" in CONTROL_PANEL_HTML


@pytest.mark.asyncio
async def test_pipeline_boundary_sets_the_run_specific_telemetry_stage():
    stages = []

    class Telemetry:
        @staticmethod
        def set_stage(run_id: str, stage: str):
            stages.append((run_id, stage))

    class Repo:
        @staticmethod
        async def get_run(run_id: str):
            return SimpleNamespace(id=run_id, status=RunStatus.RUNNING.value)

        @staticmethod
        async def checkpoint(run_id: str, stage: str, state: dict):
            pass

        @staticmethod
        async def event(run_id: str, event_type: str, payload: dict):
            pass

    pipeline = ResearchPipeline.__new__(ResearchPipeline)
    pipeline.telemetry = Telemetry()
    pipeline.repo = Repo()

    await pipeline._boundary({"run_id": "run-a", "round_number": 2}, "NORMALIZE")

    assert stages == [("run-a", "NORMALIZE")]
