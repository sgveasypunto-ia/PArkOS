# Tests de installer/lite/ParkosLite.Core.ps1: rutas, puertos, secretos, env
# file, estado, gating/menu y decisiones del refresh. Pester 3.4 (Mock sin
# -ModuleName; Should Throw con substring; sin Should Not Throw). Todo acceso
# al sistema (puertos, git, procesos) pasa por wrappers que se mockean aqui.

. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Core.ps1')

$script:uuid = '11111111-2222-4333-8444-555555555555'

Describe 'Get-ParkosLitePaths' {
    It 'cuelga todo de LitePath y deja el repo intacto' {
        $p = Get-ParkosLitePaths -LitePath 'C:\lite' -RepoRoot 'C:\repo'
        $p.Downloads | Should Be 'C:\lite\downloads'
        $p.PgRoot | Should Be 'C:\lite\pgsql'
        $p.PgData | Should Be 'C:\lite\data\pg'
        $p.Logs | Should Be 'C:\lite\logs'
        $p.EnvFile | Should Be 'C:\lite\data\api.env'
        $p.State | Should Be 'C:\lite\state.json'
        $p.Secrets | Should Be 'C:\lite\data\secrets.json'
        $p.JwtKey | Should Be 'C:\lite\data\jwt-signing.key'
        $p.ApiExe | Should Be 'C:\repo\installer\payload\services\api-sucursal\api-sucursal\api-sucursal.exe'
        $p.MigrateDir | Should Be 'C:\repo\installer\payload\services\migrate\migrate'
        $p.FrontDir | Should Be 'C:\repo\apps\electron-sucursal'
        $p.SeedSql | Should Be 'C:\repo\installer\lite\seed_demo.sql'
    }
    It 'Postgres y el resto de artefactos se leen de installer\payload\parts (donde viven versionados)' {
        $p = Get-ParkosLitePaths -LitePath 'C:\lite' -RepoRoot 'C:\repo'
        $p.PartsDir | Should Be 'C:\repo\installer\payload\parts'
        $p.PayloadRoot | Should Be 'C:\repo\installer\payload'
        $p.PgPayload | Should Be 'C:\repo\installer\payload\parts\postgres'
    }
    It 'las partes de Postgres del repo real se encuentran con PgPayload (sin problemas)' {
        . (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
        $repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
        $p = Get-ParkosLitePaths -LitePath 'C:\lite' -RepoRoot $repo
        $info = Get-ParkosPostgresDownloadInfo
        $st = Get-ParkosPostgresPartsStatus -Dir $p.PgPayload -FileName $info.FileName
        $st.Problem | Should BeNullOrEmpty
        (@($st.Parts).Count -ge 1) | Should Be $true
    }
}

Describe 'Find-ParkosLiteFreePort / Resolve-ParkosLitePort' {
    It 'salta los puertos ocupados' {
        $busy = @(5433, 5434)
        $r = Find-ParkosLiteFreePort -Start 5433 -IsInUse { param($p) $busy -contains $p }
        $r | Should Be 5435
    }
    It 'respeta Exclude' {
        $r = Find-ParkosLiteFreePort -Start 8100 -Exclude @(8100) -IsInUse { param($p) $false }
        $r | Should Be 8101
    }
    It 'falla si no hay ninguno libre en el rango' {
        { Find-ParkosLiteFreePort -Start 9000 -MaxTries 3 -IsInUse { param($p) $true } } | Should Throw 'puerto libre'
    }
    It 'un puerto pedido explicitamente se respeta si esta libre' {
        (Resolve-ParkosLitePort -Requested 5440 -Persisted 5433 -Start 5433 -IsInUse { param($p) $false }) | Should Be 5440
    }
    It 'un puerto pedido que esta ocupado por otro proceso falla' {
        { Resolve-ParkosLitePort -Requested 5440 -Persisted 0 -Start 5433 -IsInUse { param($p) $true } -Name 'Postgres' } | Should Throw 'Postgres'
    }
    It 'reusa el puerto persistido si esta libre' {
        (Resolve-ParkosLitePort -Requested 0 -Persisted 5436 -Start 5433 -IsInUse { param($p) $false }) | Should Be 5436
    }
    It 'reusa el persistido aunque este ocupado cuando es el propio servicio (-OwnedByLite)' {
        (Resolve-ParkosLitePort -Requested 0 -Persisted 5436 -Start 5433 -OwnedByLite -IsInUse { param($p) $true }) | Should Be 5436
    }
    It 'sin persistido elige el primero libre desde Start' {
        $busy = @(5433)
        (Resolve-ParkosLitePort -Requested 0 -Persisted 0 -Start 5433 -IsInUse { param($p) $busy -contains $p }) | Should Be 5434
    }
    It 'si el persistido se ocupo por un tercero elige otro' {
        $busy = @(5436)
        (Resolve-ParkosLitePort -Requested 0 -Persisted 5436 -Start 5433 -IsInUse { param($p) $busy -contains $p }) | Should Be 5433
    }
}

Describe 'Secretos y env file' {
    It 'New-ParkosLiteSecrets genera passwords distintas y largas' {
        $s = New-ParkosLiteSecrets
        $s.PostgresPassword.Length | Should BeGreaterThan 19
        $s.SuperuserPassword.Length | Should BeGreaterThan 19
        $s.AppPassword.Length | Should BeGreaterThan 19
        $s.AppPassword | Should Not Be $s.SuperuserPassword
        $s.AppPassword | Should Match '^[A-Za-z0-9]+$'
    }
    It 'Get-ParkosLiteEnvLines trae todas las variables que exige load_config' {
        $lines = Get-ParkosLiteEnvLines -SucursalUuid $script:uuid -AppPassword 'pw' -DbPort 5434 -ApiPort 8101 -JwtKeyPath 'C:\l\jwt.key' -SyncJwtPath 'C:\l\sync.jwt'
        $map = @{}
        foreach ($l in $lines) { $k, $v = $l -split '=', 2; $map[$k] = $v }
        $map['PARKOS_DEPLOY'] | Should Be 'branch'
        $map['PARKOS_SYNC_ENGINE'] | Should Be 'catalog_branch'
        $map['PARKOS_SUCURSAL_UUID'] | Should Be $script:uuid
        $map['PARKOS_DB_URL'] | Should Be 'postgresql+psycopg://parkos_app:pw@127.0.0.1:5434/parkos'
        $map['DATABASE_URL'] | Should Be 'postgresql+asyncpg://parkos_app:pw@127.0.0.1:5434/parkos'
        $map['PARKOS_CLOUD_API_URL'] | Should Be 'http://127.0.0.1:1'
        $map['PARKOS_JWT_KEY_PATH'] | Should Be 'C:\l\jwt.key'
        $map['PARKOS_SYNC_JWT_PATH'] | Should Be 'C:\l\sync.jwt'
        $map['PORT'] | Should Be '8101'
    }
    It 'Read-ParkosLiteEnvFile devuelve el hashtable y respeta valores con =' {
        $f = Join-Path $TestDrive 'api.env'
        Set-Content $f @('A=1', '# comentario', '', 'B=x=y')
        $m = Read-ParkosLiteEnvFile -Path $f
        $m['A'] | Should Be '1'
        $m['B'] | Should Be 'x=y'
        $m.ContainsKey('#') | Should Be $false
    }
    It 'Write-ParkosLiteEnvFile crea el directorio y es re-escribible' {
        $f = Join-Path $TestDrive 'sub\api.env'
        Write-ParkosLiteEnvFile -Path $f -Lines @('A=1')
        Write-ParkosLiteEnvFile -Path $f -Lines @('A=2')
        (Read-ParkosLiteEnvFile -Path $f)['A'] | Should Be '2'
    }
    It 'Test-ParkosUuidV4 valida la forma' {
        (Test-ParkosUuidV4 -Value $script:uuid) | Should Be $true
        (Test-ParkosUuidV4 -Value '11111111-2222-1333-8444-555555555555') | Should Be $false
        (Test-ParkosUuidV4 -Value 'nope') | Should Be $false
    }
}

Describe 'Estado persistente' {
    It 'devuelve un estado vacio por defecto si no existe el archivo' {
        $s = Read-ParkosLiteState -Path (Join-Path $TestDrive 'nope.json')
        $s.steps.Count | Should Be 0
        $s.sucursal_uuid | Should Be ''
    }
    It 'guarda y relee (roundtrip) incluyendo pasos y puertos' {
        $f = Join-Path $TestDrive 'st\state.json'
        $s = Read-ParkosLiteState -Path $f
        $s.sucursal_uuid = $script:uuid
        $s.db_port = 5434
        Set-ParkosLiteStepState -State $s -Key 'db' -Value 'ok'
        Save-ParkosLiteState -State $s -Path $f
        $r = Read-ParkosLiteState -Path $f
        $r.sucursal_uuid | Should Be $script:uuid
        $r.db_port | Should Be 5434
        $r.steps['db'] | Should Be 'ok'
    }
    It 'un JSON corrupto no rompe: vuelve al estado vacio' {
        $f = Join-Path $TestDrive 'bad.json'
        Set-Content $f '{ no es json'
        (Read-ParkosLiteState -Path $f).steps.Count | Should Be 0
    }
}

Describe 'Pasos, gating y menu' {
    It 'define los 6 pasos de instalacion en orden' {
        $steps = Get-ParkosLiteSteps
        (($steps | ForEach-Object { $_.Key }) -join ',') | Should Be 'env,db,api,migrate,seed,front'
        $steps[0].Number | Should Be '10'
        $steps[5].Number | Should Be '15'
    }
    It 'sin nada hecho, solo el paso 1 esta libre' {
        $st = @{ env = 'pending'; db = 'pending'; api = 'pending'; migrate = 'pending'; seed = 'pending'; front = 'pending' }
        (Get-ParkosLiteBlockReason -Key 'env' -Status $st) | Should Be $null
        (Get-ParkosLiteBlockReason -Key 'db' -Status $st) | Should Match 'Preparar entorno'
        (Get-ParkosLiteBlockReason -Key 'migrate' -Status $st) | Should Match 'Instalar base de datos'
    }
    It 'migrar exige db y api; seed exige migrate; iniciar exige seed, api y front' {
        $st = @{ env = 'ok'; db = 'ok'; api = 'pending'; migrate = 'pending'; seed = 'pending'; front = 'pending' }
        (Get-ParkosLiteBlockReason -Key 'migrate' -Status $st) | Should Match 'Construir API'
        $st.api = 'ok'
        (Get-ParkosLiteBlockReason -Key 'migrate' -Status $st) | Should Be $null
        (Get-ParkosLiteBlockReason -Key 'seed' -Status $st) | Should Match 'Migrar'
        (Get-ParkosLiteBlockReason -Key 'start' -Status $st) | Should Match 'Cargar datos'
        $st.migrate = 'ok'; $st.seed = 'ok'
        (Get-ParkosLiteBlockReason -Key 'start' -Status $st) | Should Match 'dependencias del front'
        $st.front = 'ok'
        (Get-ParkosLiteBlockReason -Key 'start' -Status $st) | Should Be $null
    }
    It 'Get-ParkosLiteMenuLines marca OK/FAIL/BLOQ/pendiente en los pasos avanzados' {
        $st = @{ env = 'ok'; db = 'fail'; api = 'pending'; migrate = 'pending'; seed = 'pending'; front = 'pending' }
        $lines = @(Get-ParkosLiteMenuLines -Status $st | Where-Object { $_.Kind -eq 'item' })
        $env = $lines | Where-Object { $_.Number -eq 10 }
        $db = $lines | Where-Object { $_.Number -eq 11 }
        $api = $lines | Where-Object { $_.Number -eq 12 }
        $mig = $lines | Where-Object { $_.Number -eq 13 }
        $env.Text | Should Match '\[ OK \] 10\) Preparar entorno'
        $db.Text | Should Match '\[FAIL\] 11\)'
        $api.Text | Should Match '\[\.\.\.\.\] 12\)'
        $mig.Text | Should Match '\[BLOQ\] 13\).*corre primero: 11\)'
        $env.Color | Should Be 'Green'
        $db.Color | Should Be 'Red'
    }
}

Describe 'Menu unico secuencial' {
    $allPending = @{ env = 'pending'; db = 'pending'; api = 'pending'; migrate = 'pending'; seed = 'pending'; front = 'pending' }
    It 'la numeracion es estrictamente secuencial 1..15 y sin repetidos' {
        $items = @(Get-ParkosLiteMenuItems)
        $items.Count | Should Be 15
        (($items | ForEach-Object { $_.Number }) -join ',') | Should Be '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15'
    }
    It 'Instalar todo es la opcion 1' {
        $items = @(Get-ParkosLiteMenuItems)
        $items[0].Action | Should Be 'installall'
        $items[0].Name | Should Match 'Instalar todo'
    }
    It 'los pasos avanzados conservan sus keys y van en el orden de instalacion (10..15)' {
        $adv = @(Get-ParkosLiteMenuItems | Where-Object { $_.Group -eq 'AVANZADO' })
        (($adv | ForEach-Object { $_.Action }) -join ',') | Should Be 'env,db,api,migrate,seed,front'
        $adv[0].Number | Should Be 10
    }
    It 'el orden de las lineas: PRIMERA VEZ, USO DIARIO, AVANZADO y 0) Salir al final' {
        $lines = @(Get-ParkosLiteMenuLines -Status $allPending)
        $headers = @($lines | Where-Object { $_.Kind -eq 'header' } | ForEach-Object { $_.Text.Trim() })
        ($headers -join '|') | Should Match '^PRIMERA VEZ\|USO DIARIO\|AVANZADO'
        $lines[0].Text.Trim() | Should Be 'PRIMERA VEZ'
        $lines[1].Text | Should Match '1\) Instalar todo \(guiado\)'
        $lines[1].Text | Should Match 'recomendado'
        $lines[$lines.Count - 1].Text | Should Match '0\) Salir'
    }
    It 'Iniciar todo es la 2 y muestra BLOQ con el motivo cuando falta algo' {
        $lines = @(Get-ParkosLiteMenuLines -Status $allPending)
        $start = $lines | Where-Object { $_.Kind -eq 'item' -and $_.Text -match '2\) Iniciar todo' }
        $start.Text | Should Match '\[BLOQ\]'
        $start.Text | Should Match 'corre primero'
        $ok = @{ env = 'ok'; db = 'ok'; api = 'ok'; migrate = 'ok'; seed = 'ok'; front = 'ok' }
        $start2 = Get-ParkosLiteMenuLines -Status $ok | Where-Object { $_.Kind -eq 'item' -and $_.Text -match '2\) Iniciar todo' }
        $start2.Text | Should Match '\[\.\.\.\.\]'
    }
    It 'los numeros visibles aparecen en orden estrictamente creciente' {
        $nums = @(Get-ParkosLiteMenuLines -Status $allPending | Where-Object { $_.Kind -ne 'header' } | ForEach-Object { if ($_.Text -match '(\d+)\) ') { [int]$Matches[1] } })
        $nums.Count | Should Be 16
        (($nums | Select-Object -First 15) -join ',') | Should Be '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15'
        $nums[15] | Should Be 0
    }
    It 'no queda ningun comando de letra en el menu visible' {
        $text = (Get-ParkosLiteMenuLines -Status $allPending | ForEach-Object { $_.Text }) -join "`n"
        $text | Should Not Match '(?m)(^|\s)[A-Za-z]\) '
        $text | Should Not Match '\bQ\)'
    }
    It 'Resolve-ParkosLiteMenuChoice mapea cada numero a su accion' {
        $map = @{ '1' = 'installall'; '2' = 'start'; '3' = 'stop'; '4' = 'restart'; '5' = 'status'; '6' = 'browser'; '7' = 'refresh'; '8' = 'logs'; '9' = 'autostart'
            '10' = 'env'; '11' = 'db'; '12' = 'api'; '13' = 'migrate'; '14' = 'seed'; '15' = 'front'; '0' = 'exit' }
        foreach ($k in $map.Keys) { (Resolve-ParkosLiteMenuChoice -Choice $k) | Should Be $map[$k] }
    }
    It 'Resolve-ParkosLiteMenuChoice acepta espacios y Q/q como Salir' {
        (Resolve-ParkosLiteMenuChoice -Choice ' 3 ') | Should Be 'stop'
        (Resolve-ParkosLiteMenuChoice -Choice 'q') | Should Be 'exit'
        (Resolve-ParkosLiteMenuChoice -Choice 'Q') | Should Be 'exit'
    }
    It 'Resolve-ParkosLiteMenuChoice devuelve null con entradas invalidas' {
        foreach ($bad in @('', '   ', 'G', 'b', '16', '-1', '99', 'abc', '1 2', '01')) {
            (Resolve-ParkosLiteMenuChoice -Choice $bad) | Should Be $null
        }
        (Resolve-ParkosLiteMenuChoice -Choice $null) | Should Be $null
    }
    It 'un state.json de la version anterior (sin cambios de formato) se carga sin error' {
        $f = Join-Path $TestDrive 'old\state.json'
        New-Item -ItemType Directory -Force -Path (Split-Path $f) | Out-Null
        Set-Content $f '{"sucursal_uuid":"11111111-2222-4333-8444-555555555555","db_port":5433,"api_port":8100,"front_port":5173,"source_branch":"dev","api_built_commit":"abc","steps":{"env":"ok","db":"ok","api":"fail"}}'
        $s = Read-ParkosLiteState -Path $f
        $s.db_port | Should Be 5433
        $s.steps['env'] | Should Be 'ok'
        $s.steps['api'] | Should Be 'fail'
    }
}

Describe 'Get-ParkosLiteStepStatus (probe, no solo el archivo de estado)' {
    $okFacts = @{ ToolsMissing = @(); PgInstalled = $true; PgInitialized = $true; ApiBuilt = $true; MigrateBuilt = $true; DbReady = $true; SchemaMigrated = $true; Seeded = $true; FrontInstalled = $true }
    It 'todo presente y estado ok => ok' {
        $st = @{ steps = @{ env = 'ok'; db = 'ok'; api = 'ok'; migrate = 'ok'; seed = 'ok'; front = 'ok' } }
        $r = Get-ParkosLiteStepStatus -State $st -Facts $okFacts
        ($r.Values | Where-Object { $_ -ne 'ok' }).Count | Should Be 0
    }
    It 'el estado dice ok pero falta el exe => api pending (se verifica probando)' {
        $f = $okFacts.Clone(); $f.ApiBuilt = $false
        $st = @{ steps = @{ env = 'ok'; db = 'ok'; api = 'ok'; migrate = 'ok'; seed = 'ok'; front = 'ok' } }
        (Get-ParkosLiteStepStatus -State $st -Facts $f).api | Should Be 'pending'
    }
    It 'el archivo de estado dice fail y el probe no lo contradice => fail' {
        $f = $okFacts.Clone(); $f.PgInitialized = $false
        $st = @{ steps = @{ db = 'fail' } }
        (Get-ParkosLiteStepStatus -State $st -Facts $f).db | Should Be 'fail'
    }
    It 'sin estado pero con todo instalado el probe reconoce db=ok' {
        $st = @{ steps = @{ } }
        (Get-ParkosLiteStepStatus -State $st -Facts $okFacts).db | Should Be 'ok'
    }
    It 'con la DB apagada, migrate/seed se confian al estado guardado' {
        $f = $okFacts.Clone(); $f.DbReady = $false; $f.SchemaMigrated = $false; $f.Seeded = $false
        $st = @{ steps = @{ migrate = 'ok'; seed = 'ok' } }
        $r = Get-ParkosLiteStepStatus -State $st -Facts $f
        $r.migrate | Should Be 'ok'
        $r.seed | Should Be 'ok'
    }
    It 'con la DB encendida y sin esquema, migrate=pending aunque el estado diga ok' {
        $f = $okFacts.Clone(); $f.SchemaMigrated = $false; $f.Seeded = $false
        $st = @{ steps = @{ migrate = 'ok'; seed = 'ok' } }
        $r = Get-ParkosLiteStepStatus -State $st -Facts $f
        $r.migrate | Should Be 'pending'
        $r.seed | Should Be 'pending'
    }
    It 'faltan herramientas => env pending' {
        $f = $okFacts.Clone(); $f.ToolsMissing = @('uv')
        (Get-ParkosLiteStepStatus -State @{ steps = @{} } -Facts $f).env | Should Be 'pending'
    }
}

Describe 'env requiere configuracion generada' {
    It 'herramientas ok pero sin config (uuid/env file) => env pending' {
        $f = @{ ToolsMissing = @(); ConfigReady = $false; PgInstalled = $false; PgInitialized = $false; ApiBuilt = $false; MigrateBuilt = $false; DbReady = $false; SchemaMigrated = $false; Seeded = $false; FrontInstalled = $false }
        (Get-ParkosLiteStepStatus -State @{ steps = @{} } -Facts $f).env | Should Be 'pending'
    }
}

Describe 'Get-ParkosLitePaths (tools)' {
    It 'las herramientas portatiles viven bajo <lite>\tools' {
        $paths = Get-ParkosLitePaths -LitePath 'C:\L' -RepoRoot 'C:\R'
        $paths.Tools | Should Be 'C:\L\tools'
    }
}

Describe 'Get-ParkosLiteRefreshPlan' {
    It 'cambios en backend/ reconstruyen el exe y migran' {
        $p = Get-ParkosLiteRefreshPlan -ChangedFiles @('backend/packages/parkos_core/src/x.py', 'README.md') -ApiBuilt $true
        $p.RebuildApi | Should Be $true
        $p.PnpmInstall | Should Be $false
    }
    It 'cambios solo en apps/ no reconstruyen el exe' {
        $p = Get-ParkosLiteRefreshPlan -ChangedFiles @('apps/electron-sucursal/src/renderer/App.tsx') -ApiBuilt $true
        $p.RebuildApi | Should Be $false
        $p.PnpmInstall | Should Be $false
    }
    It 'cambios en package.json o lockfile de apps/ reinstalan dependencias' {
        (Get-ParkosLiteRefreshPlan -ChangedFiles @('apps/pnpm-lock.yaml') -ApiBuilt $true).PnpmInstall | Should Be $true
        (Get-ParkosLiteRefreshPlan -ChangedFiles @('apps/electron-sucursal/package.json') -ApiBuilt $true).PnpmInstall | Should Be $true
        (Get-ParkosLiteRefreshPlan -ChangedFiles @('apps/ui-kit/package.json') -ApiBuilt $true).PnpmInstall | Should Be $true
    }
    It 'cambios en installer/bootstrap reconstruyen el exe' {
        (Get-ParkosLiteRefreshPlan -ChangedFiles @('installer/bootstrap/entry_api_sucursal.py') -ApiBuilt $true).RebuildApi | Should Be $true
    }
    It 'si el exe no existe se construye aunque no haya cambios' {
        (Get-ParkosLiteRefreshPlan -ChangedFiles @() -ApiBuilt $false).RebuildApi | Should Be $true
    }
    It 'migrar y recargar el seed se piden siempre (son idempotentes)' {
        $p = Get-ParkosLiteRefreshPlan -ChangedFiles @() -ApiBuilt $true
        $p.Migrate | Should Be $true
        $p.Reseed | Should Be $true
    }
    It 'acepta rutas con separador de Windows' {
        (Get-ParkosLiteRefreshPlan -ChangedFiles @('backend\x.py') -ApiBuilt $true).RebuildApi | Should Be $true
    }
}

Describe 'Test-ParkosLiteBranchName' {
    It 'acepta dev y release/v1.0' {
        (Test-ParkosLiteBranchName -Branch 'dev') | Should Be $true
        (Test-ParkosLiteBranchName -Branch 'release/v1.0') | Should Be $true
    }
    It 'rechaza metacaracteres' {
        (Test-ParkosLiteBranchName -Branch 'dev; calc') | Should Be $false
        (Test-ParkosLiteBranchName -Branch '') | Should Be $false
    }
}

Describe 'Get-ParkosLiteStartOrderUrls' {
    It 'arma las URLs de estado' {
        $u = Get-ParkosLiteUrls -ApiPort 8101 -FrontPort 5173
        $u.Front | Should Be 'http://127.0.0.1:5173/'
        $u.ApiHealth | Should Be 'http://127.0.0.1:8101/health'
    }
}

Describe 'Mensajes del lite: numeracion vigente del menu' {

    It 'ningun script del lite cita pasos con la numeracion antigua ("paso N)")' {
        $viejos = @()
        foreach ($f in (Get-ChildItem (Join-Path $PSScriptRoot '..\lite') -Filter '*.ps1')) {
            $lineas = Get-Content -LiteralPath $f.FullName
            for ($i = 0; $i -lt $lineas.Count; $i++) {
                if ($lineas[$i] -match '(?i)\bpaso [0-9]\)') { $viejos += ('{0}:{1}' -f $f.Name, ($i + 1)) }
            }
        }
        ($viejos -join ', ') | Should Be ''
    }
}
