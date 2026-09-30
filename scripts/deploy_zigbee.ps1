[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$PiHost = "AC",
    [string]$PiUser = "air",
    [string]$RemotePath = "/home/air/aircon-controller",
    [string]$IdentityFile = (Join-Path $HOME ".ssh\airconpi")
)

$ErrorActionPreference = "Stop"

if ($PiHost -notmatch "^[A-Za-z0-9.-]+$") {
    throw "PiHost contains unsupported characters."
}
if ($PiUser -notmatch "^[A-Za-z0-9_-]+$") {
    throw "PiUser contains unsupported characters."
}
if ($RemotePath -notmatch "^/[A-Za-z0-9._/-]+$") {
    throw "RemotePath must be an absolute POSIX path without spaces."
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "SSH identity file was not found: $IdentityFile"
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$relativePaths = @(
    "deploy/zigbee/.env.example",
    "deploy/zigbee/README.md",
    "deploy/zigbee/compose.yaml",
    "deploy/zigbee/mosquitto/mosquitto.conf",
    "deploy/zigbee/zigbee2mqtt/configuration.example.yaml",
    "scripts/install_zigbee_host.sh",
    "scripts/setup_zigbee_stack.sh",
    "scripts/check_zigbee_stack.sh",
    "scripts/backup_zigbee_stack.sh"
)

$files = @(
    foreach ($relativePath in $relativePaths) {
        $fullPath = Join-Path $projectRoot ($relativePath.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw "Required deployment file was not found: $relativePath"
        }
        $item = Get-Item -LiteralPath $fullPath
        [PSCustomObject]@{
            RelativePath = $relativePath
            FullPath = $item.FullName
            Bytes = $item.Length
            Sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
)

$mode = if ($Apply) { "APPLY" } else { "PREVIEW" }
$totalBytes = ($files | Measure-Object -Property Bytes -Sum).Sum
Write-Output "MODE=$mode"
Write-Output "TARGET=$PiUser@$PiHost`:$RemotePath"
Write-Output "FILE_COUNT=$($files.Count)"
Write-Output "TOTAL_BYTES=$totalBytes"
$files | ForEach-Object {
    Write-Output ("FILE={0} BYTES={1} SHA256={2}" -f $_.RelativePath, $_.Bytes, $_.Sha256)
}

if (-not $Apply) {
    Write-Output "NO_REMOTE_CHANGES=preview-only"
    Write-Output "Run again with -Apply only after the Raspberry Pi update is approved."
    exit 0
}

$sshOptions = @(
    "-i", $IdentityFile,
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes"
)
$destination = "{0}@{1}" -f $PiUser, $PiHost
$remoteDirectories = @(
    $files | ForEach-Object {
        $separator = $_.RelativePath.LastIndexOf("/")
        if ($separator -gt 0) {
            $_.RelativePath.Substring(0, $separator)
        }
    } | Sort-Object -Unique
)
$remoteDirectoryArguments = @("'$RemotePath'")
$remoteDirectoryArguments += $remoteDirectories | ForEach-Object { "'$RemotePath/$_'" }
$mkdirCommand = "mkdir -p -- " + ($remoteDirectoryArguments -join " ")

& ssh @sshOptions $destination $mkdirCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create one or more remote deployment directories."
}

foreach ($file in $files) {
    $remoteFile = "$RemotePath/$($file.RelativePath)"
    & scp @sshOptions -q $file.FullPath "${destination}:$remoteFile"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to transfer: $($file.RelativePath)"
    }
}

$scriptPaths = $files.RelativePath | Where-Object { $_ -like "scripts/*.sh" }
$chmodArguments = $scriptPaths | ForEach-Object { "'$RemotePath/$_'" }
& ssh @sshOptions $destination ("chmod 755 -- " + ($chmodArguments -join " "))
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set deployment script permissions."
}

$relativeArguments = $files.RelativePath -join " "
$remoteHashLines = @(& ssh @sshOptions $destination "cd '$RemotePath' && sha256sum -- $relativeArguments")
if ($LASTEXITCODE -ne 0) {
    throw "Remote SHA-256 calculation failed."
}

$remoteHashes = @{}
foreach ($line in $remoteHashLines) {
    if ($line -notmatch "^([0-9a-f]{64})\s+(.+)$") {
        throw "Unexpected remote checksum output: $line"
    }
    $remoteHashes[$Matches[2]] = $Matches[1]
}

foreach ($file in $files) {
    if (-not $remoteHashes.ContainsKey($file.RelativePath)) {
        throw "Remote checksum is missing: $($file.RelativePath)"
    }
    if ($remoteHashes[$file.RelativePath] -ne $file.Sha256) {
        throw "Checksum mismatch: $($file.RelativePath)"
    }
}

Write-Output "CHECKSUMS=verified"
Write-Output "DEPLOYMENT_STATUS=success"
