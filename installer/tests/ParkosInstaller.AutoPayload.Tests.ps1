# Tests del instalador completo autosuficiente (rama
# feature/instalador_completo_automatico): lo aprendido del instalador lite.
#
#   - Get-ParkosPayloadBuildPlan / Get-ParkosPayloadBlockers: decision de
#     construir (exe faltantes, fuente mas nuevo que el exe mas viejo, MSI,
#     componentes de terceros) y bloqueos (sin fuente, sin toolchain).
#   - Stop-ParkosPayloadProcesses: cierra procesos propios que bloquean la
#     recompilacion (PyInstaller 'Acceso denegado' sobre un .pyd en uso).
#   - Invoke-ParkosEnsurePayload (etapa 0 guiada) e Invoke-ParkosPreparePayload
#     (-Command Prepare): orquestacion con mocks (nada compila ni descarga).
#   - Puertos por listeners reales (no por bind/connect de prueba).
#   - Saneamiento de particiones tras las migraciones.
#   - Respuestas sin intervencion: PARKOS_SUCURSAL_UUID / parkos-install.json.
#   - Pre-flight que agrega varios problemas, idempotencia por etapa, resumen.
#
# Pester 3.4.0: Mock sin -ModuleName; todo `Should Throw` lleva substring de
# mensaje; un Mock declarado dentro de un It se filtra a los siguientes, asi que
# los Mock de cada Describe leen variables $script: que cada It fija.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

function New-FakePayload {
    param([Parameter(Mandatory)][string]$Root, [string[]]$Without = @())
    $files = @(Get-ParkosExpectedPayloadExes) + @('apps\web_sucursal-0.0.1-x64.msi', 'nssm.exe', 'pg_partman\extension\pg_partman.control')
    foreach ($rel in $files) {
        if ($Without -contains $rel) { continue }
        $full = Join-Path $Root $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $full -Parent) | Out-Null
        Set-Content -Path $full -Value 'x'
        (Get-Item $full).LastWriteTimeUtc = [datetime]::new(2020, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)
    }
}

Describe 'Get-ParkosPayloadBuildPlan (decision de construir)' {

    Mock Get-ParkosSourceFileList { $script:SourceFiles }

    function New-FakeRepo {
        param([Parameter(Mandatory)][string]$Root, [datetime]$SourceTime)
        New-Item -ItemType Directory -Force -Path (Join-Path $Root 'backend') | Out-Null
        $f = Join-Path $Root 'backend\a.py'
        Set-Content $f 'x'
        (Get-Item $f).LastWriteTimeUtc = $SourceTime
        $script:SourceFiles = @('backend/a.py')
    }

    It 'payload completo y fuente mas viejo que el exe mas viejo: no hace falta construir' {
        $pl = Join-Path $TestDrive 'plan-ok'; $repo = Join-Path $TestDrive 'repo-ok'
        New-FakePayload -Root $pl
        New-FakeRepo -Root $repo -SourceTime ([datetime]::new(2019, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc))
        $plan = Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot $repo
        $plan.Needed | Should Be $false
        @($plan.Switches).Count | Should Be 0
    }

    It 'un exe faltante pide reconstruir los 5 programas congelados' {
        $pl = Join-Path $TestDrive 'plan-noexe'; $repo = Join-Path $TestDrive 'repo-noexe'
        New-FakePayload -Root $pl -Without @('services\seed\seed\seed.exe')
        New-FakeRepo -Root $repo -SourceTime ([datetime]::new(2019, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc))
        $plan = Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot $repo
        $plan.Needed | Should Be $true
        (@($plan.Switches) -join ',') | Should Be 'ApiSucursal,JobSync,Migrate,Seed,Doctor'
        ($plan.Reasons -join ' ') | Should Match 'seed.exe'
    }

    It 'un fuente mas nuevo que el exe MAS VIEJO pide reconstruir' {
        $pl = Join-Path $TestDrive 'plan-stale'; $repo = Join-Path $TestDrive 'repo-stale'
        New-FakePayload -Root $pl
        New-FakeRepo -Root $repo -SourceTime ([datetime]::new(2021, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc))
        $plan = Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot $repo
        $plan.Needed | Should Be $true
        ($plan.Reasons -join ' ') | Should Match 'mas nuevo'
    }

    It 'si no se puede listar el fuente (git falla) construye por seguridad' {
        $pl = Join-Path $TestDrive 'plan-nogit'
        New-FakePayload -Root $pl
        $script:SourceFiles = $null
        $plan = Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot (Join-Path $TestDrive 'repo-ok')
        $plan.Needed | Should Be $true
    }

    It 'sin repo (paquete entregado sin fuente) no compara fechas: con todo presente no construye' {
        $pl = Join-Path $TestDrive 'plan-norepo'
        New-FakePayload -Root $pl
        (Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot '').Needed | Should Be $false
    }

    It 'sin MSI pide -WebSucursal y sin nssm/pg_partman pide -Payload' {
        $pl = Join-Path $TestDrive 'plan-parts'
        New-FakePayload -Root $pl -Without @('apps\web_sucursal-0.0.1-x64.msi', 'nssm.exe')
        $plan = Get-ParkosPayloadBuildPlan -PayloadRoot $pl -RepoRoot ''
        (@($plan.Switches) -join ',') | Should Be 'Payload,WebSucursal'
    }
}

Describe 'Get-ParkosMissingBuildTools / Get-ParkosPayloadBlockers' {

    Mock Test-ParkosCommandAvailable { $script:Tools -contains $Name }

    It 'solo exige git+uv para los exe y node+pnpm para el MSI' {
        $script:Tools = @()
        (@(Get-ParkosMissingBuildTools -Switches @('Seed')) -join ',') | Should Be 'git,uv'
        (@(Get-ParkosMissingBuildTools -Switches @('WebSucursal')) -join ',') | Should Be 'node,pnpm'
        @(Get-ParkosMissingBuildTools -Switches @('Payload')).Count | Should Be 0
    }

    It 'con todo el toolchain no falta nada' {
        $script:Tools = @('git', 'uv', 'node', 'pnpm')
        @(Get-ParkosMissingBuildTools -Switches @('Seed', 'WebSucursal')).Count | Should Be 0
    }

    It 'sin necesidad de construir no hay bloqueos' {
        $plan = [PSCustomObject]@{ Needed = $false; Switches = @(); Reasons = @() }
        @(Get-ParkosPayloadBlockers -Plan $plan -RepoRoot 'C:\repo').Count | Should Be 0
    }

    It 'sin fuente y sin programas: UN mensaje que manda a pedir un instalador completo' {
        $plan = [PSCustomObject]@{ Needed = $true; Switches = @('Seed'); Reasons = @('x') }
        $b = @(Get-ParkosPayloadBlockers -Plan $plan -RepoRoot '')
        $b.Count | Should Be 1
        $b[0] | Should Match 'equipo de soporte'
    }

    It 'con fuente pero sin toolchain: UN mensaje con TODAS las herramientas faltantes' {
        $script:Tools = @('git')
        $plan = [PSCustomObject]@{ Needed = $true; Switches = @('Seed', 'WebSucursal'); Reasons = @('x') }
        $b = @(Get-ParkosPayloadBlockers -Plan $plan -RepoRoot 'C:\repo')
        $b.Count | Should Be 1
        $b[0] | Should Match 'uv, node, pnpm'
    }

    It 'con fuente y toolchain completo no bloquea (se construye solo)' {
        $script:Tools = @('git', 'uv', 'node', 'pnpm')
        $plan = [PSCustomObject]@{ Needed = $true; Switches = @('Seed', 'WebSucursal'); Reasons = @('x') }
        @(Get-ParkosPayloadBlockers -Plan $plan -RepoRoot 'C:\repo').Count | Should Be 0
    }
}

Describe 'Stop-ParkosPayloadProcesses (exe bloqueados antes de recompilar)' {

    Mock Write-Host { }
    Mock Start-Sleep { }
    Mock Stop-ParkosProcessById { $script:Stopped += $Id }
    Mock Get-ParkosPayloadLockingProcesses {
        @([PSCustomObject]@{ Id = 4101; ProcessName = 'api-sucursal' }, [PSCustomObject]@{ Id = 4102; ProcessName = 'migrate' })
    }

    It 'detiene cada proceso que bloquea archivos del payload y devuelve cuantos' {
        $script:Stopped = @()
        $n = Stop-ParkosPayloadProcesses -PayloadRoot 'C:\pl'
        $n | Should Be 2
        ($script:Stopped -join ',') | Should Be '4101,4102'
    }
}

Describe 'Get-ParkosPayloadLockingProcesses (filtro por ruta)' {

    It 'solo devuelve procesos cuyo exe vive bajo el payload o .pyinstaller-work (y nunca el propio)' {
        Mock Get-Process {
            @(
                [PSCustomObject]@{ Id = 11; ProcessName = 'api-sucursal'; Path = 'C:\inst\payload\services\api-sucursal\api-sucursal\api-sucursal.exe' }
                [PSCustomObject]@{ Id = 12; ProcessName = 'work'; Path = 'C:\inst\.pyinstaller-work\build\x.exe' }
                [PSCustomObject]@{ Id = 13; ProcessName = 'otro'; Path = 'C:\Windows\notepad.exe' }
                [PSCustomObject]@{ Id = 14; ProcessName = 'prefijo'; Path = 'C:\inst\payload-viejo\x.exe' }
                [PSCustomObject]@{ Id = $PID; ProcessName = 'yo'; Path = 'C:\inst\payload\yo.exe' }
                [PSCustomObject]@{ Id = 15; ProcessName = 'sinpath'; Path = $null }
            )
        }
        $ids = @(Get-ParkosPayloadLockingProcesses -PayloadRoot 'C:\inst\payload' | ForEach-Object { $_.Id })
        ($ids -join ',') | Should Be '11,12'
    }
}

Describe 'Get-ParkosBuildSteps' {
    It 'agrupa en terceros, MSI, un paso con todos los exe y (opcional) el exe del instalador' {
        $steps = @(Get-ParkosBuildSteps -Switches @('Payload', 'WebSucursal', 'ApiSucursal', 'JobSync', 'Migrate', 'Seed', 'Doctor') -IncludeInstallerExe)
        $steps.Count | Should Be 4
        ($steps[0].Switches -join ',') | Should Be 'Payload'
        ($steps[1].Switches -join ',') | Should Be 'WebSucursal'
        ($steps[2].Switches -join ',') | Should Be 'ApiSucursal,JobSync,Migrate,Seed,Doctor'
        ($steps[3].Switches -join ',') | Should Be 'Installer'
    }
    It 'solo los pasos que el plan pide' {
        $steps = @(Get-ParkosBuildSteps -Switches @('Seed', 'Doctor'))
        $steps.Count | Should Be 1
        ($steps[0].Switches -join ',') | Should Be 'Seed,Doctor'
    }
}

Describe 'Invoke-ParkosEnsurePayload (etapa 0 del flujo guiado)' {

    Mock Write-Host { }
    Mock Get-ParkosPayloadBuildPlan { $script:Plan }
    Mock Get-ParkosPayloadBlockers { $script:Blockers }
    Mock Stop-ParkosPayloadProcesses { $script:Calls += 'stop'; 0 }
    Mock Invoke-ParkosBuildReleaseScript { $script:Calls += ('build:' + ($Switches -join '+')); $script:BuildCode }
    Mock Test-ParkosPayloadReady { $script:Ready }

    BeforeEach {
        $script:Calls = @()
        $script:Blockers = @()
        $script:BuildCode = 0
        $script:Ready = $true
        $script:Plan = [PSCustomObject]@{ Needed = $true; Switches = @('WebSucursal', 'ApiSucursal', 'Migrate'); Reasons = @('faltan programas') }
    }

    It 'si ya esta todo al dia no compila ni cierra procesos' {
        $script:Plan = [PSCustomObject]@{ Needed = $false; Switches = @(); Reasons = @() }
        Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs'
        @($script:Calls).Count | Should Be 0
    }

    It 'cierra primero los procesos que bloquean y luego construye por pasos y al final el manifest' {
        Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs'
        ($script:Calls -join '|') | Should Be 'stop|build:WebSucursal|build:ApiSucursal+Migrate|build:Manifest'
    }

    It 'muestra el avance como "n de m"' {
        Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs'
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -match 'Preparando 1 de 3' }
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -match 'Preparando 3 de 3' }
    }

    It 'si hay bloqueos (sin toolchain) lanza el mensaje y NO toca nada' {
        $script:Blockers = @('falta instalar: uv')
        { Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs' } | Should Throw 'falta instalar: uv'
        @($script:Calls).Count | Should Be 0
    }

    It 'si un paso de build falla corta con el codigo y no genera el manifest' {
        $script:BuildCode = 7
        { Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs' } | Should Throw 'codigo 7'
        (@($script:Calls | Where-Object { $_ -like 'build:*' })).Count | Should Be 1
    }

    It 'si tras construir sigue incompleto lo informa' {
        $script:Ready = $false
        { Invoke-ParkosEnsurePayload -PayloadRoot 'C:\pl' -RepoRoot 'C:\repo' -LogDir 'C:\logs' } | Should Throw 'siguen faltando'
    }
}

Describe 'Invoke-ParkosPreparePayload (-Command Prepare)' {

    Mock Write-Host { }
    Mock Get-ParkosRepoRoot { 'C:\repo' }
    Mock Get-ParkosMissingBuildTools { $script:MissingTools }
    Mock Resolve-ParkosMasterKeySource { $script:KeySource }
    Mock Import-ParkosMasterKey { $script:Calls += "import:$SourcePath" }
    Mock Get-ParkosMasterKeyProblem { $script:KeyProblem }
    Mock Stop-ParkosPayloadProcesses { $script:Calls += 'stop'; 0 }
    Mock Invoke-ParkosBuildReleaseScript { $script:Calls += ('build:' + ($Switches -join '+')); 0 }
    Mock Get-ParkosPostgresPayloadProblem { $script:PgProblem }
    Mock Get-ParkosPayloadCompletenessProblems { $script:Problems }

    BeforeEach {
        $script:Calls = @()
        $script:MissingTools = @()
        $script:KeySource = ''
        $script:KeyProblem = $null
        $script:PgProblem = $null
        $script:Problems = @()
    }

    It 'orquesta todo: clave, cierre de procesos, build de todo (incluye exe del instalador), Postgres y manifest' {
        $script:KeySource = 'D:\k\master.key'
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 0
        ($script:Calls -join '|') | Should Be 'import:D:\k\master.key|stop|build:Payload|build:WebSucursal|build:ApiSucursal+JobSync+Migrate+Seed+Doctor|build:Installer|build:Manifest'
    }

    It 'sin clave en ninguna fuente falla con la pista de PARKOS_MASTER_KEY_FILE' {
        $script:KeyProblem = 'No se encontro la clave maestra'
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 1
        $r.Detail | Should Match 'PARKOS_MASTER_KEY_FILE'
        @($script:Calls).Count | Should Be 0
    }

    It 'sin toolchain falla UNA vez listando todo lo que falta y sin compilar' {
        $script:MissingTools = @('git', 'uv', 'node')
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 1
        $r.Detail | Should Match 'git, uv, node'
        @($script:Calls).Count | Should Be 0
    }

    It 'si solo hay partes versionadas de Postgres NO descarga ni crea el zip (solo verifica)' {
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 0
        Assert-MockCalled Get-ParkosPostgresPayloadProblem -Scope It -Times 1 -Exactly
    }

    It 'sin partes ni zip de Postgres falla con el comando git para restaurarlas' {
        $script:PgProblem = 'faltan las partes versionadas de Postgres (git checkout -- installer/payload/parts)'
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 1
        $r.Detail | Should Match 'git checkout'
    }

    It 'si la verificacion final encuentra faltantes devuelve ExitCode 1 con la lista' {
        $script:Problems = @('falta nssm.exe')
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 1
        $r.Detail | Should Match 'nssm.exe'
    }
}

Describe 'Get-ParkosPostgresPayloadProblem / Get-ParkosPayloadCompletenessProblems' {

    Mock Test-ParkosPostgresZip { $true }

    It 'partes + sidecar versionados son suficientes (sin zip completo)' {
        $pl = Join-Path $TestDrive 'pg-parts'
        $name = (Get-ParkosPostgresDownloadInfo).FileName
        New-Item -ItemType Directory -Force -Path (Join-Path $pl 'postgres') | Out-Null
        foreach ($i in 1, 2) { Set-Content (Join-Path $pl ("postgres\$name.part{0:D2}" -f $i)) 'x' }
        Set-Content (Join-Path $pl "postgres\$name.sha256") 'h'
        Get-ParkosPostgresPayloadProblem -PayloadRoot $pl | Should Be $null
    }

    It 'sin partes ni zip dice como restaurarlas' {
        $pl = Join-Path $TestDrive 'pg-none'
        New-Item -ItemType Directory -Force -Path (Join-Path $pl 'postgres') | Out-Null
        Get-ParkosPostgresPayloadProblem -PayloadRoot $pl | Should Match 'git checkout'
    }

    It 'un hueco en las partes se informa' {
        $pl = Join-Path $TestDrive 'pg-gap'
        $name = (Get-ParkosPostgresDownloadInfo).FileName
        New-Item -ItemType Directory -Force -Path (Join-Path $pl 'postgres') | Out-Null
        foreach ($i in 1, 3) { Set-Content (Join-Path $pl ("postgres\$name.part{0:D2}" -f $i)) 'x' }
        Set-Content (Join-Path $pl "postgres\$name.sha256") 'h'
        Get-ParkosPostgresPayloadProblem -PayloadRoot $pl | Should Match 'Falta la parte 02'
    }

    It 'el chequeo de payload completo lista TODO lo que falta' {
        $pl = Join-Path $TestDrive 'pg-empty'
        New-Item -ItemType Directory -Force -Path $pl | Out-Null
        $p = @(Get-ParkosPayloadCompletenessProblems -PayloadRoot $pl)
        ($p -join ' ') | Should Match 'api-sucursal.exe'
        ($p -join ' ') | Should Match 'MSI'
        ($p -join ' ') | Should Match 'manifest.sha256.json'
        ($p -join ' ') | Should Match 'parkos-master.key'
        $p.Count | Should BeGreaterThan 8
    }
}

Describe 'Puertos: listeners reales, no un connect de prueba' {

    Mock Get-ParkosListeningPorts { $script:Busy }
    Mock Test-NetConnection { throw 'no debe usarse Test-NetConnection para elegir puertos' }

    It 'Select-ParkosFreePort salta los puertos que algun proceso (p.ej. Docker) escucha' {
        $script:Busy = @(5432)
        Select-ParkosFreePort -CandidatePorts @(5432, 5433) | Should Be 5433
    }

    It 'Select-ParkosFreePort devuelve $null si todos estan ocupados' {
        $script:Busy = @(8000, 8001)
        Select-ParkosFreePort -CandidatePorts @(8000, 8001) | Should Be $null
    }

    It 'Test-PostgresPorts elige 5433 cuando Docker retiene 5432 y nunca llama Test-NetConnection' {
        $script:Busy = @(5432)
        Test-PostgresPorts | Should Be 5433
        Assert-MockCalled Test-NetConnection -Scope It -Times 0 -Exactly
    }

    It 'Test-PostgresPorts lanza un mensaje claro si 5432..5439 estan todos ocupados' {
        $script:Busy = @(5432..5439)
        { Test-PostgresPorts } | Should Throw 'estan todos ocupados'
    }

    It 'Test-ApiPort elige el primer puerto libre desde 8000' {
        $script:Busy = @(8000, 8001)
        Test-ApiPort | Should Be 8002
    }

    It 'Test-ApiPort lanza si no queda ninguno de los candidatos' {
        $script:Busy = @(8000, 8001, 8002)
        { Test-ApiPort -CandidatePorts @(8000, 8001, 8002) } | Should Throw 'todos ocupados'
    }
}

Describe 'Invoke-ParkosPartitionSanity' {

    Mock Write-Host { }
    Mock Invoke-ParkosPsqlScalar { [PSCustomObject]@{ ExitCode = $script:PsqlCode; Output = $script:PsqlOut } }

    It 'ejecuta SELECT prod.fn_ensure_partitions() como parkos en el puerto indicado' {
        $script:PsqlCode = 0; $script:PsqlOut = ''
        Invoke-ParkosPartitionSanity -PsqlPath 'C:\pg\psql.exe' -Port 5433
        Assert-MockCalled Invoke-ParkosPsqlScalar -Scope It -Times 1 -Exactly -ParameterFilter {
            $Sql -like '*prod.fn_ensure_partitions()*' -and $Port -eq 5433 -and $User -eq 'parkos'
        }
    }

    It 'si psql falla lanza con el motivo (no sigue con particiones sin crear)' {
        $script:PsqlCode = 3; $script:PsqlOut = 'function does not exist'
        { Invoke-ParkosPartitionSanity -PsqlPath 'C:\pg\psql.exe' -Port 5432 } | Should Throw 'particiones'
    }
}

Describe 'Etapa 2 (migraciones) corre el saneamiento de particiones DESPUES de migrar' {

    It 'Invoke-MigrationsAndSeed y luego Invoke-ParkosPartitionSanity' {
        $script:order = @()
        $script:roles = @{ SuperuserPassword = 's'; AppPassword = 'a' }
        $script:port = 5433
        Mock Invoke-MigrationsAndSeed { $script:order += 'migrate' }
        Mock Invoke-ParkosPartitionSanity { $script:order += "partitions:$Port" }
        $defs = Get-ParkosStageDefinitions -InstallPath (Join-Path $TestDrive 'i') -DataPath (Join-Path $TestDrive 'd') `
            -SucursalUuid '00000000-0000-0000-0000-000000000001' -CloudApiUrl 'https://cloud.invalid'
        & $defs.Stages['2'].Action
        ($script:order -join ',') | Should Be 'migrate,partitions:5433'
    }
}

Describe 'Respuestas sin intervencion (UUID por variable de entorno o parkos-install.json)' {

    Mock Get-ParkosEnvironmentValue { $script:EnvValue }

    BeforeEach {
        $script:EnvValue = $null
        $script:ParkosAnswersParam = ''
        $script:answers = Join-Path $TestDrive "answers-$(Get-Random).json"
    }
    AfterEach { $script:ParkosAnswersParam = '' }

    It 'sin ninguna fuente devuelve vacio' {
        Resolve-ParkosSucursalUuidSource | Should Be ''
    }

    It 'prioridad: parametro > variable de entorno > archivo' {
        Set-Content $script:answers '{ "sucursalUuid": "33333333-3333-3333-3333-333333333333" }'
        $script:ParkosAnswersParam = $script:answers
        $script:EnvValue = '22222222-2222-2222-2222-222222222222'
        Resolve-ParkosSucursalUuidSource -Explicit '11111111-1111-1111-1111-111111111111' | Should Be '11111111-1111-1111-1111-111111111111'
        Resolve-ParkosSucursalUuidSource | Should Be '22222222-2222-2222-2222-222222222222'
        $script:EnvValue = $null
        Resolve-ParkosSucursalUuidSource | Should Be '33333333-3333-3333-3333-333333333333'
    }

    It 'Read-SucursalUuid toma el UUID de la variable de entorno SIN preguntar' {
        Mock Read-Host { throw 'no deberia preguntar' }
        Mock Write-Host { }
        $script:EnvValue = '2222AAAA-2222-2222-2222-222222222222'
        Read-SucursalUuid | Should Be '2222aaaa-2222-2222-2222-222222222222'
        Assert-MockCalled Read-Host -Scope It -Times 0 -Exactly
    }

    It 'un -AnswersPath inexistente falla con mensaje claro' {
        $script:ParkosAnswersParam = (Join-Path $TestDrive 'no-existe.json')
        { Get-ParkosInstallAnswer -Name 'sucursalUuid' } | Should Throw '-AnswersPath'
    }

    It 'un JSON invalido falla con mensaje claro' {
        Set-Content $script:answers '{ esto no es json'
        $script:ParkosAnswersParam = $script:answers
        { Get-ParkosInstallAnswer -Name 'sucursalUuid' } | Should Throw 'JSON valido'
    }

    It 'eulaAccepted:true en el archivo acepta el EULA sin Read-Host' {
        Mock Read-Host { throw 'no deberia preguntar' }
        Set-Content $script:answers '{ "eulaAccepted": true }'
        $script:ParkosAnswersParam = $script:answers
        Test-ParkosEulaPreAccepted | Should Be $true
        Show-Eula | Should Be $true
    }

    It 'cloudApiUrl del archivo se usa cuando no hay parametro ni variable' {
        Set-Content $script:answers '{ "cloudApiUrl": "https://desde-archivo.example.test/" }'
        $script:ParkosAnswersParam = $script:answers
        Resolve-ParkosCloudApiUrl | Should Be 'https://desde-archivo.example.test'
    }

    It 'Resolve-ParkosMasterKeySource: parametro > PARKOS_MASTER_KEY_FILE > vacio' {
        Resolve-ParkosMasterKeySource | Should Be ''
        $script:EnvValue = 'D:\ci\master.key'
        Resolve-ParkosMasterKeySource | Should Be 'D:\ci\master.key'
        Resolve-ParkosMasterKeySource -Explicit 'E:\otra.key' | Should Be 'E:\otra.key'
    }
}

Describe 'Test-Preflight agrega TODOS los problemas bloqueantes de una vez' {

    Mock Write-Host { }
    Mock Test-NetConnection { $true }
    Mock Get-ParkosMasterKeyProblem { 'clave maestra ausente' }

    It 'muestra [FALLO] por cada problema (programas x2 + clave maestra) y devuelve $false' {
        $ok = Test-Preflight -InstallPath "$env:SystemDrive\Parkos" -DataPath (Join-Path $TestDrive 'pf-agg') `
            -CloudApiUrl 'https://cloud.example.test' -RequireMasterKey `
            -ExtraProblems @('falta instalar: uv', 'falta instalar: node')
        $ok | Should Be $false
        Assert-MockCalled Write-Host -Scope It -Times 2 -Exactly -ParameterFilter { $Object -match '^\[FALLO\] Programas de Parkos' }
        Assert-MockCalled Write-Host -Scope It -Times 1 -Exactly -ParameterFilter { $Object -match '^\[FALLO\] Clave maestra' }
        Assert-MockCalled Write-Host -Scope It -Times 1 -ParameterFilter { $Object -match 'falta instalar: uv' }
        Assert-MockCalled Write-Host -Scope It -Times 1 -ParameterFilter { $Object -match 'falta instalar: node' }
    }
}

Describe 'Get-ParkosStageSkipReason / Restore-ParkosDatabaseContext (idempotencia guiada)' {

    $uuid = '11111111-1111-1111-1111-111111111111'

    Mock Get-ParkosServiceState { $script:SvcState }
    Mock Read-ParkosEnvLines { @("PARKOS_SUCURSAL_UUID=$($script:EnvUuid)", 'PORT=8003') }
    Mock Get-EnvFilePostgresPort { 5433 }
    Mock Invoke-ParkosPgIsReady { $script:PgReady }
    Mock Test-ParkosElectronInstalled { $script:Electron }
    Mock New-ParkosDerivedPassword { "pw-$Purpose" }

    BeforeEach {
        $script:SvcState = 'Running'
        $script:EnvUuid = '11111111-1111-1111-1111-111111111111'
        $script:PgReady = 0
        $script:Electron = $false
        $script:envFile = Join-Path $TestDrive 'skip.env'
        Set-Content $script:envFile 'x=1'
    }

    It 'etapa 1: servicio corriendo, responde y el .env es de esta sucursal -> se omite' {
        Get-ParkosStageSkipReason -Number 1 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Match 'base de datos ya esta'
    }
    It 'etapa 1: servicio detenido -> corre' {
        $script:SvcState = 'Stopped'
        Get-ParkosStageSkipReason -Number 1 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Be $null
    }
    It 'etapa 1: .env de OTRA sucursal -> corre' {
        $script:EnvUuid = '99999999-9999-9999-9999-999999999999'
        Get-ParkosStageSkipReason -Number 1 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Be $null
    }
    It 'etapa 1: Postgres no responde -> corre' {
        $script:PgReady = 2
        Get-ParkosStageSkipReason -Number 1 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Be $null
    }
    It 'etapa 1: sin .env -> corre' {
        Get-ParkosStageSkipReason -Number 1 -EnvFilePath (Join-Path $TestDrive 'no.env') -SucursalUuid $uuid | Should Be $null
    }
    It 'etapa 7: app ya instalada -> se omite; si no, corre' {
        $script:Electron = $true
        Get-ParkosStageSkipReason -Number 7 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Match 'ya esta instalada'
        $script:Electron = $false
        Get-ParkosStageSkipReason -Number 7 -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Be $null
    }
    It 'las etapas baratas e idempotentes (2,3,4,5,6,8) NUNCA se omiten' {
        foreach ($n in 2, 3, 4, 5, 6, 8) {
            Get-ParkosStageSkipReason -Number $n -EnvFilePath $script:envFile -SucursalUuid $uuid | Should Be $null
        }
    }
    It 'Restore-ParkosDatabaseContext recupera puertos del .env y re-deriva las contrasenas' {
        Restore-ParkosDatabaseContext -EnvFilePath $script:envFile -SucursalUuid $uuid
        $script:port | Should Be 5433
        $script:apiPort | Should Be 8003
        $script:roles.SuperuserPassword | Should Be 'pw-parkos-superuser'
        $script:roles.AppPassword | Should Be 'pw-parkos-app'
    }
}

Describe 'Remove-ParkosNssmServiceIfPresent (servicios re-registrables)' {

    function global:fakenssm { $global:NssmCalls += ($args -join ' ') }

    It 'si el servicio existe: stop + remove confirm' {
        $global:NssmCalls = @()
        Mock Get-ParkosServiceState { 'Running' }
        Remove-ParkosNssmServiceIfPresent -NssmPath 'fakenssm' -Name 'ParkosApiSucursal'
        ($global:NssmCalls -join '|') | Should Be 'stop ParkosApiSucursal|remove ParkosApiSucursal confirm'
    }

    It 'si no existe no llama a nssm' {
        $global:NssmCalls = @()
        Mock Get-ParkosServiceState { $null }
        Remove-ParkosNssmServiceIfPresent -NssmPath 'fakenssm' -Name 'ParkosApiSucursal'
        @($global:NssmCalls).Count | Should Be 0
    }
}

Describe 'Write-ParkosInstallSummary (pantalla final en lenguaje llano)' {

    Mock Get-EnvFilePostgresPort { 5433 }
    Mock Read-ParkosEnvLines { @('PORT=8002') }
    Mock Write-Host { $script:Out += [string]$Object }

    It 'dice que se instalo, URLs/puertos, donde estan los registros, como comprobar y como desinstalar' {
        $script:Out = @()
        Write-ParkosInstallSummary -InstallPath 'C:\P' -DataPath 'C:\D' -LogPath 'C:\D\installer-runs\x.log'
        $text = $script:Out -join "`n"
        $text | Should Match 'http://127.0.0.1:8002/health'
        $text | Should Match 'puerto 5433'
        $text | Should Match 'C:\\D\\installer-runs\\x.log'
        $text | Should Match 'Get-ParkosHealth'
        $text | Should Match 'Uninstall-Parkos'
        $text | Should Match 'sincronizacion'
    }
}

Describe 'build-release.ps1 (contrato estatico)' {
    $src = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot '..\build-release.ps1'))

    It 'acepta -MasterKeyPath y PARKOS_MASTER_KEY_FILE y nunca genera la clave' {
        $src | Should Match '\[string\]\$MasterKeyPath'
        $src | Should Match 'PARKOS_MASTER_KEY_FILE'
        $src | Should Not Match 'RandomNumberGenerator'
    }
    It 'tiene -Manifest y el manifest cubre las partes versionadas (payload\parts, incluida Postgres y su sidecar)' {
        $src | Should Match '\[switch\]\$Manifest'
        $src | Should Match "Join-Path \`$PayloadRoot 'parts'"
        # Enumeracion .NET (no Get-ChildItem.FullName): robusta ante rutas cortas 8.3.
        $src | Should Match 'EnumerateFiles\(\$partsBase'
        $src | Should Match 'SearchOption\]::AllDirectories'
        $src | Should Match "'ParkosPayloadParts\.ps1'"
    }
    It 'tiene -Pack y -Restore y los cuenta como switches (no disparan el build completo)' {
        $src | Should Match '\[switch\]\$Pack'
        $src | Should Match '\[switch\]\$Restore'
        $src | Should Match '\$Manifest -or \$Pack -or \$Restore'
        $src | Should Match 'Invoke-ParkosPackPayload'
        $src | Should Match 'Restore-ParkosPayloadAll'
    }
    It 'restaura de payload\parts antes de descargar los terceros' {
        $src | Should Match "Restore-PayloadFromParts -Id 'powershell7-msi'"
        $src | Should Match "Restore-PayloadFromParts -Id 'nssm'"
        $src | Should Match "Restore-PayloadFromParts -Id 'pg_partman-extension'"
    }
    It 'sigue siendo analizable por el parser de PowerShell' {
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($src, [ref]$null, [ref]$errors)
        @($errors).Count | Should Be 0
    }
}
