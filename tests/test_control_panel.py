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
        assert health.json()["version"] == "0.6.9"

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
