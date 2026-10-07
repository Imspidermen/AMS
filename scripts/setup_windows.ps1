$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Node = Get-Command node -ErrorAction SilentlyContinue
if (-not $Node) { throw 'Node.js was not found. Install Node.js 22.12+, 24.x, or 26+ and rerun this script.' }
$NodeParts = ((& node --version).Trim().TrimStart('v') -split '\.')
$NodeMajor = [int]$NodeParts[0]
$NodeMinor = [int]$NodeParts[1]
$NodeSupported = ($NodeMajor -eq 22 -and $NodeMinor -ge 12) -or $NodeMajor -eq 24 -or $NodeMajor -ge 26
if (-not $NodeSupported) { throw "Unsupported Node.js $(& node --version). Use 22.12+, 24.x, or 26+." }

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    & py -3.11 -m venv (Join-Path $Backend '.venv')
} else {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) { throw 'Python 3.11 was not found. Install Python 3.11 and rerun this script.' }
    & python -m venv (Join-Path $Backend '.venv')
}
if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed.' }
& $VenvPython -m pip install -r (Join-Path $Backend 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

Push-Location $Frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
} finally { Pop-Location }

New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data') | Out-Null
$EnvFile = Join-Path $Root '.env'
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root '.env.example') $EnvFile
    Write-Host 'Created .env from the safe template. Replace both secret placeholders before running SSAMS.' -ForegroundColor Yellow
} else {
    Write-Host 'Existing .env preserved. Review database, secret, timezone and cookie settings.'
}
Write-Host @'
Dependencies are installed. Before starting the app:
  1. Edit .env and set unique SESSION_SECRET and BIOMETRIC_ENCRYPTION_KEY values.
  2. Generate candidates with: cd backend; .venv\Scripts\python.exe -m app.cli generate-secrets
  3. Start the unified single-port app (http://localhost:8000) with:
       powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1
     For the Vite development workflow (http://localhost:5173) use scripts\dev_windows.ps1.
The application timezone defaults to Asia/Kolkata (IST, UTC+05:30); your Windows timezone is left untouched.
'@
