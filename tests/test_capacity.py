from __future__ import annotations

import asyncio

import pytest

from research_platform.capacity import (
    ABSOLUTE_GUARD,
    CapacityGate,
    Measurement,
    model_lease,
    plan_capacity,
    startup_ceiling,
)
from research_platform.config import Settings


def settings(**overrides) -> Settings:
    return Settings(**overrides)


def machine(
    *,
    ram: float = 22.8,
    cpus: int = 16,
    busy: float = 0.0,
    vram: float | None = 4.13,
) -> Measurement:
    return Measurement(
        available_ram_gb=ram, cpu_count=cpus, busy_cores=busy, resident_vram_gb=vram
    )


def test_this_machine_gets_several_slots_and_says_which_resource_decides():
    """Measured inside the worker container: 22.8 GB free, 16 CPUs, 4.13 GB resident."""
    capacity = plan_capacity(machine(), settings())
    assert capacity.allowed == 4
    assert capacity.limited_by == "cpu"
    assert capacity.slots_ram > capacity.slots_cpu


def test_memory_can_be_the_one_saying_no():
    capacity = plan_capacity(machine(ram=9.0), settings())
    # (9.0 - 4.0 reserve) / 2.5 per run
    assert capacity.slots_ram == 2
    assert capacity.allowed == 2
    assert capacity.limited_by == "ram"


def test_a_busy_machine_offers_fewer_slots_by_itself():
    """The budget is added on top of the load that is already there.

    Sizing from the total instead would let the platform fill a machine that something
    else is already using, which is the bottleneck this exists to prevent.
    """
    quiet = plan_capacity(machine(busy=0.0), settings()).allowed
    busy = plan_capacity(machine(busy=10.0), settings()).allowed
    assert busy < quiet


def test_the_reserve_is_never_spent():
    # Everything above the reserve is gone: no run may be admitted on memory grounds.
    capacity = plan_capacity(machine(ram=4.2), settings())
    assert capacity.slots_ram == 0
    # ...but the platform does not stop entirely; one run still runs.
    assert capacity.allowed == 1


def test_one_run_always_runs():
    capacity = plan_capacity(machine(ram=0.0, cpus=1, busy=1.0), settings())
    assert capacity.allowed == 1


def test_models_that_cannot_stay_resident_collapse_it_to_one():
    """Ollama evicts and reloads on every switch when the models do not co-reside, and
    parallel runs alternate between completion and embedding far more often than one."""
    tight = plan_capacity(machine(vram=7.8), settings(gpu_vram_total_gb=8.0))
    assert tight.slots_gpu == 1
    assert tight.allowed == 1
    assert tight.limited_by == "gpu"


def test_an_unreachable_ollama_is_not_read_as_an_idle_gpu():
    capacity = plan_capacity(machine(vram=None), settings())
    assert capacity.slots_gpu == ABSOLUTE_GUARD
    # RAM and CPU still bound the answer.
    assert capacity.allowed == 4


def test_the_guard_holds_when_the_measurements_go_wrong():
    capacity = plan_capacity(machine(ram=4096.0, cpus=512, vram=0.0), settings())
    assert capacity.allowed == ABSOLUTE_GUARD


def test_the_guard_is_loaded_from_settings():
    capacity = plan_capacity(
        machine(ram=4096.0, cpus=512, vram=0.0),
        settings(capacity_absolute_guard=3),
    )
    assert capacity.allowed == 3
    assert capacity.slots_gpu == 3


def test_startup_ceiling_is_a_real_number_for_this_machine():
    ceiling = startup_ceiling(settings())
    assert 1 <= ceiling <= ABSOLUTE_GUARD


@pytest.mark.asyncio
async def test_the_gate_holds_a_run_back_and_says_so_once(monkeypatch):
    gate = CapacityGate()
    announced: list[int] = []

    async def one_slot(*args, **kwargs):
        return machine(ram=6.4, cpus=4, busy=0.0)

    monkeypatch.setattr("research_platform.capacity.measure", one_slot)
    config = settings(capacity_poll_s=1.0)

    first = await gate.acquire("RUN1", settings=config)
    assert first.allowed == 1
    assert gate.active == 1

    async def on_wait(capacity):
        announced.append(capacity.allowed)

    second = asyncio.ensure_future(
        gate.acquire("RUN2", settings=config, on_wait=on_wait)
    )
    await asyncio.sleep(0.05)
    assert not second.done()
    assert announced == [1]

    gate.release("RUN1")
    await asyncio.wait_for(second, timeout=2)
    assert gate.active == 1
    # The notice is written once, not on every poll.
    assert announced == [1]


@pytest.mark.asyncio
async def test_a_freed_slot_goes_to_the_urgent_waiter_first(monkeypatch):
    """Otherwise the priority band would stop at the queue's edge: whichever waiter
    happened to poll first would take the slot."""
    gate = CapacityGate()

    async def one_slot(*args, **kwargs):
        return machine(ram=6.4, cpus=4, busy=0.0)

    monkeypatch.setattr("research_platform.capacity.measure", one_slot)
    config = settings(capacity_poll_s=1.0)

    await gate.acquire("HOLDER", settings=config)
    normal = asyncio.ensure_future(gate.acquire("NORMAL", settings=config))
    await asyncio.sleep(0.05)
    urgent = asyncio.ensure_future(
        gate.acquire("URGENT", priority="urgent", settings=config)
    )
    await asyncio.sleep(0.05)

    gate.release("HOLDER")
    await asyncio.wait_for(urgent, timeout=2)
    assert not normal.done()

    gate.release("URGENT")
    await asyncio.wait_for(normal, timeout=2)


@pytest.mark.asyncio
async def test_two_model_calls_are_never_in_flight_together():
    overlap = 0
    peak = 0

    async def call():
        nonlocal overlap, peak
        async with model_lease():
            overlap += 1
            peak = max(peak, overlap)
            await asyncio.sleep(0.02)
            overlap -= 1

    await asyncio.gather(*(call() for _ in range(4)))
    assert peak == 1


def test_the_domain_limiter_is_shared_across_runs():
    """Politeness is a property of the machine: one limiter per run made domain_delay_s
    silently become domain_delay_s / number-of-runs."""
    import httpx

    from research_platform.acquisition import AcquisitionService

    config = settings()
    first = AcquisitionService(config, httpx.AsyncClient())
    second = AcquisitionService(config, httpx.AsyncClient())
    assert first.limiter is second.limiter
