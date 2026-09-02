from research_platform.text_similarity import claim_duplicate_reason, prose_overlaps


def test_semantic_claim_dedup_catches_reordered_paraphrase() -> None:
    left = "Surgery improved turbinate size and NOSE scores versus conservative treatment."
    right = "Compared with conservative treatment, surgery yielded better NOSE scores and turbinate size."

    reason, _ = claim_duplicate_reason(
        left,
        right,
        left_vector=[1.0, 0.0],
        right_vector=[0.99, 0.1],
    )

    assert reason == "embedding_and_words"


def test_claim_dedup_does_not_merge_changed_number_or_negation() -> None:
    assert claim_duplicate_reason("The score improved by 10%.", "The score improved by 20%.")[0] == ""
    assert claim_duplicate_reason("The score improved.", "The score did not improve.")[0] == ""


def test_reader_visible_overlap_gate_combines_word_and_phrase_similarity() -> None:
    assert prose_overlaps(
        "Cerrahi müdahale konservatif tedaviye göre NOSE skorlarını iyileştirdi.",
        "Cerrahi müdahale konservatif tedaviye göre NOSE skorlarını belirgin biçimde iyileştirdi.",
    )
