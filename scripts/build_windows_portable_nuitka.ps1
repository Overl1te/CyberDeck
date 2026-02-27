param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$IconIco = Join-Path $RepoRoot "icon.ico"
$RequirementsBuild = Join-Path $RepoRoot "requirements-build.txt"
$LauncherI18nJson = Join-Path $RepoRoot "cyberdeck\launcher\i18n.json"
$PortableDistDir = Join-Path $RepoRoot "dist-portable"
$PortableOutDir = Join-Path $RepoRoot "Output"
$PortableExeName = "CyberDeck.exe"
$PortableOutExe = Join-Path $PortableOutDir $PortableExeName
$PortableCoreFiles = @(
  "icon.png",
  "icon.ico",
  "icon-qr-code.png",
  "logo.gif"
)

function Stop-ProcessesFromPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RootPath
  )

  $root = ([System.IO.Path]::GetFullPath($RootPath)).TrimEnd('\') + '\'
  $killed = 0

  try {
    $procList = Get-CimInstance Win32_Process
    foreach ($proc in $procList) {
      $exePath = [string]$proc.ExecutablePath
      if (-not $exePath) {
        continue
      }
      if ($exePath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        $killed++
      }
    }
  } catch {
    Get-Process -Name "CyberDeck","CyberDeckPortable" -ErrorAction SilentlyContinue |
      Stop-Process -Force -ErrorAction SilentlyContinue
  }

  if ($killed -gt 0) {
    Write-Host ("Stopped {0} running process(es) from {1}" -f $killed, $RootPath)
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
$timelineNames = @($timelineMedia | ForEach-Object { [System.IO.Path]::GetFileName($_) } | Sort-Object -Unique)
$portableExternalFiles = @($PortableCoreFiles + $timelineNames | Sort-Object -Unique)

$nuitkaArgs = @(
  "launcher.py"
  "--onefile"
  "--enable-plugin=tk-inter"
  "--include-data-dir=static=static"
  "--include-data-file=icon.png=icon.png"
  "--include-data-file=icon.ico=icon.ico"
  "--include-data-file=logo.gif=logo.gif"
  "--include-data-file=icon-qr-code.png=icon-qr-code.png"
  "--include-data-file=cyberdeck/launcher/i18n.json=cyberdeck/launcher/i18n.json"
  "--include-data-files-external=icon.png"
  "--include-data-files-external=icon.ico"
  "--include-data-files-external=icon-qr-code.png"
  "--include-data-files-external=logo.gif"
  "--windows-icon-from-ico=$IconIco"
  "--include-package=customtkinter"
  "--include-package-data=customtkinter"
  "--windows-console-mode=disable"
  "--windows-uac-admin"
  "--output-dir=$PortableDistDir"
  "--output-filename=$PortableExeName"
)
foreach ($mediaPath in $timelineMedia) {
  $mediaName = [System.IO.Path]::GetFileName($mediaPath)
  $nuitkaArgs += "--include-data-file=$mediaPath=$mediaName"
  $nuitkaArgs += "--include-data-files-external=$mediaName"
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

if (Test-Path $PortableDistDir) {
  Stop-ProcessesFromPath -RootPath $PortableDistDir
  $cleanOk = Remove-PathWithRetries -Path $PortableDistDir
  if (-not $cleanOk) {
    throw "Failed to clean '$PortableDistDir'. Close processes using that folder and retry."
  }
}

if (Test-Path $PortableOutDir) {
  Stop-ProcessesFromPath -RootPath $PortableOutDir
  foreach ($name in @($portableExternalFiles + $PortableExeName | Sort-Object -Unique)) {
    $path = Join-Path $PortableOutDir $name
    if (Test-Path $path) {
      Remove-Item -Force $path -ErrorAction SilentlyContinue
    }
  }
}

python -m nuitka @nuitkaArgs

$builtPath = Join-Path $PortableDistDir $PortableExeName
if (-not (Test-Path $builtPath)) {
  throw "Build finished, but output executable path was not detected: $builtPath"
}

if (-not (Test-Path $PortableOutDir)) {
  New-Item -ItemType Directory -Path $PortableOutDir | Out-Null
}

Copy-Item $builtPath -Destination $PortableOutExe -Force

foreach ($name in $portableExternalFiles) {
  $src = Join-Path $PortableDistDir $name
  if (Test-Path $src) {
    Copy-Item $src -Destination (Join-Path $PortableOutDir $name) -Force
  }
}

Write-Host ""
Write-Host ("Portable onefile exe: {0}" -f $PortableOutExe)
