# Run HiveFlowAI web UI locally (public site + portal).
# Usage: .\scripts\serve_web.ps1 [--port 8080] [--host 127.0.0.1]
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Missing .venv. Run: python -m venv .venv; .\scripts\install_dev.ps1"
}

& $venvPython (Join-Path $PSScriptRoot "serve_web.py") @args
