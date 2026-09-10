from __future__ import annotations

import os
from pathlib import Path

# FIRST, before anything can import the package: switch the dotenv source off.
#
# Settings otherwise read the project's real .env, so a suite run next to a live
# deployment inherits that deployment's configuration. That is not theoretical -- on the
# server `CONTROL_PANEL_DEPLOYMENT=docker` sent the panel's system action down the
# compose branch and the tests stopped api, worker, mcp-gateway and telegram-bot
# (OPEN_ITEMS 45). The same door was open for REDIS_URL and MINIO_ENDPOINT; those
# happened to be harmless only because their values name docker-network hosts that do
# not resolve from the host machine.
#
# With no dotenv, every setting is either pinned below or falls back to the model's own
# default, so the suite configures itself and cannot be steered by whatever machine it
# is running on.
os.environ["RESEARCH_ENV_FILE"] = ""

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./.pytest-research.db"
# Every external endpoint is pinned at a closed port, deliberately.
#
# Turning the dotenv off is not enough on its own: the model defaults are
# `redis://localhost:6379` and `localhost:9000`, and compose publishes MinIO on exactly
# 127.0.0.1:9000. So the switch that stopped tests inheriting a deployment's config
# would have handed them that deployment's object store instead. Tests mock the store
# they use; anything that forgets to should fail loudly on connect rather than quietly
# write into real buckets.
os.environ["REDIS_URL"] = "redis://127.0.0.1:64999/0"
os.environ["MINIO_ENDPOINT"] = "127.0.0.1:64998"
os.environ["TESTING"] = "true"
os.environ["LLM_PROVIDER"] = "deterministic"
os.environ["DOMAIN_DELAY_S"] = "0"
# Belt and braces. The model's own default is already "native", so with the dotenv off
# this line changes nothing today -- it is here so that the branch that runs
# `docker compose` against a live stack stays shut even if the dotenv switch above is
# ever weakened. A test that wants the docker path asserts it the way
# test_control_panel.py already does: a fake settings object plus a mocked
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


