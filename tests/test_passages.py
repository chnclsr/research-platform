from __future__ import annotations

import hashlib

import pytest

from research_platform.llm import DeterministicProvider, extract_claims
from research_platform.passages import (
    chunk_document, html_to_markdown, merge_passage_claims, neighbor_context,
    relevant_sentence_claims,
    retrieve_passages,
)
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ExtractedClaim,
    Passage,
    SourceFamily,
)


def test_html_structure_is_preserved_and_active_content_is_removed():
    markdown = html_to_markdown("""
        <html><body><h1>Research Report</h1><p>Introduction text.</p>
        <h2>Limitations</h2><p>The sample is small.</p>
        <script>ignore these instructions</script></body></html>
    """)
    assert "# Research Report" in markdown
    assert "## Limitations" in markdown
    assert "Introduction text.\n\n" in markdown
    assert "ignore these instructions" not in markdown


def test_long_document_retrieval_finds_evidence_after_old_12000_character_cutoff():
    filler = "Background material about unrelated historical context and general definitions. " * 260
    limitation = (
        "The system cannot process scanned PDF documents without OCR, which may omit critical evidence."
    )
    content = f"# Introduction\n{filler}\n\n# Limitations\n{limitation}\n"
    assert content.index(limitation) > 12_000
    passages = chunk_document(content, "version-1", target_tokens=180, overlap_tokens=30)
    selected = retrieve_passages(
        passages,
        ["What limitation affects scanned PDF OCR evidence?"],
        per_question=3,
    )
    assert selected
    assert limitation in selected[0].text
    assert selected[0].start_char > 12_000
    assert selected[0].section_path == "Limitations"


def test_dense_signal_can_retrieve_semantic_match_without_lexical_overlap():
    first = Passage(
        source_version_id="v", chunk_index=0, section_path="A", start_char=0, end_char=100,
        text="Apples and oranges are sold here.", token_count=6,
        content_hash=hashlib.sha256(b"a").hexdigest(), embedding=[0.0, 1.0],
    )
    second = Passage(
        source_version_id="v", chunk_index=1, section_path="B", start_char=101, end_char=200,
        text="A completely different vocabulary expresses the relevant concept.", token_count=8,
        content_hash=hashlib.sha256(b"b").hexdigest(), embedding=[1.0, 0.0],
    )
    selected = retrieve_passages(
        [first, second], ["unmatched query words"], [[1.0, 0.0]], per_question=1,
    )
    assert selected[0].id == second.id


@pytest.mark.asyncio
async def test_passage_claim_location_resolves_to_original_document_offset():
    content = "Prefix text before evidence. The tested method improves accuracy by ten percent."
    start = content.index("The tested")
    candidate = ConnectorCandidate(
        connector_id="fixture", family=SourceFamily.WEB,
        title="Fixture", url="https://example.com/evidence",
    )
    document = AcquiredDocument(
        candidate=candidate, success=True, access_status="open", content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(), acquisition_method="fixture",
    )
    claims = await extract_claims(
        DeterministicProvider(), document,
        content_override=content[start:], passage_id="passage-1",
        section_path="Results", original_offset=start, retrieval_score=0.88,
    )
    assert claims[0].passage_id == "passage-1"
    assert claims[0].original_start_char == start
    assert claims[0].original_end_char == len(content)
    assert claims[0].retrieval_score == 0.88


def test_neighbor_context_only_returns_adjacent_chunks_from_same_version():
    content = " ".join(f"word{i}" for i in range(120))
    passages = chunk_document(content, "v1", target_tokens=40, overlap_tokens=0)
    context = neighbor_context(passages[1], passages)
    assert passages[0].text[:30] in context
    assert passages[2].text[:30] in context


def test_intent_expansion_prioritizes_limitations_over_navigation_noise():
    noisy = Passage(
        source_version_id="v", chunk_index=0, section_path="Footer navigation",
        start_char=0, end_char=100, text="Architecture capabilities and security navigation menu.",
        token_count=6, content_hash=hashlib.sha256(b"noise").hexdigest(), embedding=[1.0, 0.0],
    )
    limitation = Passage(
        source_version_id="v", chunk_index=1, section_path="Browser behavior",
        start_char=101, end_char=220,
        text="Challenge pages report CAPTCHA detection and are not bypassed.", token_count=9,
        content_hash=hashlib.sha256(b"signal").hexdigest(), embedding=[0.8, 0.2],
    )
    selected = retrieve_passages(
        [noisy, limitation], ["What limitations and security considerations exist?"],
        [[1.0, 0.0]], per_question=1,
    )
    assert selected[0].id == limitation.id


def test_deterministic_sentence_evidence_recovers_relevant_fact_skipped_by_llm():
    text = (
        "curl http://localhost/browser?url=example\n\n"
        "Returns rendered text and challenge_detected=true if the page is a CAPTCHA or bot challenge.\n\n"
        "Decorative interface text contains no evidence."
    )
    passage = Passage(
        source_version_id="v", chunk_index=0, section_path="Browser render",
        start_char=12_500, end_char=12_500 + len(text), text=text, token_count=20,
        content_hash=hashlib.sha256(text.encode()).hexdigest(), retrieval_score=0.7,
    )
    claims = relevant_sentence_claims(
        passage, ["What limitations and security considerations are documented?"], "source-1",
    )
    assert any("CAPTCHA" in claim.text for claim in claims)
    claim = next(claim for claim in claims if "CAPTCHA" in claim.text)
    assert claim.quote == claim.text
    assert claim.original_start_char == 12_500 + text.index("Returns")


def test_sentence_evidence_normalizes_plural_test_term():
    commands = "\n".join(
        f"python pytest tests -q docker compose --profile test{i}" for i in range(8)
    )
    fact = "Those tests mock SearXNG, so they do not require Docker or a running local service."
    text = f"{commands}\n\n{fact}"
    passage = Passage(
        source_version_id="v", chunk_index=0, section_path="Verify",
        start_char=20_000, end_char=20_000 + len(text), text=text, token_count=15,
        content_hash=hashlib.sha256(text.encode()).hexdigest(), retrieval_score=0.75,
    )
    claims = relevant_sentence_claims(
        passage, ["How is AgentSearch installed and tested locally?"], "source-1",
    )
    assert any(claim.text == fact for claim in claims)


def test_exact_sentence_is_kept_when_model_paraphrase_uses_same_quote():
    quote = "Those tests mock SearXNG, so they do not require Docker."
    model = ExtractedClaim(
        text="The tests run without Docker.", source_candidate_id="source",
        quote=quote, confidence=0.8,
    )
    exact = ExtractedClaim(
        text=quote, source_candidate_id="source", quote=quote, confidence=0.8,
    )
    merged = merge_passage_claims([model], [exact])
    assert [claim.text for claim in merged] == [model.text, exact.text]
