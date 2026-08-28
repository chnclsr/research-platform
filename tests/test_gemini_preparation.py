from __future__ import annotations

import json

import httpx
import pytest

from research_platform.config import Settings
from research_platform.llm import GeminiProvider, build_preparation_llm
from research_platform.pipeline import ResearchPipeline


def settings(**overrides) -> Settings:
    values = {
        "testing": False,
        "telegram_preparation_llm_enabled": True,
        "gemini_api_key": "secret-test-key",
        "gemini_preparation_model": "gemini-3.6-flash",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_gemini_requests_json_without_putting_the_key_in_the_url():
    seen: dict = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"label":"lung_ct"}'}]}}],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 13,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = GeminiProvider(settings(), client)
        result = await provider.complete_json("Return a label", "QUESTION: lung CT")

    assert result == {"label": "lung_ct"}
    assert "secret-test-key" not in seen["url"]
    assert seen["key"] == "secret-test-key"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert provider.drain_metrics() == [{
        "provider": "gemini",
        "model": "gemini-3.6-flash",
        "wall_seconds": pytest.approx(0, abs=1),
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "total_tokens": 13,
    }]


@pytest.mark.asyncio
async def test_gemini_retries_a_rate_limit_using_retry_after(monkeypatch):
    calls = 0
    delays: list[float] = []

    def answer(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
        )

    async def no_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("research_platform.llm.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = GeminiProvider(settings(gemini_preparation_max_retries=1), client)
        assert await provider.complete_json("system", "user") == {}

    assert calls == 2
    assert delays == [2.0]


@pytest.mark.asyncio
async def test_gemini_errors_do_not_expose_the_key_or_response_body():
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="secret-test-key and private prompt")

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = GeminiProvider(settings(), client)
        with pytest.raises(RuntimeError) as failure:
            await provider.complete_json("system", "private prompt")

    assert "secret-test-key" not in str(failure.value)
    assert "private prompt" not in str(failure.value)
    assert "HTTP 401" in str(failure.value)


@pytest.mark.asyncio
async def test_enabled_preparation_requires_a_key_and_disabled_mode_builds_nothing():
    disabled = settings(telegram_preparation_llm_enabled=False)
    async with httpx.AsyncClient() as client:
        assert build_preparation_llm(disabled, client) is None
        missing = settings(gemini_api_key=None)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_preparation_llm(missing, client)


def test_pipeline_uses_gemini_only_for_telegram_preparation():
    local = object()
    gemini = object()
    pipeline = ResearchPipeline.__new__(ResearchPipeline)
    pipeline.llm = local
    pipeline.preparation_llm = gemini

    pipeline._telegram_preparation = False
    assert pipeline._preparation_provider() is local

    pipeline._telegram_preparation = True
    assert pipeline._preparation_provider() is gemini
