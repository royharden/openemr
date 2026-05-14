#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2310,SC2312
# Reset Wk2 document-upload demo state and re-seed the four fixture patients.
#
# Default target: docker/development-easy, database openemr/openemr@mysql.
# Override with COPILOT_DEMO_DB_USER/PASS/NAME/HOST if needed.

set -euo pipefail

show_help() {
    cat <<'EOF'
Usage: scripts/reset_wk2_demo_baseline.sh [MODE] [--dry-run]

Runs the existing Wk2 reset script inside the OpenEMR Docker container, then
re-seeds the four Wk2 demo patients (Chen, Whitaker, Reyes, Kowalski) unless
a mode flag suppresses re-seed.

Modes (mutually exclusive — pick at most one):
  --full-reseed  Default. Wipe all matched Wk2 demo patients (seeded +
                 intake-created) plus all derived artifacts, then re-seed
                 the four canonical fixture patients. Same as bare
                 invocation. Use when you want a known-good baseline.
  --reset-only   Wipe everything but do NOT re-seed. Post-state: zero Wk2
                 demo patients in the DB. Use to force the intake-create
                 demo path — the next chart must be created from an
                 intake upload. (Plan_wk2_Claude_Next07 §A.2.)
  --uploads-only Preserve the four seed patients (pids 9101-9104) and
                 their uuids; clear only their uploads + facts + lab
                 chain + intake-created patients. Use for chart-side
                 take re-records against the same Anne Chen.

Modifiers:
  --dry-run      Preview only — print every DELETE / rm that would
                 execute, but run none. Composes with any of the three
                 modes above. Exit code 0.
  -h, --help     Show this help.

Environment overrides:
  COPILOT_DEMO_DB_USER   default: openemr
  COPILOT_DEMO_DB_PASS   default: openemr
  COPILOT_DEMO_DB_NAME   default: openemr
  COPILOT_DEMO_DB_HOST   default: mysql
EOF
}

reset_only=0
uploads_only=0
dry_run=0
for arg in "$@"; do
    case "${arg}" in
        --reset-only)
            reset_only=1
            ;;
        --uploads-only)
            uploads_only=1
            ;;
        --full-reseed)
            # Explicit alias for today's default. No-op flag; here for
            # operator clarity in scripts and runbook copy-paste.
            ;;
        --dry-run)
            dry_run=1
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: ${arg}" >&2
            show_help >&2
            exit 2
            ;;
    esac
done

# Plan_wk2_Claude_Next07_v2 §A.1 — mutual exclusion. --reset-only and
# --uploads-only describe contradictory post-states (zero patients vs. four
# seeds preserved); refusing the combination protects the operator from a
# silent fallback to one of them.
if [[ "${reset_only}" == "1" && "${uploads_only}" == "1" ]]; then
    echo "ERROR: --reset-only and --uploads-only are mutually exclusive." >&2
    show_help >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

compose_file="docker/development-easy/docker-compose.yml"
override_file="docker/development-easy/docker-compose.override.yml"
# Plan_wk2_Claude_Next07_v2 §A.2 lesson: passing only -f base.yml suppresses
# docker compose's default auto-load of docker-compose.override.yml, which
# carries the AgDR-0066 COPILOT_DEMO_MODE + COPILOT_API_BASE_URL env vars
# that the openemr container needs to come back healthy after a recreate.
# Layer the override explicitly when present so recreates preserve env.
compose=(docker compose -f "${compose_file}")
if [[ -f "${override_file}" ]]; then
    compose=(docker compose -f "${compose_file}" -f "${override_file}")
fi

export COPILOT_DEMO_RESET_OK=1
export COPILOT_DEMO_DB_USER="${COPILOT_DEMO_DB_USER:-openemr}"
export COPILOT_DEMO_DB_PASS="${COPILOT_DEMO_DB_PASS:-openemr}"
export COPILOT_DEMO_DB_NAME="${COPILOT_DEMO_DB_NAME:-openemr}"
export COPILOT_DEMO_DB_HOST="${COPILOT_DEMO_DB_HOST:-mysql}"
export COPILOT_DEMO_RESET_ONLY="${reset_only}"
# Plan_wk2_Claude_Next07_v2 §A.0/§A.1 — new env flags propagated through
# docker compose exec into the openemr container.
export COPILOT_DEMO_DRY_RUN="${dry_run}"
export COPILOT_DEMO_UPLOADS_ONLY="${uploads_only}"

exec_env=(
    -e COPILOT_DEMO_RESET_OK
    -e COPILOT_DEMO_DB_USER
    -e COPILOT_DEMO_DB_PASS
    -e COPILOT_DEMO_DB_NAME
    -e COPILOT_DEMO_DB_HOST
    -e COPILOT_DEMO_RESET_ONLY
    -e COPILOT_DEMO_DRY_RUN
    -e COPILOT_DEMO_UPLOADS_ONLY
)
if [[ -n "${COPILOT_DEMO_ALLOW_ROOT_ROOT:-}" ]]; then
    exec_env+=(-e COPILOT_DEMO_ALLOW_ROOT_ROOT)
fi

echo "Starting OpenEMR demo stack if needed..."
"${compose[@]}" up --detach --wait mysql openemr

echo "Resetting Wk2 demo upload state..."
MSYS_NO_PATHCONV=1 "${compose[@]}" exec -T "${exec_env[@]}" openemr bash -lc '
set -euo pipefail

if ! command -v mysql >/dev/null 2>&1; then
    if command -v mariadb >/dev/null 2>&1; then
        ln -sf "$(command -v mariadb)" /usr/local/bin/mysql 2>/dev/null || true
    fi
fi

if ! command -v mysql >/dev/null 2>&1; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "ERROR: mysql client not found and apt-get is unavailable in the openemr container." >&2
        exit 10
    fi
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y mariadb-client
fi

reset_script="/var/www/localhost/htdocs/openemr/agent/copilot-api/scripts/reset_demo_state.sh"
seed_sql="/var/www/localhost/htdocs/openemr/agent/copilot-api/scripts/seed_demo_patients.sql"

bash "${reset_script}"

# Plan_wk2_Claude_Next07_v2 sections A.1 and A.2 -- re-seed is skipped in
# three cases:
#   * --reset-only  (existing behavior kept verbatim)
#   * --uploads-only (seeds already survived the reset, nothing to do)
#   * --dry-run     (no DELETEs ran, so the post-run patient list print
#                    would lie about what changed; INSERT IGNORE itself
#                    would be safe but the message would mislead)
if [[ "${COPILOT_DEMO_RESET_ONLY}" != "1" \
        && "${COPILOT_DEMO_UPLOADS_ONLY}" != "1" \
        && "${COPILOT_DEMO_DRY_RUN}" != "1" ]]; then
    echo "Re-seeding Wk2 demo patients..."
    MYSQL_PWD="${COPILOT_DEMO_DB_PASS}" mysql \
        -h"${COPILOT_DEMO_DB_HOST}" \
        -u"${COPILOT_DEMO_DB_USER}" \
        "${COPILOT_DEMO_DB_NAME}" < "${seed_sql}"

    echo "Clean baseline patient list:"
    MYSQL_PWD="${COPILOT_DEMO_DB_PASS}" mysql \
        -h"${COPILOT_DEMO_DB_HOST}" \
        -u"${COPILOT_DEMO_DB_USER}" \
        -N -B "${COPILOT_DEMO_DB_NAME}" \
        -e "SELECT pubpid, fname, lname FROM patient_data WHERE pubpid LIKE '\''WK2-DEMO-%'\'' ORDER BY pubpid;"
elif [[ "${COPILOT_DEMO_DRY_RUN}" == "1" ]]; then
    echo "Dry-run mode complete; no DELETEs executed and no re-seed performed."
elif [[ "${COPILOT_DEMO_UPLOADS_ONLY}" == "1" ]]; then
    echo "Uploads-only mode complete; the four seed patients were preserved (no re-seed needed)."
else
    echo "Reset-only mode complete; demo patients were not re-seeded."
fi
'

echo "Wk2 demo baseline reset complete."
