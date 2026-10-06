# Tests de installer/shared/ParkosPostgresDownload.ps1 (descarga/instalacion
# de Postgres 16 + extension pg_partman SQL-only, compartido por el instalador
# completo y el instalador lite). Pester 3.4: Mock sin -ModuleName; Should
# Throw lleva substring; "no deberia lanzar" = try/catch + Should Be $true.
# Toda llamada de red/zip/hash/sleep esta envuelta en funciones propias que se
# mockean aqui: ningun test toca la red.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')

$script:quiet = { param($m) }

Describe 'Get-ParkosPostgresDownloadInfo' {
    It 'fija version y URL de EnterpriseDB' {
        $i = Get-ParkosPostgresDownloadInfo
        $i.Version | Should Match '^16\.\d+-\d+$'
        $i.FileName | Should Be "postgresql-$($i.Version)-windows-x64-binaries.zip"
        $i.Url | Should Be "https://get.enterprisedb.com/postgresql/$($i.FileName)"
    }
}

Describe 'Test-ParkosPostgresZip' {
    It 'acepta un zip con pg_ctl, initdb y psql' {
        Mock Get-ParkosZipEntryNames { 'pgsql/bin/pg_ctl.exe', 'pgsql/bin/initdb.exe', 'pgsql/bin/psql.exe', 'pgsql/share/x' }
        (Test-ParkosPostgresZip -Path 'x.zip') | Should Be $true
    }
    It 'acepta separadores de Windows y mayusculas' {
        Mock Get-ParkosZipEntryNames { 'PGSQL\BIN\PG_CTL.EXE', 'pgsql\bin\initdb.exe', 'pgsql\bin\psql.exe' }
        (Test-ParkosPostgresZip -Path 'x.zip') | Should Be $true
    }
    It 'rechaza un zip al que le falta initdb' {
        Mock Get-ParkosZipEntryNames { 'pgsql/bin/pg_ctl.exe', 'pgsql/bin/psql.exe' }
        (Test-ParkosPostgresZip -Path 'x.zip') | Should Be $false
    }
    It 'rechaza un archivo que no es zip (la lectura lanza)' {
        Mock Get-ParkosZipEntryNames { throw 'invalid zip' }
        (Test-ParkosPostgresZip -Path 'x.zip') | Should Be $false
    }
}

Describe 'Get-ParkosDownloadBackoffSeconds' {
    It 'crece de forma exponencial y se acota' {
        (Get-ParkosDownloadBackoffSeconds -Attempt 1) | Should Be 5
        (Get-ParkosDownloadBackoffSeconds -Attempt 2) | Should Be 10
        (Get-ParkosDownloadBackoffSeconds -Attempt 3) | Should Be 20
        (Get-ParkosDownloadBackoffSeconds -Attempt 10) | Should Be 60
    }
}

Describe 'Get-ParkosDownloadFailureMessage' {
    It 'incluye URL, carpeta destino y nombre de archivo, en español' {
        $m = Get-ParkosDownloadFailureMessage -What 'Postgres' -Url 'https://x/y.zip' -TargetDir 'C:\d' -FileName 'y.zip' -Detail 'boom'
        $m | Should Match 'https://x/y.zip'
        $m | Should Match 'C:\\d'
        $m | Should Match 'y\.zip'
        $m | Should Match 'boom'
        $m | Should Match 'Internet'
    }
}

Describe 'Get-ParkosPostgresZip' {
    BeforeEach {
        $script:id = [guid]::NewGuid().ToString('N')
        $script:cache = Join-Path $TestDrive "dl$($script:id)"
        $script:payload = Join-Path $TestDrive "payload$($script:id)"
        $script:name = (Get-ParkosPostgresDownloadInfo).FileName
        Mock Start-ParkosSleep { }
        Mock Get-ParkosFileSha256 { 'HASH1' }
    }

    It 'cache hit: no descarga y devuelve la ruta cacheada' {
        New-Item -ItemType Directory -Force -Path $script:cache | Out-Null
        Set-Content (Join-Path $script:cache $script:name) 'zip'
        Mock Test-ParkosPostgresZip { $true }
        Mock Invoke-ParkosHttpDownload { throw 'no deberia descargar' }

        $r = Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet
        $r | Should Be (Join-Path $script:cache $script:name)
    }

    It 'cache hit registra el hash en el .sha256 la primera vez' {
        New-Item -ItemType Directory -Force -Path $script:cache | Out-Null
        $z = Join-Path $script:cache $script:name
        Set-Content $z 'zip'
        Mock Test-ParkosPostgresZip { $true }
        Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet | Out-Null
        (Get-Content "$z.sha256" -Raw).Trim() | Should Be 'HASH1'
    }

    It 'cache hit con hash distinto al registrado falla sin descargar' {
        New-Item -ItemType Directory -Force -Path $script:cache | Out-Null
        $z = Join-Path $script:cache $script:name
        Set-Content $z 'zip'
        Set-Content "$z.sha256" 'OTHER'
        Mock Test-ParkosPostgresZip { $true }
        Mock Invoke-ParkosHttpDownload { }
        { Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet -MaxAttempts 1 } | Should Throw 'hash'
    }

    It 'usa el zip de installer\payload\postgres si existe (nombre generico)' {
        New-Item -ItemType Directory -Force -Path $script:payload | Out-Null
        $p = Join-Path $script:payload 'postgresql-16-windows-x64-binaries.zip'
        Set-Content $p 'zip'
        Mock Test-ParkosPostgresZip { $true }
        Mock Invoke-ParkosHttpDownload { throw 'no deberia descargar' }
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        $r | Should Be $p
    }

    It 'sin cache: descarga a .part, valida, renombra y guarda hash' {
        $global:dlTry = 0
        Mock Invoke-ParkosHttpDownload { $global:dlTry++; Set-Content $OutFile 'data' }
        Mock Test-ParkosPostgresZip { $true }
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet
        $r | Should Be (Join-Path $script:cache $script:name)
        (Test-Path $r) | Should Be $true
        (Test-Path "$r.part") | Should Be $false
        (Test-Path "$r.sha256") | Should Be $true
        $global:dlTry | Should Be 1
    }

    It 'reintenta con backoff y tiene exito en el 3er intento' {
        $global:dlTry = 0; $global:sleepN = 0
        Mock Start-ParkosSleep { $global:sleepN++ }
        Mock Invoke-ParkosHttpDownload { $global:dlTry++; if ($global:dlTry -lt 3) { throw 'timeout' }; Set-Content $OutFile 'data' }
        Mock Test-ParkosPostgresZip { $true }
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet
        (Test-Path $r) | Should Be $true
        $global:dlTry | Should Be 3
        $global:sleepN | Should Be 2
    }

    It 'agota los intentos y lanza el mensaje en español con la URL' {
        $global:dlTry = 0
        Mock Invoke-ParkosHttpDownload { $global:dlTry++; throw 'sin red' }
        $threw = $false; $msg = ''
        try { Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet -MaxAttempts 3 } catch { $threw = $true; $msg = $_.Exception.Message }
        $threw | Should Be $true
        $msg | Should Match 'get.enterprisedb.com'
        $msg | Should Match 'sin red'
        $global:dlTry | Should Be 3
    }

    It 'un zip descargado invalido se descarta (no se reanuda) y cuenta como intento fallido' {
        Mock Invoke-ParkosHttpDownload { Set-Content $OutFile 'corrupto' }
        Mock Test-ParkosPostgresZip { $false }
        $threw = $false
        try { Get-ParkosPostgresZip -CacheDir $script:cache -Logger $script:quiet -MaxAttempts 2 } catch { $threw = $true }
        $threw | Should Be $true
        (Test-Path (Join-Path $script:cache "$($script:name).part")) | Should Be $false
        (Test-Path (Join-Path $script:cache $script:name)) | Should Be $false
    }
}

Describe 'Expand-ParkosPostgresZip' {
    It 'extrae a un temporal y deja PgRoot con bin\pg_ctl.exe' {
        $root = Join-Path $TestDrive 'lite\pgsql'
        Mock Expand-ParkosZipArchive {
            New-Item -ItemType Directory -Force -Path (Join-Path $Destination 'pgsql\bin') | Out-Null
            Set-Content (Join-Path $Destination 'pgsql\bin\pg_ctl.exe') 'x'
        }
        $r = Expand-ParkosPostgresZip -ZipPath 'a.zip' -PgRoot $root -Logger $script:quiet
        $r | Should Be $root
        (Test-Path (Join-Path $root 'bin\pg_ctl.exe')) | Should Be $true
        (Test-Path "$root.extracting") | Should Be $false
    }
    It 'es idempotente: si ya esta extraido no vuelve a extraer' {
        $root = Join-Path $TestDrive 'lite2\pgsql'
        New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin') | Out-Null
        Set-Content (Join-Path $root 'bin\pg_ctl.exe') 'x'
        Mock Expand-ParkosZipArchive { throw 'no deberia extraer' }
        (Expand-ParkosPostgresZip -ZipPath 'a.zip' -PgRoot $root -Logger $script:quiet) | Should Be $root
    }
    It 'falla con mensaje claro si el zip no trae bin\pg_ctl.exe' {
        $root = Join-Path $TestDrive 'lite3\pgsql'
        Mock Expand-ParkosZipArchive { New-Item -ItemType Directory -Force -Path (Join-Path $Destination 'otra') | Out-Null }
        { Expand-ParkosPostgresZip -ZipPath 'a.zip' -PgRoot $root -Logger $script:quiet } | Should Throw 'pg_ctl.exe'
    }
}

Describe 'Get-ParkosPgPartmanExtension / New-ParkosPgPartmanSqlOnly' {
    BeforeEach { Mock Start-ParkosSleep { } }

    It 'usa el directorio del payload si ya tiene .sql y .control (sin descargar)' {
        $pl = Join-Path $TestDrive 'pl\extension'
        New-Item -ItemType Directory -Force -Path $pl | Out-Null
        Set-Content (Join-Path $pl 'pg_partman--5.1.0.sql') 'x'
        Set-Content (Join-Path $pl 'pg_partman.control') 'x'
        Mock Invoke-ParkosHttpDownload { throw 'no deberia descargar' }
        $r = Get-ParkosPgPartmanExtension -ExtensionDir (Join-Path $TestDrive 'cache\ext') -PayloadDir $pl -TempDir (Join-Path $TestDrive 'tmp') -Logger $script:quiet
        $r | Should Be $pl
    }

    It 'ensambla el SQL-only en el mismo orden types,tables,functions,procedures' {
        $src = Join-Path $TestDrive 'src'
        foreach ($s in 'types', 'tables', 'functions', 'procedures') {
            New-Item -ItemType Directory -Force -Path (Join-Path $src "sql\$s") | Out-Null
            Set-Content (Join-Path $src "sql\$s\b.sql") "-- $s b"
            Set-Content (Join-Path $src "sql\$s\a.sql") "-- $s a"
        }
        Set-Content (Join-Path $src 'pg_partman.control') 'default_version = 5.1.0'
        $out = Join-Path $TestDrive 'out'
        New-ParkosPgPartmanSqlOnly -SourceRoot $src -Version '5.1.0' -OutDir $out
        $text = [IO.File]::ReadAllText((Join-Path $out 'pg_partman--5.1.0.sql'))
        $order = [regex]::Matches($text, '-- (\w+) (\w)') | ForEach-Object { "$($_.Groups[1].Value)$($_.Groups[2].Value)" }
        ($order -join ',') | Should Be 'typesa,typesb,tablesa,tablesb,functionsa,functionsb,proceduresa,proceduresb'
        (Test-Path (Join-Path $out 'pg_partman.control')) | Should Be $true
    }

    It 'sin payload ni cache descarga el archivo de GitHub y lo ensambla' {
        $ext = Join-Path $TestDrive 'cache2\ext'
        Mock Invoke-ParkosHttpDownload { Set-Content $OutFile 'zipdata' }
        Mock Expand-ParkosZipArchive {
            $r = Join-Path $Destination 'pg_partman-5.1.0'
            foreach ($s in 'types', 'tables', 'functions', 'procedures') {
                New-Item -ItemType Directory -Force -Path (Join-Path $r "sql\$s") | Out-Null
                Set-Content (Join-Path $r "sql\$s\a.sql") "-- $s"
            }
            Set-Content (Join-Path $r 'pg_partman.control') 'c'
        }
        $r = Get-ParkosPgPartmanExtension -ExtensionDir $ext -TempDir (Join-Path $TestDrive 'tmp2') -Logger $script:quiet
        $r | Should Be $ext
        (Test-Path (Join-Path $ext 'pg_partman--5.1.0.sql')) | Should Be $true
        (Test-Path (Join-Path $ext 'pg_partman.control')) | Should Be $true
    }

    It 'falla con mensaje en español si la descarga no es posible' {
        Mock Invoke-ParkosHttpDownload { throw 'sin red' }
        $threw = $false; $msg = ''
        try { Get-ParkosPgPartmanExtension -ExtensionDir (Join-Path $TestDrive 'c3\ext') -TempDir (Join-Path $TestDrive 'tmp3') -Logger $script:quiet -MaxAttempts 2 } catch { $threw = $true; $msg = $_.Exception.Message }
        $threw | Should Be $true
        $msg | Should Match 'pg_partman'
        $msg | Should Match 'github.com'
    }
}

Describe 'Install-ParkosPgPartmanExtension' {
    It 'copia .sql y .control a share\extension del PgRoot' {
        $ext = Join-Path $TestDrive 'e\ext'
        New-Item -ItemType Directory -Force -Path $ext | Out-Null
        Set-Content (Join-Path $ext 'pg_partman--5.1.0.sql') 'x'
        Set-Content (Join-Path $ext 'pg_partman.control') 'x'
        $pg = Join-Path $TestDrive 'e\pgsql'
        New-Item -ItemType Directory -Force -Path (Join-Path $pg 'share\extension') | Out-Null
        Install-ParkosPgPartmanExtension -PgRoot $pg -ExtensionDir $ext
        (Test-Path (Join-Path $pg 'share\extension\pg_partman.control')) | Should Be $true
        (Test-Path (Join-Path $pg 'share\extension\pg_partman--5.1.0.sql')) | Should Be $true
    }
}

# ---------------------------------------------------------------------------
# Partes versionadas del ZIP (el ZIP completo supera los 100 MB de GitHub)
# ---------------------------------------------------------------------------
Describe 'Postgres ZIP en partes versionadas' {
    BeforeEach {
        $script:id = [guid]::NewGuid().ToString('N')
        $script:cache = Join-Path $TestDrive "dl$($script:id)"
        $script:payload = Join-Path $TestDrive "pl$($script:id)"
        New-Item -ItemType Directory -Force -Path $script:payload | Out-Null
        $script:name = (Get-ParkosPostgresDownloadInfo).FileName
        Mock Start-ParkosSleep { }
        Mock Test-ParkosPostgresZip { $true }
        Mock Get-ParkosFileSha256 { param($Path) (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
        Mock Invoke-ParkosHttpDownload { throw 'no deberia descargar' }
        # Contenido conocido repartido en 3 partes (la 11 sirve para probar el orden numerico).
        $script:bytes = [byte[]](1..250)
        $script:partData = @(
            $script:bytes[0..99],
            $script:bytes[100..199],
            $script:bytes[200..249]
        )
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $script:fullHash = ([BitConverter]::ToString($sha.ComputeHash([byte[]]$script:bytes)) -replace '-', '').ToLowerInvariant()
        $sha.Dispose()
    }

    function New-FakeParts([int[]]$Numbers = @(1, 2, 3), [string]$Sidecar = $null) {
        for ($i = 0; $i -lt $Numbers.Count; $i++) {
            [System.IO.File]::WriteAllBytes((Join-Path $script:payload ("{0}.part{1:D2}" -f $script:name, $Numbers[$i])), [byte[]]$script:partData[$i])
        }
        if (-not $Sidecar) { $Sidecar = $script:fullHash }
        Set-Content -Path (Join-Path $script:payload "$($script:name).sha256") -Value $Sidecar -NoNewline
    }

    It 'Join-ParkosFileParts concatena en el orden recibido (streaming)' {
        New-FakeParts
        $parts = 1..3 | ForEach-Object { Join-Path $script:payload ("{0}.part{1:D2}" -f $script:name, $_) }
        $dest = Join-Path $TestDrive "joined$($script:id).bin"
        Join-ParkosFileParts -PartPaths $parts -Destination $dest
        ([System.IO.File]::ReadAllBytes($dest) -join ',') | Should Be ($script:bytes -join ',')
    }

    It 'Get-ParkosPostgresPartsStatus ordena NUMERICAMENTE (part10 al final, no tras part1)' {
        foreach ($n in 1..10) { Set-Content (Join-Path $script:payload ("{0}.part{1:D2}" -f $script:name, $n)) 'x' }
        Set-Content (Join-Path $script:payload "$($script:name).sha256") 'h'
        $s = Get-ParkosPostgresPartsStatus -Dir $script:payload -FileName $script:name
        $s.Problem | Should Be $null
        @($s.Parts).Count | Should Be 10
        $s.Parts[2] | Should Match 'part03$'
        $s.Parts[9] | Should Match 'part10$'
    }

    It 'Get-ParkosPostgresPartsStatus detecta un hueco en la numeracion' {
        foreach ($n in 1, 2, 4) { Set-Content (Join-Path $script:payload ("{0}.part{1:D2}" -f $script:name, $n)) 'x' }
        Set-Content (Join-Path $script:payload "$($script:name).sha256") 'h'
        (Get-ParkosPostgresPartsStatus -Dir $script:payload -FileName $script:name).Problem | Should Match 'Falta la parte 03'
    }
    It 'sin partes devuelve lista vacia y sin problema' {
        $s = Get-ParkosPostgresPartsStatus -Dir $script:payload -FileName $script:name
        @($s.Parts).Count | Should Be 0
        $s.Problem | Should Be $null
    }

    It 'partes sin .sha256 es un problema explicito' {
        New-FakeParts
        Remove-Item (Join-Path $script:payload "$($script:name).sha256")
        (Get-ParkosPostgresPartsStatus -Dir $script:payload -FileName $script:name).Problem | Should Match 'sha256'
    }

    It 'rearma en el CACHE (nunca en el payload), verifica el hash y no descarga' {
        New-FakeParts
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        $r | Should Be (Join-Path $script:cache $script:name)
        ([System.IO.File]::ReadAllBytes($r) -join ',') | Should Be ($script:bytes -join ',')
        (Test-Path (Join-Path $script:payload $script:name)) | Should Be $false
        (Test-Path "$r.assembling") | Should Be $false
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 0 -Scope It
    }

    It 'las partes tienen precedencia sobre un cache viejo/distinto y sobre la descarga' {
        New-FakeParts
        New-Item -ItemType Directory -Force -Path $script:cache | Out-Null
        Set-Content (Join-Path $script:cache $script:name) 'cache viejo con otro contenido'
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        ([System.IO.File]::ReadAllBytes($r) -join ',') | Should Be ($script:bytes -join ',')
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 0 -Scope It
    }

    It 're-ejecucion idempotente: reutiliza el ZIP ya rearmado sin volver a unir' {
        New-FakeParts
        $first = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        # Sello de fecha antigua: si se volviera a unir, el archivo se reescribiria.
        $old = [datetime]::new(2001, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)
        (Get-Item $first).LastWriteTimeUtc = $old
        $second = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        $second | Should Be $first
        (Get-Item $second).LastWriteTimeUtc | Should Be $old
    }

    It 'un ZIP completo valido en el payload gana sobre las partes' {
        New-FakeParts
        $full = Join-Path $script:payload $script:name
        Set-Content $full 'zip completo'
        (Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet) | Should Be $full
    }

    It 'falta una parte: error claro, no se cae a la descarga' {
        New-FakeParts -Numbers @(1, 3)
        { Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet } | Should Throw 'Falta la parte 02'
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 0 -Scope It
    }

    It 'hash que no coincide: borra el rearmado, error claro y no descarga' {
        New-FakeParts -Sidecar ('0' * 64)
        { Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet } | Should Throw 'hash SHA-256'
        (Test-Path (Join-Path $script:cache $script:name)) | Should Be $false
        (Test-Path (Join-Path $script:cache "$($script:name).assembling")) | Should Be $false
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 0 -Scope It
    }

    It 'sin partes ni cache cae a la descarga (ultimo recurso)' {
        Mock Invoke-ParkosHttpDownload { Set-Content $OutFile 'data' }
        $r = Get-ParkosPostgresZip -CacheDir $script:cache -PayloadDir $script:payload -Logger $script:quiet
        $r | Should Be (Join-Path $script:cache $script:name)
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 1 -Scope It
    }
}

