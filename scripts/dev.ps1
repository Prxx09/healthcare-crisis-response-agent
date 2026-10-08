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

Write-Host "API:       http://127.0.0.1:8000"
Write-Host "Dashboard: http://127.0.0.1:5173"

$Api = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--app-dir", "backend" -NoNewWindow -PassThru
try {
    npm run dev --prefix frontend -- --host 127.0.0.1
}
finally {
    if ($Api -and -not $Api.HasExited) {
        Stop-Process -Id $Api.Id
    }
}
