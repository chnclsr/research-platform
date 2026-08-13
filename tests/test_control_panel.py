import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from research_platform import control_panel
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol


def _network_guard_app(networks: list[str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        control_panel.ControlPanelNetworkGuard,
        allowed_networks=networks,
    )

    @app.get("/")
    async def index():
        return {"ok": True}

    return app


def test_control_panel_network_guard_allows_office_cidr_and_rejects_others():
    guarded = _network_guard_app(["10.0.10.0/24"])
    with TestClient(guarded, client=("10.0.10.42", 50000)) as allowed:
        assert allowed.get("/").status_code == 200
    with TestClient(guarded, client=("10.0.11.42", 50000)) as denied:
        response = denied.get("/")
        assert response.status_code == 403
        assert response.text == "Office network access denied"


def test_control_panel_is_local_management_surface():
    with TestClient(control_panel.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.7.0"

        page = client.get("/")
        assert page.status_code == 200
        assert "Research Platform" in page.text
        assert "Sentinel recall" in page.text
        assert "Connector operasyon görünümü" in page.text
        assert "Araştırma akışı" in page.text
        assert "flow-nodes" in page.text
        assert control_panel.CONTROL_TOKEN in page.text
        assert page.headers["x-frame-options"] == "DENY"

        unauthorized = client.get("/api/status")
        assert unauthorized.status_code == 403


def test_control_panel_status_and_stop_action_are_token_protected(monkeypatch):
    async def fake_status():
        return {"overall": "running", "queue": {"waiting": 0}, "runs": {"active": []}}

    async def fake_powershell(script: str):
        assert script == "stop_native.ps1"
        return 0, "stopped"

    monkeypatch.setattr(control_panel, "build_status", fake_status)
    monkeypatch.setattr(control_panel, "_run_powershell", fake_powershell)
    headers = {"X-Control-Token": control_panel.CONTROL_TOKEN}

    with TestClient(control_panel.app) as client:
        status = client.get("/api/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["overall"] == "running"

        stopped = client.post("/api/system/stop", headers=headers)
        assert stopped.status_code == 200
        assert stopped.json() == {
            "ok": True,
            "action": "stop",
            "message": "stopped",
        }

        invalid = client.post("/api/system/stop")
        assert invalid.status_code == 403


@pytest.mark.asyncio
async def test_run_detail_exposes_timeline_funnel_and_quality():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session)
        run = await repo.create_run(ResearchProtocol(
            title="Panel detail",
            primary_question="Does the panel explain research collection quality?",
        ))
        await repo.event(run.id, "stage", {"stage": "SEARCH", "round": 1})
        await repo.event(run.id, "connector_metrics", {"calls": [{
            "connector": "crossref", "branch_id": "query:0", "query": "quality",
            "success": True, "result_count": 3, "latency_seconds": 0.5,
        }]})
        await repo.event(run.id, "coverage_gaps", {
            "discovery_quality": {"sentinel_recall": 0.5, "accepted_candidates": 2},
        })
    detail = await control_panel._run_detail(run.id)
    assert detail["timeline"][0]["stage"] == "SEARCH"
    assert detail["flow"]["current_stage"] == "SEARCH"
    assert any(
        node["stage"] == "SEARCH" and node["state"] == "active"
        for node in detail["flow"]["nodes"]
    )
    assert detail["funnel"]["steps"][0]["value"] == 3
    assert detail["quality"]["sentinel_recall"] == 0.5
    assert detail["query_branches"][0]["connectors"] == ["crossref"]


@pytest.mark.asyncio
async def test_gpu_snapshot_keeps_row_when_power_draw_is_not_available(monkeypatch):
    class Process:
        returncode = 0

        async def communicate(self):
            return (
                b"0, NVIDIA GeForce RTX 4060, 7, 1388, 8188, 30, [N/A], 115.00\n",
                b"",
            )

    async def fake_subprocess(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    rows = await control_panel._gpu_snapshot()
    assert rows[0]["name"] == "NVIDIA GeForce RTX 4060"
    assert rows[0]["memory_total_mb"] == 8188
    assert rows[0]["power_draw_w"] is None


def test_compose_environment_drops_keys_the_project_env_file_defines(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+asyncpg://research:research@postgres:5432/research\n"
        "# comment=ignored\n"
        "REDIS_URL=redis://redis:6379/0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(control_panel, "ROOT", tmp_path)
    # start_control_panel.ps1 loads the native env file into the panel's own process.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://research:research@127.0.0.1:5433/research")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    monkeypatch.setenv("PATH", "/usr/bin")

    environment = control_panel._compose_environment()

    # Compose must fall back to the project .env instead of the panel's host addresses.
    assert "DATABASE_URL" not in environment
    assert "REDIS_URL" not in environment
    assert environment["PATH"] == "/usr/bin"


class _DeploymentSettings:
    def __init__(self, deployment: str, telegram_bot_token: str | None = None):
        self.control_panel_deployment = deployment
        self.telegram_bot_token = telegram_bot_token


@pytest.mark.asyncio
async def test_docker_deployment_reads_service_state_from_compose(monkeypatch):
    class Process:
        returncode = 0

        async def communicate(self):
            return (
                b'{"Service":"api","State":"running","Status":"Up 2 hours"}\n'
                b'{"Service":"mcp-gateway","State":"running","Status":"Up 5 minutes"}\n'
                b'{"Service":"worker","State":"exited","Status":"Exited (1)"}\n'
                b'{"Service":"postgres","State":"running","Status":"Up 2 hours"}\n',
                b"",
            )

    async def fake_subprocess(*args, **kwargs):
        assert args[:3] == ("docker", "compose", "ps")
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    monkeypatch.setattr(control_panel, "get_settings", lambda: _DeploymentSettings("docker"))

    processes = await control_panel._service_processes()

    # Compose spells two services differently; the panel keeps its own names.
    assert processes["api"] == {"running": True, "pid": None, "detail": "Up 2 hours"}
    assert processes["mcp"] == {"running": True, "pid": None, "detail": "Up 5 minutes"}
    assert processes["worker"]["running"] is False
    # telegram-bot never appeared in the compose output, so it stays absent.
    assert processes["telegram"] == {"running": False, "pid": None, "detail": ""}


@pytest.mark.asyncio
async def test_docker_deployment_start_uses_compose_and_skips_telegram_without_token(monkeypatch):
    calls: list[tuple[str, ...]] = []

    class Process:
        returncode = 0

        async def communicate(self):
            return (b"started", b"")

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        return Process()

    async def fail_powershell(script: str):
        raise AssertionError(f"native script {script} must not run in docker deployment")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    monkeypatch.setattr(control_panel, "_run_powershell", fail_powershell)
    monkeypatch.setattr(control_panel, "get_settings", lambda: _DeploymentSettings("docker"))

    return_code, _ = await control_panel._run_compose_action("start")
    assert return_code == 0
    assert calls[0] == ("docker", "compose", "up", "-d")

    calls.clear()
    monkeypatch.setattr(
        control_panel, "get_settings", lambda: _DeploymentSettings("docker", "bot-token")
    )
    await control_panel._run_compose_action("stop")
    assert calls[0] == (
        "docker",
        "compose",
        "--profile",
        "telegram",
        "stop",
        "api",
        "worker",
        "mcp-gateway",
        "telegram-bot",
    )
