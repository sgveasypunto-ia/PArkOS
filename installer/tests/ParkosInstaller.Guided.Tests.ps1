# Tests del flujo guiado por defecto del instalador (rama
# feature/instalador_automatizado): el operador de sucursal corre el
# instalador sin elegir opciones de menu y solo tipea el UUID de la sucursal.
#
#   - Resolve-ParkosCloudApiUrl / Get-ParkosCloudEndpoint: URL del cloud desde
#     PARKOS_CLOUD_API_URL (default http://localhost:8000), nunca se pregunta.
#   - Test-Preflight: la conectividad se mide contra el host:puerto del cloud
#     (no github.com); la clave maestra es el requisito duro del flujo guiado.
#   - Show-Eula: Enter acepta. Read-InstallPaths: nunca pregunta.
#   - Read-SucursalUuid: unico dato tipeado; forma estricta + re-pregunta.
#   - ConvertTo-ParkosRelaunchArgs / Get-ParkosRelaunchArgumentList: la
#     elevacion/relanzo conserva los parametros con nombre (antes $args los
#     perdia todos) y los arreglos (-File convertia "2,7" en 27).
#   - Resolve-ParkosInstallMode / Invoke-ParkosGuidedInstall / cascada -Guided:
#     la etapa 0 (build) NO corre salvo -IncludeBuild.
#
# Pester 3.4.0: todo `Should Throw` lleva substring de mensaje (sin el, no
# evalua). Para "no tira" se usa try/catch manual + `Should Be`.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

Describe 'Resolve-ParkosCloudApiUrl' {

    It 'sin parametro ni variable de entorno devuelve el default http://localhost:8000' {
        Mock Get-ParkosEnvironmentValue { $null }
        Resolve-ParkosCloudApiUrl | Should Be 'http://localhost:8000'
    }

    It 'usa la variable de entorno PARKOS_CLOUD_API_URL cuando existe' {
        Mock Get-ParkosEnvironmentValue { 'https://cloud.example.test' }
        Resolve-ParkosCloudApiUrl | Should Be 'https://cloud.example.test'
    }

    It 'el parametro explicito gana sobre la variable de entorno' {
        Mock Get-ParkosEnvironmentValue { 'https://desde-entorno.example.test' }
        Resolve-ParkosCloudApiUrl -Explicit 'https://explicita.example.test' | Should Be 'https://explicita.example.test'
    }

    It 'quita la barra final para no duplicarla al armar rutas' {
        Mock Get-ParkosEnvironmentValue { 'https://cloud.example.test/' }
        Resolve-ParkosCloudApiUrl | Should Be 'https://cloud.example.test'
    }

    It 'una URL que no es http/https lanza un mensaje que nombra la variable' {
        Mock Get-ParkosEnvironmentValue { 'ftp://cloud.example.test' }
        # try/catch manual: un `{ ... } | Should Throw` se ejecuta fuera del
        # scope del It y no ve el Mock de Get-ParkosEnvironmentValue.
        $message = ''
        try { Resolve-ParkosCloudApiUrl | Out-Null } catch { $message = $_.Exception.Message }
        $message | Should Match 'PARKOS_CLOUD_API_URL'
    }

    It 'un texto que no es una URL lanza un mensaje que nombra la variable' {
        Mock Get-ParkosEnvironmentValue { 'esto no es una url' }
        # try/catch manual: un `{ ... } | Should Throw` se ejecuta fuera del
        # scope del It y no ve el Mock de Get-ParkosEnvironmentValue.
        $message = ''
        try { Resolve-ParkosCloudApiUrl | Out-Null } catch { $message = $_.Exception.Message }
        $message | Should Match 'PARKOS_CLOUD_API_URL'
    }
}

Describe 'Get-ParkosCloudEndpoint' {

    It 'toma host y puerto explicitos y marca loopback para localhost' {
        $e = Get-ParkosCloudEndpoint -Url 'http://localhost:8000'
        $e.Host | Should Be 'localhost'
        $e.Port | Should Be 8000
        $e.IsLoopback | Should Be $true
    }

    It 'https sin puerto usa 443 y http sin puerto usa 80' {
        (Get-ParkosCloudEndpoint -Url 'https://cloud.example.test').Port | Should Be 443
        (Get-ParkosCloudEndpoint -Url 'http://cloud.example.test').Port | Should Be 80
        (Get-ParkosCloudEndpoint -Url 'https://cloud.example.test').IsLoopback | Should Be $false
    }

    It '127.0.0.1 tambien es loopback' {
        (Get-ParkosCloudEndpoint -Url 'http://127.0.0.1:9000').IsLoopback | Should Be $true
    }
}

Describe 'Test-Preflight - conectividad hacia el cloud' {

    function Invoke-PreflightQuiet {
        param([string]$CloudApiUrl, [switch]$RequireMasterKey)
        Test-Preflight -InstallPath "$env:SystemDrive\Parkos" -DataPath (Join-Path $env:TEMP "parkos-pf-$(Get-Random -Maximum 999999)") `
            -CloudApiUrl $CloudApiUrl -RequireMasterKey:$RequireMasterKey
    }

    It 'mide host:puerto del cloud y NO github.com' {
        Mock Write-Host { }
        Mock Get-ParkosMasterKeyProblem { $null }
        Mock Test-NetConnection { $true }
        $null = Invoke-PreflightQuiet -CloudApiUrl 'https://cloud.example.test:8443'
        Assert-MockCalled Test-NetConnection -Scope It -Times 1 -Exactly -ParameterFilter { $ComputerName -eq 'cloud.example.test' -and $Port -eq 8443 }
        Assert-MockCalled Test-NetConnection -Scope It -Times 0 -Exactly -ParameterFilter { $ComputerName -eq 'github.com' }
    }

    It 'cloud remoto inalcanzable BLOQUEA (aparece [FALLO] de conexion)' {
        Mock Write-Host { }
        Mock Get-ParkosMasterKeyProblem { $null }
        Mock Test-NetConnection { $false }
        $result = Invoke-PreflightQuiet -CloudApiUrl 'https://cloud.example.test'
        $result | Should Be $false
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -like '*[[]FALLO[]] Conexion con el servidor Parkos*' }
    }

    It 'cloud en localhost inalcanzable solo AVISA (no bloquea por esa causa)' {
        Mock Write-Host { }
        Mock Get-ParkosMasterKeyProblem { $null }
        Mock Test-NetConnection { $false }
        $null = Invoke-PreflightQuiet -CloudApiUrl 'http://localhost:8000'
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*[[]FALLO[]] Conexion con el servidor Parkos*' }
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -like '*[[]AVISO[]]*PARKOS_CLOUD_API_URL*' }
    }

    It '-RequireMasterKey con clave ausente BLOQUEA y muestra el mensaje accionable' {
        Mock Write-Host { }
        Mock Get-ParkosMasterKeyProblem { 'No se encontro la clave maestra de Parkos en X. Solicitela al equipo de soporte' }
        Mock Test-NetConnection { $true }
        $result = Invoke-PreflightQuiet -CloudApiUrl 'https://cloud.example.test' -RequireMasterKey
        $result | Should Be $false
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -like '*[[]FALLO[]] Clave maestra de Parkos*' }
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -like '*Solicitela al equipo de soporte*' }
    }
}

Describe 'Show-Eula - Enter acepta' {

    It 'muestra el texto y acepta con Enter (respuesta vacia) sin exigir ACEPTO' {
        $script:Unattended = $false
        $eula = Join-Path $TestDrive 'eula.txt'
        Set-Content -Path $eula -Value 'TEXTO DEL EULA'
        Mock Write-Host { }
        Mock Read-Host { '' }
        $accepted = Show-Eula -EulaPath $eula
        $accepted | Should Be $true
        Assert-MockCalled Read-Host -Scope It -Times 1 -Exactly
    }
}

Describe 'Read-InstallPaths - nunca pregunta' {

    It 'devuelve las rutas recibidas sin llamar a Read-Host' {
        $script:Unattended = $false
        Mock Read-Host { throw 'no deberia preguntar nada' }
        $paths = Read-InstallPaths -DefaultInstallPath 'C:\Program Files\Parkos' -DefaultDataPath 'C:\ProgramData\Parkos'
        $paths.InstallPath | Should Be 'C:\Program Files\Parkos'
        $paths.DataPath | Should Be 'C:\ProgramData\Parkos'
        Assert-MockCalled Read-Host -Scope It -Times 0 -Exactly
    }

    It 'una ruta no permitida (C:\Windows) sigue lanzando' {
        $script:Unattended = $false
        { Read-InstallPaths -DefaultInstallPath 'C:\Windows\Parkos' -DefaultDataPath 'C:\ProgramData\Parkos' } | Should Throw 'Ruta de instalacion invalida'
    }
}

Describe 'Read-SucursalUuid - unico dato tipeado' {

    BeforeEach { $script:Unattended = $false }

    It 'un UUID valido recibido por parametro no pregunta nada' {
        Mock Read-Host { throw 'no deberia preguntar' }
        Mock Write-Host { }
        Read-SucursalUuid -Uuid '11111111-2222-3333-4444-555555555555' | Should Be '11111111-2222-3333-4444-555555555555'
        Assert-MockCalled Read-Host -Scope It -Times 0 -Exactly
    }

    It 'vacio: pregunta y acepta un UUID valido (tolera espacios alrededor)' {
        Mock Read-Host { '  AAAAAAAA-bbbb-cccc-dddd-eeeeeeeeeeee  ' }
        Mock Write-Host { }
        Read-SucursalUuid -Uuid '' | Should Be 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        Assert-MockCalled Read-Host -Scope It -Times 1 -Exactly
    }

    It 'entrada invalida: avisa, vuelve a preguntar y termina al recibir un UUID valido' {
        $script:Answers = [System.Collections.Generic.Queue[string]]::new([string[]]@('abc', '11111111-2222-3333-4444-5555555555', '11111111-2222-3333-4444-555555555555'))
        Mock Read-Host { $script:Answers.Dequeue() }
        Mock Write-Host { }
        Read-SucursalUuid -Uuid '' | Should Be '11111111-2222-3333-4444-555555555555'
        Assert-MockCalled Read-Host -Scope It -Times 3 -Exactly
    }

    It 'no adivina: 32 hex sin guiones o con llaves se rechazan (solo forma 8-4-4-4-12)' {
        $script:Answers = [System.Collections.Generic.Queue[string]]::new([string[]]@('11111111222233334444555555555555', '{11111111-2222-3333-4444-555555555555}', '11111111-2222-3333-4444-555555555555'))
        Mock Read-Host { $script:Answers.Dequeue() }
        Mock Write-Host { }
        Read-SucursalUuid -Uuid '' | Should Be '11111111-2222-3333-4444-555555555555'
        Assert-MockCalled Read-Host -Scope It -Times 3 -Exactly
    }

    It 'tras 5 intentos invalidos lanza un mensaje claro en vez de preguntar para siempre' {
        Mock Read-Host { 'no-es-un-uuid' }
        Mock Write-Host { }
        { Read-SucursalUuid -Uuid '' } | Should Throw 'Demasiados intentos'
        Assert-MockCalled Read-Host -Scope It -Times 5 -Exactly
    }

    It 'en -Unattended un UUID invalido lanza sin preguntar' {
        $script:Unattended = $true
        Mock Read-Host { throw 'no deberia preguntar' }
        { Read-SucursalUuid -Uuid 'abc' } | Should Throw 'no tiene formato valido'
        Assert-MockCalled Read-Host -Scope It -Times 0 -Exactly
    }
}

Describe 'ConvertTo-ParkosRelaunchArgs / Get-ParkosRelaunchArgumentList' {

    It 'un literal de PowerShell va entre comillas simples y duplica las comillas simples internas' {
        Format-ParkosPsLiteral -Value 'abc' | Should Be "'abc'"
        Format-ParkosPsLiteral -Value "D:\Mi 'Parkos' Carpeta" | Should Be "'D:\Mi ''Parkos'' Carpeta'"
        Format-ParkosPsLiteral -Value '' | Should Be "''"
    }

    It 'conserva parametros con nombre: string, switch, entero y arreglo' {
        $bound = [ordered]@{ Command = 'Install'; SucursalUuid = '11111111-2222-3333-4444-555555555555'; Unattended = [switch]$true; StopAfterStage = 4; SkipStage = @(2, 7) }
        $argsOut = @(ConvertTo-ParkosRelaunchArgs -BoundParameters $bound)
        ($argsOut -join ' ') | Should Be "-Command 'Install' -SucursalUuid '11111111-2222-3333-4444-555555555555' -Unattended -StopAfterStage 4 -SkipStage 2,7"
    }

    It 'un switch en false viaja como -Nombre:$false y los valores con espacios quedan en un solo literal' {
        $bound = [ordered]@{ Force = [switch]$false; InstallPath = 'D:\Mi Parkos' }
        $argsOut = @(ConvertTo-ParkosRelaunchArgs -BoundParameters $bound)
        $argsOut[0] | Should Be '-Force:$false'
        $argsOut[1] | Should Be '-InstallPath'
        $argsOut[2] | Should Be "'D:\Mi Parkos'"
    }

    It 'MasterKeyPath y PayloadPath relativos se convierten a ruta absoluta (el proceso elevado arranca en otro directorio)' {
        $bound = [ordered]@{ MasterKeyPath = '.\parkos-master.key' }
        $argsOut = @(ConvertTo-ParkosRelaunchArgs -BoundParameters $bound)
        $argsOut[0] | Should Be '-MasterKeyPath'
        $argsOut[1] | Should Be (Format-ParkosPsLiteral -Value ([System.IO.Path]::GetFullPath('.\parkos-master.key')))
    }

    It 'sin parametros devuelve una lista vacia' {
        @(ConvertTo-ParkosRelaunchArgs -BoundParameters @{}).Count | Should Be 0
    }

    It 'la lista de relanzo usa -EncodedCommand, apunta al script y propaga el codigo de salida' {
        $argv = @(Get-ParkosRelaunchArgumentList -ScriptPath 'C:\Program Files\x\parkos-installer.ps1' -OriginalArgs @('-Command', "'Install'"))
        $argv[0] | Should Be '-ExecutionPolicy'
        $argv[2] | Should Be '-EncodedCommand'
        $body = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($argv[3]))
        $body | Should Be "& 'C:\Program Files\x\parkos-installer.ps1' -Command 'Install'; exit `$LASTEXITCODE"
    }

    It 'viaje real de ida y vuelta: un proceso pwsh hijo recibe los mismos valores (espacios, comillas, arreglo) y su ExitCode' {
        $stub = Join-Path $TestDrive 'stub script.ps1'
        $out = Join-Path $TestDrive 'stub.out'
        Set-Content -Path $stub -Value @'
param([string]$Command, [string]$InstallPath, [string]$SucursalUuid, [switch]$Unattended, [int[]]$SkipStage)
"$Command|$InstallPath|$SucursalUuid|$($Unattended.IsPresent)|$($SkipStage -join ',')" | Set-Content -Path $env:PARKOS_STUB_OUT
exit 7
'@
        $env:PARKOS_STUB_OUT = $out
        $tricky = "D:\Mi 'Parkos' `"Carpeta`""
        $bound = [ordered]@{ Command = 'Install'; InstallPath = $tricky; SucursalUuid = '11111111-2222-3333-4444-555555555555'; Unattended = [switch]$true; SkipStage = @(2, 7) }
        $argv = Get-ParkosRelaunchArgumentList -ScriptPath $stub -OriginalArgs @(ConvertTo-ParkosRelaunchArgs -BoundParameters $bound)
        $p = Start-Process pwsh -ArgumentList $argv -Wait -PassThru -WindowStyle Hidden
        Remove-Item Env:\PARKOS_STUB_OUT
        $p.ExitCode | Should Be 7
        (Get-Content $out -Raw).Trim() | Should Be "Install|$tricky|11111111-2222-3333-4444-555555555555|True|2,7"
    }
}

Describe 'Resolve-ParkosInstallMode' {

    It 'por defecto (sin -Menu ni -Unattended) es el flujo guiado' {
        Resolve-ParkosInstallMode | Should Be 'Guided'
    }

    It '-Menu elige el menu interactivo' {
        Resolve-ParkosInstallMode -Menu | Should Be 'Menu'
    }

    It '-Unattended elige la cascada desatendida' {
        Resolve-ParkosInstallMode -Unattended | Should Be 'Unattended'
    }

    It '-Unattended y -Menu juntos son incompatibles' {
        { Resolve-ParkosInstallMode -Unattended -Menu } | Should Throw 'incompatibles'
    }
}

# Etapas de prueba autonomas (mismo patron que ParkosInstaller.Unattended.Tests.ps1).
function New-GuidedFakeStages {
    param([int]$FailingStage = -1)
    $stages = [ordered]@{}
    foreach ($n in 0..8) {
        $actionCode = "`$script:GuidedCallLog += 'action:$n'"
        if ($n -eq $FailingStage) { $actionCode += "; throw 'boom etapa de prueba $n'" }
        $stages["$n"] = @{
            Key      = "stage$n"
            Name     = "Etapa de prueba $n"
            Action   = [scriptblock]::Create($actionCode)
            Rollback = [scriptblock]::Create("`$script:GuidedCallLog += 'rollback:$n'")
        }
    }
    return @{ Stages = $stages; Paths = @{} }
}

function Set-GuidedTestParams {
    param([Parameter(Mandatory)][string]$Root, [switch]$IncludeBuild)
    $script:InstallPath = Join-Path $Root 'Parkos'
    $script:DataPath = Join-Path $Root 'ParkosData'
    $script:Unattended = $false
    $script:EulaAccepted = $false
    $script:Force = $false
    $script:SucursalUuid = '11111111-1111-1111-1111-111111111111'
    $script:CloudApiUrl = 'https://cloud.example.test'
    $script:SkipStage = @()
    $script:StopAfterStage = -1
    $script:MasterKeyPath = ''
    $script:IncludeBuild = [bool]$IncludeBuild
    $script:GuidedCallLog = @()
    $script:OriginalArgs = @('-Command', 'Install')
    # Resultados que leen los Mock de nivel Describe (un Mock declarado dentro
    # de un It se filtra a los It siguientes en este Pester 3.4.0).
    $script:PreflightResult = $true
    $script:PayloadReady = $true
    $script:PayloadBlockers = @()
    $script:SkipStages = @()
    $script:FailingStage = -1
}

Describe 'Invoke-ParkosUnattendedCascade -Guided (flujo del operador de sucursal)' {

    Mock Test-Preflight { $script:PreflightResult -and (@($ExtraProblems).Count -eq 0) }
    Mock Test-ParkosPayloadReady { $script:PayloadReady }
    Mock Get-ParkosRepoRoot { 'C:\repo' }
    Mock Get-ParkosPayloadBuildPlan { [PSCustomObject]@{ Needed = (-not $script:PayloadReady); Switches = @('ApiSucursal'); Reasons = @('prueba') } }
    Mock Get-ParkosPayloadBlockers { $script:PayloadBlockers }
    Mock Get-ParkosStageSkipReason { if ($script:SkipStages -contains $Number) { 'ya hecho' } else { $null } }
    Mock Resolve-ParkosMasterKeySource { '' }
    Mock Show-Eula { $true }
    Mock Write-Host { }
    Mock Read-Host { throw 'el flujo guiado no deberia preguntar nada aqui' }
    Mock Get-ParkosStageDefinitions { New-GuidedFakeStages -FailingStage $script:FailingStage }

    It 'con el payload listo la etapa 0 NO corre y las etapas 1..8 corren en orden -> ExitCode 0' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-happy')
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 0
        ($script:GuidedCallLog -join ',') | Should Be 'action:1,action:2,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It 'el pre-flight exige la clave maestra y usa la URL del cloud resuelta' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-preflight')
        $null = Invoke-ParkosUnattendedCascade -Guided
        Assert-MockCalled Test-Preflight -Scope It -Times 1 -Exactly -ParameterFilter { $RequireMasterKey -and $CloudApiUrl -eq 'https://cloud.example.test' }
    }

    It 'con -IncludeBuild la etapa 0 SI corre' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-build') -IncludeBuild
        $script:PayloadReady = $false
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 0
        ($script:GuidedCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It 'sin payload y SIN toolchain el pre-flight recibe el problema, devuelve ExitCode 2 y no toca el sistema' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-nopayload')
        $script:PayloadReady = $false
        $script:PayloadBlockers = @('falta instalar: uv')
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 2
        $result.Detail | Should Match 'requisitos'
        @($script:GuidedCallLog).Count | Should Be 0
        Assert-MockCalled Test-Preflight -Scope It -Times 1 -Exactly -ParameterFilter { @($ExtraProblems) -contains 'falta instalar: uv' }
        Assert-MockCalled Show-Eula -Scope It -Times 0 -Exactly
    }

    It 'sin payload pero CON toolchain la etapa 0 SI corre sola (construccion automatica) y el resto sigue' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-autobuild')
        $script:PayloadReady = $false
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 0
        ($script:GuidedCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It 'una etapa que ya estaba hecha (idempotencia) se omite y se informa' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-skip')
        Mock Get-ParkosStageSkipReason { if ($Number -eq 7) { 'ya instalada' } else { $null } }
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 0
        ($script:GuidedCallLog -join ',') | Should Be 'action:1,action:2,action:3,action:4,action:5,action:6,action:8'
    }

    It 'si el pre-flight falla (p.ej. sin clave maestra) devuelve ExitCode 2 sin correr etapas' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-pfail')
        $script:PreflightResult = $false
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 2
        @($script:GuidedCallLog).Count | Should Be 0
    }

    It 'una etapa fallida corta, hace rollback y devuelve ExitCode 1 con instruccion para el operador' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-fail')
        $script:FailingStage = 3
        $result = Invoke-ParkosUnattendedCascade -Guided
        $result.ExitCode | Should Be 1
        ($script:GuidedCallLog -join ',') | Should Be 'action:1,action:2,action:3,rollback:3'
    }

    It 'el modo -Unattended sigue corriendo las 9 etapas (compatibilidad con la cascada tecnica)' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'unattended-compat')
        $script:Unattended = $true
        $script:EulaAccepted = $true
        $result = Invoke-ParkosUnattendedCascade
        $result.ExitCode | Should Be 0
        ($script:GuidedCallLog -join ',') | Should Be 'action:0,action:1,action:2,action:3,action:4,action:5,action:6,action:7,action:8'
    }

    It '-Unattended ya no exige -CloudApiUrl (se toma de PARKOS_CLOUD_API_URL o el default)' {
        $threw = $false
        try { Assert-ParkosCascadeParamsValid -Unattended -EulaAccepted } catch { $threw = $true }
        $threw | Should Be $false
    }
}

Describe 'Invoke-ParkosGuidedInstall' {

    It 'eleva y relanza PowerShell 7 conservando los argumentos, y luego corre la cascada guiada' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-entry')
        $script:OriginalArgs = @('-Command', 'Install', '-SucursalUuid', 'x')
        Mock Ensure-PowerShell7 { }
        Mock Request-Elevation { }
        Mock Write-Host { }
        Mock Invoke-ParkosUnattendedCascade { [PSCustomObject]@{ ExitCode = 0; Detail = 'ok' } }
        $result = Invoke-ParkosGuidedInstall
        $result.ExitCode | Should Be 0
        Assert-MockCalled Ensure-PowerShell7 -Scope It -Times 1 -Exactly -ParameterFilter { ($OriginalArgs -join ' ') -eq '-Command Install -SucursalUuid x' }
        Assert-MockCalled Request-Elevation -Scope It -Times 1 -Exactly -ParameterFilter { ($OriginalArgs -join ' ') -eq '-Command Install -SucursalUuid x' }
        Assert-MockCalled Invoke-ParkosUnattendedCascade -Scope It -Times 1 -Exactly -ParameterFilter { $Guided }
    }

    It 'si la cascada falla muestra que hacer (enviar el log a soporte) y propaga el ExitCode' {
        Set-GuidedTestParams -Root (Join-Path $TestDrive 'guided-entry-fail')
        Mock Ensure-PowerShell7 { }
        Mock Request-Elevation { }
        Mock Write-Host { }
        Mock Invoke-ParkosUnattendedCascade { [PSCustomObject]@{ ExitCode = 1; Detail = 'Etapa 3 fallo' } }
        $result = Invoke-ParkosGuidedInstall
        $result.ExitCode | Should Be 1
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -like '*equipo de soporte*' }
    }
}

# Ejecutar con: Invoke-Pester -Path installer/tests/ParkosInstaller.Guided.Tests.ps1
