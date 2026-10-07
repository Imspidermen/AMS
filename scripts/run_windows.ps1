<#
.SYNOPSIS
    Build the React frontend (if needed) and start the complete SSAMS application on ONE port.

.DESCRIPTION
    Unified/production-style run mode: FastAPI serves the built frontend at `/` and the API at
    `/api`, then you can expose the whole application with a single tunnel:

        ngrok http 8000

    Use scripts\dev_windows.ps1 for the two-process Vite development workflow instead.

.PARAMETER Rebuild
    Force `npm run build` even when frontend\dist already exists.

.PARAMETER SkipBuild
    Serve the existing frontend\dist without running a build (fails if it is missing).
#>
param(
    [switch]$Rebuild,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Root '.env'
$IndexHtml = Join-Path $Frontend 'dist\index.html'

if (-not (Test-Path $EnvFile)) { throw 'Missing .env. Run scripts\setup_windows.ps1 and configure the secret values.' }
$EnvText = Get-Content -Raw $EnvFile
if ($EnvText -match '(?m)^SESSION_SECRET=(replace-|\s*$)' -or $EnvText -match '(?m)^BIOMETRIC_ENCRYPTION_KEY=(replace-|\s*$)') {
    throw 'Replace the secret placeholders in .env before starting SSAMS.'
}
if (-not (Test-Path $VenvPython)) { throw 'Backend environment missing. Run scripts\setup_windows.ps1 first.' }
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) { throw 'Frontend dependencies missing. Run scripts\setup_windows.ps1 first.' }

$Port = 8000
$Match = [regex]::Match($EnvText, '(?m)^APP_PORT=(\d+)\s*$')
if ($Match.Success) { $Port = [int]$Match.Groups[1].Value }

if ($SkipBuild -and -not (Test-Path $IndexHtml)) {
    throw "frontend\dist\index.html is missing. Run without -SkipBuild so the frontend can be built."
}
if (-not $SkipBuild -and ($Rebuild -or -not (Test-Path $IndexHtml))) {
    Write-Host 'Building the React frontend (npm run build)...' -ForegroundColor Cyan
    Push-Location $Frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. Fix the reported error and retry.' }
    } finally { Pop-Location }
}

Push-Location $Backend
try {
    & $VenvPython -m app.cli migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally { Pop-Location }

Write-Host ''
Write-Host 'SSAMS is starting in unified single-port mode:' -ForegroundColor Green
Write-Host "  Application : http://localhost:$Port/"
Write-Host "  API         : http://localhost:$Port/api/v1"
Write-Host "  API docs    : http://localhost:$Port/docs"
Write-Host "  Health      : http://localhost:$Port/api/health"
Write-Host '  Timezone    : Asia/Kolkata (IST, UTC+05:30)'
Write-Host ''
Write-Host "Expose the whole application with ONE tunnel, e.g.: ngrok http $Port" -ForegroundColor Yellow
Write-Host 'Camera/location on a phone need the HTTPS URL a tunnel provides (http://localhost is local-only).' -ForegroundColor Yellow
Write-Host 'Press Ctrl+C to stop the server.'
Write-Host ''

Push-Location $Backend
try {
    # Serves frontend\dist at / and the API at /api on APP_HOST:APP_PORT (0.0.0.0:8000 by default).
    & $VenvPython -m app.cli serve
} finally { Pop-Location }
