<#
.SYNOPSIS
    Parkos management module - lifecycle cmdlets for an existing branch
    installation (Fases 25-30 of plan.md, PR1 of the installer gap-closing
    plan).

.DESCRIPTION
    Separate, independently importable PowerShell module a field technician
    can load without the full parkos-installer.ps1 TUI. installer/build-release.ps1
    Stage 0 copies Parkos.psd1/Parkos.psm1/about_Parkos.help.txt (unmodified,
    versioned in the repo, never downloaded) into the release payload, and
    parkos-installer.ps1's Fase 24 verify stage installs them into
    C:\Program Files\PowerShell\Modules\Parkos\<version>\ once the branch
    install itself passes.

    PR1 ships only the module skeleton: manifest, private helpers, and 8
    placeholder public cmdlets that log + warn + return without doing any
    real work. PR2-PR9 replace each placeholder body with its real
    implementation one at a time; the public surface (function names,
    documented future parameters) is fixed here so those PRs do not need to
    touch the manifest again.

    No tildes/accented characters anywhere in this file (not even in long
    comments) - this matches the exact convention already used end-to-end in
    parkos-installer.ps1 and build-release.ps1 (verified: zero accented
    characters in either file), which avoids PS5.1/PS7 mixed-encoding
    mojibake on a field machine.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Module-scope constants
# ---------------------------------------------------------------------------

$script:ModuleVersion = '1.0.0'
$script:DefaultDataPath = 'C:\ProgramData\Parkos'
$script:DefaultInstallPath = 'C:\Program Files\Parkos'

# Mismo layout fijo que usa parkos-installer.ps1 (Test-PostInstallation,
# Invoke-ParkosInstall) para psql.exe - Postgres 16 siempre termina en esta
# ruta sin importar si el metodo de instalacion fue winget o el ZIP de
# fallback (Install-Postgres converge en el mismo layout en ambos casos).
$script:PostgresInstallPath = 'C:\Program Files\PostgreSQL\16'
$script:PsqlExePath = Join-Path $script:PostgresInstallPath 'bin\psql.exe'

# ---------------------------------------------------------------------------
# Private helpers (script: scope - never exported; the manifest's
# FunctionsToExport is the actual export gate, this is defense in depth and
# matches the convention requested for this module).
# ---------------------------------------------------------------------------

# Derives every path this module cares about from the two defaults above.
# Only defaults today (no override parameters) - a future PR can add
# -InstallPath/-DataPath overrides here if a real need shows up; not
# over-designing this in PR1.
function script:Resolve-ParkosPaths {
    [CmdletBinding()]
    param()

    $installPath = $script:DefaultInstallPath
    $dataPath = $script:DefaultDataPath

    return @{
        InstallPath  = $installPath
        DataPath     = $dataPath
        SecretsPath  = Join-Path $dataPath 'secrets'
        LogsPath     = Join-Path $dataPath 'logs'
        BackupsPath  = Join-Path $dataPath 'backups'
        ReleasesPath = Join-Path $installPath 'releases'
    }
}

# Same admin-check pattern as Request-Elevation in parkos-installer.ps1 -
# [Security.Principal.WindowsPrincipal] over the current WindowsIdentity,
# checked against the built-in Administrator role.
function script:Test-IsAdmin {
    [CmdletBinding()]
    param()

    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator
    )
}

# Best-effort logger, NOT a gate: a cmdlet in this module must never fail
# because its own log line could not be written (locked file, read-only
# ProgramData on a locked-down machine, etc). Every failure path here is a
# silent catch on purpose.
function script:Write-ParkosLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [string]$Level = 'INFO'
    )

    try {
        $paths = Resolve-ParkosPaths
        $logPath = Join-Path $paths.DataPath 'logs\module.log'
        $logDir = Split-Path $logPath -Parent
        New-Item -ItemType Directory -Force -Path $logDir -ErrorAction Stop | Out-Null
        $timestamp = (Get-Date).ToString('o')
        Add-Content -Path $logPath -Value "[$timestamp][$Level] $Message" -ErrorAction Stop
    } catch {
        # Best-effort - see comment above the function. Never re-throw.
    }
}

# Parses a Parkos runtime .env file into an ordered hashtable. Shared by
# Get-ParkosHealth and Test-CrashRecovery so the parsing pattern (Get-Content
# | Where-Object { $_ -match '=' } + split en el primer '=') vive en un solo
# lugar en vez de repetirse en cada cmdlet - mismo patron que ya usa
# parkos-installer.ps1 en Test-PostInstallation/Invoke-CatalogSeed/
# Install-ApiService. Throws if the file does not exist so callers get one
# clean failure point (a missing .env means "no hay instalacion todavia").
function script:Import-ParkosEnvFile {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path $Path)) {
        throw "No se encontro el archivo .env en $Path."
    }

    # Fase 27 (HU-F27.2/DEC-INST-40): parkos-installer.ps1 ahora escribe el
    # .env cifrado con CMS (Protect-CmsMessage, formato ASCII-armored con
    # encabezado '-----BEGIN CMS-----') - detectado aca por el CONTENIDO
    # crudo, nunca por extension/convencion de nombre, para seguir aceptando
    # sin cambios cualquier .env en texto plano preexistente (instalaciones
    # hechas con una version anterior de este instalador, o cualquier
    # fixture de test que siga escribiendo texto plano - retrocompatibilidad
    # obligatoria, ver los tests de este mismo Describe).
    $rawContent = Get-Content -Path $Path -Raw
    if ($rawContent -match '^\s*-----BEGIN CMS-----') {
        $rawContent = Unprotect-CmsMessage -Path $Path
    }

    $envMap = [ordered]@{}
    $lines = @($rawContent -split "`r?`n") | Where-Object { $_ -match '=' }
    foreach ($line in $lines) {
        $parts = $line -split '=', 2
        $envMap[$parts[0]] = $parts[1]
    }
    return $envMap
}

# Extrae el puerto de Postgres desde PARKOS_DB_URL (preferido) o DATABASE_URL
# como fallback - ambas variables las escribe Write-RuntimeEnvFile en
# parkos-installer.ps1 con la forma esquema://usuario:password@host:puerto/db.
# Throws si ninguna de las dos variables esta presente o parseable, en vez de
# devolver un puerto adivinado.
function script:Get-ParkosPostgresPort {
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Collections.IDictionary]$EnvMap)

    foreach ($key in 'PARKOS_DB_URL', 'DATABASE_URL') {
        if ($EnvMap.Contains($key) -and $EnvMap[$key] -match '@[^:/]+:(\d+)/') {
            return [int]$Matches[1]
        }
    }
    throw 'No se pudo determinar el puerto de Postgres desde PARKOS_DB_URL ni DATABASE_URL en el .env.'
}

# Corre doctor.exe con las variables del .env ya cargadas en el proceso
# actual (mismo patron Get-Content/Set-Item que Test-PostInstallation e
# Invoke-CatalogSeed en parkos-installer.ps1), parado en su propio directorio
# (alembic.ini's script_location es relativo al CWD - mismo motivo por el que
# migrate.exe necesita Push-Location). Devuelve el JSON ya parseado. Throws
# si el binario no existe en la ruta indicada o si su salida no es JSON
# valido, para que el cmdlet que lo llama pueda reportar un FAIL claro en vez
# de asumir "fallo el doctor" cuando en realidad falta el binario.
function script:Invoke-ParkosDoctorExe {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$DoctorExePath,
        [Parameter(Mandatory)][System.Collections.IDictionary]$EnvMap
    )

    if (-not (Test-Path $DoctorExePath)) {
        throw "Falta el binario doctor.exe en $DoctorExePath - la instalacion no incluye el modulo de diagnostico."
    }

    foreach ($key in $EnvMap.Keys) {
        Set-Item -Path "Env:$key" -Value $EnvMap[$key]
    }

    Push-Location (Split-Path $DoctorExePath -Parent)
    try {
        return (& $DoctorExePath | ConvertFrom-Json)
    } finally {
        Pop-Location
    }
}

# Endurece la ACL de TODO el directorio secrets\ (recursivo, /T) a solo
# Administrators+SYSTEM - mismo patron que Set-PgPassFile ya aplica en
# parkos-installer.ps1 para el archivo pgpass.conf suelto, pero aca sobre el
# directorio completo (jwt.key, .env, pgpass.conf, etc, y cualquier archivo
# futuro que caiga ahi). Usado por Test-ParkosSecretsAcl/Repair-ParkosInstall
# (E4) para re-aplicar el endurecimiento cuando se detecta una ACL alterada.
function script:Set-ParkosSecretsAcl {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    icacls $Path /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' /T | Out-Null
}

# Wrapper minimo sobre nssm.exe - existe solo para que Repair-ParkosInstall
# (E1, re-registro de un servicio NSSM faltante) sea testeable: Pester no
# puede interceptar una invocacion `& $NssmPath ...` por ruta literal (no
# resuelve por nombre de comando), pero SI puede mockear esta funcion con
# nombre propio.
function script:Invoke-ParkosNssm {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$NssmPath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    & $NssmPath @Arguments
}

# Wrapper minimo sobre psql.exe para una consulta administrativa de solo
# lectura (\du+, \l) - existe por el mismo motivo que Invoke-ParkosNssm:
# Pester no puede mockear selectivamente un "& $PsqlExePath ..." por ruta
# literal (Test-ParkosDatabaseIntegrity ya tiene el mismo problema, pero ahi
# se resuelve mockeando esa funcion completa desde afuera; aca, en cambio,
# el consumidor SI necesita ver que argumentos se le pasan, por eso el
# wrapper propio). Usado por Export-ParkosDiagnostics (E8) para
# pgsql-roles.txt/pgsql-databases.txt.
function script:Invoke-ParkosPsql {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PsqlExePath,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Command
    )

    & $PsqlExePath -w -h 127.0.0.1 -p $Port -U parkos_app -d parkos -c $Command 2>&1
}

# Wrapper minimo sobre el metodo estatico .NET [System.Diagnostics.EventLog]::
# SourceExists() - Pester no puede mockear una llamada a un metodo estatico
# de .NET directamente (a diferencia de un cmdlet o una funcion), asi que se
# aisla en su propia funcion mockeable, mismo criterio que el resto de los
# wrappers de este archivo (Invoke-ParkosNssm, Invoke-ParkosPsql). Usado por
# Export-ParkosDiagnostics para decidir si eventlog.csv tiene contenido real
# o solo el header (maquina que nunca corrio Invoke-ParkosUpdate).
function script:Test-ParkosEventLogSourceExists {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Source)

    return [System.Diagnostics.EventLog]::SourceExists($Source)
}

# Redacta secretos de UNA linea de texto - usada por Export-ParkosDiagnostics
# sobre TODO archivo de texto que genera (no solo env-redacted.txt), porque
# un secreto puede aparecer incrustado dentro de una linea mas larga (ej.
# "nssm dump" vuelca todo AppEnvironmentExtra - incluyendo
# PARKOS_JWT_SECRET/PARKOS_DB_URL - adentro de una sola linea de su salida).
# Por eso NINGUN patron esta anclado a inicio/fin de linea (^...$): busca la
# ocurrencia en cualquier parte de la linea, no solo cuando la linea entera
# es exactamente "KEY=VALUE".
#
# Dos reglas, en este orden (no hay conflicto de orden real: PARKOS_DB_URL/
# DATABASE_URL no contienen ninguna de las palabras clave genericas):
#   1. Caso especial URL postgresql://usuario:password@host - redacta SOLO
#      la contrasena, preservando usuario@host:puerto/db visible (mismo
#      formato de ejemplo del plan: ...postgresql_app:<redactado, 87
#      caracteres>@...).
#   2. Caso generico KEY=VALUE donde KEY contiene JWT, PASSWORD, _KEY_PATH,
#      TOKEN o SECRET (case-insensitive) - redacta el VALUE completo.
# Ambas reemplazan por "<redactado, N caracteres>" (N = longitud real del
# valor original) para dar contexto de tamano sin exponer nada.
#
# Limitacion conocida y aceptada: el VALUE (o la contrasena de la URL) se
# corta en el primer espacio/comilla/'@' - un valor con espacios sin
# comillas (poco comun en este .env) quedaria parcialmente sin cubrir
# despues del primer espacio; los defaults de este instalador (rutas bajo
# C:\ProgramData\Parkos, sin espacios) no caen en este caso.
function script:Protect-ParkosDiagnosticText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [AllowEmptyString()]
        [string]$Line
    )

    process {
        $result = $Line

        $urlEvaluator = [System.Text.RegularExpressions.MatchEvaluator]{
            param($m)
            $pass = $m.Groups['pass'].Value
            "$($m.Groups['prefix'].Value)<redactado, $($pass.Length) caracteres>$($m.Groups['suffix'].Value)"
        }
        $result = [regex]::Replace(
            $result,
            '(?i)(?<prefix>postgresql(?:\+\w+)?://[^:/\s@"]+:)(?<pass>[^@\s"]+)(?<suffix>@)',
            $urlEvaluator
        )

        $keyEvaluator = [System.Text.RegularExpressions.MatchEvaluator]{
            param($m)
            $val = $m.Groups['value'].Value
            "$($m.Groups['key'].Value)<redactado, $($val.Length) caracteres>"
        }
        $result = [regex]::Replace(
            $result,
            '(?i)(?<!\w)(?<key>[A-Za-z0-9_]*(?:JWT|PASSWORD|_KEY_PATH|TOKEN|SECRET)[A-Za-z0-9_]*\s*=\s*)(?<value>[^\s"]+)',
            $keyEvaluator
        )

        $result
    }
}

# Gate de seguridad real (no cosmetico) que corre Export-ParkosDiagnostics
# ANTES de empaquetar - escanea todo archivo de texto ya generado (y
# supuestamente ya redactado por Protect-ParkosDiagnosticText de arriba)
# buscando el MISMO tipo de ocurrencia (URL postgresql:// con contrasena,
# variable con palabra clave de secreto) pero exigiendo que el valor
# capturado YA sea el placeholder "<redactado, N caracteres>" - si el valor
# capturado NO tiene esa forma, la redaccion de esa linea fallo y se reporta
# como hallazgo. Correr el regex de deteccion "en crudo" (sin este chequeo
# de placeholder) habria hecho que el gate SIEMPRE encontrara "coincidencias"
# incluso en un archivo perfectamente redactado (toda linea "KEY=<redactado,
# N caracteres>" sigue siendo, sintacticamente, una linea "KEY=valor") - por
# eso el criterio real de deteccion es "el valor no tiene forma de
# placeholder", no "la linea tiene forma de KEY=valor".
function script:Test-ParkosDiagnosticsContainSecrets {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $placeholderPattern = '^<redactado, \d+ caracteres>$'
    $findings = [System.Collections.Generic.List[string]]::new()

    $files = Get-ChildItem -Path $Path -File -Recurse -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        $lines = @(Get-Content -Path $file.FullName -ErrorAction SilentlyContinue)
        $lineNumber = 0
        foreach ($line in $lines) {
            $lineNumber++

            foreach ($m in [regex]::Matches($line, '(?i)postgresql(?:\+\w+)?://[^:/\s@"]+:(?<pass>[^@\s"]+)@')) {
                if ($m.Groups['pass'].Value -notmatch $placeholderPattern) {
                    $findings.Add("$($file.FullName):$lineNumber - URL postgresql:// con contrasena sin redactar")
                }
            }

            foreach ($m in [regex]::Matches($line, '(?i)(?<!\w)[A-Za-z0-9_]*(?:JWT|PASSWORD|_KEY_PATH|TOKEN|SECRET)[A-Za-z0-9_]*\s*=\s*(?<value>[^\s"]+)')) {
                if ($m.Groups['value'].Value -notmatch $placeholderPattern) {
                    $findings.Add("$($file.FullName):$lineNumber - variable con palabra clave de secreto sin redactar")
                }
            }
        }
    }

    return [PSCustomObject]@{
        HasSecrets = (@($findings).Count -gt 0)
        Findings   = @($findings)
    }
}

# Verificacion de integridad de base de datos a nivel SQL (no solo TCP como
# el check "Postgres alcanzable" de Get-ParkosHealth) - usado por
# Repair-ParkosInstall (E6): SELECT 1 confirma que el servidor responde
# consultas reales (no solo que el puerto acepta conexiones), y SELECT
# current_user confirma que la identidad de runtime (parkos_app) sigue
# siendo la que responde. Aislado en su propia funcion para que sea
# mockeable en tests sin invocar psql.exe de verdad.
function script:Test-ParkosDatabaseIntegrity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PsqlExePath,
        [Parameter(Mandatory)][int]$Port
    )

    try {
        $selectOne = (& $PsqlExePath -w -h 127.0.0.1 -p $Port -U parkos_app -d parkos -tAc 'SELECT 1;' 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $selectOne -or $selectOne.Trim() -ne '1') { return $false }

        $currentUser = (& $PsqlExePath -w -h 127.0.0.1 -p $Port -U parkos_app -d parkos -tAc 'SELECT current_user;' 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $currentUser -or $currentUser.Trim() -ne 'parkos_app') { return $false }

        return $true
    } catch {
        return $false
    }
}

# Algoritmo de retencion "abuelo-padre-hijo" (7+4+1) para
# Register-ParkosBackupTask/Invoke-DailyBackup.ps1 - funcion PURA (nunca
# toca el filesystem) para poder testearla sin mocks de disco. El mismo
# algoritmo se duplica inline dentro del here-string que
# Register-ParkosBackupTask genera para Invoke-DailyBackup.ps1: ese script
# standalone corre bajo svc-parkos sin el modulo Parkos importado, y no
# puede llamar una funcion script:-scoped de un modulo que no importa -
# mismo criterio de duplicacion ya aceptado en el resto del instalador
# (Invoke-ParkosNssm/Invoke-ParkosPsql/etc en este mismo archivo, o los
# wrappers pg_dump/pg_restore duplicados entre este modulo y
# parkos-installer.ps1).
#
# Algoritmo EXACTO, deliberadamente determinista (no reinterpretar):
#   1. Ordenar las fechas descendente (mas reciente primero).
#   2. Tier "hijo" (diario): las 7 fechas mas recientes SIEMPRE se
#      conservan, sin excepcion.
#   3. Tier "padre" (semanal): de las fechas restantes (posicion 8 en
#      adelante), recorridas en el mismo orden descendente, se conserva la
#      PRIMERA fecha de cada semana ISO distinta (ISOWeek.GetYear +
#      ISOWeek.GetWeekOfYear), hasta un maximo de 4 semanas distintas.
#   4. Tier "abuelo" (mensual): de lo que sobra despues de los 2 tiers de
#      arriba, se conserva como maximo UNA fecha adicional (la primera en
#      orden descendente) - nunca "1 por mes historico distinto".
#   5. Todo lo que no quedo en Keep (hijo+padre+abuelo) va a Delete.
function script:Get-ParkosBackupRetentionPlan {
    [CmdletBinding()]
    param([Parameter(Mandatory)][datetime[]]$DumpDates)

    $sorted = @($DumpDates | Sort-Object -Descending)
    $keep = [System.Collections.Generic.List[datetime]]::new()

    # --- Tier hijo (diario): las 7 mas recientes ------------------------
    $dailyCount = [Math]::Min(7, $sorted.Count)
    for ($i = 0; $i -lt $dailyCount; $i++) { $keep.Add($sorted[$i]) }
    $remaining = if ($sorted.Count -gt 7) { @($sorted[7..($sorted.Count - 1)]) } else { @() }

    # --- Tier padre (semanal): 1ra fecha de cada semana ISO, hasta 4 ----
    $seenWeeks = [System.Collections.Generic.HashSet[string]]::new()
    $weeklyCount = 0
    $afterWeekly = [System.Collections.Generic.List[datetime]]::new()
    foreach ($date in $remaining) {
        $weekKey = "$([System.Globalization.ISOWeek]::GetYear($date))-W$([System.Globalization.ISOWeek]::GetWeekOfYear($date))"
        if ($weeklyCount -lt 4 -and -not $seenWeeks.Contains($weekKey)) {
            $seenWeeks.Add($weekKey) | Out-Null
            $weeklyCount++
            $keep.Add($date)
        } else {
            $afterWeekly.Add($date)
        }
    }

    # --- Tier abuelo (mensual): como maximo 1 fecha adicional -----------
    $delete = [System.Collections.Generic.List[datetime]]::new()
    for ($i = 0; $i -lt $afterWeekly.Count; $i++) {
        if ($i -eq 0) { $keep.Add($afterWeekly[$i]) } else { $delete.Add($afterWeekly[$i]) }
    }

    return [PSCustomObject]@{ Keep = @($keep); Delete = @($delete) }
}

# ---------------------------------------------------------------------------
# Public cmdlets - PR1 placeholders (FunctionsToExport in Parkos.psd1)
# ---------------------------------------------------------------------------

function Get-ParkosHealth {
    <#
    .SYNOPSIS
        Reports the health of an existing Parkos branch installation.

    .DESCRIPTION
        Future signature: Get-ParkosHealth [-Detailed]

        Runs 6 checks: Postgres reachable, api-sucursal service running,
        job-sync-sucursal service running, /health responds 200, doctor.exe
        passes, disk has more than 5GB free (WARN when <=10% free). If
        nothing is installed it reports a single FAIL line (ExitCode 2,
        NotInstalled=$true). Exit codes: 0 (all OK),
        1 (degraded - at least one non-critical check failed), 2 (critical -
        installation cannot be considered healthy).

    .PARAMETER Detailed
        Prints the per-check breakdown instead of only the summary verdict.

    .EXAMPLE
        PS C:\> Get-ParkosHealth

    .EXAMPLE
        PS C:\> Get-ParkosHealth -Detailed

    .NOTES
        PowerShell no tiene un exit code real para una funcion de modulo -
        por eso este cmdlet devuelve el objeto [PSCustomObject] Y ADEMAS
        setea $global:LASTEXITCODE, para que un script que la invoque pueda
        hacer algo como: & { Get-ParkosHealth } ; exit $LASTEXITCODE

        Regla de exit code: 0 si los 6 checks estan OK, 1 si hay al menos un
        WARN y cero FAIL, 2 si hay al menos un FAIL.
    #>
    [CmdletBinding()]
    param(
        [switch]$Detailed
    )

    Write-ParkosLog 'Get-ParkosHealth invoked.'

    $paths = Resolve-ParkosPaths
    $envFilePath = Join-Path $paths.SecretsPath '.env'

    $envMap = $null
    $envLoadError = $null
    try {
        $envMap = Import-ParkosEnvFile -Path $envFilePath
    } catch {
        $envLoadError = $_.Exception.Message
    }
    $noInstallMessage = "No se encontro instalacion en $($paths.InstallPath)."

    # Early exit: nada instalado (ni carpeta de instalacion ni .env). Los 6
    # checks fallarian todos con el mismo mensaje redundante; se reporta UNA
    # linea clara. ExitCode 2 (critico) para no cambiar la semantica que
    # esperan Repair/Update/menu A; NotInstalled permite distinguirlo.
    if (-not $envMap -and -not (Test-Path -LiteralPath $paths.InstallPath)) {
        $notInstalledDetail = "Parkos no esta instalado (sin instalacion en $($paths.InstallPath) ni .env en $envFilePath)."
        Write-Host '[FAIL] Parkos no esta instalado' -ForegroundColor Red
        if ($Detailed) {
            Write-Host "       $notInstalledDetail" -ForegroundColor Red
        }
        Write-ParkosLog 'Get-ParkosHealth exit code: 2 (Parkos no esta instalado).'
        $global:LASTEXITCODE = 2
        return [PSCustomObject]@{
            ExitCode     = 2
            NotInstalled = $true
            Checks       = [ordered]@{ 'Instalacion' = @{ Status = 'FAIL'; Detail = $notInstalledDetail } }
        }
    }

    $checks = [ordered]@{}

    # 1. Postgres alcanzable
    try {
        if (-not $envMap) { throw "$noInstallMessage $envLoadError" }
        $pgPort = Get-ParkosPostgresPort -EnvMap $envMap
        $pgReachable = Test-NetConnection -ComputerName '127.0.0.1' -Port $pgPort -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($pgReachable) {
            $checks['Postgres alcanzable'] = @{ Status = 'OK'; Detail = "Puerto $pgPort respondio." }
        } else {
            $checks['Postgres alcanzable'] = @{ Status = 'FAIL'; Detail = "Puerto $pgPort no respondio." }
        }
    } catch {
        $checks['Postgres alcanzable'] = @{ Status = 'FAIL'; Detail = $_.Exception.Message }
    }

    # 2. Servicio api-sucursal
    try {
        $svc = Get-Service -Name 'ParkosApiSucursal' -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq 'Running') {
            $checks['Servicio api-sucursal'] = @{ Status = 'OK'; Detail = 'ParkosApiSucursal esta Running.' }
        } else {
            $estado = if ($svc) { $svc.Status } else { 'no encontrado' }
            $checks['Servicio api-sucursal'] = @{ Status = 'FAIL'; Detail = "ParkosApiSucursal: $estado." }
        }
    } catch {
        $checks['Servicio api-sucursal'] = @{ Status = 'FAIL'; Detail = $_.Exception.Message }
    }

    # 3. Servicio job-sync-sucursal (no critico - detenido es WARN, no FAIL)
    try {
        $svc = Get-Service -Name 'ParkosJobSyncSucursal' -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq 'Running') {
            $checks['Servicio job-sync-sucursal'] = @{ Status = 'OK'; Detail = 'ParkosJobSyncSucursal esta Running.' }
        } else {
            $estado = if ($svc) { $svc.Status } else { 'no encontrado' }
            $checks['Servicio job-sync-sucursal'] = @{ Status = 'WARN'; Detail = "ParkosJobSyncSucursal: $estado (no critico para servir trafico, reparable)." }
        }
    } catch {
        $checks['Servicio job-sync-sucursal'] = @{ Status = 'WARN'; Detail = $_.Exception.Message }
    }

    # 4. /health responde 200
    try {
        if (-not $envMap) { throw "$noInstallMessage $envLoadError" }
        if (-not $envMap.Contains('PORT')) { throw 'El .env no contiene la variable PORT.' }
        $apiPort = $envMap['PORT']
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$apiPort/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            $checks['API /health'] = @{ Status = 'OK'; Detail = "Puerto $apiPort respondio 200." }
        } else {
            $checks['API /health'] = @{ Status = 'FAIL'; Detail = "Puerto $apiPort respondio $($resp.StatusCode)." }
        }
    } catch {
        $checks['API /health'] = @{ Status = 'FAIL'; Detail = $_.Exception.Message }
    }

    # 5. Doctor pasa
    try {
        if (-not $envMap) { throw "$noInstallMessage $envLoadError" }
        $doctorExe = Join-Path $paths.InstallPath 'doctor\doctor.exe'
        $doctorJson = Invoke-ParkosDoctorExe -DoctorExePath $doctorExe -EnvMap $envMap
        $doctorOk = ($doctorJson.env_status -eq 'ok') -and ($doctorJson.db_connectivity -like 'ok*') -and ($doctorJson.jwt_key_path_exists -eq $true)
        if ($doctorOk) {
            $checks['Doctor'] = @{ Status = 'OK'; Detail = 'env_status=ok, db_connectivity=ok*, jwt_key_path_exists=true.' }
        } else {
            $checks['Doctor'] = @{ Status = 'FAIL'; Detail = "env_status=$($doctorJson.env_status), db_connectivity=$($doctorJson.db_connectivity), jwt_key_path_exists=$($doctorJson.jwt_key_path_exists)." }
        }
    } catch {
        $checks['Doctor'] = @{ Status = 'FAIL'; Detail = $_.Exception.Message }
    }

    # 6. Espacio en disco: FAIL solo bajo el piso absoluto (5GB, igual que el
    # pre-flight del instalador); el porcentaje (<=10%) es solo WARN, porque
    # en discos grandes 9% libre son cientos de GB.
    try {
        $driveLetter = $paths.InstallPath.Substring(0, 1)
        $drive = Get-PSDrive -Name $driveLetter -ErrorAction Stop
        $total = $drive.Free + $drive.Used
        $freeRatio = if ($total -gt 0) { $drive.Free / $total } else { 0 }
        $freeGb = [math]::Round($drive.Free / 1GB, 1)
        if ($drive.Free -le 5GB) {
            $checks['Espacio en disco'] = @{ Status = 'FAIL'; Detail = ("Solo {0} GB libres en {1}: (minimo 5 GB)." -f $freeGb, $driveLetter) }
        } elseif ($freeRatio -le 0.10) {
            $checks['Espacio en disco'] = @{ Status = 'WARN'; Detail = ("{0:P1} libre en {1}: ({2} GB)." -f $freeRatio, $driveLetter, $freeGb) }
        } else {
            $checks['Espacio en disco'] = @{ Status = 'OK'; Detail = ("{0:P1} libre en {1}: ({2} GB)." -f $freeRatio, $driveLetter, $freeGb) }
        }
    } catch {
        $checks['Espacio en disco'] = @{ Status = 'FAIL'; Detail = $_.Exception.Message }
    }

    foreach ($entry in $checks.GetEnumerator()) {
        $status = $entry.Value.Status
        $color = switch ($status) {
            'OK'    { 'Green' }
            'WARN'  { 'Yellow' }
            default { 'Red' }
        }
        Write-Host "[$status] $($entry.Key)" -ForegroundColor $color
        if ($Detailed) {
            Write-Host "       $($entry.Value.Detail)" -ForegroundColor $color
        }
    }

    # @(...) fuerza array incluso con 0 o 1 coincidencias - sin esto, bajo
    # Set-StrictMode -Version Latest, ".Count" sobre $null (0 matches) tira
    # PropertyNotFoundException en vez de devolver 0.
    $failCount = @($checks.Values | Where-Object { $_.Status -eq 'FAIL' }).Count
    $warnCount = @($checks.Values | Where-Object { $_.Status -eq 'WARN' }).Count
    $exitCode = if ($failCount -gt 0) { 2 } elseif ($warnCount -gt 0) { 1 } else { 0 }

    Write-ParkosLog "Get-ParkosHealth exit code: $exitCode ($failCount FAIL, $warnCount WARN)."
    $global:LASTEXITCODE = $exitCode

    return [PSCustomObject]@{ ExitCode = $exitCode; Checks = $checks }
}

function Repair-ParkosInstall {
    <#
    .SYNOPSIS
        Auto-repairs a set of known-safe failure scenarios on an existing
        Parkos branch installation.

    .DESCRIPTION
        Covers 7 scenarios: E1 (NSSM registration missing for
        ParkosApiSucursal/ParkosJobSyncSucursal), E2 (a registered service
        stopped - started with 3 retries, backoff 1/5/30s), E3 (an installed
        binary's hash does not match manifest.sha256.json - DEC-INST-23),
        E4 (secrets\ ACL drifted from Administrators+SYSTEM-only), E5 (.env
        missing or unparseable), E6 (database fails a SQL-level integrity
        check - SELECT 1 / current_user) and E7 (E2's 3 retries exhausted
        without the service coming up). E6/E7 abort the ENTIRE repair (no
        further scenario is processed) and call Export-ParkosDiagnostics;
        E3/E5 degrade to a clear warning and CONTINUE with the rest when no
        prior release/backup is available to restore from (there may
        simply be no releases\ or backups\ content yet on a fresh
        installation - Register-ParkosBackupTask, PR8, does not retroactively
        create backup history for an install that predates it).

        Detection always runs first (independent of -WhatIf); every
        detected scenario is auto-fixed, in order E1 to E7, unless -WhatIf
        is given (nothing is applied, only reported) or the interactive
        confirmation is declined.

    .PARAMETER Force
        Skips the confirmation prompt ("Reparar? (s/N)") that otherwise
        precedes any real auto-fix when -WhatIf is not given.

    .EXAMPLE
        PS C:\> Repair-ParkosInstall -WhatIf

    .EXAMPLE
        PS C:\> Repair-ParkosInstall -Force

    .NOTES
        -WhatIf/-Confirm come from SupportsShouldProcess, not a hand-rolled
        switch. Exit codes: 0 (healthy already, or repaired - even if E3/E5
        degraded to "not repairable, continued"), 3 (aborted on E6/E7 or on
        an unknown failure with no matching scenario - manual intervention
        required).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [switch]$Force
    )

    Write-ParkosLog 'Repair-ParkosInstall invoked.'

    if (-not (Test-IsAdmin)) {
        throw 'Repair-ParkosInstall requiere permisos de administrador.'
    }

    $paths = Resolve-ParkosPaths
    $envFilePath = Join-Path $paths.SecretsPath '.env'

    Write-Host '[Parkos] Diagnostico inicial:' -ForegroundColor Cyan
    $health = Get-ParkosHealth

    if ($health.ExitCode -eq 0) {
        Write-Host '[Parkos] Instalacion saludable, nada que reparar.' -ForegroundColor Green
        Write-ParkosLog 'Repair-ParkosInstall exit code: 0 (nada que reparar).'
        $global:LASTEXITCODE = 0
        return [PSCustomObject]@{ ExitCode = 0; Scenarios = @() }
    }

    # -------------------------------------------------------------------
    # Deteccion (siempre corre, incluso bajo -WhatIf - son checks de
    # lectura, nunca gateados por ShouldProcess).
    # -------------------------------------------------------------------
    $apiSvc = Get-Service -Name 'ParkosApiSucursal' -ErrorAction SilentlyContinue
    $jobSvc = Get-Service -Name 'ParkosJobSyncSucursal' -ErrorAction SilentlyContinue
    $e1 = (-not $apiSvc) -or (-not $jobSvc)
    $e2 = (($apiSvc -and $apiSvc.Status -ne 'Running') -or ($jobSvc -and $jobSvc.Status -ne 'Running'))

    $binaryInstallPaths = [ordered]@{
        'api-sucursal.exe'      = Join-Path $paths.InstallPath 'api-sucursal\api-sucursal.exe'
        'job-sync-sucursal.exe' = Join-Path $paths.InstallPath 'job-sync-sucursal\job-sync-sucursal.exe'
        'doctor.exe'            = Join-Path $paths.InstallPath 'doctor\doctor.exe'
    }
    $mismatchedBinaries = @()
    $manifestPath = Join-Path $paths.DataPath 'manifest.sha256.json'
    if (Test-Path $manifestPath) {
        try {
            $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
            foreach ($binName in $binaryInstallPaths.Keys) {
                if (-not ($manifest.binaries.PSObject.Properties.Name -contains $binName)) { continue }
                $binPath = $binaryInstallPaths[$binName]
                if (-not (Test-Path $binPath)) { continue }
                $actualHash = (Get-FileHash -Path $binPath -Algorithm SHA256).Hash
                if ($actualHash -ne $manifest.binaries.$binName) {
                    $mismatchedBinaries += $binName
                }
            }
        } catch {
            # manifest.sha256.json corrupto/no parseable - no se puede
            # comparar, se trata como "sin evidencia de alteracion" en vez
            # de asumir E3 sin datos reales.
        }
    }
    $e3 = @($mismatchedBinaries).Count -gt 0

    $aclCheck = Test-ParkosSecretsAcl
    $e4 = ($aclCheck.ExitCode -ne 0)

    $envReadable = $true
    try {
        if (-not (Test-Path $envFilePath)) { $envReadable = $false }
        else { Import-ParkosEnvFile -Path $envFilePath | Out-Null }
    } catch {
        $envReadable = $false
    }
    $e5 = -not $envReadable

    $dbPort = $null
    if ($envReadable) {
        try {
            $dbPort = Get-ParkosPostgresPort -EnvMap (Import-ParkosEnvFile -Path $envFilePath)
        } catch { }
    }
    $e6 = $false
    if ($dbPort) {
        $e6 = -not (Test-ParkosDatabaseIntegrity -PsqlExePath $script:PsqlExePath -Port $dbPort)
    }

    $scenarios = @()
    if ($e1) { $scenarios += 'E1' }
    if ($e2) { $scenarios += 'E2' }
    if ($e3) { $scenarios += 'E3' }
    if ($e4) { $scenarios += 'E4' }
    if ($e5) { $scenarios += 'E5' }
    if ($e6) { $scenarios += 'E6' }

    if ($scenarios.Count -eq 0) {
        Write-Host '[Parkos] Get-ParkosHealth reporto fallas pero ningun escenario E1-E6 conocido aplica; no hay auto-fix disponible.' -ForegroundColor Red
        Write-ParkosLog 'Repair-ParkosInstall exit code: 3 (sin escenario conocido).'
        $global:LASTEXITCODE = 3
        return [PSCustomObject]@{ ExitCode = 3; Scenarios = @(); Detail = 'No se detecto un escenario de auto-fix conocido (E1-E6); revisar manualmente.' }
    }

    Write-Host "[Parkos] Escenarios detectados: $($scenarios -join ', ')" -ForegroundColor Yellow

    if (-not $WhatIfPreference -and -not $Force) {
        $answer = Read-Host 'Reparar? (s/N)'
        if ($answer -notmatch '^[sS]') {
            Write-Host '[Parkos] Reparacion cancelada por el usuario; no se aplico ningun cambio.' -ForegroundColor Yellow
            Write-ParkosLog 'Repair-ParkosInstall exit code: 0 (cancelado por el usuario).'
            $global:LASTEXITCODE = 0
            return [PSCustomObject]@{
                ExitCode  = 0
                Scenarios = @($scenarios | ForEach-Object { [PSCustomObject]@{ Scenario = $_; WouldFix = $true } })
                Detail    = 'Reparacion cancelada por el usuario; no se aplico ningun cambio.'
            }
        }
    }

    $applied = @()

    # --- E1: registro NSSM faltante ------------------------------------
    if ($e1) {
        if ($PSCmdlet.ShouldProcess('ParkosApiSucursal/ParkosJobSyncSucursal', 'Re-registrar servicio(s) faltante(s) con NSSM')) {
            $nssmPath = Join-Path $paths.InstallPath 'nssm.exe'
            if (-not (Test-Path $nssmPath)) {
                throw "No se encontro nssm.exe en $nssmPath - no se puede re-registrar el servicio NSSM faltante (E1)."
            }
            $envVarsApi = $null
            $envVarsJob = $null
            if (Test-Path $envFilePath) {
                # Fase 27 (DEC-INST-40): Import-ParkosEnvFile ya decodifica
                # CMS o texto plano de forma transparente - NSSM sigue
                # necesitando las variables en texto plano en su
                # AppEnvironmentExtra real (el servicio no sabe leer CMS),
                # eso no cambia; lo que cambia es como este cmdlet las
                # extrae del .env para reconstruirlas.
                $envLinesE1 = @((Import-ParkosEnvFile -Path $envFilePath).GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })
                $envVarsApi = $envLinesE1 -join "`r`n"
                $envVarsJob = ($envLinesE1 + @(
                    'PARKOS_SYNC_POLL_INTERVAL_S=10', 'PARKOS_SYNC_BATCH_SIZE=100'
                )) -join "`r`n"
            }

            if (-not $apiSvc) {
                $apiExePath = $binaryInstallPaths['api-sucursal.exe']
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('install', 'ParkosApiSucursal', $apiExePath) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppDirectory', (Split-Path $apiExePath)) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppStdout', (Join-Path $paths.LogsPath 'api-sucursal.out.log')) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppStderr', (Join-Path $paths.LogsPath 'api-sucursal.err.log')) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppRotateFiles', '1') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppRotateBytes', '10485760') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppRotateOnline', '1') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'Start', 'SERVICE_AUTO_START') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppRestartDelay', '1000') | Out-Null
                if ($envVarsApi) {
                    Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosApiSucursal', 'AppEnvironmentExtra', $envVarsApi) | Out-Null
                }
                Write-Host '[OK] ParkosApiSucursal re-registrado con NSSM.' -ForegroundColor Green
            }
            if (-not $jobSvc) {
                $jobExePath = $binaryInstallPaths['job-sync-sucursal.exe']
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('install', 'ParkosJobSyncSucursal', $jobExePath) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppDirectory', (Split-Path $jobExePath)) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppStdout', (Join-Path $paths.LogsPath 'job-sync.out.log')) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppRotateFiles', '1') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppRotateBytes', '10485760') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'Start', 'SERVICE_AUTO_START') | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppRestartDelay', '1000') | Out-Null
                if ($envVarsJob) {
                    Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('set', 'ParkosJobSyncSucursal', 'AppEnvironmentExtra', $envVarsJob) | Out-Null
                }
                Write-Host '[OK] ParkosJobSyncSucursal re-registrado con NSSM.' -ForegroundColor Green
            }
            $applied += [PSCustomObject]@{ Scenario = 'E1'; WouldFix = $false }
        } else {
            $applied += [PSCustomObject]@{ Scenario = 'E1'; WouldFix = $true }
        }
    }

    # --- E2 (+ posible escalada a E7): arrancar servicio(s) detenidos ---
    # Corre para CUALQUIER servicio que hoy no este Running, incluidos los
    # que E1 acaba de registrar (un servicio NSSM recien registrado siempre
    # arranca detenido) - por eso no depende de $e2 en soledad.
    $apiPortForHealth = $null
    if ($envReadable) {
        try {
            $envMapForPort = Import-ParkosEnvFile -Path $envFilePath
            if ($envMapForPort.Contains('PORT')) { $apiPortForHealth = $envMapForPort['PORT'] }
        } catch { }
    }

    foreach ($svcName in 'ParkosApiSucursal', 'ParkosJobSyncSucursal') {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if (-not $svc -or $svc.Status -eq 'Running') { continue }

        if (-not $PSCmdlet.ShouldProcess($svcName, 'Iniciar servicio (reintentos 1/5/30s)')) {
            $applied += [PSCustomObject]@{ Scenario = 'E2'; WouldFix = $true }
            continue
        }

        $started = $false
        foreach ($delaySeconds in 1, 5, 30) {
            try { Start-Service -Name $svcName -ErrorAction Stop } catch { }
            Start-Sleep -Seconds $delaySeconds
            if ($svcName -eq 'ParkosApiSucursal' -and $apiPortForHealth) {
                try {
                    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$apiPortForHealth/health" -UseBasicParsing -TimeoutSec 3
                    if ($resp.StatusCode -eq 200) { $started = $true }
                } catch { }
            } else {
                $liveStatus = (Get-Service -Name $svcName -ErrorAction SilentlyContinue).Status
                if ($liveStatus -eq 'Running') { $started = $true }
            }
            if ($started) { break }
        }

        if (-not $started) {
            Write-Host "[FAIL] $svcName no arranco tras 3 reintentos (1/5/30s) - escalando a E7, abortando el resto de la reparacion." -ForegroundColor Red
            Export-ParkosDiagnostics
            $applied += [PSCustomObject]@{ Scenario = 'E7'; WouldFix = $false }
            $scenariosJoined = ($applied | ForEach-Object { $_.Scenario }) -join ', '
            Write-ParkosLog "Repair-ParkosInstall exit code: 3 (E7, escenarios: $scenariosJoined)."
            $global:LASTEXITCODE = 3
            return [PSCustomObject]@{
                ExitCode  = 3
                Scenarios = $applied
                Detail    = "$svcName no respondio tras 3 reintentos - abortando el resto de la reparacion (escenarios: $scenariosJoined). Export-ParkosDiagnostics invocado (PR7 completa su implementacion real)."
            }
        }
        Write-Host "[OK] $svcName arrancado correctamente." -ForegroundColor Green
        $applied += [PSCustomObject]@{ Scenario = 'E2'; WouldFix = $false }
    }

    # --- E3: binario alterado -------------------------------------------
    if ($e3) {
        foreach ($binName in $mismatchedBinaries) {
            $restored = $false
            if (Test-Path $paths.ReleasesPath) {
                $releaseDirs = Get-ChildItem -Path $paths.ReleasesPath -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
                foreach ($releaseDir in $releaseDirs) {
                    $candidate = Join-Path $releaseDir.FullName $binName
                    if (Test-Path $candidate) {
                        if ($PSCmdlet.ShouldProcess($binName, "Restaurar desde release anterior ($($releaseDir.Name))")) {
                            Copy-Item -Path $candidate -Destination $binaryInstallPaths[$binName] -Force
                            Write-Host "[OK] $binName restaurado desde la release $($releaseDir.Name)." -ForegroundColor Green
                            $restored = $true
                        }
                        break
                    }
                }
            }
            if (-not $restored) {
                Write-Host "[WARN] $binName no coincide con manifest.sha256.json y no hay una release anterior disponible en $($paths.ReleasesPath) - no reparable automaticamente, continuando con el resto." -ForegroundColor Yellow
            }
            $applied += [PSCustomObject]@{ Scenario = 'E3'; WouldFix = -not $restored }
        }
    }

    # --- E4: ACL alterada -------------------------------------------------
    if ($e4) {
        if ($PSCmdlet.ShouldProcess($paths.SecretsPath, 'Re-aplicar ACL (Administrators+SYSTEM)')) {
            Set-ParkosSecretsAcl -Path $paths.SecretsPath
            Write-Host "[OK] ACL de $($paths.SecretsPath) re-aplicada (Administrators+SYSTEM)." -ForegroundColor Green
            $applied += [PSCustomObject]@{ Scenario = 'E4'; WouldFix = $false }
        } else {
            $applied += [PSCustomObject]@{ Scenario = 'E4'; WouldFix = $true }
        }
    }

    # --- E5: .env ilegible -------------------------------------------------
    if ($e5) {
        $restored = $false
        if (Test-Path $paths.BackupsPath) {
            $latestBackup = Get-ChildItem -Path $paths.BackupsPath -Filter '*.env*' -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($latestBackup) {
                if ($PSCmdlet.ShouldProcess($envFilePath, "Restaurar desde backup ($($latestBackup.Name))")) {
                    New-Item -ItemType Directory -Force -Path (Split-Path $envFilePath) | Out-Null
                    Copy-Item -Path $latestBackup.FullName -Destination $envFilePath -Force
                    Write-Host "[OK] .env restaurado desde el backup $($latestBackup.Name)." -ForegroundColor Green
                    $restored = $true
                }
            }
        }
        if (-not $restored) {
            Write-Host "[WARN] El .env no existe o no se pudo parsear y no hay backup disponible en $($paths.BackupsPath) - .env sigue corrupto, continuando con el resto." -ForegroundColor Yellow
        }
        $applied += [PSCustomObject]@{ Scenario = 'E5'; WouldFix = -not $restored }
    }

    # --- E6: base de datos corrupta - aborta el resto --------------------
    if ($e6) {
        Write-Host '[FAIL] La base de datos no paso la verificacion de integridad (SELECT 1 / current_user) - escalando a E6, abortando el resto de la reparacion.' -ForegroundColor Red
        Export-ParkosDiagnostics
        $applied += [PSCustomObject]@{ Scenario = 'E6'; WouldFix = $false }
        $scenariosJoined = ($applied | ForEach-Object { $_.Scenario }) -join ', '
        Write-ParkosLog "Repair-ParkosInstall exit code: 3 (E6, escenarios: $scenariosJoined)."
        $global:LASTEXITCODE = 3
        return [PSCustomObject]@{
            ExitCode  = 3
            Scenarios = $applied
            Detail    = "Base de datos corrupta o current_user inesperado (escenarios: $scenariosJoined). Export-ParkosDiagnostics invocado (PR7 completa su implementacion real)."
        }
    }

    Write-Host '[Parkos] Diagnostico post-reparacion:' -ForegroundColor Cyan
    $postHealth = Get-ParkosHealth
    $scenariosJoined = if ($applied.Count -gt 0) { ($applied | ForEach-Object { $_.Scenario }) -join ', ' } else { 'ninguno' }
    $detail = "Escenarios procesados: $scenariosJoined. Salud post-reparacion: ExitCode=$($postHealth.ExitCode)."
    Write-ParkosLog "Repair-ParkosInstall exit code: 0 ($detail)"
    $global:LASTEXITCODE = 0
    return [PSCustomObject]@{ ExitCode = 0; Scenarios = $applied; Detail = $detail }
}

function Uninstall-Parkos {
    <#
    .SYNOPSIS
        Uninstalls a Parkos branch installation.

    .DESCRIPTION
        Removes services (ParkosApiSucursal, ParkosJobSyncSucursal via
        NSSM), the ParkosPgPartmanMaintenance scheduled task, the
        web_sucursal MSI (via its Windows Uninstall registry entry - same
        pattern as Uninstall-ParkosElectron in parkos-installer.ps1),
        InstallPath (binarios: api-sucursal, job-sync-sucursal, doctor,
        nssm.exe) and finally its own PowerShell module folder - always,
        with or without -PurgeData.

        By default (no -PurgeData) DataPath's Postgres data (pg-data\),
        backups\, secrets\, logs\ and installer-runs\ quedan PRESERVADOS,
        el usuario local svc-parkos queda PRESERVADO, y el servicio/
        instalacion de Postgres quedan PRESERVADOS (puede estar compartido
        con otro uso en esta maquina). Con -PurgeData todo eso tambien se
        borra: las subcarpetas de datos de DataPath, ParkosBackupDiario (si
        existe - PR8 todavia puede no haberla creado, manejado con
        gracia), svc-parkos, y el propio Postgres (servicio detenido + su
        carpeta de instalacion borrada; pg-data ya queda cubierto arriba).

        Exige una confirmacion de doble paso antes de tocar nada:
        interactivamente, la palabra literal DESINSTALAR (sin -PurgeData) o
        CONFIRMAR (-PurgeData); si no coincide, cancela limpio sin ninguna
        mutacion. -Unattended salta el prompt; -Unattended junto con
        -PurgeData exige ademas -UnattendedPurgeConfirmed como confirmacion
        explicita no interactiva de que la purga de datos fue intencional
        (si falta, throw). Preservar datos en modo -Unattended no necesita
        ningun flag extra - es la opcion segura por default.

        Cada paso individual de limpieza (parar/remover un servicio, borrar
        una carpeta, etc) corre en su propio try/catch: un paso que falla
        se loguea como advertencia y NO frena el resto de la desinstalacion.
        Si algun paso fallo, el ExitCode devuelto es 1 aunque la
        desinstalacion haya terminado igual, y el Detail lista que no se
        pudo limpiar.

    .PARAMETER PurgeData
        Tambien borra los datos de DataPath (Postgres pg-data, secrets,
        backups, logs, installer-runs), ParkosBackupDiario, svc-parkos y el
        servicio/instalacion de Postgres, en vez de preservarlos.

    .PARAMETER UnattendedPurgeConfirmed
        Requerido junto con -PurgeData cuando ademas se usa -Unattended;
        sin el, una purga de datos desatendida se rechaza (throw) en vez de
        honrarse en silencio.

    .PARAMETER Unattended
        Salta la confirmacion interactiva por Read-Host. Declara
        explicitamente que no hay un operador presente para responder un
        prompt (este modulo nunca asume "no interactivo" solo por ser un
        modulo - quien lo invoca lo tiene que declarar).

    .EXAMPLE
        PS C:\> Uninstall-Parkos

    .EXAMPLE
        PS C:\> Uninstall-Parkos -PurgeData

    .EXAMPLE
        PS C:\> Uninstall-Parkos -PurgeData -Unattended -UnattendedPurgeConfirmed

    .NOTES
        Exige administrador SIEMPRE, incluso sin -PurgeData: desregistrar
        los servicios NSSM y la tarea programada ParkosPgPartmanMaintenance
        ya requieren admin de por si - gatear el requisito solo a
        -PurgeData habria sido inconsistente con lo que las acciones
        realmente necesitan (DEC-INST-36 en plan.md).

        El modulo se borra a si mismo al final (ultimo bloque de esta
        funcion) - esto es seguro porque PowerShell carga un modulo de
        script (.psm1/.psd1) parseando su contenido a memoria en vez de
        mantener un handle de archivo abierto sobre el .psm1 en disco
        mientras el modulo esta en uso (a diferencia de una DLL nativa, que
        Windows si bloquea mientras el proceso la tiene cargada) - por eso
        borrar el directorio del modulo mientras esta funcion todavia esta
        corriendo no falla ni corrompe la ejecucion en curso; una sesion
        NUEVA que despues intente Import-Module Parkos simplemente no lo va
        a encontrar, que es exactamente lo que significa haberlo
        desinstalado.

        DEC-INST-37 (plan.md): la tabla de politica de preservacion
        original asume $DataPath\releases\, pero el codigo real
        (Resolve-ParkosPaths, DEC-INST-28/30) ubica releases bajo
        $InstallPath\releases - InstallPath se borra siempre (con o sin
        -PurgeData), asi que releases no se puede preservar por separado
        sin -PurgeData; se documenta en vez de reinventar el layout real
        del instalador.
    #>
    [CmdletBinding()]
    param(
        [switch]$PurgeData,
        [switch]$UnattendedPurgeConfirmed,
        [switch]$Unattended
    )

    Write-ParkosLog 'Uninstall-Parkos invoked.'

    # Siempre exige admin - ver DEC-INST-36 en plan.md y el comentario en
    # .NOTES arriba: desregistrar servicios NSSM y una tarea programada ya
    # requieren privilegios elevados de por si, con o sin -PurgeData.
    if (-not (Test-IsAdmin)) {
        throw 'Uninstall-Parkos requiere permisos de administrador.'
    }

    if ($PurgeData -and $Unattended -and -not $UnattendedPurgeConfirmed) {
        throw 'Uninstall-Parkos -PurgeData en modo -Unattended requiere -UnattendedPurgeConfirmed explicito, como confirmacion no interactiva de que el borrado de datos fue intencional.'
    }

    if (-not $Unattended) {
        $expectedWord = if ($PurgeData) { 'CONFIRMAR' } else { 'DESINSTALAR' }
        $promptText = if ($PurgeData) {
            'Esto desinstalara Parkos Y BORRARA TODOS LOS DATOS (Postgres, secrets, backups, logs). Escriba CONFIRMAR para continuar'
        } else {
            'Esto desinstalara Parkos preservando los datos existentes. Escriba DESINSTALAR para continuar'
        }
        $answer = Read-Host $promptText
        if ($answer -ne $expectedWord) {
            Write-Host '[Parkos] Desinstalacion cancelada por el operador; no se aplico ningun cambio.' -ForegroundColor Yellow
            Write-ParkosLog 'Uninstall-Parkos exit code: 1 (cancelado por el operador).'
            $global:LASTEXITCODE = 1
            return [PSCustomObject]@{ ExitCode = 1; Detail = 'Cancelado por el operador.' }
        }
    }

    Write-Host '[Parkos] Iniciando desinstalacion...' -ForegroundColor Cyan

    $paths = Resolve-ParkosPaths
    $warnings = [System.Collections.Generic.List[string]]::new()

    # Helper local de borrado tolerante a fallos - un solo lugar para el
    # patron "si existe, borralo, y si falla loguealo como advertencia sin
    # frenar el resto" que se repite para cada carpeta de datos. Definida
    # dentro de esta funcion (scope local, nunca exportada) porque solo
    # tiene sentido en este contexto.
    function Remove-ParkosDataItem {
        param([string]$Path, [string]$Label)
        if (-not (Test-Path -Path $Path)) { return }
        try {
            Remove-Item -Path $Path -Recurse -Force -ErrorAction Stop
            Write-Host "[OK] $Label borrado ($Path)." -ForegroundColor Green
        } catch {
            $msg = "$Label ($Path): $($_.Exception.Message)"
            Write-ParkosLog "No se pudo borrar $Label ($Path): $($_.Exception.Message)" -Level WARN
            Write-Host "[WARN] No se pudo borrar $Label ($Path)." -ForegroundColor Yellow
            $warnings.Add($msg)
        }
    }

    # --- Servicios NSSM (siempre) -------------------------------------------
    $nssmPath = Join-Path $paths.InstallPath 'nssm.exe'
    if (Test-Path $nssmPath) {
        foreach ($svcName in 'ParkosApiSucursal', 'ParkosJobSyncSucursal') {
            try {
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('stop', $svcName) | Out-Null
                Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('remove', $svcName, 'confirm') | Out-Null
                Write-Host "[OK] Servicio $svcName desregistrado." -ForegroundColor Green
            } catch {
                $msg = "Servicio ${svcName}: $($_.Exception.Message)"
                Write-ParkosLog "No se pudo desregistrar el servicio ${svcName}: $($_.Exception.Message)" -Level WARN
                Write-Host "[WARN] No se pudo desregistrar el servicio $svcName." -ForegroundColor Yellow
                $warnings.Add($msg)
            }
        }
    } else {
        $msg = "nssm.exe no encontrado en $nssmPath - no se pudieron desregistrar ParkosApiSucursal/ParkosJobSyncSucursal."
        Write-ParkosLog $msg -Level WARN
        Write-Host "[WARN] $msg" -ForegroundColor Yellow
        $warnings.Add($msg)
    }

    # --- Tarea pg_partman (siempre) -----------------------------------------
    try {
        Unregister-ScheduledTask -TaskName 'ParkosPgPartmanMaintenance' -Confirm:$false -ErrorAction Stop
        Write-Host '[OK] Tarea ParkosPgPartmanMaintenance desregistrada.' -ForegroundColor Green
    } catch {
        $msg = "Tarea ParkosPgPartmanMaintenance: $($_.Exception.Message)"
        Write-ParkosLog "No se pudo desregistrar la tarea ParkosPgPartmanMaintenance: $($_.Exception.Message)" -Level WARN
        Write-Host '[WARN] No se pudo desregistrar la tarea ParkosPgPartmanMaintenance.' -ForegroundColor Yellow
        $warnings.Add($msg)
    }

    # --- MSI web_sucursal (siempre) - mismo patron que Uninstall-ParkosElectron
    # en parkos-installer.ps1 (duplicado aca a proposito: el modulo no puede
    # importar funciones de ese script separado sin duplicar codigo, mismo
    # criterio ya usado con Invoke-ParkosNssm para el wrapper de NSSM).
    try {
        $installedMsi = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
            Where-Object { $_ -and $_.DisplayName -match 'Parkos' } | Select-Object -First 1
        if ($installedMsi) {
            $productCode = $installedMsi.PSChildName
            Start-Process msiexec.exe -ArgumentList "/x $productCode /qn" -Wait | Out-Null
            Write-Host '[OK] MSI de web_sucursal desinstalado.' -ForegroundColor Green
        }
    } catch {
        $msg = "MSI web_sucursal: $($_.Exception.Message)"
        Write-ParkosLog "No se pudo desinstalar el MSI de web_sucursal: $($_.Exception.Message)" -Level WARN
        Write-Host '[WARN] No se pudo desinstalar el MSI de web_sucursal.' -ForegroundColor Yellow
        $warnings.Add($msg)
    }

    if ($PurgeData) {
        Remove-ParkosDataItem -Path $paths.LogsPath -Label 'Logs'
        Remove-ParkosDataItem -Path (Join-Path $paths.DataPath 'pg-data') -Label 'Datos de Postgres (pg-data)'
        Remove-ParkosDataItem -Path $paths.BackupsPath -Label 'Backups'
        Remove-ParkosDataItem -Path $paths.SecretsPath -Label 'Secrets'
        Remove-ParkosDataItem -Path $paths.ReleasesPath -Label 'Releases'
        Remove-ParkosDataItem -Path (Join-Path $paths.DataPath 'installer-runs') -Label 'Installer-runs'

        # --- Tarea ParkosBackupDiario (PR8 puede no haberla creado todavia) -
        try {
            $backupTask = $null
            try {
                $backupTask = Get-ScheduledTask -TaskName 'ParkosBackupDiario' -ErrorAction SilentlyContinue
            } catch {
                # No existe todavia (PR8) - segun el modulo ScheduledTasks
                # instalado esto puede llegar como $null (arriba) o como una
                # excepcion ObjectNotFound; ambos casos son "no existe
                # todavia", nunca una falla real de este cmdlet.
                $backupTask = $null
            }
            if ($backupTask) {
                Unregister-ScheduledTask -TaskName 'ParkosBackupDiario' -Confirm:$false -ErrorAction Stop
                Write-Host '[OK] Tarea ParkosBackupDiario desregistrada.' -ForegroundColor Green
            }
        } catch {
            $msg = "Tarea ParkosBackupDiario: $($_.Exception.Message)"
            Write-ParkosLog "No se pudo desregistrar la tarea ParkosBackupDiario: $($_.Exception.Message)" -Level WARN
            Write-Host '[WARN] No se pudo desregistrar la tarea ParkosBackupDiario.' -ForegroundColor Yellow
            $warnings.Add($msg)
        }

        # --- Usuario local svc-parkos ---------------------------------------
        try {
            if (Get-LocalUser -Name 'svc-parkos' -ErrorAction SilentlyContinue) {
                Remove-LocalUser -Name 'svc-parkos' -ErrorAction Stop
                Write-Host '[OK] Usuario local svc-parkos borrado.' -ForegroundColor Green
            }
        } catch {
            $msg = "Usuario local svc-parkos: $($_.Exception.Message)"
            Write-ParkosLog "No se pudo borrar el usuario local svc-parkos: $($_.Exception.Message)" -Level WARN
            Write-Host '[WARN] No se pudo borrar el usuario local svc-parkos.' -ForegroundColor Yellow
            $warnings.Add($msg)
        }

        # --- Postgres (servicio + carpeta de instalacion) -------------------
        # Nombre del servicio resuelto DINAMICAMENTE por patron, nunca
        # hardcodeado - mismo patron que ya usa Test-CrashRecovery en este
        # mismo archivo.
        try {
            $pgService = Get-Service | Where-Object { $_ -and $_.Name -match 'postgresql' } | Select-Object -First 1
            if ($pgService) {
                Stop-Service -Name $pgService.Name -Force -ErrorAction Stop
                Write-Host "[OK] Servicio de Postgres ('$($pgService.Name)') detenido." -ForegroundColor Green
            }
        } catch {
            $msg = "Servicio de Postgres: $($_.Exception.Message)"
            Write-ParkosLog "No se pudo detener el servicio de Postgres: $($_.Exception.Message)" -Level WARN
            Write-Host '[WARN] No se pudo detener el servicio de Postgres.' -ForegroundColor Yellow
            $warnings.Add($msg)
        }
        Remove-ParkosDataItem -Path $script:PostgresInstallPath -Label 'Instalacion de Postgres'
    }

    # --- InstallPath (binarios) - siempre, despues de usar nssm.exe arriba --
    Remove-ParkosDataItem -Path $paths.InstallPath -Label 'Binarios (InstallPath)'

    $exitCode = if ($warnings.Count -gt 0) { 1 } else { 0 }

    if ($PurgeData) {
        $detailLines = @(
            'Parkos desinstalado.'
            ''
            'Se borraron todos los datos de esta instalacion (Postgres, secrets, backups, logs, releases, installer-runs).'
        )
    } else {
        $detailLines = @(
            'Parkos desinstalado.'
            ''
            'Preservado en este equipo:'
            "  - Datos Postgres en: $(Join-Path $paths.DataPath 'pg-data')\"
            "  - Backups en: $($paths.BackupsPath)\"
            "  - Logs en: $($paths.LogsPath)\"
            ''
            'Para reactivar: reinstalar y apuntar la opcion 1 (Postgres) a este mismo pg-data\.'
        )
    }

    if ($warnings.Count -gt 0) {
        $detailLines += ''
        $detailLines += 'No se pudo limpiar completamente:'
        foreach ($w in $warnings) { $detailLines += "  - $w" }
    }

    $detail = $detailLines -join "`n"
    $detailColor = if ($exitCode -eq 0) { 'Green' } else { 'Yellow' }
    Write-Host $detail -ForegroundColor $detailColor
    Write-ParkosLog "Uninstall-Parkos exit code: $exitCode ($($warnings.Count) advertencia(s))."
    $global:LASTEXITCODE = $exitCode
    $result = [PSCustomObject]@{ ExitCode = $exitCode; Detail = $detail }

    # El modulo se borra a si mismo, LITERALMENTE al final, despues de todo
    # lo demas (servicios, tareas, MSI, datos, InstallPath) - ver .NOTES mas
    # arriba para por que esto es seguro en PowerShell. $result ya quedo
    # armado antes de este paso: si el borrado propio fallara (poco comun),
    # no invalida el resto de la desinstalacion ya realizada.
    try {
        $moduleRoot = Split-Path -Parent $PSScriptRoot
        Remove-Item -Path $moduleRoot -Recurse -Force -ErrorAction Stop
    } catch {
        Write-ParkosLog "No se pudo borrar el directorio del modulo Parkos: $($_.Exception.Message)" -Level WARN
    }

    return $result
}

function Export-ParkosDiagnostics {
    <#
    .SYNOPSIS
        Exports a diagnostics bundle for support/escalation.

    .DESCRIPTION
        Genera un ZIP (carpeta parkos-diag-<timestamp>\ dentro del ZIP) con
        versions.txt, health.txt, doctor.json, services.txt,
        postgres-config.txt, pgsql-roles.txt, pgsql-databases.txt, logs\
        (api-sucursal.out/err.log, job-sync.out.log), nssm-dump-api.txt,
        nssm-dump-job.txt, env-redacted.txt y eventlog.csv - util para
        diagnosticar una instalacion de sucursal en forma remota, con TODOS
        los secretos redactados por Protect-ParkosDiagnosticText.

        Cualquier archivo fuente que no exista o no se pueda leer (.env
        corrupto/ausente, postgresql.conf ausente porque Postgres no esta
        instalado, doctor.exe/nssm.exe faltantes, fuente de Event Log
        inexistente) se OMITE del ZIP con una advertencia -
        Export-ParkosDiagnostics nunca aborta el export completo por un
        archivo individual faltante.

        La UNICA razon real de aborto es el gate de seguridad final,
        Test-ParkosDiagnosticsContainSecrets: si detecta que algun archivo
        ya "redactado" todavia contiene un valor que no tiene forma de
        placeholder "<redactado, N caracteres>", se hace throw explicito
        ANTES de llamar Compress-Archive, y la carpeta temporal se borra
        igual (try/finally) - nunca se genera un ZIP con un posible secreto
        adentro.

    .PARAMETER OutputPath
        Destino del ZIP generado. Default:
        <Escritorio>\parkos-diag-<yyyy-MM-ddTHH-mm-ss>.zip (con guiones en
        vez de ':' en la hora - un timestamp ISO con ':' rompe nombres de
        archivo en Windows).

    .EXAMPLE
        PS C:\> Export-ParkosDiagnostics

    .EXAMPLE
        PS C:\> Export-ParkosDiagnostics -OutputPath C:\Temp\diag.zip

    .NOTES
        No exige Test-IsAdmin - el plan original de esta fase dice
        explicitamente "NO requiere admin", y ningun paso de arriba (leer
        logs/config, correr psql/nssm dump/doctor.exe, leer el Event Log)
        necesita elevacion real POR SI SOLO. Matiz real encontrado y
        documentado en vez de ignorado: DataPath\secrets\ queda endurecido
        por Set-ParkosSecretsAcl a solo Administrators+SYSTEM (ver
        Test-ParkosSecretsAcl/Repair-ParkosInstall E4) - un usuario
        interactivo SIN esos permisos no va a poder leer .env, y por lo
        tanto doctor.json/pgsql-roles.txt/pgsql-databases.txt/
        env-redacted.txt se van a omitir con advertencia (degradacion
        elegante, nunca un throw) en vez de completarse. El diagnostico
        sigue siendo generable sin admin, solo que mas limitado; correrlo
        como Administrator produce el bundle completo.

        Exit codes: 0 (ZIP generado, con o sin advertencias de archivos
        omitidos), 1 (Compress-Archive fallo por una razon no relacionada
        con secretos - ej. disco lleno, permiso denegado en -OutputPath).
        El gate de secretos NO devuelve ExitCode 1: hace throw directo,
        mismo criterio que el gate de configuracion insegura de
        Test-CrashRecovery (throw = precondicion bloqueante, nunca se llego
        a intentar la accion real; ExitCode = la accion SI corrio).
    #>
    [CmdletBinding()]
    param(
        [string]$OutputPath
    )

    Write-ParkosLog 'Export-ParkosDiagnostics invoked.'

    if (-not $OutputPath) {
        $timestamp = Get-Date -Format 'yyyy-MM-ddTHH-mm-ss'
        $OutputPath = Join-Path ([Environment]::GetFolderPath('Desktop')) "parkos-diag-$timestamp.zip"
    }

    $paths = Resolve-ParkosPaths
    $tempRoot = Join-Path $env:TEMP "parkos-diag-tmp-$(Get-Random)"
    $bundleName = "parkos-diag-$(Get-Date -Format 'yyyy-MM-ddTHH-mm-ss')"
    $bundleDir = Join-Path $tempRoot $bundleName
    $logsDir = Join-Path $bundleDir 'logs'
    $envFilePath = Join-Path $paths.SecretsPath '.env'

    try {
        New-Item -ItemType Directory -Force -Path $logsDir -ErrorAction Stop | Out-Null

        $envMap = $null
        try { $envMap = Import-ParkosEnvFile -Path $envFilePath } catch { $envMap = $null }

        # --- 1. versions.txt (llama al placeholder de Get-ParkosVersion tal
        # cual - si sigue siendo placeholder, se documenta su propio texto
        # de "no implementado" en el archivo, no se reimplementa aca) -----
        try {
            $versionLines = @(Get-ParkosVersion 6>&1 | ForEach-Object { $_.ToString() })
            if (@($versionLines).Count -eq 0) { $versionLines = @('Get-ParkosVersion no devolvio salida.') }
            $versionText = ($versionLines | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }) -join "`n"
            Set-Content -Path (Join-Path $bundleDir 'versions.txt') -Value $versionText -Encoding UTF8
        } catch {
            Write-Host "[Parkos] versions.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
        }

        # --- 2. health.txt (formateado como texto plano desde el objeto
        # devuelto por Get-ParkosHealth -Detailed, no el objeto crudo) -----
        try {
            $health = Get-ParkosHealth -Detailed
            $healthLines = [System.Collections.Generic.List[string]]::new()
            $healthLines.Add('Parkos - Get-ParkosHealth -Detailed')
            $healthLines.Add("ExitCode: $($health.ExitCode)")
            $healthLines.Add('')
            foreach ($entry in $health.Checks.GetEnumerator()) {
                $healthLines.Add("[$($entry.Value.Status)] $($entry.Key)")
                $healthLines.Add("       $($entry.Value.Detail)")
            }
            $healthText = ($healthLines | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }) -join "`n"
            Set-Content -Path (Join-Path $bundleDir 'health.txt') -Value $healthText -Encoding UTF8
        } catch {
            Write-Host "[Parkos] health.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
        }

        # --- 3. doctor.json --------------------------------------------
        if ($envMap) {
            try {
                $doctorExe = Join-Path $paths.InstallPath 'doctor\doctor.exe'
                $doctorJson = Invoke-ParkosDoctorExe -DoctorExePath $doctorExe -EnvMap $envMap
                $doctorLines = (($doctorJson | ConvertTo-Json -Depth 10) -split "`r?`n") |
                    ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                Set-Content -Path (Join-Path $bundleDir 'doctor.json') -Value ($doctorLines -join "`n") -Encoding UTF8
            } catch {
                Write-Host "[Parkos] doctor.json omitido: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        } else {
            Write-Host '[Parkos] doctor.json omitido: no se pudo cargar el .env.' -ForegroundColor Yellow
        }

        # --- 4. services.txt ---------------------------------------------
        try {
            $servicesText = (Get-Service -Name 'Parkos*' -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-String)
            if ([string]::IsNullOrWhiteSpace($servicesText)) { $servicesText = 'No se encontraron servicios Parkos*.' }
            $serviceLines = ($servicesText -split "`r?`n") | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
            Set-Content -Path (Join-Path $bundleDir 'services.txt') -Value ($serviceLines -join "`n") -Encoding UTF8
        } catch {
            Write-Host "[Parkos] services.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
        }

        # --- 5. postgres-config.txt (misma redaccion que env-redacted.txt
        # por si alguna linea tiene una credencial inline) -----------------
        $confPath = Join-Path $paths.DataPath 'pg-data\postgresql.conf'
        if (Test-Path $confPath) {
            try {
                $confLines = Get-Content -Path $confPath -ErrorAction Stop | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                Set-Content -Path (Join-Path $bundleDir 'postgres-config.txt') -Value ($confLines -join "`n") -Encoding UTF8
            } catch {
                Write-Host "[Parkos] postgres-config.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[Parkos] postgres-config.txt omitido: no se encontro $confPath (Postgres no instalado o pg-data ausente)." -ForegroundColor Yellow
        }

        # --- 6/7. pgsql-roles.txt / pgsql-databases.txt -------------------
        if ($envMap) {
            $pgPort = $null
            try { $pgPort = Get-ParkosPostgresPort -EnvMap $envMap } catch { $pgPort = $null }

            if ($pgPort) {
                try {
                    $rolesText = (Invoke-ParkosPsql -PsqlExePath $script:PsqlExePath -Port $pgPort -Command '\du+' | Out-String)
                    $rolesLines = ($rolesText -split "`r?`n") | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                    Set-Content -Path (Join-Path $bundleDir 'pgsql-roles.txt') -Value ($rolesLines -join "`n") -Encoding UTF8
                } catch {
                    Write-Host "[Parkos] pgsql-roles.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
                }
                try {
                    $dbText = (Invoke-ParkosPsql -PsqlExePath $script:PsqlExePath -Port $pgPort -Command '\l' | Out-String)
                    $dbLines = ($dbText -split "`r?`n") | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                    Set-Content -Path (Join-Path $bundleDir 'pgsql-databases.txt') -Value ($dbLines -join "`n") -Encoding UTF8
                } catch {
                    Write-Host "[Parkos] pgsql-databases.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
                }
            } else {
                Write-Host '[Parkos] pgsql-roles.txt/pgsql-databases.txt omitidos: no se pudo determinar el puerto de Postgres desde el .env.' -ForegroundColor Yellow
            }
        } else {
            Write-Host '[Parkos] pgsql-roles.txt/pgsql-databases.txt omitidos: no se pudo cargar el .env.' -ForegroundColor Yellow
        }

        # --- 8. logs\ - nombres EXACTOS confirmados contra Install-ApiService/
        # Install-JobService en parkos-installer.ps1: job-sync-sucursal NUNCA
        # tuvo un AppStderr configurado (solo AppStdout), asi que job-sync.err.log
        # no existe por diseno del instalador, no por un olvido de este PR -
        # no se intenta copiar. --------------------------------------------
        $logFileNames = @('api-sucursal.out.log', 'api-sucursal.err.log', 'job-sync.out.log')
        foreach ($logFileName in $logFileNames) {
            $sourcePath = Join-Path $paths.LogsPath $logFileName
            if (Test-Path $sourcePath) {
                try {
                    $logLines = Get-Content -Path $sourcePath -ErrorAction Stop | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                    Set-Content -Path (Join-Path $logsDir $logFileName) -Value ($logLines -join "`n") -Encoding UTF8
                } catch {
                    Write-Host "[Parkos] Log omitido ($logFileName): $($_.Exception.Message)" -ForegroundColor Yellow
                }
            } else {
                Write-Host "[Parkos] Log omitido (no existe): $sourcePath" -ForegroundColor Yellow
            }
        }

        # --- 9/10. nssm-dump-api.txt / nssm-dump-job.txt ------------------
        $nssmPath = Join-Path $paths.InstallPath 'nssm.exe'
        if (Test-Path $nssmPath) {
            $nssmDumps = @(
                @{ File = 'nssm-dump-api.txt'; Service = 'ParkosApiSucursal' }
                @{ File = 'nssm-dump-job.txt'; Service = 'ParkosJobSyncSucursal' }
            )
            foreach ($dump in $nssmDumps) {
                try {
                    $dumpText = (Invoke-ParkosNssm -NssmPath $nssmPath -Arguments @('dump', $dump.Service) | Out-String)
                    $dumpLines = ($dumpText -split "`r?`n") | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
                    Set-Content -Path (Join-Path $bundleDir $dump.File) -Value ($dumpLines -join "`n") -Encoding UTF8
                } catch {
                    Write-Host "[Parkos] $($dump.File) omitido: $($_.Exception.Message)" -ForegroundColor Yellow
                }
            }
        } else {
            Write-Host "[Parkos] nssm-dump-*.txt omitidos: no se encontro nssm.exe en $nssmPath." -ForegroundColor Yellow
        }

        # --- 11. env-redacted.txt -----------------------------------------
        # Fase 27 (DEC-INST-40): el .env real puede estar cifrado con CMS
        # (-----BEGIN CMS-----), asi que NUNCA se lee $envFilePath crudo con
        # Get-Content aca - esto era un gap real dejado pendiente por PR9
        # (volcaba el blob CMS tal cual, sin decodificar ni redactar nada
        # util). $envMap ya viene descifrado/parseado por Import-ParkosEnvFile
        # (linea de arriba) - reconstruimos KEY=VALUE desde ahi y recien
        # aplicamos la redaccion, igual que a cualquier otro archivo generado.
        if ($envMap) {
            try {
                $envLines = $envMap.GetEnumerator() | ForEach-Object { Protect-ParkosDiagnosticText -Line "$($_.Key)=$($_.Value)" }
                Set-Content -Path (Join-Path $bundleDir 'env-redacted.txt') -Value ($envLines -join "`n") -Encoding UTF8
            } catch {
                Write-Host "[Parkos] env-redacted.txt omitido: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[Parkos] env-redacted.txt omitido: no se pudo cargar/descifrar $envFilePath." -ForegroundColor Yellow
        }

        # --- 12. eventlog.csv - fuente inexistente (maquina que nunca corrio
        # Invoke-ParkosUpdate) genera solo el header, nunca falla. ----------
        $csvHeader = '"Index","TimeGenerated","EntryType","Source","InstanceId","Message"'
        try {
            if (Test-ParkosEventLogSourceExists -Source 'ParkosInstaller') {
                $cutoff = (Get-Date).AddDays(-30)
                $events = @(Get-EventLog -LogName Application -Source 'ParkosInstaller' -After $cutoff -ErrorAction SilentlyContinue)
                if ($events.Count -gt 0) {
                    $csvText = ($events |
                        Select-Object Index, TimeGenerated, EntryType, Source, InstanceId, Message |
                        ConvertTo-Csv -NoTypeInformation) -join "`n"
                } else {
                    $csvText = $csvHeader
                }
            } else {
                $csvText = $csvHeader
            }
            $csvLines = ($csvText -split "`r?`n") | ForEach-Object { Protect-ParkosDiagnosticText -Line $_ }
            Set-Content -Path (Join-Path $bundleDir 'eventlog.csv') -Value ($csvLines -join "`n") -Encoding UTF8
        } catch {
            Write-Host "[Parkos] eventlog.csv: fallo la lectura del Event Log ($($_.Exception.Message)) - se genera igual solo con el header." -ForegroundColor Yellow
            Set-Content -Path (Join-Path $bundleDir 'eventlog.csv') -Value $csvHeader -Encoding UTF8
        }

        # -------------------------------------------------------------------
        # Gate de seguridad OBLIGATORIO: verificar la redaccion ANTES de
        # empaquetar. Si encuentra algo, aborta el empaquetado COMPLETO -
        # nunca genera el ZIP (throw real, no cosmetico - ver .NOTES).
        # -------------------------------------------------------------------
        $secretsCheck = Test-ParkosDiagnosticsContainSecrets -Path $bundleDir
        if ($secretsCheck.HasSecrets) {
            $findingsJoined = ($secretsCheck.Findings -join '; ')
            $abortMessage = "Export-ParkosDiagnostics aborto antes de empaquetar: se detecto redaccion incompleta en: $findingsJoined. No se genero ningun ZIP."
            Write-Host "[FAIL] $abortMessage" -ForegroundColor Red
            Write-ParkosLog "Export-ParkosDiagnostics abortado por el gate de secretos: $findingsJoined" -Level ERROR
            throw $abortMessage
        }

        # --- Empaquetado ---------------------------------------------------
        try {
            $outputDir = Split-Path -Path $OutputPath -Parent
            if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir -ErrorAction SilentlyContinue | Out-Null }
            Compress-Archive -Path $bundleDir -DestinationPath $OutputPath -Force
        } catch {
            $detail = "No se pudo generar el ZIP en ${OutputPath}: $($_.Exception.Message)"
            Write-Host "[FAIL] $detail" -ForegroundColor Red
            Write-ParkosLog "Export-ParkosDiagnostics exit code: 1 ($detail)"
            $global:LASTEXITCODE = 1
            return [PSCustomObject]@{ ExitCode = 1; OutputPath = $null; Detail = $detail }
        }

        $detail = "Diagnostico exportado a $OutputPath."
        Write-Host "[OK] $detail" -ForegroundColor Green
        Write-ParkosLog "Export-ParkosDiagnostics exit code: 0 ($detail)"
        $global:LASTEXITCODE = 0
        return [PSCustomObject]@{ ExitCode = 0; OutputPath = $OutputPath; Detail = $detail }
    } finally {
        # Siempre - exito o fallo (incluido el throw del gate de secretos).
        if (Test-Path $tempRoot) {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Register-ParkosBackupTask {
    <#
    .SYNOPSIS
        Registers the daily Postgres backup scheduled task.

    .DESCRIPTION
        Real implementation (PR8). Valida que Postgres este corriendo y que
        parkos_app tenga acceso real (SELECT 1), estima el tamano del dump
        con pg_database_size('parkos') y exige mas del doble de ese tamano
        libre en el disco de DataPath, confirma que el usuario de servicio
        svc-parkos ya existe (creado por Ensure-ServiceAccount en
        parkos-installer.ps1 - ver .NOTES, este cmdlet nunca lo crea),
        genera $DataPath\scripts\Invoke-DailyBackup.ps1 (script standalone,
        autocontenido, sin depender de que el modulo Parkos este importado)
        con una ACL restringida (Administrators+SYSTEM+svc-parkos), registra
        la tarea programada diaria ParkosBackupDiario (mismo patron que
        Register-PgPartmanMaintenance en parkos-installer.ps1:
        New-ScheduledTaskAction/New-ScheduledTaskTrigger -Daily -At/
        New-ScheduledTaskPrincipal -UserId 'svc-parkos' -LogonType
        ServiceAccount/Register-ScheduledTask) y corre un backup de PRUEBA
        inmediato (invocando el script recien escrito, no el scheduler) para
        no dejar la tarea registrada apuntando a un script sin validar.

        El script generado aplica la retencion "abuelo-padre-hijo" (7+4+1)
        - misma logica que Get-ParkosBackupRetentionPlan (helper privado
        PURO de este modulo, testeable por separado) - ANTES de generar el
        dump nuevo de cada corrida.

        RunOnlyIfNetworkAvailable queda explicitamente en $false (via
        New-ScheduledTaskSettingsSet) - el backup diario tiene que poder
        correr offline, requisito central de este producto.

    .PARAMETER DailyAt
        Hora del dia (formato HH:mm) en la que corre la tarea diaria.
        Default: '03:00' - distinto de las 2am que ya usa
        ParkosPgPartmanMaintenance, para no competir por I/O de disco con
        el mantenimiento de particiones.

    .EXAMPLE
        PS C:\> Register-ParkosBackupTask

    .EXAMPLE
        PS C:\> Register-ParkosBackupTask -DailyAt '02:30'

    .NOTES
        Requiere administrador.

        NO crea el usuario svc-parkos: esa cuenta (con su derecho
        SeBatchLogonRight ya otorgado via secedit) la crea
        Ensure-ServiceAccount en parkos-installer.ps1 durante la
        instalacion - duplicar ese manejo (~25 lineas de secedit/SID) en
        este modulo no se justifica. Si svc-parkos no existe todavia, es un
        prerequisito no cumplido (correr el instalador primero), no algo
        que este cmdlet deba resolver creando la cuenta el mismo.

        Decision de diseno (evita otro round-trip de payload/manifest/
        Install-ManagementModule para un script de ~40 lineas):
        Invoke-DailyBackup.ps1 NO viaja en installer/payload/scripts/ - este
        cmdlet GENERA su contenido (here-string embebido aca abajo, con
        placeholders __TOKEN__ reemplazados por Replace()) y lo escribe a
        $DataPath\scripts\ recien al momento de registrar la tarea, quedando
        autocontenido en el modulo (mismo criterio ya usado para duplicar
        pequenos fragmentos de logica NSSM entre el instalador y este
        modulo, en vez de compartir codigo entre un .ps1 y un .psm1).

        Exit codes: cualquier precondicion no cumplida (Postgres/parkos_app
        sin acceso, espacio insuficiente, svc-parkos ausente, backup de
        prueba fallido) hace throw explicito - nunca continua en silencio.
        Si el backup de prueba falla DESPUES de registrar la tarea, esta se
        desregistra (best-effort) antes del throw, para no dejar
        ParkosBackupDiario apuntando a un script sin validar. ExitCode 0 es
        el unico valor que este cmdlet retorna al completar con exito - no
        existe hoy un escenario de "exito degradado" para esta tarea.
    #>
    [CmdletBinding()]
    param(
        [string]$DailyAt = '03:00'
    )

    Write-ParkosLog 'Register-ParkosBackupTask invoked.'

    if (-not (Test-IsAdmin)) {
        throw 'Register-ParkosBackupTask requiere permisos de administrador.'
    }

    try {
        $dailyAtTime = [datetime]::ParseExact($DailyAt, 'HH:mm', [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        throw "Formato de hora invalido en -DailyAt: '$DailyAt' (use HH:mm, ejemplo: 03:00)."
    }

    $paths = Resolve-ParkosPaths
    $envFilePath = Join-Path $paths.SecretsPath '.env'

    # -------------------------------------------------------------------
    # 1. Postgres corriendo + parkos_app con acceso real (SELECT 1) -
    # reusa Get-ParkosPostgresPort + el wrapper mockeable Invoke-ParkosPsql
    # (agregado en PR7, DEC-INST-38). Nota de criterio: la firma real de
    # Invoke-ParkosPsql (PsqlExePath/Port/Command, siempre -U parkos_app
    # -d parkos -c) difiere de lo asumido en el plan original (un
    # -Arguments generico) - se reusa la firma REAL en vez de duplicar un
    # wrapper competidor. La decision se basa unicamente en el contenido
    # devuelto (nunca en $LASTEXITCODE), para que sea deterministamente
    # testeable bajo Mock sin depender del ultimo exit code que haya
    # quedado de otra llamada nativa previa en la sesion.
    # -------------------------------------------------------------------
    $port = $null
    $selectOneOk = $false
    try {
        $envMap = Import-ParkosEnvFile -Path $envFilePath
        $port = Get-ParkosPostgresPort -EnvMap $envMap
        $checkOutput = @(Invoke-ParkosPsql -PsqlExePath $script:PsqlExePath -Port $port -Command 'SELECT 1;')
        $selectOneOk = [bool]($checkOutput | Where-Object { $_ -match '^\s*1\s*$' })
    } catch {
        $selectOneOk = $false
    }
    if (-not $selectOneOk) {
        throw 'Register-ParkosBackupTask requiere que Postgres este corriendo y que parkos_app tenga acceso (SELECT 1 fallo) - verificalo con Get-ParkosHealth antes de reintentar.'
    }

    # -------------------------------------------------------------------
    # 2. Espacio en disco: mas del doble del tamano estimado del dump
    # (pg_database_size('parkos'), via el mismo wrapper).
    # -------------------------------------------------------------------
    $sizeOutput = @(Invoke-ParkosPsql -PsqlExePath $script:PsqlExePath -Port $port -Command "SELECT pg_database_size('parkos');")
    $sizeLine = $sizeOutput | Where-Object { $_ -match '^\s*\d+\s*$' } | Select-Object -First 1
    if (-not $sizeLine) {
        throw 'No se pudo estimar el tamano de la base de datos parkos (pg_database_size no devolvio un valor numerico).'
    }
    $estimatedBytes = [int64]($sizeLine.Trim())
    $requiredBytes = $estimatedBytes * 2

    $driveLetter = $paths.DataPath.Substring(0, 1)
    $drive = Get-PSDrive -Name $driveLetter -ErrorAction Stop
    if ($drive.Free -le $requiredBytes) {
        $requiredMb = [Math]::Round($requiredBytes / 1MB, 1)
        $freeMb = [Math]::Round($drive.Free / 1MB, 1)
        throw ('Espacio insuficiente para backup: se necesitan al menos {0} MB, hay {1} MB libres en {2}:.' -f $requiredMb, $freeMb, $driveLetter)
    }

    # -------------------------------------------------------------------
    # 3. svc-parkos ya debe existir - lo crea Ensure-ServiceAccount en el
    # instalador (ver .NOTES); este cmdlet nunca lo crea el mismo.
    # -------------------------------------------------------------------
    if (-not (Get-LocalUser -Name 'svc-parkos' -ErrorAction SilentlyContinue)) {
        throw "El usuario de servicio 'svc-parkos' no existe todavia - corre el instalador (parkos-installer.ps1, Ensure-ServiceAccount) antes de registrar la tarea de backup."
    }

    # -------------------------------------------------------------------
    # 4. Generar Invoke-DailyBackup.ps1 (standalone, autocontenido) + ACL
    # restringida. Here-string SIN interpolar (comillas simples @'...'@) -
    # los __TOKEN__ se reemplazan con Replace() despues; cualquier '$' que
    # aparezca aca abajo es literal, para la ejecucion FUTURA del script
    # generado, no para esta funcion.
    # -------------------------------------------------------------------
    $template = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$dataPath     = '__DATAPATH__'
$secretsPath  = '__SECRETSPATH__'
$backupsDir   = '__BACKUPSPATH__\daily'
$logsPath     = '__LOGSPATH__'
$logFile      = Join-Path $logsPath 'backup.log'
$envFilePath  = Join-Path $secretsPath '.env'
$pgDumpExe    = '__PGDUMPEXE__'
$pgRestoreExe = '__PGRESTOREEXE__'

function Write-BackupLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $logsPath -ErrorAction SilentlyContinue | Out-Null
    $timestamp = (Get-Date).ToString('o')
    Add-Content -Path $logFile -Value "[$timestamp] $Message" -ErrorAction SilentlyContinue
}

try {
    New-Item -ItemType Directory -Force -Path $backupsDir -ErrorAction Stop | Out-Null

    # Puerto de Postgres parseado inline desde el .env - este script corre
    # bajo svc-parkos via tarea programada, standalone, sin el modulo
    # Parkos importado (duplicado a proposito, mismo criterio ya usado
    # entre parkos-installer.ps1 y Parkos.psm1 en el resto del instalador).
    if (-not (Test-Path $envFilePath)) {
        throw "No se encontro el .env en $envFilePath."
    }
    # Fase 27 (HU-F27.2/DEC-INST-40): el .env ahora puede venir cifrado con
    # CMS (Protect-CmsMessage, encabezado ASCII-armored '-----BEGIN CMS-----')
    # o en texto plano (instalaciones anteriores a este cambio) - deteccion
    # por CONTENIDO, nunca por convencion, duplicada aca a proposito (mismo
    # criterio ya documentado en este archivo: este script standalone corre
    # bajo svc-parkos, sin el modulo Parkos importado, asi que no puede
    # reusar script:Import-ParkosEnvFile). NOTA (limitacion conocida, no
    # resuelta en este PR): Unprotect-CmsMessage necesita acceso de LECTURA a
    # la clave PRIVADA del certificado 'CN=ParkosEnvProtection' en
    # Cert:\LocalMachine\My - hoy esa clave privada queda con los permisos
    # default que New-SelfSignedCertificate le asigna (tipicamente solo la
    # cuenta que la creo, un proceso elevado de Administrator durante la
    # instalacion), sin una concesion explicita para svc-parkos. Si este
    # backup diario empieza a fallar con un error de Unprotect-CmsMessage por
    # permisos, ese es el ACL a revisar/otorgar (fuera de alcance de este PR
    # - no se pidio tocar permisos de almacen de certificados, solo el
    # cifrado en si).
    $envFirstLine = Get-Content -Path $envFilePath -TotalCount 1
    if ($envFirstLine -match '^-----BEGIN CMS-----') {
        $envRawContent = Unprotect-CmsMessage -Path $envFilePath
        $envLinesForPort = @($envRawContent -split "`r`n|`n") | Where-Object { $_ -match '=' }
    } else {
        $envLinesForPort = @(Get-Content -Path $envFilePath | Where-Object { $_ -match '=' })
    }

    $port = $null
    foreach ($line in $envLinesForPort) {
        $parts = $line -split '=', 2
        if (($parts[0] -eq 'PARKOS_DB_URL' -or $parts[0] -eq 'DATABASE_URL') -and $parts[1] -match '@[^:/]+:(\d+)/') {
            $port = [int]$Matches[1]
            break
        }
    }
    if (-not $port) {
        throw 'No se pudo determinar el puerto de Postgres desde el .env.'
    }

    # Retencion abuelo-padre-hijo (7+4+1) ANTES de generar el dump nuevo -
    # duplicado inline desde Get-ParkosBackupRetentionPlan (Parkos.psm1);
    # este script no puede llamar una funcion script:-scoped de un modulo
    # que no importa.
    $existingDumps = @(Get-ChildItem -Path $backupsDir -Filter 'backup-*.dump' -File -ErrorAction SilentlyContinue)
    if ($existingDumps.Count -gt 0) {
        $dumpsByDate = @{}
        foreach ($f in $existingDumps) {
            if ($f.BaseName -match 'backup-(\d{8}-\d{6})') {
                $parsedDate = [datetime]::ParseExact($Matches[1], 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture)
                $dumpsByDate[$parsedDate] = $f.FullName
            }
        }
        $sortedDates = @($dumpsByDate.Keys | Sort-Object -Descending)
        $keepDates = [System.Collections.Generic.List[datetime]]::new()
        $dailyCount = [Math]::Min(7, $sortedDates.Count)
        for ($i = 0; $i -lt $dailyCount; $i++) { $keepDates.Add($sortedDates[$i]) }
        $remaining = if ($sortedDates.Count -gt 7) { @($sortedDates[7..($sortedDates.Count - 1)]) } else { @() }
        $seenWeeks = [System.Collections.Generic.HashSet[string]]::new()
        $weeklyCount = 0
        $afterWeekly = [System.Collections.Generic.List[datetime]]::new()
        foreach ($d in $remaining) {
            $weekKey = "$([System.Globalization.ISOWeek]::GetYear($d))-W$([System.Globalization.ISOWeek]::GetWeekOfYear($d))"
            if ($weeklyCount -lt 4 -and -not $seenWeeks.Contains($weekKey)) {
                $seenWeeks.Add($weekKey) | Out-Null
                $weeklyCount++
                $keepDates.Add($d)
            } else {
                $afterWeekly.Add($d)
            }
        }
        if ($afterWeekly.Count -gt 0) { $keepDates.Add($afterWeekly[0]) }
        foreach ($d in $dumpsByDate.Keys) {
            if (-not ($keepDates -contains $d)) {
                Remove-Item -Path $dumpsByDate[$d] -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # Generar el dump nuevo.
    $timestamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $dumpPath = Join-Path $backupsDir "backup-$timestamp.dump"
    & $pgDumpExe -Fc -U parkos_app -h 127.0.0.1 -p $port -d parkos -f $dumpPath
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump.exe fallo (exit $LASTEXITCODE) generando $dumpPath."
    }

    # Verificar el dump - mismo gate que Invoke-ParkosUpdate en
    # parkos-installer.ps1 (Test-ParkosDumpHasObjects): pg_restore --list
    # debe listar al menos 1 objeto real.
    $listing = & $pgRestoreExe --list $dumpPath 2>$null
    $objectLines = @($listing | Where-Object { $_ -and ($_ -notmatch '^;') })
    if ($LASTEXITCODE -ne 0 -or $objectLines.Count -lt 1) {
        throw "El backup generado en $dumpPath no paso la verificacion de pg_restore --list (vacio o corrupto)."
    }

    Write-BackupLog "OK - backup generado y verificado en $dumpPath."
    exit 0
} catch {
    Write-BackupLog "FAIL - $($_.Exception.Message)"
    exit 1
}
'@

    $scriptsDir = Join-Path $paths.DataPath 'scripts'
    New-Item -ItemType Directory -Force -Path $scriptsDir -ErrorAction Stop | Out-Null
    $scriptPath = Join-Path $scriptsDir 'Invoke-DailyBackup.ps1'

    $pgDumpExe = Join-Path $script:PostgresInstallPath 'bin\pg_dump.exe'
    $pgRestoreExe = Join-Path $script:PostgresInstallPath 'bin\pg_restore.exe'

    $scriptContent = $template.
        Replace('__DATAPATH__', $paths.DataPath).
        Replace('__SECRETSPATH__', $paths.SecretsPath).
        Replace('__BACKUPSPATH__', $paths.BackupsPath).
        Replace('__LOGSPATH__', $paths.LogsPath).
        Replace('__PGDUMPEXE__', $pgDumpExe).
        Replace('__PGRESTOREEXE__', $pgRestoreExe)

    Set-Content -Path $scriptPath -Value $scriptContent -Encoding UTF8

    # Restringida a Administrators+SYSTEM+svc-parkos - similar a
    # Set-ParkosSecretsAcl pero sin reusarla: ese helper NO incluye
    # svc-parkos, que si necesita poder leer/ejecutar este script en
    # particular (corre bajo esa identidad via la tarea programada).
    icacls $scriptPath /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' 'svc-parkos:RX' | Out-Null

    # -------------------------------------------------------------------
    # 5. Registrar la tarea programada diaria - mismo patron EXACTO que
    # Register-PgPartmanMaintenance en parkos-installer.ps1.
    # -------------------------------------------------------------------
    $action = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument "-NoProfile -File `"$scriptPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At $dailyAtTime
    $principal = New-ScheduledTaskPrincipal -UserId 'svc-parkos' -LogonType ServiceAccount
    $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable:$false
    Register-ScheduledTask -TaskName 'ParkosBackupDiario' -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description 'Backup diario de Postgres (Parkos) con retencion abuelo-padre-hijo (7+4+1).' `
        -Force | Out-Null

    # -------------------------------------------------------------------
    # 6. Backup de PRUEBA inmediato (proceso separado, mismo patron
    # 'pwsh.exe -NoProfile -File' que la propia Action de la tarea) - nunca
    # dejar ParkosBackupDiario registrada apuntando a un script sin
    # validar.
    # -------------------------------------------------------------------
    $testRun = Start-Process -FilePath 'pwsh.exe' -ArgumentList @('-NoProfile', '-File', $scriptPath) -Wait -PassThru -NoNewWindow
    if ($testRun.ExitCode -ne 0) {
        try {
            Unregister-ScheduledTask -TaskName 'ParkosBackupDiario' -Confirm:$false -ErrorAction Stop
        } catch {
            # Best-effort: el throw de abajo ya reporta la falla real: esto
            # solo evita dejar basura registrada cuando se puede.
        }
        throw "El backup de prueba fallo (pwsh.exe exit $($testRun.ExitCode)) al ejecutar $scriptPath - la tarea ParkosBackupDiario NO quedo registrada. Revisar $(Join-Path $paths.LogsPath 'backup.log')."
    }

    # -------------------------------------------------------------------
    # 7. Proximos 3 horarios programados - Get-ScheduledTaskInfo solo da el
    # siguiente, nunca una lista, asi que se calcula aca.
    # -------------------------------------------------------------------
    $now = Get-Date
    $todayAt = Get-Date -Hour $dailyAtTime.Hour -Minute $dailyAtTime.Minute -Second 0 -Millisecond 0
    $firstRun = if ($todayAt -gt $now) { $todayAt } else { $todayAt.AddDays(1) }
    $nextRuns = 0..2 | ForEach-Object { $firstRun.AddDays($_) }

    Write-Host '[OK] Tarea ParkosBackupDiario registrada y backup de prueba exitoso.' -ForegroundColor Green
    Write-Host 'Proximos horarios programados:' -ForegroundColor Cyan
    foreach ($run in $nextRuns) {
        Write-Host "  - $($run.ToString('yyyy-MM-dd HH:mm'))" -ForegroundColor Cyan
    }

    $nextRunsJoined = ($nextRuns | ForEach-Object { $_.ToString('yyyy-MM-dd HH:mm') }) -join ', '
    $detail = "Tarea ParkosBackupDiario registrada (diaria a las $DailyAt). Backup de prueba exitoso. Proximos horarios: $nextRunsJoined."
    Write-ParkosLog "Register-ParkosBackupTask exit code: 0 ($detail)"
    $global:LASTEXITCODE = 0
    return [PSCustomObject]@{ ExitCode = 0; Detail = $detail }
}

function Test-CrashRecovery {
    <#
    .SYNOPSIS
        Simulates an abrupt Postgres outage and verifies WAL-based recovery.

    .DESCRIPTION
        Future signature: Test-CrashRecovery [-TimeoutSeconds 30]

        Forces an abrupt stop of the Postgres service and verifies the
        instance recovers cleanly via WAL replay within the given timeout.

    .PARAMETER TimeoutSeconds
        Maximum time to wait for a clean recovery before considering the
        test failed. Defaults to 30.

    .EXAMPLE
        PS C:\> Test-CrashRecovery -TimeoutSeconds 60

    .NOTES
        Decision de diseno: una configuracion insegura de Postgres (fsync u
        full_page_writes efectivamente apagados) hace throw INMEDIATO, no
        return con ExitCode=2 - es un aborto bloqueante antes de tocar nada
        (nunca se llega a matar el proceso de Postgres), a proposito
        distinto del ExitCode=1 que usa el resto de la funcion para "la
        recuperacion no trajo la fila esperada". Se documenta aca para que
        quede sin ambiguedad: throw = configuracion insegura (no se corrio
        la prueba), ExitCode 0/1 = la prueba SI se corrio.

        El timing de "matar Postgres a mitad de una transaccion abierta" es
        best-effort: no hay forma de cortar con precision perfecta desde
        afuera del proceso psql, hay una carrera inherente entre el
        Start-Sleep de 1 segundo y el pg_sleep(2) de la transaccion en el
        job de fondo. Ver el comentario junto al Start-Job mas abajo.
    #>
    [CmdletBinding()]
    param(
        [int]$TimeoutSeconds = 30
    )

    Write-ParkosLog 'Test-CrashRecovery invoked.'

    if (-not (Test-IsAdmin)) {
        throw 'Test-CrashRecovery requiere permisos de administrador.'
    }

    $paths = Resolve-ParkosPaths

    # 1. Gate de configuracion segura - bloqueante, se ejecuta ANTES de tocar
    # cualquier proceso o servicio. "Efectivamente activo" quiere decir una
    # linea SIN comentar (sin '#' antes) con valor 'on' - una linea comentada
    # o ausente no cuenta como garantia visible de que el default este en
    # vigor, asi que tambien se considera insegura para esta verificacion.
    $confPath = Join-Path $paths.DataPath 'pg-data\postgresql.conf'
    if (-not (Test-Path $confPath)) {
        throw "No se encontro postgresql.conf en $confPath - no se puede verificar la configuracion de seguridad antes de la prueba de crash."
    }
    $confLines = Get-Content -Path $confPath

    $fsyncOn = [bool]($confLines | Where-Object { $_ -match '^\s*fsync\s*=\s*on\b' })
    $fullPageWritesOn = [bool]($confLines | Where-Object { $_ -match '^\s*full_page_writes\s*=\s*on\b' })

    if (-not $fsyncOn -or -not $fullPageWritesOn) {
        $detalle = @()
        if (-not $fsyncOn) { $detalle += 'fsync no esta efectivamente en on (ausente, comentado o en off)' }
        if (-not $fullPageWritesOn) { $detalle += 'full_page_writes no esta efectivamente en on (ausente, comentado o en off)' }
        throw "Configuracion insegura, abortando: $($detalle -join '; ')"
    }
    Write-Host '[OK] fsync y full_page_writes estan efectivamente en on.' -ForegroundColor Green

    # Puerto de Postgres, desde el .env de la instalacion (mismo parser
    # compartido que usa Get-ParkosHealth).
    $envFilePath = Join-Path $paths.SecretsPath '.env'
    $envMap = Import-ParkosEnvFile -Path $envFilePath
    $port = Get-ParkosPostgresPort -EnvMap $envMap

    # 2. Transaccion de prueba abierta con pg_sleep, en un Start-Job de fondo
    # para poder matar Postgres mientras sigue "abierta". PGPASSFILE ya esta
    # seteado a nivel de maquina por el instalador (Set-PgPassFile) - no se
    # resetea aca.
    $timestampIso = (Get-Date).ToString('o')
    $expectedPayload = "recovery-test-$timestampIso"
    $sql = "CREATE TABLE IF NOT EXISTS test_crash_recovery (id int PRIMARY KEY, payload text); BEGIN; INSERT INTO test_crash_recovery (id, payload) VALUES (1, '$expectedPayload') ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload; SELECT pg_sleep(2); COMMIT;"

    Write-Host '[..] Iniciando transaccion de prueba en segundo plano...' -ForegroundColor Yellow
    $job = Start-Job -ScriptBlock {
        param($PsqlExePath, $Port, $Sql)
        & $PsqlExePath -w -h 127.0.0.1 -p $Port -U parkos_app -d parkos -c $Sql
    } -ArgumentList $script:PsqlExePath, $port, $sql

    # NOTA HONESTA sobre el timing: no existe una forma perfectamente timeada
    # de "cortar a mitad de una transaccion abierta" desde afuera del propio
    # proceso psql - esto es la aproximacion mas simple que sigue siendo una
    # prueba real, no una garantia exacta. Se espera ~1 segundo (la mitad del
    # pg_sleep(2) de la transaccion) para maximizar la chance de que la
    # transaccion siga abierta en ese instante, pero hay una carrera
    # inherente: en una maquina muy lenta o muy rapida, el corte podria caer
    # antes de que el INSERT se aplique localmente o despues de que el COMMIT
    # ya haya corrido. Se documenta en vez de afirmar que "funciona perfecto".
    Start-Sleep -Seconds 1

    # 3. Resolver el nombre real del servicio de Postgres DINAMICAMENTE - no
    # esta hardcodeado en ningun lado de parkos-installer.ps1 (Install-Postgres
    # /Install-PostgresViaWinget/Install-PostgresViaZip nunca registran ni
    # nombran el servicio de Windows explicitamente), asi que se resuelve en
    # runtime por patron, nunca adivinado.
    $pgService = Get-Service | Where-Object { $_.Name -match 'postgresql' } | Select-Object -First 1
    if (-not $pgService) {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        throw "No se encontro el servicio de Windows de Postgres (patron '*postgresql*') - no se puede continuar con la prueba de crash recovery."
    }
    $pgServiceName = $pgService.Name

    $pgProcessId = (Get-CimInstance Win32_Service -Filter "Name='$pgServiceName'").ProcessId
    if (-not $pgProcessId) {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        throw "No se pudo resolver el PID del servicio '$pgServiceName'."
    }
    Stop-Process -Id $pgProcessId -Force
    Write-Host "[OK] Proceso de Postgres (PID $pgProcessId, servicio '$pgServiceName') detenido a la fuerza." -ForegroundColor Green
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue

    # 4. Reiniciar el servicio.
    Write-Host "[..] Reiniciando el servicio '$pgServiceName'..." -ForegroundColor Yellow
    Start-Service -Name $pgServiceName

    # 5. Esperar a que vuelva a aceptar conexiones y verificar la fila.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $reachable = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName '127.0.0.1' -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) {
            $reachable = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $reachable) {
        $exitCode = 1
        $detail = "Postgres (servicio '$pgServiceName') no volvio a aceptar conexiones dentro de $TimeoutSeconds segundos."
        Write-Host "[FAIL] $detail" -ForegroundColor Red
        Write-ParkosLog "Test-CrashRecovery exit code: $exitCode ($detail)"
        $global:LASTEXITCODE = $exitCode
        return [PSCustomObject]@{ ExitCode = $exitCode; Detail = $detail }
    }
    Write-Host "[OK] Postgres volvio a aceptar conexiones en el puerto $port." -ForegroundColor Green

    $recovered = (& $script:PsqlExePath -w -h 127.0.0.1 -p $port -U parkos_app -d parkos -tAc 'SELECT payload FROM test_crash_recovery WHERE id = 1;').Trim()
    $rowOk = ($recovered -eq $expectedPayload)

    # 6. Cleanup - solo la fila, la tabla se reutiliza en corridas futuras
    # (el CREATE TABLE IF NOT EXISTS del paso 1 ya es idempotente).
    & $script:PsqlExePath -w -h 127.0.0.1 -p $port -U parkos_app -d parkos -c 'DELETE FROM test_crash_recovery WHERE id = 1;' | Out-Null

    if ($rowOk) {
        $exitCode = 0
        $detail = 'Recuperacion exitosa: la fila de prueba sobrevivio al crash abrupto de Postgres.'
        Write-Host "[OK] $detail" -ForegroundColor Green
    } else {
        $exitCode = 1
        $detail = "Postgres no recupero la fila esperada tras el crash (obtenido: '$recovered')."
        Write-Host "[FAIL] $detail" -ForegroundColor Red
    }

    Write-ParkosLog "Test-CrashRecovery exit code: $exitCode ($detail)"
    $global:LASTEXITCODE = $exitCode
    return [PSCustomObject]@{ ExitCode = $exitCode; Detail = $detail }
}

function Get-ParkosVersion {
    <#
    .SYNOPSIS
        Reports the installed Parkos version.

    .DESCRIPTION
        Future signature: Get-ParkosVersion

        Returns the installed binaries' version together with this
        management module's own version ($script:ModuleVersion).

    .EXAMPLE
        PS C:\> Get-ParkosVersion

    .NOTES
        Placeholder (PR1). Real implementation lands in PR8.
    #>
    [CmdletBinding()]
    param()

    Write-ParkosLog 'Get-ParkosVersion invoked (placeholder PR1).'
    Write-Host '[Parkos] Get-ParkosVersion aun no esta implementado (placeholder PR1).' -ForegroundColor Yellow
    return
}

function Test-ParkosSecretsAcl {
    <#
    .SYNOPSIS
        Verifies the ACL on the secrets directory.

    .DESCRIPTION
        Verifies the ACL on DataPath\secrets grants access only to
        BUILTIN\Administrators, NT AUTHORITY\SYSTEM, or another NT
        AUTHORITY\* system principal (the owner Windows itself assigns).
        Any other principal with access - the current interactive user,
        a domain account, Everyone, BUILTIN\Users, etc - is a finding.

    .EXAMPLE
        PS C:\> Test-ParkosSecretsAcl

    .NOTES
        Implemented ahead of its original PR9 slot: Repair-ParkosInstall
        (PR3, E4) depends on this cmdlet to detect an altered secrets\ ACL.
        Deliberately minimal (as scoped) - it only reports; the fix itself
        is script:Set-ParkosSecretsAcl, applied by Repair-ParkosInstall.
    #>
    [CmdletBinding()]
    param()

    Write-ParkosLog 'Test-ParkosSecretsAcl invoked.'

    $paths = Resolve-ParkosPaths

    try {
        $acl = Get-Acl -Path $paths.SecretsPath -ErrorAction Stop
    } catch {
        $detail = "No se pudo leer el ACL de $($paths.SecretsPath): $($_.Exception.Message)"
        Write-Host "[FAIL] $detail" -ForegroundColor Red
        Write-ParkosLog "Test-ParkosSecretsAcl exit code: 1 ($detail)"
        $global:LASTEXITCODE = 1
        return [PSCustomObject]@{ ExitCode = 1; Detail = $detail }
    }

    # BUILTIN\Administrators exacto, o cualquier principal NT AUTHORITY\*
    # (SYSTEM, y el owner que Windows asigna por defecto a este tipo de
    # carpeta) - todo lo demas (usuario interactivo, dominio, Everyone,
    # BUILTIN\Users) es una falla.
    $allowedPattern = '^(BUILTIN\\Administrators|NT AUTHORITY\\.+)$'
    $extraneous = @($acl.Access |
        ForEach-Object { $_.IdentityReference.ToString() } |
        Where-Object { $_ -notmatch $allowedPattern } |
        Select-Object -Unique)

    if ($extraneous.Count -eq 0) {
        $detail = "ACL de $($paths.SecretsPath) correcta: solo Administrators/SYSTEM (u otro principal NT AUTHORITY) tienen acceso."
        Write-Host "[OK] $detail" -ForegroundColor Green
        $exitCode = 0
    } else {
        $detail = "ACL de $($paths.SecretsPath) expone principales adicionales no permitidos: $($extraneous -join ', ')."
        Write-Host "[FAIL] $detail" -ForegroundColor Red
        $exitCode = 1
    }

    Write-ParkosLog "Test-ParkosSecretsAcl exit code: $exitCode ($detail)"
    $global:LASTEXITCODE = $exitCode
    return [PSCustomObject]@{ ExitCode = $exitCode; Detail = $detail }
}

# ---------------------------------------------------------------------------
# Import-time installation detection (informational only - never blocks
# import; every cmdlet above works, in a limited/placeholder way, with or
# without a detected installation).
# ---------------------------------------------------------------------------

if (Test-Path (Join-Path $script:DefaultDataPath 'pairing.json')) {
    Write-Verbose '[Parkos] Instalacion detectada.'
} else {
    Write-Verbose '[Parkos] No se detecto instalacion - los cmdlets funcionaran en modo limitado.'
}
