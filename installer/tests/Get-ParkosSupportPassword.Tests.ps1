# Tests de installer/tools/Get-ParkosSupportPassword.ps1 (herramienta de
# SOPORTE, DEC-INST-42): reconstruye las 3 passwords de Postgres de una
# sucursal a partir de su UUID (no secreto) + la copia propia de soporte de
# la clave maestra, sin duplicar la logica de HMAC-SHA256 de
# New-ParkosDerivedPassword (parkos-installer.ps1).
#
# ADVERTENCIA DE HERRAMIENTA (mismo hallazgo ya documentado en
# ParkosInstaller.Update.Tests.ps1/ParkosInstaller.Security.Tests.ps1): el
# Pester 3.4.0 de esta instalacion tiene un defecto real en `Should
# Throw`/`Should Not Throw` SIN argumento de mensaje - SIEMPRE se usa
# `{ ... } | Should Throw '<substring esperado>'` con argumento explicito;
# para "no deberia lanzar" se usa try/catch manual + `Should Be $true/$false`,
# nunca `Should Not Throw`.
#
# Get-ParkosSupportPassword.ps1 NO es un archivo de solo-funciones como
# parkos-installer.ps1 (que se dot-sourcea UNA vez al tope del archivo y
# nunca ejecuta su flujo real porque su guard de fin de archivo lo evita
# cuando InvocationName -eq '.'): es un script imperativo de parametros
# obligatorios que hace trabajo real apenas se lo dot-sourcea. Por eso el
# MISMO patron de dot-source (`Join-Path $PSScriptRoot '..\...'` + `. $ruta`)
# se usa aca, pero invocado CON PARAMETROS DENTRO DE CADA It - nunca una vez
# sola al tope del archivo.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

$scriptUnderTest = Join-Path $PSScriptRoot '..\tools\Get-ParkosSupportPassword.ps1'

function New-TestMasterKeyFile {
    # Clave de prueba EFIMERA: generada aca mismo, nunca commiteada, nunca
    # bajo installer/payload/security/. Se limpia en el `finally` de cada test.
    param([byte[]]$Bytes = $null)
    if (-not $Bytes) {
        $Bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
    }
    $path = Join-Path $env:TEMP "parkos-support-testkey-$(Get-Random -Maximum 999999).key"
    [System.IO.File]::WriteAllBytes($path, $Bytes)
    return $path
}

Describe 'Get-ParkosSupportPassword.ps1 - validacion de parametros' {

    It 'lanza con un SucursalUuid invalido (mismo estilo de mensaje que Read-SucursalUuid)' {
        $keyPath = New-TestMasterKeyFile
        try {
            { . $scriptUnderTest -SucursalUuid 'esto-no-es-un-uuid' -MasterKeyPath $keyPath } |
                Should Throw 'no tiene formato valido'
        } finally {
            Remove-Item -Path $keyPath -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza si MasterKeyPath no existe' {
        $missingKeyPath = Join-Path $env:TEMP "parkos-support-missing-$(Get-Random -Maximum 999999).key"
        $uuid = [guid]::NewGuid().ToString()
        { . $scriptUnderTest -SucursalUuid $uuid -MasterKeyPath $missingKeyPath } |
            Should Throw 'No se encontro la clave maestra de Parkos'
    }
}

Describe 'Get-ParkosSupportPassword.ps1 - derivacion (DEC-INST-42: debe coincidir con New-ParkosDerivedPassword)' {

    It 'con -Purpose parkos-app copia la MISMA password que New-ParkosDerivedPassword directamente' {
        $fixedKeyBytes = [System.Text.Encoding]::UTF8.GetBytes('clave-de-prueba-soporte-fija-32-bytes!!')
        $keyPath = New-TestMasterKeyFile -Bytes $fixedKeyBytes
        $uuid = [guid]::NewGuid().ToString()
        $expectedPassword = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $fixedKeyBytes

        Mock Set-Clipboard { }
        try {
            . $scriptUnderTest -SucursalUuid $uuid -MasterKeyPath $keyPath -Purpose 'parkos-app'
            Assert-MockCalled Set-Clipboard -ParameterFilter {
                $Value -eq $expectedPassword
            } -Times 1 -Exactly -Scope It
        } finally {
            Remove-Item -Path $keyPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Get-ParkosSupportPassword.ps1 - modo clipboard por defecto (-Purpose all)' {

    It 'copia las 3 passwords y pide confirmacion SOLO entre pares (2 veces para 3 passwords, nunca despues de la ultima)' {
        $keyPath = New-TestMasterKeyFile
        $uuid = [guid]::NewGuid().ToString()

        Mock Set-Clipboard { }
        Mock Read-Host { '' }
        try {
            . $scriptUnderTest -SucursalUuid $uuid -MasterKeyPath $keyPath -Purpose 'all'

            Assert-MockCalled Set-Clipboard -Times 3 -Exactly -Scope It
            # Regla implementada: confirmar despues de la password 1 y de la
            # password 2, pero NUNCA despues de la 3ra (ultima) - no hay
            # ninguna password siguiente que la vaya a sobreescribir.
            Assert-MockCalled Read-Host -Times 2 -Exactly -Scope It
        } finally {
            Remove-Item -Path $keyPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Get-ParkosSupportPassword.ps1 - modo -Reveal' {

    It 'nunca toca el portapapeles y muestra la tabla completa en texto plano' {
        $fixedKeyBytes = [System.Text.Encoding]::UTF8.GetBytes('otra-clave-de-prueba-fija-de-32-bytes!!')
        $keyPath = New-TestMasterKeyFile -Bytes $fixedKeyBytes
        $uuid = [guid]::NewGuid().ToString()
        $expectedPassword = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $fixedKeyBytes

        Mock Set-Clipboard { throw 'no deberia llamarse en modo -Reveal' }
        try {
            $output = . $scriptUnderTest -SucursalUuid $uuid -MasterKeyPath $keyPath -Purpose 'parkos-app' -Reveal | Out-String

            Assert-MockCalled Set-Clipboard -Times 0 -Exactly -Scope It
            ($output -match 'parkos-app') | Should Be $true
            ($output -match [regex]::Escape($expectedPassword)) | Should Be $true
        } finally {
            Remove-Item -Path $keyPath -Force -ErrorAction SilentlyContinue
        }
    }
}
