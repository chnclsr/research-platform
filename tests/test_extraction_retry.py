from __future__ import annotations

from collections import Counter

import httpx
import pytest

from research_platform.llm import OutputTruncated
from research_platform.pipeline import retry_unusable_answer


@pytest.mark.asyncio
async def test_an_answer_cut_off_once_is_asked_for_again():
    """Run 01M2FGWHWKW1GCRXVWTC97B94H lost a Transformer-paper passage to one runaway call."""
    answers: list[object] = [OutputTruncated("hit the ceiling"), ["a claim"]]

    async def call():
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    counts: Counter[str] = Counter()
    assert await retry_unusable_answer(call, counts) == ["a claim"]
    assert counts == {"retried": 1, "recovered": 1}


@pytest.mark.asyncio
async def test_a_second_unusable_answer_still_fails_the_passage():
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        raise ValueError("LLM did not return valid JSON")

    counts: Counter[str] = Counter()
    with pytest.raises(ValueError):
        await retry_unusable_answer(call, counts)
    assert calls == 2
    assert counts == {"retried": 1}


@pytest.mark.asyncio
async def test_a_transport_failure_is_not_retried_here():
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("provider down")

    counts: Counter[str] = Counter()
    with pytest.raises(httpx.ConnectError):
        await retry_unusable_answer(call, counts)
    assert calls == 1
    assert not counts
