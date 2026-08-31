import asyncio
import json
import re

import pytest
from conftest import acting_principal
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from research_platform import control_panel
from research_platform.auth import Principal
from research_platform.control_panel_ui import CONTROL_PANEL_HTML
from research_platform.db import SessionLocal, create_schema
from research_platform.identity import create_user, get_user_by_email
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol
from research_platform.version import VERSION

PANEL_PASSWORD = "panel-test-password"


def test_run_drawer_uses_turkish_title_case_and_collapsible_sources():
    assert "Kalite ve Kapsam" in CONTROL_PANEL_HTML
    assert "Sorgu Dalları" in CONTROL_PANEL_HTML
    assert "Kabul Edilen Kaynaklar" in CONTROL_PANEL_HTML
    assert "Kalite ve coverage" not in CONTROL_PANEL_HTML
    assert "detailSection('Sorgu dalları')" not in CONTROL_PANEL_HTML
    assert "collapsibleDetailSection(`Kabul Edilen Kaynaklar" in CONTROL_PANEL_HTML
    assert "h('details','drawer-section collapsible-section')" in CONTROL_PANEL_HTML


def test_flow_view_absorbs_the_timeline_and_can_go_fullscreen():
    # The chronological strip is gone: a 205-round run made it 2069 cards long, and the
    # rounds of one stage were unreachable without hunting through it.
    assert "detailSection('Pipeline Zaman Çizelgesi')" not in CONTROL_PANEL_HTML
    assert "detailSection('Araştırma Akışı')" in CONTROL_PANEL_HTML
    assert "⤢ Tam ekran" in CONTROL_PANEL_HTML
    assert "flow-fullscreen" in CONTROL_PANEL_HTML
    # Only a stage that actually ran is clickable, and its rounds come from the new endpoint.
    assert "if(node.visits){item.classList.add('clickable')" in CONTROL_PANEL_HTML
    assert "/api/runs/${data.run.id}/stages/${encodeURIComponent(next)}" in CONTROL_PANEL_HTML
    # Escape leaves fullscreen before it closes the run drawer.
    assert "const expanded=document.querySelector('.flow-fullscreen');if(expanded)" in (
        CONTROL_PANEL_HTML
    )


def test_stage_durations_below_a_second_keep_their_decimals():
    # A recovery round that acquired nothing returns in milliseconds. Math.round turned every
    # such stage into "0 sn", which read as a broken timeline rather than a no-op stage.
    assert "if(s>0&&s<1)return`${s.toFixed(2).replace('.',',')} sn`" in CONTROL_PANEL_HTML
    # Whole seconds, minutes and hours keep the format they already had.
    assert "if(s<60)return`${Math.round(s)} sn`" in CONTROL_PANEL_HTML
    assert "if(s<3600)return`${Math.floor(s/60)} dk ${Math.round(s%60)} sn`" in CONTROL_PANEL_HTML


def test_panel_has_persistent_light_mode_and_relevance_sorted_sources():
    assert "☀ Aydınlık Mod" in CONTROL_PANEL_HTML
    assert "☾ Karanlık Mod" in CONTROL_PANEL_HTML
    assert "research-platform-theme" in CONTROL_PANEL_HTML
    assert 'html[data-theme="light"]' in CONTROL_PANEL_HTML
    assert "detailSection('Referans Haritası')" in CONTROL_PANEL_HTML
    assert "detailSection('Kaynak Hunisi')" not in CONTROL_PANEL_HTML
    assert "sort((a,b)=>Number(b.relevance_score??0)-Number(a.relevance_score??0))" in CONTROL_PANEL_HTML


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


async def _account(email: str, role: str) -> str:
    """Create a panel account, or return the existing one's id."""
    await create_schema()
    async with SessionLocal() as session:
        existing = await get_user_by_email(session, email)
        if existing is not None:
            return existing.id
        user = await create_user(
            session,
            email=email,
            display_name=email.split("@")[0],
            password=PANEL_PASSWORD,
            role=role,
        )
        return user.id


def _sign_in(client: TestClient, email: str) -> str:
    """Sign in through the real form and return the session's CSRF token."""
    response = client.post(
        "/login",
        data={"email": email, "password": PANEL_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    page = client.get("/")
    assert page.status_code == 200
    match = re.search(r'name="control-token" content="([0-9a-f]+)"', page.text)
    assert match, "panel sayfası CSRF jetonu taşımalı"
    return match.group(1)


def test_panel_requires_a_session_and_serves_the_login_form():
    with TestClient(control_panel.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == VERSION

        # The dashboard is no longer reachable without signing in.
        redirected = client.get("/", follow_redirects=False)
        assert redirected.status_code == 303
        assert redirected.headers["location"] == "/login"

        form = client.get("/login")
        assert form.status_code == 200
        assert "Giriş yap" in form.text
        assert form.headers["x-frame-options"] == "DENY"

        assert client.get("/api/status").status_code == 401


@pytest.mark.asyncio
async def test_signed_in_user_sees_the_dashboard():
    await _account("panel-user@example.test", "user")
    with TestClient(control_panel.app) as client:
        _sign_in(client, "panel-user@example.test")
        page = client.get("/")
        assert "Sentinel Recall" in page.text
        assert "Connector operasyon görünümü" in page.text
        assert "flow-nodes" in page.text
        assert f"· v{VERSION}" in page.text


@pytest.mark.asyncio
async def test_bad_credentials_do_not_reveal_whether_the_account_exists():
    await _account("panel-user@example.test", "user")
    with TestClient(control_panel.app) as client:
        wrong_password = client.post(
            "/login",
            data={"email": "panel-user@example.test", "password": "not-the-password"},
            follow_redirects=False,
        )
        unknown_account = client.post(
            "/login",
            data={"email": "nobody@example.test", "password": PANEL_PASSWORD},
            follow_redirects=False,
        )
    assert wrong_password.status_code == unknown_account.status_code == 401
    assert "E-posta veya parola hatalı" in wrong_password.text
    assert wrong_password.text == unknown_account.text


@pytest.mark.asyncio
async def test_stopping_the_stack_is_restricted_to_administrators(monkeypatch):
    """The button that stops the worker must not come with an ordinary account."""

    async def fake_status(principal):
        return {"overall": "running", "queue": {"waiting": 0}, "runs": {"active": []}}

    async def fake_powershell(script: str):
        assert script == "stop_native.ps1"
        return 0, "stopped"

    monkeypatch.setattr(control_panel, "build_status", fake_status)
    monkeypatch.setattr(control_panel, "_run_powershell", fake_powershell)

    await _account("panel-user@example.test", "user")
    await _account("panel-admin@example.test", "admin")

    with TestClient(control_panel.app) as client:
        csrf = _sign_in(client, "panel-user@example.test")
        assert client.get("/api/status").status_code == 200
        denied = client.post("/api/system/stop", headers={"X-Control-Token": csrf})
        assert denied.status_code == 403

    with TestClient(control_panel.app) as client:
        csrf = _sign_in(client, "panel-admin@example.test")
        stopped = client.post("/api/system/stop", headers={"X-Control-Token": csrf})
        assert stopped.status_code == 200
        assert stopped.json() == {"ok": True, "action": "stop", "message": "stopped"}


@pytest.mark.asyncio
async def test_state_changing_calls_need_the_session_csrf_token():
    await _account("panel-admin@example.test", "admin")
    with TestClient(control_panel.app) as client:
        _sign_in(client, "panel-admin@example.test")
        # A valid session is not enough; the request must echo the page's token.
        assert client.post("/api/system/stop").status_code == 403
        assert (
            client.post("/api/system/stop", headers={"X-Control-Token": "wrong"}).status_code
            == 403
        )


@pytest.mark.asyncio
async def test_panel_run_list_shows_only_the_signed_in_users_runs():
    owner_id = await _account("panel-owner@example.test", "user")
    other_id = await _account("panel-other@example.test", "user")
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.user(owner_id))
        mine = await repo.create_run(ResearchProtocol(
            title="Owner run",
            primary_question="Which runs belong to the signed-in panel user?",
            budget={"max_wall_minutes": 30},
        ))
        theirs = await Repository(session, actor=Principal.user(other_id)).create_run(
            ResearchProtocol(
                title="Other run",
                primary_question="Which runs belong to somebody else entirely?",
                budget={"max_wall_minutes": 30},
            )
        )

    queue = {"jobs": []}
    snapshot = await control_panel._run_snapshot(queue, Principal.user(owner_id))
    assert mine.id in {run["id"] for run in snapshot["active"] + snapshot["recent"]}
    # Not merely absent from the tables: absent from the payload. The team section now
    # reports the other user's run, so the assertion has to cover what it says about it.
    assert theirs.id not in json.dumps(snapshot)
    assert "Which runs belong to somebody else entirely?" not in json.dumps(snapshot)

    # And the panel's detail view refuses the other user's run outright.
    with pytest.raises(HTTPException) as excinfo:
        await control_panel._run_detail(theirs.id, Principal.user(owner_id))
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_stage_endpoint_breaks_each_stage_visit_down_by_tool():
    """Tools moved off the detail payload: the flow view asks for one stage at a time."""
    owner_id = await _account("panel-tools@example.test", "user")
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.user(owner_id))
        run = await repo.create_run(ResearchProtocol(
            title="Tooling run",
            primary_question="Which tools ran in which stage of this research?",
            budget={"max_wall_minutes": 30},
        ))
        await repo.event(run.id, "stage", {"stage": "SEARCH", "round": 1})
        await repo.event(run.id, "connector_metrics", {"calls": [
            {"connector": "crossref", "success": True, "result_count": 6,
             "latency_seconds": 1.2},
        ]})
        await repo.event(run.id, "stage", {"stage": "ACQUIRE", "round": 1})
        await repo.event(run.id, "acquisition_metrics", {"calls": [
            {"connector": "crossref", "success": True, "method": "direct",
             "parser_id": "pdf", "latency_seconds": 3.0},
        ]})

    # The detail payload still lists every visit, it just no longer carries tool rows.
    detail = await control_panel._run_detail(run.id, Principal.user(owner_id))
    assert [row["stage"] for row in detail["timeline"]] == ["SEARCH", "ACQUIRE"]
    assert "tools" not in detail["timeline"][0]

    principal = Principal.user(owner_id)
    search = await control_panel._run_stage_detail(run.id, "SEARCH", 0, principal)
    assert search["visit_count"] == 1
    assert [(row["kind"], row["name"]) for row in search["visits"][0]["tools"]] == [
        ("connector", "crossref")
    ]
    assert search["visits"][0]["tools"][0]["results"] == 6
    assert search["visits"][0]["summary"]["connectors"] == 1
    assert search["has_more"] is False

    acquire = await control_panel._run_stage_detail(run.id, "ACQUIRE", 0, principal)
    assert [(row["kind"], row["name"]) for row in acquire["visits"][0]["tools"]] == [
        ("method", "direct"),
        ("parser", "pdf"),
    ]


@pytest.mark.asyncio
async def test_stage_endpoint_lists_every_round_and_hides_other_peoples_runs():
    """A recovery loop visits a stage many times; the flow view has to show all of them."""
    owner_id = await _account("panel-stage-rounds@example.test", "user")
    other_id = await _account("panel-stage-other@example.test", "user")
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.user(owner_id))
        run = await repo.create_run(ResearchProtocol(
            title="Looping run",
            primary_question="How many times did acquisition run in this research?",
            budget={"max_wall_minutes": 30},
        ))
        for round_number in range(1, 6):
            await repo.event(run.id, "stage", {"stage": "SEARCH", "round": round_number})
            await repo.event(run.id, "stage", {"stage": "ACQUIRE", "round": round_number})
            await repo.event(run.id, "acquisition_metrics", {"calls": [
                {"connector": "crossref", "success": True, "method": "direct",
                 "parser_id": "pdf", "latency_seconds": 1.0},
            ]})

    principal = Principal.user(owner_id)
    acquire = await control_panel._run_stage_detail(run.id, "ACQUIRE", 0, principal)
    assert acquire["visit_count"] == 5
    assert [row["round"] for row in acquire["visits"]] == [1, 2, 3, 4, 5]
    assert all(row["tools"] for row in acquire["visits"])

    with pytest.raises(HTTPException) as excinfo:
        await control_panel._run_stage_detail(run.id, "NOT_A_STAGE", 0, principal)
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        await control_panel._run_stage_detail(run.id, "ACQUIRE", 0, Principal.user(other_id))
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_panel_shows_other_peoples_active_runs_without_their_content():
    """Isolation without this reads as a broken panel: a queued run and an empty table."""
    watcher_id = await _account("panel-watcher@example.test", "user")
    busy_id = await _account("panel-busy@example.test", "user")
    async with SessionLocal() as session:
        theirs = await Repository(session, actor=Principal.user(busy_id)).create_run(
            ResearchProtocol(
                title="Somebody else's subject",
                primary_question="What is the other team member actually researching?",
                budget={"max_wall_minutes": 30},
            )
        )

    queue = {"jobs": [{"run_id": theirs.id, "position": 2, "running": False}]}
    snapshot = await control_panel._run_snapshot(queue, Principal.user(watcher_id))

    entry = next(
        item for item in snapshot["team"] if item["owner_name"] == "panel-busy"
    )
    assert entry["status"] == "queued"
    assert entry["queue_position"] == 2
    assert set(entry) == {
        "owner_name",
        "status",
        "current_stage",
        "queue_position",
        "priority",
        "elapsed_seconds",
    }
    assert theirs.id not in json.dumps(snapshot)
    assert "Somebody else's subject" not in json.dumps(snapshot)


@pytest.mark.asyncio
async def test_admin_gets_no_team_section_because_the_main_table_is_complete():
    admin_id = await _account("panel-team-admin@example.test", "admin")
    other_id = await _account("panel-team-other@example.test", "user")
    async with SessionLocal() as session:
        await Repository(session, actor=Principal.user(other_id)).create_run(
            ResearchProtocol(
                title="Visible to the admin in full",
                primary_question="Does the admin need a redacted copy of this run?",
                budget={"max_wall_minutes": 30},
            )
        )

    snapshot = await control_panel._run_snapshot(
        {"jobs": []}, Principal.user(admin_id, "admin")
    )
    assert snapshot["team"] == []
    # The run is not hidden from them -- it is in the main table, in full.
    assert "Visible to the admin in full" in json.dumps(snapshot)


def test_queue_listing_hides_run_identifiers_from_non_admins():
    """The team view is careful about ids; the queue card must not hand them out anyway."""
    queue = {
        "available": True,
        "waiting": 1,
        "jobs": [{"job_id": "run:abc", "run_id": "abc", "position": 1, "running": True}],
    }
    for_user = control_panel._publishable_queue(queue, Principal.user("01USER".ljust(26, "0")))
    assert for_user["waiting"] == 1
    assert for_user["jobs"] == [{"position": 1, "running": True}]

    for_admin = control_panel._publishable_queue(queue, Principal.user("01ADM".ljust(26, "0"), "admin"))
    assert for_admin["jobs"][0]["run_id"] == "abc"


@pytest.mark.asyncio
async def test_connector_snapshot_prefers_the_service_token(monkeypatch):
    """Connector health uses the same trusted-intermediary credential as panel proxies."""
    request_headers: dict[str, str] = {}

    class Settings:
        research_api_url = "http://research-api.example.test"
        service_token = "service-token"
        api_token = "legacy-api-token"

    class Response:
        is_success = True

        @staticmethod
        def json():
            return [
                {
                    "id": "snapshot_test",
                    "family": "academic",
                    "enabled": True,
                    "healthy": True,
                    "detail": "configured",
                    "capabilities": ["search"],
                }
            ]

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, url: str, *, headers: dict[str, str]):
            assert url == "http://research-api.example.test/v1/connectors"
            request_headers.update(headers)
            return Response()

    monkeypatch.setattr(control_panel, "get_settings", Settings)
    monkeypatch.setattr(control_panel.httpx, "AsyncClient", Client)

    snapshot = await control_panel._connector_snapshot()

    assert request_headers == {"Authorization": "Bearer service-token"}
    connector = next(item for item in snapshot if item["id"] == "snapshot_test")
    assert connector["enabled"] is True
    assert connector["healthy"] is True


@pytest.mark.asyncio
async def test_run_detail_exposes_timeline_funnel_and_quality():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(ResearchProtocol(
            title="Panel detail",
            primary_question="Does the panel explain research collection quality?",
            budget={"max_wall_minutes": 30},
        ))
        await repo.event(run.id, "stage", {"stage": "SEARCH", "round": 1})
        await repo.event(run.id, "connector_metrics", {"calls": [{
            "connector": "crossref", "branch_id": "query:0", "query": "quality",
            "success": True, "result_count": 3, "latency_seconds": 0.5,
        }]})
        await repo.event(run.id, "coverage_gaps", {
            "discovery_quality": {"sentinel_recall": 0.5, "accepted_candidates": 2},
        })
    detail = await control_panel._run_detail(run.id, acting_principal())
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


# ------------------------------------------------- kullanicinin kendi parolasini degistirmesi


def _change_password(client: TestClient, csrf: str, current: str, new: str):
    return client.post(
        "/api/account/password",
        headers={"X-Control-Token": csrf},
        json={"current_password": current, "new_password": new},
    )


@pytest.mark.asyncio
async def test_user_changes_own_password_and_stays_signed_in():
    """The caller keeps working; the database holds the new hash."""
    await _account("pw-change@example.test", "user")
    new_password = "yeni-parola-degeri"
    with TestClient(control_panel.app) as client:
        csrf = _sign_in(client, "pw-change@example.test")
        assert _change_password(client, csrf, PANEL_PASSWORD, new_password).status_code == 200

        # The cookie was re-issued with the bumped token_version, so this session lives on.
        assert client.get("/api/session").status_code == 200

    # Old password no longer works, new one does.
    with TestClient(control_panel.app) as client:
        rejected = client.post(
            "/login",
            data={"email": "pw-change@example.test", "password": PANEL_PASSWORD},
            follow_redirects=False,
        )
        assert rejected.status_code == 401
        accepted = client.post(
            "/login",
            data={"email": "pw-change@example.test", "password": new_password},
            follow_redirects=False,
        )
        assert accepted.status_code == 303


@pytest.mark.asyncio
async def test_wrong_current_password_is_refused_and_changes_nothing():
    """Otherwise a borrowed session would become permanent account takeover."""
    await _account("pw-wrong@example.test", "user")
    async with SessionLocal() as session:
        before = (await get_user_by_email(session, "pw-wrong@example.test")).password_hash

    with TestClient(control_panel.app) as client:
        csrf = _sign_in(client, "pw-wrong@example.test")
        response = _change_password(client, csrf, "bu-parola-yanlis", "yeni-parola-degeri")
        assert response.status_code == 403

    async with SessionLocal() as session:
        user = await get_user_by_email(session, "pw-wrong@example.test")
        assert user.password_hash == before

    # The account still opens with the original password.
    with TestClient(control_panel.app) as client:
        assert _sign_in(client, "pw-wrong@example.test")


@pytest.mark.asyncio
async def test_password_change_signs_out_other_devices():
    """token_version is bumped, so a cookie issued before the change stops working."""
    await _account("pw-others@example.test", "user")
    with TestClient(control_panel.app) as other_device:
        _sign_in(other_device, "pw-others@example.test")
        assert other_device.get("/api/session").status_code == 200

        with TestClient(control_panel.app) as changer:
            csrf = _sign_in(changer, "pw-others@example.test")
            assert _change_password(
                changer, csrf, PANEL_PASSWORD, "bambaska-bir-parola"
            ).status_code == 200

        assert other_device.get("/api/session").status_code == 401


@pytest.mark.asyncio
async def test_password_change_requires_a_session_and_the_csrf_token():
    await _account("pw-guard@example.test", "user")
    with TestClient(control_panel.app) as client:
        # No session at all.
        assert client.post(
            "/api/account/password",
            json={"current_password": PANEL_PASSWORD, "new_password": "x-y-z"},
        ).status_code == 401

    with TestClient(control_panel.app) as client:
        csrf = _sign_in(client, "pw-guard@example.test")
        # Signed in, but the request does not echo the page's token.
        assert client.post(
            "/api/account/password",
            json={"current_password": PANEL_PASSWORD, "new_password": "x-y-z"},
        ).status_code == 403
        # Empty new password is refused before anything is written.
        assert _change_password(client, csrf, PANEL_PASSWORD, "").status_code == 400


def _panel_route_paths() -> set[str]:
    return {getattr(route, "path", "") for route in control_panel.app.routes}


def test_the_panel_cannot_answer_a_checkpoint():
    """One gate, one mouth.

    Answering from the panel while Telegram was waiting left the chat holding buttons for
    a decision already made. The API's own /v1/research-runs/{id}/respond stays -- this is
    only the panel's proxy, and its absence is what makes the rule enforceable rather than
    a convention.
    """
    assert "/api/runs/{run_id}/respond" not in _panel_route_paths()
    assert not hasattr(control_panel, "run_respond")


def test_the_panel_still_manages_the_queue():
    """Pause, resume, cancel and priority are queue operations, not chat interventions."""
    paths = _panel_route_paths()
    assert "/api/runs/{run_id}/priority" in paths
    assert "/api/runs/{run_id}/{action}" in paths


def test_the_checkpoint_card_shows_the_decision_without_offering_it():
    """Watching a run means seeing what it is waiting for; only the inputs are gone."""
    # No way back to the removed route, by button or by fetch.
    assert "submitHitl" not in CONTROL_PANEL_HTML
    assert "/respond" not in CONTROL_PANEL_HTML
    # The payload is still rendered in full for every checkpoint type.
    assert "function renderHitl(" in CONTROL_PANEL_HTML
    assert "card.append(planView(plan))" in CONTROL_PANEL_HTML
    assert "JSON.stringify(payload.outline||payload,null,2)" in CONTROL_PANEL_HTML
    assert "payload.domains||[]" in CONTROL_PANEL_HTML
    assert "payload.questions||[]" in CONTROL_PANEL_HTML
    # The title no longer asks the reader for a decision they cannot give here.
    assert "detailSection('Kullanıcı Kararı Bekleniyor')" in CONTROL_PANEL_HTML
    assert "Kullanıcı Kararı Gerekiyor" not in CONTROL_PANEL_HTML
    # And it says where the decision does happen.
    assert "koşunun başlatıldığı kanaldan veriliyor" in CONTROL_PANEL_HTML


def test_no_dead_approval_strings_are_left_in_the_plan_labels():
    """A label nothing renders rots quietly; the plan text keeps only what is used."""
    assert "rejectNeedsReason" not in CONTROL_PANEL_HTML
    assert "Onayla ve başlat" not in CONTROL_PANEL_HTML
    assert "Approve and start" not in CONTROL_PANEL_HTML
    # The duration label survives: the plan card still reports the budget it was given.
    assert "Araştırma süresi (dakika)" in CONTROL_PANEL_HTML


@pytest.mark.asyncio
async def test_the_main_table_names_who_started_each_run():
    """An admin's table is the only one that mixes owners, and it was anonymous."""
    admin_id = await _account("panel-owner-admin@example.test", "admin")
    other_id = await _account("panel-owner-other@example.test", "user")
    async with SessionLocal() as session:
        await Repository(session, actor=Principal.user(other_id)).create_run(
            ResearchProtocol(
                title="Started by somebody else",
                primary_question="Who started this run?",
                budget={"max_wall_minutes": 30},
            )
        )

    snapshot = await control_panel._run_snapshot(
        {"jobs": []}, Principal.user(admin_id, "admin")
    )
    row = next(
        item
        for item in snapshot["active"] + snapshot["recent"]
        if item["title"] == "Started by somebody else"
    )
    assert row["owner_name"] == "panel-owner-other"
    assert row["owner_id"] == other_id


@pytest.mark.asyncio
async def test_a_run_without_an_owner_is_not_attributed_to_the_reader():
    admin_id = await _account("panel-owner-orphan@example.test", "admin")
    async with SessionLocal() as session:
        run = await Repository(session, actor=Principal.user(admin_id, "admin")).create_run(
            ResearchProtocol(
                title="Predates ownership",
                primary_question="Whose run is this?",
                budget={"max_wall_minutes": 30},
            )
        )
        row = await session.get(control_panel.ResearchRunRow, run.id)
        row.owner_id = None
        await session.commit()

    snapshot = await control_panel._run_snapshot(
        {"jobs": []}, Principal.user(admin_id, "admin")
    )
    orphan = next(
        item
        for item in snapshot["active"] + snapshot["recent"]
        if item["title"] == "Predates ownership"
    )
    assert orphan["owner_name"] is None
    assert orphan["owner_id"] is None


def test_the_owner_column_is_revealed_by_the_session_not_by_the_payload():
    """Every table renders the column; only an admin's session shows it."""
    assert '<th class="owner-col">Başlatan</th>' in CONTROL_PANEL_HTML
    assert "body:not(.is-admin) .owner-col{display:none}" in CONTROL_PANEL_HTML
    assert "document.body.classList.toggle('is-admin',!!s.is_admin)" in CONTROL_PANEL_HTML
    assert "tr.append(runTitle(run),ownerCell(run))" in CONTROL_PANEL_HTML


def test_the_query_branch_table_collapses_like_the_source_table():
    assert "collapsibleDetailSection(`Sorgu Dalları" in CONTROL_PANEL_HTML
    assert "detailSection('Sorgu Dalları')" not in CONTROL_PANEL_HTML
    assert "branchSection.content.append(branchWrap);body.append(branchSection.wrap)" in (
        CONTROL_PANEL_HTML
    )
