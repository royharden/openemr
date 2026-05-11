"""SQLite + sqlite-vec corpus store for the guideline RAG pipeline.

Schema
------
  chunks(id TEXT PK, source_id TEXT, source_organization TEXT,
         source_name TEXT, page_or_section TEXT,
         recommendation_grade TEXT, source_year INTEGER,
         text TEXT, embedding BLOB, bm25_terms TEXT)

The ``bm25_terms`` column is the pre-tokenised, lowercased, whitespace-joined
form of ``text`` used by BM25Index for term-frequency counting.  Storing it
avoids re-tokenising on every retrieval.

sqlite-vec is loaded as a runtime extension via ``sqlite_vec.load()``.
See https://alexgarcia.xyz/sqlite-vec/python.html — the extension ships as a
platform wheel and is importable as a plain Python package.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any

try:
    import sqlite_vec  # type: ignore[import]
    _SQLITE_VEC_AVAILABLE = True
except ImportError:  # pragma: no cover — CI installs it; guard for dev laptops
    _SQLITE_VEC_AVAILABLE = False

from .contracts import GuidelineChunk

logger = logging.getLogger(__name__)

# Default corpus file location (overridable via env or constructor arg).
DEFAULT_CORPUS_PATH = Path(__file__).parent.parent.parent / "corpus.db"

# Embedding dimensionality for the default Voyage voyage-4-large model.
VOYAGE_DIM = 1024

_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    if not _SQLITE_VEC_AVAILABLE:
        logger.warning("sqlite-vec not installed — vector search disabled")
        return
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except sqlite3.OperationalError as exc:
        logger.warning("sqlite-vec extension load failed (%s) - vector search will use fallback", exc)
    finally:
        try:
            conn.enable_load_extension(False)
        except sqlite3.OperationalError:
            pass


class Corpus:
    """Wrapper around the SQLite + sqlite-vec chunk store.

    Usage::

        corpus = Corpus()            # opens/creates at DEFAULT_CORPUS_PATH
        corpus.open()
        corpus.ensure_schema()
        # … ingestors call corpus.upsert_chunk(chunk, embedding)
        corpus.close()

    The ``open`` / ``close`` pattern is explicit so callers (build_corpus.py,
    tests) can control the connection lifecycle.  Use as a context manager::

        with Corpus() as corpus:
            corpus.ensure_schema()
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CORPUS_PATH
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "Corpus":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        _load_sqlite_vec(self._conn)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Corpus is not open — call open() first")
        return self._conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id                   TEXT PRIMARY KEY,
                source_id            TEXT NOT NULL,
                source_organization  TEXT NOT NULL,
                source_name          TEXT NOT NULL,
                page_or_section      TEXT NOT NULL,
                recommendation_grade TEXT,
                source_year          INTEGER,
                text                 TEXT NOT NULL,
                embedding            BLOB,
                bm25_terms           TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_source_org
                ON chunks(source_organization);
            CREATE INDEX IF NOT EXISTS idx_chunks_source_year
                ON chunks(source_year);
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Content hash (idempotency)
    # ------------------------------------------------------------------

    def content_hash(self) -> str:
        """SHA-256 of all (id, text, embedding) tuples — stable iff corpus unchanged."""
        cur = self.conn.execute(
            "SELECT id, text, embedding FROM chunks ORDER BY id"
        )
        h = hashlib.sha256()
        for row in cur:
            h.update(row["id"].encode())
            h.update((row["text"] or "").encode())
            h.update(row["embedding"] or b"")
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_chunk(self, chunk: GuidelineChunk, embedding: list[float] | None) -> None:
        text = _scrub_contact_patterns(chunk.text)
        blob = _pack_embedding(embedding) if embedding else None
        bm25_terms = _tokenize(text)
        self.conn.execute(
            """
            INSERT INTO chunks
                (id, source_id, source_organization, source_name,
                 page_or_section, recommendation_grade, source_year,
                 text, embedding, bm25_terms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_id            = excluded.source_id,
                source_organization  = excluded.source_organization,
                source_name          = excluded.source_name,
                page_or_section      = excluded.page_or_section,
                recommendation_grade = excluded.recommendation_grade,
                source_year          = excluded.source_year,
                text                 = excluded.text,
                embedding            = excluded.embedding,
                bm25_terms           = excluded.bm25_terms
            """,
            (
                chunk.chunk_id,
                chunk.source_id,
                chunk.source_organization,
                chunk.source_name,
                chunk.page_or_section,
                chunk.recommendation_grade,
                chunk.source_year,
                text,
                blob,
                bm25_terms,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def chunk_exists(self, chunk_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM chunks WHERE id = ? LIMIT 1", (chunk_id,)
        )
        return cur.fetchone() is not None

    def get_chunk(self, chunk_id: str) -> GuidelineChunk | None:
        cur = self.conn.execute(
            """SELECT id, source_id, source_organization, source_name,
                      page_or_section, recommendation_grade, source_year, text
               FROM chunks WHERE id = ?""",
            (chunk_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return GuidelineChunk(
            chunk_id=row["id"],
            source_id=row["source_id"],
            source_organization=row["source_organization"],
            source_name=row["source_name"],
            page_or_section=row["page_or_section"],
            recommendation_grade=row["recommendation_grade"],
            source_year=row["source_year"],
            text=row["text"],
        )

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cur.fetchone()[0]

    def all_rows(self) -> list[dict[str, Any]]:
        """Return lightweight row dicts (no embedding blob) for BM25 indexing.

        AgDR-0080: includes ``source_organization`` / ``recommendation_grade``
        / ``source_year`` so the BM25 index can be filtered post-retrieval
        without a second DB roundtrip.
        """
        cur = self.conn.execute(
            """SELECT id, bm25_terms, source_organization,
                      recommendation_grade, source_year
               FROM chunks ORDER BY id"""
        )
        return [
            {
                "id": r["id"],
                "bm25_terms": r["bm25_terms"],
                "source_organization": r["source_organization"],
                "recommendation_grade": r["recommendation_grade"],
                "source_year": r["source_year"],
            }
            for r in cur
        ]

    def vector_candidates(
        self,
        query_embedding: list[float],
        k: int = 20,
        *,
        source_organizations: list[str] | None = None,
        year_window: tuple[int, int] | None = None,
    ) -> list[tuple[str, float]]:
        """Return up to *k* (chunk_id, cosine_score) pairs via sqlite-vec.

        Optional AgDR-0080 filters are pushed down to SQL when set:
          * ``source_organizations`` — restrict to chunks whose
            ``source_organization`` is in the supplied list (case-sensitive
            because the corpus stores canonical organization names like
            ``CDC-ACIP``, ``FDA``, ``ACC-AHA``).
          * ``year_window`` — ``(min_year, max_year)`` inclusive on
            ``source_year``. Pass ``None`` for an unbounded side via the
            tuple itself; the caller is expected to supply both bounds
            when this filter is used.

        Recommendation-grade filtering happens at the Python layer in
        ``HybridRetriever.query`` because grade ordering ("A" < "B" < "C")
        is application-level semantics that does not belong in the SQL
        schema.

        Falls back to brute-force dot-product scan if the extension isn't
        loaded (e.g., CI environments without the wheel) — same filters
        applied there.
        """
        if not _SQLITE_VEC_AVAILABLE:
            return self._brute_force_vector(
                query_embedding,
                k,
                source_organizations=source_organizations,
                year_window=year_window,
            )

        q_blob = _pack_embedding(query_embedding)
        params: list[Any] = [q_blob]
        where_clauses = ["embedding IS NOT NULL"]
        if source_organizations:
            placeholders = ",".join("?" * len(source_organizations))
            where_clauses.append(f"source_organization IN ({placeholders})")
            params.extend(source_organizations)
        if year_window is not None:
            min_year, max_year = year_window
            where_clauses.append("source_year BETWEEN ? AND ?")
            params.extend([min_year, max_year])
        params.append(k)
        where_sql = " AND ".join(where_clauses)
        try:
            # sqlite-vec uses vec_distance_cosine (lower = more similar).
            cur = self.conn.execute(
                f"""
                SELECT id,
                       1.0 - vec_distance_cosine(embedding, ?) AS score
                FROM chunks
                WHERE {where_sql}
                ORDER BY score DESC
                LIMIT ?
                """,
                params,
            )
            return [(r[0], float(r[1])) for r in cur]
        except Exception:  # noqa: BLE001 — extension may lack the function
            return self._brute_force_vector(
                query_embedding,
                k,
                source_organizations=source_organizations,
                year_window=year_window,
            )

    def _brute_force_vector(
        self,
        query_embedding: list[float],
        k: int,
        *,
        source_organizations: list[str] | None = None,
        year_window: tuple[int, int] | None = None,
    ) -> list[tuple[str, float]]:
        """Pure-Python cosine similarity fallback. AgDR-0080 filters honored."""
        params: list[Any] = []
        where_clauses = ["embedding IS NOT NULL"]
        if source_organizations:
            placeholders = ",".join("?" * len(source_organizations))
            where_clauses.append(f"source_organization IN ({placeholders})")
            params.extend(source_organizations)
        if year_window is not None:
            min_year, max_year = year_window
            where_clauses.append("source_year BETWEEN ? AND ?")
            params.extend([min_year, max_year])
        where_sql = " AND ".join(where_clauses)
        cur = self.conn.execute(
            f"SELECT id, embedding FROM chunks WHERE {where_sql}",
            params,
        )
        scored: list[tuple[str, float]] = []
        q = query_embedding
        q_norm = sum(x * x for x in q) ** 0.5 or 1.0
        for row in cur:
            vec = _unpack_embedding(row[1])
            if len(vec) != len(q):
                continue
            dot = sum(a * b for a, b in zip(q, vec))
            v_norm = sum(x * x for x in vec) ** 0.5 or 1.0
            scored.append((row[0], dot / (q_norm * v_norm)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _tokenize(text: str) -> str:
    """Lowercase, strip punctuation, return space-joined terms for BM25."""
    import re
    tokens = [token for token in re.findall(r"[a-z0-9]+", text.lower()) if not token.isdigit()]
    return " ".join(tokens)


def _scrub_contact_patterns(text: str) -> str:
    """Remove public contact strings that trip the corpus PHI scanner."""
    scrubbed = _EMAIL_RE.sub("[email-redacted]", text)
    return _PHONE_RE.sub("[phone-redacted]", scrubbed)


def _pack_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
