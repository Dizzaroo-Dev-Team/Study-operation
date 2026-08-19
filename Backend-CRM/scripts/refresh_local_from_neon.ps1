# =====================================================================
# refresh_local_from_neon.ps1
#
# Pulls the current schema from Neon (source of truth), drops + recreates
# the local Postgres database, loads the schema, then seeds master data.
#
# Caveman version: "Neon big rock. Local small rock. Make small rock
# same shape as big rock, then put master-data acorns inside."
#
# Prereqs on dev's machine:
#   - psql + pg_dump on PATH (PostgreSQL client tools, version >= 15)
#   - Local Postgres running and reachable (default: localhost:5432, user postgres)
#   - Neon connection string (set NEON_DATABASE_URL env var, or pass -NeonUrl)
#
# Usage:
#   $env:NEON_DATABASE_URL = "postgresql://USER:PASS@HOST/DB?sslmode=require"
#   pwsh scripts/refresh_local_from_neon.ps1
#
#   # or with explicit args
#   pwsh scripts/refresh_local_from_neon.ps1 `
#     -NeonUrl "postgresql://..." `
#     -LocalDb crm_local `
#     -LocalUser postgres `
#     -LocalHost localhost
# =====================================================================

[CmdletBinding()]
param(
    [string]$NeonUrl   = $env:NEON_DATABASE_URL,
    [string]$LocalDb   = "crm_local",
    [string]$LocalUser = "postgres",
    [string]$LocalHost = "localhost",
    [int]   $LocalPort = 5432,
    [switch]$SkipDrop,
    [switch]$SkipSeeds
)

$ErrorActionPreference = "Stop"

if (-not $NeonUrl) {
    Write-Error "Neon connection string is required. Set `$env:NEON_DATABASE_URL or pass -NeonUrl."
}

# Resolve paths relative to Backend-CRM/ (this script lives in Backend-CRM/scripts/)
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Split-Path -Parent $scriptDir
Set-Location $backendRoot

$schemaFile  = Join-Path $backendRoot "local_schema.sql"
$setupFile   = Join-Path $scriptDir   "setup_local_from_neon.sql"

Write-Host ""
Write-Host "==> Backend root: $backendRoot"
Write-Host "==> Schema dump:  $schemaFile"
Write-Host "==> Local target: postgres://$LocalUser@$LocalHost`:$LocalPort/$LocalDb"
Write-Host ""

# --- 1. Refresh schema dump from Neon -------------------------------------
Write-Host "==> Step 1/4: pg_dump schema from Neon ..."
& pg_dump --no-owner --no-privileges --schema-only --schema=public `
    --file=$schemaFile $NeonUrl
if ($LASTEXITCODE -ne 0) { throw "pg_dump from Neon failed (exit $LASTEXITCODE)." }
Write-Host "    ok ($((Get-Item $schemaFile).Length) bytes)"

# --- 2. Drop + recreate local DB ------------------------------------------
$env:PGHOST = $LocalHost
$env:PGPORT = "$LocalPort"
$env:PGUSER = $LocalUser

if (-not $SkipDrop) {
    Write-Host "==> Step 2/4: drop + recreate local DB '$LocalDb' ..."
    & psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $LocalDb;"
    if ($LASTEXITCODE -ne 0) { throw "DROP DATABASE failed." }
    & psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $LocalDb;"
    if ($LASTEXITCODE -ne 0) { throw "CREATE DATABASE failed." }
} else {
    Write-Host "==> Step 2/4: -SkipDrop set, reusing existing '$LocalDb'."
}

# --- 3. Load schema + seeds via the SQL wrapper ---------------------------
Write-Host "==> Step 3/4: load schema + seeds into '$LocalDb' ..."
if ($SkipSeeds) {
    & psql -d $LocalDb -v ON_ERROR_STOP=1 -f $schemaFile
} else {
    & psql -d $LocalDb -v ON_ERROR_STOP=1 -f $setupFile
}
if ($LASTEXITCODE -ne 0) { throw "Loading schema/seeds failed." }

# --- 4. Done --------------------------------------------------------------
Write-Host ""
Write-Host "==> Step 4/4: done. Local '$LocalDb' now matches Neon."
Write-Host ""
Write-Host "Connection string for .env:"
Write-Host "  DATABASE_URL=postgresql://$LocalUser@$LocalHost`:$LocalPort/$LocalDb"
