"""The report's own prose on a stronger model: REPORT_LLM_CHAIN.

Decided 2026-09-15: synthesis, the claim and figure-caption translations and document
revision planning go to an API model so the report reads as good Turkish. Collection,
extraction, filtering and appraisal stay on the run's own model.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from research_platform.config import Settings
from research_platform.figure_analysis import _localize_text_items
from research_platform.llm import (
    FallbackProvider,
    GeminiProvider,
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    OutputTruncated,
    ProviderUnavailable,
    build_report_llm,
)
from research_platform.pipeline import ResearchPipeline
from research_platform.report_synthesis import _prompt_char_budget


def settings(**overrides) -> Settings:
    values = {
        "testing": False,
        "deepseek_api_key": "deepseek-test-key",
        "gemini_api_key": "gemini-test-key",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_an_empty_chain_keeps_the_report_on_the_run_model():
    async with httpx.AsyncClient() as client:
        assert build_report_llm(settings(), client) is None
        assert build_report_llm(settings(report_llm_chain="deepseek", testing=True), client) is None


def test_the_chain_only_accepts_known_providers_once():
    assert settings(report_llm_chain=" DeepSeek , local ").report_chain == ("deepseek", "local")
    with pytest.raises(ValidationError, match="unknown providers"):
        settings(report_llm_chain="gpt")
    with pytest.raises(ValidationError, match="same provider twice"):
        settings(report_llm_chain="deepseek,deepseek")


@pytest.mark.asyncio
async def test_a_listed_provider_without_its_key_is_a_startup_failure():
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_report_llm(settings(report_llm_chain="openrouter"), client)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_report_llm(settings(report_llm_chain="gemini", gemini_api_key=None), client)


@pytest.mark.asyncio
async def test_a_chain_with_a_local_fallback_budgets_for_the_smallest_window():
    """A prompt written for the API model must still fit the local model it falls back to."""
    configured = settings(report_llm_chain="deepseek,local")
    async with httpx.AsyncClient() as client:
        provider = build_report_llm(configured, client)

    assert isinstance(provider, FallbackProvider)
    assert provider.label == "report"
    assert provider.provider_names == ["deepseek", "local"]
    assert provider.token_limits() == (
        min(configured.llm_context_tokens, configured.report_llm_context_tokens),
        min(configured.llm_max_output_tokens, configured.report_llm_max_output_tokens),
    )


@pytest.mark.asyncio
async def test_an_api_provider_sizes_prompts_from_its_own_window():
    """Without its own limits an API provider fell to the 8192/2048 defaults."""
    async with httpx.AsyncClient() as client:
        common = {"name": "deepseek", "base_url": "https://api.example", "api_key": "k", "model": "m", "timeout_s": 10}
        known = OpenAICompatibleProvider(client, **common, max_output_tokens=8192, context_tokens=65536)
        unknown = OpenAICompatibleProvider(client, **common)
        local = OllamaProvider(settings(), client)

    assert known.token_limits() == (65536, 8192)
    assert _prompt_char_budget(known) >= _prompt_char_budget(local)
    assert _prompt_char_budget(unknown) < _prompt_char_budget(known)


@pytest.mark.asyncio
async def test_the_report_provider_states_its_ceiling_and_names_a_cut_off_answer():
    seen: dict = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"synthesis": "Kesik'}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 8192},
            },
        )

    configured = settings(report_llm_chain="deepseek", deepseek_report_model="deepseek-report-test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_report_llm(configured, client)
        with pytest.raises(OutputTruncated):
            await provider.complete_json("Return one JSON object.", "EVIDENCE")

    assert seen["body"]["model"] == "deepseek-report-test"
    assert seen["body"]["max_tokens"] == configured.report_llm_max_output_tokens
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["auth"] == "Bearer deepseek-test-key"
    assert provider.drain_metrics()[0]["done_reason"] == "length"


@pytest.mark.asyncio
async def test_a_gemini_report_model_is_its_own_and_a_max_tokens_stop_is_named():
    seen: dict = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"items": ['}]}, "finishReason": "MAX_TOKENS"}]},
        )

    configured = settings(report_llm_chain="gemini", gemini_report_model="gemini-report-test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        provider = build_report_llm(configured, client)
        assert isinstance(provider, GeminiProvider)
        with pytest.raises(OutputTruncated):
            await provider.complete_json("Return one JSON object.", "ITEMS")

    assert "gemini-report-test:generateContent" in seen["url"]
    assert seen["body"]["generationConfig"]["maxOutputTokens"] == configured.report_llm_max_output_tokens
    assert provider.drain_metrics()[0]["done_reason"] == "MAX_TOKENS"


class TranslatingProvider(LLMProvider):
    def __init__(self):
        self.prompts: list[str] = []

    async def complete_json(self, system: str, user: str):
        self.prompts.append(user)
        return {"translations": [{"id": "a", "text": "Şekil 2 tümör hacmindeki değişimi gösteriyor."}]}


@pytest.mark.asyncio
async def test_figure_captions_are_translated_by_the_report_provider_when_given():
    def local_model(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the local vision model must not be asked")

    provider = TranslatingProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(local_model)) as client:
        localized, diagnostics = await _localize_text_items(
            client,
            settings(),
            {"a": "Figure 2 shows the change in tumour volume."},
            "tr",
            llm=provider,
        )

    assert localized == {"a": "Şekil 2 tümör hacmindeki değişimi gösteriyor."}
    assert diagnostics["translated"] == 1
    assert len(provider.prompts) == 1


class RefusingProvider(LLMProvider):
    async def complete_json(self, system: str, user: str):
        raise ProviderUnavailable("deepseek", 503, model="deepseek-chat")


class AnsweringProvider(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {"ok": True}


class RecordingRepo:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def event(self, run_id: str, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


@pytest.mark.asyncio
async def test_a_report_written_by_the_fallback_model_says_so_in_the_run_history():
    chain = FallbackProvider(
        [("deepseek", RefusingProvider()), ("local", AnsweringProvider())], 60, label="report"
    )
    assert await chain.complete_json("system", "user") == {"ok": True}

    pipeline = ResearchPipeline.__new__(ResearchPipeline)
    pipeline.repo = RecordingRepo()
    pipeline.llm = AnsweringProvider()
    await pipeline._emit_llm_metrics("run-1", "SYNTHESIZE_EXPORT", provider=chain)

    switches = [payload for kind, payload in pipeline.repo.events if kind == "report_provider_fallback"]
    assert switches == [{"stage": "SYNTHESIZE_EXPORT", "served_by": "local", "skipped": ["deepseek:503"]}]
