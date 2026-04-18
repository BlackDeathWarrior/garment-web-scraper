param(
  [double]$IntervalMinutes = 10,
  [int]$MaxProducts = 0,
  [string]$Sources = "flipkart,myntra,amazon",
  [int]$MaxRuns = 0,
  [switch]$NoAppendExisting
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe"
}

$logDir = Join-Path $repoRoot "outputs\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logDir "scraper-watch-$stamp.log"
$publicLog = Join-Path $repoRoot "frontend\public\scraper.log"
New-Item -ItemType Directory -Path (Split-Path -Parent $publicLog) -Force | Out-Null
# Reset public log each run so UI always shows the current session first.
Set-Content -Path $publicLog -Value "" -Encoding UTF8

Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

$args = @(
  "-m", "scraper.collect",
  "--watch",
  "--interval-minutes", $IntervalMinutes.ToString([System.Globalization.CultureInfo]::InvariantCulture),
  "--max-products", $MaxProducts.ToString(),
  "--sources", $Sources,
  "--max-runs", $MaxRuns.ToString()
)

if (-not $NoAppendExisting) {
  $args += "--append-existing"
}

if ($MaxProducts -le 0) {
  $maxLabel = "Unlimited"
} else {
  $maxLabel = $MaxProducts
}

Write-Host "[scraper] Starting watch mode..."
Write-Host "[scraper] Interval: $IntervalMinutes min | Max/source: $maxLabel | Sources: $Sources"
Write-Host "[scraper] Archive log: $logFile"
Write-Host "[scraper] UI log: $publicLog"
Write-Host "[scraper] Press Ctrl+C to stop."
Write-Host ""

& $pythonExe @args 2>&1 | Tee-Object -FilePath $publicLog | Tee-Object -FilePath $logFile
