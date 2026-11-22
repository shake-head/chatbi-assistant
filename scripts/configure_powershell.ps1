$ErrorActionPreference = 'Continue'
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
$profilePath = Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\profile.ps1'
if (Test-Path -LiteralPath $profilePath) {
    Unblock-File -LiteralPath $profilePath -ErrorAction SilentlyContinue
}
Get-ExecutionPolicy -Scope CurrentUser
Write-Output "PowerShell profile path: $profilePath"
Write-Output "Profile exists: $(Test-Path -LiteralPath $profilePath)"
