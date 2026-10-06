# Parkos LITE - ejecucion: configuracion inicial, procesos (API exe + Vite),
# 'Iniciar/Detener todo', pasos de instalacion y refresh desde dev.
#
# Solo funciones. $Ctx = @{ Paths; State; Secrets; Branch; Logger; ScriptPath;
# Requested } (lo arma parkos-lite.ps1). Procesos, red, git, builds y pnpm
# estan en wrappers pequenos que los tests mockean. PowerShell 5.1 compatible.
# Requiere los otros ParkosLite.*.ps1 y shared\ParkosPostgresDownload.ps1.

function Write-ParkosLiteLog {
    param($Ctx, [string]$Message)
    if ($Ctx -and $Ctx.Logger) { & $Ctx.Logger $Message } else { Write-Host $Message }
}

# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------

function New-ParkosLiteJwtKey {
    param([Parameter(Mandatory)][string]$Path, [int]$Bytes = 64)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    $b = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($b) } finally { $rng.Dispose() }
    [System.IO.File]::WriteAllBytes($Path, $b)
}

function Get-ParkosLiteNodePath {
    $c = Get-Command node -ErrorAction SilentlyContinue
    if (-not $c) { throw 'No se encontro node en el PATH (paso 1: Preparar entorno).' }
    return $c.Source
}

# Lanza un proceso oculto con stdout/stderr a archivos y variables de entorno
# solo para ese hijo. Devuelve el PID.
function Start-ParkosLiteProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory,
        [hashtable]$Env = @{},
        [Parameter(Mandatory)][string]$StdOut,
        [Parameter(Mandatory)][string]$StdErr
    )
    New-Item -ItemType Directory -Force -Path (Split-Path $StdOut) | Out-Null
    $saved = @{}
    foreach ($k in $Env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$Env[$k], 'Process')
    }
    try {
        $sp = @{ FilePath = $FilePath; WindowStyle = 'Hidden'; PassThru = $true; RedirectStandardOutput = $StdOut; RedirectStandardError = $StdErr }
        if ($Arguments.Count -gt 0) { $sp.ArgumentList = $Arguments }
        if ($WorkingDirectory) { $sp.WorkingDirectory = $WorkingDirectory }
        $p = Start-Process @sp
        return $p.Id
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
}

function Stop-ParkosLiteProcessTree {
    param([Parameter(Mandatory)][int]$ProcessId)
    & taskkill.exe /PID $ProcessId /T /F | Out-Null
}

function Invoke-ParkosLiteHttpGet {
    param([Parameter(Mandatory)][string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

function Invoke-ParkosLiteGit {
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string[]]$Arguments)
    return (Invoke-ParkosLiteNative -FilePath 'git' -Arguments (@('-C', $RepoRoot) + $Arguments))
}

function Invoke-ParkosLiteBuildScript {
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$LogPath)
    New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
    $ps = (Get-Process -Id $PID).Path
    & $ps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot 'installer\build-release.ps1') -ApiSucursal -Migrate *>&1 | Tee-Object -FilePath $LogPath | ForEach-Object { Write-Host $_ }
    return $LASTEXITCODE
}

# Fecha de la ultima modificacion de los fuentes que entran al exe (backend/ e
# installer/bootstrap/, tracked + untracked no ignorados: cubre tambien cambios
# locales sin commit). $null si no se puede saber.
function Get-ParkosLiteApiSourceNewestWrite {
    param([Parameter(Mandatory)][string]$RepoRoot)
    $r = Invoke-ParkosLiteGit -RepoRoot $RepoRoot -Arguments @('ls-files', '-co', '--exclude-standard', '--', 'backend', 'installer/bootstrap')
    if ($r.ExitCode -ne 0) { return $null }
    $newest = $null
    foreach ($rel in @($r.Output | Where-Object { $_ -and $_.Trim() })) {
        $f = Join-Path $RepoRoot $rel.Trim()
        if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { continue }
        $t = (Get-Item -LiteralPath $f).LastWriteTimeUtc
        if (-not $newest -or $t -gt $newest) { $newest = $t }
    }
    return $newest
}

# $true si hay que (re)construir api-sucursal.exe/migrate.exe: faltan, o algun
# fuente es mas nuevo que el exe mas viejo. Si no se puede saber, construye.
function Test-ParkosLiteApiBuildNeeded {
    param([Parameter(Mandatory)]$Paths)
    if (-not ((Test-Path $Paths.ApiExe) -and (Test-Path $Paths.MigrateExe))) { return $true }
    $exeTime = @((Get-Item $Paths.ApiExe).LastWriteTimeUtc, (Get-Item $Paths.MigrateExe).LastWriteTimeUtc) | Sort-Object | Select-Object -First 1
    $src = Get-ParkosLiteApiSourceNewestWrite -RepoRoot $Paths.RepoRoot
    if (-not $src) { return $true }
    return ($src -gt $exeTime)
}

function Invoke-ParkosLitePnpmInstall {
    param([Parameter(Mandatory)][string]$AppsDir, [Parameter(Mandatory)][string]$LogPath)
    New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
    # --ignore-scripts: no baja el binario de Electron (el lite usa el navegador).
    # --lockfile=false: el lockfile del repo puede ir desfasado de los package.json
    # (--frozen falla) y asi un install del lite nunca ensucia el arbol git.
    Push-Location $AppsDir
    try {
        & pnpm install --ignore-scripts --frozen-lockfile=false --lockfile=false --config.confirmModulesPurge=false *>&1 | Tee-Object -FilePath $LogPath | ForEach-Object { if ("$_" -notmatch '^Progress:') { Write-Host $_ } }
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Configuracion inicial (uuid, secretos, puertos, llave jwt, env file)
# ---------------------------------------------------------------------------

function Initialize-ParkosLiteConfig {
    param(
        [Parameter(Mandatory)]$Ctx,
        [int]$DbPortRequested = 0,
        [int]$ApiPortRequested = 0,
        [int]$FrontPortRequested = 0
    )
    $paths = $Ctx.Paths
    $state = $Ctx.State

    if (-not (Test-ParkosUuidV4 -Value $state.sucursal_uuid)) {
        $state.sucursal_uuid = [guid]::NewGuid().ToString()
    }

    $secrets = Read-ParkosLiteSecrets -Path $paths.Secrets
    if (-not $secrets) {
        $secrets = New-ParkosLiteSecrets
        Save-ParkosLiteSecrets -Path $paths.Secrets -Secrets $secrets
    }
    $Ctx.Secrets = $secrets

    $dbOwned = $false
    if ($state.db_port -gt 0) {
        try { $dbOwned = [bool](Test-ParkosLitePgAccepting -PgRoot $paths.PgRoot -Port $state.db_port) } catch { $dbOwned = $false }
    }
    $state.db_port = Resolve-ParkosLitePort -Requested $DbPortRequested -Persisted $state.db_port -Start 5433 -OwnedByLite:$dbOwned -Name 'Postgres'
    $apiOwned = [bool](Get-ParkosLiteLivePid -Paths $paths -Name 'api' -ExpectedProcess 'api-sucursal')
    $state.api_port = Resolve-ParkosLitePort -Requested $ApiPortRequested -Persisted $state.api_port -Start 8100 -OwnedByLite:$apiOwned -Exclude @($state.db_port) -Name 'la API'
    $frontOwned = [bool](Get-ParkosLiteLivePid -Paths $paths -Name 'front' -ExpectedProcess 'node')
    $state.front_port = Resolve-ParkosLitePort -Requested $FrontPortRequested -Persisted $state.front_port -Start 5173 -OwnedByLite:$frontOwned -Exclude @($state.db_port, $state.api_port) -Name 'el front'

    if (-not (Test-Path $paths.JwtKey)) { New-ParkosLiteJwtKey -Path $paths.JwtKey }

    $lines = Get-ParkosLiteEnvLines -SucursalUuid $state.sucursal_uuid -AppPassword $secrets.AppPassword -DbPort $state.db_port -ApiPort $state.api_port -JwtKeyPath $paths.JwtKey -SyncJwtPath $paths.SyncJwt
    Write-ParkosLiteEnvFile -Path $paths.EnvFile -Lines $lines
    Save-ParkosLiteState -State $state -Path $paths.State
}

# ---------------------------------------------------------------------------
# Procesos
# ---------------------------------------------------------------------------

function Save-ParkosLitePid {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][int]$ProcessId)
    New-Item -ItemType Directory -Force -Path $Paths.Run | Out-Null
    Set-Content -Path (Join-Path $Paths.Run "$Name.pid") -Value "$ProcessId" -Encoding ASCII
}

# PID del servicio SOLO si el proceso existe Y es el esperado (un pid file viejo
# o un PID reutilizado por otro programa devuelve $null).
function Get-ParkosLiteLivePid {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$ExpectedProcess)
    $f = Join-Path $Paths.Run "$Name.pid"
    if (-not (Test-Path $f)) { return $null }
    $n = 0
    if (-not [int]::TryParse((Get-Content $f -Raw).Trim(), [ref]$n)) { return $null }
    $pname = Get-ParkosLiteProcessName -ProcessId $n
    if ($pname -and $pname -eq $ExpectedProcess) { return $n }
    return $null
}

function Get-ParkosLiteViteArguments {
    param([Parameter(Mandatory)][string]$ViteJs, [Parameter(Mandatory)][int]$Port)
    return @("`"$ViteJs`"", '--port', "$Port", '--host', '127.0.0.1', '--strictPort')
}

function Start-ParkosLiteApi {
    param([Parameter(Mandatory)]$Ctx)
    $paths = $Ctx.Paths
    $existing = Get-ParkosLiteLivePid -Paths $paths -Name 'api' -ExpectedProcess 'api-sucursal'
    if ($existing) { return $existing }
    if (-not (Test-Path $paths.EnvFile)) { throw 'Falta el archivo de configuracion de la API: corre el paso 1) Preparar entorno.' }
    $envMap = Read-ParkosLiteEnvFile -Path $paths.EnvFile
    $p = Start-ParkosLiteProcess -FilePath $paths.ApiExe -WorkingDirectory (Split-Path $paths.ApiExe) -Env $envMap -StdOut (Join-Path $paths.Logs 'api.out.log') -StdErr (Join-Path $paths.Logs 'api.err.log')
    Save-ParkosLitePid -Paths $paths -Name 'api' -ProcessId $p
    return $p
}

function Start-ParkosLiteFront {
    param([Parameter(Mandatory)]$Ctx)
    $paths = $Ctx.Paths
    $existing = Get-ParkosLiteLivePid -Paths $paths -Name 'front' -ExpectedProcess 'node'
    if ($existing) { return $existing }
    $viteJs = Join-Path $paths.FrontDir 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path $viteJs)) { throw 'Vite no esta instalado: corre el paso 6) Instalar dependencias del front.' }
    $node = Get-ParkosLiteNodePath
    $p = Start-ParkosLiteProcess -FilePath $node -Arguments (Get-ParkosLiteViteArguments -ViteJs $viteJs -Port $Ctx.State.front_port) -WorkingDirectory $paths.FrontDir -Env @{ PARKOS_API_PORT = "$($Ctx.State.api_port)" } -StdOut (Join-Path $paths.Logs 'front.out.log') -StdErr (Join-Path $paths.Logs 'front.err.log')
    Save-ParkosLitePid -Paths $paths -Name 'front' -ProcessId $p
    return $p
}

function Stop-ParkosLiteService {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$ExpectedProcess)
    $live = Get-ParkosLiteLivePid -Paths $Paths -Name $Name -ExpectedProcess $ExpectedProcess
    $stopped = $false
    if ($live) {
        Stop-ParkosLiteProcessTree -ProcessId $live
        $stopped = $true
    }
    Remove-Item (Join-Path $Paths.Run "$Name.pid") -Force -ErrorAction SilentlyContinue
    return $stopped
}

function Wait-ParkosLiteHttp {
    param([Parameter(Mandatory)][string]$Url, [int]$TimeoutSec = 60, [int]$ExpectStatus = 200)
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        if ((Invoke-ParkosLiteHttpGet -Url $Url) -eq $ExpectStatus) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Start-ParkosLiteAll {
    param([Parameter(Mandatory)]$Ctx, [switch]$DbOnly)
    $paths = $Ctx.Paths
    $state = $Ctx.State
    Start-ParkosLitePg -Paths $paths -Port $state.db_port | Out-Null
    Write-ParkosLiteLog $Ctx "Postgres listo en 127.0.0.1:$($state.db_port)"
    if ($DbOnly) { return }

    $urls = Get-ParkosLiteUrls -ApiPort $state.api_port -FrontPort $state.front_port
    Start-ParkosLiteApi -Ctx $Ctx | Out-Null
    if (-not (Wait-ParkosLiteHttp -Url $urls.ApiHealth -TimeoutSec 90)) {
        throw "La API no respondio en $($urls.ApiHealth). Revisa $(Join-Path $paths.Logs 'api.err.log') y api.out.log"
    }
    Write-ParkosLiteLog $Ctx "API lista: $($urls.ApiHealth)"
    Start-ParkosLiteFront -Ctx $Ctx | Out-Null
    if (-not (Wait-ParkosLiteHttp -Url $urls.Front -TimeoutSec 90)) {
        throw "El front no respondio en $($urls.Front). Revisa $(Join-Path $paths.Logs 'front.err.log') y front.out.log"
    }
    Write-ParkosLiteLog $Ctx "Front listo: $($urls.Front)"
}

function Stop-ParkosLiteAll {
    param([Parameter(Mandatory)]$Ctx, [switch]$KeepDb)
    Stop-ParkosLiteService -Paths $Ctx.Paths -Name 'front' -ExpectedProcess 'node' | Out-Null
    Stop-ParkosLiteService -Paths $Ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal' | Out-Null
    if (-not $KeepDb) { Stop-ParkosLitePg -Paths $Ctx.Paths | Out-Null }
}

# ---------------------------------------------------------------------------
# Pasos de instalacion
# ---------------------------------------------------------------------------

function Invoke-ParkosLiteStep {
    param([Parameter(Mandatory)]$Ctx, [Parameter(Mandatory)][string]$Key)
    $paths = $Ctx.Paths
    $state = $Ctx.State
    switch ($Key) {
        'env' {
            $missing = @(Get-ParkosLiteMissingTools)
            if ($missing.Count -gt 0) {
                $msg = "Faltan herramientas:`n" + (($missing | ForEach-Object { "  - $($_.Name): $($_.Hint)" }) -join "`n") + "`nInstalalas, abre una consola nueva y reintenta."
                throw $msg
            }
            $req = $Ctx.Requested
            if (-not $req) { $req = @{ Db = 0; Api = 0; Front = 0 } }
            Initialize-ParkosLiteConfig -Ctx $Ctx -DbPortRequested $req.Db -ApiPortRequested $req.Api -FrontPortRequested $req.Front
            Write-ParkosLiteLog $Ctx "Sucursal lite: $($state.sucursal_uuid) | puertos DB $($state.db_port), API $($state.api_port), front $($state.front_port)"
        }
        'db' {
            Install-ParkosLiteDatabase -Paths $paths -Port $state.db_port -Secrets $Ctx.Secrets -Logger $Ctx.Logger
            try {
                $r = Enable-ParkosLiteAutostart -Paths $paths -ScriptPath $Ctx.ScriptPath
                Write-ParkosLiteLog $Ctx "Arranque automatico de la base de datos activado ($($r.Method)). Se puede quitar con la opcion A."
            } catch {
                Write-ParkosLiteLog $Ctx "No se pudo activar el arranque automatico (no es critico): $($_.Exception.Message)"
            }
        }
        'api' {
            if (-not (Test-ParkosLiteApiBuildNeeded -Paths $paths)) {
                Write-ParkosLiteLog $Ctx 'La API (api-sucursal.exe y migrate.exe) ya esta construida y el codigo no cambio: se omite el build.'
                if (-not $state.api_built_commit) {
                    $head = Invoke-ParkosLiteGit -RepoRoot $paths.RepoRoot -Arguments @('rev-parse', 'HEAD')
                    if ($head.ExitCode -eq 0) { $state.api_built_commit = ($head.Output -join '').Trim() }
                }
                return
            }
            Write-ParkosLiteLog $Ctx 'Construyendo la API (PyInstaller). Tarda entre 3 y 10 minutos la primera vez; no cierres la ventana.'
            # El build reemplaza los .exe: si el nuestro esta corriendo, Windows bloquea los archivos.
            Stop-ParkosLiteService -Paths $paths -Name 'api' -ExpectedProcess 'api-sucursal' | Out-Null
            $rc = Invoke-ParkosLiteBuildScript -RepoRoot $paths.RepoRoot -LogPath (Join-Path $paths.Logs 'build-api.log')
            if ($rc -ne 0) { throw "build-release.ps1 fallo (exit $rc). Revisa $(Join-Path $paths.Logs 'build-api.log')" }
            if (-not ((Test-Path $paths.ApiExe) -and (Test-Path $paths.MigrateExe))) { throw 'El build termino pero faltan api-sucursal.exe o migrate.exe.' }
            $head = Invoke-ParkosLiteGit -RepoRoot $paths.RepoRoot -Arguments @('rev-parse', 'HEAD')
            if ($head.ExitCode -eq 0) { $state.api_built_commit = ($head.Output -join '').Trim() }
        }
        'migrate' {
            Start-ParkosLitePg -Paths $paths -Port $state.db_port | Out-Null
            Invoke-ParkosLiteMigrate -Paths $paths -Port $state.db_port -Secrets $Ctx.Secrets
            if (-not (Invoke-ParkosLiteEnsurePartitions -Paths $paths -Port $state.db_port -Secrets $Ctx.Secrets)) {
                Write-ParkosLiteLog $Ctx 'Aviso: prod.fn_ensure_partitions() no se pudo ejecutar (no bloquea).'
            }
        }
        'seed' {
            Start-ParkosLitePg -Paths $paths -Port $state.db_port | Out-Null
            $out = Invoke-ParkosLiteSeed -Paths $paths -Port $state.db_port -Secrets $Ctx.Secrets -SucursalUuid $state.sucursal_uuid
            Write-ParkosLiteLog $Ctx (($out | Select-Object -Last 8) -join "`n")
        }
        'front' {
            # Vite mantiene abiertos esbuild.exe y node_modules: pnpm no puede reemplazarlos.
            Stop-ParkosLiteService -Paths $paths -Name 'front' -ExpectedProcess 'node' | Out-Null
            Write-ParkosLiteLog $Ctx 'Instalando dependencias del front (pnpm). Puede tardar varios minutos; es normal que no muestre avance continuo.'
            $rc = Invoke-ParkosLitePnpmInstall -AppsDir $paths.AppsDir -LogPath (Join-Path $paths.Logs 'pnpm-install.log')
            if ($rc -ne 0) { throw "pnpm install fallo (exit $rc). Revisa $(Join-Path $paths.Logs 'pnpm-install.log')" }
        }
        default { throw "Paso desconocido: $Key" }
    }
}

# ---------------------------------------------------------------------------
# Refresh: bajar cambios de dev y reiniciar
# ---------------------------------------------------------------------------

function Invoke-ParkosLiteGitChecked {
    param([string]$RepoRoot, [string[]]$Arguments, [string]$Failure)
    $r = Invoke-ParkosLiteGit -RepoRoot $RepoRoot -Arguments $Arguments
    if ($r.ExitCode -ne 0) { throw "$Failure ($($r.Output -join ' '))" }
    return $r
}

# fetch + checkout + pull --ff-only (mismo criterio que Update-SourceFromBranch
# del instalador completo) con guardas: nombre de rama y arbol limpio.
function Update-ParkosLiteSource {
    param([Parameter(Mandatory)][string]$RepoRoot, [string]$Branch = 'dev')

    if (-not (Test-ParkosLiteBranchName -Branch $Branch)) {
        throw "nombre de rama invalido: '$Branch'. Usa solo letras, numeros, '.', '_', '-' y '/'."
    }
    $dirty = Invoke-ParkosLiteGit -RepoRoot $RepoRoot -Arguments @('status', '--porcelain', '--untracked-files=no')
    if ($dirty.ExitCode -ne 0) { throw "git status fallo: $($dirty.Output -join ' ')" }
    if (@($dirty.Output | Where-Object { $_ -and $_.Trim() }).Count -gt 0) {
        throw "Hay cambios locales en archivos versionados; el pull no se puede hacer limpio. Guardalos (git stash) o descartalos y reintenta:`n$($dirty.Output -join "`n")"
    }
    $old = (Invoke-ParkosLiteGitChecked -RepoRoot $RepoRoot -Arguments @('rev-parse', 'HEAD') -Failure 'git rev-parse HEAD fallo').Output -join ''
    Invoke-ParkosLiteGitChecked -RepoRoot $RepoRoot -Arguments @('fetch', 'origin', $Branch) -Failure "git fetch origin $Branch fallo" | Out-Null
    $cur = (Invoke-ParkosLiteGitChecked -RepoRoot $RepoRoot -Arguments @('rev-parse', '--abbrev-ref', 'HEAD') -Failure 'git rev-parse fallo').Output -join ''
    if ($cur.Trim() -ne $Branch) {
        Invoke-ParkosLiteGitChecked -RepoRoot $RepoRoot -Arguments @('checkout', $Branch) -Failure "git checkout $Branch fallo" | Out-Null
    }
    $pull = Invoke-ParkosLiteGit -RepoRoot $RepoRoot -Arguments @('pull', '--ff-only', 'origin', $Branch)
    if ($pull.ExitCode -ne 0) {
        throw "git pull --ff-only fallo: la rama local diverge de origin/$Branch; resuelvelo manualmente antes de reintentar. ($($pull.Output -join ' '))"
    }
    $new = (Invoke-ParkosLiteGitChecked -RepoRoot $RepoRoot -Arguments @('rev-parse', 'HEAD') -Failure 'git rev-parse HEAD fallo').Output -join ''
    return @{ OldHead = $old.Trim(); NewHead = $new.Trim() }
}

function Get-ParkosLiteChangedFiles {
    param([Parameter(Mandatory)][string]$RepoRoot, [string]$From, [string]$To)
    if ($From -eq $To) { return @() }
    $r = Invoke-ParkosLiteGit -RepoRoot $RepoRoot -Arguments @('diff', '--name-only', $From, $To)
    if ($r.ExitCode -ne 0) { throw "git diff fallo: $($r.Output -join ' ')" }
    return @($r.Output | Where-Object { $_ })
}

# stop -> pull -> (reconstruir exe solo si cambio backend/) -> migrar ->
# (pnpm install solo si cambio lockfile/package.json) -> re-sembrar -> start.
# Si el pull falla se vuelve a levantar lo que habia y se propaga el error.
function Invoke-ParkosLiteRefresh {
    param([Parameter(Mandatory)]$Ctx)
    $paths = $Ctx.Paths
    Stop-ParkosLiteAll -Ctx $Ctx
    try {
        $src = Update-ParkosLiteSource -RepoRoot $paths.RepoRoot -Branch $Ctx.Branch
    } catch {
        Write-ParkosLiteLog $Ctx "El pull fallo; se reinicia la version anterior."
        Start-ParkosLiteAll -Ctx $Ctx
        throw
    }
    $changed = Get-ParkosLiteChangedFiles -RepoRoot $paths.RepoRoot -From $src.OldHead -To $src.NewHead
    $apiBuilt = (Test-Path $paths.ApiExe) -and (Test-Path $paths.MigrateExe)
    $plan = Get-ParkosLiteRefreshPlan -ChangedFiles $changed -ApiBuilt $apiBuilt
    Write-ParkosLiteLog $Ctx "Archivos cambiados: $(@($changed).Count) | reconstruir exe: $($plan.RebuildApi) | pnpm install: $($plan.PnpmInstall)"
    if ($plan.RebuildApi) { Invoke-ParkosLiteStep -Ctx $Ctx -Key 'api' }
    if ($plan.Migrate) { Invoke-ParkosLiteStep -Ctx $Ctx -Key 'migrate' }
    if ($plan.PnpmInstall) { Invoke-ParkosLiteStep -Ctx $Ctx -Key 'front' }
    if ($plan.Reseed) { Invoke-ParkosLiteStep -Ctx $Ctx -Key 'seed' }
    Start-ParkosLiteAll -Ctx $Ctx
}
