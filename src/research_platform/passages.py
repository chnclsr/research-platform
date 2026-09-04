from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Any

# Re-exported so existing importers keep working; the parser itself now lives in parsers/.
from .parsers.html import StructuredHTMLParser, html_to_markdown
from .relevance import terms
from .schemas import ExtractedClaim, Passage

__all__ = ["StructuredHTMLParser", "html_to_markdown"]


INTENT_EXPANSIONS = {
    "limitation": {"constraint", "risk", "security", "captcha", "challenge", "failure", "slow", "rate", "untrusted"},
    "limitations": {"constraint", "risk", "security", "captcha", "challenge", "failure", "slow", "rate", "untrusted"},
    "security": {"auth", "token", "redirect", "untrusted", "scrub", "captcha", "challenge", "private"},
    "install": {"setup", "deploy", "docker", "python", "requirements", "verify", "test", "pytest"},
    "installed": {"setup", "deploy", "docker", "python", "requirements", "verify", "test", "pytest"},
    "architecture": {"components", "server", "stack", "dependency", "database", "api", "mcp"},
    "capabilities": {"features", "endpoints", "providers", "extraction", "browser", "search"},
}

BOILERPLATE_SECTIONS = {
    "navigation menu", "footer", "footer navigation", "saved searches", "appearance settings",
}


def expanded_terms(question: str) -> set[str]:
    output = terms(question)
    for token in list(output):
        output.update(INTENT_EXPANSIONS.get(token, set()))
    return output


def _sections(content: str) -> list[tuple[str, int, int]]:
    headings = list(re.finditer(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", content))
    if not headings:
        return [("Document", 0, len(content))]
    output: list[tuple[str, int, int]] = []
    if headings[0].start() > 0 and content[:headings[0].start()].strip():
        output.append(("Document", 0, headings[0].start()))
    path: list[tuple[int, str]] = []
    for index, heading in enumerate(headings):
        level = len(heading.group(0).lstrip()) - len(heading.group(0).lstrip().lstrip("#"))
        title = heading.group(1).strip()
        path = [(item_level, name) for item_level, name in path if item_level < level]
        path.append((level, title))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        output.append((" > ".join(name for _, name in path), heading.end(), end))
    return output


def chunk_document(
    content: str,
    source_version_id: str,
    *,
    target_tokens: int = 700,
    overlap_tokens: int = 100,
) -> list[Passage]:
    passages: list[Passage] = []
    step = max(1, target_tokens - overlap_tokens)
    for section_path, section_start, section_end in _sections(content):
        section_text = content[section_start:section_end]
        words = list(re.finditer(r"\S+", section_text))
        if not words:
            continue
        for offset in range(0, len(words), step):
            window = words[offset:offset + target_tokens]
            if not window:
                break
            local_start, local_end = window[0].start(), window[-1].end()
            start, end = section_start + local_start, section_start + local_end
            text = content[start:end].strip()
            if len(text) < 80:
                continue
            passages.append(Passage(
                source_version_id=source_version_id,
                chunk_index=len(passages),
                section_path=section_path,
                page_number=(
                    int(match.group(1)) if (match := re.search(r"(?:^| > )Page (\d+)(?:$| > )", section_path))
                    else None
                ),
                start_char=start,
                end_char=end,
                text=text,
                token_count=len(window),
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            ))
            if offset + target_tokens >= len(words):
                break
    return passages


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def retrieve_passages(
    passages: list[Passage],
    questions: list[str],
    query_embeddings: list[list[float]] | None = None,
    *,
    per_question: int = 8,
    max_total: int | None = None,
    max_per_source: int | None = None,
) -> list[Passage]:
    if not passages or not questions:
        return []
    document_frequency: Counter[str] = Counter()
    passage_terms: list[Counter[str]] = []
    for passage in passages:
        counts = Counter(terms(f"{passage.section_path} {passage.text}"))
        passage_terms.append(counts)
        document_frequency.update(counts.keys())
    total = len(passages)
    total_limit = max_total or per_question * len(questions)
    source_limit = max_per_source or max(3, per_question // 2)
    per_branch_target = min(per_question, math.ceil(total_limit / len(questions)))
    ranked_by_question: list[list[tuple[float, Passage]]] = []

    for question_index, question in enumerate(questions):
        query_terms = expanded_terms(question)
        raw: list[tuple[float, float, float, Passage]] = []
        dense_query = (query_embeddings or [])[question_index] if query_embeddings and question_index < len(query_embeddings) else []
        for index, passage in enumerate(passages):
            counts = passage_terms[index]
            length = max(1, sum(counts.values()))
            bm25 = 0.0
            for token in query_terms:
                frequency = counts.get(token, 0)
                if not frequency:
                    continue
                inverse = math.log(1 + (total - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
                bm25 += inverse * (frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * length / 120))
            lexical = bm25 / (bm25 + 3.0) if bm25 else 0.0
            dense = max(0.0, _cosine(passage.embedding, dense_query))
            section_overlap = len(terms(passage.section_path) & query_terms)
            section_score = min(1.0, section_overlap / 2)
            hybrid = 0.50 * lexical + 0.40 * dense + 0.10 * section_score
            section_lower = passage.section_path.lower()
            if any(marker in section_lower for marker in BOILERPLATE_SECTIONS):
                hybrid *= 0.10
            raw.append((lexical, dense, hybrid, passage))
        lexical_rank = {
            passage.id: rank for rank, (_, _, _, passage) in enumerate(
                sorted(raw, key=lambda item: item[0], reverse=True), start=1,
            )
        }
        dense_rank = {
            passage.id: rank for rank, (_, _, _, passage) in enumerate(
                sorted(raw, key=lambda item: item[1], reverse=True), start=1,
            )
        }
        ranked: list[tuple[float, Passage]] = []
        for lexical, dense, hybrid, passage in raw:
            rrf = (
                1 / (60 + lexical_rank[passage.id])
                + 1 / (60 + dense_rank[passage.id])
            ) / (2 / 61)
            passage_words = terms(passage.text)
            query_coverage = len(passage_words & query_terms) / max(1, len(query_terms))
            prose_quality = min(1.0, len(re.findall(r"[.!?](?:\s|$)", passage.text)) / 4)
            reranked = 0.50 * rrf + 0.30 * hybrid + 0.15 * query_coverage + 0.05 * prose_quality
            ranked.append((reranked, passage))
        ranked.sort(key=lambda item: item[0], reverse=True)
        kept: list[tuple[float, Passage]] = []
        per_section: Counter[str] = Counter()
        seen_content: set[str] = set()
        for score, passage in ranked:
            if score <= 0:
                continue
            section_key = passage.section_path.lower()
            if per_section[section_key] >= 2:
                continue
            if passage.content_hash in seen_content:
                continue
            kept.append((score, passage))
            per_section[section_key] += 1
            seen_content.add(passage.content_hash)
            # Keep a reserve behind the branch quota. The global diversity pass may need
            # to skip several high-ranked passages from an already saturated source.
            if len(kept) >= max(per_branch_target * 4, per_question):
                break
        ranked_by_question.append(kept)

    selected: dict[str, Passage] = {}
    selected_order: list[str] = []
    scores: dict[str, float] = defaultdict(float)
    source_counts: Counter[str] = Counter()
    branch_counts: Counter[int] = Counter()
    positions = [0 for _ in questions]

    def take(question_index: int, *, enforce_source_limit: bool) -> bool:
        ranked = ranked_by_question[question_index]
        while positions[question_index] < len(ranked):
            score, passage = ranked[positions[question_index]]
            positions[question_index] += 1
            if passage.id in selected:
                branch_counts[question_index] += 1
                scores[passage.id] = max(scores[passage.id], score)
                return True
            if enforce_source_limit and source_counts[passage.source_version_id] >= source_limit:
                continue
            selected[passage.id] = passage
            selected_order.append(passage.id)
            source_counts[passage.source_version_id] += 1
            branch_counts[question_index] += 1
            scores[passage.id] = max(scores[passage.id], score)
            return True
        return False

    # Round-robin is the contract: a generic review on the primary question cannot consume
    # the entire global allowance before a dataset or evaluation branch gets a turn.
    while len(selected) < total_limit:
        progress = False
        for question_index in range(len(questions)):
            if branch_counts[question_index] >= per_branch_target:
                continue
            progress = take(question_index, enforce_source_limit=True) or progress
            if len(selected) >= total_limit:
                break
        if not progress:
            break

    def fill(*, enforce_source_limit: bool) -> None:
        reserve = sorted(
            (
                (score, question_index, passage)
                for question_index, ranked in enumerate(ranked_by_question)
                for score, passage in ranked
                if passage.id not in selected
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        for score, _question_index, passage in reserve:
            if len(selected) >= total_limit:
                return
            if passage.id in selected:
                continue
            if enforce_source_limit and source_counts[passage.source_version_id] >= source_limit:
                continue
            selected[passage.id] = passage
            selected_order.append(passage.id)
            source_counts[passage.source_version_id] += 1
            scores[passage.id] = max(scores[passage.id], score)

    fill(enforce_source_limit=True)
    # A small corpus should still use its evidence. Relax diversity only after every source
    # that could contribute under the approved cap has had the opportunity to do so.
    if len(selected) < total_limit:
        fill(enforce_source_limit=False)

    matched: dict[str, set[str]] = defaultdict(set)
    for question, ranked in zip(questions, ranked_by_question):
        for score, passage in ranked:
            if passage.id in selected:
                matched[passage.id].add(question)
                scores[passage.id] = max(scores[passage.id], score)

    output = []
    for passage_id in selected_order:
        passage = selected[passage_id]
        passage.retrieval_score = round(scores[passage_id], 4)
        passage.matched_questions = sorted(matched[passage_id])
        output.append(passage)
    return output


def neighbor_context(passage: Passage, all_passages: list[Passage]) -> str:
    neighbors = [
        item for item in all_passages
        if item.source_version_id == passage.source_version_id
        and abs(item.chunk_index - passage.chunk_index) == 1
    ]
    return "\n\n".join(
        f"[{item.section_path}; neighboring passage]\n{item.text[:1800]}" for item in neighbors
    )


def relevant_sentence_claims(
    passage: Passage,
    questions: list[str],
    source_candidate_id: str,
    *,
    limit: int = 6,
) -> list[ExtractedClaim]:
    query_terms = set().union(*(expanded_terms(question) for question in questions))
    candidates: list[tuple[int, str]] = []
    for match in re.finditer(r"(?m)^[ \t]*(\S[^\n]{35,700})[ \t]*$", passage.text):
        value = match.group(1).strip()
        candidates.append((passage.text.find(value, match.start()), value))
    for match in re.finditer(r"(?m)(?:^|(?<=[.!?]))\s*([^\n.!?][^\n.!?]{35,700}[.!?]?)", passage.text):
        value = match.group(1).strip()
        candidates.append((passage.text.find(value, match.start()), value))
    ranked: list[tuple[float, int, str]] = []
    seen: set[str] = set()
    for local_start, sentence in candidates:
        if sentence.lower() in seen:
            continue
        seen.add(sentence.lower())
        sentence_terms = terms(sentence)
        overlap = sentence_terms & query_terms
        score = len(overlap) / max(1, min(len(sentence_terms), 10))
        if len(overlap) >= 2 and score >= 0.20:
            prose_bonus = 0.15 if sentence.endswith((".", "!", "?")) else 0.0
            shell_tokens = re.findall(
                r"\b(pip|pytest|python|docker|curl|git)\b", sentence, re.IGNORECASE,
            )
            code_penalty = 0.20 if (
                re.match(r"\s*(pip|pytest|python|docker|curl|git)\b", sentence, re.IGNORECASE)
                or len(shell_tokens) >= 2 or re.search(r"[{}\\]|--[a-z]", sentence)
            ) else 0.0
            ranked.append((score + prose_bonus - code_penalty, local_start, sentence))
    output = []
    for score, local_start, sentence in sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]:
        output.append(ExtractedClaim(
            text=sentence,
            source_candidate_id=source_candidate_id,
            quote=sentence,
            start_char=local_start,
            end_char=local_start + len(sentence),
            direction="supports",
            confidence=round(min(0.98, 0.70 + score * 0.25), 4),
            passage_id=passage.id,
            section_path=passage.section_path,
            page_number=passage.page_number,
            original_start_char=passage.start_char + local_start,
            original_end_char=passage.start_char + local_start + len(sentence),
            retrieval_score=passage.retrieval_score,
        ))
    return output


def merge_passage_claims(
    model_claims: list[ExtractedClaim], deterministic_claims: list[ExtractedClaim],
) -> list[ExtractedClaim]:
    existing_texts = {claim.text.lower().strip() for claim in model_claims}
    supplements = [
        claim for claim in deterministic_claims
        if claim.text.lower().strip() not in existing_texts
    ]
    return [*model_claims, *supplements]


def passage_payload(passage: Passage) -> dict[str, Any]:
    return passage.model_dump(mode="json")
