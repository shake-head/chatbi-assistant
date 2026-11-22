$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $root 'var'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$stdout = Join-Path $dataDir 'server.stdout.log'
$stderr = Join-Path $dataDir 'server.stderr.log'
$pidFile = Join-Path $dataDir 'server.pid'
$python = Join-Path $root '.venv\Scripts\python.exe'
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Port 8000 is already in use by PID $($existing.OwningProcess)."
    exit 2
}
$process = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru
$process.Id | Out-File -FilePath $pidFile -Encoding ascii
Write-Output "API started, PID=$($process.Id)"
Write-Output "stdout=$stdout"
Write-Output "stderr=$stderr"
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
        $health | ConvertTo-Json -Compress
        exit 0
    }
    catch {
        if ($process.HasExited) {
            Write-Output "API process exited with code $($process.ExitCode)."
            Get-Content -Path $stderr -Tail 40 -ErrorAction SilentlyContinue
            exit 1
        }
    }
}
Write-Output 'API did not become healthy within 10 seconds.'
Get-Content -Path $stderr -Tail 40 -ErrorAction SilentlyContinue
exit 1
