$ErrorActionPreference = 'Continue'
winget install --id Docker.DockerDesktop -e --silent --accept-package-agreements --accept-source-agreements *> docker-install.log
$code = $LASTEXITCODE
"exit_code=$code" | Out-File -FilePath docker-install.exit -Encoding ascii
Write-Output "docker install exit code: $code"
Get-Content -Path docker-install.log -Tail 40 -ErrorAction SilentlyContinue
