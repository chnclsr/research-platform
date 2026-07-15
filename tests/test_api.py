from fastapi.testclient import TestClient

from research_platform.api import app


def test_create_and_read_run():
    with TestClient(app) as client:
        response = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "API acceptance test",
                "primary_question": "Can the API create a validated research run?",
                "connectors": {"profile": "core"},
            }
        })
        assert response.status_code == 200, response.text
        created = response.json()
        assert created["status"] == "queued"
        fetched = client.get(f"/v1/research-runs/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["protocol"]["title"] == "API acceptance test"


def test_api_rejects_bad_protocol():
    with TestClient(app) as client:
        response = client.post("/v1/research-runs", json={
            "protocol": {"title": "x", "primary_question": "short"}
        })
        assert response.status_code == 422

