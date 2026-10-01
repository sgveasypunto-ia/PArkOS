# Tests de installer/parkos-installer.ps1's cascada -Unattended
# (Invoke-ParkosUnattendedCascade), PR5 de 11 del plan de cierre de gaps
# (DEC-INST-32..35). Mismo dot-source directo de parkos-installer.ps1 que ya
# usa installer/tests/ParkosInstaller.Update.Tests.ps1 (no Import-Module) -
# el guard final del archivo (`if ($MyInvocation.InvocationName -ne '.')`)
# no dispara ningun auto-run al dot-sourcear.
#
# Mismo hallazgo de Pester 3.4.0 ya documentado en ParkosInstaller.Update.
# Tests.ps1: `Should Throw`/`Should Not Throw` SIN argumento de mensaje NUNCA
# evalua de verdad en esta instalacion (bug real, confirmado) - todo
# `Should Throw` de este archivo lleva un substring de mensaje esperado.
#
# Estrategia de aislamiento: Get-ParkosStageDefinitions (DEC-INST-32) se
# MOCKEA en los tests de la cascada (New-FakeStageDefinitions abajo) en vez
# de dejar correr las 9 Action reales (Postgres/NSSM/msiexec reales) - lo que
# se prueba aca es la LOGICA de la cascada (orden, -SkipStage,
# -StopAfterStage, rollback-al-fallar, exit codes), no las etapas en si
# (esas ya tienen su propia cobertura implicita via el uso real del
# instalador). Cada etapa falsa anota su paso en $script:StageCallLog en vez
# de hacer nada real, para poder verificar exactamente que corrio y en que
# orden.
#
# Cobertura real (10 tests, por encima del minimo de 6 exigido):
#   - Validaciones (Assert-ParkosCascadeParamsValid): falta -EulaAccepted,
#     -SkipStage fuera de rango, -SkipStage con 1 sin -Force.
#   - Read-SucursalUuid vacio en modo -Unattended: confirma (no duplica) que
#     ya tira throw por si solo - ver el comentario de Assert-
#     ParkosCascadeParamsValid en el archivo principal.
#   - Cascada feliz (9 etapas OK) -> ExitCode 0, las 9 corren en orden.
#   - Una etapa falla a mitad de camino -> su Rollback se invoca, las etapas
#     posteriores NUNCA corren, ExitCode 1.
#   - -SkipStage omite una etapa puntual (su Action nunca se invoca) y la
#     cascada sigue con las demas, ExitCode 0.
#   - -StopAfterStage corta deliberadamente en la etapa indicada, ExitCode 0
#     (no 1 - no es un fallo).
#   - Dispatcher final -Command Update/Restore (bug corregido en este PR): un
#     fallo suave (ExitCode=1, sin excepcion) de Invoke-ParkosUpdate/
#     Invoke-ParkosRestore SI propaga exit 1 del proceso real - ver el
#     Describe dedicado mas abajo (unico bloque de este archivo que corre el
#     bloque dispatcher real en un proceso pwsh hijo separado).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

# Fabrica 9 etapas de prueba autonomas (sin tocar Postgres/NSSM/msiexec
# reales) - cada Action/Rollback solo anota su paso en $script:StageCallLog.
# Construidas con [scriptblock]::Create (en vez de un `foreach` con closures
# normales) para que cada scriptblock capture su propio numero de etapa por
# valor, literal en el texto del scriptblock - evita el problema clasico de
# cerrar sobre una variable de loop compartida.
function New-FakeStageDefinitions {
    param([int[]]$FailingStages = @())

    $stages = [ordered]@{}
    foreach ($n in 0..8) {
        $actionCode = if ($FailingStages -contains $n) {
            "`$script:StageCallLog += 'action:$n'; throw 'boom etapa de prueba $n'"
        } else {
            "`$script:StageCallLog += 'action:$n'"
        }
        $rollbackCode = "`$script:StageCallLog += 'rollback:$n'"

        $stages["$n"] = @{
            Key      = "stage$n"
            Name     = "Etapa de prueba $n"
            Action   = [scriptblock]::Create($actionCode)
            Rollback = [scriptblock]::Create($rollbackCode)
        }
    }
    return @{ Stages = $stages; Paths = @{} }
}

# Mismo mecanismo de scope que Set-UpdateTestParams/Set-RestoreTestParams
# (ParkosInstaller.Update.Tests.ps1): Invoke-ParkosUnattendedCascade lee
# estas variables sin calificar (mismo patron que Invoke-ParkosUpdate ya
# usa), y un `It` de Pester es, en los hechos, un scope hijo - mutar
# $script:X aca es lo unico que una funcion resuelve correctamente.
function Set-CascadeTestParams {
    param(
        [Parameter(Mandatory)][string]$Root,
        [int[]]$SkipStage = @(),
        [int]$StopAfterStage = -1,
        [switch]$Force,
        [switch]$EulaAccepted
    )

    $script:InstallPath = Join-Path $Root 'Parkos'
    $script:DataPath = Join-Path $Root 'ParkosData'
    $script:Unattended = $true
    $script:EulaAccepted = [bool]$EulaAccepted
    $script:Force = [bool]$Force
    $script:SucursalUuid = '11111111-1111-1111-1111-111111111111'
    $script:CloudApiUrl = 'https://cloud.example.test'
    $script:SkipStage = $SkipStage
    $script:StopAfterStage = $StopAfterStage
    $script:StageCallLog = @()
}

Describe 'Assert-ParkosCascadeParamsValid' {

    It 'falta -EulaAccepted en modo -Unattended dispara throw' {
        { Assert-ParkosCascadeParamsValid -Unattended -CloudApiUrl 'https://cloud.example.test' } |
            Should Throw '-EulaAccepted'
    }

    It '-SkipStage fuera de rango (0..8) dispara throw' {
        { Assert-ParkosCascadeParamsValid -SkipStage @(9) -Unattended -EulaAccepted -CloudApiUrl 'https://cloud.example.test' } |
            Should Throw 'invalido'
    }

    It '-SkipStage con la etapa 1 (Postgres) sin -Force dispara throw' {
        { Assert-ParkosCascadeParamsValid -SkipStage @(1) -Unattended -EulaAccepted -CloudApiUrl 'https://cloud.example.test' } |
            Should Throw '-Force'
    }

    It '-SkipStage con la etapa 1 (Postgres) CON -Force no dispara throw (solo advierte)' {
        # No se usa `Should Not Throw` aca a proposito: con un substring que
        # no aparezca en NINGUN mensaje de error real de esta funcion (como
        # 'invalido', que no aparece en el mensaje de -Force), `Should Not
        # Throw '<substring>'` reportaria exito igual aunque la funcion
        # tirara una excepcion DISTINTA - un falso positivo que no detectaria
        # una regresion real. Un try/catch manual + `Should Be` evita el bug
        # de PesterThrow.ps1 por completo en vez de esquivarlo a medias.
        $threw = $false
        try {
            Assert-ParkosCascadeParamsValid -SkipStage @(1) -Force -Unattended -EulaAccepted -CloudApiUrl 'https://cloud.example.test'
        } catch {
            $threw = $true
        }
        $threw | Should Be $false
    }
}

Describe 'Read-SucursalUuid en modo -Unattended (confirma, no duplica, la validacion existente)' {

    It 'UUID vacio en modo -Unattended dispara throw' {
        $script:Unattended = $true
        { Read-SucursalUuid -Uuid '' } | Should Throw '-SucursalUuid'
    }
}

Describe 'Invoke-ParkosUnattendedCascade' {

    Mock Test-Preflight { $true }

    It 'cascada feliz: las 9 etapas mockeadas OK corren en orden -> ExitCode 0' {
        $root = Join-Path $TestDrive 'happy'
        Set-CascadeTestParams -Root $root -EulaAccepted

        Mock Get-ParkosStageDefinitions { New-FakeStageDefinitions }

        $result = Invoke-ParkosUnattendedCascade

        $result.ExitCode | Should Be 0
        ($script:StageCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It 'una etapa fallida corta la cascada, invoca su Rollback y NUNCA corre las etapas posteriores -> ExitCode 1' {
        $root = Join-Path $TestDrive 'midfail'
        Set-CascadeTestParams -Root $root -EulaAccepted

        Mock Get-ParkosStageDefinitions { New-FakeStageDefinitions -FailingStages @(3) }

        $result = Invoke-ParkosUnattendedCascade

        $result.ExitCode | Should Be 1
        ($script:StageCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,rollback:3'
    }

    It '-SkipStage omite la etapa indicada (su Action nunca se invoca) y la cascada sigue con las demas -> ExitCode 0' {
        $root = Join-Path $TestDrive 'skipstage'
        Set-CascadeTestParams -Root $root -EulaAccepted -SkipStage @(2)

        Mock Get-ParkosStageDefinitions { New-FakeStageDefinitions }

        $result = Invoke-ParkosUnattendedCascade

        $result.ExitCode | Should Be 0
        ($script:StageCallLog -join ',') | Should Be 'action:0,action:1,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It '-StopAfterStage corta deliberadamente en la etapa indicada -> ExitCode 0 (no 1)' {
        $root = Join-Path $TestDrive 'stopafter'
        Set-CascadeTestParams -Root $root -EulaAccepted -StopAfterStage 4

        Mock Get-ParkosStageDefinitions { New-FakeStageDefinitions }

        $result = Invoke-ParkosUnattendedCascade

        $result.ExitCode | Should Be 0
        ($script:StageCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,action:4'
    }
}

# Bug real (ya diagnosticado y documentado en la cabecera de installer/tests/
# e2e/Invoke-UnattendedE2E.ps1 antes de este fix): los brazos 'Update'/
# 'Restore' del dispatcher final del archivo (el `if ($MyInvocation.
# InvocationName -ne '.') { switch ($Command) {...} }` de mas arriba)
# llamaban a Invoke-ParkosUpdate/Invoke-ParkosRestore y DESCARTABAN el objeto
# [PSCustomObject]@{ExitCode=...} que devuelven - un fallo suave (ExitCode=1,
# ya logueado, sin excepcion) igual terminaba el PROCESO completo con exit
# code 0, exactamente igual que 'Install' -Unattended hacia ANTES de PR5
# (corregido ahi con `exit $cascadeResult.ExitCode`, el mismo patron que
# ahora se replica en 'Update'/'Restore').
#
# Ninguno de los archivos de tests de este directorio ejercita hoy el bloque
# dispatcher en si mismo: TODOS (incluido este archivo, arriba) dot-sourcean
# parkos-installer.ps1 precisamente PORQUE eso deja $MyInvocation.
# InvocationName en '.' y salta el guard - asi se puede probar
# Invoke-ParkosUnattendedCascade/Invoke-ParkosUpdate/Invoke-ParkosRestore
# como funciones normales sin que un `exit` real mate el proceso de Pester
# (mismo razonamiento, ya documentado ahi, de por que
# Invoke-ParkosUnattendedCascade en si nunca llama `exit`). Probar el
# WRAPPER en si (que el `exit` de verdad reciba el ExitCode correcto) no
# tiene atajo dentro del mismo proceso: un `exit` real SIEMPRE termina el
# proceso completo sin importar el scope. Los 2 tests de abajo corren el
# bloque REAL del dispatcher en un proceso pwsh hijo separado (mismo
# mecanismo que Invoke-ParkosInstallerProcess ya usa en
# Invoke-UnattendedE2E.ps1 para leer un exit code de verdad sin arriesgar el
# proceso llamador) - el cuerpo del bloque se EXTRAE del AST real del
# archivo (misma API [System.Management.Automation.Language.Parser]::
# ParseFile que usa la validacion de sintaxis de este PR) en vez de
# copiarlo a mano, para que el test nunca quede desincronizado en silencio
# de una futura edicion real del dispatcher.
Describe 'Dispatcher final -Command Update/Restore: el ExitCode del resultado SI se propaga como exit code de proceso (bug corregido)' {

    function Get-ParkosDispatcherBodyText {
        $parseTokens = $null
        $parseErrors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($installerScript, [ref]$parseTokens, [ref]$parseErrors)
        $dispatcherIf = $ast.EndBlock.Statements |
            Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] } |
            Select-Object -Last 1
        if ($null -eq $dispatcherIf) {
            throw 'No se encontro el if-statement final del dispatcher en parkos-installer.ps1 (cambio de forma inesperado).'
        }
        $blockText = $dispatcherIf.Clauses[0].Item2.Extent.Text
        # $blockText incluye las llaves externas del StatementBlockAst
        # ('{ ... }') - se despojan con Substring (no regex, para no
        # depender de que el contenido interno no tenga llaves sueltas al
        # principio/final) porque el proceso hijo ejecuta este cuerpo
        # directamente en su scope de nivel superior, sin el `if
        # ($MyInvocation...)` que lo envuelve en el archivo real (ese guard
        # no aplica aca - el proceso hijo siempre debe correr el dispatcher).
        return $blockText.Substring(1, $blockText.Length - 2)
    }

    function Invoke-ParkosDispatcherChildProcess {
        param(
            [Parameter(Mandatory)][ValidateSet('Update', 'Restore')][string]$DispatchCommand,
            [Parameter(Mandatory)][int]$StubExitCode
        )

        $dispatcherBody = Get-ParkosDispatcherBodyText
        $stubFunctionName = "Invoke-Parkos$DispatchCommand"

        # Stub de funcion normal, NO Pester Mock: un proceso hijo separado no
        # comparte el runspace de Pester, asi que Mock/Assert-MockCalled no
        # alcanzarian aca. Se redefine DESPUES del dot-source real para que
        # gane sobre la definicion real del archivo (misma regla de
        # PowerShell: la ultima definicion de una funcion en un scope gana) -
        # nunca ejecuta nada real (Postgres/servicios/pg_dump).
        $childScriptLines = @(
            "`$ErrorActionPreference = 'Stop'"
            ". '$installerScript' -Command $DispatchCommand"
            "function $stubFunctionName { [PSCustomObject]@{ ExitCode = $StubExitCode; Detail = 'stub de prueba del dispatcher - nunca ejecuta nada real' } }"
            $dispatcherBody
        )
        $childScriptText = $childScriptLines -join "`n"

        $tempScript = Join-Path $TestDrive "dispatcher-child-$DispatchCommand.ps1"
        Set-Content -Path $tempScript -Value $childScriptText -Encoding UTF8

        $process = Start-Process -FilePath 'pwsh' -ArgumentList @('-NoProfile', '-NonInteractive', '-File', $tempScript) -PassThru -Wait -WindowStyle Hidden
        return $process.ExitCode
    }

    It '-Command Update: un fallo suave de Invoke-ParkosUpdate (ExitCode=1, sin excepcion) SI propaga exit 1 del proceso' {
        $exitCode = Invoke-ParkosDispatcherChildProcess -DispatchCommand 'Update' -StubExitCode 1
        $exitCode | Should Be 1
    }

    It '-Command Restore: un fallo suave de Invoke-ParkosRestore (ExitCode=1, sin excepcion) SI propaga exit 1 del proceso' {
        $exitCode = Invoke-ParkosDispatcherChildProcess -DispatchCommand 'Restore' -StubExitCode 1
        $exitCode | Should Be 1
    }
}

# Ejecutar con: Invoke-Pester -Path installer/tests/ParkosInstaller.Unattended.Tests.ps1
