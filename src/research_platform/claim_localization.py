"""Claim statements in the language the report is written in.

A run works in English whatever language it was asked in, so `claim.text` is English. Two
places put that text into the report unchanged: the synthesis fallback that runs whenever the
model's own prose is rejected, and the atomic-findings appendices. In a Turkish report both
came out English, which is what readers were seeing.

Translation happens once per run, here, and the result is handed to every surface -- Word,
the full markdown report and the executive summary -- so the three cannot disagree and the
cost is paid once rather than three times.

Nothing is overwritten in the database. This is a display projection, exactly like the figure
captions in `figure_analysis`: evidence matching, the audit trail and `content_hash` stay
bound to the English statement.
"""

from __future__ import annotations

import json
from typing import Any

from .language_guard import (
    foreign_sentences,
    language_matches,
    numbers_match,
    target_language_name,
    text_snippet,
)
from .llm import LLMProvider

#: Longer than a claim ever is; the cap exists so one malformed record cannot fill a prompt.
_CLAIM_CHARS = 1000

#: Two isolated attempts, as with figure captions. A third buys little: a model that has
#: produced the wrong language twice with the failure quoted back to it is not about to
#: produce the right one.
_ATTEMPTS = 2

#: Claims per translation call. Small enough that one prompt stays inside the local model's
#: latency budget, large enough that a normal run still costs a handful of calls.
_BATCH_SIZE = 8

_SYSTEM = (
    "You translate research findings for a report, preserving meaning exactly. "
    'Answer with JSON only: {"items": [{"id": "<id>", "text": "<translation>"}]}. '
    "Keep every number, unit, percentage and citation marker such as [S01] unchanged. "
    "Keep proper names, product names and acronyms as they are. "
    "Do not add, remove or soften any claim."
)


def _new_diagnostics() -> dict[str, Any]:
    return {
        "direct": 0,
        "translated": 0,
        "failed": 0,
        "reasons": {},
        "call_count": 0,
    }


def _record_failure(diagnostics: dict[str, Any], reason: str) -> None:
    diagnostics["reasons"][reason] = int(diagnostics["reasons"].get(reason, 0)) + 1


def _prompt(pending: dict[str, str], language: str, failure: str = "") -> str:
    listing = "\n".join(f"- {item_id}: {text}" for item_id, text in pending.items())
    body = (
        f"Translate each item into {target_language_name(language)}.\n\n"
        f"Items:\n{listing}"
    )
    if failure:
        body += (
            f"\n\nYour previous answer was rejected: {failure}\n"
            "Return every id, keep the numbers identical, and answer in the requested "
            "language."
        )
    return body


def _batched(items: dict[str, str], size: int) -> list[dict[str, str]]:
    """Split the work so one slow prompt cannot cost every claim its translation.

    Measured: a run asking for 7 claims in one call succeeded; the same call with 31 timed
    out and all 31 kept their English text. The prompt grows with the claims, and the local
    model's ceiling is not a function of how many findings a run happens to produce.
    """
    keys = list(items)
    return [
        {key: items[key] for key in keys[start : start + size]}
        for start in range(0, len(keys), size)
    ]


async def _translate_batch(
    llm: LLMProvider,
    batch: dict[str, str],
    language: str,
    localized: dict[str, str],
    diagnostics: dict[str, Any],
) -> None:
    """Two isolated attempts for one batch, validating every item that comes back."""
    pending = dict(batch)
    failure = ""
    for _ in range(_ATTEMPTS):
        if not pending:
            return
        try:
            diagnostics["call_count"] += 1
            answer = await llm.complete_json(_SYSTEM, _prompt(pending, language, failure))
        except Exception as exc:  # noqa: BLE001 - the original text stands, the run does not stop
            # Retried rather than abandoned. An earlier version broke out of the loop here,
            # so one timeout cost a whole run its translations even though a second attempt
            # was budgeted for exactly this. The message is recorded because "provider_error"
            # alone left the next reader guessing which provider failed and how.
            failure = f"{type(exc).__name__}: {exc}"[:200]
            _record_failure(diagnostics, "provider_error")
            diagnostics.setdefault("errors", []).append(failure)
            continue
        if isinstance(answer, str):
            try:
                answer = json.loads(answer)
            except (TypeError, ValueError):
                failure = "invalid_json"
                _record_failure(diagnostics, "invalid_json")
                continue
        items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(items, list):
            failure = "invalid_json"
            _record_failure(diagnostics, "invalid_json")
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if item_id not in pending:
                _record_failure(diagnostics, "unknown_id")
                continue
            translated = text_snippet(item.get("text"), _CLAIM_CHARS)
            if not translated:
                reason = "empty_text"
            elif not language_matches(translated, language):
                reason = "language_mismatch"
            elif not numbers_match(pending[item_id], translated):
                reason = "number_mismatch"
            else:
                localized[item_id] = translated
                diagnostics["translated"] += 1
                pending.pop(item_id, None)
                continue
            _record_failure(diagnostics, reason)
            failure = reason


async def localize_claim_texts(
    llm: LLMProvider,
    claims: list[Any],
    language: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Claim id to statement in `language`, plus what happened while getting there.

    A claim already in the target language is never sent anywhere. A translation that loses a
    number, comes back in the wrong language or arrives empty is refused and the **original
    English is kept** -- showing an invented Turkish sentence would be worse than showing an
    English one, because the reader cannot tell it is invented.
    """
    diagnostics = _new_diagnostics()
    localized: dict[str, str] = {}
    pending: dict[str, str] = {}
    for claim in claims:
        claim_id = str(getattr(claim, "id", "") or "")
        rendered = text_snippet(getattr(claim, "text", ""), _CLAIM_CHARS)
        if not claim_id or not rendered:
            continue
        if language_matches(rendered, language):
            localized[claim_id] = rendered
            diagnostics["direct"] += 1
        else:
            pending[claim_id] = rendered
    for batch in _batched(pending, _BATCH_SIZE):
        await _translate_batch(llm, batch, language, localized, diagnostics)
    # Whatever no batch managed to translate. Batches fail independently, so a timeout on
    # one no longer decides the language of the whole report.
    pending = {
        item_id: text for item_id, text in pending.items() if item_id not in localized
    }
    for item_id, original in pending.items():
        # Kept rather than dropped: an English finding still carries its evidence, and a
        # missing one would silently shorten the report.
        localized[item_id] = original
        diagnostics["failed"] += 1
    return localized, diagnostics


async def sweep_foreign_prose(
    llm: LLMProvider,
    texts: dict[str, str],
    language: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Last pass over the report's prose: find sentences in the wrong language and fix them.

    The root-cause repairs upstream should leave nothing here, and finding nothing is the
    point -- a zero count is evidence they held. It exists because "the report is in one
    language" is a promise to the reader, and a promise that depends on every upstream path
    being correct is weaker than one that is checked at the end.

    Only the offending sentences are translated, not the paragraph around them. Re-translating
    prose that was already correct costs tokens and can only degrade it.

    Attribution lines -- citations, source titles, URLs, quotations -- are never touched;
    `foreign_sentences` skips them, because a translated title cannot be looked up.
    """
    diagnostics = _new_diagnostics()
    swept: dict[str, str] = dict(texts)
    pending: dict[str, str] = {}
    owners: dict[str, str] = {}
    for key, value in texts.items():
        rendered = str(value or "")
        for index, sentence in enumerate(foreign_sentences(rendered, language)):
            item_id = f"{key}:{index}"
            pending[item_id] = sentence
            owners[item_id] = key
    diagnostics["scanned"] = len(texts)
    diagnostics["foreign"] = len(pending)
    if not pending:
        return swept, diagnostics
    failure = ""
    remaining = dict(pending)
    for _ in range(_ATTEMPTS):
        if not remaining:
            break
        try:
            diagnostics["call_count"] += 1
            answer = await llm.complete_json(_SYSTEM, _prompt(remaining, language, failure))
        except Exception:  # noqa: BLE001 - the original prose stands rather than the run failing
            _record_failure(diagnostics, "provider_error")
            break
        if isinstance(answer, str):
            try:
                answer = json.loads(answer)
            except (TypeError, ValueError):
                failure = "invalid_json"
                _record_failure(diagnostics, "invalid_json")
                continue
        items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(items, list):
            failure = "invalid_json"
            _record_failure(diagnostics, "invalid_json")
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if item_id not in remaining:
                _record_failure(diagnostics, "unknown_id")
                continue
            translated = text_snippet(item.get("text"), _CLAIM_CHARS)
            if not translated:
                reason = "empty_text"
            elif not language_matches(translated, language):
                reason = "language_mismatch"
            elif not numbers_match(remaining[item_id], translated):
                reason = "number_mismatch"
            else:
                key = owners[item_id]
                swept[key] = swept[key].replace(remaining[item_id], translated, 1)
                diagnostics["translated"] += 1
                remaining.pop(item_id, None)
                continue
            _record_failure(diagnostics, reason)
            failure = reason
    diagnostics["failed"] = len(remaining)
    return swept, diagnostics
