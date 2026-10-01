<#
.SYNOPSIS
    Ciclo de vida E2E completo del instalador (PR11/11, ultimo del plan de
    cierre de gaps): instalacion limpia -Unattended -> chequeo de salud ->
    -Command Update -> -Command Restore -> chequeo de salud otra vez.

.DESCRIPTION
    Contraparte de integracion real de installer/tests/ParkosInstaller.
    Unattended.Tests.ps1 y ParkosInstaller.Update.Tests.ps1 (DEC-INST-24..35),
    que mockean Get-ParkosStageDefinitions/Stop-Service/Start-Service/etc. -
    este script NO mockea nada: ejecuta parkos-installer.ps1 de verdad, tres
    veces, como procesos hijos separados (`pwsh -File`, nunca dot-source ni
    `&` en este mismo proceso - ver la nota dentro de Invoke-CleanInstall
    sobre por que eso es obligatorio, no un detalle de estilo).

    Standalone e imperativo, NO es un test de Pester y NO importa el modulo
    Parkos ni depende de Pester - pensado para que un ingeniero lo corra a
    mano en una VM real (`pwsh -File installer/tests/e2e/
    Invoke-UnattendedE2E.ps1`) para reproducir un fallo de CI sin tener que
    leer el YAML del workflow que lo invoca
    (.github/workflows/e2e-unattended-vm.yml).

    ADVERTENCIA: instala Postgres real, registra servicios NSSM reales y crea
    una cuenta local real (svc-parkos) en la maquina donde corre. Disenado
    para una VM Windows desechable (windows-2022 en CI), NUNCA para una
    maquina de desarrollo real.

    HONESTIDAD sobre "Update -> Restore" (pedido explicito de esta tarea):
    la VM de CI es SIEMPRE la primera instalacion, asi que releases\ esta
    vacio - no existe una release N-1 real publicada a la cual revertir. En
    vez de fabricar un escenario falso, Invoke-UpdateAndRestoreCycle apunta
    -Command Update al MISMO payload recien compilado por build-release.ps1
    (el mismo que uso Invoke-CleanInstall), "como si" fuera una version
    nueva. El comportamiento REAL de Invoke-ParkosUpdate (paso REPLACE)
    archiva la version SALIENTE (la que -Command Install acaba de dejar
    corriendo) bajo $InstallPath\releases\<version-saliente>\ ANTES de
    copiar el payload nuevo encima - esa es la version que despues se
    revierte con -Command Restore. No es literalmente "restaurar una
    release N-1 publicada", pero SI ejercita de punta a punta el mecanismo
    real de rollback Update -> Restore (el mismo que protege a un cliente
    real cuando una actualizacion sale mal en produccion), que es la
    intencion real de este PR.

    HALLAZGO IMPORTANTE (verificado leyendo parkos-installer.ps1 completo, no
    asumido): el dispatcher final del archivo (`if ($MyInvocation.
    InvocationName -ne '.') { switch ($Command) {...} }`) SOLO traduce un
    resultado a un exit code de proceso real para 'Install' en modo
    -Unattended (`exit $cascadeResult.ExitCode`) - es la UNICA linea del
    archivo que hace eso. Para 'Update' y 'Restore' el dispatcher llama
    Invoke-ParkosUpdate/Invoke-ParkosRestore y DESCARTA el objeto
    [PSCustomObject]@{ExitCode=...} que devuelven (confirmado contra
    installer/tests/ParkosInstaller.Update.Tests.ps1, que SI lee ese objeto
    directamente porque dot-sourcea la funcion, nunca corriendo el proceso
    completo). Un fallo que lanza una excepcion real (`throw`, con
    $ErrorActionPreference='Stop' sin captura arriba) SI sigue produciendo un
    proceso con exit code distinto de cero, pero el "fallo suave" que sus
    propios tests documentan (ej.: migrate.exe falla, el rollback tier-2 SI
    corre con exito, y la funcion hace `return` con ExitCode=1 en vez de
    `throw`) NO se propaga hoy a un exit code de proceso real para -Command
    Update/Restore. Por eso Invoke-UpdateAndRestoreCycle nunca confia SOLO en
    $LASTEXITCODE para esos dos comandos: tambien verifica el estado real en
    disco (que releases\ tenga una version nueva archivada) y llama
    Test-HealthEndpoint despues de cada uno como señal de verdad adicional.

.PARAMETER SucursalUuid
    UUID de sucursal para -SucursalUuid. Por defecto genera uno nuevo (esta
    VM es desechable, cualquier UUID con formato valido sirve para el smoke
    test).

.PARAMETER CloudApiUrl
    URL para -CloudApiUrl. Por defecto un host .invalid (RFC 2606) - esta VM
    nunca necesita hablar con un backend cloud real para este smoke test.

.PARAMETER VersionTag
    Tag opcional, puramente informativo (se imprime en el resumen final).
    Este script NUNCA reinstala desde una release publicada con ese tag -
    ver la nota de honestidad arriba.

.PARAMETER InstallPath
    Debe coincidir con el default de parkos-installer.ps1 salvo que se pruebe
    deliberadamente una ruta distinta.

.PARAMETER DataPath
    Idem InstallPath.
#>

[CmdletBinding()]
param(
    [string]$SucursalUuid = ([guid]::NewGuid().ToString()),
    [string]$CloudApiUrl = 'https://parkos-e2e.invalid',
    [string]$VersionTag = '',
    [string]$InstallPath = 'C:\Program Files\Parkos',
    [string]$DataPath = 'C:\ProgramData\Parkos'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# installer/tests/e2e/ -> ..\.. = installer/ (2 niveles, NO 3 - verificado
# contando los segmentos de $PSScriptRoot antes de escribir esto).
$script:InstallerRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:InstallerScript = Join-Path $script:InstallerRoot 'parkos-installer.ps1'
$script:PayloadPath = Join-Path $script:InstallerRoot 'payload'

if (-not (Test-Path $script:InstallerScript)) {
    throw "No se encontro parkos-installer.ps1 en $script:InstallerScript - ¿se movio el script o cambio la estructura de carpetas de installer/?"
}

# Degrada con gracia fuera de GitHub Actions (pedido explicito: este script
# debe poder correr a mano en una VM real sin depender de GITHUB_*) - el
# agrupado de logs `::group::`/`::endgroup::` es puramente cosmetico.
function Write-E2EGroupStart {
    param([Parameter(Mandatory)][string]$Name)
    if ($env:GITHUB_ACTIONS -eq 'true') {
        Write-Host "::group::$Name"
    } else {
        Write-Host ''
        Write-Host ('=' * 70) -ForegroundColor Cyan
        Write-Host "  $Name" -ForegroundColor Cyan
        Write-Host ('=' * 70) -ForegroundColor Cyan
    }
}

function Write-E2EGroupEnd {
    if ($env:GITHUB_ACTIONS -eq 'true') {
        Write-Host '::endgroup::'
    }
}

function Write-E2ELog {
    param([string]$Message)
    Write-Host "    $Message"
}

# Invoca parkos-installer.ps1 SIEMPRE como un proceso hijo separado
# (`pwsh -File`), nunca dot-sourced ni via `&` dentro de este mismo proceso.
# Motivo (no es un detalle de estilo, es obligatorio para que el script no
# se auto-mate): -Command Install -Unattended termina en `exit
# $cascadeResult.ExitCode` DENTRO de parkos-installer.ps1 (ver el hallazgo en
# la cabecera de este archivo). `exit` en PowerShell termina el PROCESO
# completo, no solo el scope del script invocado - si se corriera in-process
# aca, ese `exit` matariaa este mismo orquestador antes de llegar al chequeo
# de salud, al Update o al Restore. Como proceso hijo separado, solo el hijo
# termina y este script sigue vivo para leer $LASTEXITCODE y continuar.
function Invoke-ParkosInstallerProcess {
    param([Parameter(Mandatory)][string[]]$CommandArgs)

    & pwsh -NoLogo -NoProfile -File $script:InstallerScript @CommandArgs
    return $LASTEXITCODE
}

function Invoke-CleanInstall {
    [CmdletBinding()]
    param()

    Write-E2ELog "SucursalUuid=$SucursalUuid CloudApiUrl=$CloudApiUrl InstallPath=$InstallPath DataPath=$DataPath"

    $installArgs = @(
        '-Command', 'Install',
        '-Unattended',
        '-EulaAccepted',
        '-SucursalUuid', $SucursalUuid,
        '-CloudApiUrl', $CloudApiUrl,
        '-InstallPath', $InstallPath,
        '-DataPath', $DataPath
    )

    $exitCode = Invoke-ParkosInstallerProcess -CommandArgs $installArgs

    # DEC-INST-32..35: Invoke-ParkosUnattendedCascade documenta sus exit
    # codes en la cabecera de parkos-installer.ps1: 0 (completo, o una etapa
    # deliberadamente omitida/cortada con -SkipStage/-StopAfterStage - NO
    # usados aca, corremos las 9 etapas), 1 (una etapa fallo, rollback
    # intentado) y 2 (configuracion o pre-flight invalidos).
    if ($exitCode -ne 0) {
        $meaning = switch ($exitCode) {
            1 { 'una etapa de la cascada fallo y se intento su rollback - ver installer-runs\*.log y logs\* en el artifact subido por el workflow' }
            2 { 'configuracion o pre-flight invalidos (revisar -SucursalUuid/-CloudApiUrl/-EulaAccepted, o que el runner corra como Administrator)' }
            default { 'codigo de salida no documentado por Invoke-ParkosUnattendedCascade' }
        }
        throw "Invoke-CleanInstall: -Command Install -Unattended salio con codigo $exitCode ($meaning)."
    }
    Write-E2ELog 'ExitCode 0 - cascada completa.'
}

function Test-HealthEndpoint {
    [CmdletBinding()]
    param(
        [int]$TimeoutSeconds = 60,
        [int]$RetryIntervalSeconds = 2
    )

    # PARKOS_API_ORIGIN se escribe a nivel Machine (Set-MachineApiOrigin en
    # parkos-installer.ps1, via [Environment]::SetEnvironmentVariable(...,
    # 'Machine')) - un cambio de registro que NO se propaga automaticamente
    # al bloque de entorno de un proceso pwsh YA en marcha. Cada paso de
    # GitHub Actions (y este propio script, corriendo en su propio proceso
    # pwsh) hereda su entorno del proceso que lo lanzo, iniciado ANTES de que
    # -Command Install corriera - por eso se lee con el scope 'Machine'
    # explicito (relee el registro en vivo) en vez de confiar en
    # $env:PARKOS_API_ORIGIN sin mas. El puerto NUNCA se hardcodea a 8000
    # (DEC-INST-18: Test-ApiPort elige uno libre en cada instalacion).
    $origin = [Environment]::GetEnvironmentVariable('PARKOS_API_ORIGIN', 'Machine')
    if ([string]::IsNullOrWhiteSpace($origin)) {
        # Fallback defensivo por si este proceso heredara la variable de
        # sesion por alguna razon (no deberia pasar en el flujo normal de CI).
        $origin = $env:PARKOS_API_ORIGIN
    }
    if ([string]::IsNullOrWhiteSpace($origin)) {
        throw 'Test-HealthEndpoint: no se pudo leer PARKOS_API_ORIGIN (ni Machine ni sesion) - la instalacion no la seteo, o Test-ApiPort/Set-MachineApiOrigin cambiaron de contrato.'
    }

    # Confirmado en parkos-installer.ps1 (RESTART, SMOKE TEST y
    # Wait-ForApiHealth): el path real es /health, no /healthz.
    $healthUrl = "$origin/health"
    Write-E2ELog "URL de salud resuelta: $healthUrl"

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = 'sin intentos'
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                Write-E2ELog "Respondio 200 OK."
                return
            }
            $lastError = "respondio $($resp.StatusCode), se esperaba 200"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds $RetryIntervalSeconds
    }
    throw "Test-HealthEndpoint: $healthUrl no respondio 200 dentro de $TimeoutSeconds s. Ultimo error: $lastError"
}

function Invoke-UpdateAndRestoreCycle {
    [CmdletBinding()]
    param()

    # Ver la nota de HONESTIDAD y el HALLAZGO IMPORTANTE en la cabecera del
    # archivo - resumen: -Command Update apunta al mismo payload recien
    # compilado, y la version a restaurar se DESCUBRE listando releases\
    # despues (nunca se adivina/precalcula, porque Invoke-ParkosUpdate arma
    # el nombre "unknown-<timestamp-de-esa-corrida>" en caliente cuando
    # $DataPath\current-version.txt todavia no existe, que es exactamente
    # nuestro caso: primera actualizacion de esta VM).
    $releasesPath = Join-Path $InstallPath 'releases'
    $releasesBefore = @()
    if (Test-Path $releasesPath) {
        $releasesBefore = @(Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    }

    Write-E2ELog "-Command Update -PayloadPath $script:PayloadPath -Force"
    # -Force omite SOLO el pre-check de salud (Get-ParkosHealth) - el backup
    # (pg_dump) y la verificacion de manifest/hash del payload NUNCA se
    # omiten (confirmado leyendo Invoke-ParkosUpdate). Se pasa aca porque el
    # modulo de gestion Parkos recien se instalo en esta misma corrida
    # (Stage 8 de la cascada) y no hay necesidad de ejercitar ese pre-check
    # en un smoke test que ya paso Test-HealthEndpoint explicitamente arriba.
    $updateArgs = @(
        '-Command', 'Update',
        '-PayloadPath', $script:PayloadPath,
        '-Force'
    )
    $updateExitCode = Invoke-ParkosInstallerProcess -CommandArgs $updateArgs
    if ($updateExitCode -ne 0) {
        throw "Invoke-UpdateAndRestoreCycle: -Command Update salio con codigo $updateExitCode (excepcion no capturada por el proceso - ver installer-runs/logs)."
    }

    if (-not (Test-Path $releasesPath)) {
        throw "Invoke-UpdateAndRestoreCycle: -Command Update termino con exit 0 pero $releasesPath no existe - REPLACE no archivo ninguna version saliente."
    }
    $releasesAfter = @(Get-ChildItem -Path $releasesPath -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $newReleases = @($releasesAfter | Where-Object { $releasesBefore -notcontains $_ })
    if ($newReleases.Count -eq 0) {
        throw "Invoke-UpdateAndRestoreCycle: -Command Update no archivo ninguna version nueva bajo $releasesPath (se esperaba exactamente 1, primera actualizacion de esta VM) - el exit code 0 no es suficiente señal de exito (ver HALLAZGO en la cabecera del archivo)."
    }
    if ($newReleases.Count -gt 1) {
        Write-E2ELog "Advertencia: se archivaron $($newReleases.Count) versiones nuevas, se esperaba 1. Usando la mas reciente (orden lexicografico = cronologico, formato yyyyMMdd-HHmmss)."
    }
    $archivedVersion = @($newReleases | Sort-Object -Descending)[0]
    Write-E2ELog "Version saliente archivada por Update: '$archivedVersion'."

    Write-E2ELog 'Verificando salud tras el Update...'
    Test-HealthEndpoint

    Write-E2ELog "-Command Restore -Version $archivedVersion -Unattended -UnattendedRestoreConfirmed"
    $restoreArgs = @(
        '-Command', 'Restore',
        '-Version', $archivedVersion,
        '-Unattended',
        '-UnattendedRestoreConfirmed'
    )
    $restoreExitCode = Invoke-ParkosInstallerProcess -CommandArgs $restoreArgs
    if ($restoreExitCode -ne 0) {
        throw "Invoke-UpdateAndRestoreCycle: -Command Restore -Version $archivedVersion salio con codigo $restoreExitCode (excepcion no capturada por el proceso - ver installer-runs/logs)."
    }

    return $archivedVersion
}

# ---------------------------------------------------------------------------
# Orquestacion: 4 pasos nombrados, secuenciales (cada uno depende del
# anterior) - un fallo detiene los pasos restantes (se marcan SKIPPED) en vez
# de seguir corriendo pasos que asumen un estado que nunca se alcanzo. Mismo
# patron de resumen ordenado que build-release.ps1's Invoke-Stage/$results.
# ---------------------------------------------------------------------------

$script:ArchivedVersion = $null

$steps = [ordered]@{
    'Clean install (-Command Install -Unattended)' = { Invoke-CleanInstall }
    'Health check (post-install)'                  = { Test-HealthEndpoint }
    'Update + Restore rollback cycle'              = { $script:ArchivedVersion = Invoke-UpdateAndRestoreCycle }
    'Health check (post-restore)'                  = { Test-HealthEndpoint }
}

$summary = [ordered]@{}
$failed = $false

foreach ($stepName in $steps.Keys) {
    if ($failed) {
        $summary[$stepName] = 'SKIPPED (paso previo fallo)'
        continue
    }

    Write-E2EGroupStart $stepName
    try {
        & $steps[$stepName]
        $summary[$stepName] = 'OK'
    } catch {
        $summary[$stepName] = "FAILED: $($_.Exception.Message)"
        $failed = $true
        Write-Host "[FAIL] $stepName : $($_.Exception.Message)" -ForegroundColor Red
    } finally {
        Write-E2EGroupEnd
    }
}

Write-Host ''
Write-Host ('=' * 70)
Write-Host '  Resumen Invoke-UnattendedE2E'
Write-Host ('=' * 70)
foreach ($entry in $summary.GetEnumerator()) {
    Write-Host ("  {0,-55} {1}" -f $entry.Key, $entry.Value)
}
if ($script:ArchivedVersion) {
    Write-Host "  Version archivada/restaurada durante el ciclo: $script:ArchivedVersion"
}
if ($VersionTag) {
    Write-Host "  version_tag (informativo - NO una release publicada real): $VersionTag"
}
Write-Host ('=' * 70)

if ($failed) {
    Write-Host 'RESULTADO: FALLO' -ForegroundColor Red
    exit 1
}
Write-Host 'RESULTADO: OK' -ForegroundColor Green
exit 0
