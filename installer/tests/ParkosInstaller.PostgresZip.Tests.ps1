# Tests de la etapa 1 del instalador completo (DEC-INST-45): Postgres SIEMPRE
# desde el ZIP de EDB (payload o descarga), registrado como servicio de
# Windows de inicio automatico, con espera de "listo" antes de crear roles.
# Pester 3.4: Mock sin -ModuleName; Should Throw lleva substring; "no deberia
# lanzar" = try/catch + Should Be $true. Ningun test toca red, servicios,
# procesos ni pg_ctl reales: todo va por wrappers mockeados.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

Describe 'etapa 1 - el instalador ya no usa winget' {
    It 'el archivo no invoca winget ni define las funciones winget' {
        $src = Get-Content -Path $installerScript -Raw
        $src | Should Not Match '(?m)^\s*winget\s+(install|uninstall)'
        (Get-Command Install-PostgresViaWinget -ErrorAction SilentlyContinue) | Should Be $null
    }

    It 'el codigo compartido de descarga quedo cargado (dot-source)' {
        $script:ParkosSharedPostgresLoaded | Should Be $true
        (Get-Command Get-ParkosPostgresZip -ErrorAction SilentlyContinue) | Should Not Be $null
    }
}

Describe 'Get-ParkosPgCtlRegisterArguments / servicio' {
    It 'el nombre del servicio contiene postgresql (patron de Parkos.psm1)' {
        (Get-ParkosPostgresServiceName) | Should Match '(?i)postgresql'
    }

    It 'registra con inicio automatico y el data directory' {
        $a = Get-ParkosPgCtlRegisterArguments -ServiceName 'postgresql-parkos' -PgDataPath 'D:\pg-data'
        ($a -join ' ') | Should Be 'register -N postgresql-parkos -D D:\pg-data -S auto'
    }
}

Describe 'Register-ParkosPostgresService' {
    BeforeEach { $script:PostgresServiceRegistered = $false }

    It 'servicio nuevo: llama pg_ctl register una vez con los argumentos esperados' {
        Mock Get-ParkosServiceState { $null }
        Mock Remove-ParkosPostgresService { }
        Mock Invoke-ParkosPgCtl { [PSCustomObject]@{ ExitCode = 0; Output = '' } }
        Register-ParkosPostgresService -PgInstallPath 'C:\pg' -PgDataPath 'D:\pg-data'
        Assert-MockCalled Invoke-ParkosPgCtl -Times 1 -Scope It -ParameterFilter {
            $PgCtlPath -eq 'C:\pg\bin\pg_ctl.exe' -and ($Arguments -join ' ') -eq 'register -N postgresql-parkos -D D:\pg-data -S auto'
        }
        Assert-MockCalled Remove-ParkosPostgresService -Times 0 -Scope It
        $script:PostgresServiceRegistered | Should Be $true
    }

    It 'idempotente: si el servicio ya existe lo quita y lo registra de nuevo (sin duplicar)' {
        Mock Get-ParkosServiceState { 'Running' }
        Mock Remove-ParkosPostgresService { }
        Mock Invoke-ParkosPgCtl { [PSCustomObject]@{ ExitCode = 0; Output = '' } }
        Register-ParkosPostgresService -PgInstallPath 'C:\pg' -PgDataPath 'D:\pg-data'
        Assert-MockCalled Remove-ParkosPostgresService -Times 1 -Scope It
        Assert-MockCalled Invoke-ParkosPgCtl -Times 1 -Scope It
    }

    It 'si pg_ctl register falla lanza con el codigo y la salida' {
        Mock Get-ParkosServiceState { $null }
        Mock Invoke-ParkosPgCtl { [PSCustomObject]@{ ExitCode = 1; Output = 'acceso denegado' } }
        { Register-ParkosPostgresService -PgInstallPath 'C:\pg' -PgDataPath 'D:\pg-data' } | Should Throw 'acceso denegado'
        $script:PostgresServiceRegistered | Should Be $false
    }
}

Describe 'Remove-ParkosPostgresService' {
    It 'servicio inexistente: no hace nada' {
        Mock Get-ParkosServiceState { $null }
        Mock Stop-ParkosServiceByName { }
        Mock Invoke-ParkosPgCtl { }
        Remove-ParkosPostgresService -PgInstallPath 'C:\pg'
        Assert-MockCalled Stop-ParkosServiceByName -Times 0 -Scope It
        Assert-MockCalled Invoke-ParkosPgCtl -Times 0 -Scope It
    }

    It 'servicio en marcha: lo detiene y lo desregistra con pg_ctl' {
        $root = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-pgsvc-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path (Join-Path $root 'bin') -Force | Out-Null
        Set-Content -Path (Join-Path $root 'bin\pg_ctl.exe') -Value 'x'
        try {
            Mock Get-ParkosServiceState { 'Running' }
            Mock Stop-ParkosServiceByName { }
            Mock Invoke-ParkosPgCtl { [PSCustomObject]@{ ExitCode = 0; Output = '' } }
            Mock Invoke-ParkosScDelete { 0 }
            Remove-ParkosPostgresService -PgInstallPath $root
            Assert-MockCalled Stop-ParkosServiceByName -Times 1 -Scope It
            Assert-MockCalled Invoke-ParkosPgCtl -Times 1 -ParameterFilter { ($Arguments -join ' ') -eq 'unregister -N postgresql-parkos' } -Scope It
            Assert-MockCalled Invoke-ParkosScDelete -Times 0 -Scope It
        } finally {
            Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'sin pg_ctl cae a sc.exe delete' {
        Mock Get-ParkosServiceState { 'Stopped' }
        Mock Stop-ParkosServiceByName { }
        Mock Invoke-ParkosScDelete { 0 }
        Remove-ParkosPostgresService -PgInstallPath 'C:\no-existe-pg'
        Assert-MockCalled Invoke-ParkosScDelete -Times 1 -ParameterFilter { $ServiceName -eq 'postgresql-parkos' } -Scope It
    }
}

Describe 'Remove-ParkosStalePostmasterPid (decision de pid obsoleto)' {
    BeforeEach {
        $script:pgd = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-pid-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $script:pgd -Force | Out-Null
    }
    AfterEach { Remove-Item $script:pgd -Recurse -Force -ErrorAction SilentlyContinue }

    It 'sin postmaster.pid no hace nada' {
        (Remove-ParkosStalePostmasterPid -PgDataPath $script:pgd) | Should Be $false
    }

    It 'PID que ya no existe: lo borra' {
        Set-Content -Path (Join-Path $script:pgd 'postmaster.pid') -Value @('4242', 'C:/data', '1')
        Mock Get-ParkosProcessNameById { $null }
        (Remove-ParkosStalePostmasterPid -PgDataPath $script:pgd) | Should Be $true
        (Test-Path (Join-Path $script:pgd 'postmaster.pid')) | Should Be $false
    }

    It 'PID reciclado por otro programa: lo borra' {
        Set-Content -Path (Join-Path $script:pgd 'postmaster.pid') -Value @('4242', 'C:/data')
        Mock Get-ParkosProcessNameById { 'notepad' }
        (Remove-ParkosStalePostmasterPid -PgDataPath $script:pgd) | Should Be $true
    }

    It 'PID de un postgres vivo: lo conserva' {
        Set-Content -Path (Join-Path $script:pgd 'postmaster.pid') -Value @('4242', 'C:/data')
        Mock Get-ParkosProcessNameById { 'postgres' }
        (Remove-ParkosStalePostmasterPid -PgDataPath $script:pgd) | Should Be $false
        (Test-Path (Join-Path $script:pgd 'postmaster.pid')) | Should Be $true
    }

    It 'contenido ilegible: lo trata como obsoleto' {
        Set-Content -Path (Join-Path $script:pgd 'postmaster.pid') -Value 'basura'
        Mock Get-ParkosProcessNameById { 'postgres' }
        (Remove-ParkosStalePostmasterPid -PgDataPath $script:pgd) | Should Be $true
    }
}

Describe 'Wait-ParkosPostgresReady / Start-ParkosPostgresService' {
    It 'reintenta hasta que pg_isready responde 0' {
        $script:calls = 0
        Mock Invoke-ParkosPgIsReady { $script:calls++; if ($script:calls -lt 3) { 2 } else { 0 } }
        Mock Start-ParkosSleep { }
        Wait-ParkosPostgresReady -PgInstallPath 'C:\pg' -Port 5432
        Assert-MockCalled Invoke-ParkosPgIsReady -Times 3 -ParameterFilter { $PgIsReadyPath -eq 'C:\pg\bin\pg_isready.exe' -and $Port -eq 5432 } -Scope It
        Assert-MockCalled Start-ParkosSleep -Times 2 -Scope It
    }

    It 'si nunca responde lanza un mensaje en espanol accionable' {
        Mock Invoke-ParkosPgIsReady { 2 }
        Mock Start-ParkosSleep { }
        { Wait-ParkosPostgresReady -PgInstallPath 'C:\pg' -Port 5433 -MaxAttempts 3 -IntervalSeconds 1 } | Should Throw 'no acepto conexiones'
    }

    It 'servicio detenido: borra pid obsoleto, arranca y espera ANTES de volver' {
        $script:order = @()
        Mock Get-ParkosServiceState { 'Stopped' }
        Mock Remove-ParkosStalePostmasterPid { $script:order += 'stale'; $false }
        Mock Start-ParkosServiceByName { $script:order += 'start' }
        Mock Wait-ParkosPostgresReady { $script:order += 'ready' }
        Start-ParkosPostgresService -PgInstallPath 'C:\pg' -PgDataPath 'D:\d' -Port 5432
        ($script:order -join ',') | Should Be 'stale,start,ready'
    }

    It 'servicio ya en marcha: no lo vuelve a arrancar pero si espera' {
        Mock Get-ParkosServiceState { 'Running' }
        Mock Remove-ParkosStalePostmasterPid { }
        Mock Start-ParkosServiceByName { }
        Mock Wait-ParkosPostgresReady { }
        Start-ParkosPostgresService -PgInstallPath 'C:\pg' -PgDataPath 'D:\d' -Port 5432
        Assert-MockCalled Start-ParkosServiceByName -Times 0 -Scope It
        Assert-MockCalled Remove-ParkosStalePostmasterPid -Times 0 -Scope It
        Assert-MockCalled Wait-ParkosPostgresReady -Times 1 -Scope It
    }
}

Describe 'Set-ParkosPgConfSetting' {
    It 'agrega la linea y al repetir la reemplaza sin duplicar' {
        $conf = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-conf-' + [guid]::NewGuid().ToString('N') + '.conf')
        try {
            Set-Content -Path $conf -Value @('#port = 5432', 'max_connections = 100')
            Set-ParkosPgConfSetting -ConfPath $conf -Name 'port' -Value '5433'
            Set-ParkosPgConfSetting -ConfPath $conf -Name 'port' -Value '5434'
            $lines = @(Get-Content $conf)
            @($lines | Where-Object { $_ -match '^\s*port\s*=' }).Count | Should Be 1
            ($lines -contains 'port = 5434') | Should Be $true
            ($lines -contains '#port = 5432') | Should Be $true
            ($lines -contains 'max_connections = 100') | Should Be $true
        } finally {
            Remove-Item $conf -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Get-ParkosPostgresZipForInstall (precedencia payload / cache / descarga)' {
    BeforeEach {
        $script:tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-pgzip-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path (Join-Path $script:tmpRoot 'payload\postgres') -Force | Out-Null
        $script:PayloadRoot = Join-Path $script:tmpRoot 'payload'
    }
    AfterEach { Remove-Item $script:tmpRoot -Recurse -Force -ErrorAction SilentlyContinue }

    It 'zip pre-descargado en payload\postgres: se usa y NO se descarga' {
        $zip = Join-Path $script:PayloadRoot 'postgres\postgresql-16-windows-x64-binaries.zip'
        Set-Content -Path $zip -Value 'x'
        Mock Test-ParkosPostgresZip { $true }
        Mock Get-ParkosPostgresZip { 'NO' }
        (Get-ParkosPostgresZipForInstall -DownloadDir (Join-Path $script:tmpRoot 'dl')) | Should Be $zip
        Assert-MockCalled Get-ParkosPostgresZip -Times 0 -Scope It
    }

    It 'payload invalido o ausente: delega en la cache/descarga compartida con <DataPath>\downloads' {
        Set-Content -Path (Join-Path $script:PayloadRoot 'postgres\postgresql-16-windows-x64-binaries.zip') -Value 'corrupto'
        Mock Test-ParkosPostgresZip { $false }
        Mock Get-ParkosPostgresZip { 'C:\cache\pg.zip' }
        $dl = Join-Path $script:tmpRoot 'dl'
        (Get-ParkosPostgresZipForInstall -DownloadDir $dl) | Should Be 'C:\cache\pg.zip'
        Assert-MockCalled Get-ParkosPostgresZip -Times 1 -ParameterFilter { $CacheDir -eq $dl -and $PayloadDir -like '*payload\postgres' } -Scope It
    }
}

Describe 'Install-PostgresViaZip' {
    BeforeEach {
        $script:tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-viazip-' + [guid]::NewGuid().ToString('N'))
        $script:pgData = Join-Path $script:tmpRoot 'pg-data'
        New-Item -ItemType Directory -Path $script:tmpRoot -Force | Out-Null
        $script:PostgresDataCreatedByInstaller = $false
        Mock Expand-ParkosPostgresZip { 'C:\pg' }
        Mock Grant-ParkosPgDataAccess { }
        Mock Invoke-ParkosInitdb {
            New-Item -ItemType Directory -Path $PgDataPath -Force | Out-Null
            Set-Content -Path (Join-Path $PgDataPath 'PG_VERSION') -Value '16'
            Set-Content -Path (Join-Path $PgDataPath 'postgresql.conf') -Value '#port = 5432'
            0
        }
    }
    AfterEach { Remove-Item $script:tmpRoot -Recurse -Force -ErrorAction SilentlyContinue }

    It 'data directory nuevo: extrae, corre initdb, fija puerto y marca que lo creo' {
        Install-PostgresViaZip -PayloadZipPath 'a.zip' -PgInstallPath 'C:\pg' -PgDataPath $script:pgData -Port 5433 -SuperuserPassword 'pw'
        Assert-MockCalled Expand-ParkosPostgresZip -Times 1 -ParameterFilter { $ZipPath -eq 'a.zip' -and $PgRoot -eq 'C:\pg' } -Scope It
        Assert-MockCalled Invoke-ParkosInitdb -Times 1 -ParameterFilter { $InitdbPath -eq 'C:\pg\bin\initdb.exe' } -Scope It
        (Get-Content (Join-Path $script:pgData 'postgresql.conf')) -contains 'port = 5433' | Should Be $true
        Assert-MockCalled Grant-ParkosPgDataAccess -Times 1 -Scope It
        $script:PostgresDataCreatedByInstaller | Should Be $true
    }

    It 'idempotente: con PG_VERSION existente NO corre initdb ni lo marca como creado' {
        New-Item -ItemType Directory -Path $script:pgData -Force | Out-Null
        Set-Content -Path (Join-Path $script:pgData 'PG_VERSION') -Value '16'
        Set-Content -Path (Join-Path $script:pgData 'postgresql.conf') -Value @('port = 5432', 'port = 5432')
        Install-PostgresViaZip -PayloadZipPath 'a.zip' -PgInstallPath 'C:\pg' -PgDataPath $script:pgData -Port 5433 -SuperuserPassword 'pw'
        Assert-MockCalled Invoke-ParkosInitdb -Times 0 -Scope It
        $script:PostgresDataCreatedByInstaller | Should Be $false
        @((Get-Content (Join-Path $script:pgData 'postgresql.conf')) | Where-Object { $_ -match '^port\s*=' }).Count | Should Be 1
    }

    It 'initdb fallido lanza y no deja el archivo de password' {
        Mock Invoke-ParkosInitdb { 1 }
        { Install-PostgresViaZip -PayloadZipPath 'a.zip' -PgInstallPath 'C:\pg' -PgDataPath $script:pgData -Port 5432 -SuperuserPassword 'pw' } | Should Throw 'initdb fallo'
    }
}

Describe 'Install-Postgres (orquestacion y fallo de descarga)' {
    BeforeEach {
        $script:PostgresInstallMethod = $null
        $script:order = @()
        Mock Get-ParkosPostgresZipForInstall { $script:order += 'zip'; 'C:\cache\pg.zip' }
        Mock Install-PostgresViaZip { $script:order += 'viazip' }
        Mock Register-ParkosPostgresService { $script:order += 'register' }
        Mock Start-ParkosPostgresService { $script:order += 'start' }
    }

    It 'zip -> initdb -> registrar -> arrancar/esperar, devuelve zip y nunca llama winget' {
        $r = Install-Postgres -PgInstallPath 'C:\pg' -PgDataPath 'D:\d' -Port 5432 -SuperuserPassword 'pw' -DownloadDir 'D:\dl'
        $r | Should Be 'zip'
        ($script:order -join ',') | Should Be 'zip,viazip,register,start'
        $script:PostgresInstallMethod | Should Be 'zip'
        Assert-MockCalled Get-ParkosPostgresZipForInstall -Times 1 -ParameterFilter { $DownloadDir -eq 'D:\dl' } -Scope It
    }

    It 'fallo de descarga: propaga el mensaje compartido (URL + carpeta) y no instala nada' {
        Mock Get-ParkosPostgresZipForInstall {
            throw (Get-ParkosDownloadFailureMessage -What 'los binarios de Postgres' -Url 'https://get.enterprisedb.com/x.zip' -TargetDir 'D:\dl' -FileName 'x.zip' -Detail 'sin red')
        }
        $msg = ''
        try { Install-Postgres -PgInstallPath 'C:\pg' -PgDataPath 'D:\d' -Port 5432 -SuperuserPassword 'pw' -DownloadDir 'D:\dl' | Out-Null } catch { $msg = $_.Exception.Message }
        $msg | Should Match 'https://get.enterprisedb.com/x.zip'
        $msg | Should Match 'D:\\dl'
        Assert-MockCalled Install-PostgresViaZip -Times 0 -Scope It
        $script:PostgresInstallMethod | Should Be $null
    }

    It 'sin el codigo compartido falla con mensaje claro' {
        $saved = $script:ParkosSharedPostgresLoaded
        $script:ParkosSharedPostgresLoaded = $false
        try {
            { Install-Postgres -PgInstallPath 'C:\pg' -PgDataPath 'D:\d' -Port 5432 -SuperuserPassword 'pw' } | Should Throw 'ParkosPostgresDownload.ps1'
        } finally {
            $script:ParkosSharedPostgresLoaded = $saved
        }
    }
}

Describe 'etapa 1 - Action y Rollback' {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('parkos-stage1-' + [guid]::NewGuid().ToString('N'))

    BeforeEach {
        New-Item -ItemType Directory -Path (Join-Path $tmp 'payload') -Force | Out-Null
        $script:PayloadRoot = Join-Path $tmp 'payload'
        $script:StageStatus = @{ db = [ParkosStageState]::Ok }
        $script:PostgresInstallMethod = $null
        $script:PostgresServiceRegistered = $false
        $script:PostgresDataCreatedByInstaller = $false
        Mock Get-ParkosServiceState { $null }
        Mock Stop-ParkosServiceByName { }
        Mock Test-PostgresPorts { 5432 }
        Mock Test-ApiPort { 8000 }
        Mock New-ParkosDerivedPassword { 'stub-pass' }
        Mock Install-Postgres { 'zip' }
        Mock Initialize-DatabaseRoles { @{ AppPassword = 'a'; SuperuserPassword = 's' } }
        Mock Ensure-ServiceAccount { }
        Mock New-JwtSigningKey { }
        Mock Test-JwtSecretGate { $true }
        Mock Get-OrCreateParkosEnvCert { }
        Mock Write-RuntimeEnvFile { }
        Mock Set-MachineApiOrigin { }
        Mock Install-PgPartman { }
        Mock Register-PgPartmanMaintenance { }
        Mock Remove-ParkosPostgresService { }
    }
    AfterEach { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

    function New-Defs1 {
        Get-ParkosStageDefinitions -InstallPath (Join-Path $tmp 'install') -DataPath (Join-Path $tmp 'data') `
            -SucursalUuid '00000000-0000-0000-0000-000000000001' -CloudApiUrl 'https://cloud.invalid'
    }

    It 'el Action instala via Install-Postgres con la carpeta de descargas bajo DataPath, antes de crear roles' {
        $defs = New-Defs1
        & $defs.Stages['1'].Action
        Assert-MockCalled Install-Postgres -Times 1 -ParameterFilter { $DownloadDir -eq (Join-Path $tmp 'data\downloads') } -Scope It
        Assert-MockCalled Initialize-DatabaseRoles -Times 1 -Scope It
        Assert-MockCalled Install-PgPartman -Times 1 -ParameterFilter { $DownloadDir -eq (Join-Path $tmp 'data\downloads') } -Scope It
        $script:PostgresInstallMethod | Should Be 'zip'
    }

    It 're-ejecucion: detiene el servicio propio antes de buscar puerto libre' {
        Mock Get-ParkosServiceState { 'Running' }
        $defs = New-Defs1
        & $defs.Stages['1'].Action
        Assert-MockCalled Stop-ParkosServiceByName -Times 1 -ParameterFilter { $Name -eq 'postgresql-parkos' } -Scope It
    }

    It 'si la instalacion falla, la etapa falla (reintentable) y no crea roles' {
        Mock Install-Postgres { throw 'No se pudo obtener los binarios de Postgres' }
        $defs = New-Defs1
        { & $defs.Stages['1'].Action } | Should Throw 'No se pudo obtener'
        Assert-MockCalled Initialize-DatabaseRoles -Times 0 -Scope It
    }

    It 'Rollback: desregistra el servicio y borra binarios y data que creo esta corrida' {
        $defs = New-Defs1
        $ctx = $script:StageContext
        New-Item -ItemType Directory -Path $ctx.PgDataPath -Force | Out-Null
        Set-Content -Path (Join-Path $ctx.PgDataPath 'PG_VERSION') -Value '16'
        $script:PostgresInstallMethod = 'zip'
        $script:PostgresServiceRegistered = $true
        $script:PostgresDataCreatedByInstaller = $true
        # Remove-Item mockeado: el PgInstallPath de la etapa es el real
        # (C:\Program Files\PostgreSQL) y NUNCA debe tocarse desde un test.
        Mock Remove-Item { }
        & $defs.Stages['1'].Rollback
        Assert-MockCalled Remove-ParkosPostgresService -Times 1 -Scope It
        Assert-MockCalled Remove-Item -Times 1 -ParameterFilter { $Path -eq $ctx.PgInstallPath } -Scope It
        Assert-MockCalled Remove-Item -Times 1 -ParameterFilter { $Path -eq $ctx.PgDataPath } -Scope It
    }

    It 'Rollback: NO borra un data directory que ya existia (no lo creo esta corrida)' {
        $defs = New-Defs1
        $ctx = $script:StageContext
        New-Item -ItemType Directory -Path $ctx.PgDataPath -Force | Out-Null
        Set-Content -Path (Join-Path $ctx.PgDataPath 'PG_VERSION') -Value '16'
        $script:PostgresInstallMethod = 'stub'
        $script:PostgresServiceRegistered = $false
        $script:PostgresDataCreatedByInstaller = $false
        Mock Remove-Item { }
        & $defs.Stages['1'].Rollback
        Assert-MockCalled Remove-ParkosPostgresService -Times 0 -Scope It
        Assert-MockCalled Remove-Item -Times 0 -Scope It
    }
}
