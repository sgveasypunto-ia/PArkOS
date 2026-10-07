# Tests del pre-flight del runtime de Visual C++ para los binarios de Postgres
# del lite (Assert-ParkosLitePgRuntime). Ningun proceso real se ejecuta: la sonda
# (Invoke-ParkosLiteProbe) y la carpeta de sistema se mockean; los DLL son
# archivos de prueba en TestDrive.

. (Join-Path $PSScriptRoot '..\shared\ParkosPostgresDownload.ps1')
. (Join-Path $PSScriptRoot '..\shared\ParkosPayloadParts.ps1')
. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Db.ps1')

$script:dlls = @('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll')

function New-RuntimeFixture {
    param([string]$Name, [string[]]$InSystem = $script:dlls, [string[]]$InBin = @())
    $root = Join-Path $TestDrive $Name
    $sys = Join-Path $root 'System32'
    $pg = Join-Path $root 'pgsql'
    New-Item -ItemType Directory -Force -Path $sys, (Join-Path $pg 'bin') | Out-Null
    foreach ($d in $InSystem) { Set-Content (Join-Path $sys $d) "sys-$d" }
    foreach ($d in $InBin) { Set-Content (Join-Path $pg "bin\$d") "bin-$d" }
    return @{ Sys = $sys; Pg = $pg }
}

$global:bad = @{ ExitCode = -1058471934; TimedOut = $false; Output = @('LIBPQ.dll no esta disenado para ejecutarse en Windows') }
$global:good = @{ ExitCode = 0; TimedOut = $false; Output = @('initdb (PostgreSQL) 16.15') }

Describe 'Assert-ParkosLitePgRuntime' {
    BeforeEach {
        $script:msgs = @()
        $script:logger = { param($m) $script:msgs += $m }
        $global:probeCalls = 0
    }
    It 'initdb --version funciona: no copia nada' {
        $fx = New-RuntimeFixture 'ok'
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; $global:good }
        Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger
        $global:probeCalls | Should Be 1
        (Test-Path (Join-Path $fx.Pg 'bin\vcruntime140.dll')) | Should Be $false
    }
    It 'exit 0xC0E90002: copia solo los DLL que faltan, sin sobrescribir, y reintenta una vez' {
        $fx = New-RuntimeFixture 'bad' -InBin @('msvcp140.dll')
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; if ($global:probeCalls -eq 1) { $global:bad } else { $global:good } }
        Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger
        $global:probeCalls | Should Be 2
        foreach ($d in $script:dlls) { (Test-Path (Join-Path $fx.Pg "bin\$d")) | Should Be $true }
        (Get-Content (Join-Path $fx.Pg 'bin\msvcp140.dll') -Raw).Trim() | Should Be 'bin-msvcp140.dll'
        (Get-Content (Join-Path $fx.Pg 'bin\vcruntime140.dll') -Raw).Trim() | Should Be 'sys-vcruntime140.dll'
        ($script:msgs -join "`n") | Should Match 'Visual C\+\+'
    }
    It 'tambien reconoce el codigo sin signo (3236495362)' {
        $fx = New-RuntimeFixture 'unsigned'
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; if ($global:probeCalls -eq 1) { @{ ExitCode = 3236495362; TimedOut = $false; Output = @() } } else { $global:good } }
        Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger
        $global:probeCalls | Should Be 2
    }
    It 'la sonda se cuelga (timeout): trata como runtime roto, copia y reintenta' {
        $fx = New-RuntimeFixture 'hang'
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; if ($global:probeCalls -eq 1) { @{ ExitCode = -1; TimedOut = $true; Output = @() } } else { $global:good } }
        Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger
        $global:probeCalls | Should Be 2
        (Test-Path (Join-Path $fx.Pg 'bin\vcruntime140_1.dll')) | Should Be $true
    }
    It 'los DLL no estan en System32: mensaje accionable con el redistribuible de Microsoft y falla limpio (sin reintento)' {
        $fx = New-RuntimeFixture 'nodll' -InSystem @()
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; $global:bad }
        { Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger } | Should Throw 'Microsoft Visual C++ Redistributable 2015-2022 x64'
        $global:probeCalls | Should Be 1
    }
    It 'se copiaron los DLL pero sigue fallando: mensaje con el codigo y el redistribuible' {
        $fx = New-RuntimeFixture 'still'
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; $global:bad }
        { Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger } | Should Throw 'aka.ms/vs/17/release/vc_redist.x64.exe'
        $global:probeCalls | Should Be 2
    }
    It 'otro error de initdb --version (no es el runtime): no toca nada y no bloquea' {
        $fx = New-RuntimeFixture 'other'
        Mock Get-ParkosLiteSystemDir { $fx.Sys }
        Mock Invoke-ParkosLiteProbe { $global:probeCalls++; @{ ExitCode = 1; TimedOut = $false; Output = @('boom') } }
        Assert-ParkosLitePgRuntime -PgRoot $fx.Pg -Logger $script:logger
        $global:probeCalls | Should Be 1
        (Test-Path (Join-Path $fx.Pg 'bin\vcruntime140.dll')) | Should Be $false
    }
}

Describe 'Invoke-ParkosLiteProbe (proceso real, inofensivo)' {
    It 'devuelve el codigo de salida de un proceso corto' {
        $r = Invoke-ParkosLiteProbe -FilePath "$env:SystemRoot\System32\cmd.exe" -Arguments @('/c', 'exit 7') -TimeoutSec 20
        $r.ExitCode | Should Be 7
        $r.TimedOut | Should Be $false
    }
    It 'mata el proceso y marca TimedOut si no termina a tiempo' {
        $r = Invoke-ParkosLiteProbe -FilePath "$env:SystemRoot\System32\cmd.exe" -Arguments @('/c', 'ping -n 30 127.0.0.1 >nul') -TimeoutSec 2
        $r.TimedOut | Should Be $true
    }
    It 'un ejecutable inexistente no lanza: ExitCode -1' {
        $r = Invoke-ParkosLiteProbe -FilePath (Join-Path $TestDrive 'no-existe.exe') -Arguments @() -TimeoutSec 5
        $r.ExitCode | Should Be -1
    }
}

