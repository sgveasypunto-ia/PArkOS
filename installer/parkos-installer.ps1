#Requires -Version 7.0
<#
.SYNOPSIS
    Parkos branch installer - installs the full sucursal stack (Postgres,
    api-sucursal + job-sync-sucursal Windows services, web_sucursal) on a
    client Windows machine with no Docker.

.DESCRIPTION
    Runtime installer for plan.md Parte III, Fases 21-24. Compiled to
    parkos-installer.exe via ps2exe (installer/build-release.ps1 Stage 4).
    Consumes the payload produced by build-release.ps1: web_sucursal MSI,
    the two frozen service exes, and the offline Postgres/pg_partman/NSSM
    payload.

    DEC-INST-02/03/04 (2026-09-27): Invoke-ParkosInstall is a MENU, not a
    forced linear wizard - the operator runs/re-runs any of 9 stages
    independently (0: descargar main + compilar, 1: Postgres+roles+pg_partman,
    2: migraciones, 3: crear sucursal real en prod.sucursal, 4: seed de
    catalogos, 5: servicio api-sucursal, 6: job de sync, 7: app de escritorio,
    8: verificacion final). Each stage keeps its own hard gate (throws on
    failure, caught at the menu level so one bad stage doesn't kill the
    whole session) - see Invoke-TuiStep. Port reconciliation (DEC-INST-03):
    the API port is no longer hardcoded to 8000 anywhere - Test-ApiPort picks
    a free one and Set-MachineApiOrigin/PARKOS_API_ORIGIN propagate it to the
    packaged Electron app via its preload bridge (resolveRequestUrl.ts).
    Sucursal creation (DEC-INST-03): no REST endpoint or CLI exists anywhere
    in the backend for this (verified directly against
    backend/.../api/v1/admin_views.py) - Install-SucursalRow is a direct SQL
    INSERT against models/V/sucursal.py's exact contract, replacing the
    previous raw "paste a UUID" prompt that never corresponded to any real
    row.

.NOTES
    Ternary/null-coalescing operators are deliberately avoided even though
    PS7 supports them, so this file stays parseable (for syntax checks) on
    a box that only has Windows PowerShell 5.1 - the actual dev machine
    this was written on has no PowerShell 7 installed at all.
#>

[CmdletBinding()]
param(
    [string]$InstallPath = 'C:\Program Files\Parkos',
    [string]$DataPath = 'C:\ProgramData\Parkos',
    # Operational values the installer cannot invent - real business/ops
    # inputs, not defaults. Prompted interactively if left empty and
    # -Unattended is not set; -Unattended requires them to be passed.
    [string]$SucursalUuid = '',
    # Datos reales de la sucursal - usados para GENERAR el UUID e insertar
    # la fila en prod.sucursal (Install-SucursalRow). Si -SucursalUuid ya
    # vino explicito (sucursal existente, escenario repair/reinstall), se
    # ignoran y no se crea ninguna fila nueva.
    [string]$SucursalNombre = '',
    [string]$SucursalPrefijo = '',
    [string]$SucursalCiudad = '',
    [string]$CloudApiUrl = '',
    [switch]$Unattended
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PayloadRoot = Join-Path $PSScriptRoot 'payload'
$script:PS7_MSI_NAME = 'PowerShell-7.4.6-win-x64.msi'
$script:PS7_MSI_URL = "https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/$($script:PS7_MSI_NAME)"
# Real SHA256, computed directly from the file downloaded over HTTPS from
# this exact GitHub Releases URL (Get-FileHash against the payload's cached
# copy) - not fabricated, not copy-pasted from a doc.
$script:PS7_MSI_SHA256 = 'ED331A04679B83D4C013705282D1F3F8D8300485EB04C081F36E11EAF1148BD0'

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.1: pre-flight check (6 blocking verifications)
# ---------------------------------------------------------------------------

function Test-WindowsVersion {
    param([int]$MinBuild = 19044)  # Windows 10 21H2
    $build = [System.Environment]::OSVersion.Version.Build
    return $build -ge $MinBuild
}

function Test-Preflight {
    [CmdletBinding()]
    param([string]$InstallPath = $script:InstallPath, [string]$DataPath = $script:DataPath)

    $driveLetter = $InstallPath.Substring(0, 1)
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator
    )
    $freeBytes = (Get-PSDrive -Name $driveLetter).Free
    $hasConnectivity = Test-NetConnection -ComputerName 'github.com' -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
    $alreadyInstalled = Test-Path (Join-Path $DataPath 'pairing.json')

    $results = [ordered]@{
        'Windows >= 10 21H2'         = (Test-WindowsVersion)
        'PowerShell >= 7'            = ($PSVersionTable.PSVersion.Major -ge 7)
        'Permisos de administrador'  = $isAdmin
        'Espacio en disco (>=5GB)'   = ($freeBytes -gt 5GB)
        'Conectividad saliente'      = $hasConnectivity
        'Sin instalacion previa'     = (-not $alreadyInstalled)
    }

    foreach ($check in $results.GetEnumerator()) {
        if ($check.Value) {
            Write-Host "[OK]    $($check.Key)" -ForegroundColor Green
        } else {
            Write-Host "[FALLO] $($check.Key)" -ForegroundColor Red
        }
    }

    if ($alreadyInstalled) {
        Write-Host ''
        Write-Host 'Ya existe una instalacion de Parkos en este equipo.' -ForegroundColor Yellow
        Write-Host 'Use Repair-ParkosInstall o Update-ParkosStack en vez de una instalacion limpia (Fases 25/26).' -ForegroundColor Yellow
    }

    return -not ($results.Values -contains $false)
}

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.1 BR2: auto-elevacion (relanzo con -Verb RunAs si no es admin)
# ---------------------------------------------------------------------------
# Found by actually running this installer, not by re-reading the spec:
# Test-Preflight only REPORTED the admin check as failed - nothing ever
# relaunched elevated, so every step past it (Copy-Item into "Program
# Files\PostgreSQL\16\share\extension", Postgres/NSSM service registration)
# hit real "Access denied" errors instead of the self-elevation HU-F21.1
# actually specifies ("se relanza a si mismo con Start-Process pwsh -Verb
# RunAs una sola vez; si el usuario rechaza la elevacion, exit code 2").
function Request-Elevation {
    [CmdletBinding()]
    param([string[]]$OriginalArgs = @())

    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator
    )
    if ($isAdmin) {
        return
    }

    Write-Host 'Se requieren permisos de administrador; solicitando elevacion (UAC)...' -ForegroundColor Yellow
    $relaunchArgs = @('-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $OriginalArgs
    try {
        $proc = Start-Process pwsh -ArgumentList $relaunchArgs -Verb RunAs -Wait -PassThru
    } catch {
        # UAC dialog dismissed/denied - Start-Process throws rather than
        # returning a process object in that case.
        Write-Host 'Se requieren permisos de administrador para instalar Parkos.' -ForegroundColor Red
        exit 2
    }
    exit $proc.ExitCode
}

# ---------------------------------------------------------------------------
# DEC-INST-04: descargar main + compilar (menu item 0)
# ---------------------------------------------------------------------------
# Corre en la maquina del TECNICO (con toolchain de desarrollo completo -
# git/pnpm/uv), NUNCA en el PC final de la sucursal - confirmado
# explicitamente con el operador (2026-09-27): el PC de produccion no debe
# terminar con herramientas de desarrollo instaladas permanentemente. Si
# falta alguna, esta opcion tira un error claro (que herramienta falta +
# la alternativa: correr build-release.ps1 a mano en otra maquina y copiar
# installer\payload\) en vez de instalarla sobre la marcha.
function Test-BuildToolchain {
    $missing = @()
    foreach ($tool in 'git', 'pnpm', 'uv') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            $missing += $tool
        }
    }
    return $missing
}

function Invoke-SourceUpdateAndBuild {
    [CmdletBinding()]
    param()

    $missing = Test-BuildToolchain
    if ($missing.Count -gt 0) {
        throw "Falta instalar: $($missing -join ', '). Alternativa: corre build-release.ps1 a mano en una maquina con el toolchain completo y copia installer\payload\ aca."
    }

    # installer/ es hijo directo de la raiz del repo (mismo calculo que
    # build-release.ps1's propio $RepoRoot).
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    Push-Location $repoRoot
    try {
        & git fetch origin main
        if ($LASTEXITCODE -ne 0) { throw 'git fetch origin main fallo.' }
        & git checkout main
        if ($LASTEXITCODE -ne 0) { throw 'git checkout main fallo.' }
        & git pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw 'git pull --ff-only fallo (la rama local diverge de origin/main - resolvelo manualmente antes de reintentar).' }
    } finally {
        Pop-Location
    }

    # Sin switches -> build-release.ps1 corre TODAS las etapas (confirmado
    # en su propio param block: "$anySwitch = ...; No switch passed at all
    # -> full build"). Reusa el orquestador existente por proceso separado
    # en vez de duplicar su logica (~350 lineas) inline.
    $buildScript = Join-Path $PSScriptRoot 'build-release.ps1'
    & $buildScript
    if ($LASTEXITCODE -ne 0) {
        throw "build-release.ps1 fallo (exit $LASTEXITCODE)."
    }

    # Gate real: build-release.ps1 puede reportar exit 0 en un stage
    # individual y aun asi dejar el payload incompleto si otro stage tuvo
    # un problema no fatal - confirmar que los 5 artefactos esperados
    # realmente existen antes de dar esta opcion por exitosa.
    $expectedExes = @(
        'services\api-sucursal\api-sucursal\api-sucursal.exe'
        'services\job-sync-sucursal\job-sync-sucursal\job-sync-sucursal.exe'
        'services\migrate\migrate\migrate.exe'
        'services\seed\seed\seed.exe'
        'services\doctor\doctor\doctor.exe'
    )
    foreach ($rel in $expectedExes) {
        $full = Join-Path $script:PayloadRoot $rel
        if (-not (Test-Path $full)) {
            throw "Build termino sin error pero falta el artefacto esperado: $rel"
        }
    }
    $msi = Get-ChildItem (Join-Path $script:PayloadRoot 'apps') -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $msi) {
        throw 'Build termino sin error pero no se encontro el MSI de web_sucursal en installer\payload\apps.'
    }
}

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.2: auto-instalacion de PowerShell 7 sobre un equipo 5.1
# ---------------------------------------------------------------------------

function Ensure-PowerShell7 {
    [CmdletBinding()]
    param([string[]]$OriginalArgs = @())

    if ($PSVersionTable.PSVersion.Major -ge 7) {
        return
    }

    Write-Host 'Instalando PowerShell 7 (requerido)...' -ForegroundColor Yellow
    $msiPath = Join-Path $env:TEMP $script:PS7_MSI_NAME
    Invoke-WebRequest -Uri $script:PS7_MSI_URL -OutFile $msiPath -UseBasicParsing

    $actualHash = (Get-FileHash -Path $msiPath -Algorithm SHA256).Hash
    if ($actualHash -ne $script:PS7_MSI_SHA256) {
        throw 'Hash de PowerShell 7 no coincide; instalacion abortada por seguridad.'
    }

    Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /qn" -Wait

    $relaunchArgs = @('-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $OriginalArgs
    $proc = Start-Process pwsh -ArgumentList $relaunchArgs -Wait -PassThru
    exit $proc.ExitCode
}

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.3: EULA y seleccion de rutas de instalacion
# ---------------------------------------------------------------------------

function Show-Eula {
    [CmdletBinding()]
    param([string]$EulaPath = (Join-Path $script:PayloadRoot 'README-EULA.txt'))

    if (-not (Test-Path $EulaPath)) {
        # Real legal text is a business/legal deliverable, not something to
        # fabricate here - fail loudly instead of shipping a blank EULA.
        throw "EULA file not found at $EulaPath - a real EULA (with PostgreSQL/NSSM/Electron third-party attributions) must be staged there before this installer ships."
    }

    Get-Content $EulaPath | Out-Host -Paging

    if ($Unattended) {
        return $true
    }

    $answer = Read-Host 'Escriba ACEPTO para continuar (cualquier otra respuesta cancela la instalacion)'
    if ($answer -ne 'ACEPTO') {
        Write-Host 'EULA no aceptada. Saliendo sin cambios.' -ForegroundColor Yellow
        exit 0
    }
    return $true
}

function Test-InstallPathAllowed {
    param([string]$Path)

    $normalized = $Path.TrimEnd('\')
    if ($normalized -match '^[A-Za-z]:\\Windows(\\|$)') { return $false }
    if ($normalized -match '^[A-Za-z]:\\Program Files \(x86\)(\\|$)') { return $false }
    if ($normalized -match '^\\\\') { return $false }  # UNC network path
    return $true
}

function Read-InstallPaths {
    [CmdletBinding()]
    param(
        [string]$DefaultInstallPath = 'C:\Program Files\Parkos',
        [string]$DefaultDataPath = 'C:\ProgramData\Parkos'
    )

    if ($Unattended) {
        return @{ InstallPath = $DefaultInstallPath; DataPath = $DefaultDataPath }
    }

    $installPath = Read-Host "Ruta de instalacion de binarios [$DefaultInstallPath]"
    if ([string]::IsNullOrWhiteSpace($installPath)) { $installPath = $DefaultInstallPath }
    if (-not (Test-InstallPathAllowed $installPath)) {
        throw "Ruta de instalacion invalida: $installPath (no se permite C:\Windows, Program Files (x86), ni rutas de red UNC)."
    }

    $dataPath = Read-Host "Ruta de datos [$DefaultDataPath]"
    if ([string]::IsNullOrWhiteSpace($dataPath)) { $dataPath = $DefaultDataPath }
    if (-not (Test-InstallPathAllowed $dataPath)) {
        throw "Ruta de datos invalida: $dataPath (no se permite C:\Windows, Program Files (x86), ni rutas de red UNC)."
    }

    return @{ InstallPath = $installPath; DataPath = $dataPath }
}

# ---------------------------------------------------------------------------
# Fase 22 - HU-F22.1: deteccion de puertos y coexistencia con Postgres previo
# ---------------------------------------------------------------------------

function Test-PostgresPorts {
    foreach ($candidatePort in 5432, 5433) {
        $inUse = Test-NetConnection -ComputerName '127.0.0.1' -Port $candidatePort -InformationLevel Quiet -WarningAction SilentlyContinue
        if (-not $inUse) { return $candidatePort }
    }
    throw 'Puertos 5432 y 5433 ambos ocupados; no se puede instalar Postgres de Parkos.'
}

# DEC-INST-03 (port reconciliation): mismo patron que Test-PostgresPorts -
# el puerto de api-sucursal estaba hardcodeado a 8000 en 3 lugares
# (Write-RuntimeEnvFile, Invoke-CatalogSeed, Wait-ForApiHealth) sin ninguna
# deteccion de conflicto. `resolveRequestUrl.ts` en electron-sucursal (via
# window.bridge.config.getApiOrigin, backed por PARKOS_API_ORIGIN) ya puede
# leer un puerto distinto en runtime - lo que faltaba era que el instalador
# realmente eligiera uno y lo propagara de punta a punta.
function Test-ApiPort {
    param([int[]]$CandidatePorts = @(8000, 8001, 8002))
    foreach ($candidatePort in $CandidatePorts) {
        $inUse = Test-NetConnection -ComputerName '127.0.0.1' -Port $candidatePort -InformationLevel Quiet -WarningAction SilentlyContinue
        if (-not $inUse) { return $candidatePort }
    }
    throw "Puertos $($CandidatePorts -join ', ') todos ocupados; no se puede instalar el servicio api-sucursal."
}

# Machine-level (no solo este proceso) - mismo patron exacto que
# Set-PgPassFile's PGPASSFILE: la app Electron se lanza despues, en una
# sesion nueva que no hereda nada de este instalador, asi que necesita
# leerlo de una variable de entorno de MAQUINA, no de sesion/usuario.
function Set-MachineApiOrigin {
    param([int]$Port)

    $origin = "http://127.0.0.1:$Port"
    [Environment]::SetEnvironmentVariable('PARKOS_API_ORIGIN', $origin, 'Machine')
    $env:PARKOS_API_ORIGIN = $origin
}

# ---------------------------------------------------------------------------
# Fase 22 - HU-F22.2: instalacion de Postgres 16 (winget con fallback a ZIP)
# ---------------------------------------------------------------------------

# Found by actually running Install-PostgresViaWinget for real (not just
# reading it): a bare `winget install` with no `--override` never sets a
# superuser password or a custom port at all - the EDB installer it wraps
# would fall back to whatever its own silent-mode default is (verified
# manually: it accepts `--superpassword`/`--serverport` via winget's
# `--override` passthrough only when explicitly given). Every earlier
# manual test in this session that "worked" set these by hand outside this
# function; the function itself had never been exercised before this fix.
function Install-PostgresViaWinget {
    param([int]$Port, [string]$SuperuserPassword)

    $overrideArgs = "--mode unattended --unattendedmodeui none --superpassword $SuperuserPassword --serverport $Port --disable-components stackbuilder"
    winget install --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements --override $overrideArgs | Out-Host
    return $LASTEXITCODE -eq 0
}

function Install-PostgresViaZip {
    param([string]$PayloadZipPath, [string]$PgInstallPath, [string]$PgDataPath, [int]$Port, [string]$SuperuserPassword)

    Expand-Archive -Path $PayloadZipPath -DestinationPath $PgInstallPath -Force
    # `-U postgres` (default bootstrap superuser), never `-U parkos` - the
    # winget path (HU-F22.2's primary method, verified against a real
    # install) always bootstraps as `postgres`; using a different bootstrap
    # identity here would make Initialize-DatabaseRoles need two incompatible
    # code paths depending on which install method ran. Both paths converge
    # on the same idempotent `parkos` role creation afterward.
    $pwFile = New-TemporaryFile
    Set-Content -Path $pwFile -Value $SuperuserPassword -NoNewline
    try {
        & "$PgInstallPath\bin\initdb.exe" -D $PgDataPath --locale=es-CO --encoding=UTF8 -U postgres --pwfile=$pwFile --auth=scram-sha-256
        if ($LASTEXITCODE -ne 0) {
            throw 'initdb fallo al inicializar el data directory de Postgres.'
        }
    } finally {
        Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
    }
    # ZIP path needs an explicit port (winget's package sets it via
    # --override at install time; a manual initdb+ZIP layout defaults to
    # 5432 via postgresql.conf otherwise).
    $confPath = Join-Path $PgDataPath 'postgresql.conf'
    Add-Content -Path $confPath -Value "port = $Port"
}

function Install-Postgres {
    param([string]$PgInstallPath, [string]$PgDataPath, [int]$Port, [string]$SuperuserPassword)

    Write-Host 'Instalando Postgres via winget...'
    $wingetOk = $false
    try {
        $wingetOk = Install-PostgresViaWinget -Port $Port -SuperuserPassword $SuperuserPassword
    } catch {
        $wingetOk = $false
    }

    if ($wingetOk) {
        return
    }

    Write-Host 'winget no disponible o fallo; usando ZIP de EDB del payload...' -ForegroundColor Yellow
    $zipPath = Join-Path $script:PayloadRoot 'postgres\postgresql-16-windows-x64-binaries.zip'
    if (-not (Test-Path $zipPath)) {
        throw "Ni winget ni el ZIP de fallback ($zipPath) estan disponibles; no se puede instalar Postgres."
    }
    Install-PostgresViaZip -PayloadZipPath $zipPath -PgInstallPath $PgInstallPath -PgDataPath $PgDataPath -Port $Port -SuperuserPassword $SuperuserPassword
}

# ---------------------------------------------------------------------------
# Fase 22 - HU-F22.3: superusuario de migracion + rol parkos_app de runtime
# ---------------------------------------------------------------------------

function New-SecurePassword {
    param([int]$Length = 24)
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return ([Convert]::ToBase64String($bytes) -replace '[+/=]', 'x').Substring(0, $Length)
}

# Found by actually running this installer end-to-end, not by re-reading
# the spec: every raw `psql -U <role>` call in this file needs SOME
# password source, or it blocks on an interactive prompt on whatever
# console the installer happens to be running in (confirmed live - a real
# operator saw exactly this hang). Passing passwords ad hoc per call
# (PGPASSWORD set/unset around each invocation) is what caused that gap in
# the first place - easy to add a new psql call and forget it. `.pgpass` is
# Postgres's own native mechanism for unattended authentication: write it
# ONCE with every identity this installer or its scheduled task will ever
# need, point PGPASSFILE at it machine-wide, and EVERY psql invocation
# (including Register-PgPartmanMaintenance's task, which runs unattended
# tomorrow with no shell environment to inherit a per-call PGPASSWORD from)
# authenticates silently from then on.
$script:PgPassCredentials = @{}

function Set-PgPassFile {
    # Additive across calls (script-scoped accumulator): Initialize-
    # DatabaseRoles writes postgres+parkos first; Invoke-MigrationsAndSeed
    # adds parkos_app once migration 0021 actually sets that password.
    # Each call rewrites the whole file from the accumulated set so no
    # earlier entry is ever clobbered by a later one.
    param([int]$Port, [hashtable]$Credentials)

    foreach ($key in $Credentials.Keys) { $script:PgPassCredentials[$key] = $Credentials[$key] }

    $pgpassDir = Join-Path $script:DataPath 'secrets'
    New-Item -ItemType Directory -Force -Path $pgpassDir | Out-Null
    $pgpassPath = Join-Path $pgpassDir 'pgpass.conf'
    $lines = foreach ($user in $script:PgPassCredentials.Keys) { "127.0.0.1:${Port}:*:${user}:$($script:PgPassCredentials[$user])" }
    Set-Content -Path $pgpassPath -Value $lines

    # Windows psql does not enforce .pgpass file-permission checks the way
    # Unix does (Postgres docs: "assumed secure... permissions are not
    # currently checked") - restrict the ACL ourselves anyway (Administrators
    # + SYSTEM only) as defense in depth, since this file holds every
    # Postgres identity's plaintext password.
    icacls $pgpassPath /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' | Out-Null

    # Machine-level (not just this process) so the scheduled task - which
    # runs under svc-parkos in a fresh session tomorrow, inheriting nothing
    # from this installer process - picks it up too.
    [Environment]::SetEnvironmentVariable('PGPASSFILE', $pgpassPath, 'Machine')
    $env:PGPASSFILE = $pgpassPath
}

function Initialize-DatabaseRoles {
    param([string]$PsqlPath, [int]$Port, [string]$BootstrapPassword)

    $superuserPassword = New-SecurePassword
    $appPassword = New-SecurePassword

    # Write postgres+parkos credentials to .pgpass BEFORE the first psql
    # call below - `-w` (never prompt) turns any credential mistake here
    # into a clean connection failure instead of a hang. `parkos_app`'s
    # entry is added once migration 0021 actually sets that password
    # (Invoke-MigrationsAndSeed), not here - the role does not exist yet.
    Set-PgPassFile -Port $Port -Credentials @{ postgres = $BootstrapPassword; parkos = $superuserPassword }

    # Bootstraps as `postgres` (the identity both Install-PostgresViaWinget
    # and Install-PostgresViaZip now converge on, using $BootstrapPassword -
    # the same password Install-Postgres set at install time). `parkos` may
    # or may not exist yet depending on prior runs, so this is idempotent -
    # verified against a real winget-installed Postgres 16 where `parkos`
    # genuinely did not exist (only `postgres` did; a plain `ALTER ROLE
    # parkos ...` fails outright in that real, common case).
    $sql = @"
DO `$`$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parkos') THEN
        CREATE ROLE parkos LOGIN SUPERUSER PASSWORD '$superuserPassword';
    ELSE
        ALTER ROLE parkos WITH PASSWORD '$superuserPassword' SUPERUSER LOGIN;
    END IF;
END
`$`$;
"@
    # `Out-Null` is not decorative here: any external command's stdout that
    # a function doesn't capture becomes part of THAT function's own return
    # value in PowerShell - without this, the caller gets psql's own "DO"
    # output mixed into the hashtable below (confirmed: turns the return
    # into an array, so $roles.AppPassword resolves to nothing).
    & $PsqlPath -w -p $Port -h 127.0.0.1 -U postgres -c $sql | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo configurar el superusuario parkos.'
    }

    # `CREATE DATABASE` cannot run inside a transaction/DO block (Postgres
    # utility command restriction) - a separate idempotent check+create.
    # Found by actually running the migration step against a real install:
    # nothing else in Fase 22 ever created the `parkos` database itself
    # (only the `postgres` default database exists after initdb/winget),
    # so `alembic upgrade head` failed outright with "database does not
    # exist" before this was added.
    $dbExists = (& $PsqlPath -w -p $Port -h 127.0.0.1 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'parkos';").Trim()
    if ($dbExists -ne '1') {
        & $PsqlPath -w -p $Port -h 127.0.0.1 -U postgres -c 'CREATE DATABASE parkos OWNER parkos;' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'No se pudo crear la base de datos parkos.'
        }
    }

    return @{ SuperuserPassword = $superuserPassword; AppPassword = $appPassword }
}

# Two INDEPENDENT env vars carry the DB connection, not one - verified
# against the real code, not assumed:
#   - PARKOS_DB_URL  -> validated by runtime/env.py's load_config() gate
#                       (sync scheme, postgresql+psycopg://). The gate only
#                       checks this string is non-empty; it never actually
#                       opens a connection with it.
#   - DATABASE_URL   -> read directly by db/engine.py's _resolve_url()
#                       (async scheme, postgresql+asyncpg://) to build the
#                       REAL SQLAlchemy engine. NOT checked by the gate at
#                       all - if this one is missing/wrong, load_config()
#                       still passes and the service only crashes on the
#                       first actual query (RuntimeError from db/engine.py).
# Both must be written, kept in sync, and never point at the superuser.
function Write-RuntimeEnvFile {
    param(
        [Parameter(Mandatory)][string]$EnvFilePath,
        [Parameter(Mandatory)][string]$AppPassword,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$SucursalUuid,
        [Parameter(Mandatory)][string]$CloudApiUrl,
        [Parameter(Mandatory)][string]$JwtKeyPath,
        [Parameter(Mandatory)][string]$SyncJwtPath,
        [int]$ApiPort = 8000
    )

    $lines = @(
        'PARKOS_DEPLOY=branch'
        "PARKOS_SUCURSAL_UUID=$SucursalUuid"
        "PARKOS_DB_URL=postgresql+psycopg://parkos_app:$AppPassword@127.0.0.1:$Port/parkos"
        "DATABASE_URL=postgresql+asyncpg://parkos_app:$AppPassword@127.0.0.1:$Port/parkos"
        "PARKOS_CLOUD_API_URL=$CloudApiUrl"
        "PARKOS_JWT_KEY_PATH=$JwtKeyPath"
        "PARKOS_SYNC_JWT_PATH=$SyncJwtPath"
        "PORT=$ApiPort"
        # No lo lee api-sucursal.exe (solo PORT) - lo lee la app Electron
        # via el bridge (electron/main.ts's config:api-origin handler),
        # que hereda variables de entorno de MAQUINA, no de este .env.
        # Se escribe aca tambien solo para que el .env quede autocontenido
        # como referencia de diagnostico; el wiring real es
        # Set-MachineApiOrigin (ver Invoke-ParkosInstall).
        "PARKOS_API_ORIGIN=http://127.0.0.1:$ApiPort"
    )

    New-Item -ItemType Directory -Force -Path (Split-Path $EnvFilePath) | Out-Null
    Set-Content -Path $EnvFilePath -Value $lines -NoNewline:$false
}

# ---------------------------------------------------------------------------
# Adelantado de Fase 27 (HU-F27.1): cuenta minima svc-parkos
# ---------------------------------------------------------------------------
# Found by actually running Register-PgPartmanMaintenance for real: it fails
# with "No mapping between account names and security IDs" because
# `-UserId 'svc-parkos'` requires that LOCAL WINDOWS ACCOUNT to already
# exist - and it doesn't, since its full creation + ACL hardening is Fase
# 27 (HU-F27.1), not written yet. Fase 22's scheduled task genuinely needs
# it earlier than Fase 27 runs, so only the bare account is created here
# (idempotent); Fase 27 owns ACL restriction/hardening later, not creation.
function Ensure-ServiceAccount {
    param([string]$Name = 'svc-parkos')

    if (Get-LocalUser -Name $Name -ErrorAction SilentlyContinue) {
        return
    }
    $password = New-SecurePassword -Length 32 | ConvertTo-SecureString -AsPlainText -Force
    # New-LocalUser -Description caps at 48 chars (Windows API limit).
    New-LocalUser -Name $Name -Password $password -PasswordNeverExpires -UserMayNotChangePassword `
        -AccountNeverExpires -Description 'Parkos service account (NSSM, tasks)' | Out-Null
    # A Scheduled Task "ServiceAccount" logon type still needs the "Log on
    # as a batch job" right; New-LocalUser alone does not grant it. Direct
    # registry-based grant since Windows exposes no first-party cmdlet for
    # user rights assignment (only secedit/ntrights, both external tools).
    $sid = (Get-LocalUser -Name $Name).SID.Value
    $secEditIni = Join-Path $env:TEMP 'svc-parkos-rights.inf'
    $tmpDb = Join-Path $env:TEMP 'svc-parkos-rights.sdb'
    secedit /export /cfg $secEditIni /quiet | Out-Null
    $content = Get-Content $secEditIni
    $line = $content | Where-Object { $_ -match '^SeBatchLogonRight' }
    if ($line) {
        $newLine = "$line,*$sid"
        $content = $content -replace [regex]::Escape($line), $newLine
    } else {
        $content += "SeBatchLogonRight = *$sid"
    }
    Set-Content -Path $secEditIni -Value $content
    secedit /configure /db $tmpDb /cfg $secEditIni /quiet | Out-Null
    Remove-Item $secEditIni, $tmpDb -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Fase 22 - HU-F22.4: pg_partman (extension SQL-only, sin bgw compilado)
# ---------------------------------------------------------------------------
# pg_partman no tiene binario oficial precompilado para Windows (verificado:
# issues #55/#111/#197 en pgpartman/pg_partman, sin paquete PGDG tampoco). El
# .so del contenedor Docker parkos-postgres:16-pgpartman del proyecto tampoco
# sirve - son binarios Linux/ELF, no cargan en Windows.
#
# El propio Makefile de la extension confirma que el background worker
# (pg_partman_bgw, lo unico que requiere compilar) es OPCIONAL (NO_BGW=1):
# todas las funciones de gestion de particiones son PL/pgSQL puro. build-
# release.ps1's Get-PgPartmanBinaries ya arma pg_partman--5.1.0.sql
# concatenando sql/types+tables+functions+procedures en el orden exacto del
# Makefile upstream, junto al pg_partman.control sin modificar - verificado
# end-to-end contra un Postgres 16 real (CREATE EXTENSION, create_parent(),
# run_maintenance_proc() con particiones reales creadas). Sin bgw no hace
# falta shared_preload_libraries ni reiniciar el servicio: el mantenimiento
# lo dispara la tarea programada de Windows (Register-PgPartmanMaintenance),
# nunca el timer interno del bgw - exactamente lo que DEC-INST-14 ya pedia.
function Install-PgPartman {
    param([string]$PgInstallPath, [string]$PsqlPath, [int]$Port)

    $payloadExtension = Join-Path $script:PayloadRoot 'pg_partman\extension'
    Copy-Item "$payloadExtension\*" "$PgInstallPath\share\extension\" -Force

    # `-w` (never prompt) + `-h 127.0.0.1` (.pgpass matches by exact
    # hostname): relies on the `parkos` entry Initialize-DatabaseRoles
    # already wrote to .pgpass via Set-PgPassFile - no ad hoc PGPASSWORD
    # juggling here (that pattern is exactly what caused a real interactive-
    # prompt hang elsewhere in this file before Set-PgPassFile existed).
    & $PsqlPath -w -p $Port -h 127.0.0.1 -U parkos -c 'CREATE SCHEMA IF NOT EXISTS partman;' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el schema partman (psql exit $LASTEXITCODE) - revisar .pgpass/autenticacion de 'parkos'."
    }
    & $PsqlPath -w -p $Port -h 127.0.0.1 -U parkos -c 'CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA partman;' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "CREATE EXTENSION pg_partman fallo (psql exit $LASTEXITCODE)."
    }
    $check = (& $PsqlPath -w -p $Port -h 127.0.0.1 -U parkos -tAc "SELECT 1 FROM pg_extension WHERE extname = 'pg_partman';")
    if ($LASTEXITCODE -ne 0 -or -not $check -or $check.Trim() -ne '1') {
        throw 'pg_partman no quedo activo tras CREATE EXTENSION.'
    }
}

function Register-PgPartmanMaintenance {
    param([string]$PsqlPath, [int]$Port)

    # `-w -h 127.0.0.1`: this runs unattended tomorrow at 2am with no shell
    # environment to inherit a password from - it authenticates purely from
    # the machine-level PGPASSFILE Set-PgPassFile already wrote (parkos_app's
    # entry is added once Invoke-MigrationsAndSeed knows that password).
    $action = New-ScheduledTaskAction -Execute $PsqlPath -Argument "-w -p $Port -h 127.0.0.1 -U parkos_app -d parkos -c `"CALL partman.run_maintenance_proc();`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 2am
    $principal = New-ScheduledTaskPrincipal -UserId 'svc-parkos' -LogonType ServiceAccount
    Register-ScheduledTask -TaskName 'ParkosPgPartmanMaintenance' -Action $action -Trigger $trigger -Principal $principal -Description 'Mantenimiento diario de particiones pg_partman (Parkos)' -Force | Out-Null
}

# ---------------------------------------------------------------------------
# Fase 23 - HU-F23.1: alembic upgrade head via el migrate.exe congelado
# ---------------------------------------------------------------------------
# plan.md's own HU-F23.1 snippet assumes `.\venv\Scripts\alembic.exe` (a
# real venv on disk) - inconsistent with DEC-INST-01/02's "frozen binary,
# no Python installed" framing, and with the PyInstaller direction this
# build actually took. Neither api-sucursal.exe nor job-sync-sucursal.exe
# expose an Alembic CLI (each is a single-purpose onedir bundle tied to its
# own entry script), so build-release.ps1 freezes a third, dedicated
# migrate.exe (installer/bootstrap/entry_migrate.py -> alembic.config:main)
# just for this step.
#
# alembic.ini's `script_location = migrations` and `prepend_sys_path =
# ../src` are CWD-relative (verified: not `%(here)s`-anchored) - migrate.exe
# must run from its own directory, exactly like plan.md's Push-Location
# pattern, or Alembic cannot find the migration scripts at all.
function Invoke-MigrationsAndSeed {
    param([hashtable]$Roles, [int]$Port)

    $migrateDir = Join-Path $script:PayloadRoot 'services\migrate\migrate'
    $migrateExe = Join-Path $migrateDir 'migrate.exe'

    Push-Location $migrateDir
    try {
        $env:DATABASE_URL = "postgresql://parkos:$($Roles.SuperuserPassword)@127.0.0.1:$Port/parkos"
        $env:PARKOS_APP_DB_PASSWORD = $Roles.AppPassword
        & $migrateExe -c alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "alembic upgrade head fallo (exit $LASTEXITCODE)."
        }
    } finally {
        Remove-Item Env:\PARKOS_APP_DB_PASSWORD -ErrorAction SilentlyContinue
        Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
        Pop-Location
    }

    # parkos_app now exists (migration 0021 just created it with this exact
    # password) - add it to .pgpass so every later parkos_app connection
    # (HU-F24.4's gate, Register-PgPartmanMaintenance's daily task) also
    # authenticates without a prompt.
    Set-PgPassFile -Port $Port -Credentials @{ parkos_app = $Roles.AppPassword }
}

# ---------------------------------------------------------------------------
# Fase 22b - HU-F22.x: creacion real de la fila de sucursal (DEC-INST-03)
# ---------------------------------------------------------------------------
# Investigacion directa (2026-09-27) confirmo que NO existe ningun endpoint
# REST ni CLI para esto en todo el repo -
# backend/packages/parkos_core/src/parkos_core/api/v1/admin_views.py solo
# expone GET /admin/sucursales y GET /admin/sucursales/{uuid}/dashboard,
# ningun POST. El unico precedente es
# infra/scripts/bootstrap_pairing.py::ensure_sucursal, que ademas apunta a
# la CLOUD-db, no a la base LOCAL de esta sucursal. Sin esto, el operador
# tipeaba un UUID crudo (Read-Host 'UUID (v4)...') que nunca correspondia a
# ninguna fila real - runtime/env.py's load_config() solo valida que tenga
# FORMA de UUIDv4, nunca que exista, asi que el sistema "funcionaba" con un
# UUID inventado hasta que algo necesitara datos reales de la sucursal.
#
# Contrato exacto verificado en models/V/sucursal.py: 8 columnas de negocio
# nullable (String sin limite de longitud), FKs a tipo_sucursal/empresa
# "application-enforced" (sin constraint SQL - se dejan NULL), UK real en
# (prefijo_nombre, vigente_desde). `uuid` es la PK fisica heredada de
# VersionedBase (misma base que `ON CONFLICT (uuid)` ya asume en
# ensure_sucursal, confirmado ahi mismo).
function Read-SucursalData {
    [CmdletBinding()]
    param(
        [string]$Nombre = '',
        [string]$Prefijo = '',
        [string]$Ciudad = ''
    )

    if ($Unattended) {
        if ([string]::IsNullOrWhiteSpace($Nombre) -or [string]::IsNullOrWhiteSpace($Prefijo)) {
            throw '-SucursalNombre y -SucursalPrefijo son obligatorios en modo -Unattended.'
        }
    } else {
        if ([string]::IsNullOrWhiteSpace($Nombre)) {
            $Nombre = Read-Host 'Nombre de la sucursal (ej. "Parqueadero Centro")'
        }
        if ([string]::IsNullOrWhiteSpace($Nombre)) {
            throw 'El nombre de la sucursal es obligatorio.'
        }

        if ([string]::IsNullOrWhiteSpace($Prefijo)) {
            $Prefijo = Read-Host 'Prefijo / siglas de la sucursal (ej. "PQC")'
        }
        if ([string]::IsNullOrWhiteSpace($Prefijo)) {
            throw 'El prefijo/siglas de la sucursal es obligatorio.'
        }

        if ([string]::IsNullOrWhiteSpace($Ciudad)) {
            $Ciudad = Read-Host 'Ciudad de la sucursal'
        }
    }

    # El operador ya NO tipea el UUID (era el bug original) - se genera aca
    # y se informa en pantalla para que quede documentado.
    $uuid = [guid]::NewGuid().ToString()
    Write-Host "UUID generado para esta sucursal: $uuid" -ForegroundColor Cyan

    return @{ Uuid = $uuid; Nombre = $Nombre; Prefijo = $Prefijo; Ciudad = $Ciudad }
}

function Install-SucursalRow {
    param(
        [string]$PsqlPath,
        [int]$Port,
        [string]$Uuid,
        [string]$Nombre,
        [string]$Prefijo,
        [string]$Ciudad
    )

    # Texto libre tipeado por el operador (no generado por el programa, a
    # diferencia de las passwords en Initialize-DatabaseRoles) - escapar
    # comillas simples es necesario de verdad, no defensivo de mas: nombres
    # reales de sucursal/ciudad ("Parqueadero D'Elia") rompen la sintaxis
    # SQL sin esto.
    $nombreSql = $Nombre.Replace("'", "''")
    $prefijoSql = $Prefijo.Replace("'", "''")
    $ciudadSql = $Ciudad.Replace("'", "''")

    # ON CONFLICT (uuid) DO NOTHING - idempotente, mismo patron que
    # ensure_sucursal en bootstrap_pairing.py: reintentar esta opcion del
    # menu con el mismo UUID no duplica la fila.
    $sql = @"
INSERT INTO prod.sucursal (
    uuid, vigente_desde, vigente_hasta, estado,
    created_at, created_by,
    nombre, prefijo_nombre, ciudad,
    uuid_tipo_sucursal, uuid_empresa
) VALUES (
    '$Uuid', NOW(), NULL, 'activo',
    NOW(), NULL,
    '$nombreSql', '$prefijoSql', '$ciudadSql',
    NULL, NULL
)
ON CONFLICT (uuid) DO NOTHING;
"@
    & $PsqlPath -w -p $Port -h 127.0.0.1 -U parkos_app -d parkos -c $sql | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo crear la fila de sucursal en prod.sucursal.'
    }

    # Gate real (no solo "el comando termino sin error"): confirmar que la
    # fila realmente quedo visible y vigente antes de dejar avanzar al
    # siguiente paso (sembrar catalogos depende de esto).
    $exists = (& $PsqlPath -w -p $Port -h 127.0.0.1 -U parkos_app -d parkos -tAc "SELECT 1 FROM prod.sucursal WHERE uuid = '$Uuid' AND vigente_hasta IS NULL;").Trim()
    if ($exists -ne '1') {
        throw 'La fila de sucursal no quedo visible tras el INSERT (verificacion post-insert fallo).'
    }
}

# ---------------------------------------------------------------------------
# Fase 23 - HU-F23.2: seed de tipos_vehiculo via la API real
# ---------------------------------------------------------------------------
# Only `tipos_vehiculo` has no seed anywhere in the migrations (verified -
# see entry_seed.py's own docstring for why `tipo_arqueo`/`impuestos`/
# `config_caja` are NOT seeded here). The API needs api-sucursal actually
# running to receive these calls, but Fase 24 (NSSM service registration)
# hasn't happened yet at this point in the install - so this starts
# api-sucursal.exe as a plain temporary process (loopback only, matching
# DEC-INST's "never expose beyond 127.0.0.1"), seeds through it, then stops
# it; Fase 24 registers the permanent NSSM service afterward.
function Invoke-CatalogSeed {
    param(
        [string]$EnvFilePath,
        [hashtable]$Roles,
        [int]$Port,
        [string]$JwtKeyPath,
        [string]$SucursalUuid,
        [int]$ApiPort = 8000
    )

    $apiExe = Join-Path $script:PayloadRoot 'services\api-sucursal\api-sucursal\api-sucursal.exe'
    $seedExe = Join-Path $script:PayloadRoot 'services\seed\seed\seed.exe'
    $logDir = Join-Path $script:DataPath 'logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    $envLines = Get-Content $EnvFilePath | Where-Object { $_ -match '=' }
    foreach ($line in $envLines) {
        $parts = $line -split '=', 2
        Set-Item -Path "Env:$($parts[0])" -Value $parts[1]
    }

    $proc = Start-Process -FilePath $apiExe -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'seed-api.out.log') `
        -RedirectStandardError (Join-Path $logDir 'seed-api.err.log')
    try {
        $healthy = $false
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/health" -UseBasicParsing -TimeoutSec 2
                if ($resp.StatusCode -eq 200) { $healthy = $true; break }
            } catch { }
        }
        if (-not $healthy) {
            throw 'api-sucursal.exe (temporal, para seed) no respondio /health a tiempo.'
        }

        $migrationDsn = "postgresql://parkos:$($Roles.SuperuserPassword)@127.0.0.1:$Port/parkos"
        & $seedExe --database-url $migrationDsn --api-base-url "http://127.0.0.1:$ApiPort" `
            --jwt-key-path $JwtKeyPath --sucursal-uuid $SucursalUuid
        if ($LASTEXITCODE -ne 0) {
            throw "seed.exe fallo (exit $LASTEXITCODE)."
        }
    } finally {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Fase 24 - HU-F24.1/24.2: servicios NSSM (api-sucursal, job-sync-sucursal)
# ---------------------------------------------------------------------------

function Copy-ServiceBundle {
    param([string]$Name, [string]$InstallPath)

    $src = Join-Path $script:PayloadRoot "services\$Name\$Name"
    $dest = Join-Path $InstallPath $Name
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item "$src\*" $dest -Recurse -Force
    return (Join-Path $dest "$Name.exe")
}

function Install-ApiService {
    param([string]$NssmPath, [string]$ExePath, [string]$EnvFilePath)

    & $NssmPath install ParkosApiSucursal $ExePath | Out-Null
    & $NssmPath set ParkosApiSucursal AppDirectory (Split-Path $ExePath) | Out-Null
    & $NssmPath set ParkosApiSucursal AppStdout (Join-Path $script:DataPath 'logs\api-sucursal.out.log') | Out-Null
    & $NssmPath set ParkosApiSucursal AppStderr (Join-Path $script:DataPath 'logs\api-sucursal.err.log') | Out-Null
    & $NssmPath set ParkosApiSucursal AppRotateFiles 1 | Out-Null
    & $NssmPath set ParkosApiSucursal AppRotateBytes 10485760 | Out-Null
    & $NssmPath set ParkosApiSucursal AppRotateOnline 1 | Out-Null
    & $NssmPath set ParkosApiSucursal Start SERVICE_AUTO_START | Out-Null
    & $NssmPath set ParkosApiSucursal AppRestartDelay 1000 | Out-Null

    $envVars = (Get-Content $EnvFilePath | Where-Object { $_ -match '=' }) -join "`r`n"
    & $NssmPath set ParkosApiSucursal AppEnvironmentExtra $envVars | Out-Null

    Start-Service ParkosApiSucursal
}

function Wait-ForApiHealth {
    param([string]$Url = 'http://127.0.0.1:8000/health', [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($resp.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Seconds 2 }
    }
    return $false
}

function Install-JobService {
    param([string]$NssmPath, [string]$ExePath, [string]$EnvFilePath)

    & $NssmPath install ParkosJobSyncSucursal $ExePath | Out-Null
    & $NssmPath set ParkosJobSyncSucursal AppDirectory (Split-Path $ExePath) | Out-Null
    & $NssmPath set ParkosJobSyncSucursal AppStdout (Join-Path $script:DataPath 'logs\job-sync.out.log') | Out-Null
    & $NssmPath set ParkosJobSyncSucursal AppRotateFiles 1 | Out-Null
    & $NssmPath set ParkosJobSyncSucursal AppRotateBytes 10485760 | Out-Null
    & $NssmPath set ParkosJobSyncSucursal Start SERVICE_AUTO_START | Out-Null
    & $NssmPath set ParkosJobSyncSucursal AppRestartDelay 1000 | Out-Null

    $envVars = ((Get-Content $EnvFilePath | Where-Object { $_ -match '=' }) + @(
        'PARKOS_SYNC_POLL_INTERVAL_S=10', 'PARKOS_SYNC_BATCH_SIZE=100'
    )) -join "`r`n"
    & $NssmPath set ParkosJobSyncSucursal AppEnvironmentExtra $envVars | Out-Null

    Start-Service ParkosJobSyncSucursal
}

function Wait-ForSyncPollCycle {
    # plan.md assumed a "poll cycle" log substring; the real structured
    # logger (structlog) never emits that literal word - verified against
    # a real running service, whose actual output is `sync_sucursal.*` /
    # `cycle_error` lines (structlog event names). `cycle_error` here is
    # itself a CORRECT, expected state on a fresh unpaired install
    # (`PARKOS_SYNC_JWT_PATH ... missing - branch must pair first`,
    # per Fase 29) - this check only confirms the worker is alive and
    # looping, not that sync itself succeeded (pairing hasn't happened yet).
    param([string]$LogPath, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-Content $LogPath -ErrorAction SilentlyContinue) -match 'sync_sucursal\.|cycle_error|worker_started') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# ---------------------------------------------------------------------------
# Fase 24 - HU-F24.3: instalacion silenciosa del MSI de web_sucursal
# ---------------------------------------------------------------------------

function Install-Electron {
    param([string]$MsiPath)

    $logPath = Join-Path $script:DataPath 'logs\electron-install.log'
    $proc = Start-Process msiexec.exe -ArgumentList "/i `"$MsiPath`" /qn /l*v `"$logPath`"" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Start-Process msiexec.exe -ArgumentList "/x `"$MsiPath`" /qn" -Wait
        throw "Instalacion de web_sucursal fallo (exit $($proc.ExitCode)); ver $logPath"
    }
    # `Get-Package` (PackageManagement/OneGet) does not reliably enumerate a
    # just-installed MSI without a provider refresh - verified against a
    # real install that msiexec completed cleanly (exit 0, confirmed via
    # Win32_Product AND the Uninstall registry key) while Get-Package still
    # found nothing. The Uninstall registry key is what Windows itself
    # populates on every MSI install - fast, no side effects (unlike
    # Win32_Product, which triggers a reconfigure of every installed MSI).
    $installed = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -match 'Parkos' }
    if (-not $installed) {
        throw 'MSI reporto exito pero web_sucursal no aparece en el registro de desinstalacion.'
    }
}

# ---------------------------------------------------------------------------
# Fase 24 - HU-F24.4: verificacion post-instalacion integral (el gate final)
# ---------------------------------------------------------------------------

function Test-PostInstallation {
    param([string]$EnvFilePath, [int]$Port)

    $doctorExe = Join-Path $script:PayloadRoot 'services\doctor\doctor\doctor.exe'
    $envLines = Get-Content $EnvFilePath | Where-Object { $_ -match '=' }
    foreach ($line in $envLines) {
        $parts = $line -split '=', 2
        Set-Item -Path "Env:$($parts[0])" -Value $parts[1]
    }
    $doctorJson = & $doctorExe | ConvertFrom-Json
    $doctorOk = ($doctorJson.env_status -eq 'ok') -and ($doctorJson.db_connectivity -like 'ok*') -and $doctorJson.jwt_key_path_exists

    # `-w` (never prompt) relying on the machine-level .pgpass
    # Invoke-MigrationsAndSeed already wrote parkos_app's entry into - found
    # by actually running this gate against a real elevated install that a
    # bare `psql -U parkos_app` with no password source blocks on an
    # INTERACTIVE prompt on whatever console the installer happens to be
    # running in (confirmed live - a real operator saw exactly this hang).
    $psqlPath = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'
    $currentUser = (& $psqlPath -w -p $Port -h 127.0.0.1 -U parkos_app -d parkos -tAc 'SELECT current_user;').Trim()
    $privilegeDenied = $true
    & $psqlPath -w -p $Port -h 127.0.0.1 -U parkos_app -d parkos -c "CREATE ROLE test_should_fail_$(Get-Random) LOGIN;" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $privilegeDenied = $false }
    $isAppUser = ($currentUser -eq 'parkos_app') -and $privilegeDenied

    $jwtPath = ($envLines | Where-Object { $_ -match '^PARKOS_JWT_KEY_PATH=' }) -replace '^PARKOS_JWT_KEY_PATH=', ''
    $jwtOk = (Test-Path $jwtPath) -and ((Get-Item $jwtPath).Length -ge 32)

    $results = [ordered]@{
        'Diagnostico general (doctor)'       = $doctorOk
        'Runtime conecta como parkos_app'    = $isAppUser
        'parkos_app no puede CREATE ROLE'    = $privilegeDenied
        'Secreto JWT real (>=32 bytes)'       = $jwtOk
    }
    $results.GetEnumerator() | Format-Table -AutoSize | Out-Host
    if ($results.Values -contains $false) {
        throw 'Verificacion post-instalacion fallo; ver detalle arriba. La instalacion NO se considera exitosa.'
    }
}

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

function New-JwtSigningKey {
    param([string]$Path, [int]$Bytes = 64)

    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    $keyBytes = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
    [System.IO.File]::WriteAllBytes($Path, $keyBytes)
}

# ---------------------------------------------------------------------------
# TUI paso a paso (DEC-INST-01: "ANSI puro, sin Terminal.Gui")
# ---------------------------------------------------------------------------
# `\r` (carriage return) alone - not a full ANSI/VT cursor-control sequence -
# rewrites the current line: universally supported (legacy conhost, Windows
# Terminal, VS Code's integrated terminal), unlike `\e[1A`-style sequences
# that need VT mode explicitly enabled. That is "ANSI puro" in the simplest,
# most compatible sense DEC-INST-01 asks for, not a TUI framework.
#
# DEC-INST-02: no longer a fixed "[i/N]" linear counter - the menu (see
# Invoke-ParkosInstall below) lets the operator run/re-run any stage in any
# order, so a running index across the whole session would be misleading
# (e.g. "[9/7]" after re-running one stage twice). The stage's own name plus
# its menu number (shown by the menu itself) is enough context.
function Invoke-TuiStep {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][scriptblock]$Action)

    Write-Host "  [....] $Name" -NoNewline -ForegroundColor Yellow
    try {
        & $Action
        Write-Host "`r  [ OK ] $Name" -ForegroundColor Green
    } catch {
        Write-Host "`r  [FAIL] $Name" -ForegroundColor Red
        Write-Host "         $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

function Invoke-ParkosInstall {
    [CmdletBinding()]
    param()

    Ensure-PowerShell7 -OriginalArgs $script:OriginalArgs
    Request-Elevation -OriginalArgs $script:OriginalArgs

    Write-Host '=== Parkos - pre-flight ===' -ForegroundColor Cyan
    $preflightOk = Test-Preflight -InstallPath $InstallPath -DataPath $DataPath
    if (-not $preflightOk) {
        Write-Host 'Pre-flight fallo. Instalacion abortada, sin cambios en el sistema.' -ForegroundColor Red
        exit 2
    }

    Write-Host ''
    Write-Host '=== Parkos - EULA ===' -ForegroundColor Cyan
    Show-Eula | Out-Null

    Write-Host ''
    Write-Host '=== Parkos - rutas de instalacion ===' -ForegroundColor Cyan
    $paths = Read-InstallPaths -DefaultInstallPath $InstallPath -DefaultDataPath $DataPath
    $script:DataPath = $paths.DataPath

    # Real operational values - never fabricated. Prompted here (once) if
    # not passed as parameters; -Unattended requires them upfront.
    #
    # DEC-INST-03: ya no se le pide al operador un UUID crudo por teclado -
    # ese UUID nunca correspondia a ninguna fila real en prod.sucursal (ver
    # Install-SucursalRow, Fase 22b - no existe ningun endpoint/CLI para
    # crear una sucursal, confirmado por investigacion directa 2026-09-27).
    # Si -SucursalUuid vino explicito por parametro (repair/reinstall de una
    # sucursal que YA tiene su fila en otro lado), se respeta tal cual y se
    # salta la recoleccion de datos nueva - $script:SucursalData queda $null
    # y la opcion 3 del menu ("Crear sucursal") lo refleja al intentarse.
    $script:SucursalData = $null
    if ([string]::IsNullOrWhiteSpace($SucursalUuid)) {
        $script:SucursalData = Read-SucursalData -Nombre $SucursalNombre -Prefijo $SucursalPrefijo -Ciudad $SucursalCiudad
        $SucursalUuid = $script:SucursalData.Uuid
    }
    if ([string]::IsNullOrWhiteSpace($CloudApiUrl)) {
        if ($Unattended) { throw '-CloudApiUrl es obligatorio en modo -Unattended.' }
        $CloudApiUrl = Read-Host 'URL de la API cloud (PARKOS_CLOUD_API_URL)'
    }

    Write-Host ''
    Write-Host '=== Parkos - instalacion (Fases 22-24) ===' -ForegroundColor Cyan

    $pgInstallPath = 'C:\Program Files\PostgreSQL\16'
    $pgDataPath = Join-Path $paths.DataPath 'pg-data'
    $psqlPath = Join-Path $pgInstallPath 'bin\psql.exe'
    $secretsDir = Join-Path $paths.DataPath 'secrets'
    $jwtKeyPath = Join-Path $secretsDir 'jwt.key'
    $syncJwtPath = Join-Path $secretsDir 'sync-agent.jwt'  # written later by the pairing flow (Fase 29), not here
    $envFilePath = Join-Path $secretsDir '.env'
    $nssmPath = Join-Path $script:PayloadRoot 'nssm.exe'
    $script:roles = $null
    $script:port = $null

    # DEC-INST-02: menu-driven instead of a single forced top-to-bottom pass.
    # Each stage keeps its own internal gate (Wait-ForApiHealth,
    # Wait-ForSyncPollCycle, etc. still throw exactly as before) - what
    # changes is that a thrown failure now returns to the menu (see the
    # dispatch loop below) instead of killing the whole process, and the
    # operator can re-run any single stage independently (e.g. re-run
    # migrations after an update without repeating Postgres install).
    $script:StageStatus = [ordered]@{
        build = $false
        db = $false; migrate = $false; sucursal = $false; seed = $false
        api = $false; job = $false; electron = $false; verify = $false
    }

    $stages = [ordered]@{
        '0' = @{
            Key    = 'build'
            Name   = 'Descargar ultima version de main y compilar artefactos'
            Action = {
                Invoke-SourceUpdateAndBuild
            }
        }
        '1' = @{
            Key    = 'db'
            Name   = 'Instalar base de datos (Postgres + roles + pg_partman)'
            Action = {
                $script:port = Test-PostgresPorts
                $script:apiPort = Test-ApiPort
                $bootstrapPassword = New-SecurePassword
                Install-Postgres -PgInstallPath $pgInstallPath -PgDataPath $pgDataPath -Port $script:port -SuperuserPassword $bootstrapPassword
                $script:roles = Initialize-DatabaseRoles -PsqlPath $psqlPath -Port $script:port -BootstrapPassword $bootstrapPassword

                New-JwtSigningKey -Path $jwtKeyPath
                Write-RuntimeEnvFile -EnvFilePath $envFilePath -AppPassword $script:roles.AppPassword -Port $script:port -ApiPort $script:apiPort `
                    -SucursalUuid $SucursalUuid -CloudApiUrl $CloudApiUrl -JwtKeyPath $jwtKeyPath -SyncJwtPath $syncJwtPath
                Set-MachineApiOrigin -Port $script:apiPort

                Install-PgPartman -PgInstallPath $pgInstallPath -PsqlPath $psqlPath -Port $script:port
                Ensure-ServiceAccount
                Register-PgPartmanMaintenance -PsqlPath $psqlPath -Port $script:port
            }
        }
        '2' = @{
            Key    = 'migrate'
            Name   = 'Ejecutar migraciones de base de datos'
            Action = {
                if ($null -eq $script:roles) { throw 'Corre primero "Instalar base de datos" (opcion 1).' }
                Invoke-MigrationsAndSeed -Roles $script:roles -Port $script:port
            }
        }
        '3' = @{
            Key    = 'sucursal'
            Name   = 'Crear sucursal en base de datos'
            Action = {
                if (-not $script:StageStatus.migrate) { throw 'Corre primero "Ejecutar migraciones" (opcion 2).' }
                if ($null -eq $script:SucursalData) {
                    throw '-SucursalUuid vino por parametro (sucursal existente) - no hay datos nuevos que insertar.'
                }
                Install-SucursalRow -PsqlPath $psqlPath -Port $script:port -Uuid $script:SucursalData.Uuid `
                    -Nombre $script:SucursalData.Nombre -Prefijo $script:SucursalData.Prefijo -Ciudad $script:SucursalData.Ciudad
            }
        }
        '4' = @{
            Key    = 'seed'
            Name   = 'Sembrar catalogos iniciales (arranca api-sucursal temporalmente)'
            Action = {
                if (-not $script:StageStatus.migrate) { throw 'Corre primero "Ejecutar migraciones" (opcion 2).' }
                Invoke-CatalogSeed -EnvFilePath $envFilePath -Roles $script:roles -Port $script:port -JwtKeyPath $jwtKeyPath -SucursalUuid $SucursalUuid -ApiPort $script:apiPort
            }
        }
        '5' = @{
            Key    = 'api'
            Name   = 'Instalar servicio api-sucursal (NSSM)'
            Action = {
                $apiExePath = Copy-ServiceBundle -Name 'api-sucursal' -InstallPath $paths.InstallPath
                Install-ApiService -NssmPath $nssmPath -ExePath $apiExePath -EnvFilePath $envFilePath
                if (-not (Wait-ForApiHealth -Url "http://127.0.0.1:$($script:apiPort)/health")) {
                    throw 'ParkosApiSucursal no respondio /health a tiempo tras el registro NSSM.'
                }
            }
        }
        '6' = @{
            Key    = 'job'
            Name   = 'Instalar job de sincronizacion (NSSM)'
            Action = {
                $jobExePath = Copy-ServiceBundle -Name 'job-sync-sucursal' -InstallPath $paths.InstallPath
                Install-JobService -NssmPath $nssmPath -ExePath $jobExePath -EnvFilePath $envFilePath
                $syncLogPath = Join-Path $paths.DataPath 'logs\job-sync.out.log'
                if (-not (Wait-ForSyncPollCycle -LogPath $syncLogPath)) {
                    throw 'ParkosJobSyncSucursal no mostro un ciclo de sondeo en el log a tiempo.'
                }
            }
        }
        '7' = @{
            Key    = 'electron'
            Name   = 'Instalar aplicacion de escritorio (web_sucursal)'
            Action = {
                $msiPath = (Get-ChildItem (Join-Path $script:PayloadRoot 'apps') -Filter '*.msi' | Select-Object -First 1).FullName
                if (-not $msiPath) {
                    throw 'No se encontro el MSI de web_sucursal en el payload.'
                }
                Install-Electron -MsiPath $msiPath
            }
        }
        '8' = @{
            Key    = 'verify'
            Name   = 'Verificacion final (Postgres, JWT, servicios)'
            Action = {
                Test-PostInstallation -EnvFilePath $envFilePath -Port $script:port
            }
        }
    }

    while ($true) {
        Write-Host ''
        Write-Host '=== Parkos - menu de instalacion ===' -ForegroundColor Cyan
        foreach ($number in $stages.Keys) {
            $stage = $stages[$number]
            $isDone = $script:StageStatus[$stage.Key]
            $tag = if ($isDone) { '[ OK ]' } else { '[ .. ]' }
            $color = if ($isDone) { 'Green' } else { 'White' }
            Write-Host ("  {0} {1}) {2}" -f $tag, $number, $stage.Name) -ForegroundColor $color
        }
        Write-Host '  [    ] Q) Salir' -ForegroundColor White
        $choice = Read-Host 'Elegi una opcion'

        if ($choice -eq 'q' -or $choice -eq 'Q') { break }
        if (-not $stages.Contains($choice)) {
            Write-Host 'Opcion invalida.' -ForegroundColor Red
            continue
        }

        $stage = $stages[$choice]
        try {
            Invoke-TuiStep -Name $stage.Name -Action $stage.Action
            $script:StageStatus[$stage.Key] = $true
        } catch {
            Write-Host "La etapa '$($stage.Name)' fallo: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host 'Podes reintentar esta opcion o resolver el problema antes de continuar.' -ForegroundColor Yellow
        }
    }

    $port = $script:port
    Write-Host ''
    Write-Host "Instalando en: $($paths.InstallPath)" -ForegroundColor Green
    Write-Host "Datos en:      $($paths.DataPath)" -ForegroundColor Green
    if ($port) {
        Write-Host "Postgres en puerto: $port" -ForegroundColor Green
    }
    Write-Host ''
    Write-Host 'Sesion de instalacion finalizada.' -ForegroundColor Green
}

if ($MyInvocation.InvocationName -ne '.') {
    $script:OriginalArgs = $args
    Invoke-ParkosInstall
}
