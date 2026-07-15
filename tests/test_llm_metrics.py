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
        provider = OllamaProvider(Settings(_env_file=None), client)
        assert await provider.complete_json("system", "user") == {"ok": True}
        metrics = provider.drain_metrics()

    assert metrics[0]["prompt_tokens"] == 12
    assert metrics[0]["completion_tokens"] == 8
    assert metrics[0]["prompt_seconds"] == 0.5
    assert metrics[0]["generation_seconds"] == 1.0
    assert captured["think"] is False
    assert captured["options"]["num_ctx"] == 8192
    assert captured["options"]["num_predict"] == 2048
    assert provider.drain_metrics() == []
