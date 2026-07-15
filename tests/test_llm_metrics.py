from __future__ import annotations

import json

import httpx
import pytest

from research_platform.config import Settings
from research_platform.llm import OllamaProvider


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
    assert captured["options"]["num_ctx"] == 8192
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
                "message": {"thinking": "checked all pairs", "content": '{"answer": 42}'},
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
