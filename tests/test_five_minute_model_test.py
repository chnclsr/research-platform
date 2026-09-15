import json

import pytest

from scripts import run_five_minute_model_test as benchmark
from scripts.run_five_minute_model_test import (
    BM25,
    planning_user_prompt,
    reciprocal_rank_fusion,
    retrieval_metrics,
    safe_plan,
    tokenize,
)


def corpus():
    return {
        "documents": [
            {
                "id": "D1",
                "title": "Controlled study",
                "text": "causal productivity control",
                "source_type": "study",
            },
            {
                "id": "D2",
                "title": "Unrelated",
                "text": "tourism weather",
                "source_type": "study",
            },
            {
                "id": "D3",
                "title": "Counter evidence",
                "text": "productivity null result",
                "source_type": "study",
            },
        ],
        "relevant_document_ids": ["D1", "D3"],
        "critical_document_ids": ["D1"],
        "counter_evidence_ids": ["D3"],
    }


def test_bm25_and_rrf_are_deterministic():
    engine = BM25(corpus()["documents"])
    rankings = [
        engine.search("causal productivity"),
        engine.search("productivity null"),
    ]
    first = reciprocal_rank_fusion(rankings)
    second = reciprocal_rank_fusion(rankings)
    assert first == second
    assert {row["document_id"] for row in first} == {"D1", "D3"}


def test_retrieval_metrics_keep_objective_categories_separate():
    ranking = [
        {"document_id": "D1"},
        {"document_id": "D2"},
        {"document_id": "D3"},
    ]
    metrics = retrieval_metrics(corpus(), ranking)
    assert metrics["relevant_recall"] == 1.0
    assert metrics["critical_recall"] == 1.0
    assert metrics["counter_evidence_recall"] == 1.0
    assert metrics["precision"] == 0.6667
    assert metrics["first_relevant_rank"] == 1


def test_turkish_words_remain_whole_without_turning_into_english_words():
    assert tokenize("Çalışanların refahı ve iş yoğunlaştırma") == [
        "çalışanların",
        "refahı",
        "ve",
        "iş",
        "yoğunlaştırma",
    ]
    assert tokenize("İŞ IŞIK AI Implementation") == [
        "iş",
        "ışık",
        "ai",
        "implementation",
    ]
    assert tokenize("iş") != tokenize("is")


def test_stopwords_and_turkish_words_cannot_create_fake_english_matches():
    engine = BM25(corpus()["documents"])
    assert engine.search("is and the") == []
    assert engine.search("iş") == []
    assert engine.search("causal productivity")


def test_unusable_or_turkish_plans_skip_retrieval_instead_of_searching_the_question():
    for call in (
        {"status": "ok", "content": '{"queries": ["unfinished"'},
        {"status": "ok", "content": '{"queries": "causal productivity"}'},
        {"status": "ok", "content": '{"queries": ["iş yoğunlaştırma"]}'},
        {"status": "timeout", "content": '{"queries": ["causal productivity"]}'},
    ):
        plan, failed = safe_plan(call)
        assert failed is True
        assert plan["queries"] == []
        ranking, per_query = benchmark.retrieve(corpus(), plan["queries"])
        assert ranking == per_query == []

    turkish_plan, _ = safe_plan({"status": "ok", "content": '{"queries": ["iş yoğunlaştırma"]}'})
    assert "English corpus language" in turkish_plan["risks"][0]

    plan, failed = safe_plan(
        {
            "status": "ok",
            "content": '{"queries": ["causal productivity", "causal productivity"]}',
        }
    )
    assert failed is False
    assert plan["queries"] == ["causal productivity"]


def test_the_locked_english_corpus_does_not_fake_match_the_turkish_question():
    locked = json.loads(benchmark.DEFAULT_CORPUS.read_text(encoding="utf-8"))
    ranking, per_query = benchmark.retrieve(locked, [locked["question"]])
    assert ranking == []
    assert per_query == [[]]
    assert retrieval_metrics(locked, ranking)["relevant_recall"] == 0.0


def test_planning_prompt_requires_queries_in_the_corpus_language():
    prompt = planning_user_prompt("Türkçe araştırma sorusu")
    assert "yalnız İNGİLİZCE arama sorgusu" in prompt
    assert "korpusu İngilizcedir" in prompt
    assert "İngilizce veya Türkçe" not in prompt


@pytest.mark.asyncio
async def test_an_invalid_plan_never_sends_empty_documents_to_evidence_analysis(
    monkeypatch,
):
    phases = []

    class SilentGPU:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def summary(self):
            return {"sample_count": 0}

    async def fake_chat(*_, phase, user, **__):
        phases.append(phase)
        if phase == "planning":
            return {"phase": phase, "status": "ok", "content": "{"}
        assert phase == "synthesis"
        assert "Hiç belge getirilemedi; bu testte kanıt yok." in user
        return {"phase": phase, "status": "ok", "content": "Kanıt bulunamadı."}

    monkeypatch.setattr(benchmark, "GPUMonitor", SilentGPU)
    monkeypatch.setattr(benchmark, "stop_loaded_models", lambda: None)
    monkeypatch.setattr(benchmark, "ollama_ps", lambda: "")
    monkeypatch.setattr(benchmark, "chat", fake_chat)

    result = await benchmark.run_model(
        benchmark.PROFILES[0],
        {"question": "Türkçe soru", **corpus()},
        "http://ollama.invalid",
    )
    assert phases == ["planning", "synthesis"]
    assert result["research"]["retrieval_status"] == "skipped_unusable_plan"
    assert result["research"]["retrieval_metrics"]["retrieved_document_ids"] == []
    assert result["research"]["search_language"] == "en"
    assert result["research"]["retrieval_contract_version"] == "1.1"
    blind = benchmark.blind_payload(result)
    assert blind["retrieval_status"] == "skipped_unusable_plan"
    assert blind["retrieval_contract_version"] == "1.1"


@pytest.mark.asyncio
async def test_a_valid_english_plan_still_reaches_evidence_and_audit(monkeypatch):
    phases = []

    class SilentGPU:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def summary(self):
            return {"sample_count": 0}

    async def fake_chat(*_, phase, user, **__):
        phases.append(phase)
        if phase == "planning":
            content = '{"queries": ["causal productivity"]}'
        else:
            if phase == "evidence_analysis":
                assert "[D1] Controlled study" in user
            content = "{}"
        return {"phase": phase, "status": "ok", "content": content}

    monkeypatch.setattr(benchmark, "GPUMonitor", SilentGPU)
    monkeypatch.setattr(benchmark, "stop_loaded_models", lambda: None)
    monkeypatch.setattr(benchmark, "ollama_ps", lambda: "")
    monkeypatch.setattr(benchmark, "chat", fake_chat)

    result = await benchmark.run_model(
        benchmark.PROFILES[0],
        {"question": "Which studies address productivity?", **corpus()},
        "http://ollama.invalid",
    )
    assert phases == ["planning", "evidence_analysis", "adversarial_audit", "synthesis"]
    assert result["research"]["retrieval_status"] == "matched"
    assert result["research"]["retrieval_metrics"]["retrieved_document_ids"]
