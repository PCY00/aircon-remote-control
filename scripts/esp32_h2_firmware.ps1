[CmdletBinding()]
param(
    [ValidateSet("build", "flash", "monitor")]
    [string]$Action = "build",

    [string]$Port,

    [string]$IdfPath = "C:\Espressif\frameworks\esp-idf-v5.5.4",
    [string]$IdfToolsPath = $env:IDF_TOOLS_PATH,
    [string]$BuildRoot = "C:\esp"
)

$ErrorActionPreference = "Stop"

# Never guess a device port on another PC. Validate before copying or exporting IDF.
if ($Action -in @("flash", "monitor") -and $Port -notmatch "^COM[1-9][0-9]*$") {
    throw "Specify the connected board's port with -Port COM<number>. No device was accessed."
}

$sourcePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\firmware\esp32-h2-ir-node")).Path
$asciiRoot = [System.IO.Path]::GetFullPath($BuildRoot)
if ($asciiRoot -match "[^\x20-\x7E]") {
    throw "BuildRoot must use an ASCII-only path for ESP-IDF on Windows."
}
# Different checkouts must not reuse each other's sdkconfig or generated files.
$hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $sourceHash = [BitConverter]::ToString(
        $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($sourcePath.ToLowerInvariant()))
    ).Replace("-", "").Substring(0, 12).ToLowerInvariant()
} finally {
    $hasher.Dispose()
}
$projectPath = Join-Path $asciiRoot "aircon-h2-ir-node-$sourceHash"

if (-not (Test-Path -LiteralPath (Join-Path $IdfPath "tools\idf.py"))) {
    throw "ESP-IDF was not found at $IdfPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $IdfPath "export.ps1"))) {
    throw "ESP-IDF export.ps1 was not found at $IdfPath"
}
if (-not $IdfToolsPath) {
    $IdfToolsPath = "C:\Espressif"
}

if (-not (Test-Path -LiteralPath $asciiRoot)) {
    New-Item -ItemType Directory -Path $asciiRoot | Out-Null
}

if (-not (Test-Path -LiteralPath $projectPath)) {
    New-Item -ItemType Directory -Path $projectPath | Out-Null
}

# ESP-IDF's Windows Kconfig tools can decode a Korean project path with the
# legacy cp949 codec.  A junction is not sufficient because CMake resolves it
# back to the original path, so copy only the firmware sources to an ASCII-only
# staging directory and keep all generated files there.
New-Item -ItemType Directory -Path (Join-Path $projectPath "main") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourcePath "CMakeLists.txt") -Destination $projectPath -Force
Copy-Item -LiteralPath (Join-Path $sourcePath "sdkconfig.defaults") -Destination $projectPath -Force
Copy-Item -Path (Join-Path $sourcePath "main\*") -Destination (Join-Path $projectPath "main") -Recurse -Force

$configPath = Join-Path $projectPath "sdkconfig"
if ((Test-Path -LiteralPath $configPath) -and
    -not (Select-String -LiteralPath $configPath -Pattern '^CONFIG_IDF_TARGET="esp32h2"$' -Quiet)) {
    throw "The staging sdkconfig is not for esp32h2. Choose a different -BuildRoot."
}
Write-Output "BUILD_DIRECTORY=$projectPath"

$env:IDF_PATH = $IdfPath
$env:IDF_TOOLS_PATH = $IdfToolsPath
. (Join-Path $IdfPath "export.ps1")

function Invoke-Idf {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & idf.py @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "idf.py failed with exit code $LASTEXITCODE"
    }
}

Push-Location $projectPath
try {
    if (-not (Test-Path -LiteralPath "sdkconfig")) {
        Invoke-Idf -Arguments @("set-target", "esp32h2")
    }

    switch ($Action) {
        "build" {
            Invoke-Idf -Arguments @("build")
        }
        "flash" {
            Invoke-Idf -Arguments @("-p", $Port, "flash")
        }
        "monitor" {
            Invoke-Idf -Arguments @("-p", $Port, "monitor")
        }
    }
} finally {
    Pop-Location
}
