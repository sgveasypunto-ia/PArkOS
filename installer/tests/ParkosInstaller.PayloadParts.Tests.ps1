# Tests del cableado del instalador completo con el payload en partes
# (installer/shared/ParkosPayloadParts.ps1 + installer/parkos-installer.ps1):
# 'restaurar de payload\parts cuando falta el crudo' ANTES de decidir construir.
#
#   - Get-ParkosPartsRestorePlan: decision restaurar/construir por artefacto.
#   - Get-ParkosPayloadBuildPlan: lo restaurable cuenta como presente (RestoreIds).
#   - Invoke-ParkosEnsurePayload: restaura (progreso) y solo construye lo demas.
#   - Assert-PayloadPath / Restore-ParkosPayloadForPath: restauran antes de fallar.
#   - Prepare: verifica las partes (Get-ParkosPayloadPartsProblems).
#   - Postgres: las partes versionadas viven en payload\parts\postgres.
#
# Pester 3.4: Mock sin -ModuleName; todo `Should Throw` lleva substring; datos
# sinteticos pequenos en $TestDrive (nunca los 300 MB reales).

$installerScript = Join-Path $PSScriptRoot '..\parkos-installer.ps1'
. $installerScript

function New-PartsEntry {
    param([string]$Id, [string]$Target, [bool]$SourceDependent = $false, [bool]$RestoreToPayload = $true, [string]$Commit = 'abc123')
    return [PSCustomObject]@{
        id = $Id; kind = 'file'; target = $Target; parts = @([PSCustomObject]@{ name = "$Id.bin"; size = 1; sha256 = 'x' })
        sourceDependent = $SourceDependent; restoreToPayload = $RestoreToPayload; builtFromCommit = $Commit
    }
}

function New-AllEntries {
    return @(
        (New-PartsEntry -Id 'nssm' -Target 'nssm.exe')
        (New-PartsEntry -Id 'pg_partman-extension' -Target 'pg_partman\extension')
        (New-PartsEntry -Id 'postgres' -Target 'postgres\pg.zip' -RestoreToPayload $false)
        (New-PartsEntry -Id 'web-sucursal-msi' -Target 'apps\web_sucursal-0.1.0-x64.msi' -SourceDependent $true)
        (New-PartsEntry -Id 'api-sucursal' -Target 'services\api-sucursal' -SourceDependent $true)
        (New-PartsEntry -Id 'job-sync-sucursal' -Target 'services\job-sync-sucursal' -SourceDependent $true)
        (New-PartsEntry -Id 'migrate' -Target 'services\migrate' -SourceDependent $true)
        (New-PartsEntry -Id 'seed' -Target 'services\seed' -SourceDependent $true)
        (New-PartsEntry -Id 'doctor' -Target 'services\doctor' -SourceDependent $true)
    )
}

Describe 'Get-ParkosPartsRestorePlan (restaurar o construir por artefacto)' {

    Mock Get-ParkosPartsEntries { $script:Entries }
    Mock Get-ParkosPartsChangedFiles { $script:Changed }

    BeforeEach {
        $script:Entries = New-AllEntries
        $script:Changed = @()
    }

    It 'sin repo (paquete entregado): restaura todo lo que falta, salvo Postgres (se rearma al instalar)' {
        $ids = @(Get-ParkosPartsRestorePlan -PayloadRoot (Join-Path $TestDrive 'rp1') -RepoRoot '')
        ($ids -join ',') | Should Be 'nssm,pg_partman-extension,web-sucursal-msi,api-sucursal,job-sync-sucursal,migrate,seed,doctor'
    }

    It 'con repo y sin cambios en backend/ ni installer\bootstrap\ desde builtFromCommit: restaura servicios' {
        $script:Changed = @()
        $ids = @(Get-ParkosPartsRestorePlan -PayloadRoot (Join-Path $TestDrive 'rp2') -RepoRoot 'C:\repo')
        ($ids -contains 'migrate') | Should Be $true
        ($ids -contains 'web-sucursal-msi') | Should Be $true
    }

    It 'con cambios de codigo: servicios y MSI se construyen (no se restauran); terceros si' {
        $script:Changed = @('backend/x.py')
        $ids = @(Get-ParkosPartsRestorePlan -PayloadRoot (Join-Path $TestDrive 'rp3') -RepoRoot 'C:\repo')
        ($ids -join ',') | Should Be 'nssm,pg_partman-extension'
    }

    It 'git no responde (null): se restaura (sin informacion de git)' {
        $script:Changed = $null
        $ids = @(Get-ParkosPartsRestorePlan -PayloadRoot (Join-Path $TestDrive 'rp4') -RepoRoot 'C:\repo')
        ($ids -contains 'api-sucursal') | Should Be $true
    }

    It 'lo que ya esta en el payload no se restaura; con un MSI en apps\ no se restaura otro' {
        $pl = Join-Path $TestDrive 'rp5'
        New-Item -ItemType Directory -Force -Path (Join-Path $pl 'apps') | Out-Null
        Set-Content (Join-Path $pl 'apps\web_sucursal-9.9.9-x64.msi') 'x'
        Set-Content (Join-Path $pl 'nssm.exe') 'x'
        $ids = @(Get-ParkosPartsRestorePlan -PayloadRoot $pl -RepoRoot '')
        ($ids -contains 'nssm') | Should Be $false
        ($ids -contains 'web-sucursal-msi') | Should Be $false
        ($ids -contains 'pg_partman-extension') | Should Be $true
    }

    It 'sin manifest de partes: nada que restaurar' {
        $script:Entries = @()
        @(Get-ParkosPartsRestorePlan -PayloadRoot (Join-Path $TestDrive 'rp6') -RepoRoot '').Count | Should Be 0
    }
}

Describe 'Get-ParkosPayloadBuildPlan con partes (lo restaurable cuenta como presente)' {

    Mock Get-ParkosPartsEntries { $script:Entries }
    Mock Get-ParkosPartsChangedFiles { $script:Changed }
    Mock Get-ParkosSourceFileList { @() }

    BeforeEach {
        $script:Entries = New-AllEntries
        $script:Changed = @()
    }

    It 'payload vacio pero todo en partes y codigo sin cambios: no hay que construir, hay que restaurar' {
        $p = Get-ParkosPayloadBuildPlan -PayloadRoot (Join-Path $TestDrive 'bp1') -RepoRoot 'C:\repo'
        $p.Needed | Should Be $false
        @($p.Switches).Count | Should Be 0
        ($p.RestoreIds -contains 'nssm') | Should Be $true
        ($p.RestoreIds -contains 'migrate') | Should Be $true
    }

    It 'con cambios de codigo: construye MSI y programas, restaura solo terceros' {
        $script:Changed = @('installer/bootstrap/entry_migrate.py')
        $p = Get-ParkosPayloadBuildPlan -PayloadRoot (Join-Path $TestDrive 'bp2') -RepoRoot 'C:\repo'
        $p.Needed | Should Be $true
        ($p.Switches -contains 'WebSucursal') | Should Be $true
        ($p.Switches -contains 'Migrate') | Should Be $true
        ($p.Switches -contains 'Payload') | Should Be $false
        ($p.RestoreIds -join ',') | Should Be 'nssm,pg_partman-extension'
    }

    It 'sin partes y sin nada: se comporta como antes (construir todo)' {
        $script:Entries = @()
        $p = Get-ParkosPayloadBuildPlan -PayloadRoot (Join-Path $TestDrive 'bp3') -RepoRoot 'C:\repo'
        $p.Needed | Should Be $true
        ($p.Switches -contains 'Payload') | Should Be $true
        @($p.RestoreIds).Count | Should Be 0
    }
}

Describe 'Invoke-ParkosEnsurePayload restaura de partes antes de construir' {

    Mock Write-Host { }
    Mock Get-ParkosPartsEntries { $script:Entries }
    Mock Get-ParkosPartsChangedFiles { @() }
    Mock Get-ParkosSourceFileList { @() }
    Mock Stop-ParkosPayloadProcesses { 0 }
    Mock Invoke-ParkosBuildReleaseScript { $script:Built += ($Switches -join '+'); 0 }
    Mock Invoke-ParkosRestoreFromParts { $script:Restored += $Ids }
    Mock Test-ParkosPayloadReady { $true }

    BeforeEach {
        $script:Entries = New-AllEntries
        $script:Built = @()
        $script:Restored = @()
    }

    It 'todo restaurable: restaura con Restaurando n de m y NO compila' {
        Invoke-ParkosEnsurePayload -PayloadRoot (Join-Path $TestDrive 'en1') -RepoRoot 'C:\repo' -LogDir (Join-Path $TestDrive 'logs')
        @($script:Built).Count | Should Be 0
        ($script:Restored -contains 'nssm') | Should Be $true
        ($script:Restored -contains 'doctor') | Should Be $true
        Assert-MockCalled Invoke-ParkosRestoreFromParts -Times 1 -Exactly -Scope It
    }

    It 'si faltan terceros NO restaurables (sin partes) construye Payload' {
        $script:Entries = @()
        Mock Get-ParkosPayloadBlockers { @() }
        Invoke-ParkosEnsurePayload -PayloadRoot (Join-Path $TestDrive 'en2') -RepoRoot 'C:\repo' -LogDir (Join-Path $TestDrive 'logs')
        ($script:Built -join '|') | Should Match 'Payload'
        @($script:Restored).Count | Should Be 0
    }
}

Describe 'Assert-PayloadPath / Restore-ParkosPayloadForPath (restaurar antes de fallar)' {

    BeforeEach {
        $script:savedRoot = $script:PayloadRoot
        $script:PayloadRoot = Join-Path $TestDrive "pl-$([guid]::NewGuid().ToString('N'))"
        New-Item -ItemType Directory -Force -Path $script:PayloadRoot | Out-Null
        $src = Join-Path $TestDrive 'src\nssm.exe'
        New-Item -ItemType Directory -Force -Path (Split-Path $src -Parent) | Out-Null
        [System.IO.File]::WriteAllBytes($src, (1..200 | ForEach-Object { [byte]($_ % 256) }))
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 'nssm' -PartsDir (Join-Path $script:PayloadRoot 'parts') -Target 'nssm.exe' -Logger { param($m) })
        $d = Join-Path $TestDrive 'src\ext'
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Set-Content (Join-Path $d 'pg_partman.control') 'control'
        [void](Pack-ParkosPayloadArtifact -Source $d -Id 'pg_partman-extension' -PartsDir (Join-Path $script:PayloadRoot 'parts') -Target 'pg_partman\extension' -Logger { param($m) })
    }
    AfterEach { $script:PayloadRoot = $script:savedRoot }

    Mock Write-Host { }

    It 'un archivo faltante que esta en partes se restaura y Assert-PayloadPath no falla' {
        $p = Join-Path $script:PayloadRoot 'nssm.exe'
        { Assert-PayloadPath -Path $p -What 'nssm' } | Should Not Throw
        (Test-Path $p) | Should Be $true
        (Get-Item $p).Length | Should Be 200
    }

    It 'una ruta DENTRO de un artefacto de carpeta restaura la carpeta completa' {
        $p = Join-Path $script:PayloadRoot 'pg_partman\extension\pg_partman.control'
        (Restore-ParkosPayloadForPath -Path $p) | Should Be $true
        (Get-Content $p) | Should Be 'control'
    }

    It 'lo que no esta en partes sigue fallando con el mensaje de siempre' {
        { Assert-PayloadPath -Path (Join-Path $script:PayloadRoot 'otra\cosa.exe') -What 'otra cosa' } | Should Throw 'Falta otra cosa en el payload'
    }

    It 'fuera del payload no restaura nada' {
        (Restore-ParkosPayloadForPath -Path 'C:\fuera\nssm.exe') | Should Be $false
    }

    It 'una parte danada se propaga como error (no se sigue en silencio)' {
        $part = Join-Path $script:PayloadRoot 'parts\nssm\nssm.exe'
        $b = [System.IO.File]::ReadAllBytes($part); $b[3] = [byte](($b[3] + 1) % 256); [System.IO.File]::WriteAllBytes($part, $b)
        { Assert-PayloadPath -Path (Join-Path $script:PayloadRoot 'nssm.exe') -What 'nssm' } | Should Throw 'danada'
    }

    It 'Restore-ParkosPayloadById restaura solo si el destino falta' {
        (Restore-ParkosPayloadById -Id 'nssm') | Should Be $true
        (Restore-ParkosPayloadById -Id 'nssm') | Should Be $false
        (Restore-ParkosPayloadById -Id 'no-existe') | Should Be $false
    }
}

Describe 'Get-ParkosPayloadPartsProblems / Postgres en payload\parts' {

    Mock Test-ParkosPostgresZip { $true }

    It 'sin manifest de partes: sin problemas (paquete antiguo)' {
        @(Get-ParkosPayloadPartsProblems -PayloadRoot (Join-Path $TestDrive 'pp-none')).Count | Should Be 0
    }

    It 'manifest consistente: sin problemas; parte borrada: lo informa' {
        $pl = Join-Path $TestDrive 'pp-ok'
        $src = Join-Path $TestDrive 'pp-src\a.bin'
        New-Item -ItemType Directory -Force -Path (Split-Path $src -Parent) | Out-Null
        Set-Content $src 'hola'
        [void](Pack-ParkosPayloadArtifact -Source $src -Id 'a' -PartsDir (Join-Path $pl 'parts') -Target 'a.bin' -Logger { param($m) })
        @(Get-ParkosPayloadPartsProblems -PayloadRoot $pl).Count | Should Be 0
        Remove-Item (Join-Path $pl 'parts\a\a.bin')
        (@(Get-ParkosPayloadPartsProblems -PayloadRoot $pl) -join ' ') | Should Match 'falta la parte a.bin'
    }

    It 'las partes de Postgres en payload\parts\postgres bastan (sin zip completo)' {
        $pl = Join-Path $TestDrive 'pp-pg'
        $name = (Get-ParkosPostgresDownloadInfo).FileName
        $dir = Join-Path $pl 'parts\postgres'
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        foreach ($i in 1, 2) { Set-Content (Join-Path $dir ("$name.part{0:D2}" -f $i)) 'x' }
        Set-Content (Join-Path $dir "$name.sha256") 'h'
        Get-ParkosPostgresPayloadProblem -PayloadRoot $pl | Should Be $null
        (Get-ParkosPostgresPartsDir -PayloadRoot $pl) | Should Be $dir
    }

    It 'sin partes dice como restaurarlas desde parts\' {
        $pl = Join-Path $TestDrive 'pp-pg-none'
        New-Item -ItemType Directory -Force -Path $pl | Out-Null
        Get-ParkosPostgresPayloadProblem -PayloadRoot $pl | Should Match 'git checkout -- installer/payload/parts'
    }

    It 'el paquete completo exige tambien ParkosPayloadParts.ps1' {
        $pl = Join-Path $TestDrive 'pp-complete'
        New-Item -ItemType Directory -Force -Path $pl | Out-Null
        (@(Get-ParkosPayloadCompletenessProblems -PayloadRoot $pl) -join ' ') | Should Match 'ParkosPayloadParts.ps1'
    }
}

Describe 'Prepare verifica las partes versionadas' {

    Mock Write-Host { }
    Mock Get-ParkosRepoRoot { 'C:\repo' }
    Mock Get-ParkosMissingBuildTools { @() }
    Mock Resolve-ParkosMasterKeySource { '' }
    Mock Get-ParkosMasterKeyProblem { $null }
    Mock Stop-ParkosPayloadProcesses { 0 }
    Mock Invoke-ParkosBuildReleaseScript { 0 }
    Mock Get-ParkosPostgresPayloadProblem { $null }
    Mock Get-ParkosPayloadCompletenessProblems { @() }
    Mock Get-ParkosPayloadPartsProblems { $script:PartsProblems }

    It 'partes inconsistentes: Prepare falla con el detalle' {
        $script:PartsProblems = @('la parte x.part01 de nssm tiene hash distinto')
        $r = Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs'
        $r.ExitCode | Should Be 1
        $r.Detail | Should Match 'inconsistentes'
        $r.Detail | Should Match 'x.part01'
    }

    It 'partes consistentes: Prepare termina bien' {
        $script:PartsProblems = @()
        (Invoke-ParkosPreparePayload -PayloadRoot 'C:\pl' -LogDir 'C:\logs').ExitCode | Should Be 0
    }
}
