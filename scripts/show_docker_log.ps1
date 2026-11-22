$ErrorActionPreference = 'Continue'
if (Test-Path -LiteralPath 'docker-up.log') {
    Get-Item -LiteralPath 'docker-up.log' | Select-Object LastWriteTime, Length | Format-List
    Get-Content -LiteralPath 'docker-up.log' -Tail 40
}
else {
    Write-Output 'docker-up.log not found'
}
