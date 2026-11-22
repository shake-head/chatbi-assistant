$ErrorActionPreference = 'Continue'
if (Test-Path -LiteralPath 'docker-pull.log') {
    Get-Item -LiteralPath 'docker-pull.log' | Select-Object LastWriteTime, Length | Format-List
    Get-Content -LiteralPath 'docker-pull.log' -Tail 20
}
else {
    Write-Output 'docker-pull.log not found'
}
