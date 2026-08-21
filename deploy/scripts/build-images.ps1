param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$Version,

    [string]$Platform = 'linux/amd64',

    [string]$OutputDirectory = 'artifacts'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$resolvedOutput = Join-Path $repositoryRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$apiImage = "sberpi-api:$Version"
$frontendImage = "sberpi-frontend:$Version"

docker buildx build --platform $Platform --load --file "$repositoryRoot\backend\Dockerfile.production" --tag $apiImage $repositoryRoot
docker buildx build --platform $Platform --load --file "$repositoryRoot\frontend\Dockerfile" --tag $frontendImage $repositoryRoot

docker image inspect $apiImage $frontendImage | Out-Null
docker save --output "$resolvedOutput\sberpi-api-$Version.tar" $apiImage
docker save --output "$resolvedOutput\sberpi-frontend-$Version.tar" $frontendImage

Get-FileHash -Algorithm SHA256 "$resolvedOutput\sberpi-api-$Version.tar", "$resolvedOutput\sberpi-frontend-$Version.tar" |
    ForEach-Object { "{0}  {1}" -f $_.Hash.ToLowerInvariant(), (Split-Path $_.Path -Leaf) } |
    Set-Content -Encoding ascii "$resolvedOutput\SHA256SUMS-$Version.txt"

Write-Host "Images and checksums are ready in $resolvedOutput"
