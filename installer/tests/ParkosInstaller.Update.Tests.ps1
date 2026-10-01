# Tests de installer/parkos-installer.ps1's -Command Update (Invoke-ParkosUpdate),
# PR4a de 11 del plan de cierre de gaps (DEC-INST-24..27). A diferencia de
# installer/tests/Parkos.Module.Tests.ps1 (que IMPORTA el modulo Parkos con
# Import-Module), este archivo DOT-SOURCEA parkos-installer.ps1 directamente -
# es el primer archivo de tests que lo hace. Verificado empiricamente antes
# de escribir esto: $MyInvocation.InvocationName -eq '.' cuando el script se
# dot-sourcea, asi que el guard final del archivo (`if ($MyInvocation.
# InvocationName -ne '.') { ... Invoke-ParkosInstall/Update ... }`) NUNCA
# dispara el auto-run - dot-sourcear es seguro. Como las funciones quedan en
# el scope del propio script de test (no en un modulo), los Mock/
# Assert-MockCalled de abajo NO llevan -ModuleName.
#
# HALLAZGO IMPORTANTE (verificado empiricamente, no asumido): el Pester
# 3.4.0 que trae este Windows (`C:\Program Files\WindowsPowerShell\Modules\
# Pester\3.4.0`) tiene un defecto real en `Should Throw`/`Should Not Throw`
# SIN argumento de mensaje - `Get-DoMessagesMatch` en PesterThrow.ps1 hace
# `$ActualExceptionMessage.Contains($expected)` con `$expected = $null`
# cuando no se pasa mensaje, y `"...".Contains($null)` siempre devuelve
# $false en .NET - o sea, `Should Throw` (sin mensaje) SIEMPRE reporta
# fallo y `Should Not Throw` (sin mensaje) SIEMPRE reporta exito,
# independientemente de si realmente se lanzo una excepcion. Confirmado con
# un repro minimo fuera de este archivo antes de escribir los tests de
# abajo. Por eso TODOS los `Should Throw` de este archivo llevan un
# substring de mensaje esperado (unico caso donde el matching de
# PesterThrow.ps1 funciona de verdad) - nunca `Should Throw` a secas. Esto
# es una limitacion del entorno, no del codigo bajo prueba; no se toco
# installer/tests/Parkos.Module.Tests.ps1 (usa `Should Not Throw` sin
# mensaje en varios lugares, pre-existente, fuera de alcance de este PR).
#
# Cobertura real (4 tests minimos exigidos) vs. documentado como no cubierto
# por tiempo - ver el reporte final, resumen aca tambien:
#   - Cubierto: orden PRE-CHECK->BACKUP->STOP->VERIFY BINARIES, tier-1 vs.
#     tier-2 de rollback, -WhatIf.
#   - NO cubierto (documentado, no exigido por los 4 minimos): RESTART/SMOKE
#     TEST fallando (mismo patron tier-2 que MIGRATE, ya probado una vez),
#     -RollbackOnly, el pre-check de salud (Get-ParkosHealth) sin -Force, y
#     el camino SUCCESS completo (Event Log + escritura de
#     current-version.txt) - ninguno de los 4 tests exigidos llega a
#     SUCCESS por diseno (cada uno corta el flujo antes).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

function New-UpdateTestFixture {
    param([Parameter(Mandatory)][string]$Root)

    $installPath = Join-Path $Root 'Parkos'
    $dataPath = Join-Path $Root 'ParkosData'
    $payloadPath = Join-Path $Root 'payload'

    New-Item -ItemType Directory -Force -Path (Join-Path $dataPath 'secrets') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $dataPath 'logs') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $installPath 'api-sucursal') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $installPath 'job-sync-sucursal') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $payloadPath 'services\api-sucursal\api-sucursal') | Out-Null
    # MIGRATE hace Push-Location a esta carpeta de verdad (no esta mockeado,
    # alembic.ini es CWD-relative) - solo Invoke-ParkosMigrateExe (el exe en
    # si) esta mockeado, asi que la carpeta debe existir realmente.
    New-Item -ItemType Directory -Force -Path (Join-Path $payloadPath 'services\migrate\migrate') | Out-Null

    Set-Content -Path (Join-Path $installPath 'api-sucursal\api-sucursal.exe') -Value 'dummy'
    Set-Content -Path (Join-Path $installPath 'job-sync-sucursal\job-sync-sucursal.exe') -Value 'dummy'
    Set-Content -Path (Join-Path $payloadPath 'services\api-sucursal\api-sucursal\api-sucursal.exe') -Value 'dummy-new'

    $envLines = @(
        'PARKOS_DEPLOY=branch'
        'PARKOS_DB_URL=postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
        'DATABASE_URL=postgresql+asyncpg://parkos_app:secret@127.0.0.1:5432/parkos'
        'PORT=8000'
    )
    Set-Content -Path (Join-Path $dataPath 'secrets\.env') -Value $envLines

    Set-Content -Path (Join-Path $dataPath 'secrets\pgpass.conf') -Value '127.0.0.1:5432:*:parkos:superuserpass'
    Set-Content -Path (Join-Path $dataPath 'current-version.txt') -Value '20250101-000000' -NoNewline

    $manifest = [ordered]@{
        generated_at = '2026-01-01T00:00:00Z'
        binaries     = [ordered]@{
            'services\api-sucursal\api-sucursal\api-sucursal.exe' = 'MATCHINGHASH'
        }
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $payloadPath 'manifest.sha256.json')

    return @{ InstallPath = $installPath; DataPath = $dataPath; PayloadPath = $payloadPath }
}

# Setea las mismas variables que Invoke-ParkosUpdate lee directamente (mismo
# mecanismo de scope que $InstallPath/$DataPath ya usan dentro de
# Invoke-ParkosInstall) - verificado empiricamente antes de escribir esto
# que $script:X mutado desde un scope anidado (un It de Pester es, en los
# hechos, un scope hijo) SI es visto por una funcion que resuelve $X sin
# calificar.
function Set-UpdateTestParams {
    param([hashtable]$Fixture, [switch]$Force, [switch]$RollbackOnly)

    $script:InstallPath = $Fixture.InstallPath
    $script:DataPath = $Fixture.DataPath
    $script:PayloadPath = $Fixture.PayloadPath
    $script:Force = [bool]$Force
    $script:RollbackOnly = [bool]$RollbackOnly
}

Describe 'Invoke-ParkosUpdate' {

    # Evita los 30s reales de timeout de Wait-ForApiHealth/Wait-
    # ForSyncPollCycle en cada test - ambas funciones ya existen en
    # parkos-installer.ps1 y son directamente mockeables (dot-sourced, no
    # modulo).
    Mock Wait-ForApiHealth { $true }
    Mock Wait-ForSyncPollCycle { $true }
    Mock Stop-Service { }
    Mock Start-Service { }
    Mock Move-Item { }
    Mock Copy-Item { }
    Mock Invoke-WebRequest { [PSCustomObject]@{ StatusCode = 200 } }

    It 'manifest de payload que no coincide dispara SOLO recuperacion tier-1 (Stop-Service + Start-Service, sin pg_restore --clean ni mover binarios)' {
        $root = Join-Path $TestDrive 'mismatch'
        $fixture = New-UpdateTestFixture -Root $root
        Set-UpdateTestParams -Fixture $fixture -Force

        Mock Invoke-ParkosPgDump { }
        Mock Test-ParkosDumpHasObjects { $true }
        Mock Invoke-ParkosPgRestoreClean { }
        Mock Invoke-ParkosMigrateExe { 0 }
        # Hash que NUNCA coincide con 'MATCHINGHASH' del manifest de fixture.
        Mock Get-FileHash { [PSCustomObject]@{ Hash = 'MISMATCHEDHASH' } }

        { Invoke-ParkosUpdate } | Should Throw 'Hash SHA256 no coincide'

        Assert-MockCalled Invoke-ParkosPgDump -Scope It
        Assert-MockCalled Stop-Service -Scope It
        Assert-MockCalled Get-FileHash -Scope It
        Assert-MockCalled Start-Service -Scope It
        Assert-MockCalled Move-Item -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-ParkosPgRestoreClean -Times 0 -Exactly -Scope It
    }

    It 'un backup vacio (pg_restore --list sin objetos) aborta ANTES de detener servicios' {
        $root = Join-Path $TestDrive 'emptydump'
        $fixture = New-UpdateTestFixture -Root $root
        Set-UpdateTestParams -Fixture $fixture -Force

        Mock Invoke-ParkosPgDump { }
        Mock Test-ParkosDumpHasObjects { $false }

        { Invoke-ParkosUpdate } | Should Throw 'quedo vacio o invalido'

        Assert-MockCalled Invoke-ParkosPgDump -Scope It
        Assert-MockCalled Stop-Service -Times 0 -Exactly -Scope It
    }

    It 'una falla de migrate.exe dispara el rollback completo tier-2 (pg_restore --clean)' {
        $root = Join-Path $TestDrive 'migratefail'
        $fixture = New-UpdateTestFixture -Root $root
        Set-UpdateTestParams -Fixture $fixture -Force

        Mock Invoke-ParkosPgDump { }
        Mock Test-ParkosDumpHasObjects { $true }
        Mock Invoke-ParkosPgRestoreClean { }
        Mock Get-FileHash { [PSCustomObject]@{ Hash = 'MATCHINGHASH' } }
        Mock Invoke-ParkosMigrateExe { 1 }

        $result = Invoke-ParkosUpdate

        $result.ExitCode | Should Be 1
        Assert-MockCalled Invoke-ParkosMigrateExe -Scope It
        Assert-MockCalled Invoke-ParkosPgRestoreClean -Times 1 -Exactly -Scope It
        Assert-MockCalled Start-Service -Scope It
    }

    It '-WhatIf no ejecuta ninguna llamada real (Stop-Service/Start-Service/Get-FileHash/pg_dump)' {
        $root = Join-Path $TestDrive 'whatif'
        $fixture = New-UpdateTestFixture -Root $root
        Set-UpdateTestParams -Fixture $fixture -Force

        Mock Invoke-ParkosPgDump { }
        Mock Test-ParkosDumpHasObjects { $true }
        Mock Get-FileHash { [PSCustomObject]@{ Hash = 'MATCHINGHASH' } }

        $result = Invoke-ParkosUpdate -WhatIf

        $result.ExitCode | Should Be 0
        Assert-MockCalled Stop-Service -Times 0 -Exactly -Scope It
        Assert-MockCalled Start-Service -Times 0 -Exactly -Scope It
        Assert-MockCalled Get-FileHash -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-ParkosPgDump -Times 0 -Exactly -Scope It
    }
}

# ---------------------------------------------------------------------------
# Tests de -Command Restore (Invoke-ParkosRestore), PR4b (ultimo de 11 del
# plan de cierre de gaps, DEC-INST-28..31). Comparten el mismo dot-source de
# parkos-installer.ps1 de arriba (linea 42) en vez de duplicarlo en un
# archivo nuevo - por eso este bloque vive en el mismo archivo que los tests
# de Invoke-ParkosUpdate en vez de en installer/tests/ParkosInstaller.
# Restore.Tests.ps1 separado.
#
# Cobertura real (5 tests minimos exigidos):
#   - -Version inexistente en releases\ -> throw listando versiones disponibles.
#   - Confirmacion interactiva incorrecta (no escribe RESTAURAR) -> cancela
#     limpio, CERO mutaciones (Stop-Service nunca se llama).
#   - -Unattended sin -UnattendedRestoreConfirmed -> throw.
#   - -RestoreDatabase sin un dump 'pre-update-<Version>-*.dump' que matchee
#     EXACTAMENTE esa version -> NO throw, continua, pg_restore NUNCA se
#     invoca (nunca se adivina con "el mas reciente que sea").
#   - Sin MSI archivado para esa version (releases\<Version>\apps\ vacio o
#     inexistente) -> continua sin throw, restaura SOLO binarios
#     (Install-Electron/Uninstall-ParkosElectron nunca se llaman).
# Mismo hallazgo de Pester 3.4.0 documentado arriba - todo `Should Throw` de
# este bloque lleva substring de mensaje esperado, nunca a secas.

function New-RestoreTestFixture {
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Version = '20250101-000000',
        [switch]$WithMsi
    )

    $fixture = New-UpdateTestFixture -Root $Root

    $releaseDir = Join-Path $fixture.InstallPath "releases\$Version"
    New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir 'api-sucursal') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir 'job-sync-sucursal') | Out-Null
    Set-Content -Path (Join-Path $releaseDir 'api-sucursal\api-sucursal.exe') -Value 'dummy-old'
    Set-Content -Path (Join-Path $releaseDir 'job-sync-sucursal\job-sync-sucursal.exe') -Value 'dummy-old'

    if ($WithMsi) {
        New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir 'apps') | Out-Null
        Set-Content -Path (Join-Path $releaseDir 'apps\web_sucursal-1.2.3.msi') -Value 'dummy-msi'
    }

    # Dump PRE-EXISTENTE que a proposito NO matchea 'pre-update-<Version>-' -
    # prueba que -RestoreDatabase nunca "adivina" con el dump mas reciente
    # que sea, solo con el que matchea la version pedida exactamente.
    $backupsDir = Join-Path $fixture.DataPath 'backups'
    New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null
    Set-Content -Path (Join-Path $backupsDir 'pre-update-otraversion-20260101-010101.dump') -Value 'dummy-dump'

    $fixture.Version = $Version
    return $fixture
}

function Set-RestoreTestParams {
    param(
        [hashtable]$Fixture,
        [switch]$Unattended,
        [switch]$UnattendedRestoreConfirmed,
        [switch]$RestoreDatabase
    )

    $script:InstallPath = $Fixture.InstallPath
    $script:DataPath = $Fixture.DataPath
    $script:Version = $Fixture.Version
    $script:Unattended = [bool]$Unattended
    $script:UnattendedRestoreConfirmed = [bool]$UnattendedRestoreConfirmed
    $script:RestoreDatabase = [bool]$RestoreDatabase
}

Describe 'Invoke-ParkosRestore' {

    Mock Wait-ForApiHealth { $true }
    Mock Wait-ForSyncPollCycle { $true }
    Mock Stop-Service { }
    Mock Start-Service { }
    Mock Copy-Item { }
    Mock Invoke-ParkosPgDump { }
    Mock Invoke-ParkosPgRestoreClean { }
    Mock Install-Electron { }
    Mock Uninstall-ParkosElectron { }
    Mock Read-Host { 'RESTAURAR' }

    It '-Version que no existe en releases\ dispara throw listando las versiones disponibles' {
        $root = Join-Path $TestDrive 'restore-badversion'
        $fixture = New-RestoreTestFixture -Root $root -Version '20250101-000000'
        Set-RestoreTestParams -Fixture $fixture
        $script:Version = 'no-existe-esta-version'

        { Invoke-ParkosRestore } | Should Throw "No existe la version 'no-existe-esta-version'"
    }

    It 'confirmacion incorrecta (no escribe RESTAURAR) cancela limpio sin ninguna mutacion' {
        $root = Join-Path $TestDrive 'restore-badconfirm'
        $fixture = New-RestoreTestFixture -Root $root
        Set-RestoreTestParams -Fixture $fixture

        Mock Read-Host { 'no' }

        $result = Invoke-ParkosRestore

        $result.ExitCode | Should Be 0
        Assert-MockCalled Stop-Service -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-ParkosPgDump -Times 0 -Exactly -Scope It
        Assert-MockCalled Copy-Item -Times 0 -Exactly -Scope It
    }

    It '-Unattended sin -UnattendedRestoreConfirmed dispara throw' {
        $root = Join-Path $TestDrive 'restore-unattended'
        $fixture = New-RestoreTestFixture -Root $root
        Set-RestoreTestParams -Fixture $fixture -Unattended

        { Invoke-ParkosRestore } | Should Throw '-UnattendedRestoreConfirmed es obligatorio'

        Assert-MockCalled Stop-Service -Times 0 -Exactly -Scope It
    }

    It '-RestoreDatabase sin un dump que matchee pre-update-<Version>- continua sin throw y NUNCA llama pg_restore' {
        $root = Join-Path $TestDrive 'restore-nodump'
        $fixture = New-RestoreTestFixture -Root $root
        Set-RestoreTestParams -Fixture $fixture -RestoreDatabase

        # Pester 3.4.0: un `Mock` definido DENTRO de un It reemplaza el Mock
        # de nivel Describe para el resto del bloque (no queda aislado a ese
        # It) - el test anterior de confirmacion incorrecta dejo Read-Host
        # devolviendo 'no'. Se re-mockea aca explicitamente para no depender
        # del orden de ejecucion de los tests.
        Mock Read-Host { 'RESTAURAR' }

        $result = Invoke-ParkosRestore

        $result.ExitCode | Should Be 0
        Assert-MockCalled Invoke-ParkosPgRestoreClean -Times 0 -Exactly -Scope It
        Assert-MockCalled Stop-Service -Scope It
    }

    It 'sin MSI archivado para esa version continua sin throw y restaura solo binarios (sin (des)instalar el MSI)' {
        $root = Join-Path $TestDrive 'restore-nomsi'
        $fixture = New-RestoreTestFixture -Root $root -WithMsi:$false
        Set-RestoreTestParams -Fixture $fixture

        # Ver comentario del test anterior: re-mockeado explicitamente por la
        # misma razon (el Mock de nivel Describe no sobrevive intacto a un
        # Mock redefinido dentro de un It previo).
        Mock Read-Host { 'RESTAURAR' }

        $result = Invoke-ParkosRestore

        $result.ExitCode | Should Be 0
        Assert-MockCalled Install-Electron -Times 0 -Exactly -Scope It
        Assert-MockCalled Uninstall-ParkosElectron -Times 0 -Exactly -Scope It
        Assert-MockCalled Stop-Service -Scope It
    }
}

# Ejecutar con: Invoke-Pester -Path installer/tests/ParkosInstaller.Update.Tests.ps1
