from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from research_platform.config import Settings
from research_platform.llm import (
    DeterministicProvider,
    FallbackProvider,
    GeminiProvider,
    build_preparation_llm,
)
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


def chain_settings(**overrides) -> Settings:
    return settings(**{
        "preparation_llm_chain": "gemini,openrouter,deepseek",
        "openrouter_api_key": "openrouter-test-key",
        "deepseek_api_key": "deepseek-test-key",
        **overrides,
    })


def _openai_answer(text: str) -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }


@pytest.mark.asyncio
async def test_a_rate_limited_gemini_hands_the_call_to_the_next_provider():
    """The point of the chain: a 429 costs one request, not the run."""
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=_openai_answer('{"label":"lung_ct"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(chain_settings(), client)
        assert isinstance(provider, FallbackProvider)
        assert await provider.complete_json("system", "user") == {"label": "lung_ct"}

    assert seen == ["generativelanguage.googleapis.com", "openrouter.ai"]
    assert provider.drain_fallbacks() == [
        {"served_by": "openrouter", "skipped": ["gemini:429"]}
    ]
    # The answering provider's usage still reaches the run's metrics through the chain.
    assert [call["provider"] for call in provider.drain_metrics()] == ["openrouter"]


@pytest.mark.asyncio
async def test_a_long_retry_after_is_a_cooldown_not_a_sleep(monkeypatch):
    """Preparation makes several calls; an exhausted quota must be paid for once."""
    calls: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=_openai_answer("{}"))

    async def no_sleep(delay: float) -> None:
        raise AssertionError(f"the chain slept {delay}s instead of moving on")

    monkeypatch.setattr("research_platform.llm.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(chain_settings(), client)
        await provider.complete_json("system", "user")
        await provider.complete_json("system", "user")

    assert calls == ["generativelanguage.googleapis.com", "openrouter.ai", "openrouter.ai"]


@pytest.mark.asyncio
async def test_a_wrong_key_retires_a_provider_and_an_empty_answer_moves_on():
    hosts: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(403, text="secret-test-key")
        if request.url.host == "openrouter.ai":
            return httpx.Response(200, json=_openai_answer("sorry, no JSON here"))
        return httpx.Response(200, json=_openai_answer('{"ok":true}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(chain_settings(), client)
        assert await provider.complete_json("system", "user") == {"ok": True}
        await provider.complete_json("system", "user")

    # Gemini is asked once: a 403 does not heal while the process runs. OpenRouter keeps
    # being asked, because an unparseable answer says nothing about its health.
    assert hosts.count("generativelanguage.googleapis.com") == 1
    assert hosts.count("openrouter.ai") == 2
    assert provider.drain_fallbacks()[0]["skipped"] == ["gemini:403", "openrouter:invalid-json"]


@pytest.mark.asyncio
async def test_an_exhausted_chain_fails_the_run_without_leaking_the_prompt():
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="secret-test-key and private prompt")

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(chain_settings(), client)
        with pytest.raises(RuntimeError) as failure:
            await provider.complete_json("system", "private prompt")

    message = str(failure.value)
    assert "secret-test-key" not in message and "private prompt" not in message
    assert "gemini:503" in message and "openrouter:503" in message and "deepseek:503" in message


@pytest.mark.asyncio
async def test_the_chain_carries_the_key_of_each_provider_and_asks_for_json():
    seen: dict[str, httpx.Request] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429)
        return httpx.Response(200, json=_openai_answer("{}"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(chain_settings(), client)
        await provider.complete_json("system", "user")

    openrouter = seen["openrouter.ai"]
    assert openrouter.headers["Authorization"] == "Bearer openrouter-test-key"
    assert "openrouter-test-key" not in str(openrouter.url)
    body = json.loads(openrouter.content)
    assert body["model"] == "z-ai/glm-5.2:free"
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_every_known_provider_can_be_built_and_carries_its_own_key():
    """One OpenAI-compatible class serves three endpoints, each with its own credentials."""
    seen: dict[str, httpx.Request] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request
        if request.url.host in {"generativelanguage.googleapis.com", "openrouter.ai"}:
            return httpx.Response(429)
        return httpx.Response(200, json=_openai_answer("{}"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_preparation_llm(
            chain_settings(
                preparation_llm_chain="gemini,openrouter,groq",
                groq_api_key="groq-test-key",
            ),
            client,
        )
        assert provider.provider_names == ["gemini", "openrouter", "groq"]
        await provider.complete_json("system", "user")

    groq = seen["api.groq.com"]
    assert groq.url.path == "/openai/v1/chat/completions"
    assert groq.headers["Authorization"] == "Bearer groq-test-key"
    assert json.loads(groq.content)["model"] == "openai/gpt-oss-120b"
    assert provider.drain_fallbacks() == [
        {"served_by": "groq", "skipped": ["gemini:429", "openrouter:429"]}
    ]


@pytest.mark.asyncio
async def test_a_provider_named_in_the_chain_without_a_key_is_a_startup_failure():
    async with httpx.AsyncClient() as client:
        keyless = settings(preparation_llm_chain="gemini,openrouter")
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_preparation_llm(keyless, client)
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            build_preparation_llm(settings(preparation_llm_chain="gemini,groq"), client)
        # One configured provider needs no chain wrapper.
        assert isinstance(build_preparation_llm(settings(), client), GeminiProvider)


def test_the_chain_only_accepts_known_providers_and_free_openrouter_models():
    with pytest.raises(ValidationError, match="unknown providers"):
        settings(preparation_llm_chain="gemini,claude")
    with pytest.raises(ValidationError, match="twice"):
        settings(preparation_llm_chain="gemini,gemini")
    with pytest.raises(ValidationError, match="at least one provider"):
        settings(preparation_llm_chain=" , ")
    with pytest.raises(ValidationError, match=":free"):
        settings(openrouter_preparation_model="anthropic/claude-sonnet-4")
    assert settings(preparation_llm_chain=" Gemini , LOCAL ").preparation_chain == (
        "gemini",
        "local",
    )


def test_the_pipeline_writes_a_fallback_to_the_run_history():
    """A run planned by the second-choice model says so in its own event log."""
    events: list[tuple[str, dict]] = []

    class Repo:
        async def event(self, run_id, event_type, payload=None):
            events.append((event_type, payload or {}))

    chain = FallbackProvider([("gemini", DeterministicProvider())], cooldown_s=1.0)
    chain._fallbacks.append({"served_by": "openrouter", "skipped": ["gemini:429"]})
    pipeline = ResearchPipeline.__new__(ResearchPipeline)
    pipeline.repo = Repo()
    pipeline.llm = DeterministicProvider()

    asyncio.run(pipeline._emit_llm_metrics("run-1", "DECOMPOSE", provider=chain))

    assert events == [(
        "preparation_provider_fallback",
        {"stage": "DECOMPOSE", "served_by": "openrouter", "skipped": ["gemini:429"]},
    )]
