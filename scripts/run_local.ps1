$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found. Run: python -m venv .venv"
}

$hostAddress = if ($env:AIRCON_HOST) { $env:AIRCON_HOST } else { "127.0.0.1" }
$servicePort = if ($env:AIRCON_PORT) { $env:AIRCON_PORT } else { "8001" }
# The app's Host allowlist is built from AIRCON_HOST (loopback is always allowed).
$env:AIRCON_HOST = $hostAddress

Push-Location $projectRoot
try {
    & $pythonPath -m uvicorn app.main:app --host $hostAddress --port $servicePort --reload
}
finally {
    Pop-Location
}
