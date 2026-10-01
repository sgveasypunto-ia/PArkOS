# Tests de installer/parkos-installer.ps1's menu interactivo extendido (PR10
# de 11 del plan de cierre de gaps, DEC-INST-41 - ver plan.md, nota sobre la
# colision con el DEC-INST-40 ya ocupado por Fase 27): migracion de
# $script:StageStatus de booleano a enum ParkosStageState, y las 8 opciones
# de letra nuevas (A/R/U/V/X/D/M/C) agregadas a Invoke-ParkosInstall. Mismo
# dot-source directo de parkos-installer.ps1 que ya usan
# ParkosInstaller.Update.Tests.ps1/ParkosInstaller.Unattended.Tests.ps1 (no
# Import-Module de parkos-installer.ps1 en si) - las funciones quedan en el
# scope de este archivo de test, los Mock/Assert-MockCalled de abajo NO
# llevan -ModuleName para esas.
#
# El modulo Parkos (los 8 cmdlets reales que las opciones de letra invocan)
# SI se importa de verdad (mismo patron ya usado en
# installer/tests/Parkos.Module.Tests.ps1: Import-Module real del .psd1,
# nunca mockeado) - Invoke-ParkosInstall llama a esos cmdlets desde AFUERA
# del modulo (parkos-installer.ps1 nunca es parte de el), asi que
# mockearlos sin -ModuleName (como se hace mas abajo) intercepta
# correctamente esas llamadas externas sin tocar Postgres/NSSM/msiexec/
# Task Scheduler reales.
#
# Mismo hallazgo de Pester 3.4.0 ya documentado en los otros archivos de
# tests de este directorio: `Should Throw`/`Should Not Throw` SIN argumento
# de mensaje NUNCA evalua de verdad en esta instalacion - todo `Should
# Throw` de este archivo lleva un substring de mensaje esperado; para "no
# deberia lanzar" se usa try/catch manual + `Should Be $true/$false`, nunca
# `Should Not Throw`.
#
# Cobertura real (10 tests, por encima del minimo de 8 exigido):
#   1. Trampa de truthiness del enum: una etapa en NotRun (no $false) SIGUE
#      disparando el gate "Corre primero" de una etapa dependiente.
#   2. Opcion R con instalacion incompleta pide confirmacion; 'N' -> nunca
#      llama Repair-ParkosInstall.
#   3. Opcion A con instalacion incompleta NO pide confirmacion (exenta) y
#      llama Get-ParkosHealth directo.
#   4. Opcion U pide -PayloadPath y lo setea correctamente antes de llamar a
#      Invoke-ParkosUpdate (que es `param()` - sin argumento formal).
#   4b. Opcion U con un fallo suave de Invoke-ParkosUpdate (ExitCode=1, sin
#       excepcion) muestra el fallo en rojo en vez de silencio (bug
#       corregido en este PR).
#   5. Opcion V lista versiones de releases\ bajo InstallPath (NUNCA bajo
#      DataPath - DEC-INST-37) y setea $script:Version antes de llamar a
#      Invoke-ParkosRestore.
#   5b. Opcion V con un fallo suave de Invoke-ParkosRestore (ExitCode=1, sin
#       excepcion) muestra el fallo en rojo en vez de silencio (mismo bug,
#       corregido en este PR).
#   6. Opcion X exitosa (Uninstall-Parkos mockeado ExitCode=0) termina el
#      bucle del menu - verificado con el conteo de llamadas a Read-Host.
#   7. Q con instalacion incompleta y 'N' -> vuelve al menu (no sale).
#   8. Get-ParkosStageMenuLines: una etapa Failed renderiza "re-ejecutable".

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

$moduleManifestPath = Join-Path $PSScriptRoot '..\payload\management\Parkos.psd1'

# Mismo mecanismo de scope que Set-CascadeTestParams/Set-UpdateTestParams
# (los otros archivos de este directorio): Invoke-ParkosInstall lee estas
# variables sin calificar, y un `It` de Pester es, en los hechos, un scope
# hijo - mutar $script:X aca es lo unico que la funcion resuelve
# correctamente.
function Set-MenuTestParams {
    param([Parameter(Mandatory)][string]$Root)

    # $script:OriginalArgs SOLO se setea hoy dentro del guard final del
    # archivo (`if ($MyInvocation.InvocationName -ne '.') { ... }`), que
    # nunca corre al dot-sourcear (mismo mecanismo ya documentado en
    # ParkosInstaller.Update.Tests.ps1) - Invoke-ParkosInstall lo pasa a
    # Ensure-PowerShell7/Request-Elevation (mockeadas mas abajo, pero
    # Set-StrictMode -Version Latest igual revienta al EVALUAR el argumento
    # si la variable nunca se seteo) asi que hay que setearlo aca.
    $script:OriginalArgs = @()
    $script:InstallPath = Join-Path $Root 'Parkos'
    $script:DataPath = Join-Path $Root 'ParkosData'
    $script:Unattended = $false
    $script:SucursalUuid = '11111111-1111-1111-1111-111111111111'
    $script:CloudApiUrl = 'https://cloud.example.test'
    $script:PayloadPath = ''
    $script:Version = ''
    $script:RollbackOnly = $false
    $script:Force = $false
    $script:RestoreDatabase = $false
    $script:UnattendedRestoreConfirmed = $false
}

# Fabrica 9 etapas de prueba SIN ninguna Action/Rollback real (evita
# Postgres/NSSM/msiexec reales) - unicamente usada para dejar que
# Invoke-ParkosInstall arme su $script:StageStatus interno (todas arrancan
# en NotRun); ninguno de los tests de este archivo elige una opcion NUMERICA
# (0-8), asi que Action nunca se invoca de verdad.
function New-FakeMenuStageDefinitions {
    $keys = 'build', 'db', 'migrate', 'sucursal', 'seed', 'api', 'job', 'electron', 'verify'
    $stages = [ordered]@{}
    for ($i = 0; $i -lt 9; $i++) {
        $stages["$i"] = @{
            Key      = $keys[$i]
            Name     = "Etapa de prueba $i"
            Action   = { }
            Rollback = $null
        }
    }
    return @{ Stages = $stages; Paths = @{} }
}

# Mock de Read-Host respaldado por una cola FIFO de respuestas scripteadas -
# cada test arma la secuencia EXACTA de respuestas que Invoke-ParkosInstall
# va a pedir (opcion de menu + cualquier confirmacion/prompt de seguimiento
# de esa opcion), en el orden en que las va a pedir. Si la cola se queda sin
# respuestas, el mock hace throw en vez de bloquearse esperando input real -
# eso delata un test mal armado (secuencia incompleta) en vez de colgar la
# corrida de Pester.
function Set-MenuReadHostQueue {
    param([string[]]$Responses)
    $script:MenuReadHostQueue = [System.Collections.Generic.Queue[string]]::new([string[]]$Responses)
}

Describe 'StageStatus enum: gates explicitos (no truthiness implicita)' {

    It 'una etapa en NotRun (no $false) SIGUE disparando el gate "Corre primero" de una etapa dependiente' {
        $root = Join-Path $TestDrive 'gate-notrun'
        Set-MenuTestParams -Root $root

        $definitions = Get-ParkosStageDefinitions -InstallPath $script:InstallPath -DataPath $script:DataPath `
            -SucursalUuid $script:SucursalUuid -CloudApiUrl $script:CloudApiUrl

        # 'db' arranca en NotRun (nunca corrio) - con el $script:StageStatus
        # VIEJO (booleano) esto era $false y el `if (-not ...)` de antes SI
        # disparaba el throw. El bug real a evitar en la migracion a enum es
        # que 'NotRun' (un string no vacio, por lo tanto verdadero en
        # PowerShell) deje de ser "falsy" y el throw NUNCA dispare si el gate
        # se hubiera dejado como `if (-not $script:StageStatus.db)`. Este
        # test prueba que el gate real de Get-ParkosStageDefinitions sigue
        # funcionando porque compara EXPLICITAMENTE contra ::Ok.
        $script:StageStatus = [ordered]@{
            build = [ParkosStageState]::NotRun
            db = [ParkosStageState]::NotRun; migrate = [ParkosStageState]::NotRun; sucursal = [ParkosStageState]::NotRun; seed = [ParkosStageState]::NotRun
            api = [ParkosStageState]::NotRun; job = [ParkosStageState]::NotRun; electron = [ParkosStageState]::NotRun; verify = [ParkosStageState]::NotRun
        }

        { & $definitions.Stages['3'].Action } | Should Throw 'Corre primero "Instalar base de datos"'
    }
}

Describe 'Invoke-ParkosInstall - opciones de letra (A/R/U/D/X) y gate de Q' {

    Mock Ensure-PowerShell7 { }
    Mock Request-Elevation { }
    Mock Test-Preflight { $true }
    Mock Show-Eula { $true }
    Mock Read-SucursalUuid { $script:SucursalUuid }

    Import-Module $moduleManifestPath -Force

    It 'opcion R con instalacion incompleta pide confirmacion; "N" nunca llama Repair-ParkosInstall' {
        $root = Join-Path $TestDrive 'menu-r-decline'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Repair-ParkosInstall { [PSCustomObject]@{ ExitCode = 0; Scenarios = @() } }

        Set-MenuReadHostQueue -Responses @('R', 'N', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Repair-ParkosInstall -Times 0 -Exactly -Scope It
    }

    It 'opcion A con instalacion incompleta NO pide confirmacion (exenta) y llama Get-ParkosHealth directo' {
        $root = Join-Path $TestDrive 'menu-a-exempt'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Get-ParkosHealth { [PSCustomObject]@{ ExitCode = 0; Checks = @{} } }

        Set-MenuReadHostQueue -Responses @('A', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Get-ParkosHealth -Times 1 -Exactly -Scope It
    }

    It 'opcion U pide -PayloadPath y lo setea antes de llamar a Invoke-ParkosUpdate (param(), sin argumento formal)' {
        $root = Join-Path $TestDrive 'menu-u-update'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Invoke-ParkosUpdate { [PSCustomObject]@{ ExitCode = 0; Detail = 'ok' } }

        Set-MenuReadHostQueue -Responses @('U', 's', 'C:\fake\payload-nuevo', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Invoke-ParkosUpdate -Times 1 -Exactly -Scope It
        $script:PayloadPath | Should Be 'C:\fake\payload-nuevo'
    }

    # Bug real (confirmado leyendo el codigo antes de este fix): la opcion U
    # solo capturaba una EXCEPCION lanzada por Invoke-ParkosUpdate (`catch`),
    # pero nunca revisaba el objeto DEVUELTO ([PSCustomObject]@{ExitCode=...})
    # cuando la funcion no lanza nada - un "fallo suave" (ExitCode=1, ya
    # logueado dentro de la funcion, sin excepcion) se trataba en silencio
    # como exito. Este menu es interactivo: NUNCA debe llamar `exit` real
    # aca (a diferencia del dispatcher -Unattended, ver
    # ParkosInstaller.Unattended.Tests.ps1) - solo debe mostrar el fallo con
    # el mismo estilo `Write-Host -ForegroundColor Red` que ya usa el bloque
    # catch de esta misma opcion, y volver al bucle del menu.
    It 'opcion U con un fallo suave de Invoke-ParkosUpdate (ExitCode=1, sin excepcion) muestra el fallo en rojo (no lo trata como exito silencioso)' {
        $root = Join-Path $TestDrive 'menu-u-update-soft-fail'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Invoke-ParkosUpdate { [PSCustomObject]@{ ExitCode = 1; Detail = 'Hash SHA256 no coincide (fallo suave de prueba)' } }
        Mock Write-Host { }

        Set-MenuReadHostQueue -Responses @('U', 's', 'C:\fake\payload-nuevo', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Invoke-ParkosUpdate -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-Host -Scope It -ParameterFilter {
            $Object -match 'Invoke-ParkosUpdate fallo' -and $Object -match 'Hash SHA256 no coincide' -and $ForegroundColor -eq 'Red'
        }
    }

    It 'opcion X exitosa (Uninstall-Parkos ExitCode=0) termina el bucle del menu' {
        $root = Join-Path $TestDrive 'menu-x-uninstall'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Uninstall-Parkos { [PSCustomObject]@{ ExitCode = 0; Detail = 'desinstalado' } }

        # X es exenta del gate de instalacion incompleta - solo 2 respuestas:
        # la opcion elegida y la confirmacion de -PurgeData. Si el menu
        # siguiera pidiendo una 3ra opcion (no termino el bucle), la cola se
        # quedaria corta y Read-Host haria throw.
        Set-MenuReadHostQueue -Responses @('X', 'N')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Uninstall-Parkos -Times 1 -Exactly -Scope It
        Assert-MockCalled Read-Host -Times 2 -Exactly -Scope It
    }

    It 'Q con instalacion incompleta y "N" -> vuelve al menu (no sale)' {
        $root = Join-Path $TestDrive 'menu-q-decline'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }

        # 'Q','N' (declina salir, vuelve al menu) seguido de un 2do 'Q','S'
        # (esta vez confirma) para poder terminar el test de forma limpia -
        # si el 'N' hubiera salido igual, la 2da vuelta de 'Q' nunca se
        # habria pedido y la cola sobrante haria fallar el conteo de abajo.
        Set-MenuReadHostQueue -Responses @('Q', 'N', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Read-Host -Times 4 -Exactly -Scope It
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Invoke-ParkosInstall - opcion V restaura desde releases\ bajo InstallPath (DEC-INST-37)' {

    Mock Ensure-PowerShell7 { }
    Mock Request-Elevation { }
    Mock Test-Preflight { $true }
    Mock Show-Eula { $true }
    Mock Read-SucursalUuid { $script:SucursalUuid }

    Import-Module $moduleManifestPath -Force

    It 'lista las versiones de $InstallPath\releases\ y pasa la elegida a Invoke-ParkosRestore' {
        $root = Join-Path $TestDrive 'menu-v-restore'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Invoke-ParkosRestore { [PSCustomObject]@{ ExitCode = 0; Detail = 'ok' } }

        # Releases vive bajo InstallPath (DEC-INST-37/DEC-INST-30), nunca
        # bajo DataPath - el enunciado original de esta fase decia
        # "$DataPath\releases", corregido aca contra el codigo real de
        # Invoke-ParkosRestore ($releasesPath = Join-Path $InstallPath
        # 'releases').
        New-Item -ItemType Directory -Force -Path (Join-Path $script:InstallPath 'releases\20250101-000000') | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $script:InstallPath 'releases\20250202-000000') | Out-Null

        Set-MenuReadHostQueue -Responses @('V', 's', '20250202-000000', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Invoke-ParkosRestore -Times 1 -Exactly -Scope It
        $script:Version | Should Be '20250202-000000'
    }

    # Mismo bug que la opcion U (ver el comentario del test equivalente en el
    # bloque 'opciones de letra' de arriba): la opcion V tampoco revisaba el
    # ExitCode del objeto devuelto por Invoke-ParkosRestore cuando no lanza
    # una excepcion - un fallo suave se trataba como exito silencioso. Sigue
    # siendo el menu interactivo: NUNCA debe llamar `exit` real aca, solo
    # mostrar el fallo en rojo y volver al bucle.
    It 'opcion V con un fallo suave de Invoke-ParkosRestore (ExitCode=1, sin excepcion) muestra el fallo en rojo (no lo trata como exito silencioso)' {
        $root = Join-Path $TestDrive 'menu-v-restore-soft-fail'
        Set-MenuTestParams -Root $root
        Mock Read-InstallPaths { @{ InstallPath = $script:InstallPath; DataPath = $script:DataPath } }
        Mock Get-ParkosStageDefinitions { New-FakeMenuStageDefinitions }
        Mock Invoke-ParkosRestore { [PSCustomObject]@{ ExitCode = 1; Detail = 'No existe la version indicada (fallo suave de prueba)' } }
        Mock Write-Host { }

        New-Item -ItemType Directory -Force -Path (Join-Path $script:InstallPath 'releases\20250101-000000') | Out-Null

        Set-MenuReadHostQueue -Responses @('V', 's', '20250101-000000', 'Q', 'S')
        Mock Read-Host {
            if ($script:MenuReadHostQueue.Count -eq 0) { throw 'Read-Host: cola de respuestas de prueba agotada.' }
            return $script:MenuReadHostQueue.Dequeue()
        }

        Invoke-ParkosInstall

        Assert-MockCalled Invoke-ParkosRestore -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-Host -Scope It -ParameterFilter {
            $Object -match 'Invoke-ParkosRestore fallo' -and $Object -match 'No existe la version indicada' -and $ForegroundColor -eq 'Red'
        }
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Get-ParkosStageMenuLines' {

    It 'una etapa en estado Failed renderiza la etiqueta [FAIL] y el texto "re-ejecutable"' {
        $fakeStages = (New-FakeMenuStageDefinitions).Stages
        $status = [ordered]@{
            build = [ParkosStageState]::Ok
            db = [ParkosStageState]::Failed; migrate = [ParkosStageState]::NotRun; sucursal = [ParkosStageState]::NotRun; seed = [ParkosStageState]::NotRun
            api = [ParkosStageState]::NotRun; job = [ParkosStageState]::NotRun; electron = [ParkosStageState]::NotRun; verify = [ParkosStageState]::NotRun
        }

        $lines = Get-ParkosStageMenuLines -Stages $fakeStages -StageStatus $status -Prereqs @{}
        $dbLine = $lines[1]

        ($dbLine.Text -match '\[FAIL\]') | Should Be $true
        ($dbLine.Text -match 're-ejecutable') | Should Be $true
    }
}

# Ejecutar con: Invoke-Pester -Path installer/tests/ParkosInstaller.Menu.Tests.ps1
