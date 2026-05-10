"""RAG package — hybrid retrieval over the bundled guideline corpus.

Workstream B (wk2-team-b-rag) implements:
  - corpus.py       — SQLite + sqlite-vec chunk store
  - chunker.py      — section-boundary chunker
  - embedder.py     — Voyage voyage-4-large (OpenAI fallback)
  - retriever.py    — HybridRetriever (BM25 + vector union, k=20)
  - reranker.py     — CohereReranker (local cross-encoder fallback)
  - ingestion/      — CDC ACIP, openFDA, HMS-LOE ingestors
  - _eval_mocks.py  — EvalEmbedder, EvalReranker for COPILOT_EVAL_MODE=1
  - phi_filter.py   — strip_phi() helper for query sanitisation
"""

from .contracts import GuidelineChunk, RecommendationGrade, SourceOrganization
from .phi_filter import strip_phi

__all__ = [
    "GuidelineChunk",
    "RecommendationGrade",
    "SourceOrganization",
    "strip_phi",
]
