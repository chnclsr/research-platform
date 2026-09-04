from __future__ import annotations

import asyncio

import pytest

from research_platform.rate_limits import DomainLimiter, shared_domain_limiter


@pytest.mark.asyncio
async def test_domain_limiter_hold_serialises_a_domain():
    """`wait()` spaces starts; `hold()` also keeps two requests from overlapping."""
    limiter = DomainLimiter(0.0)
    overlap = 0
    live = 0

    async def one():
        nonlocal overlap, live
        async with limiter.hold("https://example.org/x"):
            live += 1
            overlap = max(overlap, live)
            await asyncio.sleep(0.01)
            live -= 1

    await asyncio.gather(one(), one(), one())
    assert overlap == 1


@pytest.mark.asyncio
async def test_domain_limiter_hold_spaces_consecutive_requests():
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    limiter = DomainLimiter(5.0)
    async with limiter.hold("https://example.org/a"):
        pass
    original = asyncio.sleep
    asyncio.sleep = fake_sleep
    try:
        async with limiter.hold("https://example.org/b"):
            pass
    finally:
        asyncio.sleep = original
    assert slept and slept[0] > 4.0


@pytest.mark.asyncio
async def test_domain_limiter_keeps_separate_hosts_independent():
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    limiter = DomainLimiter(5.0)
    async with limiter.hold("https://one.example.org/a"):
        pass
    original = asyncio.sleep
    asyncio.sleep = fake_sleep
    try:
        async with limiter.hold("https://two.example.org/a"):
            pass
    finally:
        asyncio.sleep = original
    assert slept == []


def test_shared_limiter_is_created_once_per_delay():
    assert shared_domain_limiter(3.25) is shared_domain_limiter(3.25)
    assert shared_domain_limiter(3.25) is not shared_domain_limiter(3.5)
