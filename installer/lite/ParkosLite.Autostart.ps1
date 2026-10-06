# Parkos LITE - arranque automatico de la base de datos.
#
# Metodo por defecto (SIN admin): tarea programada POR USUARIO con disparador
# AtLogOn (Register-ScheduledTask). Fallback: clave HKCU\...\Run. Opcional y
# SOLO si el TUI corre elevado: servicio de Windows via `pg_ctl register`.
# La tarea/clave invoca parkos-lite.ps1 -Action StartDb|StartAll (oculto), que
# a su vez ejecuta `pg_ctl start -w -D <pgdata>` tolerando un postmaster.pid
# huerfano y esperando a que la DB acepte conexiones.
#
# Solo funciones; los wrappers de Task Scheduler / registro / servicios se
# mockean en Pester. Compatible con PowerShell 5.1.

$script:ParkosLiteAutostartName = 'ParkosLiteDb'
$script:ParkosLiteRunKeyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

# ---------------------------------------------------------------------------
# Wrappers (Task Scheduler, registro, servicios, elevacion)
# ---------------------------------------------------------------------------

function Test-ParkosLiteElevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Register-ParkosLiteTask {
    param(
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$Execute,
        [Parameter(Mandatory)][string]$Argument
    )
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $Execute -Argument $Argument
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Parkos LITE: inicia la base de datos local al iniciar sesion' -Force -ErrorAction Stop | Out-Null
}

function Unregister-ParkosLiteTask {
    param([Parameter(Mandatory)][string]$TaskName)
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
}

# Devuelve @{ Execute; Argument } o $null.
function Get-ParkosLiteTask {
    param([Parameter(Mandatory)][string]$TaskName)
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { return $null }
    $a = $t.Actions | Select-Object -First 1
    return @{ Execute = $a.Execute; Argument = $a.Arguments }
}

function Set-ParkosLiteRunKey {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$Command)
    Set-ItemProperty -Path $script:ParkosLiteRunKeyPath -Name $Name -Value $Command -ErrorAction Stop
}

function Remove-ParkosLiteRunKey {
    param([Parameter(Mandatory)][string]$Name)
    Remove-ItemProperty -Path $script:ParkosLiteRunKeyPath -Name $Name -ErrorAction Stop
}

function Get-ParkosLiteRunKey {
    param([Parameter(Mandatory)][string]$Name)
    $p = Get-ItemProperty -Path $script:ParkosLiteRunKeyPath -Name $Name -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    return $p.$Name
}

function Get-ParkosLiteService {
    param([Parameter(Mandatory)][string]$Name)
    $s = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $s) { return $null }
    return @{ Name = $s.Name; Status = [string]$s.Status }
}

function Invoke-ParkosLitePgCtlRegister {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string[]]$Arguments)
    & (Join-Path $PgRoot 'bin\pg_ctl.exe') @Arguments | Out-Null
    return $LASTEXITCODE
}

function Unregister-ParkosLiteService {
    param([Parameter(Mandatory)][string]$PgRoot, [Parameter(Mandatory)][string]$Name)
    & (Join-Path $PgRoot 'bin\pg_ctl.exe') unregister -N $Name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl unregister fallo (exit $LASTEXITCODE)." }
}

# ---------------------------------------------------------------------------
# Logica
# ---------------------------------------------------------------------------

function Get-ParkosLiteAutostartCommand {
    param(
        [Parameter(Mandatory)][string]$PowerShellPath,
        [Parameter(Mandatory)][string]$ScriptPath,
        [Parameter(Mandatory)][string]$LitePath,
        [ValidateSet('Db', 'All')][string]$Mode = 'Db'
    )
    $action = 'StartDb'
    if ($Mode -eq 'All') { $action = 'StartAll' }
    $arg = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`" -LitePath `"$LitePath`" -Action $action"
    return @{
        Execute     = $PowerShellPath
        Argument    = $arg
        CommandLine = ('"{0}" {1}' -f $PowerShellPath, $arg)
    }
}

function Get-ParkosLiteServiceArguments {
    param([Parameter(Mandatory)][string]$PgData)
    return @('register', '-N', $script:ParkosLiteAutostartName, '-D', $PgData, '-S', 'auto', '-w')
}

function Get-ParkosLiteModeFromText {
    param([string]$Text)
    if ($Text -match '-Action StartAll') { return 'All' }
    return 'Db'
}

function Get-ParkosLiteAutostartStatus {
    $name = $script:ParkosLiteAutostartName
    $task = Get-ParkosLiteTask -TaskName $name
    if ($task) { return @{ Enabled = $true; Method = 'task'; Mode = (Get-ParkosLiteModeFromText $task.Argument) } }
    $run = Get-ParkosLiteRunKey -Name $name
    if ($run) { return @{ Enabled = $true; Method = 'runkey'; Mode = (Get-ParkosLiteModeFromText $run) } }
    $svc = Get-ParkosLiteService -Name $name
    if ($svc) { return @{ Enabled = $true; Method = 'service'; Mode = 'Db' } }
    return @{ Enabled = $false; Method = 'none'; Mode = '' }
}

function Format-ParkosLiteAutostartLine {
    param([Parameter(Mandatory)]$Status)
    if (-not $Status.Enabled) { return 'Arranque automatico: desactivado' }
    $what = 'solo base de datos'
    if ($Status.Mode -eq 'All') { $what = 'base de datos, API y front' }
    $mode = $Status.Method
    return "Arranque automatico: activado ($mode, $what)"
}

# Quita TODO mecanismo de arranque (tarea, clave Run, servicio). El servicio
# solo se puede quitar con elevacion; sin ella se avisa y se continua.
function Disable-ParkosLiteAutostart {
    param([Parameter(Mandatory)]$Paths)
    $name = $script:ParkosLiteAutostartName
    $warnings = @()
    if (Get-ParkosLiteTask -TaskName $name) { Unregister-ParkosLiteTask -TaskName $name }
    if (Get-ParkosLiteRunKey -Name $name) { Remove-ParkosLiteRunKey -Name $name }
    if (Get-ParkosLiteService -Name $name) {
        if (Test-ParkosLiteElevated) {
            Unregister-ParkosLiteService -PgRoot $Paths.PgRoot -Name $name
        } else {
            $warnings += "El servicio de Windows '$name' existe pero quitarlo requiere administrador: ejecuta 'pg_ctl unregister -N $name' desde una consola elevada."
        }
    }
    return @{ Warnings = $warnings }
}

# Activa el arranque. Idempotente: primero quita lo existente (reemplaza, nunca
# duplica). Method: auto (tarea -> fallback HKCU Run) | task | runkey | service.
function Enable-ParkosLiteAutostart {
    param(
        [Parameter(Mandatory)]$Paths,
        [Parameter(Mandatory)][string]$ScriptPath,
        [string]$PowerShellPath,
        [ValidateSet('auto', 'task', 'runkey', 'service')][string]$Method = 'auto',
        [switch]$IncludeApp
    )
    $name = $script:ParkosLiteAutostartName
    if ($Method -eq 'service' -and -not (Test-ParkosLiteElevated)) {
        throw 'El servicio de Windows requiere administrador: abre el TUI como administrador o usa el arranque por tarea de usuario (sin admin).'
    }
    if (-not $PowerShellPath) { $PowerShellPath = (Get-Process -Id $PID).Path }

    Disable-ParkosLiteAutostart -Paths $Paths | Out-Null

    $mode = 'Db'
    if ($IncludeApp) { $mode = 'All' }
    $cmd = Get-ParkosLiteAutostartCommand -PowerShellPath $PowerShellPath -ScriptPath $ScriptPath -LitePath $Paths.Lite -Mode $mode

    if ($Method -eq 'service') {
        $rc = Invoke-ParkosLitePgCtlRegister -PgRoot $Paths.PgRoot -Arguments (Get-ParkosLiteServiceArguments -PgData $Paths.PgData)
        if ($rc -ne 0) { throw "pg_ctl register fallo (exit $rc)." }
        return @{ Method = 'service'; Mode = 'Db' }
    }

    if ($Method -eq 'auto' -or $Method -eq 'task') {
        try {
            Register-ParkosLiteTask -TaskName $name -Execute $cmd.Execute -Argument $cmd.Argument
            return @{ Method = 'task'; Mode = $mode }
        } catch {
            if ($Method -eq 'task') { throw }
        }
    }
    Set-ParkosLiteRunKey -Name $name -Command $cmd.CommandLine
    return @{ Method = 'runkey'; Mode = $mode }
}
