$ErrorActionPreference = 'Continue'
$mirrors = @(
    'https://docker.m.daocloud.io/v2/',
    'https://docker.1ms.run/v2/',
    'https://docker.xuanyuan.me/v2/',
    'https://hub.rat.dev/v2/',
    'https://docker.rainbond.cc/v2/',
    'https://registry-1.docker.io/v2/'
)
foreach ($uri in $mirrors) {
    $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 8 $uri
    $exit = $LASTEXITCODE
    Write-Output "$uri http=$code curl_exit=$exit"
}
