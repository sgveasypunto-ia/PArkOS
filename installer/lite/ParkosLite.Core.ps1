# Parkos LITE - nucleo: rutas, puertos, secretos, env file, estado persistente,
# pasos/gating/menu y decisiones del refresh. Solo define funciones (sin
# StrictMode, sin param(), sin efectos al cargar) para poder dot-sourcearlo
# desde los tests Pester. Compatible con Windows PowerShell 5.1 y pwsh 7.
# Todo acceso al sistema (puertos, comandos, git) vive en wrappers pequenos
# (Test-ParkosLitePortInUse, Test-ParkosLiteCommand) que los tests mockean.

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

function Get-ParkosLiteDefaultPath {
    $base = $env:LOCALAPPDATA
    if (-not $base) { $base = Join-Path $env:USERPROFILE 'AppData\Local' }
    return (Join-Path $base 'ParkosLite')
}

function Get-ParkosLitePaths {
    param([Parameter(Mandatory)][string]$LitePath, [Parameter(Mandatory)][string]$RepoRoot)

    $data = Join-Path $LitePath 'data'
    $svc = Join-Path $RepoRoot 'installer\payload\services'
    return @{
        Lite       = $LitePath
        Downloads  = Join-Path $LitePath 'downloads'
        Tools      = Join-Path $LitePath 'tools'
        PgRoot     = Join-Path $LitePath 'pgsql'
        PgData     = Join-Path $data 'pg'
        Logs       = Join-Path $LitePath 'logs'
        Run        = Join-Path $LitePath 'run'
        Data       = $data
        EnvFile    = Join-Path $data 'api.env'
        State      = Join-Path $LitePath 'state.json'
        Secrets    = Join-Path $data 'secrets.json'
        JwtKey     = Join-Path $data 'jwt-signing.key'
        SyncJwt    = Join-Path $data 'sync-agent.jwt'
        ApiExe     = Join-Path $svc 'api-sucursal\api-sucursal\api-sucursal.exe'
        MigrateDir = Join-Path $svc 'migrate\migrate'
        MigrateExe = Join-Path $svc 'migrate\migrate\migrate.exe'
        FrontDir   = Join-Path $RepoRoot 'apps\electron-sucursal'
        AppsDir    = Join-Path $RepoRoot 'apps'
        SeedSql    = Join-Path $RepoRoot 'installer\lite\seed_demo.sql'
        # Partes versionadas en git (zips en partes + payload-parts.json). Postgres
        # vive en parts\postgres (se movio desde payload\postgres).
        PartsDir   = Join-Path $RepoRoot 'installer\payload\parts'
        PayloadRoot = Join-Path $RepoRoot 'installer\payload'
        PgPayload  = Join-Path $RepoRoot 'installer\payload\parts\postgres'
        PartmanPayload = Join-Path $RepoRoot 'installer\payload\pg_partman\extension'
        RepoRoot   = $RepoRoot
    }
}

function Get-ParkosLiteUrls {
    param([Parameter(Mandatory)][int]$ApiPort, [Parameter(Mandatory)][int]$FrontPort)
    return @{
        Front     = "http://127.0.0.1:$FrontPort/"
        ApiHealth = "http://127.0.0.1:$ApiPort/health"
        ApiDocs   = "http://127.0.0.1:$ApiPort/docs"
    }
}

# ---------------------------------------------------------------------------
# Puertos
# ---------------------------------------------------------------------------

# Wrapper: consulta los listeners TCP activos del sistema (cualquier direccion).
# No se usa un bind de prueba: en Windows un bind a 0.0.0.0 puede "tener exito"
# aunque otro proceso (p. ej. Docker Desktop) ya escuche ese puerto.
function Test-ParkosLitePortInUse {
    param([Parameter(Mandatory)][int]$Port)
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    foreach ($l in $listeners) { if ($l.Port -eq $Port) { return $true } }
    return $false
}

function Find-ParkosLiteFreePort {
    param(
        [Parameter(Mandatory)][int]$Start,
        [int[]]$Exclude = @(),
        [int]$MaxTries = 50,
        [scriptblock]$IsInUse = { param($p) Test-ParkosLitePortInUse -Port $p }
    )
    for ($p = $Start; $p -lt ($Start + $MaxTries); $p++) {
        if ($Exclude -contains $p) { continue }
        if (-not (& $IsInUse $p)) { return $p }
    }
    throw "No se encontro un puerto libre entre $Start y $($Start + $MaxTries - 1)."
}

# Decide el puerto de un servicio: explicito (-Requested) > persistido > primero
# libre desde -Start. Un puerto explicito ocupado por un tercero es un error;
# un puerto persistido ocupado por un tercero se reemplaza; si lo ocupa el
# propio servicio lite (-OwnedByLite) se conserva.
function Resolve-ParkosLitePort {
    param(
        [int]$Requested = 0,
        [int]$Persisted = 0,
        [Parameter(Mandatory)][int]$Start,
        [switch]$OwnedByLite,
        [int[]]$Exclude = @(),
        [string]$Name = 'servicio',
        [scriptblock]$IsInUse = { param($p) Test-ParkosLitePortInUse -Port $p }
    )
    if ($Requested -gt 0) {
        if ((& $IsInUse $Requested) -and -not $OwnedByLite) {
            throw "El puerto $Requested pedido para $Name esta ocupado por otro proceso. Elige otro con el parametro correspondiente."
        }
        return $Requested
    }
    if ($Persisted -gt 0) {
        if ($OwnedByLite -or -not (& $IsInUse $Persisted)) { return $Persisted }
    }
    return (Find-ParkosLiteFreePort -Start $Start -Exclude $Exclude -IsInUse $IsInUse)
}

# ---------------------------------------------------------------------------
# Secretos descartables + env file
# ---------------------------------------------------------------------------

function New-ParkosLiteRandomPassword {
    param([int]$Length = 24)
    $bytes = New-Object byte[] ($Length * 2)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', '').Substring(0, $Length)
}

# El lite NO usa clave maestra: genera passwords aleatorias descartables (solo
# viven en el directorio de datos del lite; es un entorno de demo).
function New-ParkosLiteSecrets {
    return @{
        PostgresPassword  = New-ParkosLiteRandomPassword
        SuperuserPassword = New-ParkosLiteRandomPassword
        AppPassword       = New-ParkosLiteRandomPassword
    }
}

function Read-ParkosLiteSecrets {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $o = Get-Content $Path -Raw | ConvertFrom-Json
    return @{
        PostgresPassword  = $o.PostgresPassword
        SuperuserPassword = $o.SuperuserPassword
        AppPassword       = $o.AppPassword
    }
}

function Save-ParkosLiteSecrets {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Secrets)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    ($Secrets | ConvertTo-Json) | Set-Content -Path $Path -Encoding UTF8
}

function Test-ParkosUuidV4 {
    param([string]$Value)
    return [bool]($Value -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$')
}

# Mismas variables que Write-RuntimeEnvFile del instalador completo
# (runtime/env.py::load_config + engine_flag + db/engine.py), pero SIN cifrar
# (CMS): el lite es un entorno de demo y el exe corre como proceso de usuario.
# PARKOS_CLOUD_API_URL es un placeholder: sin job de sync nunca se contacta.
function Get-ParkosLiteEnvLines {
    param(
        [Parameter(Mandatory)][string]$SucursalUuid,
        [Parameter(Mandatory)][string]$AppPassword,
        [Parameter(Mandatory)][int]$DbPort,
        [Parameter(Mandatory)][int]$ApiPort,
        [Parameter(Mandatory)][string]$JwtKeyPath,
        [Parameter(Mandatory)][string]$SyncJwtPath
    )
    return @(
        'PARKOS_DEPLOY=branch'
        'PARKOS_SYNC_ENGINE=catalog_branch'
        "PARKOS_SUCURSAL_UUID=$SucursalUuid"
        "PARKOS_DB_URL=postgresql+psycopg://parkos_app:$AppPassword@127.0.0.1:$DbPort/parkos"
        "DATABASE_URL=postgresql+asyncpg://parkos_app:$AppPassword@127.0.0.1:$DbPort/parkos"
        'PARKOS_CLOUD_API_URL=http://127.0.0.1:1'
        "PARKOS_JWT_KEY_PATH=$JwtKeyPath"
        "PARKOS_SYNC_JWT_PATH=$SyncJwtPath"
        "PORT=$ApiPort"
    )
}

function Write-ParkosLiteEnvFile {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string[]]$Lines)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    Set-Content -Path $Path -Value $Lines -Encoding ASCII
}

function Read-ParkosLiteEnvFile {
    param([Parameter(Mandatory)][string]$Path)
    $map = @{}
    foreach ($line in (Get-Content $Path)) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $idx = $t.IndexOf('=')
        if ($idx -lt 1) { continue }
        $map[$t.Substring(0, $idx)] = $t.Substring($idx + 1)
    }
    return $map
}

# ---------------------------------------------------------------------------
# Estado persistente (un hint; el estado real se verifica probando)
# ---------------------------------------------------------------------------

function New-ParkosLiteState {
    return @{
        sucursal_uuid     = ''
        db_port           = 0
        api_port          = 0
        front_port        = 0
        source_branch     = ''
        api_built_commit  = ''
        steps             = @{}
    }
}

function Read-ParkosLiteState {
    param([Parameter(Mandatory)][string]$Path)
    $state = New-ParkosLiteState
    if (-not (Test-Path $Path)) { return $state }
    try {
        $o = Get-Content $Path -Raw | ConvertFrom-Json
        foreach ($k in 'sucursal_uuid', 'source_branch', 'api_built_commit') {
            if ($null -ne $o.$k) { $state[$k] = [string]$o.$k }
        }
        foreach ($k in 'db_port', 'api_port', 'front_port') {
            if ($null -ne $o.$k) { $state[$k] = [int]$o.$k }
        }
        if ($o.steps) {
            foreach ($p in $o.steps.PSObject.Properties) { $state.steps[$p.Name] = [string]$p.Value }
        }
    } catch {
        return (New-ParkosLiteState)
    }
    return $state
}

function Save-ParkosLiteState {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)][string]$Path)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    ($State | ConvertTo-Json -Depth 5) | Set-Content -Path $Path -Encoding UTF8
}

function Set-ParkosLiteStepState {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)][string]$Key, [Parameter(Mandatory)][string]$Value)
    $State.steps[$Key] = $Value
}

# ---------------------------------------------------------------------------
# Pasos, gating y menu
# ---------------------------------------------------------------------------

function Get-ParkosLiteSteps {
    return @(
        [PSCustomObject]@{ Number = '10'; Key = 'env';     Name = 'Preparar entorno' }
        [PSCustomObject]@{ Number = '11'; Key = 'db';      Name = 'Instalar base de datos' }
        [PSCustomObject]@{ Number = '12'; Key = 'api';     Name = 'Construir API (.exe)' }
        [PSCustomObject]@{ Number = '13'; Key = 'migrate'; Name = 'Migrar base de datos' }
        [PSCustomObject]@{ Number = '14'; Key = 'seed';    Name = 'Cargar datos de demo' }
        [PSCustomObject]@{ Number = '15'; Key = 'front';   Name = 'Instalar dependencias del front' }
    )
}

$script:ParkosLiteStepPrereqs = @{
    env     = @()
    db      = @('env')
    api     = @('env')
    migrate = @('db', 'api')
    seed    = @('migrate')
    front   = @('env')
    start   = @('seed', 'api', 'front')
}

function Get-ParkosLiteStepName {
    param([string]$Key)
    foreach ($s in (Get-ParkosLiteSteps)) { if ($s.Key -eq $Key) { return $s.Name } }
    return $Key
}

# Devuelve $null si el paso esta libre, o el motivo (primer prerrequisito sin
# cumplir) si esta bloqueado. 'start' es la accion "Iniciar todo".
function Get-ParkosLiteBlockReason {
    param([Parameter(Mandatory)][string]$Key, [Parameter(Mandatory)]$Status)
    foreach ($pre in $script:ParkosLiteStepPrereqs[$Key]) {
        if ($Status[$pre] -ne 'ok') {
            $n = (Get-ParkosLiteSteps | Where-Object { $_.Key -eq $pre }).Number
            return "corre primero: $n) $(Get-ParkosLiteStepName -Key $pre)"
        }
    }
    return $null
}

# Menu unico, secuencial y agrupado. Action es la clave que despacha el TUI:
# las de los pasos de instalacion son las Key de Get-ParkosLiteSteps (el estado
# persistente y el gating siguen usando esas keys, no los numeros visibles).
function Get-ParkosLiteMenuItems {
    $items = @(
        @{ Group = 'PRIMERA VEZ'; Action = 'installall'; Name = 'Instalar todo (guiado)' }
        @{ Group = 'USO DIARIO'; Action = 'start'; Name = 'Iniciar todo (DB + API + front)' }
        @{ Group = 'USO DIARIO'; Action = 'stop'; Name = 'Detener todo' }
        @{ Group = 'USO DIARIO'; Action = 'restart'; Name = 'Reiniciar' }
        @{ Group = 'USO DIARIO'; Action = 'status'; Name = 'Estado' }
        @{ Group = 'USO DIARIO'; Action = 'browser'; Name = 'Abrir el navegador' }
        @{ Group = 'USO DIARIO'; Action = 'refresh'; Name = 'Bajar cambios de dev y reiniciar' }
        @{ Group = 'USO DIARIO'; Action = 'logs'; Name = 'Ver logs' }
        @{ Group = 'USO DIARIO'; Action = 'autostart'; Name = 'Arranque automatico de la base de datos' }
    )
    foreach ($s in (Get-ParkosLiteSteps)) {
        $items += @{ Group = 'AVANZADO'; Action = $s.Key; Name = $s.Name }
    }
    $n = 0
    $result = @()
    foreach ($i in $items) {
        $n++
        $result += [PSCustomObject]@{ Number = $n; Group = $i.Group; Action = $i.Action; Name = $i.Name }
    }
    return $result
}

# Entrada del usuario -> clave de accion ('exit' para 0/Q), o $null si no es valida.
function Resolve-ParkosLiteMenuChoice {
    param([AllowNull()][AllowEmptyString()][string]$Choice)
    if ($null -eq $Choice) { return $null }
    $c = $Choice.Trim()
    if ($c -eq '0' -or $c -ieq 'q') { return 'exit' }
    if ($c -notmatch '^[1-9][0-9]*$') { return $null }
    foreach ($i in (Get-ParkosLiteMenuItems)) {
        if ([string]$i.Number -eq $c) { return $i.Action }
    }
    return $null
}

# Lineas del menu (Kind: header | item | exit). Los pasos de instalacion y
# "Iniciar todo" llevan etiqueta de estado [ OK ]/[FAIL]/[BLOQ]/[....].
function Get-ParkosLiteMenuLines {
    param([Parameter(Mandatory)]$Status)
    $lines = @()
    $group = ''
    foreach ($i in (Get-ParkosLiteMenuItems)) {
        if ($i.Group -ne $group) {
            $group = $i.Group
            $title = $group
            if ($group -eq 'AVANZADO') { $title = 'AVANZADO (paso a paso, en este orden)' }
            $lines += [PSCustomObject]@{ Kind = 'header'; Number = $null; Text = " $title"; Color = 'Cyan' }
        }
        $tag = '      '; $color = 'White'; $suffix = ''
        $isStatusItem = ($i.Action -eq 'start') -or ($i.Group -eq 'AVANZADO')
        if ($isStatusItem) {
            $reason = Get-ParkosLiteBlockReason -Key $i.Action -Status $Status
            if ($reason) { $tag = '[BLOQ]'; $color = 'DarkYellow'; $suffix = " ($reason)" }
            elseif ($Status[$i.Action] -eq 'ok') { $tag = '[ OK ]'; $color = 'Green' }
            elseif ($Status[$i.Action] -eq 'fail') { $tag = '[FAIL]'; $color = 'Red'; $suffix = ' (re-ejecutable)' }
            else { $tag = '[....]' }
        }
        if ($i.Action -eq 'installall') { $suffix = '   <- recomendado: hace los pasos 10 a 15 solo y luego inicia todo'; $color = 'Green' }
        $lines += [PSCustomObject]@{ Kind = 'item'; Number = $i.Number; Text = ('  {0} {1}) {2}{3}' -f $tag, $i.Number, $i.Name, $suffix); Color = $color }
    }
    $lines += [PSCustomObject]@{ Kind = 'exit'; Number = 0; Text = '         0) Salir'; Color = 'White' }
    return $lines
}

# Estado real = probe (Facts) + pista del archivo de estado. Nunca se confia
# solo en el archivo: si el artefacto desaparecio el paso vuelve a pending.
function Get-ParkosLiteStepStatus {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)]$Facts)

    $saved = $State.steps
    function _hint($k) { if ($saved -and $saved.ContainsKey($k)) { return $saved[$k] } return '' }

    $r = @{}
    $r.env = 'pending'
    $configReady = (-not $Facts.ContainsKey('ConfigReady')) -or $Facts.ConfigReady
    if (@($Facts.ToolsMissing).Count -eq 0 -and $configReady) { $r.env = 'ok' }

    $r.db = 'pending'
    if ($Facts.PgInstalled -and $Facts.PgInitialized) {
        if ((_hint 'db') -eq 'fail') { $r.db = 'fail' } else { $r.db = 'ok' }
    } elseif ((_hint 'db') -eq 'fail') { $r.db = 'fail' }

    $r.api = 'pending'
    if ($Facts.ApiBuilt -and $Facts.MigrateBuilt) { $r.api = 'ok' }
    elseif ((_hint 'api') -eq 'fail') { $r.api = 'fail' }

    foreach ($pair in @(@('migrate', 'SchemaMigrated'), @('seed', 'Seeded'))) {
        $k = $pair[0]; $fact = $pair[1]
        $r[$k] = 'pending'
        if ($Facts.DbReady) {
            # DB encendida: el probe manda.
            if ($Facts[$fact]) { $r[$k] = 'ok' } elseif ((_hint $k) -eq 'fail') { $r[$k] = 'fail' }
        } else {
            # DB apagada: no se puede probar; se usa la pista guardada.
            $h = _hint $k
            if ($h -eq 'ok' -or $h -eq 'fail') { $r[$k] = $h }
        }
    }

    $r.front = 'pending'
    if ($Facts.FrontInstalled) { $r.front = 'ok' }
    elseif ((_hint 'front') -eq 'fail') { $r.front = 'fail' }
    return $r
}

# Herramientas (git, uv, node, pnpm): ver ParkosLite.Tools.ps1 (sistema o portatiles).

# ---------------------------------------------------------------------------
# Refresh ("bajar cambios de dev")
# ---------------------------------------------------------------------------

function Test-ParkosLiteBranchName {
    param([string]$Branch)
    return [bool]($Branch -match '^[A-Za-z0-9][A-Za-z0-9._/-]*$')
}

# Decide que rehacer segun los archivos que cambio el pull (git diff
# --name-only). Migrar y re-sembrar siempre (idempotentes y baratos).
function Get-ParkosLiteRefreshPlan {
    param([string[]]$ChangedFiles = @(), [Parameter(Mandatory)][bool]$ApiBuilt)

    $files = @($ChangedFiles | ForEach-Object { ($_ -replace '\\', '/') })
    $rebuild = (-not $ApiBuilt)
    $pnpm = $false
    foreach ($f in $files) {
        if ($f -like 'backend/*' -or $f -like 'installer/bootstrap/*') { $rebuild = $true }
        if ($f -eq 'apps/pnpm-lock.yaml' -or $f -eq 'apps/pnpm-workspace.yaml' -or $f -like 'apps/*package.json') { $pnpm = $true }
    }
    return @{ RebuildApi = $rebuild; PnpmInstall = $pnpm; Migrate = $true; Reseed = $true }
}
