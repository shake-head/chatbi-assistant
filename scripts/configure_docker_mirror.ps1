$ErrorActionPreference = 'Stop'
$daemonPath = Join-Path $env:USERPROFILE '.docker\daemon.json'
$daemonDir = Split-Path -Parent $daemonPath
New-Item -ItemType Directory -Force -Path $daemonDir | Out-Null

if (Test-Path -LiteralPath $daemonPath) {
    Copy-Item -LiteralPath $daemonPath -Destination "$daemonPath.before-mirror.bak" -Force
    $config = Get-Content -LiteralPath $daemonPath -Raw | ConvertFrom-Json
}
else {
    $config = [pscustomobject]@{}
}

$mirrors = @(
    'https://docker.1ms.run',
    'https://docker.xuanyuan.me',
    'https://docker.m.daocloud.io'
)
$config | Add-Member -NotePropertyName 'registry-mirrors' -NotePropertyValue $mirrors -Force
$json = $config | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($daemonPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Output "Configured registry mirror in $daemonPath"
Get-Content -LiteralPath $daemonPath
