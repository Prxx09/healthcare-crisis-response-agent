$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Python environment not found. Run: .\scripts\setup.ps1"
}

if (-not (Test-Path ".\frontend\node_modules")) {
    Write-Error "Frontend dependencies not found. Run: .\scripts\setup.ps1"
}

if (-not (Test-Path ".\backend\.env")) {
    Write-Error "backend\.env is missing. Copy backend\.env.example and add the required values."
}

$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
if ($BackendPort -notin @("8000", "8001", "8002")) {
    Write-Error "BACKEND_PORT must be 8000, 8001, or 8002."
}
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "5173" }
if ($FrontendPort -notin @("5173", "5174")) {
    Write-Error "FRONTEND_PORT must be 5173 or 5174."
}
$env:PUBLIC_APP_URL = "http://127.0.0.1:$FrontendPort"

Write-Host "API:       http://127.0.0.1:$BackendPort"
Write-Host "Dashboard: $env:PUBLIC_APP_URL"

$Api = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", $BackendPort, "--app-dir", "backend" -NoNewWindow -PassThru
try {
    npm run dev --prefix frontend -- --host 127.0.0.1 --port $FrontendPort --strictPort
}
finally {
    if ($Api -and -not $Api.HasExited) {
        Stop-Process -Id $Api.Id
    }
}
