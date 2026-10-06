# Tests de installer/shared/ParkosPayloadParts.ps1 (payload en partes: empaquetar,
# cortar en partes <= 90 MiB, restaurar con verificacion de hashes). Pester 3.4:
# Mock sin -ModuleName; todo `Should Throw` lleva substring de mensaje. Datos
# sinteticos pequenos en $TestDrive (nunca los 300 MB reales); el disco real se
# usa solo para archivos de pocos MB.

. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')

$script:quiet = { param($m) }

function New-RandomFile {
    param([string]$Path, [int]$Bytes)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    $b = New-Object byte[] $Bytes
    (New-Object System.Random 42).NextBytes($b)
    [System.IO.File]::WriteAllBytes($Path, $b)
}

function New-SampleDir {
    param([string]$Root)
    New-Item -ItemType Directory -Force -Path (Join-Path $Root 'sub\deep') | Out-Null
    Set-Content -Path (Join-Path $Root 'b.txt') -Value 'bravo'
    Set-Content -Path (Join-Path $Root 'a.txt') -Value 'alpha'
    Set-Content -Path (Join-Path $Root 'sub\deep\c.txt') -Value 'charlie'
}

Describe 'Pack-ParkosPayloadArtifact (archivo)' {
    It 'archivo pequeno: una parte con el mismo nombre y entrada en el manifest' {
        $src = Join-Path $TestDrive 'small\nssm.exe'; New-RandomFile -Path $src -Bytes 1000
        $parts = Join-Path $TestDrive 'small-parts'
        $e = Pack-ParkosPayloadArtifact -Source $src -Id 'nssm' -PartsDir $parts -Target 'nssm.exe' -SourceInfo 'third-party download' -Logger $script:quiet
        $e.partCount | Should Be 1
        $e.parts[0].name | Should Be 'nssm.exe'
        (Test-Path (Join-Path $parts 'nssm\nssm.exe')) | Should Be $true
        $e.sha256 | Should Be (Get-FileHash $src -Algorithm SHA256).Hash.ToLowerInvariant()
        $m = Get-ParkosPayloadManifest -PartsDir $parts
        $m.version | Should Be 1
        @($m.artifacts).Count | Should Be 1
        $m.artifacts[0].target | Should Be 'nssm.exe'
        $m.artifacts[0].source | Should Be 'third-party download'
    }

    It 'archivo grande: se corta en partes <= MaxPartBytes con nombres .part01..NN' {
        $src = Join-Path $TestDrive 'big\big.msi'; New-RandomFile -Path $src -Bytes (2500KB)
        $parts = Join-Path $TestDrive 'big-parts'
        $e = Pack-ParkosPayloadArtifact -Source $src -Id 'big' -PartsDir $parts -Target 'big.msi' -MaxPartBytes 1MB -Logger $script:quiet
        $e.partCount | Should Be 3
        $e.parts[0].name | Should Be 'big.msi.part01'
        $e.parts[2].name | Should Be 'big.msi.part03'
        foreach ($p in $e.parts) { ($p.size -le 1MB) | Should Be $true }
        ($e.parts[0].size + $e.parts[1].size + $e.parts[2].size) | Should Be (2500KB)
    }

    It 'un archivo exacto multiplo del maximo no deja una parte vacia' {
        $src = Join-Path $TestDrive 'mult\m.bin'; New-RandomFile -Path $src -Bytes (2MB)
        $parts = Join-Path $TestDrive 'mult-parts'
        $e = Pack-ParkosPayloadArtifact -Source $src -Id 'm' -PartsDir $parts -Target 'm.bin' -MaxPartBytes 1MB -Logger $script:quiet
        $e.partCount | Should Be 2
    }

    It 'rechaza un MaxPartBytes por encima del limite seguro de 95 MiB' {
        $src = Join-Path $TestDrive 'lim\x.bin'; New-RandomFile -Path $src -Bytes 100
        { Pack-ParkosPayloadArtifact -Source $src -Id 'x' -PartsDir (Join-Path $TestDrive 'lim-parts') -Target 'x.bin' -MaxPartBytes 96MB } | Should Throw '95 MiB'
    }

    It 'Assert-ParkosPartsFileSize rechaza (y borra) un archivo sobre el limite duro' {
        $f = Join-Path $TestDrive 'hard\h.bin'; New-RandomFile -Path $f -Bytes 2000
        $old = $script:ParkosPartsHardLimitBytes
        $script:ParkosPartsHardLimitBytes = 1000
        try {
            { Assert-ParkosPartsFileSize -Path $f } | Should Throw 'mayor de 95 MiB'
        } finally { $script:ParkosPartsHardLimitBytes = $old }
        (Test-Path $f) | Should Be $false
    }

    It 'sin cambios: no reescribe las partes (misma fecha de escritura)' {
        $src = Join-Path $TestDrive 'same\s.bin'; New-RandomFile -Path $src -Bytes (1500KB)
        $parts = Join-Path $TestDrive 'same-parts'
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 's' -PartsDir $parts -Target 's.bin' -MaxPartBytes 1MB -Logger $script:quiet)
        $p1 = Join-Path $parts 's\s.bin.part01'
        (Get-Item $p1).LastWriteTimeUtc = [datetime]::new(2001, 2, 3, 4, 5, 6, [System.DateTimeKind]::Utc)
        $before = (Get-Item $p1).LastWriteTimeUtc
        $e = Pack-ParkosPayloadArtifact -Source $src -Id 's' -PartsDir $parts -Target 's.bin' -MaxPartBytes 1MB -Logger $script:quiet
        (Get-Item $p1).LastWriteTimeUtc | Should Be $before
        $e.partCount | Should Be 2
    }

    It 'contenido distinto: reemplaza y elimina partes obsoletas del id' {
        $src = Join-Path $TestDrive 'chg\c.bin'; New-RandomFile -Path $src -Bytes (2500KB)
        $parts = Join-Path $TestDrive 'chg-parts'
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 'c' -PartsDir $parts -Target 'c.bin' -MaxPartBytes 1MB -Logger $script:quiet)
        New-RandomFile -Path $src -Bytes (1200KB)
        $e = Pack-ParkosPayloadArtifact -Source $src -Id 'c' -PartsDir $parts -Target 'c.bin' -MaxPartBytes 1MB -Logger $script:quiet
        $e.partCount | Should Be 2
        (Test-Path (Join-Path $parts 'c\c.bin.part03')) | Should Be $false
    }
}

Describe 'Pack/Restore (carpeta)' {
    It 'el zip es determinista: mismo contenido, mismo sha256' {
        $src = Join-Path $TestDrive 'det\src'; New-SampleDir -Root $src
        $e1 = Pack-ParkosPayloadArtifact -Source $src -Id 'd' -PartsDir (Join-Path $TestDrive 'det-p1') -Target 'd' -Logger $script:quiet
        Start-Sleep -Milliseconds 1100
        (Get-Item (Join-Path $src 'a.txt')).LastWriteTime = Get-Date
        $e2 = Pack-ParkosPayloadArtifact -Source $src -Id 'd' -PartsDir (Join-Path $TestDrive 'det-p2') -Target 'd' -Logger $script:quiet
        $e1.kind | Should Be 'dir'
        $e1.sha256 | Should Be $e2.sha256
    }

    It 'restaura la carpeta con el mismo contenido y es idempotente' {
        $src = Join-Path $TestDrive 'rt\src'; New-SampleDir -Root $src
        $parts = Join-Path $TestDrive 'rt-parts'
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 'ext' -PartsDir $parts -Target 'pg_partman\extension' -Logger $script:quiet)
        $root = Join-Path $TestDrive 'rt-payload'
        $log = [System.Collections.Generic.List[string]]::new()
        $logger = { param($m) $log.Add($m) }.GetNewClosure()
        $t = Restore-ParkosPayloadArtifact -Id 'ext' -PartsDir $parts -PayloadRoot $root -Logger $logger
        $t | Should Be (Join-Path $root 'pg_partman\extension')
        (Get-Content (Join-Path $t 'sub\deep\c.txt')) | Should Be 'charlie'
        (Get-Content (Join-Path $t 'a.txt')) | Should Be 'alpha'
        (Test-Path "$t.parts-sha256") | Should Be $true
        # segunda llamada: no-op
        (Get-Item (Join-Path $t 'a.txt')).LastWriteTimeUtc = [datetime]::new(2001, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)
        $log.Clear()
        [void](Restore-ParkosPayloadArtifact -Id 'ext' -PartsDir $parts -PayloadRoot $root -Logger $logger)
        (@($log | Where-Object { $_ -match 'ya restaurado' })).Count | Should Be 1
        (Get-Item (Join-Path $t 'a.txt')).LastWriteTimeUtc.Year | Should Be 2001
    }

    It 'si el destino cambio de contenido (marcador distinto) lo rehace' {
        $src = Join-Path $TestDrive 'redo\src'; New-SampleDir -Root $src
        $parts = Join-Path $TestDrive 'redo-parts'
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 'r' -PartsDir $parts -Target 'r' -Logger $script:quiet)
        $root = Join-Path $TestDrive 'redo-payload'
        $t = Restore-ParkosPayloadArtifact -Id 'r' -PartsDir $parts -PayloadRoot $root -Logger $script:quiet
        Set-Content "$t.parts-sha256" 'otro'
        Set-Content (Join-Path $t 'a.txt') 'roto'
        [void](Restore-ParkosPayloadArtifact -Id 'r' -PartsDir $parts -PayloadRoot $root -Logger $script:quiet)
        (Get-Content (Join-Path $t 'a.txt')) | Should Be 'alpha'
    }

    It 'Expand-ParkosPartsZip rechaza entradas fuera del destino (zip-slip)' {
        Add-Type -AssemblyName System.IO.Compression
        $zipPath = Join-Path $TestDrive 'slip.zip'
        $fs = [System.IO.File]::Create($zipPath)
        $z = New-Object System.IO.Compression.ZipArchive ($fs, [System.IO.Compression.ZipArchiveMode]::Create)
        $e = $z.CreateEntry('../evil.txt'); $w = New-Object System.IO.StreamWriter ($e.Open()); $w.Write('x'); $w.Dispose()
        $z.Dispose(); $fs.Dispose()
        { Expand-ParkosPartsZip -ZipPath $zipPath -Destination (Join-Path $TestDrive 'slip-out') } | Should Throw 'fuera del destino'
        (Test-Path (Join-Path $TestDrive 'evil.txt')) | Should Be $false
    }
}

Describe 'Restore-ParkosPayloadArtifact (archivo cortado)' {
    BeforeEach {
        $script:src = Join-Path $TestDrive 'rf\big.msi'
        New-RandomFile -Path $script:src -Bytes (2500KB)
        $script:parts = Join-Path $TestDrive "rf-parts-$([guid]::NewGuid().ToString('N'))"
        [void](Pack-ParkosPayloadArtifact -Source $script:src -Id 'big' -PartsDir $script:parts -Target 'big.msi' -MaxPartBytes 1MB -Logger $script:quiet)
        $script:root = Join-Path $TestDrive "rf-payload-$([guid]::NewGuid().ToString('N'))"
    }

    It 'une las partes y el resultado es byte a byte igual (hash)' {
        $t = Restore-ParkosPayloadArtifact -Id 'big' -PartsDir $script:parts -PayloadRoot $script:root -Logger $script:quiet
        (Get-FileHash $t -Algorithm SHA256).Hash | Should Be (Get-FileHash $script:src -Algorithm SHA256).Hash
        (Test-Path "$t.restoring") | Should Be $false
    }

    It 'falta una parte: error claro y no deja el destino' {
        Remove-Item (Join-Path $script:parts 'big\big.msi.part02')
        { Restore-ParkosPayloadArtifact -Id 'big' -PartsDir $script:parts -PayloadRoot $script:root -Logger $script:quiet } | Should Throw 'falta la parte big.msi.part02'
        (Test-Path (Join-Path $script:root 'big.msi')) | Should Be $false
    }

    It 'una parte danada (mismo tamano, otro contenido): error de hash y sin destino' {
        $p = Join-Path $script:parts 'big\big.msi.part01'
        $bytes = [System.IO.File]::ReadAllBytes($p); $bytes[10] = [byte](($bytes[10] + 1) % 256)
        [System.IO.File]::WriteAllBytes($p, $bytes)
        { Restore-ParkosPayloadArtifact -Id 'big' -PartsDir $script:parts -PayloadRoot $script:root -Logger $script:quiet } | Should Throw 'esta danada'
        (Test-Path (Join-Path $script:root 'big.msi')) | Should Be $false
        (Test-Path (Join-Path $script:root 'big.msi.restoring')) | Should Be $false
    }

    It 'una parte con tamano distinto: error de tamano' {
        Add-Content -Path (Join-Path $script:parts 'big\big.msi.part03') -Value 'extra'
        { Restore-ParkosPayloadArtifact -Id 'big' -PartsDir $script:parts -PayloadRoot $script:root -Logger $script:quiet } | Should Throw 'el manifest dice'
    }

    It 'id desconocido: error claro' {
        { Restore-ParkosPayloadArtifact -Id 'nada' -PartsDir $script:parts -PayloadRoot $script:root -Logger $script:quiet } | Should Throw "no esta en el manifest"
    }
}

Describe 'Restore-ParkosPayloadAll' {
    It 'restaura solo los que van a payload y registra Restaurando <id> n de m' {
        $parts = Join-Path $TestDrive 'all-parts'
        $a = Join-Path $TestDrive 'all\a.bin'; New-RandomFile -Path $a -Bytes 500
        $b = Join-Path $TestDrive 'all\b.bin'; New-RandomFile -Path $b -Bytes 600
        $c = Join-Path $TestDrive 'all\c.bin'; New-RandomFile -Path $c -Bytes 700
        [void](Pack-ParkosPayloadArtifact -Source $a -Id 'aa' -PartsDir $parts -Target 'a.bin' -Logger $script:quiet)
        [void](Pack-ParkosPayloadArtifact -Source $b -Id 'bb' -PartsDir $parts -Target 'b.bin' -Logger $script:quiet)
        [void](Pack-ParkosPayloadArtifact -Source $c -Id 'cc' -PartsDir $parts -Target 'c.bin' -NoRestoreToPayload -Logger $script:quiet)
        $root = Join-Path $TestDrive 'all-payload'
        $log = [System.Collections.Generic.List[string]]::new()
        $ids = @(Restore-ParkosPayloadAll -PartsDir $parts -PayloadRoot $root -Logger ({ param($m) $log.Add($m) }.GetNewClosure()))
        ($ids -join ',') | Should Be 'aa,bb'
        (@($log | Where-Object { $_ -eq 'Restaurando aa 1 de 2' })).Count | Should Be 1
        (@($log | Where-Object { $_ -eq 'Restaurando bb 2 de 2' })).Count | Should Be 1
        (Test-Path (Join-Path $root 'c.bin')) | Should Be $false
    }

    It '-Ids restaura el pedido (aunque no vaya a payload) y falla con un id inexistente' {
        $parts = Join-Path $TestDrive 'ids-parts'
        $c = Join-Path $TestDrive 'ids\c.bin'; New-RandomFile -Path $c -Bytes 700
        [void](Pack-ParkosPayloadArtifact -Source $c -Id 'cc' -PartsDir $parts -Target 'c.bin' -NoRestoreToPayload -Logger $script:quiet)
        $root = Join-Path $TestDrive 'ids-payload'
        [void](Restore-ParkosPayloadAll -PartsDir $parts -PayloadRoot $root -Ids @('cc') -Logger $script:quiet)
        (Test-Path (Join-Path $root 'c.bin')) | Should Be $true
        { Restore-ParkosPayloadAll -PartsDir $parts -PayloadRoot $root -Ids @('zz') -Logger $script:quiet } | Should Throw "'zz'"
    }

    It 'sin manifest: error claro' {
        { Restore-ParkosPayloadAll -PartsDir (Join-Path $TestDrive 'nada-parts') -PayloadRoot $TestDrive -Logger $script:quiet } | Should Throw 'no hay artefactos en partes'
    }
}

Describe 'Test-ParkosPayloadParts' {
    BeforeEach {
        $script:tp = Join-Path $TestDrive "tp-$([guid]::NewGuid().ToString('N'))"
        $f = Join-Path $TestDrive 'tpsrc\t.bin'; New-RandomFile -Path $f -Bytes (1500KB)
        [void](Pack-ParkosPayloadArtifact -Source $f -Id 't' -PartsDir $script:tp -Target 't.bin' -MaxPartBytes 1MB -Logger $script:quiet)
    }

    It 'partes consistentes: Ok' {
        $r = Test-ParkosPayloadParts -PartsDir $script:tp
        $r.Ok | Should Be $true
        @($r.Problems).Count | Should Be 0
    }
    It 'sin manifest: no Ok' {
        $r = Test-ParkosPayloadParts -PartsDir (Join-Path $TestDrive 'vacio-parts')
        $r.Ok | Should Be $false
    }
    It 'detecta parte faltante' {
        Remove-Item (Join-Path $script:tp 't\t.bin.part02')
        $r = Test-ParkosPayloadParts -PartsDir $script:tp
        $r.Ok | Should Be $false
        ($r.Problems -join ' ') | Should Match 'falta la parte t.bin.part02'
    }
    It 'detecta hash distinto con el mismo tamano y -SkipHash lo omite' {
        $p = Join-Path $script:tp 't\t.bin.part01'
        $bytes = [System.IO.File]::ReadAllBytes($p); $bytes[5] = [byte](($bytes[5] + 1) % 256)
        [System.IO.File]::WriteAllBytes($p, $bytes)
        (Test-ParkosPayloadParts -PartsDir $script:tp).Ok | Should Be $false
        (Test-ParkosPayloadParts -PartsDir $script:tp -SkipHash).Ok | Should Be $true
    }
    It 'detecta archivos desconocidos' {
        Set-Content (Join-Path $script:tp 't\sobra.txt') 'x'
        $r = Test-ParkosPayloadParts -PartsDir $script:tp
        $r.Ok | Should Be $false
        ($r.Problems -join ' ') | Should Match 'archivo desconocido'
    }
    It 'acepta el sidecar <archivo>.sha256 de un artefacto' {
        Set-Content (Join-Path $script:tp 't\t.bin.sha256') 'abc'
        (Test-ParkosPayloadParts -PartsDir $script:tp).Ok | Should Be $true
    }
}

Describe 'Register-ParkosPayloadExistingParts' {
    It 'registra partes existentes sin tocar sus bytes y verifica el hash esperado' {
        $parts = Join-Path $TestDrive 'reg-parts'
        $src = Join-Path $TestDrive 'reg\z.zip'; New-RandomFile -Path $src -Bytes (1500KB)
        $idDir = Join-Path $parts 'pg'
        [void](Split-ParkosPartsFile -Path $src -PartsDir $idDir -ArchiveName 'z.zip' -MaxPartBytes 1MB)
        $before = (Get-FileHash (Join-Path $idDir 'z.zip.part01') -Algorithm SHA256).Hash
        $sha = (Get-FileHash $src -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content (Join-Path $idDir 'z.zip.sha256') $sha
        $e = Register-ParkosPayloadExistingParts -Id 'pg' -PartsDir $parts -ArchiveName 'z.zip' -Target 'postgres\z.zip' -NoRestoreToPayload -Logger $script:quiet
        $e.sha256 | Should Be $sha
        $e.partCount | Should Be 2
        $e.restoreToPayload | Should Be $false
        (Get-FileHash (Join-Path $idDir 'z.zip.part01') -Algorithm SHA256).Hash | Should Be $before
        (Test-ParkosPayloadParts -PartsDir $parts).Ok | Should Be $true
    }
    It 'hash esperado distinto: no registra' {
        $parts = Join-Path $TestDrive 'reg2-parts'
        $src = Join-Path $TestDrive 'reg2\z.zip'; New-RandomFile -Path $src -Bytes (1500KB)
        [void](Split-ParkosPartsFile -Path $src -PartsDir (Join-Path $parts 'pg') -ArchiveName 'z.zip' -MaxPartBytes 1MB)
        { Register-ParkosPayloadExistingParts -Id 'pg' -PartsDir $parts -ArchiveName 'z.zip' -Target 'z.zip' -ExpectedSha256 ('0' * 64) -Logger $script:quiet } | Should Throw 'no se registran'
    }
}

Describe 'Get-ParkosPartsArtifactDecision (restaurar o construir)' {
    $third = [PSCustomObject]@{ id = 'nssm'; parts = @([PSCustomObject]@{ name = 'n' }); sourceDependent = $false }
    $svc = [PSCustomObject]@{ id = 'migrate'; parts = @([PSCustomObject]@{ name = 'n' }); sourceDependent = $true }

    It 'sin entrada o sin partes: construir' {
        Get-ParkosPartsArtifactDecision -Entry $null | Should Be 'build'
        Get-ParkosPartsArtifactDecision -Entry ([PSCustomObject]@{ id = 'x'; parts = @(); sourceDependent = $true }) | Should Be 'build'
    }
    It 'terceros: siempre restaurar aunque haya cambios' {
        Get-ParkosPartsArtifactDecision -Entry $third -ChangedFiles @('backend/a.py') | Should Be 'restore'
    }
    It 'servicio sin informacion de git: restaurar' {
        Get-ParkosPartsArtifactDecision -Entry $svc -ChangedFiles $null | Should Be 'restore'
    }
    It 'servicio sin cambios en backend/ ni installer/bootstrap/: restaurar' {
        Get-ParkosPartsArtifactDecision -Entry $svc -ChangedFiles @() | Should Be 'restore'
    }
    It 'servicio con cambios desde builtFromCommit: construir' {
        Get-ParkosPartsArtifactDecision -Entry $svc -ChangedFiles @('backend/x.py') | Should Be 'build'
    }
}

Describe 'Get-ParkosPartsChangedFiles' {
    It 'sin commit o sin repo: $null (no hay informacion de git)' {
        (Get-ParkosPartsChangedFiles -RepoRoot '' -Commit 'abc') | Should BeNullOrEmpty
        (Get-ParkosPartsChangedFiles -RepoRoot $TestDrive -Commit '') | Should BeNullOrEmpty
    }
}

Describe 'Get-ParkosPayloadArtifactTable' {
    It 'define terceros por defecto y servicios/MSI solo bajo pedido' {
        $t = Get-ParkosPayloadArtifactTable
        (@($t | Where-Object { $_.Default } | ForEach-Object { $_.Id }) -join ',') | Should Be 'postgres,powershell7-msi,nssm,pg_partman-extension'
        foreach ($id in 'web-sucursal-msi', 'api-sucursal', 'job-sync-sucursal', 'migrate', 'seed', 'doctor') {
            $row = $t | Where-Object { $_.Id -eq $id }
            $row.Default | Should Be $false
            $row.SourceDependent | Should Be $true
        }
        ($t | Where-Object { $_.Id -eq 'postgres' }).RestoreToPayload | Should Be $false
    }
}

Describe 'Invoke-ParkosPackPayload (tabla de artefactos)' {
    BeforeEach {
        $script:pl = Join-Path $TestDrive "pk-$([guid]::NewGuid().ToString('N'))"
        $script:pp = Join-Path $script:pl 'parts'
        New-RandomFile -Path (Join-Path $script:pl 'tool.exe') -Bytes 800
        New-SampleDir -Root (Join-Path $script:pl 'ext')
        New-RandomFile -Path (Join-Path $script:pl 'apps\app-9.9.9-x64.msi') -Bytes 900
        $script:tbl = @(
            [PSCustomObject]@{ Id = 'tool'; Path = 'tool.exe'; Kind = 'file'; Default = $true; SourceDependent = $false; RestoreToPayload = $true; Source = 'third-party download' }
            [PSCustomObject]@{ Id = 'ext'; Path = 'ext'; Kind = 'dir'; Default = $true; SourceDependent = $false; RestoreToPayload = $true; Source = 'third-party download' }
            [PSCustomObject]@{ Id = 'faltante'; Path = 'nada.exe'; Kind = 'file'; Default = $true; SourceDependent = $false; RestoreToPayload = $true; Source = 'x' }
            [PSCustomObject]@{ Id = 'web'; Path = 'apps\app-*-x64.msi'; Kind = 'file'; Default = $false; SourceDependent = $true; RestoreToPayload = $true; Source = 'built' }
        )
    }

    It 'sin -Ids empaqueta solo los Default presentes y omite los ausentes' {
        $ids = @(Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $script:tbl -Logger $script:quiet)
        ($ids -join ',') | Should Be 'tool,ext'
        (Find-ParkosPayloadEntry -PartsDir $script:pp -Id 'web') | Should BeNullOrEmpty
        # una carpeta se empaqueta como carpeta (no como su ultimo archivo)
        (Find-ParkosPayloadEntry -PartsDir $script:pp -Id 'ext').kind | Should Be 'dir'
        (Find-ParkosPayloadEntry -PartsDir $script:pp -Id 'ext').target | Should Be 'ext'
        (Test-ParkosPayloadParts -PartsDir $script:pp).Ok | Should Be $true
    }

    It '-Ids pide un artefacto de comodin y registra el nombre real y sourceDependent' {
        $ids = @(Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $script:tbl -Ids @('web') -Logger $script:quiet)
        ($ids -join ',') | Should Be 'web'
        $e = Find-ParkosPayloadEntry -PartsDir $script:pp -Id 'web'
        $e.target | Should Be 'apps\app-9.9.9-x64.msi'
        $e.sourceDependent | Should Be $true
    }

    It '-Ids con un artefacto ausente del payload falla con mensaje claro' {
        { Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $script:tbl -Ids @('faltante') -Logger $script:quiet } | Should Throw 'no se puede empaquetar'
    }

    It '-Ids con un id fuera de la tabla falla' {
        { Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $script:tbl -Ids @('zzz') -Logger $script:quiet } | Should Throw 'no esta en la tabla'
    }

    It 'ZIP crudo ausente pero partes presentes sin registrar: las registra sin cambiar sus bytes' {
        $src = Join-Path $TestDrive 'regsrc\pg.zip'; New-RandomFile -Path $src -Bytes (1500KB)
        $idDir = Join-Path $script:pp 'pgx'
        [void](Split-ParkosPartsFile -Path $src -PartsDir $idDir -ArchiveName 'pg.zip' -MaxPartBytes 1MB)
        $tbl = @([PSCustomObject]@{ Id = 'pgx'; Path = 'postgres\pg.zip'; Kind = 'file'; Default = $true; SourceDependent = $false; RestoreToPayload = $false; Source = 'third-party download' })
        $ids = @(Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $tbl -Logger $script:quiet)
        ($ids -join ',') | Should Be 'pgx'
        (Find-ParkosPayloadEntry -PartsDir $script:pp -Id 'pgx').restoreToPayload | Should Be $false
    }

    It 'ya registrado en partes y sin copia cruda: se deja tal cual (tambien con -Ids)' {
        $src = Join-Path $TestDrive 'regsrc2\pg.zip'; New-RandomFile -Path $src -Bytes (1500KB)
        [void](Split-ParkosPartsFile -Path $src -PartsDir (Join-Path $script:pp 'pgy') -ArchiveName 'pg.zip' -MaxPartBytes 1MB)
        $tbl = @([PSCustomObject]@{ Id = 'pgy'; Path = 'postgres\pg.zip'; Kind = 'file'; Default = $true; SourceDependent = $false; RestoreToPayload = $false; Source = 'x' })
        [void](Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $tbl -Logger $script:quiet)
        $ids = @(Invoke-ParkosPackPayload -PayloadRoot $script:pl -PartsDir $script:pp -Table $tbl -Ids @('pgy') -Logger $script:quiet)
        ($ids -join ',') | Should Be 'pgy'
    }
}
