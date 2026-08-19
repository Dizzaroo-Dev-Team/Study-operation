# Simple one-command DB setup. Run from Backend-CRM:
#   .\migrate.ps1
#   .\migrate.ps1 -WithSeeds

param([switch]$WithSeeds)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "crm_user" }
$pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { "crm_db" }

function Run-Sql([string]$path) {
    Write-Host "Running $path ..."
    Get-Content $path -Raw | docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "Failed: $path" }
}

Write-Host "Starting postgres (if needed) ..."
docker compose up -d postgres | Out-Null

Run-Sql "scripts/setup_local_db_full.sql"

Get-ChildItem migrations -Filter "*.sql" -File |
    Where-Object { $_.Name -notmatch '^(reset_|rename_|delete_|update_|ensure_|drop_)' } |
    Sort-Object Name |
    ForEach-Object { Run-Sql $_.FullName }

if ($WithSeeds) {
    Write-Host "Running seed scripts ..."
    docker compose exec -T backend python migrations/seed/seed_budgeting_master_data.py
    docker compose exec -T backend python migrations/seed/seed_categories_and_bundles.py
}

Write-Host "Done — database is ready."
