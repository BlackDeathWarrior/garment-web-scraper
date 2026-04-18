param(
  [double]$IntervalMinutes = 10,
  [int]$MaxProducts = 0,
  [string]$Sources = "flipkart,myntra,amazon",
  [int]$MaxRuns = 1,
  [switch]$NoAppendExisting
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path $PSScriptRoot
$runner = Join-Path $repoRoot "scraper\run_watch_cycle.ps1"

if (-not (Test-Path $runner)) {
  throw "Missing runner script: $runner"
}

Write-Host "[start] Launching live scraper terminal..."
Write-Host "[start] Use Ctrl+C to stop."
Write-Host ""

& $runner `
  -IntervalMinutes $IntervalMinutes `
  -MaxProducts $MaxProducts `
  -Sources $Sources `
  -MaxRuns $MaxRuns `
  -NoAppendExisting:$NoAppendExisting
