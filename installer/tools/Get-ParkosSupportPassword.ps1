<#
.SYNOPSIS
    Herramienta de SOPORTE: reconstruye las passwords de Postgres de una
    sucursal Parkos ya instalada, sin necesidad de acceder a esa maquina.

.DESCRIPTION
    Uso EXCLUSIVO del equipo de soporte, ejecutado en la maquina PROPIA de
    soporte - NUNCA en la maquina de un cliente/sucursal. Las 3 passwords de
    Postgres (postgres-bootstrap/parkos-superuser/parkos-app) no son
    aleatorias: se derivan deterministicamente via
    HMAC-SHA256(clave_maestra, "<uuid_sucursal>:<purpose>")
    (ver New-ParkosDerivedPassword en parkos-installer.ps1, DEC-INST-42).
    Esta herramienta reconstruye esas mismas passwords a partir de:
      (a) el UUID de la sucursal (NO es secreto - visible en el panel admin
          o en el ticket de soporte), y
      (b) la copia PROPIA de soporte de la clave maestra de la empresa
          (obtenida por un canal seguro de la compania - fuera del alcance
          de este script).

    La clave maestra NUNCA debe vivir en la maquina de un cliente ni en este
    repositorio: -MasterKeyPath es OBLIGATORIO y a proposito no tiene
    default, para no confundir "la clave que usa el build" con "la clave
    que usa soporte para consultar" - aunque conceptualmente sea el mismo
    archivo.

    Por defecto (sin -Reveal), cada password se copia al portapapeles y
    NUNCA se imprime en pantalla. Con -Purpose all se derivan las 3 UNA POR
    UNA: entre cada password (salvo la ultima) se pide confirmar con Enter
    antes de continuar, para que soporte la use/pegue antes de que la
    siguiente sobreescriba el portapapeles. La ultima no pide confirmacion
    porque no hay ninguna password siguiente que la vaya a pisar.

    Con -Reveal se imprime la tabla completa (Purpose | Password) en texto
    plano, SIN tocar el portapapeles, advirtiendo que queda visible en el
    historial de la consola.

    Ninguna password se escribe jamas a disco (ni siquiera temporalmente):
    todo vive en memoria y, cuando corresponde, en el portapapeles.

.PARAMETER SucursalUuid
    UUID de la sucursal (no secreto), tal como aparece en el panel admin o
    en el ticket de soporte.

.PARAMETER MasterKeyPath
    Ruta LOCAL (de la maquina de soporte) a la copia propia de la clave
    maestra de Parkos. Obligatorio, sin default: nunca debe apuntar al
    payload de un build ni a ninguna ruta versionada del repositorio.

.PARAMETER Purpose
    Cual de las 3 passwords derivar: 'postgres-bootstrap',
    'parkos-superuser', 'parkos-app', o 'all' (default) para las 3.

.PARAMETER Reveal
    Imprime las passwords en texto plano en vez de copiarlas al
    portapapeles. Usar solo si el portapapeles no esta disponible (ej.
    sesion remota headless/SSH) o si soporte necesita verlas directamente.

.EXAMPLE
    .\Get-ParkosSupportPassword.ps1 -SucursalUuid '3fa85f64-5717-4562-b3fc-2c963f66afa6' -MasterKeyPath 'D:\soporte\parkos-master.key'

    Deriva las 3 passwords y las copia al portapapeles una por una, pidiendo
    confirmacion entre cada una (salvo la ultima).

.EXAMPLE
    .\Get-ParkosSupportPassword.ps1 -SucursalUuid '3fa85f64-5717-4562-b3fc-2c963f66afa6' -MasterKeyPath 'D:\soporte\parkos-master.key' -Purpose parkos-app

    Deriva y copia SOLO la password de la app (parkos_app).

.EXAMPLE
    .\Get-ParkosSupportPassword.ps1 -SucursalUuid '3fa85f64-5717-4562-b3fc-2c963f66afa6' -MasterKeyPath 'D:\soporte\parkos-master.key' -Purpose parkos-superuser -Reveal

    Imprime la password de superuser en texto plano (sesion sin
    portapapeles disponible).
#>

param(
    [Parameter(Mandatory)][string]$SucursalUuid,
    [Parameter(Mandatory)][string]$MasterKeyPath,
    [ValidateSet('postgres-bootstrap', 'parkos-superuser', 'parkos-app', 'all')]
    [string]$Purpose = 'all',
    [switch]$Reveal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Mismo estilo de mensaje que Read-SucursalUuid en parkos-installer.ps1 (no
# se inventa una redaccion nueva para el mismo tipo de error).
$parsedUuid = [guid]::Empty
if (-not [guid]::TryParse($SucursalUuid, [ref]$parsedUuid)) {
    throw "El UUID de sucursal '$SucursalUuid' no tiene formato valido (UUIDv4 esperado). Verificalo en el panel admin antes de reintentar."
}

if (-not (Test-Path $MasterKeyPath)) {
    throw "No se encontro la clave maestra de Parkos en $MasterKeyPath - debe ser la copia propia de soporte, obtenida por un canal seguro de la compania (nunca debe vivir en una maquina de cliente/sucursal ni en este repositorio)."
}

# IMPORTANTE: se resuelven ANTES del dot-source de parkos-installer.ps1 de
# abajo. Ese archivo tiene su PROPIO param() con, entre otros, un
# -SucursalUuid (default ''). Dot-sourcing ejecuta ese param block en el
# scope de ESTE script (asi es como se reutiliza New-ParkosDerivedPassword
# sin duplicar su logica) - sin este paso previo, pisaria en silencio la
# variable $SucursalUuid de arriba con el default vacio del instalador.
# $Purpose/$Reveal no colisionan con ningun parametro del instalador hoy,
# pero se resuelven aca tambien por las dudas (defensivo ante cambios
# futuros en parkos-installer.ps1).
$resolvedSucursalUuid = $parsedUuid.ToString()
$resolvedPurpose = $Purpose
$resolvedReveal = $Reveal.IsPresent
$masterKeyBytes = [System.IO.File]::ReadAllBytes($MasterKeyPath)

# Dot-source (NO se importa como modulo ni se duplica la logica): reusa
# Get-ParkosMasterKeyBytes/New-ParkosDerivedPassword ya definidas alli
# (DEC-INST-42, HMAC-SHA256 deterministico). El guard de fin de archivo
# `if ($MyInvocation.InvocationName -ne '.') { ... }` evita que esto
# dispare el menu/flujo real del instalador.
. (Join-Path $PSScriptRoot '..\parkos-installer.ps1')

$purposesToProcess = if ($resolvedPurpose -eq 'all') {
    @('postgres-bootstrap', 'parkos-superuser', 'parkos-app')
} else {
    @($resolvedPurpose)
}

$results = foreach ($currentPurpose in $purposesToProcess) {
    [PSCustomObject]@{
        Purpose  = $currentPurpose
        Password = (New-ParkosDerivedPassword -SucursalUuid $resolvedSucursalUuid -Purpose $currentPurpose -MasterKeyBytes $masterKeyBytes)
    }
}

if ($resolvedReveal) {
    Write-Host 'La password queda visible en el historial de esta consola - preferi el modo sin -Reveal si podes.' -ForegroundColor Yellow
    # Deliberadamente NO se usa `| Out-Host`: eso escribe directo a la UI del
    # host y NUNCA pasa por el pipeline de salida (ni un caller, ni un test
    # que capture output con Out-String lo veria). Dejar que Format-Table
    # fluya por el pipeline normal se ve identico en una consola interactiva
    # y ademas queda capturable.
    $results | Format-Table -Property Purpose, Password -AutoSize
    return
}

# Copia al portapapeles UNA password a la vez. Con -Purpose all esto copia
# las 3 en secuencia; entre cada par (i, i+1) se pide confirmar con Enter
# para que soporte la use antes de que la siguiente pise el portapapeles.
# Regla exacta (debe coincidir con el test que la verifica): confirmacion
# DESPUES de la password 1 y DESPUES de la password 2, pero NUNCA despues
# de la ULTIMA - no hay ninguna password siguiente que la vaya a
# sobreescribir, asi que pedir Enter ahi no protegeria nada.
for ($i = 0; $i -lt $results.Count; $i++) {
    $entry = $results[$i]
    try {
        Set-Clipboard -Value $entry.Password
        Write-Host "[$($entry.Purpose)] copiado al portapapeles (no se muestra en pantalla)"
    } catch {
        Write-Host "No se pudo copiar [$($entry.Purpose)] al portapapeles ($($_.Exception.Message)). Reintenta con -Reveal para verla en texto plano." -ForegroundColor Red
    }

    $isLast = ($i -eq ($results.Count - 1))
    if (-not $isLast) {
        Read-Host 'Presiona Enter cuando ya la copiaste/usaste, para continuar con la siguiente' | Out-Null
    }
}
