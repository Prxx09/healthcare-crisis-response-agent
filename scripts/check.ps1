$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m compileall backend/app
npm run build --prefix frontend
