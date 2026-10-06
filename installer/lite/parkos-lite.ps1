<#
.SYNOPSIS
    Parkos LITE - instalador/TUI para demos y pruebas de usuario.

.DESCRIPTION
    Levanta una sucursal completa SIN Docker, SIN servicios de Windows, SIN
    Electron, SIN elevacion y SIN conectividad en ejecucion:
      - Postgres 16 local (binarios descargados, proceso de usuario),
      - api-sucursal como .exe (PyInstaller, build-release.ps1),
      - el front React de la sucursal servido por Vite en el navegador,
      - sin job de sync, con datos de demo (tarifas, config, usuarios).
    Postgres, pg_partman, la API (api-sucursal/migrate) y las herramientas
    portatiles git/uv/node/pnpm salen de installer\payload\parts (versionado en
    git): se descarga/compila solo si faltan o si backend/ cambio. Internet solo
    hace falta para pnpm install del front, git pull y reconstruir la API. Compatible con Windows PowerShell 5.1 y pwsh 7.

.PARAMETER LitePath
    Carpeta de trabajo del lite (binarios de Postgres, datos, logs, estado).
    Default: %LOCALAPPDATA%\ParkosLite (fuera del repo y de git).
.PARAMETER SourceBranch
    Rama de la que "Bajar cambios" hace pull (default dev).
.PARAMETER PgPort / ApiPort / FrontPort
    Puertos. 0 = automatico (Postgres desde 5433, API desde 8100, front desde 5173).
.PARAMETER Action
    Menu (default, interactivo) | InstallAll | StartDb | StartAll | StopAll | Status.
    StartDb/StartAll son las que usa el arranque automatico (sin interaccion).
#>
[CmdletBinding()]
param(
    [string]$LitePath,
    [string]$SourceBranch = 'dev',
    [int]$PgPort = 0,
    [int]$ApiPort = 0,
    [int]$FrontPort = 0,
    [ValidateSet('Menu', 'InstallAll', 'StartDb', 'StartAll', 'StopAll', 'Status')][string]$Action = 'Menu'
)

$ErrorActionPreference = 'Stop'
$script:LiteScriptPath = $MyInvocation.MyCommand.Path
$script:LiteRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')
. (Join-Path $PSScriptRoot 'ParkosLite.Core.ps1')
. (Join-Path $PSScriptRoot 'ParkosLite.Db.ps1')
. (Join-Path $PSScriptRoot 'ParkosLite.Tools.ps1')
. (Join-Path $PSScriptRoot 'ParkosLite.Autostart.ps1')
. (Join-Path $PSScriptRoot 'ParkosLite.Run.ps1')

$script:DemoUsers = @(
    @{ Email = 'demo.operador@parkos.local'; Password = 'Demo1234' }
    @{ Email = 'demo.operador2@parkos.local'; Password = 'Demo1234' }
)

function New-ParkosLiteContext {
    param([string]$LitePath, [string]$Branch, [int]$Db, [int]$Api, [int]$Front)
    if (-not $LitePath) { $LitePath = Get-ParkosLiteDefaultPath }
    $paths = Get-ParkosLitePaths -LitePath $LitePath -RepoRoot $script:LiteRepoRoot
    New-Item -ItemType Directory -Force -Path $paths.Lite, $paths.Logs, $paths.Run | Out-Null
    # Si ya hay herramientas portatiles en <lite>	ools, solo este proceso y sus hijos las ven.
    Enable-ParkosLiteToolchainEnv -LitePath $paths.Lite | Out-Null
    $logFile = Join-Path $paths.Logs 'lite.log'
    $logger = {
        param($m)
        Write-Host $m
        Add-Content -Path $logFile -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    }.GetNewClosure()
    return @{
        Paths      = $paths
        State      = (Read-ParkosLiteState -Path $paths.State)
        Secrets    = (Read-ParkosLiteSecrets -Path $paths.Secrets)
        Branch     = $Branch
        Logger     = $logger
        ScriptPath = $script:LiteScriptPath
        Requested  = @{ Db = $Db; Api = $Api; Front = $Front }
    }
}

function Get-ParkosLiteFacts {
    param([Parameter(Mandatory)]$Ctx)
    $p = $Ctx.Paths
    $facts = @{
        ToolsMissing   = @(Get-ParkosLiteMissingTools -LitePath $p.Lite | ForEach-Object { $_.Name })
        ConfigReady    = ((Test-ParkosUuidV4 -Value $Ctx.State.sucursal_uuid) -and (Test-Path $p.EnvFile) -and $Ctx.State.db_port -gt 0)
        PgInstalled    = (Test-Path (Join-Path $p.PgRoot 'bin\pg_ctl.exe'))
        PgInitialized  = ((Test-Path (Join-Path $p.PgData 'PG_VERSION')) -and (Test-Path $p.Secrets))
        ApiBuilt       = (Test-Path $p.ApiExe)
        MigrateBuilt   = (Test-Path $p.MigrateExe)
        FrontInstalled = (Test-Path (Join-Path $p.FrontDir 'node_modules\vite\bin\vite.js'))
    }
    $db = @{ DbReady = $false; SchemaMigrated = $false; Seeded = $false }
    if ($facts.PgInstalled -and $Ctx.Secrets) {
        $db = Get-ParkosLiteDbFacts -Paths $p -Port $Ctx.State.db_port -Secrets $Ctx.Secrets -SucursalUuid $Ctx.State.sucursal_uuid
    }
    foreach ($k in $db.Keys) { $facts[$k] = $db[$k] }
    return $facts
}

function Get-ParkosLiteCurrentStatus {
    param([Parameter(Mandatory)]$Ctx)
    return (Get-ParkosLiteStepStatus -State $Ctx.State -Facts (Get-ParkosLiteFacts -Ctx $Ctx))
}

# Corre un paso (con gating real: refuta si un prerrequisito no esta ok) y
# registra ok/fail en el estado persistente. Devuelve $true/$false.
function Invoke-ParkosLiteTuiStep {
    param([Parameter(Mandatory)]$Ctx, [Parameter(Mandatory)][string]$Key)
    $status = Get-ParkosLiteCurrentStatus -Ctx $Ctx
    $reason = Get-ParkosLiteBlockReason -Key $Key -Status $status
    if ($reason) {
        Write-Host "  Bloqueado: $reason" -ForegroundColor Yellow
        return $false
    }
    $name = Get-ParkosLiteStepName -Key $Key
    Write-Host ''
    Write-Host "=== $name ===" -ForegroundColor Cyan
    try {
        Invoke-ParkosLiteStep -Ctx $Ctx -Key $Key
        Set-ParkosLiteStepState -State $Ctx.State -Key $Key -Value 'ok'
        Save-ParkosLiteState -State $Ctx.State -Path $Ctx.Paths.State
        Write-Host "[ OK ] $name" -ForegroundColor Green
        return $true
    } catch {
        Set-ParkosLiteStepState -State $Ctx.State -Key $Key -Value 'fail'
        Save-ParkosLiteState -State $Ctx.State -Path $Ctx.Paths.State
        & $Ctx.Logger "[FAIL] $name : $($_.Exception.Message)"
        Write-Host "[FAIL] $name" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        return $false
    }
}

# Pasos caros que no se repiten en el guiado si ya estan hechos (migrar y
# sembrar si corren siempre: son baratos e idempotentes).
$script:LiteSkipWhenOk = @('db', 'api', 'front')
$script:LiteStepHints = @{
    env     = 'unos segundos a 1 minuto; git/uv/node/pnpm portatiles salen del repositorio (sin Internet, sin admin)'
    db      = 'rearma Postgres y pg_partman desde el repositorio (sin Internet): 1 a 3 minutos la primera vez'
    api     = 'restaura la API del repositorio (segundos); solo compila si backend/ cambio (3 a 10 minutos, necesita Internet)'
    migrate = 'menos de 1 minuto'
    seed    = 'unos segundos'
    front   = 'descarga dependencias del front (unico paso que necesita Internet): 1 a 5 minutos la primera vez'
}

function Invoke-ParkosLiteInstallAll {
    param([Parameter(Mandatory)]$Ctx)
    Write-Host ''
    Write-Host 'INSTALACION GUIADA: deja esta ventana abierta, no necesitas hacer nada mas.' -ForegroundColor Cyan
    Write-Host 'Internet solo hace falta para las dependencias del front (pnpm install). Total estimado: 3 a 10 minutos la primera vez (segundos si ya estaba instalado).'
    $steps = @(Get-ParkosLiteSteps)
    $n = 0
    foreach ($s in $steps) {
        $n++
        $status = Get-ParkosLiteCurrentStatus -Ctx $Ctx
        if (($script:LiteSkipWhenOk -contains $s.Key) -and $status[$s.Key] -eq 'ok') {
            Write-Host ("Paso {0} de {1}: {2} - ya estaba hecho, se omite." -f $n, ($steps.Count + 1), $s.Name) -ForegroundColor DarkGray
            continue
        }
        Write-Host ''
        Write-Host ("Paso {0} de {1}: {2}  ({3})" -f $n, ($steps.Count + 1), $s.Name, $script:LiteStepHints[$s.Key]) -ForegroundColor White
        if (-not (Invoke-ParkosLiteTuiStep -Ctx $Ctx -Key $s.Key)) {
            Write-Host ''
            Write-Host "La instalacion se detuvo en el paso $($s.Number)) $($s.Name)." -ForegroundColor Yellow
            Write-Host "  Que hacer: lee el mensaje rojo de arriba, corrige lo que indica (internet, herramienta faltante, espacio en disco) y elige la opcion 1 otra vez: retoma donde quedo." -ForegroundColor Yellow
            Write-Host "  Detalle tecnico: opcion 8 (Ver logs) o la carpeta $($Ctx.Paths.Logs)" -ForegroundColor Yellow
            return $false
        }
    }
    Write-Host ''
    Write-Host ("Paso {0} de {0}: Iniciar base de datos, API y front  (1 a 2 minutos)" -f ($steps.Count + 1)) -ForegroundColor White
    return (Invoke-ParkosLiteStart -Ctx $Ctx)
}

function Show-ParkosLiteSummary {
    param([Parameter(Mandatory)]$Ctx)
    $u = Get-ParkosLiteUrls -ApiPort $Ctx.State.api_port -FrontPort $Ctx.State.front_port
    $line = ('=' * 62)
    Write-Host ''
    Write-Host $line -ForegroundColor Green
    Write-Host '  PARKOS LITE LISTO' -ForegroundColor Green
    Write-Host $line -ForegroundColor Green
    Write-Host ("  Abre en el navegador : {0}" -f $u.Front) -ForegroundColor Green
    Write-Host ("  Usuario demo         : {0}" -f $script:DemoUsers[0].Email)
    Write-Host ("  Clave                : {0}" -f $script:DemoUsers[0].Password)
    Write-Host ("  Segundo usuario      : {0}  (misma clave)" -f $script:DemoUsers[1].Email)
    Write-Host ("  API (para soporte)   : {0}   docs: {1}" -f $u.ApiHealth, $u.ApiDocs)
    Write-Host '  Para detener         : opcion 3 de este menu (o -Action StopAll)'
    Write-Host '  Para ver el estado   : opcion 5.   Si algo falla: opcion 8 (Ver logs).'
    Write-Host '  Al reiniciar el PC   : la base de datos arranca sola; para el resto usa la opcion 2 (Iniciar todo).'
    Write-Host $line -ForegroundColor Green
}

function Invoke-ParkosLiteStart {
    param([Parameter(Mandatory)]$Ctx)
    $status = Get-ParkosLiteCurrentStatus -Ctx $Ctx
    $reason = Get-ParkosLiteBlockReason -Key 'start' -Status $status
    if ($reason) { Write-Host "  Bloqueado: $reason" -ForegroundColor Yellow; return $false }
    try {
        Start-ParkosLiteAll -Ctx $Ctx
        $u = Get-ParkosLiteUrls -ApiPort $Ctx.State.api_port -FrontPort $Ctx.State.front_port
        Show-ParkosLiteSummary -Ctx $Ctx
        return $true
    } catch {
        & $Ctx.Logger "[FAIL] iniciar: $($_.Exception.Message)"
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-Host '  Que hacer: opcion 8 para ver los logs, o opcion 4 (Reiniciar) otra vez.' -ForegroundColor Yellow
        return $false
    }
}

function Show-ParkosLiteStatus {
    param([Parameter(Mandatory)]$Ctx)
    $p = $Ctx.Paths; $s = $Ctx.State
    $u = Get-ParkosLiteUrls -ApiPort $s.api_port -FrontPort $s.front_port
    $dbUp = $false
    if ($Ctx.Secrets -and $s.db_port -gt 0 -and (Test-Path (Join-Path $p.PgRoot 'bin\pg_isready.exe'))) { $dbUp = Test-ParkosLitePgAccepting -PgRoot $p.PgRoot -Port $s.db_port }
    $apiPid = Get-ParkosLiteLivePid -Paths $p -Name 'api' -ExpectedProcess 'api-sucursal'
    $frPid = Get-ParkosLiteLivePid -Paths $p -Name 'front' -ExpectedProcess 'node'
    $health = 0
    if ($apiPid) { $health = Invoke-ParkosLiteHttpGet -Url $u.ApiHealth }
    $front = 0
    if ($frPid) { $front = Invoke-ParkosLiteHttpGet -Url $u.Front }

    Write-Host ''
    Write-Host '--- Estado ---' -ForegroundColor Cyan
    Write-Host ("  Postgres : {0} (127.0.0.1:{1})" -f $(if ($dbUp) { 'ARRIBA' } else { 'abajo' }), $s.db_port)
    Write-Host ("  API      : {0} pid={1} puerto={2} /health={3}" -f $(if ($apiPid) { 'ARRIBA' } else { 'abajo' }), $apiPid, $s.api_port, $health)
    Write-Host ("  Front    : {0} pid={1} puerto={2} http={3}" -f $(if ($frPid) { 'ARRIBA' } else { 'abajo' }), $frPid, $s.front_port, $front)
    Write-Host ("  Sucursal : {0}" -f $s.sucursal_uuid)
    Write-Host '  Herramientas (sistema o portatil en <lite>	ools):'
    foreach ($l in (Format-ParkosLiteToolLines -Status (Get-ParkosLiteToolStatus -LitePath $p.Lite))) { Write-Host $l }
    Write-Host ("  Rama     : {0}   Commit del exe: {1}" -f $Ctx.Branch, $s.api_built_commit)
    Write-Host ('  ' + (Format-ParkosLiteAutostartLine -Status (Get-ParkosLiteAutostartStatus)))
    Write-Host ("  URL front: {0}" -f $u.Front)
    Write-Host ("  API      : {0}   docs: {1}" -f $u.ApiHealth, $u.ApiDocs)
    Write-Host '  Usuarios demo (solo pruebas locales):'
    foreach ($d in $script:DemoUsers) { Write-Host ("    {0}  /  {1}" -f $d.Email, $d.Password) }
    Write-Host ("  Carpeta lite: {0}" -f $p.Lite)
}

function Show-ParkosLiteLogs {
    param([Parameter(Mandatory)]$Ctx)
    $files = @('lite.log', 'api.err.log', 'api.out.log', 'front.err.log', 'front.out.log', 'postgres.log', 'build-api.log', 'pnpm-install.log')
    $i = 1
    foreach ($f in $files) { Write-Host ("  {0}) {1}" -f $i, $f); $i++ }
    $sel = Read-Host 'Cual log (numero, Enter = lite.log)'
    $n = 1
    if ($sel -match '^\d+$') { $n = [int]$sel }
    if ($n -lt 1 -or $n -gt $files.Count) { $n = 1 }
    $path = Join-Path $Ctx.Paths.Logs $files[$n - 1]
    if (-not (Test-Path $path)) { Write-Host "  (sin $($files[$n - 1]) todavia)"; return }
    Write-Host "--- ultimas 40 lineas de $path ---" -ForegroundColor Cyan
    Get-Content $path -Tail 40
}

function Invoke-ParkosLiteAutostartMenu {
    param([Parameter(Mandatory)]$Ctx)
    Write-Host ''
    Write-Host ('  ' + (Format-ParkosLiteAutostartLine -Status (Get-ParkosLiteAutostartStatus)))
    Write-Host '  1) Activar: solo base de datos (tarea de usuario, sin admin)'
    Write-Host '  2) Activar: base de datos + API + front'
    Write-Host '  3) Desactivar'
    if (Test-ParkosLiteElevated) { Write-Host '  4) Activar como servicio de Windows (requiere admin; estas elevado)' }
    $sel = Read-Host 'Opcion (Enter = cancelar)'
    try {
        switch ($sel) {
            '1' { $r = Enable-ParkosLiteAutostart -Paths $Ctx.Paths -ScriptPath $Ctx.ScriptPath; Write-Host "Activado ($($r.Method))." -ForegroundColor Green }
            '2' { $r = Enable-ParkosLiteAutostart -Paths $Ctx.Paths -ScriptPath $Ctx.ScriptPath -IncludeApp; Write-Host "Activado ($($r.Method), con API y front)." -ForegroundColor Green }
            '3' {
                $r = Disable-ParkosLiteAutostart -Paths $Ctx.Paths
                Write-Host 'Desactivado.' -ForegroundColor Green
                foreach ($w in $r.Warnings) { Write-Host $w -ForegroundColor Yellow }
            }
            '4' {
                if (Test-ParkosLiteElevated) { Enable-ParkosLiteAutostart -Paths $Ctx.Paths -ScriptPath $Ctx.ScriptPath -Method service | Out-Null; Write-Host 'Servicio ParkosLiteDb registrado (inicio automatico).' -ForegroundColor Green }
            }
        }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}

function Invoke-ParkosLiteMenu {
    param([Parameter(Mandatory)]$Ctx)
    while ($true) {
        $status = Get-ParkosLiteCurrentStatus -Ctx $Ctx
        Write-Host ''
        Write-Host '=============== PARKOS LITE (demo) ===============' -ForegroundColor Cyan
        foreach ($l in (Get-ParkosLiteMenuLines -Status $status)) { Write-Host $l.Text -ForegroundColor $l.Color }
        $action = Resolve-ParkosLiteMenuChoice -Choice (Read-Host 'Opcion (numero)')
        switch ($action) {
            'exit' { return }
            'installall' { Invoke-ParkosLiteInstallAll -Ctx $Ctx | Out-Null }
            'start' { Invoke-ParkosLiteStart -Ctx $Ctx | Out-Null }
            'stop' { Stop-ParkosLiteAll -Ctx $Ctx; Write-Host 'Detenido.' -ForegroundColor Green }
            'restart' { Stop-ParkosLiteAll -Ctx $Ctx; Invoke-ParkosLiteStart -Ctx $Ctx | Out-Null }
            'status' { Show-ParkosLiteStatus -Ctx $Ctx }
            'browser' { $u = Get-ParkosLiteUrls -ApiPort $Ctx.State.api_port -FrontPort $Ctx.State.front_port; Start-Process $u.Front }
            'refresh' {
                try { Invoke-ParkosLiteRefresh -Ctx $Ctx; Write-Host 'Cambios aplicados.' -ForegroundColor Green }
                catch { & $Ctx.Logger "[FAIL] refresh: $($_.Exception.Message)"; Write-Host $_.Exception.Message -ForegroundColor Red }
            }
            'logs' { Show-ParkosLiteLogs -Ctx $Ctx }
            'autostart' { Invoke-ParkosLiteAutostartMenu -Ctx $Ctx }
            { $_ -in 'env', 'db', 'api', 'migrate', 'seed', 'front' } { Invoke-ParkosLiteTuiStep -Ctx $Ctx -Key $action | Out-Null }
            default { Write-Host 'Opcion no valida, elige un numero de la lista' -ForegroundColor Yellow }
        }
    }
}

# --- Punto de entrada (no corre si se dot-sourcea) ---------------------------
if ($MyInvocation.InvocationName -ne '.') {
    $ctx = New-ParkosLiteContext -LitePath $LitePath -Branch $SourceBranch -Db $PgPort -Api $ApiPort -Front $FrontPort
    try {
        switch ($Action) {
            'Menu' { Invoke-ParkosLiteMenu -Ctx $ctx }
            'InstallAll' { if (-not (Invoke-ParkosLiteInstallAll -Ctx $ctx)) { exit 1 } }
            'StartDb' { Start-ParkosLiteAll -Ctx $ctx -DbOnly }
            'StartAll' { Start-ParkosLiteAll -Ctx $ctx }
            'StopAll' { Stop-ParkosLiteAll -Ctx $ctx }
            'Status' { Show-ParkosLiteStatus -Ctx $ctx }
        }
    } catch {
        & $ctx.Logger "[FAIL] $Action : $($_.Exception.Message)"
        exit 1
    }
}
