# =============================================================================
#  Libra — Library OS · one-command local start (Windows PowerShell)
#  Usage:  .\start.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\backend"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
Write-Host "Installing dependencies (first run may take a minute)..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -r requirements.txt --quiet

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (SQLite development defaults)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Libra — Library OS" -ForegroundColor Green
Write-Host "  App:  http://localhost:8000" -ForegroundColor Green
Write-Host "  Docs: http://localhost:8000/api/docs" -ForegroundColor Green
Write-Host ""
Write-Host "  Demo accounts:" -ForegroundColor Green
Write-Host "    admin@library.com     / Admin@123      (administrator)"
Write-Host "    librarian@library.com / Librarian@123  (librarian)"
Write-Host "    member@library.com    / Member@123     (member)"
Write-Host ""

& $python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
