# install.ps1 — Install ai-memory Hermes plugin on Windows
param(
    [string]$ServerUrl = "http://127.0.0.1:49374"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin installer"

Write-Host "==> ai-memory Hermes plugin installer" -ForegroundColor Cyan
Write-Host ""

# Locate the script directory
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptPath
$PluginSrc = Join-Path $ProjectDir "plugins\memory\ai-memory"

if (-not (Test-Path (Join-Path $PluginSrc "__init__.py"))) {
    Write-Host "ERROR: plugin source not found at $PluginSrc" -ForegroundColor Red
    Write-Host "Run this script from the project root or the scripts/ directory."
    exit 1
}

# Resolve HERMES_HOME
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"

Write-Host "  Source:      $PluginSrc"
Write-Host "  Target:      $PluginDir"
Write-Host "  Server URL:  $ServerUrl"

# Create target directory
$null = New-Item -ItemType Directory -Force -Path (Join-Path $HermesHome "plugins")

# Create junction (NTFS symlink) or copy
if ((Get-Command New-Item -ErrorAction SilentlyContinue) -and (Get-PSDrive -PSProvider FileSystem).Count -gt 0) {
    if (Test-Path $PluginDir) {
        Remove-Item -Recurse -Force $PluginDir
    }
    New-Item -ItemType Junction -Path $PluginDir -Target $PluginSrc | Out-Null
    Write-Host "  Install:     junction"
}
else {
    Copy-Item -Recurse -Force $PluginSrc $PluginDir
    Write-Host "  Install:     copy"
}

# Write initial config if none exists
$ConfigFile = Join-Path $HermesHome "ai-memory.json"
if (-not (Test-Path $ConfigFile)) {
    $Config = @{
        server_url = $ServerUrl
        workspace  = "hermes"
        project    = "hermes-default"
    }
    $Config | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "  Config:      $ConfigFile (created)"
}
else {
    Write-Host "  Config:      $ConfigFile (exists, untouched)"
}

Write-Host ""
Write-Host "==> Done. Run these commands to enable:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    hermes plugins enable ai-memory"
Write-Host "    hermes memory setup"
Write-Host "    hermes memory status"
