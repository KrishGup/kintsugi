<#
.SYNOPSIS
  One-time setup of this checkout on Windows, everything kept on the project drive (nothing new on C:).

.DESCRIPTION
  Creates .venv in the repo, installs the package with dev + tools extras, installs and builds the web app, checks for
  OpenSCAD, Git and Node, points every cache (pip, npm, Playwright browsers, the impeccable engine) at <repo>\.cache,
  and writes .env from .env.example if there is none. Re-runnable: every step is idempotent.

.PARAMETER Serve
  Start `kin serve` at the end.

.PARAMETER SkipWeb
  Leave the web app alone (web\dist is committed; only needed after UI changes).

.EXAMPLE
  PS X:\Code\26Projects\kitsug> scripts\bootstrap.ps1
  PS X:\Code\26Projects\kitsug> scripts\bootstrap.ps1 -Serve
#>
[CmdletBinding()]
param([switch]$Serve, [switch]$SkipWeb)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Write-Host "Kintsugi at $Root" -ForegroundColor Cyan

# Native tools (pip, npm, OpenSCAD) write warnings to stderr; Windows PowerShell 5.1 turns those into terminating
# errors under "Stop". Run every native command through here: stderr flows through, the exit code is what counts.
function Run([string]$what, [scriptblock]$cmd) {
  $ErrorActionPreference = "Continue"
  & $cmd 2>&1 | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { $_ } }
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}
function Need($name, $exe, $probe, $hint) {
  $ErrorActionPreference = "Continue"
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { Write-Host "  MISSING $name - $hint" -ForegroundColor Yellow; return $false }
  $v = ""
  try { $v = (& $probe 2>&1 | Out-String).Trim() } catch {}
  Write-Host "  ok   $name  $(($v -split "`n")[0])"
  return $true
}

# ---- caches on this drive, not C: -----------------------------------------------------------------------------------
$Cache = Join-Path $Root ".cache"
New-Item -ItemType Directory -Force -Path $Cache, "$Cache\pip", "$Cache\npm", "$Cache\ms-playwright", "$Cache\impeccable" | Out-Null
$env:PIP_CACHE_DIR = "$Cache\pip"
$env:npm_config_cache = "$Cache\npm"
$env:PLAYWRIGHT_BROWSERS_PATH = "$Cache\ms-playwright"
$env:IMPECCABLE_HOME = "$Cache\impeccable"
# make them stick for future shells (user environment; registry only, no files on C:)
foreach ($pair in @(@("PIP_CACHE_DIR", $env:PIP_CACHE_DIR), @("PLAYWRIGHT_BROWSERS_PATH", $env:PLAYWRIGHT_BROWSERS_PATH), @("IMPECCABLE_HOME", $env:IMPECCABLE_HOME))) {
  [Environment]::SetEnvironmentVariable($pair[0], $pair[1], "User")
}

# ---- prerequisites ---------------------------------------------------------------------------------------------------
Write-Host "Prerequisites" -ForegroundColor Cyan
# python: the `py` launcher with 3.11+, else a `python` on PATH that is 3.11+
$Py = $null
foreach ($cand in @(@("py", "-3.11"), @("py", "-3.12"), @("py", "-3.13"), @("python", $null))) {
  if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
  $ErrorActionPreference = "Continue"
  $ver = if ($cand[1]) { (& $cand[0] $cand[1] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null) } else { (& $cand[0] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null) }
  $ErrorActionPreference = "Stop"
  if ($ver -and [version]$ver -ge [version]"3.11") { $Py = @($cand[0]) + @($cand[1] | Where-Object { $_ }); Write-Host "  ok   Python $ver  ($($Py -join ' '))"; break }
}
$py = [bool]$Py
if (-not $py) { Write-Host "  MISSING Python 3.11+ - winget install Python.Python.3.11 (or 3.12)" -ForegroundColor Yellow }
$node = Need "Node 22" "node" { node --version } "winget install OpenJS.NodeJS.LTS"
$git = Need "Git" "git" { git --version } "winget install Git.Git (Git Bash is used for the designer's shell tool)"
$Drive = (Split-Path -Qualifier $Root)                      # a portable OpenSCAD lives on the same drive as the checkout
$Portable = @("$Drive\Tools\OpenSCAD\openscad.com", "$Drive\Tools\OpenSCAD\openscad.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$scad = $false
if ($env:KIN_OPENSCAD_BIN -and (Test-Path $env:KIN_OPENSCAD_BIN)) { $scad = Need "OpenSCAD (KIN_OPENSCAD_BIN)" $env:KIN_OPENSCAD_BIN { & $env:KIN_OPENSCAD_BIN --version } "" }
elseif (Get-Command openscad -ErrorAction SilentlyContinue) { $scad = Need "OpenSCAD" "openscad" { openscad --version } "" }
elseif ($Portable) {
  $env:KIN_OPENSCAD_BIN = $Portable; [Environment]::SetEnvironmentVariable("KIN_OPENSCAD_BIN", $Portable, "User")
  $scad = Need "OpenSCAD (portable)" $Portable { & $Portable --version } ""
}
else { Write-Host "  MISSING OpenSCAD - unzip the 2021.01 portable build to $Drive\Tools\OpenSCAD (keeps C: clean; the app finds it there by itself) or 'winget install OpenSCAD.OpenSCAD'; set KIN_OPENSCAD_BIN if it is somewhere else" -ForegroundColor Yellow }
if (-not ($py -and $node -and $git)) { throw "install the missing prerequisites and run again" }

# ---- python ----------------------------------------------------------------------------------------------------------
Write-Host "Python environment (.venv on this drive)" -ForegroundColor Cyan
$Venv = Join-Path $Root ".venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VPy)) {
  $venvArgs = @($Py | Select-Object -Skip 1) + @("-m", "venv", $Venv)
  Run "venv" { & $Py[0] $venvArgs }
}
Run "pip upgrade" { & $VPy -m pip install --upgrade pip --quiet --disable-pip-version-check }
Run "pip install" { & $VPy -m pip install -e ".[dev,tools]" --quiet --disable-pip-version-check }
Run "playwright chromium" { & $VPy -m playwright install chromium }
$ErrorActionPreference = "Continue"
$kinVer = (& $VPy -c "import sys, kintsugi; print('kintsugi on Python ' + sys.version.split()[0])" 2>&1 | Out-String).Trim()
$ErrorActionPreference = "Stop"
Write-Host "  ok   $kinVer"

# ---- web -------------------------------------------------------------------------------------------------------------
if (-not $SkipWeb) {
  Write-Host "Web app" -ForegroundColor Cyan
  Push-Location web
  try {
    if (Test-Path "package-lock.json") { Run "npm ci" { npm ci --no-audit --no-fund --loglevel=error } } else { Run "npm install" { npm install --no-audit --no-fund --loglevel=error } }
    Run "npm run build" { npm run build --silent }
  } finally { Pop-Location }
  Write-Host "  ok   web\dist built"
}

# ---- settings --------------------------------------------------------------------------------------------------------
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "  wrote .env from .env.example - put OPENAI_API_KEY in it, or paste the key in the app's Settings" -ForegroundColor Yellow }

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1 ; kin serve        -> http://localhost:8000"
Write-Host "  python scripts\walk.py                         -> drives the UI in a headless browser, screenshots in scratch\walk\"
Write-Host "  ruff check kintsugi tests ; pytest -m 'not llm'"
if (-not $scad) { Write-Host "  (OpenSCAD is missing: compiles will fail until it is installed)" -ForegroundColor Yellow }
if ($Serve) { & (Join-Path $Venv "Scripts\kin.exe") serve }
