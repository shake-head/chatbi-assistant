$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'docker_up.ps1'
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script `
    -WindowStyle Hidden
Write-Output 'Docker validation worker started. See docker-up-report.json when complete.'
