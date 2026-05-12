"""Anthropic Contextual Retrieval — chunk context summary generator.

AgDR-0079, Plan §7.2.b.

For each chunk, generate a ≤80-token LLM context summary that situates the
chunk inside its source document (section, topic, surrounding facts). The
summary is prepended to the chunk text before embedding + BM25 indexing,
giving the retriever extra surface to match against — Anthropic's published
technique (2024) demonstrates 35-49% retrieval accuracy gains over plain
chunks. The verbatim ``chunk.text`` is preserved for display so the user
always sees the original source content, not the LLM-generated blurb.

Activation is opt-in via ``COPILOT_CONTEXTUAL_RETRIEVAL=1`` so the existing
non-contextualized corpus.db (Phase 5.2 rebuild) stays valid until an
explicit rebuild. Re-runs of the same chunk hit the disk cache and pay $0
Anthropic.

Cache key: ``sha256(source_id|chunk_id|source_doc_hash|model)[:32]``. The
``source_doc_hash`` is a stable hash of the source document — if the source
document changes, the cache key changes too, and the LLM is re-called.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONTEXTUAL_MODEL_DEFAULT = "claude-haiku-4-5-20251001"

# Eval-mode placeholder context. Deterministic, byte-stable across runs so
# the corpus content_hash stays predictable in CI. The placeholder is
# intentionally short and information-bearing enough to test the prepend
# pipeline without taking on a fixture-corpus dependency.
_EVAL_PLACEHOLDER_PREFIX = "Context: "


def _is_eval_mode() -> bool:
    return os.getenv("COPILOT_EVAL_MODE") == "1"


def is_contextual_retrieval_enabled() -> bool:
    """Public predicate. Read at ingestion time, never cached at module scope
    so a test can flip the env var without reload."""

    return os.getenv("COPILOT_CONTEXTUAL_RETRIEVAL") == "1"


def _default_cache_dir() -> Path:
    """Disk cache root. ``$XDG_CACHE_HOME/copilot/contextual`` if set; else
    ``~/.copilot-cache/contextual``. Created on first write."""

    if os.getenv("COPILOT_CONTEXTUAL_CACHE_DIR"):
        return Path(os.environ["COPILOT_CONTEXTUAL_CACHE_DIR"])
    xdg = os.getenv("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "copilot" / "contextual"
    return Path.home() / ".copilot-cache" / "contextual"


def _source_doc_hash(source_doc_text: str) -> str:
    """Stable hash of the source document. SHA-256, first 16 hex chars.

    Per Plan §7.2.b cache-key spec; truncated to keep the cache filename
    short on Windows (260-char path limit on legacy filesystems).
    """

    return hashlib.sha256(source_doc_text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _cache_key(source_id: str, chunk_id: str, source_doc_text: str, model: str) -> str:
    raw = f"{source_id}|{chunk_id}|{_source_doc_hash(source_doc_text)}|{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _cache_get(cache_dir: Path, key: str) -> str | None:
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = payload.get("context_summary")
    return summary if isinstance(summary, str) and summary else None


def _cache_put(cache_dir: Path, key: str, summary: str, source_id: str, chunk_id: str, model: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "context_summary": summary,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "model": model,
        "created_at": int(time.time()),
    }
    try:
        _cache_path(cache_dir, key).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("contextualization: failed to write cache (%s)", exc)


def _eval_summary(chunk_text: str, source_info: dict[str, Any]) -> str:
    """Deterministic eval-mode placeholder. Includes the source organization
    + year + a content fingerprint so the prepend pipeline is exercised but
    no Anthropic call is made."""

    org = str(source_info.get("source_organization") or "guideline").strip() or "guideline"
    year = source_info.get("source_year")
    fingerprint = hashlib.sha256(chunk_text.encode("utf-8", errors="replace")).hexdigest()[:6]
    if year is None:
        return f"{_EVAL_PLACEHOLDER_PREFIX}{org} guideline (fingerprint={fingerprint})"
    return f"{_EVAL_PLACEHOLDER_PREFIX}{org} {year} guideline (fingerprint={fingerprint})"


def _call_anthropic(
    chunk_text: str,
    source_doc_text: str,
    source_info: dict[str, Any],
    model: str,
) -> str | None:
    """Plain-text Anthropic call. Returns ``None`` on any failure so the
    caller can fall back to the eval placeholder rather than blocking the
    ingestion."""

    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("contextualization: anthropic SDK unavailable")
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("contextualization: ANTHROPIC_API_KEY missing")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    # Anthropic Contextual Retrieval prompt template (Plan §7.2.b §1).
    # Document body truncated to 12_000 chars — empirically enough context
    # for an 80-token summary, and well under Haiku's 200k context window
    # while keeping per-call cost ~$0.0001.
    doc_excerpt = source_doc_text[:12_000]
    org = source_info.get("source_organization") or "the source document"
    year = source_info.get("source_year")
    year_str = f" ({year})" if year else ""

    user_msg = (
        f"<document>\n{doc_excerpt}\n</document>\n"
        f"<chunk>\n{chunk_text}\n</chunk>\n\n"
        f"In 80 words or fewer, situate this chunk inside the document "
        f"({org}{year_str}). State the section, topic, and 1–2 surrounding "
        f"facts. Output the context only — do not quote the chunk or repeat "
        f"its content."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=160,  # ~80 tokens × 2 to absorb tokenization variance.
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as exc:
        logger.warning("contextualization: Anthropic call failed (%s)", exc)
        return None

    parts: list[str] = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "")))
    summary = " ".join(parts).strip()
    if not summary:
        return None
    return summary


def generate_context_summary(
    chunk_text: str,
    source_doc_text: str,
    source_info: dict[str, Any],
    *,
    source_id: str,
    chunk_id: str,
    model: str | None = None,
    cache_dir: Path | None = None,
) -> str:
    """Return the context summary for one chunk.

    Behavior:
      * ``COPILOT_EVAL_MODE=1`` → return deterministic placeholder; never
        hit Anthropic; do not touch the disk cache.
      * Otherwise: check disk cache; on miss, call Anthropic; on success,
        write the cache. On any Anthropic failure, fall back to the
        deterministic placeholder so ingestion never blocks on the
        contextualization step (degraded but not broken).

    The cache key is ``sha256(source_id|chunk_id|source_doc_hash|model)`` —
    a source document edit invalidates every chunk's cache, which is the
    correct behavior (contextualization is document-conditional).
    """

    resolved_model = model or os.getenv("COPILOT_CONTEXTUAL_MODEL", CONTEXTUAL_MODEL_DEFAULT)

    if _is_eval_mode():
        return _eval_summary(chunk_text, source_info)

    cache_dir = cache_dir or _default_cache_dir()
    key = _cache_key(source_id, chunk_id, source_doc_text, resolved_model)
    cached = _cache_get(cache_dir, key)
    if cached is not None:
        return cached

    summary = _call_anthropic(chunk_text, source_doc_text, source_info, resolved_model)
    if summary is None:
        # Degrade to deterministic placeholder rather than block ingestion.
        # Do NOT cache the fallback — a future retry should re-attempt the
        # live call.
        return _eval_summary(chunk_text, source_info)

    _cache_put(cache_dir, key, summary, source_id, chunk_id, resolved_model)
    return summary


def contextualize_text_for_embedding(chunk_text: str, context_summary: str) -> str:
    """Combine the context summary with the verbatim chunk text in the form
    that gets embedded + BM25-indexed.

    Plan §7.2.b §3 specifies "Prepend the response to the chunk's ``text``
    field before BM25 indexing and embedding". We separate the two with a
    blank line so Voyage's input chunking treats them as related but
    distinct paragraphs.
    """

    if not context_summary:
        return chunk_text
    return f"{context_summary}\n\n{chunk_text}"


def embed_and_upsert_chunks(
    corpus: Any,
    embedder: Any,
    chunks: list[Any],
    source_doc_text: str,
    *,
    model: str | None = None,
    cache_dir: Path | None = None,
) -> None:
    """Ingestor entry point — embed + persist a batch of chunks, with
    optional Anthropic Contextual Retrieval applied when
    ``COPILOT_CONTEXTUAL_RETRIEVAL=1``.

    Replaces the inline two-step pattern::

        embeddings = embedder.embed([c.text for c in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            corpus.upsert_chunk(chunk, embedding)

    with a single call that takes care of the contextualization decision.
    When contextualization is disabled the embedded text is the verbatim
    chunk (byte-identical to the pre-AgDR-0079 path); when enabled, the
    embedded + BM25-indexed text is ``context_summary + "\\n\\n" + text``
    and the ``context_summary`` is persisted to the new
    ``chunks.context_summary`` column.
    """

    if not chunks:
        return

    contextualize = is_contextual_retrieval_enabled()

    if not contextualize:
        embeddings = embedder.embed([c.text for c in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            corpus.upsert_chunk(chunk, embedding)
        return

    summaries: list[str] = []
    texts_to_embed: list[str] = []
    for chunk in chunks:
        summary = generate_context_summary(
            chunk.text,
            source_doc_text,
            {
                "source_organization": getattr(chunk, "source_organization", None),
                "source_year": getattr(chunk, "source_year", None),
                "source_name": getattr(chunk, "source_name", None),
            },
            source_id=chunk.source_id,
            chunk_id=chunk.chunk_id,
            model=model,
            cache_dir=cache_dir,
        )
        summaries.append(summary)
        texts_to_embed.append(contextualize_text_for_embedding(chunk.text, summary))

    embeddings = embedder.embed(texts_to_embed)
    for chunk, embedding, summary in zip(chunks, embeddings, summaries):
        corpus.upsert_chunk(chunk, embedding, context_summary=summary)
