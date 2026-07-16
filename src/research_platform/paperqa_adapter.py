from __future__ import annotations

import importlib.util
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .config import Settings


class AcademicEvidenceEngine(ABC):
    @abstractmethod
    async def retrieve_evidence(
        self, question: str, documents: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class NativeAcademicEvidenceEngine(AcademicEvidenceEngine):
    async def retrieve_evidence(
        self, question: str, documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "engine": "native",
            "available": True,
            "question": question,
            "document_count": len(documents),
            "contexts": [],
        }


class PaperQA2EvidenceEngine(AcademicEvidenceEngine):
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("paperqa") is not None

    async def retrieve_evidence(
        self, question: str, documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.installed():
            return {
                "engine": "paperqa2",
                "available": False,
                "reason": "optional paper-qa package is not installed",
                "contexts": [],
            }
        from paperqa import Docs, Settings as PaperQASettings

        selected = documents[: self.settings.paperqa2_max_documents]
        with tempfile.TemporaryDirectory(prefix="research-platform-paperqa2-") as directory:
            docs = Docs()
            for index, document in enumerate(selected):
                path = Path(directory) / f"document-{index:03d}.txt"
                path.write_text(str(document.get("content", "")), encoding="utf-8")
                await docs.aadd(path)
            paperqa_settings = PaperQASettings()
            session = await docs.aget_evidence(question, settings=paperqa_settings)
            contexts = []
            for context in getattr(session, "contexts", []) or getattr(session, "context", []):
                contexts.append({
                    "text": str(getattr(context, "context", context)),
                    "score": getattr(context, "score", None),
                    "citation": str(getattr(context, "citation", "")),
                })
            return {
                "engine": "paperqa2",
                "available": True,
                "document_count": len(selected),
                "contexts": contexts,
            }


def paperqa2_health(settings: Settings) -> dict[str, Any]:
    installed = PaperQA2EvidenceEngine.installed()
    return {
        "id": "paperqa2_evidence",
        "family": "academic",
        "enabled": settings.paperqa2_enabled,
        "healthy": installed if settings.paperqa2_enabled else True,
        "requires_credentials": False,
        "missing_credentials": [],
        "capabilities": ["local_index", "evidence_retrieval", "contradiction_candidates"],
        "detail": (
            "installed; shadow mode enabled"
            if installed and settings.paperqa2_shadow_mode
            else "installed"
            if installed
            else "optional paper-qa package is not installed"
        ),
    }
