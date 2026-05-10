"""Deterministic mock boundaries for COPILOT_EVAL_MODE=1.

Integrates Team A's vision extractor mock and provides Team B stubs until
their PR lands. All mocks are deterministic: same input => same output.

Cache key invariant (Plan §15.5.9, AgDR-0042):
  key = sha256(text + "|" + model_id + "|" + MOCK_VERSION)
This ensures a fixture content change or model upgrade busts the cache.

MOCK_VERSION — bump when fixture data changes to bust stale cache.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

MOCK_VERSION = "wk2-c-v1"

_EVAL_MODE = os.environ.get("COPILOT_EVAL_MODE", "0") == "1"


# ---------------------------------------------------------------------------
# Vision extractor mock — integrate Team A's _eval_mocks_a.py
# ---------------------------------------------------------------------------

try:
    from app.extractors._eval_mocks_a import (  # type: ignore[import-not-found]
        get_intake_mock_fields,
        get_lab_mock_fields,
        is_eval_mode,
        resolve_intake_fixture_key,
        resolve_lab_fixture_key,
    )
    _TEAM_A_MOCKS_AVAILABLE = True
except ImportError:
    _TEAM_A_MOCKS_AVAILABLE = False

    def is_eval_mode() -> bool:
        return _EVAL_MODE

    def get_lab_mock_fields(fixture_key: str) -> list[Any]:
        return []

    def get_intake_mock_fields(fixture_key: str) -> list[Any]:
        return []

    def resolve_lab_fixture_key(document_sha256: str, filename: str = "") -> str:
        return document_sha256[:8]

    def resolve_intake_fixture_key(document_sha256: str, filename: str = "") -> str:
        return document_sha256[:8]


class EvalVisionExtractor:
    """Deterministic vision extractor for eval mode."""

    def extract_lab(self, document_sha256: str, filename: str = "") -> list[Any]:
        key = resolve_lab_fixture_key(document_sha256, filename)
        return get_lab_mock_fields(key)

    def extract_intake(self, document_sha256: str, filename: str = "") -> list[Any]:
        key = resolve_intake_fixture_key(document_sha256, filename)
        return get_intake_mock_fields(key)


# ---------------------------------------------------------------------------
# Embedder mock
# ---------------------------------------------------------------------------

_EMBED_DIM = 1024


def _embed_cache_key(text: str, model_id: str = "voyage-4-large") -> str:
    raw = f"{text}|{model_id}|{MOCK_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _text_to_vector(text: str) -> list[float]:
    """Deterministic pseudo-embedding: hash text into a fixed-dim float vector."""
    digest = hashlib.sha256(text.encode()).digest()
    repeated = (digest * ((_EMBED_DIM // 32) + 1))[:_EMBED_DIM]
    return [(b - 127.5) / 127.5 for b in repeated]


class EvalEmbedder:
    """Deterministic embedder for eval mode.

    Cache key includes text + model_id + MOCK_VERSION (Plan §15.5.9).
    """

    def __init__(self, model_id: str = "voyage-4-large") -> None:
        self.model_id = model_id
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            key = _embed_cache_key(text, self.model_id)
            if key not in self._cache:
                self._cache[key] = _text_to_vector(text)
            results.append(self._cache[key])
        return results

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ---------------------------------------------------------------------------
# Reranker mock
# ---------------------------------------------------------------------------

def _rerank_cache_key(query: str, doc: str) -> str:
    raw = f"{query}|{doc}|{MOCK_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


class EvalReranker:
    """Deterministic reranker for eval mode.

    Ranks candidates by descending BM25-like term overlap with the query.
    Cache key includes query + doc text + MOCK_VERSION.
    """

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        query_terms = set(query.lower().split())
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for i, cand in enumerate(candidates):
            text = str(cand.get("text", ""))
            overlap = len(query_terms & set(text.lower().split()))
            score = overlap + (1.0 / (i + 1)) * 0.001
            scored.append((score, i, cand))
        scored.sort(key=lambda t: (-t[0], t[1]))
        result = []
        for rank, (score, _i, cand) in enumerate(scored[:top_n]):
            item = dict(cand)
            item["rerank_score"] = round(score, 6)
            item["rerank_position"] = rank
            item["reranker"] = "fallback"
            result.append(item)
        return result


# ---------------------------------------------------------------------------
# Synthesizer mock
# ---------------------------------------------------------------------------

_SYNTH_REGISTRY: dict[str, dict[str, Any]] = {
    "__default__": {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "Patient has documented lab results on file.",
                "claim_type": "fact",
                "source_ids": [],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    },
    "__injection__": {
        "answer_type": "pre_room_brief",
        "claims": [],
        "missing_data": [],
        "refusals": ["This request contains instructions that cannot be followed."],
        "suggested_followups": [],
    },
}

_INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard your instructions",
    "system prompt",
    "jailbreak",
    "ignore your",
    "forget your instructions",
)


def get_eval_synthesis_response(
    question: str,
    case_id: str = "",
) -> dict[str, Any]:
    """Return a deterministic synthesis response for eval mode."""
    question_lower = question.lower()
    for phrase in _INJECTION_PHRASES:
        if phrase in question_lower:
            return dict(_SYNTH_REGISTRY["__injection__"])
    key = hashlib.sha256(question.encode()).hexdigest()[:16]
    return dict(_SYNTH_REGISTRY.get(key, _SYNTH_REGISTRY["__default__"]))
