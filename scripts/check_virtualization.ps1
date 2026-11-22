$ErrorActionPreference = 'Continue'
Get-CimInstance Win32_ComputerSystem |
    Select-Object HypervisorPresent |
    Format-List
Get-CimInstance Win32_Processor |
    Select-Object Name, VirtualizationFirmwareEnabled, VMMonitorModeExtensions, SecondLevelAddressTranslationExtensions |
    Format-List
foreach ($feature in @('VirtualMachinePlatform', 'Microsoft-Windows-Subsystem-Linux', 'Microsoft-Hyper-V-All')) {
    try {
        $state = Get-WindowsOptionalFeature -Online -FeatureName $feature -ErrorAction Stop
        Write-Output "$feature=$($state.State)"
    }
    catch {
        Write-Output "$feature=QUERY_FAILED"
    }
}
