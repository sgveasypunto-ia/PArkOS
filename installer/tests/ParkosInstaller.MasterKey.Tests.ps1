# Tests de la clave maestra versionada en el repositorio (decision del
# proyecto: los testers corren el instalador completo sin pedir nada a soporte).
#
#   - Resolve-ParkosMasterKey: orden param > env > repo (origen param|env|repo).
#   - Test-Preflight: aviso amarillo cuando se usa la clave del repo; -Produccion
#     la rechaza y acepta param/env; el tamano minimo sigue aplicando.
#   - Write-ParkosInstallSummary repite el aviso.
#   - build-release.ps1 resuelve igual (analisis estatico del script).
#   - Ningun log/resumen/aviso contiene los bytes de la clave.
#
# Pester 3.4.0: todo `Should Throw` lleva substring de mensaje.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function New-FakeKeyFile {
    param([string]$Dir, [string]$Name, [byte[]]$Bytes)
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $p = Join-Path $Dir $Name
    [System.IO.File]::WriteAllBytes($p, $Bytes)
    return $p
}

# Bytes de prueba reconocibles (NO son la clave del repositorio).
$script:FakeBytes = [byte[]](101..140)
$script:FakeText = [Convert]::ToBase64String($script:FakeBytes)

Describe 'Resolve-ParkosMasterKey: param > env > repo' {

    BeforeEach {
        Set-ParkosMasterKeyOverride -SourcePath ''
        $script:PayloadRoot = Join-Path $TestDrive 'payload'
        $script:EnvValue = $null
    }
    Mock Get-ParkosEnvironmentValue { $script:EnvValue }

    It 'sin param ni env usa la copia del repositorio (origen repo)' {
        $r = Resolve-ParkosMasterKey
        $r.Source | Should Be 'repo'
        $r.Path | Should Be (Join-Path $script:PayloadRoot 'security\parkos-master.key')
    }

    It 'PARKOS_MASTER_KEY_FILE gana sobre el repositorio (origen env)' {
        $script:EnvValue = 'D:\ci\master.key'
        $r = Resolve-ParkosMasterKey
        $r.Source | Should Be 'env'
        $r.Path | Should Be 'D:\ci\master.key'
    }

    It '-MasterKeyPath explicito gana sobre env y repo (origen param)' {
        $script:EnvValue = 'D:\ci\master.key'
        $r = Resolve-ParkosMasterKey -Explicit 'E:\otra.key'
        $r.Source | Should Be 'param'
        $r.Path | Should Be 'E:\otra.key'
    }

    It 'el override de la ejecucion (param ya validado) gana sobre env' {
        $k = New-FakeKeyFile -Dir (Join-Path $TestDrive 'ov') -Name 'k.key' -Bytes $script:FakeBytes
        Mock Write-Host { }
        $script:EnvValue = 'D:\ci\master.key'
        Set-ParkosMasterKeyOverride -SourcePath $k -Source 'param'
        (Resolve-ParkosMasterKey).Source | Should Be 'param'
        Set-ParkosMasterKeyOverride -SourcePath ''
        (Resolve-ParkosMasterKey).Source | Should Be 'env'
    }

    It 'Get-ParkosMasterKeyDefaultPath devuelve la ruta resuelta' {
        Get-ParkosMasterKeyDefaultPath | Should Be (Join-Path $script:PayloadRoot 'security\parkos-master.key')
    }
}

Describe 'Get-ParkosMasterKeyProblem sobre la clave del repositorio' {

    BeforeEach {
        Set-ParkosMasterKeyOverride -SourcePath ''
        $script:PayloadRoot = Join-Path $TestDrive 'pl-problem'
        $script:EnvValue = $null
    }
    Mock Get-ParkosEnvironmentValue { $script:EnvValue }

    It 'copia del repo ausente (paquete danado): mensaje accionable' {
        Get-ParkosMasterKeyProblem | Should Match 'git checkout -- installer/payload/security'
    }

    It 'copia del repo con menos de 32 bytes: el tamano minimo sigue aplicando' {
        [void](New-FakeKeyFile -Dir (Join-Path $script:PayloadRoot 'security') -Name 'parkos-master.key' -Bytes ([byte[]](1..31)))
        Get-ParkosMasterKeyProblem | Should Match 'demasiado corta \(31 bytes; minimo 32\)'
    }

    It 'copia del repo valida: sin problema' {
        [void](New-FakeKeyFile -Dir (Join-Path $script:PayloadRoot 'security') -Name 'parkos-master.key' -Bytes $script:FakeBytes)
        Get-ParkosMasterKeyProblem | Should BeNullOrEmpty
    }
}

Describe 'Test-Preflight: aviso y -Produccion segun el origen de la clave' {

    function Invoke-KeyPreflight {
        param([switch]$Produccion, [switch]$RequireMasterKey)
        Test-Preflight -InstallPath "$env:SystemDrive\Parkos" -DataPath (Join-Path $TestDrive "pf-$(Get-Random -Maximum 999999)") `
            -CloudApiUrl 'http://localhost:8000' -RequireMasterKey:$RequireMasterKey -Produccion:$Produccion
    }

    Mock Write-Host { }
    Mock Test-NetConnection { $true }
    Mock Test-WindowsVersion { $true }
    Mock Get-ParkosEnvironmentValue { $script:EnvValue }
    Mock Get-ParkosMasterKeyProblem { $null }

    BeforeEach {
        Set-ParkosMasterKeyOverride -SourcePath ''
        $script:EnvValue = $null
    }

    It 'origen repo: imprime el [AVISO] amarillo y NO bloquea por la clave' {
        $null = Invoke-KeyPreflight -RequireMasterKey
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter {
            $Object -eq (Get-ParkosRepoMasterKeyNotice) -and $ForegroundColor -eq 'Yellow'
        }
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*[[]FALLO[]] Clave maestra*' }
    }

    It 'el texto del aviso es el acordado' {
        Get-ParkosRepoMasterKeyNotice | Should Be '[AVISO] Usando la clave maestra versionada en el repositorio (solo pruebas/QA). Cualquiera con acceso al repositorio puede derivar las contrasenas de Postgres. Para produccion entregue su propia clave con -MasterKeyPath o PARKOS_MASTER_KEY_FILE.'
    }

    It 'origen env: NO hay aviso de clave del repositorio' {
        $script:EnvValue = 'D:\ci\master.key'
        $null = Invoke-KeyPreflight -RequireMasterKey
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*clave maestra versionada en el repositorio*' }
    }

    It 'origen param (override): NO hay aviso de clave del repositorio' {
        $k = New-FakeKeyFile -Dir (Join-Path $TestDrive 'pfp') -Name 'k.key' -Bytes $script:FakeBytes
        Set-ParkosMasterKeyOverride -SourcePath $k -Source 'param'
        $null = Invoke-KeyPreflight -RequireMasterKey
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*clave maestra versionada en el repositorio*' }
    }

    It '-Produccion con clave del repo: BLOQUEA con [FALLO] y mensaje claro (sin aviso amarillo)' {
        $ok = Invoke-KeyPreflight -Produccion -RequireMasterKey
        $ok | Should Be $false
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter { $Object -like '*[[]FALLO[]] Clave maestra*' }
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter { $Object -like '*-Produccion no admite la clave maestra versionada*' }
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*[[]AVISO[]] Usando la clave maestra*' }
    }

    It '-Produccion con clave env: no bloquea por la clave' {
        $script:EnvValue = 'D:\ci\master.key'
        $null = Invoke-KeyPreflight -Produccion -RequireMasterKey
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*[[]FALLO[]] Clave maestra*' }
    }

    It '-Produccion con clave param (override): no bloquea por la clave' {
        $k = New-FakeKeyFile -Dir (Join-Path $TestDrive 'pfq') -Name 'k.key' -Bytes $script:FakeBytes
        Set-ParkosMasterKeyOverride -SourcePath $k -Source 'param'
        $null = Invoke-KeyPreflight -Produccion -RequireMasterKey
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*[[]FALLO[]] Clave maestra*' }
    }
}

Describe 'Test-Preflight: clave del repo ausente (paquete danado) bloquea en guiado' {

    Mock Write-Host { }
    Mock Test-NetConnection { $true }
    Mock Test-WindowsVersion { $true }
    Mock Get-ParkosEnvironmentValue { $null }

    It 'sin ningun archivo de clave: [FALLO] con la pista de git checkout' {
        Set-ParkosMasterKeyOverride -SourcePath ''
        $script:PayloadRoot = Join-Path $TestDrive 'pl-empty'
        $ok = Test-Preflight -InstallPath "$env:SystemDrive\Parkos" -DataPath (Join-Path $TestDrive 'pf-empty') `
            -CloudApiUrl 'http://localhost:8000' -RequireMasterKey
        $ok | Should Be $false
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter { $Object -like '*git checkout -- installer/payload/security*' }
    }
}

Describe 'Write-ParkosInstallSummary: repite el aviso solo con la clave del repo' {

    Mock Write-Host { }
    Mock Get-EnvFilePostgresPort { 5433 }
    Mock Read-ParkosEnvLines { @() }
    Mock Get-ParkosEnvironmentValue { $script:EnvValue }

    BeforeEach {
        Set-ParkosMasterKeyOverride -SourcePath ''
        $script:EnvValue = $null
    }

    It 'origen repo: el resumen incluye el aviso' {
        Write-ParkosInstallSummary -InstallPath 'C:\P' -DataPath 'C:\D'
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter { $Object -eq (Get-ParkosRepoMasterKeyNotice) }
    }

    It 'origen env: el resumen NO incluye el aviso' {
        $script:EnvValue = 'D:\ci\master.key'
        Write-ParkosInstallSummary -InstallPath 'C:\P' -DataPath 'C:\D'
        Assert-MockCalled Write-Host -Scope It -Times 0 -Exactly -ParameterFilter { $Object -like '*clave maestra versionada*' }
    }
}

Describe 'Ningun texto emitido contiene los bytes de la clave' {

    It 'avisos, mensajes de problema y de Produccion no contienen la clave ni su base64' {
        $dir = Join-Path $TestDrive 'nobytes'
        $script:PayloadRoot = $dir
        Set-ParkosMasterKeyOverride -SourcePath ''
        [void](New-FakeKeyFile -Dir (Join-Path $dir 'security') -Name 'parkos-master.key' -Bytes $script:FakeBytes)
        $texts = @(
            (Get-ParkosRepoMasterKeyNotice)
            (Get-ParkosProduccionRepoKeyMessage)
            (Get-ParkosMasterKeyProblem)
            (Get-ParkosMasterKeyProblem -MasterKeyPath (Join-Path $dir 'no-existe.key'))
        ) -join "`n"
        $texts.Contains($script:FakeText) | Should Be $false
        $texts.Contains([System.Text.Encoding]::Latin1.GetString($script:FakeBytes)) | Should Be $false
    }

    It 'la cascada guiada registra el ORIGEN de la clave y nunca sus bytes' {
        $src = Get-Content -LiteralPath $installerScript -Raw
        $src | Should Match 'Origen de la clave maestra: \$\(\(Resolve-ParkosMasterKey\)\.Source\)'
    }

    It 'el log real de una cascada con clave de prueba no contiene la clave' {
        $dir = Join-Path $TestDrive 'logcheck'
        $keyFile = New-FakeKeyFile -Dir $dir -Name 'k.key' -Bytes $script:FakeBytes
        $logPath = Join-Path $dir 'run.log'
        Mock Write-Host { }
        Set-ParkosMasterKeyOverride -SourcePath $keyFile -Source 'param'
        Write-ParkosInstallerLog -LogPath $logPath -Level 'INIT' -Message "Origen de la clave maestra: $((Resolve-ParkosMasterKey).Source) (el contenido de la clave nunca se registra)"
        Set-ParkosMasterKeyOverride -SourcePath ''
        $log = Get-Content -LiteralPath $logPath -Raw
        $log | Should Match 'Origen de la clave maestra: param'
        $log.Contains($script:FakeText) | Should Be $false
    }
}

Describe 'Clave versionada en el repositorio (artefacto real)' {

    It 'installer/payload/security/parkos-master.key existe y mide >= 32 bytes' {
        $p = Join-Path $script:RepoRoot 'installer\payload\security\parkos-master.key'
        (Test-Path -LiteralPath $p -PathType Leaf) | Should Be $true
        ((Get-Item -LiteralPath $p).Length -ge 32) | Should Be $true
    }
}

Describe 'build-release.ps1 resuelve la clave igual (param > env > repo, sin copiar)' {

    $src = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\build-release.ps1') -Raw

    It 'usa param, luego PARKOS_MASTER_KEY_FILE, luego la copia del repositorio' {
        $src | Should Match "(?s)function Get-MasterKeyPayload.*origin = 'param'.*PARKOS_MASTER_KEY_FILE.*origin = 'env'.*origin = 'repo'"
    }

    It 'ya no copia una clave sobre payload\security (no ensucia el archivo versionado)' {
        $body = ($src -split 'function Get-MasterKeyPayload', 2)[1]
        $body = ($body -split 'function Get-PowerShell7Msi', 2)[0]
        $body | Should Not Match 'Copy-Item'
    }

    It 'falla con mensaje accionable si falta la copia del repositorio' {
        $src | Should Match 'git checkout -- installer/payload/security'
    }
}

Describe 'Declaracion de parametros' {

    It '-Produccion es un switch del instalador' {
        $src = Get-Content -LiteralPath $installerScript -Raw
        $src | Should Match '\[switch\]\$Produccion'
    }
}
