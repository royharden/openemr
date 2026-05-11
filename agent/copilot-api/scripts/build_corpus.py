"""Idempotent corpus builder for the Clinical Co-Pilot guideline RAG pipeline.

Usage
-----
    python scripts/build_corpus.py [--corpus-path PATH] [--force]

Defaults
--------
Corpus DB: agent/copilot-api/corpus.db (adjacent to the app package).

Idempotency
-----------
The builder computes a SHA-256 content hash of all (id, text, embedding)
rows before and after running each ingestor.  If the hash is unchanged after
an ingestor run, no rows were modified.  On a completely unchanged input set,
the corpus.db file is bit-identical to the previous run.

Sources ingested
----------------
1. CDC ACIP recommendations + immunization schedules (public domain).
   Fetches fresh from cdc.gov; falls back to bundled snapshot on error.
   Source: app/rag/ingestion/cdc_acip.py

2. openFDA drug labels — 25 high-frequency PCP drugs:
   metformin, lisinopril, atorvastatin, amlodipine, omeprazole,
   levothyroxine, metoprolol, losartan, albuterol, simvastatin,
   gabapentin, sertraline, amoxicillin, azithromycin, warfarin,
   hydrochlorothiazide, furosemide, clopidogrel, fluticasone,
   rosuvastatin, prednisone, ibuprofen, acetaminophen,
   insulin glargine, pantoprazole.
   Source: app/rag/ingestion/openfda.py

3. HMS Library of Evidence — curated subset of evidence summaries
   covering primary-care CDS topics (diabetes, HTN, hyperlipidemia,
   anticoagulation, asthma/COPD, immunization, pain management).
   Source: app/rag/ingestion/hms_loe.py

NOT included (deferred)
-----------------------
- USPSTF recommendations — deferred to Week 3 (status file §I, §K drift
  entry 2026-05-09; API key lead time incompatible with sprint clock).

Environment variables
---------------------
COPILOT_EVAL_MODE=1   — use EvalEmbedder (deterministic, no Voyage call)
VOYAGE_API_KEY        — required for live embedding (unless eval mode)
OPENFDA_API_KEY       — optional; raises openFDA rate limit to 240/min
EMBEDDER_PROVIDER     — "voyage" (default) or "openai"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Ensure the copilot-api package root is on sys.path when run as a script.
_HERE = Path(__file__).resolve().parent
_PKG_ROOT = _HERE.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from app.rag.corpus import Corpus
from app.rag.embedder import get_embedder
from app.rag.ingestion import cdc_acip, openfda, hms_loe, ada_2026, acc_aha_2026

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger("build_corpus")


def build(corpus_path: Path | None = None, force: bool = False) -> None:
    """Run all ingestors, log counts, verify idempotency."""
    corpus = Corpus(path=corpus_path)
    embedder = get_embedder()

    with corpus:
        corpus.ensure_schema()
        hash_before = corpus.content_hash()
        count_before = corpus.count()
        logger.info(
            "Corpus opened: %d existing chunks (hash=%s)",
            count_before,
            hash_before[:12],
        )

        # --- CDC ACIP ---
        t0 = time.monotonic()
        n_acip = cdc_acip.ingest(corpus, embedder)
        logger.info("CDC ACIP: %d chunks upserted (%.1fs)", n_acip, time.monotonic() - t0)

        # --- openFDA ---
        t0 = time.monotonic()
        n_fda = openfda.ingest(corpus, embedder)
        logger.info("openFDA: %d chunks upserted (%.1fs)", n_fda, time.monotonic() - t0)

        # --- HMS-LOE ---
        t0 = time.monotonic()
        n_hms = hms_loe.ingest(corpus, embedder)
        logger.info("HMS-LOE: %d chunks upserted (%.1fs)", n_hms, time.monotonic() - t0)

        # --- ADA 2026 Standards of Care (locally-authored summaries) ---
        t0 = time.monotonic()
        n_ada = ada_2026.ingest(corpus, embedder)
        logger.info("ADA-SoC-2026: %d chunks upserted (%.1fs)", n_ada, time.monotonic() - t0)

        # --- ACC/AHA 2026 Dyslipidemia (locally-authored summaries) ---
        t0 = time.monotonic()
        n_acc = acc_aha_2026.ingest(corpus, embedder)
        logger.info(
            "ACC-AHA-Lipid-2026: %d chunks upserted (%.1fs)",
            n_acc,
            time.monotonic() - t0,
        )

        hash_after = corpus.content_hash()
        count_after = corpus.count()
        added = count_after - count_before
        changed = hash_before != hash_after

        logger.info(
            "Build complete: %d total chunks (%+d vs before). "
            "Content hash %s → %s (%s)",
            count_after,
            added,
            hash_before[:12],
            hash_after[:12],
            "CHANGED" if changed else "UNCHANGED",
        )

        if not changed and count_after > 0:
            logger.info("Corpus is idempotent — no modifications on unchanged sources.")
        elif count_after == 0:
            logger.error("Corpus is empty after build — check ingestor logs above.")
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=None,
        help="Path to corpus.db (default: auto-derived from package location)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-embed even if hash is unchanged (not normally needed)",
    )
    args = parser.parse_args()
    build(corpus_path=args.corpus_path, force=args.force)


if __name__ == "__main__":
    main()
