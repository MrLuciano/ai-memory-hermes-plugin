# uninstall.ps1 — Remove the ai-memory Hermes plugin on Windows
#
# Removes the plugin from $HERMES_HOME\plugins\ai-memory. The ai-memory.json
# config file is kept unless -RemoveConfig is passed.
#
# Options:
#   -DryRun         Show what would be done without making changes
#   -Yes            Skip confirmation prompts
#   -RemoveConfig   Also remove the ai-memory.json config file
param(
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$RemoveConfig
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin uninstaller"

# --- Flag resolution ---
$Script:DoDryRun = $DryRun -or ($env:DRY_RUN -eq "true")
$Script:DoYes = $Yes -or ($env:FORCE -eq "true")
$DoRemoveConfig = $RemoveConfig -or ($env:REMOVE_CONFIG -eq "true")

# --- Helper functions ---
function Write-Info  { param([string]$Msg) Write-Host "  $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "  OK: $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "  WARNING: $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) { Write-Host "ERROR: $Msg" -ForegroundColor Red } }

function Invoke-OrDryRun {
    param([scriptblock]$Action, [string]$Description)
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] $Description"
    }
    else {
        & $Action
    }
}

function Confirm-Action {
    param([string]$Message)
    if ($Script:DoDryRun) { return $true }
    if ($Script:DoYes) { return $true }
    if (-not [Console]::IsInputRedirected) {
        Write-Host ""
        Write-Host $Message
        $answer = Read-Host "  Proceed? [y/N]"
        if ($answer -match '^[yY]') { return $true }
        Write-Info "Aborted."
        exit 0
    }
    Write-Host ""
    Write-Host "  NOTE: non-interactive mode detected (piped input)."
    Write-Host "  To skip this prompt, pass -Yes or set FORCE=true."
    Write-Host "  Proceeding with uninstall..."
    return $true
}

# --- Pre-flight checks ---
function Invoke-Preflight {
    Write-Host ""
    Write-Host "==> Pre-flight checks" -ForegroundColor Cyan
    Write-Host ""

    # 1. Plugin state
    if (Test-Path $PluginDir) {
        $item = Get-Item $PluginDir -ErrorAction SilentlyContinue
        $isJunction = $item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        if ($isJunction) {
            Write-Info "Plugin:       $PluginDir (junction -> $($item.Target))"
        }
        else {
            $fileCount = (Get-ChildItem -Path $PluginDir -File -Recurse).Count
            Write-Info "Plugin:       $PluginDir ($fileCount files)"
        }
    }
    else {
        Write-Info "Plugin:       not found at $PluginDir"
        return
    }

    # 2. Config file
    if (Test-Path $ConfigFile) {
        if ($DoRemoveConfig) {
            Write-Info "Config:       $ConfigFile (will be removed)"
        }
        else {
            Write-Info "Config:       $ConfigFile (will be kept)"
        }
    }
    else {
        Write-Info "Config:       not found"
    }

    # 3. Hermes CLI
    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if ($hermes) {
        Write-Ok "Hermes CLI found"
    }
    else {
        Write-Warn "Hermes CLI not found — cannot disable plugin automatically."
    }

    # 4. Hermes process
    $hermesProc = Get-Process -Name "hermes*" -ErrorAction SilentlyContinue
    if ($hermesProc) {
        Write-Warn "Hermes process appears to be running."
        Write-Info "You will need to restart Hermes after uninstall."
    }

    # 5. ai-memory server
    $serverUrl = "http://127.0.0.1:49374"
    if (Test-Path $ConfigFile) {
        try {
            $cfg = Get-Content $ConfigFile -Raw | ConvertFrom-Json
            if ($cfg.server_url) { $serverUrl = $cfg.server_url }
        }
        catch { }
    }
    Write-Info "Checking ai-memory server at $serverUrl ..."
    try {
        $response = Invoke-WebRequest -Uri "$serverUrl/admin/status" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        Write-Ok "ai-memory server is reachable — will become unavailable after uninstall"
    }
    catch {
        Write-Info "ai-memory server is not reachable (may already be stopped)"
    }

    Write-Host ""
    Write-Host "  Checks complete." -ForegroundColor Cyan
}

# --- Main ---
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"
$ConfigFile = Join-Path $HermesHome "ai-memory.json"

Write-Host "==> ai-memory Hermes plugin uninstaller" -ForegroundColor Cyan
Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "  *** DRY RUN MODE — no changes will be made ***" -ForegroundColor Yellow
}

# Run pre-flight
Invoke-Preflight

# Show planned actions
Write-Host ""
Write-Host "==> Planned actions" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $PluginDir) {
    $item = Get-Item $PluginDir -ErrorAction SilentlyContinue
    $isJunction = $item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    if ($isJunction) {
        Write-Info "1. Remove junction: $PluginDir"
    }
    else {
        Write-Info "1. Remove directory: $PluginDir"
    }
}
else {
    Write-Info "1. (nothing to remove — plugin not found)"
}

$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($hermes) {
    Write-Info "2. Disable plugin in Hermes (best-effort)"
}
else {
    Write-Info "2. (Hermes CLI not found — skip disable)"
}

if ($DoRemoveConfig -and (Test-Path $ConfigFile)) {
    Write-Info "3. Remove config: $ConfigFile"
}
elseif (Test-Path $ConfigFile) {
    Write-Info "3. Config kept: $ConfigFile"
}
else {
    Write-Info "3. (no config to remove)"
}

# Confirmation
$confirmMsg = @"
This will remove the ai-memory plugin:
  Plugin:   $PluginDir
  Config:   $ConfigFile $(if ($DoRemoveConfig) { "(will be removed)" } else { "(kept)" })

The plugin will be disabled in Hermes if the CLI is available.
"@
if (-not (Confirm-Action $confirmMsg)) { exit 0 }

# --- Uninstall ---
Write-Host ""
Write-Host "==> Uninstalling" -ForegroundColor Cyan

# Remove plugin directory, junction, or symlink
if (Test-Path $PluginDir) {
    Invoke-OrDryRun -Description "Remove $PluginDir" -Action {
        Remove-Item -Recurse -Force $PluginDir
    }
    Write-Info "Removed: $PluginDir"
}
else {
    Write-Info "Plugin not found at $PluginDir"
}

# Optionally disable in Hermes (best effort)
$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($hermes) {
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] Would run: hermes plugins disable ai-memory"
    }
    else {
        try {
            $null = & hermes plugins disable ai-memory
            Write-Info "Disabled plugin in Hermes"
        }
        catch {
            Write-Info "Could not disable plugin in Hermes (it may already be disabled)"
        }
    }
}
else {
    Write-Info "Hermes CLI not found; skipping disable"
}

# Remove config only when explicitly requested
if ($DoRemoveConfig -and (Test-Path $ConfigFile)) {
    Invoke-OrDryRun -Description "Remove $ConfigFile" -Action {
        Remove-Item -Force $ConfigFile
    }
    Write-Info "Removed config: $ConfigFile"
}
elseif (Test-Path $ConfigFile) {
    Write-Info "Config kept: $ConfigFile (pass -RemoveConfig to remove)"
}

Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "==> Dry run complete. No changes were made." -ForegroundColor Cyan
    Write-Host "    Re-run without -DryRun to apply."
}
else {
    Write-Host "==> Done." -ForegroundColor Cyan
}
