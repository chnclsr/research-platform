"""Everything that touches the ARQ queue, in one place.

Until now five call sites reached for ``redis.enqueue_job`` directly and two of them did
not even pass a job id. Adding a priority to that arrangement means five chances to forget
one, and a forgotten one is silent: the run simply waits in the wrong order. So the queue
gets an owner.

**Why not a second ARQ queue.** An arq ``Worker`` consumes exactly one ``queue_name``, so
two real queues means two worker processes, and two workers on this machine race for the
one GPU -- the serialisation the whole platform is built on. Instead there is one queue
with two bands inside it, the urgent band entirely ahead of the normal one.

**How the band works.** arq keeps pending jobs in a Redis sorted set. When ``_defer_until``
is given the score is that instant in epoch milliseconds (``arq/connections.py``), and the
worker pulls with ``zrangebyscore(min=-inf, max=now)`` -- ascending score
(``arq/worker.py``). Score *is* queue position. An urgent job is enqueued with its own
enqueue time shifted ten years into the past: a constant shift, so urgent jobs keep FIFO
order among themselves, and ten years is further back than any normal job could have been
waiting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from arq.constants import (
    default_queue_name,
    in_progress_key_prefix,
    job_key_prefix,
    result_key_prefix,
    retry_key_prefix,
)

from .config import get_settings

Priority = Literal["normal", "urgent"]

PRIORITIES: tuple[str, ...] = ("normal", "urgent")
URGENT: str = "urgent"
NORMAL: str = "normal"

# How far below the normal band the urgent band sits. Any value larger than the longest
# a normal job could plausibly wait works; ten years is unambiguous and still leaves the
# score far inside the float range Redis uses.
PRIORITY_SHIFT = timedelta(days=get_settings().queue_priority_shift_days)

# arq derives the job key's TTL from the score when none is given, which goes negative for
# a back-dated score and makes Redis reject the PSETEX. Passing it explicitly keeps the
# job alive for the same day arq would have chosen.
JOB_EXPIRY = timedelta(seconds=get_settings().queue_job_expiry_s)


def normalize_priority(value: Any) -> str:
    """Anything unrecognised is normal: an odd value must not create a fast lane."""
    return URGENT if str(value or "").strip().lower() == URGENT else NORMAL


def job_id_for(run_id: str) -> str:
    return f"run:{run_id}"


def run_id_of(job_id: str) -> str | None:
    text = job_id.decode() if isinstance(job_id, bytes) else str(job_id)
    return text[len("run:") :] if text.startswith("run:") else None


def score_kwargs(priority: str, *, now: datetime | None = None) -> dict[str, Any]:
    """The enqueue_job keywords that place a job in its band."""
    moment = now or datetime.now(timezone.utc)
    if normalize_priority(priority) == URGENT:
        moment = moment - PRIORITY_SHIFT
    return {"_defer_until": moment, "_expires": JOB_EXPIRY}


async def enqueue_run(redis: Any, run_id: str, priority: str = NORMAL) -> Any:
    """Put a run on the queue in its band, and say whether it landed.

    The job id is the run id on every path, which is what lets cancellation remove the
    job, the panel report a queue position and :func:`rescore_run` find it again. arq
    refuses a job whose key still exists, and a finished job's result key lingers for
    ``keep_result`` seconds -- long enough to block the resume and HITL paths, which is why
    those two used random ids and lost all three of those properties. Clearing the stale
    keys first restores the deterministic id without reintroducing that failure.

    A run that is already executing is left alone: deleting the keys under a running job
    would break the worker's own bookkeeping.
    """
    job_id = job_id_for(run_id)
    if await redis.exists(f"{in_progress_key_prefix}{job_id}"):
        return None
    await redis.delete(f"{job_key_prefix}{job_id}", f"{result_key_prefix}{job_id}")
    return await redis.enqueue_job(
        "execute_research_run",
        run_id,
        _job_id=job_id,
        **score_kwargs(priority),
    )


async def rescore_run(redis: Any, run_id: str, priority: str) -> bool:
    """Move a waiting job into another band. True when a waiting job was moved."""
    job_id = job_id_for(run_id)
    if await redis.exists(f"{in_progress_key_prefix}{job_id}"):
        return False
    if await redis.zscore(default_queue_name, job_id) is None:
        return False
    score = score_kwargs(priority)["_defer_until"].timestamp() * 1000
    # xx: only ever update, so a job that left the queue between the check above and here
    # is not resurrected by being added back.
    await redis.zadd(default_queue_name, {job_id: score}, xx=True)
    return True


async def discard_run_jobs(redis: Any, run_id: str) -> None:
    """Forget a run's queued job entirely -- used when it is cancelled or reconciled."""
    job_id = job_id_for(run_id)
    await redis.zrem(default_queue_name, job_id)
    await redis.delete(
        f"{job_key_prefix}{job_id}",
        f"{in_progress_key_prefix}{job_id}",
        f"{retry_key_prefix}{job_id}",
    )
