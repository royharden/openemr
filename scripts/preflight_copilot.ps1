<#
.SYNOPSIS
    Clinical Co-Pilot pre-flight check -- verifies every service the
    Co-Pilot brief + document-upload paths depend on before you test.

.DESCRIPTION
    Plan_wk2_Claude_Next08 follow-up. Roy hit flaky behaviour during
    manual testing because the openemr container was still mid-boot
    (rsync -> chown -> Apache start can take 10-30 min on a Windows
    host) -- endpoints 404 or error until Apache binds, then "suddenly
    work". This script makes that state explicit so you never guess.

    Run it from PowerShell on the Windows side. Every check that needs
    the container runs via `docker exec` (no Git-Bash path-mangling).

    Exit code 0 = all hard checks passed (ready to test).
    Exit code 1 = at least one hard check failed (fix before reporting
                  behaviour). WARN-level findings do not fail the run.

.EXAMPLE
    .\scripts\preflight_copilot.ps1

.NOTES
    Dependency stack verified:
      1. mysql container          -- healthy
      2. openemr container        -- healthy (Apache finished booting)
      3. Apache                   -- answering /meta/health/readyz
      4. demo-mode env vars       -- COPILOT_DEMO_MODE + COPILOT_API_BASE_URL
      5. Python sidecar           -- uvicorn on 127.0.0.1:8000 (host process)
      6. sidecar <- container hop -- host.docker.internal:8000 reachable
      7. corpus.db                -- present (RAG source)
      8. live RAG retrieve        -- corpus + embedder + Voyage key all work
#>

[CmdletBinding()]
param(
    # Repo root. Defaults to two levels up from this script (scripts/ -> openemr/).
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    # Compose project container names. Override if your compose project name differs.
    [string]$OpenemrContainer = 'development-easy-openemr-1',
    [string]$MysqlContainer = 'development-easy-mysql-1',
    # Sidecar host:port.
    [string]$SidecarHost = '127.0.0.1',
    [int]$SidecarPort = 8000,
    # Gateway shared secret -- must match docker-compose.override.yml.
    [string]$GatewaySecret = 'local-dev-shared-secret'
)

$ErrorActionPreference = 'Continue'
Set-Location $RepoRoot

$OK = '[ OK ]'
$NO = '[FAIL]'
$WN = '[WARN]'
$hardFailures = 0

function Write-Check {
    param([string]$Tag, [string]$Message)
    switch ($Tag) {
        $OK { Write-Host "$Tag $Message" -ForegroundColor Green }
        $WN { Write-Host "$Tag $Message" -ForegroundColor Yellow }
        $NO { Write-Host "$Tag $Message" -ForegroundColor Red }
        default { Write-Host "$Tag $Message" }
    }
}

Write-Host ""
Write-Host "=== Clinical Co-Pilot pre-flight ===" -ForegroundColor Cyan
Write-Host "repo: $RepoRoot"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Docker daemon
# ---------------------------------------------------------------------------
docker info *> $null
if ($?) {
    Write-Check $OK 'Docker daemon running'
} else {
    Write-Check $NO 'Docker daemon NOT running -- start Docker Desktop'
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 2. mysql container healthy
# ---------------------------------------------------------------------------
$mysqlHealth = docker inspect --format '{{.State.Health.Status}}' $MysqlContainer 2>$null
if ($mysqlHealth -eq 'healthy') {
    Write-Check $OK 'mysql container healthy'
} elseif ($mysqlHealth) {
    Write-Check $NO "mysql container state=$mysqlHealth"
    $hardFailures++
} else {
    Write-Check $NO "mysql container '$MysqlContainer' not found -- run: docker compose ... up -d"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 3. openemr container healthy  (the one that caused the flaky test)
# ---------------------------------------------------------------------------
$openemrHealth = docker inspect --format '{{.State.Health.Status}}' $OpenemrContainer 2>$null
if ($openemrHealth -eq 'healthy') {
    Write-Check $OK 'openemr container healthy'
} elseif ($openemrHealth) {
    Write-Check $WN "openemr container state=$openemrHealth -- STILL BOOTING. The rsync -> chown -> Apache cycle takes 10-30 min on a Windows host. Wait and re-run this script."
} else {
    Write-Check $NO "openemr container '$OpenemrContainer' not found -- run: docker compose -f docker/development-easy/docker-compose.yml -f docker/development-easy/docker-compose.override.yml up -d"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 4. Apache actually answering inside the container
# ---------------------------------------------------------------------------
$readyz = docker exec $OpenemrContainer curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://localhost/meta/health/readyz 2>$null
if ($readyz -eq '200') {
    Write-Check $OK 'Apache responding (readyz 200)'
} else {
    Write-Check $NO "Apache not ready (readyz=$readyz) -- container still booting; wait and re-run"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 5. demo-mode env vars inside the container
# ---------------------------------------------------------------------------
$demoMode = docker exec $OpenemrContainer printenv COPILOT_DEMO_MODE 2>$null
$apiBase = docker exec $OpenemrContainer printenv COPILOT_API_BASE_URL 2>$null
if ($demoMode -eq '1') {
    Write-Check $OK 'COPILOT_DEMO_MODE=1 in container'
} else {
    Write-Check $NO "COPILOT_DEMO_MODE='$demoMode' -- override file not applied. Recreate: docker compose -f docker/development-easy/docker-compose.yml -f docker/development-easy/docker-compose.override.yml up -d"
    $hardFailures++
}
if ($apiBase) {
    Write-Check $OK "COPILOT_API_BASE_URL=$apiBase"
} else {
    Write-Check $NO 'COPILOT_API_BASE_URL unset in container -- PHP gateway has no sidecar URL'
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 6. Python sidecar /healthz from the host
# ---------------------------------------------------------------------------
$sidecarBase = "http://${SidecarHost}:${SidecarPort}"
try {
    $health = Invoke-RestMethod -Uri "$sidecarBase/healthz" -TimeoutSec 5
    if ($health.status -eq 'ok') {
        Write-Check $OK "Sidecar /healthz = ok ($sidecarBase)"
    } else {
        Write-Check $WN "Sidecar /healthz = $($health.status) -- startup self-test may still be running; re-run in ~30s"
    }
} catch {
    Write-Check $NO "Sidecar NOT reachable on $sidecarBase -- start it in its own terminal: cd agent/copilot-api ; python -m uvicorn app.main:app --host $SidecarHost --port $SidecarPort"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 7. Sidecar reachable from INSIDE the openemr container (the gateway hop)
# ---------------------------------------------------------------------------
$sidecarFromContainer = docker exec $OpenemrContainer curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://host.docker.internal:8000/healthz 2>$null
if ($sidecarFromContainer -eq '200') {
    Write-Check $OK 'Sidecar reachable from openemr container (host.docker.internal:8000)'
} else {
    Write-Check $NO "Sidecar NOT reachable from container (http=$sidecarFromContainer) -- the PHP gateway cannot call the sidecar; brief + extraction will fail"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 8. corpus.db present (RAG source)
# ---------------------------------------------------------------------------
$corpusPath = Join-Path $RepoRoot 'agent/copilot-api/corpus.db'
if (Test-Path $corpusPath) {
    $corpusKb = [math]::Round((Get-Item $corpusPath).Length / 1KB)
    Write-Check $OK "corpus.db present ($corpusKb KB)"
} else {
    Write-Check $NO "corpus.db missing at $corpusPath -- RAG retrieval returns nothing; briefs will have no guideline citations"
    $hardFailures++
}

# ---------------------------------------------------------------------------
# 9. Live RAG retrieve smoke -- proves corpus + embedder + Voyage key all work
# ---------------------------------------------------------------------------
try {
    $body = @{ query = 'lisinopril blood pressure'; top_k = 3 } | ConvertTo-Json
    $headers = @{ 'x-copilot-gateway-secret' = $GatewaySecret }
    $retrieve = Invoke-RestMethod -Uri "$sidecarBase/v1/rag/retrieve" -Method Post -Body $body -ContentType 'application/json' -Headers $headers -TimeoutSec 20
    if ($retrieve.chunks.Count -gt 0) {
        Write-Check $OK "RAG retrieve OK ($($retrieve.chunks.Count) chunks -- corpus + embedder + Voyage key all work)"
    } else {
        Write-Check $WN 'RAG retrieve returned 0 chunks -- corpus may be empty or embedder degraded'
    }
} catch {
    Write-Check $WN "RAG retrieve smoke failed: $($_.Exception.Message) -- retrieval degraded (briefs will run but without guideline citations)"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
if ($hardFailures -eq 0) {
    Write-Host "All hard checks passed -- Co-Pilot + upload paths are ready to test." -ForegroundColor Green
    Write-Host "(A [WARN] on the RAG smoke is tolerable -- retrieval is degraded, not dead.)" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
} else {
    Write-Host "$hardFailures hard check(s) FAILED -- fix these before reporting behaviour." -ForegroundColor Red
    Write-Host "Most common cause: the openemr container is still mid-boot. Wait 10-30 min, re-run." -ForegroundColor DarkGray
    Write-Host ""
    exit 1
}
