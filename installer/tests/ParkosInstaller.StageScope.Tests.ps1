# Tests del scope de los Action/Rollback de Get-ParkosStageDefinitions.
#
# Regresion: los Action/Rollback de la fabrica NO son closures - los locals
# de la fabrica ($envFilePath, $pgInstallPath, $nssmPath, ...) ya no existen
# cuando el scriptblock corre (`& $Action` en Invoke-TuiStep / la cascada), y
# bajo Set-StrictMode -Version Latest eso tiraba "variable no establecida"
# antes de llegar al trabajo real de cada etapa.
#
# Estrategia: se stubean con Mock todos los comandos pesados (Postgres, NSSM,
# msiexec, build) y se corre cada Action/Rollback bajo StrictMode. Lo unico
# que se afirma es que NINGUNA etapa tira un error de variable no
# establecida; cualquier otro error (p.ej. un exe inexistente) es aceptable
# porque ya es "trabajo real" de la etapa. Pester 3.4.0: `Should Throw`/
# `Should Not Throw` sin substring de mensaje no evalua - se usa -match.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

$script:VarErrorPattern = 'no se ha establecido|has not been set|cannot be retrieved|No se puede recuperar la variable'

function Invoke-StageBlock {
    param([Parameter(Mandatory)][scriptblock]$Block)
    Set-StrictMode -Version Latest
    try { & $Block | Out-Null; return '' } catch { return $_.Exception.Message }
}

Describe 'Get-ParkosStageDefinitions - scope de Action/Rollback' {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-stagescope-' + [guid]::NewGuid().ToString('N'))

    BeforeEach {
        New-Item -ItemType Directory -Path (Join-Path $tmp 'payload\apps') -Force | Out-Null
        $script:PayloadRoot = Join-Path $tmp 'payload'
        $script:StageStatus = @{ db = [ParkosStageState]::Ok; migrate = [ParkosStageState]::Ok }
        $script:port = $null
        $script:apiPort = $null
        $script:roles = $null
        $script:PostgresInstallMethod = $null

        Mock Invoke-SourceUpdateAndBuild { }
        Mock Test-PostgresPorts { 5432 }
        Mock Test-ApiPort { 8000 }
        Mock New-ParkosDerivedPassword { 'stub-pass' }
        Mock Install-Postgres { 'stub' }
        Mock Initialize-DatabaseRoles { @{ AppPassword = 'a'; SuperuserPassword = 's' } }
        Mock Ensure-ServiceAccount { }
        Mock New-JwtSigningKey { }
        Mock Test-JwtSecretGate { $true }
        Mock Get-OrCreateParkosEnvCert { }
        Mock Write-RuntimeEnvFile { }
        Mock Set-MachineApiOrigin { }
        Mock Install-PgPartman { }
        Mock Register-PgPartmanMaintenance { }
        Mock Invoke-MigrationsAndSeed { }
        Mock Update-SucursalUuidInEnvFile { }
        Mock Invoke-CatalogSeed { }
        Mock Copy-ServiceBundle { 'C:\stub\svc.exe' }
        Mock Install-ApiService { }
        Mock Install-JobService { }
        Mock Wait-ForApiHealth { $true }
        Mock Wait-ForSyncPollCycle { $true }
        Mock Install-Electron { }
        Mock Test-PostInstallation { }
        Mock Install-ManagementModule { }
        Mock Get-EnvFilePostgresPort { 5432 }
        Mock Start-Process { }
    }

    AfterEach {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        $script:PostgresInstallMethod = $null
    }

    function New-Defs {
        Get-ParkosStageDefinitions -InstallPath (Join-Path $tmp 'install') -DataPath (Join-Path $tmp 'data') `
            -SucursalUuid '00000000-0000-0000-0000-000000000001' -CloudApiUrl 'https://cloud.invalid'
    }

    It 'ningun Action (etapas 0-8, en orden) tira un error de variable no establecida bajo StrictMode' {
        $defs = New-Defs
        $failures = @()
        foreach ($n in 0..8) {
            $stage = $defs.Stages["$n"]
            $msg = Invoke-StageBlock -Block $stage.Action
            if ($msg -match $script:VarErrorPattern) { $failures += "etapa ${n}: $msg" }
        }
        ($failures -join '; ') | Should Be ''
    }

    It 'ningun Rollback tira un error de variable no establecida bajo StrictMode' {
        $defs = New-Defs
        $failures = @()
        foreach ($n in 0..8) {
            $stage = $defs.Stages["$n"]
            if ($null -eq $stage.Rollback) { continue }
            $msg = Invoke-StageBlock -Block $stage.Rollback
            if ($msg -match $script:VarErrorPattern) { $failures += "rollback ${n}: $msg" }
        }
        ($failures -join '; ') | Should Be ''
    }

    It 'las etapas comparten estado via $script: ($script:port y $script:roles llegan a la etapa 2)' {
        $defs = New-Defs
        $msg = Invoke-StageBlock -Block $defs.Stages['1'].Action
        $msg | Should Be ''
        $script:port | Should Be 5432
        $script:roles.AppPassword | Should Be 'a'
        $msg = Invoke-StageBlock -Block $defs.Stages['2'].Action
        $msg | Should Be ''
        Assert-MockCalled Invoke-MigrationsAndSeed -Times 1 -ParameterFilter { $Port -eq 5432 -and $Roles.AppPassword -eq 'a' } -Scope It
    }

    It 'la etapa 8 sin etapa 1 previa recupera el puerto del .env en vez de pasar $null/0' {
        $defs = New-Defs
        $script:port = $null
        $msg = Invoke-StageBlock -Block $defs.Stages['8'].Action
        $msg | Should Be ''
        Assert-MockCalled Get-EnvFilePostgresPort -Times 1 -Scope It
        Assert-MockCalled Test-PostInstallation -Times 1 -ParameterFilter { $Port -eq 5432 -and $EnvFilePath -like '*secrets\.env' } -Scope It
    }

    It 'la etapa 8 usa $script:port cuando la etapa 1 ya corrio' {
        $defs = New-Defs
        $script:port = 5499
        $msg = Invoke-StageBlock -Block $defs.Stages['8'].Action
        $msg | Should Be ''
        Assert-MockCalled Get-EnvFilePostgresPort -Times 0 -Scope It
        Assert-MockCalled Test-PostInstallation -Times 1 -ParameterFilter { $Port -eq 5499 } -Scope It
    }
}
