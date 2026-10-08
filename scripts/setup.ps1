$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
npm ci --prefix frontend

Write-Host "Setup complete. Configure backend\.env, then run: .\scripts\dev.ps1"
