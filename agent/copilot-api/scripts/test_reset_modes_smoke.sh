#!/usr/bin/env bash
# shellcheck disable=SC2310
#
# Smoke test for the Wk2 demo-reset modes added in
# Plan_wk2_Claude_Next07_v2 (Workstream A). Runs in a few hundred
# milliseconds, requires no DB / no Docker / no network — pure static
# inspection of the bash sources + a `bash -n` parse pass on each one.
#
# What it pins (all PASS / FAIL lines printed to stdout; exit non-zero if
# anything fails):
#
#   1. reset_demo_state.sh + reset_wk2_demo_baseline.sh both `bash -n` clean.
#   2. reset_demo_state.sh declares the dry-run / uploads-only env vars,
#      the mysql_run_destructive / mysql_run_destructive_strict /
#      fs_remove_destructive helpers, and the PATIENT_DELETE_CSV
#      two-set decomposition.
#   3. Every former destructive `mysql_run_optional "DELETE ..."` /
#      `mysql_run "DELETE ..."` call site now routes through the new
#      destructive helpers — no bare `mysql_run_optional "DELETE` or
#      `mysql_run "DELETE` survives in the script.
#   4. The wrapper exposes --dry-run, --uploads-only, --full-reseed; the
#      mutual-exclusion guard for --reset-only + --uploads-only is
#      present; and the two new env vars are propagated through
#      docker compose exec via -e.
#   5. The PowerShell wrapper mirrors -DryRun / -UploadsOnly / -FullReseed
#      and the mutual-exclusion guard.
#   6. The DEMO_RUNBOOK_Wk2 §0.3 cheat sheet names all four modes.
#
# Plan reference: Plan_wk2_Claude_Next07_v2 §A.3.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

INNER_SH="${SCRIPT_DIR}/reset_demo_state.sh"
WRAPPER_SH="${REPO_ROOT}/openemr/scripts/reset_wk2_demo_baseline.sh"
WRAPPER_PS1="${REPO_ROOT}/openemr/scripts/reset_wk2_demo_baseline.ps1"
RUNBOOK="${REPO_ROOT}/openemr/agentdocs/DEMO_RUNBOOK_Wk2.md"

FAILED=0

pass() { printf '  PASS  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=$((FAILED + 1)); }

require_file() {
    if [[ ! -f "$1" ]]; then
        fail "missing file: $1"
        return 1
    fi
    return 0
}

require_grep() {
    # require_grep <label> <pattern> <file>
    if grep -qE "$2" "$3" 2>/dev/null; then
        pass "$1"
    else
        fail "$1 (pattern: $2 not in $3)"
    fi
}

require_no_grep() {
    # require_no_grep <label> <pattern> <file>
    if grep -qE "$2" "$3" 2>/dev/null; then
        fail "$1 (unwanted pattern: $2 still present in $3)"
    else
        pass "$1"
    fi
}

echo "=== Test 1: bash -n on reset_demo_state.sh + wrapper ==="
require_file "${INNER_SH}" || exit 1
require_file "${WRAPPER_SH}" || exit 1
if bash -n "${INNER_SH}" 2>/dev/null; then
    pass "reset_demo_state.sh parses clean"
else
    fail "reset_demo_state.sh bash -n failed"
fi
if bash -n "${WRAPPER_SH}" 2>/dev/null; then
    pass "reset_wk2_demo_baseline.sh parses clean"
else
    fail "reset_wk2_demo_baseline.sh bash -n failed"
fi

echo "=== Test 2: inner script declares mode env vars + helpers ==="
require_grep "COPILOT_DEMO_DRY_RUN env declared" \
    'DRY_RUN="\$\{COPILOT_DEMO_DRY_RUN' "${INNER_SH}"
require_grep "COPILOT_DEMO_UPLOADS_ONLY env declared" \
    'UPLOADS_ONLY="\$\{COPILOT_DEMO_UPLOADS_ONLY' "${INNER_SH}"
require_grep "mysql_run_destructive helper defined" \
    '^mysql_run_destructive\(\) \{' "${INNER_SH}"
require_grep "mysql_run_destructive_strict helper defined" \
    '^mysql_run_destructive_strict\(\) \{' "${INNER_SH}"
require_grep "fs_remove_destructive helper defined" \
    '^fs_remove_destructive\(\) \{' "${INNER_SH}"
require_grep "PATIENT_DELETE_CSV two-set decomposition" \
    'PATIENT_DELETE_CSV=' "${INNER_SH}"

echo "=== Test 3: no bare destructive calls remain ==="
# Every DELETE call should now go through mysql_run_destructive or
# mysql_run_destructive_strict. The grep for mysql_run_optional "DELETE
# should return zero hits in the post-Next07 script.
require_no_grep "no bare mysql_run_optional DELETE" \
    'mysql_run_optional "DELETE' "${INNER_SH}"
require_no_grep "no bare mysql_run DELETE (use _destructive_strict)" \
    'mysql_run "DELETE' "${INNER_SH}"

echo "=== Test 4: bash wrapper exposes the new flags + guards ==="
require_grep "--dry-run flag parsed" \
    '\-\-dry-run\)' "${WRAPPER_SH}"
require_grep "--uploads-only flag parsed" \
    '\-\-uploads-only\)' "${WRAPPER_SH}"
require_grep "--full-reseed flag parsed" \
    '\-\-full-reseed\)' "${WRAPPER_SH}"
require_grep "mutual-exclusion guard present" \
    'mutually exclusive' "${WRAPPER_SH}"
require_grep "COPILOT_DEMO_DRY_RUN exported" \
    'export COPILOT_DEMO_DRY_RUN' "${WRAPPER_SH}"
require_grep "COPILOT_DEMO_UPLOADS_ONLY exported" \
    'export COPILOT_DEMO_UPLOADS_ONLY' "${WRAPPER_SH}"
require_grep "-e COPILOT_DEMO_DRY_RUN passthrough" \
    '-e COPILOT_DEMO_DRY_RUN' "${WRAPPER_SH}"
require_grep "-e COPILOT_DEMO_UPLOADS_ONLY passthrough" \
    '-e COPILOT_DEMO_UPLOADS_ONLY' "${WRAPPER_SH}"

echo "=== Test 5: PowerShell wrapper mirrors the flags + guard ==="
if require_file "${WRAPPER_PS1}"; then
    require_grep "PowerShell -DryRun switch" \
        '\[switch\]\$DryRun' "${WRAPPER_PS1}"
    require_grep "PowerShell -UploadsOnly switch" \
        '\[switch\]\$UploadsOnly' "${WRAPPER_PS1}"
    require_grep "PowerShell -FullReseed switch" \
        '\[switch\]\$FullReseed' "${WRAPPER_PS1}"
    require_grep "PowerShell mutual-exclusion guard" \
        'mutually exclusive' "${WRAPPER_PS1}"
fi

echo "=== Test 6: runbook §0.3 cheat sheet names all four modes ==="
if require_file "${RUNBOOK}"; then
    require_grep "runbook documents --dry-run" \
        '\-\-dry-run' "${RUNBOOK}"
    require_grep "runbook documents --uploads-only" \
        '\-\-uploads-only' "${RUNBOOK}"
    require_grep "runbook documents --reset-only" \
        '\-\-reset-only' "${RUNBOOK}"
    require_grep "runbook documents Mode-selection cheat sheet" \
        'Mode-selection cheat sheet' "${RUNBOOK}"
fi

echo ""
if (( FAILED == 0 )); then
    echo "ALL CHECKS PASSED"
    exit 0
else
    echo "${FAILED} CHECK(S) FAILED"
    exit 1
fi
