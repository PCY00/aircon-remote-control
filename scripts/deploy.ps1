[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$PiHost = "AC",
    [string]$PiUser = "air",
    [string]$RemotePath = "/home/air/aircon-controller",
    [string]$IdentityFile = (Join-Path $HOME ".ssh\airconpi"),
    [string]$KnownHostsFile = "",
    [string[]]$Include = @()
)

$ErrorActionPreference = "Stop"

function Get-DeploymentSha256([string]$LiteralPath) {
    # Works in Windows PowerShell even when the utility module's Get-FileHash
    # function is unavailable to a non-interactive pipeline.
    $stream = [System.IO.File]::OpenRead($LiteralPath)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

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
if ($KnownHostsFile -and -not (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf)) {
    throw "Verified SSH host record was not found."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectPrefix = $projectRoot.TrimEnd("\") + "\"
$recursiveRoots = @("app", "deploy", "device_profiles", "tests")
$explicitFiles = @(
    "scripts/run_pi.sh",
    "scripts/setup_app_mqtt.sh",
    ".env.example",
    "pyproject.toml",
    "README.md"
)
# AGENTS.md: never sync Git data, virtualenvs, caches, secrets, local logs,
# temporary files, editor settings or runtime data, even inside copied folders.
$excludedDirectoryNames = @(
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".git", ".venv", "venv", ".deploy", "secrets", "logs", "runtime", "runtime_preview",
    "tmp", "node_modules", ".vscode", ".idea"
)
$excludedExtensions = @(".pyc", ".pyo", ".key", ".pem", ".pfx", ".p12", ".log")

function Test-ExcludedDeploymentFile([string]$RelativePath) {
    $segments = $RelativePath.Replace("\", "/").Split("/")
    $name = $segments[-1]
    return (
        ($segments | Where-Object { $_ -in $excludedDirectoryNames }) -or
        ($name -like ".env*" -and $name -ne ".env.example") -or
        [System.IO.Path]::GetExtension($name) -in $excludedExtensions
    )
}

$candidateFiles = @()
if ($Include.Count -gt 0) {
    foreach ($requestedPath in $Include) {
        $relativeFile = $requestedPath.Replace("\", "/")
        if (
            $relativeFile -notmatch "^[A-Za-z0-9._/-]+$" -or
            $relativeFile.StartsWith("/") -or
            $relativeFile -match "(^|/)\.\.($|/)"
        ) {
            throw "Include contains an unsupported relative path: $requestedPath"
        }
        if (Test-ExcludedDeploymentFile $relativeFile) {
            throw "Include names a secret, log, cache or runtime file: $relativeFile"
        }
        $fullFile = Join-Path $projectRoot ($relativeFile.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $fullFile -PathType Leaf)) {
            throw "Included deployment file was not found: $relativeFile"
        }
        $candidateFiles += Get-Item -LiteralPath $fullFile
    }
} else {
    foreach ($relativeRoot in $recursiveRoots) {
        $fullRoot = Join-Path $projectRoot $relativeRoot
        if (-not (Test-Path -LiteralPath $fullRoot -PathType Container)) {
            throw "Required source directory was not found: $relativeRoot"
        }

        $candidateFiles += Get-ChildItem -LiteralPath $fullRoot -File -Recurse | Where-Object {
            -not (Test-ExcludedDeploymentFile $_.FullName.Substring($projectPrefix.Length))
        }
    }

    foreach ($relativeFile in $explicitFiles) {
        $fullFile = Join-Path $projectRoot ($relativeFile.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $fullFile -PathType Leaf)) {
            throw "Required source file was not found: $relativeFile"
        }
        $candidateFiles += Get-Item -LiteralPath $fullFile
    }
}

$files = @(
    $candidateFiles |
        Sort-Object FullName -Unique |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($projectPrefix.Length).Replace("\", "/")
            if ($relativePath -notmatch "^[A-Za-z0-9._/-]+$") {
                throw "Deployment path contains unsupported characters: $relativePath"
            }
            [PSCustomObject]@{
                RelativePath = $relativePath
                FullPath = $_.FullName
                Bytes = $_.Length
                Sha256 = Get-DeploymentSha256 $_.FullName
            }
        }
)

if ($files.Count -eq 0) {
    throw "Deployment manifest is empty."
}

$totalBytes = ($files | Measure-Object -Property Bytes -Sum).Sum
$mode = if ($Apply) { "APPLY" } else { "PREVIEW" }
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
if ($KnownHostsFile) {
    $sshOptions += @("-o", "UserKnownHostsFile=$KnownHostsFile")
}

$remoteDirectories = @(
    $files | ForEach-Object {
        $separator = $_.RelativePath.LastIndexOf("/")
        if ($separator -gt 0) {
            $_.RelativePath.Substring(0, $separator)
        }
    } | Where-Object { $_ } | Sort-Object -Unique
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
    $remoteSpec = "${destination}:$remoteFile"
    & scp @sshOptions -q $file.FullPath $remoteSpec
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to transfer: $($file.RelativePath)"
    }
}

if ($files.RelativePath -contains "scripts/run_pi.sh") {
    & ssh @sshOptions $destination "chmod 755 -- '$RemotePath/scripts/run_pi.sh'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set the Pi run script executable bit."
    }
}

$relativeArguments = $files.RelativePath -join " "
$hashCommand = "cd '$RemotePath' && sha256sum -- $relativeArguments"
$remoteHashLines = @(& ssh @sshOptions $destination $hashCommand)
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
