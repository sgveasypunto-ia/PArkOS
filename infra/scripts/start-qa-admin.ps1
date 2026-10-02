#!/usr/bin/env pwsh
# start-qa-admin.ps1 - Bring up the Parkos cloud + branch Docker stack and the
# web_admin Vite dev server for end-to-end QA of the admin panel.
#
# SYNOPSIS: idempotent "Fase 0" bootstrap. Safe to re-run: docker compose is
# itself idempotent (only rebuilds/recreates what changed), the partition
# fixup is a no-op once applied, bootstrap_pairing.py is skipped once
# sync.jwt already exists, and the Vite server is reused if the port is
# already listening.
#
# USAGE: powershell.exe -ExecutionPolicy Bypass -NoProfile -File start-qa-admin.ps1
#   Optional: -FreshVolumes to wipe cloud-db/branch-db and start from an empty DB
#             -DianProviderUrl 'https://...' to override the dev mock
#             -BranchUuid '<uuid>' to target a different branch fixture
#
# WHY THIS SCRIPT EXISTS (context for future maintainers)
# --------------------------------------------------------------------------
# Running `docker compose ... up -d --build` + `alembic upgrade head` +
# `bootstrap_pairing.py` + the seed scripts BY HAND, in order, on a database
# that is either brand-new or was partially migrated weeks ago, hits three
# real bugs that are not this script's to fix (they live in the migration
# chain and in bootstrap_pairing.py itself, both out of scope for a Fase 0
# environment-bootstrap task):
#
#   1. Migration 0064_ensure_forward_partitions.py creates partitions named
#      "<table>_p_<YYYY_MM>" / "<table>_default", but migration 0001 (and
#      0018 for pairing_tokens/revoked_sync_jwts) already created a same-
#      month partition under the LEGACY name "<table>_p_current" /
#      "<table>_p_default". Running the FULL chain (0001..head) in one
#      sitting -- the normal shape of a fresh install -- makes 0064 try to
#      create a second partition covering the exact same range, which
#      Postgres rejects ("would overlap" / "conflicts with existing default
#      partition"). 0064's own docstring documents this as a known gap
#      (ADR-004 follow-up). Fix applied here: rename the legacy partition to
#      the canonical name 0064 expects, which is a no-op once a partition
#      with that canonical name already exists.
#   2. 0064 creates 291 new child partitions across 10 parent tables but
#      never re-GRANTs the least-privilege `rol_app` role on them. Postgres
#      enforces ACLs per-partition for row access even though the app only
#      ever queries the parent, so every one of those 291 partitions comes
#      up with zero privileges for `rol_app` / `parkos_app` until someone
#      mirrors the parent's grants onto them. Fix applied here: copy every
#      non-owner grant from each partitioned parent onto all of its current
#      child partitions (idempotent -- re-granting an already-granted
#      privilege is a no-op in Postgres).
#   3. `rol_app` is only granted SELECT+INSERT on `prod.pairing_tokens`
#      (migration 0021), but `/api/v1/sync/pair` does
#      `SELECT ... FOR UPDATE SKIP LOCKED` to consume a pairing token, and
#      Postgres requires UPDATE privilege (not just SELECT) to take a row
#      lock with FOR UPDATE. Fix applied here: explicit GRANT UPDATE.
#   4. bootstrap_pairing.py's ensure_admin_user() scopes the admin to every
#      row currently in prod.sucursal -- but it runs BEFORE
#      ensure_sucursal() creates the branch row, so on a truly empty DB the
#      admin gets scoped to zero branches and step 3 (POST
#      /admin/pairing-tokens) 403s with unauthorized_sucursal_context. A
#      second pass succeeds because by then the branch row exists. This
#      script runs bootstrap_pairing.py up to twice for that reason, and
#      only on the FIRST ever run (sync.jwt existing is the "already
#      bootstrapped" signal -- bootstrap_pairing.py's own genesis-hash-chain
#      step is NOT safe to run a third time: it hard-RAISEs on a second
#      genesis row for the same branch instead of silently skipping it).
#
# All of the above are applied as DATA-PLANE fixes (renames + grants) on the
# already-migrated schema; this script does not edit migration files or
# application code.

[CmdletBinding()]
param(
    [int]$VitePort = 5173,
    [string]$DianProviderUrl = '',
    # Fixture BRANCH_NORTE uuid used by apps/web_admin's own e2e tests
    # (kept in sync with that suite on purpose, so QA data lines up with
    # what the e2e specs expect to find).
    [string]$BranchUuid = '22222222-2222-2222-2222-222222222222',
    [int]$MaxRetries = 3,
    [int]$RetryDelaySec = 3,
    [int]$HealthTimeoutSec = 90,
    [switch]$FreshVolumes,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'
$prefix = '[start-qa-admin ' + (Get-Date -Format 'HH:mm:ss') + ']'

function Step($m) { Write-Host ($prefix + ' [STEP] ' + $m) -ForegroundColor Cyan }
function Ok($m)   { Write-Host ($prefix + ' [OK]   ' + $m) -ForegroundColor Green }
function Warn($m) { Write-Host ($prefix + ' [WARN] ' + $m) -ForegroundColor Yellow }
function Err($m)  { Write-Host ($prefix + ' [ERR]  ' + $m) -ForegroundColor Red }

# dev-only mock: infra/deploy/docker-compose.cloud.yml requires
# PARKOS_DIAN_PROVIDER_URL with no default (the compose interpolation aborts
# without it) and there is no real DIAN/Factus sandbox wired for local QA.
# ".example" is a reserved TLD (RFC 2606) precisely so this can never resolve
# to a live endpoint by accident.
$DefaultDianMock = 'https://api.factus.example/v1'

$CloudCompose = Join-Path $RepoRoot 'infra\deploy\docker-compose.cloud.yml'
$LocalCompose = Join-Path $RepoRoot 'infra\deploy\docker-compose.local.yml'
$EnvLocalPath = Join-Path $RepoRoot 'infra\deploy\.env.local'
$SecretsDir   = Join-Path $RepoRoot 'infra\deploy\secrets'
$SyncJwtPath  = Join-Path $SecretsDir 'sync.jwt'
$JwtKeyPath   = Join-Path $SecretsDir 'jwt_private.pem'
$BackendDir   = Join-Path $RepoRoot 'backend'
$AppsDir      = Join-Path $RepoRoot 'apps'

# The combined, idempotent data-plane fixup described above (gotchas #1-#3).
# Single-quoted here-string: no PowerShell interpolation, so the plpgsql
# `$do$ ... $do$` dollar-quoting and `||` concatenation pass through as-is.
$FixupSql = @'
DO $do$
DECLARE
  ym  text := to_char(CURRENT_DATE, 'YYYY_MM');
  ymd text := to_char(CURRENT_DATE, 'YYYY_MM_DD');
  tbl text;
  rec RECORD;
  priv RECORD;
  n_renames int := 0;
  n_grants int := 0;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['arqueo','caja','factura_detalle','factura_pagos',
                              'log_transaccional','salidas','sync_log','sync_queue']
  LOOP
    IF to_regclass('prod.' || tbl || '_p_current') IS NOT NULL
       AND to_regclass('prod.' || tbl || '_p_' || ym) IS NULL THEN
      EXECUTE format('ALTER TABLE prod.%I RENAME TO %I', tbl || '_p_current', tbl || '_p_' || ym);
      n_renames := n_renames + 1;
    END IF;
  END LOOP;

  IF to_regclass('prod.sync_queue_lw_buffer_p_current') IS NOT NULL
     AND to_regclass('prod.sync_queue_lw_buffer_p_' || ymd) IS NULL THEN
    EXECUTE format('ALTER TABLE prod.sync_queue_lw_buffer_p_current RENAME TO %I', 'sync_queue_lw_buffer_p_' || ymd);
    n_renames := n_renames + 1;
  END IF;

  FOREACH tbl IN ARRAY ARRAY['pairing_tokens','revoked_sync_jwts']
  LOOP
    IF to_regclass('prod.' || tbl || '_p_default') IS NOT NULL
       AND to_regclass('prod.' || tbl || '_default') IS NULL THEN
      EXECUTE format('ALTER TABLE prod.%I RENAME TO %I', tbl || '_p_default', tbl || '_default');
      n_renames := n_renames + 1;
    END IF;
  END LOOP;

  FOR rec IN
    SELECT DISTINCT c.oid AS child_oid, c.relname AS child, p.oid AS parent_oid
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    JOIN pg_class p ON p.oid = i.inhparent
    JOIN pg_namespace n ON n.oid = p.relnamespace
    WHERE n.nspname = 'prod' AND c.relkind = 'r'
  LOOP
    FOR priv IN
      SELECT (aclexplode(pc.relacl)).grantee::regrole::text AS grantee,
             (aclexplode(pc.relacl)).privilege_type AS privilege_type
      FROM pg_class pc WHERE pc.oid = rec.parent_oid
    LOOP
      IF priv.grantee <> 'parkos' THEN
        EXECUTE format('GRANT %s ON prod.%I TO %I', priv.privilege_type, rec.child, priv.grantee);
        n_grants := n_grants + 1;
      END IF;
    END LOOP;
  END LOOP;

  IF to_regclass('prod.pairing_tokens') IS NOT NULL THEN
    EXECUTE 'GRANT UPDATE ON prod.pairing_tokens TO rol_app';
    FOR rec IN
      SELECT c.relname AS child
      FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
      JOIN pg_class p ON p.oid = i.inhparent
      JOIN pg_namespace n ON n.oid = p.relnamespace
      WHERE n.nspname = 'prod' AND p.relname = 'pairing_tokens'
    LOOP
      EXECUTE format('GRANT UPDATE ON prod.%I TO rol_app', rec.child);
    END LOOP;
  END IF;

  RAISE NOTICE 'partition fixup: % rename(s), % grant(s) applied', n_renames, n_grants;
END
$do$;
'@

function Invoke-WithRetry {
    param([ScriptBlock]$Action, [string]$Description, [int]$Attempts = $MaxRetries, [int]$Delay = $RetryDelaySec)
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

function Wait-ContainerHealthy {
    param([string]$ContainerName, [int]$TimeoutSec = $HealthTimeoutSec)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        $status = docker inspect --format '{{.State.Health.Status}}' $ContainerName 2>$null
        if ($status -eq 'healthy') { return $true }
        Start-Sleep -Seconds 3
        $elapsed += 3
    }
    return $false
}

function Invoke-PartitionFixup {
    param([string[]]$ComposeArgs, [string]$DbService)
    $script:FixupSql | & docker compose @ComposeArgs exec -T $DbService psql -U parkos -d parkos 2>&1 | ForEach-Object { Write-Host ('    ' + $_) }
}

function Invoke-AlembicUpgrade {
    param([string[]]$ComposeArgs, [string]$ApiService, [string]$DbService)
    $dsn = 'postgresql+psycopg2://parkos:parkos@' + $DbService + ':5432/parkos'
    $attempt = 0
    while ($true) {
        $attempt++
        & docker compose @ComposeArgs exec -u parkos -e ('DATABASE_URL=' + $dsn) $ApiService bash -lc `
            'cd /app/backend/packages/parkos_core && /app/backend/.venv/bin/alembic upgrade head'
        $ec = $LASTEXITCODE
        if ($ec -eq 0) {
            Ok ('alembic upgrade head OK on ' + $DbService + ' (attempt ' + $attempt + ')')
            return
        }
        if ($attempt -ge $MaxRetries) {
            throw ('alembic upgrade head failed on ' + $DbService + ' after ' + $attempt + ' attempts.')
        }
        Warn ('alembic upgrade head failed on ' + $DbService + ' (attempt ' + $attempt + ') -- applying the known partition fixup (see header comment) and retrying...')
        Invoke-PartitionFixup -ComposeArgs $ComposeArgs -DbService $DbService
    }
}

function Invoke-BootstrapPairing {
    if (Test-Path $SyncJwtPath) {
        Ok ('sync.jwt already present at ' + $SyncJwtPath + ' -- skipping bootstrap_pairing.py (its genesis-hash-chain step hard-fails on a second run for the same branch; see header comment #4).')
        return
    }
    Push-Location $BackendDir
    try {
        for ($i = 1; $i -le 2; $i++) {
            & python (Join-Path $RepoRoot 'infra\scripts\bootstrap_pairing.py') `
                --branch-uuid $BranchUuid --jwt-key-path $JwtKeyPath
            if (Test-Path $SyncJwtPath) {
                Ok ('bootstrap_pairing.py completed on pass ' + $i + ' (sync.jwt persisted).')
                return
            }
            Warn ('bootstrap_pairing.py pass ' + $i + ' did not persist sync.jwt yet (expected on a brand-new DB -- see header comment #4). Retrying...')
        }
        throw 'bootstrap_pairing.py did not persist sync.jwt after 2 passes.'
    } finally {
        Pop-Location
    }
}

# ── Pre-flight ──────────────────────────────────────────────────────
Step 'Pre-flight checks'
try {
    $dockerVersion = Invoke-WithRetry -Description 'docker version' -Action { docker version --format '{{.Server.Version}}' 2>$null }
    Ok ('Docker daemon reachable (server ' + $dockerVersion + ')')
} catch {
    Err 'Docker daemon unreachable. Start Docker Desktop and retry.'
    exit 1
}
Step 'Existing parkos-* containers'
docker ps -a --filter 'name=parkos-' --format '  {{.Names}}: {{.Status}}' | ForEach-Object { Write-Host $_ }

# ── DIAN provider URL (mock) ─────────────────────────────────────────
if (-not $DianProviderUrl) {
    try {
        $envLines = docker inspect parkos-api-admin --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
        $found = $envLines | Select-String '^PARKOS_DIAN_PROVIDER_URL=' | Select-Object -First 1
        if ($found) { $DianProviderUrl = ($found.Line -split '=', 2)[1] }
    } catch {}
}
if (-not $DianProviderUrl) { $DianProviderUrl = $DefaultDianMock }
$env:PARKOS_DIAN_PROVIDER_URL = $DianProviderUrl
Ok ('PARKOS_DIAN_PROVIDER_URL = ' + $DianProviderUrl + $(if ($DianProviderUrl -eq $DefaultDianMock) { ' (dev mock, no real DIAN/Factus sandbox)' } else { ' (reused from existing container)' }))

# ── Optional clean slate ────────────────────────────────────────────
if ($FreshVolumes) {
    Step 'FreshVolumes requested: tearing down existing stacks + volumes'
    if (Test-Path $EnvLocalPath) {
        & docker compose -f $LocalCompose --env-file $EnvLocalPath down -v 2>$null | Out-Null
    }
    & docker compose -f $CloudCompose down -v 2>$null | Out-Null
    Ok 'Volumes removed.'
}

# ── Cloud stack ──────────────────────────────────────────────────────
Step 'Cloud stack (cloud-db + api-admin + job-sync-cloud)'
& docker compose -f $CloudCompose up -d --build
if ($LASTEXITCODE -ne 0) { Err 'docker compose (cloud) up failed.'; exit 2 }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-cloud-db')) { Err 'cloud-db never became healthy.'; exit 2 }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-api-admin')) { Err 'api-admin never became healthy.'; exit 2 }
Ok 'Cloud stack healthy.'

Step 'Migrating cloud-db (alembic upgrade head, as the parkos superuser)'
Invoke-AlembicUpgrade -ComposeArgs @('-f', $CloudCompose) -ApiService 'api-admin' -DbService 'cloud-db'
Invoke-PartitionFixup -ComposeArgs @('-f', $CloudCompose) -DbService 'cloud-db'

# ── .env.local (branch uuid) ────────────────────────────────────────
if (-not (Test-Path $EnvLocalPath)) {
    Step ('Creating ' + $EnvLocalPath)
    Set-Content -Path $EnvLocalPath -Value ('PARKOS_SUCURSAL_UUID=' + $BranchUuid) -NoNewline
    Ok 'Written (gitignored -- never commit this file).'
} else {
    Ok ($EnvLocalPath + ' already exists -- leaving as-is.')
}

# ── Branch stack ─────────────────────────────────────────────────────
Step 'Branch stack (branch-db + api-sucursal + job-sync-sucursal)'
& docker compose -f $LocalCompose --env-file $EnvLocalPath up -d --build
if ($LASTEXITCODE -ne 0) { Err 'docker compose (local/branch) up failed.'; exit 2 }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-branch-db')) { Err 'branch-db never became healthy.'; exit 2 }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-api-sucursal')) { Err 'api-sucursal never became healthy.'; exit 2 }
Ok 'Branch stack healthy.'

Step 'Migrating branch-db (alembic upgrade head, as the parkos superuser)'
Invoke-AlembicUpgrade -ComposeArgs @('-f', $LocalCompose, '--env-file', $EnvLocalPath) -ApiService 'api-sucursal' -DbService 'branch-db'
Invoke-PartitionFixup -ComposeArgs @('-f', $LocalCompose, '--env-file', $EnvLocalPath) -DbService 'branch-db'

Step 'Restarting app containers so they pick up the freshly migrated schema'
docker restart parkos-job-sync-sucursal parkos-job-sync-cloud parkos-api-sucursal parkos-api-admin | ForEach-Object { Write-Host ('  ' + $_) }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-api-admin')) { Err 'api-admin never became healthy after restart.'; exit 2 }
if (-not (Wait-ContainerHealthy -ContainerName 'parkos-api-sucursal')) { Err 'api-sucursal never became healthy after restart.'; exit 2 }
Ok 'App containers healthy.'

# ── Bootstrap pairing (admin user, branch row, sync JWT) ────────────
Step 'bootstrap_pairing.py (dev admin user + branch + sync JWT)'
Invoke-BootstrapPairing

# ── Seed data ────────────────────────────────────────────────────────
Step 'Seeding prod.alert_types (cloud + branch -- idempotent, ON CONFLICT DO NOTHING)'
& python (Join-Path $RepoRoot 'infra\scripts\seed_alert_types.py') --dsn 'postgresql://parkos:parkos@localhost:5432/parkos'
& python (Join-Path $RepoRoot 'infra\scripts\seed_alert_types.py') --dsn 'postgresql://parkos:parkos@localhost:5433/parkos'

Step 'Seeding tipos-vehiculo catalog via the admin API (smoke-test script)'
Push-Location $BackendDir
try {
    & python (Join-Path $RepoRoot 'infra\scripts\seed_catalogs.py') --cloud-api-url 'http://localhost:8000' `
        --jwt-key-path $JwtKeyPath --branch-uuid $BranchUuid --table tipos-vehiculo --rows 'carro,moto,bicicleta,patineta,otro'
    if ($LASTEXITCODE -ne 0) {
        Warn 'seed_catalogs.py reported partial/failed rows. Expected once tipos-vehiculo already holds 5 rows (migration 0062 seeds them canonically; this script has no dedupe-by-name and the API enforces a hard cap of 5 -- see its docstring). Not fatal.'
    }
} finally { Pop-Location }

# ── Frontend ─────────────────────────────────────────────────────────
Step 'pnpm install (apps/ workspace)'
Push-Location $AppsDir
try {
    & pnpm install
    if ($LASTEXITCODE -ne 0) { throw 'pnpm install failed.' }
} finally { Pop-Location }

Step ('web_admin dev server on :' + $VitePort)
$portBound = Test-NetConnection -ComputerName 127.0.0.1 -Port $VitePort -InformationLevel Quiet -WarningAction SilentlyContinue
if ($portBound) {
    Ok ('Port :' + $VitePort + ' already listening -- reusing the existing dev server.')
} else {
    $outLog = (Join-Path $env:TEMP 'web_admin-qa.out')
    $errLog = (Join-Path $env:TEMP 'web_admin-qa.err')
    Push-Location $AppsDir
    try {
        $proc = Start-Process -FilePath 'pnpm' -ArgumentList '--filter', 'web_admin', 'dev' `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    } finally { Pop-Location }
    Ok ('Vite started (PID ' + $proc.Id + '); stdout=' + $outLog + ' stderr=' + $errLog)

    $viteOk = $false
    for ($i = 1; $i -le 10; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $VitePort + '/login') -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $viteOk = $true; break }
        } catch {}
    }
    if (-not $viteOk) {
        Err ('Vite never became ready on :' + $VitePort + '. See ' + $errLog)
        exit 3
    }
    Ok ('Vite responding on :' + $VitePort)
}

# ── Summary ──────────────────────────────────────────────────────────
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  PARKOS QA ADMIN STACK READY' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host ('  web_admin (Vite):     http://127.0.0.1:' + $VitePort + '/login')
Write-Host '  api-admin (cloud):    http://127.0.0.1:8000'
Write-Host '  api-sucursal:         http://127.0.0.1:8100'
Write-Host '  cloud-db:             localhost:5432 (parkos/parkos)'
Write-Host '  branch-db:            localhost:5433 (parkos/parkos)'
Write-Host '  Admin login:          admin@parkos.local / Admin12345! (dev-only, hardcoded in bootstrap_pairing.py)'
Write-Host ('  Branch uuid:          ' + $BranchUuid + ' (web_admin e2e fixture BRANCH_NORTE)')
Write-Host ('  DIAN provider URL:    ' + $DianProviderUrl + ' (mock)')
Write-Host ''
Write-Host 'Next step (chrome-devtools MCP):'
Write-Host ('  navigate_page url="http://127.0.0.1:' + $VitePort + '/login"')
Write-Host '  fill data-testid="login-email" -> admin@parkos.local'
Write-Host '  fill data-testid="login-password" -> Admin12345!'
Write-Host '  click data-testid="login-submit"'
Write-Host ''
Ok 'Done.'
