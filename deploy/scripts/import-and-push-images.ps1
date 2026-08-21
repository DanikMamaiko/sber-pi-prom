param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$NexusRepository,

    [string]$ArchiveDirectory = 'artifacts',

    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$resolvedArchiveDirectory = Join-Path $repositoryRoot $ArchiveDirectory
$nexusRepository = $NexusRepository.TrimEnd('/')
$checksumFile = Join-Path $resolvedArchiveDirectory "SHA256SUMS-$Version.txt"
$archiveNames = @("sberpi-api-$Version.tar", "sberpi-frontend-$Version.tar")

if (-not (Test-Path -LiteralPath $checksumFile)) {
    throw "Checksum file not found: $checksumFile"
}

$checksumLines = Get-Content -LiteralPath $checksumFile
foreach ($archiveName in $archiveNames) {
    $archivePath = Join-Path $resolvedArchiveDirectory $archiveName
    if (-not (Test-Path -LiteralPath $archivePath)) {
        throw "Image archive not found: $archivePath"
    }
    $checksumLine = $checksumLines | Where-Object { $_ -match "^[0-9a-fA-F]{64}\s+$([regex]::Escape($archiveName))$" }
    if (@($checksumLine).Count -ne 1) {
        throw "Expected exactly one checksum for $archiveName"
    }
    $expectedHash = ($checksumLine -split '\s+')[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "Checksum mismatch for $archiveName"
    }
}

Write-Host 'Image archive checksums are valid.'
if ($VerifyOnly) {
    return
}

docker load --input "$resolvedArchiveDirectory\sberpi-api-$Version.tar"
docker load --input "$resolvedArchiveDirectory\sberpi-frontend-$Version.tar"

$apiTarget = "$nexusRepository/sberpi-api:$Version"
$frontendTarget = "$nexusRepository/sberpi-frontend:$Version"

docker tag "sberpi-api:$Version" $apiTarget
docker tag "sberpi-frontend:$Version" $frontendTarget
docker push $apiTarget
docker push $frontendTarget

Write-Host "Published $apiTarget"
Write-Host "Published $frontendTarget"
