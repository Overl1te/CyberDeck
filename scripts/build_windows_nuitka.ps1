param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
$IconIco = Join-Path $RepoRoot "icon.ico"
$RequirementsBuild = Join-Path $RepoRoot "requirements-build.txt"
$LauncherI18nJson = Join-Path $RepoRoot "cyberdeck\launcher\i18n.json"

function Stop-CyberDeckFromDist {
  param(
    [Parameter(Mandatory = $true)]
    [string]$DistPath
  )

  $distRoot = ([System.IO.Path]::GetFullPath($DistPath)).TrimEnd('\') + '\'
  $killed = 0

  try {
    $procList = Get-CimInstance Win32_Process -Filter "Name='CyberDeck.exe'"
    foreach ($proc in $procList) {
      $exePath = [string]$proc.ExecutablePath
      if (-not $exePath) {
        continue
      }
      if ($exePath.StartsWith($distRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        $killed++
      }
    }
  } catch {
    # Fallback when CIM path resolution is unavailable.
    Get-Process -Name "CyberDeck" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  }

  if ($killed -gt 0) {
    Write-Host ("Stopped {0} running CyberDeck process(es) from dist." -f $killed)
    Start-Sleep -Milliseconds 700
  }
}

function Remove-PathWithRetries {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [int]$Retries = 6
  )

  for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    if (-not (Test-Path $Path)) {
      return $true
    }

    try {
      Remove-Item -Recurse -Force $Path -ErrorAction Stop
    } catch {
      if ($attempt -ge $Retries) {
        return $false
      }
      Start-Sleep -Milliseconds (350 * $attempt)
    }
  }

  return (-not (Test-Path $Path))
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python not found in PATH"
}
if (-not (Test-Path $IconIco)) {
  throw "icon.ico not found: $IconIco"
}
if (-not (Test-Path $RequirementsBuild)) {
  throw "requirements-build.txt not found: $RequirementsBuild"
}
if (-not (Test-Path $LauncherI18nJson)) {
  throw "launcher i18n.json not found: $LauncherI18nJson"
}

$timelinePatterns = @(
  "*timeline*.gif",
  "*Timeline*.gif",
  "*timeline*.webp",
  "*Timeline*.webp",
  "*timeline*.png",
  "*Timeline*.png",
  "*timeline*.jpg",
  "*Timeline*.jpg",
  "*timeline*.jpeg",
  "*Timeline*.jpeg",
  "*timeline*.bmp",
  "*Timeline*.bmp"
)
$timelineMedia = @()
foreach ($pattern in $timelinePatterns) {
  $timelineMedia += Get-ChildItem -Path $RepoRoot -File -Filter $pattern -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
}
$timelineMedia = @($timelineMedia | Sort-Object -Unique)

$nuitkaArgs = @(
  "launcher.py"
  "--standalone"
  "--enable-plugin=tk-inter"
  "--include-data-dir=static=static"
  "--include-data-file=icon.png=icon.png"
  "--include-data-file=icon.ico=icon.ico"
  "--include-data-file=logo.gif=logo.gif"
  "--include-data-file=icon-qr-code.png=icon-qr-code.png"
  "--include-data-file=cyberdeck/launcher/i18n.json=cyberdeck/launcher/i18n.json"
  "--windows-icon-from-ico=$IconIco"
  "--include-package=customtkinter"
  "--include-package-data=customtkinter"
  "--windows-console-mode=disable"
  "--windows-uac-admin"
  "--output-dir=dist"
  "--output-filename=CyberDeck.exe"
)
foreach ($mediaPath in $timelineMedia) {
  $mediaName = [System.IO.Path]::GetFileName($mediaPath)
  $nuitkaArgs += "--include-data-file=$mediaPath=$mediaName"
}

if ($DryRun) {
  Write-Host "Dry run. Nuitka command:"
  Write-Host ("python -m nuitka {0}" -f ($nuitkaArgs -join " "))
  exit 0
}

python -m venv .venv

$Activate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
  throw "Venv activation script not found: $Activate"
}

. $Activate

python -m pip install -U pip
pip install -r requirements-build.txt

$distDir = Join-Path $RepoRoot "dist"
if (Test-Path $distDir) {
  Stop-CyberDeckFromDist -DistPath $distDir
  $cleanOk = Remove-PathWithRetries -Path $distDir
  if (-not $cleanOk) {
    throw "Failed to clean '$distDir'. Close processes using that folder and retry."
  }
}

python -m nuitka @nuitkaArgs

$builtCandidates = @(
  (Join-Path $RepoRoot "dist\\launcher.dist\\CyberDeck.exe"),
  (Join-Path $RepoRoot "dist\\CyberDeck.exe")
)
$builtPath = $builtCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

Write-Host ""
if ($builtPath) {
  Write-Host ("Built: {0}" -f $builtPath)
} else {
  Write-Host "Build finished, but output executable path was not detected."
}
