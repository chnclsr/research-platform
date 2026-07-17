from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Any


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "bir": 1,
    "iki": 2,
    "üç": 3,
    "uc": 3,
    "dört": 4,
    "dort": 4,
    "beş": 5,
    "bes": 5,
    "altı": 6,
    "alti": 6,
}

RELATIVE_RANGE_PATTERNS = (
    re.compile(
        r"\b(?:last|past|previous)\s+"
        r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+"
        r"(?P<unit>days?|weeks?|months?|years?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:son|geçen|gecen)\s+"
        r"(?P<count>\d+|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti)\s+"
        r"(?P<unit>gün|gun|hafta|ay|yıl|yil)\b",
        re.IGNORECASE,
    ),
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def infer_relative_date_range(
    question: str,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """Turn explicit relative windows such as 'last 3 months' into UTC bounds."""
    current = _utc(now or datetime.now(timezone.utc))
    for pattern in RELATIVE_RANGE_PATTERNS:
        match = pattern.search(question)
        if not match:
            continue
        raw_count = match.group("count").lower()
        count = int(raw_count) if raw_count.isdigit() else NUMBER_WORDS[raw_count]
        unit = match.group("unit").lower()
        if unit.startswith(("day", "gün", "gun")):
            start = current - timedelta(days=count)
        elif unit.startswith(("week", "hafta")):
            start = current - timedelta(weeks=count)
        elif unit.startswith(("year", "yıl", "yil")):
            start = subtract_months(current, count * 12)
        else:
            start = subtract_months(current, count)
        return start, current
    return None


def _from_date_parts(value: Any) -> datetime | None:
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            values = parts[0]
            if values and values[0]:
                year = int(values[0])
                month = int(values[1]) if len(values) > 1 and values[1] else 1
                day = int(values[2]) if len(values) > 2 and values[2] else 1
                return datetime(year, month, day, tzinfo=timezone.utc)
        for key in ("date-time", "date", "value"):
            parsed = parse_datetime(value.get(key))
            if parsed:
                return parsed
    return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _utc(value)
    nested = _from_date_parts(value)
    if nested:
        return nested
    if isinstance(value, int) and 1000 <= value <= 9999:
        return datetime(value, 1, 1, tzinfo=timezone.utc)
    text = str(value).strip()
    if re.fullmatch(r"\d{4}", text):
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    try:
        return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


PUBLICATION_DATE_KEYS = (
    "publication_date",
    "publicationDate",
    "firstPublicationDate",
    "first_publication_date",
    "published-online",
    "published",
    "issued",
    "publication_year",
    "pubYear",
    "year",
)


def publication_datetime(metadata: dict[str, Any] | None) -> tuple[datetime | None, str | None]:
    values = metadata or {}
    for key in PUBLICATION_DATE_KEYS:
        parsed = parse_datetime(values.get(key))
        if parsed:
            return parsed, key
    attributes = values.get("attributes")
    if isinstance(attributes, dict):
        for key in PUBLICATION_DATE_KEYS:
            parsed = parse_datetime(attributes.get(key))
            if parsed:
                return parsed, f"attributes.{key}"
    return None, None


def enrich_publication_date(candidate: Any, content: str = "") -> tuple[datetime | None, str | None]:
    """Enrich missing academic dates from stable identifiers or explicit page metadata."""
    if getattr(candidate, "published_at", None) is not None:
        return candidate.published_at, "candidate.published_at"
    identity = " ".join([
        str(getattr(candidate, "persistent_id", "") or ""),
        str(getattr(candidate, "url", "") or ""),
    ])
    arxiv = re.search(r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)(\d{2})(\d{2})\.\d{4,5}", identity, re.I)
    if arxiv:
        year = 2000 + int(arxiv.group(1))
        month = int(arxiv.group(2))
        if 1 <= month <= 12:
            value = datetime(year, month, 1, tzinfo=timezone.utc)
            candidate.published_at = value
            candidate.metadata["published_at"] = value.isoformat()
            candidate.metadata["publication_date_basis"] = "arxiv_identifier"
            return value, "arxiv_identifier"
    excerpt = content[:100_000]
    patterns = (
        r'<meta[^>]+(?:name|property)=["\'](?:citation_(?:publication_)?date|article:published_time)["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:citation_(?:publication_)?date|article:published_time)["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, excerpt, re.I)
        parsed = parse_datetime(match.group(1)) if match else None
        if parsed:
            candidate.published_at = parsed
            candidate.metadata["published_at"] = parsed.isoformat()
            candidate.metadata["publication_date_basis"] = "document_metadata"
            return parsed, "document_metadata"
    return None, None


def date_scope_decision(
    published_at: datetime | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[bool, str]:
    if start_date is None and end_date is None:
        return True, "unbounded"
    if published_at is None:
        return False, "publication_date_unknown"
    value = _utc(published_at)
    if start_date is not None and value < _utc(start_date):
        return False, "before_start_date"
    if end_date is not None and value > _utc(end_date):
        return False, "after_end_date"
    return True, "within_date_scope"


def constrain_text_to_scope(
    value: str,
    start_date: datetime | None,
    end_date: datetime | None,
) -> str:
    """Remove LLM-invented years that contradict an explicit protocol scope."""
    if start_date is None and end_date is None:
        return value
    minimum_year = _utc(start_date).year if start_date else 0
    maximum_year = _utc(end_date).year if end_date else 9999

    def replace(match: re.Match[str]) -> str:
        year = int(match.group(0))
        return match.group(0) if minimum_year <= year <= maximum_year else ""

    cleaned = re.sub(r"\b(?:19|20)\d{2}\b", replace, value)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    return " ".join(cleaned.split())
