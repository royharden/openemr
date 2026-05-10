"""Startup self-test for the Clinical Co-Pilot sidecar.

Plan §15.5.11 + AgDR-0056: when uvicorn boots, `startup_self_test()` runs
a fail-fast sanity sequence. A `STARTUP_SELF_TEST: FAILED` line on stderr
causes uvicorn to exit non-zero, so a broken sidecar never accepts traffic.

Steps (all bounded ≤500ms total when each succeeds):

  1. `validate_provider_credentials()` — pings each configured provider
     once with a minimal call (Plan §3 decision #20 / AgDR-0043). Skipped
     entirely under `COPILOT_EVAL_MODE=1` since the deterministic mocks
     do not need vendor connectivity.
  2. `validate_corpus_db()` — confirms corpus.db is loadable AND has rows
     in `chunks` (when the file exists). During Wk2 Workstream 0/0.5, the
     corpus is not yet built, so a missing file is logged as a warning but
     does NOT fail the self-test. After Workstream B lands, the corpus
     becomes a hard requirement.
  3. `run_smoke_pytest()` — runs L1 unit tests matching `test_smoke_*.py`
     in <500ms. Wk2 starts with zero such files; Teams A/B/C add them.

Bypass policies:
  - `COPILOT_SKIP_STARTUP_SELF_TEST=1` — skip everything (tests / CI only).
    Documented as antipattern §13.23 — never use in production.

The Wk2 plan keeps this file deliberately small. The contract is the
public API:

    startup_self_test() -> None  # raises StartupSelfTestError on hard failure

Callers (uvicorn entrypoint, healthcheck) catch the error and exit / 503.
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
from typing import Callable

logger = logging.getLogger(__name__)


class StartupSelfTestError(RuntimeError):
    """Raised when a hard self-test step fails."""


# ----------------------------------------------------------------------------
# Provider credential validation (decision #20 / AgDR-0043)
# ----------------------------------------------------------------------------


def _ping_anthropic() -> None:
    """One cheap call to confirm the configured model id is accepted."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise StartupSelfTestError("ANTHROPIC_API_KEY not set")
    try:
        import anthropic  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise StartupSelfTestError(f"anthropic SDK not installed: {e}") from e
    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("COPILOT_MODEL", "claude-haiku-4-5-20251001")
    # Minimal completion to verify model id is accepted by the API.
    client.messages.create(
        model=model,
        max_tokens=4,
        messages=[{"role": "user", "content": "ping"}],
    )


def _ping_voyage() -> None:
    """Embed one tiny string to confirm the key + model id are valid."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        # Voyage is optional during W0 / W0.5 — Workstream B makes it required.
        logger.info("VOYAGE_API_KEY not set; skipping voyage ping")
        return
    try:
        import voyageai  # type: ignore
    except ImportError:  # pragma: no cover
        logger.info("voyageai SDK not installed; skipping voyage ping")
        return
    voyageai.Client(api_key=api_key).embed(["ok"], model="voyage-4-large")


def _ping_cohere() -> None:
    """Rerank one candidate to confirm Cohere accepts the key."""
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        logger.info("COHERE_API_KEY not set; skipping cohere ping")
        return
    try:
        import cohere  # type: ignore
    except ImportError:  # pragma: no cover
        logger.info("cohere SDK not installed; skipping cohere ping")
        return
    cohere.Client(api_key=api_key).rerank(
        model="rerank-3.5",
        query="ok",
        documents=["ok"],
        top_n=1,
    )


def validate_provider_credentials() -> None:
    """Decision #20 / AgDR-0043. Raises StartupSelfTestError on misconfig."""
    if os.getenv("COPILOT_EVAL_MODE") == "1":
        logger.info("COPILOT_EVAL_MODE=1; skipping live provider pings")
        return

    pings: list[tuple[str, Callable[[], None]]] = [
        ("anthropic", _ping_anthropic),
        ("voyage", _ping_voyage),
        ("cohere", _ping_cohere),
    ]
    for name, fn in pings:
        try:
            fn()
        except StartupSelfTestError:
            raise
        except Exception as e:
            raise StartupSelfTestError(
                f"validate_provider_credentials: {name} ping failed: {e}"
            ) from e


# ----------------------------------------------------------------------------
# Corpus.db validation (W2 Workstream B output)
# ----------------------------------------------------------------------------


def validate_corpus_db() -> None:
    corpus_path_str = os.getenv("COPILOT_CORPUS_DB", "corpus.db")
    corpus_path = pathlib.Path(corpus_path_str)
    if not corpus_path.is_absolute():
        # Resolve relative to the sidecar root (parent of this file's package).
        corpus_path = (pathlib.Path(__file__).resolve().parent.parent / corpus_path).resolve()

    if not corpus_path.exists():
        logger.warning(
            "corpus.db not found at %s; Workstream B has not yet built it. "
            "This is acceptable until W2 RAG lands.",
            corpus_path,
        )
        return

    import sqlite3

    try:
        con = sqlite3.connect(corpus_path)
        try:
            row = con.execute("SELECT count(*) FROM chunks").fetchone()
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        raise StartupSelfTestError(f"corpus.db chunks table not queryable: {e}") from e
    if not row or int(row[0]) == 0:
        raise StartupSelfTestError("corpus.db has zero chunks")


# ----------------------------------------------------------------------------
# Smoke pytest run (≤500ms)
# ----------------------------------------------------------------------------


def run_smoke_pytest() -> None:
    """Run any `test_smoke_*.py` files under tests/ in-process. Soft fail."""
    try:
        import pytest  # type: ignore
    except ImportError:  # pragma: no cover
        logger.info("pytest not available; skipping smoke run")
        return

    sidecar_root = pathlib.Path(__file__).resolve().parent.parent
    smoke_files = list(sidecar_root.glob("tests/**/test_smoke_*.py"))
    if not smoke_files:
        logger.info("no test_smoke_*.py files found; skipping smoke run")
        return

    started = time.monotonic()
    rc = pytest.main(["-q", "--no-header", *map(str, smoke_files)])
    elapsed_ms = (time.monotonic() - started) * 1000
    if elapsed_ms > 500:
        logger.warning(
            "smoke pytest exceeded 500ms budget (%.0fms) — trim or move to L2",
            elapsed_ms,
        )
    if rc != 0:
        raise StartupSelfTestError(f"smoke pytest failed (rc={rc})")


# ----------------------------------------------------------------------------
# Public entrypoint
# ----------------------------------------------------------------------------


def startup_self_test() -> None:
    if os.getenv("COPILOT_SKIP_STARTUP_SELF_TEST") == "1":
        # Antipattern §13.23 — only used in unit tests that import `app`.
        logger.warning("COPILOT_SKIP_STARTUP_SELF_TEST=1; bypassing startup checks")
        print("STARTUP_SELF_TEST: SKIPPED", file=sys.stderr)
        return

    started = time.monotonic()
    try:
        validate_provider_credentials()
        validate_corpus_db()
        run_smoke_pytest()
    except StartupSelfTestError as e:
        elapsed_ms = (time.monotonic() - started) * 1000
        print(f"STARTUP_SELF_TEST: FAILED ({elapsed_ms:.0f}ms) — {e}", file=sys.stderr)
        raise
    elapsed_ms = (time.monotonic() - started) * 1000
    print(f"STARTUP_SELF_TEST: PASSED ({elapsed_ms:.0f}ms)", file=sys.stderr)
