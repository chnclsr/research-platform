from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./.pytest-research.db"
os.environ["TESTING"] = "true"
os.environ["LLM_PROVIDER"] = "deterministic"
os.environ["DOMAIN_DELAY_S"] = "0"
# NOT cosmetic: this one keeps the suite from stopping a real deployment.
#
# Settings fall back to the project's .env, and on a server that file says
# `CONTROL_PANEL_DEPLOYMENT=docker`. The panel's system actions then take the compose
# branch (control_panel.py, `system_action`) instead of the PowerShell one, and
# `docker compose` runs on the host against whatever stack is actually up. Running the
# suite next to a live deployment stopped api, worker, mcp-gateway and telegram-bot --
# measured 2026-09-10, OPEN_ITEMS 45.
#
# Environment variables outrank the dotenv file in pydantic-settings, so pinning it here
# closes the branch for every test at once. A test that wants the docker path asserts it
# the way test_control_panel.py already does: a fake settings object plus a mocked
# create_subprocess_exec, so nothing reaches a real daemon.
os.environ["CONTROL_PANEL_DEPLOYMENT"] = "native"

# Ownership is enforced in the repository and is deliberately *not* disabled by
# TESTING -- a filter that switches off under test proves nothing. So tests that are
# about pipeline behaviour rather than authorization run as this actor: it holds a
# real user id, so runs it creates get a real owner, and the admin role keeps those
# tests focused on what they were written for. Isolation itself is exercised
# end to end in tests/test_run_ownership.py.
TEST_ACTOR_ID = "01TESTACTOR".ljust(26, "0")


def acting_principal():
    from research_platform.auth import Principal

    return Principal.user(TEST_ACTOR_ID, "admin")


async def ensure_test_user(user_id: str = TEST_ACTOR_ID, role: str = "admin") -> str:
    """Insert a user row so API calls can present a credential that resolves to it.

    The API no longer has a TESTING bypass, so its tests authenticate the way real
    callers do: the service token plus an X-Actor-User header naming this row.
    """
    from research_platform.auth import hash_secret
    from research_platform.db import SessionLocal, UserRow, create_schema

    await create_schema()
    async with SessionLocal() as session:
        if await session.get(UserRow, user_id) is None:
            session.add(
                UserRow(
                    id=user_id,
                    email=f"{user_id.lower()}@example.test",
                    display_name="Test Actor",
                    password_hash=hash_secret("test-password"),
                    role=role,
                    is_active=True,
                    token_version=0,
                )
            )
            await session.commit()
    return user_id


def api_headers(user_id: str = TEST_ACTOR_ID) -> dict[str, str]:
    """Service-token credential acting for ``user_id`` -- what the panel sends."""
    from research_platform.config import get_settings

    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.service_token or settings.api_token}",
        "X-Actor-User": user_id,
    }


def pytest_sessionstart(session):
    Path(".pytest-research.db").unlink(missing_ok=True)


