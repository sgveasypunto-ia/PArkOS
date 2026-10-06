<#
.SYNOPSIS
    Empaqueta los artefactos del payload (zip + partes <= 90 MiB) en
    installer\payload\parts\ para versionarlos en git.

.DESCRIPTION
    GitHub rechaza archivos > 100 MB. Este script toma lo que hay "crudo" en
    installer\payload (MSI de PowerShell 7, nssm.exe, extension pg_partman,
    ZIP de Postgres si existe) y lo deja como partes + manifest
    (parts\payload-parts.json). Lo ya empaquetado y sin cambios no se reescribe.

    Servicios congelados y MSI de web_sucursal estan en la tabla pero SOLO se
    empaquetan con -Ids (se hace al publicar una version: la salida de
    PyInstaller no es reproducible y cada reempaquetado agrega su peso al
    historial de git para siempre).

.EXAMPLE
    pwsh -File installer\tools\Pack-ParkosPayload.ps1
    pwsh -File installer\tools\Pack-ParkosPayload.ps1 -Ids api-sucursal,migrate,web-sucursal-msi
#>
[CmdletBinding()]
param(
    [string]$PayloadRoot = '',
    [string[]]$Ids,
    [switch]$Force,
    [string]$PartsDir = '',
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'

# -File no convierte 'a,b' en lista: se acepta cualquiera de las dos formas.
$Ids = @($Ids | ForEach-Object { $_ -split ',' } | Where-Object { $_ })

$installerRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $PayloadRoot) { $PayloadRoot = Join-Path $installerRoot 'payload' }
if (-not $PartsDir) { $PartsDir = Join-Path $PayloadRoot 'parts' }
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $installerRoot '..')).Path }

. (Join-Path $installerRoot 'shared\ParkosPayloadParts.ps1')

$done = @(Invoke-ParkosPackPayload -PayloadRoot $PayloadRoot -PartsDir $PartsDir -RepoRoot $RepoRoot -Ids $Ids -Force:$Force -Logger { param($m) Write-Host "[pack] $m" })
$check = Test-ParkosPayloadParts -PartsDir $PartsDir
if (-not $check.Ok) { throw "Las partes quedaron inconsistentes: $($check.Problems -join '; ')" }
Write-Host "[pack] Listo: $($done.Count) artefacto(s) en $PartsDir ($($done -join ', '))."
