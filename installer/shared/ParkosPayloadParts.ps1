# Payload en partes: empaqueta (zip + corte en partes <= 90 MiB) y restaura
# (une por streaming, verifica hashes, expande) los artefactos del payload que
# viajan versionados en git. COMPARTIDO por el instalador completo
# (installer/parkos-installer.ps1, installer/build-release.ps1) y el lite.
#
# Por que: GitHub rechaza cualquier archivo > 100 MB. Todo artefacto grande
# (MSI, servicios congelados, binarios de terceros) se versiona como partes en
# installer\payload\parts\<id>\<archivo>.partNN + el manifest
# installer\payload\parts\payload-parts.json, y se rearma al instalar.
#
# Reglas de este archivo (para poder dot-sourcearlo desde cualquier sitio):
#   - Sin StrictMode, sin param() de script, sin efectos al cargar: solo
#     define funciones. Sin elevacion.
#   - Todo directorio llega por parametro; el log llega como scriptblock
#     (-Logger, recibe UN string).
#   - Toda operacion de disco pesada (hash, zip, corte, union) esta en un
#     wrapper propio (Get-ParkosPartsFileSha256, New-ParkosPartsZip,
#     Expand-ParkosPartsZip, Split-ParkosPartsFile, Join-ParkosPartsFile,
#     Get-ParkosPartsGitCommit, Get-ParkosPartsChangedFiles) para mockearlo.
#   - Compatible con Windows PowerShell 5.1 y pwsh 7 (sin ternario, sin ?.).
#
# Funciones publicas:
#   Get-ParkosPayloadManifest        -PartsDir
#   Get-ParkosPayloadArtifactTable
#   Pack-ParkosPayloadArtifact       -Source -Id -PartsDir -Target [-Kind] [-MaxPartBytes] [-SourceInfo] [-Note]
#                                    [-RepoRoot] [-SourceDependent] [-NoRestoreToPayload] [-Force] [-Logger]
#   Register-ParkosPayloadExistingParts -Id -PartsDir -ArchiveName -Target [-ExpectedSha256] ...
#   Restore-ParkosPayloadArtifact    -Id -PartsDir -PayloadRoot [-CacheDir] [-Force] [-Logger]
#   Restore-ParkosPayloadAll         -PartsDir -PayloadRoot [-Ids] [-CacheDir] [-Force] [-Logger]
#   Test-ParkosPayloadParts          -PartsDir [-SkipHash]   -> { Ok; Problems }
#   Get-ParkosPartsArtifactDecision  -Entry [-ChangedFiles]  -> 'restore' | 'build'
#   Get-ParkosPartsChangedFiles      -RepoRoot -Commit

$script:ParkosPartsMaxPartBytes = 90MB
$script:ParkosPartsHardLimitBytes = 95MB
$script:ParkosPartsManifestName = 'payload-parts.json'

function Write-ParkosPartsLog {
    param([scriptblock]$Logger, [string]$Message)
    if ($Logger) { & $Logger $Message } else { Write-Host $Message }
}

# Lee una propiedad opcional de un objeto del manifest (StrictMode-safe).
function Get-ParkosPartsProp {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    return $p.Value
}

# ---------------------------------------------------------------------------
# Wrappers mockeables (disco, zip, hash, git)
# ---------------------------------------------------------------------------

function ConvertTo-ParkosPartsHex {
    param([byte[]]$Bytes)
    return ([System.BitConverter]::ToString($Bytes) -replace '-', '').ToLowerInvariant()
}

# SHA-256 (minusculas) por streaming; nunca carga el archivo en memoria.
function Get-ParkosPartsFileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $in = [System.IO.File]::OpenRead($Path)
    try {
        return (ConvertTo-ParkosPartsHex -Bytes $sha.ComputeHash($in))
    } finally {
        $in.Dispose()
        $sha.Dispose()
    }
}

function Get-ParkosPartsGitCommit {
    param([string]$RepoRoot)
    if (-not $RepoRoot) { return '' }
    try {
        $c = @(& git -C $RepoRoot rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -ne 0 -or $c.Count -eq 0) { return '' }
        return ([string]$c[0]).Trim()
    } catch {
        return ''
    }
}

# Archivos bajo backend/ e installer/bootstrap/ cambiados desde <Commit>
# (diff contra el arbol de trabajo + no rastreados). $null si no se puede saber.
function Get-ParkosPartsChangedFiles {
    param([string]$RepoRoot, [string]$Commit)
    if (-not $RepoRoot -or -not $Commit) { return $null }
    try {
        $diff = @(& git -C $RepoRoot diff --name-only $Commit -- backend installer/bootstrap 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        $new = @(& git -C $RepoRoot ls-files -o --exclude-standard -- backend installer/bootstrap 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        return @(@($diff) + @($new) | Where-Object { $_ -and $_.Trim() })
    } catch {
        return $null
    }
}

# Zip determinista de una carpeta: entradas en orden ordinal, '/' como
# separador, fecha fija (2020-01-01) y compresion Optimal. Devuelve los bytes
# sin comprimir.
function New-ParkosPartsZip {
    param([Parameter(Mandatory)][string]$SourceDir, [Parameter(Mandatory)][string]$ZipPath)

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root = (Resolve-Path -LiteralPath $SourceDir).Path.TrimEnd('\')
    $names = [System.Collections.Generic.List[string]]::new()
    foreach ($f in Get-ChildItem -LiteralPath $root -Recurse -File -Force) {
        $names.Add($f.FullName.Substring($root.Length + 1).Replace('\', '/'))
    }
    $arr = $names.ToArray()
    [Array]::Sort($arr, [System.StringComparer]::Ordinal)

    $fixedDate = [System.DateTimeOffset]::new(2020, 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    $total = 0L
    $fs = [System.IO.File]::Open($ZipPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    try {
        $zip = New-Object System.IO.Compression.ZipArchive ($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)
        try {
            foreach ($name in $arr) {
                $full = Join-Path $root $name.Replace('/', '\')
                $entry = $zip.CreateEntry($name, [System.IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = $fixedDate
                $es = $entry.Open()
                $in = [System.IO.File]::OpenRead($full)
                try {
                    $in.CopyTo($es, 81920)
                    $total += $in.Length
                } finally {
                    $in.Dispose()
                    $es.Dispose()
                }
            }
        } finally { $zip.Dispose() }
    } finally { $fs.Dispose() }
    return $total
}

# Expande un zip validando cada ruta (zip-slip): una entrada que resuelva fuera
# de <Destination> aborta. No conserva las fechas del zip (los archivos quedan
# con la fecha de la restauracion: asi no parecen "viejos" frente al codigo).
function Expand-ParkosPartsZip {
    param([Parameter(Mandatory)][string]$ZipPath, [Parameter(Mandatory)][string]$Destination)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $destFull = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            $target = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($Destination, $name.Replace('/', '\')))
            if (-not $target.StartsWith($destFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "El archivo comprimido contiene una ruta fuera del destino ($name): se aborta la restauracion."
            }
            if ($name.EndsWith('/')) {
                New-Item -ItemType Directory -Force -Path $target | Out-Null
                continue
            }
            New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
            $in = $entry.Open()
            $out = [System.IO.File]::Open($target, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
            try { $in.CopyTo($out, 81920) } finally { $out.Dispose(); $in.Dispose() }
        }
    } finally { $zip.Dispose() }
}

# Corta <Path> en <ArchiveName>.part01..NN dentro de <PartsDir> (cada parte
# <= MaxPartBytes) por streaming. Devuelve las rutas de las partes en orden.
function Split-ParkosPartsFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$PartsDir,
        [Parameter(Mandatory)][string]$ArchiveName,
        [Parameter(Mandatory)][long]$MaxPartBytes
    )

    New-Item -ItemType Directory -Force -Path $PartsDir | Out-Null
    $buffer = New-Object byte[] (4MB)
    $paths = [System.Collections.Generic.List[string]]::new()
    $in = [System.IO.File]::OpenRead($Path)
    try {
        $out = $null
        $inPart = 0L
        try {
            while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $offset = 0
                while ($read -gt 0) {
                    if ($null -eq $out -or $inPart -ge $MaxPartBytes) {
                        if ($null -ne $out) { $out.Dispose() }
                        $p = Join-Path $PartsDir ('{0}.part{1:D2}' -f $ArchiveName, ($paths.Count + 1))
                        $paths.Add($p)
                        $out = [System.IO.File]::Open($p, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
                        $inPart = 0L
                    }
                    $n = [int][math]::Min([long]$read, $MaxPartBytes - $inPart)
                    $out.Write($buffer, $offset, $n)
                    $offset += $n; $read -= $n; $inPart += $n
                }
            }
        } finally { if ($null -ne $out) { $out.Dispose() } }
    } finally { $in.Dispose() }
    return @($paths)
}

# Une las partes (en el orden dado) en <Destination> por streaming (buffer 4 MB)
# y calcula en la misma pasada el SHA-256 de cada parte y del total.
function Join-ParkosPartsFile {
    param([Parameter(Mandatory)][string[]]$PartPaths, [Parameter(Mandatory)][string]$Destination)

    $buffer = New-Object byte[] (4MB)
    $empty = New-Object byte[] 0
    $total = [System.Security.Cryptography.SHA256]::Create()
    $partHashes = [System.Collections.Generic.List[string]]::new()
    $size = 0L
    $out = [System.IO.File]::Open($Destination, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        foreach ($part in $PartPaths) {
            $ph = [System.Security.Cryptography.SHA256]::Create()
            $in = [System.IO.File]::OpenRead($part)
            try {
                while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $out.Write($buffer, 0, $read)
                    [void]$ph.TransformBlock($buffer, 0, $read, $null, 0)
                    [void]$total.TransformBlock($buffer, 0, $read, $null, 0)
                    $size += $read
                }
            } finally { $in.Dispose() }
            [void]$ph.TransformFinalBlock($empty, 0, 0)
            $partHashes.Add((ConvertTo-ParkosPartsHex -Bytes $ph.Hash))
            $ph.Dispose()
        }
        [void]$total.TransformFinalBlock($empty, 0, 0)
    } finally { $out.Dispose() }
    $result = [PSCustomObject]@{ PartHashes = @($partHashes); TotalHash = (ConvertTo-ParkosPartsHex -Bytes $total.Hash); TotalSize = $size }
    $total.Dispose()
    return $result
}

# Hash del archivo resultante de unir las partes, sin escribirlo a disco.
function Get-ParkosPartsJoinedSha256 {
    param([Parameter(Mandatory)][string[]]$PartPaths)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $buffer = New-Object byte[] (4MB)
    try {
        foreach ($part in $PartPaths) {
            $in = [System.IO.File]::OpenRead($part)
            try {
                while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) { [void]$sha.TransformBlock($buffer, 0, $read, $null, 0) }
            } finally { $in.Dispose() }
        }
        [void]$sha.TransformFinalBlock((New-Object byte[] 0), 0, 0)
        return (ConvertTo-ParkosPartsHex -Bytes $sha.Hash)
    } finally { $sha.Dispose() }
}

# Seguridad: ningun archivo bajo parts\ puede superar el limite duro (GitHub
# rechaza > 100 MB; aqui se corta en 95 MiB para dejar margen).
function Assert-ParkosPartsFileSize {
    param([Parameter(Mandatory)][string]$Path)
    $len = (Get-Item -LiteralPath $Path).Length
    if ($len -gt $script:ParkosPartsHardLimitBytes) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        throw "Se rechaza escribir $Path en parts\ por ser mayor de 95 MiB ($len bytes): GitHub rechaza archivos de mas de 100 MB. Use un -MaxPartBytes menor."
    }
}

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

function Get-ParkosPayloadManifest {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$PartsDir)

    $path = Join-Path $PartsDir $script:ParkosPartsManifestName
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try {
        $m = [System.IO.File]::ReadAllText($path) | ConvertFrom-Json
    } catch {
        throw "El manifest de partes ($path) no es un JSON valido: $($_.Exception.Message)"
    }
    return $m
}

function Get-ParkosPayloadManifestEntries {
    param($Manifest)
    if ($null -eq $Manifest) { return @() }
    return @(Get-ParkosPartsProp -Object $Manifest -Name 'artifacts' -Default @())
}

function Save-ParkosPayloadManifest {
    param([Parameter(Mandatory)][string]$PartsDir, [Parameter(Mandatory)][object[]]$Entries)

    New-Item -ItemType Directory -Force -Path $PartsDir | Out-Null
    $sorted = @($Entries | Sort-Object { $_.id })
    $manifest = [ordered]@{
        version          = 1
        generator        = 'installer/shared/ParkosPayloadParts.ps1'
        maxPartBytes     = [long]$script:ParkosPartsMaxPartBytes
        artifacts        = $sorted
    }
    $json = ConvertTo-Json -InputObject $manifest -Depth 8
    $json = ($json -replace "`r`n", "`n").TrimEnd() + "`n"
    [System.IO.File]::WriteAllText((Join-Path $PartsDir $script:ParkosPartsManifestName), $json, (New-Object System.Text.UTF8Encoding($false)))
}

# Tabla declarativa de artefactos conocidos: Path relativo al payload (puede
# llevar comodin), Kind, Default = se empaqueta sin -Ids, SourceDependent = su
# contenido sale del codigo de backend/ o installer/bootstrap/ (se reconstruye
# si el codigo cambio), RestoreToPayload = Restore-All lo deja en payload\.
function Get-ParkosPayloadArtifactTable {
    $rows = @(
        @('postgres', 'postgres\postgresql-16.15-1-windows-x64-binaries.zip', 'file', $true, $false, $false, 'third-party download (EnterpriseDB)'),
        @('powershell7-msi', 'PowerShell-7.4.6-win-x64.msi', 'file', $true, $false, $true, 'third-party download (PowerShell GitHub release)'),
        @('nssm', 'nssm.exe', 'file', $true, $false, $true, 'third-party download (nssm 2.24)'),
        @('pg_partman-extension', 'pg_partman\extension', 'dir', $true, $false, $true, 'third-party download (pg_partman 5.1.0 SQL-only)'),
        @('web-sucursal-msi', 'apps\web_sucursal-*-x64.msi', 'file', $false, $true, $true, 'built from apps/electron-sucursal'),
        @('api-sucursal', 'services\api-sucursal', 'dir', $false, $true, $true, 'built from backend (PyInstaller onedir)'),
        @('job-sync-sucursal', 'services\job-sync-sucursal', 'dir', $false, $true, $true, 'built from backend (PyInstaller onedir)'),
        @('migrate', 'services\migrate', 'dir', $false, $true, $true, 'built from backend (PyInstaller onedir)'),
        @('seed', 'services\seed', 'dir', $false, $true, $true, 'built from backend (PyInstaller onedir)'),
        @('doctor', 'services\doctor', 'dir', $false, $true, $true, 'built from backend (PyInstaller onedir)')
    )
    return @($rows | ForEach-Object {
            [PSCustomObject]@{
                Id               = $_[0]
                Path             = $_[1]
                Kind             = $_[2]
                Default          = [bool]$_[3]
                SourceDependent  = [bool]$_[4]
                RestoreToPayload = [bool]$_[5]
                Source           = $_[6]
            }
        })
}

function New-ParkosPartsEntry {
    param(
        [string]$Id, [string]$Kind, [string]$Target, [string]$ArchiveName,
        [long]$UncompressedSize, [long]$ArchiveSize, [string]$Sha256,
        [string[]]$PartNames, [string[]]$PartHashes, [long[]]$PartSizes,
        [string]$Commit, [string]$SourceInfo, [string]$Note,
        [bool]$SourceDependent, [bool]$RestoreToPayload
    )
    $parts = @()
    for ($i = 0; $i -lt $PartNames.Count; $i++) {
        $parts += [ordered]@{ name = $PartNames[$i]; size = $PartSizes[$i]; sha256 = $PartHashes[$i] }
    }
    return [PSCustomObject][ordered]@{
        id               = $Id
        kind             = $Kind
        target           = $Target
        archive          = $ArchiveName
        uncompressedSize = $UncompressedSize
        archiveSize      = $ArchiveSize
        sha256           = $Sha256
        partCount        = $PartNames.Count
        parts            = @($parts)
        builtFromCommit  = $Commit
        packedAtUtc      = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        source           = $SourceInfo
        note             = $Note
        sourceDependent  = $SourceDependent
        restoreToPayload = $RestoreToPayload
    }
}

function Set-ParkosPayloadManifestEntry {
    param([Parameter(Mandatory)][string]$PartsDir, [Parameter(Mandatory)]$Entry)
    $current = @(Get-ParkosPayloadManifestEntries -Manifest (Get-ParkosPayloadManifest -PartsDir $PartsDir) | Where-Object { $_.id -ne $Entry.id })
    Save-ParkosPayloadManifest -PartsDir $PartsDir -Entries (@($current) + @($Entry))
}

function Find-ParkosPayloadEntry {
    param([Parameter(Mandatory)][string]$PartsDir, [Parameter(Mandatory)][string]$Id)
    $m = Get-ParkosPayloadManifest -PartsDir $PartsDir
    return (Get-ParkosPayloadManifestEntries -Manifest $m | Where-Object { $_.id -eq $Id } | Select-Object -First 1)
}

# ---------------------------------------------------------------------------
# Empaquetar
# ---------------------------------------------------------------------------

# Empaqueta <Source> (archivo o carpeta) en <PartsDir>\<Id>\ y registra la
# entrada en el manifest. Si el contenido (sha256 del archivo final) no cambio y
# las partes siguen en su sitio, no reescribe nada (sin ruido en git).
function Pack-ParkosPayloadArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$PartsDir,
        [Parameter(Mandatory)][string]$Target,
        [long]$MaxPartBytes = $script:ParkosPartsMaxPartBytes,
        [string]$SourceInfo = '',
        [string]$Note = '',
        [string]$RepoRoot = '',
        [switch]$SourceDependent,
        [switch]$NoRestoreToPayload,
        [switch]$Force,
        [scriptblock]$Logger
    )

    if ($MaxPartBytes -gt $script:ParkosPartsHardLimitBytes) {
        throw "MaxPartBytes ($MaxPartBytes) supera el limite seguro de 95 MiB: GitHub rechaza archivos de mas de 100 MB."
    }
    if ($MaxPartBytes -lt 1MB) { throw "MaxPartBytes ($MaxPartBytes) es demasiado pequeno (minimo 1 MiB)." }
    if (-not (Test-Path -LiteralPath $Source)) { throw "No existe el origen a empaquetar para '$Id': $Source" }

    $isDir = (Get-Item -LiteralPath $Source).PSIsContainer
    $kind = 'file'
    if ($isDir) { $kind = 'dir' }
    $tmpZip = $null
    try {
        if ($isDir) {
            $archiveName = "$Id.zip"
            $tmpZip = Join-Path ([System.IO.Path]::GetTempPath()) "parkos-pack-$Id-$([guid]::NewGuid().ToString('N')).zip"
            Write-ParkosPartsLog $Logger "Empaquetando '$Id' (carpeta -> zip)..."
            $uncompressed = [long](New-ParkosPartsZip -SourceDir $Source -ZipPath $tmpZip)
            $archivePath = $tmpZip
        } else {
            $archiveName = (Get-Item -LiteralPath $Source).Name
            $archivePath = $Source
            $uncompressed = (Get-Item -LiteralPath $Source).Length
        }
        $archiveSize = (Get-Item -LiteralPath $archivePath).Length
        $sha = Get-ParkosPartsFileSha256 -Path $archivePath

        $idDir = Join-Path $PartsDir $Id
        $existing = Find-ParkosPayloadEntry -PartsDir $PartsDir -Id $Id
        if ($existing -and -not $Force -and $existing.sha256 -eq $sha -and $existing.archive -eq $archiveName) {
            $intact = $true
            foreach ($p in @($existing.parts)) {
                $pp = Join-Path $idDir $p.name
                if (-not (Test-Path -LiteralPath $pp -PathType Leaf) -or (Get-Item -LiteralPath $pp).Length -ne $p.size) { $intact = $false }
            }
            if ($intact) {
                Write-ParkosPartsLog $Logger "'$Id' sin cambios (sha256 $sha): se dejan las partes existentes."
                return $existing
            }
        }

        # Contenido nuevo (o partes danadas): se reemplazan todas las partes del id.
        if (Test-Path -LiteralPath $idDir) { Remove-Item -LiteralPath $idDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $idDir | Out-Null

        if ($archiveSize -le $MaxPartBytes) {
            $dest = Join-Path $idDir $archiveName
            Copy-Item -LiteralPath $archivePath -Destination $dest -Force
            $partPaths = @($dest)
        } else {
            Write-ParkosPartsLog $Logger "Cortando '$archiveName' ($([math]::Round($archiveSize / 1MB, 1)) MB) en partes de <= $([math]::Round($MaxPartBytes / 1MB, 1)) MB..."
            $partPaths = @(Split-ParkosPartsFile -Path $archivePath -PartsDir $idDir -ArchiveName $archiveName -MaxPartBytes $MaxPartBytes)
        }
        foreach ($pp in $partPaths) { Assert-ParkosPartsFileSize -Path $pp }

        $names = @($partPaths | ForEach-Object { Split-Path $_ -Leaf })
        $sizes = @($partPaths | ForEach-Object { (Get-Item -LiteralPath $_).Length })
        $hashes = @($partPaths | ForEach-Object { Get-ParkosPartsFileSha256 -Path $_ })
        $entry = New-ParkosPartsEntry -Id $Id -Kind $kind -Target $Target -ArchiveName $archiveName `
            -UncompressedSize $uncompressed -ArchiveSize $archiveSize -Sha256 $sha `
            -PartNames $names -PartHashes $hashes -PartSizes $sizes `
            -Commit (Get-ParkosPartsGitCommit -RepoRoot $RepoRoot) -SourceInfo $SourceInfo -Note $Note `
            -SourceDependent ([bool]$SourceDependent) -RestoreToPayload (-not [bool]$NoRestoreToPayload)
        Set-ParkosPayloadManifestEntry -PartsDir $PartsDir -Entry $entry
        Write-ParkosPartsLog $Logger "'$Id' empaquetado en $($names.Count) parte(s), sha256 $sha."
        return $entry
    } finally {
        if ($tmpZip -and (Test-Path -LiteralPath $tmpZip)) { Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue }
    }
}

# Registra en el manifest partes que YA existen en <PartsDir>\<Id>\ (p. ej. las
# de Postgres migradas desde payload\postgres) sin tocar sus bytes. El hash del
# archivo unido se verifica contra -ExpectedSha256 (o el sidecar
# <ArchiveName>.sha256 si existe).
function Register-ParkosPayloadExistingParts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$PartsDir,
        [Parameter(Mandatory)][string]$ArchiveName,
        [Parameter(Mandatory)][string]$Target,
        [string]$ExpectedSha256 = '',
        [string]$Kind = 'file',
        [string]$SourceInfo = '',
        [string]$Note = '',
        [string]$RepoRoot = '',
        [switch]$NoRestoreToPayload,
        [scriptblock]$Logger
    )

    $idDir = Join-Path $PartsDir $Id
    $partFiles = @(Get-ChildItem -LiteralPath $idDir -File -Filter "$ArchiveName.part*" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '\.part\d+$' } | Sort-Object Name)
    if ($partFiles.Count -eq 0) { throw "No hay partes de '$ArchiveName' en $idDir para registrar." }
    for ($i = 0; $i -lt $partFiles.Count; $i++) {
        if ($partFiles[$i].Name -ne ('{0}.part{1:D2}' -f $ArchiveName, ($i + 1))) {
            throw "Las partes de $ArchiveName en $idDir no son contiguas (se esperaba la parte $('{0:D2}' -f ($i + 1)), hay $($partFiles[$i].Name))."
        }
    }
    $paths = @($partFiles | ForEach-Object { $_.FullName })
    $sidecar = Join-Path $idDir "$ArchiveName.sha256"
    if (-not $ExpectedSha256 -and (Test-Path -LiteralPath $sidecar)) {
        $ExpectedSha256 = (([System.IO.File]::ReadAllText($sidecar)).Trim() -split '\s+')[0]
    }
    $sha = Get-ParkosPartsJoinedSha256 -PartPaths $paths
    if ($ExpectedSha256 -and $sha -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "Las partes de $ArchiveName unidas tienen sha256 $sha y se esperaba ${ExpectedSha256}: no se registran."
    }
    foreach ($p in $paths) { Assert-ParkosPartsFileSize -Path $p }
    $sizes = @($paths | ForEach-Object { (Get-Item -LiteralPath $_).Length })
    $total = [long]0
    foreach ($s in $sizes) { $total += $s }
    $entry = New-ParkosPartsEntry -Id $Id -Kind $Kind -Target $Target -ArchiveName $ArchiveName `
        -UncompressedSize $total -ArchiveSize $total -Sha256 $sha `
        -PartNames @($partFiles | ForEach-Object { $_.Name }) -PartHashes @($paths | ForEach-Object { Get-ParkosPartsFileSha256 -Path $_ }) -PartSizes $sizes `
        -Commit (Get-ParkosPartsGitCommit -RepoRoot $RepoRoot) -SourceInfo $SourceInfo -Note $Note `
        -SourceDependent $false -RestoreToPayload (-not [bool]$NoRestoreToPayload)
    Set-ParkosPayloadManifestEntry -PartsDir $PartsDir -Entry $entry
    Write-ParkosPartsLog $Logger "'$Id' registrado en el manifest ($($paths.Count) partes existentes, sha256 $sha)."
    return $entry
}

# ---------------------------------------------------------------------------
# Restaurar
# ---------------------------------------------------------------------------

function Get-ParkosPartsEntryPaths {
    param([Parameter(Mandatory)]$Entry, [Parameter(Mandatory)][string]$PartsDir)
    $idDir = Join-Path $PartsDir $Entry.id
    return @(@($Entry.parts) | ForEach-Object { Join-Path $idDir $_.name })
}

# Problemas (texto) de las partes de una entrada: falta, tamano, sin hash.
function Get-ParkosPartsEntryProblems {
    param([Parameter(Mandatory)]$Entry, [Parameter(Mandatory)][string]$PartsDir, [switch]$SkipHash)
    $problems = [System.Collections.Generic.List[string]]::new()
    $idDir = Join-Path $PartsDir $Entry.id
    foreach ($p in @($Entry.parts)) {
        $path = Join-Path $idDir $p.name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $problems.Add("falta la parte $($p.name) de '$($Entry.id)' en $idDir")
            continue
        }
        $len = (Get-Item -LiteralPath $path).Length
        if ($len -ne $p.size) { $problems.Add("la parte $($p.name) de '$($Entry.id)' pesa $len bytes y el manifest dice $($p.size)"); continue }
        if ($len -gt $script:ParkosPartsMaxPartBytes) { $problems.Add("la parte $($p.name) de '$($Entry.id)' supera 90 MiB ($len bytes)") }
        if (-not $SkipHash) {
            $h = Get-ParkosPartsFileSha256 -Path $path
            if ($h -ne $p.sha256) { $problems.Add("la parte $($p.name) de '$($Entry.id)' tiene hash $h y el manifest dice $($p.sha256)") }
        }
    }
    return @($problems)
}

# Restaura un artefacto a <PayloadRoot>\<target>. Idempotente: si el marcador
# <target>.parts-sha256 coincide con el sha256 del manifest y el destino existe,
# no hace nada. Verifica tamano/hash de cada parte y el sha256 final; nunca
# continua en silencio ante una parte faltante o danada.
function Restore-ParkosPayloadArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$PartsDir,
        [Parameter(Mandatory)][string]$PayloadRoot,
        [string]$CacheDir = '',
        [switch]$Force,
        [scriptblock]$Logger
    )

    $entry = Find-ParkosPayloadEntry -PartsDir $PartsDir -Id $Id
    if (-not $entry) { throw "El artefacto '$Id' no esta en el manifest de partes ($(Join-Path $PartsDir $script:ParkosPartsManifestName))." }

    $target = Join-Path $PayloadRoot $entry.target
    $marker = "$target.parts-sha256"
    if (-not $Force -and (Test-Path -LiteralPath $marker -PathType Leaf) -and (Test-Path -LiteralPath $target)) {
        $okSize = $true
        if ($entry.kind -eq 'file') { $okSize = ((Get-Item -LiteralPath $target).Length -eq $entry.uncompressedSize) }
        if ($okSize -and ([System.IO.File]::ReadAllText($marker).Trim() -eq $entry.sha256)) {
            Write-ParkosPartsLog $Logger "'$Id' ya restaurado y al dia: $target"
            return $target
        }
    }

    # Tamanos/presencia antes de leer cientos de MB.
    $problems = @(Get-ParkosPartsEntryProblems -Entry $entry -PartsDir $PartsDir -SkipHash)
    if ($problems.Count -gt 0) {
        throw "No se puede restaurar '$Id': $($problems -join '; '). Restaure las partes con git (git checkout -- installer/payload/parts) o copie de nuevo el paquete completo."
    }
    $paths = @(Get-ParkosPartsEntryPaths -Entry $entry -PartsDir $PartsDir)

    if (-not $CacheDir) { $CacheDir = Join-Path ([System.IO.Path]::GetTempPath()) 'parkos-parts-cache' }
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent), $CacheDir | Out-Null

    if ($entry.kind -eq 'dir') {
        $joined = Join-Path $CacheDir "$($entry.id)-$([guid]::NewGuid().ToString('N')).zip"
    } else {
        $joined = "$target.restoring"
    }
    Write-ParkosPartsLog $Logger "Uniendo $($paths.Count) parte(s) de '$Id'..."
    try {
        $r = Join-ParkosPartsFile -PartPaths $paths -Destination $joined
        for ($i = 0; $i -lt $paths.Count; $i++) {
            if ($r.PartHashes[$i] -ne $entry.parts[$i].sha256) {
                throw "La parte $($entry.parts[$i].name) de '$Id' esta danada: hash $($r.PartHashes[$i]) y el manifest dice $($entry.parts[$i].sha256). Restaure las partes con git (git checkout -- installer/payload/parts)."
            }
        }
        if ($r.TotalHash -ne $entry.sha256) {
            throw "El archivo rearmado de '$Id' tiene hash $($r.TotalHash) y el manifest dice $($entry.sha256): las partes son de otra version."
        }

        if ($entry.kind -eq 'dir') {
            $staging = "$target.restoring"
            if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
            Write-ParkosPartsLog $Logger "Expandiendo '$Id' a $target ..."
            Expand-ParkosPartsZip -ZipPath $joined -Destination $staging
            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
            Move-Item -LiteralPath $staging -Destination $target
        } else {
            Move-Item -LiteralPath $joined -Destination $target -Force
        }
    } finally {
        if (Test-Path -LiteralPath $joined) { Remove-Item -LiteralPath $joined -Recurse -Force -ErrorAction SilentlyContinue }
        $stg = "$target.restoring"
        if ($entry.kind -eq 'dir' -and (Test-Path -LiteralPath $stg)) { Remove-Item -LiteralPath $stg -Recurse -Force -ErrorAction SilentlyContinue }
    }
    [System.IO.File]::WriteAllText($marker, $entry.sha256)
    Write-ParkosPartsLog $Logger "'$Id' restaurado y verificado: $target"
    return $target
}

# Restaura todos los artefactos del manifest que van a payload\ (o los de -Ids).
# Registra 'Restaurando <id> n de m'. Devuelve los ids procesados.
function Restore-ParkosPayloadAll {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PartsDir,
        [Parameter(Mandatory)][string]$PayloadRoot,
        [string[]]$Ids,
        [string]$CacheDir = '',
        [switch]$Force,
        [scriptblock]$Logger
    )

    $manifest = Get-ParkosPayloadManifest -PartsDir $PartsDir
    if (-not $manifest) { throw "No existe $(Join-Path $PartsDir $script:ParkosPartsManifestName): no hay artefactos en partes para restaurar." }
    $entries = @(Get-ParkosPayloadManifestEntries -Manifest $manifest)
    if ($Ids -and @($Ids).Count -gt 0) {
        foreach ($id in $Ids) {
            if (-not ($entries | Where-Object { $_.id -eq $id })) { throw "El artefacto '$id' no esta en el manifest de partes." }
        }
        $selected = @($entries | Where-Object { $Ids -contains $_.id })
    } else {
        $selected = @($entries | Where-Object { [bool](Get-ParkosPartsProp -Object $_ -Name 'restoreToPayload' -Default $true) })
    }
    $n = 0
    $done = @()
    foreach ($e in $selected) {
        $n++
        Write-ParkosPartsLog $Logger "Restaurando $($e.id) $n de $($selected.Count)"
        [void](Restore-ParkosPayloadArtifact -Id $e.id -PartsDir $PartsDir -PayloadRoot $PayloadRoot -CacheDir $CacheDir -Force:$Force -Logger $Logger)
        $done += $e.id
    }
    return $done
}

# ---------------------------------------------------------------------------
# Verificacion (CI / Prepare)
# ---------------------------------------------------------------------------

# Verifica manifest vs archivos: partes presentes, tamanos, hashes, ninguna
# > 90 MiB, sin archivos desconocidos. Devuelve { Ok; Problems }.
function Test-ParkosPayloadParts {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$PartsDir, [switch]$SkipHash)

    $problems = [System.Collections.Generic.List[string]]::new()
    $manifest = $null
    try { $manifest = Get-ParkosPayloadManifest -PartsDir $PartsDir } catch { $problems.Add($_.Exception.Message) }
    if (-not $manifest -and $problems.Count -eq 0) { $problems.Add("falta $(Join-Path $PartsDir $script:ParkosPartsManifestName)") }
    if ($manifest) {
        $entries = @(Get-ParkosPayloadManifestEntries -Manifest $manifest)
        $known = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        [void]$known.Add($script:ParkosPartsManifestName)
        foreach ($e in $entries) {
            foreach ($p in @(Get-ParkosPartsEntryProblems -Entry $e -PartsDir $PartsDir -SkipHash:$SkipHash)) { $problems.Add($p) }
            foreach ($part in @($e.parts)) { [void]$known.Add("$($e.id)\$($part.name)") }
            [void]$known.Add("$($e.id)\$($e.archive).sha256")   # sidecar opcional
        }
        $root = (Resolve-Path -LiteralPath $PartsDir).Path.TrimEnd('\')
        foreach ($f in @(Get-ChildItem -LiteralPath $root -Recurse -File -Force)) {
            $rel = $f.FullName.Substring($root.Length + 1)
            if (-not $known.Contains($rel)) { $problems.Add("archivo desconocido en parts\: $rel (no figura en el manifest)") }
            if ($f.Length -gt $script:ParkosPartsMaxPartBytes) { $problems.Add("$rel supera 90 MiB ($($f.Length) bytes)") }
        }
    }
    return [PSCustomObject]@{ Ok = ($problems.Count -eq 0); Problems = @($problems | Select-Object -Unique) }
}

# ---------------------------------------------------------------------------
# Decision pura: restaurar de partes o construir
# ---------------------------------------------------------------------------

# 'restore' cuando hay entrada con partes y (no hay informacion de git -
# ChangedFiles $null - o ningun archivo de backend/ o installer/bootstrap/
# cambio desde builtFromCommit); 'build' en otro caso. Los artefactos que no
# dependen del codigo (terceros) siempre se restauran. Es pura: ChangedFiles
# lo calcula Get-ParkosPartsChangedFiles.
function Get-ParkosPartsArtifactDecision {
    [CmdletBinding()]
    param($Entry, $ChangedFiles = $null)

    if ($null -eq $Entry) { return 'build' }
    if (@(Get-ParkosPartsProp -Object $Entry -Name 'parts' -Default @()).Count -eq 0) { return 'build' }
    if (-not [bool](Get-ParkosPartsProp -Object $Entry -Name 'sourceDependent' -Default $false)) { return 'restore' }
    if ($null -eq $ChangedFiles) { return 'restore' }
    if (@($ChangedFiles).Count -gt 0) { return 'build' }
    return 'restore'
}

# ---------------------------------------------------------------------------
# Empaquetado por tabla (lo usan tools\Pack-ParkosPayload.ps1 y build-release -Pack)
# ---------------------------------------------------------------------------

# Empaqueta los artefactos de la tabla que esten presentes en <PayloadRoot>.
# Sin -Ids: solo los 'Default' (terceros estables); con -Ids: exactamente esos
# (si un id pedido no esta en el payload crudo, falla). Postgres ya viaja como
# partes en parts\postgres: si no hay ZIP crudo pero las partes existen y no
# estan en el manifest, se registran sin tocar sus bytes.
function Invoke-ParkosPackPayload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PayloadRoot,
        [Parameter(Mandatory)][string]$PartsDir,
        [string]$RepoRoot = '',
        [string[]]$Ids,
        [switch]$Force,
        [object[]]$Table,
        [scriptblock]$Logger
    )

    if (-not $Table) { $Table = @(Get-ParkosPayloadArtifactTable) }
    $explicit = ($Ids -and @($Ids).Count -gt 0)
    if ($explicit) {
        foreach ($id in $Ids) {
            if (-not ($Table | Where-Object { $_.Id -eq $id })) { throw "El artefacto '$id' no esta en la tabla de artefactos (ids validos: $((@($Table | ForEach-Object { $_.Id })) -join ', '))." }
        }
        $rows = @($Table | Where-Object { $Ids -contains $_.Id })
    } else {
        $rows = @($Table | Where-Object { $_.Default })
    }

    $done = @()
    foreach ($row in $rows) {
        $found = @(Get-Item -Path (Join-Path $PayloadRoot $row.Path) -Force -ErrorAction SilentlyContinue | Sort-Object Name)
        if ($found.Count -eq 0) {
            $idDir = Join-Path $PartsDir $row.Id
            $hasParts = (Test-Path -LiteralPath $idDir) -and (@(Get-ChildItem -LiteralPath $idDir -File -Filter '*.part*' -ErrorAction SilentlyContinue).Count -gt 0)
            if ($hasParts -and -not (Find-ParkosPayloadEntry -PartsDir $PartsDir -Id $row.Id)) {
                $archive = (Split-Path $row.Path -Leaf)
                [void](Register-ParkosPayloadExistingParts -Id $row.Id -PartsDir $PartsDir -ArchiveName $archive -Target $row.Path -Kind $row.Kind -SourceInfo $row.Source -RepoRoot $RepoRoot -NoRestoreToPayload:(-not $row.RestoreToPayload) -Logger $Logger)
                $done += $row.Id
                continue
            }
            if ($hasParts -and (Find-ParkosPayloadEntry -PartsDir $PartsDir -Id $row.Id)) {
                Write-ParkosPartsLog $Logger "'$($row.Id)' ya esta empaquetado en partes y no hay copia cruda en el payload: se deja tal cual."
                $done += $row.Id
                continue
            }
            if ($explicit) { throw "No se encontro '$($row.Path)' en ${PayloadRoot}: no se puede empaquetar '$($row.Id)'. Construyalo antes (build-release.ps1)." }
            Write-ParkosPartsLog $Logger "'$($row.Id)' no esta en $PayloadRoot ($($row.Path)): se omite."
            continue
        }
        $item = $found[-1]
        $target = $row.Path
        if ($row.Path.Contains('*')) { $target = (Join-Path (Split-Path $row.Path -Parent) $item.Name) }
        $info = $row.Source
        if ($row.SourceDependent) {
            $c = Get-ParkosPartsGitCommit -RepoRoot $RepoRoot
            if ($c) { $info = "$info @ $c" }
        }
        [void](Pack-ParkosPayloadArtifact -Source $item.FullName -Id $row.Id -PartsDir $PartsDir -Target $target `
                -SourceInfo $info -RepoRoot $RepoRoot -SourceDependent:$row.SourceDependent `
                -NoRestoreToPayload:(-not $row.RestoreToPayload) -Force:$Force -Logger $Logger)
        $done += $row.Id
    }
    return $done
}
