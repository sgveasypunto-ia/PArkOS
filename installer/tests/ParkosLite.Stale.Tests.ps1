# Tests de la deteccion de build desactualizado del lite (API/front construidos
# en un commit anterior al HEAD del repo) y de la oferta de reconstruir.
# Git, preguntas y pasos pasan por wrappers que se mockean; nada real se ejecuta.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Core.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Tools.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Autostart.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Run.ps1')

# Vive en parkos-lite.ps1 (el TUI); aqui solo se necesita para poder mockearla.
function Invoke-ParkosLiteTuiStep { param($Ctx, $Key) $true }

function New-TestCtx {
    param([string]$Name)
    $lite = Join-Path $TestDrive $Name
    $paths = Get-ParkosLitePaths -LitePath $lite -RepoRoot (Join-Path $TestDrive "$Name-repo")
    return @{ Paths = $paths; State = (New-ParkosLiteState); Secrets = @{ PostgresPassword = 'p'; SuperuserPassword = 's'; AppPassword = 'a' }; Branch = 'dev'; Logger = { param($m) }; ScriptPath = 'C:\x\parkos-lite.ps1' }
}

Describe 'Get-ParkosLiteCommitsAhead' {
    It 'cuenta los commits entre el commit construido y HEAD' {
        Mock Invoke-ParkosLiteGit {
            if ($Arguments[0] -eq 'rev-parse') { @{ ExitCode = 0; Output = @('abc') } } else { @{ ExitCode = 0; Output = @('23') } }
        }
        Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built 'abcdef1234' | Should Be 23
    }
    It 'con rutas limita el conteo (-- rutas)' {
        $global:aheadArgs = @()
        Mock Invoke-ParkosLiteGit {
            $global:aheadArgs += ($Arguments -join ' ')
            if ($Arguments[0] -eq 'rev-parse') { @{ ExitCode = 0; Output = @('abc') } } else { @{ ExitCode = 0; Output = @('4') } }
        }
        Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built 'abcdef1234' -PathSpecs @('backend', 'installer/bootstrap') | Should Be 4
        ($global:aheadArgs -join '|') | Should Match 'rev-list --count abcdef1234\.\.HEAD -- backend installer/bootstrap'
    }
    It 'commit vacio, mal formado o ausente del clon (superficial): $null' {
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 1; Output = @('fatal') } }
        ($null -eq (Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built '')) | Should Be $true
        ($null -eq (Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built 'no es un sha')) | Should Be $true
        ($null -eq (Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built 'abcdef1234')) | Should Be $true
    }
    It 'sin git (el comando lanza): $null, no revienta' {
        Mock Invoke-ParkosLiteGit { throw 'git: no se reconoce' }
        ($null -eq (Get-ParkosLiteCommitsAhead -RepoRoot 'C:' -Built 'abcdef1234')) | Should Be $true
    }
}

Describe 'Get-ParkosLiteBuildStaleness' {
    BeforeEach {
        $script:ctx = New-TestCtx 'stale'
        $script:ctx.State.api_built_commit = 'abcdef1234567890'
        $script:ctx.State.front_built_commit = '1234567abcdef000'
    }
    It 'API con commits de backend nuevos: avisa con commit corto, N y la opcion 12' {
        Mock Get-ParkosLiteCommitsAhead {
            if ($PathSpecs -contains 'backend') { 5 } elseif ($PathSpecs.Count -gt 0) { 0 } else { 23 }
        }
        $r = @(Get-ParkosLiteBuildStaleness -Ctx $script:ctx)
        $r.Count | Should Be 1
        $r[0].Key | Should Be 'api'
        $r[0].Message | Should Match 'abcdef1'
        $r[0].Message | Should Match '23 commits adelante'
        $r[0].Message | Should Match 'opcion 12 \(Construir API \(\.exe\)\)'
    }
    It 'solo cambio documentacion (ningun commit toca backend/): no avisa' {
        Mock Get-ParkosLiteCommitsAhead { if ($PathSpecs.Count -gt 0) { 0 } else { 30 } }
        @(Get-ParkosLiteBuildStaleness -Ctx $script:ctx).Count | Should Be 0
    }
    It 'dependencias del front con cambios: avisa con la opcion 15' {
        Mock Get-ParkosLiteCommitsAhead {
            if ($PathSpecs -contains 'backend') { 0 } elseif ($PathSpecs.Count -gt 0) { 2 } else { 9 }
        }
        $r = @(Get-ParkosLiteBuildStaleness -Ctx $script:ctx)
        $r.Count | Should Be 1
        $r[0].Key | Should Be 'front'
        $r[0].Message | Should Match 'opcion 15 \(Instalar dependencias del front\)'
    }
    It 'estado viejo sin front_built_commit o sin git: no avisa ni revienta' {
        $script:ctx.State.Remove('front_built_commit')
        $script:ctx.State.api_built_commit = ''
        Mock Get-ParkosLiteCommitsAhead { $null }
        @(Get-ParkosLiteBuildStaleness -Ctx $script:ctx).Count | Should Be 0
    }
    It 'contexto sin rutas: lista vacia' {
        @(Get-ParkosLiteBuildStaleness -Ctx @{ State = @{} }).Count | Should Be 0
    }
}

Describe 'Invoke-ParkosLiteStaleBuildOffer' {
    BeforeEach {
        $script:ctx = New-TestCtx 'offer'
        $global:offerCalls = @()
        $global:offerOut = @()
        Mock Write-Host { $global:offerOut += [string]$Object }
        Mock Invoke-ParkosLiteTuiStep { $global:offerCalls += "step:$Key"; $true }
        Mock Get-ParkosLiteBuildStaleness {
            @([PSCustomObject]@{ Key = 'api'; Message = 'La API se construyo en abcdef1 y el repo esta 23 commits adelante.' })
        }
    }
    It 'sin build viejo no dice ni pregunta nada' {
        Mock Get-ParkosLiteBuildStaleness { @() }
        Mock Read-Host { throw 'no deberia preguntar' }
        Invoke-ParkosLiteStaleBuildOffer -Ctx $script:ctx -AllowRebuild | Should Be $false
        $global:offerOut.Count | Should Be 0
    }
    It 'no interactivo (desatendido): solo avisa, NUNCA reconstruye ni pregunta' {
        Mock Test-ParkosLiteInteractive { $false }
        Mock Read-Host { throw 'no deberia preguntar' }
        Invoke-ParkosLiteStaleBuildOffer -Ctx $script:ctx -AllowRebuild | Should Be $false
        ($global:offerOut -join "`n") | Should Match 'La API se construyo en abcdef1'
        $global:offerCalls.Count | Should Be 0
    }
    It 'interactivo, Enter (default No): no reconstruye' {
        Mock Test-ParkosLiteInteractive { $true }
        Mock Read-Host { '' }
        Invoke-ParkosLiteStaleBuildOffer -Ctx $script:ctx -AllowRebuild | Should Be $false
        $global:offerCalls.Count | Should Be 0
    }
    It 'sin -AllowRebuild (menu/estado): solo avisa' {
        Mock Test-ParkosLiteInteractive { $true }
        Mock Read-Host { throw 'no deberia preguntar' }
        Invoke-ParkosLiteStaleBuildOffer -Ctx $script:ctx | Should Be $false
        $global:offerCalls.Count | Should Be 0
    }
    It 'interactivo y responde s: reconstruye la API y migra' {
        Mock Test-ParkosLiteInteractive { $true }
        Mock Read-Host { 's' }
        Invoke-ParkosLiteStaleBuildOffer -Ctx $script:ctx -AllowRebuild | Should Be $true
        ($global:offerCalls -join ',') | Should Be 'step:api,step:migrate'
    }
}

Describe 'commits de build en el estado' {
    It 'front_built_commit existe en el estado nuevo y un estado viejo (sin el campo) se lee bien' {
        (New-ParkosLiteState).ContainsKey('front_built_commit') | Should Be $true
        $f = Join-Path $TestDrive 'old-state.json'
        Set-Content $f '{"sucursal_uuid":"","db_port":5433,"api_port":8100,"front_port":5173,"source_branch":"dev","api_built_commit":"abc","steps":{"env":"ok"}}'
        $s = Read-ParkosLiteState -Path $f
        $s.api_built_commit | Should Be 'abc'
        $s.front_built_commit | Should Be ''
    }
    It 'el estado guardado conserva front_built_commit' {
        $f = Join-Path $TestDrive 'new-state.json'
        $s = New-ParkosLiteState
        $s.front_built_commit = 'fedcba9876'
        Save-ParkosLiteState -State $s -Path $f
        (Read-ParkosLiteState -Path $f).front_built_commit | Should Be 'fedcba9876'
    }
    It 'el paso front guarda el commit con el que instalo las dependencias' {
        $ctx = New-TestCtx 'frontc'
        Mock Stop-ParkosLiteService { $true }
        Mock Invoke-ParkosLitePnpmInstall { 0 }
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 0; Output = @('headcommit123') } }
        Invoke-ParkosLiteStep -Ctx $ctx -Key 'front'
        $ctx.State.front_built_commit | Should Be 'headcommit123'
    }
    It 'el paso api con exe al dia (omite el build) actualiza api_built_commit a HEAD' {
        $ctx = New-TestCtx 'apiskip'
        $ctx.State.api_built_commit = 'oldold1'
        Mock Get-ParkosLiteApiSourcePlan { @{ Action = 'build'; Commit = ''; Reason = 'sin partes' } }
        Mock Test-ParkosLiteApiBuildNeeded { $false }
        Mock Invoke-ParkosLiteGit { @{ ExitCode = 0; Output = @('headcommit123') } }
        Invoke-ParkosLiteStep -Ctx $ctx -Key 'api'
        $ctx.State.api_built_commit | Should Be 'headcommit123'
    }
}
