"""Decide a source's scope role from proof, not from the model's label.

The semantic judge proposes `scope_role`, per-facet `matched` flags and a quote for each.
Nothing here trusts the label: the role is a function of which required facets are
*proven* against the source text and which approved exclusions are *proven* against it.
That is the same split `claim_appraisal` uses -- the model contributes signals, the
deterministic layer decides -- and it is here because the label alone was deciding scope.

WHY THE PREDICATE IS NOT A PLAIN SUBSTRING TEST. Run 01M203HHZXZB61YF59AZZQ2YA4 barred 121
of 254 sources as near-scope. 89 of them had every required facet `matched: true`, every
exclusion decision complete and no exclusion matched -- every signal said in-scope. All 89
were downgraded by one condition: the model's quote was not a raw casefolded substring of
title+snippet+content[:6000]. Classifying those 123 unproven facet quotes:

    38  elided        -- two real fragments joined with "..."
    32  punctuation / letter case only
     5  whitespace only
     1  unicode quote or dash
    39  paraphrase with high token overlap ("AI in CT imaging")
     8  weaker paraphrase or invention

So roughly 60% were formatting, not fabrication, and a 4B quantized model reliably
reproduces meaning but not punctuation. Among the 89 was CT2Rep, the single most on-topic
paper in that run. The paraphrases must stay rejected; the formatting must stop deciding.

WHAT IS DELIBERATELY NOT FIXED HERE. Only the *existence* of a quote is verified, never its
*relevance*: the model decides `matched`, and a quote that is genuinely present but does not
demonstrate the facet still passes. `FacetProof.value_present` is recorded per facet so that
population stays countable and a stricter gate can be added later without a redesign.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .schemas import ResearchScopeCriteria, SourceScopeRole

ProofRoute = Literal[
    "verbatim",
    "normalized",
    "elided",
    "accepted_value",
    "accepted_value_no_quote",
    "unproven",
]

# Roughly two words. A three-character fragment of an elided quote proves nothing, and
# without a floor the model could satisfy every segment with noise.
MIN_QUOTE_SEGMENT_CHARS = 12

_ELLIPSIS = re.compile(r"\[\s*(?:\.\s*\.\s*\.|…)\s*\]|\.\s*\.\s*\.|…")


def signal_key(value: str) -> str:
    """Fold a scope-signal label so wording differences stop deciding scope."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


# The opening of a paper carries its central claim, so it is always kept.
SCOPE_EXCERPT_HEAD_CHARS = 2000
# Enough either side of a hit for the sentence around it to survive, so the judge can
# tell "we image the chest" from "unlike chest imaging, we".
SCOPE_EXCERPT_WINDOW_CHARS = 500
SCOPE_EXCERPT_GAP = "\n[...]\n"


def _signal_pattern(value: str) -> re.Pattern[str] | None:
    """Whole-token matcher for one accepted value, or None if it carries no signal."""
    tokens = signal_key(value).split()
    # Same floor as accepted_value_present: one character matches far too much.
    if not tokens or len("".join(tokens)) < 2:
        return None
    body = r"\W+".join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def scope_excerpt(
    content: str,
    criteria: ResearchScopeCriteria | None,
    *,
    budget: int = 6000,
    head: int = SCOPE_EXCERPT_HEAD_CHARS,
    window: int = SCOPE_EXCERPT_WINDOW_CHARS,
) -> str:
    """Build the text the scope judge reads, from wherever the evidence actually is.

    THE PROBLEM THIS REPLACES. Both the judge's prompt and the proof haystack used
    ``content[:6000]``. Documents in a real run average 74k characters and reach 1.8M, so
    the window covered about 8% of the average source -- and a facet stated on page 12
    could not be proven at any price. Measured on run 01M25MS209TX4AV9DGK4K43K4J: of 41
    near_scope sources, 31 had every unproven facet's accepted value present in the
    document, only past the cutoff. For the anatomy facet not one source was missing the
    term; all 16 had it, outside the window.

    Widening the haystack alone would not have helped. The judge quotes what it read, so
    if it never sees the sentence it cannot cite it, and the quote-based proof routes stay
    empty no matter how much text the verifier is given. Prompt and haystack have to move
    together, which is why this returns one excerpt used for both.

    WHAT IT DOES. Keeps the opening, then adds a window around occurrences of each
    required facet's accepted values -- and each approved exclusion signal -- found
    anywhere in the document. Signals take turns rather than being served in order: a
    facet with forty hits must not spend the budget a facet with one hit needs, and that
    single hit is exactly the one deciding the role. Cost is unchanged: the excerpt is
    capped at the same budget the truncation used.

    Exclusions are included deliberately. Leaving them out would widen the evidence for
    admitting a source without widening the evidence for excluding it, which is not a
    neutral change to a gate.
    """
    text = str(content or "")
    if criteria is None or len(text) <= budget:
        return text[:budget]

    opening_len = min(head, budget)
    opening = text[:opening_len]
    remaining = budget - len(opening)
    if remaining <= len(SCOPE_EXCERPT_GAP):
        return opening

    hits_by_signal: list[list[int]] = []
    for values in (
        *(facet.accepted_values for facet in criteria.required_facets),
        *([signal] for signal in criteria.exclusion_signals),
    ):
        positions: list[int] = []
        for value in values:
            pattern = _signal_pattern(value)
            if pattern is None:
                continue
            positions.extend(
                match.start() for match in pattern.finditer(text, opening_len)
            )
        if positions:
            hits_by_signal.append(sorted(positions))

    spans: list[tuple[int, int]] = []
    consumed = 0
    cursors = [0] * len(hits_by_signal)
    progressed = True
    while progressed and consumed + len(SCOPE_EXCERPT_GAP) < remaining:
        progressed = False
        for index, positions in enumerate(hits_by_signal):
            if cursors[index] >= len(positions):
                continue
            position = positions[cursors[index]]
            cursors[index] += 1
            progressed = True
            start = max(opening_len, position - window // 2)
            end = min(len(text), position + window // 2)
            # A hit already inside a span costs nothing and must not end the round.
            if any(start >= low and end <= high for low, high in spans):
                continue
            cost = (end - start) + len(SCOPE_EXCERPT_GAP)
            if consumed + cost > remaining:
                progressed = False
                break
            spans.append((start, end))
            consumed += cost

    if not spans:
        return opening

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    parts = [opening]
    for start, end in merged:
        parts.append(SCOPE_EXCERPT_GAP)
        parts.append(text[start:end])
    return "".join(parts)


def exclusion_decision(
    signal: str,
    exclusion_assessments: list[dict[str, Any]],
    approved_signals: list[str],
) -> dict[str, Any] | None:
    """Find the model's decision for one approved exclusion signal.

    The prompt asks for the approved label verbatim and the model often rewords or merges
    it. Measured on run 01M1XQTGQEFT08K2F0S0YP3665: 12 of 19 near-scope sources had every
    exclusion recorded under a merged label -- "2D-only or single-slice input" standing for
    two separate approved signals -- so an exact-key lookup read them as undecided and
    downgraded papers whose own classification reason began "direct:". EXACT echoed the
    three labels verbatim and reached primary_in_scope; OrganLens did not and did not.
    Nothing about the sources differed, only the model's formatting.

    Matching is token-subset and must be unambiguous: a fragment that fits more than one
    approved signal ("input") decides neither. Coordination elides the shared head, so
    "2D-only" has to reach "2D-only input" while never reaching "single-slice input".

    A merged label may complete a decision but may never prove an exclusion. Accepting
    "A or B: matched=true" for both A and B would assert a per-signal finding the model
    never made, and EXCLUDED is the one verdict that removes a source outright.
    """
    wanted = signal_key(signal)
    if not wanted:
        return None
    wanted_tokens = set(wanted.split())
    approved_tokens = [set(signal_key(other).split()) for other in approved_signals]
    compound: dict[str, Any] | None = None
    for item in exclusion_assessments:
        label = str(item.get("exclusion") or "")
        if not label:
            continue
        if signal_key(label) == wanted:
            return item
        if item.get("matched") is not False:
            continue
        for part in re.split(r"\s+or\s+|/|,", label):
            tokens = set(signal_key(part).split())
            if not tokens or not tokens <= wanted_tokens:
                continue
            if sum(tokens <= other for other in approved_tokens) != 1:
                continue
            compound = compound or item
            break
    return compound


@dataclass(frozen=True)
class ScopeHaystack:
    """The source text a quote must be found in, in both matching shapes."""

    raw: str
    padded: str

    @classmethod
    def build(cls, assessment_text: str) -> ScopeHaystack:
        text = str(assessment_text or "")
        return cls(raw=text.casefold(), padded=f" {signal_key(text)} ")


def folded_contains(needle: str, haystack: ScopeHaystack) -> bool:
    """Whole-token containment: " ct " never matches inside "reconstruction"."""
    folded = signal_key(needle)
    return bool(folded) and f" {folded} " in haystack.padded


def accepted_value_present(
    accepted_values: Sequence[str], haystack: ScopeHaystack
) -> bool:
    """Is any accepted value of this facet present as a whole token?

    A one-character value is ignored: it carries no signal and matches far too much.
    """
    return any(
        len(signal_key(value)) >= 2 and folded_contains(value, haystack)
        for value in accepted_values
    )


def evidence_route(
    evidence: str,
    haystack: ScopeHaystack,
    accepted_values: Sequence[str] = (),
    *,
    allow_accepted_values: bool = True,
    min_segment_chars: int = MIN_QUOTE_SEGMENT_CHARS,
) -> ProofRoute:
    """How -- if at all -- this quote is proven against the source text.

    First hit wins, most faithful route first. `verbatim` reproduces the pre-fix predicate
    byte for byte, which makes the whole ladder a strict superset of it: nothing admitted
    before this module existed can be rejected by it. It is also the only route that
    survives the 500-character cap cutting a quote mid-word, because every later route
    matches on token boundaries.
    """
    quote = str(evidence or "").strip()
    if quote:
        if quote.casefold() in haystack.raw:
            return "verbatim"
        if folded_contains(quote, haystack):
            return "normalized"
        if _ELLIPSIS.search(quote):
            segments = [
                folded
                for part in _ELLIPSIS.split(quote)
                if len(folded := signal_key(part)) >= min_segment_chars
            ]
            # In order, so fragments cannot be stitched into a proof that reads backwards.
            # Tokens share their separating space, so the next search may start on it.
            cursor = 0
            for segment in segments:
                found = haystack.padded.find(f" {segment} ", cursor)
                if found < 0:
                    break
                cursor = found + len(segment) + 1
            else:
                if segments:
                    return "elided"
    if allow_accepted_values and accepted_value_present(accepted_values, haystack):
        return "accepted_value" if quote else "accepted_value_no_quote"
    return "unproven"


@dataclass(frozen=True)
class FacetProof:
    """What became of one required facet."""

    facet: str
    requested_match: bool | None
    route: ProofRoute
    value_present: bool

    @property
    def proven(self) -> bool:
        return self.route != "unproven"

    @property
    def quote_proved(self) -> bool:
        return self.route in {"verbatim", "normalized", "elided"}

    def as_audit_entry(self) -> dict[str, Any]:
        return {
            "facet_key": self.facet,
            "proof_route": self.route,
            "value_present": self.value_present,
        }


def facet_proof(
    item: dict[str, Any],
    haystack: ScopeHaystack,
    accepted_values: Sequence[str] = (),
) -> FacetProof:
    """One facet's proof. Shared with the pipeline so what is recorded is what was decided.

    A facet the model declined is never rescued by an accepted value: `matched: false` is a
    decision, and the value route exists to repair quoting, not to overrule the judge.
    """
    matched = item.get("matched")
    return FacetProof(
        facet=signal_key(item.get("facet")),
        requested_match=matched if isinstance(matched, bool) else None,
        route=(
            evidence_route(item.get("evidence"), haystack, accepted_values)
            if matched is True
            else "unproven"
        ),
        value_present=accepted_value_present(accepted_values, haystack),
    )


def exclusion_route(item: dict[str, Any], haystack: ScopeHaystack) -> ProofRoute:
    """Accepted values are withheld here.

    An exclusion label whose own words appear in the text is not evidence that the exclusion
    applies -- "PET/CT is not used" says the opposite -- so only a quote may remove a source.
    """
    if item.get("matched") is not True:
        return "unproven"
    return evidence_route(item.get("evidence"), haystack, allow_accepted_values=False)


@dataclass(frozen=True)
class ScopeVerdict:
    """The deterministic scope decision, with everything needed to explain it."""

    role: SourceScopeRole
    requested_role: SourceScopeRole
    facet_proofs: tuple[FacetProof, ...] = ()
    proven_facets: tuple[str, ...] = ()
    unproven_facets: tuple[str, ...] = ()
    excused_facets: tuple[str, ...] = ()
    proven_exclusions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    generated_by: Literal["deterministic"] = "deterministic"

    def as_audit_entry(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "requested_role": self.requested_role.value,
            "role_source": self.generated_by,
            "proven_facets": list(self.proven_facets),
            "unproven_facets": list(self.unproven_facets),
            "excused_facets": list(self.excused_facets),
            "role_reasons": list(self.reasons),
        }


def _decided(item: dict[str, Any] | None) -> bool:
    return (
        item is not None
        and isinstance(item.get("matched"), bool)
        and bool(str(item.get("reason") or "").strip())
    )


def _facets_by_key(facet_assessments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fold model-supplied facet names; on a collision the more decided entry wins.

    The model does not treat the facet field as a closed vocabulary -- run 01M203's
    decisions carry six invented names -- and an unfolded lookup loses a real decision to
    a "model_decision_missing" backfill written under the canonical spelling.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for item in facet_assessments:
        key = signal_key(item.get("facet"))
        if not key:
            continue
        current = by_key.get(key)
        if current is None or (not _decided(current) and _decided(item)):
            by_key[key] = item
    return by_key


def _task_like_facet(criteria: ResearchScopeCriteria) -> str | None:
    """The benchmark lane's excusable facet, found by meaning rather than by literal name.

    `required.discard("task")` assumed decompose always names it `task`; run 01M203's own
    round-0 criteria named it `application_task`, under which the excusal silently never
    fired. Two task-like facets excuse none, the same way an ambiguous exclusion fragment
    decides nothing.
    """
    matches = [
        signal_key(facet.name)
        for facet in criteria.required_facets
        if "task" in signal_key(facet.name).split()
    ]
    return matches[0] if len(matches) == 1 else None


def scope_verdict(
    criteria: ResearchScopeCriteria,
    requested_role: SourceScopeRole,
    facet_assessments: list[dict[str, Any]],
    exclusion_assessments: list[dict[str, Any]],
    assessment_text: str,
    classification_reason: str,
) -> ScopeVerdict:
    """Decide the role from proof. The requested role only picks a lane.

    A bare model label is not evidence in either direction: it can neither admit a source
    whose facets are unproven nor bar one whose facets are proven.
    """
    haystack = ScopeHaystack.build(assessment_text)
    reasons: list[str] = []

    def verdict(role: SourceScopeRole, **kwargs: Any) -> ScopeVerdict:
        return ScopeVerdict(
            role=role,
            requested_role=requested_role,
            reasons=tuple(reasons),
            **kwargs,
        )

    if not str(classification_reason or "").strip():
        reasons.append("classification_reason_missing")
        return verdict(SourceScopeRole.NEAR_SCOPE)

    decisions = {
        signal: exclusion_decision(signal, exclusion_assessments, criteria.exclusion_signals)
        for signal in criteria.exclusion_signals
    }
    for signal in criteria.exclusion_signals:
        item = decisions.get(signal)
        if not _decided(item) or item.get("matched") is not True:
            continue
        key = signal_key(signal)
        if exclusion_route(item, haystack) != "unproven":
            reasons.append(f"exclusion_proven:{key}")
            return verdict(SourceScopeRole.EXCLUDED, proven_exclusions=(key,))
        reasons.append(f"exclusion_claimed_unproven:{key}")
        return verdict(SourceScopeRole.NEAR_SCOPE)

    undecided = [
        signal_key(signal)
        for signal in criteria.exclusion_signals
        if not _decided(decisions.get(signal))
    ]
    if undecided:
        reasons.extend(f"exclusion_decision_missing:{key}" for key in undecided)
        return verdict(SourceScopeRole.NEAR_SCOPE)

    by_key = _facets_by_key(facet_assessments)
    accepted = {signal_key(f.name): f.accepted_values for f in criteria.required_facets}
    required = list(accepted)

    missing = [key for key in required if not _decided(by_key.get(key))]
    if missing:
        reasons.extend(f"facet_decision_missing:{key}" for key in missing)
        return verdict(SourceScopeRole.NEAR_SCOPE)

    excused: tuple[str, ...] = ()
    if requested_role == SourceScopeRole.SUPPORTING_BENCHMARK:
        task_key = _task_like_facet(criteria)
        # Only a facet the model consciously declined; a backfilled non-decision is not a
        # benchmark's admission that it does not perform the task.
        if task_key and by_key[task_key].get("matched") is False:
            excused = (task_key,)
            reasons.append(f"benchmark_task_excused:{task_key}")

    proofs = [facet_proof(by_key[key], haystack, accepted[key]) for key in required]

    proven = tuple(p.facet for p in proofs if p.proven)
    unproven = tuple(p.facet for p in proofs if not p.proven and p.facet not in excused)
    common = {
        "facet_proofs": tuple(proofs),
        "proven_facets": proven,
        "unproven_facets": unproven,
        "excused_facets": excused,
    }
    if unproven:
        reasons.extend(f"facet_unproven:{key}" for key in unproven)
        return verdict(SourceScopeRole.NEAR_SCOPE, **common)

    role = (
        SourceScopeRole.SUPPORTING_BENCHMARK
        if requested_role == SourceScopeRole.SUPPORTING_BENCHMARK
        else SourceScopeRole.PRIMARY_IN_SCOPE
    )
    if role != requested_role:
        reasons.append(f"role_promoted_from:{requested_role.value}")
    return verdict(role, **common)
