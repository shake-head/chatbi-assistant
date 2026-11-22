$ErrorActionPreference = 'Continue'
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$desktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$report = @{}
$report.wsl = (wsl --status 2>&1 | Out-String)
$running = Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue
if (-not $running -and (Test-Path -LiteralPath $desktop)) {
    Start-Process -FilePath $desktop
    Write-Output 'Docker Desktop launch requested.'
}
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $docker) {
        & $docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }
}
$report.docker_engine_ready = $ready
if ($ready) {
    $report.docker_version = (& $docker --version | Out-String).Trim()
    $report.compose_version = (& $docker compose version | Out-String).Trim()
}
$report | ConvertTo-Json -Depth 4
$report | ConvertTo-Json -Depth 4 | Out-File -FilePath (Join-Path (Split-Path -Parent $PSScriptRoot) 'docker-engine-report.json') -Encoding utf8
if (-not $ready) {
    Write-Output 'Docker engine is not ready. Confirm BIOS/UEFI virtualization is enabled, then reboot again.'
    exit 1
}
