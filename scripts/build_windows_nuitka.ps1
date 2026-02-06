param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python not found in PATH"
}

python -m venv .venv

$Activate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
  throw "Venv activation script not found: $Activate"
}

. $Activate

python -m pip install -U pip
pip install -r requirements.txt

$nuitkaArgs = @(
  "launcher.py"
  "--standalone"
  "--enable-plugin=tk-inter"
  "--include-data-dir=static=static"
  "--include-data-file=icon.png=icon.png"
  "--include-data-file=icon.ico=icon.ico"
  "--include-package=customtkinter"
  "--include-package-data=customtkinter"
  "--windows-disable-console"
  "--output-dir=dist-nuitka-win"
  "--output-filename=CyberDeck.exe"
)

if ($DryRun) {
  Write-Host "Dry run. Nuitka command:"
  Write-Host ("python -m nuitka {0}" -f ($nuitkaArgs -join " "))
  exit 0
}

python -m nuitka @nuitkaArgs

Write-Host ""
Write-Host ("Built: {0}" -f (Join-Path $RepoRoot "dist-nuitka-win\CyberDeck.dist\CyberDeck.exe"))
