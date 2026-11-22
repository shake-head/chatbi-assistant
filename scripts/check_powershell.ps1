$ErrorActionPreference = 'Continue'
Write-Output '--- execution policy list ---'
Get-ExecutionPolicy -List | Format-List Scope, ExecutionPolicy
Write-Output '--- profile check ---'
$profilePath = Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\profile.ps1'
Write-Output "profile=$profilePath exists=$(Test-Path -LiteralPath $profilePath)"
try {
    Get-Content -LiteralPath $profilePath -ErrorAction Stop | Select-Object -First 1 | Out-Null
    Write-Output 'profile_read=ok'
}
catch {
    Write-Output "profile_read=failed $($_.Exception.Message)"
}
Write-Output '--- nested powershell ---'
powershell.exe -NoLogo -Command "Write-Output NESTED_POWERSHELL_OK" 2>&1
