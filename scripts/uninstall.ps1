# uninstall.ps1 — Remove the ai-memory Hermes plugin on Windows
#
# Removes the plugin from $HERMES_HOME\plugins\ai-memory. The ai-memory.json
# config file is kept unless -RemoveConfig is passed.
param(
    [switch]$RemoveConfig
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin uninstaller"

$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"
$ConfigFile = Join-Path $HermesHome "ai-memory.json"

Write-Host "==> ai-memory Hermes plugin uninstaller" -ForegroundColor Cyan
Write-Host ""

# Remove plugin directory, junction, or symlink
if (Test-Path $PluginDir) {
    Remove-Item -Recurse -Force $PluginDir
    Write-Host "  Removed: $PluginDir"
}
else {
    Write-Host "  Plugin not found at $PluginDir"
}

# Optionally disable in Hermes (best effort)
$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($hermes) {
    try {
        $null = & hermes plugins disable ai-memory
        Write-Host "  Disabled plugin in Hermes"
    }
    catch {
        Write-Host "  Could not disable plugin in Hermes (it may already be disabled)"
    }
}
else {
    Write-Host "  Hermes CLI not found; skipping disable"
}

# Remove config only when explicitly requested
if ($RemoveConfig -and (Test-Path $ConfigFile)) {
    Remove-Item -Force $ConfigFile
    Write-Host "  Removed config: $ConfigFile"
}
elseif (Test-Path $ConfigFile) {
    Write-Host "  Config kept: $ConfigFile (pass -RemoveConfig to remove)"
}

Write-Host ""
Write-Host "==> Done." -ForegroundColor Cyan
