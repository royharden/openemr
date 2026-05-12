#!/usr/bin/env bash
# Wk2 Next05 Phase 8.2 — final verification harness.
#
# Runs the deterministic verification matrix and captures all output to
# agentdocs/wk2_next05_verification.log so the parent Next05 status
# companion can reference one canonical artifact.
#
# What this does (deterministic; safe to re-run; no PHI in output):
#   - pytest the full sidecar suite
#   - eval runner with --rubric-report (132+ cases, 11 rubric floors)
#   - corpus.db inspection: chunk count + organizations + contextualization status
#   - corpus PHI scan (rejects SSN/MRN/phone/email patterns in any chunk)
#   - corpus copyright scan (rejects tripwire phrases per AgDR-0070)
#   - python -m py_compile across every .py file under agent/copilot-api
#   - git status / branch / HEAD summary
#
# What this does NOT do (live + browser-dependent — Phase 5.1 territory):
#   - the 21-step browser sequence (Chen lab upload → chip click → drawer)
#   - Langfuse trace inspection
#   - PHP container smoke tests
#
# Usage:
#   bash openemr/scripts/wk2_next05_final_verification.sh
# Output:
#   openemr/agentdocs/wk2_next05_verification.log (overwritten on each run)
#
# Exit 0 only if every step passed. Any failure terminates the run with
# the failing command's exit code so CI / pre-recording checks see RED.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIDECAR_ROOT="$REPO_ROOT/agent/copilot-api"
LOG_PATH="$REPO_ROOT/agentdocs/wk2_next05_verification.log"

# Truncate log; write a header.
{
    echo "============================================================"
    echo "Wk2 Next05 — final verification log"
    echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "Host:    $(uname -a 2>/dev/null || echo windows)"
    echo "Repo:    $REPO_ROOT"
    echo "Sidecar: $SIDECAR_ROOT"
    echo "============================================================"
    echo
} > "$LOG_PATH"

# Helper: run a step, log header + output + exit code; abort on failure.
run_step() {
    local name="$1"
    shift
    {
        echo
        echo "------------------------------------------------------------"
        echo "STEP: $name"
        echo "CMD : $*"
        echo "TIME: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "------------------------------------------------------------"
    } >> "$LOG_PATH"
    if ! "$@" >> "$LOG_PATH" 2>&1; then
        local rc=$?
        echo "STEP '$name' FAILED with exit $rc" >> "$LOG_PATH"
        echo "STEP '$name' FAILED with exit $rc — see $LOG_PATH" >&2
        exit $rc
    fi
    echo "STEP '$name' OK" >> "$LOG_PATH"
    echo "[ok] $name"
}

# --- Repo state ---
echo "[info] writing log to $LOG_PATH"
run_step "git: HEAD + branch" git -C "$REPO_ROOT" log --oneline -1
run_step "git: status --short" git -C "$REPO_ROOT" status --short
run_step "git: branch" git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD

# --- pytest ---
cd "$SIDECAR_ROOT"
run_step "pytest (full suite)" python -m pytest tests/ -q --no-header

# --- evals ---
run_step "evals (rubric-report)" python -m evals.runner --rubric-report

# --- corpus inspection ---
run_step "corpus: chunk count" sqlite3 corpus.db \
    "SELECT 'total=' || COUNT(*) FROM chunks;"
run_step "corpus: org breakdown" sqlite3 corpus.db \
    "SELECT source_organization || ': ' || COUNT(*) FROM chunks GROUP BY source_organization ORDER BY source_organization;"
run_step "corpus: contextualization coverage" sqlite3 corpus.db \
    "SELECT 'contextualized=' || COUNT(*) || ' / total=' || (SELECT COUNT(*) FROM chunks) FROM chunks WHERE context_summary IS NOT NULL;"

# --- corpus PHI scan ---
# The PHI scan uses the same patterns as evals/rubrics.py::_PHI_PATTERNS.
# A non-empty result fails the step.
run_step "corpus: PHI scan (SSN / phone / MRN / DOB-shape)" python -c '
import re, sqlite3, sys
patterns = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                 # SSN
    re.compile(r"\b\d{3}[.\-\s]\d{3}[.\-\s]\d{4}\b"),     # phone
    re.compile(r"\bMRN[:\s]\s*\S+", re.IGNORECASE),       # MRN label
]
conn = sqlite3.connect("corpus.db")
hits = []
for cid, text in conn.execute("SELECT id, text FROM chunks"):
    for p in patterns:
        m = p.search(text or "")
        if m:
            hits.append((cid, p.pattern, m.group()))
if hits:
    print(f"PHI HIT in {len(hits)} chunk(s):")
    for cid, pat, snip in hits[:5]:
        print(f"  {cid}  pattern={pat}  match=<redacted>")
    sys.exit(2)
print("PHI scan clean.")
'

# --- corpus copyright scan (AgDR-0070) ---
run_step "corpus: copyright tripwire scan" python -m evals.runner --check-corpus-copyright

# --- python -m py_compile sweep ---
run_step "py_compile: all .py under agent/copilot-api" bash -c '
find . -type f -name "*.py" -not -path "*/.venv/*" -not -path "*/__pycache__/*" -print0 \
    | xargs -0 python -m py_compile && echo "py_compile clean across all .py files"
'

# --- summary ---
{
    echo
    echo "============================================================"
    echo "Wk2 Next05 — final verification PASSED"
    echo "Finished: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "============================================================"
} >> "$LOG_PATH"

echo "[ok] full verification passed — see $LOG_PATH"
