#!/usr/bin/env pwsh
# start-qa-replay.ps1 - Boot the parkos QA replay stack.
#
# SYNOPSIS: Bring up parkos-api-sucursal container (Sep 17 image) + Vite
# renderer with bounded timeouts + linear backoff retries per AGENTS.md
# Operational Timeouts section. Exits non-zero on any unrecoverable step;
# never blocks the operator on a hung HTTP call.
#
# USAGE: powershell.exe -ExecutionPolicy Bypass -NoProfile -File start-qa-replay.ps1
#   Optional flags: -MaxRetries 5, -ApiPort 8100, -OperadorEmail 'qa@parkos.local'

[CmdletBinding()]
param(
    [int]$VitePort = 5173,
    [int]$ApiPort = 8100,
    [int]$ApiHealthTimeoutSec = 30,
    [int]$ViteReadyTimeoutSec = 30,
    [int]$MaxRetries = 3,
    [int]$RetryDelaySec = 2,
    [string]$OperadorEmail = 'operador@parkos.local',
    [string]$OperadorPassword = 'Pass1234word',
    [string]$ApiImage = 'parkos:api-sucursal-test',
    [string]$ApiNetwork = 'parkos-cloud_parkos-cloud-net',
    [string]$BranchDbContainer = 'parkos-branch-db',
    [string]$BranchUuid = '360357ea-3564-4843-a680-7e821dd26383',
    [string]$SecretsDir = 'E:\easypunto_parkos\infra\deploy\secrets',
    [string]$ApiContainerName = 'parkos-api-sucursal-run'
)

$ErrorActionPreference = 'Continue'
$prefix = '[start-qa-replay ' + (Get-Date -Format 'HH:mm:ss') + ']'

# Pretty logging helpers
function Step($m) { Write-Host ($prefix + ' [STEP] ' + $m) -ForegroundColor Cyan }
function Ok($m)   { Write-Host ($prefix + ' [OK]   ' + $m) -ForegroundColor Green }
function Warn($m) { Write-Host ($prefix + ' [WARN] ' + $m) -ForegroundColor Yellow }
function Err($m)  { Write-Host ($prefix + ' [ERR]  ' + $m) -ForegroundColor Red }

# Retry helper (linear backoff)
function Invoke-WithRetry {
    param(
        [ScriptBlock]$Action,
        [string]$Description,
        [int]$Attempts = $MaxRetries,
        [int]$Delay = $RetryDelaySec
    )
    $i = 0
    $lastErr = ''
    while ($i -lt $Attempts) {
        $i++
        try {
            $r = & $Action
            if ($r) { return $r }
        } catch {
            $lastErr = $_.Exception.Message
            Warn ($Description + ' attempt ' + $i + '/' + $Attempts + ' failed: ' + $lastErr)
        }
        if ($i -lt $Attempts) { Start-Sleep -Seconds $Delay }
    }
    throw ($Description + ' failed after ' + $Attempts + ' attempts. Last error: ' + $lastErr)
}

# ── Pre-flight ────────────────────────────────────────────────────
Step 'Pre-flight checks'

try {
    $dockerVersion = Invoke-WithRetry -Description 'docker version' `
        -Action { docker version --format '{{.Server.Version}}' 2>$null }
    Ok ('Docker daemon reachable (server ' + $dockerVersion + ')')
} catch {
    Err 'Docker daemon unreachable. Start Docker Desktop and retry.'
    exit 1
}

# ── Backend ────────────────────────────────────────────────────────
Step ('Backend (api-sucursal on :' + $ApiPort + ')')

# Idempotent: prune any leftover standalone container from a previous QA replay
$existing = docker ps -a --filter ('name=' + $ApiContainerName) --format '{{.Names}}' 2>$null
if ($existing -eq $ApiContainerName) {
    Step ('Removing leftover ' + $ApiContainerName)
    docker stop $ApiContainerName 2>$null | Out-Null
    docker rm $ApiContainerName 2>$null | Out-Null
}

# If port is already bound by something (e.g. the canonical Sep 16 image),
# use it and don't fight. Otherwise bring up the standalone Sep 17 container.
$portBound = Test-NetConnection -ComputerName 127.0.0.1 -Port $ApiPort `
    -InformationLevel Quiet -WarningAction SilentlyContinue

if (-not $portBound) {
    Step ('Starting ' + $ApiContainerName + ' (image=' + $ApiImage + ', network=' + $ApiNetwork + ')')
    $dbUrl = ('postgresql+psycopg://parkos:parkos@' + $BranchDbContainer + ':5432/parkos')
    $containerId = docker run -d `
        --name $ApiContainerName `
        --network $ApiNetwork `
        -p (($ApiPort.ToString()) + ':8000') `
        -e PARKOS_DEPLOY=branch `
        -e PARKOS_SYNC_ENGINE=catalog_branch `
        -e PARKOS_SUCURSAL_UUID=$BranchUuid `
        -e DATABASE_URL=$dbUrl `
        -e 'PARKOS_CLOUD_API_URL=http://api-admin:8000' `
        -e PARKOS_JWT_KEY_PATH=/var/run/parkos/jwt_private.pem `
        -e PARKOS_SYNC_JWT_PATH=/var/run/parkos/sync.jwt `
        -v (($SecretsDir + ':/var/run/parkos:ro')) `
        $ApiImage `
        python -m uvicorn parkos_core.api.app_factory:create_app --factory --host 0.0.0.0 --port 8000 `
        2>$null
    if ($LASTEXITCODE -ne 0) {
        Err ('docker run failed (exit ' + $LASTEXITCODE + ')')
        exit 2
    }
    Ok ('Container started (' + $containerId + ')')
    # uvicorn takes 8-30s to bind inside the container; wait before first probe.
    Start-Sleep -Seconds 5
} else {
    Ok ('Port :' + $ApiPort + ' already bound -- using existing api-sucursal')
}

# Health probe with retries
Step ('Probing /health on :' + $ApiPort)
$healthOk = $false
$healthAttempt = 0
while (($healthAttempt -lt $MaxRetries) -and (-not $healthOk)) {
    $healthAttempt++
    $statusGot = ''
    $errMsg = ''
    try {
        $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $ApiPort + '/health') `
            -TimeoutSec $ApiHealthTimeoutSec -UseBasicParsing -ErrorAction Stop
        $statusGot = $r.StatusCode
        if ($r.StatusCode -eq 200) {
            Ok ('/health 200 OK -- ' + $r.Content)
            $healthOk = $true
            break
        }
    } catch {
        $errMsg = $_.Exception.Message
    }
    if (-not $healthOk) {
        if ($statusGot -ne '') {
            Warn ('Health attempt ' + $healthAttempt + '/' + $MaxRetries + ': status=' + $statusGot)
        } else {
            Warn ('Health attempt ' + $healthAttempt + '/' + $MaxRetries + ': ' + $errMsg)
        }
        if ($healthAttempt -lt $MaxRetries) { Start-Sleep -Seconds $RetryDelaySec }
    }
}
if (-not $healthOk) {
    $totalWaitSec = [int]$ApiHealthTimeoutSec * [int]$MaxRetries
    $msg = 'api-sucursal /health failed after ' + $MaxRetries + ' attempts (' + $totalWaitSec + 's total wait).'
    Err $msg
    exit 2
}

# ── Vite renderer ────────────────────────────────────────────────
Step ('Vite renderer on :' + $VitePort)

# Free the port if stale process owns it
Get-NetTCPConnection -LocalPort $VitePort -State Listen -ErrorAction SilentlyContinue `
    | ForEach-Object {
        Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue `
            | Stop-Process -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Seconds 2

$outLog = ($env:TEMP + '\vite-qa-replay.out')
$errLog = ($env:TEMP + '\vite-qa-replay.err')
# Push-Location changes the WORKING directory so Start-Process resolves
# the relative vite.cmd path. popd restores the caller CWD afterwards.
Push-Location -LiteralPath 'E:\easypunto_parkos\apps\electron-sucursal'
try {
    $proc = Start-Process -FilePath 'node_modules\.bin\vite.cmd' `
        -ArgumentList '--port', $VitePort, '--host', '127.0.0.1', '--force' `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden -PassThru
} finally {
    Pop-Location
}
Ok ('Vite started (PID ' + $proc.Id + '); stdout=' + $outLog + ' stderr=' + $errLog)

# Wait for Vite to be ready
Step ('Probing :' + $VitePort)
$viteOk = $false
$viteAttempt = 0
while (($viteAttempt -lt $MaxRetries) -and (-not $viteOk)) {
    $viteAttempt++
    Start-Sleep -Seconds 2
    $statusGot = ''
    $errMsg = ''
    try {
        $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $VitePort) `
            -TimeoutSec $ViteReadyTimeoutSec -UseBasicParsing -ErrorAction Stop
        $statusGot = $r.StatusCode
        if (($r.StatusCode -eq 200) -or ($r.StatusCode -eq 304)) {
            Ok ('Vite responding on :' + $VitePort)
            $viteOk = $true
            break
        }
    } catch {
        $errMsg = $_.Exception.Message
    }
    if (-not $viteOk) {
        if ($statusGot -ne '') {
            Warn ('Vite attempt ' + $viteAttempt + '/' + $MaxRetries + ': status=' + $statusGot)
        } else {
            Warn ('Vite attempt ' + $viteAttempt + '/' + $MaxRetries + ': ' + $errMsg)
        }
    }
}
if (-not $viteOk) {
    Err ('Vite never became ready after ' + $MaxRetries + ' attempts. See ' + $errLog)
    exit 3
}

# ── Smoke: login ──────────────────────────────────────────────────
Step ('Smoke login as ' + $OperadorEmail)
$token = $null
try {
    $loginBody = ('{"email":"' + $OperadorEmail + '","password":"' + $OperadorPassword + '"}')
    $r = Invoke-WebRequest -Method POST -Uri ('http://127.0.0.1:' + $ApiPort + '/api/v1/auth/login') `
        -Headers @{ 'Content-Type' = 'application/json' } `
        -Body $loginBody `
        -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) {
        $token = ($r.Content | ConvertFrom-Json).access_token
        Ok ('Login 200 OK (token len ' + $token.Length + ')')
    } else {
        Warn ('Login returned ' + $r.StatusCode)
    }
} catch {
    Warn ('Login failed: ' + $_.Exception.Message)
}

# ── Output ────────────────────────────────────────────────────────
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  PARKOS QA REPLAY STACK READY' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host ('  Vite renderer:        http://127.0.0.1:' + $VitePort)
Write-Host ('  api-sucursal:         http://127.0.0.1:' + $ApiPort)
Write-Host ('  Operador login:       ' + $OperadorEmail + ' / ' + $OperadorPassword)
if ($token) {
    Write-Host ('  Smoke token preview: ' + $token.Substring(0, 16) + '...')
}
Write-Host ''
Write-Host 'Next step (chrome-devtools MCP):'
Write-Host ('  navigate_page pageId=1 url="http://127.0.0.1:' + $VitePort + '" timeout=30000')
Write-Host ''
Write-Host 'Logs:'
Write-Host ('  Vite stdout:  ' + $outLog)
Write-Host ('  Vite stderr:  ' + $errLog)
Write-Host ''
Ok 'Done.'
