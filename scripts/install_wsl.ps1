$ErrorActionPreference = 'Continue'
wsl --install --no-distribution *> wsl-install.log
$code = $LASTEXITCODE
"exit_code=$code" | Out-File -FilePath wsl-install.exit -Encoding ascii
Write-Output "wsl install exit code: $code"
Get-Content -Path wsl-install.log -Tail 40 -ErrorAction SilentlyContinue
