param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8765,
  [string]$Sources = "amazon,myntra,flipkart",
  [int]$MaxProducts = 0
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe"
}

$logDir = Join-Path $repoRoot "outputs\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $logDir "scraper-worker-$stamp.out.log"
$err = Join-Path $logDir "scraper-worker-$stamp.err.log"

Write-Host "[worker] Starting local scraper worker..."
Write-Host "[worker] URL: http://${BindHost}:$Port"
Write-Host "[worker] Sources: $Sources | Max/source: $MaxProducts"
Write-Host "[worker] Out log: $out"
Write-Host "[worker] Err log: $err"
Write-Host "[worker] Press Ctrl+C to stop."
Write-Host ""

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

& $pythonExe -m scraper.worker `
  --host $BindHost `
  --port $Port `
  --sources $Sources `
  --max-products $MaxProducts
