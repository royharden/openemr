"""Embedder wrapper — Voyage voyage-4-large primary, OpenAI text-embedding-3-small fallback.

Decision #7 (AgDR-0033): Voyage voyage-4-large is the canonical embedder.
Fallback to OpenAI text-embedding-3-small is triggered by:
  - ``EMBEDDER_PROVIDER=openai`` in the environment, OR
  - ``voyageai`` not installed / VoyageAI key absent.

In ``COPILOT_EVAL_MODE=1`` the embedder is replaced by ``EvalEmbedder`` from
``_eval_mocks.py`` (decision #19, AgDR-0042) so CI never hits the vendor.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

VOYAGE_DIM = 1024
OPENAI_DIM = 1536


class EmbedderProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


class VoyageEmbedder:
    """Voyage voyage-4-large embedder (200 M free tokens)."""

    MODEL = "voyage-4-large"

    def __init__(self, api_key: str | None = None) -> None:
        import voyageai  # type: ignore[import]
        self._client = voyageai.Client(api_key=api_key or os.environ["VOYAGE_API_KEY"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._client.embed(texts, model=self.MODEL, input_type="document")
        return result.embeddings

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small fallback."""

    MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str | None = None) -> None:
        from openai import OpenAI  # type: ignore[import]
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.MODEL, input=texts)
        return [item.embedding for item in response.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def get_embedder() -> EmbedderProtocol:
    """Factory — returns the right embedder for the current environment."""
    if os.environ.get("COPILOT_EVAL_MODE") == "1":
        from ._eval_mocks import EvalEmbedder
        return EvalEmbedder()

    provider = os.environ.get("EMBEDDER_PROVIDER", "voyage").lower()
    if provider == "openai":
        logger.info("Using OpenAI embedder (EMBEDDER_PROVIDER=openai)")
        return OpenAIEmbedder()

    try:
        return VoyageEmbedder()
    except Exception as exc:
        logger.warning("VoyageEmbedder init failed (%s) — falling back to OpenAI", exc)
        return OpenAIEmbedder()
