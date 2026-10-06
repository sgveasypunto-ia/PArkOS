# Tests del preflight de payload de installer/parkos-installer.ps1
# (Assert-PayloadPath, Copy-ServiceBundle e Invoke-MigrationsAndSeed): en una
# maquina donde la etapa 0 nunca produjo el payload, las etapas 5/6/7 deben
# fallar con un mensaje claro (artefacto faltante + "opcion 0") en vez del
# "No se encuentra la ruta de acceso" crudo de Copy-Item/Push-Location.
#
# Mismo dot-source directo de parkos-installer.ps1 que los otros archivos de
# este directorio. Pester 3.4.0: todo `Should Throw` lleva un substring de
# mensaje esperado (sin mensaje nunca evalua de verdad en esta instalacion).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

function New-PayloadTestRoot {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) ("parkos-payload-test-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    return $root
}

Describe 'Assert-PayloadPath' {
    It 'lanza un mensaje claro que nombra el artefacto y la opcion 0 cuando falta la ruta' {
        $root = New-PayloadTestRoot
        try {
            { Assert-PayloadPath -Path (Join-Path $root 'nope') -What 'el artefacto X' } | Should Throw 'Falta el artefacto X en el payload'
            { Assert-PayloadPath -Path (Join-Path $root 'nope') -What 'el artefacto X' } | Should Throw 'opcion 0'
        } finally { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
    }

    It 'no lanza cuando la ruta existe' {
        $root = New-PayloadTestRoot
        $threw = $false
        try { Assert-PayloadPath -Path $root -What 'la raiz' } catch { $threw = $true }
        Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
        $threw | Should Be $false
    }
}

Describe 'Copy-ServiceBundle preflight' {
    It 'con el directorio del servicio ausente lanza el mensaje del bundle (no el crudo de Copy-Item)' {
        $root = New-PayloadTestRoot
        $script:PayloadRoot = Join-Path $root 'payload'
        try {
            { Copy-ServiceBundle -Name 'api-sucursal' -InstallPath (Join-Path $root 'inst') } | Should Throw "bundle del servicio 'api-sucursal'"
            Test-Path (Join-Path $root 'inst') | Should Be $false
        } finally { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
    }

    It 'con el onedir presente pero sin el .exe lanza el mensaje del ejecutable' {
        $root = New-PayloadTestRoot
        $script:PayloadRoot = Join-Path $root 'payload'
        New-Item -ItemType Directory -Force -Path (Join-Path $script:PayloadRoot 'services\api-sucursal\api-sucursal') | Out-Null
        try {
            { Copy-ServiceBundle -Name 'api-sucursal' -InstallPath (Join-Path $root 'inst') } | Should Throw "api-sucursal.exe"
        } finally { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
    }

    It 'con el payload completo copia el onedir y devuelve la ruta del .exe' {
        $root = New-PayloadTestRoot
        $script:PayloadRoot = Join-Path $root 'payload'
        $src = Join-Path $script:PayloadRoot 'services\api-sucursal\api-sucursal'
        New-Item -ItemType Directory -Force -Path $src | Out-Null
        Set-Content -Path (Join-Path $src 'api-sucursal.exe') -Value 'dummy'
        try {
            $exe = Copy-ServiceBundle -Name 'api-sucursal' -InstallPath (Join-Path $root 'inst')
            $exe | Should Be (Join-Path $root 'inst\api-sucursal\api-sucursal.exe')
            Test-Path $exe | Should Be $true
        } finally { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
    }
}

Describe 'Invoke-MigrationsAndSeed preflight' {
    It 'con el bundle migrate ausente lanza el mensaje claro antes de Push-Location' {
        $root = New-PayloadTestRoot
        $script:PayloadRoot = Join-Path $root 'payload'
        try {
            { Invoke-MigrationsAndSeed -Roles @{} -Port 5432 } | Should Throw "bundle del servicio 'migrate'"
        } finally { Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue }
    }
}
