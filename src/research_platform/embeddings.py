from __future__ import annotations

import time
from typing import Any

import httpx

from .capacity import model_lease
from .config import Settings


class EmbeddingClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.metrics: list[dict[str, Any]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or self.settings.testing:
            return [[] for _ in texts]
        output: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            started = time.perf_counter()
            # The same single file the LLM calls queue in: embedding and completion share
            # one GPU, so they have to share one lease or parallel runs would put both on
            # the card at once.
            async with model_lease():
                response = await self.client.post(
                    f"{self.settings.ollama_url}/api/embed",
                    json={"model": self.settings.embedding_model, "input": batch, "truncate": True},
                    timeout=180,
                )
            response.raise_for_status()
            payload = response.json()
            vectors = payload.get("embeddings", [])
            if len(vectors) != len(batch):
                raise ValueError("Embedding response count does not match input count")
            output.extend(vectors)
            self.metrics.append({
                "model": self.settings.embedding_model,
                "batch_size": len(batch),
                "wall_seconds": round(time.perf_counter() - started, 4),
                "prompt_tokens": payload.get("prompt_eval_count", 0),
                "total_seconds": round(payload.get("total_duration", 0) / 1e9, 4),
            })
        return output

    def drain_metrics(self) -> list[dict[str, Any]]:
        metrics, self.metrics = self.metrics, []
        return metrics
