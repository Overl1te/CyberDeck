param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VendorDir = Join-Path $RepoRoot "vendor\cloudflared\windows-amd64"
$VendorExe = Join-Path $VendorDir "cloudflared.exe"
$DownloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

if ((Test-Path $VendorExe) -and (-not $Force)) {
  Write-Host ("Bundled cloudflared already present: {0}" -f $VendorExe)
  exit 0
}

New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null

$tempRoot = Join-Path $env:TEMP ("cyberdeck-cloudflared-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
  $tempExe = Join-Path $tempRoot "cloudflared.exe"
  Write-Host ("Downloading cloudflared from {0}" -f $DownloadUrl)
  Invoke-WebRequest -Uri $DownloadUrl -OutFile $tempExe -TimeoutSec 30

  if (-not (Test-Path $tempExe)) {
    throw "Download did not produce cloudflared.exe"
  }

  Copy-Item $tempExe -Destination $VendorExe -Force
  Write-Host ("Bundled cloudflared saved to {0}" -f $VendorExe)
} finally {
  if (Test-Path $tempRoot) {
    Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
