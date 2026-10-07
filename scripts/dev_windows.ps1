<#
.SYNOPSIS
    Development mode: FastAPI on APP_PORT plus the Vite dev server on port 5173.

.DESCRIPTION
    Keeps the fast Vite editing experience (hot reload, HMR). Vite proxies /api to the backend, so
    the browser only talks to http://localhost:5173. Use scripts\run_windows.ps1 for the unified
    single-port application (and for tunnels).
#>
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Root '.env'

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

$PowerShellExe = (Get-Process -Id $PID).Path
$BackendCommand = "Set-Location -LiteralPath '$Backend'; & '$VenvPython' -m app.cli migrate; if (`$LASTEXITCODE -eq 0) { & '$VenvPython' -m app.cli serve }"
$FrontendCommand = "Set-Location -LiteralPath '$Frontend'; npm run dev -- --host 0.0.0.0 --port 5173"
Start-Process -FilePath $PowerShellExe -ArgumentList @('-NoExit', '-Command', $BackendCommand) -WorkingDirectory $Backend
Start-Process -FilePath $PowerShellExe -ArgumentList @('-NoExit', '-Command', $FrontendCommand) -WorkingDirectory $Frontend
Write-Host "SSAMS development terminals opened (API on $Port, Vite on 5173)." -ForegroundColor Green
Write-Host 'Open http://localhost:5173 — Vite proxies /api to the API, so the browser uses one origin.'
Write-Host 'For the unified single-port application (and for ngrok/Cloudflare tunnels) use scripts\run_windows.ps1.' -ForegroundColor Yellow
