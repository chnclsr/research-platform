"""Choose the source families a question actually needs, instead of always sweeping.

Every run starts on `CORE_FAMILIES` -- web, academic, official_legal, code_data -- whatever
was asked. A question about case law and a question about a training recipe get the same
four families and the same connector fan-out, which costs calls on families that were never
going to answer.

The model picks from a closed catalogue of presets that are already known to validate, so
the output space contains no invalid answer; it never writes a family list of its own. What
comes back is checked against the protocol validator and repaired at most once, because the
family minimums can exceed a narrow `max_sources` budget and that is a real, reachable
failure rather than a hypothetical one.
"""

from __future__ import annotations

import json
from typing import Any

from .llm import LLMProvider
from .schemas import ResearchProtocol
from .scoping import FAMILY_PRESET_GUIDE, apply_families, scoping_text

_SYSTEM = (
    "You choose which families of sources a research run should search. "
    "Answer with JSON only: {\"preset\": \"<key>\", \"reason\": \"<one sentence>\"}. "
    "The preset must be one of the keys you are given; never invent a key and never "
    "return a list of families."
)


def _user_prompt(question: str, error: str = "") -> str:
    catalogue = "\n".join(f"- {key}: {guide}" for key, guide in FAMILY_PRESET_GUIDE.items())
    body = f"Research question:\n{question}\n\nAvailable presets:\n{catalogue}"
    if error:
        body += (
            f"\n\nYour previous answer was rejected by validation:\n{error}\n"
            "Choose a preset that needs fewer families."
        )
    return body


def _read_preset(answer: Any) -> tuple[str, str] | None:
    """The preset and its reason, or None when the answer is unusable.

    Anything outside the catalogue is refused rather than mapped to a neighbour: a guess
    about what the model meant is exactly the kind of unseen decision this layer exists to
    avoid.
    """
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except (TypeError, ValueError):
            return None
    if not isinstance(answer, dict):
        return None
    preset = str(answer.get("preset") or "").strip()
    if preset not in FAMILY_PRESET_GUIDE:
        return None
    return preset, str(answer.get("reason") or "").strip()[:300]


async def synthesize_source_selection(
    llm: LLMProvider,
    protocol: ResearchProtocol,
) -> tuple[ResearchProtocol, dict | None]:
    """Return the protocol with a chosen preset applied, and the event describing it.

    Returns the protocol unchanged with `None` whenever anything is off -- an unreachable
    model, a broken answer, a key outside the catalogue, a selection that will not
    validate twice. The deterministic fallback is today's behaviour, so failing here costs
    nothing that was not already the default.
    """
    text = scoping_text(protocol.display_language())
    calls = 0
    error = ""
    for attempt in range(2):
        try:
            calls += 1
            answer = await llm.complete_json(
                _SYSTEM, _user_prompt(protocol.primary_question, error)
            )
        except Exception:  # noqa: BLE001 - a model outage must not decide the protocol
            return protocol, None
        chosen = _read_preset(answer)
        if chosen is None:
            return protocol, None
        preset, reason = chosen
        payload = protocol.model_dump(mode="json")
        detail = apply_families(payload, preset, text, source="synthesis")
        if detail is None:
            return protocol, None
        try:
            updated = ResearchProtocol.model_validate(payload)
        except ValueError as exc:
            # The reachable case: family minimums above a narrow max_sources budget.
            # One repair, with the validator's own words -- then the default stands.
            error = str(exc)[:500]
            continue
        return updated, {
            "preset": preset,
            "reason": reason,
            "families": [family.value for family in updated.connectors.included_families],
            "repaired": attempt > 0,
            "call_count": calls,
        }
    return protocol, None
