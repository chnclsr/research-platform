"""Scoping answers that bind to the protocol instead of only nudging a prompt.

The questions asked before a run starts used to reach the pipeline as prompt guidance and
nothing else: picking "official sources" left `connectors.included_families` untouched, so
the answer looked like a setting while behaving like a suggestion a 4B model was free to
ignore. Two of the questions are fixed here, their options carry real enum values, and
:func:`apply_planning_answers` writes them into the protocol. The rest stay free-form
steering -- a model-invented option has nothing to bind to.

Pure module: no network, no database, no LLM. Everything here is a function of its
arguments, which is what makes the binding testable.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from .schemas import CORE_FAMILIES, ResearchProtocol, SourceFamily, utcnow

# Turkish dotless i survives NFKD intact and would simply be dropped by an ASCII filter,
# which turns "ısı" into "s". The other Turkish letters decompose correctly on their own.
_TRANSLITERATE = str.maketrans({"ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s"})

# Words that name no topic. The second group is there because the label now has to be
# typed into commands: a live run came back as "Research_artificial_intelligence_studies_
# that_last_3m", where only two words said anything and the rest was 25 characters of
# filler in front of the part a person has to retype.
_SLUG_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is",
    "of", "on", "or", "the", "to", "what", "which", "with",
    "about", "based", "into", "review", "research", "studies", "study", "that", "these",
    "this", "using",
    "ve", "ile", "icin", "gibi", "olan", "olarak", "nasil", "nedir", "mi", "mu", "de",
    "da", "bir", "bu", "su", "en", "her",
}

# How long a run label may get before the date suffix. Short enough to retype from a chat
# window, which is the whole reason the label exists.
LABEL_MAX_LENGTH = 32

# Windows a fixed answer can select, in days. Calendar-exact years are not worth a
# dependency here: the value ends up as a search filter, not as an accounting boundary.
_DATE_WINDOWS = {"last_1y": 365, "last_3y": 3 * 365, "last_5y": 5 * 365}

_FAMILY_PRESETS: dict[str, list[SourceFamily]] = {
    "academic": [SourceFamily.ACADEMIC, SourceFamily.WEB],
    "official": [SourceFamily.OFFICIAL_LEGAL, SourceFamily.WEB, SourceFamily.ACADEMIC],
    "code_data": [SourceFamily.CODE_DATA, SourceFamily.WEB],
    "core": list(CORE_FAMILIES),
}

SCOPING_TEXT = {
    "tr": {
        "date_scope": "Hangi tarih aralığına bakalım?",
        "date_keep": "Sorudaki aralık ({window})",
        "date_last_1y": "Son 1 yıl",
        "date_last_3y": "Son 3 yıl",
        "date_last_5y": "Son 5 yıl",
        "date_any": "Tarih sınırı olmasın",
        "source_families": "Hangi kaynaklara ağırlık verelim?",
        "source_academic": "Akademik yayınlar",
        "source_official": "Resmî belgeler ve mevzuat",
        "source_code_data": "Kod ve veri kümeleri",
        "source_core": "Geniş tarama (hepsi)",
        "applied_dates": "Tarih",
        "applied_families": "Kaynak",
        "dates_any": "sınır yok",
    },
    "en": {
        "date_scope": "Which date range should we look at?",
        "date_keep": "The range in your question ({window})",
        "date_last_1y": "Last 1 year",
        "date_last_3y": "Last 3 years",
        "date_last_5y": "Last 5 years",
        "date_any": "No date limit",
        "source_families": "Which sources should we weight?",
        "source_academic": "Academic publications",
        "source_official": "Official documents and regulation",
        "source_code_data": "Code and datasets",
        "source_core": "Broad sweep (all of them)",
        "applied_dates": "Dates",
        "applied_families": "Sources",
        "dates_any": "no limit",
    },
}


def scoping_text(language: str) -> dict[str, str]:
    return SCOPING_TEXT["en" if language == "en" else "tr"]


def slugify(text: str, *, max_length: int = 48) -> str:
    """A short `snake_case` handle for a research topic.

    Display only. Two runs on the same topic produce the same slug, so this never stands
    in for the run id -- it stands next to it.
    """
    folded = unicodedata.normalize("NFKD", str(text).translate(_TRANSLITERATE))
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    words = [word for word in re.findall(r"[A-Za-z0-9]+", folded) if word]
    kept = [word for word in words if word.lower() not in _SLUG_STOPWORDS] or words
    slug = ""
    for word in kept:
        candidate = f"{slug}_{word}" if slug else word
        if len(candidate) > max_length:
            break
        slug = candidate
    return slug or ""


def date_suffix(protocol: ResearchProtocol) -> str:
    """`_last_3m` style tail for a label, when the run has a bounded window."""
    start, end = protocol.scope.start_date, protocol.scope.end_date
    if start is None or end is None:
        return ""
    days = max(1, (end - start).days)
    if days <= 45:
        return "_last_1m"
    if days < 330:
        return f"_last_{max(1, round(days / 30))}m"
    return f"_last_{max(1, round(days / 365))}y"


def fixed_questions(protocol: ResearchProtocol, language: str) -> list[dict]:
    """The two questions whose answers become protocol fields.

    Asked ahead of the model's questions so the binding ones are answered first, and worded
    from a table rather than generated: an option can only bind if its value is one this
    module knows how to apply.
    """
    text = scoping_text(language)
    dates: dict = {
        "id": "date_scope",
        "question": text["date_scope"],
        "options": [],
        "values": [],
    }
    # The window a phrase like "last 3 months" produced is applied silently today. Offering
    # it as the first option turns that inference into a decision the user actually made.
    if protocol.scope.dates_inferred and protocol.scope.start_date and protocol.scope.end_date:
        window = (
            f"{protocol.scope.start_date.date().isoformat()} → "
            f"{protocol.scope.end_date.date().isoformat()}"
        )
        dates["options"].append(text["date_keep"].format(window=window))
        dates["values"].append("keep")
    for value in ("last_1y", "last_3y", "last_5y", "any"):
        dates["options"].append(text[f"date_{value}"])
        dates["values"].append(value)

    families = {
        "id": "source_families",
        "question": text["source_families"],
        "options": [text[f"source_{value}"] for value in _FAMILY_PRESETS],
        "values": list(_FAMILY_PRESETS),
    }
    return [dates, families]


def _window_days(value: str) -> int | None:
    """Days behind `value`, for the three offered windows and any `last_<n>y` besides.

    The buttons offer three; typed feedback says "son 2 yil" as readily as "son 1 yil" and
    there is no reason the same sentence should bind only when it names a preset.
    """
    if value in _DATE_WINDOWS:
        return _DATE_WINDOWS[value]
    match = re.fullmatch(r"last_(\d{1,2})y", value)
    if match and 1 <= int(match.group(1)) <= 50:
        return int(match.group(1)) * 365
    return None


def _apply_date_scope(payload: dict, value: str, text: dict[str, str]) -> str | None:
    scope = payload.setdefault("scope", {})
    if value == "keep":
        return None
    days = _window_days(value)
    if days is None and value != "any":
        return None
    # No longer inferred from wording: the user was shown the alternatives and picked one.
    # `dates_chosen` is what stops the validator inferring the window straight back after
    # "no limit" clears it.
    scope["dates_inferred"] = False
    scope["dates_chosen"] = True
    if value == "any":
        scope["start_date"] = None
        scope["end_date"] = None
        return text["dates_any"]
    end = utcnow()
    start = end - timedelta(days=days or 0)
    scope["start_date"] = start.isoformat()
    scope["end_date"] = end.isoformat()
    return f"{start.date().isoformat()} → {end.date().isoformat()}"


def _apply_families(payload: dict, value: str, text: dict[str, str]) -> str | None:
    preset = _FAMILY_PRESETS.get(value)
    if preset is None:
        return None
    connectors = payload.setdefault("connectors", {})
    connectors["included_families"] = [family.value for family in preset]
    # "core" is the profile's own default, so leaving the profile alone there keeps the
    # protocol describing itself honestly; anything else is a deliberate custom selection.
    connectors["profile"] = "core" if value == "core" else "custom"
    # Cleared rather than filtered: the validator only ever narrows an existing map, so a
    # widened family list would otherwise keep targets for families that are gone and none
    # for the ones just added.
    payload["family_targets"] = {}
    return ", ".join(family.value for family in preset)


_APPLIERS = {"date_scope": _apply_date_scope, "source_families": _apply_families}

# Typed plan feedback, matched against the same closed vocabulary the buttons write. Kept
# deterministic on purpose: the gate already waits on a person, and a model asked to read
# an intent out of one sentence would make the protocol depend on a guess nobody sees.
# Anything these do not match stays exactly what it was before -- guidance for the prompts.
_FEEDBACK_YEARS = re.compile(
    r"(?:son|last|past)\s*(\d{1,2})\s*(?:y[ıi]l|sene|year)", re.IGNORECASE
)
_FEEDBACK_ANY_DATE = re.compile(
    r"(?:t[üu]m\s+zamanlar|tarih\s+(?:s[ıi]n[ıi]r[ıi]|k[ıi]s[ıi]t[ıi])\s*(?:olmas[ıi]n|kalks[ıi]n|yok)"
    r"|no\s+date\s+(?:limit|filter)|any\s+time|all\s+time)",
    re.IGNORECASE,
)
# Families bind only behind an explicit "only", because feedback that merely mentions a
# family ("akademik kaynaklarin maliyeti") is describing the topic, not narrowing the run.
_FEEDBACK_FAMILIES = (
    (re.compile(r"(?:sadece|yaln[ıi]zca?|only)\b[^.\n]{0,40}akademik|academic[^.\n]{0,20}only",
                re.IGNORECASE), "academic"),
    (re.compile(r"(?:sadece|yaln[ıi]zca?|only)\b[^.\n]{0,40}(?:resm[ıi]|mevzuat)"
                r"|official[^.\n]{0,20}only", re.IGNORECASE), "official"),
    (re.compile(r"(?:sadece|yaln[ıi]zca?|only)\b[^.\n]{0,40}(?:kod|veri)"
                r"|(?:code|data)[^.\n]{0,20}only", re.IGNORECASE), "code_data"),
)


def feedback_answers(feedback: list[str]) -> list[dict]:
    """Read plan feedback as scoping answers, so a rejection can move the protocol.

    Rejection notes used to reach the prompts and nothing else, which meant "make it the
    last year" left the dates exactly where they were and the rebuilt plan showed the
    window the user had just asked to change. The later note wins: a person revising twice
    means the second one.
    """
    answers: dict[str, dict] = {}
    for note in feedback:
        text = str(note)
        years = _FEEDBACK_YEARS.search(text)
        if years and 1 <= int(years.group(1)) <= 50:
            answers["date_scope"] = {"id": "date_scope", "value": f"last_{int(years.group(1))}y"}
        elif _FEEDBACK_ANY_DATE.search(text):
            answers["date_scope"] = {"id": "date_scope", "value": "any"}
        for pattern, value in _FEEDBACK_FAMILIES:
            if pattern.search(text):
                answers["source_families"] = {"id": "source_families", "value": value}
                break
    return list(answers.values())

_APPLIED_LABEL = {"date_scope": "applied_dates", "source_families": "applied_families"}


def apply_planning_answers(
    protocol: ResearchProtocol,
    answers: list[dict],
) -> tuple[ResearchProtocol, list[dict]]:
    """Write the bound answers into the protocol; report what changed.

    An answer only binds when it carries a `value` the table above recognises -- a typed
    reply, or an option the model invented, carries none and stays what it always was:
    guidance for the prompts. Returns the protocol unchanged (and an empty report) when
    nothing bound, or when the result would not validate.
    """
    text = scoping_text(protocol.display_language())
    payload = protocol.model_dump(mode="json")
    applied: list[dict] = []
    for item in answers:
        if not isinstance(item, dict):
            continue
        applier = _APPLIERS.get(str(item.get("id") or ""))
        value = str(item.get("value") or "")
        if applier is None or not value:
            continue
        detail = applier(payload, value, text)
        if detail is None:
            continue
        applied.append(
            {
                "id": item["id"],
                "label": text[_APPLIED_LABEL[item["id"]]],
                "value": value,
                "detail": detail,
            }
        )
    if not applied:
        return protocol, []
    try:
        return ResearchProtocol.model_validate(payload), applied
    except ValueError:
        # A family minimum can exceed max_sources. A scoping answer is worth less than the
        # run: keep the protocol that was already valid and let the answers steer instead.
        return protocol, []
