@{
    RootModule = 'Parkos.psm1'
    ModuleVersion = '1.0.0'
    GUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    Author = 'Parkos S.A.S.'
    Description = 'Cmdlets de gestion del ciclo de vida de una instalacion Parkos en una sucursal.'
    PowerShellVersion = '7.0'
    FunctionsToExport = @(
        'Get-ParkosHealth', 'Repair-ParkosInstall', 'Uninstall-Parkos',
        'Export-ParkosDiagnostics', 'Register-ParkosBackupTask',
        'Test-CrashRecovery', 'Get-ParkosVersion', 'Test-ParkosSecretsAcl'
    )
    CmdletsToExport = @()
    VariablesToExport = @()
    AliasesToExport = @()
    PrivateData = @{ PSData = @{ Tags = @('Parkos', 'sucursal', 'diagnostico') } }
}
