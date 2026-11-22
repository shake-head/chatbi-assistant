$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'post_reboot_docker.ps1'
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script `
    -WindowStyle Hidden
Write-Output 'Docker engine worker started. See docker-engine-report.json when complete.'
