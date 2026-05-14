[CmdletBinding()]
param(
    [switch]$ResetOnly,
    # Plan_wk2_Claude_Next07_v2 §A.0/§A.1 — three new mode switches.
    # `FullReseed` is the explicit alias for today's default (bare
    # invocation) and is a no-op at the param level; it exists so operators
    # can write `.\reset_wk2_demo_baseline.ps1 -FullReseed` for clarity in
    # runbook copy-paste.
    [switch]$UploadsOnly,
    [switch]$DryRun,
    [switch]$FullReseed
)

$ErrorActionPreference = 'Stop'

# Mutual exclusion (Plan §A.1). `-ResetOnly` zeroes the patient list;
# `-UploadsOnly` keeps the four seeds; the combination is contradictory.
if ($ResetOnly -and $UploadsOnly) {
    Write-Error '-ResetOnly and -UploadsOnly are mutually exclusive.'
    exit 2
}

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Set-EnvDefault {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, 'Process'))) {
        [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
    }
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$composeFile = 'docker/development-easy/docker-compose.yml'
$overrideFile = 'docker/development-easy/docker-compose.override.yml'
# Plan_wk2_Claude_Next07_v2 §A.2 lesson (bash mirror): passing only -f base.yml
# suppresses docker compose's default auto-load of the override file, which
# carries the AgDR-0066 COPILOT_DEMO_MODE + COPILOT_API_BASE_URL env vars the
# openemr container needs to come back healthy after a recreate. Layer the
# override explicitly when it exists.
$compose = @('compose', '-f', $composeFile)
if (Test-Path $overrideFile) {
    $compose = @('compose', '-f', $composeFile, '-f', $overrideFile)
}

$savedEnv = @{}
foreach ($name in @(
    'COPILOT_DEMO_RESET_OK',
    'COPILOT_DEMO_DB_USER',
    'COPILOT_DEMO_DB_PASS',
    'COPILOT_DEMO_DB_NAME',
    'COPILOT_DEMO_DB_HOST',
    'COPILOT_DEMO_RESET_ONLY',
    'COPILOT_DEMO_DRY_RUN',
    'COPILOT_DEMO_UPLOADS_ONLY'
)) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

Push-Location $repoRoot
try {
    Set-EnvDefault -Name 'COPILOT_DEMO_DB_USER' -Value 'openemr'
    Set-EnvDefault -Name 'COPILOT_DEMO_DB_PASS' -Value 'openemr'
    Set-EnvDefault -Name 'COPILOT_DEMO_DB_NAME' -Value 'openemr'
    Set-EnvDefault -Name 'COPILOT_DEMO_DB_HOST' -Value 'mysql'
    [Environment]::SetEnvironmentVariable('COPILOT_DEMO_RESET_OK', '1', 'Process')
    [Environment]::SetEnvironmentVariable(
        'COPILOT_DEMO_RESET_ONLY',
        ($(if ($ResetOnly) { '1' } else { '0' })),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'COPILOT_DEMO_DRY_RUN',
        ($(if ($DryRun) { '1' } else { '0' })),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'COPILOT_DEMO_UPLOADS_ONLY',
        ($(if ($UploadsOnly) { '1' } else { '0' })),
        'Process'
    )
    # `-FullReseed` is intentionally a no-op alias — bare invocation maps
    # to full-reseed; the switch exists for operator clarity in runbook
    # copy-paste. Suppress the unused-variable warning rather than emit a
    # dummy assignment that would mask real lints later.
    $null = $FullReseed

    Write-Host 'Starting OpenEMR demo stack if needed...'
    Invoke-Docker -Arguments ($compose + @('up', '--detach', '--wait', 'mysql', 'openemr'))

    $containerScript = @'
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

# Plan_wk2_Claude_Next07_v2 sections A.1 and A.2 -- re-seed is skipped for
# --reset-only, --uploads-only, and --dry-run (see the bash wrapper for
# detail; this here-string mirrors that logic).
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
        -e "SELECT pubpid, fname, lname FROM patient_data WHERE pubpid LIKE 'WK2-DEMO-%' ORDER BY pubpid;"
elif [[ "${COPILOT_DEMO_DRY_RUN}" == "1" ]]; then
    echo "Dry-run mode complete; no DELETEs executed and no re-seed performed."
elif [[ "${COPILOT_DEMO_UPLOADS_ONLY}" == "1" ]]; then
    echo "Uploads-only mode complete; the four seed patients were preserved (no re-seed needed)."
else
    echo "Reset-only mode complete; demo patients were not re-seeded."
fi
'@

    Write-Host 'Resetting Wk2 demo upload state...'
    $execArgs = $compose + @(
        'exec', '-T',
        '-e', 'COPILOT_DEMO_RESET_OK',
        '-e', 'COPILOT_DEMO_DB_USER',
        '-e', 'COPILOT_DEMO_DB_PASS',
        '-e', 'COPILOT_DEMO_DB_NAME',
        '-e', 'COPILOT_DEMO_DB_HOST',
        '-e', 'COPILOT_DEMO_RESET_ONLY',
        '-e', 'COPILOT_DEMO_DRY_RUN',
        '-e', 'COPILOT_DEMO_UPLOADS_ONLY'
    )

    if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('COPILOT_DEMO_ALLOW_ROOT_ROOT', 'Process'))) {
        $execArgs += @('-e', 'COPILOT_DEMO_ALLOW_ROOT_ROOT')
    }

    $execArgs += @('openemr', 'bash', '-lc', $containerScript)
    Invoke-Docker -Arguments $execArgs

    Write-Host 'Wk2 demo baseline reset complete.'
}
finally {
    foreach ($entry in $savedEnv.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
    Pop-Location
}
