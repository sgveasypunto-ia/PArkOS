# Regresion Stage 0 (Invoke-SourceUpdateAndBuild / Test-BuildToolchain):
# Test-BuildToolchain retorna @() cuando TODAS las herramientas estan
# presentes, y PowerShell desenrolla @() a $null al salir de la funcion.
# `$missing.Count` sobre $null revienta bajo Set-StrictMode -Version Latest
# ("No se encuentra la propiedad Count"), justo en el camino feliz. El fix
# envuelve la llamada en @(...).
#
# Como en ParkosInstaller.Update.Tests.ps1, parkos-installer.ps1 se
# DOT-SOURCEA (el guard final con InvocationName '.' evita el auto-run) y
# los Mock no llevan -ModuleName. Ese dot-source ejecuta
# `Set-StrictMode -Version Latest` (parkos-installer.ps1:145) en el scope
# del test, asi que las funciones corren bajo StrictMode sin setearlo aca.
# Los `Should Throw` llevan substring de mensaje (Pester 3.4 reporta mal
# `Should Throw` a secas).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

Describe 'Invoke-SourceUpdateAndBuild - toolchain check bajo StrictMode' {

    # Corta justo despues del check del toolchain: si el check pasa, el
    # primer paso siguiente es Push-Location (sentinela); asi no se ejecuta
    # git ni build-release.ps1 de verdad.
    Mock Push-Location { throw 'SENTINELA-POST-TOOLCHAIN' }

    It 'no lanza por .Count cuando Test-BuildToolchain retorna vacio (toolchain completo)' {
        Mock Test-BuildToolchain { @() }

        { Invoke-SourceUpdateAndBuild } | Should Throw 'SENTINELA-POST-TOOLCHAIN'
    }

    It 'sigue fallando con mensaje claro cuando falta una herramienta' {
        Mock Test-BuildToolchain { 'pnpm' }

        { Invoke-SourceUpdateAndBuild } | Should Throw 'Falta instalar: pnpm'
    }

    It 'reporta todas las herramientas faltantes (varias)' {
        Mock Test-BuildToolchain { 'git'; 'uv' }

        { Invoke-SourceUpdateAndBuild } | Should Throw 'Falta instalar: git, uv'
    }
}

Describe 'Test-BuildToolchain' {

    It 'retorna vacio cuando git, pnpm y uv estan presentes' {
        Mock Get-Command { [pscustomobject]@{ Name = 'fake' } } -ParameterFilter { $Name -in 'git', 'pnpm', 'uv' }
        @(Test-BuildToolchain).Count | Should Be 0
    }

    It 'lista las herramientas ausentes' {
        Mock Get-Command { $null } -ParameterFilter { $Name -in 'git', 'pnpm', 'uv' }
        (@(Test-BuildToolchain) -join ',') | Should Be 'git,pnpm,uv'
    }
}
