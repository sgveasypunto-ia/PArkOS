# Tests de installer/lite/ParkosLite.Run.ps1: configuracion inicial (uuid,
# puertos, secretos, env file), arranque/parada de API (exe) y front (Vite),
# 'Iniciar todo', 'Detener todo' y el refresh desde dev. Procesos, git, red y
# builds pasan por wrappers que se mockean aqui; nada real se ejecuta.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Core.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Tools.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Autostart.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Run.ps1')

$script:quiet = { param($m) }

function New-TestCtx {
    param([string]$Name)
    $lite = Join-Path $TestDrive $Name
    $paths = Get-ParkosLitePaths -LitePath $lite -RepoRoot (Join-Path $TestDrive "$Name-repo")
    $state = New-ParkosLiteState
    return @{ Paths = $paths; State = $state; Secrets = @{ PostgresPassword = 'p'; SuperuserPassword = 's'; AppPassword = 'a' }; Branch = 'dev'; Logger = $script:quiet; ScriptPath = 'C:\x\parkos-lite.ps1' }
}

Describe 'Initialize-ParkosLiteConfig' {
    It 'genera uuid v4, puertos, secretos, llave jwt y env file (y los persiste)' {
        Mock Test-ParkosLitePortInUse { $false }
        Mock New-ParkosLiteJwtKey { param($Path) New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null; Set-Content $Path 'k' }
        $ctx = New-TestCtx 'cfg1'
        Initialize-ParkosLiteConfig -Ctx $ctx -DbPortRequested 0 -ApiPortRequested 0 -FrontPortRequested 0
        (Test-ParkosUuidV4 -Value $ctx.State.sucursal_uuid) | Should Be $true
        $ctx.State.db_port | Should Be 5433
        $ctx.State.api_port | Should Be 8100
        $ctx.State.front_port | Should Be 5173
        (Test-Path $ctx.Paths.EnvFile) | Should Be $true
        $env = Read-ParkosLiteEnvFile -Path $ctx.Paths.EnvFile
        $env['PARKOS_SUCURSAL_UUID'] | Should Be $ctx.State.sucursal_uuid
        $env['PORT'] | Should Be '8100'
        (Test-Path $ctx.Paths.Secrets) | Should Be $true
        (Test-Path $ctx.Paths.State) | Should Be $true
    }
    It 'es idempotente: segunda corrida conserva uuid, secretos y puertos' {
        Mock Test-ParkosLitePortInUse { $false }
        Mock New-ParkosLiteJwtKey { param($Path) New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null; Set-Content $Path 'k' }
        $ctx = New-TestCtx 'cfg2'
        Initialize-ParkosLiteConfig -Ctx $ctx
        $uuid = $ctx.State.sucursal_uuid
        $pw = (Read-ParkosLiteSecrets -Path $ctx.Paths.Secrets).AppPassword
        $ctx2 = New-TestCtx 'cfg2'
        $ctx2.State = Read-ParkosLiteState -Path $ctx.Paths.State
        Initialize-ParkosLiteConfig -Ctx $ctx2
        $ctx2.State.sucursal_uuid | Should Be $uuid
        (Read-ParkosLiteSecrets -Path $ctx2.Paths.Secrets).AppPassword | Should Be $pw
        $ctx2.State.db_port | Should Be 5433
    }
    It 'el puerto de API ocupado se reemplaza por el siguiente libre' {
        Mock Test-ParkosLitePortInUse { param($Port) $Port -eq 8100 }
        Mock New-ParkosLiteJwtKey { param($Path) New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null; Set-Content $Path 'k' }
        $ctx = New-TestCtx 'cfg3'
        Initialize-ParkosLiteConfig -Ctx $ctx
        $ctx.State.api_port | Should Be 8101
        (Read-ParkosLiteEnvFile -Path $ctx.Paths.EnvFile)['PORT'] | Should Be '8101'
    }
}

Describe 'Get-ParkosLiteViteArguments' {
    It 'enlaza a loopback con puerto estricto' {
        $a = Get-ParkosLiteViteArguments -ViteJs 'C:\a\vite.js' -Port 5173
        ($a -join ' ') | Should Be '"C:\a\vite.js" --port 5173 --host 127.0.0.1 --strictPort'
    }
}

Describe 'Procesos (pid files)' {
    It 'Save/Get-ParkosLitePid hace roundtrip y un pid muerto devuelve $null' {
        $ctx = New-TestCtx 'pid1'
        Save-ParkosLitePid -Paths $ctx.Paths -Name 'api' -ProcessId 4242
        Mock Get-ParkosLiteProcessName { 'api-sucursal' }
        (Get-ParkosLiteLivePid -Paths $ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal') | Should Be 4242
        Mock Get-ParkosLiteProcessName { $null }
        (Get-ParkosLiteLivePid -Paths $ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal') | Should Be $null
    }
    It 'un pid reutilizado por otro proceso no cuenta como el servicio' {
        $ctx = New-TestCtx 'pid2'
        Save-ParkosLitePid -Paths $ctx.Paths -Name 'api' -ProcessId 4242
        Mock Get-ParkosLiteProcessName { 'chrome' }
        (Get-ParkosLiteLivePid -Paths $ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal') | Should Be $null
    }
}

Describe 'Start-ParkosLiteApi' {
    It 'carga el env file al entorno del proceso, redirige logs y guarda el pid' {
        $ctx = New-TestCtx 'api1'
        Write-ParkosLiteEnvFile -Path $ctx.Paths.EnvFile -Lines @('PORT=8101', 'PARKOS_DEPLOY=branch')
        $global:started = $null
        Mock Get-ParkosLiteLivePid { $null }
        Mock Start-ParkosLiteProcess { $global:started = @{ File = $FilePath; Env = $Env; Out = $StdOut; Err = $StdErr; Cwd = $WorkingDirectory }; 777 }
        $pidv = Start-ParkosLiteApi -Ctx $ctx
        $pidv | Should Be 777
        $global:started.File | Should Be $ctx.Paths.ApiExe
        $global:started.Env['PORT'] | Should Be '8101'
        $global:started.Out | Should Match 'api.out.log'
        $global:started.Err | Should Match 'api.err.log'
        (Get-Content (Join-Path $ctx.Paths.Run 'api.pid') -Raw).Trim() | Should Be '777'
    }
    It 'si ya corre no lo vuelve a lanzar' {
        $ctx = New-TestCtx 'api2'
        Mock Get-ParkosLiteLivePid { 555 }
        Mock Start-ParkosLiteProcess { throw 'no deberia lanzar' }
        (Start-ParkosLiteApi -Ctx $ctx) | Should Be 555
    }
}

Describe 'Start-ParkosLiteFront' {
    It 'lanza node con vite y PARKOS_API_PORT apuntando al puerto de la API' {
        $ctx = New-TestCtx 'fr1'
        $ctx.State.api_port = 8101; $ctx.State.front_port = 5173
        New-Item -ItemType Directory -Force -Path (Join-Path $ctx.Paths.FrontDir 'node_modules\vite\bin') | Out-Null
        Set-Content (Join-Path $ctx.Paths.FrontDir 'node_modules\vite\bin\vite.js') '//'
        $global:started = $null
        Mock Get-ParkosLiteLivePid { $null }
        Mock Get-ParkosLiteNodePath { 'C:\node\node.exe' }
        Mock Start-ParkosLiteProcess { $global:started = @{ File = $FilePath; Args = $Arguments; Env = $Env; Cwd = $WorkingDirectory }; 888 }
        (Start-ParkosLiteFront -Ctx $ctx) | Should Be 888
        $global:started.File | Should Be 'C:\node\node.exe'
        $global:started.Env['PARKOS_API_PORT'] | Should Be '8101'
        $global:started.Cwd | Should Be $ctx.Paths.FrontDir
        ($global:started.Args -join ' ') | Should Match '--port 5173'
    }
    It 'sin vite instalado falla con el paso a correr' {
        $ctx = New-TestCtx 'fr2'
        Mock Get-ParkosLiteLivePid { $null }
        Mock Get-ParkosLiteNodePath { 'C:\node\node.exe' }
        { Start-ParkosLiteFront -Ctx $ctx } | Should Throw 'dependencias del front'
    }
}

Describe 'Stop-ParkosLiteService' {
    It 'mata el arbol del proceso y borra el pid file' {
        $ctx = New-TestCtx 'stop1'
        Save-ParkosLitePid -Paths $ctx.Paths -Name 'api' -ProcessId 4242
        $global:killed = @()
        Mock Get-ParkosLiteLivePid { 4242 }
        Mock Stop-ParkosLiteProcessTree { $global:killed += $ProcessId }
        (Stop-ParkosLiteService -Paths $ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal') | Should Be $true
        $global:killed -contains 4242 | Should Be $true
        (Test-Path (Join-Path $ctx.Paths.Run 'api.pid')) | Should Be $false
    }
    It 'sin proceso vivo no hace nada y limpia un pid file viejo' {
        $ctx = New-TestCtx 'stop2'
        Save-ParkosLitePid -Paths $ctx.Paths -Name 'api' -ProcessId 1
        Mock Get-ParkosLiteLivePid { $null }
        Mock Stop-ParkosLiteProcessTree { throw 'no deberia matar' }
        (Stop-ParkosLiteService -Paths $ctx.Paths -Name 'api' -ExpectedProcess 'api-sucursal') | Should Be $false
        (Test-Path (Join-Path $ctx.Paths.Run 'api.pid')) | Should Be $false
    }
}

Describe 'Wait-ParkosLiteHttp' {
    It 'reintenta hasta recibir el status esperado' {
        $global:n = 0
        Mock Invoke-ParkosLiteHttpGet { $global:n++; if ($global:n -lt 3) { 0 } else { 200 } }
        Mock Start-Sleep { }
        (Wait-ParkosLiteHttp -Url 'http://x/health' -TimeoutSec 10) | Should Be $true
        $global:n | Should Be 3
    }
    It 'devuelve false al agotar el tiempo' {
        Mock Invoke-ParkosLiteHttpGet { 0 }
        Mock Start-Sleep { }
        (Wait-ParkosLiteHttp -Url 'http://x/health' -TimeoutSec 2) | Should Be $false
    }
}

Describe 'Start-ParkosLiteAll / Stop-ParkosLiteAll' {
    It 'arranca DB, espera, API (health), front, en ese orden' {
        $ctx = New-TestCtx 'all1'
        $ctx.State.db_port = 5434; $ctx.State.api_port = 8101; $ctx.State.front_port = 5173
        $global:order = @()
        Mock Start-ParkosLitePg { $global:order += 'db'; $true }
        Mock Start-ParkosLiteApi { $global:order += 'api'; 1 }
        Mock Start-ParkosLiteFront { $global:order += 'front'; 2 }
        Mock Wait-ParkosLiteHttp { $global:order += "wait:$Url"; $true }
        Start-ParkosLiteAll -Ctx $ctx
        ($global:order -join ',') | Should Be 'db,api,wait:http://127.0.0.1:8101/health,front,wait:http://127.0.0.1:5173/'
    }
    It 'si la API no queda sana lanza apuntando a los logs y no arranca el front' {
        $ctx = New-TestCtx 'all2'
        $ctx.State.db_port = 5434; $ctx.State.api_port = 8101; $ctx.State.front_port = 5173
        $global:order = @()
        Mock Start-ParkosLitePg { $true }
        Mock Start-ParkosLiteApi { 1 }
        Mock Start-ParkosLiteFront { $global:order += 'front'; 2 }
        Mock Wait-ParkosLiteHttp { $false }
        { Start-ParkosLiteAll -Ctx $ctx } | Should Throw 'api.err.log'
        $global:order.Count | Should Be 0
    }
    It '-DbOnly solo levanta la base de datos (autoarranque modo Db)' {
        $ctx = New-TestCtx 'all3'
        $ctx.State.db_port = 5434
        $global:order = @()
        Mock Start-ParkosLitePg { $global:order += 'db'; $true }
        Mock Start-ParkosLiteApi { $global:order += 'api'; 1 }
        Start-ParkosLiteAll -Ctx $ctx -DbOnly
        ($global:order -join ',') | Should Be 'db'
    }
    It 'Stop-ParkosLiteAll detiene front, api y db en ese orden' {
        $ctx = New-TestCtx 'all4'
        $global:order = @()
        Mock Stop-ParkosLiteService { $global:order += $Name; $true }
        Mock Stop-ParkosLitePg { $global:order += 'db'; $true }
        Stop-ParkosLiteAll -Ctx $ctx
        ($global:order -join ',') | Should Be 'front,api,db'
    }
}

Describe 'Update-ParkosLiteSource (git pull)' {
    It 'rechaza una rama invalida sin invocar git' {
        Mock Invoke-ParkosLiteGit { throw 'no deberia' }
        { Update-ParkosLiteSource -RepoRoot 'C:\r' -Branch 'dev; calc' } | Should Throw 'nombre de rama invalido'
    }
    It 'rechaza cambios locales en archivos versionados antes de hacer pull' {
        Mock Invoke-ParkosLiteGit { if ($Arguments[0] -eq 'status') { @{ ExitCode = 0; Output = @(' M backend/x.py') } } else { throw 'no deberia' } }
        { Update-ParkosLiteSource -RepoRoot 'C:\r' -Branch 'dev' } | Should Throw 'cambios locales'
    }
    It 'fetch, checkout (si hace falta) y pull --ff-only; devuelve HEAD viejo y nuevo' {
        $global:gitCalls = @()
        $global:headN = 0
        Mock Invoke-ParkosLiteGit {
            $global:gitCalls += ($Arguments -join ' ')
            $o = @()
            if ($Arguments[0] -eq 'rev-parse' -and $Arguments[1] -eq 'HEAD') { $global:headN++; $o = @("sha$($global:headN)") }
            if ($Arguments[0] -eq 'rev-parse' -and $Arguments[1] -eq '--abbrev-ref') { $o = @('feature/x') }
            @{ ExitCode = 0; Output = $o }
        }
        $r = Update-ParkosLiteSource -RepoRoot 'C:\r' -Branch 'dev'
        $r.OldHead | Should Be 'sha1'
        $r.NewHead | Should Be 'sha2'
        ($global:gitCalls -join '|') | Should Match 'fetch origin dev'
        ($global:gitCalls -join '|') | Should Match 'checkout dev'
        ($global:gitCalls -join '|') | Should Match 'pull --ff-only origin dev'
    }
    It 'un pull que no es fast-forward falla con mensaje accionable' {
        Mock Invoke-ParkosLiteGit {
            if ($Arguments[0] -eq 'pull') { @{ ExitCode = 128; Output = @('fatal') } }
            elseif ($Arguments[0] -eq 'status') { @{ ExitCode = 0; Output = @() } }
            elseif ($Arguments[0] -eq 'rev-parse' -and $Arguments[1] -eq '--abbrev-ref') { @{ ExitCode = 0; Output = @('dev') } }
            else { @{ ExitCode = 0; Output = @('sha') } }
        }
        { Update-ParkosLiteSource -RepoRoot 'C:\r' -Branch 'dev' } | Should Throw 'ff-only'
    }
    It 'Get-ParkosLiteChangedFiles usa git diff --name-only entre los dos HEAD' {
        $global:gitCalls = @()
        Mock Invoke-ParkosLiteGit { $global:gitCalls += ($Arguments -join ' '); @{ ExitCode = 0; Output = @('backend/a.py', 'apps/b.ts') } }
        $f = Get-ParkosLiteChangedFiles -RepoRoot 'C:\r' -From 'a1' -To 'b2'
        $f.Count | Should Be 2
        $global:gitCalls[0] | Should Be 'diff --name-only a1 b2'
    }
    It 'sin cambio de HEAD no consulta el diff' {
        Mock Invoke-ParkosLiteGit { throw 'no deberia' }
        (Get-ParkosLiteChangedFiles -RepoRoot 'C:\r' -From 'a1' -To 'a1').Count | Should Be 0
    }
}

Describe 'Invoke-ParkosLiteRefresh' {
    BeforeEach {
        $global:order = @()
        Mock Stop-ParkosLiteAll { $global:order += 'stop' }
        Mock Start-ParkosLiteAll { $global:order += 'start' }
        Mock Invoke-ParkosLiteStep { $global:order += "step:$Key" }
        Mock Test-Path { $true }
    }
    It 'solo front cambiado: stop, pull, migrate, seed, start (sin reconstruir ni pnpm)' {
        $ctx = New-TestCtx 'ref1'
        Mock Update-ParkosLiteSource { @{ OldHead = 'a'; NewHead = 'b' } }
        Mock Get-ParkosLiteChangedFiles { @('apps/electron-sucursal/src/x.tsx') }
        Invoke-ParkosLiteRefresh -Ctx $ctx
        ($global:order -join ',') | Should Be 'stop,step:migrate,step:seed,start'
    }
    It 'backend cambiado: reconstruye el exe antes de migrar' {
        $ctx = New-TestCtx 'ref2'
        Mock Update-ParkosLiteSource { @{ OldHead = 'a'; NewHead = 'b' } }
        Mock Get-ParkosLiteChangedFiles { @('backend/packages/x.py') }
        Invoke-ParkosLiteRefresh -Ctx $ctx
        ($global:order -join ',') | Should Be 'stop,step:api,step:migrate,step:seed,start'
    }
    It 'lockfile cambiado: reinstala el front' {
        $ctx = New-TestCtx 'ref3'
        Mock Update-ParkosLiteSource { @{ OldHead = 'a'; NewHead = 'b' } }
        Mock Get-ParkosLiteChangedFiles { @('apps/pnpm-lock.yaml') }
        Invoke-ParkosLiteRefresh -Ctx $ctx
        ($global:order -join ',') | Should Be 'stop,step:migrate,step:front,step:seed,start'
    }
    It 'si el pull falla, vuelve a arrancar lo que estaba y propaga el error' {
        $ctx = New-TestCtx 'ref4'
        Mock Update-ParkosLiteSource { throw 'ff-only fallo' }
        { Invoke-ParkosLiteRefresh -Ctx $ctx } | Should Throw 'ff-only'
        ($global:order -join ',') | Should Be 'stop,start'
    }
}

Describe 'Test-ParkosLiteApiBuildNeeded (decision de build)' {
    function New-ExePair($ctx, [datetime]$when) {
        foreach ($e in @($ctx.Paths.ApiExe, $ctx.Paths.MigrateExe)) {
            New-Item -ItemType Directory -Force -Path (Split-Path $e) | Out-Null
            Set-Content $e 'x'
            (Get-Item $e).LastWriteTimeUtc = $when
        }
    }
    It 'construye cuando faltan los exe (maquina limpia)' {
        $ctx = New-TestCtx 'bn1'
        Mock Get-ParkosLiteApiSourceNewestWrite { [datetime]'2026-01-01' }
        (Test-ParkosLiteApiBuildNeeded -Paths $ctx.Paths) | Should Be $true
    }
    It 'omite el build cuando los exe son mas nuevos que los fuentes' {
        $ctx = New-TestCtx 'bn2'
        New-ExePair $ctx ([datetime]'2026-02-01')
        Mock Get-ParkosLiteApiSourceNewestWrite { ([datetime]'2026-01-01').ToUniversalTime() }
        (Test-ParkosLiteApiBuildNeeded -Paths $ctx.Paths) | Should Be $false
    }
    It 'construye cuando algun fuente es mas nuevo que el exe' {
        $ctx = New-TestCtx 'bn3'
        New-ExePair $ctx ([datetime]'2026-01-01')
        Mock Get-ParkosLiteApiSourceNewestWrite { ([datetime]'2026-02-01').ToUniversalTime() }
        (Test-ParkosLiteApiBuildNeeded -Paths $ctx.Paths) | Should Be $true
    }
    It 'construye si no se pueden leer los fuentes (git falla)' {
        $ctx = New-TestCtx 'bn4'
        New-ExePair $ctx ([datetime]'2026-02-01')
        Mock Get-ParkosLiteApiSourceNewestWrite { $null }
        (Test-ParkosLiteApiBuildNeeded -Paths $ctx.Paths) | Should Be $true
    }
}

Describe 'Invoke-ParkosLiteStep api' {
    It 'no llama al build si esta al dia' {
        $ctx = New-TestCtx 'st1'
        Mock Test-ParkosLiteApiBuildNeeded { $false }
        Mock Invoke-ParkosLiteBuildScript { 0 }
        Invoke-ParkosLiteStep -Ctx $ctx -Key 'api'
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 0
    }
    It 'detiene la API propia antes de construir y falla si el build falla' {
        $ctx = New-TestCtx 'st2'
        Mock Test-ParkosLiteApiBuildNeeded { $true }
        Mock Stop-ParkosLiteService { $true }
        Mock Invoke-ParkosLiteBuildScript { 1 }
        { Invoke-ParkosLiteStep -Ctx $ctx -Key 'api' } | Should Throw 'build-release.ps1 fallo'
        Assert-MockCalled Stop-ParkosLiteService -Times 1
    }
}

Describe 'Invoke-ParkosLiteMenu (menu unico numerado)' {
    . (Join-Path $PSScriptRoot '..\lite\parkos-lite.ps1')
    $pending = @{ env = 'pending'; db = 'pending'; api = 'pending'; migrate = 'pending'; seed = 'pending'; front = 'pending' }
    function Start-MenuRun {
        param([string[]]$Inputs)
        $global:menuInputs = New-Object System.Collections.Queue
        foreach ($i in $Inputs) { $global:menuInputs.Enqueue($i) }
        $global:menuOut = @()
        $global:menuCalls = @()
        Invoke-ParkosLiteMenu -Ctx @{ State = @{ api_port = 8100; front_port = 5173 }; Logger = $script:quiet }
    }
    Mock Get-ParkosLiteCurrentStatus { $pending }
    Mock Read-Host { $global:menuInputs.Dequeue() }
    Mock Write-Host { $global:menuOut += [string]$Object }
    Mock Invoke-ParkosLiteInstallAll { $global:menuCalls += 'installall'; $true }
    Mock Invoke-ParkosLiteStart { $global:menuCalls += 'start'; $true }
    Mock Stop-ParkosLiteAll { $global:menuCalls += 'stop' }
    Mock Show-ParkosLiteStatus { $global:menuCalls += 'status' }
    Mock Show-ParkosLiteLogs { $global:menuCalls += 'logs' }
    Mock Invoke-ParkosLiteRefresh { $global:menuCalls += 'refresh' }
    Mock Invoke-ParkosLiteAutostartMenu { $global:menuCalls += 'autostart' }
    Mock Start-Process { $global:menuCalls += 'browser' }
    Mock Invoke-ParkosLiteTuiStep { $global:menuCalls += "step:$Key"; $true }

    It 'muestra el menu con Instalar todo como 1) y sale con 0' {
        Start-MenuRun -Inputs @('0')
        $global:menuOut -join "`n" | Should Match '1\) Instalar todo \(guiado\)'
        ($global:menuOut | Where-Object { $_ -match '0\) Salir' }).Count | Should Be 1
        $global:menuCalls.Count | Should Be 0
    }
    It 'cada numero despacha su accion' {
        Start-MenuRun -Inputs @('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '0')
        ($global:menuCalls -join ',') | Should Be 'installall,start,stop,stop,start,status,browser,refresh,logs,autostart,step:env,step:db,step:api,step:migrate,step:seed,step:front'
    }
    It 'Q/q sale (alias oculto)' {
        Start-MenuRun -Inputs @('q')
        $global:menuCalls.Count | Should Be 0
    }
    It 'entrada invalida muestra el mensaje claro y vuelve a mostrar el menu' {
        Start-MenuRun -Inputs @('G', '99', '0')
        ($global:menuOut | Where-Object { $_ -eq 'Opcion no valida, elige un numero de la lista' }).Count | Should Be 2
        ($global:menuOut | Where-Object { $_ -match '1\) Instalar todo' }).Count | Should Be 3
        $global:menuCalls.Count | Should Be 0
    }
}

# ---------------------------------------------------------------------------
# Paso 12 parts-first: restaurar api-sucursal/migrate del repo o construir
# ---------------------------------------------------------------------------

function New-ApiPartsFixture {
    # Empaqueta de verdad api-sucursal y migrate (carpetas minimas) y un 'doctor'
    # que el lite jamas debe restaurar. Devuelve el directorio de partes.
    param([string]$Root)
    $parts = Join-Path $Root 'parts'
    foreach ($id in 'api-sucursal', 'migrate', 'doctor') {
        $src = Join-Path $Root "src\$id\$id"
        New-Item -ItemType Directory -Force -Path $src | Out-Null
        Set-Content (Join-Path $src "$id.exe") "exe-$id"
        [void](Pack-ParkosPayloadArtifact -Source (Join-Path $Root "src\$id") -Id $id -PartsDir $parts -Target "services\$id" -SourceDependent -Logger { param($m) })
    }
    return $parts
}

function New-FakeApiEntry {
    param([string]$Id, [string]$Commit = 'abcdef1234567890')
    return [PSCustomObject]@{ id = $Id; parts = @(@{ name = "$Id.zip" }); sourceDependent = $true; builtFromCommit = $Commit }
}

Describe 'Get-ParkosLiteApiSourcePlan' {
    BeforeEach {
        $script:ctx = New-TestCtx 'pl'
        New-Item -ItemType Directory -Force -Path $script:ctx.Paths.PartsDir | Out-Null
        Mock Find-ParkosPayloadEntry { New-FakeApiEntry -Id $Id }
        Mock Get-ParkosLiteChangedSinceCommit { , @() }
    }
    It 'sin cambios en backend/ ni installer/bootstrap/ desde el commit de las partes: restore (con el commit)' {
        $p = Get-ParkosLiteApiSourcePlan -Paths $script:ctx.Paths
        $p.Action | Should Be 'restore'
        $p.Commit | Should Be 'abcdef1234567890'
        Assert-MockCalled Get-ParkosLiteChangedSinceCommit -ParameterFilter { $Commit -eq 'abcdef1234567890' } -Times 2 -Scope It
    }
    It 'pregunta solo por api-sucursal y migrate (nunca seed, doctor, job-sync, msi)' {
        Get-ParkosLiteApiSourcePlan -Paths $script:ctx.Paths | Out-Null
        Assert-MockCalled Find-ParkosPayloadEntry -ParameterFilter { $Id -eq 'api-sucursal' -or $Id -eq 'migrate' } -Times 2 -Scope It
        Assert-MockCalled Find-ParkosPayloadEntry -ParameterFilter { $Id -ne 'api-sucursal' -and $Id -ne 'migrate' } -Times 0 -Scope It
    }
    It 'si backend/ cambio desde el commit: build y lo explica' {
        Mock Get-ParkosLiteChangedSinceCommit { , @('backend/packages/parkos_core/x.py') }
        $p = Get-ParkosLiteApiSourcePlan -Paths $script:ctx.Paths
        $p.Action | Should Be 'build'
        $p.Reason | Should Match 'backend/'
        $p.Reason | Should Match 'abcdef1'
    }
    It 'si git no puede saberlo ($null): build' {
        Mock Get-ParkosLiteChangedSinceCommit { $null }
        $p = Get-ParkosLiteApiSourcePlan -Paths $script:ctx.Paths
        $p.Action | Should Be 'build'
        $p.Reason | Should Match 'git'
    }
    It 'si falta la entrada del manifest (api o migrate): build' {
        Mock Find-ParkosPayloadEntry { if ($Id -eq 'migrate') { $null } else { New-FakeApiEntry -Id $Id } }
        $p = Get-ParkosLiteApiSourcePlan -Paths $script:ctx.Paths
        $p.Action | Should Be 'build'
        $p.Reason | Should Match 'migrate'
    }
    It 'si el repo no tiene carpeta de partes: build sin error' {
        $ctx2 = New-TestCtx 'pl2'
        $p = Get-ParkosLiteApiSourcePlan -Paths $ctx2.Paths
        $p.Action | Should Be 'build'
    }
}

Describe 'Restore-ParkosLiteApiFromParts (real, con partes de prueba)' {
    It 'restaura api-sucursal y migrate a payload\services y NO restaura doctor' {
        $ctx = New-TestCtx 'rf'
        $root = Join-Path $TestDrive 'rf-fixture'
        $ctx.Paths.PartsDir = New-ApiPartsFixture -Root $root
        Restore-ParkosLiteApiFromParts -Paths $ctx.Paths -Logger $script:quiet
        (Test-Path (Join-Path $ctx.Paths.PayloadRoot 'services\api-sucursal\api-sucursal\api-sucursal.exe')) | Should Be $true
        (Test-Path (Join-Path $ctx.Paths.PayloadRoot 'services\migrate\migrate\migrate.exe')) | Should Be $true
        (Test-Path (Join-Path $ctx.Paths.PayloadRoot 'services\doctor')) | Should Be $false
        (Test-Path $ctx.Paths.ApiExe) | Should Be $true
        (Test-Path $ctx.Paths.MigrateExe) | Should Be $true
    }
    It 'es idempotente: la segunda vez no vuelve a expandir (marcador al dia)' {
        $ctx = New-TestCtx 'rf2'
        $ctx.Paths.PartsDir = New-ApiPartsFixture -Root (Join-Path $TestDrive 'rf2-fixture')
        Restore-ParkosLiteApiFromParts -Paths $ctx.Paths -Logger $script:quiet
        $script:msgs = @()
        Restore-ParkosLiteApiFromParts -Paths $ctx.Paths -Logger { param($m) $script:msgs += $m }
        ($script:msgs -join ' ') | Should Match 'ya restaurado y al dia'
    }
}

Describe 'Invoke-ParkosLiteStep api (parts-first)' {
    BeforeEach {
        $script:ctx = New-TestCtx 'ps'
        $script:logs = @()
        $script:ctx.Logger = { param($m) $script:logs += $m }
        Mock Stop-ParkosLiteService { $true }
        Mock Invoke-ParkosLiteBuildScript { 0 }
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 0; Output = @('headhead') } }
        Mock Test-ParkosLiteApiBuildNeeded { $false }
    }
    It 'restore: restaura, NO compila (ni mira el mtime), loguea el commit y guarda api_built_commit' {
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'restore'; Commit = 'abcdef1234567890'; Reason = '' } }
        Mock Restore-ParkosLiteApiFromParts {
            foreach ($e in @($script:ctx.Paths.ApiExe, $script:ctx.Paths.MigrateExe)) { New-Item -ItemType Directory -Force -Path (Split-Path $e) | Out-Null; Set-Content $e 'x' }
        }
        Invoke-ParkosLiteStep -Ctx $script:ctx -Key 'api'
        Assert-MockCalled Restore-ParkosLiteApiFromParts -Times 1 -Scope It
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 0 -Scope It
        Assert-MockCalled Test-ParkosLiteApiBuildNeeded -Times 0 -Scope It
        Assert-MockCalled Stop-ParkosLiteService -Times 1 -Scope It
        ($script:logs -join "`n") | Should Match 'API restaurada desde el repositorio \(commit abcdef1\)'
        $script:ctx.State.api_built_commit | Should Be 'abcdef1234567890'
    }
    It 'restore que falla (partes danadas): avisa y cae al build como antes' {
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'restore'; Commit = 'abcdef1234567890'; Reason = '' } }
        Mock Restore-ParkosLiteApiFromParts { throw 'la parte 01 esta danada' }
        Mock Test-ParkosLiteApiBuildNeeded { $true }
        Mock Invoke-ParkosLiteBuildScript { foreach ($e in @($script:ctx.Paths.ApiExe, $script:ctx.Paths.MigrateExe)) { New-Item -ItemType Directory -Force -Path (Split-Path $e) | Out-Null; Set-Content $e 'x' }; 0 }
        Invoke-ParkosLiteStep -Ctx $script:ctx -Key 'api'
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 1 -Scope It
        ($script:logs -join "`n") | Should Match 'no sirven'
    }
    It 'build por codigo cambiado: lo dice y avisa que necesita uv/Python e Internet' {
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'build'; Commit = ''; Reason = 'backend/ o installer/bootstrap/ cambio desde el commit abcdef1 de las partes (3 archivos)' } }
        Mock Restore-ParkosLiteApiFromParts { throw 'no deberia restaurar' }
        Mock Test-ParkosLiteApiBuildNeeded { $true }
        # El build "fabrica" los exe
        Mock Invoke-ParkosLiteBuildScript { foreach ($e in @($script:ctx.Paths.ApiExe, $script:ctx.Paths.MigrateExe)) { New-Item -ItemType Directory -Force -Path (Split-Path $e) | Out-Null; Set-Content $e 'x' }; 0 }
        Invoke-ParkosLiteStep -Ctx $script:ctx -Key 'api'
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 1 -Scope It
        Assert-MockCalled Restore-ParkosLiteApiFromParts -Times 0 -Scope It
        ($script:logs -join "`n") | Should Match 'cambio desde el commit abcdef1'
        ($script:logs -join "`n") | Should Match 'uv/Python e Internet'
    }
    It 'build forzado si la carpeta es la restaurada del repo (marcador) aunque el mtime diga que esta al dia' {
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'build'; Commit = ''; Reason = 'backend/ cambio' } }
        Mock Test-ParkosLiteApiBuildNeeded { $false }
        $markers = @(Get-ParkosLiteApiRestoreMarkers -Paths $script:ctx.Paths)
        foreach ($m in $markers) { New-Item -ItemType Directory -Force -Path (Split-Path $m) | Out-Null; Set-Content $m 'sha' }
        Mock Invoke-ParkosLiteBuildScript { foreach ($e in @($script:ctx.Paths.ApiExe, $script:ctx.Paths.MigrateExe)) { New-Item -ItemType Directory -Force -Path (Split-Path $e) | Out-Null; Set-Content $e 'x' }; 0 }
        Invoke-ParkosLiteStep -Ctx $script:ctx -Key 'api'
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 1 -Scope It
        foreach ($m in $markers) { (Test-Path $m) | Should Be $false }
    }
    It 'sin partes y con exe al dia (construidos aqui): omite el build como siempre' {
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'build'; Commit = ''; Reason = 'sin partes' } }
        Mock Test-ParkosLiteApiBuildNeeded { $false }
        Invoke-ParkosLiteStep -Ctx $script:ctx -Key 'api'
        Assert-MockCalled Invoke-ParkosLiteBuildScript -Times 0 -Scope It
        ($script:logs -join "`n") | Should Match 'ya esta construida'
    }
}

Describe 'Invoke-ParkosLiteStep env pasa las partes del repo a las herramientas' {
    It 'Install-ParkosLiteToolchain recibe PartsDir del repo' {
        $ctx = New-TestCtx 'pe'
        $ctx.Requested = @{ Db = 0; Api = 0; Front = 0 }
        Mock Install-ParkosLiteToolchain { }
        Mock Initialize-ParkosLiteConfig { }
        Invoke-ParkosLiteStep -Ctx $ctx -Key 'env'
        Assert-MockCalled Install-ParkosLiteToolchain -ParameterFilter { $PartsDir -eq $ctx.Paths.PartsDir } -Times 1 -Scope It
    }
}

Describe 'Get-ParkosLiteChangedSinceCommit' {
    It 'con archivos cambiados los devuelve' {
        Mock Get-ParkosPartsChangedFiles { @('backend/a.py', 'backend/b.py') }
        $r = Get-ParkosLiteChangedSinceCommit -RepoRoot 'C:' -Commit 'abc'
        @($r).Count | Should Be 2
    }
    It 'sin cambios y commit conocido: arreglo vacio (NO $null)' {
        Mock Get-ParkosPartsChangedFiles { @() }
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 0; Output = @('abc') } }
        $r = Get-ParkosLiteChangedSinceCommit -RepoRoot 'C:' -Commit 'abc'
        ($null -eq $r) | Should Be $false
        @($r).Count | Should Be 0
    }
    It 'commit desconocido para git (clon superficial): $null' {
        Mock Get-ParkosPartsChangedFiles { $null }
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 1; Output = @('fatal') } }
        ($null -eq (Get-ParkosLiteChangedSinceCommit -RepoRoot 'C:' -Commit 'abc')) | Should Be $true
    }
    It 'sin commit en el manifest: $null' {
        ($null -eq (Get-ParkosLiteChangedSinceCommit -RepoRoot 'C:' -Commit '')) | Should Be $true
    }
    It 'git no instalado (el comando lanza): $null' {
        Mock Get-ParkosPartsChangedFiles { $null }
        Mock Invoke-ParkosLiteGit { throw 'git: no se reconoce' }
        ($null -eq (Get-ParkosLiteChangedSinceCommit -RepoRoot 'C:' -Commit 'abc')) | Should Be $true
    }
}
