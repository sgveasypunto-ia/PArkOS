# Tests de installer/parkos-installer.ps1's Fase 27 (HU-F27.2/HU-F27.3,
# DEC-INST-40): cifrado CMS del .env en reposo (Get-OrCreateParkosEnvCert,
# Protect-ParkosEnvContent, Write-RuntimeEnvFile, Read-ParkosEnvLines) y el
# gate de fortaleza/denylist del secreto JWT (Test-JwtSecretGate).
#
# Mismo patron que ParkosInstaller.Update.Tests.ps1: DOT-SOURCEA
# parkos-installer.ps1 directamente (las funciones quedan en el scope de
# este archivo de test, no en un modulo) - los Mock/Assert-MockCalled de
# abajo NO llevan -ModuleName.
#
# ADVERTENCIA DE HERRAMIENTA (mismo hallazgo ya documentado en
# ParkosInstaller.Update.Tests.ps1): el Pester 3.4.0 de esta instalacion
# tiene un defecto real en `Should Throw`/`Should Not Throw` SIN argumento de
# mensaje - SIEMPRE se usa `{ ... } | Should Throw '<substring esperado>'`
# con argumento explicito; para "no deberia lanzar" se usa try/catch manual +
# `Should Be $true/$false`, nunca `Should Not Throw`.

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

Describe 'Read-ParkosEnvLines (Fase 27/DEC-INST-40: CMS + texto plano)' {

    It 'parsea un .env en texto plano igual que Get-Content + Where-Object de antes' {
        $path = Join-Path $env:TEMP "parkos-readenv-plain-$(Get-Random -Maximum 999999).env"
        Set-Content -Path $path -Value @(
            'PARKOS_DEPLOY=branch'
            'PORT=8000'
        )
        try {
            $lines = @(Read-ParkosEnvLines -EnvFilePath $path)
            ($lines -contains 'PARKOS_DEPLOY=branch') | Should Be $true
            ($lines -contains 'PORT=8000') | Should Be $true
        } finally {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    It 'decodifica un .env cifrado con CMS (Unprotect-CmsMessage mockeado) devolviendo las mismas lineas' {
        $path = Join-Path $env:TEMP "parkos-readenv-cms-$(Get-Random -Maximum 999999).env"
        Set-Content -Path $path -Value @(
            '-----BEGIN CMS-----'
            'QmFzZTY0T3BhY29TaW11bGFkbw=='
            '-----END CMS-----'
        )
        Mock Unprotect-CmsMessage -ParameterFilter { $Path -eq $path } {
            "PARKOS_DEPLOY=branch`r`nPORT=8000"
        }
        try {
            $lines = @(Read-ParkosEnvLines -EnvFilePath $path)
            ($lines -contains 'PARKOS_DEPLOY=branch') | Should Be $true
            ($lines -contains 'PORT=8000') | Should Be $true
            Assert-MockCalled Unprotect-CmsMessage -Times 1 -Exactly -Scope It
        } finally {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza si el .env no existe' {
        $missingPath = Join-Path $env:TEMP "parkos-readenv-missing-$(Get-Random -Maximum 999999).env"
        { Read-ParkosEnvLines -EnvFilePath $missingPath } | Should Throw 'No se encontro el archivo .env'
    }
}

Describe 'Test-JwtSecretGate (Fase 27/HU-F27.3/DEC-INST-40)' {

    It 'no lanza con un archivo de 64 bytes aleatorios (secreto real generado por New-JwtSigningKey)' {
        $path = Join-Path $env:TEMP "parkos-jwt-ok-$(Get-Random -Maximum 999999).key"
        $bytes = New-Object byte[] 64
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        [System.IO.File]::WriteAllBytes($path, $bytes)
        try {
            $threw = $false
            try {
                Test-JwtSecretGate -Path $path | Out-Null
            } catch {
                $threw = $true
            }
            $threw | Should Be $false
        } finally {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza "demasiado corto" con un archivo de menos de 32 bytes' {
        $path = Join-Path $env:TEMP "parkos-jwt-short-$(Get-Random -Maximum 999999).key"
        [System.IO.File]::WriteAllBytes($path, (New-Object byte[] 10))
        try {
            { Test-JwtSecretGate -Path $path } | Should Throw 'Secreto JWT demasiado corto. Regenerar.'
        } finally {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza "desarrollo conocido" cuando el hash del archivo esta en la denylist (_DEFAULT_DEV_SECRET real del backend)' {
        $path = Join-Path $env:TEMP "parkos-jwt-devsecret-$(Get-Random -Maximum 999999).key"
        Set-Content -Path $path -Value 'parkos-dev-secret-do-not-use-in-prod-aaaaaaaaaaaaaaaaaaaaaaaa' -NoNewline -Encoding UTF8
        try {
            { Test-JwtSecretGate -Path $path } | Should Throw 'Secreto JWT es uno de desarrollo conocido. Regenerar.'
        } finally {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza si el archivo no existe' {
        $missingPath = Join-Path $env:TEMP "parkos-jwt-missing-$(Get-Random -Maximum 999999).key"
        { Test-JwtSecretGate -Path $missingPath } | Should Throw 'No se encontro el archivo de secreto JWT'
    }
}

Describe 'Get-OrCreateParkosEnvCert (Fase 27/HU-F27.2/DEC-INST-40)' {

    It 'es idempotente: si ya existe un certificado con Subject CN=ParkosEnvProtection, no llama New-SelfSignedCertificate' {
        Mock Get-ParkosEnvCert {
            [PSCustomObject]@{ Subject = 'CN=ParkosEnvProtection'; Thumbprint = 'EXISTINGTHUMBPRINT' }
        }
        Mock New-SelfSignedCertificate { throw 'no deberia llamarse - el certificado ya existia' }
        Mock Set-Content -ParameterFilter { $Path -like '*env-cert-thumbprint.txt' } { }

        $tempDataPath = Join-Path $env:TEMP "parkos-envcert-$(Get-Random -Maximum 999999)"
        try {
            $cert = Get-OrCreateParkosEnvCert -DataPath $tempDataPath
            $cert.Thumbprint | Should Be 'EXISTINGTHUMBPRINT'
            Assert-MockCalled New-SelfSignedCertificate -Times 0 -Exactly -Scope It
        } finally {
            Remove-Item -Path $tempDataPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'crea un certificado nuevo (New-SelfSignedCertificate) cuando ninguno existe con ese Subject' {
        Mock Get-ParkosEnvCert { return $null }
        Mock New-SelfSignedCertificate {
            [PSCustomObject]@{ Subject = 'CN=ParkosEnvProtection'; Thumbprint = 'BRANDNEWTHUMBPRINT' }
        }
        Mock Set-Content -ParameterFilter { $Path -like '*env-cert-thumbprint.txt' } { }

        $tempDataPath = Join-Path $env:TEMP "parkos-envcert-new-$(Get-Random -Maximum 999999)"
        try {
            $cert = Get-OrCreateParkosEnvCert -DataPath $tempDataPath
            $cert.Thumbprint | Should Be 'BRANDNEWTHUMBPRINT'
            Assert-MockCalled New-SelfSignedCertificate -ParameterFilter {
                $Subject -eq 'CN=ParkosEnvProtection' -and $Type -eq 'DocumentEncryptionCert'
            } -Times 1 -Exactly -Scope It
        } finally {
            Remove-Item -Path $tempDataPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Write-RuntimeEnvFile (Fase 27/HU-F27.2/DEC-INST-40: cifra con CMS)' {

    It 'llama Protect-CmsMessage (mockeado) en vez de Set-Content en texto plano' {
        Mock Get-ParkosEnvCert {
            [PSCustomObject]@{ Subject = 'CN=ParkosEnvProtection'; Thumbprint = 'FAKETHUMBPRINT' }
        }
        Mock Protect-CmsMessage { }
        Mock Set-Content { }

        $tempRoot = Join-Path $env:TEMP "parkos-writeenv-$(Get-Random -Maximum 999999)"
        $envPath = Join-Path $tempRoot 'secrets\.env'
        try {
            Write-RuntimeEnvFile -EnvFilePath $envPath -AppPassword 'S3cr3tPass' -Port 5432 -ApiPort 8000 `
                -SucursalUuid ([guid]::NewGuid().ToString()) -CloudApiUrl 'https://cloud.example.test' `
                -JwtKeyPath 'C:\ProgramData\Parkos\secrets\jwt.key' -SyncJwtPath 'C:\ProgramData\Parkos\secrets\sync-agent.jwt'

            # Nota: -To se liga al tipo real CmsMessageRecipient[] incluso a
            # traves del proxy de Mock (PowerShell convierte el string
            # 'cn=ParkosEnvProtection' a ese tipo ANTES de que el
            # ParameterFilter lo vea) - comparar $To contra el string
            # original con -eq siempre da $false, asi que el filtro se
            # limita a $OutFile (lo que realmente importa: que se escribio
            # en la ruta correcta).
            Assert-MockCalled Protect-CmsMessage -ParameterFilter {
                $OutFile -eq $envPath
            } -Times 1 -Exactly -Scope It
            Assert-MockCalled Set-Content -ParameterFilter { $Path -eq $envPath } -Times 0 -Exactly -Scope It
        } finally {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # DEC-INST-43: gap real detectado comparando infra/deploy/docker-compose.branch.yml
    # (fija PARKOS_SYNC_ENGINE=catalog_branch para api-sucursal y job-sync-sucursal)
    # contra este instalador, que nunca escribia la variable - obligatoria segun
    # engine_flag.py::_parse() (raise si esta ausente, sin default).
    It 'incluye PARKOS_SYNC_ENGINE=catalog_branch en el contenido que cifra' {
        Mock Get-ParkosEnvCert {
            [PSCustomObject]@{ Subject = 'CN=ParkosEnvProtection'; Thumbprint = 'FAKETHUMBPRINT' }
        }
        $script:capturedLines = $null
        Mock Protect-CmsMessage -ParameterFilter { $OutFile -eq $envPath } {
            # Mismo truco que el resto de este archivo para inspeccionar el
            # contenido en texto plano antes de cifrar: Protect-CmsMessage
            # (cmdlet nativo de PKI) recibe -Content como string ya armado
            # (lines -join "`r`n") en Write-RuntimeEnvFile.
            $script:capturedLines = $Content
        }
        Mock Set-Content { }

        $tempRoot = Join-Path $env:TEMP "parkos-writeenv-syncengine-$(Get-Random -Maximum 999999)"
        $envPath = Join-Path $tempRoot 'secrets\.env'
        try {
            Write-RuntimeEnvFile -EnvFilePath $envPath -AppPassword 'S3cr3tPass' -Port 5432 -ApiPort 8000 `
                -SucursalUuid ([guid]::NewGuid().ToString()) -CloudApiUrl 'https://cloud.example.test' `
                -JwtKeyPath 'C:\ProgramData\Parkos\secrets\jwt.key' -SyncJwtPath 'C:\ProgramData\Parkos\secrets\sync-agent.jwt'

            ($script:capturedLines -split "`r`n") -contains 'PARKOS_SYNC_ENGINE=catalog_branch' | Should Be $true
        } finally {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza un error claro si el certificado CN=ParkosEnvProtection no existe (en vez del error criptico de Protect-CmsMessage)' {
        Mock Get-ParkosEnvCert { return $null }
        Mock Protect-CmsMessage { throw 'esto no deberia invocarse' }

        $tempRoot = Join-Path $env:TEMP "parkos-writeenv-nocert-$(Get-Random -Maximum 999999)"
        $envPath = Join-Path $tempRoot 'secrets\.env'
        try {
            { Write-RuntimeEnvFile -EnvFilePath $envPath -AppPassword 'S3cr3tPass' -Port 5432 -ApiPort 8000 `
                -SucursalUuid ([guid]::NewGuid().ToString()) -CloudApiUrl 'https://cloud.example.test' `
                -JwtKeyPath 'C:\ProgramData\Parkos\secrets\jwt.key' -SyncJwtPath 'C:\ProgramData\Parkos\secrets\sync-agent.jwt'
            } | Should Throw "No se encontro el certificado 'CN=ParkosEnvProtection'"
        } finally {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# DEC-INST-42: las 3 passwords de Postgres (bootstrap/superuser/app) dejan de
# ser aleatorias (New-SecurePassword) y pasan a derivarse deterministicamente
# de HMAC-SHA256(clave_maestra, "<uuid_sucursal>:<purpose>") - el UUID de
# sucursal NO es secreto (viaja sin redactar en env-redacted.txt), por eso la
# clave maestra es lo que evita que cualquiera con el UUID reconstruya la
# password real.
Describe 'New-ParkosDerivedPassword (DEC-INST-42: HMAC-SHA256 deterministico)' {

    $script:FixedMasterKeyBytes = [System.Text.Encoding]::UTF8.GetBytes('clave-maestra-de-prueba-fija-32-bytes!!')

    It 'con el mismo SucursalUuid+Purpose+clave siempre devuelve el mismo resultado' {
        $uuid = [guid]::NewGuid().ToString()
        $first = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $script:FixedMasterKeyBytes
        $second = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $script:FixedMasterKeyBytes
        $first | Should Be $second
    }

    It 'con el mismo SucursalUuid, un Purpose distinto da un resultado distinto (los 3 pares)' {
        $uuid = [guid]::NewGuid().ToString()
        $bootstrap = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'postgres-bootstrap' -MasterKeyBytes $script:FixedMasterKeyBytes
        $superuser = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-superuser' -MasterKeyBytes $script:FixedMasterKeyBytes
        $app = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $script:FixedMasterKeyBytes

        ($bootstrap -eq $superuser) | Should Be $false
        ($bootstrap -eq $app) | Should Be $false
        ($superuser -eq $app) | Should Be $false
    }

    It 'con el mismo Purpose, un SucursalUuid distinto da un resultado distinto' {
        $uuidA = [guid]::NewGuid().ToString()
        $uuidB = [guid]::NewGuid().ToString()
        $passwordA = New-ParkosDerivedPassword -SucursalUuid $uuidA -Purpose 'parkos-superuser' -MasterKeyBytes $script:FixedMasterKeyBytes
        $passwordB = New-ParkosDerivedPassword -SucursalUuid $uuidB -Purpose 'parkos-superuser' -MasterKeyBytes $script:FixedMasterKeyBytes

        ($passwordA -eq $passwordB) | Should Be $false
    }

    It 'el resultado nunca contiene +, / ni = (mismo criterio que New-SecurePassword)' {
        1..20 | ForEach-Object {
            $uuid = [guid]::NewGuid().ToString()
            $password = New-ParkosDerivedPassword -SucursalUuid $uuid -Purpose 'parkos-app' -MasterKeyBytes $script:FixedMasterKeyBytes
            $password.Contains('+') | Should Be $false
            $password.Contains('/') | Should Be $false
            $password.Contains('=') | Should Be $false
        }
    }
}

Describe 'Get-ParkosMasterKeyBytes (DEC-INST-42: clave maestra de la empresa, nunca generada automaticamente)' {

    It 'lanza con el mensaje exacto si el archivo de clave maestra no existe' {
        $missingPath = Join-Path $env:TEMP "parkos-master-key-missing-$(Get-Random -Maximum 999999).key"
        { Get-ParkosMasterKeyBytes -MasterKeyPath $missingPath } | Should Throw "No se encontro la clave maestra de Parkos en $missingPath"
    }

    It 'el mensaje de clave faltante es accionable: ruta exacta + pedirla a soporte' {
        $missingPath = Join-Path $env:TEMP "parkos-master-key-missing-$(Get-Random -Maximum 999999).key"
        { Get-ParkosMasterKeyBytes -MasterKeyPath $missingPath } | Should Throw 'Solicitela al equipo de soporte por un canal seguro y copiela a esa ruta'
    }

    It 'lanza un mensaje distinto si la clave existe pero mide menos de 32 bytes' {
        $shortPath = Join-Path $env:TEMP "parkos-master-key-short-$(Get-Random -Maximum 999999).key"
        [System.IO.File]::WriteAllBytes($shortPath, [byte[]](1..31))
        try {
            { Get-ParkosMasterKeyBytes -MasterKeyPath $shortPath } | Should Throw 'demasiado corta (31 bytes; minimo 32)'
        } finally {
            Remove-Item -LiteralPath $shortPath -Force -ErrorAction SilentlyContinue
        }
    }

    It 'devuelve los bytes de una clave valida de 32 bytes' {
        $keyPath = Join-Path $env:TEMP "parkos-master-key-ok-$(Get-Random -Maximum 999999).key"
        $expected = [byte[]](1..32)
        [System.IO.File]::WriteAllBytes($keyPath, $expected)
        try {
            $bytes = Get-ParkosMasterKeyBytes -MasterKeyPath $keyPath
            ($bytes -join ',') | Should Be ($expected -join ',')
        } finally {
            Remove-Item -LiteralPath $keyPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Import-ParkosMasterKey (-MasterKeyPath: copia validada de la clave entregada por soporte)' {

    It 'copia una clave valida al destino y no imprime sus bytes' {
        $srcPath = Join-Path $env:TEMP "parkos-mk-src-$(Get-Random -Maximum 999999).key"
        $dstDir = Join-Path $env:TEMP "parkos-mk-dst-$(Get-Random -Maximum 999999)"
        $dstPath = Join-Path $dstDir 'security\parkos-master.key'
        $expected = [byte[]](40..80)
        [System.IO.File]::WriteAllBytes($srcPath, $expected)
        try {
            Import-ParkosMasterKey -SourcePath $srcPath -DestinationPath $dstPath
            (Test-Path -LiteralPath $dstPath) | Should Be $true
            ([System.IO.File]::ReadAllBytes($dstPath) -join ',') | Should Be ($expected -join ',')
        } finally {
            Remove-Item -LiteralPath $srcPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $dstDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'rechaza una clave corta y NO crea el destino' {
        $srcPath = Join-Path $env:TEMP "parkos-mk-short-$(Get-Random -Maximum 999999).key"
        $dstPath = Join-Path $env:TEMP "parkos-mk-nodst-$(Get-Random -Maximum 999999)\parkos-master.key"
        [System.IO.File]::WriteAllBytes($srcPath, [byte[]](1..8))
        try {
            { Import-ParkosMasterKey -SourcePath $srcPath -DestinationPath $dstPath } | Should Throw 'demasiado corta'
            (Test-Path -LiteralPath $dstPath) | Should Be $false
        } finally {
            Remove-Item -LiteralPath $srcPath -Force -ErrorAction SilentlyContinue
        }
    }

    It 'lanza si el archivo origen no existe' {
        $srcPath = Join-Path $env:TEMP "parkos-mk-nosrc-$(Get-Random -Maximum 999999).key"
        { Import-ParkosMasterKey -SourcePath $srcPath -DestinationPath (Join-Path $env:TEMP 'x.key') } | Should Throw 'No se encontro el archivo indicado en -MasterKeyPath'
    }
}

Describe 'Test-Preflight (aviso de clave maestra, no bloqueante)' {

    It 'imprime el [AVISO] de clave maestra cuando esta ausente' {
        Mock Get-ParkosMasterKeyProblem { 'No se encontro la clave maestra de Parkos en X' }
        Mock Write-Host { }
        Mock Test-NetConnection { $true }
        Mock Test-WindowsVersion { $true }
        $null = Test-Preflight -InstallPath "$env:SystemDrive\Parkos" -DataPath (Join-Path $env:TEMP "parkos-pf-$(Get-Random -Maximum 999999)")
        Assert-MockCalled Write-Host -ParameterFilter { $Object -like '*[[]AVISO[]] Clave maestra*' } -Times 1
    }
}

Describe 'Initialize-DatabaseRoles (DEC-INST-42: deriva superuser/app password por SucursalUuid)' {

    It 'llama New-ParkosDerivedPassword con Purpose parkos-superuser y parkos-app para el SucursalUuid recibido' {
        $uuid = [guid]::NewGuid().ToString()
        Mock New-ParkosDerivedPassword { 'mocked-password' }
        Mock Set-PgPassFile { }

        # Initialize-DatabaseRoles sigue invocando `& $PsqlPath` de forma
        # directa (Fase 22, anterior a los wrappers introducidos en fases
        # posteriores) - eso no es mockeable con Pester (mismo hallazgo ya
        # documentado en DEC-INST-38 para Invoke-ParkosNssm/Invoke-ParkosPsql).
        # Este test NO agrega cobertura nueva de psql: solo confirma que las
        # 2 passwords derivadas se piden con el Purpose correcto, que ocurre
        # ANTES de ese punto no mockeable - se tolera el fallo esperado de la
        # llamada real a psql que viene despues.
        try {
            Initialize-DatabaseRoles -PsqlPath 'C:\ruta-inexistente\psql.exe' -Port 5432 -BootstrapPassword 'boot' -SucursalUuid $uuid | Out-Null
        } catch {
            # Esperado: psql.exe no existe en esa ruta.
        }

        Assert-MockCalled New-ParkosDerivedPassword -ParameterFilter {
            $SucursalUuid -eq $uuid -and $Purpose -eq 'parkos-superuser'
        } -Times 1 -Exactly -Scope It
        Assert-MockCalled New-ParkosDerivedPassword -ParameterFilter {
            $SucursalUuid -eq $uuid -and $Purpose -eq 'parkos-app'
        } -Times 1 -Exactly -Scope It
    }
}

# Auditoria de seguridad (confianza 8/10, severidad Medium): las passwords de
# postgres (bootstrap) y parkos (superusuario) viajaban como argumento de
# linea de comandos en 3 puntos (winget --override, psql -c, seed.exe
# --database-url), expuestas ante Event ID 4688/Sysmon/EDR. Los 2 tests de
# abajo cubren los puntos 2 y 3 de esa correccion.
Describe 'Initialize-DatabaseRoles (seguridad: password de parkos por stdin, nunca por argumento)' {

    # `& $PsqlPath` con un PATH LITERAL no es mockeable con Pester (mismo
    # hallazgo ya documentado arriba para el propio Initialize-DatabaseRoles,
    # DEC-INST-38 para Invoke-ParkosNssm/Invoke-ParkosPsql) - Pester solo
    # intercepta un comando resuelto POR NOMBRE. Se predeclara aca una
    # funcion `psql` (nombre de comando resoluble) y se pasa -PsqlPath 'psql'
    # (no una ruta) para que `& $PsqlPath` SI pase por resolucion de comando
    # y el Mock de abajo lo intercepte de verdad - confirmado con un repro
    # minimo antes de escribir esto (invocar por ruta literal nunca dispara
    # el Mock; invocar por nombre resoluble si).
    function psql { }

    It 'invoca psql sin que la password aparezca en ninguno de los argumentos (viaja solo por stdin via pipeline)' {
        $uuid = [guid]::NewGuid().ToString()
        $fixedSuperuserPassword = 'Sup3r-Secret-Should-Never-Appear-In-Argv'
        Mock New-ParkosDerivedPassword -ParameterFilter { $Purpose -eq 'parkos-superuser' } { $fixedSuperuserPassword }
        Mock New-ParkosDerivedPassword -ParameterFilter { $Purpose -eq 'parkos-app' } { 'app-password-unused-here' }
        Mock Set-PgPassFile { }

        $script:CapturedPsqlCalls = @()
        Mock psql {
            # Solo args/BoundParameters son observables aca (Pester 3.4.0 NO
            # reenvia el contenido del pipeline al cuerpo del mock -
            # confirmado leyendo Mock.ps1's ExecuteBlock; por eso este test
            # no intenta capturar el SQL en si, solo confirma su AUSENCIA
            # de los argumentos, que es exactamente lo que pide la
            # correccion). Devuelve '1' para que el chequeo de
            # `-tAc "SELECT 1 FROM pg_database..."` crea que la DB ya
            # existe y no dispare una 3ra llamada (CREATE DATABASE).
            $script:CapturedPsqlCalls += , @($args)
            $global:LASTEXITCODE = 0
            '1'
        }

        Initialize-DatabaseRoles -PsqlPath 'psql' -Port 5432 -BootstrapPassword 'boot' -SucursalUuid $uuid | Out-Null

        Assert-MockCalled psql -Times 2 -Exactly -Scope It
        $script:CapturedPsqlCalls.Count | Should Be 2
        foreach ($callArgs in $script:CapturedPsqlCalls) {
            ($callArgs -contains $fixedSuperuserPassword) | Should Be $false
            ($callArgs -join ' ').Contains($fixedSuperuserPassword) | Should Be $false
            ($callArgs -contains '-c') | Should Be $false
        }
    }
}

Describe 'Invoke-CatalogSeed (seguridad: DSN de migracion por $env:DATABASE_URL, nunca por --database-url)' {

    It 'setea $env:DATABASE_URL con el DSN correcto antes de invocar seed.exe y lo limpia en el finally (mismo patron que Invoke-MigrationsAndSeed)' {
        $tempRoot = Join-Path $env:TEMP "parkos-catalogseed-$(Get-Random -Maximum 999999)"
        $script:PayloadRoot = Join-Path $tempRoot 'payload'
        $script:DataPath = Join-Path $tempRoot 'ParkosData'
        New-Item -ItemType Directory -Force -Path (Join-Path $script:PayloadRoot 'services\seed\seed') | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $script:PayloadRoot 'services\api-sucursal\api-sucursal') | Out-Null

        Mock Read-ParkosEnvLines { @('PARKOS_DEPLOY=branch') }
        Mock Start-Process { [PSCustomObject]@{ Id = 999999 } }
        Mock Invoke-WebRequest { [PSCustomObject]@{ StatusCode = 200 } }
        Mock Stop-Process { }

        # seed.exe (ruta literal via $script:PayloadRoot, no existe en este
        # fixture) no es mockeable por el mismo motivo que psql arriba - se
        # deja que esa invocacion falle (rapido, deterministico:
        # CommandNotFoundException) y se tolera con try/catch, igual que el
        # test de Initialize-DatabaseRoles ya hace con psql. Lo que SI se
        # puede observar sin tocar esa llamada no-mockeable es el `finally`
        # que limpia $env:DATABASE_URL.
        #
        # IMPORTANTE: NO se usa `Mock Remove-Item` (a diferencia de la
        # version anterior de este test) - Remove-Item es un cmdlet
        # multi-provider que implementa IDynamicParameters, y el
        # Get-DynamicParametersForCmdlet interno de Pester 3.4.0 (que
        # instancia el cmdlet real y llama su GetDynamicParameters() para
        # poder mockearlo) dispara una recursion patologica en esta
        # combinacion de SO/build de PowerShell que termina en
        # ScriptCallDepthException ("desbordamiento de profundidad de
        # llamada") - confirmado reproduciendo este mismo test de forma
        # aislada: con `Mock Remove-Item` tomaba ~95s reales (NO por los 30
        # reintentos del loop de salud - ese mock de Invoke-WebRequest SI
        # intercepta a la primera - sino por miles de frames de recursion
        # antes de tocar el limite de profundidad), y sin ese Mock el mismo
        # test corre en ~1.2s. Ademas esa excepcion no respeta
        # -ErrorAction SilentlyContinue (es terminante a nivel CLR) y
        # haciaa que el propio `finally` de Invoke-CatalogSeed fallara
        # ANTES de borrar $env:DATABASE_URL, que es la causa real de que
        # `(Test-Path Env:\DATABASE_URL) | Should Be $false` diera `$true`.
        #
        # En vez de Mock, se predeclara una funcion simple `Remove-Item`
        # (mismo patron que `function psql { }` arriba: una funcion de
        # PowerShell comun nunca pasa por el codigo de dynamicparam de
        # cmdlets de Pester) que captura el valor de $env:DATABASE_URL
        # justo antes de removerlo SOLO para esa ruta exacta, y siempre
        # delega en el cmdlet real (calificado por modulo) para no romper
        # ningun otro Remove-Item (incluida la limpieza de $tempRoot mas
        # abajo).
        $script:CapturedDatabaseUrlBeforeCleanup = $null
        function Remove-Item {
            [CmdletBinding()]
            param(
                [Parameter(Position = 0)] $Path,
                [switch]$Recurse,
                [switch]$Force
            )
            if ("$Path" -eq 'Env:\DATABASE_URL') {
                $script:CapturedDatabaseUrlBeforeCleanup = $env:DATABASE_URL
            }
            Microsoft.PowerShell.Management\Remove-Item @PSBoundParameters
        }

        $roles = @{ SuperuserPassword = 'known-superuser-pw-for-test'; AppPassword = 'unused-app-pw' }
        try {
            Invoke-CatalogSeed -EnvFilePath (Join-Path $script:DataPath 'secrets\.env') -Roles $roles -Port 5433 `
                -JwtKeyPath 'C:\ProgramData\Parkos\secrets\jwt.key' -SucursalUuid ([guid]::NewGuid().ToString()) -ApiPort 8000 | Out-Null
        } catch {
            # Esperado: seed.exe no existe en esa ruta de fixture.
        } finally {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }

        $script:CapturedDatabaseUrlBeforeCleanup | Should Be 'postgresql://parkos:known-superuser-pw-for-test@127.0.0.1:5433/parkos'
        (Test-Path Env:\DATABASE_URL) | Should Be $false
    }
}
