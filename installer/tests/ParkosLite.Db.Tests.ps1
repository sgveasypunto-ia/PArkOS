# Tests de installer/lite/ParkosLite.Db.ps1: initdb, roles, arranque/parada de
# Postgres con tolerancia a postmaster.pid huerfano, espera de readiness,
# migraciones y seed. Todo binario externo (initdb/pg_ctl/psql/pg_isready/
# migrate.exe) pasa por Invoke-ParkosLiteNative, que se mockea aqui.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')

$script:paths = @{
    PgRoot = 'C:\lite\pgsql'; PgData = 'C:\lite\data\pg'; Logs = 'C:\lite\logs'
    MigrateDir = 'C:\repo\installer\payload\services\migrate\migrate'
    MigrateExe = 'C:\repo\installer\payload\services\migrate\migrate\migrate.exe'
    SeedSql = 'C:\repo\installer\lite\seed_demo.sql'
}
$script:uuid = '11111111-2222-4333-8444-555555555555'
$script:secrets = @{ PostgresPassword = 'pgpw'; SuperuserPassword = 'supw'; AppPassword = 'apppw' }
$script:ok = @{ ExitCode = 0; Output = @() }

Describe 'Get-ParkosLitePgBin' {
    It 'resuelve ejecutables dentro de bin' {
        (Get-ParkosLitePgBin -PgRoot 'C:\lite\pgsql' -Name 'psql') | Should Be 'C:\lite\pgsql\bin\psql.exe'
    }
}

Describe 'Get-ParkosLitePostgresConfLines' {
    It 'fija puerto y solo loopback' {
        $l = Get-ParkosLitePostgresConfLines -Port 5434
        $l -contains 'port = 5434' | Should Be $true
        $l -contains "listen_addresses = '127.0.0.1'" | Should Be $true
    }
    It 'fija timezone UTC (el esquema usa timestamps naive-UTC comparados con NOW())' {
        $l = Get-ParkosLitePostgresConfLines -Port 5434
        $l -contains "timezone = 'UTC'" | Should Be $true
    }
}

Describe 'Initialize-ParkosLitePgData' {
    It 'no vuelve a ejecutar initdb si el data dir ya existe (PG_VERSION)' {
        $d = Join-Path $TestDrive 'pg1'
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Set-Content (Join-Path $d 'PG_VERSION') '16'
        $global:initCalls = 0
        Mock Invoke-ParkosLiteNative { $global:initCalls++; $script:ok }
        $r = Initialize-ParkosLitePgData -PgRoot 'C:\lite\pgsql' -PgData $d -Port 5434 -PostgresPassword 'x'
        $r | Should Be $false
        $global:initCalls | Should Be 0
    }
    It 'ejecuta initdb con pwfile, UTF8 y scram, y agrega el puerto al conf' {
        $d = Join-Path $TestDrive 'pg2'
        $global:initArgs = @()
        Mock Invoke-ParkosLiteNative {
            $global:initArgs = $Arguments
            New-Item -ItemType Directory -Force -Path $d | Out-Null
            Set-Content (Join-Path $d 'PG_VERSION') '16'
            Set-Content (Join-Path $d 'postgresql.conf') '# conf'
            $script:ok
        }
        $r = Initialize-ParkosLitePgData -PgRoot 'C:\lite\pgsql' -PgData $d -Port 5434 -PostgresPassword 'x'
        $r | Should Be $true
        ($global:initArgs -join ' ') | Should Match '-U postgres'
        ($global:initArgs -join ' ') | Should Match '--encoding=UTF8'
        ($global:initArgs -join ' ') | Should Match '--auth=scram-sha-256'
        ($global:initArgs -join ' ') | Should Match '--pwfile='
        (Get-Content (Join-Path $d 'postgresql.conf') -Raw) | Should Match 'port = 5434'
        # el pwfile temporal se limpia
        $pwArg = ($global:initArgs | Where-Object { $_ -like '--pwfile=*' }) -replace '^--pwfile=', ''
        (Test-Path $pwArg) | Should Be $false
    }
    It 'si initdb falla lanza con el codigo de salida' {
        $d = Join-Path $TestDrive 'pg3'
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 1; Output = @('boom') } }
        { Initialize-ParkosLitePgData -PgRoot 'C:\lite\pgsql' -PgData $d -Port 5434 -PostgresPassword 'x' } | Should Throw 'initdb'
    }
}

Describe 'Get-ParkosLiteStalePidDecision' {
    It 'sin archivo pid: clean' {
        (Get-ParkosLiteStalePidDecision -PidFileExists $false -StatusExitCode 3 -PidProcessName $null) | Should Be 'clean'
    }
    It 'pid y pg_ctl status 0 con proceso postgres: running' {
        (Get-ParkosLiteStalePidDecision -PidFileExists $true -StatusExitCode 0 -PidProcessName 'postgres') | Should Be 'running'
    }
    It 'pid y pg_ctl status 3 (nadie dueño): stale' {
        (Get-ParkosLiteStalePidDecision -PidFileExists $true -StatusExitCode 3 -PidProcessName $null) | Should Be 'stale'
    }
    It 'pid reutilizado por otro proceso (status 0 pero no es postgres): stale' {
        (Get-ParkosLiteStalePidDecision -PidFileExists $true -StatusExitCode 0 -PidProcessName 'chrome') | Should Be 'stale'
    }
}

Describe 'Repair-ParkosLiteStalePid' {
    It 'borra SOLO el postmaster.pid huerfano' {
        $d = Join-Path $TestDrive 'pgs1'
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Set-Content (Join-Path $d 'postmaster.pid') @('4242', 'x')
        Set-Content (Join-Path $d 'PG_VERSION') '16'
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 3; Output = @() } }
        Mock Get-ParkosLiteProcessName { $null }
        $r = Repair-ParkosLiteStalePid -PgRoot 'C:\lite\pgsql' -PgData $d
        $r | Should Be 'stale'
        (Test-Path (Join-Path $d 'postmaster.pid')) | Should Be $false
        (Test-Path (Join-Path $d 'PG_VERSION')) | Should Be $true
    }
    It 'respeta el pid de un postgres vivo' {
        $d = Join-Path $TestDrive 'pgs2'
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Set-Content (Join-Path $d 'postmaster.pid') @('4242', 'x')
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 0; Output = @() } }
        Mock Get-ParkosLiteProcessName { 'postgres' }
        (Repair-ParkosLiteStalePid -PgRoot 'C:\lite\pgsql' -PgData $d) | Should Be 'running'
        (Test-Path (Join-Path $d 'postmaster.pid')) | Should Be $true
    }
}

Describe 'Start-ParkosLitePg' {
    It 'si ya esta corriendo no arranca de nuevo' {
        $global:ctl = @()
        Mock Repair-ParkosLiteStalePid { 'running' }
        Mock Invoke-ParkosLiteNative { $global:ctl += ($Arguments -join ' '); $script:ok }
        Mock Wait-ParkosLitePgReady { $true }
        (Start-ParkosLitePg -Paths $script:paths -Port 5434) | Should Be $true
        ($global:ctl | Where-Object { $_ -like 'start*' }).Count | Should Be 0
    }
    It 'arranca con pg_ctl start -w y log en logs\ tras limpiar el pid huerfano' {
        $global:ctl = @()
        Mock Repair-ParkosLiteStalePid { 'stale' }
        Mock Invoke-ParkosLitePgCtlStart { $global:ctl += ($Arguments -join ' '); $script:ok }
        Mock Wait-ParkosLitePgReady { $true }
        Mock New-Item { }
        (Start-ParkosLitePg -Paths $script:paths -Port 5434) | Should Be $true
        $start = $global:ctl | Where-Object { $_ -like 'start*' }
        $start | Should Match '-w'
        $start | Should Match '-D C:\\lite\\data\\pg'
        $start | Should Match 'postgres.log'
    }
    It 'si pg_ctl start falla, lanza apuntando al log' {
        Mock Repair-ParkosLiteStalePid { 'clean' }
        Mock Invoke-ParkosLitePgCtlStart { @{ ExitCode = 1; Output = @('x') } }
        Mock New-Item { }
        { Start-ParkosLitePg -Paths $script:paths -Port 5434 } | Should Throw 'postgres.log'
    }
}

Describe 'Wait-ParkosLitePgReady' {
    It 'devuelve true en cuanto pg_isready responde 0' {
        $global:n = 0
        Mock Invoke-ParkosLiteNative { $global:n++; if ($global:n -lt 3) { @{ ExitCode = 2; Output = @() } } else { $script:ok } }
        Mock Start-Sleep { }
        (Wait-ParkosLitePgReady -PgRoot 'C:\lite\pgsql' -Port 5434 -TimeoutSec 30) | Should Be $true
        $global:n | Should Be 3
    }
    It 'devuelve false al agotar el tiempo' {
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 2; Output = @() } }
        Mock Start-Sleep { }
        (Wait-ParkosLitePgReady -PgRoot 'C:\lite\pgsql' -Port 5434 -TimeoutSec 2) | Should Be $false
    }
}

Describe 'Stop-ParkosLitePg' {
    It 'no hace nada si no esta corriendo' {
        $global:ctl = @()
        Mock Invoke-ParkosLiteNative { $global:ctl += ($Arguments -join ' '); @{ ExitCode = 3; Output = @() } }
        Mock Get-ParkosLiteProcessName { $null }
        Stop-ParkosLitePg -Paths $script:paths
        ($global:ctl | Where-Object { $_ -like 'stop*' }).Count | Should Be 0
    }
    It 'detiene en modo fast si esta corriendo' {
        $global:ctl = @()
        Mock Get-ParkosLiteProcessName { 'postgres' }
        Mock Test-Path { $true }
        Mock Get-Content { '4242' }
        Mock Invoke-ParkosLiteNative { $global:ctl += ($Arguments -join ' '); $script:ok }
        Stop-ParkosLitePg -Paths $script:paths
        ($global:ctl | Where-Object { $_ -like 'stop*-m fast*' }).Count | Should Be 1
    }
}

Describe 'Roles SQL' {
    It 'crea parkos superusuario de forma idempotente con su password' {
        $sql = Get-ParkosLiteRolesSql -SuperuserPassword 'supw'
        $sql | Should Match "IF NOT EXISTS \(SELECT 1 FROM pg_roles WHERE rolname = 'parkos'\)"
        $sql | Should Match "CREATE ROLE parkos LOGIN SUPERUSER PASSWORD 'supw'"
        $sql | Should Match "ALTER ROLE parkos WITH PASSWORD 'supw'"
    }
    It 'Initialize-ParkosLiteRoles crea la base solo si falta' {
        $global:sqls = @()
        Mock Invoke-ParkosLitePsql {
            $global:sqls += "$Sql|$($Arguments -join ' ')"
            if ($Arguments -contains '-tAc') { @{ ExitCode = 0; Output = @('') } } else { $script:ok }
        }
        Initialize-ParkosLiteRoles -Paths $script:paths -Port 5434 -Secrets $script:secrets
        ($global:sqls | Where-Object { $_ -like '*CREATE DATABASE parkos OWNER parkos*' }).Count | Should Be 1
        Mock Invoke-ParkosLitePsql {
            $global:sqls += "$Sql|$($Arguments -join ' ')"
            if ($Arguments -contains '-tAc') { @{ ExitCode = 0; Output = @('1') } } else { $script:ok }
        }
        $global:sqls = @()
        Initialize-ParkosLiteRoles -Paths $script:paths -Port 5434 -Secrets $script:secrets
        ($global:sqls | Where-Object { $_ -like '*CREATE DATABASE*' }).Count | Should Be 0
    }
}

Describe 'Migraciones' {
    It 'Get-ParkosLiteMigrateEnv usa la URL de superusuario sync y la password de la app' {
        $e = Get-ParkosLiteMigrateEnv -Port 5434 -Secrets $script:secrets
        $e['DATABASE_URL'] | Should Be 'postgresql://parkos:supw@127.0.0.1:5434/parkos'
        $e['PARKOS_APP_DB_PASSWORD'] | Should Be 'apppw'
    }
    It 'Invoke-ParkosLiteMigrate corre migrate.exe -c alembic.ini upgrade head desde su carpeta' {
        $global:mig = $null
        Mock Invoke-ParkosLiteNative { $global:mig = @{ File = $FilePath; Args = ($Arguments -join ' '); Cwd = $WorkingDirectory; Env = $Env }; $script:ok }
        Invoke-ParkosLiteMigrate -Paths $script:paths -Port 5434 -Secrets $script:secrets
        $global:mig.File | Should Be $script:paths.MigrateExe
        $global:mig.Args | Should Be '-c alembic.ini upgrade head'
        $global:mig.Cwd | Should Be $script:paths.MigrateDir
        $global:mig.Env['PARKOS_APP_DB_PASSWORD'] | Should Be 'apppw'
    }
    It 'si migrate falla lanza' {
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 1; Output = @('err') } }
        { Invoke-ParkosLiteMigrate -Paths $script:paths -Port 5434 -Secrets $script:secrets } | Should Throw 'upgrade head'
    }
}

Describe 'Seed' {
    It 'Get-ParkosLiteSeedArguments pasa uuid como variable psql, ON_ERROR_STOP y el archivo' {
        $a = Get-ParkosLiteSeedArguments -SeedSql 'C:\r\seed_demo.sql' -SucursalUuid $script:uuid
        ($a -join ' ') | Should Be "-v ON_ERROR_STOP=1 -v sucursal_uuid=$($script:uuid) -f C:\r\seed_demo.sql"
    }
    It 'rechaza un uuid que no es v4 (nunca llega a psql)' {
        { Get-ParkosLiteSeedArguments -SeedSql 'x.sql' -SucursalUuid "1'; DROP" } | Should Throw 'uuid'
    }
    It 'Invoke-ParkosLiteSeed corre psql como superusuario sobre la base parkos' {
        $global:seed = $null
        Mock Invoke-ParkosLitePsql { $global:seed = @{ User = $User; Db = $Database; Args = ($Arguments -join ' ') }; $script:ok }
        Invoke-ParkosLiteSeed -Paths $script:paths -Port 5434 -Secrets $script:secrets -SucursalUuid $script:uuid
        $global:seed.User | Should Be 'parkos'
        $global:seed.Db | Should Be 'parkos'
        $global:seed.Args | Should Match 'seed_demo.sql'
    }
    It 'si el seed falla lanza' {
        Mock Invoke-ParkosLitePsql { @{ ExitCode = 3; Output = @('x') } }
        { Invoke-ParkosLiteSeed -Paths $script:paths -Port 5434 -Secrets $script:secrets -SucursalUuid $script:uuid } | Should Throw 'seed'
    }
}

Describe 'Get-ParkosLiteDbFacts' {
    It 'con la DB apagada no consulta y marca DbReady false' {
        Mock Test-ParkosLitePgAccepting { $false }
        Mock Invoke-ParkosLitePsql { throw 'no deberia consultar' }
        $f = Get-ParkosLiteDbFacts -Paths $script:paths -Port 5434 -Secrets $script:secrets -SucursalUuid $script:uuid
        $f.DbReady | Should Be $false
        $f.SchemaMigrated | Should Be $false
        $f.Seeded | Should Be $false
    }
    It 'con la DB encendida lee esquema y seed' {
        Mock Test-ParkosLitePgAccepting { $true }
        Mock Invoke-ParkosLitePsql { @{ ExitCode = 0; Output = @('t') } }
        $f = Get-ParkosLiteDbFacts -Paths $script:paths -Port 5434 -Secrets $script:secrets -SucursalUuid $script:uuid
        $f.DbReady | Should Be $true
        $f.SchemaMigrated | Should Be $true
        $f.Seeded | Should Be $true
    }
}

# ---------------------------------------------------------------------------
# Paso 11: Postgres y pg_partman salen de las partes del repo (sin descargar)
# ---------------------------------------------------------------------------

function New-PartmanPartsFixture {
    param([string]$Root)
    $src = Join-Path $Root 'src'
    New-Item -ItemType Directory -Force -Path $src | Out-Null
    Set-Content (Join-Path $src 'pg_partman.control') "default_version = '5.1.0'"
    Set-Content (Join-Path $src 'pg_partman--5.1.0.sql') 'select 1;'
    $parts = Join-Path $Root 'parts'
    [void](Pack-ParkosPayloadArtifact -Source $src -Id 'pg_partman-extension' -PartsDir $parts -Target 'pg_partman\extension' -Logger { param($m) })
    return $parts
}

Describe 'Restore-ParkosLitePartmanFromParts' {
    It 'restaura la extension a <Downloads>\pg_partman\extension desde las partes (sin red)' {
        $root = Join-Path $TestDrive 'pm1'
        $parts = New-PartmanPartsFixture -Root $root
        $paths = @{ Downloads = (Join-Path $root 'dl'); PartsDir = $parts }
        (Restore-ParkosLitePartmanFromParts -Paths $paths -Logger { param($m) }) | Should Be $true
        (Test-ParkosPgPartmanExtensionDir -Dir (Join-Path $root 'dl\pg_partman\extension')) | Should Be $true
    }
    It 'si la extension ya esta en la cache no vuelve a restaurar' {
        $root = Join-Path $TestDrive 'pm2'
        $ext = Join-Path $root 'dl\pg_partman\extension'
        New-Item -ItemType Directory -Force -Path $ext | Out-Null
        Set-Content (Join-Path $ext 'pg_partman.control') 'x'
        Set-Content (Join-Path $ext 'pg_partman--5.1.0.sql') 'x'
        Mock Restore-ParkosPayloadArtifact { throw 'no deberia restaurar' }
        (Restore-ParkosLitePartmanFromParts -Paths @{ Downloads = (Join-Path $root 'dl'); PartsDir = (Join-Path $root 'parts') } -Logger { param($m) }) | Should Be $true
        Assert-MockCalled Restore-ParkosPayloadArtifact -Times 0 -Scope It
    }
    It 'sin partes en el repo devuelve $false (el llamador descarga)' {
        $root = Join-Path $TestDrive 'pm3'
        (Restore-ParkosLitePartmanFromParts -Paths @{ Downloads = (Join-Path $root 'dl'); PartsDir = (Join-Path $root 'nada') } -Logger { param($m) }) | Should Be $false
    }
    It 'partes danadas: devuelve $false y avisa (no rompe la instalacion)' {
        $root = Join-Path $TestDrive 'pm4'
        $parts = New-PartmanPartsFixture -Root $root
        $zip = Get-ChildItem (Join-Path $parts 'pg_partman-extension') -File | Select-Object -First 1
        [IO.File]::WriteAllBytes($zip.FullName, [byte[]](1..40))
        $script:msgs = @()
        (Restore-ParkosLitePartmanFromParts -Paths @{ Downloads = (Join-Path $root 'dl'); PartsDir = $parts } -Logger { param($m) $script:msgs += $m }) | Should Be $false
        ($script:msgs -join ' ') | Should Match 'se descarga'
    }
}

Describe 'Install-ParkosLiteDatabase: orden de origen' {
    BeforeEach {
        $script:order = @()
        $script:paths2 = @{ Downloads = 'C:\lite\downloads'; PgRoot = 'C:\lite\pgsql'; PgData = 'C:\lite\data\pg'; Logs = 'C:\lite\logs'
            PgPayload = 'C:\repo\installer\payload\parts\postgres'; PartmanPayload = 'C:\repo\installer\payload\pg_partman\extension'
            PartsDir = 'C:\repo\installer\payload\parts' }
        Mock Get-ParkosPostgresZip { $script:order += 'pgzip'; 'C:\lite\downloads\pg.zip' }
        Mock Expand-ParkosPostgresZip { $script:order += 'expand' }
        Mock Assert-ParkosLitePgRuntime { $script:order += 'runtime' }
        Mock Restore-ParkosLitePartmanFromParts { $script:order += 'partman-parts'; $true }
        Mock Get-ParkosPgPartmanExtension { $script:order += 'partman-ext'; 'C:\lite\downloads\pg_partman\extension' }
        Mock Install-ParkosPgPartmanExtension { }
        Mock Initialize-ParkosLitePgData { $true }
        Mock Start-ParkosLitePg { $true }
        Mock Initialize-ParkosLiteRoles { }
        Mock Enable-ParkosLitePartman { }
    }
    It 'Postgres se pide a las partes del repo (PgPayload) y pg_partman se restaura de partes antes de buscar/descargar' {
        Install-ParkosLiteDatabase -Paths $script:paths2 -Port 5433 -Secrets $script:secrets -Logger { param($m) }
        Assert-MockCalled Get-ParkosPostgresZip -ParameterFilter { $PayloadDir -eq 'C:\repo\installer\payload\parts\postgres' -and $CacheDir -eq 'C:\lite\downloads' } -Times 1 -Scope It
        ($script:order -join ',') | Should Be 'pgzip,expand,runtime,partman-parts,partman-ext'
    }
}
