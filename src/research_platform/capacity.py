"""How many research runs this machine can carry right now.

The worker ran one run at a time. That protected the single GPU, but it was a much wider
limit than the GPU needed: most of a run's wall clock is SEARCH, ACQUIRE and NORMALIZE --
network and CPU -- with the GPU idle throughout. A second run could have used that gap.

So the number is measured instead of chosen. Nothing here is a policy cap: the configured
values are the *budget* a run is assumed to need and the headroom the machine keeps for
itself, and the slot count falls out of dividing what is free by what a run costs. If the
hardware carries five runs, five runs start.

Three separate concerns live here because they are the same decision seen from three
angles:

* :func:`measure` / :func:`plan_capacity` -- how many runs fit, from live numbers.
* :class:`CapacityGate` -- the process-wide admission queue that hands out those slots.
* :func:`model_lease` -- the process-wide single file for GPU work (see the module note
  on why the GPU does not multiply the slot count).
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any

import httpx
import psutil

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

# Not a policy number: a runaway brake. If the measurements ever go wrong -- a container
# limit disappears, psutil reports nonsense -- the answer must still be finite.
ABSOLUTE_GUARD = 8


@dataclass(frozen=True)
class Measurement:
    """What the machine looks like at one instant."""

    available_ram_gb: float
    cpu_count: int
    busy_cores: float
    # None when Ollama could not be reached: unknown is not the same as zero, and a probe
    # failure must not be read as "the GPU is free".
    resident_vram_gb: float | None


@dataclass(frozen=True)
class Capacity:
    """The admission decision, with the reason attached.

    `limited_by` exists so the number is explainable. A capacity system whose answer
    cannot be traced back to a resource is one nobody can tune or trust.
    """

    allowed: int
    limited_by: str
    slots_ram: int
    slots_cpu: int
    slots_gpu: int
    measurement: Measurement

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "limited_by": self.limited_by,
            "slots": {"ram": self.slots_ram, "cpu": self.slots_cpu, "gpu": self.slots_gpu},
            "available_ram_gb": round(self.measurement.available_ram_gb, 2),
            "cpu_count": self.measurement.cpu_count,
            "busy_cores": round(self.measurement.busy_cores, 2),
            "resident_vram_gb": (
                round(self.measurement.resident_vram_gb, 2)
                if self.measurement.resident_vram_gb is not None
                else None
            ),
        }


async def resident_vram_gb(settings: Settings, client: httpx.AsyncClient | None = None) -> float | None:
    """VRAM the models currently occupy, straight from Ollama.

    Ollama is the only thing on this machine that puts work on the GPU, so what it reports
    resident is the number that matters. `nvidia-smi` would also count the desktop
    compositor, and it is not installed in the worker container anyway.
    """
    url = f"{settings.ollama_url.rstrip('/')}/api/ps"
    try:
        if client is not None:
            response = await client.get(url, timeout=5)
        else:
            async with httpx.AsyncClient(timeout=5) as owned:
                response = await owned.get(url)
        response.raise_for_status()
        models = response.json().get("models") or []
    except Exception:
        return None
    total = sum(float(model.get("size_vram") or 0) for model in models)
    return total / 1024**3


async def measure(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> Measurement:
    settings = settings or get_settings()
    memory = psutil.virtual_memory()
    cpu_count = psutil.cpu_count() or 1
    # interval=None reads the load since the previous call rather than blocking; the gate
    # polls often enough that the sample is meaningful, and a blocking read here would
    # stall the event loop it is trying to protect.
    busy_fraction = min(100.0, max(0.0, psutil.cpu_percent(interval=None))) / 100.0
    return Measurement(
        available_ram_gb=memory.available / 1024**3,
        cpu_count=cpu_count,
        busy_cores=cpu_count * busy_fraction,
        resident_vram_gb=await resident_vram_gb(settings, client),
    )


def plan_capacity(measurement: Measurement, settings: Settings | None = None) -> Capacity:
    """Turn a measurement into a slot count. Pure: no clocks, no sockets, no globals."""
    settings = settings or get_settings()

    # Spend only what is free beyond the reserve. Using total memory here would let the
    # machine be filled up to the point where everything else starts swapping, which is
    # the bottleneck this is supposed to prevent.
    spendable_ram = measurement.available_ram_gb - settings.ram_reserve_gb
    slots_ram = int(math.floor(spendable_ram / settings.run_memory_budget_gb))

    # The budget is added on top of the load that is already there, not carved out of the
    # total: a machine that is busy with something else offers fewer slots by itself.
    usable_cores = measurement.cpu_count * (1.0 - settings.cpu_headroom)
    spendable_cpu = usable_cores - measurement.busy_cores
    slots_cpu = int(math.floor(spendable_cpu / settings.run_cpu_budget))

    slots_gpu = _gpu_slots(measurement, settings)

    allowed = min(slots_ram, slots_cpu, slots_gpu, ABSOLUTE_GUARD)
    # One run always runs. A machine too loaded for even a single run would otherwise
    # stop the platform entirely, and refusing every run is worse than running one.
    allowed = max(1, allowed)

    named = {"ram": slots_ram, "cpu": slots_cpu, "gpu": slots_gpu, "guard": ABSOLUTE_GUARD}
    limited_by = min(named, key=lambda key: named[key])
    return Capacity(
        allowed=allowed,
        limited_by=limited_by,
        slots_ram=slots_ram,
        slots_cpu=slots_cpu,
        slots_gpu=slots_gpu,
        measurement=measurement,
    )


def _gpu_slots(measurement: Measurement, settings: Settings) -> int:
    """VRAM is a precondition here, not a multiplier.

    Model calls are serialised process-wide (:func:`model_lease`) and Ollama keeps one
    copy of a model resident, so a second run adds no VRAM. What VRAM decides is whether
    the models can *stay* resident: if the LLM and the embedding model together do not fit
    with a margin, Ollama evicts and reloads on every switch between them -- and parallel
    runs alternate between the two far more often than one run does. That thrash is worth
    avoiding, so the answer there is a single run.

    DOCLING IS A SECOND CONSUMER THIS FUNCTION CANNOT SEE. `resident_vram_gb` comes from
    Ollama, and :func:`model_lease` serialises Ollama calls -- neither covers a GPU
    docling service sitting on the same card. It does not queue behind the lease either:
    parse() runs on a worker thread and the lease is an asyncio primitive, so making it
    wait there would mean cross-loop signalling to buy mutual exclusion nobody asked for
    (one run's acquisition and another's analysis overlapping is the point of parallel
    runs). A flat reservation is the honest model instead: the service keeps its models
    resident, so its VRAM is a constant, not a spike. Settings default it to 0.0 and it
    is meant to be measured with nvidia-smi during a conversion, not guessed.
    """
    if measurement.resident_vram_gb is None:
        # The probe failed. Say nothing rather than something wrong: RAM and CPU still
        # bound the answer, and treating an unreachable Ollama as "no GPU pressure" would
        # be the one reading that cannot be justified.
        return ABSOLUTE_GUARD
    headroom = (settings.gpu_vram_total_gb
                - measurement.resident_vram_gb
                - settings.docling_vram_reserve_gb)
    return ABSOLUTE_GUARD if headroom >= settings.gpu_vram_margin_gb else 1


def startup_ceiling(settings: Settings | None = None) -> int:
    """The arq `max_jobs` value, fixed for the life of the worker process.

    arq settles `max_jobs` when the Worker is built and it cannot be changed afterwards,
    so this is the ceiling the live gate then refines downward. It uses totals rather than
    the current load: hardware does not change while the process runs, load does, and load
    is the gate's job. No network call -- this is evaluated at import time.
    """
    settings = settings or get_settings()
    memory = psutil.virtual_memory()
    cpu_count = psutil.cpu_count() or 1
    by_ram = int(math.floor(
        (memory.total / 1024**3 - settings.ram_reserve_gb) / settings.run_memory_budget_gb
    ))
    by_cpu = int(math.floor(
        cpu_count * (1.0 - settings.cpu_headroom) / settings.run_cpu_budget
    ))
    return max(1, min(by_ram, by_cpu, ABSOLUTE_GUARD))


class CapacityGate:
    """Hands out run slots, in priority order, against a freshly measured capacity.

    Process-wide and in-memory on purpose: one worker process executes every run, so the
    truth about "how many are running right now" is here, and a Redis counter would be a
    second copy of it that can drift.

    A run that cannot start **waits** rather than going back on the queue. Deferred
    re-enqueueing does not work for the urgent band: its score is ten years in the past
    (see queueing.py), so any `_defer_until` still lands far below `now` and the job is
    pulled straight back -- a spin loop dressed up as a delay.
    """

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._waiting: list[tuple[int, int, str]] = []
        self._sequence = 0
        self._changed = asyncio.Event()

    @property
    def active(self) -> int:
        return len(self._active)

    def snapshot(self) -> dict[str, Any]:
        return {"running": len(self._active), "waiting": len(self._waiting)}

    def _turn(self, ticket: tuple[int, int, str]) -> bool:
        """Whether this waiter is the one a free slot belongs to.

        Urgent first, then arrival order. Without this any waiter could take the slot the
        moment it polls, which would make the priority band stop at the queue's edge.
        """
        return min(self._waiting) == ticket if self._waiting else True

    async def acquire(
        self,
        run_id: str,
        *,
        priority: str = "normal",
        settings: Settings | None = None,
        on_wait=None,
    ) -> Capacity:
        settings = settings or get_settings()
        self._sequence += 1
        ticket = (0 if priority == "urgent" else 1, self._sequence, run_id)
        self._waiting.append(ticket)
        announced = False
        try:
            while True:
                capacity = plan_capacity(await measure(settings), settings)
                if len(self._active) < capacity.allowed and self._turn(ticket):
                    self._active.add(run_id)
                    return capacity
                if not announced and on_wait is not None:
                    # Said once: a run that sits here looks stuck otherwise, and the
                    # measurement is the only thing that explains the wait.
                    await on_wait(capacity)
                    announced = True
                self._changed.clear()
                try:
                    await asyncio.wait_for(
                        self._changed.wait(), timeout=settings.capacity_poll_s
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    pass
        finally:
            self._waiting.remove(ticket)

    def release(self, run_id: str) -> None:
        self._active.discard(run_id)
        # Wake the waiters now rather than letting them find out on their next poll.
        self._changed.set()


# One gate and one model lease per process. Both are deliberately module-level: they
# describe this machine, and a per-pipeline copy would police nothing.
GATE = CapacityGate()

_MODEL_LEASE = asyncio.Semaphore(1)


def model_lease() -> asyncio.Semaphore:
    """The single file every GPU-bound call queues in.

    Held around one model call, not around a pipeline stage. A stage-wide lock would hold
    the GPU for the minutes EXTRACT_EVIDENCE takes and make the other run's one-second
    DECOMPOSE call wait all of it. Per call gives the same guarantee -- two model calls are
    never in flight together -- without the starvation.

    `llm_timeout_s` is passed to httpx per request, so the clock starts after the lease is
    taken: queueing here does not eat into a call's timeout budget. That was the real risk
    of running several runs against one GPU.
    """
    return _MODEL_LEASE
