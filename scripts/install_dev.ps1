# Editable install of all meshflow packages (run from repo root).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install -e ".\packages\meshflow-platform"
python -m pip install -e ".\packages\meshflow-connectors"
python -m pip install -e ".\packages\meshflow-lake"
python -m pip install -e ".\packages\meshflow-dna"
python -m pip install -e ".\packages\meshflow-portal"
python -m pip install -e ".\packages\meshflow[dev]"
Write-Host "Installed meshflow packages in editable mode."
