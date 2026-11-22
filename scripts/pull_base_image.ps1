$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$image = 'swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/python:3.11-slim'
docker pull $image *> docker-pull.log
$code = $LASTEXITCODE
$report = @{
    image = $image
    exit_code = $code
    ok = ($code -eq 0)
    finished_at = (Get-Date).ToString('o')
}
if ($code -eq 0) {
    $report.image_id = (& docker image inspect $image --format '{{.Id}}' 2>&1 | Out-String).Trim()
}
$report | ConvertTo-Json -Depth 4 | Out-File -FilePath (Join-Path $root 'docker-pull-report.json') -Encoding utf8
$report | ConvertTo-Json -Depth 4
exit $code
