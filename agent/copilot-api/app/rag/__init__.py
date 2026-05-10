"""RAG package — hybrid retrieval over the bundled guideline corpus.

Wk2 Workstream 0.5 lands the package skeleton + ``contracts.py`` so Team B
can branch from a known-good shared shape. Implementation modules
(``corpus.py``, ``ingestion/*.py``, ``chunker.py``, ``embedder.py``,
``retriever.py``, ``reranker.py``) are added by Workstream B.
"""

from .contracts import GuidelineChunk, RecommendationGrade, SourceOrganization

__all__ = ["GuidelineChunk", "RecommendationGrade", "SourceOrganization"]
