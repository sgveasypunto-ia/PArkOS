$moduleManifestPath = Join-Path $PSScriptRoot '..\payload\management\Parkos.psd1'

Describe 'Parkos module manifest' {

    Import-Module $moduleManifestPath -Force

    $expectedFunctions = @(
        'Get-ParkosHealth', 'Repair-ParkosInstall', 'Uninstall-Parkos',
        'Export-ParkosDiagnostics', 'Register-ParkosBackupTask',
        'Test-CrashRecovery', 'Get-ParkosVersion', 'Test-ParkosSecretsAcl'
    )

    It 'exports exactly the 8 expected public functions' {
        $exported = Get-Command -Module Parkos
        $exported.Count | Should Be 8
    }

    foreach ($name in $expectedFunctions) {
        It "exports $name" {
            Get-Command $name -Module Parkos | Should Not BeNullOrEmpty
        }
    }

    It "reports ModuleVersion '1.0.0'" {
        (Get-Module Parkos).Version.ToString() | Should Be '1.0.0'
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Parkos placeholder functions' {

    Import-Module $moduleManifestPath -Force

    It 'Repair-ParkosInstall does not throw' {
        { Repair-ParkosInstall } | Should Not Throw
    }

    # Export-ParkosDiagnostics ya NO es un placeholder (PR7) - su cobertura
    # real vive en el Describe 'Export-ParkosDiagnostics' mas abajo, con los
    # mocks necesarios para no tocar disco/red real (Compress-Archive real
    # hacia el Escritorio real, psql.exe real, etc.).

    # Register-ParkosBackupTask ya NO es un placeholder (PR8) - su cobertura
    # real vive en los Describe 'Get-ParkosBackupRetentionPlan' y
    # 'Register-ParkosBackupTask' mas abajo. Llamarla sin mocks aca haria
    # throw de verdad (requiere admin/Postgres/svc-parkos reales), asi que
    # ya no aplica un "does not throw" generico como el resto de este
    # bloque.

    It 'Get-ParkosVersion does not throw' {
        { Get-ParkosVersion } | Should Not Throw
    }

    It 'Test-ParkosSecretsAcl does not throw' {
        { Test-ParkosSecretsAcl } | Should Not Throw
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Import-ParkosEnvFile (Fase 27/DEC-INST-40: CMS + texto plano)' {

    Import-Module $moduleManifestPath -Force

    # Funcion PRIVADA script:-scoped (no exportada) - se invoca via
    # scriptblock inyectado en el modulo (operador de llamada sobre el
    # PSModuleInfo), mismo patron ya usado en este archivo para
    # Test-ParkosDiagnosticsContainSecrets/Get-ParkosBackupRetentionPlan:
    # InModuleScope (Pester 3.4.0) no cierra sobre variables locales del It
    # que lo invoca de forma confiable.
    function Invoke-ImportEnvFile {
        param([string]$Path)
        & (Get-Module Parkos) { param($p) Import-ParkosEnvFile -Path $p } $Path
    }

    # Test de REGRESION explicito (Tarea 3 del PR): un .env en texto plano
    # SIN el encabezado CMS debe seguir parseando exactamente igual que
    # antes de este cambio - los tests de PR2/PR3/PR7/PR8 que dependen de
    # Import-ParkosEnvFile (todos mockeados a nivel Describe, nunca llaman a
    # la implementacion real) no se tocan; este test cubre la implementacion
    # real directamente.
    It 'parsea un .env en texto plano (sin encabezado CMS) igual que antes' {
        $envPath = Join-Path $env:TEMP "parkos-envfile-plain-$(Get-Random -Maximum 999999).env"
        Set-Content -Path $envPath -Value @(
            'PARKOS_DEPLOY=branch'
            'PORT=8000'
            'PARKOS_DB_URL=postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
        )
        try {
            $envMap = Invoke-ImportEnvFile -Path $envPath
            $envMap['PORT'] | Should Be '8000'
            $envMap['PARKOS_DEPLOY'] | Should Be 'branch'
            $envMap['PARKOS_DB_URL'] | Should Be 'postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
        } finally {
            Remove-Item -Path $envPath -Force -ErrorAction SilentlyContinue
        }
    }

    It 'parsea un .env cifrado con CMS (Unprotect-CmsMessage mockeado) devolviendo las mismas keys que el modo texto plano' {
        $envPath = Join-Path $env:TEMP "parkos-envfile-cms-$(Get-Random -Maximum 999999).env"
        Set-Content -Path $envPath -Value @(
            '-----BEGIN CMS-----'
            'QmFzZTY0T3BhY29TaW11bGFkbw=='
            '-----END CMS-----'
        )
        Mock Unprotect-CmsMessage -ModuleName Parkos {
            return @(
                'PARKOS_DEPLOY=branch'
                'PORT=8000'
                'PARKOS_DB_URL=postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
            ) -join "`r`n"
        }
        try {
            $envMap = Invoke-ImportEnvFile -Path $envPath
            $envMap['PORT'] | Should Be '8000'
            $envMap['PARKOS_DEPLOY'] | Should Be 'branch'
            $envMap['PARKOS_DB_URL'] | Should Be 'postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
            Assert-MockCalled Unprotect-CmsMessage -ModuleName Parkos -Times 1 -Exactly -Scope It
        } finally {
            Remove-Item -Path $envPath -Force -ErrorAction SilentlyContinue
        }
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Get-ParkosHealth' {

    Import-Module $moduleManifestPath -Force

    # Dependencias externas comunes a los 3 escenarios - mockeadas una sola
    # vez a nivel Describe. Cada It solo sobreescribe lo que necesita variar
    # (Get-Service / Invoke-WebRequest) para su escenario puntual.
    Mock Import-ParkosEnvFile -ModuleName Parkos {
        return @{
            PORT          = '8000'
            PARKOS_DB_URL = 'postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
        }
    }
    Mock Get-PSDrive -ModuleName Parkos {
        [PSCustomObject]@{ Name = 'C'; Free = 90GB; Used = 10GB }
    }
    Mock Invoke-ParkosDoctorExe -ModuleName Parkos {
        [PSCustomObject]@{ env_status = 'ok'; db_connectivity = 'ok'; jwt_key_path_exists = $true }
    }

    It 'returns ExitCode 0 when the 6 checks pass' {
        Mock Test-NetConnection -ModuleName Parkos { $true }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosApiSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosApiSucursal'; Status = 'Running' }
        }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosJobSyncSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosJobSyncSucursal'; Status = 'Running' }
        }
        Mock Invoke-WebRequest -ModuleName Parkos {
            [PSCustomObject]@{ StatusCode = 200 }
        }

        $result = Get-ParkosHealth
        $result.ExitCode | Should Be 0
    }

    It 'returns ExitCode 2 when /health does not respond with 200' {
        Mock Test-NetConnection -ModuleName Parkos { $true }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosApiSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosApiSucursal'; Status = 'Running' }
        }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosJobSyncSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosJobSyncSucursal'; Status = 'Running' }
        }
        Mock Invoke-WebRequest -ModuleName Parkos {
            [PSCustomObject]@{ StatusCode = 500 }
        }

        $result = Get-ParkosHealth
        $result.ExitCode | Should Be 2
    }

    It 'returns ExitCode 1 when only the sync service is stopped' {
        Mock Test-NetConnection -ModuleName Parkos { $true }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosApiSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosApiSucursal'; Status = 'Running' }
        }
        Mock Get-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'ParkosJobSyncSucursal' } {
            [PSCustomObject]@{ Name = 'ParkosJobSyncSucursal'; Status = 'Stopped' }
        }
        Mock Invoke-WebRequest -ModuleName Parkos {
            [PSCustomObject]@{ StatusCode = 200 }
        }

        $result = Get-ParkosHealth
        $result.ExitCode | Should Be 1
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Test-CrashRecovery' {

    Import-Module $moduleManifestPath -Force

    It 'throws a clear error when postgresql.conf has fsync off' {
        Mock Test-IsAdmin -ModuleName Parkos { $true }
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-Content -ModuleName Parkos {
            @('fsync = off', 'full_page_writes = on')
        }

        { Test-CrashRecovery } | Should Throw 'Configuracion insegura'
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Repair-ParkosInstall' {

    Import-Module $moduleManifestPath -Force

    # Mocks comunes a todo el Describe - cada It sobreescribe solo lo que
    # necesita variar para su escenario puntual (mismo patron que el
    # Describe de Get-ParkosHealth mas arriba). Test-Path se mockea en
    # "todo false" por defecto para que ningun check basado en archivos
    # reales (manifest, nssm.exe, releases\, backups\) dependa del estado
    # real de la maquina donde corren los tests.
    Mock Test-IsAdmin -ModuleName Parkos { $true }
    Mock Test-ParkosSecretsAcl -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 0; Detail = 'ACL ok' } }
    Mock Test-ParkosDatabaseIntegrity -ModuleName Parkos { $true }
    Mock Test-Path -ModuleName Parkos { $false }
    Mock Import-ParkosEnvFile -ModuleName Parkos {
        return @{
            PORT          = '8000'
            PARKOS_DB_URL = 'postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos'
        }
    }
    Mock Export-ParkosDiagnostics -ModuleName Parkos { }
    Mock Start-Service -ModuleName Parkos { }
    Mock Start-Sleep -ModuleName Parkos { }
    Mock Invoke-ParkosNssm -ModuleName Parkos { }
    Mock Set-ParkosSecretsAcl -ModuleName Parkos { }
    Mock Read-Host -ModuleName Parkos { 's' }
    Mock Invoke-WebRequest -ModuleName Parkos { [PSCustomObject]@{ StatusCode = 200 } }

    It 'does nothing and returns ExitCode 0 when Get-ParkosHealth is already OK' {
        Mock Get-ParkosHealth -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 0; Checks = @{} } }

        $result = Repair-ParkosInstall -Force
        $result.ExitCode | Should Be 0
        $result.Scenarios.Count | Should Be 0
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Start-Service -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'detects E1 (servicio faltante) and calls nssm install' {
        Mock Get-ParkosHealth -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 2; Checks = @{} } }
        Mock Get-Service -ModuleName Parkos { $null }
        Mock Test-Path -ModuleName Parkos -ParameterFilter { $Path -like '*nssm.exe' } { $true }

        $result = Repair-ParkosInstall -Force
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -ParameterFilter { $Arguments -contains 'install' } -Scope It
        ($result.Scenarios | Where-Object { $_.Scenario -eq 'E1' }) | Should Not BeNullOrEmpty
    }

    It 'escalates to E7 (ExitCode 3) when the 3 start retries are exhausted, and calls Export-ParkosDiagnostics' {
        Mock Get-ParkosHealth -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 2; Checks = @{} } }
        Mock Get-Service -ModuleName Parkos { [PSCustomObject]@{ Status = 'Stopped' } }
        Mock Invoke-WebRequest -ModuleName Parkos { [PSCustomObject]@{ StatusCode = 500 } }
        Mock Test-Path -ModuleName Parkos -ParameterFilter { $Path -like '*nssm.exe' } { $true }

        $result = Repair-ParkosInstall -Force
        $result.ExitCode | Should Be 3
        ($result.Scenarios | Where-Object { $_.Scenario -eq 'E7' }) | Should Not BeNullOrEmpty
        Assert-MockCalled Export-ParkosDiagnostics -ModuleName Parkos -Times 1 -Exactly -Scope It
    }

    It 'aborts immediately with ExitCode 3 on E6 (base de datos corrupta) without repairing other scenarios' {
        Mock Get-ParkosHealth -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 2; Checks = @{} } }
        Mock Get-Service -ModuleName Parkos { [PSCustomObject]@{ Status = 'Running' } }
        Mock Test-Path -ModuleName Parkos -ParameterFilter { $Path -like '*secrets\.env' } { $true }
        Mock Test-ParkosDatabaseIntegrity -ModuleName Parkos { $false }

        $result = Repair-ParkosInstall -Force
        $result.ExitCode | Should Be 3
        $result.Scenarios.Count | Should Be 1
        $result.Scenarios[0].Scenario | Should Be 'E6'
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Set-ParkosSecretsAcl -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It '-WhatIf does not execute any real auto-fix' {
        Mock Get-ParkosHealth -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 2; Checks = @{} } }
        Mock Get-Service -ModuleName Parkos { $null }
        Mock Test-Path -ModuleName Parkos -ParameterFilter { $Path -like '*nssm.exe' } { $true }
        # Reset explicito: Mock no se resetea entre It dentro del mismo
        # Describe (a diferencia de Assert-MockCalled -Scope It) - sin esto
        # este test heredaria el $false que dejo el test de E6 de arriba.
        Mock Test-ParkosDatabaseIntegrity -ModuleName Parkos { $true }

        $result = Repair-ParkosInstall -WhatIf
        Assert-MockCalled Start-Service -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -Times 0 -Exactly -Scope It
        ($result.Scenarios | Where-Object { $_.Scenario -eq 'E1' }).WouldFix | Should Be $true
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Test-ParkosSecretsAcl' {

    Import-Module $moduleManifestPath -Force

    It 'returns ExitCode 0 when only Administrators/SYSTEM have access' {
        Mock Get-Acl -ModuleName Parkos {
            [PSCustomObject]@{
                Access = @(
                    [PSCustomObject]@{ IdentityReference = 'BUILTIN\Administrators' }
                    [PSCustomObject]@{ IdentityReference = 'NT AUTHORITY\SYSTEM' }
                )
            }
        }

        $result = Test-ParkosSecretsAcl
        $result.ExitCode | Should Be 0
    }

    It 'returns ExitCode 1 when an extra principal has access' {
        Mock Get-Acl -ModuleName Parkos {
            [PSCustomObject]@{
                Access = @(
                    [PSCustomObject]@{ IdentityReference = 'BUILTIN\Administrators' }
                    [PSCustomObject]@{ IdentityReference = 'NT AUTHORITY\SYSTEM' }
                    [PSCustomObject]@{ IdentityReference = 'CONTOSO\jdoe' }
                )
            }
        }

        $result = Test-ParkosSecretsAcl
        $result.ExitCode | Should Be 1
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Uninstall-Parkos' {

    Import-Module $moduleManifestPath -Force

    # Mocks comunes a todo el Describe - mismo patron que el Describe de
    # Repair-ParkosInstall: cada It sobreescribe lo que necesita variar.
    # Remove-Item SIEMPRE mockeado (nunca debe tocar disco de verdad en un
    # test, ni siquiera el propio directorio del modulo que Uninstall-Parkos
    # borra al final).
    Mock Test-IsAdmin -ModuleName Parkos { $true }
    Mock Invoke-ParkosNssm -ModuleName Parkos { }
    Mock Unregister-ScheduledTask -ModuleName Parkos { }
    Mock Start-Process -ModuleName Parkos { }
    Mock Get-ItemProperty -ModuleName Parkos { $null }
    Mock Get-LocalUser -ModuleName Parkos { $null }
    Mock Remove-LocalUser -ModuleName Parkos { }
    Mock Get-Service -ModuleName Parkos { $null }
    Mock Stop-Service -ModuleName Parkos { }
    Mock Get-ScheduledTask -ModuleName Parkos { $null }
    Mock Remove-Item -ModuleName Parkos { }
    Mock Test-Path -ModuleName Parkos { $false }

    It 'cancels without any mutation when the confirmation word is wrong (no -PurgeData)' {
        Mock Read-Host -ModuleName Parkos { 'lo que sea' }

        $result = Uninstall-Parkos

        $result.ExitCode | Should Be 1
        $result.Detail | Should Be 'Cancelado por el operador.'
        Assert-MockCalled Remove-Item -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Unregister-ScheduledTask -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Start-Process -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Remove-LocalUser -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'removes services/task/MSI/module but preserves data folders when confirmed without -PurgeData' {
        Mock Read-Host -ModuleName Parkos { 'DESINSTALAR' }
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-ItemProperty -ModuleName Parkos {
            [PSCustomObject]@{ DisplayName = 'Parkos web_sucursal'; PSChildName = '{11111111-2222-3333-4444-555555555555}' }
        }

        $result = Uninstall-Parkos

        $result.ExitCode | Should Be 0
        Assert-MockCalled Invoke-ParkosNssm -ModuleName Parkos -ParameterFilter { $Arguments -contains 'remove' } -Scope It
        Assert-MockCalled Unregister-ScheduledTask -ModuleName Parkos -ParameterFilter { $TaskName -eq 'ParkosPgPartmanMaintenance' } -Scope It
        Assert-MockCalled Start-Process -ModuleName Parkos -ParameterFilter { $FilePath -eq 'msiexec.exe' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\Program Files\Parkos' } -Scope It
        # El borrado final del propio modulo tambien pasa por Remove-Item -
        # en total deberia haber exactamente 2 llamadas (InstallPath + el
        # directorio del modulo), NUNCA ninguna carpeta de datos de abajo.
        Assert-MockCalled Remove-Item -ModuleName Parkos -Times 2 -Exactly -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -like '*pg-data*' } -Times 0 -Exactly -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\backups' } -Times 0 -Exactly -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\secrets' } -Times 0 -Exactly -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\logs' } -Times 0 -Exactly -Scope It
        Assert-MockCalled Remove-LocalUser -ModuleName Parkos -Times 0 -Exactly -Scope It
        Assert-MockCalled Stop-Service -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'removes all data folders, the local user and Postgres when confirmed with -PurgeData' {
        Mock Read-Host -ModuleName Parkos { 'CONFIRMAR' }
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-ItemProperty -ModuleName Parkos { $null }
        Mock Get-LocalUser -ModuleName Parkos { [PSCustomObject]@{ Name = 'svc-parkos' } }
        Mock Get-Service -ModuleName Parkos { [PSCustomObject]@{ Name = 'postgresql-x64-16' } }
        Mock Get-ScheduledTask -ModuleName Parkos { $null }

        $result = Uninstall-Parkos -PurgeData

        $result.ExitCode | Should Be 0
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\pg-data' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\backups' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\secrets' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\logs' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\ProgramData\Parkos\installer-runs' } -Scope It
        Assert-MockCalled Remove-LocalUser -ModuleName Parkos -ParameterFilter { $Name -eq 'svc-parkos' } -Scope It
        Assert-MockCalled Stop-Service -ModuleName Parkos -ParameterFilter { $Name -eq 'postgresql-x64-16' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\Program Files\PostgreSQL\16' } -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq 'C:\Program Files\Parkos' } -Scope It
    }

    It 'throws when -PurgeData -Unattended is used without -UnattendedPurgeConfirmed' {
        { Uninstall-Parkos -PurgeData -Unattended } | Should Throw 'UnattendedPurgeConfirmed'
    }

    It 'proceeds without any Read-Host prompt with -PurgeData -Unattended -UnattendedPurgeConfirmed' {
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-ItemProperty -ModuleName Parkos { $null }
        Mock Get-LocalUser -ModuleName Parkos { $null }
        Mock Get-Service -ModuleName Parkos { $null }
        Mock Get-ScheduledTask -ModuleName Parkos { $null }

        $result = Uninstall-Parkos -PurgeData -Unattended -UnattendedPurgeConfirmed

        $result.ExitCode | Should Be 0
        Assert-MockCalled Read-Host -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'continues normally when the ParkosBackupDiario scheduled task does not exist (Get-ScheduledTask throws ObjectNotFound)' {
        Mock Read-Host -ModuleName Parkos { 'CONFIRMAR' }
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-ItemProperty -ModuleName Parkos { $null }
        Mock Get-LocalUser -ModuleName Parkos { $null }
        Mock Get-Service -ModuleName Parkos { $null }
        Mock Get-ScheduledTask -ModuleName Parkos { throw [System.Management.Automation.ItemNotFoundException]::new('ObjectNotFound') }

        # Patron manual try/catch en vez de "Should Not Throw" - ver la
        # advertencia de herramienta sobre Pester 3.4.0 al inicio de esta
        # suite: Should Not Throw (con o sin argumento) no evalua de forma
        # confiable en esta instalacion.
        $threw = $false
        $result = $null
        try {
            $result = Uninstall-Parkos -PurgeData
        } catch {
            $threw = $true
        }

        $threw | Should Be $false
        $result.ExitCode | Should Be 0
    }

    It 'also continues normally when Get-ScheduledTask returns null for ParkosBackupDiario' {
        Mock Read-Host -ModuleName Parkos { 'CONFIRMAR' }
        Mock Test-Path -ModuleName Parkos { $true }
        Mock Get-ItemProperty -ModuleName Parkos { $null }
        Mock Get-LocalUser -ModuleName Parkos { $null }
        Mock Get-Service -ModuleName Parkos { $null }
        Mock Get-ScheduledTask -ModuleName Parkos { $null }

        $threw = $false
        $result = $null
        try {
            $result = Uninstall-Parkos -PurgeData
        } catch {
            $threw = $true
        }

        $threw | Should Be $false
        $result.ExitCode | Should Be 0
        Assert-MockCalled Unregister-ScheduledTask -ModuleName Parkos -ParameterFilter { $TaskName -eq 'ParkosBackupDiario' } -Times 0 -Exactly -Scope It
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Export-ParkosDiagnostics' {

    Import-Module $moduleManifestPath -Force

    # Get-Date/Get-Random mockeados (SOLO dentro del modulo, via -ModuleName
    # Parkos) para que el nombre de la carpeta temporal y del bundle sean
    # una ruta fija y verificable desde el test - Export-ParkosDiagnostics
    # arma ambos nombres con Get-Random y Get-Date -Format.
    Mock Get-Date -ModuleName Parkos {
        param($Format)
        $fixed = [DateTime]::new(2026, 1, 1, 0, 0, 0)
        if ($Format) { return $fixed.ToString($Format) }
        return $fixed
    }
    Mock Get-Random -ModuleName Parkos { 999 }

    $script:testOutputPath = Join-Path $env:TEMP 'parkos-diag-test-output.zip'
    $script:expectedTempRoot = Join-Path $env:TEMP 'parkos-diag-tmp-999'
    $script:expectedBundleDir = Join-Path $expectedTempRoot 'parkos-diag-2026-01-01T00-00-00'

    # Mocks comunes de "camino feliz" - cada It sobreescribe lo que necesita
    # variar (mismo patron que el resto de este archivo). Compress-Archive y
    # Remove-Item SIEMPRE mockeados - un test nunca debe generar un ZIP real
    # ni depender de borrar/no borrar disco real para pasar.
    Mock Get-ParkosHealth -ModuleName Parkos {
        [PSCustomObject]@{
            ExitCode = 0
            Checks   = [ordered]@{
                'Postgres alcanzable' = @{ Status = 'OK'; Detail = 'Puerto 5432 respondio.' }
            }
        }
    }
    Mock Import-ParkosEnvFile -ModuleName Parkos {
        return [ordered]@{
            PORT          = '8000'
            PARKOS_DB_URL = 'postgresql+psycopg://parkos_app:S3cr3tPass!@127.0.0.1:5432/parkos'
        }
    }
    Mock Invoke-ParkosDoctorExe -ModuleName Parkos {
        [PSCustomObject]@{ env_status = 'ok'; db_connectivity = 'ok'; jwt_key_path_exists = $true }
    }
    Mock Get-Service -ModuleName Parkos { $null }
    Mock Invoke-ParkosPsql -ModuleName Parkos { 'col1 col2' }
    Mock Invoke-ParkosNssm -ModuleName Parkos { 'nssm dump ok' }
    Mock Test-ParkosEventLogSourceExists -ModuleName Parkos { $false }
    Mock Get-EventLog -ModuleName Parkos { @() }
    Mock Compress-Archive -ModuleName Parkos { }
    Mock Remove-Item -ModuleName Parkos { }
    Mock Test-Path -ModuleName Parkos { $true }
    Mock Get-Content -ModuleName Parkos { @('FAKE_LINE=fakevalue') }

    # La carpeta temporal es una ruta FIJA en todo este Describe (Get-Date/
    # Get-Random mockeados arriba) y Remove-Item esta mockeado (no borra de
    # verdad) - sin este BeforeEach, un archivo real escrito por un It
    # anterior (ej. postgres-config.txt cuando el origen SI "existia")
    # sobreviviria al siguiente It que espera que ese origen este ausente.
    BeforeEach {
        if (Test-Path $expectedBundleDir) {
            Remove-Item -Path $expectedBundleDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'redacta PARKOS_DB_URL/JWT/SECRET reales en env-redacted.txt sin dejar los valores originales' {
        # Fase 27 (DEC-INST-40): env-redacted.txt ya NO lee $envFilePath
        # crudo con Get-Content (ese archivo puede ser un blob CMS cifrado) -
        # se arma desde $envMap, que sale de Import-ParkosEnvFile (ya
        # descifrado/parseado). Sobreescribimos ESE mock aca, no Get-Content.
        Mock Import-ParkosEnvFile -ModuleName Parkos {
            return [ordered]@{
                PARKOS_DB_URL     = 'postgresql+psycopg://parkos_app:S3cr3tRealPass!@127.0.0.1:5432/parkos'
                PARKOS_JWT_SECRET = 'realsecretvalue12345'
                PORT              = '8000'
            }
        }

        $result = Export-ParkosDiagnostics -OutputPath $testOutputPath
        $result.ExitCode | Should Be 0

        $envRedactedPath = Join-Path $expectedBundleDir 'env-redacted.txt'
        $content = Get-Content -Path $envRedactedPath -Raw

        $content | Should Not Match 'S3cr3tRealPass!'
        $content | Should Not Match 'realsecretvalue12345'
        $content | Should Match 'parkos_app:<redactado, \d+ caracteres>@127\.0\.0\.1:5432/parkos'
        $content | Should Match 'PARKOS_JWT_SECRET=<redactado, \d+ caracteres>'
    }

    It 'Test-ParkosDiagnosticsContainSecrets detecta un archivo con un secreto sin redactar' {
        # Carpeta real independiente de $expectedTempRoot - Get-Random real
        # (esta llamada corre en el scope del test, no del modulo, asi que
        # el mock -ModuleName Parkos de arriba no la afecta).
        $badDir = Join-Path $env:TEMP "parkos-diag-badfile-$(Get-Random -Maximum 999999)"
        New-Item -ItemType Directory -Force -Path $badDir | Out-Null
        try {
            Set-Content -Path (Join-Path $badDir 'leaked.txt') -Value 'PARKOS_JWT_SECRET=estoNOestaRedactado123'

            # Test-ParkosDiagnosticsContainSecrets llama Get-Content
            # internamente - invocarla via el modulo la deja sujeta al mock
            # generico de Get-Content de arriba (que devolveria contenido
            # falso en vez del secreto real). Se sobreescribe puntualmente
            # con el MISMO contenido que se acaba de escribir en disco -
            # NUNCA se debe invocar el cmdlet real por su nombre calificado
            # desde dentro de un Mock del mismo nombre simple: en esta
            # version de Pester eso recursiona hasta desbordar la pila
            # (confirmado - "desbordamiento de profundidad de llamada").
            Mock Get-Content -ModuleName Parkos -ParameterFilter { $Path -like '*leaked.txt' } {
                @('PARKOS_JWT_SECRET=estoNOestaRedactado123')
            }

            # InModuleScope (Pester 3.4.0) no cierra sobre variables locales
            # del It que lo invoca - se usa en cambio el operador de llamada
            # sobre el PSModuleInfo, que SI pasa argumentos de forma
            # confiable a un scriptblock ejecutado en el scope del modulo.
            $checkResult = & (Get-Module Parkos) { param($Path) Test-ParkosDiagnosticsContainSecrets -Path $Path } $badDir

            $checkResult.HasSecrets | Should Be $true
            @($checkResult.Findings).Count | Should BeGreaterThan 0
        } finally {
            Remove-Item -Path $badDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'un archivo fuente faltante (postgresql.conf) no aborta el export' {
        Mock Test-Path -ModuleName Parkos -ParameterFilter { $Path -like '*postgresql.conf' } { $false }

        $result = Export-ParkosDiagnostics -OutputPath $testOutputPath

        $result.ExitCode | Should Be 0
        (Test-Path (Join-Path $expectedBundleDir 'postgres-config.txt')) | Should Be $false
        Assert-MockCalled Compress-Archive -ModuleName Parkos -Times 1 -Exactly -Scope It
    }

    It 'fuente de Event Log inexistente genera eventlog.csv vacio con header, sin reventar' {
        Mock Test-ParkosEventLogSourceExists -ModuleName Parkos { $false }

        $threw = $false
        $result = $null
        try {
            $result = Export-ParkosDiagnostics -OutputPath $testOutputPath
        } catch {
            $threw = $true
        }

        $threw | Should Be $false
        $result.ExitCode | Should Be 0

        $csvContent = (Get-Content -Path (Join-Path $expectedBundleDir 'eventlog.csv') -Raw).Trim()
        $csvContent | Should Be '"Index","TimeGenerated","EntryType","Source","InstanceId","Message"'
        Assert-MockCalled Get-EventLog -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'caso feliz completo: ExitCode 0, Compress-Archive llamado y la carpeta temporal se borra' {
        Mock Test-Path -ModuleName Parkos { $true }

        $result = Export-ParkosDiagnostics -OutputPath $testOutputPath

        $result.ExitCode | Should Be 0
        $result.OutputPath | Should Be $testOutputPath
        Assert-MockCalled Compress-Archive -ModuleName Parkos -ParameterFilter { $DestinationPath -eq $testOutputPath } -Times 1 -Exactly -Scope It
        Assert-MockCalled Remove-Item -ModuleName Parkos -ParameterFilter { $Path -eq $expectedTempRoot } -Times 1 -Exactly -Scope It
    }

    # Este test va DELIBERADAMENTE al final del Describe: Mock no se resetea
    # entre It dentro del mismo Describe en Pester 3.4.0 (mismo comentario ya
    # documentado en el Describe de Repair-ParkosInstall mas arriba), y este
    # mock de Test-ParkosDiagnosticsContainSecrets forzando HasSecrets=$true
    # contaminaria cualquier It posterior que dependa del gate real.
    It 'si Test-ParkosDiagnosticsContainSecrets detecta algo, aborta sin llamar Compress-Archive' {
        Mock Test-ParkosDiagnosticsContainSecrets -ModuleName Parkos {
            [PSCustomObject]@{ HasSecrets = $true; Findings = @('fake.txt:1 - secreto sin redactar') }
        }

        { Export-ParkosDiagnostics -OutputPath $testOutputPath } | Should Throw 'redaccion incompleta'
        Assert-MockCalled Compress-Archive -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    # Limpieza real (Remove-Item esta mockeado -ModuleName Parkos arriba,
    # asi que la carpeta temporal fija reutilizada por todos los Its de este
    # Describe nunca se borro de verdad durante los tests) - esto corre UNA
    # vez, en el scope del test, fuera del modulo, con el cmdlet real.
    if (Test-Path $expectedTempRoot) {
        Remove-Item -Path $expectedTempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $testOutputPath) {
        Remove-Item -Path $testOutputPath -Recurse -Force -ErrorAction SilentlyContinue
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Get-ParkosBackupRetentionPlan' {

    Import-Module $moduleManifestPath -Force

    # Funcion PURA script:-scoped (no exportada) - se invoca via scriptblock
    # inyectado en el modulo (operador de llamada sobre el PSModuleInfo),
    # mismo patron ya usado mas arriba para Test-ParkosDiagnosticsContainSecrets:
    # InModuleScope (Pester 3.4.0) no cierra sobre variables locales del It
    # que lo invoca de forma confiable.
    function Invoke-RetentionPlan {
        param([datetime[]]$Dates)
        & (Get-Module Parkos) { param($d) Get-ParkosBackupRetentionPlan -DumpDates $d } $Dates
    }

    It 'con 20 fechas diarias consecutivas conserva 7 diarias + 3 semanales + 1 mensual, resto a Delete' {
        # 2026-01-01 es jueves (semana ISO 1 de 2026 = 29-dic-2025 al
        # 4-ene-2026); 20 dias consecutivos (1 al 20 de enero) dejan, tras
        # los 7 dias mas recientes (14-20 ene, semanas ISO 3 y 4), 13
        # fechas restantes que solo tocan 3 semanas ISO distintas (semana 3:
        # 12-18 ene, semana 2: 5-11 ene, semana 1: 1-4 ene) - conteo
        # verificado a mano, no aproximado: 7 diarias + 3 semanales (13,
        # 11, 4 ene) + 1 mensual (12 ene) = 11 en Keep, 9 en Delete.
        $dates = 1..20 | ForEach-Object { Get-Date -Year 2026 -Month 1 -Day $_ -Hour 0 -Minute 0 -Second 0 -Millisecond 0 }

        $plan = Invoke-RetentionPlan -Dates $dates

        $plan.Keep.Count | Should Be 11
        $plan.Delete.Count | Should Be 9

        foreach ($day in 14, 15, 16, 17, 18, 19, 20, 13, 11, 4, 12) {
            $expected = Get-Date -Year 2026 -Month 1 -Day $day -Hour 0 -Minute 0 -Second 0 -Millisecond 0
            ($plan.Keep -contains $expected) | Should Be $true
        }
        foreach ($day in 10, 9, 8, 7, 6, 5, 3, 2, 1) {
            $expected = Get-Date -Year 2026 -Month 1 -Day $day -Hour 0 -Minute 0 -Second 0 -Millisecond 0
            ($plan.Delete -contains $expected) | Should Be $true
        }
    }

    It 'con menos de 7 fechas conserva todas y Delete queda vacio' {
        $dates = 1..3 | ForEach-Object { Get-Date -Year 2026 -Month 3 -Day $_ -Hour 0 -Minute 0 -Second 0 -Millisecond 0 }

        $plan = Invoke-RetentionPlan -Dates $dates

        $plan.Keep.Count | Should Be 3
        $plan.Delete.Count | Should Be 0
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

Describe 'Register-ParkosBackupTask' {

    Import-Module $moduleManifestPath -Force

    # Mocks de "camino feliz" comunes a todo el Describe - cada It
    # sobreescribe solo lo que necesita variar (mismo patron que el resto de
    # este archivo). '1' como salida generica de Invoke-ParkosPsql satisface
    # a la vez el chequeo 'SELECT 1;' (regex '^\s*1\s*$') y una estimacion
    # de tamano de BD minima (regex '^\s*\d+\s*$') para el chequeo de disco.
    Mock Test-IsAdmin -ModuleName Parkos { $true }
    Mock Import-ParkosEnvFile -ModuleName Parkos {
        return @{ PARKOS_DB_URL = 'postgresql+psycopg://parkos_app:secret@127.0.0.1:5432/parkos' }
    }
    Mock Invoke-ParkosPsql -ModuleName Parkos { @('1') }
    Mock Get-PSDrive -ModuleName Parkos { [PSCustomObject]@{ Name = 'C'; Free = 900GB; Used = 100GB } }
    Mock Get-LocalUser -ModuleName Parkos { [PSCustomObject]@{ Name = 'svc-parkos' } }
    Mock New-Item -ModuleName Parkos { }
    Mock Set-Content -ModuleName Parkos { }
    Mock icacls -ModuleName Parkos { }
    # New-ScheduledTaskAction/-Trigger/-Principal/-SettingsSet NUNCA se
    # mockean: son constructores puros (devuelven un CimInstance en
    # memoria, sin tocar el servicio de Task Scheduler) - un Mock devolviendo
    # un string generico rompe el binding de tipos ESTRICTO que
    # Register-ScheduledTask exige para -Action/-Trigger/-Principal/
    # -Settings (confirmado corriendo la suite: "no se puede convertir
    # 'fake-action' a CimInstance[]"). Solo Register-ScheduledTask (la unica
    # que persiste algo real) se mockea.
    Mock Register-ScheduledTask -ModuleName Parkos { }
    Mock Unregister-ScheduledTask -ModuleName Parkos { }
    Mock Start-Process -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 0 } }

    It 'lanza un throw explicito cuando el espacio en disco es insuficiente, y no registra la tarea' {
        Mock Invoke-ParkosPsql -ModuleName Parkos -ParameterFilter { $Command -like '*pg_database_size*' } { @('10737418240') }
        Mock Get-PSDrive -ModuleName Parkos { [PSCustomObject]@{ Name = 'C'; Free = 1GB; Used = 99GB } }

        { Register-ParkosBackupTask } | Should Throw 'Espacio insuficiente'
        Assert-MockCalled Register-ScheduledTask -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'lanza un throw explicito y no registra la tarea cuando svc-parkos no existe' {
        # Reset explicito: Mock no se resetea entre It dentro del mismo
        # Describe (mismo comentario ya documentado en el Describe de
        # Repair-ParkosInstall mas arriba) - sin esto, este test heredaria
        # el Get-PSDrive/Invoke-ParkosPsql de espacio insuficiente que dejo
        # el It anterior, y el chequeo de disco tiraria antes de llegar al
        # chequeo de svc-parkos que este test quiere ejercitar.
        Mock Invoke-ParkosPsql -ModuleName Parkos { @('1') }
        Mock Get-PSDrive -ModuleName Parkos { [PSCustomObject]@{ Name = 'C'; Free = 900GB; Used = 100GB } }
        Mock Get-LocalUser -ModuleName Parkos { $null }

        { Register-ParkosBackupTask } | Should Throw 'svc-parkos'
        Assert-MockCalled Register-ScheduledTask -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'caso feliz completo: registra la tarea con Daily/ServiceAccount y corre el backup de prueba, ExitCode 0' {
        # Mismo reset explicito que el It anterior - ver el comentario de
        # arriba.
        Mock Invoke-ParkosPsql -ModuleName Parkos { @('1') }
        Mock Get-PSDrive -ModuleName Parkos { [PSCustomObject]@{ Name = 'C'; Free = 900GB; Used = 100GB } }
        Mock Get-LocalUser -ModuleName Parkos { [PSCustomObject]@{ Name = 'svc-parkos' } }

        $result = Register-ParkosBackupTask -DailyAt '02:30'

        $result.ExitCode | Should Be 0
        # $Trigger/$Principal son los CimInstance REALES construidos por
        # New-ScheduledTaskTrigger/-Principal (no mockeados, ver comentario
        # de arriba) - se inspeccionan sus propiedades reales para
        # confirmar Daily/ServiceAccount sin necesitar mockearlos.
        Assert-MockCalled Register-ScheduledTask -ModuleName Parkos -ParameterFilter {
            $TaskName -eq 'ParkosBackupDiario' -and
            $Principal.UserId -eq 'svc-parkos' -and
            $Principal.LogonType -eq 'ServiceAccount' -and
            $Trigger.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger'
        } -Times 1 -Exactly -Scope It
        Assert-MockCalled Start-Process -ModuleName Parkos -ParameterFilter { $FilePath -eq 'pwsh.exe' } -Times 1 -Exactly -Scope It
        Assert-MockCalled Unregister-ScheduledTask -ModuleName Parkos -Times 0 -Exactly -Scope It
    }

    It 'si el backup de prueba falla, lanza throw, desregistra la tarea y no deja pasar silenciosamente' {
        # Mismo reset explicito que los dos It anteriores - ver el
        # comentario en 'lanza un throw explicito y no registra la tarea
        # cuando svc-parkos no existe' mas arriba.
        Mock Invoke-ParkosPsql -ModuleName Parkos { @('1') }
        Mock Get-PSDrive -ModuleName Parkos { [PSCustomObject]@{ Name = 'C'; Free = 900GB; Used = 100GB } }
        Mock Get-LocalUser -ModuleName Parkos { [PSCustomObject]@{ Name = 'svc-parkos' } }
        Mock Start-Process -ModuleName Parkos { [PSCustomObject]@{ ExitCode = 1 } }

        { Register-ParkosBackupTask } | Should Throw 'backup de prueba fallo'
        Assert-MockCalled Register-ScheduledTask -ModuleName Parkos -Times 1 -Exactly -Scope It
        Assert-MockCalled Unregister-ScheduledTask -ModuleName Parkos -ParameterFilter { $TaskName -eq 'ParkosBackupDiario' } -Times 1 -Exactly -Scope It
    }

    Remove-Module Parkos -Force -ErrorAction SilentlyContinue
}

# Ejecutar con: Invoke-Pester -Path installer/tests/Parkos.Module.Tests.ps1
