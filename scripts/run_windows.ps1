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

$PowerShellExe = (Get-Process -Id $PID).Path
$BackendCommand = "Set-Location -LiteralPath '$Backend'; & '$VenvPython' -m app.cli migrate; if (`$LASTEXITCODE -eq 0) { & '$VenvPython' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 }"
$FrontendCommand = "Set-Location -LiteralPath '$Frontend'; npm run dev -- --host 0.0.0.0 --port 5173"
Start-Process -FilePath $PowerShellExe -ArgumentList @('-NoExit', '-Command', $BackendCommand) -WorkingDirectory $Backend
Start-Process -FilePath $PowerShellExe -ArgumentList @('-NoExit', '-Command', $FrontendCommand) -WorkingDirectory $Frontend
Write-Host 'SSAMS development terminals opened. Visit http://localhost:5173 (or the approved HTTPS URL for camera/location testing).' -ForegroundColor Green
Write-Host 'Development HTTP does not grant camera/location access on a remote phone. Use a trusted HTTPS reverse proxy/certificate.' -ForegroundColor Yellow
