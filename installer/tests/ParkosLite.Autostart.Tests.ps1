# Tests de installer/lite/ParkosLite.Autostart.ps1: arranque automatico de la
# base de datos lite (tarea programada por usuario, HKCU Run como fallback y
# servicio de Windows solo si el TUI corre elevado). Todas las llamadas a
# Task Scheduler / registro / servicios estan envueltas en funciones propias
# que se mockean aqui; ninguna toca el sistema real.

. (Join-Path $PSScriptRoot '..\lite\ParkosLite.Autostart.ps1')

$script:paths = @{ PgData = 'C:\lite\data\pg'; PgRoot = 'C:\lite\pgsql'; Lite = 'C:\lite' }
$script:ps = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$script:script = 'C:\repo\installer\lite\parkos-lite.ps1'

Describe 'Get-ParkosLiteAutostartCommand' {
    It 'modo Db arranca solo la base de datos, oculto y sin perfil' {
        $c = Get-ParkosLiteAutostartCommand -PowerShellPath $script:ps -ScriptPath $script:script -LitePath 'C:\lite' -Mode 'Db'
        $c.Execute | Should Be $script:ps
        $c.Argument | Should Match '-WindowStyle Hidden'
        $c.Argument | Should Match '-NoProfile'
        $c.Argument | Should Match '-File "C:\\repo\\installer\\lite\\parkos-lite.ps1"'
        $c.Argument | Should Match '-LitePath "C:\\lite"'
        $c.Argument | Should Match '-Action StartDb'
    }
    It 'modo All arranca tambien API y front' {
        $c = Get-ParkosLiteAutostartCommand -PowerShellPath $script:ps -ScriptPath $script:script -LitePath 'C:\lite' -Mode 'All'
        $c.Argument | Should Match '-Action StartAll'
    }
    It 'CommandLine es Execute + Argument (para HKCU Run)' {
        $c = Get-ParkosLiteAutostartCommand -PowerShellPath $script:ps -ScriptPath $script:script -LitePath 'C:\lite' -Mode 'Db'
        $c.CommandLine | Should Be ('"{0}" {1}' -f $script:ps, $c.Argument)
    }
}

Describe 'Get-ParkosLiteServiceArguments' {
    It 'arma pg_ctl register con inicio automatico sobre el data dir lite' {
        $a = Get-ParkosLiteServiceArguments -PgData 'C:\lite\data\pg'
        ($a -join ' ') | Should Be 'register -N ParkosLiteDb -D C:\lite\data\pg -S auto -w'
    }
}

Describe 'Enable-ParkosLiteAutostart' {
    BeforeEach {
        $global:calls = @()
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { $null }
        Mock Unregister-ParkosLiteTask { $global:calls += 'unreg-task' }
        Mock Remove-ParkosLiteRunKey { $global:calls += 'rm-runkey' }
        Mock Register-ParkosLiteTask { $global:calls += "reg-task:$Argument" }
        Mock Set-ParkosLiteRunKey { $global:calls += "set-runkey:$Command" }
        Mock Test-ParkosLiteElevated { $false }
        Mock Invoke-ParkosLitePgCtlRegister { $global:calls += 'svc-register'; 0 }
    }

    It 'por defecto registra la tarea AtLogOn (sin admin)' {
        $r = Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps
        $r.Method | Should Be 'task'
        $r.Mode | Should Be 'Db'
        ($global:calls | Where-Object { $_ -like 'reg-task:*StartDb*' }).Count | Should Be 1
    }

    It 'con -IncludeApp la tarea arranca API+front (StartAll)' {
        $r = Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps -IncludeApp
        $r.Mode | Should Be 'All'
        ($global:calls | Where-Object { $_ -like 'reg-task:*StartAll*' }).Count | Should Be 1
    }

    It 'si la tarea no se puede registrar cae a la clave HKCU Run' {
        Mock Register-ParkosLiteTask { throw 'Acceso denegado' }
        $r = Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps
        $r.Method | Should Be 'runkey'
        ($global:calls | Where-Object { $_ -like 'set-runkey:*' }).Count | Should Be 1
    }

    It 'es idempotente: reemplaza lo existente y nunca deja dos mecanismos' {
        Mock Get-ParkosLiteTask { @{ Execute = 'x'; Argument = '-Action StartDb' } }
        Mock Get-ParkosLiteRunKey { 'viejo' }
        Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps | Out-Null
        $global:calls[0] | Should Be 'unreg-task'
        $global:calls[1] | Should Be 'rm-runkey'
        ($global:calls | Where-Object { $_ -like 'reg-task:*' }).Count | Should Be 1
    }

    It 'servicio de Windows sin elevacion falla con mensaje claro' {
        { Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps -Method service } | Should Throw 'administrador'
        ($global:calls | Where-Object { $_ -eq 'svc-register' }).Count | Should Be 0
    }

    It 'servicio de Windows elevado registra pg_ctl register' {
        Mock Test-ParkosLiteElevated { $true }
        $r = Enable-ParkosLiteAutostart -Paths $script:paths -ScriptPath $script:script -PowerShellPath $script:ps -Method service
        $r.Method | Should Be 'service'
        ($global:calls | Where-Object { $_ -eq 'svc-register' }).Count | Should Be 1
    }
}

Describe 'Disable-ParkosLiteAutostart' {
    BeforeEach {
        $global:calls = @()
        Mock Unregister-ParkosLiteTask { $global:calls += 'unreg-task' }
        Mock Remove-ParkosLiteRunKey { $global:calls += 'rm-runkey' }
        Mock Unregister-ParkosLiteService { $global:calls += 'unreg-svc' }
        Mock Test-ParkosLiteElevated { $false }
    }
    It 'quita tarea y clave Run cuando existen' {
        Mock Get-ParkosLiteTask { @{ Execute = 'x'; Argument = 'y' } }
        Mock Get-ParkosLiteRunKey { 'cmd' }
        Mock Get-ParkosLiteService { $null }
        Disable-ParkosLiteAutostart -Paths $script:paths
        ($global:calls -join ',') | Should Be 'unreg-task,rm-runkey'
    }
    It 'no hace nada (y no falla) si no hay nada configurado' {
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { $null }
        Disable-ParkosLiteAutostart -Paths $script:paths
        $global:calls.Count | Should Be 0
    }
    It 'quita el servicio solo si hay elevacion; si no, avisa pero continua' {
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { @{ Name = 'ParkosLiteDb' } }
        $r = Disable-ParkosLiteAutostart -Paths $script:paths
        $global:calls.Count | Should Be 0
        $r.Warnings.Count | Should Be 1
        Mock Test-ParkosLiteElevated { $true }
        Disable-ParkosLiteAutostart -Paths $script:paths | Out-Null
        ($global:calls -join ',') | Should Be 'unreg-svc'
    }
}

Describe 'Get-ParkosLiteAutostartStatus' {
    It 'sin nada: deshabilitado' {
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { $null }
        $s = Get-ParkosLiteAutostartStatus
        $s.Enabled | Should Be $false
        $s.Method | Should Be 'none'
    }
    It 'tarea con StartAll: habilitado, metodo task, modo All' {
        Mock Get-ParkosLiteTask { @{ Execute = 'x'; Argument = '-File a -Action StartAll' } }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { $null }
        $s = Get-ParkosLiteAutostartStatus
        $s.Enabled | Should Be $true
        $s.Method | Should Be 'task'
        $s.Mode | Should Be 'All'
    }
    It 'clave Run: metodo runkey, modo Db' {
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { '"ps" -File a -Action StartDb' }
        Mock Get-ParkosLiteService { $null }
        $s = Get-ParkosLiteAutostartStatus
        $s.Method | Should Be 'runkey'
        $s.Mode | Should Be 'Db'
    }
    It 'servicio: metodo service' {
        Mock Get-ParkosLiteTask { $null }
        Mock Get-ParkosLiteRunKey { $null }
        Mock Get-ParkosLiteService { @{ Name = 'ParkosLiteDb' } }
        (Get-ParkosLiteAutostartStatus).Method | Should Be 'service'
    }
    It 'Format-ParkosLiteAutostartLine muestra on/off y metodo' {
        (Format-ParkosLiteAutostartLine -Status @{ Enabled = $false; Method = 'none'; Mode = '' }) | Should Match 'desactivado'
        (Format-ParkosLiteAutostartLine -Status @{ Enabled = $true; Method = 'task'; Mode = 'Db' }) | Should Match 'activado.*task.*solo base de datos'
        (Format-ParkosLiteAutostartLine -Status @{ Enabled = $true; Method = 'runkey'; Mode = 'All' }) | Should Match 'API y front'
    }
}
