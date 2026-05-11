#!/usr/bin/env bash
#
# Week-2 Clinical Co-Pilot demo reset.
#
# Wipes Wk2 demo patients (Chen/Whitaker/Reyes/Kowalski + any intake-created
# demo patients) along with their derived facts and documents so the demo
# video can be re-recorded from a clean state.
#
# Hard-gated: requires COPILOT_DEMO_RESET_OK=1 in the environment.
# Hard-ceiling: refuses to run if the WK2-DEMO-% pattern resolves to >10
# patients (sanity guard against running against the wrong DB).
#
# Filter pattern (per plan §5.2):
#   * patient_data.pubpid LIKE 'WK2-DEMO-%'   (seed-script patients)
#   * patient_data.usertext1 LIKE 'wk2-demo-intake-%'   (intake-create endpoint)
#
# Plan reference: openemr/planning/Plan_wk2_Claude_Next04_2026-05-10_demo-and-fhir-closure.md §5
#
# Usage:
#   export COPILOT_DEMO_RESET_OK=1
#   ./scripts/reset_demo_state.sh
#
# Optional overrides:
#   COPILOT_DEMO_DB_USER   (default: root)
#   COPILOT_DEMO_DB_PASS   (default: root)
#   COPILOT_DEMO_DB_NAME   (default: openemr)

set -euo pipefail

# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------
if [[ "${COPILOT_DEMO_RESET_OK:-}" != "1" ]]; then
    echo "ERROR: refusing to run without COPILOT_DEMO_RESET_OK=1 in env." >&2
    echo "       This is a destructive script. Set the var only when you" >&2
    echo "       intend to wipe Wk2 demo patients + derived facts." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_USER="${COPILOT_DEMO_DB_USER:-root}"
DB_PASS="${COPILOT_DEMO_DB_PASS:-root}"
DB_NAME="${COPILOT_DEMO_DB_NAME:-openemr}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Logs go next to the copilot-api root (agent/copilot-api/.demo-reset.log).
LOG_FILE="${SCRIPT_DIR}/../.demo-reset.log"

# ---------------------------------------------------------------------------
# mysql helper — prints results without a header for easier scripting.
# We swallow errors from optional/maybe-missing tables (catch-and-continue
# pattern for tables created by concurrent migrations).
# ---------------------------------------------------------------------------
mysql_run() {
    mysql -u"${DB_USER}" -p"${DB_PASS}" -N -B "${DB_NAME}" -e "$1"
}

mysql_run_optional() {
    # Same as mysql_run but never fails the script. Used for DELETEs against
    # tables that may not yet exist (e.g. copilot_document_sha_index is being
    # created in a parallel migration; copilot_fact_to_result_map likewise).
    mysql -u"${DB_USER}" -p"${DB_PASS}" -N -B "${DB_NAME}" -e "$1" 2>/dev/null || true
}

log() {
    local ts
    ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "[${ts}] $*" | tee -a "${LOG_FILE}"
}

# Ensure log dir exists.
mkdir -p "$(dirname "${LOG_FILE}")"
log "=== reset_demo_state.sh start ==="
log "DB: user=${DB_USER} db=${DB_NAME}"

# ---------------------------------------------------------------------------
# Discover demo patient IDs.
# ---------------------------------------------------------------------------
FILTER_SQL="pubpid LIKE 'WK2-DEMO-%' OR usertext1 LIKE 'wk2-demo-intake-%'"

DEMO_PIDS_RAW="$(mysql_run "SELECT pid FROM patient_data WHERE ${FILTER_SQL};")"
# Normalize to a space-separated list; treat empty input as zero patients.
DEMO_PIDS=()
if [[ -n "${DEMO_PIDS_RAW}" ]]; then
    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        DEMO_PIDS+=("${line}")
    done <<< "${DEMO_PIDS_RAW}"
fi

N_PATIENTS="${#DEMO_PIDS[@]}"

# Sanity ceiling — refuse to run if too many matches (probably wrong DB).
if (( N_PATIENTS > 10 )); then
    log "ABORT: pattern resolved to ${N_PATIENTS} patients (ceiling 10)."
    log "       Refusing to delete — verify you are running against the demo DB."
    echo "ERROR: WK2-DEMO-% pattern matched ${N_PATIENTS} patients (>10 ceiling)." >&2
    exit 3
fi

log "Discovered ${N_PATIENTS} demo patient(s) to reset."

if (( N_PATIENTS == 0 )); then
    log "Nothing to do; demo state already clean."
    echo "Reset 0 demo patients, 0 facts, 0 documents"
    log "=== reset_demo_state.sh end (no-op) ==="
    exit 0
fi

# ---------------------------------------------------------------------------
# Counters for the summary line.
# ---------------------------------------------------------------------------
TOTAL_FACTS=0
TOTAL_DOCS=0
TOTAL_RESULTS=0

# Build a comma-separated PID list usable in IN(...) clauses.
PID_CSV="$(IFS=,; echo "${DEMO_PIDS[*]}")"
log "PID list: ${PID_CSV}"

# Collect patient_uuid_hash values for fact-row filtering.
# IMPORTANT (verified live 2026-05-10): copilot_document_facts is keyed on
# patient_uuid_hash CHAR(64) — the SHA-256 hex of the string form of the
# patient.uuid (with dashes, lowercase). NOT the binary uuid. PHP gateway
# computes this hash via hash('sha256', $patientUuidString) where
# $patientUuidString is UuidRegistry::uuidToString($binaryUuid). We mirror
# that here in pure SQL.
UUID_HASHES="$(mysql_run "
SELECT SHA2(
  LOWER(
    CONCAT_WS('-',
      SUBSTR(HEX(uuid), 1, 8),
      SUBSTR(HEX(uuid), 9, 4),
      SUBSTR(HEX(uuid), 13, 4),
      SUBSTR(HEX(uuid), 17, 4),
      SUBSTR(HEX(uuid), 21, 12)
    )
  ),
  256
)
FROM patient_data WHERE pid IN (${PID_CSV}) AND uuid IS NOT NULL;" || true)"
UUID_HASH_IN_CLAUSE=""
if [[ -n "${UUID_HASHES}" ]]; then
    parts=()
    while IFS= read -r h; do
        [[ -z "${h}" ]] && continue
        parts+=("'${h}'")
    done <<< "${UUID_HASHES}"
    UUID_HASH_IN_CLAUSE="$(IFS=,; echo "${parts[*]}")"
fi

# ---------------------------------------------------------------------------
# Deletion order per plan §5.2.
# Per-patient loop kept simple — bulk deletes by IN(...) where safe.
# ---------------------------------------------------------------------------

# Step a/b. copilot_document_facts + copilot_fact_to_result_map.
# Both tables are module-owned; the map table may not yet exist (parallel
# migration), so use the optional runner.
if [[ -n "${UUID_HASH_IN_CLAUSE}" ]]; then
    # Capture count BEFORE delete so we can report it.
    FACT_COUNT="$(mysql_run "SELECT COUNT(*) FROM copilot_document_facts WHERE patient_uuid_hash IN (${UUID_HASH_IN_CLAUSE});" 2>/dev/null || echo 0)"
    FACT_COUNT="${FACT_COUNT:-0}"
    TOTAL_FACTS=$((TOTAL_FACTS + FACT_COUNT))

    # Delete map rows first (FK-style relationship to fact rows). Note: we
    # also catch any orphaned map rows whose corresponding fact row was
    # already deleted in a prior partial-reset attempt.
    mysql_run_optional "DELETE FROM copilot_fact_to_result_map WHERE copilot_document_fact_id IN (SELECT id FROM copilot_document_facts WHERE patient_uuid_hash IN (${UUID_HASH_IN_CLAUSE}));"
    mysql_run_optional "DELETE FROM copilot_document_facts WHERE patient_uuid_hash IN (${UUID_HASH_IN_CLAUSE});"
    log "Deleted ${FACT_COUNT} copilot_document_facts row(s)."
fi

# Step c/d/e. procedure_result -> procedure_report -> procedure_order.
#
# AgDR-0065: LabResultWriter writes lab facts to OpenEMR's native lab chain.
# We identify Co-Pilot-created rows by their presence in
# copilot_fact_to_result_map — the map table is the authoritative ledger of
# what we wrote and is the safest filter (vs. parsing the provenance
# comment in procedure_result.comments).
#
# This filter is critical: it ensures we ONLY delete procedure_* rows we
# created. A clinician-entered procedure_result that happens to share the
# patient is untouched because it has no map row.
# NOTE: by this point the document_facts and map rows have already been
# deleted for these patient hashes. So we cannot resolve order IDs from
# the map anymore. Fall back to filtering procedure_order directly by
# patient_id AND the provenance tag ('copilot-extracted' in
# order_diagnosis) — this is safe because LabResultWriter is the only
# writer that sets that tag.
PROC_ORDER_IDS_RAW="$(mysql_run "SELECT procedure_order_id FROM procedure_order WHERE patient_id IN (${PID_CSV}) AND order_diagnosis='copilot-extracted';" 2>/dev/null || true)"
if [[ -n "${PROC_ORDER_IDS_RAW}" ]]; then
    proc_order_csv_parts=()
    while IFS= read -r oid; do
        [[ -z "${oid}" ]] && continue
        proc_order_csv_parts+=("${oid}")
    done <<< "${PROC_ORDER_IDS_RAW}"
    if (( ${#proc_order_csv_parts[@]} > 0 )); then
        PROC_ORDER_CSV="$(IFS=,; echo "${proc_order_csv_parts[*]}")"

        # Count results that will be deleted (for the summary line).
        RESULT_COUNT="$(mysql_run "SELECT COUNT(*) FROM procedure_result pr JOIN procedure_report rep ON rep.procedure_report_id = pr.procedure_report_id WHERE rep.procedure_order_id IN (${PROC_ORDER_CSV});" 2>/dev/null || echo 0)"
        RESULT_COUNT="${RESULT_COUNT:-0}"
        TOTAL_RESULTS=$((TOTAL_RESULTS + RESULT_COUNT))

        # Delete in FK-safe order: result -> order_code -> report -> order.
        mysql_run_optional "DELETE pr FROM procedure_result pr JOIN procedure_report rep ON rep.procedure_report_id = pr.procedure_report_id WHERE rep.procedure_order_id IN (${PROC_ORDER_CSV});"
        mysql_run_optional "DELETE FROM procedure_order_code WHERE procedure_order_id IN (${PROC_ORDER_CSV});"
        mysql_run_optional "DELETE FROM procedure_report WHERE procedure_order_id IN (${PROC_ORDER_CSV});"
        mysql_run_optional "DELETE FROM procedure_order WHERE procedure_order_id IN (${PROC_ORDER_CSV});"
        log "Deleted ${RESULT_COUNT} procedure_result row(s) and their parents (orders ${PROC_ORDER_CSV})."
    fi
fi

# Step f. copilot_document_sha_index — created by a concurrent migration.
# Use the optional runner so a missing table does not fail the reset.
SHA_DEL_COUNT="$(mysql_run "SELECT COUNT(*) FROM copilot_document_sha_index WHERE patient_id IN (${PID_CSV});" 2>/dev/null || echo 0)"
SHA_DEL_COUNT="${SHA_DEL_COUNT:-0}"
mysql_run_optional "DELETE FROM copilot_document_sha_index WHERE patient_id IN (${PID_CSV});"
log "Deleted ${SHA_DEL_COUNT} copilot_document_sha_index row(s) (table optional)."

# Step g/h. documents — list filesystem paths first, unlink, then delete rows.
DOC_PATHS="$(mysql_run "SELECT CONCAT_WS('/', url, name) FROM documents WHERE foreign_id IN (${PID_CSV}) AND url IS NOT NULL;" 2>/dev/null || true)"
if [[ -n "${DOC_PATHS}" ]]; then
    while IFS= read -r path; do
        [[ -z "${path}" ]] && continue
        # Documents.url may contain a "file://" prefix in some installs;
        # strip it for filesystem operations.
        fs_path="${path#file://}"
        if [[ -f "${fs_path}" ]]; then
            rm -f "${fs_path}" || log "WARN: could not unlink ${fs_path}"
            log "Unlinked ${fs_path}"
        fi
    done <<< "${DOC_PATHS}"
fi

DOC_COUNT="$(mysql_run "SELECT COUNT(*) FROM documents WHERE foreign_id IN (${PID_CSV});" 2>/dev/null || echo 0)"
DOC_COUNT="${DOC_COUNT:-0}"
TOTAL_DOCS=$((TOTAL_DOCS + DOC_COUNT))
mysql_run_optional "DELETE FROM documents WHERE foreign_id IN (${PID_CSV});"
log "Deleted ${DOC_COUNT} documents row(s)."

# Step i. uuid_registry + patient_data. uuid_registry first so we don't orphan
# its row; patient_data last so the IN-clause stays resolvable above.
# Reconstruct the binary uuid IN-clause from patient_data right now (we
# couldn't reuse the earlier UUID_HASH_IN_CLAUSE because that's the SHA-256
# of the uuid string, not the binary uuid).
UUIDS_HEX_FOR_REGISTRY="$(mysql_run "SELECT HEX(uuid) FROM patient_data WHERE pid IN (${PID_CSV}) AND uuid IS NOT NULL;" || true)"
if [[ -n "${UUIDS_HEX_FOR_REGISTRY}" ]]; then
    parts=()
    while IFS= read -r u; do
        [[ -z "${u}" ]] && continue
        parts+=("UNHEX('${u}')")
    done <<< "${UUIDS_HEX_FOR_REGISTRY}"
    if (( ${#parts[@]} > 0 )); then
        REGISTRY_IN_CLAUSE="$(IFS=,; echo "${parts[*]}")"
        mysql_run_optional "DELETE FROM uuid_registry WHERE table_name = 'patient_data' AND uuid IN (${REGISTRY_IN_CLAUSE});"
    fi
fi
mysql_run "DELETE FROM patient_data WHERE pid IN (${PID_CSV});"
log "Deleted ${N_PATIENTS} patient_data row(s)."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
SUMMARY="Reset ${N_PATIENTS} demo patients, ${TOTAL_FACTS} facts, ${TOTAL_RESULTS} lab results, ${TOTAL_DOCS} documents"
log "${SUMMARY}"
log "=== reset_demo_state.sh end (success) ==="
echo "${SUMMARY}"
