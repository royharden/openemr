#!/usr/bin/env bash
# shellcheck disable=SC2249,SC2250,SC2292
#
# run_eval_gate.sh — single source of truth for the Clinical Co-Pilot eval gate.
#
# Invoked from three places (Plan §3 decision #10):
#   - Local pre-push hook (via .pre-commit-config.yaml, hook stage `pre-push`)
#   - GitHub Actions PR-blocking workflow (.github/workflows/eval-gate.yml)
#   - Manual local runs by developers
#
# Modes:
#   --smoke           Fast subset (~10 cases) for the pre-push hook (<30s budget).
#   --full            Full case suite (the PR-blocking gate uses this).
#   --case=N,M        Run a specific subset of cases by ID prefix.
#   --rubric-report   Emit the per-rubric matrix (boolean rubrics).
#   --skip-coverage   Skip the coverage report entirely.
#   --skip-pytest     Skip the pytest layer entirely (eval-cases-only run).
#
# Determinism:
#   The runner runs in COPILOT_EVAL_MODE=1 by default, which substitutes
#   `EvalEmbedder` / `EvalReranker` / `EvalVisionExtractor` for the live
#   Voyage / Cohere / Anthropic boundaries (Plan §3 decision #19). A
#   vendor outage CANNOT block a PR merge.
#
# Coverage:
#   Coverage report is produced for visibility, but no project-wide
#   `--cov-fail-under` is enforced at the W0 stage. Per-module floors
#   land via AgDR-0051 once Teams A/B/C ship the modules they cover
#   (Plan §15.5.5 + §15.5.7). Floor changes are AgDR-gated.
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
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SIDECAR_DIR="${REPO_ROOT}/agent/copilot-api"

MODE="full"
CASE_FILTER=""
RUBRIC_REPORT="0"
SKIP_COVERAGE="0"
SKIP_PYTEST="0"

for arg in "$@"; do
    case "${arg}" in
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
        --skip-pytest)
            SKIP_PYTEST="1"
            ;;
        -h|--help)
            sed -n '2,40p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "run_eval_gate.sh: unknown arg: ${arg}" >&2
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
if [[ -z "${PYTHON_BIN}" ]]; then
    if [[ -x "${SIDECAR_DIR}/.venv/bin/python" ]]; then
        PYTHON_BIN="${SIDECAR_DIR}/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "run_eval_gate.sh: no Python interpreter found." >&2
        echo "  Install Python 3.11+ or set SIDECAR_PYTHON to a venv interpreter" >&2
        echo "  with the sidecar dependencies (pyproject.toml [project] section)." >&2
        exit 2
    fi
fi

cd "${SIDECAR_DIR}"

RUNNER_ARGS=()
case "${MODE}" in
    smoke)
        RUNNER_ARGS+=(--smoke)
        ;;
    full)
        RUNNER_ARGS+=(--full)
        ;;
    *)
        echo "run_eval_gate.sh: internal error: unhandled MODE=${MODE}" >&2
        exit 2
        ;;
esac
if [[ -n "${CASE_FILTER}" ]]; then
    RUNNER_ARGS+=(--case "${CASE_FILTER}")
fi
if [[ "${RUBRIC_REPORT}" = "1" ]]; then
    RUNNER_ARGS+=(--rubric-report)
fi

echo "==> Eval gate (mode=${MODE}, COPILOT_EVAL_MODE=${COPILOT_EVAL_MODE}, python=${PYTHON_BIN})"
"${PYTHON_BIN}" -m evals.runner "${RUNNER_ARGS[@]}"

# Pytest layer — covers the L1 unit + L2 integration tests AND the legacy
# Wk1 flat tests/test_*.py files. tests/e2e is excluded because e2e tests
# need a running sidecar; they're CI-only via a separate workflow step.
if [[ "${SKIP_PYTEST}" != "1" ]]; then
    if "${PYTHON_BIN}" -c "import pytest" >/dev/null 2>&1; then
        if [[ "${SKIP_COVERAGE}" = "1" ]]; then
            echo "==> Pytest (no coverage)"
            "${PYTHON_BIN}" -m pytest -q \
                --ignore=tests/e2e \
                tests/
        else
            echo "==> Pytest + coverage report (no project-wide floor; per-module via AgDR-0051)"
            "${PYTHON_BIN}" -m pytest -q \
                --ignore=tests/e2e \
                --cov=app \
                --cov-report=term-missing:skip-covered \
                tests/
        fi
    else
        echo "==> pytest not available; skipping pytest layer (CI must enforce)" >&2
    fi
fi

echo "==> Eval gate PASSED (mode=${MODE})"
exit 0
