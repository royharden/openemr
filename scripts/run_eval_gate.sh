#!/usr/bin/env bash
#
# run_eval_gate.sh — single source of truth for the Clinical Co-Pilot eval gate.
#
# Invoked from three places (Plan §3 decision #10):
#   - Local pre-push hook (via .pre-commit-config.yaml, hook stage `pre-push`)
#   - GitHub Actions PR-blocking workflow (.github/workflows/eval-gate.yml)
#   - Manual local runs by developers
#
# Modes:
#   --smoke      Run a fast subset (~10 cases) for the pre-push hook (<30s budget).
#   --full       Run the full case suite (the PR-blocking gate uses this).
#   --case=N,M   Run a specific subset of cases by ID prefix.
#   --rubric-report  Emit the per-rubric matrix (boolean rubrics) in addition to pass/fail.
#
# Determinism:
#   The runner runs in COPILOT_EVAL_MODE=1 by default, which substitutes
#   `EvalEmbedder` / `EvalReranker` / `EvalVisionExtractor` for the live
#   Voyage / Cohere / Anthropic boundaries (Plan §3 decision #19). This means
#   a Voyage / Cohere / Anthropic outage CANNOT block a PR merge.
#
# Coverage:
#   With --full the runner also emits `pytest --cov=app --cov-fail-under=75`
#   on the unit + integration test layers (Plan §15.5.5).
#
# Exit codes:
#   0  All cases passed at or above floor.
#   1  One or more rubrics failed or below floor (regression).
#   2  Configuration/load error (missing cases dir, bad case JSON, etc.).
#
# This script is the contract; the runner under it can change without
# breaking the contract. Do not invent a parallel script — extend this one.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SIDECAR_DIR="$REPO_ROOT/agent/copilot-api"

MODE="full"
CASE_FILTER=""
RUBRIC_REPORT="0"
SKIP_COVERAGE="0"

for arg in "$@"; do
    case "$arg" in
        --smoke)
            MODE="smoke"
            SKIP_COVERAGE="1"
            ;;
        --full)
            MODE="full"
            ;;
        --case=*)
            CASE_FILTER="${arg#--case=}"
            SKIP_COVERAGE="1"
            ;;
        --rubric-report)
            RUBRIC_REPORT="1"
            ;;
        --skip-coverage)
            SKIP_COVERAGE="1"
            ;;
        -h|--help)
            sed -n '2,40p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "run_eval_gate.sh: unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

# Default to deterministic-mock mode unless the caller explicitly opts out.
# Live-vendor smoke (.github/workflows/eval-gate-live.yml) sets COPILOT_EVAL_MODE=0.
export COPILOT_EVAL_MODE="${COPILOT_EVAL_MODE:-1}"

# Pick a Python that has the sidecar deps. Order:
#   1. SIDECAR_PYTHON env var (explicit override)
#   2. agent/copilot-api/.venv/bin/python (local venv)
#   3. python3 (system) — only works if pydantic et al. are pip-installed
PYTHON_BIN="${SIDECAR_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
    if [ -x "$SIDECAR_DIR/.venv/bin/python" ]; then
        PYTHON_BIN="$SIDECAR_DIR/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "run_eval_gate.sh: no Python interpreter found." >&2
        echo "  Install Python 3.11+ or set SIDECAR_PYTHON to a venv interpreter" >&2
        echo "  with the sidecar dependencies (pyproject.toml [project] section)." >&2
        exit 2
    fi
fi

cd "$SIDECAR_DIR"

RUNNER_ARGS=()
case "$MODE" in
    smoke)
        RUNNER_ARGS+=(--smoke)
        ;;
    full)
        RUNNER_ARGS+=(--full)
        ;;
esac
if [ -n "$CASE_FILTER" ]; then
    RUNNER_ARGS+=(--case "$CASE_FILTER")
fi
if [ "$RUBRIC_REPORT" = "1" ]; then
    RUNNER_ARGS+=(--rubric-report)
fi

echo "==> Eval gate (mode=$MODE, COPILOT_EVAL_MODE=$COPILOT_EVAL_MODE, python=$PYTHON_BIN)"
"$PYTHON_BIN" -m evals.runner "${RUNNER_ARGS[@]}"

EVAL_EXIT=$?
if [ $EVAL_EXIT -ne 0 ]; then
    echo "==> Eval gate FAILED (exit=$EVAL_EXIT)" >&2
    exit $EVAL_EXIT
fi

if [ "$SKIP_COVERAGE" != "1" ]; then
    if "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
        echo "==> Coverage gate (--cov-fail-under=75)"
        "$PYTHON_BIN" -m pytest \
            --cov=app \
            --cov-fail-under=75 \
            tests/unit tests/integration 2>&1 | tail -40 || {
            echo "==> Coverage gate FAILED" >&2
            exit 1
        }
    else
        echo "==> pytest not available; skipping coverage gate (CI must enforce)" >&2
    fi
fi

echo "==> Eval gate PASSED (mode=$MODE)"
exit 0
