"""Display titles kept separate from research questions and filename handles."""

from typing import Any

from .language_guard import language_matches

TITLE_PROMPT = (
    " Also return report_titles: an object with tr and en strings. These are matching "
    "Turkish and English reader-facing titles summarizing only the research topic. "
    "Use natural language with spaces, never snake_case, identifiers, Markdown, or a "
    "question. Aim for 5-12 words, at most 120 characters each. Preserve technical "
    "acronyms and named entities. Do not answer the question or invent findings. "
    "The tr title must be Turkish and the en title English regardless of input language."
)


def clean_report_titles(value: Any) -> dict[str, str]:
    """Reject malformed/foreign titles without making a cosmetic failure fatal."""
    if not isinstance(value, dict):
        return {}
    titles = {}
    for language in ("tr", "en"):
        title = value.get(language)
        if not isinstance(title, str):
            continue
        title = " ".join(title.replace("_", " ").replace("\x00", "").split())
        title = title.strip(' #*`"“”')
        if (
            3 <= len(title) <= 120
            and len(title.split()) <= 16
            and "?" not in title
            and language_matches(title, language)
        ):
            titles[language] = title
    return titles
