# Tests de installer/lite/ParkosLite.Run.ps1: configuracion inicial (uuid,
# puertos, secretos, env file), arranque/parada de API (exe) y front (Vite),
# 'Iniciar todo', 'Detener todo' y el refresh desde dev. Procesos, git, red y
# builds pasan por wrappers que se mockean aqui; nada real se ejecuta.

. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Core.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')
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
