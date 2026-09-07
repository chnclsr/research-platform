from __future__ import annotations

import re
from difflib import SequenceMatcher

_NON_EVIDENCE_SECTION = re.compile(
    r"(?:^|\s[>:/|]\s|\b)(?:references?|bibliograph(?:y|ies)|works cited|"
    r"how to cite|citation|cite this|kaynak(?:ça|ca)|atıf|atif|"
    r"acknowledg(?:e)?ments?|author information|about the authors?|"
    r"access paper|view pdf|download(?: paper| pdf)?|"
    r"navigation|footer|related articles?)(?:$|\b)",
    re.IGNORECASE,
)
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_YEAR = re.compile(r"\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b")
_CITATION_LEAD = re.compile(
    r"^(?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü'’-]+,?\s+(?:[A-Z]\.?\s*){1,3}|"
    r"(?:et\s+al\.|doi:|https?://doi\.org/))",
    re.IGNORECASE,
)
_KEYWORD_LEAD = re.compile(
    r"^(?:keywords?|key\s*words?|index terms?|mesh terms?|"
    r"anahtar\s+kelimeler?|indeks\s+terimleri?)\s*[:—-]",
    re.IGNORECASE,
)
_PREDICATE_SIGNAL = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|does|do|did|"
    r"can|could|may|might|must|shall|should|will|would|"
    r"show(?:s|ed)?|reports|reported|finds|found|demonstrat(?:e|es|ed)|"
    r"improv(?:e|es|ed)|reduc(?:e|es|ed)|increas(?:e|es|ed)|use(?:s|d)?|"
    r"achiev(?:e|es|ed)|outperform(?:s|ed)?|predict(?:s|ed)?|generat(?:e|es|ed)|"
    r"produc(?:e|es|ed)|includ(?:e|es|ed)|contain(?:s|ed)?|enabl(?:e|es|ed)|"
    r"requir(?:e|es|ed)|provid(?:e|es|ed)|perform(?:s|ed)?|yield(?:s|ed)?|"
    r"associat(?:e|es|ed)|correlat(?:e|es|ed)|support(?:s|ed)?|"
    r"indicat(?:e|es|ed)|suggest(?:s|ed)?|remain(?:s|ed)?|lead(?:s|ing)?|"
    r"result(?:s|ed)?|compar(?:e|es|ed)|measur(?:e|es|ed)|train(?:s|ed)?|"
    r"validat(?:e|es|ed)|detect(?:s|ed)?|classif(?:y|ies|ied)|segment(?:s|ed)?|"
    r"present(?:s|ed)?|observ(?:e|es|ed)|identif(?:y|ies|ied)|"
    r"propos(?:e|es|ed)|develop(?:s|ed)?|attain(?:s|ed)?|"
    r"oldu|olduğu|olan|vardır|göster(?:ir|di|miştir)|bul(?:du|muştur)|"
    r"art(?:ar|tı|mıştır)|azal(?:ır|dı|mıştır)|kullan(?:ır|dı|ılmıştır)|"
    r"üret(?:ir|ti|miştir)|içer(?:ir|di|miştir)|sağla(?:r|dı|mıştır)|"
    r"gerektir(?:ir|di|miştir)|doğrula(?:r|dı|mıştır)|öner(?:ir|di|miştir))\b",
    re.IGNORECASE,
)


def is_non_evidence_section(section_path: str | None) -> bool:
    """Return True for document regions that describe citations, not findings."""
    return bool(_NON_EVIDENCE_SECTION.search(section_path or ""))


def looks_like_bibliographic_text(text: str) -> bool:
    value = " ".join((text or "").split())
    if not value:
        return True
    if _DOI.search(value) and (_YEAR.search(value) or _CITATION_LEAD.search(value)):
        return True
    if _CITATION_LEAD.search(value) and _YEAR.search(value) and len(value) < 500:
        return True
    return False


def evidence_quality_gate(
    claim: str,
    quote: str,
    *,
    section_path: str | None = None,
    source_title: str = "",
    entailment_score: float | None = None,
) -> tuple[bool, str]:
    """Conservative deterministic gate before evidence can affect a report.

    It intentionally rejects citation-shell text and title-shaped pseudo claims. A
    false negative here leaves a claim unresolved; a false positive could publish a
    misleading conclusion, so the gate is fail-closed.
    """
    claim_value = " ".join((claim or "").split())
    quote_value = " ".join((quote or "").split())
    if is_non_evidence_section(section_path):
        return False, "non_evidence_section"
    if len(claim_value.split()) < 5 or len(quote_value.split()) < 5:
        return False, "insufficient_proposition"
    if _KEYWORD_LEAD.search(claim_value) or _KEYWORD_LEAD.search(quote_value):
        return False, "keyword_list"
    if looks_like_bibliographic_text(claim_value) or looks_like_bibliographic_text(quote_value):
        return False, "bibliographic_text"
    if re.search(
        r"\b(?:view|download|access)\s+(?:a\s+)?(?:pdf|paper)|"
        r"\bpaper\s+titled\b|\bby\s+[^,]{2,80}\s+and\s+\d+\s+other\s+authors?\b",
        quote_value,
        re.IGNORECASE,
    ):
        return False, "access_shell_text"
    if re.search(
        r"\b(?:please\s+)?cite\s+(?:this|the)\s+(?:preprint|paper)|"
        r"\bcite\s+(?:this|the)\s+(?:preprint|paper)\s+only\s+for\b|"
        r"\bgrant applications?\s+and\s+cv(?:s)?\b|"
        r"\bcurrent preprint settings\b",
        f"{claim_value} {quote_value}",
        re.IGNORECASE,
    ):
        return False, "citation_shell_text"
    if re.search(
        r"\bskip to (?:main )?content\b|\bskip navigation\b|"
        r"\b(?:arxiv|site) is now an independent nonprofit\b|"
        r"\b(?:sign in|log in|create account|open navigation menu)\b",
        f"{claim_value} {quote_value}",
        re.IGNORECASE,
    ):
        return False, "navigation_shell_text"
    if source_title:
        similarity = SequenceMatcher(None, claim_value.casefold(), source_title.casefold()).ratio()
        if similarity >= 0.90:
            return False, "source_title_as_claim"
    # A reportable claim is a proposition, not a title or topic label. Restricting this
    # check to delimiter-heavy lists let ordinary noun-phrase headings through unchanged.
    if not _PREDICATE_SIGNAL.search(claim_value):
        return False, "missing_predicate"
    if quote_value.endswith("?") and not claim_value.endswith("?"):
        return False, "question_does_not_entail_assertion"
    if entailment_score is not None and entailment_score < 0.50:
        return False, "low_entailment"
    return True, "accepted"
