"""A Redis stand-in that models the part of ARQ's queue the scheduler depends on.

Priority is expressed as the score of a member in a sorted set, so a fake that only
records "enqueue was called" cannot tell a correctly ordered queue from a wrong one. This
one keeps the sorted set, which lets a test assert the thing that actually matters: which
job a worker would pull first.
"""

from __future__ import annotations

from typing import Any

from arq.constants import default_queue_name
from arq.utils import to_unix_ms


class FakeRedis:
    def __init__(self) -> None:
        self.queue: dict[str, float] = {}
        self.keys: set[str] = set()
        self.enqueued: list[tuple[str, str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, ...]] = []
        self.removed: list[tuple[str, str]] = []

    # -- key space -------------------------------------------------------------------
    async def exists(self, *keys: str) -> int:
        return sum(1 for key in keys if key in self.keys)

    async def delete(self, *keys: str) -> None:
        self.deleted.append(keys)
        self.keys.difference_update(keys)

    # -- sorted set ------------------------------------------------------------------
    async def zadd(self, key: str, mapping: dict[str, float], xx: bool = False) -> int:
        added = 0
        for member, score in mapping.items():
            if xx and member not in self.queue:
                continue
            added += member not in self.queue
            self.queue[member] = score
        return added

    async def zscore(self, key: str, member: str) -> float | None:
        return self.queue.get(member)

    async def zrem(self, key: str, member: str) -> None:
        self.removed.append((key, member))
        self.queue.pop(member, None)

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        ordered = sorted(self.queue.items(), key=lambda item: item[1])
        window = ordered[start : None if end == -1 else end + 1]
        return window if withscores else [job_id for job_id, _ in window]

    # -- arq ---------------------------------------------------------------------------
    async def enqueue_job(self, function: str, run_id: str, **kwargs: Any):
        job_id = kwargs.get("_job_id") or run_id
        self.enqueued.append((function, run_id, kwargs))
        defer_until = kwargs.get("_defer_until")
        self.queue[job_id] = to_unix_ms(defer_until) if defer_until else 0.0
        self.keys.add(f"arq:job:{job_id}")
        return object()

    # -- helpers for tests ---------------------------------------------------------------
    def order(self) -> list[str]:
        """Job ids in the order a worker would pull them."""
        return [job_id for job_id, _ in sorted(self.queue.items(), key=lambda x: x[1])]

    def score_of(self, run_id: str) -> float | None:
        return self.queue.get(f"run:{run_id}")

    @property
    def queue_name(self) -> str:
        return default_queue_name
