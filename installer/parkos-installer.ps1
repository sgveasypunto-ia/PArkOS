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

    DEC-INST-17/18/19/20 (2026-09-27): Invoke-ParkosInstall is a MENU, not a
    forced linear wizard - the operator runs/re-runs any of 9 stages
    independently (0: descargar fuente (dev por defecto) + compilar, 1: Postgres+roles+pg_partman,
    2: migraciones, 3: configurar UUID de sucursal, 4: seed de catalogos,
    5: servicio api-sucursal, 6: job de sync, 7: app de escritorio,
    8: verificacion final). Each stage keeps its own hard gate (throws on
    failure, caught at the menu level so one bad stage doesn't kill the
    whole session) - see Invoke-TuiStep. Port reconciliation (DEC-INST-18):
    the API port is no longer hardcoded to 8000 anywhere - Test-ApiPort picks
    a free one and Set-MachineApiOrigin/PARKOS_API_ORIGIN propagate it to the
    packaged Electron app via its preload bridge (resolveRequestUrl.ts).
    Sucursal UUID (DEC-INST-19, CORRECTED by DEC-INST-22 on 2026-09-28): this
    installer never creates the prod.sucursal row - that row is created from
    the admin panel (a separate system, source of truth for sucursal data).
    The installer only collects/validates the UUID the admin panel already
    generated (Read-SucursalUuid) and writes it into the local env vars so
    api-sucursal/job-sync-sucursal know which sucursal they belong to; the
    row itself reaches this machine's Postgres later via job-sync-sucursal's
    own sync cycle, never via a direct SQL INSERT from this installer. Menu
    item 0 (descargar fuente (dev por defecto) + compilar) is DEC-INST-20. Stage 8 (verify) also
    installs the separate Parkos management module (Install-ManagementModule)
    after Test-PostInstallation passes - DEC-INST-21.

    NOTE (2026-09-28): DEC-INST-17/18/19/20 were originally miscited in this
    file as DEC-INST-02/03/04, colliding with the canonical decisions already
    assigned to those IDs in plan.md Sec.0.2 (standalone binaries, Postgres
    winget/ZIP fallback, no-superuser-at-runtime). Renumbered here and in
    plan.md's DEC-INST table to remove the collision; DEC-INST-01/02/14 below
    are correct, pre-existing citations and were left unchanged.

    DEC-INST-28..31 (PR4b, ultimo de 11 del plan de cierre de gaps): agrega
    -Command Restore real (Invoke-ParkosRestore), que revierte esta
    instalacion a una version previa archivada bajo releases\<version>\ (el
    mismo arbol que REPLACE de Invoke-ParkosUpdate ya escribe). Los binarios
    de api-sucursal/job-sync-sucursal siempre se revierten; la base de datos
    (-RestoreDatabase) y el MSI de escritorio son opcionales/best-effort - ver
    plan.md Sec.0.2 para el detalle de cada decision.

    DEC-INST-32..35 (PR5 de 11 del plan de cierre de gaps): -Unattended
    -Command Install ya NO cae en el menu interactivo de Invoke-ParkosInstall
    (que siempre terminaba bloqueado en un Read-Host, incompatible con un
    modo desatendido de verdad) - corre Invoke-ParkosUnattendedCascade, una
    cascada automatica de las mismas 9 etapas (0->8, definidas una sola vez
    en Get-ParkosStageDefinitions, compartida con el menu) con rollback
    automatico por etapa fallida, logging estructurado a
    $DataPath\installer-runs\<timestamp>.log, y exit codes 0 (completo u
    omitido a proposito)/1 (etapa fallida, con rollback intentado)/2
    (configuracion o pre-flight invalidos). -EulaAccepted reemplaza la
    aceptacion implicita que -Unattended tenia hasta ahora en Show-Eula;
    -SkipStage/-StopAfterStage permiten omitir etapas puntuales o cortar la
    cascada deliberadamente en una etapa dada.

.NOTES
    Ternary/null-coalescing operators are deliberately avoided even though
    PS7 supports them, so this file stays parseable (for syntax checks) on
    a box that only has Windows PowerShell 5.1 - the actual dev machine
    this was written on has no PowerShell 7 installed at all.

    Deliberately has NO `#Requires -Version 7.0`: that directive is
    enforced by the PS5.1 host before any script code runs, so it was
    silently defeating Ensure-PowerShell7 (HU-F21.2) below - the whole
    point of that function is to detect PS5.1, install PS7 and relaunch
    itself, but it can never run if the host refuses to start the script
    in the first place. PS7 is still required past that point; it is just
    no longer gated at parse time.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    # DEC-INST-24..27 (PR4a) + DEC-INST-28..31 (PR4b) de 11 del plan de
    # cierre de gaps: modo de la invocacion. 'Install' (default) preserva el
    # comportamiento previo (Invoke-ParkosInstall, TUI de menu). 'Update'
    # reemplaza binarios ya instalados por un payload nuevo
    # (Invoke-ParkosUpdate), con backup y rollback automatico obligatorios.
    # 'Restore' (PR4b) revierte esta instalacion a una version previa
    # archivada bajo releases\<version>\ (Invoke-ParkosRestore) - binarios
    # siempre, base de datos y MSI de escritorio opcionales/best-effort.
    [ValidateSet('Install', 'Update', 'Restore')]
    [string]$Command = 'Install',
    [string]$InstallPath = 'C:\Program Files\Parkos',
    [string]$DataPath = 'C:\ProgramData\Parkos',
    # Operational values the installer cannot invent - real business/ops
    # inputs, not defaults. Prompted interactively if left empty and
    # -Unattended is not set; -Unattended requires them to be passed.
    # UUID real de la sucursal, generado por el panel admin al crearla ahi -
    # este instalador NUNCA inserta la fila en prod.sucursal (DEC-INST-22,
    # corrige DEC-INST-19); solo valida el formato y lo propaga a las
    # variables de entorno. Prompted interactivamente si se deja vacio y no
    # se paso -Unattended; -Unattended lo exige.
    [string]$SucursalUuid = '',
    [string]$CloudApiUrl = '',
    [switch]$Unattended,
    # -Command Update: carpeta con el payload NUEVO (misma forma que
    # installer\payload\), compilado en otra maquina por build-release.ps1.
    [string]$PayloadPath = '',
    # -Command Update: restaura la release N-1 sin intentar reemplazar
    # binarios nuevos (sin backup nuevo, sin verificacion de payload nuevo).
    [switch]$RollbackOnly,
    # -Command Update: omite el pre-check de salud (Get-ParkosHealth). NUNCA
    # omite el backup ni la verificacion de firma/manifest del payload.
    [switch]$Force,
    # -Command Restore (PR4b): version objetivo - nombre de carpeta bajo
    # $InstallPath\releases\<Version>\, la misma que REPLACE de
    # Invoke-ParkosUpdate ya escribe (DEC-INST-24). Flag de confirmacion
    # desatendida con el mismo patron que -UnattendedPurgeConfirmed de
    # Uninstall-Parkos (plan.md BR2) - un solo flag copiado por error nunca
    # dispara un restore desatendido.
    [string]$Version = '',
    [switch]$UnattendedRestoreConfirmed,
    # -Command Restore: por defecto SOLO revierte binarios (api-sucursal/
    # job-sync-sucursal). Revertir tambien el schema de base de datos es mas
    # riesgoso (puede perder datos escritos despues de esa version) - exige
    # este switch explicito, nunca es el comportamiento por defecto.
    [switch]$RestoreDatabase,
    # DEC-INST-33 (PR5, cascada -Unattended): antes -Unattended aceptaba el
    # EULA IMPLICITAMENTE (Show-Eula: `if ($Unattended) { return $true }` sin
    # pedir nada). Ahora -Unattended exige este switch explicito ademas -
    # ver Show-Eula mas abajo. Fuera de -Unattended no tiene efecto (el
    # prompt interactivo ACEPTO sigue igual).
    [switch]$EulaAccepted,
    # DEC-INST-34 (PR5): etapas (0..8) a omitir en la cascada -Unattended
    # (ejemplo: -SkipStage @(7) para saltar la app de escritorio). Solo lo
    # consume Invoke-ParkosUnattendedCascade - el menu interactivo de
    # Invoke-ParkosInstall siempre muestra las 9 opciones, sin filtrar.
    [int[]]$SkipStage = @(),
    # DEC-INST-34 (PR5): -1 (default) corre las 9 etapas; un valor 0..8 corta
    # la cascada deliberadamente DESPUES de esa etapa (exit 0, no es un
    # fallo - util para debug de una etapa puntual sin correr el resto).
    [int]$StopAfterStage = -1,
    # Clave maestra de Parkos (>=32 bytes) entregada por el equipo de soporte:
    # si se pasa, se COPIA a payload\security\parkos-master.key (tras validar
    # su tamano) antes del pre-flight. NUNCA se genera una clave aqui y el
    # contenido jamas se imprime - ver Get-ParkosMasterKeyBytes.
    [string]$MasterKeyPath = '',
    # Flujo por defecto (sin switches) = instalacion GUIADA: el operador solo
    # tipea el UUID de la sucursal. -Menu abre el menu interactivo de 9
    # etapas (uso tecnico); no se combina con -Unattended.
    [switch]$Menu,
    # Flujo guiado: la etapa 0 (descargar fuente + compilar, git/pnpm/uv) NO
    # corre salvo con este switch - en una sucursal el payload llega ya
    # compilado (DEC-INST-20). El menu y -Unattended no lo necesitan.
    [switch]$IncludeBuild,
    # Rama de la que la etapa 0 descarga el fuente. Default dev (gitflow:
    # main solo recibe releases certificados); pasar release/vX.Y.Z o main
    # para compilar un release.
    [string]$SourceBranch = 'dev'
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

# DEC-INST-41 (PR10 de 11 del plan de cierre de gaps): $script:StageStatus
# pasa de booleano ($true/$false) a este enum - PowerShell trata CUALQUIER
# string no vacio (incluido el literal 'NotRun') como verdadero, asi que todo
# gate que compare el valor de una etapa debe hacerlo EXPLICITAMENTE contra
# [ParkosStageState]::Ok (nunca con `if (-not ...)`/`if (...)` implicito) -
# ver los gates de las etapas 3 y 4 en Get-ParkosStageDefinitions mas abajo.
enum ParkosStageState {
    NotRun
    Running
    Ok
    Failed
    RolledBack
    Blocked
}

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.1: pre-flight check (6 blocking verifications)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Flujo guiado: URL del cloud, relanzo con parametros y modo de instalacion
# ---------------------------------------------------------------------------

# Lee una variable de entorno en proceso, luego maquina, luego usuario (la
# primera con valor). Funcion propia para poder mockearla en las pruebas.
function Get-ParkosEnvironmentValue {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name)

    foreach ($target in 'Process', 'Machine', 'User') {
        $value = [System.Environment]::GetEnvironmentVariable($Name, $target)
        if (-not [string]::IsNullOrWhiteSpace($value)) { return $value.Trim() }
    }
    return $null
}

# URL de la API cloud: -CloudApiUrl explicito > PARKOS_CLOUD_API_URL > default
# http://localhost:8000. Nunca se pregunta al operador.
function Resolve-ParkosCloudApiUrl {
    [CmdletBinding()]
    param([string]$Explicit = '')

    $source = '-CloudApiUrl'
    $value = $Explicit
    if ([string]::IsNullOrWhiteSpace($value)) {
        $source = 'PARKOS_CLOUD_API_URL'
        $value = Get-ParkosEnvironmentValue -Name 'PARKOS_CLOUD_API_URL'
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return 'http://localhost:8000' }

    $value = $value.Trim()
    $uri = $null
    $valid = [uri]::TryCreate($value, [System.UriKind]::Absolute, [ref]$uri) -and
        ($uri.Scheme -eq 'http' -or $uri.Scheme -eq 'https')
    if (-not $valid) {
        throw "La direccion del servidor Parkos ('$value', tomada de $source) no es valida: debe empezar con http:// o https://. Corrija la variable de entorno PARKOS_CLOUD_API_URL (o el parametro -CloudApiUrl) o pida ayuda al equipo de soporte."
    }
    return $value.TrimEnd('/')
}

# Host, puerto efectivo y si es loopback de una URL (para el pre-flight).
function Get-ParkosCloudEndpoint {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Url)

    $uri = [uri]$Url
    return [PSCustomObject]@{
        Host       = $uri.Host
        Port       = $uri.Port
        IsLoopback = [bool]$uri.IsLoopback
    }
}

# Literal de PowerShell entre comillas simples (las comillas simples internas,
# incluidas las tipograficas que PowerShell tambien trata como comilla, se
# duplican).
function Format-ParkosPsLiteral {
    [CmdletBinding()]
    param([AllowEmptyString()][string]$Value)

    $escaped = [regex]::Replace($Value, "['\u2018\u2019\u201A\u201B]", '$0$0')
    return "'" + $escaped + "'"
}

# Reconstruye la lista de parametros con nombre ($PSBoundParameters) como
# tokens de una linea de comandos de PowerShell, para relanzar el script
# (elevacion / PowerShell 7) sin perder ninguno. $args NO sirve: no trae los
# parametros con nombre.
function ConvertTo-ParkosRelaunchArgs {
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Collections.IDictionary]$BoundParameters)

    $pathParams = @('MasterKeyPath', 'PayloadPath')
    $tokens = @()
    foreach ($name in $BoundParameters.Keys) {
        $value = $BoundParameters[$name]

        if ($value -is [System.Management.Automation.SwitchParameter]) {
            if ($value.IsPresent) { $tokens += "-$name" } else { $tokens += "-${name}:`$false" }
            continue
        }

        $items = @($value)
        $rendered = foreach ($item in $items) {
            if ($item -is [bool]) {
                if ($item) { '$true' } else { '$false' }
            } elseif ($item -is [int] -or $item -is [long] -or $item -is [double]) {
                [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, '{0}', $item)
            } else {
                $text = [string]$item
                # El proceso relanzado puede arrancar en otro directorio.
                if ($pathParams -contains $name -and -not [string]::IsNullOrWhiteSpace($text)) {
                    $text = [System.IO.Path]::GetFullPath($text)
                }
                Format-ParkosPsLiteral -Value $text
            }
        }
        $tokens += "-$name"
        $tokens += (@($rendered) -join ',')
    }
    return $tokens
}

# Argumentos de pwsh para relanzar este script: -EncodedCommand (no -File, que
# aplana los arreglos: -SkipStage 2,7 llegaria como 27) y propaga el codigo de
# salida del script.
function Get-ParkosRelaunchArgumentList {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ScriptPath,
        [string[]]$OriginalArgs = @()
    )

    $call = "& $(Format-ParkosPsLiteral -Value $ScriptPath)"
    if (@($OriginalArgs).Count -gt 0) { $call += ' ' + (@($OriginalArgs) -join ' ') }
    $body = "$call; exit `$LASTEXITCODE"
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($body))
    return @('-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded)
}

# Modo de la instalacion: Guided (default), Menu (-Menu) o Unattended.
function Resolve-ParkosInstallMode {
    [CmdletBinding()]
    param([switch]$Menu, [switch]$Unattended)

    if ($Menu -and $Unattended) {
        throw '-Menu y -Unattended son incompatibles: el menu es interactivo y -Unattended no puede preguntar nada. Elija uno solo.'
    }
    if ($Unattended) { return 'Unattended' }
    if ($Menu) { return 'Menu' }
    return 'Guided'
}

function Test-WindowsVersion {
    param([int]$MinBuild = 19044)  # Windows 10 21H2
    $build = [System.Environment]::OSVersion.Version.Build
    return $build -ge $MinBuild
}

function Test-Preflight {
    [CmdletBinding()]
    param(
        [string]$InstallPath = $script:InstallPath,
        [string]$DataPath = $script:DataPath,
        # Servidor cloud contra el que se mide la conectividad (host:puerto de
        # la URL, NO github.com). Vacio = se resuelve con
        # Resolve-ParkosCloudApiUrl (PARKOS_CLOUD_API_URL o el default).
        [string]$CloudApiUrl = '',
        # Flujo guiado: la clave maestra es el requisito duro - sin ella el
        # pre-flight bloquea. Sin el switch (menu) solo avisa.
        [switch]$RequireMasterKey
    )

    if ([string]::IsNullOrWhiteSpace($CloudApiUrl)) { $CloudApiUrl = Resolve-ParkosCloudApiUrl }
    $endpoint = Get-ParkosCloudEndpoint -Url $CloudApiUrl

    $driveLetter = $InstallPath.Substring(0, 1)
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator
    )
    $freeBytes = (Get-PSDrive -Name $driveLetter).Free
    $alreadyInstalled = Test-Path (Join-Path $DataPath 'pairing.json')

    $results = [ordered]@{
        'Windows >= 10 21H2'         = (Test-WindowsVersion)
        'PowerShell >= 7'            = ($PSVersionTable.PSVersion.Major -ge 7)
        'Permisos de administrador'  = $isAdmin
        'Espacio en disco (>=5GB)'   = ($freeBytes -gt 5GB)
        'Sin instalacion previa'     = (-not $alreadyInstalled)
    }

    # Conectividad: se mide contra el servidor Parkos configurado. Si es el
    # propio equipo (localhost) un fallo solo avisa - el servidor puede no
    # estar encendido todavia; si es remoto, bloquea.
    $reachable = [bool](Test-NetConnection -ComputerName $endpoint.Host -Port $endpoint.Port -InformationLevel Quiet -WarningAction SilentlyContinue)
    if ($reachable) {
        $results['Conexion con el servidor Parkos'] = $true
    } elseif (-not $endpoint.IsLoopback) {
        $results['Conexion con el servidor Parkos'] = $false
    }

    foreach ($check in $results.GetEnumerator()) {
        if ($check.Value) {
            Write-Host "[OK]    $($check.Key)" -ForegroundColor Green
        } else {
            Write-Host "[FALLO] $($check.Key)" -ForegroundColor Red
        }
    }
    if (-not $reachable) {
        if ($endpoint.IsLoopback) {
            Write-Host "[AVISO] No se pudo contactar al servidor Parkos en $($endpoint.Host):$($endpoint.Port) (este mismo equipo). Si el servidor esta en otro equipo, defina la variable de entorno PARKOS_CLOUD_API_URL con su direccion. La instalacion continua." -ForegroundColor Yellow
        } else {
            Write-Host "        No se pudo contactar a $($endpoint.Host):$($endpoint.Port). Revise la conexion a internet/red del equipo y que la direccion (PARKOS_CLOUD_API_URL) sea correcta." -ForegroundColor Red
        }
    }

    # Clave maestra: requisito duro en el flujo guiado; en el menu solo se
    # avisa (la etapa 0 corre sin ella, solo la etapa 1 la necesita).
    $masterKeyProblem = Get-ParkosMasterKeyProblem
    $masterKeyBlocks = $false
    if ($masterKeyProblem) {
        if ($RequireMasterKey) {
            $masterKeyBlocks = $true
            Write-Host '[FALLO] Clave maestra de Parkos' -ForegroundColor Red
            Write-Host "        $masterKeyProblem" -ForegroundColor Red
        } else {
            Write-Host '[AVISO] Clave maestra de Parkos ausente o invalida (la etapa 1 fallara sin ella)' -ForegroundColor Yellow
            Write-Host "        $masterKeyProblem" -ForegroundColor Yellow
        }
    } else {
        Write-Host '[OK]    Clave maestra de Parkos' -ForegroundColor Green
    }

    if ($alreadyInstalled) {
        Write-Host ''
        Write-Host 'Ya existe una instalacion de Parkos en este equipo.' -ForegroundColor Yellow
        Write-Host 'Use Repair-ParkosInstall o Invoke-ParkosUpdate en vez de una instalacion limpia (Fases 25/26).' -ForegroundColor Yellow
    }

    return (-not ($results.Values -contains $false)) -and (-not $masterKeyBlocks)
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
    $relaunchArgs = Get-ParkosRelaunchArgumentList -ScriptPath $PSCommandPath -OriginalArgs $OriginalArgs
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
# DEC-INST-20: descargar fuente (dev por defecto) + compilar (menu item 0)
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

# Wrapper de git para poder mockearlo en tests sin tocar el repo real.
function Invoke-Git {
    & git @args
}

# Trae el fuente de la rama indicada (default dev: gitflow del proyecto, main
# solo recibe releases certificados). El nombre se valida porque llega por
# parametro y se pasa a git.
function Update-SourceFromBranch {
    [CmdletBinding()]
    param(
        [string]$Branch = 'dev'
    )

    if ($Branch -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$') {
        throw "nombre de rama invalido: '$Branch'. Usa solo letras, numeros, '.', '_', '-' y '/'."
    }

    # installer/ es hijo directo de la raiz del repo (mismo calculo que
    # build-release.ps1's propio $RepoRoot).
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    Push-Location $repoRoot
    try {
        Invoke-Git fetch origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "git fetch origin $Branch fallo." }
        Invoke-Git checkout $Branch
        if ($LASTEXITCODE -ne 0) { throw "git checkout $Branch fallo." }
        Invoke-Git pull --ff-only origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only fallo (la rama local diverge de origin/$Branch - resolvelo manualmente antes de reintentar)." }
    } finally {
        Pop-Location
    }
}

function Invoke-SourceUpdateAndBuild {
    [CmdletBinding()]
    param(
        [string]$Branch = 'dev'
    )

    # @() fuerza array: una funcion que retorna @() desenrolla a $null y
    # $null.Count revienta bajo Set-StrictMode -Version Latest.
    $missing = @(Test-BuildToolchain)
    if ($missing.Count -gt 0) {
        throw "Falta instalar: $($missing -join ', '). Alternativa: corre build-release.ps1 a mano en una maquina con el toolchain completo y copia installer\payload\ aca."
    }

    Update-SourceFromBranch -Branch $Branch

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

    $relaunchArgs = Get-ParkosRelaunchArgumentList -ScriptPath $PSCommandPath -OriginalArgs $OriginalArgs
    $proc = Start-Process pwsh -ArgumentList $relaunchArgs -Wait -PassThru
    exit $proc.ExitCode
}

# ---------------------------------------------------------------------------
# Fase 21 - HU-F21.3: EULA y seleccion de rutas de instalacion
# ---------------------------------------------------------------------------

function Show-Eula {
    [CmdletBinding()]
    param([string]$EulaPath = (Join-Path $script:PayloadRoot 'README-EULA.txt'))

    # DEC-INST-33 (PR5): -Unattended ya NO acepta el EULA implicitamente -
    # exige -EulaAccepted explicito. Ni siquiera se muestra el texto por
    # consola en este camino (Out-Host -Paging bloquearia esperando input de
    # pagina, algo sin sentido - y sin operador presente - en un proceso
    # desatendido).
    if ($Unattended) {
        if ($EulaAccepted -ne $true) {
            throw 'EULA no aceptada explicitamente - modo -Unattended requiere -EulaAccepted.'
        }
        return $true
    }

    # -EulaAccepted tambien salta el prompt fuera de -Unattended (el operador
    # ya acepto el texto por otra via, p.ej. un script de despliegue).
    if ($EulaAccepted -eq $true) {
        return $true
    }

    if (-not (Test-Path $EulaPath)) {
        # Real legal text is a business/legal deliverable, not something to
        # fabricate here - fail loudly instead of shipping a blank EULA.
        throw "EULA file not found at $EulaPath - a real EULA (with PostgreSQL/NSSM/Electron third-party attributions) must be staged there before this installer ships."
    }

    # Mostrar el EULA de una sola vez (sin paginador) y leer ACEPTO
    # inmediatamente. Out-Host -Paging se elimino porque el paginador
    # agrega una capa de interaccion extra (espera de tecla por pagina)
    # entre el contenido y el prompt, sin beneficio real para un
    # EULA de tamano razonable.
    Get-Content $EulaPath
    Write-Host ''
    $answer = Read-Host 'Presione Enter para ACEPTAR los terminos y continuar (o escriba N y Enter para cancelar)'
    if (-not [string]::IsNullOrWhiteSpace($answer) -and $answer.Trim() -notin @('ACEPTO', 's', 'S', 'si', 'SI', 'Si')) {
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

    # Nunca pregunta: el operador no elige rutas. Se usan los valores por
    # defecto o los de -InstallPath/-DataPath, y se siguen rechazando las
    # rutas no permitidas.
    $installPath = $DefaultInstallPath
    if (-not (Test-InstallPathAllowed $installPath)) {
        throw "Ruta de instalacion invalida: $installPath (no se permite C:\Windows, Program Files (x86), ni rutas de red UNC)."
    }

    $dataPath = $DefaultDataPath
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

# DEC-INST-18 (port reconciliation): mismo patron que Test-PostgresPorts -
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

    # Auditoria de seguridad (confianza 8/10, severidad Medium): $SuperuserPassword
    # viajaba antes en texto plano dentro de $overrideArgs (argumento -c de
    # winget), visible en el argv del proceso hijo ante cualquier auditoria de
    # creacion de procesos de Windows (Event ID 4688 con linea de comandos
    # habilitada, Sysmon, EDR).
    #
    # Investigado (no asumido) contra la documentacion oficial real del
    # instalador de PostgreSQL para Windows - BitRock/InstallBuilder, el mismo
    # binario que `winget install --override` invoca en modo silencioso:
    # https://www.enterprisedb.com/docs/supported-open-source/postgresql/installing/command_line_parameters/
    # documenta `--optionfile <path>` como alternativa real (no inventada) a
    # pasar `--superpassword`/`--serverport`/`--disable-components` como
    # argumentos sueltos - el instalador lee esos mismos parametros de un
    # archivo en vez del command line. `mode`/`unattendedmodeui` (ningun
    # secreto) se dejan en el override literal a proposito: un hilo de la
    # lista de correo de postgresql.org documenta que definir
    # `mode=unattended` DENTRO del optionfile (en vez del CLI) deja vacio el
    # data directory en algunas versiones del instalador - se evita ese bug
    # conocido dejando esas dos claves fuera del archivo.
    $optionFile = New-TemporaryFile
    try {
        Set-Content -Path $optionFile -Encoding ascii -Value @(
            "superpassword=$SuperuserPassword"
            "serverport=$Port"
            'disable-components=stackbuilder'
        )
        $overrideArgs = "--mode unattended --unattendedmodeui none --optionfile `"$optionFile`""
        winget install --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements --override $overrideArgs | Out-Host
        return $LASTEXITCODE -eq 0
    } finally {
        Remove-Item $optionFile -Force -ErrorAction SilentlyContinue
    }
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

# DEC-INST-32 (PR5): devuelve el metodo REAL que instalo Postgres ('winget'
# o 'zip') - antes esta funcion era void. El rollback automatico de la etapa
# 1 (-Unattended, Get-ParkosStageDefinitions) necesita saber cual de los dos
# para desinstalar con el mecanismo correcto (winget uninstall vs. borrar el
# directorio del ZIP); guardado por el llamador en $script:PostgresInstallMethod.
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
        return 'winget'
    }

    Write-Host 'winget no disponible o fallo; usando ZIP de EDB del payload...' -ForegroundColor Yellow
    $zipPath = Join-Path $script:PayloadRoot 'postgres\postgresql-16-windows-x64-binaries.zip'
    if (-not (Test-Path $zipPath)) {
        throw "Ni winget ni el ZIP de fallback ($zipPath) estan disponibles; no se puede instalar Postgres."
    }
    Install-PostgresViaZip -PayloadZipPath $zipPath -PgInstallPath $PgInstallPath -PgDataPath $PgDataPath -Port $Port -SuperuserPassword $SuperuserPassword
    return 'zip'
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

# DEC-INST-42: las 3 passwords de Postgres que usa Initialize-DatabaseRoles
# (bootstrap del rol nativo `postgres` + superusuario `parkos` + rol de
# runtime `parkos_app`) dejan de ser aleatorias (New-SecurePassword de
# arriba) y pasan a derivarse deterministicamente de
# HMAC-SHA256(clave_maestra, "<uuid_sucursal>:<purpose>"). Motivo real: el
# UUID de sucursal NO es secreto - se tipea a mano en el prompt, queda sin
# redactar en env-redacted.txt (Export-ParkosDiagnostics, DEC-INST-38) y vive
# tambien en el panel admin. Si la password derivara SOLO del UUID (p. ej.
# base64(uuid)), cualquiera que vea el UUID - incluido quien recibe un ZIP de
# diagnostico de soporte - reconstruye la password real de la base de datos.
# Con una clave maestra que no viaja en el repo ni se deriva de nada publico,
# la password sigue siendo reproducible por soporte (con el UUID + la clave
# maestra, sin entrar a cada maquina ni depender de backups de .pgpass), pero
# nadie mas puede derivarla solo con el UUID. `Ensure-ServiceAccount` (mas
# abajo) NO participa de este cambio: esa es la password de la cuenta LOCAL
# DE WINDOWS svc-parkos, no una password de Postgres, y sigue usando
# New-SecurePassword sin modificar.
# Tamano minimo de la clave maestra (HMAC-SHA256: menos de 32 bytes debilita
# la derivacion de las 3 passwords de Postgres).
$script:MasterKeyMinBytes = 32

function Get-ParkosMasterKeyDefaultPath {
    return (Join-Path $script:PayloadRoot 'security\parkos-master.key')
}

# Valida la clave maestra SIN exponer su contenido: devuelve $null si es
# valida, o el mensaje de error accionable (nunca los bytes).
function Get-ParkosMasterKeyProblem {
    param([string]$MasterKeyPath = (Get-ParkosMasterKeyDefaultPath))
    if (-not (Test-Path -LiteralPath $MasterKeyPath -PathType Leaf)) {
        return "No se encontro la clave maestra de Parkos en $MasterKeyPath - es un secreto de la compania que NO se genera automaticamente ni vive en el repo. Solicitela al equipo de soporte por un canal seguro y copiela a esa ruta (o reintente con -MasterKeyPath <archivo>)."
    }
    $length = (Get-Item -LiteralPath $MasterKeyPath).Length
    if ($length -lt $script:MasterKeyMinBytes) {
        return "La clave maestra de Parkos en $MasterKeyPath es demasiado corta ($length bytes; minimo $($script:MasterKeyMinBytes)) - parece truncada o incorrecta. Solicite una copia valida al equipo de soporte por un canal seguro y reemplace ese archivo."
    }
    return $null
}

function Get-ParkosMasterKeyBytes {
    param([string]$MasterKeyPath = (Get-ParkosMasterKeyDefaultPath))
    $problem = Get-ParkosMasterKeyProblem -MasterKeyPath $MasterKeyPath
    if ($problem) { throw $problem }
    $bytes = [System.IO.File]::ReadAllBytes($MasterKeyPath)
    # Revalida sobre los bytes realmente leidos (el archivo pudo cambiar
    # entre la validacion y la lectura).
    if ($bytes.Length -lt $script:MasterKeyMinBytes) {
        throw "La clave maestra de Parkos en $MasterKeyPath es demasiado corta ($($bytes.Length) bytes; minimo $($script:MasterKeyMinBytes)) - parece truncada o incorrecta. Solicite una copia valida al equipo de soporte por un canal seguro y reemplace ese archivo."
    }
    return $bytes
}

# -MasterKeyPath <archivo>: copia la clave entregada por soporte a la ruta
# esperada por el instalador, validando antes su tamano. No genera nada ni
# imprime bytes.
function Import-ParkosMasterKey {
    param(
        [Parameter(Mandatory)][string]$SourcePath,
        [string]$DestinationPath = (Get-ParkosMasterKeyDefaultPath)
    )
    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
        throw "No se encontro el archivo indicado en -MasterKeyPath ($SourcePath) - solicite la clave maestra al equipo de soporte por un canal seguro."
    }
    $problem = Get-ParkosMasterKeyProblem -MasterKeyPath $SourcePath
    if ($problem) { throw $problem }
    $destDir = Split-Path -Parent $DestinationPath
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    if ([System.IO.Path]::GetFullPath($SourcePath) -ne [System.IO.Path]::GetFullPath($DestinationPath)) {
        Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    }
    Write-Host "Clave maestra copiada a $DestinationPath" -ForegroundColor Green
}

# `Purpose` distinto por rol es CRITICO: garantiza que las 3 passwords NUNCA
# sean iguales entre si aunque compartan UUID+clave maestra - evita que
# comprometer una cascada a las otras dos. El `-replace '[+/=]'` es el MISMO
# criterio que ya usa New-SecurePassword de arriba: un password con
# `+`/`/`/`=` puede romper la sintaxis de connection strings/comandos
# `psql -c` en algunos casos.
function New-ParkosDerivedPassword {
    param(
        [Parameter(Mandatory)][string]$SucursalUuid,
        [Parameter(Mandatory)][ValidateSet('postgres-bootstrap', 'parkos-superuser', 'parkos-app')][string]$Purpose,
        [byte[]]$MasterKeyBytes
    )
    if (-not $MasterKeyBytes) { $MasterKeyBytes = Get-ParkosMasterKeyBytes }
    $message = "${SucursalUuid}:${Purpose}"
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($MasterKeyBytes)
    try {
        $hash = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($message))
    } finally {
        $hmac.Dispose()
    }
    return ([Convert]::ToBase64String($hash) -replace '[+/=]', 'x')
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
    param([string]$PsqlPath, [int]$Port, [string]$BootstrapPassword, [Parameter(Mandatory)][string]$SucursalUuid)

    $superuserPassword = New-ParkosDerivedPassword -SucursalUuid $SucursalUuid -Purpose 'parkos-superuser'
    $appPassword = New-ParkosDerivedPassword -SucursalUuid $SucursalUuid -Purpose 'parkos-app'

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
    #
    # Auditoria de seguridad (confianza 8/10, severidad Medium): $sql (que
    # embebe $superuserPassword en texto plano dentro del `PASSWORD '...'`)
    # viajaba antes como argumento -c, visible en el argv del proceso ante
    # Event ID 4688/Sysmon/EDR - mismo hallazgo que Install-PostgresViaWinget.
    # psql, sin -c/-f, lee el batch completo desde stdin cuando no es
    # interactivo (comportamiento estandar y documentado de psql) - se pasa
    # el mismo texto SQL por el pipeline en vez de como argumento; el
    # contenido de un pipe no aparece en el argv del proceso hijo. El patron
    # ya existente en Install-PostgresViaZip (variable + limpieza) usa un
    # archivo temporal en vez de stdin porque ahi el consumidor es initdb.exe
    # (--pwfile), que no acepta stdin para ese proposito - psql si, por eso
    # aca la tecnica es el pipe, no un archivo.
    $sql | & $PsqlPath -w -p $Port -h 127.0.0.1 -U postgres | Out-Null
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
        # DEC-INST-43: gap real detectado comparando el despliegue Docker
        # (infra/deploy/docker-compose.branch.yml fija
        # PARKOS_SYNC_ENGINE=${PARKOS_SYNC_ENGINE:-catalog_branch} para
        # AMBOS servicios, api-sucursal y job-sync-sucursal) contra este
        # instalador, que nunca la seteaba. La variable es OBLIGATORIA, no
        # opcional - engine_flag.py::_parse() hace `raise
        # InvalidEngineModeError(...)` si esta ausente, sin ningun default.
        # get_engine() la invoca sync_router.py (montado por api-sucursal) y,
        # del lado de job-sync-sucursal, el flujo que sync_sucursal.py usa en
        # su loop principal (sync.cutover.dual_protocol/backfill). NOTA: a
        # diferencia de lo que se penso al principio, db/engine.py (motor de
        # SQLAlchemy, DATABASE_URL) NO llama get_engine() - confirmado
        # leyendo su codigo, no importa engine_flag; igual ambos servicios la
        # necesitan por las rutas de arriba. Sin esta linea, los 2 servicios
        # NSSM (ParkosApiSucursal, ParkosJobSyncSucursal) lanzan
        # InvalidEngineModeError apenas arrancan. 'catalog_branch' es el
        # unico valor ratificado (D22/ADR-001) para "branch workers"; los
        # otros 4 valores del enum son de otros servicios (api_admin,
        # dian/cloud dispatcher, jobs/sync_cloud) y no aplican aca.
        'PARKOS_SYNC_ENGINE=catalog_branch'
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
    Protect-ParkosEnvContent -EnvFilePath $EnvFilePath -Lines $lines
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
    Assert-PayloadPath -Path $migrateDir -What "el bundle del servicio 'migrate'"

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
# Fase 22b - HU-F22.x: UUID de sucursal (DEC-INST-22, corrige DEC-INST-19)
# ---------------------------------------------------------------------------
# DEC-INST-19 asumia que este instalador debia CREAR la fila de sucursal
# (Install-SucursalRow, un INSERT SQL directo) porque la investigacion
# original no encontro ningun endpoint/CLI para eso en el backend. Esa
# investigacion era correcta pero la conclusion no: el diseno real
# (confirmado por el operador, 2026-09-28) es que la sucursal SIEMPRE se
# crea desde el panel admin - un sistema aparte, no este instalador -, y esa
# fila llega a este Postgres local mas tarde via el propio ciclo de sync de
# job-sync-sucursal, nunca via SQL directo desde aca. Insertarla nosotros
# duplicaria/desincronizaria la fila que el sync va a traer.
#
# Este instalador entonces NUNCA escribe en prod.sucursal: solo recibe el
# UUID que el panel admin ya genero (por -SucursalUuid o interactivamente) y
# valida que tenga forma de UUID - mismo gate de siempre que ya usa
# runtime/env.py's load_config() (solo FORMA, nunca existencia), ahora la
# unica fuente de verdad esperada. Install-SucursalRow queda eliminada por
# completo - no es codigo muerto a mantener "por si acaso": es un camino que
# nunca deberia ejecutarse.
function Read-SucursalUuid {
    [CmdletBinding()]
    param([string]$Uuid = '')

    # Unica forma aceptada: 8-4-4-4-12 hexadecimal. No se "adivina" (32 hex
    # sin guiones o con llaves se rechazan: seria aceptar un dato mal copiado).
    $pattern = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    $maxAttempts = 5

    if ($Unattended) {
        if ([string]::IsNullOrWhiteSpace($Uuid)) {
            throw '-SucursalUuid es obligatorio en modo -Unattended (la sucursal se crea desde el panel admin, no desde este instalador).'
        }
        $candidate = $Uuid.Trim()
        if ($candidate -notmatch $pattern) {
            throw "El UUID de sucursal '$Uuid' no tiene formato valido (UUIDv4 esperado). Verificalo en el panel admin antes de reintentar."
        }
        return $candidate.ToLowerInvariant()
    }

    if (-not [string]::IsNullOrWhiteSpace($Uuid)) {
        $candidate = $Uuid.Trim()
        if ($candidate -match $pattern) { return $candidate.ToLowerInvariant() }
        Write-Host "El codigo de sucursal recibido ('$Uuid') no tiene el formato correcto. Escribalo de nuevo." -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Host 'Este es el unico dato que debe escribir: el codigo (UUID) de esta sucursal.' -ForegroundColor Cyan
    Write-Host 'Lo encuentra en el panel de administracion, en la ficha de la sucursal.' -ForegroundColor Cyan
    Write-Host 'Tiene este aspecto: 11111111-2222-3333-4444-555555555555 (puede copiarlo y pegarlo).' -ForegroundColor Cyan

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $answer = Read-Host 'Codigo (UUID) de la sucursal'
        $candidate = ([string]$answer).Trim()
        if ($candidate -match $pattern) { return $candidate.ToLowerInvariant() }
        Write-Host "Ese codigo no es valido: debe tener 5 grupos de letras/numeros separados por guiones (8-4-4-4-12). Intento $attempt de $maxAttempts." -ForegroundColor Yellow
    }
    throw "Demasiados intentos con un codigo de sucursal invalido ($maxAttempts). Verifique el codigo en el panel de administracion o pidalo al equipo de soporte, y vuelva a ejecutar el instalador."
}

# Idempotente - reescribe solo la linea PARKOS_SUCURSAL_UUID del .env sin
# tocar el resto (passwords, JWT paths, etc. ya escritos por la opcion 1).
# Permite corregir un UUID mal tipeado sin tener que reinstalar Postgres.
function Update-SucursalUuidInEnvFile {
    param([string]$EnvFilePath, [string]$SucursalUuid)

    if (-not (Test-Path $EnvFilePath)) {
        throw "No existe el archivo .env en $EnvFilePath - corre primero 'Instalar base de datos' (opcion 1)."
    }
    $lines = @(Read-ParkosEnvLines -EnvFilePath $EnvFilePath) | Where-Object { $_ -notmatch '^PARKOS_SUCURSAL_UUID=' }
    $lines += "PARKOS_SUCURSAL_UUID=$SucursalUuid"
    Protect-ParkosEnvContent -EnvFilePath $EnvFilePath -Lines $lines
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

    $envLines = Read-ParkosEnvLines -EnvFilePath $EnvFilePath
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

        # Auditoria de seguridad (confianza 8/10, severidad Medium): $migrationDsn
        # (embebe $Roles.SuperuserPassword en texto plano) viajaba antes como
        # argumento --database-url, visible en el argv del proceso ante Event
        # ID 4688/Sysmon/EDR. Mismo patron exacto que Invoke-MigrationsAndSeed
        # ya usa para migrate.exe (variable de entorno DATABASE_URL + limpieza
        # en finally) - entry_seed.py cae a leer DATABASE_URL del entorno
        # cuando --database-url no se pasa por CLI.
        $migrationDsn = "postgresql://parkos:$($Roles.SuperuserPassword)@127.0.0.1:$Port/parkos"
        try {
            $env:DATABASE_URL = $migrationDsn
            & $seedExe --api-base-url "http://127.0.0.1:$ApiPort" `
                --jwt-key-path $JwtKeyPath --sucursal-uuid $SucursalUuid
            if ($LASTEXITCODE -ne 0) {
                throw "seed.exe fallo (exit $LASTEXITCODE)."
            }
        } finally {
            Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
        }
    } finally {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Fase 24 - HU-F24.1/24.2: servicios NSSM (api-sucursal, job-sync-sucursal)
# ---------------------------------------------------------------------------

# Falla con un mensaje claro cuando falta un artefacto del payload (p. ej. la
# etapa 0 nunca corrio en esta maquina) en vez del "No se encuentra la ruta
# de acceso" crudo de Copy-Item/Get-ChildItem/Push-Location.
function Assert-PayloadPath {
    param([string]$Path, [string]$What)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Falta $What en el payload ($Path). Ejecute la opcion 0 (descarga y compilacion del payload) o copie el payload completo junto al instalador y reintente."
    }
}

function Copy-ServiceBundle {
    param([string]$Name, [string]$InstallPath)

    $src = Join-Path $script:PayloadRoot "services\$Name\$Name"
    Assert-PayloadPath -Path $src -What "el bundle del servicio '$Name'"
    Assert-PayloadPath -Path (Join-Path $src "$Name.exe") -What "el ejecutable '$Name.exe' del servicio '$Name'"
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

    $envVars = (Read-ParkosEnvLines -EnvFilePath $EnvFilePath) -join "`r`n"
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

    $envVars = ((Read-ParkosEnvLines -EnvFilePath $EnvFilePath) + @(
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

# DEC-INST-31 (PR4b): wrapper propio para desinstalar el MSI de web_sucursal
# ANTES de reinstalar una version archivada durante -Command Restore - mismo
# motivo que los wrappers de pg_dump/pg_restore/migrate.exe (comentario mas
# abajo, seccion "Wrappers de binarios externos"): Pester no puede mockear
# selectivamente un `Start-Process msiexec.exe` sin arrastrar cualquier otro
# uso de Start-Process en el archivo, asi que esto vive en su propia funcion
# nombrada. Mismo patron de registro que Install-Electron para encontrar la
# instalacion actual (Uninstall registry key, no Get-Package/Win32_Product).
# Si no hay ninguna instalacion actual (por ejemplo, la etapa 7 del menu
# nunca corrio en esta maquina), no hay nada que desinstalar - continua sin
# error, Install-Electron instala la version archivada igual.
function Uninstall-ParkosElectron {
    [CmdletBinding()]
    param()

    $installed = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -match 'Parkos' } | Select-Object -First 1
    if (-not $installed) {
        Write-Host 'No hay una version de web_sucursal instalada para desinstalar antes del restore; se procede directo a instalar la version archivada.' -ForegroundColor Yellow
        return
    }
    $productCode = $installed.PSChildName
    Start-Process msiexec.exe -ArgumentList "/x $productCode /qn" -Wait | Out-Null
}

# ---------------------------------------------------------------------------
# Fase 24 - HU-F24.4: verificacion post-instalacion integral (el gate final)
# ---------------------------------------------------------------------------

function Test-PostInstallation {
    param([string]$EnvFilePath, [int]$Port)

    $doctorExe = Join-Path $script:PayloadRoot 'services\doctor\doctor\doctor.exe'
    $envLines = Read-ParkosEnvLines -EnvFilePath $EnvFilePath
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

    # Test-JwtSecretGate (Fase 27/HU-F27.3/DEC-INST-40) reemplaza la
    # validacion inline previa (solo longitud >=32) - cubre lo mismo mas el
    # chequeo de denylist; como throws en vez de devolver booleano, se
    # envuelve en try/catch para seguir agregando a $results sin abortar
    # antes de tiempo (el throw agregado de "algun check en $false" ya pasa
    # unas lineas mas abajo).
    $jwtPath = ($envLines | Where-Object { $_ -match '^PARKOS_JWT_KEY_PATH=' }) -replace '^PARKOS_JWT_KEY_PATH=', ''
    $jwtOk = $true
    try {
        Test-JwtSecretGate -Path $jwtPath | Out-Null
    } catch {
        $jwtOk = $false
    }

    $results = [ordered]@{
        'Diagnostico general (doctor)'       = $doctorOk
        'Runtime conecta como parkos_app'    = $isAppUser
        'parkos_app no puede CREATE ROLE'    = $privilegeDenied
        'Secreto JWT pasa el gate (longitud + denylist)' = $jwtOk
    }
    $results.GetEnumerator() | Format-Table -AutoSize | Out-Host
    if ($results.Values -contains $false) {
        throw 'Verificacion post-instalacion fallo; ver detalle arriba. La instalacion NO se considera exitosa.'
    }
}

# ---------------------------------------------------------------------------
# Fase 24 - DEC-INST-23: manifest de hashes SHA256 de binarios instalados
# ---------------------------------------------------------------------------
# Base de verdad que Repair-ParkosInstall (modulo Parkos, PR3) usa para
# detectar binarios alterados (escenario E3) comparando Get-FileHash contra
# este archivo en vez de confiar ciegamente en lo que haya en disco. Se
# regenera COMPLETO en cada corrida de Install-ManagementModule (no es
# acumulativo) - un binario esperado que todavia no exista (por ejemplo si
# las etapas 5/6 del menu no corrieron en esta sesion) se omite del
# manifest con un warning en vez de hacer fallar toda la verificacion; el
# manifest documenta lo que SI esta instalado, no lo que deberia estarlo.
function New-ParkosBinaryManifest {
    param(
        [Parameter(Mandatory)][string]$InstallPath,
        [Parameter(Mandatory)][string]$DataPath
    )

    $expectedBinaries = [ordered]@{
        'api-sucursal.exe'      = Join-Path $InstallPath 'api-sucursal\api-sucursal.exe'
        'job-sync-sucursal.exe' = Join-Path $InstallPath 'job-sync-sucursal\job-sync-sucursal.exe'
        'doctor.exe'            = Join-Path $InstallPath 'doctor\doctor.exe'
    }

    $hashes = [ordered]@{}
    foreach ($name in $expectedBinaries.Keys) {
        $path = $expectedBinaries[$name]
        if (Test-Path $path) {
            $hashes[$name] = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToUpperInvariant()
        } else {
            Write-Host "Manifest: $name no encontrado en $path - se omite del manifest (correr antes las etapas que lo instalan)." -ForegroundColor Yellow
        }
    }

    $manifest = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        binaries     = $hashes
    }

    New-Item -ItemType Directory -Force -Path $DataPath | Out-Null
    $manifestPath = Join-Path $DataPath 'manifest.sha256.json'
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath
    Write-Host "Manifest de binarios generado en: $manifestPath" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Fase 24 - modulo de gestion Parkos (PR1 de 11 del plan de cierre de gaps)
# ---------------------------------------------------------------------------
# DEC-INST-21: el modulo de gestion post-instalacion (diagnostico, reparacion,
# desinstalacion, backups, etc.) vive en un paquete PowerShell SEPARADO
# (installer/payload/management/Parkos.psd1|psm1), versionado semanticamente
# (carpeta C:\Program Files\PowerShell\Modules\Parkos\<version>\, el layout
# estandar que $env:PSModulePath resuelve para PS7) en vez de vivir dentro de
# parkos-installer.ps1. Un tecnico de campo puede importarlo de forma
# independiente sin correr el TUI completo. Install-ManagementModule NUNCA
# sobreescribe una version ya instalada con contenido distinto - ver el
# comentario dentro de la funcion.
function Install-ManagementModule {
    param(
        [string]$ManagementPayloadPath = (Join-Path $script:PayloadRoot 'management'),
        [string]$InstallPath = 'C:\Program Files\Parkos'
    )

    $moduleVersion = '1.0.0'
    $sourceFiles = 'Parkos.psd1', 'Parkos.psm1', 'about_Parkos.help.txt'
    foreach ($file in $sourceFiles) {
        $src = Join-Path $ManagementPayloadPath $file
        if (-not (Test-Path $src)) {
            throw "Falta $src en el payload - no se puede instalar el modulo de gestion Parkos."
        }
    }

    $destDir = Join-Path "$env:ProgramFiles\PowerShell\Modules\Parkos" $moduleVersion
    $destModulePath = Join-Path $destDir 'Parkos.psm1'

    if (Test-Path $destDir) {
        # No hay logica de versionado automatico todavia (eso queda para un
        # PR futuro si aparece en la practica) - si la MISMA version exacta
        # ya esta instalada, comparamos el contenido real (hash) en vez de
        # asumir. Si son iguales, es un re-run idempotente: skip. Si son
        # distintos, alguien instalo manualmente una version 1.0.0 divergente
        # - eso es un conflicto que debe resolverse a mano, nunca sobreescrito
        # en silencio.
        if (Test-Path $destModulePath) {
            $srcHash = (Get-FileHash (Join-Path $ManagementPayloadPath 'Parkos.psm1') -Algorithm SHA256).Hash
            $destHash = (Get-FileHash $destModulePath -Algorithm SHA256).Hash
            if ($srcHash -eq $destHash) {
                Write-Host "Modulo de gestion Parkos $moduleVersion ya esta instalado (contenido identico); no se reinstala." -ForegroundColor Yellow
                return
            }
            throw "Ya existe una version $moduleVersion del modulo Parkos en $destDir con contenido DISTINTO al del payload actual. Esto no se resuelve automaticamente (sin versionado automatico en PR1) - revisa manualmente cual version debe prevalecer antes de continuar."
        }
    }

    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    foreach ($file in $sourceFiles) {
        Copy-Item (Join-Path $ManagementPayloadPath $file) (Join-Path $destDir $file) -Force
    }

    Write-Host "Modulo de gestion Parkos instalado en: $destDir" -ForegroundColor Green

    # doctor.exe (onedir de PyInstaller) HOY solo vive en el payload del
    # instalador - Copy-ServiceBundle (Fase 24) nunca lo copia a la maquina
    # final (solo copia api-sucursal y job-sync-sucursal). El modulo de
    # gestion Parkos (Get-ParkosHealth) lo necesita en runtime para su check
    # de diagnostico, asi que se copia aca, con el mismo patron de
    # Copy-ServiceBundle: el onedir COMPLETO, no solo el .exe suelto.
    $doctorSrc = Join-Path $script:PayloadRoot 'services\doctor\doctor'
    if (-not (Test-Path $doctorSrc)) {
        throw "Falta $doctorSrc en el payload - no se puede instalar doctor.exe para el modulo de gestion Parkos."
    }
    $doctorDest = Join-Path $InstallPath 'doctor'
    New-Item -ItemType Directory -Force -Path $doctorDest | Out-Null
    Copy-Item "$doctorSrc\*" $doctorDest -Recurse -Force

    Write-Host "doctor.exe instalado en: $doctorDest" -ForegroundColor Green

    # nssm.exe: igual que doctor.exe arriba, el modulo de gestion Parkos
    # (Repair-ParkosInstall, PR3) corre standalone en una sucursal ya
    # instalada, sin el resto del payload del instalador disponible - E1
    # (re-registrar un servicio NSSM faltante) necesita su propia copia de
    # nssm.exe en vez de asumir que el payload completo sigue presente.
    $nssmSrc = Join-Path $script:PayloadRoot 'nssm.exe'
    if (-not (Test-Path $nssmSrc)) {
        throw "Falta $nssmSrc en el payload - no se puede instalar nssm.exe para el modulo de gestion Parkos."
    }
    Copy-Item $nssmSrc (Join-Path $InstallPath 'nssm.exe') -Force
    Write-Host "nssm.exe instalado en: $(Join-Path $InstallPath 'nssm.exe')" -ForegroundColor Green

    # DEC-INST-23: manifest de hashes de los binarios recien instalados -
    # ver New-ParkosBinaryManifest arriba.
    New-ParkosBinaryManifest -InstallPath $InstallPath -DataPath $script:DataPath
}

# ---------------------------------------------------------------------------
# Fase 25/26 - HU-F25/26: actualizacion (-Command Update)
# ---------------------------------------------------------------------------
# PR4a (de 11 del plan de cierre de gaps): reemplaza binarios ya instalados
# por un payload NUEVO (compilado en otra maquina por build-release.ps1, con
# el manifest DEC-INST-26), con backup obligatorio (pg_dump) y rollback
# automatico ante cualquier falla posterior al reemplazo. PR4b (un PR
# posterior, NO este) implementara -Command Restore reusando esta misma
# infraestructura (Start-ParkosServicesInOrder, manifest de payload, etc.).

# Duplica la logica de deteccion de puerto de Parkos.psm1's
# script:Get-ParkosPostgresPort - esa funcion es privada del modulo
# (script:) y no se puede importar/reusar entre archivos; consecuencia
# mecanica del split de modulo separado de DEC-INST-21, no una decision
# nueva.
function Get-EnvFilePostgresPort {
    param([Parameter(Mandatory)][string]$EnvFilePath)

    if (-not (Test-Path $EnvFilePath)) {
        throw "No se encontro el archivo .env en $EnvFilePath - corre primero una instalacion (Invoke-ParkosInstall) antes de actualizar."
    }
    $envMap = [ordered]@{}
    foreach ($line in (Read-ParkosEnvLines -EnvFilePath $EnvFilePath)) {
        $parts = $line -split '=', 2
        $envMap[$parts[0]] = $parts[1]
    }
    foreach ($key in 'PARKOS_DB_URL', 'DATABASE_URL') {
        if ($envMap.Contains($key) -and $envMap[$key] -match '@[^:/]+:(\d+)/') {
            return [int]$Matches[1]
        }
    }
    throw 'No se pudo determinar el puerto de Postgres desde PARKOS_DB_URL ni DATABASE_URL en el .env.'
}

# DEC-INST-25: migrate.exe necesita la contrasena del superusuario 'parkos'
# para su DATABASE_URL, pero Invoke-ParkosUpdate corre en una sesion nueva
# sin $script:roles en memoria (eso solo existe durante una corrida en vivo
# de Invoke-ParkosInstall). Initialize-DatabaseRoles ya escribe la entrada
# del superusuario 'parkos' en pgpass.conf via Set-PgPassFile al instalar -
# esta funcion la recupera parseando ese mismo formato
# (host:port:database:user:password). Lanza excepcion si no la encuentra -
# nunca continua en silencio con una credencial faltante. La contrasena
# jamas se imprime con Write-Host.
function Get-PgPassPassword {
    param(
        [Parameter(Mandatory)][string]$DataPath,
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][int]$Port
    )

    $pgpassPath = Join-Path $DataPath 'secrets\pgpass.conf'
    if (-not (Test-Path $pgpassPath)) {
        throw "No se encontro pgpass.conf en $pgpassPath - no se puede recuperar la credencial de '$User'."
    }
    foreach ($line in (Get-Content -Path $pgpassPath)) {
        $parts = $line -split ':', 5
        if ($parts.Count -ne 5) { continue }
        if ([int]$parts[1] -eq $Port -and $parts[3] -eq $User) {
            return $parts[4]
        }
    }
    throw "No se encontro una credencial para el usuario '$User' en el puerto $Port dentro de pgpass.conf."
}

# ---------------------------------------------------------------------------
# Wrappers de binarios externos (pg_dump/pg_restore/migrate.exe) - Pester no
# puede interceptar una llamada `&` a una ruta literal, pero SI puede
# mockear una funcion nombrada (mismo motivo por el que Parkos.psm1 ya usa
# script:Invoke-ParkosNssm). Necesario para que installer/tests pueda
# mockear cada limite externo sin invocar binarios reales.
# ---------------------------------------------------------------------------

function Invoke-ParkosPgDump {
    param([Parameter(Mandatory)][string]$DumpPath, [Parameter(Mandatory)][int]$Port)

    $pgDumpExe = 'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe'
    & $pgDumpExe -Fc -U parkos_app -h 127.0.0.1 -p $Port -d parkos -f $DumpPath
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump.exe fallo (exit $LASTEXITCODE) generando el backup en $DumpPath."
    }
}

# Verifica que el dump generado no este vacio/corrupto: pg_restore --list
# debe listar al menos 1 objeto real. Cualquier linea que no empiece con ';'
# (comentario del listado) cuenta como objeto.
function Test-ParkosDumpHasObjects {
    param([Parameter(Mandatory)][string]$DumpPath)

    $pgRestoreExe = 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe'
    $listing = & $pgRestoreExe --list $DumpPath 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    $objectLines = $listing | Where-Object { $_ -and ($_ -notmatch '^;') }
    return (@($objectLines).Count -ge 1)
}

function Invoke-ParkosPgRestoreClean {
    param([Parameter(Mandatory)][string]$DumpPath, [Parameter(Mandatory)][int]$Port)

    $pgRestoreExe = 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe'
    & $pgRestoreExe --clean --if-exists -U parkos -h 127.0.0.1 -p $Port -d parkos $DumpPath
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore --clean --if-exists fallo (exit $LASTEXITCODE) restaurando $DumpPath durante el rollback."
    }
}

# Corre migrate.exe ya parado en su propio directorio (alembic.ini es
# CWD-relative, ver Invoke-MigrationsAndSeed) con DATABASE_URL ya seteado
# por el llamador; devuelve el exit code en vez de lanzar, para que
# Invoke-ParkosUpdate decida el rollback tier-2 en su propio catch.
function Invoke-ParkosMigrateExe {
    param([Parameter(Mandatory)][string]$MigrateExePath)

    & $MigrateExePath -c alembic.ini upgrade head
    return $LASTEXITCODE
}

# DEC-INST-29 (PR4b): extraida del paso STOP de Invoke-ParkosUpdate (que
# antes tenia este mismo Stop-Service x2 inline) para que Invoke-ParkosRestore
# (PR4b) reuse la MISMA funcion en vez de duplicar el stop-en-orden-inverso -
# mismo motivo que Start-ParkosServicesInOrder ya existia como funcion propia
# en vez de vivir inline en cada llamador. Orden inverso al de arranque (job
# de sync primero, luego api) - -ErrorAction SilentlyContinue porque un
# servicio que ya esta detenido (o que nunca llego a registrarse) no debe
# abortar ni STOP ni Restore.
function Stop-ParkosServicesInOrder {
    Stop-Service ParkosJobSyncSucursal -ErrorAction SilentlyContinue
    Stop-Service ParkosApiSucursal -ErrorAction SilentlyContinue
}

# Rollback architecture compartida (evita triplicar esta logica entre
# MIGRATE/RESTART/SMOKE TEST): arranca los 2 servicios en el mismo orden que
# el resto del instalador (api primero, luego job de sync), con los mismos
# helpers Wait-ForApiHealth/Wait-ForSyncPollCycle que ya existen (30s de
# timeout cada uno). Usada 3 veces: RESTART normal, recuperacion tier-1 de
# VERIFY BINARIES, y al final del rollback completo tier-2.
function Start-ParkosServicesInOrder {
    param(
        [Parameter(Mandatory)][int]$ApiPort,
        [Parameter(Mandatory)][string]$SyncLogPath
    )

    Start-Service ParkosApiSucursal
    if (-not (Wait-ForApiHealth -Url "http://127.0.0.1:$ApiPort/health" -TimeoutSeconds 30)) {
        throw 'ParkosApiSucursal no respondio /health a tiempo tras el reinicio.'
    }
    Start-Service ParkosJobSyncSucursal
    if (-not (Wait-ForSyncPollCycle -LogPath $SyncLogPath -TimeoutSeconds 30)) {
        throw 'ParkosJobSyncSucursal no mostro un ciclo de sondeo en el log tras el reinicio.'
    }
}

# Rollback tier-2 (ver el comentario extenso dentro de Invoke-ParkosUpdate
# sobre por que existen dos tiers distintos): REPLACE ya corrio (binarios
# movidos y, segun donde haya fallado, tambien la migracion) - esta funcion
# revierte AMBOS: restaura el dump de backup con pg_restore --clean, mueve
# los binarios viejos desde releases\<version>\ de vuelta a su lugar, y
# reinicia los servicios. NUNCA la llama el paso VERIFY BINARIES (tier-1) -
# ahi nada toco la DB ni los binarios todavia.
function Invoke-ParkosUpdateFullRollback {
    param(
        [Parameter(Mandatory)][string]$DumpPath,
        [Parameter(Mandatory)][string]$OutgoingVersion,
        [Parameter(Mandatory)][string]$InstallPath,
        [Parameter(Mandatory)][string]$DataPath,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][int]$ApiPort,
        [Parameter(Mandatory)][string]$SyncLogPath
    )

    Write-Host '  Revirtiendo actualizacion (rollback completo)...' -ForegroundColor Yellow

    Invoke-ParkosPgRestoreClean -DumpPath $DumpPath -Port $Port

    $releaseDir = Join-Path $InstallPath "releases\$OutgoingVersion"
    foreach ($name in 'api-sucursal', 'job-sync-sucursal') {
        $releaseBundle = Join-Path $releaseDir $name
        if (Test-Path $releaseBundle) {
            $dest = Join-Path $InstallPath $name
            Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
            Move-Item $releaseBundle $dest -Force
        } else {
            Write-Host "  Advertencia: no se encontro $releaseBundle - no se pudo revertir $name (revisar manualmente)." -ForegroundColor Yellow
        }
    }

    New-ParkosBinaryManifest -InstallPath $InstallPath -DataPath $DataPath
    Start-ParkosServicesInOrder -ApiPort $ApiPort -SyncLogPath $SyncLogPath

    Write-Host '  Rollback completado; version anterior restaurada.' -ForegroundColor Green
}

function Invoke-ParkosUpdate {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    $stepNames = @(
        'PRE-CHECK', 'BACKUP', 'STOP', 'VERIFY BINARIES', 'REPLACE',
        'MIGRATE', 'RESTART', 'SMOKE TEST', 'SUCCESS'
    )
    if ($WhatIfPreference) {
        Write-Host '=== Parkos - actualizacion (-WhatIf, ningun cambio real) ===' -ForegroundColor Cyan
        foreach ($step in $stepNames) {
            Write-Host "  [WHATIF] $step" -ForegroundColor Yellow
        }
        return [PSCustomObject]@{ ExitCode = 0; Detail = 'WhatIf: ningun paso se ejecuto realmente.' }
    }

    $envFilePath = Join-Path $DataPath 'secrets\.env'
    $releasesPath = Join-Path $InstallPath 'releases'
    $syncLogPath = Join-Path $DataPath 'logs\job-sync.out.log'
    $currentVersionFile = Join-Path $DataPath 'current-version.txt'

    $port = Get-EnvFilePostgresPort -EnvFilePath $envFilePath
    $envLines = Read-ParkosEnvLines -EnvFilePath $envFilePath
    $apiPort = 8000
    $apiPortLine = $envLines | Where-Object { $_ -match '^PORT=' } | Select-Object -First 1
    if ($apiPortLine) {
        $apiPort = [int]($apiPortLine -replace '^PORT=', '')
    }

    if ($RollbackOnly) {
        Write-Host '=== Parkos - rollback a la release anterior (-RollbackOnly) ===' -ForegroundColor Cyan
        if (-not (Test-Path $releasesPath)) {
            throw "No hay releases previas en $releasesPath - no hay nada a lo cual revertir."
        }
        $releaseDirs = Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        if (-not $releaseDirs -or @($releaseDirs).Count -eq 0) {
            throw "No hay releases previas en $releasesPath - no hay nada a lo cual revertir."
        }
        $mostRecent = @($releaseDirs)[0]
        foreach ($name in 'api-sucursal', 'job-sync-sucursal') {
            $releaseBundle = Join-Path $mostRecent.FullName $name
            if (Test-Path $releaseBundle) {
                $dest = Join-Path $InstallPath $name
                Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
                Move-Item $releaseBundle $dest -Force
            }
        }
        New-ParkosBinaryManifest -InstallPath $InstallPath -DataPath $DataPath
        Start-ParkosServicesInOrder -ApiPort $apiPort -SyncLogPath $syncLogPath
        Write-Host "Rollback a $($mostRecent.Name) completado." -ForegroundColor Green
        return [PSCustomObject]@{ ExitCode = 0; Detail = "Rollback a $($mostRecent.Name) completado." }
    }

    # -------------------------------------------------------------------
    # PRE-CHECK
    # -------------------------------------------------------------------
    Write-Host '=== Parkos - actualizacion ===' -ForegroundColor Cyan
    if ([string]::IsNullOrWhiteSpace($PayloadPath) -or -not (Test-Path $PayloadPath)) {
        throw "-PayloadPath vacio o inexistente ('$PayloadPath') - se requiere la carpeta con el payload nuevo (misma forma que installer\payload\)."
    }

    if (-not $Force) {
        Import-Module "$env:ProgramFiles\PowerShell\Modules\Parkos\1.0.0\Parkos.psd1" -Force -ErrorAction SilentlyContinue
        if (Get-Command Get-ParkosHealth -ErrorAction SilentlyContinue) {
            $health = Get-ParkosHealth
            if ($health.ExitCode -eq 2) {
                throw 'Get-ParkosHealth reporto ExitCode 2 (critico) - corre Repair-ParkosInstall antes de actualizar, o usa -Force para omitir este pre-check (el backup y la verificacion de integridad del payload NUNCA se omiten).'
            }
        } else {
            Write-Host 'Advertencia: el modulo de gestion Parkos no esta instalado (instalacion previa a PR1); no se puede correr el pre-check de salud. Continuando.' -ForegroundColor Yellow
        }
    }

    # Ausencia de releases previas es NORMAL en la primera actualizacion de
    # esta instalacion (DEC-INST-24) - nunca se aborta por esto.
    if (-not (Test-Path $releasesPath)) {
        Write-Host "Advertencia: no hay releases previas en $releasesPath (primera actualizacion de esta instalacion)." -ForegroundColor Yellow
    }

    # DEC-INST-24: version saliente (para nombrar releases\<version>\ y
    # correlacionar con el dump de backup) y version nueva (timestamp de
    # esta corrida, escrito en current-version.txt recien al final, en
    # SUCCESS - una falla a mitad de camino debe seguir apuntando a la
    # version vieja).
    $newVersion = (Get-Date).ToString('yyyyMMdd-HHmmss')
    if (Test-Path $currentVersionFile) {
        $outgoingVersion = (Get-Content $currentVersionFile -Raw).Trim()
    } else {
        $outgoingVersion = "unknown-$newVersion"
        Write-Host "Advertencia: no existe $currentVersionFile (primera actualizacion) - el seguimiento de versiones empieza ahora; la carpeta de release saliente se llama '$outgoingVersion' (no es un identificador de release real)." -ForegroundColor Yellow
    }

    # -------------------------------------------------------------------
    # BACKUP (siempre corre, incluso con -Force - nunca se omite)
    # -------------------------------------------------------------------
    $backupsDir = Join-Path $DataPath 'backups'
    New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null
    $dumpPath = Join-Path $backupsDir "pre-update-$outgoingVersion-$newVersion.dump"

    Invoke-TuiStep -Name 'BACKUP: pg_dump de la base de datos' -Action {
        Invoke-ParkosPgDump -DumpPath $dumpPath -Port $port
    }
    if (-not (Test-ParkosDumpHasObjects -DumpPath $dumpPath)) {
        throw "El backup en $dumpPath quedo vacio o invalido (pg_restore --list no reporto objetos) - actualizacion abortada ANTES de detener servicios; nada mas se ejecuto."
    }

    # -------------------------------------------------------------------
    # STOP (orden inverso al de arranque)
    # -------------------------------------------------------------------
    Invoke-TuiStep -Name 'STOP: detener servicios' -Action {
        Stop-ParkosServicesInOrder
    }

    # -------------------------------------------------------------------
    # VERIFY BINARIES - tier-1: si esto falla, REPLACE todavia NO corrio
    # (nada en disco ni en la DB cambio) - la unica recuperacion necesaria
    # es reiniciar los servicios que STOP acaba de detener. Llamar aca al
    # rollback completo (tier-2, pg_restore --clean incluido) seria
    # incorrecto/inutil: no hay nada que revertir en la DB todavia.
    # -------------------------------------------------------------------
    try {
        $manifestPath = Join-Path $PayloadPath 'manifest.sha256.json'
        if (-not (Test-Path $manifestPath)) {
            throw "Falta el manifest de integridad del payload en $manifestPath - no se puede verificar el payload nuevo."
        }
        # DEC-INST-26: las claves del manifest son rutas relativas bajo la
        # raiz del payload, no nombres de archivo sueltos.
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        foreach ($relativePath in $manifest.binaries.PSObject.Properties.Name) {
            $expectedHash = $manifest.binaries.$relativePath
            $fullPath = Join-Path $PayloadPath $relativePath
            if (-not (Test-Path $fullPath)) {
                throw "El payload nuevo no tiene el archivo esperado por el manifest: $relativePath."
            }
            $actualHash = (Get-FileHash -Path $fullPath -Algorithm SHA256).Hash
            if ($actualHash.ToUpperInvariant() -ne "$expectedHash".ToUpperInvariant()) {
                throw "Hash SHA256 no coincide para $relativePath - el payload puede estar corrupto o alterado."
            }
        }
        Write-Host '  [ OK ] VERIFY BINARIES: manifest de integridad del payload' -ForegroundColor Green
    } catch {
        Write-Host '  [FAIL] VERIFY BINARIES: manifest de integridad del payload' -ForegroundColor Red
        Write-Host "         $($_.Exception.Message)" -ForegroundColor Red
        Start-ParkosServicesInOrder -ApiPort $apiPort -SyncLogPath $syncLogPath
        throw
    }

    # -------------------------------------------------------------------
    # REPLACE
    # -------------------------------------------------------------------
    Invoke-TuiStep -Name 'REPLACE: mover binarios actuales a releases y copiar el payload nuevo' -Action {
        $outgoingDir = Join-Path $releasesPath $outgoingVersion
        New-Item -ItemType Directory -Force -Path $outgoingDir | Out-Null
        foreach ($name in 'api-sucursal', 'job-sync-sucursal') {
            $currentDir = Join-Path $InstallPath $name
            if (Test-Path $currentDir) {
                Move-Item $currentDir (Join-Path $outgoingDir $name) -Force
            }
            $newSrc = Join-Path $PayloadPath "services\$name\$name"
            $newDest = Join-Path $InstallPath $name
            New-Item -ItemType Directory -Force -Path $newDest | Out-Null
            Copy-Item "$newSrc\*" $newDest -Recurse -Force
        }

        # Rotacion: conservar solo las 2 releases mas recientes bajo
        # releases\ (orden lexicografico = cronologico, formato
        # yyyyMMdd-HHmmss).
        $allReleases = Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        if (@($allReleases).Count -gt 2) {
            foreach ($old in (@($allReleases) | Select-Object -Skip 2)) {
                Remove-Item $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        # Reusa la funcion ya existente (Fase 24/DEC-INST-23) para que
        # $DataPath\manifest.sha256.json (consumido por Repair-ParkosInstall)
        # refleje los binarios recien reemplazados.
        New-ParkosBinaryManifest -InstallPath $InstallPath -DataPath $DataPath

        # DEC-INST-28 (PR4b, gap retroactivo): archiva tambien el MSI NUEVO
        # (el que se esta instalando en ESTA actualizacion) bajo
        # releases\<newVersion>\apps\<nombre-original> - notar que es
        # $newVersion (la version que empieza ahora), no $outgoingVersion (la
        # que se esta reemplazando arriba): esto habilita que un futuro
        # -Command Restore -Version <newVersion> pueda reinstalar el MSI de
        # ESTA version. Es solo una copia de archivo - no dispara ninguna
        # (des)instalacion real, Install-Electron sigue siendo el unico lugar
        # que instala el MSI de verdad (etapa 7 del menu). Versiones
        # archivadas ANTES de este cambio nunca van a tener este MSI
        # disponible - Invoke-ParkosRestore maneja ese caso con un warning,
        # nunca asumiendo que siempre esta (ver DEC-INST-31).
        $newMsi = Get-ChildItem (Join-Path $PayloadPath 'apps') -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($newMsi) {
            $msiArchiveDir = Join-Path $releasesPath "$newVersion\apps"
            New-Item -ItemType Directory -Force -Path $msiArchiveDir | Out-Null
            Copy-Item $newMsi.FullName (Join-Path $msiArchiveDir $newMsi.Name) -Force
        } else {
            Write-Host "Advertencia: no se encontro un MSI en $PayloadPath\apps - no se archivo ningun instalador de escritorio para la version $newVersion (un futuro Restore a esta version no podra revertir la app de escritorio)." -ForegroundColor Yellow
        }
    }

    # -------------------------------------------------------------------
    # MIGRATE - tier-2: REPLACE ya corrio, cualquier falla desde aca en
    # adelante requiere el rollback completo (Invoke-ParkosUpdateFullRollback).
    # -------------------------------------------------------------------
    try {
        Invoke-TuiStep -Name 'MIGRATE: alembic upgrade head con el migrate.exe del payload nuevo' -Action {
            $migrateDir = Join-Path $PayloadPath 'services\migrate\migrate'
            $migrateExe = Join-Path $migrateDir 'migrate.exe'
            # DEC-INST-25: recupera la contrasena del superusuario 'parkos'
            # desde pgpass.conf - no hay $script:roles en esta sesion nueva.
            $superuserPassword = Get-PgPassPassword -DataPath $DataPath -User 'parkos' -Port $port
            Push-Location $migrateDir
            try {
                $env:DATABASE_URL = "postgresql://parkos:$superuserPassword@127.0.0.1:$port/parkos"
                $exitCode = Invoke-ParkosMigrateExe -MigrateExePath $migrateExe
                if ($exitCode -ne 0) {
                    throw "alembic upgrade head fallo (exit $exitCode) durante la actualizacion."
                }
            } finally {
                Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
                Pop-Location
            }
        }
    } catch {
        $failureMessage = $_.Exception.Message
        Invoke-ParkosUpdateFullRollback -DumpPath $dumpPath -OutgoingVersion $outgoingVersion `
            -InstallPath $InstallPath -DataPath $DataPath -Port $port -ApiPort $apiPort -SyncLogPath $syncLogPath
        return [PSCustomObject]@{ ExitCode = 1; Detail = "MIGRATE fallo y se reviritio la actualizacion: $failureMessage" }
    }

    # -------------------------------------------------------------------
    # RESTART - tier-2
    # -------------------------------------------------------------------
    try {
        Invoke-TuiStep -Name 'RESTART: reiniciar servicios' -Action {
            Start-ParkosServicesInOrder -ApiPort $apiPort -SyncLogPath $syncLogPath
        }
    } catch {
        $failureMessage = $_.Exception.Message
        Invoke-ParkosUpdateFullRollback -DumpPath $dumpPath -OutgoingVersion $outgoingVersion `
            -InstallPath $InstallPath -DataPath $DataPath -Port $port -ApiPort $apiPort -SyncLogPath $syncLogPath
        return [PSCustomObject]@{ ExitCode = 1; Detail = "RESTART fallo y se revirtio la actualizacion: $failureMessage" }
    }

    # -------------------------------------------------------------------
    # SMOKE TEST - tier-2. DEC-INST-27: no existe ningun usuario
    # smoke-test@parkos.local sembrado en installer/bootstrap/entry_seed.py
    # (solo installer-seed@parkos.local, rol admin) - el smoke test real
    # aca es /health (re-chequeado, ya cubierto implicitamente por RESTART)
    # mas GET /api/v1/sync/hello, publico por diseno (sin Depends de auth).
    # Un smoke test con login autenticado real queda pendiente de un
    # usuario de solo lectura dedicado que todavia no existe.
    # -------------------------------------------------------------------
    try {
        Invoke-TuiStep -Name 'SMOKE TEST: /health + GET /api/v1/sync/hello' -Action {
            $healthResp = Invoke-WebRequest -Uri "http://127.0.0.1:$apiPort/health" -UseBasicParsing -TimeoutSec 5
            if ($healthResp.StatusCode -ne 200) {
                throw "/health respondio $($healthResp.StatusCode), se esperaba 200."
            }
            $helloResp = Invoke-WebRequest -Uri "http://127.0.0.1:$apiPort/api/v1/sync/hello" -UseBasicParsing -TimeoutSec 5
            if ($helloResp.StatusCode -ne 200) {
                throw "/api/v1/sync/hello respondio $($helloResp.StatusCode), se esperaba 200."
            }
        }
    } catch {
        $failureMessage = $_.Exception.Message
        Invoke-ParkosUpdateFullRollback -DumpPath $dumpPath -OutgoingVersion $outgoingVersion `
            -InstallPath $InstallPath -DataPath $DataPath -Port $port -ApiPort $apiPort -SyncLogPath $syncLogPath
        return [PSCustomObject]@{ ExitCode = 1; Detail = "SMOKE TEST fallo y se revirtio la actualizacion: $failureMessage" }
    }

    # -------------------------------------------------------------------
    # SUCCESS
    # -------------------------------------------------------------------
    try {
        if (-not [System.Diagnostics.EventLog]::SourceExists('ParkosInstaller')) {
            New-EventLog -LogName Application -Source 'ParkosInstaller'
        }
        Write-EventLog -LogName Application -Source 'ParkosInstaller' -EventId 9001 -EntryType Information `
            -Message "Actualizacion de Parkos completada: $outgoingVersion -> $newVersion."
    } catch {
        Write-Host "Advertencia: no se pudo escribir en el Event Log ($($_.Exception.Message)); esto es solo informativo y no afecta el resultado de la actualizacion." -ForegroundColor Yellow
    }

    # DEC-INST-24: recien aca se sobreescribe current-version.txt - una
    # falla en cualquier paso anterior debe seguir apuntando a $outgoingVersion.
    Set-Content -Path $currentVersionFile -Value $newVersion -NoNewline

    Write-Host ''
    Write-Host "Actualizacion completada: $outgoingVersion -> $newVersion" -ForegroundColor Green
    Write-Host "Backup pre-actualizacion: $dumpPath" -ForegroundColor Green

    return [PSCustomObject]@{ ExitCode = 0; Detail = "Actualizacion completada: $outgoingVersion -> $newVersion." }
}

# ---------------------------------------------------------------------------
# Fase 26 - HU-F26.x: restauracion a una version anterior (-Command Restore)
# ---------------------------------------------------------------------------
# PR4b (ultimo de 11 del plan de cierre de gaps): reemplaza el placeholder
# `throw` de -Command Restore. Reusa la MISMA infraestructura que
# Invoke-ParkosUpdate ya escribe: releases\<version>\ bajo $InstallPath (NO
# bajo $DataPath - DEC-INST-30 corrige esto: $releasesPath ya vive bajo
# $InstallPath desde PR4a, ver la linea equivalente de Invoke-ParkosUpdate;
# usar $DataPath habria sido inconsistente con lo que REPLACE realmente
# escribe), Stop-/Start-ParkosServicesInOrder, New-ParkosBinaryManifest,
# current-version.txt, y los wrappers de pg_dump/pg_restore. Los binarios
# (api-sucursal/job-sync-sucursal) SIEMPRE se revierten; la base de datos
# (-RestoreDatabase) y el MSI de web_sucursal son opcionales/best-effort -
# ver DEC-INST-30/31 en plan.md para el detalle de cada criterio.
function Invoke-ParkosRestore {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    if ([string]::IsNullOrWhiteSpace($Version)) {
        throw '-Version es obligatorio para -Command Restore (ejemplo: -Version 20250101-000000).'
    }

    $releasesPath = Join-Path $InstallPath 'releases'
    $releaseDir = Join-Path $releasesPath $Version
    if (-not (Test-Path $releaseDir)) {
        $available = Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
        $availableText = if ($available) { $available -join ', ' } else { '(ninguna)' }
        throw "No existe la version '$Version' en $releasesPath. Versiones disponibles: $availableText."
    }

    # Confirmacion de doble paso (mismo patron que -PurgeData de
    # Uninstall-Parkos, plan.md BR2): palabra exacta 'RESTAURAR' en modo
    # interactivo, o el flag explicito -UnattendedRestoreConfirmed en modo
    # -Unattended - revertir binarios/DB es una operacion destructiva, nunca
    # silenciosa por defecto.
    if ($Unattended) {
        if (-not $UnattendedRestoreConfirmed) {
            throw '-UnattendedRestoreConfirmed es obligatorio junto con -Unattended para -Command Restore (evita que un flag copiado por error dispare un restore desatendido).'
        }
    } else {
        $answer = Read-Host "Esto va a restaurar Parkos a la version '$Version'. Escriba RESTAURAR para continuar (cualquier otra respuesta cancela sin tocar nada)"
        if ($answer -ne 'RESTAURAR') {
            Write-Host 'Restore cancelado por el operador. Nada fue modificado.' -ForegroundColor Yellow
            return [PSCustomObject]@{ ExitCode = 0; Detail = 'Restore cancelado por el operador antes de cualquier cambio.' }
        }
    }

    if ($WhatIfPreference) {
        Write-Host "=== Parkos - restore a $Version (-WhatIf, ningun cambio real) ===" -ForegroundColor Cyan
        return [PSCustomObject]@{ ExitCode = 0; Detail = 'WhatIf: ningun paso se ejecuto realmente.' }
    }

    Write-Host "=== Parkos - restore a version $Version ===" -ForegroundColor Cyan

    $envFilePath = Join-Path $DataPath 'secrets\.env'
    $port = Get-EnvFilePostgresPort -EnvFilePath $envFilePath
    $envLines = Read-ParkosEnvLines -EnvFilePath $envFilePath
    $apiPort = 8000
    $apiPortLine = $envLines | Where-Object { $_ -match '^PORT=' } | Select-Object -First 1
    if ($apiPortLine) { $apiPort = [int]($apiPortLine -replace '^PORT=', '') }
    $syncLogPath = Join-Path $DataPath 'logs\job-sync.out.log'
    $currentVersionFile = Join-Path $DataPath 'current-version.txt'
    $backupsDir = Join-Path $DataPath 'backups'

    # DEC-INST-30: flag puramente informacional en este PR - ningun otro
    # componente lo lee todavia. Un futuro mecanismo de auto-update deberia
    # respetarlo (no reintentar una actualizacion automatica sobre una
    # instalacion recien revertida a mano).
    $pauseFlagPath = Join-Path $DataPath 'auto-update-paused.flag'
    $pauseTimestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Set-Content -Path $pauseFlagPath -Value "$pauseTimestamp restored-to=$Version" -NoNewline

    try {
        Invoke-TuiStep -Name 'STOP: detener servicios' -Action {
            Stop-ParkosServicesInOrder
        }

        New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null
        $preRestoreTimestamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
        $preRestoreDumpPath = Join-Path $backupsDir "pre-restore-$Version-$preRestoreTimestamp.dump"
        Invoke-TuiStep -Name 'BACKUP: pg_dump previo al restore' -Action {
            Invoke-ParkosPgDump -DumpPath $preRestoreDumpPath -Port $port
        }

        Invoke-TuiStep -Name 'REPLACE BINARIES: restaurar binarios desde releases' -Action {
            foreach ($name in 'api-sucursal', 'job-sync-sucursal') {
                $releaseBundle = Join-Path $releaseDir $name
                if (-not (Test-Path $releaseBundle)) {
                    throw "Falta $releaseBundle - la version '$Version' archivada no tiene este binario disponible."
                }
                $dest = Join-Path $InstallPath $name
                Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
                New-Item -ItemType Directory -Force -Path $dest | Out-Null
                Copy-Item "$releaseBundle\*" $dest -Recurse -Force
            }
            New-ParkosBinaryManifest -InstallPath $InstallPath -DataPath $DataPath
            Set-Content -Path $currentVersionFile -Value $Version -NoNewline
        }

        # DEC-INST-30: SOLO si se pide explicitamente (-RestoreDatabase,
        # default $false - revertir schema es mas riesgoso que revertir
        # binarios). El dump debe matchear EXACTAMENTE
        # pre-update-<Version>-*.dump (el que Invoke-ParkosUpdate tomo justo
        # ANTES de actualizar DESDE esa version - representa su estado real).
        # Si hay varios (poco comun, pero posible tras reintentos), se usa el
        # mas reciente por nombre (el timestamp ordena lexicograficamente).
        # Nunca se adivina con "el dump mas reciente que sea" si no matchea
        # el patron exacto - eso podria restaurar el schema equivocado.
        if ($RestoreDatabase) {
            $matchingDumps = @(Get-ChildItem -Path $backupsDir -Filter "pre-update-$Version-*.dump" -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
            if ($matchingDumps.Count -gt 0) {
                $dbDump = $matchingDumps[0]
                Invoke-TuiStep -Name "RESTORE DATABASE: pg_restore --clean desde $($dbDump.Name)" -Action {
                    Invoke-ParkosPgRestoreClean -DumpPath $dbDump.FullName -Port $port
                }
            } else {
                Write-Host "Advertencia: no se encontro un dump 'pre-update-$Version-*.dump' en $backupsDir - no hay backup de base de datos que corresponda EXACTAMENTE a la version '$Version'. Continuando SIN restaurar la base de datos (el restore de binarios ya se aplico y no se revierte)." -ForegroundColor Yellow
            }
        }

        # DEC-INST-31: solo versiones archivadas DESPUES de DEC-INST-28 (este
        # PR) tienen un MSI bajo releases\<version>\apps\ - best-effort,
        # nunca aborta el restore de binarios ya aplicado.
        $archivedMsi = Get-ChildItem -Path (Join-Path $releaseDir 'apps') -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($archivedMsi) {
            Invoke-TuiStep -Name "REINSTALL MSI: revertir web_sucursal a $Version" -Action {
                Uninstall-ParkosElectron
                Install-Electron -MsiPath $archivedMsi.FullName
            }
        } else {
            Write-Host "Advertencia: no hay un MSI archivado para la version '$Version' (solo versiones archivadas despues de este cambio lo tienen) - la app de escritorio NO se pudo revertir. Continuando." -ForegroundColor Yellow
        }

        Invoke-TuiStep -Name 'RESTART: reiniciar servicios' -Action {
            Start-ParkosServicesInOrder -ApiPort $apiPort -SyncLogPath $syncLogPath
        }
    } catch {
        $failureMessage = $_.Exception.Message
        return [PSCustomObject]@{ ExitCode = 1; Detail = "Restore a $Version fallo: $failureMessage" }
    }

    Write-Host ''
    Write-Host "Restore a $Version completado." -ForegroundColor Green
    return [PSCustomObject]@{ ExitCode = 0; Detail = "Restore a $Version completado." }
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
# Fase 27 (HU-F27.2/DEC-INST-40): certificado CMS para cifrar el .env en reposo
# ---------------------------------------------------------------------------
# El plan original (HU-F27.2) pedia cifrado "DPAPI" via
# Protect-CmsMessage -To 'CN=ParkosLocalMachine' - verificado contra la
# documentacion real de PowerShell: no existe una API DPAPI de ALCANCE DE
# MAQUINA expuesta directamente por ningun cmdlet nativo (ConvertTo-
# SecureString solo cifra con alcance de USUARIO actual, inutil para un
# archivo que un servicio bajo otra cuenta - svc-parkos - necesita poder
# leer). El mecanismo real detras de la idea del plan es CMS (Cryptographic
# Message Syntax) contra un certificado de la maquina, que es exactamente lo
# que Protect-CmsMessage/Unprotect-CmsMessage implementan - y lo que
# Repair-ParkosInstall (Parkos.psm1, escenario E5) ya anticipa: CUALQUIER
# excepcion al parsear el .env (incluido un futuro fallo de
# Unprotect-CmsMessage) cae hoy en su mismo catch generico (ver
# Parkos.psm1:713-719), asi que ningun cambio adicional hace falta ahi para
# soportar este nuevo formato.
#
# -Type DocumentEncryptionCert (Key Encipherment + Data Encipherment, EKU de
# Document Encryption) es el UNICO tipo de New-SelfSignedCertificate que
# Protect-CmsMessage acepta como destinatario valido - un certificado
# generico sin ese EKU hace que Protect-CmsMessage falle con "No certificate
# found for recipient" pese a existir el certificado con el Subject correcto.
#
# Idempotente por Subject exacto (nunca por thumbprint): busca primero un
# certificado existente en Cert:\LocalMachine\My antes de crear uno nuevo,
# para nunca terminar con dos certificados validos para 'CN=ParkosEnvProtection'
# (un segundo certificado dejaria ambiguo cual usa Protect-CmsMessage al
# resolver el destinatario por nombre). El thumbprint se persiste en
# $DataPath\secrets\env-cert-thumbprint.txt solo como identificador de
# diagnostico - NO es secreto (no permite descifrar nada por si solo, la
# clave privada vive en el almacen de certificados de la maquina, protegida
# por Windows), asi que le alcanza con la misma ACL de secrets\ que protege
# al resto del directorio (Set-ParkosSecretsAcl, Fase 27/HU-F27.1).
# Wrapper minimo sobre Get-ChildItem contra el PSDrive Cert:\ - existe solo
# para que esta busqueda sea testeable: Pester 3.4.0 no intercepta de forma
# confiable un Mock de Get-ChildItem contra un proveedor con parametros
# dinamicos propios (Cert:\) - confirmado empiricamente (un Mock con
# -ParameterFilter sobre 'Cert:\LocalMachine\My' no siempre reemplaza la
# llamada real) - mismo motivo exacto por el que Parkos.psm1 ya envuelve
# nssm.exe/psql.exe/[EventLog]::SourceExists() en sus propios wrappers
# (Invoke-ParkosNssm/Invoke-ParkosPsql/Test-ParkosEventLogSourceExists).
# Devuelve $null (nunca un objeto vacio) cuando no hay ningun certificado con
# ese Subject.
function Get-ParkosEnvCert {
    [CmdletBinding()]
    param()

    return Get-ChildItem -Path 'Cert:\LocalMachine\My' -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -eq 'CN=ParkosEnvProtection' } |
        Select-Object -First 1
}

function Get-OrCreateParkosEnvCert {
    param([Parameter(Mandatory)][string]$DataPath)

    $cert = Get-ParkosEnvCert

    if (-not $cert) {
        $cert = New-SelfSignedCertificate -CertStoreLocation 'Cert:\LocalMachine\My' `
            -Subject 'CN=ParkosEnvProtection' -KeyUsage KeyEncipherment, DataEncipherment `
            -Type DocumentEncryptionCert
    }

    $secretsDir = Join-Path $DataPath 'secrets'
    New-Item -ItemType Directory -Force -Path $secretsDir | Out-Null
    Set-Content -Path (Join-Path $secretsDir 'env-cert-thumbprint.txt') -Value $cert.Thumbprint -NoNewline

    Grant-ParkosEnvCertKeyAccess -Certificate $cert

    return $cert
}

# Gap real dejado pendiente por PR9 (Fase 27): sin esto, Invoke-DailyBackup.ps1
# (PR8) corre bajo svc-parkos via tarea programada y necesita Unprotect-
# CmsMessage para leer el puerto de Postgres del .env cifrado - pero la clave
# privada del certificado, por default, solo es legible por Administrators/
# SYSTEM (quien la creo), NUNCA por una cuenta de servicio comun como
# svc-parkos. Sin esta ACL, el backup diario fallaria en produccion la
# primera vez que corriera de verdad (algo que ningun test unitario con
# mocks puede detectar). Best-effort deliberado (try/catch, solo advierte):
# esto es un endurecimiento adicional, no un gate que deba bloquear la
# instalacion si el mecanismo de claves de esta maquina difiere.
function Grant-ParkosEnvCertKeyAccess {
    # $Certificate deliberadamente SIN tipo declarado ([X509Certificate2]):
    # un parametro fuertemente tipado rechaza en el binding (antes de entrar
    # al try/catch de abajo) el fake [PSCustomObject] que los tests de
    # Get-OrCreateParkosEnvCert usan para simular un certificado - con el
    # parametro sin tipo, ese caso simplemente falla DENTRO del try (el
    # metodo de RSACertificateExtensions no aplica a un PSCustomObject) y
    # se maneja como cualquier otro "no se pudo ajustar la ACL", sin romper
    # esos tests.
    param(
        [Parameter(Mandatory)]$Certificate,
        [string]$Account = 'svc-parkos'
    )

    try {
        $rsaKey = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($Certificate)
        if (-not $rsaKey) {
            Write-Host "No se pudo resolver la clave privada de 'CN=ParkosEnvProtection' para ajustar su ACL - omitido." -ForegroundColor Yellow
            return
        }

        # CNG (moderno, default de New-SelfSignedCertificate en Windows
        # actuales) guarda la clave como un archivo suelto bajo
        # ProgramData\Microsoft\Crypto\Keys\<UniqueName> - fallback a la ruta
        # legacy CAPI (MachineKeys) si el tipo de clave no es CNG.
        $keyPath = $null
        if ($rsaKey -is [System.Security.Cryptography.RSACng]) {
            $uniqueName = $rsaKey.Key.UniqueName
            $keyPath = Join-Path $env:ProgramData "Microsoft\Crypto\Keys\$uniqueName"
        } elseif ($rsaKey -is [System.Security.Cryptography.RSACryptoServiceProvider]) {
            $uniqueName = $rsaKey.CspKeyContainerInfo.UniqueKeyContainerName
            $keyPath = Join-Path $env:ProgramData "Microsoft\Crypto\RSA\MachineKeys\$uniqueName"
        }

        if (-not $keyPath -or -not (Test-Path $keyPath)) {
            Write-Host "No se encontro el archivo de clave privada de 'CN=ParkosEnvProtection' en disco (ruta esperada: $keyPath) - ACL para '$Account' omitida." -ForegroundColor Yellow
            return
        }

        icacls $keyPath /grant "${Account}:(R)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "icacls no pudo otorgar acceso de lectura a '$Account' sobre la clave privada del certificado - el backup diario podria fallar al descifrar el .env." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "No se pudo ajustar la ACL de la clave privada de 'CN=ParkosEnvProtection' para '$Account': $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Cifra $Lines (KEY=VALUE) con CMS contra 'CN=ParkosEnvProtection' y escribe
# el resultado ASCII-armored (formato por defecto de Protect-CmsMessage,
# encabezado '-----BEGIN CMS-----') directamente en $EnvFilePath. Compartida
# por Write-RuntimeEnvFile (primera escritura del .env, mas arriba en este
# archivo) y Update-SucursalUuidInEnvFile (reescritura puntual de una sola
# linea) - unico lugar que valida la existencia del certificado ANTES de
# llamar Protect-CmsMessage, para no dejar que ese cmdlet falle con un error
# generico de "no se encontro el certificado" sin contexto de que hacer al
# respecto.
function Protect-ParkosEnvContent {
    param(
        [Parameter(Mandatory)][string]$EnvFilePath,
        [Parameter(Mandatory)][string[]]$Lines
    )

    $envCert = Get-ParkosEnvCert
    if (-not $envCert) {
        throw "No se encontro el certificado 'CN=ParkosEnvProtection' en Cert:\LocalMachine\My - corre Get-OrCreateParkosEnvCert antes de escribir el .env (el cifrado CMS del runtime env depende de el)."
    }

    $content = $Lines -join "`r`n"
    Protect-CmsMessage -To 'cn=ParkosEnvProtection' -Content $content -OutFile $EnvFilePath | Out-Null
}

# Lector retrocompatible de .env: detecta si el contenido crudo es CMS
# (encabezado ASCII-armored '-----BEGIN CMS-----') o texto plano y devuelve
# SIEMPRE lineas 'KEY=VALUE' ya decodificadas - nunca por extension de
# archivo ni por convencion de nombre, solo por el contenido real. Necesario
# para no romper ningun .env preexistente en texto plano (instalaciones
# hechas con una version anterior de este instalador, o cualquier fixture de
# test que siga escribiendo texto plano). Duplicado a proposito respecto de
# script:Import-ParkosEnvFile en Parkos.psm1 (mismo criterio ya aceptado en
# PRs anteriores: un .ps1 y un .psm1 no comparten funciones facilmente sin un
# modulo comun).
function Read-ParkosEnvLines {
    param([Parameter(Mandatory)][string]$EnvFilePath)

    if (-not (Test-Path $EnvFilePath)) {
        throw "No se encontro el archivo .env en $EnvFilePath."
    }

    $rawContent = Get-Content -Path $EnvFilePath -Raw
    if ($rawContent -match '^\s*-----BEGIN CMS-----') {
        $rawContent = Unprotect-CmsMessage -Path $EnvFilePath
    }

    return @($rawContent -split "`r?`n") | Where-Object { $_ -match '=' }
}

# ---------------------------------------------------------------------------
# Fase 27 (HU-F27.3/DEC-INST-40): gate de fortaleza/denylist del secreto JWT
# ---------------------------------------------------------------------------
# Denylist defensiva/heuristica de hashes SHA256 (mayusculas) de secretos de
# desarrollo/placeholder conocidos - deliberadamente NO exhaustiva, es
# defensa en profundidad, no la unica linea de defensa (esa es que
# New-JwtSigningKey SIEMPRE genera 64 bytes con RandomNumberGenerator, nunca
# texto legible). El primer valor es el UNICO secreto de desarrollo REAL
# encontrado en el backend (confirmado leyendo
# backend/packages/parkos_core/src/parkos_core/auth/tokens.py:26 -
# _DEFAULT_DEV_SECRET - reusado tal cual por
# backend/tests/unit/test_auth_me_not_found.py:33 como _DEV_SECRET); el
# resto son placeholders de texto genericos de uso comun en la industria
# (nunca usados de verdad en este repo), agregados solo como defensa
# adicional.
#
# Desviacion deliberada del plan original (documentada, no un olvido): el
# plan (HU-F27.3-T3) tambien pide una "allowlist firmada de secretos buenos"
# (KNOWN_GOOD_SECRETS.sha256.txt) - NO se implementa aca. Es logicamente
# incoherente para este secreto en particular: New-JwtSigningKey genera 64
# bytes aleatorios criptograficamente distintos en CADA instalacion, asi que
# ningun valor futuro va a "estar" nunca en una lista fija de valores
# pre-aprobados - una allowlist solo tiene sentido para un conjunto finito y
# estable de valores conocidos de antemano, que es exactamente lo que un
# secreto aleatorio NUNCA es. La denylist (valores conocidos MALOS) si tiene
# sentido porque esa lista es finita y estable ("estos valores nunca deberian
# aparecer"), al reves de la allowlist.
$script:KnownDevJwtSecretHashes = @(
    'C2E05E703F5E772BC07AEA71DE9E5BE850CB505156E8F0685149FCCB5C7DE715' # _DEFAULT_DEV_SECRET (backend real)
    'BD4B969EC202E3B67240D985AAA4262999C614E4E7A2CCB7FCD314853A8A1D7B' # 'dev-secret-change-me'
    '057BA03D6C44104863DC7361FE4578965D1887360F90A0895882E58A6248FC86' # 'changeme'
    'EF1767361F0CA8D71F7FB0EECC8253B88888DB4BF304DF4408C0B09C8207AB28' # 'insecure-default-key'
    '2CEAC6F36363C6246A64CCA805CD43CA7A01B14EB2FCC532CEEC3F60F2F7DF1C' # 'test-secret-key'
    '2BB80D537B1DA3E38BD30361AA855686BDE0EACD7162FEF6A25FE97BF527A25B' # 'secret'
)

# Gate de fortaleza del secreto JWT - longitud (>=32 bytes, igual que la
# validacion inline que reemplaza dentro de Test-PostInstallation) MAS hash
# SHA256 fuera de la denylist de arriba. Llamado tambien justo despues de
# New-JwtSigningKey en la etapa '1' (db) del instalador, como defensa en
# profundidad en el momento de generacion (en la practica nunca deberia
# fallar ahi, dado que el secreto es aleatorio) ademas de en la verificacion
# final de Test-PostInstallation.
function Test-JwtSecretGate {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path $Path)) {
        throw "No se encontro el archivo de secreto JWT en $Path."
    }

    $length = (Get-Item $Path).Length
    if ($length -lt 32) {
        throw 'Secreto JWT demasiado corto. Regenerar.'
    }

    $hash = (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    if ($script:KnownDevJwtSecretHashes -contains $hash) {
        throw 'Secreto JWT es uno de desarrollo conocido. Regenerar.'
    }

    return $true
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
# DEC-INST-17: no longer a fixed "[i/N]" linear counter - the menu (see
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

# ---------------------------------------------------------------------------
# DEC-INST-32 (PR5 de 11): fabrica compartida de las 9 definiciones de etapa
# ---------------------------------------------------------------------------
# Antes esto vivia INLINE dentro de Invoke-ParkosInstall (las 9 Action
# scriptblocks + las variables que usan: $pgInstallPath, $psqlPath,
# $secretsDir, $envFilePath, $nssmPath, etc.) - la cascada nueva
# -Unattended (Invoke-ParkosUnattendedCascade, mas abajo) necesitaba las
# MISMAS 9 etapas sin duplicar su cuerpo, asi que se extrajo a esta funcion.
# Ambos callers (el menu interactivo y la cascada) consumen la misma
# definicion devuelta aca - cero duplicacion de las 9 Action.
#
# Cada entrada agrega ahora una propiedad Rollback (scriptblock o $null,
# parte del manejo de errores/recuperacion de la cascada -Unattended - el
# menu interactivo la ignora por completo, DEC-INST-17 ya deja esa decision
# en manos del operador). Los Rollback son AUTONOMOS: recalculan lo que
# necesitan (p.ej. la etapa 7 vuelve a buscar el MSI) en vez de depender de
# variables locales efimeras de su propio Action - un scriptblock crea su
# propio scope hijo al ejecutarse, asi que una variable declarada dentro de
# Action no es visible desde su Rollback sibling aunque ambos esten
# definidos en el mismo lugar de este archivo.
#
# IMPORTANTE (scope): los Action/Rollback NO son closures. Un scriptblock
# literal se ejecuta (`& $Action`) en el scope de quien lo invoca, no en el
# de esta fabrica: los locals de abajo ($envFilePath, $pgInstallPath, los
# parametros, etc.) ya no existen cuando corre, y bajo Set-StrictMode
# -Version Latest eso tira "variable no establecida". Tampoco se usa
# .GetNewClosure(): captura por valor y ademas reasigna $script: al modulo
# dinamico, rompiendo el estado compartido entre etapas ($script:port,
# $script:roles, $script:StageStatus). En su lugar la fabrica publica todo en
# $script:StageContext y cada scriptblock arranca leyendolo a locals.
function Get-ParkosStageDefinitions {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$InstallPath,
        [Parameter(Mandatory)][string]$DataPath,
        [Parameter(Mandatory)][string]$SucursalUuid,
        [Parameter(Mandatory)][string]$CloudApiUrl
    )

    $pgInstallPath = 'C:\Program Files\PostgreSQL\16'
    $pgDataPath = Join-Path $DataPath 'pg-data'
    $psqlPath = Join-Path $pgInstallPath 'bin\psql.exe'
    $secretsDir = Join-Path $DataPath 'secrets'
    $jwtKeyPath = Join-Path $secretsDir 'jwt.key'
    $syncJwtPath = Join-Path $secretsDir 'sync-agent.jwt'  # written later by the pairing flow (Fase 29), not here
    $envFilePath = Join-Path $secretsDir '.env'
    $nssmPath = Join-Path $script:PayloadRoot 'nssm.exe'

    # Estado compartido entre etapas: bajo StrictMode leer una variable nunca
    # asignada tira, asi que se declara en $null (sin pisar uno ya seteado).
    foreach ($sharedName in 'port', 'apiPort', 'roles', 'PostgresInstallMethod') {
        if (-not (Get-Variable -Name $sharedName -Scope Script -ErrorAction SilentlyContinue)) {
            Set-Variable -Name $sharedName -Scope Script -Value $null
        }
    }

    # Fuente unica de verdad que leen los Action/Rollback (ver nota de scope).
    $script:StageContext = @{
        InstallPath   = $InstallPath
        DataPath      = $DataPath
        SucursalUuid  = $SucursalUuid
        CloudApiUrl   = $CloudApiUrl
        PgInstallPath = $pgInstallPath
        PgDataPath    = $pgDataPath
        PsqlPath      = $psqlPath
        SecretsDir    = $secretsDir
        JwtKeyPath    = $jwtKeyPath
        SyncJwtPath   = $syncJwtPath
        EnvFilePath   = $envFilePath
        NssmPath      = $nssmPath
    }

    $stages = [ordered]@{
        '0' = @{
            Key      = 'build'
            Name     = "Descargar ultima version de $SourceBranch y compilar artefactos"
            Action   = {
                Invoke-SourceUpdateAndBuild -Branch $SourceBranch
            }
            # De solo lectura sobre la maquina destino - este build corre en
            # la maquina del TECNICO (DEC-INST-20), nunca en el equipo final;
            # no hay nada que revertir aca.
            Rollback = $null
        }
        '1' = @{
            Key      = 'db'
            Name     = 'Instalar base de datos (Postgres + roles + pg_partman)'
            Action   = {
                $ctx = $script:StageContext
                $pgInstallPath = $ctx.PgInstallPath; $pgDataPath = $ctx.PgDataPath; $psqlPath = $ctx.PsqlPath
                $jwtKeyPath = $ctx.JwtKeyPath; $syncJwtPath = $ctx.SyncJwtPath; $envFilePath = $ctx.EnvFilePath
                $DataPath = $ctx.DataPath; $SucursalUuid = $ctx.SucursalUuid; $CloudApiUrl = $ctx.CloudApiUrl
                $script:port = Test-PostgresPorts
                $script:apiPort = Test-ApiPort
                $bootstrapPassword = New-ParkosDerivedPassword -SucursalUuid $SucursalUuid -Purpose 'postgres-bootstrap'
                $script:PostgresInstallMethod = Install-Postgres -PgInstallPath $pgInstallPath -PgDataPath $pgDataPath -Port $script:port -SuperuserPassword $bootstrapPassword
                $script:roles = Initialize-DatabaseRoles -PsqlPath $psqlPath -Port $script:port -BootstrapPassword $bootstrapPassword -SucursalUuid $SucursalUuid

                # svc-parkos tiene que existir ANTES de Get-OrCreateParkosEnvCert:
                # Grant-ParkosEnvCertKeyAccess (llamada desde ahi) le otorga acceso
                # de lectura a la clave privada del certificado CMS, y eso
                # requiere que la cuenta ya se pueda resolver - moverla mas tarde
                # (como estaba originalmente, justo antes de Register-
                # PgPartmanMaintenance) dejaba esa ACL fallando siempre en la
                # primera instalacion real de cualquier maquina.
                Ensure-ServiceAccount

                New-JwtSigningKey -Path $jwtKeyPath
                Test-JwtSecretGate -Path $jwtKeyPath | Out-Null
                Get-OrCreateParkosEnvCert -DataPath $DataPath | Out-Null
                Write-RuntimeEnvFile -EnvFilePath $envFilePath -AppPassword $script:roles.AppPassword -Port $script:port -ApiPort $script:apiPort `
                    -SucursalUuid $SucursalUuid -CloudApiUrl $CloudApiUrl -JwtKeyPath $jwtKeyPath -SyncJwtPath $syncJwtPath
                Set-MachineApiOrigin -Port $script:apiPort

                Install-PgPartman -PgInstallPath $pgInstallPath -PsqlPath $psqlPath -Port $script:port
                Register-PgPartmanMaintenance -PsqlPath $psqlPath -Port $script:port
            }
            # Desinstala Postgres con el MISMO mecanismo que lo instalo
            # ($script:PostgresInstallMethod, seteado por Install-Postgres en
            # el Action de arriba): winget uninstall si vino por winget,
            # borrar el directorio si vino por el ZIP de fallback. El data
            # directory se borra siempre (ambos metodos lo crean en el mismo
            # lugar).
            Rollback = {
                $pgInstallPath = $script:StageContext.PgInstallPath
                $pgDataPath = $script:StageContext.PgDataPath
                if ($script:PostgresInstallMethod -eq 'winget') {
                    winget uninstall --id PostgreSQL.PostgreSQL.16 --silent | Out-Host
                } elseif ($script:PostgresInstallMethod -eq 'zip') {
                    Remove-Item $pgInstallPath -Recurse -Force -ErrorAction SilentlyContinue
                }
                Remove-Item $pgDataPath -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        '2' = @{
            Key      = 'migrate'
            Name     = 'Ejecutar migraciones de base de datos'
            Action   = {
                if ($null -eq $script:roles) { throw 'Corre primero "Instalar base de datos" (opcion 1).' }
                Invoke-MigrationsAndSeed -Roles $script:roles -Port $script:port
            }
            # Intenta revertir el schema con el mismo migrate.exe (mismo
            # patron de invocacion que Invoke-MigrationsAndSeed) - si el
            # downgrade falla, NUNCA revienta el rollback completo de la
            # cascada: solo advierte (WARN) y continua (el rollback de una
            # etapa fallida no puede el mismo tirar una excepcion sin
            # manejar).
            Rollback = {
                $migrateDir = Join-Path $script:PayloadRoot 'services\migrate\migrate'
                $migrateExe = Join-Path $migrateDir 'migrate.exe'
                if (-not (Test-Path $migrateExe)) {
                    Write-Host '  [ROLLBACK] migrate.exe no encontrado; no se pudo intentar el downgrade.' -ForegroundColor Yellow
                    return
                }
                Push-Location $migrateDir
                try {
                    if ($null -ne $script:roles -and $null -ne $script:port) {
                        $env:DATABASE_URL = "postgresql://parkos:$($script:roles.SuperuserPassword)@127.0.0.1:$($script:port)/parkos"
                    }
                    & $migrateExe -c alembic.ini downgrade base
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "  [ROLLBACK] migrate.exe downgrade base fallo (exit $LASTEXITCODE) - continua sin revertir el schema." -ForegroundColor Yellow
                    }
                } catch {
                    Write-Host "  [ROLLBACK] downgrade de migraciones fallo: $($_.Exception.Message)" -ForegroundColor Yellow
                } finally {
                    Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
                    Pop-Location
                }
            }
        }
        '3' = @{
            Key      = 'sucursal'
            Name     = 'Confirmar UUID de sucursal (creada desde el panel admin)'
            Action   = {
                $envFilePath = $script:StageContext.EnvFilePath
                $SucursalUuid = $script:StageContext.SucursalUuid
                if ($script:StageStatus.db -ne [ParkosStageState]::Ok) { throw 'Corre primero "Instalar base de datos" (opcion 1).' }
                Update-SucursalUuidInEnvFile -EnvFilePath $envFilePath -SucursalUuid $SucursalUuid
                Write-Host "UUID de sucursal confirmado: $SucursalUuid" -ForegroundColor Cyan
                Write-Host 'La fila de esta sucursal vive en el panel admin y llega aca via el sync de job-sync-sucursal; este instalador nunca la crea.' -ForegroundColor Yellow
            }
            # Solo reescribe una linea del .env (DEC-INST-22 - ya no inserta
            # nada en prod.sucursal) - no hay nada real que revertir.
            Rollback = $null
        }
        '4' = @{
            Key      = 'seed'
            Name     = 'Sembrar catalogos iniciales (arranca api-sucursal temporalmente)'
            Action   = {
                $ctx = $script:StageContext
                $envFilePath = $ctx.EnvFilePath; $jwtKeyPath = $ctx.JwtKeyPath; $SucursalUuid = $ctx.SucursalUuid
                if ($script:StageStatus.migrate -ne [ParkosStageState]::Ok) { throw 'Corre primero "Ejecutar migraciones" (opcion 2).' }
                Invoke-CatalogSeed -EnvFilePath $envFilePath -Roles $script:roles -Port $script:port -JwtKeyPath $jwtKeyPath -SucursalUuid $SucursalUuid -ApiPort $script:apiPort
            }
            # Limitacion documentada (no un placeholder descuidado): un
            # rollback real de los catalogos sembrados necesitaria trackear
            # que filas EXACTAS creo esta corrida - ese tracking no existe
            # hoy. Un DELETE generico (p.ej. "borrar todo tipos_vehiculo")
            # es peligroso: podria borrar datos legitimos de una corrida
            # anterior. Se prefiere documentar la limitacion antes que
            # inventar un DELETE amplio.
            Rollback = $null
        }
        '5' = @{
            Key      = 'api'
            Name     = 'Instalar servicio api-sucursal (NSSM)'
            Action   = {
                $ctx = $script:StageContext
                $InstallPath = $ctx.InstallPath; $nssmPath = $ctx.NssmPath; $envFilePath = $ctx.EnvFilePath
                $apiExePath = Copy-ServiceBundle -Name 'api-sucursal' -InstallPath $InstallPath
                Install-ApiService -NssmPath $nssmPath -ExePath $apiExePath -EnvFilePath $envFilePath
                $apiPort = if ($null -ne $script:apiPort) { $script:apiPort } else { 8000 }  # default de Test-ApiPort/.env
                if (-not (Wait-ForApiHealth -Url "http://127.0.0.1:$apiPort/health")) {
                    throw 'ParkosApiSucursal no respondio /health a tiempo tras el registro NSSM.'
                }
            }
            Rollback = {
                $nssmPath = $script:StageContext.NssmPath
                & $nssmPath stop ParkosApiSucursal | Out-Null
                & $nssmPath remove ParkosApiSucursal confirm | Out-Null
            }
        }
        '6' = @{
            Key      = 'job'
            Name     = 'Instalar job de sincronizacion (NSSM)'
            Action   = {
                $ctx = $script:StageContext
                $InstallPath = $ctx.InstallPath; $DataPath = $ctx.DataPath
                $nssmPath = $ctx.NssmPath; $envFilePath = $ctx.EnvFilePath
                $jobExePath = Copy-ServiceBundle -Name 'job-sync-sucursal' -InstallPath $InstallPath
                Install-JobService -NssmPath $nssmPath -ExePath $jobExePath -EnvFilePath $envFilePath
                $syncLogPath = Join-Path $DataPath 'logs\job-sync.out.log'
                if (-not (Wait-ForSyncPollCycle -LogPath $syncLogPath)) {
                    throw 'ParkosJobSyncSucursal no mostro un ciclo de sondeo en el log a tiempo.'
                }
            }
            Rollback = {
                $nssmPath = $script:StageContext.NssmPath
                & $nssmPath stop ParkosJobSyncSucursal | Out-Null
                & $nssmPath remove ParkosJobSyncSucursal confirm | Out-Null
            }
        }
        '7' = @{
            Key      = 'electron'
            Name     = 'Instalar aplicacion de escritorio (web_sucursal)'
            Action   = {
                $appsDir = Join-Path $script:PayloadRoot 'apps'
                Assert-PayloadPath -Path $appsDir -What 'la carpeta apps con el MSI de web_sucursal'
                $msiPath = (Get-ChildItem $appsDir -Filter '*.msi' | Select-Object -First 1).FullName
                if (-not $msiPath) {
                    throw "Falta el MSI de web_sucursal en el payload ($appsDir). Ejecute la opcion 0 (descarga y compilacion del payload) o copie el MSI a esa carpeta y reintente."
                }
                Install-Electron -MsiPath $msiPath
            }
            # Recalcula $msiPath en vez de reusar el del Action de arriba -
            # ver el comentario general sobre Rollback autonomos.
            Rollback = {
                $msiPath = (Get-ChildItem (Join-Path $script:PayloadRoot 'apps') -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
                if ($msiPath) {
                    Start-Process msiexec.exe -ArgumentList "/x `"$msiPath`" /qn" -Wait | Out-Null
                }
            }
        }
        '8' = @{
            Key      = 'verify'
            Name     = 'Verificacion final (Postgres, JWT, servicios)'
            Action   = {
                $envFilePath = $script:StageContext.EnvFilePath
                $InstallPath = $script:StageContext.InstallPath
                # $script:port solo lo setea la etapa 1 en ESTA sesion; si el
                # operador corre la etapa 8 sola (o tras reabrir el menu) es
                # $null y [int]$null silenciaria a 0 - se recupera del .env.
                $verifyPort = $script:port
                if ($null -eq $verifyPort) { $verifyPort = Get-EnvFilePostgresPort -EnvFilePath $envFilePath }
                Test-PostInstallation -EnvFilePath $envFilePath -Port $verifyPort
                Install-ManagementModule -InstallPath $InstallPath
            }
            # De solo lectura - no hay nada que revertir.
            Rollback = $null
        }
    }

    return @{
        Stages = $stages
        Paths  = @{
            PgInstallPath = $pgInstallPath
            PgDataPath    = $pgDataPath
            PsqlPath      = $psqlPath
            SecretsDir    = $secretsDir
            JwtKeyPath    = $jwtKeyPath
            SyncJwtPath   = $syncJwtPath
            EnvFilePath   = $envFilePath
            NssmPath      = $nssmPath
        }
    }
}

# Mapa unico de dependencias entre etapas del menu: numero de etapa ->
# prerequisito(s) que deben estar [ParkosStageState]::Ok. Cada prerequisito es
# @{ Key; Number } (Key = clave en $script:StageStatus, Number = numero de
# etapa mostrado al operador); una etapa puede tener varios (array). Todos los
# prerequisitos tienen numero MENOR que la etapa, asi que el orden 0..8 de la
# cascada -Unattended (Invoke-ParkosUnattendedCascade) siempre los satisface.
function Get-ParkosStagePrerequisites {
    [CmdletBinding()]
    param()

    return @{
        '1' = @(@{ Key = 'build'; Number = '0' })
        '2' = @(@{ Key = 'db'; Number = '1' })
        '3' = @(@{ Key = 'db'; Number = '1' })
        '4' = @(@{ Key = 'migrate'; Number = '2' })
        '5' = @(@{ Key = 'seed'; Number = '4' })
        '6' = @(@{ Key = 'api'; Number = '5' })
        '7' = @(@{ Key = 'build'; Number = '0' })
        '8' = @(@{ Key = 'api'; Number = '5' }, @{ Key = 'job'; Number = '6' })
    }
}

# Artefactos que la etapa 0 (build) deja en el payload - mismo set que valida
# Invoke-SourceUpdateAndBuild al final. En una maquina de campo el payload
# llega ya compilado (la etapa 0 corre solo en la maquina del tecnico,
# DEC-INST-20), asi que "payload listo" equivale a la etapa 0 en Ok.
function Test-ParkosPayloadReady {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$PayloadRoot)

    $expectedExes = @(
        'services\api-sucursal\api-sucursal\api-sucursal.exe'
        'services\job-sync-sucursal\job-sync-sucursal\job-sync-sucursal.exe'
        'services\migrate\migrate\migrate.exe'
        'services\seed\seed\seed.exe'
        'services\doctor\doctor\doctor.exe'
    )
    foreach ($rel in $expectedExes) {
        if (-not (Test-Path (Join-Path $PayloadRoot $rel))) { return $false }
    }
    return $true
}

# Funcion pura: devuelve $null si la etapa $Number puede correr, o el texto de
# la razon ("requiere que N este OK" / "requiere que N y M esten OK",
# solo con los prerequisitos aun no Ok) si esta bloqueada. La comparten el
# render del menu y el dispatch, para que [BLOQ] y el rechazo nunca difieran.
function Get-ParkosStageBlockReason {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Number,
        [Parameter(Mandatory)]$StageStatus,
        [hashtable]$Prereqs = @{}
    )

    if (-not $Prereqs.ContainsKey($Number)) { return $null }

    $unmet = @(@($Prereqs[$Number]) | Where-Object { $StageStatus[$_.Key] -ne [ParkosStageState]::Ok })
    if ($unmet.Count -eq 0) { return $null }

    $numbers = @($unmet | ForEach-Object { $_.Number })
    if ($numbers.Count -eq 1) {
        return "requiere que $($numbers[0]) este OK"
    }
    return "requiere que $($numbers[0..($numbers.Count - 2)] -join ', ') y $($numbers[-1]) esten OK"
}

# DEC-INST-41 (PR10): helper puro (sin Write-Host adentro) que arma las
# lineas de texto del menu de etapas - separado del bucle principal de
# Invoke-ParkosInstall para poder verificar el TEXTO exacto de cada estado
# (Ok/Failed/RolledBack/NotRun-Running/Blocked) desde un test sin tener que
# mockear Write-Host ni parsear su salida por consola. $Prereqs viene de
# Get-ParkosStagePrerequisites (ver arriba).
function Get-ParkosStageMenuLines {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Stages,
        [Parameter(Mandatory)]$StageStatus,
        [hashtable]$Prereqs = @{}
    )

    $lines = @()
    foreach ($number in $Stages.Keys) {
        $stage = $Stages[$number]
        $state = $StageStatus[$stage.Key]
        $blockReason = Get-ParkosStageBlockReason -Number "$number" -StageStatus $StageStatus -Prereqs $Prereqs

        if ($null -ne $blockReason) {
            $tag = '[BLOQ]'
            $color = 'DarkYellow'
            $suffix = " ($blockReason)"
        } else {
            switch ($state) {
                ([ParkosStageState]::Ok)         { $tag = '[ OK ]'; $color = 'Green'; $suffix = '' }
                ([ParkosStageState]::Failed)     { $tag = '[FAIL]'; $color = 'Red'; $suffix = ' (re-ejecutable)' }
                ([ParkosStageState]::RolledBack) { $tag = '[ROLL]'; $color = 'Yellow'; $suffix = ' (rollback aplicado, re-ejecutable)' }
                ([ParkosStageState]::Blocked)    { $tag = '[BLOQ]'; $color = 'DarkYellow'; $suffix = '' }
                default                          { $tag = '[....]'; $color = 'White'; $suffix = '' }
            }
        }

        $lines += [PSCustomObject]@{
            Text  = ("  {0} {1}) {2}{3}" -f $tag, $number, $stage.Name, $suffix)
            Color = $color
        }
    }
    return $lines
}

function Invoke-ParkosInstall {
    [CmdletBinding()]
    param()

    Ensure-PowerShell7 -OriginalArgs $script:OriginalArgs
    Request-Elevation -OriginalArgs $script:OriginalArgs

    # La URL del cloud nunca se pregunta: -CloudApiUrl > PARKOS_CLOUD_API_URL
    # > http://localhost:8000.
    $CloudApiUrl = Resolve-ParkosCloudApiUrl -Explicit $CloudApiUrl

    if ($MasterKeyPath) { Import-ParkosMasterKey -SourcePath $MasterKeyPath }
    Write-Host '=== Parkos - pre-flight ===' -ForegroundColor Cyan
    # En el menu la clave maestra solo AVISA (sin -RequireMasterKey): la etapa
    # 0 corre sin ella; solo la etapa 1 la necesita.
    $preflightOk = Test-Preflight -InstallPath $InstallPath -DataPath $DataPath -CloudApiUrl $CloudApiUrl
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

    # Real operational value - never fabricated. Prompted here (once) if not
    # passed as a parameter; -Unattended requires it upfront.
    #
    # DEC-INST-22 (corrige DEC-INST-19): la sucursal se crea desde el panel
    # admin, no desde este instalador - Read-SucursalUuid solo valida forma
    # de UUID, nunca inserta nada en prod.sucursal (Fase 22b).
    $SucursalUuid = Read-SucursalUuid -Uuid $SucursalUuid

    Write-Host ''
    Write-Host '=== Parkos - instalacion (Fases 22-24) ===' -ForegroundColor Cyan

    $script:roles = $null
    $script:port = $null
    $script:PostgresInstallMethod = $null

    # DEC-INST-17: menu-driven instead of a single forced top-to-bottom pass.
    # Each stage keeps its own internal gate (Wait-ForApiHealth,
    # Wait-ForSyncPollCycle, etc. still throw exactly as before) - what
    # changes is that a thrown failure now returns to the menu (see the
    # dispatch loop below) instead of killing the whole process, and the
    # operator can re-run any single stage independently (e.g. re-run
    # migrations after an update without repeating Postgres install).
    $script:StageStatus = [ordered]@{
        build = [ParkosStageState]::NotRun
        db = [ParkosStageState]::NotRun; migrate = [ParkosStageState]::NotRun; sucursal = [ParkosStageState]::NotRun; seed = [ParkosStageState]::NotRun
        api = [ParkosStageState]::NotRun; job = [ParkosStageState]::NotRun; electron = [ParkosStageState]::NotRun; verify = [ParkosStageState]::NotRun
    }

    # DEC-INST-32 (PR5): las 9 definiciones de etapa (Action + Rollback)
    # viven en Get-ParkosStageDefinitions, compartida con la cascada
    # -Unattended (Invoke-ParkosUnattendedCascade) - el menu interactivo de
    # abajo ignora la propiedad Rollback por completo (DEC-INST-17 deja esa
    # decision en manos del operador, sin cambios aca).
    $definitions = Get-ParkosStageDefinitions -InstallPath $paths.InstallPath -DataPath $paths.DataPath `
        -SucursalUuid $SucursalUuid -CloudApiUrl $CloudApiUrl
    $stages = $definitions.Stages

    # Gates de dependencia entre etapas (ver Get-ParkosStagePrerequisites):
    # el menu muestra [BLOQ] y el dispatch rechaza la etapa bloqueada.
    $stagePrereqs = Get-ParkosStagePrerequisites

    # El estado de etapa es solo en memoria (no se persiste entre corridas).
    # En una maquina de campo el payload ya viene compilado y la etapa 0
    # nunca se corre aca (DEC-INST-20) - si los artefactos ya estan, la etapa
    # 0 cuenta como Ok para no bloquear 1 y 7 sin motivo.
    if (Test-ParkosPayloadReady -PayloadRoot $script:PayloadRoot) {
        $script:StageStatus['build'] = [ParkosStageState]::Ok
    }

    # DEC-INST-41 (PR10): el modulo Parkos (8 cmdlets, PR1..PR8) se importa
    # recien la PRIMERA vez que se usa alguna de las opciones A/R/U/V/X/D/M/C
    # - nunca al arrancar el script. SIEMPRE desde el PAYLOAD local
    # ($script:PayloadRoot), nunca asumiendo que ya esta instalado bajo
    # Program Files\PowerShell\Modules\Parkos\ (esa copia recien existe al
    # terminar la etapa 8 - durante una instalacion en curso o recien
    # completada puede no existir todavia).
    $moduleImported = $false
    $letterOptions = @('A', 'R', 'U', 'V', 'X', 'D', 'M', 'C')
    $exemptFromCompletionGate = @('A', 'D', 'X')

    while ($true) {
        Write-Host ''
        Write-Host '=== Parkos - menu de instalacion ===' -ForegroundColor Cyan
        foreach ($line in (Get-ParkosStageMenuLines -Stages $stages -StageStatus $script:StageStatus -Prereqs $stagePrereqs)) {
            Write-Host $line.Text -ForegroundColor $line.Color
        }
        Write-Host '  [    ] A) Diagnosticar estado actual (Get-ParkosHealth)' -ForegroundColor White
        Write-Host '  [    ] R) Reparar instalacion rota (Repair-ParkosInstall)' -ForegroundColor White
        Write-Host '  [    ] U) Actualizar stack completo (Invoke-ParkosUpdate)' -ForegroundColor White
        Write-Host '  [    ] V) Restaurar version anterior (Invoke-ParkosRestore)' -ForegroundColor White
        Write-Host '  [    ] X) Desinstalar Parkos (Uninstall-Parkos)' -ForegroundColor White
        Write-Host '  [    ] D) Exportar diagnostico para soporte (Export-ParkosDiagnostics)' -ForegroundColor White
        Write-Host '  [    ] M) Configurar backup automatico (Register-ParkosBackupTask)' -ForegroundColor White
        Write-Host '  [    ] C) Verificar recuperacion ante corte (Test-CrashRecovery)' -ForegroundColor White
        Write-Host '  [    ] Q) Salir' -ForegroundColor White
        $choice = Read-Host 'Elegi una opcion'

        if ($stages.Contains($choice)) {
            $stage = $stages[$choice]
            $blockReason = Get-ParkosStageBlockReason -Number $choice -StageStatus $script:StageStatus -Prereqs $stagePrereqs
            if ($null -ne $blockReason) {
                Write-Host "La etapa $choice ('$($stage.Name)') esta bloqueada ($blockReason)." -ForegroundColor Yellow
                continue
            }
            $script:StageStatus[$stage.Key] = [ParkosStageState]::Running
            try {
                Invoke-TuiStep -Name $stage.Name -Action $stage.Action
                $script:StageStatus[$stage.Key] = [ParkosStageState]::Ok
            } catch {
                $script:StageStatus[$stage.Key] = [ParkosStageState]::Failed
                Write-Host "La etapa '$($stage.Name)' fallo: $($_.Exception.Message)" -ForegroundColor Red
                Write-Host 'Podes reintentar esta opcion o resolver el problema antes de continuar.' -ForegroundColor Yellow
            }
            continue
        }

        $upperChoice = $choice.ToUpper()
        $installComplete = -not (@($script:StageStatus.Values) | Where-Object { $_ -ne [ParkosStageState]::Ok })

        if ($upperChoice -eq 'Q') {
            if (-not $installComplete) {
                $pendingKeys = @($script:StageStatus.Keys) | Where-Object { $script:StageStatus[$_] -ne [ParkosStageState]::Ok }
                $answer = Read-Host "La instalacion NO esta completa. Etapas pendientes: $($pendingKeys -join ', '). Salir de todos modos? (s/N)"
                if ($answer -eq 's') {
                    Write-Host 'Saliendo con la instalacion incompleta (confirmado por el operador).' -ForegroundColor Yellow
                    break
                }
                continue
            }
            break
        }

        if ($letterOptions -notcontains $upperChoice) {
            Write-Host 'Opcion invalida.' -ForegroundColor Red
            continue
        }

        if (-not $installComplete -and $exemptFromCompletionGate -notcontains $upperChoice) {
            $answer = Read-Host 'La instalacion no esta completa. Continuar? (s/N)'
            if ($answer -ne 's') {
                continue
            }
        }

        if (-not $moduleImported) {
            Import-Module (Join-Path $script:PayloadRoot 'management\Parkos.psd1') -Force -ErrorAction Stop
            $moduleImported = $true
        }

        $exitMenu = $false
        switch ($upperChoice) {
            'A' {
                try {
                    Get-ParkosHealth -Detailed
                } catch {
                    Write-Host "Get-ParkosHealth fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'R' {
                try {
                    $forceAnswer = Read-Host 'Forzar sin confirmacion interactiva? (s/N)'
                    if ($forceAnswer -eq 's') {
                        Repair-ParkosInstall -Force
                    } else {
                        Repair-ParkosInstall
                    }
                } catch {
                    Write-Host "Repair-ParkosInstall fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'U' {
                try {
                    $payloadPathInput = Read-Host 'Ruta del nuevo payload (-PayloadPath)'
                    if ([string]::IsNullOrWhiteSpace($payloadPathInput)) {
                        Write-Host 'Actualizacion cancelada: no se indico una ruta de payload.' -ForegroundColor Yellow
                    } else {
                        # Invoke-ParkosUpdate es `param()` - lee $PayloadPath
                        # del scope de script directamente (mismo mecanismo
                        # que $script:DataPath mas arriba), nunca
                        # -PayloadPath posicional/nombrado (esa firma no
                        # existe en la funcion real).
                        $script:PayloadPath = $payloadPathInput
                        $updateResult = Invoke-ParkosUpdate
                        if ($null -ne $updateResult -and $updateResult.ExitCode -ne 0) {
                            Write-Host "Invoke-ParkosUpdate fallo: $($updateResult.Detail)" -ForegroundColor Red
                        }
                    }
                } catch {
                    Write-Host "Invoke-ParkosUpdate fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'V' {
                try {
                    # DEC-INST-37: releases\ vive bajo InstallPath, NUNCA bajo
                    # DataPath (verificado contra Invoke-ParkosRestore, que
                    # define $releasesPath = Join-Path $InstallPath
                    # 'releases').
                    $releasesPath = Join-Path $paths.InstallPath 'releases'
                    $availableVersions = Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue |
                        Select-Object -ExpandProperty Name
                    if ($availableVersions) {
                        Write-Host 'Versiones disponibles:' -ForegroundColor Cyan
                        foreach ($v in $availableVersions) { Write-Host "  - $v" -ForegroundColor White }
                    } else {
                        Write-Host "No se encontraron versiones archivadas en $releasesPath." -ForegroundColor Yellow
                    }
                    $versionInput = Read-Host 'Version a restaurar'
                    if ([string]::IsNullOrWhiteSpace($versionInput)) {
                        Write-Host 'Restore cancelado: no se indico una version.' -ForegroundColor Yellow
                    } else {
                        # Invoke-ParkosRestore tambien es `param()` - mismo
                        # mecanismo que Invoke-ParkosUpdate arriba.
                        $script:Version = $versionInput
                        $restoreResult = Invoke-ParkosRestore
                        if ($null -ne $restoreResult -and $restoreResult.ExitCode -ne 0) {
                            Write-Host "Invoke-ParkosRestore fallo: $($restoreResult.Detail)" -ForegroundColor Red
                        }
                    }
                } catch {
                    Write-Host "Invoke-ParkosRestore fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'X' {
                try {
                    $purgeAnswer = Read-Host 'Purgar tambien los datos? (s/N)'
                    if ($purgeAnswer -eq 's') {
                        $result = Uninstall-Parkos -PurgeData
                    } else {
                        $result = Uninstall-Parkos
                    }
                    if ($null -ne $result -and $result.ExitCode -eq 0) {
                        Write-Host 'Parkos fue desinstalado. Cerrando el menu.' -ForegroundColor Green
                        $exitMenu = $true
                    }
                } catch {
                    Write-Host "Uninstall-Parkos fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'D' {
                try {
                    $diag = Export-ParkosDiagnostics
                    if ($null -ne $diag) {
                        Write-Host "Diagnostico exportado a: $($diag.OutputPath)" -ForegroundColor Green
                    }
                } catch {
                    Write-Host "Export-ParkosDiagnostics fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'M' {
                try {
                    $dailyAtInput = Read-Host 'Hora diaria del backup [03:00]'
                    if ([string]::IsNullOrWhiteSpace($dailyAtInput)) { $dailyAtInput = '03:00' }
                    Register-ParkosBackupTask -DailyAt $dailyAtInput
                } catch {
                    Write-Host "Register-ParkosBackupTask fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            'C' {
                try {
                    $confirmAnswer = Read-Host 'Esto reinicia Postgres a la fuerza. Continuar? (s/N)'
                    if ($confirmAnswer -eq 's') {
                        Test-CrashRecovery
                    } else {
                        Write-Host 'Cancelado por el operador.' -ForegroundColor Yellow
                    }
                } catch {
                    Write-Host "Test-CrashRecovery fallo: $($_.Exception.Message)" -ForegroundColor Red
                }
            }
        }
        if ($exitMenu) { break }
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

# ---------------------------------------------------------------------------
# Fase 30 - HU-F30.x (PR5 de 11): cascada automatica -Unattended
# ---------------------------------------------------------------------------
# DEC-INST-35: hasta este PR, -Unattended -Command Install seguia llamando a
# Invoke-ParkosInstall - que, aunque respeta $Unattended en Show-Eula/
# Read-InstallPaths/Read-SucursalUuid, SIEMPRE termina en el bucle del menu
# interactivo (`Read-Host 'Elegi una opcion'`), asi que en la practica
# quedaba colgado esperando input humano igual. Invoke-ParkosUnattendedCascade
# reemplaza ese bucle por una corrida automatica de las 9 etapas en orden
# (0->8), sin ningun Read-Host, con rollback automatico por etapa fallida
# (algo que el modo interactivo deliberadamente NO tiene - DEC-INST-17 deja
# esa decision en manos del operador quien SI esta presente ahi) y logging
# estructurado a archivo (Write-ParkosInstallerLog).

# Escribe cada linea de log a la vez por consola (Write-Host, igual que el
# resto del archivo) Y a un archivo de la corrida - un solo archivo por
# corrida completa (el timestamp se fija UNA vez, al arrancar
# Invoke-ParkosUnattendedCascade, nunca uno nuevo por linea). Formato:
# "[yyyy-MM-ddTHH:mm:ss] [Level] Message".
function Write-ParkosInstallerLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LogPath,
        [Parameter(Mandatory)][string]$Level,
        [Parameter(Mandatory)][string]$Message
    )

    $timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    $line = "[$timestamp] [$Level] $Message"

    Write-Host $line

    $logDir = Split-Path $LogPath
    if ($logDir -and -not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -Path $LogPath -Value $line
}

# DEC-INST-34: valida los parametros propios de la cascada -Unattended.
# Separada de Invoke-ParkosUnattendedCascade a proposito para poder probarla
# con `{ ... } | Should Throw` de forma aislada, sin tener que mockear toda
# la cascada solo para verificar un mensaje de validacion.
function Assert-ParkosCascadeParamsValid {
    [CmdletBinding()]
    param(
        [int[]]$SkipStage = @(),
        [int]$StopAfterStage = -1,
        [switch]$Force,
        [switch]$Unattended,
        [switch]$EulaAccepted,
        [string]$CloudApiUrl = ''
    )

    foreach ($stageNumber in $SkipStage) {
        if ($stageNumber -lt 0 -or $stageNumber -gt 8) {
            throw "-SkipStage contiene un valor invalido ($stageNumber) - cada etapa debe estar entre 0 y 8."
        }
    }
    if ($StopAfterStage -ne -1 -and ($StopAfterStage -lt 0 -or $StopAfterStage -gt 8)) {
        throw "-StopAfterStage invalido ($StopAfterStage) - debe ser -1 (correr todas las etapas) o un valor entre 0 y 8."
    }

    if ($SkipStage -contains 1) {
        if (-not $Force) {
            throw 'Saltar la etapa 1 (Postgres) puede dejar el resto de las etapas sin base de datos - si estas seguro, agrega -Force.'
        }
        Write-Host 'Advertencia: -SkipStage incluye la etapa 1 (Postgres) junto con -Force - el resto de la instalacion puede fallar sin una base de datos disponible.' -ForegroundColor Yellow
    }

    if ($Unattended) {
        if (-not $EulaAccepted) {
            throw '-Unattended requiere -EulaAccepted (ver Show-Eula).'
        }
        # -CloudApiUrl ya NO es obligatorio: si falta se toma de
        # PARKOS_CLOUD_API_URL o del default (Resolve-ParkosCloudApiUrl).
        # -SucursalUuid deliberadamente NO se revalida aca: Read-SucursalUuid
        # ya lanza su propia excepcion en modo -Unattended si viene vacio
        # (ver mas abajo, dentro de Invoke-ParkosUnattendedCascade) - duplicar
        # el mismo chequeo en dos lugares solo divergiria con el tiempo.
    }
}

# Texto para el operador (sin jerga) de cada etapa del flujo guiado.
function Get-ParkosStagePlainName {
    [CmdletBinding()]
    param([Parameter(Mandatory)][int]$Number)

    $names = @{
        0 = 'Preparando los archivos de instalacion'
        1 = 'Instalando la base de datos'
        2 = 'Preparando las tablas de la base de datos'
        3 = 'Configurando esta sucursal'
        4 = 'Cargando los datos iniciales'
        5 = 'Instalando el servicio principal de Parkos'
        6 = 'Instalando el servicio de sincronizacion'
        7 = 'Instalando la aplicacion de escritorio'
        8 = 'Verificando que todo funcione'
    }
    return $names[$Number]
}

# -Guided: flujo del operador de sucursal (default del instalador). Misma
# cascada que -Unattended pero (a) sin la etapa 0 salvo -IncludeBuild: el
# payload debe venir ya compilado, (b) la clave maestra es requisito duro del
# pre-flight, (c) el EULA se acepta con Enter y el UUID de la sucursal es lo
# unico que se tipea, y (d) el progreso se informa como "Paso N de M" en
# lenguaje llano. Nunca llama `exit` (ver el wrapper al final del archivo).
function Invoke-ParkosUnattendedCascade {
    [CmdletBinding()]
    param([switch]$Guided)

    $modeLabel = 'Unattended'
    if ($Guided) { $modeLabel = 'Guided' }

    $runTimestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logPath = Join-Path $DataPath "installer-runs\$runTimestamp.log"
    Write-ParkosInstallerLog -LogPath $logPath -Level 'INIT' -Message "parkos-installer iniciando (modo=$modeLabel)"

    # Etapas que NO corren en este flujo: las de -SkipStage y, en el flujo
    # guiado sin -IncludeBuild, la etapa 0 (el payload ya viene compilado).
    $skipBuildStage = ($Guided -and -not $IncludeBuild)

    try {
        $resolvedCloudApiUrl = Resolve-ParkosCloudApiUrl -Explicit $CloudApiUrl

        Assert-ParkosCascadeParamsValid -SkipStage $SkipStage -StopAfterStage $StopAfterStage -Force:$Force `
            -Unattended:$Unattended -EulaAccepted:$EulaAccepted -CloudApiUrl $resolvedCloudApiUrl

        # Antes de pedir nada: sin payload compilado no hay nada que instalar.
        if ($skipBuildStage -and -not (Test-ParkosPayloadReady -PayloadRoot $script:PayloadRoot)) {
            throw 'Este instalador no trae los programas ya preparados (falta el paquete de instalacion completo). No hay nada que usted pueda corregir aqui: pida un instalador completo al equipo de soporte.'
        }

        if ($MasterKeyPath) { Import-ParkosMasterKey -SourcePath $MasterKeyPath }
        if ($Guided) {
            Write-Host ''
            Write-Host 'Revisando que este equipo este listo para instalar Parkos...' -ForegroundColor Cyan
        } else {
            Write-Host '=== Parkos - pre-flight ===' -ForegroundColor Cyan
        }
        $preflightOk = Test-Preflight -InstallPath $InstallPath -DataPath $DataPath -CloudApiUrl $resolvedCloudApiUrl -RequireMasterKey:$Guided
        if (-not $preflightOk) {
            if ($Guided) {
                throw 'El equipo todavia no cumple los requisitos para instalar (revise las lineas [FALLO] de arriba). No se hizo ningun cambio en el equipo. Corrija lo indicado o pida ayuda al equipo de soporte.'
            }
            throw 'Pre-flight fallo - instalacion abortada, sin cambios en el sistema.'
        }

        Show-Eula | Out-Null

        $paths = Read-InstallPaths -DefaultInstallPath $InstallPath -DefaultDataPath $DataPath
        $script:DataPath = $paths.DataPath

        # DEC-INST-22: solo valida forma de UUID, nunca inserta nada en
        # prod.sucursal - lanza su propia excepcion si viene vacio en modo
        # -Unattended (ver comentario de Assert-ParkosCascadeParamsValid).
        $resolvedSucursalUuid = Read-SucursalUuid -Uuid $SucursalUuid

        $script:roles = $null
        $script:port = $null
        $script:PostgresInstallMethod = $null
        $script:StageStatus = [ordered]@{
            build = [ParkosStageState]::NotRun
            db = [ParkosStageState]::NotRun; migrate = [ParkosStageState]::NotRun; sucursal = [ParkosStageState]::NotRun; seed = [ParkosStageState]::NotRun
            api = [ParkosStageState]::NotRun; job = [ParkosStageState]::NotRun; electron = [ParkosStageState]::NotRun; verify = [ParkosStageState]::NotRun
        }
        # Payload compilado == etapa 0 en Ok (mismo criterio que el menu), lo
        # que mantiene coherentes los prerequisitos de las etapas 1 y 7.
        if ($skipBuildStage) { $script:StageStatus['build'] = [ParkosStageState]::Ok }

        $definitions = Get-ParkosStageDefinitions -InstallPath $paths.InstallPath -DataPath $paths.DataPath `
            -SucursalUuid $resolvedSucursalUuid -CloudApiUrl $resolvedCloudApiUrl
        $stages = $definitions.Stages
    } catch {
        $message = $_.Exception.Message
        Write-ParkosInstallerLog -LogPath $logPath -Level 'FAIL' -Message "Configuracion invalida: $message"
        Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message 'Exit code: 2'
        return [PSCustomObject]@{ ExitCode = 2; Detail = $message }
    }

    # Total de pasos que van a correr, para "Paso N de M".
    $stagesToRun = @(0..8 | Where-Object { ($SkipStage -notcontains $_) -and -not ($skipBuildStage -and $_ -eq 0) })
    $totalSteps = $stagesToRun.Count
    $stepNumber = 0

    foreach ($number in 0..8) {
        $stage = $stages["$number"]

        if ($SkipStage -contains $number) {
            Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message 'Omitida por -SkipStage'
        } elseif ($skipBuildStage -and $number -eq 0) {
            Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message 'Omitida (flujo guiado: el payload ya esta compilado; use -IncludeBuild para compilar)'
        } else {
            $stepNumber++
            if ($Guided) {
                Write-Host ''
                Write-Host "Paso $stepNumber de ${totalSteps}: $(Get-ParkosStagePlainName -Number $number)... (puede tardar unos minutos, no cierre esta ventana)" -ForegroundColor Cyan
            }
            Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message 'Iniciando'
            $script:StageStatus[$stage.Key] = [ParkosStageState]::Running
            $stageStart = Get-Date
            try {
                & $stage.Action
                $script:StageStatus[$stage.Key] = [ParkosStageState]::Ok
                $elapsedSeconds = [int]((Get-Date) - $stageStart).TotalSeconds
                Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message "[OK] $($stage.Name)"
                Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message "Estado: Ok (${elapsedSeconds}s)"
                if ($Guided) {
                    Write-Host "Paso $stepNumber de ${totalSteps} terminado." -ForegroundColor Green
                }
            } catch {
                $failureMessage = $_.Exception.Message
                $script:StageStatus[$stage.Key] = [ParkosStageState]::Failed
                Write-ParkosInstallerLog -LogPath $logPath -Level "STAGE $number" -Message "[FAIL] $failureMessage"

                $rolledBack = $false
                if ($null -ne $stage.Rollback) {
                    try {
                        & $stage.Rollback
                        $script:StageStatus[$stage.Key] = [ParkosStageState]::RolledBack
                        $rolledBack = $true
                        Write-ParkosInstallerLog -LogPath $logPath -Level 'ROLLBACK' -Message "[OK] $($stage.Name)"
                    } catch {
                        Write-ParkosInstallerLog -LogPath $logPath -Level 'ROLLBACK' -Message "[FAIL] $($_.Exception.Message)"
                    }
                }

                if ($Guided) {
                    Write-Host ''
                    Write-Host "No se pudo completar el paso $stepNumber de ${totalSteps} ($(Get-ParkosStagePlainName -Number $number))." -ForegroundColor Red
                    if ($rolledBack) {
                        Write-Host 'El instalador deshizo automaticamente los cambios de ese paso.' -ForegroundColor Yellow
                    } else {
                        Write-Host 'No fue posible deshacer automaticamente los cambios de ese paso: informelo al equipo de soporte.' -ForegroundColor Yellow
                    }
                    Write-Host "Motivo tecnico (para soporte): $failureMessage" -ForegroundColor Yellow
                    Write-Host "Registro de esta instalacion: $logPath" -ForegroundColor Yellow
                }

                Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message 'Exit code: 1'
                return [PSCustomObject]@{ ExitCode = 1; Detail = "Etapa $number ($($stage.Name)) fallo: $failureMessage"; LogPath = $logPath }
            }
        }

        if ($StopAfterStage -ne -1 -and $number -eq $StopAfterStage) {
            Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message "Detenido en etapa $number por -StopAfterStage"
            Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message 'Exit code: 0'
            return [PSCustomObject]@{ ExitCode = 0; Detail = "Detenido deliberadamente en etapa $number (-StopAfterStage)."; LogPath = $logPath }
        }
    }

    Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message 'Estado final: Ok (todas las etapas)'
    Write-ParkosInstallerLog -LogPath $logPath -Level 'INSTALL' -Message 'Exit code: 0'
    return [PSCustomObject]@{ ExitCode = 0; Detail = 'Instalacion completada (todas las etapas).'; LogPath = $logPath }
}

# Punto de entrada del flujo por defecto: el operador no elige opciones. Eleva
# a administrador y relanza en PowerShell 7 conservando los parametros, y
# corre la cascada guiada. Devuelve el resultado (nunca llama `exit`).
function Invoke-ParkosGuidedInstall {
    [CmdletBinding()]
    param()

    Ensure-PowerShell7 -OriginalArgs $script:OriginalArgs
    Request-Elevation -OriginalArgs $script:OriginalArgs

    Write-Host ''
    Write-Host '=== Instalacion de Parkos ===' -ForegroundColor Cyan
    Write-Host 'Este asistente instala Parkos en este equipo de forma automatica.' -ForegroundColor Cyan
    Write-Host 'Solo se le pedira un dato: el codigo (UUID) de la sucursal. No cierre esta ventana hasta que termine.' -ForegroundColor Cyan

    $result = Invoke-ParkosUnattendedCascade -Guided

    Write-Host ''
    if ($result.ExitCode -eq 0) {
        Write-Host 'Listo: Parkos quedo instalado y funcionando en este equipo.' -ForegroundColor Green
    } else {
        Write-Host 'La instalacion NO se completo.' -ForegroundColor Red
        $logHint = ''
        if ($result.PSObject.Properties['LogPath'] -and $result.LogPath) { $logHint = ", junto con el archivo de registro: $($result.LogPath)" }
        Write-Host "Que hacer: tome una foto o copie los mensajes de esta ventana y envielos al equipo de soporte$logHint." -ForegroundColor Yellow
        if ($result.Detail) { Write-Host "Detalle: $($result.Detail)" -ForegroundColor Yellow }
    }
    return $result
}

if ($MyInvocation.InvocationName -ne '.') {
    # Los parametros con nombre NO viajan en $args: se reconstruyen desde
    # $PSBoundParameters (switches, textos con espacios, arreglos como
    # -SkipStage 2,7) para que la elevacion/relanzo en PowerShell 7 conserve
    # exactamente lo que el operador paso (ver Get-ParkosRelaunchArgumentList).
    $script:OriginalArgs = @(ConvertTo-ParkosRelaunchArgs -BoundParameters $PSBoundParameters)
    switch ($Command) {
        'Install' {
            try {
                $installMode = Resolve-ParkosInstallMode -Menu:$Menu -Unattended:$Unattended
            } catch {
                Write-Host $_.Exception.Message -ForegroundColor Red
                exit 2
            }
            switch ($installMode) {
                'Unattended' {
                    # DEC-INST-35: nunca Invoke-ParkosInstall aca - ese es el
                    # menu interactivo (Read-Host), incompatible con
                    # -Unattended por diseno. La funcion de cascada nunca
                    # llama `exit` internamente (para poder testearla con
                    # Pester, que no intercepta un `exit` real del proceso
                    # host de forma confiable) - este wrapper delgado es el
                    # UNICO lugar del archivo que traduce su ExitCode a una
                    # salida real de proceso.
                    $cascadeResult = Invoke-ParkosUnattendedCascade
                    exit $cascadeResult.ExitCode
                }
                'Menu' { Invoke-ParkosInstall }
                'Guided' {
                    $guidedResult = Invoke-ParkosGuidedInstall
                    # La ventana elevada se cierra sola al terminar: se deja
                    # leer el resultado antes de cerrarla.
                    try { Read-Host 'Presione Enter para cerrar esta ventana' | Out-Null } catch { $null = $_ }
                    exit $guidedResult.ExitCode
                }
            }
        }
        'Update'  { $updateResult = Invoke-ParkosUpdate; exit $updateResult.ExitCode }
        'Restore' { $restoreResult = Invoke-ParkosRestore; exit $restoreResult.ExitCode }
    }
}
