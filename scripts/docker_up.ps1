$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$reportPath = Join-Path $root 'docker-up-report.json'
$buildLog = Join-Path $root 'docker-up.log'
$report = @{}
$report.started_at = (Get-Date).ToString('o')

& docker compose config --quiet *> $null
$configCode = $LASTEXITCODE
$report.config_ok = ($configCode -eq 0)

$upStarted = Get-Date
& docker compose up --build -d *> $buildLog
$upCode = $LASTEXITCODE
$report.up_ok = ($upCode -eq 0)
$report.up_exit_code = $upCode
$report.build_seconds = [math]::Round(((Get-Date) - $upStarted).TotalSeconds, 2)

$healthy = $false
if ($upCode -eq 0) {
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
            if ($response.status -eq 'ok') {
                $healthy = $true
                $report.health = $response
                break
            }
        }
        catch {
        }
    }
}
$report.healthy = $healthy
$report.services = (& docker compose ps --format json 2>&1 | Out-String).Trim()
if (Test-Path -LiteralPath $buildLog) {
    $report.log_tail = (Get-Content -LiteralPath $buildLog -Tail 80 -ErrorAction SilentlyContinue | Out-String)
}
$report.finished_at = (Get-Date).ToString('o')
$report | ConvertTo-Json -Depth 6 | Out-File -FilePath $reportPath -Encoding utf8
$report | ConvertTo-Json -Depth 4
if (-not ($report.config_ok -and $report.up_ok -and $report.healthy)) {
    exit 1
}
