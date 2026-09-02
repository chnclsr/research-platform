from unittest.mock import AsyncMock

from research_platform.pipeline import ResearchPipeline
from research_platform.schemas import ResearchProtocol


class FakeRepository:
    def __init__(self) -> None:
        self.saved = []
        self.events = []

    async def list_claims(self, run_id):
        return []

    async def list_evidence(self, run_id):
        return []

    async def save_claims(self, run_id, claims):
        self.saved = claims

    async def update_run(self, run_id, **values):
        return None

    async def event(self, run_id, event_type, payload):
        self.events.append((event_type, payload))


class FakeEmbeddings:
    async def embed(self, texts):
        return [[1.0, 0.0], [0.995, 0.1]][: len(texts)]

    def drain_metrics(self):
        return []


class FailingEmbeddings(FakeEmbeddings):
    async def embed(self, texts):
        raise TimeoutError("embedding unavailable")


async def test_pipeline_merges_semantic_claims_and_preserves_both_evidence_inputs() -> None:
    pipeline = object.__new__(ResearchPipeline)
    pipeline.repo = FakeRepository()
    pipeline.embeddings = FakeEmbeddings()
    pipeline._boundary = AsyncMock()
    protocol = ResearchProtocol(
        title="Semantic claim deduplication",
        primary_question="Does surgery improve NOSE scores and turbinate size?",
        budget={"max_wall_minutes": 30},
    )
    claims = [
        {
            "text": "Surgery improved turbinate size and NOSE scores compared with conservative treatment.",
            "source_candidate_id": "source-1",
            "quote": "Surgery improved turbinate size and NOSE scores compared with conservative treatment.",
            "passage_id": "passage-1",
            "source_version_id": "version-1",
        },
        {
            "text": "Compared with conservative treatment, surgery yielded better NOSE scores and turbinate size.",
            "source_candidate_id": "source-2",
            "quote": "Compared with conservative treatment, surgery yielded better NOSE scores and turbinate size.",
            "passage_id": "passage-2",
            "source_version_id": "version-2",
        },
    ]

    result = await pipeline.analyze_claims(
        {
            "run_id": "01DEDUPTEST",
            "protocol": protocol.model_dump(mode="json"),
            "claims": claims,
            "documents": [],
            "sub_questions": [],
        }
    )

    assert len(pipeline.repo.saved) == 2
    assert pipeline.repo.saved[0][0].id == pipeline.repo.saved[1][0].id
    assert {version for _, version in pipeline.repo.saved} == {"version-1", "version-2"}
    diagnostic = next(payload for event, payload in pipeline.repo.events if event == "claim_deduplication")
    assert diagnostic["merged_count"] == 1
    assert diagnostic["signals"] == {"embedding_and_words": 1}
    assert len(result["claims"]) == 2


async def test_pipeline_uses_lexical_dedup_when_embeddings_fail() -> None:
    pipeline = object.__new__(ResearchPipeline)
    pipeline.repo = FakeRepository()
    pipeline.embeddings = FailingEmbeddings()
    pipeline._boundary = AsyncMock()
    protocol = ResearchProtocol(
        title="Lexical claim deduplication",
        primary_question="Does surgery improve the measured score?",
        budget={"max_wall_minutes": 30},
    )
    claims = [
        {
            "text": "Surgery significantly improved the measured clinical score.",
            "source_candidate_id": "source-1",
            "quote": "Surgery significantly improved the measured clinical score.",
            "source_version_id": "version-1",
        },
        {
            "text": "The measured clinical score significantly improved with surgery.",
            "source_candidate_id": "source-2",
            "quote": "The measured clinical score significantly improved with surgery.",
            "source_version_id": "version-2",
        },
    ]

    await pipeline.analyze_claims(
        {
            "run_id": "01LEXICALTEST",
            "protocol": protocol.model_dump(mode="json"),
            "claims": claims,
            "documents": [],
            "sub_questions": [],
        }
    )

    assert pipeline.repo.saved[0][0].id == pipeline.repo.saved[1][0].id
    assert any(
        event == "embedding_fallback" and payload["stage"] == "claim_deduplication"
        for event, payload in pipeline.repo.events
    )
