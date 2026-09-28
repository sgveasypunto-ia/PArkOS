<#
.SYNOPSIS
    Parkos release build orchestrator  - compiles every artifact the branch
    installer (installer/parkos-installer.ps1, Fases 21-24 of plan.md)
    consumes: the web_sucursal MSI, the two frozen Python services, the
    offline Postgres/pg_partman/NSSM payload, and (once it exists) the
    installer's own .exe.

.DESCRIPTION
    Single entrypoint for Parte III's "compile everything" step. Stages are
    independent except that Stage 0 (payload) must run before Stages 2-4
    consume its output, and Stage 4 consumes Stages 1-3's output. Re-run
    individual stages during iteration; use -All (or no switch) for a full
    release build.

.PARAMETER Version
    Version string stamped into artifact paths/names. Defaults to the
    version declared in apps/electron-sucursal/package.json.

.NOTES
    Stage 2/3 (PyInstaller freezes) and Stage 4 (ps2exe) are NOT executed
    as part of writing this script  - they are correct, ready-to-run
    commands, but a full freeze of the whole backend dependency tree takes
    several minutes and multiple GB of disk; run them explicitly.

    Deliberately has NO `#Requires -Version 7.0` (unlike parkos-installer.ps1,
    which needs PS7 per DEC-INST-01): this is a dev-only build tool, not the
    client-facing installer, and every construct here is 5.1-compatible by
    design (no ternary/null-coalescing/pipeline-chain operators) - verified
    by parsing this file with Windows PowerShell 5.1's own parser, not just
    assumed. Runs the same from `powershell.exe` or `pwsh`.
#>

[CmdletBinding()]
param(
    [switch]$All,
    [switch]$Payload,
    [switch]$WebSucursal,
    [switch]$ApiSucursal,
    [switch]$JobSync,
    [switch]$Migrate,
    [switch]$Seed,
    [switch]$Doctor,
    [switch]$Installer,
    [string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InstallerRoot = $PSScriptRoot
$PayloadRoot = Join-Path $InstallerRoot 'payload'
$PyiWorkRoot = Join-Path $InstallerRoot '.pyinstaller-work'

$BackendRoot = Join-Path $RepoRoot 'backend'
$ParkosCorePkg = Join-Path $BackendRoot 'packages\parkos_core'
$ElectronApp = Join-Path $RepoRoot 'apps\electron-sucursal'

if (-not $Version) {
    $pkgJson = Get-Content (Join-Path $ElectronApp 'package.json') -Raw | ConvertFrom-Json
    $Version = $pkgJson.version
}

# No switch passed at all -> full build.
$anySwitch = $Payload -or $WebSucursal -or $ApiSucursal -or $JobSync -or $Migrate -or $Seed -or $Doctor -or $Installer
if ($All -or -not $anySwitch) {
    $Payload = $true; $WebSucursal = $true; $ApiSucursal = $true; $JobSync = $true; $Migrate = $true; $Seed = $true; $Doctor = $true; $Installer = $true
}

function Write-StageBanner {
    param([string]$Name)
    Write-Host ''
    Write-Host ('=' * 70) -ForegroundColor Cyan
    Write-Host "  Stage: $Name" -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Stage 0  - third-party payload (Postgres, pg_partman, NSSM, PowerShell 7)
# ---------------------------------------------------------------------------

function Get-BuildPayload {
    New-Item -ItemType Directory -Force -Path $PayloadRoot, "$PayloadRoot\postgres", "$PayloadRoot\pg_partman" | Out-Null

    Get-PowerShell7Msi
    Get-PostgresZip
    Get-NssmBinary
    Get-PgPartmanBinaries
}

function Get-PowerShell7Msi {
    $psVersion = '7.4.6'
    $msiName = "PowerShell-$psVersion-win-x64.msi"
    $dest = Join-Path $PayloadRoot $msiName
    # Deterministic GitHub Releases URL (PowerShell always publishes this
    # exact asset name for this exact tag)  - this part is NOT a guess.
    $url = "https://github.com/PowerShell/PowerShell/releases/download/v$psVersion/$msiName"

    # Real SHA256, computed directly (Get-FileHash) from the file downloaded
    # over HTTPS from this exact GitHub Releases URL - not fabricated.
    $expectedSha256 = 'ED331A04679B83D4C013705282D1F3F8D8300485EB04C081F36E11EAF1148BD0'

    if (Test-Path $dest) {
        Write-Host "[payload] $msiName already cached, skipping download."
    } else {
        Write-Host "[payload] downloading $msiName ..."
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    }

    $actual = (Get-FileHash -Path $dest -Algorithm SHA256).Hash
    if ($actual -ne $expectedSha256) {
        throw "PowerShell 7 MSI hash mismatch for $msiName. Expected $expectedSha256, got $actual. Aborting - do not ship an unverified binary."
    }
}

function Get-PostgresZip {
    $dest = Join-Path $PayloadRoot 'postgres\postgresql-16-windows-x64-binaries.zip'
    if (Test-Path $dest) {
        Write-Host '[payload] Postgres 16 ZIP already cached, skipping.'
        return
    }
    # EnterpriseDB does not publish a stable, predictable direct-download URL
    # for a given Postgres/Windows build (their CDN paths are resolved
    # through the interactive downloads page). Do not fabricate one here  -
    # resolve the real URL manually (or via `winget show --id
    # PostgreSQL.PostgreSQL.16` metadata) and drop the ZIP at $dest, or let
    # HU-F22.2's winget path handle it online instead of relying on this
    # fallback ZIP.
    Write-Warning "[payload] Postgres 16 EDB ZIP not staged at $dest  - no stable direct-download URL exists; fetch it manually from https://www.enterprisedb.com/download-postgresql-binaries and place it there, or rely on the winget path (HU-F22.2) instead of the offline fallback."
}

function Get-NssmBinary {
    $dest = Join-Path $PayloadRoot 'nssm.exe'
    if (Test-Path $dest) {
        Write-Host '[payload] nssm.exe already cached, skipping.'
        return
    }
    $zipUrl = 'https://nssm.cc/release/nssm-2.24.zip'
    $tmpZip = Join-Path $env:TEMP 'nssm-2.24.zip'
    $tmpDir = Join-Path $env:TEMP 'nssm-2.24-extract'

    Write-Host '[payload] downloading nssm 2.24 ...'
    Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
    Copy-Item (Join-Path $tmpDir 'nssm-2.24\win64\nssm.exe') $dest -Force
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

# pg_partman has NO official precompiled Windows binary (verified: GitHub
# issues #55/#111/#197 on pgpartman/pg_partman all confirm this, no PGDG
# Windows package exists either). The Linux .so inside the project's own
# parkos-postgres:16-pgpartman Docker image is NOT usable here either - ELF
# binaries do not load on Windows.
#
# The extension's own Makefile confirms the background worker (`pg_partman_
# bgw`, the only piece that needs compiling) is OPTIONAL (`NO_BGW=1`): all
# partition-management functions are plain PL/pgSQL, built by concatenating
# sql/types + sql/tables + sql/functions + sql/procedures into one
# `pg_partman--<version>.sql`, installed alongside the untouched `.control`
# file - no compiler, no DLL. Verified end-to-end against a real disposable
# Postgres 16 container: CREATE EXTENSION, create_parent(), and
# run_maintenance_proc() all worked and produced real child partitions.
# Skipping the bgw is a non-issue here: DEC-INST-14 already drives partition
# maintenance from a Windows Scheduled Task (Register-PgPartmanMaintenance),
# never from the bgw's own timer.
function Get-PgPartmanBinaries {
    $version = '5.1.0'
    $dest = Join-Path $PayloadRoot 'pg_partman\extension'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    $sqlOut = Join-Path $dest "pg_partman--$version.sql"
    $controlOut = Join-Path $dest 'pg_partman.control'
    if ((Test-Path $sqlOut) -and (Test-Path $controlOut)) {
        Write-Host '[payload] pg_partman SQL-only extension already staged, skipping.'
        return
    }

    $tmpZip = Join-Path $env:TEMP "pg_partman-$version.zip"
    $tmpDir = Join-Path $env:TEMP "pg_partman-$version-extract"
    Write-Host "[payload] downloading pg_partman v$version source ..."
    Invoke-WebRequest -Uri "https://github.com/pgpartman/pg_partman/archive/refs/tags/v$version.zip" -OutFile $tmpZip -UseBasicParsing
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
    $srcRoot = Join-Path $tmpDir "pg_partman-$version"

    # Same order the upstream Makefile uses (types -> tables -> functions ->
    # procedures); files within each directory sorted for reproducibility.
    $sqlFiles = @()
    foreach ($sub in 'types', 'tables', 'functions', 'procedures') {
        $sqlFiles += Get-ChildItem (Join-Path $srcRoot "sql\$sub") -Filter '*.sql' | Sort-Object Name
    }
    Get-Content -Path $sqlFiles.FullName -Raw | Set-Content -Path $sqlOut -NoNewline

    Copy-Item (Join-Path $srcRoot 'pg_partman.control') $controlOut -Force
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Stage 1  - web_sucursal (Electron, electron-builder)
# ---------------------------------------------------------------------------

function Build-WebSucursal {
    Push-Location $RepoRoot
    try {
        pnpm --filter '@parkos/electron-sucursal' build
        if ($LASTEXITCODE -ne 0) { throw 'pnpm build (electron-sucursal) failed.' }

        pnpm --filter '@parkos/electron-sucursal' run build:packager
        if ($LASTEXITCODE -ne 0) { throw 'electron-builder (build:packager) failed.' }
    } finally {
        Pop-Location
    }

    $distDir = Join-Path $ElectronApp 'dist\electron'
    $msi = Get-ChildItem -Path $distDir -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $msi) {
        throw "No .msi found under $distDir  - check electron-builder.yml's win.target includes 'msi'."
    }

    New-Item -ItemType Directory -Force -Path "$PayloadRoot\apps" | Out-Null
    Copy-Item $msi.FullName "$PayloadRoot\apps\web_sucursal-$Version-x64.msi" -Force
    Write-Host "[web_sucursal] -> $PayloadRoot\apps\web_sucursal-$Version-x64.msi"
}

# ---------------------------------------------------------------------------
# Stage 2/3  - PyInstaller freezes (api-sucursal, job-sync-sucursal)
# ---------------------------------------------------------------------------

function Invoke-ServiceFreeze {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$EntryScript
    )

    $distPath = Join-Path $PayloadRoot "services\$Name"
    $workPath = Join-Path $PyiWorkRoot 'build'
    $specPath = Join-Path $PyiWorkRoot 'specs'
    New-Item -ItemType Directory -Force -Path $distPath, $workPath, $specPath | Out-Null

    Push-Location $BackendRoot
    try {
        uv run pyinstaller `
            --name $Name `
            --onedir `
            --noconfirm `
            --distpath $distPath `
            --workpath $workPath `
            --specpath $specPath `
            --collect-all cryptography `
            --collect-all bcrypt `
            --collect-all lxml `
            --collect-all pydantic `
            --collect-all pydantic_core `
            --hidden-import psycopg `
            --hidden-import psycopg2 `
            --hidden-import asyncpg `
            --hidden-import logging.config `
            $EntryScript
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $Name." }
    } finally {
        Pop-Location
    }

    # migrations/ + alembic.ini live outside the hatchling-packaged
    # src/parkos_core wheel (confirmed by reading pyproject.toml's
    # [tool.hatch.build.targets.wheel] packages list)  - PyInstaller's
    # analysis never sees them, so they're copied as plain files next to
    # the frozen exe instead of fought into --add-data.
    $serviceOutDir = Join-Path $distPath $Name
    Copy-Item (Join-Path $ParkosCorePkg 'migrations') (Join-Path $serviceOutDir 'migrations') -Recurse -Force
    Copy-Item (Join-Path $ParkosCorePkg 'alembic.ini') (Join-Path $serviceOutDir 'alembic.ini') -Force

    Write-Host "[$Name] -> $serviceOutDir"
}

function Build-ApiSucursalExe {
    Invoke-ServiceFreeze -Name 'api-sucursal' -EntryScript (Join-Path $InstallerRoot 'bootstrap\entry_api_sucursal.py')
}

function Build-JobSyncSucursalExe {
    Invoke-ServiceFreeze -Name 'job-sync-sucursal' -EntryScript (Join-Path $InstallerRoot 'bootstrap\entry_job_sync_sucursal.py')
}

# Neither api-sucursal.exe nor job-sync-sucursal.exe expose an Alembic CLI -
# each is a single-purpose onedir bundle tied to its own entry script. The
# installer's migration step (Fase 23, `alembic upgrade head`) needs its own
# frozen entry point since there is no venv on the client machine.
function Build-MigrateExe {
    Invoke-ServiceFreeze -Name 'migrate' -EntryScript (Join-Path $InstallerRoot 'bootstrap\entry_migrate.py')
}

# Fase 23 (HU-F23.2) catalog seed - talks to a temporarily-started
# api-sucursal.exe over the real HTTP API (never raw SQL for business-
# governed catalog rows), per DEC in installer/bootstrap/entry_seed.py.
function Build-SeedExe {
    Invoke-ServiceFreeze -Name 'seed' -EntryScript (Join-Path $InstallerRoot 'bootstrap\entry_seed.py')
}

# Fase 24 (HU-F24.4) post-install gate - reuses the real
# parkos_core.cli.doctor, never a parallel PowerShell reimplementation.
function Build-DoctorExe {
    Invoke-ServiceFreeze -Name 'doctor' -EntryScript (Join-Path $InstallerRoot 'bootstrap\entry_doctor.py')
}

# ---------------------------------------------------------------------------
# Stage 4  - parkos-installer.exe (ps2exe over the runtime installer script)
# ---------------------------------------------------------------------------

function Build-ParkosInstallerExe {
    $installerScript = Join-Path $InstallerRoot 'parkos-installer.ps1'

    if (-not (Test-Path $installerScript)) {
        Write-Warning '[installer] installer/parkos-installer.ps1 does not exist yet (Fases 21-24 of plan.md  - separate deliverable). Skipping ps2exe compilation.'
        return
    }
    if (-not (Get-Module -ListAvailable -Name ps2exe)) {
        Write-Warning "[installer] PowerShell module 'ps2exe' is not installed (Install-Module ps2exe -Scope CurrentUser). Skipping compilation."
        return
    }

    Import-Module ps2exe
    Invoke-ps2exe `
        -inputFile $installerScript `
        -outputFile (Join-Path $PayloadRoot 'parkos-installer.exe') `
        -noConsole:$false `
        -requireAdmin

    Write-Host "[installer] -> $PayloadRoot\parkos-installer.exe"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

$results = [ordered]@{}

function Invoke-Stage {
    param([string]$StageName, [scriptblock]$Action)
    Write-StageBanner $StageName
    try {
        & $Action
        $results[$StageName] = 'OK'
    } catch {
        $results[$StageName] = "FAILED: $($_.Exception.Message)"
        Write-Error $_.Exception.Message
        throw
    }
}

try {
    if ($Payload) { Invoke-Stage 'Payload (Postgres/pg_partman/NSSM/PS7)' { Get-BuildPayload } }
    if ($WebSucursal) { Invoke-Stage 'web_sucursal (Electron MSI)' { Build-WebSucursal } }
    if ($ApiSucursal) { Invoke-Stage 'api-sucursal.exe (PyInstaller)' { Build-ApiSucursalExe } }
    if ($JobSync) { Invoke-Stage 'job-sync-sucursal.exe (PyInstaller)' { Build-JobSyncSucursalExe } }
    if ($Migrate) { Invoke-Stage 'migrate.exe (PyInstaller)' { Build-MigrateExe } }
    if ($Seed) { Invoke-Stage 'seed.exe (PyInstaller)' { Build-SeedExe } }
    if ($Doctor) { Invoke-Stage 'doctor.exe (PyInstaller)' { Build-DoctorExe } }
    if ($Installer) { Invoke-Stage 'parkos-installer.exe (ps2exe)' { Build-ParkosInstallerExe } }
} finally {
    Write-Host ''
    Write-Host ('=' * 70)
    Write-Host '  Build summary'
    Write-Host ('=' * 70)
    foreach ($entry in $results.GetEnumerator()) {
        Write-Host ("  {0,-40} {1}" -f $entry.Key, $entry.Value)
    }
}
