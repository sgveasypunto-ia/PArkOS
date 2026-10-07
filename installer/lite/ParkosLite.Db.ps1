# Parkos LITE - base de datos local (Postgres 16 como proceso de usuario).
# initdb, roles, arranque/parada con tolerancia a postmaster.pid huerfano,
# espera de readiness, extension pg_partman, migraciones y seed.
#
# Solo funciones. Todo binario externo (initdb, pg_ctl, psql, pg_isready,
# migrate.exe) pasa por Invoke-ParkosLiteNative, que los tests mockean.
# Compatible con PowerShell 5.1. Requiere (dot-source previo) los helpers de
# installer\shared\ParkosPostgresDownload.ps1 y ParkosPayloadParts.ps1 solo en
# Install-ParkosLiteDatabase.

$script:ParkosLiteConfBegin = '# --- parkos-lite (gestionado) ---'
$script:ParkosLiteConfEnd = '# --- /parkos-lite ---'

# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------

# Corre un binario externo con variables de entorno temporales (solo para esa
# llamada), stdin opcional y cwd opcional. Devuelve @{ ExitCode; Output }.
function Invoke-ParkosLiteNative {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory,
        [hashtable]$Env = @{},
        [string]$StdIn
    )
    $saved = @{}
    foreach ($k in $Env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$Env[$k], 'Process')
    }
    if ($WorkingDirectory) { Push-Location $WorkingDirectory }
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            if ($PSBoundParameters.ContainsKey('StdIn')) {
                $out = $StdIn | & $FilePath @Arguments 2>&1
            } else {
                $out = & $FilePath @Arguments 2>&1
            }
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
        return @{ ExitCode = $code; Output = @($out | ForEach-Object { "$_" }) }
    } finally {
        if ($WorkingDirectory) { Pop-Location }
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
}

function Get-ParkosLiteProcessName {
    param([Parameter(Mandatory)][int]$ProcessId)
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    return $p.ProcessName
}

function Get-ParkosLitePgBin {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string]$Name)
    return (Join-Path $PgRoot "bin\$Name.exe")
}

function Invoke-ParkosLitePsql {
    param(
        [Parameter(Mandatory)][string]$PgRoot,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][string]$Password,
        [string]$Database = 'parkos',
        [string[]]$Arguments = @(),
        [string]$Sql
    )
    $base = @('-w', '-X', '-h', '127.0.0.1', '-p', "$Port", '-U', $User, '-d', $Database, '-v', 'ON_ERROR_STOP=1')
    $psql = Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'psql'
    if ($PSBoundParameters.ContainsKey('Sql')) {
        return (Invoke-ParkosLiteNative -FilePath $psql -Arguments ($base + $Arguments) -Env @{ PGPASSWORD = $Password } -StdIn $Sql)
    }
    return (Invoke-ParkosLiteNative -FilePath $psql -Arguments ($base + $Arguments) -Env @{ PGPASSWORD = $Password })
}

# ---------------------------------------------------------------------------
# initdb + configuracion
# ---------------------------------------------------------------------------

function Get-ParkosLitePostgresConfLines {
    param([Parameter(Mandatory)][int]$Port)
    return @(
        $script:ParkosLiteConfBegin
        "port = $Port"
        "listen_addresses = '127.0.0.1'"
        # El esquema guarda timestamps naive-UTC y los compara con NOW() (p. ej.
        # impuestos.vigente_desde <= NOW()). Con el timezone del sistema (Bogota,
        # UTC-5) el IVA sembrado queda 5 h en el futuro y toda cotizacion falla
        # con iva_no_configurado. Docker corre en UTC: igualamos.
        "timezone = 'UTC'"
        $script:ParkosLiteConfEnd
    )
}

# Reescribe el bloque gestionado del postgresql.conf (idempotente: cambiar el
# puerto no acumula lineas).
function Set-ParkosLitePgConf {
    param([Parameter(Mandatory)][string]$PgData, [Parameter(Mandatory)][int]$Port)
    $conf = Join-Path $PgData 'postgresql.conf'
    $kept = @()
    $inBlock = $false
    if (Test-Path $conf) {
        foreach ($line in (Get-Content $conf)) {
            if ($line -eq $script:ParkosLiteConfBegin) { $inBlock = $true; continue }
            if ($line -eq $script:ParkosLiteConfEnd) { $inBlock = $false; continue }
            if (-not $inBlock) { $kept += $line }
        }
    }
    Set-Content -Path $conf -Value ($kept + (Get-ParkosLitePostgresConfLines -Port $Port)) -Encoding ASCII
}

# Devuelve $true si inicializo, $false si el data dir ya existia.
function Initialize-ParkosLitePgData {
    param(
        [Parameter(Mandatory)][string]$PgRoot,
        [Parameter(Mandatory)][string]$PgData,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$PostgresPassword
    )
    if (Test-Path (Join-Path $PgData 'PG_VERSION')) {
        Set-ParkosLitePgConf -PgData $PgData -Port $Port
        return $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $PgData) | Out-Null
    $pwFile = Join-Path ([IO.Path]::GetTempPath()) ("parkoslite-" + [guid]::NewGuid().ToString('N') + '.pw')
    [IO.File]::WriteAllText($pwFile, $PostgresPassword)
    try {
        # Bootstrap como `postgres` (igual que el instalador completo); `parkos`
        # se crea despues en Initialize-ParkosLiteRoles. Locale C + UTF8: no
        # depende de que exista un locale de Windows concreto.
        $r = Invoke-ParkosLiteNative -FilePath (Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'initdb') -Arguments @(
            '-D', $PgData, '-U', 'postgres', '--encoding=UTF8', '--locale=C', '--auth=scram-sha-256', "--pwfile=$pwFile")
        if ($r.ExitCode -ne 0) {
            throw "initdb fallo (exit $($r.ExitCode)): $($r.Output -join ' ')"
        }
    } finally {
        Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
    }
    Set-ParkosLitePgConf -PgData $PgData -Port $Port
    return $true
}

# ---------------------------------------------------------------------------
# Arranque / parada
# ---------------------------------------------------------------------------

# Decision pura sobre un postmaster.pid: 'clean' (no hay), 'running' (lo tiene
# un postgres vivo) o 'stale' (huerfano tras un apagado sucio, o PID reutilizado
# por otro proceso).
function Get-ParkosLiteStalePidDecision {
    param([bool]$PidFileExists, [int]$StatusExitCode, [string]$PidProcessName)
    if (-not $PidFileExists) { return 'clean' }
    if ($StatusExitCode -eq 0 -and $PidProcessName -eq 'postgres') { return 'running' }
    return 'stale'
}

function Get-ParkosLitePgState {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string]$PgData)
    $pidFile = Join-Path $PgData 'postmaster.pid'
    $exists = Test-Path $pidFile
    $procName = $null
    $status = 3
    if ($exists) {
        $first = Get-Content $pidFile -TotalCount 1
        $pidNum = 0
        if ([int]::TryParse(("$first").Trim(), [ref]$pidNum)) { $procName = Get-ParkosLiteProcessName -ProcessId $pidNum }
        $status = (Invoke-ParkosLiteNative -FilePath (Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'pg_ctl') -Arguments @('status', '-D', $PgData)).ExitCode
    }
    return (Get-ParkosLiteStalePidDecision -PidFileExists $exists -StatusExitCode $status -PidProcessName $procName)
}

# Quita SOLO un postmaster.pid huerfano (nadie lo posee). Devuelve el estado.
function Repair-ParkosLiteStalePid {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string]$PgData)
    $state = Get-ParkosLitePgState -PgRoot $PgRoot -PgData $PgData
    if ($state -eq 'stale') {
        Remove-Item (Join-Path $PgData 'postmaster.pid') -Force
    }
    return $state
}

function Test-ParkosLitePgAccepting {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][int]$Port)
    $r = Invoke-ParkosLiteNative -FilePath (Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'pg_isready') -Arguments @('-h', '127.0.0.1', '-p', "$Port")
    return ($r.ExitCode -eq 0)
}

function Wait-ParkosLitePgReady {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][int]$Port, [int]$TimeoutSec = 60)
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        if (Test-ParkosLitePgAccepting -PgRoot $PgRoot -Port $Port) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

# pg_ctl start NO puede correr por Invoke-ParkosLiteNative: el postgres que
# deja en segundo plano hereda el pipe de captura y la lectura nunca termina
# (cuelga). Se lanza como proceso con salida a archivos y se espera SOLO a
# pg_ctl (WaitForExit), no a sus descendientes.
function Invoke-ParkosLitePgCtlStart {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string[]]$Arguments, [int]$TimeoutSec = 75)
    $out = [IO.Path]::GetTempFileName(); $err = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath (Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'pg_ctl') -ArgumentList ($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        # Windows PowerShell 5.1: sin tocar .Handle, ExitCode puede quedar $null tras WaitForExit.
        $null = $p.Handle
        if (-not $p.WaitForExit($TimeoutSec * 1000)) { return @{ ExitCode = 124; Output = @('timeout esperando a pg_ctl start') } }
        return @{ ExitCode = $p.ExitCode; Output = @((Get-Content $out) + (Get-Content $err)) }
    } finally {
        Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
    }
}

function Start-ParkosLitePg {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][int]$Port, [int]$TimeoutSec = 60)

    $state = Repair-ParkosLiteStalePid -PgRoot $Paths.PgRoot -PgData $Paths.PgData
    if ($state -ne 'running') {
        New-Item -ItemType Directory -Force -Path $Paths.Logs | Out-Null
        $log = Join-Path $Paths.Logs 'postgres.log'
        $r = Invoke-ParkosLitePgCtlStart -PgRoot $Paths.PgRoot -Arguments @(
            'start', '-w', '-t', "$TimeoutSec", '-D', $Paths.PgData, '-l', $log) -TimeoutSec ($TimeoutSec + 15)
        if ($r.ExitCode -ne 0) {
            throw "pg_ctl start fallo (exit $($r.ExitCode)). Revisa $log"
        }
    }
    if (-not (Wait-ParkosLitePgReady -PgRoot $Paths.PgRoot -Port $Port -TimeoutSec $TimeoutSec)) {
        throw "Postgres no acepto conexiones en el puerto $Port tras $TimeoutSec s. Revisa $(Join-Path $Paths.Logs 'postgres.log')"
    }
    return $true
}

function Stop-ParkosLitePg {
    param([Parameter(Mandatory)]$Paths)
    $state = Get-ParkosLitePgState -PgRoot $Paths.PgRoot -PgData $Paths.PgData
    if ($state -ne 'running') { return $false }
    $r = Invoke-ParkosLiteNative -FilePath (Get-ParkosLitePgBin -PgRoot $Paths.PgRoot -Name 'pg_ctl') -Arguments @('stop', '-D', $Paths.PgData, '-m', 'fast', '-w')
    if ($r.ExitCode -ne 0) { throw "pg_ctl stop fallo (exit $($r.ExitCode)): $($r.Output -join ' ')" }
    return $true
}

# ---------------------------------------------------------------------------
# Roles, base y extension
# ---------------------------------------------------------------------------

function Get-ParkosLiteRolesSql {
    param([Parameter(Mandatory)][string]$SuperuserPassword)
    $tpl = @'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parkos') THEN
        CREATE ROLE parkos LOGIN SUPERUSER PASSWORD '__PW__';
    ELSE
        ALTER ROLE parkos WITH PASSWORD '__PW__' SUPERUSER LOGIN;
    END IF;
END
$$;
'@
    return $tpl.Replace('__PW__', $SuperuserPassword)
}

function Initialize-ParkosLiteRoles {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)]$Secrets)

    $r = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'postgres' -Password $Secrets.PostgresPassword -Database 'postgres' -Sql (Get-ParkosLiteRolesSql -SuperuserPassword $Secrets.SuperuserPassword)
    if ($r.ExitCode -ne 0) { throw "No se pudo configurar el superusuario parkos: $($r.Output -join ' ')" }

    $exists = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'postgres' -Password $Secrets.PostgresPassword -Database 'postgres' -Arguments @('-tAc', "SELECT 1 FROM pg_database WHERE datname = 'parkos';")
    if (-not (($exists.Output -join '').Trim() -eq '1')) {
        $c = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'postgres' -Password $Secrets.PostgresPassword -Database 'postgres' -Arguments @('-c', 'CREATE DATABASE parkos OWNER parkos;')
        if ($c.ExitCode -ne 0) { throw "No se pudo crear la base parkos: $($c.Output -join ' ')" }
    }
}

function Enable-ParkosLitePartman {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)]$Secrets)
    foreach ($sql in 'CREATE SCHEMA IF NOT EXISTS partman;', 'CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA partman;') {
        $r = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'parkos' -Password $Secrets.SuperuserPassword -Database 'parkos' -Arguments @('-c', $sql)
        if ($r.ExitCode -ne 0) { throw "pg_partman: '$sql' fallo: $($r.Output -join ' ')" }
    }
}

# pg_partman SQL-only desde las partes del repo (artefacto 'pg_partman-extension')
# a <Downloads>\pg_partman\extension (la cache que ya mira Get-ParkosPgPartmanExtension).
# $true si la extension queda lista; $false si no hay partes o no sirven (el
# llamador cae al ensamblado por descarga). Nunca lanza.
function Restore-ParkosLitePartmanFromParts {
    param([Parameter(Mandatory)]$Paths, [scriptblock]$Logger)
    $extDir = Join-Path $Paths.Downloads 'pg_partman\extension'
    if (Test-ParkosPgPartmanExtensionDir -Dir $extDir) { return $true }
    $entry = $null
    try {
        if (Test-Path -LiteralPath $Paths.PartsDir) { $entry = Find-ParkosPayloadEntry -PartsDir $Paths.PartsDir -Id 'pg_partman-extension' }
    } catch { $entry = $null }
    if (-not $entry) { return $false }
    try {
        [void](Restore-ParkosPayloadArtifact -Id 'pg_partman-extension' -PartsDir $Paths.PartsDir -PayloadRoot $Paths.Downloads -CacheDir (Join-Path $Paths.Downloads 'tmp') -Force -Logger $Logger)
        if (-not (Test-ParkosPgPartmanExtensionDir -Dir $extDir)) { throw 'la extension restaurada no trae pg_partman--*.sql y pg_partman.control' }
        Write-ParkosDownloadLog $Logger 'pg_partman restaurado desde el repositorio (partes), sin descargar.'
        return $true
    } catch {
        Write-ParkosDownloadLog $Logger "Las partes del repo de pg_partman no sirven ($($_.Exception.Message)): se descarga."
        return $false
    }
}

# ---------------------------------------------------------------------------
# Runtime de Visual C++ para los binarios de Postgres (EDB)
# ---------------------------------------------------------------------------
# En algunos Windows 11 (p. ej. 24H2, build 26100) initdb/psql del zip de EDB
# fallan con "LIBPQ.dll no esta disenado para ejecutarse en Windows" (exit
# 0xC0E90002) hasta que los DLL del runtime de VC++ estan junto a pgsql\bin. Es
# dependiente del entorno (desaparece con una actualizacion de Windows). No se
# empaqueta ningun binario de Microsoft: se copian desde System32 si estan ahi.

$script:ParkosLitePgRuntimeDlls = @('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll')
$script:ParkosLiteBadImageExitCode = [int64]3236495362   # 0xC0E90002 sin signo
$script:ParkosLiteVcRedistUrl = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'

# Carpeta del sistema de 64 bits (Sysnative si este PowerShell es de 32 bits).
function Get-ParkosLiteSystemDir {
    $sys = Join-Path $env:SystemRoot 'System32'
    if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
        $native = Join-Path $env:SystemRoot 'Sysnative'
        if (Test-Path -LiteralPath $native) { return $native }
    }
    return $sys
}

# Ejecuta un binario con tope de tiempo (lo mata si se cuelga, p. ej. por el
# dialogo modal de "no esta disenado para ejecutarse"). Nunca lanza. Devuelve
# @{ ExitCode; TimedOut; Output }.
function Invoke-ParkosLiteProbe {
    param([Parameter(Mandatory)][string]$FilePath, [string[]]$Arguments = @(), [int]$TimeoutSec = 20)
    $p = $null
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FilePath
        $psi.Arguments = (($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' ')
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        $outTask = $p.StandardOutput.ReadToEndAsync()
        $errTask = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            try { $p.Kill() } catch { }
            return @{ ExitCode = -1; TimedOut = $true; Output = @() }
        }
        $p.WaitForExit()
        $text = ''
        try { $text = $outTask.Result + $errTask.Result } catch { }
        return @{ ExitCode = [int]$p.ExitCode; TimedOut = $false; Output = @($text -split "`r?`n" | Where-Object { $_ }) }
    } catch {
        return @{ ExitCode = -1; TimedOut = $false; Output = @($_.Exception.Message) }
    } finally {
        if ($p) { $p.Dispose() }
    }
}

# Pre-flight: initdb --version debe ejecutarse. Si falla con 0xC0E90002 o se
# cuelga, copia (sin sobrescribir) los DLL del runtime de VC++ desde System32 a
# pgsql\bin y reintenta una vez; si no estan en System32 o sigue fallando, falla
# con un mensaje que indica instalar el redistribuible de Microsoft. Otros
# errores no se tocan (los reporta el paso siguiente, initdb).
function Assert-ParkosLitePgRuntime {
    param([Parameter(Mandatory)][string]$PgRoot, [scriptblock]$Logger)
    $initdb = Get-ParkosLitePgBin -PgRoot $PgRoot -Name 'initdb'
    $r = Invoke-ParkosLiteProbe -FilePath $initdb -Arguments @('--version') -TimeoutSec 20
    if (-not $r.TimedOut -and $r.ExitCode -eq 0) { return }
    $isRuntime = $r.TimedOut -or (([int64]$r.ExitCode -band 4294967295L) -eq $script:ParkosLiteBadImageExitCode)
    if (-not $isRuntime) {
        Write-ParkosDownloadLog $Logger "initdb --version devolvio $($r.ExitCode) (no parece un problema del runtime de Visual C++); se continua."
        return
    }
    $why = "exit 0x{0:X8}" -f ([int64]$r.ExitCode -band 4294967295L)
    if ($r.TimedOut) { $why = 'no respondio a tiempo' }
    Write-ParkosDownloadLog $Logger "initdb --version fallo ($why): falta el runtime de Visual C++ junto a Postgres. Se copian los DLL desde System32 (solo los que faltan)."

    $bin = Join-Path $PgRoot 'bin'
    $sys = Get-ParkosLiteSystemDir
    $copied = @(); $unavailable = @()
    foreach ($dll in $script:ParkosLitePgRuntimeDlls) {
        $dest = Join-Path $bin $dll
        if (Test-Path -LiteralPath $dest) { continue }
        $src = Join-Path $sys $dll
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination $dest
            $copied += $dll
        } else {
            $unavailable += $dll
        }
    }
    if ($copied.Count -gt 0) { Write-ParkosDownloadLog $Logger "Runtime de Visual C++ copiado a ${bin}: $($copied -join ', ')." }

    $redistMsg = "Instala 'Microsoft Visual C++ Redistributable 2015-2022 x64' (enlace oficial de Microsoft: $script:ParkosLiteVcRedistUrl), reinicia esta ventana y vuelve a ejecutar la opcion 11 (Instalar base de datos)."
    if ($copied.Count -eq 0 -and $unavailable.Count -gt 0) {
        throw "Los binarios de Postgres no arrancan ($why) y los DLL del runtime de Visual C++ no estan en $sys ($($unavailable -join ', ')). $redistMsg"
    }
    $r2 = Invoke-ParkosLiteProbe -FilePath $initdb -Arguments @('--version') -TimeoutSec 20
    if ($r2.TimedOut -or $r2.ExitCode -ne 0) {
        throw "Los binarios de Postgres siguen sin arrancar tras copiar el runtime de Visual C++ (exit $($r2.ExitCode)). $redistMsg"
    }
    Write-ParkosDownloadLog $Logger 'initdb --version ya responde: runtime de Visual C++ resuelto.'
}

# Paso 2 completo. Orden de origen: partes del repo (Postgres: installer\payload\parts\postgres,
# pg_partman: artefacto pg_partman-extension) -> cache -> descarga. Luego initdb,
# arranque y roles.
function Install-ParkosLiteDatabase {
    param(
        [Parameter(Mandatory)]$Paths,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)]$Secrets,
        [scriptblock]$Logger
    )
    $zip = Get-ParkosPostgresZip -CacheDir $Paths.Downloads -PayloadDir $Paths.PgPayload -Logger $Logger
    Expand-ParkosPostgresZip -ZipPath $zip -PgRoot $Paths.PgRoot -Logger $Logger | Out-Null
    Assert-ParkosLitePgRuntime -PgRoot $Paths.PgRoot -Logger $Logger
    [void](Restore-ParkosLitePartmanFromParts -Paths $Paths -Logger $Logger)
    $ext = Get-ParkosPgPartmanExtension -ExtensionDir (Join-Path $Paths.Downloads 'pg_partman\extension') -TempDir (Join-Path $Paths.Downloads 'tmp') -PayloadDir $Paths.PartmanPayload -Logger $Logger
    Install-ParkosPgPartmanExtension -PgRoot $Paths.PgRoot -ExtensionDir $ext
    Initialize-ParkosLitePgData -PgRoot $Paths.PgRoot -PgData $Paths.PgData -Port $Port -PostgresPassword $Secrets.PostgresPassword | Out-Null
    Start-ParkosLitePg -Paths $Paths -Port $Port | Out-Null
    Initialize-ParkosLiteRoles -Paths $Paths -Port $Port -Secrets $Secrets
    Enable-ParkosLitePartman -Paths $Paths -Port $Port -Secrets $Secrets
}

# ---------------------------------------------------------------------------
# Migraciones, particiones, seed, facts
# ---------------------------------------------------------------------------

function Get-ParkosLiteMigrateEnv {
    param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)]$Secrets)
    return @{
        DATABASE_URL           = "postgresql://parkos:$($Secrets.SuperuserPassword)@127.0.0.1:$Port/parkos"
        PARKOS_APP_DB_PASSWORD = $Secrets.AppPassword
    }
}

# migrate.exe resuelve migrations/ y alembic.ini relativos a su cwd.
function Invoke-ParkosLiteMigrate {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)]$Secrets)
    $r = Invoke-ParkosLiteNative -FilePath $Paths.MigrateExe -Arguments @('-c', 'alembic.ini', 'upgrade', 'head') -WorkingDirectory $Paths.MigrateDir -Env (Get-ParkosLiteMigrateEnv -Port $Port -Secrets $Secrets)
    if ($r.ExitCode -ne 0) { throw "alembic upgrade head fallo (exit $($r.ExitCode)): $(($r.Output | Select-Object -Last 15) -join ' | ')" }
}

# Sanity de particiones (idempotente). Un fallo aqui no bloquea: se informa.
function Invoke-ParkosLiteEnsurePartitions {
    param([Parameter(Mandatory)]$Paths, [Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)]$Secrets)
    $r = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'parkos' -Password $Secrets.SuperuserPassword -Database 'parkos' -Arguments @('-tAc', 'SELECT prod.fn_ensure_partitions();')
    return ($r.ExitCode -eq 0)
}

function Get-ParkosLiteSeedArguments {
    param([Parameter(Mandatory)][string]$SeedSql, [Parameter(Mandatory)][string]$SucursalUuid)
    if ($SucursalUuid -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') {
        throw "uuid de sucursal invalido: '$SucursalUuid'"
    }
    return @('-v', 'ON_ERROR_STOP=1', '-v', "sucursal_uuid=$SucursalUuid", '-f', $SeedSql)
}

function Invoke-ParkosLiteSeed {
    param(
        [Parameter(Mandatory)]$Paths,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)]$Secrets,
        [Parameter(Mandatory)][string]$SucursalUuid
    )
    $seedArgs = Get-ParkosLiteSeedArguments -SeedSql $Paths.SeedSql -SucursalUuid $SucursalUuid
    $r = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'parkos' -Password $Secrets.SuperuserPassword -Database 'parkos' -Arguments $seedArgs
    if ($r.ExitCode -ne 0) { throw "seed de demo fallo (exit $($r.ExitCode)): $(($r.Output | Select-Object -Last 10) -join ' | ')" }
    return $r.Output
}

function Get-ParkosLiteDbFacts {
    param(
        [Parameter(Mandatory)]$Paths,
        [Parameter(Mandatory)][int]$Port,
        $Secrets,
        [string]$SucursalUuid
    )
    $facts = @{ DbReady = $false; SchemaMigrated = $false; Seeded = $false }
    if ($Port -le 0 -or -not $Secrets) { return $facts }
    if (-not (Test-ParkosLitePgAccepting -PgRoot $Paths.PgRoot -Port $Port)) { return $facts }
    $facts.DbReady = $true
    $q1 = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'parkos' -Password $Secrets.SuperuserPassword -Database 'parkos' -Arguments @('-tAc', "SELECT to_regclass('prod.tipos_vehiculo') IS NOT NULL;")
    if ($q1.ExitCode -eq 0 -and (($q1.Output -join '').Trim() -eq 't')) {
        $facts.SchemaMigrated = $true
        if ($SucursalUuid) {
            $q2 = Invoke-ParkosLitePsql -PgRoot $Paths.PgRoot -Port $Port -User 'parkos' -Password $Secrets.SuperuserPassword -Database 'parkos' -Arguments @('-tAc', "SELECT EXISTS (SELECT 1 FROM prod.tarifas_sucursal WHERE uuid_sucursal = '$SucursalUuid' AND vigente_hasta IS NULL);")
            if ($q2.ExitCode -eq 0 -and (($q2.Output -join '').Trim() -eq 't')) { $facts.Seeded = $true }
        }
    }
    return $facts
}
