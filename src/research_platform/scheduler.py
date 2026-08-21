"""Preemption: making room for an urgent run, and giving the room back afterwards.

Ordering the queue is not enough on its own. A run that has already started holds the
single GPU for as long as its collection budget allows, so an urgent question arriving one
minute later would still wait three hours behind it. This module pauses the running normal
run instead, and puts it back once the urgent work is done.

Both halves act across owners, which is why they take a system principal explicitly rather
than a request's: whose run gets paused is a scheduling decision, not something the person
starting the urgent run is authorised to do to somebody else.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .capacity import measure, plan_capacity
from .queueing import URGENT, enqueue_run, normalize_priority
from .repository import Repository
from .schemas import RunStatus

logger = logging.getLogger(__name__)


async def free_slot(repo: Repository) -> bool:
    """Whether the machine can carry one more run right now.

    Counted from the database rather than from the in-process gate: this is also asked
    from the API process, which runs no runs of its own and would see an empty gate.
    """
    capacity = plan_capacity(await measure())
    return await repo.running_run_count() < capacity.allowed


async def preempt_for(
    session: AsyncSession,
    run_id: str,
    priority: str,
) -> str | None:
    """Pause the running normal run so an urgent one can start. Returns the paused run id.

    The pipeline notices within seconds -- ``_interruptible`` re-reads the run's status on
    every poll and cancels the in-flight node -- so this does not wait for the current
    stage to finish. The cost is that the paused run later resumes from its last stage
    checkpoint, redoing whatever that stage had done since.

    Urgent runs do not preempt each other: among themselves the queue is still first come,
    first served.
    """
    if normalize_priority(priority) != URGENT:
        return None
    repo = Repository(session, actor=Principal.system())
    if await free_slot(repo):
        # Nothing to take: the machine can carry another run as it is. Preemption costs
        # the paused run everything its current stage did since the last checkpoint, and
        # paying that when a slot is simply free would be waste.
        return None
    victim = await repo.running_normal_run()
    if victim is None or victim.id == run_id:
        return None
    await repo.update_run(
        victim.id,
        status=RunStatus.PAUSED.value,
        preempted_at=datetime.now(timezone.utc),
    )
    await repo.event(
        victim.id,
        "preempted",
        {"stage": victim.current_stage, "for_run": run_id},
    )
    logger.info("run %s preempted for urgent run %s", victim.id, run_id)
    return victim.id


async def resume_preempted(session: AsyncSession, redis: Any) -> list[str]:
    """Re-queue runs the scheduler paused, once the urgent work is out of the way.

    Runs on a cron rather than at the end of the urgent job: hanging "give the room back"
    off the worker that happens to finish means a worker that crashes instead leaves the
    paused run stranded with nothing that would ever pick it up.

    Only ``preempted_at`` runs are touched. A run its owner paused looks identical in
    ``status`` and must stay exactly where they left it.
    """
    repo = Repository(session, actor=Principal.system())
    if await repo.urgent_work_pending():
        return []
    if not await free_slot(repo):
        return []
    resumed: list[str] = []
    for row in await repo.preempted_runs():
        if row.interaction:
            # The same rule the resume endpoint applies: a run waiting on a person is not
            # waiting on the queue.
            continue
        await repo.update_run(
            row.id,
            status=RunStatus.QUEUED.value,
            preempted_at=None,
            error=None,
        )
        await repo.event(row.id, "preemption_ended", {"stage": row.current_stage})
        await enqueue_run(redis, row.id, row.priority)
        resumed.append(row.id)
        # One at a time: the worker runs a single job, and re-queueing the rest now would
        # only reorder them behind whatever arrives next.
        break
    return resumed
