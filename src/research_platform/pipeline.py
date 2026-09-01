from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, TypedDict
from urllib.parse import urlparse

import httpx
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from .acquisition import AcquisitionService
from .auth import Principal
from .config import Settings
from .connectors import build_registry
from .coverage import calculate_coverage
from .db import SessionLocal
from .discovery_quality import estimated_completeness, relation_to_candidate, sentinel_recall
from .embeddings import EmbeddingClient
from .evidence_quality import evidence_quality_gate, is_non_evidence_section
from .exporter import build_exports
from .hardware_telemetry import TelemetryHub
from .llm import (
    FallbackProvider,
    LLMProvider,
    build_llm,
    build_preparation_llm,
    decompose,
    extract_claims,
    generate_search_queries,
    planning_choices,
    research_label,
    translate_research_request,
)
from .normalization import canonicalize_url, detect_language
from .paperqa_adapter import PaperQA2EvidenceEngine
from .passages import (
    chunk_document,
    merge_passage_claims,
    neighbor_context,
    passage_payload,
    relevant_sentence_claims,
    retrieve_passages,
)
from .protocol_synthesis import synthesize_source_selection
from .query_compiler import compile_provider_query
from .recovery import (
    diagnose_gaps,
    initial_missions,
    literature_scan_probe_missions,
    matches_target_entities,
    mission_signature,
    recovery_missions,
    resolve_official_entities,
    select_mission_balanced_candidates,
)
from .relevance import (
    claim_relevance,
    classify_candidate_admission,
    document_relevance,
    domain_matches,
    filter_and_rank_candidates,
    temporal_relevance,
)
from .repository import Repository
from .research_plan import build_research_plan, plan_display_and_strategy, plan_strategy
from .schemas import (
    AcquiredDocument,
    AuthorityLevel,
    ConnectorCandidate,
    CoverageGap,
    CoverageMetrics,
    ExtractedClaim,
    Passage,
    ResearchProtocol,
    RunStatus,
    SearchMission,
    SourceFamily,
    new_id,
)
from .scholarly import candidate_dedupe_key
from .scoping import (
    LABEL_MAX_LENGTH,
    apply_planning_answers,
    date_suffix,
    feedback_answers,
    fixed_questions,
    slugify,
)
from .storage import ObjectStore
from .temporal import constrain_text_to_scope, enrich_publication_date

# Used when the model cannot produce usable scoping options. The checkpoint worked with
# plain questions before options existed, so losing the tailored wording is not a reason to
# skip asking.
FALLBACK_PLANNING_QUESTIONS = {
    "tr": [
        "Araştırmanın coğrafi veya kurumsal kapsamı ne olmalı?",
        "Öncelikli kaynak türleri ve özellikle dışlanacak kaynaklar var mı?",
        "Sonuç hangi kararı desteklemeli veya hangi belirsizliği çözmeli?",
    ],
    "en": [
        "What geographic or institutional scope should the research cover?",
        "Which kinds of sources matter most, and which should be left out?",
        "Which decision should the result support, or which uncertainty resolve?",
    ],
}


class PipelineState(TypedDict, total=False):
    run_id: str
    protocol: dict[str, Any]
    sub_questions: list[str]
    concepts: list[str]
    queries: list[str]
    missions: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    attempted_missions: list[str]
    required_branch_ids: list[str]
    branch_queries: dict[str, str]
    round_number: int
    candidates: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    corpus_documents: list[dict[str, Any]]
    passages: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    branch_result_counts: dict[str, int]
    source_count_before_round: int
    coverage: dict[str, Any]
    stop_reason: str
    # VALIDATE_PROTOCOL is re-entered when a checkpoint sends the run back; this is what
    # stops the source synthesis from being paid for twice.
    synthesis_done: bool
    started_monotonic: float
    halted: bool
    discovery_stats: dict[str, Any]
    unavailable_connectors: list[str]
    available_connectors: list[str]
    connector_success_rates: dict[str, float]
    round_new_source_versions: int
    consecutive_empty_recovery_rounds: int
    budget_started_at: str
    planning_answers: list[str]
    applied_settings: list[dict[str, Any]]
    plan_feedback: list[str]
    # Fingerprints of what the preparation calls read. A checkpointed run re-enters at
    # DECOMPOSE after every answer, and without these the same question would be
    # decomposed and re-queried from scratch on each pass -- including the approval pass,
    # whose inputs are identical to the pass the user just approved.
    decompose_signature: str
    generated_queries: list[str]
    query_signature: str
    report_outline_guidance: str
    invocation_source: str


class PipelineHalted(RuntimeError):
    pass


def preparation_signature(*parts: Any) -> str:
    """A stable fingerprint of everything one preparation call reads.

    Reused output is only correct while the inputs are unchanged, so the fingerprint has to
    cover every value that reaches the prompt -- the question, the user's steering and the
    date scope the answers can move.
    """
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class PipelineStageTimeout(RuntimeError):
    pass


class ResearchPipeline:
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        client: httpx.AsyncClient,
        telemetry: TelemetryHub | None = None,
    ):
        self.settings = settings
        self.session = session
        # The pipeline executes runs on behalf of whoever owns them, so it needs
        # access to any run in the queue. Corpus reads are still scoped to the
        # run's owner -- see Repository._corpus_scope_owner.
        self.repo = Repository(session, actor=Principal.system())
        self.client = client
        self.registry = build_registry(settings, client)
        self.acquisition = AcquisitionService(settings, client)
        self.llm: LLMProvider = build_llm(settings, client)
        self.preparation_llm = build_preparation_llm(settings, client)
        self._telegram_preparation = False
        self.embeddings = EmbeddingClient(settings, client)
        self.store = ObjectStore(settings)
        self.telemetry = telemetry
        self.graph = self._build_graph()

    def _preparation_provider(self) -> LLMProvider:
        if self._telegram_preparation and self.preparation_llm is not None:
            return self.preparation_llm
        return self.llm

    def _build_graph(self):
        graph = StateGraph(PipelineState)
        graph.add_node("VALIDATE_PROTOCOL", self.validate_protocol)
        graph.add_node("DECOMPOSE", self.decompose_question)
        graph.add_node("BUILD_QUERY_BRANCHES", self.build_query_branches)
        graph.add_node("SEARCH", self.search)
        graph.add_node("ACQUIRE", self.acquire)
        graph.add_node("NORMALIZE", self.normalize)
        graph.add_node("CHUNK_INDEX", self.chunk_index)
        graph.add_node("RETRIEVE_PASSAGES", self.retrieve_relevant_passages)
        graph.add_node("EXTRACT_EVIDENCE", self.extract_evidence)
        graph.add_node("ANALYZE_CLAIMS", self.analyze_claims)
        graph.add_node("CHECK_COVERAGE", self.check_coverage)
        graph.add_node("PLAN_RECOVERY", self.plan_recovery)
        graph.add_node("AUDIT", self.audit)
        graph.add_node("ADVERSARIAL_REVIEW", self.adversarial_review)
        graph.add_node("SYNTHESIZE_EXPORT", self.synthesize_export)
        graph.add_edge(START, "VALIDATE_PROTOCOL")
        graph.add_edge("VALIDATE_PROTOCOL", "DECOMPOSE")
        graph.add_edge("DECOMPOSE", "BUILD_QUERY_BRANCHES")
        graph.add_edge("BUILD_QUERY_BRANCHES", "SEARCH")
        graph.add_edge("SEARCH", "ACQUIRE")
        graph.add_edge("ACQUIRE", "NORMALIZE")
        graph.add_edge("NORMALIZE", "CHUNK_INDEX")
        graph.add_edge("CHUNK_INDEX", "RETRIEVE_PASSAGES")
        graph.add_edge("RETRIEVE_PASSAGES", "EXTRACT_EVIDENCE")
        graph.add_edge("EXTRACT_EVIDENCE", "ANALYZE_CLAIMS")
        graph.add_edge("ANALYZE_CLAIMS", "AUDIT")
        graph.add_edge("AUDIT", "CHECK_COVERAGE")
        graph.add_conditional_edges(
            "CHECK_COVERAGE",
            self._coverage_route,
            {"expand": "PLAN_RECOVERY", "finish": "ADVERSARIAL_REVIEW", "halt": END},
        )
        graph.add_edge("PLAN_RECOVERY", "SEARCH")
        graph.add_edge("ADVERSARIAL_REVIEW", "SYNTHESIZE_EXPORT")
        graph.add_edge("SYNTHESIZE_EXPORT", END)
        return graph.compile()

    async def _boundary(self, state: PipelineState, stage: str) -> None:
        if self.telemetry is not None:
            # Mark the work that is about to begin, including checkpoint serialization.
            # The hardware sample is shared, but this stage label belongs only to this run.
            self.telemetry.set_stage(state["run_id"], stage)
        run = await self.repo.get_run(state["run_id"])
        if run is None:
            raise KeyError(state["run_id"])
        if run.status == RunStatus.PAUSED.value:
            await self.repo.event(run.id, "paused", {"stage": stage})
            raise PipelineHalted("paused")
        if run.status in {RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLED.value}:
            await self.repo.update_run(run.id, status=RunStatus.CANCELLED.value)
            await self.repo.event(run.id, "cancelled", {"stage": stage})
            raise PipelineHalted("cancelled")
        await self.repo.checkpoint(run.id, stage, dict(state))
        await self.repo.event(
            run.id, "stage", {"stage": stage, "round": state.get("round_number", 0)}
        )

    @staticmethod
    def _collection_seconds_remaining(state: PipelineState) -> float:
        protocol = ResearchProtocol.model_validate(state["protocol"])
        started_at = datetime.fromisoformat(
            state.get("budget_started_at", datetime.now(timezone.utc).isoformat()).replace(
                "Z", "+00:00"
            )
        )
        elapsed = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
        return protocol.budget.max_wall_minutes * 60 - elapsed

    async def _hitl_response(self, run_id: str, interaction_type: str) -> dict | None:
        run = await self.repo.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        for entry in reversed(run.hitl_history or []):
            if entry.get("type") == interaction_type:
                response = entry.get("response")
                return response if isinstance(response, dict) else {}
        return None

    async def _hitl_entries(self, run_id: str, interaction_type: str) -> list[dict]:
        """Every answered interaction of one type, oldest first.

        `_hitl_response` returns only the last answer, which is all the single-shot gates
        need. The plan gate has to count rejections across rounds, so it needs the series.
        """
        run = await self.repo.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return [
            entry
            for entry in (run.hitl_history or [])
            if entry.get("type") == interaction_type
        ]

    async def _request_input(
        self,
        state: PipelineState,
        interaction_type: str,
        data: dict[str, Any],
        checkpoint_stage: str,
        timeout_minutes: int = 5,
    ) -> None:
        """Park the run on a durable checkpoint and hand control to the user.

        Split out of `_maybe_hitl` because the plan gate must be able to ask again after a
        rejection, while `_maybe_hitl` deliberately replays the first answer forever.
        """
        now = datetime.now(timezone.utc)
        interaction = {
            "interaction_id": new_id(),
            "type": interaction_type,
            "data": data,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=timeout_minutes)).isoformat(),
        }
        await self.repo.checkpoint(state["run_id"], checkpoint_stage, dict(state))
        await self.repo.update_run(
            state["run_id"],
            status=RunStatus.AWAITING_INPUT.value,
            interaction=interaction,
        )
        await self.repo.event(state["run_id"], "hitl_awaiting_input", interaction)
        raise PipelineHalted("awaiting_input")

    async def _maybe_hitl(
        self,
        state: PipelineState,
        interaction_type: str,
        data: dict[str, Any],
        checkpoint_stage: str,
    ) -> dict | None:
        protocol = ResearchProtocol.model_validate(state["protocol"])
        if not getattr(protocol.hitl, interaction_type):
            return None
        previous = await self._hitl_response(state["run_id"], interaction_type)
        if previous is not None:
            return previous
        await self._request_input(state, interaction_type, data, checkpoint_stage)
        return None

    async def _plan_feedback(self, run_id: str) -> list[str]:
        """What the user asked to change, read from the answers rather than from state.

        The checkpoint is written before the rejection it is waiting for exists, so state
        always trails by one round; the answer history is the only current source.
        """
        notes = []
        for entry in await self._hitl_entries(run_id, "plan_review"):
            response = entry.get("response")
            if not isinstance(response, dict) or response.get("approved"):
                continue
            note = str(response.get("modifications", "")).strip()
            if note:
                notes.append(note)
        return notes

    async def _apply_plan_duration(
        self,
        run_id: str,
        state: PipelineState,
        protocol: ResearchProtocol,
        minutes: int,
    ) -> None:
        """Persist a duration the user changed while approving the plan.

        The resumed run reads its protocol from the row (`run()`), and the panel reads it
        from there too, so the new budget has to land in the database -- not only in the
        in-memory state.
        """
        if minutes == protocol.budget.max_wall_minutes:
            return
        payload = protocol.model_dump(mode="json")
        previous = payload["budget"]["max_wall_minutes"]
        payload["budget"]["max_wall_minutes"] = minutes
        state["protocol"] = ResearchProtocol.model_validate(payload).model_dump(mode="json")
        await self.repo.update_run(run_id, protocol=state["protocol"])
        await self.repo.event(
            run_id,
            "plan_duration_changed",
            {"from_minutes": previous, "to_minutes": minutes},
        )

    async def _plan_gate(
        self,
        state: PipelineState,
        output: dict[str, Any],
        protocol: ResearchProtocol,
    ) -> dict[str, Any]:
        """Nothing is searched until somebody has seen what the run intends to do.

        Unlike the other checkpoints this one can ask repeatedly: a rejection carries
        feedback, the run rewinds to DECOMPOSE, and the questions and queries are rebuilt
        with that feedback before the plan is presented again.
        """
        run_id = state["run_id"]
        if not protocol.hitl.plan_review:
            await self.repo.event(
                run_id,
                "plan_skipped",
                {"reason": "plan_review disabled by the caller"},
            )
            return output
        answered = [
            entry
            for entry in await self._hitl_entries(run_id, "plan_review")
            if isinstance(entry.get("response"), dict)
        ]
        latest = answered[-1]["response"] if answered else None
        if latest is not None and latest.get("approved"):
            minutes = latest.get("max_wall_minutes")
            if isinstance(minutes, int):
                await self._apply_plan_duration(run_id, state, protocol, minutes)
            await self.repo.event(
                run_id,
                "research_plan_approved",
                {"revisions": len(answered) - 1},
            )
            return output
        feedback = await self._plan_feedback(run_id)
        if len(answered) >= self.settings.plan_max_revisions:
            await self.repo.update_run(run_id, status=RunStatus.CANCELLED.value)
            await self.repo.event(
                run_id,
                "plan_rejection_limit",
                {"revisions": len(answered), "feedback": feedback},
            )
            raise PipelineHalted("plan_rejected")
        planning_state = {**state, **output, "plan_feedback": feedback}
        # The approval screen speaks the language the request arrived in. This is display
        # only: the English strings the plan describes are the ones the run will use.
        language = protocol.display_language()
        plan = build_research_plan(
            protocol=protocol,
            state=planning_state,
            settings=self.settings,
        )
        if language == "en":
            # Nothing to translate, so the note is the only thing left to ask for.
            plan["strategy_note"] = await plan_strategy(
                self._preparation_provider(), plan, language
            )
        else:
            # One request for both halves of the approval screen. Each half still fails on
            # its own: a missing translation leaves the operational English list, a missing
            # note leaves the plan without one, and neither holds the gate shut.
            display_subs, note = await plan_display_and_strategy(
                self._preparation_provider(),
                plan,
                list(planning_state.get("sub_questions", [])),
                language,
            )
            plan["questions"]["sub_questions_display"] = display_subs
            plan["strategy_note"] = note
        await self._emit_llm_metrics(
            run_id, "PLAN", provider=self._preparation_provider()
        )
        await self.repo.event(run_id, "research_plan", plan)
        await self._request_input(
            planning_state,
            "plan_review",
            {"plan": plan},
            "DECOMPOSE",
            self.settings.hitl_plan_timeout_minutes,
        )
        return output

    async def _emit_llm_metrics(
        self,
        run_id: str,
        stage: str,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        target = provider or self.llm
        metrics = target.drain_metrics()
        if metrics:
            await self.repo.event(run_id, "llm_metrics", {"stage": stage, "calls": metrics})
        if isinstance(target, FallbackProvider):
            # A run planned by the second-choice model has to say so in its own history;
            # the llm_metrics rows name the model but not that a switch happened.
            for switch in target.drain_fallbacks():
                await self.repo.event(
                    run_id, "preparation_provider_fallback", {"stage": stage, **switch}
                )

    async def _interruptible(
        self,
        awaitable,
        state: PipelineState,
        stage: str,
        timeout_s: float,
    ):
        """Wait for node I/O while observing pause/cancel and a hard deadline."""
        task = asyncio.ensure_future(awaitable)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        poll_s = self.settings.pipeline_control_poll_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                task.cancel()
                async with SessionLocal() as control_session:
                    await Repository(control_session, actor=Principal.system()).event(
                        state["run_id"],
                        "stage_timeout",
                        {"stage": stage, "timeout_seconds": timeout_s},
                    )
                raise PipelineStageTimeout(
                    f"{stage} exceeded its {timeout_s:g} second safety limit"
                )
            done, _ = await asyncio.wait({task}, timeout=min(poll_s, remaining))
            if task in done:
                return task.result()

            # The node may be using the pipeline session at the same moment. A
            # dedicated control session avoids concurrent AsyncSession access.
            async with SessionLocal() as control_session:
                control_repo = Repository(control_session, actor=Principal.system())
                run = await control_repo.get_run(state["run_id"])
                if run is None:
                    task.cancel()
                    raise KeyError(state["run_id"])
                if run.status == RunStatus.PAUSED.value:
                    task.cancel()
                    await control_repo.event(
                        run.id,
                        "paused",
                        {"stage": stage, "in_node": True},
                    )
                    raise PipelineHalted("paused")
                if run.status in {RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLED.value}:
                    task.cancel()
                    await control_repo.update_run(run.id, status=RunStatus.CANCELLED.value)
                    await control_repo.event(
                        run.id,
                        "cancelled",
                        {"stage": stage, "in_node": True},
                    )
                    raise PipelineHalted("cancelled")

    async def run(self, run_id: str) -> None:
        row = await self.repo.get_run(run_id)
        if row is None:
            raise KeyError(run_id)
        self._telegram_preparation = (
            (row.state or {}).get("invocation_source") == "telegram"
        )
        if row.status in {RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLED.value}:
            await self.repo.update_run(run_id, status=RunStatus.CANCELLED.value)
            await self.repo.event(
                run_id,
                "cancelled",
                {"stage": row.current_stage, "before_start": True},
            )
            return
        await self.repo.update_run(run_id, status=RunStatus.RUNNING.value, error=None)
        state: PipelineState = {
            "run_id": run_id,
            "protocol": row.protocol,
            "round_number": row.round_number,
            "started_monotonic": time.monotonic(),
            "coverage": row.coverage or {},
            "invocation_source": (row.state or {}).get("invocation_source", "api"),
        }
        checkpoint = await self.repo.latest_checkpoint(run_id)
        if checkpoint and row.status == RunStatus.RUNNING.value:
            state.update(checkpoint.state)
            state["run_id"] = run_id
            state["protocol"] = row.protocol
            state["started_monotonic"] = time.monotonic()
        state.setdefault("budget_started_at", datetime.now(timezone.utc).isoformat())
        try:
            protocol = ResearchProtocol.model_validate(row.protocol)
            # A literature scan can intentionally keep expanding until its
            # wall-clock or source budget is exhausted.  The fixed LangGraph
            # default previously killed such runs after roughly six rounds,
            # long before the user-selected duration elapsed.
            recursion_limit = max(
                self.settings.graph_recursion_min,
                min(
                    self.settings.graph_recursion_max,
                    self.settings.graph_recursion_min
                    + protocol.budget.max_wall_minutes
                    * self.settings.graph_recursion_per_wall_minute,
                ),
            )
            result = await self.graph.ainvoke(
                state,
                {"recursion_limit": recursion_limit},
            )
            if result.get("halted"):
                return
            coverage = CoverageMetrics.model_validate(result.get("coverage", {}))
            status = RunStatus.COMPLETED if coverage.sufficient else RunStatus.COMPLETED_INCOMPLETE
            await self.repo.update_run(
                run_id,
                status=status.value,
                current_stage="COMPLETE",
                coverage=coverage.model_dump(),
            )
            await self.repo.event(run_id, "complete", {"status": status.value})
        except PipelineHalted:
            return
        except Exception as exc:
            await self.session.rollback()
            await self.repo.update_run(
                run_id,
                status=RunStatus.FAILED.value,
                current_stage="FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )
            await self.repo.event(run_id, "failed", {"error": f"{type(exc).__name__}: {exc}"})
            raise

    async def validate_protocol(self, state: PipelineState) -> dict:
        await self._boundary(state, "VALIDATE_PROTOCOL")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        protocol, suggested_label = await self._to_research_language(
            state["run_id"], protocol
        )
        protocol = await self._name_run(state["run_id"], protocol, suggested_label)
        protocol, synthesized = await self._synthesize_sources(state, protocol)
        output = {"protocol": protocol.model_dump(mode="json")}
        if synthesized:
            output["synthesis_done"] = True
        return output

    async def _synthesize_sources(
        self,
        state: PipelineState,
        protocol: ResearchProtocol,
    ) -> tuple[ResearchProtocol, bool]:
        """Pick the source families this question needs, when nobody else has.

        Four conditions, and each one closes a way of overwriting a decision that was
        already made. The flag keeps it off by default. `selection_source` is the only
        thing that separates an untouched default from an explicit answer, since the two
        carry identical fields. `planning_questions` matters because the scoping gate runs
        later, in DECOMPOSE, and its answer overwrites the family list -- synthesising
        first would spend a call on a value about to be replaced. And VALIDATE_PROTOCOL is
        re-entered when a checkpoint sends the run back, so the work is done once.
        """
        if not (
            self.settings.protocol_source_synthesis_enabled
            and protocol.connectors.selection_source == "default"
            and protocol.hitl.planning_questions is False
            and state.get("synthesis_done") is not True
        ):
            return protocol, False
        updated, event = await synthesize_source_selection(
            self._preparation_provider(), protocol
        )
        await self._emit_llm_metrics(
            state["run_id"], "VALIDATE_PROTOCOL", provider=self._preparation_provider()
        )
        if event is None:
            return protocol, False
        await self.repo.update_run(
            state["run_id"], protocol=updated.model_dump(mode="json")
        )
        await self.repo.event(state["run_id"], "protocol_synthesis", event)
        return updated, True

    async def _name_run(
        self,
        run_id: str,
        protocol: ResearchProtocol,
        suggested: str = "",
    ) -> ResearchProtocol:
        """Give the run a short topic handle for chat clients to print instead of a ULID.

        Done after translation so the label is English whichever language the question
        arrived in -- and taken from the translation itself when that call already named the
        topic, because a second request for four words is a request this stage spends
        against an external quota for nothing. A cosmetic field either way: if the model is
        unreachable or answers with something unusable, the question itself is slugified and
        the run carries on.
        """
        if protocol.label:
            return protocol
        answer = suggested
        if not answer:
            try:
                answer = await research_label(
                    self._preparation_provider(), protocol.primary_question
                )
            except Exception:
                answer = ""
            finally:
                await self._emit_llm_metrics(
                    run_id, "VALIDATE_PROTOCOL", provider=self._preparation_provider()
                )
        label = slugify(answer, max_length=LABEL_MAX_LENGTH) or slugify(
            protocol.primary_question, max_length=LABEL_MAX_LENGTH
        )
        label += date_suffix(protocol)
        if not label:
            return protocol
        payload = protocol.model_dump(mode="json")
        payload["label"] = label[:64]
        await self.repo.update_run(run_id, protocol=payload)
        return ResearchProtocol.model_validate(payload)

    async def _record_request_language(
        self,
        run_id: str,
        protocol: ResearchProtocol,
        language: str,
    ) -> ResearchProtocol:
        """Remember which language the request arrived in, even when nothing was translated.

        The approval screen is rendered in that language, so it has to be known on every
        path -- including the ones where the question was already English or the
        translation failed.
        """
        resolved = language if language in {"tr", "en"} else "en"
        if protocol.original_language == resolved:
            return protocol
        payload = protocol.model_dump(mode="json")
        payload["original_language"] = resolved
        await self.repo.update_run(run_id, protocol=payload)
        return ResearchProtocol.model_validate(payload)

    async def _to_research_language(
        self,
        run_id: str,
        protocol: ResearchProtocol,
    ) -> tuple[ResearchProtocol, str]:
        """Move the request into English before any stage reads it.

        Done here, at the first stage, so the plan the user approves already shows the
        English wording -- a bad translation is then caught before the collection budget is
        spent rather than after.
        """
        if protocol.original_question:
            return protocol, ""
        detected = detect_language(protocol.primary_question)
        if detected == "en":
            return await self._record_request_language(run_id, protocol, "en"), ""
        try:
            question, sub_questions, source, label = await translate_research_request(
                self._preparation_provider(),
                protocol.primary_question,
                list(protocol.sub_questions),
            )
        except Exception as exc:
            # Researching in the user's language is worse than researching in English, but
            # far better than failing the run over a translation.
            await self.repo.event(
                run_id,
                "research_language_fallback",
                {"language": detected, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
            )
            return await self._record_request_language(run_id, protocol, detected), ""
        finally:
            await self._emit_llm_metrics(
                run_id, "VALIDATE_PROTOCOL", provider=self._preparation_provider()
            )
        # The model reports the language it translated from; detect_language() only gets a
        # vote when the model declines to, because it answers "und" for anything short.
        language = source if source in {"tr", "en"} else detected
        if question.strip().casefold() == protocol.primary_question.strip().casefold():
            # Short English questions come back "und" from detect_language() and reach the
            # model anyway. When it hands the text back unchanged nothing was translated,
            # and the run should not claim otherwise -- the plan would show the user a
            # pointless "your question" block.
            return await self._record_request_language(run_id, protocol, language), label
        payload = protocol.model_dump(mode="json")
        payload["original_question"] = protocol.primary_question
        payload["original_sub_questions"] = list(protocol.sub_questions)
        payload["original_language"] = language
        payload["primary_question"] = question
        if sub_questions:
            payload["sub_questions"] = sub_questions
        translated = ResearchProtocol.model_validate(payload)
        await self.repo.update_run(run_id, protocol=payload)
        await self.repo.event(
            run_id,
            "research_language_translated",
            {
                "from_language": language,
                "original_question": protocol.primary_question,
                "research_question": question,
            },
        )
        return translated, label

    async def decompose_question(self, state: PipelineState) -> dict:
        await self._boundary(state, "DECOMPOSE")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        # Answers that name a protocol value are applied before anything reads the protocol
        # again -- BUILD_QUERY_BRANCHES takes the source families from here.
        protocol, applied = await self._apply_scoping(state["run_id"], protocol)
        # Both sources of user steering reach the model as guidance rather than as
        # questions: they are preferences about the run, not things to go and find out.
        planning = await self._planning_answers(state["run_id"])
        feedback = await self._plan_feedback(state["run_id"])
        # A rejection can also name a protocol value, and until it could, the run rewound
        # here and re-applied the window the user had just asked to change.
        protocol, revised = await self._apply_feedback_scope(
            state["run_id"], protocol, feedback
        )
        applied = [*applied, *revised]
        guidance = [*planning, *feedback]
        # Every checkpoint answer re-enters the graph here, so this node runs once per
        # round trip -- including the approval pass, which reads exactly what the pass
        # before it read. Decomposing again then buys nothing and costs an external
        # request, so the answer is reused whenever nothing it depends on has moved.
        signature = preparation_signature(
            protocol.primary_question,
            list(protocol.sub_questions),
            guidance,
            protocol.scope.start_date,
            protocol.scope.end_date,
        )
        if state.get("decompose_signature") == signature and state.get("sub_questions"):
            sub_questions = list(state.get("sub_questions", []))
            concepts = list(state.get("concepts", []))
        else:
            sub_questions, concepts = await decompose(
                self._preparation_provider(),
                protocol.primary_question,
                protocol.sub_questions,
                guidance=guidance,
            )
            sub_questions = [
                constrain_text_to_scope(
                    question,
                    protocol.scope.start_date,
                    protocol.scope.end_date,
                )
                for question in sub_questions
            ]
            await self._emit_llm_metrics(
                state["run_id"], "DECOMPOSE", provider=self._preparation_provider()
            )
        output = {
            "sub_questions": sub_questions[:12],
            "concepts": concepts[:20],
            "decompose_signature": signature,
        }
        if applied:
            output["protocol"] = protocol.model_dump(mode="json")
            output["applied_settings"] = applied
        if planning:
            output["planning_answers"] = planning
        # A rejected plan rewinds the run to this stage, so what the user asked to change
        # has to reach decomposition -- otherwise the next plan repeats the rejected one.
        if feedback:
            output["plan_feedback"] = feedback
            output["sub_questions"] = list(
                dict.fromkeys([*output["sub_questions"], *feedback])
            )[:12]
        await self._planning_gate(state, output, protocol)
        return output

    async def _planning_answers(self, run_id: str) -> list[str]:
        """What the user chose while scoping the run, as `question -> answer` lines.

        Steering, not questions. An earlier version appended the raw answers to
        sub_questions, which turned a tapped option like "clinical validation" into its own
        search branch.
        """
        response = await self._hitl_response(run_id, "planning_questions")
        if not isinstance(response, dict):
            return []
        lines = []
        for item in response.get("answers", []):
            answer = str(item.get("answer", "")).strip()
            if not answer:
                continue
            question = str(item.get("question", "")).strip()
            lines.append(f"{question} -> {answer}" if question else answer)
        return lines

    async def _planning_response_items(self, run_id: str) -> list[dict]:
        """The scoping answers as they were stored, ids and values intact."""
        response = await self._hitl_response(run_id, "planning_questions")
        if not isinstance(response, dict):
            return []
        return [item for item in response.get("answers", []) if isinstance(item, dict)]

    async def _apply_scoping(
        self,
        run_id: str,
        protocol: ResearchProtocol,
    ) -> tuple[ResearchProtocol, list[dict]]:
        """Turn the answers that name a protocol value into the protocol itself.

        Persisted rather than left in state: the resumed run reads its protocol from the
        row, and so does the panel. An answer that binds to nothing -- typed by hand, or an
        option the model invented -- changes nothing here and still reaches the prompts
        through _planning_answers().
        """
        # Re-deriving on every pass would undo anything applied since: a rejected plan
        # rewinds to this stage, and the scoping answers it re-reads have not changed.
        settled = await self.repo.events_by_types(run_id, {"scoping_applied"})
        if settled:
            return protocol, list(settled[-1].payload.get("settings") or [])
        items = await self._planning_response_items(run_id)
        if not items:
            return protocol, []
        updated, applied = apply_planning_answers(protocol, items)
        if not applied:
            if any(item.get("value") for item in items):
                await self.repo.event(
                    run_id,
                    "scoping_not_applied",
                    {"values": [item.get("value") for item in items if item.get("value")]},
                )
            return protocol, []
        await self.repo.update_run(run_id, protocol=updated.model_dump(mode="json"))
        await self.repo.event(run_id, "scoping_applied", {"settings": applied})
        return updated, applied

    async def _apply_feedback_scope(
        self,
        run_id: str,
        protocol: ResearchProtocol,
        feedback: list[str],
    ) -> tuple[ResearchProtocol, list[dict]]:
        """Write the protocol values a rejection named, through the scoping binder.

        Same table, same validation, same "binds or stays guidance" rule as the scoping
        gate -- a rejection is another way of answering the questions it asked. Recorded as
        its own event so the plan can say the dates moved because the user said so, not
        because the question implied it.
        """
        if not feedback:
            return protocol, []
        answers = feedback_answers(feedback)
        if not answers:
            return protocol, []
        updated, applied = apply_planning_answers(protocol, answers)
        if not applied:
            return protocol, []
        for item in applied:
            item["source"] = "feedback"
        await self.repo.update_run(run_id, protocol=updated.model_dump(mode="json"))
        await self.repo.event(run_id, "feedback_scope_applied", {"settings": applied})
        return updated, applied

    async def _planning_gate(
        self,
        state: PipelineState,
        output: dict[str, Any],
        protocol: ResearchProtocol,
    ) -> None:
        """Let the user narrow the run before any of it is planned.

        Only asked where somebody is actually waiting to answer -- an unattended run would
        otherwise park here forever -- and only once, since the answers survive in
        hitl_history and reach decomposition through _planning_answers().
        """
        if not protocol.hitl.planning_questions:
            return
        if await self._hitl_response(state["run_id"], "planning_questions") is not None:
            return
        language = protocol.display_language()
        try:
            questions = await planning_choices(
                self._preparation_provider(),
                protocol.primary_question,
                list(output.get("sub_questions", [])),
                language,
            )
        except Exception:
            questions = []
        await self._emit_llm_metrics(
            state["run_id"],
            "PLANNING_QUESTIONS",
            provider=self._preparation_provider(),
        )
        if not questions:
            # The checkpoint predates options and still works without them; a model that
            # returns nothing usable costs the tailored wording, not the checkpoint.
            questions = [{"question": text} for text in FALLBACK_PLANNING_QUESTIONS[language]]
        # The two binding questions lead: their options carry real protocol values, so they
        # are the ones worth answering first. The generated pair stays behind them as
        # steering, and four questions is as much as a chat interview can ask for.
        questions = [*fixed_questions(protocol, language), *questions[:2]]
        await self._request_input(
            {**state, **output},
            "planning_questions",
            {"questions": questions},
            "DECOMPOSE",
            self.settings.hitl_plan_timeout_minutes,
        )

    async def build_query_branches(self, state: PipelineState) -> dict:
        await self._boundary(state, "BUILD_QUERY_BRANCHES")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        families = [f.value for f in protocol.connectors.included_families]
        guidance = [
            *state.get("planning_answers", []),
            *state.get("plan_feedback", []),
        ]
        # Reused on an unchanged pass for the same reason DECOMPOSE is; see there.
        signature = preparation_signature(
            protocol.primary_question,
            list(state.get("sub_questions", [])),
            families,
            list(protocol.languages),
            guidance,
            protocol.scope.start_date,
            protocol.scope.end_date,
        )
        cached = state.get("generated_queries")
        if state.get("query_signature") == signature and cached is not None:
            generated = list(cached)
        else:
            try:
                generated = await generate_search_queries(
                    self._preparation_provider(),
                    protocol.primary_question,
                    state.get("sub_questions", []),
                    families,
                    protocol.languages,
                    guidance=guidance,
                )
            except Exception:
                if self._telegram_preparation and self.preparation_llm is not None:
                    raise
                # Not remembered: an empty list here is a failure, and the next pass
                # deserves a fresh attempt rather than a cached disappointment.
                signature = ""
                generated = []
            generated = [
                constrain_text_to_scope(
                    query,
                    protocol.scope.start_date,
                    protocol.scope.end_date,
                )
                for query in generated
            ]
            await self._emit_llm_metrics(
                state["run_id"],
                "BUILD_QUERY_BRANCHES",
                provider=self._preparation_provider(),
            )
        queries = list(
            dict.fromkeys([protocol.primary_question, *state.get("sub_questions", []), *generated])
        )
        for concept in state.get("concepts", [])[:3]:
            queries.append(f"{concept} criticism limitations")
        queries = queries[:8]
        missions = initial_missions(protocol, queries)
        output = {
            "queries": queries,
            "generated_queries": generated,
            "query_signature": signature,
            "missions": [mission.model_dump(mode="json") for mission in missions],
            "attempted_missions": [],
            "required_branch_ids": [mission.branch_id for mission in missions],
            "branch_queries": {mission.branch_id: mission.query for mission in missions},
            "round_number": max(1, state.get("round_number", 0)),
        }
        return await self._plan_gate(state, output, protocol)

    async def search(self, state: PipelineState) -> dict:
        await self._boundary(state, "SEARCH")
        if self._collection_seconds_remaining(state) <= 0:
            await self.repo.event(
                state["run_id"],
                "collection_budget_exhausted",
                {"stage": "SEARCH", "action": "skip_new_discovery"},
            )
            return {
                "candidates": [],
                "corpus_documents": [],
                "branch_result_counts": {},
                "source_count_before_round": len(
                    await self.repo.list_sources(state["run_id"])
                ),
            }
        return await self._interruptible(
            self._search_node(state),
            state,
            "SEARCH",
            self.settings.search_stage_timeout_s,
        )

    async def _search_node(self, state: PipelineState) -> dict:
        protocol = ResearchProtocol.model_validate(state["protocol"])
        configured_connectors = list(self.registry.selected(protocol.connectors))

        async def connector_is_usable(connector) -> tuple[Any, Any | None]:
            if not hasattr(connector, "health"):
                return connector, None
            try:
                return connector, await connector.health()
            except Exception:
                return connector, None

        health_rows = await asyncio.gather(
            *(connector_is_usable(connector) for connector in configured_connectors)
        )
        selected_connectors = {
            connector.id: connector
            for connector, health in health_rows
            if health is None or (health.enabled and health.healthy)
        }
        unavailable = [
            {
                "connector": connector.id,
                "detail": health.detail if health is not None else "health check failed",
            }
            for connector, health in health_rows
            if health is not None and (not health.enabled or not health.healthy)
        ]
        if unavailable:
            await self.repo.event(
                state["run_id"],
                "connectors_skipped",
                {"connectors": unavailable},
            )
        if protocol.connectors.citation_depth > 0 and not any(
            "citations" in getattr(connector, "capabilities", ())
            for connector in selected_connectors.values()
        ):
            await self.repo.event(
                state["run_id"],
                "citation_frontier_degraded",
                {
                    "reason": "no_healthy_citation_capable_connector",
                    "requested_depth": protocol.connectors.citation_depth,
                },
            )
        missions = [SearchMission.model_validate(item) for item in state.get("missions", [])]
        if not missions:
            missions = initial_missions(protocol, state.get("queries", []))
        semaphore = asyncio.Semaphore(self.settings.search_concurrency)
        citation_budget_lock = asyncio.Lock()
        citation_seed_budget = min(
            self.settings.citation_seed_max,
            max(self.settings.citation_seed_min, protocol.budget.results_per_connector),
        )
        citation_seeds_used = 0
        connector_errors: list[dict[str, str]] = []
        connector_metrics: list[dict[str, Any]] = []

        async def one(connector, mission: SearchMission):
            nonlocal citation_seeds_used
            async with semaphore:
                started = time.perf_counter()
                try:
                    provider_query = compile_provider_query(
                        connector.id,
                        mission.query,
                        protocol,
                        state.get("concepts", []),
                    )
                    domain = mission.domain_allowlist[0] if mission.domain_allowlist else None
                    if domain and hasattr(connector, "search_with_domain"):
                        rows = await connector.search_with_domain(
                            provider_query,
                            mission.result_limit,
                            domain,
                        )
                    elif hasattr(connector, "search_scoped"):
                        rows = await connector.search_scoped(
                            provider_query,
                            mission.result_limit,
                            protocol.scope,
                        )
                    else:
                        rows = await connector.search(provider_query, mission.result_limit)
                    if domain:
                        rows = [row for row in rows if domain_matches(str(row.url), [domain])]
                    if (
                        mission.target_entities
                        and mission.required_family == SourceFamily.CODE_DATA
                    ):
                        rows = [
                            row
                            for row in rows
                            if matches_target_entities(
                                f"{row.title} {row.snippet} {row.url}",
                                mission.target_entities,
                            )
                        ]
                    if protocol.connectors.citation_depth > 0 and "citations" in getattr(
                        connector, "capabilities", ()
                    ):
                        citation_budget = min(20, max(4, mission.result_limit))
                        frontier = rows[: min(5, len(rows))]
                        seen_frontier = {candidate_dedupe_key(row) for row in rows}
                        generated: list[ConnectorCandidate] = []
                        for depth in range(1, protocol.connectors.citation_depth + 1):
                            next_frontier: list[ConnectorCandidate] = []
                            for parent in frontier[:5]:
                                async with citation_budget_lock:
                                    if citation_seeds_used >= citation_seed_budget:
                                        break
                                    citation_seeds_used += 1
                                try:
                                    relations = await connector.fetch_citations(parent)
                                except Exception as exc:
                                    connector_errors.append(
                                        {
                                            "connector": connector.id,
                                            "error": f"citation frontier: {str(exc)[:450]}",
                                        }
                                    )
                                    continue
                                relation_rows = [
                                    relation
                                    for relation in relations
                                    if relation.get("relation_type")
                                ]
                                if relation_rows:
                                    parent.metadata.setdefault(
                                        "citation_relations",
                                        [],
                                    ).extend(relation_rows)
                                for relation in relation_rows:
                                    candidate = relation_to_candidate(
                                        relation,
                                        connector_id=connector.id,
                                        family=connector.family,
                                        parent=parent,
                                        depth=depth,
                                    )
                                    if candidate is None:
                                        continue
                                    key = candidate_dedupe_key(candidate)
                                    if key in seen_frontier:
                                        continue
                                    seen_frontier.add(key)
                                    generated.append(candidate)
                                    next_frontier.append(candidate)
                                    if len(generated) >= citation_budget:
                                        break
                                if len(generated) >= citation_budget:
                                    break
                            frontier = next_frontier
                            if not frontier or len(generated) >= citation_budget:
                                break
                        rows.extend(generated)
                    for rank, row in enumerate(rows, 1):
                        row.metadata["query_branch"] = mission.branch_id
                        row.metadata["query_branches"] = [mission.branch_id]
                        row.metadata["search_mission_id"] = mission.id
                        row.metadata["coverage_gap_id"] = mission.gap_id
                        row.metadata["required_authority"] = mission.required_authority.value
                        if mission.required_authority == AuthorityLevel.OFFICIAL:
                            row.metadata["authority"] = "official"
                        row.metadata["provider_rank"] = rank
                        row.metadata["federated_rrf_score"] = 1 / (60 + rank)
                        row.metadata["discovered_by_connectors"] = [connector.id]
                        row.metadata["original_query"] = mission.query
                        row.metadata["compiled_query"] = provider_query
                    connector_metrics.append(
                        {
                            "connector": connector.id,
                            "query": mission.query,
                            "compiled_query": provider_query,
                            "mission_id": mission.id,
                            "branch_id": mission.branch_id,
                            "latency_seconds": round(time.perf_counter() - started, 4),
                            "result_count": len(rows),
                            "success": True,
                        }
                    )
                    return rows
                except Exception as exc:
                    connector_errors.append({"connector": connector.id, "error": str(exc)[:500]})
                    connector_metrics.append(
                        {
                            "connector": connector.id,
                            "query": mission.query,
                            "mission_id": mission.id,
                            "branch_id": mission.branch_id,
                            "latency_seconds": round(time.perf_counter() - started, 4),
                            "result_count": 0,
                            "success": False,
                        }
                    )
                    return []

        calls = []
        scheduled_by_connector: dict[str, int] = defaultdict(int)
        for mission in missions:
            connector_ids = [
                connector_id
                for connector_id in mission.connector_ids
                if connector_id in selected_connectors
            ]
            if not connector_ids and mission.required_family is not None:
                connector_ids = [
                    connector_id
                    for connector_id, connector in selected_connectors.items()
                    if connector.family == mission.required_family
                ]
            if not connector_ids:
                connector_ids = list(selected_connectors)
            for connector_id in connector_ids:
                connector = selected_connectors.get(connector_id)
                if connector is not None:
                    if (
                        connector_id == "semantic_scholar"
                        and not self.settings.semantic_scholar_api_key
                        and scheduled_by_connector[connector_id] >= 2
                    ):
                        continue
                    calls.append(one(connector, mission))
                    scheduled_by_connector[connector_id] += 1
        batches = await asyncio.gather(*calls)
        for error in connector_errors:
            await self.repo.event(state["run_id"], "connector_error", error)
        citation_errors = [
            error
            for error in connector_errors
            if str(error.get("error", "")).startswith("citation frontier:")
        ]
        if citation_errors:
            await self.repo.event(
                state["run_id"],
                "citation_frontier_degraded",
                {
                    "reason": "citation_provider_errors",
                    "error_count": len(citation_errors),
                    "connectors": sorted({str(item.get("connector")) for item in citation_errors}),
                },
            )
        if connector_metrics:
            await self.repo.event(
                state["run_id"],
                "connector_metrics",
                {"calls": connector_metrics},
            )
        connector_attempts: dict[str, int] = defaultdict(int)
        connector_successes: dict[str, int] = defaultdict(int)
        for metric in connector_metrics:
            connector_id = str(metric["connector"])
            connector_attempts[connector_id] += 1
            connector_successes[connector_id] += int(bool(metric["success"]))
        connector_success_rates = {
            connector_id: round(
                connector_successes[connector_id] / max(1, attempts),
                4,
            )
            for connector_id, attempts in connector_attempts.items()
        }
        unique: dict[str, ConnectorCandidate] = {}
        for mission in missions:
            for seed_url in mission.seed_urls:
                family = mission.required_family or (
                    SourceFamily.OFFICIAL_LEGAL
                    if mission.required_authority == AuthorityLevel.OFFICIAL
                    else SourceFamily.WEB
                )
                candidate = ConnectorCandidate(
                    connector_id=(
                        "official_seed" if family == SourceFamily.OFFICIAL_LEGAL else "source_seed"
                    ),
                    family=family,
                    title=mission.query,
                    url=seed_url,
                    metadata={
                        "query_branch": mission.branch_id,
                        "query_branches": [mission.branch_id],
                        "search_mission_id": mission.id,
                        "coverage_gap_id": mission.gap_id,
                        "target_entities": mission.target_entities,
                        "authority": mission.required_authority.value,
                        "seeded": True,
                        "sentinel_required": mission.branch_id.startswith("sentinel:"),
                        "relevance_score": 1.0,
                    },
                )
                unique[candidate_dedupe_key(candidate)] = candidate
        for candidate in (item for batch in batches for item in batch):
            key = candidate_dedupe_key(candidate)
            if key in unique:
                current = unique[key]
                discovered_by = current.metadata.setdefault(
                    "discovered_by_connectors",
                    [current.connector_id],
                )
                for provider in candidate.metadata.get(
                    "discovered_by_connectors",
                    [candidate.connector_id],
                ):
                    if provider not in discovered_by:
                        discovered_by.append(provider)
                branches = current.metadata.setdefault("query_branches", [])
                for branch in candidate.metadata.get("query_branches", []):
                    if branch not in branches:
                        branches.append(branch)
                snapshots = current.metadata.setdefault("provider_snapshots", {})
                snapshots.update(candidate.metadata.get("provider_snapshots", {}))
                current.metadata["federated_rrf_score"] = float(
                    current.metadata.get("federated_rrf_score", 0.0)
                ) + float(candidate.metadata.get("federated_rrf_score", 0.0))
                current.metadata.setdefault("alternate_locations", []).append(str(candidate.url))
                for relation in candidate.metadata.get("citation_relations", []):
                    if relation not in current.metadata.setdefault("citation_relations", []):
                        current.metadata["citation_relations"].append(relation)
                prefer_candidate = bool(candidate.metadata.get("exact_repository")) or (
                    candidate.connector_id == "github" and current.connector_id != "github"
                )
                prefer_candidate = prefer_candidate or (
                    bool(candidate.metadata.get("inline_fulltext"))
                    and not current.metadata.get("inline_fulltext")
                )
                if prefer_candidate:
                    candidate.metadata["provider_snapshots"] = snapshots
                    candidate.metadata["query_branches"] = branches
                    candidate.metadata["federated_rrf_score"] = current.metadata[
                        "federated_rrf_score"
                    ]
                    candidate.metadata["alternate_locations"] = current.metadata[
                        "alternate_locations"
                    ]
                    candidate.metadata["discovered_by_connectors"] = discovered_by
                    unique[key] = candidate
            else:
                unique[key] = candidate
        if state.get("round_number", 1) > 1 and not any(
            mission.domain_allowlist for mission in missions
        ):
            frontier = await self.repo.pop_frontier_candidates(
                state["run_id"],
                min(
                    protocol.budget.results_per_connector,
                    self.settings.frontier_max_links_per_document,
                ),
            )
            invalid_frontier: list[dict[str, str]] = []
            for item in frontier:
                try:
                    candidate = ConnectorCandidate(
                        connector_id="link_frontier",
                        family="web",
                        title=str(item["url"])[:500],
                        url=item["url"],
                        snippet="Discovered from an acquired source",
                        metadata={
                            **item,
                            "query_branches": [missions[0].branch_id] if missions else [],
                        },
                    )
                except Exception as exc:
                    invalid_frontier.append(
                        {
                            "url": str(item.get("url", ""))[:500],
                            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                        }
                    )
                    continue
                unique.setdefault(canonicalize_url(str(candidate.url)), candidate)
            if invalid_frontier:
                await self.repo.event(
                    state["run_id"],
                    "frontier_candidates_rejected",
                    {
                        "rejected_count": len(invalid_frontier),
                        "sample": invalid_frontier[:20],
                    },
                )
        existing = await self.repo.list_sources(state["run_id"])
        novel, novelty_rejected = await self.repo.filter_novel_candidates(
            state["run_id"],
            list(unique.values()),
        )
        if novelty_rejected:
            await self.repo.event(
                state["run_id"],
                "novelty_filter",
                {
                    "rejected_count": len(novelty_rejected),
                    "sample": novelty_rejected[:20],
                },
            )
        temporal_candidates = []
        temporal_rejected = []
        for candidate in novel:
            accepted, reason = temporal_relevance(
                candidate,
                protocol,
                reject_unknown=False,
            )
            if accepted:
                temporal_candidates.append(candidate)
            else:
                temporal_rejected.append(
                    {
                        "url": str(candidate.url),
                        "published_at": (
                            candidate.published_at.isoformat() if candidate.published_at else None
                        ),
                        "reason": reason,
                    }
                )
        if temporal_rejected:
            await self.repo.event(
                state["run_id"],
                "temporal_scope_filter",
                {
                    "rejected_count": len(temporal_rejected),
                    "sample": temporal_rejected[:20],
                    "start_date": (
                        protocol.scope.start_date.isoformat() if protocol.scope.start_date else None
                    ),
                    "end_date": (
                        protocol.scope.end_date.isoformat() if protocol.scope.end_date else None
                    ),
                },
            )
        novel = temporal_candidates
        if protocol.budget.max_sources is None:
            remaining: int | None = None
            round_cap = max(1, len(novel))
        else:
            remaining = max(0, protocol.budget.max_sources - len(existing))
            fraction = (
                self.settings.first_round_source_fraction
                if state.get("round_number", 1) == 1
                else self.settings.later_round_source_fraction
            )
            round_cap = min(
                remaining,
                max(1, math.ceil(protocol.budget.max_sources * fraction)),
            )
        reserve: list[ConnectorCandidate] = []
        if self.settings.testing:
            ranked, rejected = novel, []
            for candidate in ranked:
                candidate.metadata["admission_tier"] = "accept"
        else:
            rank_pool_limit = min(len(novel), max(round_cap * 4, round_cap))
            reserve_limit = (
                min(5, round_cap // 4)
                if protocol.research_mode == "literature_scan"
                else max(1, min(5, round_cap // 5))
            )
            ranked, reserve, rejected = classify_candidate_admission(
                novel,
                protocol,
                rank_pool_limit,
                reserve_limit=reserve_limit,
            )
        accepted_slots = max(0, round_cap - len(reserve))
        candidates = [
            *select_mission_balanced_candidates(ranked, missions, accepted_slots),
            *reserve[: max(0, round_cap - accepted_slots)],
        ]
        if rejected:
            await self.repo.event(
                state["run_id"],
                "relevance_filter",
                {"rejected_count": len(rejected), "sample": rejected[:20]},
            )
        corpus_documents: list[AcquiredDocument] = []
        if self.settings.local_corpus_results:
            corpus_passages = await self.repo.list_corpus_passages(state["run_id"])
            if corpus_passages:
                try:
                    query_vectors = await self.embeddings.embed(state["queries"])
                except Exception:
                    query_vectors = [[] for _ in state["queries"]]
                corpus_hits = retrieve_passages(
                    corpus_passages,
                    state["queries"],
                    query_vectors,
                    per_question=max(1, self.settings.local_corpus_results // 2),
                )
                corpus_hits = [hit for hit in corpus_hits if hit.retrieval_score >= 0.60][
                    : self.settings.local_corpus_results
                ]
                corpus_documents = await self.repo.corpus_documents(
                    list(dict.fromkeys(hit.source_version_id for hit in corpus_hits))
                )
                if not self.settings.testing and corpus_documents:
                    accepted_candidates, corpus_rejected = filter_and_rank_candidates(
                        [document.candidate for document in corpus_documents],
                        protocol,
                        self.settings.local_corpus_results,
                    )
                    accepted_ids = {candidate.id for candidate in accepted_candidates}
                    corpus_documents = [
                        document
                        for document in corpus_documents
                        if document.candidate.id in accepted_ids
                    ]
                    if corpus_rejected:
                        await self.repo.event(
                            state["run_id"],
                            "local_corpus_relevance_filter",
                            {
                                "rejected_count": len(corpus_rejected),
                                "sample": corpus_rejected[:10],
                            },
                        )
                await self.repo.event(
                    state["run_id"],
                    "local_corpus_search",
                    {
                        "candidate_passages": len(corpus_passages),
                        "selected_passages": len(corpus_hits),
                        "selected_documents": len(corpus_documents),
                    },
                )
        corpus_slots = (
            self.settings.local_corpus_results
            if remaining is None
            else max(0, remaining - len(candidates))
        )
        corpus_documents = corpus_documents[:corpus_slots]
        return {
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "corpus_documents": [doc.model_dump(mode="json") for doc in corpus_documents],
            "branch_result_counts": {},
            "source_count_before_round": len(existing),
            "unavailable_connectors": [item["connector"] for item in unavailable],
            "available_connectors": sorted(selected_connectors),
            "connector_success_rates": connector_success_rates,
            "discovery_stats": {
                **state.get("discovery_stats", {}),
                "round_provider_candidates": len(unique),
                "pooled_candidates": len(novel),
                "round_novel_candidates": len(novel),
                "accepted_candidates": len(ranked),
                "round_selected_candidates": len(candidates) + len(corpus_documents),
                "reserve_selected": len(reserve),
                "hard_rejected": len(rejected),
                "citation_candidates_selected": sum(
                    candidate.metadata.get("discovery_method") == "citation_frontier"
                    for candidate in candidates
                ),
                "citation_seeds_expanded": citation_seeds_used,
            },
            "attempted_missions": list(
                dict.fromkeys(
                    [
                        *state.get("attempted_missions", []),
                        *(mission_signature(mission) for mission in missions),
                    ]
                )
            ),
        }

    async def acquire(self, state: PipelineState) -> dict:
        await self._boundary(state, "ACQUIRE")
        return await self._interruptible(
            self._acquire_node(state),
            state,
            "ACQUIRE",
            self.settings.acquisition_stage_timeout_s,
        )

    async def _acquire_node(self, state: PipelineState) -> dict:
        protocol = ResearchProtocol.model_validate(state["protocol"])
        # Deterministic selection unless the protocol names a parser for a document type.
        self.acquisition.parser_overrides = dict(protocol.parsers.overrides)
        candidates = [ConnectorCandidate.model_validate(c) for c in state.get("candidates", [])]
        semaphore = asyncio.Semaphore(protocol.budget.acquisition_concurrency)
        acquisition_metrics: list[dict[str, Any]] = []

        async def one(candidate):
            async with semaphore:
                started = time.perf_counter()
                document = await self.acquisition.acquire(candidate)
                acquisition_metrics.append(
                    {
                        "connector": candidate.connector_id,
                        "url": str(candidate.url),
                        "latency_seconds": round(time.perf_counter() - started, 4),
                        "success": document.success,
                        "method": document.acquisition_method,
                        # Which parser produced the text, so the panel can break a stage
                        # down by tool without joining source_versions.provenance.
                        "parser_id": document.parser_id,
                    }
                )
                return document

        tasks = [asyncio.create_task(one(candidate)) for candidate in candidates]
        docs = []
        total = len(tasks)
        completed = 0
        cutoff = False
        remaining = self._collection_seconds_remaining(state)
        try:
            if remaining <= 0:
                cutoff = bool(tasks)
            else:
                try:
                    for task in asyncio.as_completed(tasks, timeout=remaining):
                        document = await task
                        docs.append(document)
                        completed += 1
                        await self.repo.update_run(
                            state["run_id"], current_stage="ACQUIRE"
                        )
                        await self.repo.event(
                            state["run_id"],
                            "acquisition_progress",
                            {
                                "completed": completed,
                                "total": total,
                                "successful": sum(item.success for item in docs),
                                "last_url": str(document.candidate.url),
                                "last_method": document.acquisition_method,
                            },
                        )
                except TimeoutError:
                    cutoff = True
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        if cutoff:
            await self.repo.event(
                state["run_id"],
                "collection_budget_exhausted",
                {
                    "stage": "ACQUIRE",
                    "completed": completed,
                    "total": total,
                    "successful": sum(item.success for item in docs),
                    "action": "continue_postprocessing",
                },
            )
        docs = [
            *docs,
            *[AcquiredDocument.model_validate(row) for row in state.get("corpus_documents", [])],
        ]
        if acquisition_metrics:
            await self.repo.event(
                state["run_id"],
                "acquisition_metrics",
                {"calls": acquisition_metrics},
            )
        discovery_stats = {
            **state.get("discovery_stats", {}),
            "round_acquisition_successful": sum(document.success for document in docs),
        }
        return {
            "documents": [d.model_dump(mode="json") for d in docs],
            "discovery_stats": discovery_stats,
        }

    async def _semantic_source_judgment(
        self,
        protocol: ResearchProtocol,
        document: AcquiredDocument,
    ) -> tuple[bool, float, str]:
        """Use the local model only after deterministic gates pass."""
        if protocol.research_mode == "literature_scan":
            system_prompt = (
                "Act as a high-recall literature screening classifier. Retain both directly "
                "relevant publications and contextually relevant reviews, methods, datasets, "
                "replications, negative results, safety analyses, guidelines, and critiques. "
                "Reject only a clearly unrelated central subject; a keyword-only related-article "
                "link or an adjacent disease with no transferable method is unrelated. Set "
                "directly_relevant=true for direct OR useful contextual literature. Return one "
                "JSON object with directly_relevant (boolean), relevance_score (0..1), and reason. "
                "Begin reason with 'direct:', 'contextual:', or 'unrelated:'."
            )
        else:
            system_prompt = (
                "Act as a strict research source admission gate. Decide whether the publication's "
                "central subject directly helps answer the research question. A mere keyword mention, "
                "related-article link, comparison cohort, background reference, or adjacent disease is "
                "not directly relevant. Judge the source itself by its publication/update date; "
                "a newly published systematic review can be relevant even when it summarizes "
                "older studies. Return one JSON object with directly_relevant (boolean), "
                "relevance_score (0..1, where 0 is unrelated and 1 is directly useful), and "
                "reason (short string)."
            )
        user_prompt = (
            f"QUESTION: {protocol.primary_question}\n"
            f"DATE_SCOPE: {protocol.scope.start_date} to {protocol.scope.end_date}\n"
            f"TITLE: {document.candidate.title}\n"
            f"DISCOVERY_SNIPPET: {document.candidate.snippet[:1500]}\n"
            f"DOCUMENT_EXCERPT: {document.content[:6000]}"
        )
        last_error = "invalid_response"
        for _attempt in range(self.settings.relevance_retry_attempts):
            try:
                result = await self.llm.complete_json(system_prompt, user_prompt)
                if not isinstance(result, dict) or not isinstance(
                    result.get("directly_relevant"),
                    bool,
                ):
                    last_error = "invalid_response"
                    continue
                relevance_score = max(
                    0.0,
                    min(1.0, float(result.get("relevance_score", 0.5))),
                )
                return (
                    bool(result["directly_relevant"]),
                    relevance_score,
                    str(result.get("reason", ""))[:500],
                )
            except Exception as exc:
                last_error = type(exc).__name__
        strict_delivery = (
            protocol.research_mode == "focused_answer"
            and (
                protocol.output_mode == "raw"
                or protocol.authority_policy.strict_for_major_claims
            )
        )
        if strict_delivery:
            return False, 0.0, f"judge_unavailable_fail_closed:{last_error}"
        return True, 1.0, f"judge_unavailable_fail_open:{last_error}"

    async def normalize(self, state: PipelineState) -> dict:
        await self._boundary(state, "NORMALIZE")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        prior_source_review = await self._hitl_response(state["run_id"], "source_review")
        if prior_source_review is not None and any(
            payload.get("source_version_id") for payload in state.get("documents", [])
        ):
            included = set(prior_source_review.get("included_domains", []))
            excluded = set(prior_source_review.get("excluded_domains", [])) - included
            await self.repo.apply_source_domain_review(state["run_id"], included, excluded)
            documents = [
                payload
                for payload in state.get("documents", [])
                if (
                    urlparse(str(AcquiredDocument.model_validate(payload).candidate.url)).hostname
                    or ""
                ).lower()
                not in excluded
            ]
            return {
                "documents": documents,
                "branch_result_counts": state.get("branch_result_counts", {}),
                "discovery_stats": state.get("discovery_stats", {}),
                "round_new_source_versions": state.get(
                    "round_new_source_versions",
                    len(documents),
                ),
            }
        documents = [AcquiredDocument.model_validate(d) for d in state.get("documents", [])]
        existing_version_ids = {
            version.id for _, version in await self.repo.list_source_versions(state["run_id"])
        }
        saved_docs = []
        discovery_stats = dict(state.get("discovery_stats", {}))
        discovery_stats["reserve_audited"] = int(discovery_stats.get("reserve_audited", 0)) + sum(
            document.success and document.candidate.metadata.get("admission_tier") == "reserve"
            for document in documents
        )
        discovery_stats.setdefault("reserve_relevant", 0)
        discovery_stats.setdefault("citation_relevant", 0)
        discovery_stats.setdefault("relevant_admitted", 0)
        discovery_stats["round_citation_relevant"] = 0
        discovery_stats["round_relevant_admitted"] = 0
        branch_counts: dict[str, int] = defaultdict(int)
        content_rejected: list[dict[str, Any]] = []
        for document in documents:
            if not document.success:
                continue
            enrich_publication_date(document.candidate, document.raw_content or document.content)
            temporal_ok, temporal_reason = temporal_relevance(
                document.candidate,
                protocol,
                reject_unknown=protocol.research_mode == "focused_answer",
            )
            document.candidate.metadata["temporal_scope_status"] = temporal_reason
            if not temporal_ok:
                content_rejected.append(
                    {
                        "url": str(document.candidate.url),
                        "reason": temporal_reason,
                        "stage": "post_acquisition_temporal",
                    }
                )
                continue
            relevant, relevance_score, relevance_reasons = document_relevance(
                document,
                protocol,
                [
                    *protocol.research_questions(),
                    *state.get("sub_questions", []),
                ],
            )
            if not relevant and (
                protocol.research_mode == "focused_answer" or relevance_score < 0.18
            ):
                content_rejected.append(
                    {
                        "url": str(document.candidate.url),
                        "reason": "content_not_relevant",
                        "score": relevance_score,
                        "details": relevance_reasons,
                        "stage": "post_acquisition_semantic",
                    }
                )
                continue
            deterministic_direct = relevant
            if not self.settings.testing and not document.candidate.metadata.get(
                "sentinel_required"
            ):
                judged_relevant, judge_score, judge_reason = await self._semantic_source_judgment(
                    protocol, document
                )
                document.candidate.metadata["semantic_relevance_judgment"] = {
                    "directly_relevant": judged_relevant,
                    "relevance_score": judge_score,
                    "reason": judge_reason,
                    "model": self.settings.llm_model,
                }
                reject_semantic = (
                    (not judged_relevant or judge_score < 0.45)
                    if protocol.research_mode == "focused_answer"
                    else (not judged_relevant and judge_score < 0.20)
                )
                if reject_semantic:
                    content_rejected.append(
                        {
                            "url": str(document.candidate.url),
                            "reason": "semantic_judge_not_directly_relevant",
                            "relevance_score": judge_score,
                            "details": judge_reason,
                            "stage": "post_acquisition_llm",
                        }
                    )
                    continue
                if protocol.research_mode == "literature_scan":
                    reason_prefix = judge_reason.strip().lower().split(":", 1)[0]
                    document.candidate.metadata["literature_relevance_tier"] = (
                        "direct"
                        if (
                            judged_relevant
                            and deterministic_direct
                            and reason_prefix != "contextual"
                            and float(
                                document.candidate.metadata.get(
                                    "primary_subject_coverage",
                                    0.0,
                                )
                            )
                            >= 0.80
                        )
                        else "contextual"
                    )
            if protocol.research_mode == "literature_scan":
                document.candidate.metadata.setdefault(
                    "literature_relevance_tier",
                    (
                        "direct"
                        if deterministic_direct
                        and float(
                            document.candidate.metadata.get(
                                "primary_subject_coverage",
                                0.0,
                            )
                        )
                        >= 0.80
                        else "contextual"
                    ),
                )
            snapshot = document.raw_content or document.content
            if snapshot and document.content_hash:
                extension = {
                    "html": "html",
                    "pdf": "pdf",
                    "json": "json",
                    "xml": "xml",
                }.get(document.document_type, "txt")
                snapshot_key = f"{state['run_id']}/sources/{document.content_hash}.{extension}"
                snapshot_bytes = (
                    base64.b64decode(snapshot)
                    if document.document_type == "pdf" and document.raw_content
                    else snapshot.encode("utf-8", errors="replace")
                )
                await self.store.put(snapshot_key, snapshot_bytes, document.content_type)
                document.candidate.metadata["raw_snapshot_key"] = snapshot_key
            source, version = await self.repo.save_document(state["run_id"], document)
            if version.id in existing_version_ids:
                await self.repo.event(
                    state["run_id"],
                    "duplicate_source_version",
                    {
                        "source_id": source.id,
                        "source_version_id": version.id,
                        "url": source.url,
                    },
                )
                continue
            existing_version_ids.add(version.id)
            payload = document.model_dump(mode="json")
            # raw_content holds the untouched snapshot, and for PDFs that is the whole
            # binary base64-encoded (up to max_download_bytes * 4/3 per document). It is
            # already durable in MinIO and source_versions by this point, and every later
            # reader takes it from the database, so keeping it in the graph state only
            # inflates the NORMALIZE checkpoint past PostgreSQL's 256 MB jsonb ceiling.
            payload["raw_content"] = ""
            payload["source_id"] = source.id
            payload["source_version_id"] = version.id
            saved_docs.append(payload)
            discovery_stats["relevant_admitted"] += 1
            discovery_stats["round_relevant_admitted"] += 1
            if document.candidate.metadata.get("admission_tier") == "reserve":
                discovery_stats["reserve_relevant"] += 1
            if document.candidate.metadata.get("discovery_method") == "citation_frontier":
                discovery_stats["citation_relevant"] += 1
                discovery_stats["round_citation_relevant"] += 1
            for branch in document.candidate.metadata.get("query_branches", []):
                branch_counts[branch] += 1
            if document.outgoing_links:
                added = await self.repo.add_frontier_links(
                    state["run_id"],
                    document.final_url or str(document.candidate.url),
                    document.outgoing_links,
                    max_links=self.settings.frontier_max_links_per_document,
                )
                if added:
                    await self.repo.event(
                        state["run_id"],
                        "frontier_links",
                        {
                            "source": document.final_url or str(document.candidate.url),
                            "added": added,
                        },
                    )
        if content_rejected:
            await self.repo.event(
                state["run_id"],
                "content_relevance_filter",
                {
                    "rejected_count": len(content_rejected),
                    "sample": content_rejected[:20],
                },
            )
        await self._emit_llm_metrics(state["run_id"], "CONTENT_RELEVANCE")
        sources = await self.repo.list_sources(state["run_id"])
        await self.repo.update_run(state["run_id"], sources_count=len(sources))
        output = {
            "documents": saved_docs,
            "branch_result_counts": dict(branch_counts),
            "discovery_stats": {
                **discovery_stats,
                "round_content_rejected": len(content_rejected),
            },
            "round_new_source_versions": len(saved_docs),
        }
        grouped: dict[str, dict[str, Any]] = {}
        for payload in saved_docs:
            document = AcquiredDocument.model_validate(payload)
            domain = (urlparse(str(document.candidate.url)).hostname or "unknown").lower()
            item = grouped.setdefault(
                domain,
                {
                    "domain": domain,
                    "source_count": 0,
                    "scores": [],
                    "ai_recommendation": "include",
                },
            )
            item["source_count"] += 1
            item["scores"].append(
                float(document.candidate.metadata.get("content_relevance_score", 0.5))
            )
        domains = []
        for item in grouped.values():
            scores = item.pop("scores")
            item["avg_relevance_score"] = round(sum(scores) / max(1, len(scores)), 4)
            item["ai_recommendation"] = (
                "include" if item["avg_relevance_score"] >= 0.35 else "exclude"
            )
            domains.append(item)
        response = await self._maybe_hitl(
            {**state, **output},
            "source_review",
            {"domains": sorted(domains, key=lambda item: (-item["source_count"], item["domain"]))},
            "NORMALIZE",
        )
        if response:
            included = set(response.get("included_domains", []))
            excluded = set(response.get("excluded_domains", [])) - included
            await self.repo.apply_source_domain_review(state["run_id"], included, excluded)
            output["documents"] = [
                payload
                for payload in saved_docs
                if (
                    urlparse(str(AcquiredDocument.model_validate(payload).candidate.url)).hostname
                    or ""
                ).lower()
                not in excluded
            ]
            await self.repo.event(
                state["run_id"],
                "hitl_source_filter",
                {
                    "included_domains": sorted(included),
                    "excluded_domains": sorted(excluded),
                    "retained_documents": len(output["documents"]),
                    "excluded_documents": len(saved_docs) - len(output["documents"]),
                },
            )
        return output

    async def chunk_index(self, state: PipelineState) -> dict:
        await self._boundary(state, "CHUNK_INDEX")
        all_passages: list[Passage] = []
        for payload in state.get("documents", []):
            document = AcquiredDocument.model_validate(payload)
            document_passages = chunk_document(
                document.content,
                payload["source_version_id"],
                target_tokens=self.settings.passage_target_tokens,
                overlap_tokens=self.settings.passage_overlap_tokens,
            )
            for passage in document_passages:
                passage.language = document.language
                passage.document_type = document.document_type
            all_passages.extend(document_passages)
        try:
            embedding_inputs = [
                f"{passage.section_path}\n{passage.text}" for passage in all_passages
            ]
            vectors = await self.embeddings.embed(embedding_inputs) if embedding_inputs else []
            for passage, vector in zip(all_passages, vectors):
                passage.embedding = vector
        except Exception as exc:
            await self.repo.event(
                state["run_id"],
                "embedding_fallback",
                {"error": str(exc)[:500]},
            )
        metrics = self.embeddings.drain_metrics()
        if metrics:
            await self.repo.event(
                state["run_id"],
                "embedding_metrics",
                {"stage": "CHUNK_INDEX", "calls": metrics},
            )
        await self.repo.save_passages(all_passages)
        await self.repo.event(
            state["run_id"],
            "passage_index",
            {
                "passage_count": len(all_passages),
                "embedded_count": sum(bool(passage.embedding) for passage in all_passages),
                "total_tokens": sum(passage.token_count for passage in all_passages),
            },
        )
        return {"passages": []}

    async def retrieve_relevant_passages(self, state: PipelineState) -> dict:
        await self._boundary(state, "RETRIEVE_PASSAGES")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        version_ids = [payload["source_version_id"] for payload in state.get("documents", [])]
        if not version_ids:
            await self.repo.event(
                state["run_id"],
                "passage_retrieval",
                {
                    "question_count": 0,
                    "candidate_count": 0,
                    "selected_count": 0,
                    "reason": "no_new_source_versions",
                },
            )
            return {"passages": []}
        passages = await self.repo.list_passages(state["run_id"], version_ids)
        questions = list(
            dict.fromkeys(
                [
                    protocol.primary_question,
                    *state.get("sub_questions", []),
                ]
            )
        )
        try:
            query_embeddings = await self.embeddings.embed(questions)
        except Exception as exc:
            query_embeddings = [[] for _ in questions]
            await self.repo.event(
                state["run_id"],
                "embedding_fallback",
                {"stage": "retrieval", "error": str(exc)[:500]},
            )
        metrics = self.embeddings.drain_metrics()
        if metrics:
            await self.repo.event(
                state["run_id"],
                "embedding_metrics",
                {"stage": "RETRIEVE_PASSAGES", "calls": metrics},
            )
        selected = retrieve_passages(
            passages,
            questions,
            query_embeddings,
            per_question=self.settings.passages_per_question,
        )[:16]
        await self.repo.save_passages(selected)
        await self.repo.event(
            state["run_id"],
            "passage_retrieval",
            {
                "question_count": len(questions),
                "candidate_count": len(passages),
                "selected_count": len(selected),
                "selected": [
                    {
                        "passage_id": passage.id,
                        "section": passage.section_path,
                        "score": passage.retrieval_score,
                        "questions": passage.matched_questions,
                    }
                    for passage in selected
                ],
            },
        )
        if self.settings.paperqa2_enabled and self.settings.paperqa2_shadow_mode:
            shadow_documents = [
                {
                    "source_version_id": passage.source_version_id,
                    "content": passage.text,
                    "section_path": passage.section_path,
                }
                for passage in passages
            ]
            try:
                shadow = await PaperQA2EvidenceEngine(self.settings).retrieve_evidence(
                    protocol.primary_question,
                    shadow_documents,
                )
            except Exception as exc:
                shadow = {
                    "engine": "paperqa2",
                    "available": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            await self.repo.event(state["run_id"], "paperqa2_shadow", shadow)
        selected_payloads = []
        for passage in selected:
            payload = passage_payload(passage)
            payload["embedding"] = []
            selected_payloads.append(payload)
        return {"passages": selected_payloads}

    async def extract_evidence(self, state: PipelineState) -> dict:
        await self._boundary(state, "EXTRACT_EVIDENCE")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        if protocol.output_mode == "raw":
            await self.repo.event(
                state["run_id"],
                "claim_extraction_skipped",
                {"reason": "raw_output_mode"},
            )
            return {"claims": []}
        documents = state.get("documents", [])
        passages = [Passage.model_validate(row) for row in state.get("passages", [])]
        if not passages:
            return {"claims": []}
        all_passages = await self.repo.list_passages(state["run_id"])
        evidence_questions = list(
            dict.fromkeys(
                [
                    protocol.primary_question,
                    *state.get("sub_questions", []),
                ]
            )
        )
        documents_by_version = {payload["source_version_id"]: payload for payload in documents}
        semaphore = asyncio.Semaphore(self.settings.evidence_extraction_concurrency)
        extraction_errors: list[dict[str, str]] = []

        async def one(passage: Passage):
            async with semaphore:
                payload = documents_by_version[passage.source_version_id]
                doc = AcquiredDocument.model_validate(payload)
                if doc.candidate.metadata.get("evidence_eligible") is False:
                    return []
                if is_non_evidence_section(passage.section_path):
                    return []
                try:
                    model_claims = await extract_claims(
                        self.llm,
                        doc,
                        research_question=protocol.primary_question,
                        content_override=passage.text,
                        neighbor_context=neighbor_context(passage, all_passages),
                        passage_id=passage.id,
                        section_path=passage.section_path,
                        page_number=passage.page_number,
                        original_offset=passage.start_char,
                        retrieval_score=passage.retrieval_score,
                    )
                    deterministic_claims = relevant_sentence_claims(
                        passage,
                        evidence_questions,
                        doc.candidate.id,
                        limit=2,
                    )
                    merged = merge_passage_claims(model_claims, deterministic_claims)[:4]
                    return [
                        claim
                        for claim in merged
                        if evidence_quality_gate(
                            claim.text,
                            claim.quote,
                            section_path=claim.section_path,
                            source_title=doc.candidate.title,
                        )[0]
                    ]
                except Exception as exc:
                    extraction_errors.append(
                        {"url": str(doc.candidate.url), "error": str(exc)[:500]}
                    )
                    return []

        batches = await asyncio.gather(*(one(passage) for passage in passages))
        await self._emit_llm_metrics(state["run_id"], "EXTRACT_EVIDENCE")
        for error in extraction_errors:
            await self.repo.event(state["run_id"], "claim_extract_error", error)
        rows = []
        for passage, claims in zip(passages, batches):
            for claim in claims:
                row = claim.model_dump(mode="json")
                row["source_version_id"] = passage.source_version_id
                rows.append(row)
        return {"claims": rows}

    async def analyze_claims(self, state: PipelineState) -> dict:
        await self._boundary(state, "ANALYZE_CLAIMS")
        raw = state.get("claims", [])
        accepted: list[tuple[ExtractedClaim, str]] = []
        existing = await self.repo.list_claims(state["run_id"])
        document_titles = {
            payload["source_version_id"]: AcquiredDocument.model_validate(payload).candidate.title
            for payload in state.get("documents", [])
            if payload.get("source_version_id")
        }
        seen: list[tuple[str, str]] = [
            (re.sub(r"\W+", " ", claim.text.lower()).strip(), claim.id) for claim in existing
        ]
        for payload in raw:
            version_id = payload.pop("source_version_id")
            claim = ExtractedClaim.model_validate(payload)
            relevance = claim_relevance(
                claim.text,
                " ".join(
                    [
                        ResearchProtocol.model_validate(state["protocol"]).primary_question,
                        *state.get("sub_questions", []),
                    ]
                ),
            )
            promotional = bool(
                re.search(
                    r"\b(kurun|takip edin|kaydet|olmazsa olmaz|rakipsiz|süper güç|"
                    r"install it|follow me|must-have)\b",
                    claim.text,
                    flags=re.IGNORECASE,
                )
            )
            evidence_valid, _ = evidence_quality_gate(
                claim.text,
                claim.quote,
                section_path=claim.section_path,
                source_title=document_titles.get(version_id, ""),
            )
            if relevance < 0.25 or promotional or not evidence_valid:
                continue
            normalized = re.sub(r"\W+", " ", claim.text.lower()).strip()
            match = next(
                (
                    (other, claim_id)
                    for other, claim_id in seen
                    if SequenceMatcher(None, normalized, other).ratio() > 0.92
                ),
                None,
            )
            if match:
                claim.id = match[1]
            else:
                seen.append((normalized, claim.id))
            accepted.append((claim, version_id))
        await self.repo.save_claims(state["run_id"], accepted)
        total_claims = await self.repo.list_claims(state["run_id"])
        await self.repo.update_run(state["run_id"], claims_count=len(total_claims))
        return {
            "claims": [{**c.model_dump(mode="json"), "source_version_id": v} for c, v in accepted]
        }

    async def check_coverage(self, state: PipelineState) -> dict:
        await self._boundary(state, "CHECK_COVERAGE")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        sources = [
            source
            for source in await self.repo.list_sources(state["run_id"])
            if not (source.metadata_json or {}).get("excluded_by_hitl")
        ]
        claims = await self.repo.list_claims(state["run_id"])
        evidence = await self.repo.list_evidence(state["run_id"])
        previous_count = state.get("source_count_before_round", 0)
        new_count = max(0, len(sources) - previous_count)
        rate = new_count / max(len(sources), 1)
        previous = CoverageMetrics.model_validate(state.get("coverage", {}))
        round_number = state.get("round_number", 1)
        round_new_source_versions = int(
            state.get("round_new_source_versions", len(state.get("documents", [])))
        )
        previous_empty_recovery_rounds = int(
            state.get("consecutive_empty_recovery_rounds", 0)
        )
        consecutive_empty_recovery_rounds = (
            previous_empty_recovery_rounds + 1
            if round_number > 1 and round_new_source_versions == 0
            else 0
        )
        major = sorted(
            [
                c
                for c in claims
                if c.importance == "major"
                and float((c.audit or {}).get("question_relevance", 0.0)) >= 0.25
            ],
            key=lambda claim: float(
                (claim.audit or {}).get("question_relevance", 0.0),
            ),
            reverse=True,
        )[:8]
        audited = [c for c in major if c.audit]
        unresolved = [c for c in major if c.status != "supported"]
        official_entities = resolve_official_entities(protocol.primary_question)
        official_domains = [domain for entity in official_entities for domain in entity["domains"]]
        relevant_sources = [
            source
            for source in sources
            if (
                (
                    source.family
                    in {
                        SourceFamily.WEB.value,
                        SourceFamily.ACADEMIC.value,
                    }
                    and max(
                        float((source.metadata_json or {}).get("relevance_score", 0.0)),
                        float((source.metadata_json or {}).get("content_relevance_score", 0.0)),
                    )
                    >= 0.35
                )
                or (
                    source.family == SourceFamily.CODE_DATA.value
                    and max(
                        float((source.metadata_json or {}).get("relevance_score", 0.0)),
                        float((source.metadata_json or {}).get("content_relevance_score", 0.0)),
                    )
                    >= 0.45
                )
                or (source.metadata_json or {}).get("authority") == "primary"
                or (
                    (source.metadata_json or {}).get("authority") == "official"
                    and domain_matches(source.url, official_domains)
                )
            )
        ]
        branch_counts: dict[str, int] = defaultdict(int)
        for branch_id in state.get("required_branch_ids", []):
            branch_counts[branch_id] = 0
        official_major_claim_ids: set[str] = set()
        if protocol.output_mode == "raw":
            for source in relevant_sources:
                for branch in (source.metadata_json or {}).get("query_branches", []):
                    if branch in branch_counts:
                        branch_counts[branch] += 1
        for claim, link, source in evidence:
            if link.entailment_score < 0.5 or claim.status in {"irrelevant", "unresolved"}:
                continue
            for branch in (source.metadata_json or {}).get("query_branches", []):
                if branch in branch_counts:
                    branch_counts[branch] += 1
            if (
                claim.importance == "major"
                and (source.metadata_json or {}).get("authority") == "official"
            ):
                official_major_claim_ids.add(claim.id)
        if official_entities:
            covered_entities = 0
            evidence_source_ids = {
                source.id
                for claim, link, source in evidence
                if link.entailment_score >= 0.5 and claim.status not in {"irrelevant", "unresolved"}
            }
            for entity in official_entities:
                if any(
                    (source.metadata_json or {}).get("authority") == "official"
                    and domain_matches(source.url, entity["domains"])
                    and (protocol.output_mode == "raw" or source.id in evidence_source_ids)
                    for source in relevant_sources
                ):
                    covered_entities += 1
            authority_coverage = covered_entities / len(official_entities)
        else:
            authority_coverage = (
                len(official_major_claim_ids) / len(major)
                if major
                else (
                    1.0
                    if protocol.output_mode == "raw"
                    and any(
                        (source.metadata_json or {}).get("authority") == "official"
                        for source in relevant_sources
                    )
                    else (1.0 if not protocol.authority_policy.strict_for_major_claims else 0.0)
                )
            )
        audited_count = len(audited)
        if protocol.output_mode == "raw":
            audited_count = len(major)
        source_payloads = [
            {
                "title": source.title,
                "url": source.url,
                "persistent_id": source.persistent_id,
            }
            for source in sources
        ]
        measured_sentinel_recall, missed_sentinels = sentinel_recall(
            protocol.sentinel_sources,
            source_payloads,
        )
        provider_incidence = []
        provider_union: set[str] = set()
        for source in relevant_sources:
            metadata = source.metadata_json or {}
            providers = list(metadata.get("discovered_by_connectors") or [])
            if not providers:
                providers = list((metadata.get("provider_snapshots") or {}).keys())
            if not providers:
                providers = [source.connector_id]
            provider_union.update(providers)
            provider_incidence.append(providers)
        completeness, discovery_observations = estimated_completeness(provider_incidence)
        discovery_stats = dict(state.get("discovery_stats", {}))
        reserve_audited = int(discovery_stats.get("reserve_audited", 0))
        reserve_relevant = int(discovery_stats.get("reserve_relevant", 0))
        reserve_false_negative_rate = reserve_relevant / reserve_audited if reserve_audited else 0.0
        accepted_relevant = max(
            0,
            int(discovery_stats.get("relevant_admitted", 0)) - reserve_relevant,
        )
        relative_recall = accepted_relevant / max(
            1,
            accepted_relevant + reserve_relevant,
        )
        round_relevant = int(discovery_stats.get("round_relevant_admitted", 0))
        citation_frontier_novelty = int(discovery_stats.get("round_citation_relevant", 0)) / max(
            1, round_relevant
        )
        unavailable_connectors = set(state.get("unavailable_connectors", []))
        required_connectors = set(protocol.connectors.required_connectors)
        available_connectors = set(state.get("available_connectors", []))
        connector_success_rates = state.get("connector_success_rates", {})
        operational_required_connectors = {
            connector_id
            for connector_id in available_connectors
            if float(connector_success_rates.get(connector_id, 0.0)) >= 0.5
        }
        critical_connector_coverage = (
            len(required_connectors & operational_required_connectors) / len(required_connectors)
            if required_connectors
            else 1.0
        )
        quality_diagnostics_active = (
            len(provider_union) >= 2
            or reserve_audited > 0
            or int(discovery_stats.get("citation_candidates_selected", 0)) > 0
        )
        coverage = calculate_coverage(
            protocol,
            [s.family for s in relevant_sources],
            dict(branch_counts),
            len(major),
            audited_count,
            len(unresolved),
            rate,
            previous.saturated_rounds,
            authority_coverage=authority_coverage,
            claim_audit_required=protocol.output_mode != "raw",
            sentinel_recall=measured_sentinel_recall,
            estimated_completeness=completeness,
            relative_recall=relative_recall,
            citation_frontier_novelty=citation_frontier_novelty,
            reserve_false_negative_rate=reserve_false_negative_rate,
            critical_connector_coverage=critical_connector_coverage,
            discovery_observations=discovery_observations,
            quality_diagnostics_active=quality_diagnostics_active,
        )
        budget_started_at = datetime.fromisoformat(
            state.get("budget_started_at", datetime.now(timezone.utc).isoformat()).replace(
                "Z",
                "+00:00",
            )
        )
        elapsed = max(
            0.0,
            (datetime.now(timezone.utc) - budget_started_at).total_seconds() / 60,
        )
        source_budget_hit = (
            protocol.budget.max_sources is not None and len(sources) >= protocol.budget.max_sources
        )
        literature_budget_mode = (
            protocol.research_mode == "literature_scan"
            and protocol.budget.exhaustive_until_budget
        )
        round_budget_hit = (
            round_number >= protocol.budget.max_rounds
            and not literature_budget_mode
        )
        budget_hit = (
            round_budget_hit
            or elapsed >= protocol.budget.max_wall_minutes
            or source_budget_hit
        )
        gaps = diagnose_gaps(
            protocol,
            coverage,
            [source.family for source in relevant_sources],
            [{"id": claim.id, "text": claim.text} for claim in unresolved],
            dict(branch_counts),
            state.get("branch_queries", {}),
            missed_sentinels,
        )
        attempted_missions = set(state.get("attempted_missions", []))
        exhausted = not recovery_missions(
            protocol,
            gaps,
            attempted_missions,
        )
        no_operational_connectors = not state.get("available_connectors", [])
        empty_recovery_exhausted = (
            consecutive_empty_recovery_rounds
            >= protocol.stopping_criteria.max_consecutive_empty_recovery_rounds
        )
        probe_strategies_exhausted = (
            literature_budget_mode
            and round_new_source_versions == 0
            and exhausted
            and not literature_scan_probe_missions(
                protocol,
                round_number + 1,
                attempted_missions,
            )
        )
        if literature_budget_mode:
            # In inventory mode coverage is a diagnostic, not an early-stop trigger.
            # Continue trying diversified probes while collection time remains.
            stop_reason = (
                "budget_exhausted"
                if budget_hit or no_operational_connectors
                else (
                    "recovery_exhausted_no_progress"
                    if empty_recovery_exhausted or probe_strategies_exhausted
                    else "expand"
                )
            )
        else:
            stop_reason = (
                "coverage_sufficient"
                if coverage.sufficient
                else ("budget_exhausted" if budget_hit or exhausted else "expand")
            )
        if stop_reason == "recovery_exhausted_no_progress":
            coverage.sufficient = False
            if "recovery_no_progress" not in coverage.reasons:
                coverage.reasons.append("recovery_no_progress")
        discovery_stats = dict(state.get("discovery_stats", {}))
        if round_number > 1 and round_new_source_versions == 0:
            if int(discovery_stats.get("round_provider_candidates", 0)) == 0:
                no_progress_reason = "no_provider_candidates"
            elif int(discovery_stats.get("round_novel_candidates", 0)) == 0:
                no_progress_reason = "no_novel_candidates"
            elif int(discovery_stats.get("round_selected_candidates", 0)) == 0:
                no_progress_reason = "no_admitted_candidates"
            elif int(discovery_stats.get("round_acquisition_successful", 0)) == 0:
                no_progress_reason = "acquisition_failed"
            else:
                no_progress_reason = "no_new_source_versions"
            await self.repo.event(
                state["run_id"],
                "recovery_no_progress",
                {
                    "round": round_number,
                    "reason": no_progress_reason,
                    "consecutive_empty_rounds": consecutive_empty_recovery_rounds,
                    "limit": (
                        protocol.stopping_criteria.max_consecutive_empty_recovery_rounds
                    ),
                    "terminal": stop_reason == "recovery_exhausted_no_progress",
                    "diagnostics": {
                        "provider_candidates": int(
                            discovery_stats.get("round_provider_candidates", 0)
                        ),
                        "novel_candidates": int(
                            discovery_stats.get("round_novel_candidates", 0)
                        ),
                        "selected_candidates": int(
                            discovery_stats.get("round_selected_candidates", 0)
                        ),
                        "acquisition_successful": int(
                            discovery_stats.get("round_acquisition_successful", 0)
                        ),
                        "content_rejected": int(
                            discovery_stats.get("round_content_rejected", 0)
                        ),
                        "new_source_versions": round_new_source_versions,
                    },
                },
            )
        await self.repo.update_run(
            state["run_id"],
            coverage=coverage.model_dump(),
            round_number=round_number,
            sources_count=len(sources),
            claims_count=len(claims),
        )
        await self.repo.event(
            state["run_id"],
            "coverage_gaps",
            {
                "gaps": [gap.model_dump(mode="json") for gap in gaps],
                "stop_reason": stop_reason,
                "discovery_quality": {
                    **discovery_stats,
                    "sentinel_recall": measured_sentinel_recall,
                    "missed_sentinels": missed_sentinels,
                    "estimated_completeness": completeness,
                    "relative_recall": relative_recall,
                    "provider_count": len(provider_union),
                    "citation_frontier_novelty": citation_frontier_novelty,
                    "reserve_false_negative_rate": reserve_false_negative_rate,
                    "critical_connector_coverage": critical_connector_coverage,
                    "unavailable_connectors": sorted(unavailable_connectors),
                    "connector_success_rates": connector_success_rates,
                },
            },
        )
        return {
            "coverage": coverage.model_dump(),
            "gaps": [gap.model_dump(mode="json") for gap in gaps],
            "stop_reason": stop_reason,
            "consecutive_empty_recovery_rounds": consecutive_empty_recovery_rounds,
        }

    def _coverage_route(self, state: PipelineState) -> str:
        if state.get("halted"):
            return "halt"
        return "expand" if state.get("stop_reason") == "expand" else "finish"

    async def plan_recovery(self, state: PipelineState) -> dict:
        await self._boundary(state, "PLAN_RECOVERY")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        round_number = state.get("round_number", 1) + 1
        attempted = set(state.get("attempted_missions", []))
        gaps = [CoverageGap.model_validate(item) for item in state.get("gaps", [])]
        missions = recovery_missions(protocol, gaps, attempted)
        if (
            protocol.research_mode == "literature_scan"
            and protocol.budget.exhaustive_until_budget
            and not missions
        ):
            missions = literature_scan_probe_missions(protocol, round_number, attempted)
        await self.repo.event(
            state["run_id"],
            "recovery_plan",
            {
                "round": round_number,
                "missions": [mission.model_dump(mode="json") for mission in missions],
            },
        )
        branch_queries = dict(state.get("branch_queries", {}))
        for mission in missions:
            branch_queries.setdefault(mission.branch_id, mission.query)
        return {
            "queries": [mission.query for mission in missions],
            "missions": [mission.model_dump(mode="json") for mission in missions],
            "attempted_missions": sorted(attempted),
            "required_branch_ids": state.get("required_branch_ids", []),
            "branch_queries": branch_queries,
            "round_number": round_number,
        }

    async def audit(self, state: PipelineState) -> dict:
        await self._boundary(state, "AUDIT")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        if protocol.output_mode == "raw":
            coverage = CoverageMetrics.model_validate(state.get("coverage", {}))
            stopping = protocol.stopping_criteria
            coverage.claim_audit_coverage = 1.0
            coverage.unresolved_major_claims = 0
            coverage.sufficient = (
                coverage.source_family_coverage >= stopping.minimum_source_coverage
                and coverage.query_branch_coverage >= stopping.minimum_query_branch_coverage
                and coverage.saturated_rounds >= stopping.saturation_rounds
                and (
                    not protocol.authority_policy.strict_for_major_claims
                    or coverage.authority_coverage >= 1.0
                )
            )
            reasons = []
            if coverage.source_family_coverage < stopping.minimum_source_coverage:
                reasons.append("source_family_coverage")
            if coverage.query_branch_coverage < stopping.minimum_query_branch_coverage:
                reasons.append("query_branch_coverage")
            if coverage.saturated_rounds < stopping.saturation_rounds:
                reasons.append("query_saturation")
            if (
                protocol.authority_policy.strict_for_major_claims
                and coverage.authority_coverage < 1.0
            ):
                reasons.append("authority_coverage")
            coverage.reasons = reasons
            await self.repo.update_run(state["run_id"], coverage=coverage.model_dump())
            return {"coverage": coverage.model_dump()}
        evidence = await self.repo.list_evidence(state["run_id"])
        by_claim: dict[str, list[tuple]] = defaultdict(list)
        for claim, link, source in evidence:
            by_claim[claim.id].append((link, source))
        claims = await self.repo.list_claims(state["run_id"])
        minimum = protocol.evidence_policy.minimum_independent_sources
        for claim in claims:
            links = by_claim.get(claim.id, [])
            evaluated_links = [
                (
                    e,
                    source,
                    *evidence_quality_gate(
                        claim.text,
                        e.quote,
                        section_path=(e.location or {}).get("section_path"),
                        source_title=source.title,
                        entailment_score=e.entailment_score,
                    ),
                )
                for e, source in links
            ]
            valid_links = [(e, source) for e, source, valid, _ in evaluated_links if valid]
            domains = {
                re.sub(r"^www\.", "", re.sub(r"^https?://", "", s.url).split("/", 1)[0])
                for _, s in valid_links
            }
            supporting = [
                e for e, _ in valid_links if e.direction == "supports" and e.entailment_score >= 0.5
            ]
            contradicting = [e for e, _ in valid_links if e.direction == "contradicts"]
            source_score = max(
                (
                    max(
                        float((source.metadata_json or {}).get("relevance_score", 0.0)),
                        float((source.metadata_json or {}).get("content_relevance_score", 0.0)),
                    )
                    for _, source in links
                ),
                default=0.0,
            )
            quotes = " ".join(link.quote for link, _ in links)
            relevance = claim_relevance(
                f"{claim.text} {quotes}",
                # Quotes keep the source's language, so the question terms have to cover
                # both sides here too.
                " ".join(protocol.research_questions()),
                source_score,
            )
            if relevance < 0.20:
                claim.status = "irrelevant"
            elif len(supporting) >= minimum and len(domains) >= minimum:
                claim.status = "supported"
            elif supporting:
                claim.status = "qualified"
            else:
                claim.status = "unresolved"
            claim.audit = {
                "supporting_evidence": len(supporting),
                "counter_evidence": len(contradicting),
                "independent_domains": len(domains),
                "minimum_required": minimum,
                "question_relevance": relevance,
                "source_relevance": source_score,
                "invalid_evidence": sum(not valid for _, _, valid, _ in evaluated_links),
                "invalid_evidence_reasons": sorted(
                    {reason for _, _, valid, reason in evaluated_links if not valid}
                ),
            }
        await self.session.commit()
        coverage = CoverageMetrics.model_validate(state.get("coverage", {}))
        major = [c for c in claims if c.importance == "major"]
        audited = [
            c
            for c in major
            if c.audit
            and c.audit.get("question_relevance", 0.0) >= 0.20
            and c.status != "irrelevant"
        ]
        unresolved = [c for c in major if c.status in {"unresolved", "irrelevant"}]
        coverage.claim_audit_coverage = round(len(audited) / len(major), 4) if major else 0.0
        coverage.unresolved_major_claims = len(unresolved)
        stopping = ResearchProtocol.model_validate(state["protocol"]).stopping_criteria
        coverage.sufficient = (
            coverage.source_family_coverage >= stopping.minimum_source_coverage
            and coverage.query_branch_coverage >= stopping.minimum_query_branch_coverage
            and coverage.claim_audit_coverage >= stopping.minimum_claim_audit_coverage
            and coverage.saturated_rounds >= stopping.saturation_rounds
            and coverage.unresolved_major_claims <= stopping.unresolved_major_claim_limit
        )
        reasons = []
        if coverage.source_family_coverage < stopping.minimum_source_coverage:
            reasons.append("source_family_coverage")
        if coverage.query_branch_coverage < stopping.minimum_query_branch_coverage:
            reasons.append("query_branch_coverage")
        if coverage.claim_audit_coverage < stopping.minimum_claim_audit_coverage:
            reasons.append("claim_audit_coverage")
        if coverage.saturated_rounds < stopping.saturation_rounds:
            reasons.append("query_saturation")
        if coverage.unresolved_major_claims > stopping.unresolved_major_claim_limit:
            reasons.append("unresolved_major_claims")
        coverage.reasons = reasons
        await self.repo.update_run(state["run_id"], coverage=coverage.model_dump())
        return {"coverage": coverage.model_dump()}

    async def adversarial_review(self, state: PipelineState) -> dict:
        await self._boundary(state, "ADVERSARIAL_REVIEW")
        claims = await self.repo.list_claims(state["run_id"])
        weak = [c.id for c in claims if c.status != "supported"]
        excluded = [
            c.id
            for c in claims
            if c.status in {"irrelevant", "unresolved"}
            or c.audit.get("question_relevance", 0.0) < 0.20
        ]
        await self.repo.event(
            state["run_id"],
            "adversarial_review",
            {"weak_claim_ids": weak, "excluded_claim_ids": excluded},
        )
        outline = {
            "title": ResearchProtocol.model_validate(state["protocol"]).title,
            "sections": [
                "Yönetici özeti",
                "Kapsam ve yöntem",
                "Denetlenmiş temel bulgular",
                "Çelişen kanıtlar",
                "Belirsizlikler ve kapsam boşlukları",
                "Sonuç",
            ],
            "supported_claims": sum(claim.status == "supported" for claim in claims),
            "qualified_claims": sum(claim.status == "qualified" for claim in claims),
        }
        response = await self._maybe_hitl(
            state,
            "outline_review",
            {"outline": outline},
            "ADVERSARIAL_REVIEW",
        )
        if response and not response.get("approved", False):
            return {"report_outline_guidance": str(response.get("modifications", ""))[:5000]}
        return {}

    async def synthesize_export(self, state: PipelineState) -> dict:
        await self._boundary(state, "SYNTHESIZE_EXPORT")
        protocol = ResearchProtocol.model_validate(state["protocol"])
        coverage = CoverageMetrics.model_validate(state.get("coverage", {}))
        artifacts = await build_exports(
            state["run_id"],
            protocol,
            coverage,
            self.repo,
            self.store,
            self.llm,
            outline_guidance=state.get("report_outline_guidance", ""),
        )
        await self._emit_llm_metrics(state["run_id"], "SYNTHESIZE_EXPORT")
        await self.repo.event(state["run_id"], "artifacts", {"names": artifacts})
        return {}
