$ErrorActionPreference = 'Stop'
$dockerBin = 'C:\Program Files\Docker\Docker\resources\bin'
if (-not (Test-Path -LiteralPath $dockerBin)) {
    throw "Docker bin directory not found: $dockerBin"
}
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @($userPath -split ';' | Where-Object { $_ -ne '' })
if ($parts -notcontains $dockerBin) {
    $parts += $dockerBin
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
    Write-Output 'Docker bin added to user PATH.'
}
else {
    Write-Output 'Docker bin already in user PATH.'
}
Write-Output "Restart the terminal to use: $dockerBin\\docker.exe"
