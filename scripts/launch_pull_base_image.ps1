$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'pull_base_image.ps1'
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script `
    -WindowStyle Hidden
Write-Output 'Base image pull worker started. See docker-pull-report.json when complete.'
