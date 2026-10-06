# Tests de installer/lite/ParkosLite.Tools.ps1: toolchain portatil (git, uv,
# node, pnpm) en <lite>\tools. Red, zip, procesos, PATH y carpetas pasan por
# wrappers que se mockean aqui; nada real se ejecuta ni se descarga.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Core.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Tools.ps1')

$script:quiet = { param($m) }
$script:toolsSource = Join-Path $PSScriptRoot '..\lite\ParkosLite.Tools.ps1'

Describe 'versiones y compatibilidad' {
    It 'parsea la primera version X.Y.Z del texto de --version' {
        (ConvertTo-ParkosLiteVersion -Text 'v22.23.3').ToString() | Should Be '22.23.3'
        (ConvertTo-ParkosLiteVersion -Text 'git version 2.56.0.windows.2').ToString() | Should Be '2.56.0'
        (ConvertTo-ParkosLiteVersion -Text 'uv 0.12.23 (46b84fd0b 2026-10-03 x86_64-pc-windows-msvc)').ToString() | Should Be '0.12.23'
        (ConvertTo-ParkosLiteVersion -Text 'basura') | Should BeNullOrEmpty
        (ConvertTo-ParkosLiteVersion -Text '') | Should BeNullOrEmpty
    }
    It 'node: >= 20 compatible, 18 no' {
        (Test-ParkosLiteToolVersionCompatible -Tool 'node' -VersionText 'v20.0.0') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'node' -VersionText 'v22.23.3') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'node' -VersionText 'v18.19.1') | Should Be $false
    }
    It 'pnpm: >= 10 compatible, 9 no' {
        (Test-ParkosLiteToolVersionCompatible -Tool 'pnpm' -VersionText '10.0.0') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'pnpm' -VersionText '10.4.1') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'pnpm' -VersionText '9.15.0') | Should Be $false
    }
    It 'uv y git: cualquier version reciente; texto ilegible no es compatible' {
        (Test-ParkosLiteToolVersionCompatible -Tool 'uv' -VersionText 'uv 0.12.23') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'uv' -VersionText 'uv 0.1.0') | Should Be $false
        (Test-ParkosLiteToolVersionCompatible -Tool 'git' -VersionText 'git version 2.43.0.windows.1') | Should Be $true
        (Test-ParkosLiteToolVersionCompatible -Tool 'git' -VersionText $null) | Should Be $false
        (Test-ParkosLiteToolVersionCompatible -Tool 'desconocida' -VersionText '1.0.0') | Should Be $false
    }
}

Describe 'tabla de versiones fijadas' {
    $specs = Get-ParkosLiteToolSpecs
    It 'trae las cuatro herramientas con version, URL https y tamano' {
        foreach ($n in 'git', 'uv', 'node', 'pnpm') {
            $specs[$n].Version | Should Match '^\d+\.\d+\.\d+'
            $specs[$n].Url | Should Match '^https://'
            ($specs[$n].SizeMb -gt 0) | Should Be $true
        }
    }
    It 'las URLs de zip contienen la version fijada y el hash fijado es sha256 hex' {
        foreach ($n in 'git', 'uv', 'node') {
            $specs[$n].Url | Should Match ([regex]::Escape($specs[$n].Version))
            $specs[$n].Sha256 | Should Match '^[0-9a-f]{64}$'
        }
        $specs.node.Url | Should Match 'nodejs.org/dist/'
        $specs.uv.Url | Should Match 'github.com/astral-sh/uv/releases/download/'
        $specs.git.Url | Should Match 'MinGit-.*-64-bit.zip'
        $specs.node.HashUrl | Should Match 'SHASUMS256.txt'
        $specs.uv.HashUrl | Should Match '\.sha256$'
    }
    It 'node fijado es LTS >= 20 y pnpm coincide con packageManager de apps/package.json' {
        ([version]$specs.node.Version -ge [version]'20.0.0') | Should Be $true
        $pkg = Get-Content (Join-Path $PSScriptRoot '..\..\apps\package.json') -Raw | ConvertFrom-Json
        $pkg.packageManager | Should Be "pnpm@$($specs.pnpm.Version)"
    }
    It 'el mensaje de instalacion dice que instala y cuanto pesa' {
        (Get-ParkosLiteToolInstallMessage -Spec $specs.node) | Should Match 'Instalando Node.js portatil \(22\.\d+\.\d+, ~30 MB\)'
    }
}

Describe 'Get-ParkosLiteToolStatus (PATH-first vs portatil)' {
    function New-FakePortable { param($Lite, $Name)
        $spec = (Get-ParkosLiteToolSpecs)[$Name]
        $loc = Get-ParkosLiteToolLocation -ToolsDir (Join-Path $Lite 'tools') -Spec $spec
        New-Item -ItemType Directory -Force -Path (Split-Path $loc.Exe) | Out-Null
        Set-Content -Path $loc.Exe -Value 'x'
        return $loc.Exe
    }
    BeforeEach { Mock Get-ParkosLiteProcessEnvVar { 'C:\Windows' } }

    It 'usa la del sistema si es compatible (aunque haya portatil)' {
        $lite = Join-Path $TestDrive 'st1'
        New-FakePortable -Lite $lite -Name 'node' | Out-Null
        Mock Get-ParkosLiteSystemToolPath { param($Name) "C:\sys\$Name.exe" }
        Mock Get-ParkosLiteToolVersionText { param($Path) if ($Path -like '*node*') { 'v22.1.0' } elseif ($Path -like '*uv*') { 'uv 0.9.0' } elseif ($Path -like '*pnpm*') { '10.2.0' } else { 'git version 2.40.0.windows.1' } }
        $s = Get-ParkosLiteToolStatus -LitePath $lite -Refresh
        $s.node.Origin | Should Be 'system'
        $s.node.Version | Should Be '22.1.0'
        $s.git.Origin | Should Be 'system'
    }
    It 'sistema con node 18 incompatible y portatil valida -> portable' {
        $lite = Join-Path $TestDrive 'st2'
        $exe = New-FakePortable -Lite $lite -Name 'node'
        Mock Get-ParkosLiteSystemToolPath { param($Name) if ($Name -eq 'node') { 'C:\sys\node.exe' } else { $null } }
        Mock Get-ParkosLiteToolVersionText { param($Path) if ($Path -eq 'C:\sys\node.exe') { 'v18.19.0' } else { 'v22.23.3' } }
        $s = Get-ParkosLiteToolStatus -LitePath $lite -Refresh
        $s.node.Origin | Should Be 'portable'
        $s.node.Path | Should Be $exe
        $s.uv.Origin | Should Be 'missing'
    }
    It 'sin sistema ni portatil -> missing; portatil que no responde -> missing' {
        $lite = Join-Path $TestDrive 'st3'
        New-FakePortable -Lite $lite -Name 'uv' | Out-Null
        Mock Get-ParkosLiteSystemToolPath { $null }
        Mock Get-ParkosLiteToolVersionText { $null }
        $s = Get-ParkosLiteToolStatus -LitePath $lite -Refresh
        foreach ($n in 'git', 'uv', 'node', 'pnpm') { $s[$n].Origin | Should Be 'missing' }
    }
    It 'Get-ParkosLiteMissingTools lista solo lo que falta' {
        $lite = Join-Path $TestDrive 'st4'
        Mock Get-ParkosLiteSystemToolPath { param($Name) if ($Name -eq 'uv') { $null } else { "C:\sys\$Name.exe" } }
        Mock Get-ParkosLiteToolVersionText { param($Path) if ($Path -like '*node*') { 'v22.1.0' } elseif ($Path -like '*pnpm*') { '10.2.0' } else { 'git version 2.40.0.windows.1' } }
        Get-ParkosLiteToolStatus -LitePath $lite -Refresh | Out-Null
        $m = @(Get-ParkosLiteMissingTools -LitePath $lite)
        $m.Count | Should Be 1
        $m[0].Name | Should Be 'uv'
        $m[0].Hint | Should Match 'opcion 10'
        $m[0].Hint | Should Not Match 'winget'
    }
}

Describe 'Get-ParkosLiteToolEnv (entorno de los hijos)' {
    BeforeEach { Mock Get-ParkosLiteProcessEnvVar { 'C:\Windows\System32;C:\Windows' } }
    $status = [ordered]@{
        git  = @{ Name = 'git'; Origin = 'portable'; Version = '2.56.0'; Path = 'x' }
        uv   = @{ Name = 'uv'; Origin = 'portable'; Version = '0.12.23'; Path = 'x' }
        node = @{ Name = 'node'; Origin = 'system'; Version = '22.1.0'; Path = 'x' }
        pnpm = @{ Name = 'pnpm'; Origin = 'portable'; Version = '10.0.0'; Path = 'x' }
    }
    It 'antepone las carpetas portatiles al PATH (y solo las portatiles)' {
        $e = Get-ParkosLiteToolEnv -LitePath 'C:\L' -Status $status
        $parts = $e.PATH -split ';'
        $parts[0] | Should Be 'C:\L\tools\git\cmd'
        $parts[1] | Should Be 'C:\L\tools\uv'
        $parts[2] | Should Be 'C:\L\tools\pnpm'
        ($parts -contains 'C:\L\tools\node') | Should Be $false
        $parts[-1] | Should Be 'C:\Windows'
    }
    It 'uv portatil: cache y Python de uv bajo <lite>\tools; pnpm: store, home y cache npm' {
        $e = Get-ParkosLiteToolEnv -LitePath 'C:\L' -Status $status
        $e.UV_CACHE_DIR | Should Be 'C:\L\tools\cache\uv'
        $e.UV_PYTHON_INSTALL_DIR | Should Be 'C:\L\tools\cache\uv-python'
        $e.UV_PYTHON_BIN_DIR | Should Be 'C:\L\tools\cache\uv-bin'
        $e.PNPM_HOME | Should Be 'C:\L\tools\cache\pnpm-home'
        $e.npm_config_store_dir | Should Be 'C:\L\tools\cache\pnpm-store'
        $e.npm_config_cache | Should Be 'C:\L\tools\cache\npm'
    }
    It 'si todo es del sistema no agrega nada global (PATH intacto, sin variables)' {
        $all = [ordered]@{}
        foreach ($n in 'git', 'uv', 'node', 'pnpm') { $all[$n] = @{ Name = $n; Origin = 'system'; Version = '1.0.0'; Path = 'x' } }
        $e = Get-ParkosLiteToolEnv -LitePath 'C:\L' -Status $all
        $e.PATH | Should Be 'C:\Windows\System32;C:\Windows'
        $e.ContainsKey('UV_CACHE_DIR') | Should Be $false
        $e.ContainsKey('PNPM_HOME') | Should Be $false
    }
    It 'es idempotente: no duplica tools\ si ya estaba en el PATH' {
        Mock Get-ParkosLiteProcessEnvVar { 'C:\L\tools\git\cmd;C:\L\tools\uv;C:\Windows' }
        $e = Get-ParkosLiteToolEnv -LitePath 'C:\L' -Status $status
        @($e.PATH -split ';' | Where-Object { $_ -eq 'C:\L\tools\uv' }).Count | Should Be 1
    }
}

Describe 'sin tocar el PATH/registro de Maquina o Usuario' {
    It 'Enable-ParkosLiteToolchainEnv solo escribe por el wrapper de ambito Process' {
        Mock Get-ParkosLiteProcessEnvVar { 'C:\Windows' }
        Mock Get-ParkosLiteToolStatus {
            $s = [ordered]@{}
            foreach ($n in 'git', 'uv', 'node', 'pnpm') { $s[$n] = @{ Name = $n; Origin = 'portable'; Version = '1.0.0'; Path = 'x' } }
            return $s
        }
        Mock Set-ParkosLiteProcessEnvVar { }
        Enable-ParkosLiteToolchainEnv -LitePath 'C:\L' | Out-Null
        Assert-MockCalled Set-ParkosLiteProcessEnvVar -ParameterFilter { $Name -eq 'PATH' -and $Value -like 'C:\L\tools\git\cmd;*' } -Times 1 -Scope It
        Assert-MockCalled Set-ParkosLiteProcessEnvVar -ParameterFilter { $Name -eq 'UV_PYTHON_INSTALL_DIR' } -Times 1 -Scope It
    }
    It 'el codigo fuente solo usa SetEnvironmentVariable con ambito Process y nunca toca el registro' {
        $code = @(Get-Content $script:toolsSource | Where-Object { $_.Trim() -notmatch '^#' })
        $calls = @($code | Where-Object { $_ -match 'SetEnvironmentVariable' })
        $calls.Count | Should Be 1
        $calls[0] | Should Match "'Process'"
        ($code -join "`n") | Should Not Match "'(Machine|User)'"
        ($code -join "`n") | Should Not Match 'EnvironmentVariableTarget|HKLM:|HKCU:|setx|winget'
    }
}

Describe 'Get-ParkosLiteExpectedHash' {
    It 'sin HashUrl devuelve el fijado' {
        $spec = @{ Name = 'git'; Sha256 = ('A' * 64); HashUrl = ''; FileName = 'f.zip'; Url = 'https://x/f.zip' }
        Get-ParkosLiteExpectedHash -Spec $spec | Should Be ('a' * 64)
    }
    It 'si el hash oficial coincide con el fijado, ok (formato SHASUMS)' {
        $spec = @{ Name = 'node'; Sha256 = ('b' * 64); HashUrl = 'https://x/SHASUMS256.txt'; FileName = 'node.zip'; Url = 'https://x/node.zip' }
        Mock Get-ParkosLiteRemoteText { ('c' * 64) + "  otro.zip`n" + ('b' * 64) + "  node.zip`n" }
        Get-ParkosLiteExpectedHash -Spec $spec | Should Be ('b' * 64)
    }
    It 'si el hash oficial NO coincide con el fijado, falla' {
        $spec = @{ Name = 'uv'; Sha256 = ('b' * 64); HashUrl = 'https://x/u.sha256'; FileName = 'uv.zip'; Url = 'https://x/uv.zip' }
        Mock Get-ParkosLiteRemoteText { ('d' * 64) + "  uv.zip`n" }
        { Get-ParkosLiteExpectedHash -Spec $spec } | Should Throw 'no coincide con el fijado'
    }
    It 'si el hash oficial no se puede leer (offline) usa el fijado' {
        $spec = @{ Name = 'uv'; Sha256 = ('b' * 64); HashUrl = 'https://x/u.sha256'; FileName = 'uv.zip'; Url = 'https://x/uv.zip' }
        Mock Get-ParkosLiteRemoteText { throw 'sin red' }
        Get-ParkosLiteExpectedHash -Spec $spec | Should Be ('b' * 64)
    }
}

Describe 'Get-ParkosLiteToolZip (descarga + sha256)' {
    BeforeEach {
        $script:spec = @{ Name = 'node'; Label = 'Node.js'; Version = '22.0.0'; SizeMb = 30; Url = 'https://example.test/node.zip'; FileName = 'node.zip'; Sha256 = ('a' * 64); HashUrl = '' }
        Mock Start-ParkosSleep { }
        Mock Invoke-ParkosHttpDownload { param($Url, $OutFile) Set-Content -Path $OutFile -Value 'zip' }
    }
    It 'descarga a .part, verifica y renombra al zip final' {
        Mock Get-ParkosFileSha256 { 'a' * 64 }
        $dl = Join-Path $TestDrive 'dl1'
        $zip = Get-ParkosLiteToolZip -Spec $script:spec -DownloadsDir $dl -Logger $script:quiet
        $zip | Should Be (Join-Path $dl 'node.zip')
        (Test-Path $zip) | Should Be $true
        (Test-Path "$zip.part") | Should Be $false
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 1 -Scope It
    }
    It 'reutiliza una copia valida de la cache sin descargar' {
        Mock Get-ParkosFileSha256 { 'a' * 64 }
        $dl = Join-Path $TestDrive 'dl2'
        New-Item -ItemType Directory -Force -Path $dl | Out-Null
        Set-Content (Join-Path $dl 'node.zip') 'ya'
        Get-ParkosLiteToolZip -Spec $script:spec -DownloadsDir $dl -Logger $script:quiet | Out-Null
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 0 -Scope It
    }
    It 'una copia en cache corrupta se borra y se descarga de nuevo' {
        $script:calls = 0
        Mock Get-ParkosFileSha256 { $script:calls++; if ($script:calls -eq 1) { 'f' * 64 } else { 'a' * 64 } }
        $dl = Join-Path $TestDrive 'dl3'
        New-Item -ItemType Directory -Force -Path $dl | Out-Null
        Set-Content (Join-Path $dl 'node.zip') 'corrupto'
        Get-ParkosLiteToolZip -Spec $script:spec -DownloadsDir $dl -Logger $script:quiet | Out-Null
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 1 -Scope It
    }
    It 'hash distinto en 3 intentos: borra el .part, reintenta con backoff y falla con URL, carpeta y como reintentar' {
        Mock Get-ParkosFileSha256 { '0' * 64 }
        $dl = Join-Path $TestDrive 'dl4'
        $err = ''
        try { Get-ParkosLiteToolZip -Spec $script:spec -DownloadsDir $dl -Logger $script:quiet } catch { $err = $_.Exception.Message }
        $err | Should Match 'https://example.test/node.zip'
        $err | Should Match ([regex]::Escape((Join-Path $dl 'node.zip')))
        $err | Should Match 'opcion 10'
        $err | Should Match 'Internet SOLO'
        $err | Should Match 'sha256 distinto'
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 3 -Scope It
        Assert-MockCalled Start-ParkosSleep -Times 2 -Scope It
        (Test-Path (Join-Path $dl 'node.zip.part')) | Should Be $false
        (Test-Path (Join-Path $dl 'node.zip')) | Should Be $false
    }
    It 'sin red: 3 intentos y mensaje accionable' {
        Mock Invoke-ParkosHttpDownload { throw 'No es posible conectar' }
        $dl = Join-Path $TestDrive 'dl5'
        { Get-ParkosLiteToolZip -Spec $script:spec -DownloadsDir $dl -Logger $script:quiet } | Should Throw 'No es posible conectar'
        Assert-MockCalled Invoke-ParkosHttpDownload -Times 3 -Scope It
    }
}

Describe 'Install-ParkosLiteTool' {
    BeforeEach {
        Mock Get-ParkosLiteProcessEnvVar { 'C:\Windows' }
        Mock Start-ParkosSleep { }
    }
    It 'idempotente: si tools\<tool> ya es valida no descarga ni extrae (YA ESTA)' {
        $lite = Join-Path $TestDrive 'ins1'
        $loc = Get-ParkosLiteToolLocation -ToolsDir (Join-Path $lite 'tools') -Spec (Get-ParkosLiteToolSpecs).uv
        New-Item -ItemType Directory -Force -Path (Split-Path $loc.Exe) | Out-Null
        Set-Content $loc.Exe 'x'
        Mock Get-ParkosLiteToolVersionText { 'uv 0.12.23' }
        Mock Get-ParkosLiteToolZip { throw 'no deberia descargar' }
        Mock Expand-ParkosZipArchive { }
        Install-ParkosLiteTool -Name 'uv' -LitePath $lite -Logger $script:quiet | Should Be 'YA ESTA'
        Assert-MockCalled Get-ParkosLiteToolZip -Times 0 -Scope It
        Assert-MockCalled Expand-ParkosZipArchive -Times 0 -Scope It
    }
    It 'zip: descarga, extrae a temp, mueve a tools\<tool> y verifica con --version (INSTALADO)' {
        $lite = Join-Path $TestDrive 'ins2'
        $script:placed = $false
        Mock Get-ParkosLiteToolZip { 'C:\cache\uv.zip' }
        Mock Expand-ParkosZipArchive { param($ZipPath, $Destination) New-Item -ItemType Directory -Force -Path $Destination | Out-Null }
        Mock Move-ParkosLiteExtractedContent { param($Source, $Destination) New-Item -ItemType Directory -Force -Path $Destination | Out-Null; Set-Content (Join-Path $Destination 'uv.exe') 'x'; $script:placed = $true }
        Mock Get-ParkosLiteToolVersionText { if ($script:placed) { 'uv 0.12.23' } else { $null } }
        Install-ParkosLiteTool -Name 'uv' -LitePath $lite -Logger $script:quiet | Should Be 'INSTALADO'
        Assert-MockCalled Get-ParkosLiteToolZip -Times 1 -Scope It
        Assert-MockCalled Move-ParkosLiteExtractedContent -ParameterFilter { $Destination -eq (Join-Path $lite 'tools\uv') } -Times 1 -Scope It
    }
    It 'si tras extraer --version no responde, falla con mensaje claro' {
        $lite = Join-Path $TestDrive 'ins3'
        Mock Get-ParkosLiteToolZip { 'C:\cache\uv.zip' }
        Mock Expand-ParkosZipArchive { param($Destination) New-Item -ItemType Directory -Force -Path $Destination | Out-Null }
        Mock Move-ParkosLiteExtractedContent { param($Destination) New-Item -ItemType Directory -Force -Path $Destination | Out-Null }
        Mock Get-ParkosLiteToolVersionText { $null }
        { Install-ParkosLiteTool -Name 'uv' -LitePath $lite -Logger $script:quiet } | Should Throw 'no responde una version valida'
    }
    It 'pnpm usa el npm.cmd junto a node con --prefix en tools\pnpm' {
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 0; Output = @('ok') } }
        $spec = (Get-ParkosLiteToolSpecs).pnpm
        Install-ParkosLitePnpmPackage -Spec $spec -LitePath (Join-Path $TestDrive 'ins4') -NodePath 'C:\L\tools\node\node.exe' -Logger $script:quiet
        Assert-MockCalled Invoke-ParkosLiteNative -ParameterFilter { $FilePath -eq 'C:\L\tools\node\npm.cmd' -and ($Arguments -contains 'pnpm@10.0.0') -and ($Arguments -contains '--prefix') } -Times 1 -Scope It
    }
    It 'pnpm: si npm falla 3 veces explica como reintentar' {
        Mock Invoke-ParkosLiteNative { @{ ExitCode = 1; Output = @('ENOTFOUND registry.npmjs.org') } }
        $spec = (Get-ParkosLiteToolSpecs).pnpm
        { Install-ParkosLitePnpmPackage -Spec $spec -LitePath (Join-Path $TestDrive 'ins5') -NodePath 'C:\n\node.exe' -Logger $script:quiet } | Should Throw 'opcion 10'
        Assert-MockCalled Invoke-ParkosLiteNative -Times 3 -Scope It
    }
}

Describe 'Install-ParkosLiteToolchain (paso 10)' {
    It 'sin ninguna herramienta instala las 4 en orden git, uv, node, pnpm' {
        $script:order = @()
        $missing = [ordered]@{}
        foreach ($n in 'git', 'uv', 'node', 'pnpm') { $missing[$n] = @{ Name = $n; Origin = 'missing'; Version = ''; Path = '' } }
        Mock Get-ParkosLiteToolStatus { $missing }
        Mock Install-ParkosLiteTool { param($Name) $script:order += $Name; 'INSTALADO' }
        Mock Enable-ParkosLiteToolchainEnv { $missing }
        $r = Install-ParkosLiteToolchain -LitePath 'C:\L' -Logger $script:quiet
        ($script:order -join ',') | Should Be 'git,uv,node,pnpm'
        $r.Outcome.node | Should Be 'INSTALADO'
    }
    It 'con todo compatible en el sistema no instala nada (YA ESTA)' {
        $ok = [ordered]@{}
        foreach ($n in 'git', 'uv', 'node', 'pnpm') { $ok[$n] = @{ Name = $n; Origin = 'system'; Version = '99.0.0'; Path = 'x' } }
        Mock Get-ParkosLiteToolStatus { $ok }
        Mock Install-ParkosLiteTool { throw 'no deberia instalar' }
        Mock Enable-ParkosLiteToolchainEnv { $ok }
        $r = Install-ParkosLiteToolchain -LitePath 'C:\L' -Logger $script:quiet
        $r.Outcome.git | Should Be 'YA ESTA'
        Assert-MockCalled Install-ParkosLiteTool -Times 0 -Scope It
    }
    It 'anuncia lo que instala y resume version y origen' {
        $script:logs = @()
        $st = [ordered]@{
            git  = @{ Name = 'git'; Origin = 'system'; Version = '2.43.0'; Path = 'x' }
            uv   = @{ Name = 'uv'; Origin = 'portable'; Version = '0.12.23'; Path = 'x' }
            node = @{ Name = 'node'; Origin = 'portable'; Version = '22.23.3'; Path = 'x' }
            pnpm = @{ Name = 'pnpm'; Origin = 'missing'; Version = ''; Path = '' }
        }
        $lines = Format-ParkosLiteToolLines -Status $st -Outcome @{ git = 'YA ESTA'; uv = 'INSTALADO'; node = 'YA ESTA' }
        ($lines -join "`n") | Should Match 'YA ESTA\]\s+git\s+2.43.0\s+sistema'
        ($lines -join "`n") | Should Match 'INSTALADO\]\s+uv\s+0.12.23\s+portatil'
        ($lines -join "`n") | Should Match 'FALTA\]\s+pnpm'
    }
}

Describe 'Move-ParkosLiteExtractedContent' {
    It 'aplana la unica carpeta raiz (como node-vX-win-x64) en el destino' {
        $src = Join-Path $TestDrive 'mv1\tmp'
        $root = Join-Path $src 'node-v22-win-x64'
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        Set-Content (Join-Path $root 'node.exe') 'x'
        $dst = Join-Path $TestDrive 'mv1\tools\node'
        Move-ParkosLiteExtractedContent -Source $src -Destination $dst
        (Test-Path (Join-Path $dst 'node.exe')) | Should Be $true
        (Test-Path $src) | Should Be $false
    }
    It 'zip plano (varias entradas): el contenido pasa tal cual' {
        $src = Join-Path $TestDrive 'mv2\tmp'
        New-Item -ItemType Directory -Force -Path (Join-Path $src 'cmd') | Out-Null
        Set-Content (Join-Path $src 'a.txt') 'x'
        $dst = Join-Path $TestDrive 'mv2\tools\git'
        Move-ParkosLiteExtractedContent -Source $src -Destination $dst
        (Test-Path (Join-Path $dst 'cmd')) | Should Be $true
        (Test-Path (Join-Path $dst 'a.txt')) | Should Be $true
    }
}

Describe 'compatibilidad de state.json' {
    It 'un state.json viejo (sin claves nuevas) carga y el paso env depende solo de las herramientas' {
        $f = Join-Path $TestDrive 'state-old.json'
        Set-Content $f '{"sucursal_uuid":"","db_port":5433,"api_port":8100,"front_port":5173,"source_branch":"dev","api_built_commit":"abc","steps":{"env":"ok"}}'
        $st = Read-ParkosLiteState -Path $f
        $st.db_port | Should Be 5433
        $st.steps.env | Should Be 'ok'
        $facts = @{ ToolsMissing = @(); PgInstalled = $false; PgInitialized = $false; ApiBuilt = $false; MigrateBuilt = $false; DbReady = $false; SchemaMigrated = $false; Seeded = $false; FrontInstalled = $false }
        (Get-ParkosLiteStepStatus -State $st -Facts $facts).env | Should Be 'ok'
        $facts.ToolsMissing = @('node')
        (Get-ParkosLiteStepStatus -State $st -Facts $facts).env | Should Be 'pending'
    }
}
