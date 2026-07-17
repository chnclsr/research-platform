from fastapi.testclient import TestClient

from research_platform import control_panel


def test_control_panel_is_local_management_surface():
    with TestClient(control_panel.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.5.1"

        page = client.get("/")
        assert page.status_code == 200
        assert "Research Platform" in page.text
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
