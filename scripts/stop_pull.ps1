$ErrorActionPreference = 'Continue'
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    ($_.Name -in @('powershell.exe', 'docker.exe')) -and
    (
        $_.CommandLine -like '*pull_base_image.ps1*' -or
        $_.CommandLine -like '*docker pull public.ecr.aws*'
    )
}
foreach ($target in $targets) {
    Write-Output "Stopping PID $($target.ProcessId): $($target.Name)"
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Output "Stopped $($targets.Count) matching pull process(es)."
