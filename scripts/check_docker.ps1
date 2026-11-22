$ErrorActionPreference = 'Continue'
$dockerExe = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$desktopExe = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
Write-Output "docker_exe_exists=$(Test-Path -LiteralPath $dockerExe)"
Write-Output "docker_desktop_exists=$(Test-Path -LiteralPath $desktopExe)"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
Write-Output "user_path_has_docker=$($userPath -like '*Docker*')"
if (Test-Path -LiteralPath $dockerExe) {
    & $dockerExe --version
}
Write-Output '--- wsl status ---'
wsl --status 2>&1
