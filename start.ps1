param(
    [string]$Host = "127.0.0.1",
    [string]$Port = "8001",
    [string]$OvmsBaseUrl = $Env:OVMS_BASE_URL
)

# Resolve repo root based on this script location so it works from any CWD.
$repoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $PSCommandPath }
$backendPath = Join-Path $repoRoot "backend"
$venvActivate = Join-Path $backendPath ".venv/Scripts/Activate.ps1"

if (-not (Test-Path $backendPath)) {
    Write-Error "Backend directory not found at $backendPath"; exit 1
}

if (-not (Test-Path $venvActivate)) {
    Write-Error ".venv not found. Create it first (e.g., python -m venv backend/.venv && pip install -r backend/requirements.txt)."; exit 1
}

# Default OVMS URL if not set anywhere; override via env or parameter.
if (-not $OvmsBaseUrl) { $OvmsBaseUrl = "http://127.0.0.1:8000" }
$Env:OVMS_BASE_URL = $OvmsBaseUrl

Push-Location $backendPath
try {
    Write-Host "Activating venv..."
    . $venvActivate

    Write-Host "Starting API at http://$Host:$Port (OVMS_BASE_URL=$Env:OVMS_BASE_URL)"
    uvicorn app:app --host $Host --port $Port
} finally {
    Pop-Location
}
