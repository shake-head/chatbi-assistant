$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root 'var\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output 'No server.pid found.'
    exit 1
}
$serverPid = [int](Get-Content -LiteralPath $pidFile | Select-Object -First 1)
$process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if ($null -eq $process) {
    Write-Output "Process $serverPid is not running."
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    exit 0
}
Stop-Process -Id $serverPid -Force
Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
Write-Output "Stopped API process $serverPid."
