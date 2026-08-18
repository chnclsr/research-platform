"""Per-user isolation: the guarantee that a user sees only their own research.

The structural test at the top is the important one. Behavioural tests prove the rule
holds for the methods that exist today; the structural test proves it will still hold
for the methods somebody adds next month, which is the failure this design is built
against.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from conftest import api_headers, ensure_test_user
from fastapi.testclient import TestClient

from research_platform.api import app
from research_platform.auth import Principal
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import (
    _UNGUARDED_RUN_METHODS,
    ActorRequired,
    Repository,
    RunAccessDenied,
)
from research_platform.schemas import ResearchProtocol

OWNER_ID = "01OWNER".ljust(26, "0")
INTRUDER_ID = "01INTRUDER".ljust(26, "0")
ADMIN_ID = "01ADMIN".ljust(26, "0")

owner = Principal.user(OWNER_ID)
intruder = Principal.user(INTRUDER_ID)
admin = Principal.user(ADMIN_ID, "admin")


def _protocol(title: str) -> ResearchProtocol:
    return ResearchProtocol(
        title=title,
        primary_question="Which evidence answers this ownership question in full?",
    )


async def _run_owned_by(actor: Principal, title: str = "Owned run") -> str:
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=actor)
        row = await repo.create_run(_protocol(title))
        return row.id


# --------------------------------------------------------------- structural guarantee


def test_every_run_scoped_method_is_guarded():
    """No method that takes a run_id may skip the ownership check.

    Read from the source rather than the class object so the assertion describes the
    code as written -- a method that lost its guard by being defined outside the
    metaclass's reach would still be caught here.
    """
    source = Path(inspect.getfile(Repository)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    repository_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Repository"
    )
    run_scoped = {
        node.name
        for node in repository_class.body
        if isinstance(node, ast.AsyncFunctionDef)
        and "run_id" in {arg.arg for arg in node.args.args + node.args.kwonlyargs}
    }
    assert run_scoped, "Repository should expose run-scoped methods"

    unguarded = []
    for name in sorted(run_scoped):
        if name in _UNGUARDED_RUN_METHODS:
            continue
        if not getattr(getattr(Repository, name), "__run_scoped__", False):
            unguarded.append(name)
    assert not unguarded, (
        "These Repository methods take a run_id but are not ownership-checked: "
        f"{unguarded}. Either let the metaclass wrap them or, if the method genuinely "
        "must not be checked, add it to _UNGUARDED_RUN_METHODS with a reason."
    )


def test_unguarded_allowlist_is_exactly_what_was_reviewed():
    """Opting a method out of the guard has to be a deliberate, visible change."""
    assert _UNGUARDED_RUN_METHODS == {"create_run", "_guard_run"}


# ----------------------------------------------------------------- reads and listings


@pytest.mark.asyncio
async def test_owner_reads_own_run_and_intruder_cannot():
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        assert await Repository(session, actor=owner).get_run(run_id) is not None
        with pytest.raises(RunAccessDenied):
            await Repository(session, actor=intruder).get_run(run_id)


@pytest.mark.asyncio
async def test_admin_reads_any_run():
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        assert await Repository(session, actor=admin).get_run(run_id) is not None


@pytest.mark.asyncio
async def test_missing_and_foreign_runs_are_indistinguishable():
    """Both raise the same error, so a caller cannot probe which run ids exist."""
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        repo = Repository(session, actor=intruder)
        with pytest.raises(RunAccessDenied):
            await repo.get_run(run_id)
        with pytest.raises(RunAccessDenied):
            await repo.get_run("01NOSUCHRUN".ljust(26, "0"))


@pytest.mark.asyncio
async def test_list_runs_shows_only_the_actors_own():
    mine = await _run_owned_by(owner, "Mine")
    theirs = await _run_owned_by(intruder, "Theirs")
    async with SessionLocal() as session:
        visible = {row.id for row in await Repository(session, actor=owner).list_runs(limit=200)}
        assert mine in visible
        assert theirs not in visible

        everything = {row.id for row in await Repository(session, actor=admin).list_runs(limit=200)}
        assert {mine, theirs} <= everything


@pytest.mark.asyncio
async def test_run_scoped_child_reads_are_guarded_too():
    """Sources, claims and artifacts hang off a run and must follow its ownership."""
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        repo = Repository(session, actor=intruder)
        for read in (repo.list_sources, repo.list_claims, repo.list_artifacts):
            with pytest.raises(RunAccessDenied):
                await read(run_id)


@pytest.mark.asyncio
async def test_writes_are_guarded_as_well_as_reads():
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        with pytest.raises(RunAccessDenied):
            await Repository(session, actor=intruder).update_run(run_id, status="cancelled")


# ------------------------------------------------------------------------- fail closed


@pytest.mark.asyncio
async def test_repository_without_an_actor_refuses_run_access():
    run_id = await _run_owned_by(owner)
    async with SessionLocal() as session:
        repo = Repository(session)
        with pytest.raises(ActorRequired):
            await repo.get_run(run_id)
        with pytest.raises(ActorRequired):
            await repo.list_runs()


@pytest.mark.asyncio
async def test_run_with_no_owner_is_visible_only_to_admins():
    """Rows predating ownership, or any path that forgets to set one, hide rather than leak."""
    await create_schema()
    async with SessionLocal() as session:
        row = await Repository(session, actor=owner).create_run(_protocol("Orphan"))
        run_id = row.id
        row.owner_id = None
        await session.commit()

    async with SessionLocal() as session:
        with pytest.raises(RunAccessDenied):
            await Repository(session, actor=owner).get_run(run_id)
        assert await Repository(session, actor=admin).get_run(run_id) is not None


@pytest.mark.asyncio
async def test_system_principal_cannot_create_an_unowned_run():
    """The worker owns nothing, so a run it creates would belong to nobody."""
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        with pytest.raises(ActorRequired):
            await repo.create_run(_protocol("Ownerless"))
        row = await repo.create_run(_protocol("Delegated"), owner_id=OWNER_ID)
        assert row.owner_id == OWNER_ID


@pytest.mark.asyncio
async def test_queue_wide_listing_is_restricted_to_admins():
    await create_schema()
    async with SessionLocal() as session:
        with pytest.raises(RunAccessDenied):
            await Repository(session, actor=owner).list_runs_by_statuses({"queued"})
        await Repository(session, actor=admin).list_runs_by_statuses({"queued"})


# ------------------------------------------------------------------------ corpus scope


@pytest.mark.asyncio
async def test_corpus_scope_follows_the_run_owner_not_the_caller():
    """The pipeline runs as the system principal; the corpus must still be the owner's.

    Scoping by the caller would hand every user's acquired text to every run, which is
    the same leak this feature exists to close -- just arriving through the back door.
    """
    run_id = await _run_owned_by(owner, "Corpus scope")
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        assert await repo._corpus_scope_owner(run_id, Principal.system()) == OWNER_ID


@pytest.mark.asyncio
async def test_corpus_scope_falls_back_to_the_caller_without_a_run():
    async with SessionLocal() as session:
        repo = Repository(session, actor=owner)
        assert await repo._corpus_scope_owner("", owner) == OWNER_ID
        # An admin can already see every run, so the corpus adds no new exposure.
        assert await repo._corpus_scope_owner("", admin) is None


# --------------------------------------------------------------------- over the wire


@pytest.mark.asyncio
async def test_api_reports_a_foreign_run_as_missing():
    """404 rather than 403: a 403 would confirm the run exists."""
    run_id = await _run_owned_by(owner)
    await ensure_test_user(INTRUDER_ID, role="user")
    with TestClient(app) as client:
        response = client.get(
            f"/v1/research-runs/{run_id}", headers=api_headers(INTRUDER_ID)
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_run_listing_is_scoped_to_the_caller():
    mine = await _run_owned_by(owner, "Wire mine")
    theirs = await _run_owned_by(intruder, "Wire theirs")
    await ensure_test_user(OWNER_ID, role="user")
    with TestClient(app) as client:
        listed = client.get(
            "/v1/research-runs?limit=200", headers=api_headers(OWNER_ID)
        ).json()
        ids = {run["id"] for run in listed}
        assert mine in ids
        assert theirs not in ids
