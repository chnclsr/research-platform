from scripts.run_five_minute_model_test import BM25, reciprocal_rank_fusion, retrieval_metrics


def corpus():
    return {
        "documents": [
            {"id": "D1", "title": "Controlled study", "text": "causal productivity control"},
            {"id": "D2", "title": "Unrelated", "text": "tourism weather"},
            {"id": "D3", "title": "Counter evidence", "text": "productivity null result"},
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
