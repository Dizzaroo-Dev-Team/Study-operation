# Backend Startup Script
# Run this script to start the backend with all environment variables set

Write-Host "Starting Backend Server..." -ForegroundColor Cyan

# Set environment variables. Credentials come from the environment — never
# hard-code them here (compose defaults: POSTGRES_USER/POSTGRES_PASSWORD).
$postgresHostPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5434" }
if (-not $env:DATABASE_URL) {
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "crm_user" }
    $pgPass = $env:POSTGRES_PASSWORD
    if (-not $pgPass) {
        Write-Host "POSTGRES_PASSWORD (or a full DATABASE_URL) must be set - refusing to guess credentials." -ForegroundColor Red
        exit 1
    }
    $pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "crm_db" }
    $env:DATABASE_URL = "postgresql+asyncpg://${pgUser}:${pgPass}@localhost:${postgresHostPort}/${pgDb}"
}
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL = "redis://localhost:6379/1"
$env:MOCK_PROVIDER_TOKEN = "mock_token_123"

Write-Host "Environment variables set:" -ForegroundColor Green
$maskedUrl = $env:DATABASE_URL -replace "://([^:/@]+):[^@]+@", "://`$1:***@"
Write-Host "  DATABASE_URL: $maskedUrl" -ForegroundColor Gray
Write-Host "  REDIS_URL: $env:REDIS_URL" -ForegroundColor Gray
Write-Host "  CELERY_BROKER_URL: $env:CELERY_BROKER_URL" -ForegroundColor Gray
Write-Host "  MOCK_PROVIDER_TOKEN: $env:MOCK_PROVIDER_TOKEN" -ForegroundColor Gray
Write-Host ""

# Check if venv is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠️  Virtual environment not activated!" -ForegroundColor Yellow
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & ".\venv\Scripts\Activate.ps1"
}

# Run uvicorn
Write-Host "Starting uvicorn server..." -ForegroundColor Cyan
Write-Host "Backend will be available at: http://localhost:8000" -ForegroundColor Green
Write-Host "API Docs at: http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

