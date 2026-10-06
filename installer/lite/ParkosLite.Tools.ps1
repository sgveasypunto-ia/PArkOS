# Parkos LITE - herramientas portatiles (git, uv, node, pnpm).
#
# Si el equipo ya trae una herramienta compatible en el PATH se usa esa; si no,
# el lite descarga una copia PORTATIL en <LitePath>\tools\<herramienta>\ (sin
# admin, sin winget, sin instalador) y la antepone al PATH SOLO del proceso del
# lite y de sus hijos (build-release.ps1, uv, pnpm, node/vite, git). Nunca se
# toca el PATH de Maquina/Usuario, el registro ni ningun estado global.
#
# Solo funciones (sin efectos al cargar). Compatible con PowerShell 5.1 y 7.
# Todo acceso al sistema (PATH, procesos, red, zip, mover carpetas) vive en
# wrappers pequenos que los tests mockean. Requiere (dot-source previo):
#   shared\ParkosPostgresDownload.ps1 (descarga, sha256, zip, backoff, mensaje)
#   ParkosLite.Db.ps1 (Invoke-ParkosLiteNative)
#
# Orden de origen de cada herramienta: PATH (compatible) -> partes versionadas en
# el repo (installer\payload\parts\tools-*, verificadas contra el sha256 FIJADO
# de esta tabla) -> descarga. Requiere tambien shared\ParkosPayloadParts.ps1.
#
# Cache de descargas: <LitePath>\downloads (los zip sobreviven a limpiar tools\).

# ---------------------------------------------------------------------------
# Tabla de versiones fijadas (UNICO lugar: versiones, URLs y hashes)
#   node : Sha256 fijado + se contrasta con SHASUMS256.txt del mismo dist.
#   uv   : Sha256 fijado + se contrasta con el asset .sha256 del release.
#   git  : Sha256 fijado = digest que publica GitHub para el asset del release
#          (Git for Windows no publica un .sha256 aparte).
#   pnpm : se instala con npm (portatil) en --prefix; la version sigue el
#          packageManager de apps\package.json.
# ---------------------------------------------------------------------------

$script:ParkosLiteNodeVersion = '22.23.3'
$script:ParkosLiteUvVersion = '0.12.23'
$script:ParkosLiteGitVersion = '2.56.0.2'      # MinGit 2.56.0.2 (tag v2.56.0.windows.2)
$script:ParkosLitePnpmVersion = '10.0.0'

function Get-ParkosLiteToolSpecs {
    $node = $script:ParkosLiteNodeVersion
    $uv = $script:ParkosLiteUvVersion
    $git = $script:ParkosLiteGitVersion
    $gitTag = 'v{0}.windows.{1}' -f ($git -replace '\.\d+$', ''), ($git -replace '^.*\.', '')
    return [ordered]@{
        git  = @{
            Name = 'git'; Label = 'Git (MinGit)'; Version = $git; MinVersion = [version]'2.20.0'
            Url = "https://github.com/git-for-windows/git/releases/download/$gitTag/MinGit-$git-64-bit.zip"
            FileName = "MinGit-$git-64-bit.zip"
            Sha256 = 'da35e72aa21c005a5a0d298cfbae110bc1609a815730ea0dde84b01a1b3cd3be'
            HashUrl = ''; SizeMb = 40; Dir = 'git'; BinDir = 'cmd'; Exe = 'cmd\git.exe'; Kind = 'zip'
        }
        uv   = @{
            Name = 'uv'; Label = 'uv'; Version = $uv; MinVersion = [version]'0.5.0'
            Url = "https://github.com/astral-sh/uv/releases/download/$uv/uv-x86_64-pc-windows-msvc.zip"
            FileName = "uv-$uv-x86_64-pc-windows-msvc.zip"
            Sha256 = '75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90'
            HashUrl = "https://github.com/astral-sh/uv/releases/download/$uv/uv-x86_64-pc-windows-msvc.zip.sha256"
            SizeMb = 18; Dir = 'uv'; BinDir = ''; Exe = 'uv.exe'; Kind = 'zip'
        }
        node = @{
            Name = 'node'; Label = 'Node.js'; Version = $node; MinVersion = [version]'20.0.0'
            Url = "https://nodejs.org/dist/v$node/node-v$node-win-x64.zip"
            FileName = "node-v$node-win-x64.zip"
            Sha256 = '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71'
            HashUrl = "https://nodejs.org/dist/v$node/SHASUMS256.txt"
            SizeMb = 30; Dir = 'node'; BinDir = ''; Exe = 'node.exe'; Kind = 'zip'
        }
        pnpm = @{
            Name = 'pnpm'; Label = 'pnpm'; Version = $script:ParkosLitePnpmVersion; MinVersion = [version]'10.0.0'
            Url = "https://registry.npmjs.org/pnpm/-/pnpm-$($script:ParkosLitePnpmVersion).tgz"
            FileName = ''; Sha256 = ''; HashUrl = ''
            SizeMb = 10; Dir = 'pnpm'; BinDir = ''; Exe = 'pnpm.cmd'; Kind = 'npm'
        }
    }
}

function Get-ParkosLiteToolNames { return @('git', 'uv', 'node', 'pnpm') }

# ---------------------------------------------------------------------------
# Rutas del toolchain
# ---------------------------------------------------------------------------

function Get-ParkosLiteToolPaths {
    param([Parameter(Mandatory)][string]$LitePath)
    $tools = Join-Path $LitePath 'tools'
    return @{
        Tools      = $tools
        Downloads  = Join-Path $LitePath 'downloads'
        UvCache    = Join-Path $tools 'cache\uv'
        UvPython   = Join-Path $tools 'cache\uv-python'
        UvBin      = Join-Path $tools 'cache\uv-bin'
        NpmCache   = Join-Path $tools 'cache\npm'
        PnpmStore  = Join-Path $tools 'cache\pnpm-store'
        PnpmHome   = Join-Path $tools 'cache\pnpm-home'
    }
}

# Directorio que va al PATH y ejecutable de cada herramienta portatil.
function Get-ParkosLiteToolLocation {
    param([Parameter(Mandatory)][string]$ToolsDir, [Parameter(Mandatory)]$Spec)
    $root = Join-Path $ToolsDir $Spec.Dir
    $bin = $root
    if ($Spec.BinDir) { $bin = Join-Path $root $Spec.BinDir }
    return @{ Root = $root; BinDir = $bin; Exe = (Join-Path $root $Spec.Exe) }
}

# ---------------------------------------------------------------------------
# Decisiones puras
# ---------------------------------------------------------------------------

# Primera version X.Y[.Z] del texto de '<tool> --version' ($null si no hay).
function ConvertTo-ParkosLiteVersion {
    param([AllowNull()][AllowEmptyString()][string]$Text)
    if (-not $Text) { return $null }
    $m = [regex]::Match($Text, '(\d+)\.(\d+)(?:\.(\d+))?')
    if (-not $m.Success) { return $null }
    $patch = 0
    if ($m.Groups[3].Success) { $patch = [int]$m.Groups[3].Value }
    return (New-Object System.Version ([int]$m.Groups[1].Value), ([int]$m.Groups[2].Value), $patch)
}

function Test-ParkosLiteToolVersionCompatible {
    param([Parameter(Mandatory)][string]$Tool, [AllowNull()][AllowEmptyString()][string]$VersionText)
    $spec = (Get-ParkosLiteToolSpecs)[$Tool]
    if (-not $spec) { return $false }
    $v = ConvertTo-ParkosLiteVersion -Text $VersionText
    if (-not $v) { return $false }
    return ($v -ge $spec.MinVersion)
}

# ---------------------------------------------------------------------------
# Wrappers (PATH, procesos, red, carpetas): los tests los mockean
# ---------------------------------------------------------------------------

# UNICA puerta de escritura de variables de entorno: SIEMPRE ambito Process.
# Nunca Machine ni User (un test lo verifica sobre el codigo fuente).
function Set-ParkosLiteProcessEnvVar {
    param([Parameter(Mandatory)][string]$Name, [AllowNull()][string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}

function Get-ParkosLiteProcessEnvVar {
    param([Parameter(Mandatory)][string]$Name)
    return [Environment]::GetEnvironmentVariable($Name, 'Process')
}

# Primer ejecutable en el PATH que NO viva dentro de <ToolsDir> (la copia del
# sistema; asi un PATH ya enriquecido con tools\ no esconde la del equipo).
function Get-ParkosLiteSystemToolPath {
    param([Parameter(Mandatory)][string]$Name, [string]$ToolsDir = '')
    $all = @(Get-Command $Name -All -ErrorAction SilentlyContinue | Where-Object { $_.Source })
    foreach ($c in $all) {
        if ($ToolsDir -and $c.Source.StartsWith($ToolsDir, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if ($c.CommandType -eq 'ExternalScript') { continue }
        return $c.Source
    }
    return $null
}

# Texto de '<exe> --version' (o $null si falla).
function Get-ParkosLiteToolVersionText {
    param([Parameter(Mandatory)][string]$Path, [hashtable]$Env = @{})
    try {
        $r = Invoke-ParkosLiteNative -FilePath $Path -Arguments @('--version') -Env $Env
        if ($r.ExitCode -ne 0) { return $null }
        return (($r.Output -join ' ').Trim())
    } catch {
        return $null
    }
}

function Get-ParkosLiteRemoteText {
    param([Parameter(Mandatory)][string]$Url)
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    return [string](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop).Content
}

# Descomprime el zip en una carpeta temporal y deja el contenido en Destination
# (si el zip trae una sola carpeta raiz, como node, se aplana).
function Move-ParkosLiteExtractedContent {
    param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
    $items = @(Get-ChildItem -LiteralPath $Source -Force)
    $root = $Source
    if ($items.Count -eq 1 -and $items[0].PSIsContainer) { $root = $items[0].FullName }
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    $moved = $false
    for ($i = 1; $i -le 5 -and -not $moved; $i++) {
        try { Move-Item -LiteralPath $root -Destination $Destination -ErrorAction Stop; $moved = $true }
        catch { if ($i -eq 5) { throw }; Start-Sleep -Seconds 2 }   # antivirus escaneando lo recien extraido
    }
    if (Test-Path -LiteralPath $Source) { Remove-Item -LiteralPath $Source -Recurse -Force -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------------------
# Entorno de los hijos (UNA funcion central)
# ---------------------------------------------------------------------------

# Estado por herramienta: Origin = system | portable | missing.
# PATH-first: una copia compatible del sistema gana; si no, la portatil valida.
$script:ParkosLiteToolStatusCache = $null

function Get-ParkosLiteToolStatus {
    param([Parameter(Mandatory)][string]$LitePath, [switch]$Refresh)
    if (-not $Refresh -and $script:ParkosLiteToolStatusCache -and $script:ParkosLiteToolStatusCache.Lite -eq $LitePath) {
        return $script:ParkosLiteToolStatusCache.Status
    }
    $tp = Get-ParkosLiteToolPaths -LitePath $LitePath
    $specs = Get-ParkosLiteToolSpecs
    $probeEnv = Get-ParkosLiteToolEnv -LitePath $LitePath
    $status = [ordered]@{}
    foreach ($name in (Get-ParkosLiteToolNames)) {
        $spec = $specs[$name]
        $entry = @{ Name = $name; Origin = 'missing'; Version = ''; Path = '' }
        $sys = Get-ParkosLiteSystemToolPath -Name $name -ToolsDir $tp.Tools
        if ($sys) {
            $txt = Get-ParkosLiteToolVersionText -Path $sys
            if (Test-ParkosLiteToolVersionCompatible -Tool $name -VersionText $txt) {
                $entry = @{ Name = $name; Origin = 'system'; Version = (ConvertTo-ParkosLiteVersion -Text $txt).ToString(); Path = $sys }
            }
        }
        if ($entry.Origin -eq 'missing') {
            $loc = Get-ParkosLiteToolLocation -ToolsDir $tp.Tools -Spec $spec
            if (Test-Path -LiteralPath $loc.Exe) {
                $txt = Get-ParkosLiteToolVersionText -Path $loc.Exe -Env $probeEnv
                if (Test-ParkosLiteToolVersionCompatible -Tool $name -VersionText $txt) {
                    $entry = @{ Name = $name; Origin = 'portable'; Version = (ConvertTo-ParkosLiteVersion -Text $txt).ToString(); Path = $loc.Exe }
                }
            }
        }
        $status[$name] = $entry
    }
    $script:ParkosLiteToolStatusCache = @{ Lite = $LitePath; Status = $status }
    return $status
}

# Variables que ven los procesos hijos del lite. PATH lleva primero las carpetas
# de las herramientas portatiles (solo las que se usan: Status dado -> origen
# 'portable'; sin Status -> las que existan en disco, para sondear versiones).
function Get-ParkosLiteToolEnv {
    param([Parameter(Mandatory)][string]$LitePath, $Status)
    $tp = Get-ParkosLiteToolPaths -LitePath $LitePath
    $specs = Get-ParkosLiteToolSpecs
    $dirs = @()
    $portable = @{}
    foreach ($name in (Get-ParkosLiteToolNames)) {
        $loc = Get-ParkosLiteToolLocation -ToolsDir $tp.Tools -Spec $specs[$name]
        $use = $false
        if ($Status) { $use = ($Status[$name].Origin -eq 'portable') }
        else { $use = (Test-Path -LiteralPath $loc.Exe) }
        if ($use) { $dirs += $loc.BinDir; $portable[$name] = $true }
    }
    $current = Get-ParkosLiteProcessEnvVar -Name 'PATH'
    # Quita tools\ ya presentes (idempotente al aplicar dos veces).
    $rest = @($current -split ';' | Where-Object { $_ -and -not $_.StartsWith($tp.Tools, [StringComparison]::OrdinalIgnoreCase) })
    $envMap = @{ PATH = ((@($dirs) + $rest) -join ';') }
    if ($portable.ContainsKey('uv')) {
        $envMap.UV_CACHE_DIR = $tp.UvCache
        $envMap.UV_PYTHON_INSTALL_DIR = $tp.UvPython
        $envMap.UV_PYTHON_BIN_DIR = $tp.UvBin   # 'uv python install' no debe dejar shims en ~\.local\bin
    }
    if ($portable.ContainsKey('pnpm') -or $portable.ContainsKey('node')) {
        $envMap.PNPM_HOME = $tp.PnpmHome
        $envMap.npm_config_store_dir = $tp.PnpmStore
        $envMap.npm_config_cache = $tp.NpmCache
    }
    return $envMap
}

# Aplica el entorno al PROCESO actual (los hijos lo heredan: Start-Process, &).
function Enable-ParkosLiteToolchainEnv {
    param([Parameter(Mandatory)][string]$LitePath, [switch]$Refresh)
    $status = Get-ParkosLiteToolStatus -LitePath $LitePath -Refresh:$Refresh
    $envMap = Get-ParkosLiteToolEnv -LitePath $LitePath -Status $status
    foreach ($k in $envMap.Keys) { Set-ParkosLiteProcessEnvVar -Name $k -Value ([string]$envMap[$k]) }
    return $status
}

# ---------------------------------------------------------------------------
# Descarga + verificacion + instalacion
# ---------------------------------------------------------------------------

# Hash esperado: el fijado en la tabla; si hay HashUrl oficial y responde, debe
# coincidir (si no responde se usa el fijado). Distinto -> error.
function Get-ParkosLiteExpectedHash {
    param([Parameter(Mandatory)]$Spec)
    $pinned = $Spec.Sha256.ToLowerInvariant()
    if (-not $Spec.HashUrl) { return $pinned }
    $official = $null
    try {
        $text = Get-ParkosLiteRemoteText -Url $Spec.HashUrl
        foreach ($line in ($text -split "`n")) {
            if ($line -match '^\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$') {
                $file = $Matches[2]
                if ($file -eq $Spec.FileName -or $Spec.Url.EndsWith("/$file")) { $official = $Matches[1].ToLowerInvariant(); break }
            }
        }
    } catch { $official = $null }
    if ($official -and $official -ne $pinned) {
        throw "El hash oficial de $($Spec.Name) ($official) no coincide con el fijado en el lite ($pinned). Actualiza la tabla de versiones de ParkosLite.Tools.ps1."
    }
    return $pinned
}

# ---------------------------------------------------------------------------
# Partes versionadas en el repo (installer\payload\parts\tools-*)
# ---------------------------------------------------------------------------

# Id del artefacto en el manifest de partes (git viaja como MinGit).
function Get-ParkosLiteToolPartsId {
    param([Parameter(Mandatory)][string]$Name)
    if ($Name -eq 'git') { return 'tools-mingit' }
    return "tools-$Name"
}

# Entrada del manifest para la herramienta, o $null (sin carpeta, sin manifest,
# JSON roto o sin la entrada). Nunca lanza: un repo sin partes simplemente
# obliga a descargar.
function Get-ParkosLiteToolPartsEntry {
    param([string]$PartsDir, [Parameter(Mandatory)][string]$Name)
    if (-not $PartsDir -or -not (Test-Path -LiteralPath $PartsDir)) { return $null }
    try { return (Find-ParkosPayloadEntry -PartsDir $PartsDir -Id (Get-ParkosLiteToolPartsId -Name $Name)) } catch { return $null }
}

# Rearma el zip pinneado de la herramienta desde las partes del repo, dentro de
# <Downloads>\_parts (se borra siempre), lo verifica contra el sha256 FIJADO de
# la tabla del lite y lo deja en <Downloads>\<FileName>. Devuelve la ruta o
# $null (sin partes / otra version / hash distinto / partes danadas: se avisa y
# el llamador descarga).
function Restore-ParkosLiteToolZipFromParts {
    param([Parameter(Mandatory)]$Spec, [Parameter(Mandatory)][string]$DownloadsDir, [string]$PartsDir, [scriptblock]$Logger)
    $entry = Get-ParkosLiteToolPartsEntry -PartsDir $PartsDir -Name $Spec.Name
    if (-not $entry) { return $null }
    if ($entry.archive -ne $Spec.FileName) {
        Write-ParkosDownloadLog -Logger $Logger -Message "  Las partes del repo de $($Spec.Label) son de otra version ($($entry.archive), el lite fija $($Spec.FileName)): se descarga."
        return $null
    }
    $staging = Join-Path $DownloadsDir '_parts'
    try {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $staging | Out-Null
        $restored = Restore-ParkosPayloadArtifact -Id $entry.id -PartsDir $PartsDir -PayloadRoot $staging -CacheDir $staging -Force -Logger $Logger
        $actual = Get-ParkosFileSha256 -Path $restored
        if ($actual -ne $Spec.Sha256.ToLowerInvariant()) {
            Write-ParkosDownloadLog -Logger $Logger -Message "  El zip de $($Spec.Label) rearmado desde el repo ($actual) no coincide con el sha256 fijado en el lite ($($Spec.Sha256)): se descarga."
            return $null
        }
        $target = Join-Path $DownloadsDir $Spec.FileName
        Move-Item -LiteralPath $restored -Destination $target -Force
        Write-ParkosDownloadLog -Logger $Logger -Message "  $($Spec.Label) $($Spec.Version) restaurado desde el repositorio (partes), sin descargar."
        return $target
    } catch {
        Write-ParkosDownloadLog -Logger $Logger -Message "  Las partes del repo de $($Spec.Label) no sirven ($($_.Exception.Message)): se descarga."
        return $null
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

# pnpm: restaura la carpeta portatil (tools\pnpm) desde las partes directamente
# bajo <LitePath> (el target del manifest es tools\pnpm). $true si quedo
# restaurada; $false si no hay partes o no sirven (se instala con npm).
function Restore-ParkosLitePnpmFromParts {
    param([Parameter(Mandatory)][string]$LitePath, [string]$PartsDir, [scriptblock]$Logger)
    $entry = Get-ParkosLiteToolPartsEntry -PartsDir $PartsDir -Name 'pnpm'
    if (-not $entry) { return $false }
    try {
        $tp = Get-ParkosLiteToolPaths -LitePath $LitePath
        [void](Restore-ParkosPayloadArtifact -Id $entry.id -PartsDir $PartsDir -PayloadRoot $LitePath -CacheDir $tp.Downloads -Force -Logger $Logger)
        Write-ParkosDownloadLog -Logger $Logger -Message '  pnpm restaurado desde el repositorio (partes), sin npm ni Internet.'
        return $true
    } catch {
        Write-ParkosDownloadLog -Logger $Logger -Message "  Las partes del repo de pnpm no sirven ($($_.Exception.Message)): se instala con npm."
        return $false
    }
}

# Orden: copia valida en la cache -> partes del repo -> descarga (.part + rename)
# y verifica sha256. 3 intentos con backoff; borra copias corruptas. El hash
# oficial (red) solo se consulta si hay que descargar.
function Get-ParkosLiteToolZip {
    param([Parameter(Mandatory)]$Spec, [Parameter(Mandatory)][string]$DownloadsDir, [string]$PartsDir, [scriptblock]$Logger, [int]$MaxAttempts = 3)
    New-Item -ItemType Directory -Force -Path $DownloadsDir | Out-Null
    $target = Join-Path $DownloadsDir $Spec.FileName
    $part = "$target.part"
    $pinned = $Spec.Sha256.ToLowerInvariant()

    if (Test-Path -LiteralPath $target) {
        if ((Get-ParkosFileSha256 -Path $target) -eq $pinned) { return $target }
        Write-ParkosDownloadLog -Logger $Logger -Message "  La copia en cache de $($Spec.FileName) no coincide con el hash esperado: se descarga de nuevo."
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    }
    if ($PartsDir) {
        $fromParts = Restore-ParkosLiteToolZipFromParts -Spec $Spec -DownloadsDir $DownloadsDir -PartsDir $PartsDir -Logger $Logger
        if ($fromParts) { return $fromParts }
    }
    $expected = Get-ParkosLiteExpectedHash -Spec $Spec
    $lastError = ''
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Invoke-ParkosHttpDownload -Url $Spec.Url -OutFile $part -Activity "Descargando $($Spec.Label) $($Spec.Version)"
            $actual = Get-ParkosFileSha256 -Path $part
            if ($actual -ne $expected) {
                Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
                throw "sha256 distinto al esperado (esperado $expected, obtenido $actual)"
            }
            Move-Item -LiteralPath $part -Destination $target -Force
            return $target
        } catch {
            $lastError = $_.Exception.Message
            Write-ParkosDownloadLog -Logger $Logger -Message "  Intento $attempt de $MaxAttempts fallo: $lastError"
            if ($attempt -lt $MaxAttempts) { Start-ParkosSleep -Seconds (Get-ParkosDownloadBackoffSeconds -Attempt $attempt) }
        }
    }
    throw (Get-ParkosDownloadFailureMessage -What "$($Spec.Label) portatil $($Spec.Version) (~$($Spec.SizeMb) MB)" -Url $Spec.Url -TargetDir $DownloadsDir -FileName $Spec.FileName -Detail "$lastError. Para reintentar: opcion 10 (Preparar entorno)")
}

# pnpm portatil con el npm de node (portatil o del sistema) en <tools>\pnpm.
function Install-ParkosLitePnpmPackage {
    param([Parameter(Mandatory)]$Spec, [Parameter(Mandatory)][string]$LitePath, [Parameter(Mandatory)][string]$NodePath, [scriptblock]$Logger, [int]$MaxAttempts = 3)
    $tp = Get-ParkosLiteToolPaths -LitePath $LitePath
    $npm = Join-Path (Split-Path $NodePath) 'npm.cmd'
    $prefix = Join-Path $tp.Tools $Spec.Dir
    New-Item -ItemType Directory -Force -Path $prefix, $tp.NpmCache | Out-Null
    $envMap = @{ PATH = ((Split-Path $NodePath) + ';' + (Get-ParkosLiteProcessEnvVar -Name 'PATH')) }
    $lastError = ''
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $r = Invoke-ParkosLiteNative -FilePath $npm -Arguments @('install', '-g', "pnpm@$($Spec.Version)", '--prefix', $prefix, '--cache', $tp.NpmCache, '--no-fund', '--no-audit') -Env $envMap
        if ($r.ExitCode -eq 0) { return }
        $lastError = ($r.Output | Select-Object -Last 3) -join ' '
        Write-ParkosDownloadLog -Logger $Logger -Message "  Intento $attempt de $MaxAttempts fallo (npm exit $($r.ExitCode)): $lastError"
        if ($attempt -lt $MaxAttempts) { Start-ParkosSleep -Seconds (Get-ParkosDownloadBackoffSeconds -Attempt $attempt) }
    }
    throw "No se pudo instalar pnpm $($Spec.Version) portatil (se necesita Internet SOLO en este paso).`n  Detalle : npm install fallo: $lastError`n  Fuente  : $($Spec.Url) (registro npm)`n  Que hacer: revisa la conexion o el proxy corporativo (npm_config_proxy / HTTPS_PROXY) y vuelve a correr la opcion 10 (Preparar entorno)."
}

# Instala UNA herramienta portatil. Devuelve 'YA ESTA' (valida en tools\) o
# 'INSTALADO'. Idempotente: valida con '<tool> --version' antes de nada.
# Orden de origen (con -PartsDir): partes del repo -> descarga/npm. Lo restaurado
# de las partes que no responda '--version' se descarta y se cae a la descarga.
function Install-ParkosLiteTool {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$LitePath, [string]$PartsDir, [scriptblock]$Logger)
    $spec = (Get-ParkosLiteToolSpecs)[$Name]
    $tp = Get-ParkosLiteToolPaths -LitePath $LitePath
    $loc = Get-ParkosLiteToolLocation -ToolsDir $tp.Tools -Spec $spec
    $probeEnv = Get-ParkosLiteToolEnv -LitePath $LitePath

    if (Test-Path -LiteralPath $loc.Exe) {
        $txt = Get-ParkosLiteToolVersionText -Path $loc.Exe -Env $probeEnv
        if (Test-ParkosLiteToolVersionCompatible -Tool $Name -VersionText $txt) { return 'YA ESTA' }
        Write-ParkosDownloadLog -Logger $Logger -Message "  La copia portatil de $($spec.Label) en $($loc.Root) no responde: se reinstala."
    }
    New-Item -ItemType Directory -Force -Path $tp.Tools | Out-Null

    $tryParts = [bool]$PartsDir
    while ($true) {
        $fromParts = $false
        if ($spec.Kind -eq 'npm') {
            if ($tryParts) { $fromParts = Restore-ParkosLitePnpmFromParts -LitePath $LitePath -PartsDir $PartsDir -Logger $Logger }
            if (-not $fromParts) {
                $nodePath = (Get-ParkosLiteToolStatus -LitePath $LitePath -Refresh)['node'].Path
                if (-not $nodePath) { throw 'No se puede instalar pnpm sin node (el paso de Node.js debe completarse primero).' }
                Install-ParkosLitePnpmPackage -Spec $spec -LitePath $LitePath -NodePath $nodePath -Logger $Logger
            }
        } else {
            $zip = Get-ParkosLiteToolZip -Spec $spec -DownloadsDir $tp.Downloads -PartsDir $PartsDir -Logger $Logger
            $tmp = Join-Path $tp.Tools "_extract-$Name"
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
            Expand-ParkosZipArchive -ZipPath $zip -Destination $tmp
            Move-ParkosLiteExtractedContent -Source $tmp -Destination $loc.Root
        }

        $txt = Get-ParkosLiteToolVersionText -Path $loc.Exe -Env (Get-ParkosLiteToolEnv -LitePath $LitePath)
        if (Test-ParkosLiteToolVersionCompatible -Tool $Name -VersionText $txt) { return 'INSTALADO' }
        if ($fromParts) {
            # Lo restaurado de las partes no responde: se reintenta una vez con npm.
            Write-ParkosDownloadLog -Logger $Logger -Message "  El pnpm restaurado del repo no responde '--version': se instala con npm."
            $tryParts = $false
            continue
        }
        throw "$($spec.Label) se extrajo en $($loc.Root) pero '$($loc.Exe) --version' no responde una version valida (antivirus o descarga corrupta). Borra $($loc.Root) y el zip de $($tp.Downloads), y reintenta la opcion 10."
    }
}

# ---------------------------------------------------------------------------
# Orquestacion (paso 10) y presentacion
# ---------------------------------------------------------------------------

function Get-ParkosLiteToolInstallMessage {
    param([Parameter(Mandatory)]$Spec)
    return ("Instalando {0} portatil ({1}, ~{2} MB)..." -f $Spec.Label, $Spec.Version, $Spec.SizeMb)
}

# Lineas "OK / YA ESTA / INSTALADO" y resumen con version y origen.
function Format-ParkosLiteToolLines {
    param([Parameter(Mandatory)]$Status, [hashtable]$Outcome = @{})
    $lines = @()
    foreach ($name in (Get-ParkosLiteToolNames)) {
        $s = $Status[$name]
        if ($s.Origin -eq 'missing') { $lines += ('  [FALTA]     {0,-5} (no instalado)' -f $name); continue }
        $tag = '[ OK ]    '
        if ($Outcome[$name] -eq 'YA ESTA') { $tag = '[YA ESTA]  ' } elseif ($Outcome[$name] -eq 'INSTALADO') { $tag = '[INSTALADO]' }
        $origin = 'sistema'
        if ($s.Origin -eq 'portable') { $origin = 'portatil' }
        $lines += ('  {0} {1,-5} {2,-9} {3}' -f $tag, $name, $s.Version, $origin)
    }
    return $lines
}

# Herramientas que faltan (ni compatibles en el sistema ni portatiles validas).
function Get-ParkosLiteMissingTools {
    param([string]$LitePath)
    if (-not $LitePath) { $LitePath = Get-ParkosLiteDefaultPath }
    $status = Get-ParkosLiteToolStatus -LitePath $LitePath
    $missing = @()
    foreach ($name in (Get-ParkosLiteToolNames)) {
        if ($status[$name].Origin -eq 'missing') {
            $missing += [PSCustomObject]@{ Name = $name; Hint = 'la opcion 10 (Preparar entorno) la instala sola, portatil' }
        }
    }
    return $missing
}

# Garantiza las 4 herramientas (sistema compatible o portatil; esta ultima sale de
# las partes del repo si hay, si no se descarga), activa el PATH
# del proceso y devuelve el estado final. Orden: git, uv, node, pnpm (pnpm usa npm).
function Install-ParkosLiteToolchain {
    param([Parameter(Mandatory)][string]$LitePath, [string]$PartsDir, [scriptblock]$Logger)
    $specs = Get-ParkosLiteToolSpecs
    $outcome = @{}
    foreach ($name in (Get-ParkosLiteToolNames)) {
        $status = Get-ParkosLiteToolStatus -LitePath $LitePath -Refresh
        if ($status[$name].Origin -ne 'missing') {
            $outcome[$name] = 'YA ESTA'
            continue
        }
        Write-ParkosDownloadLog -Logger $Logger -Message (Get-ParkosLiteToolInstallMessage -Spec $specs[$name])
        $outcome[$name] = Install-ParkosLiteTool -Name $name -LitePath $LitePath -PartsDir $PartsDir -Logger $Logger
        Enable-ParkosLiteToolchainEnv -LitePath $LitePath -Refresh | Out-Null
    }
    $final = Enable-ParkosLiteToolchainEnv -LitePath $LitePath -Refresh
    foreach ($l in (Format-ParkosLiteToolLines -Status $final -Outcome $outcome)) { Write-ParkosDownloadLog -Logger $Logger -Message $l }
    return @{ Status = $final; Outcome = $outcome }
}
