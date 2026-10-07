# Descarga e instalacion de Postgres 16 (binarios ZIP de EnterpriseDB) y de la
# extension pg_partman SQL-only. COMPARTIDO por el instalador completo
# (installer/parkos-installer.ps1) y el instalador lite (installer/lite).
#
# Reglas de este archivo (para poder dot-sourcearlo desde cualquier sitio):
#   - Sin StrictMode, sin param() de script, sin efectos al cargar: solo
#     define funciones.
#   - Sin elevacion y sin dependencia de estado propio del lite o del full:
#     todo directorio llega por parametro; el log llega como scriptblock
#     (-Logger, recibe UN string).
#   - Toda llamada de red / zip / hash / sleep esta en un wrapper propio
#     (Invoke-ParkosHttpDownload, Get-ParkosZipEntryNames,
#     Expand-ParkosZipArchive, Get-ParkosFileSha256, Start-ParkosSleep) para
#     poder mockearlo en Pester 3.4.
#   - Compatible con Windows PowerShell 5.1 y pwsh 7 (sin ternario, sin ?.).
#
# Funciones publicas:
#   Get-ParkosPostgresDownloadInfo
#   Get-ParkosPostgresZip           -CacheDir [-PayloadDir] [-Logger] [-MaxAttempts]
#   Expand-ParkosPostgresZip        -ZipPath -PgRoot [-Logger] [-Force]
#   Get-ParkosPgPartmanExtension    -ExtensionDir -TempDir [-PayloadDir] [-Logger] [-MaxAttempts]
#   Install-ParkosPgPartmanExtension -PgRoot -ExtensionDir
#   Test-ParkosPostgresZip          -Path
#   Get-ParkosDownloadBackoffSeconds -Attempt
#   Get-ParkosDownloadFailureMessage -What -Url -TargetDir -FileName [-Detail]

$script:ParkosPgRequiredBinaries = @('pg_ctl.exe', 'initdb.exe', 'psql.exe')

# Version fijada (verificada con HEAD 200 contra get.enterprisedb.com). EDB no
# publica un SHA-256 oficial por archivo, asi que el hash esperado se fija aqui
# (ParkosPgPinnedSha256) con el del ZIP completo versionado en el repo
# (installer\payload\parts\payload-parts.json y postgres\<zip>.sha256; un test lo
# cruza). Todo ZIP que se use (payload, cache o descarga) debe coincidir; el
# hash que se registra en <zip>.sha256 en la primera descarga ya no es la
# fuente de confianza. Al subir de version: cambiar Version y este hash a la vez.
$script:ParkosPgPinnedSha256 = '25e6fcdfb8caec38691bf461125e7564508760666f7b8e5dc6a5f0818f58f81e'

function Get-ParkosPostgresDownloadInfo {
    $version = '16.15-1'
    $fileName = "postgresql-$version-windows-x64-binaries.zip"
    return @{
        Version  = $version
        FileName = $fileName
        Url      = "https://get.enterprisedb.com/postgresql/$fileName"
        Sha256   = $script:ParkosPgPinnedSha256
    }
}

# Version de pg_partman: la misma que ensambla installer/build-release.ps1
# (Get-PgPartmanBinaries). SQL-only: sin DLL, sin bgw.
function Get-ParkosPgPartmanDownloadInfo {
    $version = '5.1.0'
    return @{
        Version = $version
        Url     = "https://github.com/pgpartman/pg_partman/archive/refs/tags/v$version.zip"
    }
}

function Write-ParkosDownloadLog {
    param([scriptblock]$Logger, [string]$Message)
    if ($Logger) { & $Logger $Message } else { Write-Host $Message }
}

# ---------------------------------------------------------------------------
# Wrappers mockeables (red, zip, hash, sleep)
# ---------------------------------------------------------------------------

function Start-ParkosSleep {
    param([int]$Seconds)
    Start-Sleep -Seconds $Seconds
}

function Get-ParkosFileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Get-ParkosZipEntryNames {
    param([Parameter(Mandatory)][string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        return @($zip.Entries | ForEach-Object { $_.FullName })
    } finally {
        $zip.Dispose()
    }
}

function Expand-ParkosZipArchive {
    param([Parameter(Mandatory)][string]$ZipPath, [Parameter(Mandatory)][string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Destination)
}

# Descarga con HttpClient en streaming: reanuda un .part existente con Range
# (si el servidor lo soporta; si responde 200 reinicia), muestra progreso y
# fuerza TLS 1.2. Lanza ante cualquier error HTTP/red; el reintento lo decide
# el llamador (Get-ParkosPostgresZip).
function Invoke-ParkosHttpDownload {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$OutFile,
        [string]$Activity = 'Descargando'
    )

    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Add-Type -AssemblyName System.Net.Http

    $existing = 0L
    if (Test-Path $OutFile) { $existing = (Get-Item $OutFile).Length }

    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(60)
    try {
        $request = New-Object System.Net.Http.HttpRequestMessage ([System.Net.Http.HttpMethod]::Get), $Url
        if ($existing -gt 0) {
            $request.Headers.Range = New-Object System.Net.Http.Headers.RangeHeaderValue ($existing, $null)
        }
        $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        try {
            $status = [int]$response.StatusCode
            if ($status -eq 416) {
                # El .part ya esta completo (o el rango no encaja): reiniciar.
                Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
                throw 'HTTP 416: rango no satisfacible, se reinicia la descarga.'
            }
            if ($status -ne 200 -and $status -ne 206) {
                throw "HTTP $status al descargar $Url"
            }
            $append = ($status -eq 206)
            $total = $response.Content.Headers.ContentLength
            if ($append -and $total) { $total = $total + $existing }
            $mode = [System.IO.FileMode]::Create
            if ($append) { $mode = [System.IO.FileMode]::Append } else { $existing = 0L }

            $in = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $out = New-Object System.IO.FileStream ($OutFile, $mode, [System.IO.FileAccess]::Write)
            try {
                $buffer = New-Object byte[] (1MB)
                $done = $existing
                $lastTick = [DateTime]::UtcNow
                while (($n = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $out.Write($buffer, 0, $n)
                    $done += $n
                    if (([DateTime]::UtcNow - $lastTick).TotalMilliseconds -ge 500) {
                        $lastTick = [DateTime]::UtcNow
                        $mb = [math]::Round($done / 1MB, 1)
                        if ($total) {
                            $pct = [int](100 * $done / $total)
                            Write-Progress -Activity $Activity -Status "$mb MB de $([math]::Round($total / 1MB, 1)) MB" -PercentComplete $pct
                        } else {
                            Write-Progress -Activity $Activity -Status "$mb MB"
                        }
                    }
                }
            } finally {
                $out.Dispose()
                $in.Dispose()
                Write-Progress -Activity $Activity -Completed
            }
        } finally {
            $response.Dispose()
        }
    } finally {
        $client.Dispose()
    }
}

# ---------------------------------------------------------------------------
# Decisiones puras
# ---------------------------------------------------------------------------

function Get-ParkosDownloadBackoffSeconds {
    param([Parameter(Mandatory)][int]$Attempt)
    $s = 5 * [math]::Pow(2, $Attempt - 1)
    if ($s -gt 60) { $s = 60 }
    return [int]$s
}

function Get-ParkosDownloadFailureMessage {
    param(
        [Parameter(Mandatory)][string]$What,
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$TargetDir,
        [Parameter(Mandatory)][string]$FileName,
        [string]$Detail = ''
    )
    return @"
No se pudo obtener $What (se necesita Internet SOLO en este paso).
  Detalle : $Detail
  URL     : $Url
  Manual  : descarga el archivo desde esa URL y guardalo como
            $(Join-Path $TargetDir $FileName)
            luego vuelve a ejecutar este paso (es re-ejecutable).
"@
}

# Un zip de Postgres es valido si abre y trae pg_ctl, initdb y psql (con o sin
# carpeta raiz 'pgsql/'; tolera separadores y mayusculas).
function Test-ParkosPostgresZip {
    param([Parameter(Mandatory)][string]$Path)
    try {
        $names = @(Get-ParkosZipEntryNames -Path $Path | ForEach-Object { ($_ -replace '\\', '/').ToLowerInvariant() })
    } catch {
        return $false
    }
    foreach ($bin in $script:ParkosPgRequiredBinaries) {
        $suffix = "bin/$bin"
        $hit = $names | Where-Object { $_ -eq $suffix -or $_.EndsWith("/$suffix") } | Select-Object -First 1
        if (-not $hit) { return $false }
    }
    return $true
}

# ---------------------------------------------------------------------------
# Postgres ZIP en partes (el ZIP completo supera los 100 MB de GitHub, asi que
# el repo versiona <zip>.part01..NN + <zip>.sha256 del ZIP COMPLETO)
# ---------------------------------------------------------------------------

# Estado de las partes de <FileName> en <Dir>: Parts = rutas ordenadas
# numericamente (vacio si no hay ninguna); Problem = $null o el texto de lo que
# esta mal (hueco en la numeracion, falta el .sha256).
function Get-ParkosPostgresPartsStatus {
    param([Parameter(Mandatory)][string]$Dir, [Parameter(Mandatory)][string]$FileName)

    $found = @()
    if (Test-Path -LiteralPath $Dir) {
        foreach ($f in @(Get-ChildItem -LiteralPath $Dir -File -Filter "$FileName.part*")) {
            if ($f.Name -match '\.part(\d+)$') { $found += [PSCustomObject]@{ Number = [int]$Matches[1]; Path = $f.FullName } }
        }
    }
    $found = @($found | Sort-Object Number)
    if ($found.Count -eq 0) { return [PSCustomObject]@{ Parts = @(); Problem = $null } }

    for ($i = 0; $i -lt $found.Count; $i++) {
        if ($found[$i].Number -ne ($i + 1)) {
            $missing = '{0:D2}' -f ($i + 1)
            return [PSCustomObject]@{ Parts = @(); Problem = "Falta la parte $missing de $FileName en ${Dir} (se encontraron $($found.Count) partes no contiguas). Restaure las partes con git (git checkout -- installer/payload/parts/postgres) o copie de nuevo el paquete completo." }
        }
    }
    $sidecar = Join-Path $Dir "$FileName.sha256"
    if (-not (Test-Path -LiteralPath $sidecar)) {
        return [PSCustomObject]@{ Parts = @(); Problem = "Falta el archivo $FileName.sha256 junto a las partes en ${Dir}: sin el no se puede verificar el ZIP rearmado." }
    }
    return [PSCustomObject]@{ Parts = @($found | ForEach-Object { $_.Path }); Problem = $null }
}

# Concatena las partes (en el orden dado) en <Destination> por streaming (buffer
# de 4 MB: nunca carga un ZIP de ~330 MB en memoria).
function Join-ParkosFileParts {
    param([Parameter(Mandatory)][string[]]$PartPaths, [Parameter(Mandatory)][string]$Destination)

    $buffer = New-Object byte[] (4MB)
    $out = [System.IO.File]::Open($Destination, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        foreach ($part in $PartPaths) {
            $in = [System.IO.File]::OpenRead($part)
            try {
                while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) { $out.Write($buffer, 0, $read) }
            } finally { $in.Dispose() }
        }
    } finally { $out.Dispose() }
}

# Rearma el ZIP desde las partes de <PayloadDir> hacia <CacheDir> (nunca dentro
# del payload) y lo verifica contra <zip>.sha256 del payload. Si el cache ya
# tiene un ZIP valido con ese hash lo reusa (re-ejecucion idempotente).
function Restore-ParkosPostgresZipFromParts {
    param(
        [Parameter(Mandatory)][string]$PayloadDir,
        [Parameter(Mandatory)][string]$CacheDir,
        [Parameter(Mandatory)][string]$FileName,
        [Parameter(Mandatory)][string[]]$PartPaths,
        [scriptblock]$Logger
    )

    $expected = (([System.IO.File]::ReadAllText((Join-Path $PayloadDir "$FileName.sha256"))).Trim() -split '\s+')[0].ToLowerInvariant()
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $target = Join-Path $CacheDir $FileName

    if ((Test-Path -LiteralPath $target) -and ((Get-ParkosFileSha256 -Path $target) -eq $expected) -and (Test-ParkosPostgresZip -Path $target)) {
        Write-ParkosDownloadLog $Logger "Postgres ZIP ya rearmado en cache: $target"
        return $target
    }

    $tmp = "$target.assembling"
    Write-ParkosDownloadLog $Logger "Rearmando Postgres ZIP desde $($PartPaths.Count) partes versionadas del paquete..."
    try {
        Join-ParkosFileParts -PartPaths $PartPaths -Destination $tmp
        $actual = Get-ParkosFileSha256 -Path $tmp
        if ($actual -ne $expected) {
            throw "El ZIP de Postgres rearmado desde las partes tiene hash SHA-256 $actual y se esperaba $expected ($FileName.sha256). Alguna parte esta danada o es de otra version: restaure las partes con git (git checkout -- installer/payload/parts/postgres) o copie de nuevo el paquete."
        }
        if (-not (Test-ParkosPostgresZip -Path $tmp)) {
            throw 'El ZIP rearmado coincide con el hash pero no contiene pg_ctl/initdb/psql: el paquete esta mal armado.'
        }
    } catch {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        throw
    }
    Move-Item -LiteralPath $tmp -Destination $target -Force
    Set-Content -Path "$target.sha256" -Value $actual -NoNewline
    Write-ParkosDownloadLog $Logger "Postgres ZIP rearmado y verificado: $target"
    return $target
}

# ---------------------------------------------------------------------------
# Postgres ZIP
# ---------------------------------------------------------------------------

# $true si el SHA-256 del archivo es el fijado. Falla cerrado: sin hash fijado
# lanza (nunca acepta "cualquier zip").
function Test-ParkosPostgresZipPinnedHash {
    param([Parameter(Mandatory)][string]$Path, [string]$Sha256)
    if (-not $Sha256) { throw 'No hay SHA-256 fijado para el ZIP de Postgres (ParkosPgPinnedSha256): no se puede verificar; se rechaza el archivo.' }
    return ((Get-ParkosFileSha256 -Path $Path) -eq $Sha256.ToLowerInvariant())
}

# Devuelve la ruta de un zip de Postgres valido: cache (-CacheDir), payload del
# instalador (-PayloadDir: nombre fijado o 'postgresql-16-windows-x64-binaries.zip')
# o descarga nueva a <CacheDir> (.part -> validar -> renombrar).
function Get-ParkosPostgresZip {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$CacheDir,
        [string]$PayloadDir,
        [scriptblock]$Logger,
        [int]$MaxAttempts = 3
    )

    $info = Get-ParkosPostgresDownloadInfo
    $cached = Join-Path $CacheDir $info.FileName

    # 1) Payload del instalador: ZIP completo (con el SHA-256 fijado).
    if ($PayloadDir) {
        foreach ($name in @($info.FileName, 'postgresql-16-windows-x64-binaries.zip')) {
            $p = Join-Path $PayloadDir $name
            if ((Test-Path $p) -and (Test-ParkosPostgresZip -Path $p)) {
                if (Test-ParkosPostgresZipPinnedHash -Path $p -Sha256 $info.Sha256) {
                    Write-ParkosDownloadLog $Logger "Postgres ZIP en payload: $p"
                    return $p
                }
                Write-ParkosDownloadLog $Logger "El ZIP $p no coincide con el SHA-256 fijado de Postgres $($info.Version): se ignora."
            }
        }

        # 2) Payload del instalador: partes versionadas -> se rearma en el
        #    CACHE y se verifica contra el .sha256. Cualquier problema aqui
        #    es un error del paquete: NO se cae en silencio a una descarga.
        $partsStatus = Get-ParkosPostgresPartsStatus -Dir $PayloadDir -FileName $info.FileName
        if ($partsStatus.Problem) { throw $partsStatus.Problem }
        if (@($partsStatus.Parts).Count -gt 0) {
            return (Restore-ParkosPostgresZipFromParts -PayloadDir $PayloadDir -CacheDir $CacheDir -FileName $info.FileName -PartPaths $partsStatus.Parts -Logger $Logger)
        }
    }

    # 3) Cache de descargas (con verificacion de hash registrado).
    if (Test-Path $cached) {
        if (Test-ParkosPostgresZip -Path $cached) {
            $hashFile = "$cached.sha256"
            $actual = Get-ParkosFileSha256 -Path $cached
            if (Test-Path $hashFile) {
                $expected = (Get-Content $hashFile -Raw).Trim()
                if ($expected -ne $actual) {
                    throw "El hash SHA-256 de $cached ($actual) no coincide con el registrado ($expected). El archivo cambio desde que se descargo: muevelo o borralo manualmente y reintenta."
                }
            } else {
                Set-Content -Path $hashFile -Value $actual -NoNewline
                Write-ParkosDownloadLog $Logger "Hash SHA-256 registrado (primer uso): $actual"
            }
            if (Test-ParkosPostgresZipPinnedHash -Path $cached -Sha256 $info.Sha256) {
                Write-ParkosDownloadLog $Logger "Postgres ZIP en cache: $cached"
                return $cached
            }
            Write-ParkosDownloadLog $Logger "El ZIP en cache ($actual) no coincide con el SHA-256 fijado de Postgres $($info.Version); se aparta como .bad y se descarga de nuevo."
            Move-Item -Path $cached -Destination "$cached.bad" -Force
            Remove-Item -LiteralPath $hashFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-ParkosDownloadLog $Logger "El ZIP en cache es invalido; se aparta como .bad y se descarga de nuevo."
            Move-Item -Path $cached -Destination "$cached.bad" -Force
        }
    }

    # 4) Descarga con reintentos (ultimo recurso).
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $part = "$cached.part"
    $lastError = ''
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-ParkosDownloadLog $Logger "Descargando Postgres $($info.Version) (intento $attempt de $MaxAttempts): $($info.Url)"
            Invoke-ParkosHttpDownload -Url $info.Url -OutFile $part -Activity "Descargando Postgres $($info.Version)"
            if (-not (Test-ParkosPostgresZip -Path $part)) {
                Remove-Item $part -Force -ErrorAction SilentlyContinue
                throw 'el archivo descargado no es un ZIP de Postgres valido (faltan pg_ctl/initdb/psql).'
            }
            if (-not (Test-ParkosPostgresZipPinnedHash -Path $part -Sha256 $info.Sha256)) {
                Remove-Item $part -Force -ErrorAction SilentlyContinue
                throw "el ZIP descargado no coincide con el SHA-256 fijado ($($info.Sha256)) de Postgres $($info.Version): se descarta."
            }
            Move-Item -Path $part -Destination $cached -Force
            $hash = Get-ParkosFileSha256 -Path $cached
            Set-Content -Path "$cached.sha256" -Value $hash -NoNewline
            Write-ParkosDownloadLog $Logger "Descarga completa. SHA-256 registrado: $hash"
            return $cached
        } catch {
            $lastError = $_.Exception.Message
            Write-ParkosDownloadLog $Logger "Intento $attempt fallo: $lastError"
            if ($attempt -lt $MaxAttempts) {
                $wait = Get-ParkosDownloadBackoffSeconds -Attempt $attempt
                Write-ParkosDownloadLog $Logger "Reintentando en $wait s..."
                Start-ParkosSleep -Seconds $wait
            }
        }
    }
    throw (Get-ParkosDownloadFailureMessage -What "los binarios de Postgres $($info.Version)" -Url $info.Url -TargetDir $CacheDir -FileName $info.FileName -Detail $lastError)
}

# Extrae el zip a <PgRoot> (la carpeta que contiene bin\, share\, lib\).
# Extrae primero a <PgRoot>.extracting y mueve: una extraccion interrumpida
# nunca deja un PgRoot a medias. Idempotente.
function Expand-ParkosPostgresZip {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ZipPath,
        [Parameter(Mandatory)][string]$PgRoot,
        [scriptblock]$Logger,
        [switch]$Force
    )

    $ctl = Join-Path $PgRoot 'bin\pg_ctl.exe'
    if ((Test-Path $ctl) -and -not $Force) {
        Write-ParkosDownloadLog $Logger "Postgres ya extraido en $PgRoot"
        return $PgRoot
    }

    $tmp = "$PgRoot.extracting"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Write-ParkosDownloadLog $Logger "Extrayendo Postgres a $PgRoot (puede tardar un par de minutos)..."
    Expand-ParkosZipArchive -ZipPath $ZipPath -Destination $tmp

    $source = $null
    if (Test-Path (Join-Path $tmp 'pgsql\bin\pg_ctl.exe')) { $source = Join-Path $tmp 'pgsql' }
    elseif (Test-Path (Join-Path $tmp 'bin\pg_ctl.exe')) { $source = $tmp }
    if (-not $source) {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        throw "El ZIP extraido no contiene bin\pg_ctl.exe (ni pgsql\bin\pg_ctl.exe): no es un paquete de binarios de Postgres."
    }

    if (Test-Path $PgRoot) { Remove-Item $PgRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Split-Path $PgRoot) | Out-Null
    Move-Item -Path $source -Destination $PgRoot
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    return $PgRoot
}

# ---------------------------------------------------------------------------
# pg_partman SQL-only
# ---------------------------------------------------------------------------

function Test-ParkosPgPartmanExtensionDir {
    param([string]$Dir)
    if (-not $Dir) { return $false }
    $sql = @(Get-ChildItem -Path $Dir -Filter 'pg_partman--*.sql' -ErrorAction SilentlyContinue)
    return (($sql.Count -gt 0) -and (Test-Path (Join-Path $Dir 'pg_partman.control')))
}

# Mismo ensamblado que installer/build-release.ps1 (Get-PgPartmanBinaries):
# concatena sql/types + tables + functions + procedures (cada directorio
# ordenado por nombre) en pg_partman--<version>.sql y copia el .control.
# Agrega un salto de linea entre archivos para que un comentario final sin
# newline nunca absorba la primera sentencia del siguiente.
function New-ParkosPgPartmanSqlOnly {
    param(
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$Version,
        [Parameter(Mandatory)][string]$OutDir
    )

    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $sb = New-Object System.Text.StringBuilder
    foreach ($sub in 'types', 'tables', 'functions', 'procedures') {
        $dir = Join-Path $SourceRoot "sql\$sub"
        foreach ($f in (Get-ChildItem -Path $dir -Filter '*.sql' | Sort-Object Name)) {
            [void]$sb.Append([IO.File]::ReadAllText($f.FullName))
            [void]$sb.Append("`n")
        }
    }
    $sqlOut = Join-Path $OutDir "pg_partman--$Version.sql"
    [IO.File]::WriteAllText($sqlOut, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
    Copy-Item -Path (Join-Path $SourceRoot 'pg_partman.control') -Destination (Join-Path $OutDir 'pg_partman.control') -Force
}

# Devuelve el directorio con la extension lista: -PayloadDir si ya la trae
# (build-release.ps1), si no -ExtensionDir (cache; se ensambla si falta).
function Get-ParkosPgPartmanExtension {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ExtensionDir,
        [Parameter(Mandatory)][string]$TempDir,
        [string]$PayloadDir,
        [scriptblock]$Logger,
        [int]$MaxAttempts = 3
    )

    if (Test-ParkosPgPartmanExtensionDir -Dir $PayloadDir) {
        Write-ParkosDownloadLog $Logger "pg_partman SQL-only en payload: $PayloadDir"
        return $PayloadDir
    }
    if (Test-ParkosPgPartmanExtensionDir -Dir $ExtensionDir) {
        Write-ParkosDownloadLog $Logger "pg_partman SQL-only en cache: $ExtensionDir"
        return $ExtensionDir
    }

    $info = Get-ParkosPgPartmanDownloadInfo
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
    $zip = Join-Path $TempDir "pg_partman-$($info.Version).zip"
    $extract = Join-Path $TempDir "pg_partman-$($info.Version)-extract"
    $lastError = ''
    $ok = $false
    for ($attempt = 1; $attempt -le $MaxAttempts -and -not $ok; $attempt++) {
        try {
            Write-ParkosDownloadLog $Logger "Descargando pg_partman $($info.Version) (intento $attempt de $MaxAttempts): $($info.Url)"
            Invoke-ParkosHttpDownload -Url $info.Url -OutFile $zip -Activity "Descargando pg_partman $($info.Version)"
            if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
            Expand-ParkosZipArchive -ZipPath $zip -Destination $extract
            $ok = $true
        } catch {
            $lastError = $_.Exception.Message
            Write-ParkosDownloadLog $Logger "Intento $attempt fallo: $lastError"
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            if ($attempt -lt $MaxAttempts) {
                Start-ParkosSleep -Seconds (Get-ParkosDownloadBackoffSeconds -Attempt $attempt)
            }
        }
    }
    if (-not $ok) {
        throw (Get-ParkosDownloadFailureMessage -What "la extension pg_partman $($info.Version)" -Url $info.Url -TargetDir $TempDir -FileName "pg_partman-$($info.Version).zip" -Detail $lastError)
    }

    $srcRoot = Join-Path $extract "pg_partman-$($info.Version)"
    New-ParkosPgPartmanSqlOnly -SourceRoot $srcRoot -Version $info.Version -OutDir $ExtensionDir
    Remove-Item $zip, $extract -Recurse -Force -ErrorAction SilentlyContinue
    Write-ParkosDownloadLog $Logger "pg_partman SQL-only ensamblado en $ExtensionDir"
    return $ExtensionDir
}

# Copia la extension al share\extension del Postgres extraido.
function Install-ParkosPgPartmanExtension {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string]$ExtensionDir)
    $dest = Join-Path $PgRoot 'share\extension'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -Path (Join-Path $ExtensionDir 'pg_partman*') -Destination $dest -Force
}
