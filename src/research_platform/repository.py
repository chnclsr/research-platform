from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse, urlsplit

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .config import get_settings
from .db import (
    ArtifactRow,
    CheckpointRow,
    ClaimRow,
    ConnectorSyncCursorRow,
    EventRow,
    EvidenceRow,
    FigureObservationRow,
    FrontierRow,
    PassageRow,
    ResearchRunRow,
    SourceRelationRow,
    SourceRow,
    SourceVersionRow,
    UserRow,
)
from .normalization import canonicalize_url
from .queueing import NORMAL, URGENT, normalize_priority
from .relevance import evidence_entailment
from .schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    CoverageMetrics,
    ExtractedClaim,
    Passage,
    ResearchProtocol,
    RunStatus,
    RunView,
    SourceFamily,
    new_id,
)
from .scholarly import candidate_dedupe_key, scholarly_identity, title_fingerprint

# PostgreSQL refuses a jsonb value once its elements exceed 256 MiB. Stop below that so
# the run fails with an actionable error instead of an opaque driver exception that also
# poisons the session.
CHECKPOINT_MAX_BYTES = get_settings().checkpoint_max_bytes

# Passages arrive one document at a time, so a batch this size holds a whole document in
# a single statement while keeping the bound parameter payload well inside what both
# drivers accept. research/bulk-insert measures where the gain comes from.
PASSAGE_UPSERT_BATCH = 1000
# A chunk is identified by (source_version_id, chunk_index). Everything else is content
# that re-ingesting the document is allowed to overwrite. ``id`` is deliberately absent:
# claims already reference the stored row, so re-chunking must not mint it a new one.
# These are physical column names, which is how ``excluded`` is keyed.
_PASSAGE_UPSERT_COLUMNS = (
    "section_path",
    "page_number",
    "start_char",
    "end_char",
    "text",
    "token_count",
    "content_hash",
    "embedding",
    "metadata",
)
_PASSAGE_UPSERT_BUILDERS = {
    "postgresql": postgresql_insert,
    "sqlite": sqlite_insert,
}


class ActorRequired(RuntimeError):
    """A run-scoped operation was attempted without saying who is asking.

    Fail-closed: constructing a ``Repository`` without an actor is not "full access",
    it is "no run access". Code paths with no network caller -- the worker, the
    pipeline, cron jobs -- pass ``Principal.system()`` explicitly.
    """


class RunAccessDenied(RuntimeError):
    """The actor does not own this run and is not an admin.

    Callers facing the network translate this to 404, never 403: a 403 confirms the
    run exists, which tells one user something about another user's data.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id} is not accessible to this actor")
        self.run_id = run_id


# Methods that take a ``run_id`` but must not be ownership-checked, each for a reason
# that had to be argued rather than assumed. Anything not listed here is guarded
# automatically by _OwnershipEnforced below.
_UNGUARDED_RUN_METHODS = {
    # Writes ownership itself; there is no run to check yet.
    "create_run",
    # The guard's own lookup -- checking access from inside it would not terminate.
    "_guard_run",
}


def _takes_run_id(candidate: Any) -> bool:
    """True for coroutine functions with a ``run_id`` parameter."""
    if not inspect.iscoroutinefunction(candidate):
        return False
    try:
        return "run_id" in inspect.signature(candidate).parameters
    except (TypeError, ValueError):
        return False


def _run_scoped(method):
    """Wrap a coroutine method so its ``run_id`` is ownership-checked first."""
    signature = inspect.signature(method)

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        bound = signature.bind_partial(self, *args, **kwargs)
        run_id = bound.arguments.get("run_id")
        if run_id is not None:
            await self._guard_run(run_id)
        return await method(self, *args, **kwargs)

    wrapper.__run_scoped__ = True
    return wrapper


class _OwnershipEnforced(type):
    """Applies the ownership guard to every run-scoped method at class creation.

    Guarding by hand meant 25 identical two-line preambles, and the failure mode of
    that approach is silent: method 26 gets added without one and reads another user's
    data with no error anywhere. Here the rule is applied by construction -- a new
    method that takes a ``run_id`` is guarded before anyone runs a test, and opting out
    requires naming it in :data:`_UNGUARDED_RUN_METHODS`, which is itself asserted
    against an expected set in ``tests/test_run_ownership.py``.
    """

    def __new__(mcls, name, bases, namespace, **kwargs):
        for attribute, value in list(namespace.items()):
            if attribute in _UNGUARDED_RUN_METHODS:
                continue
            if _takes_run_id(value):
                namespace[attribute] = _run_scoped(value)
        return super().__new__(mcls, name, bases, namespace, **kwargs)


# The states in which a run is still holding, or waiting for, the single GPU. Kept here
# rather than imported from the control panel because the repository must not depend on a
# presentation module; the panel's ACTIVE_STATUSES is asserted equal to this in tests.
ACTIVE_RUN_STATUSES = frozenset(
    {
        RunStatus.QUEUED.value,
        RunStatus.RUNNING.value,
        RunStatus.PAUSED.value,
        RunStatus.AWAITING_INPUT.value,
        RunStatus.CANCEL_REQUESTED.value,
    }
)


@dataclass(frozen=True)
class TeamActivity:
    """Somebody else's in-flight run, reduced to what explains the wait.

    Every field here was argued for individually. That is the point of the type: a
    redacted view produced by deleting fields from a full row is one forgotten field --
    or one new column on ``research_runs`` -- away from leaking, whereas this cannot
    carry what it has no place for.

    There is deliberately **no run id**. Without one the panel cannot make the row
    clickable by accident, and a caller cannot turn the listing into a set of ids to
    probe ``/api/runs/<id>`` with. ``owner_name`` is None for a run whose owner row is
    missing; the label for that case belongs to the presentation layer.
    """

    owner_name: str | None
    status: str
    current_stage: str
    queue_position: int | None
    elapsed_seconds: float
    # Deliberately widens the redaction this type was built for. Without it a normal-band
    # run sits at position 2 with no explanation of why the number never moves, which is
    # the same misreading -- "the platform is broken rather than busy" -- that made this
    # cross-owner view necessary in the first place. It carries no identity.
    priority: str = NORMAL


class CheckpointTooLarge(RuntimeError):
    """Raised when a pipeline state is too large to persist as a checkpoint."""


def checkpoint_payload(state: dict[str, Any]) -> dict[str, Any]:
    """
    Return the state as it should be persisted, without raw document snapshots.

    ACQUIRE puts every fetched document into the graph state and, for PDFs, raw_content
    is the entire binary base64-encoded. Persisting that pushes the checkpoint past
    PostgreSQL's jsonb ceiling.

    The caller's state is never mutated: NORMALIZE still reads raw_content from memory to
    write the MinIO snapshot and source_versions, so a normal run keeps every raw file.
    Only a run resumed from this checkpoint sees the field already emptied.
    """
    documents = state.get("documents")
    if not isinstance(documents, list):
        return state
    trimmed: list[Any] = []
    for payload in documents:
        if isinstance(payload, dict) and payload.get("raw_content"):
            payload = {**payload, "raw_content": ""}
        trimmed.append(payload)
    return {**state, "documents": trimmed}


def _assert_checkpoint_fits(run_id: str, stage: str, state: dict[str, Any]) -> None:
    size = len(json.dumps(state, ensure_ascii=False, default=str).encode("utf-8"))
    if size <= CHECKPOINT_MAX_BYTES:
        return
    largest = sorted(
        (
            (len(json.dumps(value, ensure_ascii=False, default=str)), key)
            for key, value in state.items()
        ),
        reverse=True,
    )[:3]
    raise CheckpointTooLarge(
        f"{stage} checkpoint for run {run_id} is {size / 1048576:.0f} MiB, over the "
        f"{CHECKPOINT_MAX_BYTES / 1048576:.0f} MiB limit. Largest state keys: "
        + ", ".join(f"{key} {value / 1048576:.0f} MiB" for value, key in largest)
    )


class Repository(metaclass=_OwnershipEnforced):
    """Data access for research runs, scoped to whoever is asking.

    ``actor`` is the enforcement point for per-user isolation. It lives here rather
    than in the route handlers because the control panel reads this data two ways --
    over the API and straight from the database -- and a filter applied at one of
    those doors leaves the other one open.
    """

    def __init__(self, session: AsyncSession, *, actor: Principal | None = None):
        self.session = session
        self.actor = actor

    def require_actor(self) -> Principal:
        if self.actor is None:
            raise ActorRequired(
                "This repository has no actor. Pass actor=Principal.system() for "
                "worker and cron paths, or the request's principal for network paths."
            )
        return self.actor

    async def _guard_run(self, run_id: str) -> None:
        """Raise unless the actor owns this run or is an admin.

        A run with no owner is reachable only by admins. That matters for rows that
        predate ownership and for any future path that forgets to set one: the
        omission hides data instead of exposing it.
        """
        actor = self.require_actor()
        if actor.is_admin:
            return
        owner_id = await self.session.scalar(
            select(ResearchRunRow.owner_id).where(ResearchRunRow.id == run_id)
        )
        # A missing run and a foreign run are the same answer on purpose; telling them
        # apart would let a caller probe which run ids exist.
        if owner_id is None or owner_id != actor.user_id:
            raise RunAccessDenied(run_id)

    async def create_run(
        self,
        protocol: ResearchProtocol,
        *,
        owner_id: str | None = None,
        priority: str = NORMAL,
        invocation_source: str = "api",
    ) -> ResearchRunRow:
        """Create a run owned by ``owner_id``, defaulting to the acting user.

        The system principal has no user id, so a job with no human caller (the Zotero
        sync) must name an owner explicitly -- otherwise the run would be created
        unowned and become invisible to everyone but an admin.
        """
        actor = self.require_actor()
        resolved_owner = owner_id or actor.user_id
        if resolved_owner is None:
            raise ActorRequired(
                "create_run needs an owner: the system principal owns nothing, so "
                "pass owner_id explicitly (see ZOTERO_SYNC_OWNER_EMAIL)."
            )
        now = datetime.now(timezone.utc)
        row = ResearchRunRow(
            id=new_id(),
            owner_id=resolved_owner,
            status=RunStatus.QUEUED.value,
            priority=normalize_priority(priority),
            current_stage="INIT",
            protocol=protocol.model_dump(mode="json"),
            state={"invocation_source": invocation_source},
            coverage=CoverageMetrics().model_dump(),
            interaction=None,
            hitl_history=[],
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_run(self, run_id: str, *, lock: bool = False) -> ResearchRunRow | None:
        stmt = (
            select(ResearchRunRow)
            .where(ResearchRunRow.id == run_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_runs_by_statuses(self, statuses: set[str]) -> list[ResearchRunRow]:
        """Every run in the given states, regardless of owner -- system paths only.

        Used by startup reconciliation and the worker, which have to see the whole
        queue to do their job. Restricted to admin/system so it cannot become a
        listing endpoint by accident.
        """
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        if not statuses:
            return []
        rows = await self.session.scalars(
            select(ResearchRunRow)
            .where(ResearchRunRow.status.in_(statuses))
            .order_by(ResearchRunRow.created_at)
        )
        return list(rows)

    async def list_failed_runs_since(self, cutoff: datetime) -> list[ResearchRunRow]:
        """Runs that failed recently, for the notice the bot sends their owners.

        Bounded on purpose: `list_runs_by_statuses` would return every run that ever failed,
        and the notifier walks this list on each poll cycle. The cutoff is also what keeps
        the feature from replaying old failures the first time it runs.

        Carries the same admin guard as `list_runs_by_statuses` -- system paths only.
        """
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        rows = await self.session.scalars(
            select(ResearchRunRow)
            .where(
                ResearchRunRow.status == RunStatus.FAILED.value,
                ResearchRunRow.updated_at >= cutoff,
            )
            .order_by(ResearchRunRow.updated_at)
        )
        return list(rows)

    async def list_runs_cancelled_by_event_since(
        self, cutoff: datetime, event_type: str
    ) -> list[ResearchRunRow]:
        """Recently cancelled runs carrying `event_type`, for the notice their owners get.

        Cancellation is normally the user's own doing and stays silent on purpose. A
        cancellation the platform decided is a different thing wearing the same status, and
        the event is what tells them apart -- so the caller names the event rather than
        this widening to every cancelled run.

        Carries the same admin guard as the other whole-queue reads.
        """
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        # A membership test rather than a join with DISTINCT: this table carries `protocol`
        # and `state`, the migration created them as plain `json`, and PostgreSQL has no
        # equality operator for that type -- so DISTINCT over the row raised
        # UndefinedFunctionError in production while passing on SQLite in the tests.
        rows = await self.session.scalars(
            select(ResearchRunRow)
            .where(
                ResearchRunRow.status == RunStatus.CANCELLED.value,
                ResearchRunRow.updated_at >= cutoff,
                ResearchRunRow.id.in_(
                    select(EventRow.run_id).where(EventRow.event_type == event_type)
                ),
            )
            .order_by(ResearchRunRow.updated_at)
        )
        return list(rows)

    async def running_normal_run(self) -> ResearchRunRow | None:
        """The normal-priority run currently holding the worker, if there is one.

        Scheduling is a platform-level decision, so like the other whole-queue reads this
        is admin/system only -- it deliberately crosses the ownership boundary, and the
        caller that acts on it is the scheduler, never a request handler acting for a user.
        """
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        return await self.session.scalar(
            select(ResearchRunRow)
            .where(
                ResearchRunRow.status == RunStatus.RUNNING.value,
                ResearchRunRow.priority == NORMAL,
            )
            .order_by(ResearchRunRow.created_at)
        )

    async def running_run_count(self) -> int:
        """How many runs hold a slot right now, across every owner."""
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        rows = await self.session.scalars(
            select(ResearchRunRow.id).where(ResearchRunRow.status == RunStatus.RUNNING.value)
        )
        return len(list(rows))

    async def urgent_work_pending(self) -> bool:
        """Whether an urgent run is queued or running -- the gate on resuming a preempted one."""
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        found = await self.session.scalar(
            select(ResearchRunRow.id)
            .where(
                ResearchRunRow.priority == URGENT,
                ResearchRunRow.status.in_(
                    {RunStatus.QUEUED.value, RunStatus.RUNNING.value}
                ),
            )
            .limit(1)
        )
        return found is not None

    async def preempted_runs(self) -> list[ResearchRunRow]:
        """Runs the scheduler paused, oldest first. Never ones their owner paused."""
        actor = self.require_actor()
        if not actor.is_admin:
            raise RunAccessDenied("*")
        rows = await self.session.scalars(
            select(ResearchRunRow)
            .where(
                ResearchRunRow.status == RunStatus.PAUSED.value,
                ResearchRunRow.preempted_at.is_not(None),
            )
            .order_by(ResearchRunRow.preempted_at)
        )
        return list(rows)

    async def list_runs(self, *, limit: int = 50) -> list[ResearchRunRow]:
        """Runs visible to the actor: their own, or all of them for an admin."""
        actor = self.require_actor()
        stmt = select(ResearchRunRow).order_by(ResearchRunRow.created_at.desc())
        if not actor.is_admin:
            stmt = stmt.where(ResearchRunRow.owner_id == actor.user_id)
        rows = await self.session.scalars(stmt.limit(min(max(1, limit), 200)))
        return list(rows)

    async def list_team_activity(
        self, *, queue_positions: Mapping[str, int] | None = None
    ) -> list[TeamActivity]:
        """Other people's in-flight runs, redacted to status and stage.

        This is the one read that crosses the ownership boundary on purpose. Isolation
        without it produces a misleading panel: on a single-GPU machine the person whose
        run sits in ``queued`` sees a still row and an empty table, and concludes the
        platform is broken rather than busy. What leaks is the *existence* of work and
        who owns it -- never a title, a question, a count or an id.

        Returns nothing for an admin: their own table already lists every run in full, so
        a second redacted copy of the same rows would only confuse.
        """
        actor = self.require_actor()
        if actor.is_admin:
            return []
        positions = queue_positions or {}
        rows = await self.session.execute(
            select(
                ResearchRunRow.id,
                ResearchRunRow.status,
                ResearchRunRow.current_stage,
                ResearchRunRow.created_at,
                ResearchRunRow.updated_at,
                UserRow.display_name,
                ResearchRunRow.priority,
            )
            .outerjoin(UserRow, UserRow.id == ResearchRunRow.owner_id)
            .where(
                ResearchRunRow.status.in_(ACTIVE_RUN_STATUSES),
                # An unowned run is included on purpose. It still occupies the GPU, and
                # hiding it would understate the queue; it carries no identity to leak.
                # The NULL has to be spelled out -- ``owner_id != :id`` is NULL, not true,
                # for a NULL owner, so the plain comparison would drop exactly those rows.
                or_(
                    ResearchRunRow.owner_id.is_(None),
                    ResearchRunRow.owner_id != actor.user_id,
                ),
            )
            .order_by(ResearchRunRow.created_at)
        )
        activity = []
        for run_id, status, stage, created_at, updated_at, display_name, priority in rows:
            elapsed = (
                max(0.0, (updated_at - created_at).total_seconds())
                if created_at and updated_at
                else 0.0
            )
            activity.append(
                TeamActivity(
                    owner_name=display_name,
                    status=status,
                    current_stage=stage or "INIT",
                    # Resolved in here so the run id never crosses the return boundary.
                    queue_position=positions.get(run_id),
                    elapsed_seconds=round(elapsed, 2),
                    priority=normalize_priority(priority),
                )
            )
        return activity

    async def apply_source_domain_review(
        self,
        run_id: str,
        included_domains: set[str],
        excluded_domains: set[str],
    ) -> None:
        """Persist HITL domain decisions without deleting raw provenance."""
        sources = await self.list_sources(run_id)
        for source in sources:
            domain = (urlparse(source.url).hostname or "").lower()
            metadata = dict(source.metadata_json or {})
            if domain in included_domains:
                metadata["hitl_source_decision"] = "include"
                metadata["excluded_by_hitl"] = False
            elif domain in excluded_domains:
                metadata["hitl_source_decision"] = "exclude"
                metadata["excluded_by_hitl"] = True
            else:
                metadata.setdefault("hitl_source_decision", "ai_recommendation")
            source.metadata_json = metadata
        await self.session.commit()

    async def update_run(self, run_id: str, **values: Any) -> ResearchRunRow:
        row = await self.get_run(run_id, lock=True)
        if row is None:
            raise KeyError(run_id)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return row

    def run_view(self, row: ResearchRunRow) -> RunView:
        return RunView(
            id=row.id,
            status=RunStatus(row.status),
            current_stage=row.current_stage,
            priority=normalize_priority(row.priority),
            preempted_at=row.preempted_at,
            protocol=ResearchProtocol.model_validate(row.protocol),
            round_number=row.round_number,
            sources_count=row.sources_count,
            claims_count=row.claims_count,
            coverage=CoverageMetrics.model_validate(row.coverage or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
            error=row.error,
            hitl_config=ResearchProtocol.model_validate(row.protocol).hitl,
            interaction=row.interaction,
            hitl_history=row.hitl_history or [],
        )

    async def checkpoint(self, run_id: str, stage: str, state: dict[str, Any]) -> None:
        state = checkpoint_payload(state)
        # Check before touching the session: a driver-side size error aborts the
        # transaction and every later write on it, including the failure event.
        _assert_checkpoint_fits(run_id, stage, state)
        existing = await self.session.scalar(
            select(CheckpointRow).where(
                CheckpointRow.run_id == run_id, CheckpointRow.stage == stage
            )
        )
        if existing:
            existing.state = state
            existing.created_at = datetime.now(timezone.utc)
        else:
            self.session.add(CheckpointRow(run_id=run_id, stage=stage, state=state))
        await self.update_run(run_id, current_stage=stage, state=state)

    async def latest_checkpoint(self, run_id: str) -> CheckpointRow | None:
        return await self.session.scalar(
            select(CheckpointRow)
            .where(CheckpointRow.run_id == run_id)
            .order_by(CheckpointRow.created_at.desc())
            .limit(1)
        )

    async def event(
        self, run_id: str, event_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.session.add(EventRow(run_id=run_id, event_type=event_type, payload=payload or {}))
        await self.session.commit()

    async def events_after(self, run_id: str, after_id: int = 0) -> list[EventRow]:
        rows = await self.session.scalars(
            select(EventRow)
            .where(EventRow.run_id == run_id, EventRow.id > after_id)
            .order_by(EventRow.id)
            .limit(200)
        )
        return list(rows)

    async def events_by_types(self, run_id: str, event_types: set[str]) -> list[EventRow]:
        """Read a run's complete audit subset without the streaming endpoint's page cap."""
        if not event_types:
            return []
        rows = await self.session.scalars(
            select(EventRow)
            .where(EventRow.run_id == run_id, EventRow.event_type.in_(event_types))
            .order_by(EventRow.id)
        )
        return list(rows)

    async def save_document(
        self, run_id: str, document: AcquiredDocument
    ) -> tuple[SourceRow, SourceVersionRow]:
        c = document.candidate
        persisted_metadata = dict(c.metadata)
        persisted_metadata.pop("inline_fulltext", None)
        if c.published_at is not None:
            persisted_metadata["published_at"] = c.published_at.isoformat()
            persisted_metadata.setdefault("publication_year", c.published_at.year)
        canonical = document.canonical_url or canonicalize_url(str(c.url))
        dedupe_key = candidate_dedupe_key(c)[:512]
        source = await self.session.scalar(
            select(SourceRow).where(SourceRow.run_id == run_id, SourceRow.dedupe_key == dedupe_key)
        )
        if source is None:
            candidates = list(
                await self.session.scalars(
                    select(SourceRow).where(SourceRow.run_id == run_id).limit(500)
                )
            )
            normalized_title = " ".join(c.title.lower().split())
            identity = scholarly_identity(c.metadata, c.persistent_id)
            publication_year = c.metadata.get("publication_year") or c.metadata.get("year")
            fingerprint = title_fingerprint(c.title, c.authors, publication_year)
            source = next(
                (
                    row
                    for row in candidates
                    if (
                        SequenceMatcher(
                            None, normalized_title, " ".join(row.title.lower().split())
                        ).ratio()
                        >= 0.96
                        and (
                            canonicalize_url(row.url) == canonical
                            or row.metadata_json.get("title_fingerprint") == fingerprint
                        )
                    )
                ),
                None,
            )
        if source is None:
            identity = scholarly_identity(c.metadata, c.persistent_id)
            publication_year = c.metadata.get("publication_year") or c.metadata.get("year")
            source = SourceRow(
                id=new_id(),
                run_id=run_id,
                dedupe_key=dedupe_key,
                family=c.family.value,
                connector_id=c.connector_id,
                title=c.title,
                url=canonical,
                persistent_id=identity.doi or c.persistent_id,
                metadata_json={
                    **persisted_metadata,
                    "scholarly_identity": identity.model_dump(exclude_none=True),
                    "title_fingerprint": title_fingerprint(c.title, c.authors, publication_year),
                },
            )
            self.session.add(source)
            await self.session.flush()
        else:
            updated_metadata = dict(source.metadata_json or {})
            snapshots = dict(updated_metadata.get("provider_snapshots") or {})
            snapshots.update(persisted_metadata.get("provider_snapshots", {}))
            updated_metadata["provider_snapshots"] = snapshots
            discovered_by = list(updated_metadata.get("discovered_by_connectors") or [])
            for connector_id in persisted_metadata.get(
                "discovered_by_connectors",
                [c.connector_id],
            ):
                if connector_id not in discovered_by:
                    discovered_by.append(connector_id)
            updated_metadata["discovered_by_connectors"] = discovered_by
            branches = list(updated_metadata.get("query_branches") or [])
            for branch in persisted_metadata.get("query_branches", []):
                if branch not in branches:
                    branches.append(branch)
            updated_metadata["query_branches"] = branches
            alternate_locations = list(updated_metadata.get("alternate_locations") or [])
            if str(c.url) not in alternate_locations:
                alternate_locations.append(str(c.url))
            updated_metadata["alternate_locations"] = alternate_locations
            source.metadata_json = updated_metadata
        version = await self.session.scalar(
            select(SourceVersionRow).where(
                SourceVersionRow.source_id == source.id,
                SourceVersionRow.content_hash == document.content_hash,
            )
        )
        if version is None:
            version = SourceVersionRow(
                id=new_id(),
                source_id=source.id,
                content_hash=document.content_hash,
                acquisition_method=document.acquisition_method,
                access_status=document.access_status,
                content=document.content,
                raw_content=document.raw_content,
                retrieved_at=document.retrieved_at,
                provenance={
                    "url": str(c.url),
                    "canonical_url": canonical,
                    "final_url": document.final_url,
                    "redirect_chain": document.redirect_chain,
                    "content_type": document.content_type,
                    "document_type": document.document_type,
                    "language": document.language,
                    "connector": c.connector_id,
                    "raw_snapshot_key": c.metadata.get("raw_snapshot_key"),
                    "strategies_tried": document.strategies_tried,
                    # Which parser produced `content`, so an audit can tell whether a run
                    # used the deterministic pick or a ParserSelection override.
                    "parser_id": document.parser_id,
                    # Which engine handled which page, for parsers that mix them.
                    "parse_provenance": document.parse_provenance,
                    "tables": document.tables,
                    "code_blocks": document.code_blocks,
                    "error": document.error,
                },
            )
            self.session.add(version)
        else:
            # Same text, but not necessarily the same route to it: a parser can be
            # reconfigured, an engine can drop out or be added, and the extracted
            # text still come out byte-identical. Reusing the version is right --
            # content_hash is what identifies it -- but leaving the old parse
            # provenance in place would have an audit read the wrong parser, engine
            # and threshold versions for this fetch. Only the parse-side keys are
            # refreshed; the rest describes the original fetch and still holds.
            refreshed = dict(version.provenance or {})
            refreshed["parser_id"] = document.parser_id
            refreshed["parse_provenance"] = document.parse_provenance
            version.provenance = refreshed
        await self.save_source_relations(
            run_id, source.id, c.metadata.get("citation_relations", [])
        )
        await self.session.commit()
        return source, version

    async def save_source_relations(
        self,
        run_id: str,
        source_id: str,
        relations: list[dict[str, Any]],
    ) -> None:
        for relation in relations:
            target = str(relation.get("target_persistent_id") or "").strip()
            if not target:
                continue
            relation_type = str(relation.get("relation_type") or "").strip()
            provider = str(relation.get("provider") or "unknown")
            existing = await self.session.scalar(
                select(SourceRelationRow).where(
                    SourceRelationRow.source_id == source_id,
                    SourceRelationRow.target_persistent_id == target,
                    SourceRelationRow.relation_type == relation_type,
                    SourceRelationRow.provider == provider,
                )
            )
            if existing is None:
                self.session.add(
                    SourceRelationRow(
                        id=new_id(),
                        run_id=run_id,
                        source_id=source_id,
                        target_persistent_id=target,
                        relation_type=relation_type,
                        provider=provider,
                        metadata_json=relation.get("metadata") or {},
                    )
                )

    async def list_source_relations(self, run_id: str) -> list[SourceRelationRow]:
        return list(
            await self.session.scalars(
                select(SourceRelationRow).where(SourceRelationRow.run_id == run_id)
            )
        )

    async def get_sync_cursor(
        self, connector_id: str, scope_key: str
    ) -> ConnectorSyncCursorRow | None:
        return await self.session.scalar(
            select(ConnectorSyncCursorRow).where(
                ConnectorSyncCursorRow.connector_id == connector_id,
                ConnectorSyncCursorRow.scope_key == scope_key,
            )
        )

    async def set_sync_cursor(
        self,
        connector_id: str,
        scope_key: str,
        cursor_value: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorSyncCursorRow:
        row = await self.get_sync_cursor(connector_id, scope_key)
        if row is None:
            row = ConnectorSyncCursorRow(
                id=new_id(),
                connector_id=connector_id,
                scope_key=scope_key,
                cursor_value=cursor_value,
                metadata_json=metadata or {},
            )
            self.session.add(row)
        else:
            row.cursor_value = cursor_value
            row.metadata_json = metadata or row.metadata_json
        await self.session.commit()
        return row

    async def list_sources(self, run_id: str) -> list[SourceRow]:
        return list(await self.session.scalars(select(SourceRow).where(SourceRow.run_id == run_id)))

    async def filter_novel_candidates(
        self,
        run_id: str,
        candidates: list[ConnectorCandidate],
    ) -> tuple[list[ConnectorCandidate], list[dict[str, str]]]:
        existing = await self.list_sources(run_id)
        by_dedupe_key = {source.dedupe_key: source for source in existing}
        by_url = {canonicalize_url(source.url): source for source in existing}
        by_persistent_id = {
            source.persistent_id.lower(): source for source in existing if source.persistent_id
        }
        novel: list[ConnectorCandidate] = []
        rejected: list[dict[str, str]] = []
        enriched = False
        for candidate in candidates:
            key = candidate_dedupe_key(candidate)[:512]
            canonical = canonicalize_url(str(candidate.url))
            persistent = (candidate.persistent_id or "").lower()
            source = (
                by_dedupe_key.get(key)
                or by_url.get(canonical)
                or (by_persistent_id.get(persistent) if persistent else None)
            )
            if source is not None:
                metadata = dict(source.metadata_json or {})
                branches = list(metadata.get("query_branches") or [])
                for branch in candidate.metadata.get("query_branches", []):
                    if branch not in branches:
                        branches.append(branch)
                        enriched = True
                metadata["query_branches"] = branches
                if (
                    candidate.metadata.get("authority") == "official"
                    and metadata.get("authority") != "official"
                ):
                    metadata["authority"] = "official"
                    enriched = True
                if enriched:
                    source.metadata_json = metadata
                rejected.append({"url": str(candidate.url), "reason": "existing_source"})
                continue
            novel.append(candidate)
        if enriched:
            await self.session.commit()
        return novel, rejected

    async def list_source_versions(self, run_id: str) -> list[tuple[SourceRow, SourceVersionRow]]:
        rows = await self.session.execute(
            select(SourceRow, SourceVersionRow)
            .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
            .where(SourceRow.run_id == run_id)
        )
        return list(rows.tuples())

    async def list_unchunked_versions(
        self, run_id: str
    ) -> list[tuple[SourceRow, SourceVersionRow]]:
        """Acquired versions this run never turned into passages.

        Normally empty: CHUNK_INDEX chunks whatever the round just acquired. It fills up when
        a run is requeued mid-flight -- the resumed pass acquires nothing new, so the node
        that reads only the round's new documents chunks nothing, and a corpus that is
        sitting in the database becomes invisible to the rest of the pipeline.

        A membership test rather than an outer join with DISTINCT: `research_runs` is not in
        this query, but the same rule earned its place the hard way (open item #26) and the
        EXISTS form is the cheaper plan here anyway.
        """
        rows = await self.session.execute(
            select(SourceRow, SourceVersionRow)
            .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
            .where(
                SourceRow.run_id == run_id,
                SourceVersionRow.id.not_in(
                    select(PassageRow.source_version_id).distinct()
                ),
            )
            .order_by(SourceVersionRow.id)
        )
        return list(rows.tuples())

    async def has_evidence(self, run_id: str) -> bool:
        """Whether this run has extracted any evidence yet.

        The signal that separates a run still working on its first evidence pass from one
        whose later round simply found nothing new. Only the first may fall back to the whole
        corpus; doing it in a later round would re-extract passages already mined.
        """
        found = await self.session.scalar(
            select(EvidenceRow.id)
            .join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
            .where(ClaimRow.run_id == run_id)
            .limit(1)
        )
        return found is not None

    @staticmethod
    def _passage_values(passage: Passage) -> dict[str, Any]:
        return {
            "id": passage.id,
            "source_version_id": passage.source_version_id,
            "chunk_index": passage.chunk_index,
            "section_path": passage.section_path,
            "page_number": passage.page_number,
            "start_char": passage.start_char,
            "end_char": passage.end_char,
            "text": passage.text,
            "token_count": passage.token_count,
            "content_hash": passage.content_hash,
            "embedding": passage.embedding,
            "metadata_json": {
                "retrieval_score": passage.retrieval_score,
                "matched_questions": passage.matched_questions,
                "language": passage.language,
                "document_type": passage.document_type,
            },
        }

    @staticmethod
    def _passage_upsert_rows(passages: list[Passage]) -> list[dict[str, Any]]:
        """Collapse repeated chunks and order the batch by the conflict key.

        Two rows with the same identity in one statement make PostgreSQL reject the
        whole batch, so they are merged here instead. The merge keeps the first id and
        the last content, which is what the previous row-by-row loop produced: its
        SELECT found the row it had just written and updated it in place.

        Sorting is for concurrency, not tidiness. Upsert takes row locks, so two writers
        saving overlapping chunks in different orders could deadlock; a fixed order means
        they always take those locks in the same sequence.
        """
        by_chunk: dict[tuple[str, int], dict[str, Any]] = {}
        for passage in passages:
            key = (passage.source_version_id, passage.chunk_index)
            values = Repository._passage_values(passage)
            existing = by_chunk.get(key)
            if existing is not None:
                values["id"] = existing["id"]
            by_chunk[key] = values
        return [by_chunk[key] for key in sorted(by_chunk)]

    async def save_passages(self, passages: list[Passage]) -> None:
        """Write passages, overwriting any chunk this source version already has.

        One statement per batch rather than a lookup and a write per passage. The old
        loop cost 2N round trips because autoflush had to send each pending write before
        the next existence check could run.

        Every batch shares the caller's transaction and the single commit at the end, so
        a failure part way through leaves none of them applied. The failure is raised
        rather than rolled back here: this method does not own the session, and the
        caller's transaction may hold work of its own that predates this call.
        """
        if not passages:
            # Commit anyway. The previous implementation ended in a commit whatever it
            # was handed, and callers lean on that: zotero_sync only flushes its
            # document row and lets this call make it durable, so an item that chunks
            # to nothing would otherwise leave that write hanging in the transaction.
            await self.session.commit()
            return
        dialect = self.session.get_bind().dialect.name
        builder = _PASSAGE_UPSERT_BUILDERS.get(dialect)
        if builder is None:
            raise RuntimeError(
                f"save_passages needs ON CONFLICT support; {dialect!r} is not one of "
                f"{sorted(_PASSAGE_UPSERT_BUILDERS)}."
            )
        statement = builder(PassageRow)
        upsert = statement.on_conflict_do_update(
            index_elements=[PassageRow.source_version_id, PassageRow.chunk_index],
            set_={name: statement.excluded[name] for name in _PASSAGE_UPSERT_COLUMNS},
        )
        rows = self._passage_upsert_rows(passages)
        for start in range(0, len(rows), PASSAGE_UPSERT_BATCH):
            await self.session.execute(upsert, rows[start : start + PASSAGE_UPSERT_BATCH])
        await self.session.commit()
        # A core-level write leaves any PassageRow already in the identity map holding
        # its pre-write state, and this session is deliberately configured not to expire
        # on commit. The pipeline reads a run's passages, writes retrieval metadata back
        # through here, and lists them again on the same session, so those instances are
        # dropped or that second read silently returns what was there before.
        for instance in list(self.session.identity_map.values()):
            if isinstance(instance, PassageRow):
                self.session.expire(instance)

    async def list_passages(
        self,
        run_id: str,
        source_version_ids: list[str] | None = None,
    ) -> list[Passage]:
        stmt = (
            select(PassageRow)
            .join(SourceVersionRow, SourceVersionRow.id == PassageRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(SourceRow.run_id == run_id)
            .order_by(PassageRow.source_version_id, PassageRow.chunk_index)
        )
        if source_version_ids is not None:
            if not source_version_ids:
                return []
            stmt = stmt.where(PassageRow.source_version_id.in_(source_version_ids))
        rows = list(await self.session.scalars(stmt))
        return [
            Passage(
                id=row.id,
                source_version_id=row.source_version_id,
                chunk_index=row.chunk_index,
                section_path=row.section_path,
                page_number=row.page_number,
                start_char=row.start_char,
                end_char=row.end_char,
                text=row.text,
                token_count=row.token_count,
                content_hash=row.content_hash,
                embedding=row.embedding or [],
                language=(row.metadata_json or {}).get("language", "und"),
                document_type=(row.metadata_json or {}).get("document_type", "text"),
                retrieval_score=(row.metadata_json or {}).get("retrieval_score", 0.0),
                matched_questions=(row.metadata_json or {}).get("matched_questions", []),
            )
            for row in rows
        ]

    async def list_corpus_passages(self, exclude_run_id: str, limit: int = 3000) -> list[Passage]:
        """Passages from *other* runs, used to seed a new run from past work.

        This is the one deliberately cross-run read in the repository, which makes it
        the one place per-user isolation could leak sideways: without scoping, a user's
        new run would be fed text acquired under someone else's account. With
        ``CORPUS_SCOPE=owner`` (the default) the pool stays inside the actor's own
        history; ``global`` restores the shared pool as a documented choice.
        """
        actor = self.require_actor()
        stmt = (
            select(PassageRow)
            .join(SourceVersionRow, SourceVersionRow.id == PassageRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(SourceRow.run_id != exclude_run_id)
        )
        scope_owner = await self._corpus_scope_owner(exclude_run_id, actor)
        if scope_owner is not None:
            stmt = stmt.join(ResearchRunRow, ResearchRunRow.id == SourceRow.run_id).where(
                ResearchRunRow.owner_id == scope_owner
            )
        rows = list(
            await self.session.scalars(
                stmt.order_by(SourceVersionRow.retrieved_at.desc()).limit(limit)
            )
        )
        return [
            Passage(
                id=row.id,
                source_version_id=row.source_version_id,
                chunk_index=row.chunk_index,
                section_path=row.section_path,
                page_number=row.page_number,
                start_char=row.start_char,
                end_char=row.end_char,
                text=row.text,
                token_count=row.token_count,
                content_hash=row.content_hash,
                embedding=row.embedding or [],
                language=(row.metadata_json or {}).get("language", "und"),
                document_type=(row.metadata_json or {}).get("document_type", "text"),
            )
            for row in rows
        ]

    async def _corpus_scope_owner(self, exclude_run_id: str, actor: Principal) -> str | None:
        """Whose corpus this read may draw on, or None for the unrestricted pool.

        The scope follows the *run being built*, not the caller. That distinction
        matters: the pipeline executes runs under the system principal, so scoping by
        the caller would hand every user's text to every run. Scoping by the run's
        owner keeps a user's research fed by their own history no matter which
        internal component is doing the work.
        """
        if get_settings().corpus_scope == "global":
            return None
        if exclude_run_id:
            return await self.session.scalar(
                select(ResearchRunRow.owner_id).where(ResearchRunRow.id == exclude_run_id)
            )
        # No run context: an admin searching the corpus directly sees everything they
        # could already see run by run; anyone else is held to their own history.
        if actor.is_admin:
            return None
        return actor.user_id

    async def corpus_documents(self, version_ids: list[str]) -> list[AcquiredDocument]:
        if not version_ids:
            return []
        rows = (
            await self.session.execute(
                select(SourceRow, SourceVersionRow)
                .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
                .where(SourceVersionRow.id.in_(version_ids))
            )
        ).tuples()
        return [
            AcquiredDocument(
                candidate={
                    "connector_id": "local_corpus",
                    "family": SourceFamily(source.family),
                    "title": source.title,
                    "url": source.url,
                    "persistent_id": source.persistent_id,
                    "metadata": {
                        **(source.metadata_json or {}),
                        "local_corpus": True,
                        "source_version_id": version.id,
                    },
                },
                success=True,
                access_status=version.access_status,
                content=version.content,
                raw_content=version.raw_content or "",
                content_hash=version.content_hash,
                content_type=(version.provenance or {}).get("content_type", "text/plain"),
                document_type=(version.provenance or {}).get("document_type", "text"),
                language=(version.provenance or {}).get("language", "und"),
                canonical_url=source.url,
                final_url=(version.provenance or {}).get("final_url") or source.url,
                acquisition_method="local_corpus",
                strategies_tried=["local_corpus"],
            )
            for source, version in rows
        ]

    async def source_metadata_for_versions(
        self, version_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not version_ids:
            return {}
        rows = (
            await self.session.execute(
                select(SourceRow, SourceVersionRow)
                .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
                .where(SourceVersionRow.id.in_(version_ids))
            )
        ).tuples()
        return {
            version.id: {
                "source_id": source.id,
                "title": source.title,
                "url": source.url,
                "family": source.family,
                "connector_id": source.connector_id,
                "content_hash": version.content_hash,
                "retrieved_at": version.retrieved_at.isoformat(),
            }
            for source, version in rows
        }

    async def add_frontier_links(
        self,
        run_id: str,
        source_url: str,
        links: list[str],
        *,
        max_links: int,
    ) -> int:
        source_host = urlsplit(canonicalize_url(source_url)).hostname or ""
        added = 0
        for link in list(dict.fromkeys(links))[:max_links]:
            canonical = canonicalize_url(link)
            # A hostless link (mailto:, javascript:, bare fragment) has no domain to
            # compare and nothing to crawl; skipping beats aborting the whole run.
            link_host = urlsplit(canonical).hostname
            if not link_host:
                continue
            existing = await self.session.scalar(
                select(FrontierRow).where(
                    FrontierRow.run_id == run_id,
                    FrontierRow.canonical_url == canonical,
                )
            )
            if existing:
                continue
            same_domain = link_host == source_host
            self.session.add(
                FrontierRow(
                    id=new_id(),
                    run_id=run_id,
                    canonical_url=canonical,
                    discovered_from=source_url,
                    depth=1,
                    priority=1.0 if same_domain else 0.35,
                    metadata_json={"same_domain": same_domain},
                )
            )
            added += 1
        await self.session.commit()
        return added

    async def pop_frontier_candidates(self, run_id: str, limit: int) -> list[dict[str, Any]]:
        rows = list(
            await self.session.scalars(
                select(FrontierRow)
                .where(
                    FrontierRow.run_id == run_id,
                    FrontierRow.status == "pending",
                )
                .order_by(FrontierRow.priority.desc(), FrontierRow.created_at)
                .limit(limit)
            )
        )
        for row in rows:
            row.status = "scheduled"
        await self.session.commit()
        return [
            {
                "url": row.canonical_url,
                "depth": row.depth,
                "discovered_from": row.discovered_from,
                "priority": row.priority,
            }
            for row in rows
        ]

    async def save_claims(
        self,
        run_id: str,
        claims: list[tuple[ExtractedClaim, str]],
    ) -> None:
        existing_ids = set(
            await self.session.scalars(select(ClaimRow.id).where(ClaimRow.run_id == run_id))
        )
        existing_pairs = set(
            (
                await self.session.execute(
                    select(EvidenceRow.claim_id, EvidenceRow.source_version_id)
                    .join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
                    .where(ClaimRow.run_id == run_id)
                )
            ).tuples()
        )
        for claim, version_id in claims:
            if claim.id not in existing_ids:
                self.session.add(
                    ClaimRow(
                        id=claim.id,
                        run_id=run_id,
                        text=claim.text,
                        importance=claim.importance,
                        confidence=claim.confidence,
                        status="unresolved",
                        audit={},
                    )
                )
                existing_ids.add(claim.id)
            pair = (claim.id, version_id)
            if pair not in existing_pairs:
                self.session.add(
                    EvidenceRow(
                        id=new_id(),
                        claim_id=claim.id,
                        source_version_id=version_id,
                        direction=claim.direction,
                        quote=claim.quote,
                        location={
                            "start_char": claim.original_start_char
                            if claim.original_start_char is not None
                            else claim.start_char,
                            "end_char": claim.original_end_char
                            if claim.original_end_char is not None
                            else claim.end_char,
                            "passage_id": claim.passage_id,
                            "section_path": claim.section_path,
                            "page_number": claim.page_number,
                            "retrieval_score": claim.retrieval_score,
                        },
                        entailment_score=evidence_entailment(
                            claim.text,
                            claim.quote,
                            claim.confidence,
                        ),
                    )
                )
                existing_pairs.add(pair)
        await self.session.commit()

    async def list_claims(self, run_id: str) -> list[ClaimRow]:
        return list(await self.session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id)))

    async def list_evidence(self, run_id: str) -> list[tuple[ClaimRow, EvidenceRow, SourceRow]]:
        result = await self.session.execute(
            select(ClaimRow, EvidenceRow, SourceRow)
            .join(EvidenceRow, EvidenceRow.claim_id == ClaimRow.id)
            .join(SourceVersionRow, SourceVersionRow.id == EvidenceRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(ClaimRow.run_id == run_id)
        )
        return list(result.tuples())

    async def save_figure_observation(
        self,
        *,
        run_id: str,
        source_id: str,
        source_version_id: str,
        image_hash: str,
        image_key: str,
        page_number: int | None,
        caption: str,
        vision_model: str,
        analysis: dict[str, Any],
    ) -> FigureObservationRow:
        row = await self.session.scalar(
            select(FigureObservationRow).where(
                FigureObservationRow.source_version_id == source_version_id,
                FigureObservationRow.image_hash == image_hash,
                FigureObservationRow.vision_model == vision_model,
            )
        )
        if row is None:
            row = FigureObservationRow(
                id=new_id(),
                run_id=run_id,
                source_id=source_id,
                source_version_id=source_version_id,
                image_hash=image_hash,
                image_key=image_key,
                page_number=page_number,
                caption=caption,
                vision_model=vision_model,
                analysis=analysis,
            )
            self.session.add(row)
        else:
            row.image_key = image_key
            row.page_number = page_number
            row.caption = caption
            row.analysis = analysis
        await self.session.commit()
        return row

    async def list_figure_observations(self, run_id: str) -> list[FigureObservationRow]:
        return list(
            await self.session.scalars(
                select(FigureObservationRow)
                .where(FigureObservationRow.run_id == run_id)
                .order_by(FigureObservationRow.created_at, FigureObservationRow.id)
            )
        )

    async def save_artifact(
        self, run_id: str, name: str, media_type: str, object_key: str, size_bytes: int
    ) -> ArtifactRow:
        row = await self.session.scalar(
            select(ArtifactRow).where(ArtifactRow.run_id == run_id, ArtifactRow.name == name)
        )
        if row is None:
            row = ArtifactRow(
                id=new_id(),
                run_id=run_id,
                name=name,
                media_type=media_type,
                object_key=object_key,
                size_bytes=size_bytes,
            )
            self.session.add(row)
        else:
            row.object_key, row.size_bytes, row.media_type = object_key, size_bytes, media_type
        await self.session.commit()
        return row

    async def list_artifacts(self, run_id: str) -> list[ArtifactRow]:
        return list(
            await self.session.scalars(select(ArtifactRow).where(ArtifactRow.run_id == run_id))
        )

    async def purge_run(self, run_id: str) -> dict[str, int]:
        """Erase a run and everything that only exists because of it.

        There are no database-level cascades on these tables -- run_id is an indexed
        column, not a foreign key -- so every child has to be named here. That is the
        risk this method exists to contain: a caller deleting the run row by hand leaves
        thousands of orphans behind that nothing will ever look at again.

        The object store is not touched here; it has its own client and the caller owns
        it. :meth:`artifact_keys` and the ``<run_id>/`` snapshot prefix are what to remove
        there.

        **Passages go too.** They are the corpus pool that seeds later runs
        (``list_corpus_passages``), so purging a run also withdraws its text from that
        pool. For an abandoned run that is the point; for a completed one, think twice.
        """
        source_ids = select(SourceRow.id).where(SourceRow.run_id == run_id)
        version_ids = select(SourceVersionRow.id).where(
            SourceVersionRow.source_id.in_(source_ids)
        )
        claim_ids = select(ClaimRow.id).where(ClaimRow.run_id == run_id)

        # Children before parents, so a failure halfway through cannot leave a row whose
        # own parent is already gone and which nothing can find any more.
        removed: dict[str, int] = {}
        for name, statement in (
            ("evidence", delete(EvidenceRow).where(EvidenceRow.claim_id.in_(claim_ids))),
            ("passages", delete(PassageRow).where(PassageRow.source_version_id.in_(version_ids))),
            ("source_versions", delete(SourceVersionRow).where(
                SourceVersionRow.source_id.in_(source_ids)
            )),
            ("claims", delete(ClaimRow).where(ClaimRow.run_id == run_id)),
            ("sources", delete(SourceRow).where(SourceRow.run_id == run_id)),
            ("source_relations", delete(SourceRelationRow).where(
                SourceRelationRow.run_id == run_id
            )),
            ("figure_observations", delete(FigureObservationRow).where(
                FigureObservationRow.run_id == run_id
            )),
            ("frontier", delete(FrontierRow).where(FrontierRow.run_id == run_id)),
            ("artifacts", delete(ArtifactRow).where(ArtifactRow.run_id == run_id)),
            ("checkpoints", delete(CheckpointRow).where(CheckpointRow.run_id == run_id)),
            ("events", delete(EventRow).where(EventRow.run_id == run_id)),
            ("run", delete(ResearchRunRow).where(ResearchRunRow.id == run_id)),
        ):
            result = await self.session.execute(statement)
            removed[name] = result.rowcount or 0
        await self.session.commit()
        return removed

    async def delete_artifacts(self, run_id: str, names: set[str]) -> None:
        if not names:
            return
        await self.session.execute(
            delete(ArtifactRow).where(
                ArtifactRow.run_id == run_id,
                ArtifactRow.name.in_(names),
            )
        )
        await self.session.commit()
