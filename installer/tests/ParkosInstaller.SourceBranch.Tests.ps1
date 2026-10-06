# Etapa 0: la rama de la que se descarga el fuente era `main` fija. El flujo
# del proyecto es gitflow (dev = integracion, main = produccion solo via
# release), asi que el tecnico recibia un fuente desactualizado. Ahora la rama
# es -SourceBranch con default `dev`.
#
# parkos-installer.ps1 se DOT-SOURCEA (el guard final con InvocationName '.'
# evita el auto-run) y los Mock no llevan -ModuleName. `Invoke-Git` se mockea para no
# tocar el repo real; los Should Throw llevan substring (Pester 3.4).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

Describe 'Update-SourceFromBranch' {

    Mock Push-Location { }
    Mock Pop-Location { }

    It 'usa dev por defecto (fetch, checkout y pull de dev, nunca main)' {
        $global:GitCalls = @()
        Mock Invoke-Git { $global:GitCalls += ($args -join ' '); $global:LASTEXITCODE = 0 }

        Update-SourceFromBranch

        ($global:GitCalls -join '|') | Should Be 'fetch origin dev|checkout dev|pull --ff-only origin dev'
    }

    It 'respeta una rama explicita' {
        $global:GitCalls = @()
        Mock Invoke-Git { $global:GitCalls += ($args -join ' '); $global:LASTEXITCODE = 0 }

        Update-SourceFromBranch -Branch 'release/v1.2.0'

        ($global:GitCalls -join '|') | Should Be 'fetch origin release/v1.2.0|checkout release/v1.2.0|pull --ff-only origin release/v1.2.0'
    }

    It 'rechaza nombres de rama con caracteres peligrosos sin invocar git' {
        $global:GitCalls = @()
        Mock Invoke-Git { $global:GitCalls += ($args -join ' '); $global:LASTEXITCODE = 0 }

        { Update-SourceFromBranch -Branch 'dev; calc' } | Should Throw 'nombre de rama invalido'

        $global:GitCalls.Count | Should Be 0
    }

    It 'el mensaje de error nombra la rama cuando el fetch falla' {
        Mock Invoke-Git { $global:LASTEXITCODE = 1 }

        { Update-SourceFromBranch -Branch 'dev' } | Should Throw 'git fetch origin dev fallo'
    }

    It 'el mensaje de error nombra la rama cuando el pull diverge' {
        Mock Invoke-Git { $global:LASTEXITCODE = if ($args[0] -eq 'pull') { 1 } else { 0 } }

        { Update-SourceFromBranch -Branch 'dev' } | Should Throw 'origin/dev'
    }
}

Describe 'Parametro -SourceBranch del instalador' {

    It 'existe y su default es dev' {
        $cmd = Get-Command $installerScript
        $cmd.Parameters.ContainsKey('SourceBranch') | Should Be $true
        $script:SourceBranch | Should Be 'dev'
    }
}
