from __future__ import annotations

import json

import httpx
import pytest

from research_platform.config import Settings
from research_platform.llm import (
    LLMProvider,
    OllamaProvider,
    OutputTruncated,
    extract_claims,
)
from research_platform.schemas import AcquiredDocument, ConnectorCandidate, SourceFamily


@pytest.mark.asyncio
async def test_ollama_metrics_capture_tokens_and_durations():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"content": '{"ok": true}'},
            "prompt_eval_count": 12,
            "eval_count": 8,
            "prompt_eval_duration": 500_000_000,
            "eval_duration": 1_000_000_000,
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(Settings(
            _env_file=None,
            llm_temperature=0.5,
            llm_top_p=0.95,
            llm_top_k=20,
            llm_presence_penalty=1.5,
        ), client)
        assert await provider.complete_json("system", "user") == {"ok": True}
        metrics = provider.drain_metrics()

    assert metrics[0]["prompt_tokens"] == 12
    assert metrics[0]["completion_tokens"] == 8
    assert metrics[0]["prompt_seconds"] == 0.5
    assert metrics[0]["generation_seconds"] == 1.0
    assert captured["think"] is False
    # Tracks the Settings default, raised from 8192 so the MERGE and OVERVIEW prompts reach
    # the 24000-character ceiling: below that a many-packet theme divided their budget down
    # to card fields too narrow to carry an [Sxx]. Drafting prompts are capped separately by
    # `_PACKET_TARGET_CHARS` and do not follow this setting upward.
    assert captured["options"]["num_ctx"] == 16384
    assert captured["options"]["num_predict"] == 2048
    assert captured["options"]["temperature"] == 0.5
    assert captured["options"]["top_p"] == 0.95
    assert captured["options"]["top_k"] == 20
    assert captured["options"]["presence_penalty"] == 1.5
    assert provider.drain_metrics() == []


@pytest.mark.asyncio
async def test_ollama_two_stage_reasoning_then_json_formatting():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        if len(captured) == 1:
            return httpx.Response(200, json={
                "message": {"thinking": "checked all pairs", "content": "answer: 42"},
                "prompt_eval_count": 20,
                "eval_count": 100,
                "prompt_eval_duration": 100_000_000,
                "eval_duration": 2_000_000_000,
                "done_reason": "stop",
            })
        return httpx.Response(200, json={
            "message": {"content": '{"answer": 42}'},
            "prompt_eval_count": 30,
            "eval_count": 8,
            "prompt_eval_duration": 200_000_000,
            "eval_duration": 300_000_000,
            "done_reason": "stop",
        })

    settings = Settings(
        _env_file=None,
        llm_think=True,
        llm_reason_then_format=True,
        llm_context_tokens=24576,
        llm_reasoning_output_tokens=20480,
        llm_temperature=1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(settings, client)
        assert await provider.complete_json("Return answer", "six times seven") == {"answer": 42}
        metrics = provider.drain_metrics()

    assert len(captured) == 2
    assert captured[0]["think"] is True
    assert "format" not in captured[0]
    assert captured[0]["options"]["num_ctx"] == 24576
    assert captured[0]["options"]["num_predict"] == 20480
    assert captured[1]["think"] is False
    assert captured[1]["format"] == "json"
    assert [metric["phase"] for metric in metrics] == ["reasoning", "formatting"]
    assert metrics[0]["thinking_chars"] == len("checked all pairs")


@pytest.mark.asyncio
async def test_reasoning_direct_json_uses_native_sampling_without_formatter():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"thinking": "done", "content": '```json\n{"answer": 42}\n```'},
            "prompt_eval_count": 10,
            "eval_count": 20,
            "eval_duration": 100_000_000,
            "done_reason": "stop",
        })

    settings = Settings(
        _env_file=None,
        llm_think=True,
        llm_reason_then_format=True,
        llm_temperature=0.6,
        llm_top_p=0.95,
        llm_top_k=0,
        llm_min_p=0.01,
        llm_repeat_penalty=1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(settings, client)
        assert await provider.complete_json("Return answer", "six times seven") == {"answer": 42}

    assert len(captured) == 1
    assert captured[0]["options"]["top_k"] == 0
    assert captured[0]["options"]["min_p"] == 0.01
    assert captured[0]["options"]["repeat_penalty"] == 1


class ArrayClaimsProvider(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return [{
            "text": "The intervention improved outcomes.",
            "quote": "The intervention improved outcomes.",
            "direction": "supports",
            "importance": "major",
            "confidence": 0.9,
        }]


@pytest.mark.asyncio
async def test_extract_claims_accepts_top_level_array():
    document = AcquiredDocument(
        candidate=ConnectorCandidate(
            connector_id="test",
            family=SourceFamily.ACADEMIC,
            title="Study",
            url="https://example.com/study",
        ),
        success=True,
        access_status="open",
        content="The intervention improved outcomes.",
        document_type="text",
        acquisition_method="fixture",
    )
    claims = await extract_claims(ArrayClaimsProvider(), document)
    assert len(claims) == 1
    assert claims[0].direction == "supports"


# --------------------------------------------------------------------------------------
# Telling a truncated answer apart from a broken one.
#
# Run 01M27RKQFHR80WNHEQVF2AF2DS stopped six of 114 calls on `done_reason="length"`. Every
# one surfaced as a bare ValueError, indistinguishable from a transport failure, and a whole
# theme plus the overview layer disappeared reported only as "ValueError+ValueError".
# --------------------------------------------------------------------------------------


def _ollama(handler) -> tuple[httpx.AsyncClient, OllamaProvider]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client, OllamaProvider(Settings(_env_file=None), client)


def _answer(content: str, done_reason: str) -> httpx.Response:
    return httpx.Response(200, json={
        "message": {"content": content},
        "done_reason": done_reason,
        "prompt_eval_count": 10,
        "eval_count": 2048,
    })


def test_output_truncated_is_a_value_error() -> None:
    """`FallbackProvider` and the reasoning fallback both branch on ValueError.

    One line, but if the base class ever changes both of those paths stop catching this and
    do so silently.
    """
    assert issubclass(OutputTruncated, ValueError)


@pytest.mark.asyncio
async def test_an_answer_cut_off_mid_json_names_itself_truncated() -> None:
    client, provider = _ollama(lambda request: _answer('{"synthesis": "half a sen', "length"))
    async with client:
        with pytest.raises(OutputTruncated):
            await provider.complete_json("system", "user")


@pytest.mark.asyncio
async def test_an_answer_that_is_merely_invalid_stays_a_plain_value_error() -> None:
    """A model that answered with prose failed differently, and retrying it is reasonable."""
    client, provider = _ollama(lambda request: _answer("not json at all", "stop"))
    async with client:
        with pytest.raises(ValueError) as caught:
            await provider.complete_json("system", "user")
    assert not isinstance(caught.value, OutputTruncated)


@pytest.mark.asyncio
async def test_a_length_stop_that_still_parsed_is_not_an_error() -> None:
    """Under `format: "json"` a model can close its JSON and then hit the ceiling on
    trailing whitespace. That call is usable, which is why the parse still runs first."""
    client, provider = _ollama(lambda request: _answer('{"ok": true}   ', "length"))
    async with client:
        assert await provider.complete_json("system", "user") == {"ok": True}


@pytest.mark.asyncio
async def test_a_truncated_call_still_records_its_metric() -> None:
    """The metric is written before the parse, and `done_reason` is how a run is audited."""
    client, provider = _ollama(lambda request: _answer('{"synthesis": "half', "length"))
    async with client:
        with pytest.raises(OutputTruncated):
            await provider.complete_json("system", "user")
    metrics = provider.drain_metrics()
    assert metrics and metrics[0]["done_reason"] == "length"
