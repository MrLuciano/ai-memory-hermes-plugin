# update.ps1 — Update the ai-memory Hermes plugin on Windows
#
# Defaults to downloading the latest plugin from GitHub. Set $env:UPDATE_FROM_LOCAL=true
# to update from a cloned repository instead (preserves the junction install).
#
# Options:
#   -DryRun         Show what would be done without making changes
#   -Yes            Skip confirmation prompts
#   -FromLocal      Update from local repo instead of GitHub
param(
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$FromLocal
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin updater"

# --- Flag resolution ---
$Script:DoDryRun = $DryRun -or ($env:DRY_RUN -eq "true")
$Script:DoYes = $Yes -or ($env:FORCE -eq "true")
$UpdateFromLocal = if ($env:UPDATE_FROM_LOCAL) { $env:UPDATE_FROM_LOCAL } else { $FromLocal.ToString().ToLower() }

$RepoTarballUrl = if ($env:REPO_TARBALL_URL) { $env:REPO_TARBALL_URL } else { "https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.zip" }

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
    Write-Host "  Proceeding with update..."
    return $true
}

# --- Pre-flight checks ---
function Invoke-Preflight {
    Write-Host ""
    Write-Host "==> Pre-flight checks" -ForegroundColor Cyan
    Write-Host ""

    # 1. Plugin state
    if (-not (Test-Path $PluginDir)) {
        Write-Err "Plugin not installed at $PluginDir"
        Write-Err "Run scripts\install.ps1 first."
        exit 1
    }

    if ((Test-Path $PluginDir) -and -not (Test-Path (Join-Path $PluginDir "__init__.py"))) {
        Write-Warn "$PluginDir exists but is empty; continuing update."
    }

    $targetInfo = Get-Item $PluginDir -ErrorAction SilentlyContinue
    $isJunction = $targetInfo -and ($targetInfo.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    if ($isJunction) {
        Write-Info "Install method: junction -> $($targetInfo.Target)"
    }
    else {
        $fileCount = (Get-ChildItem -Path $PluginDir -File -Recurse).Count
        Write-Info "Install method: copy ($fileCount files)"
    }

    # 2. Wrong path
    if (Test-Path $WrongPluginDir) {
        Write-Warn "Found $WrongPluginDir"
        Write-Info "User-installed plugins belong in $PluginDir"
    }

    # 3. Config file
    if (Test-Path $ConfigFile) {
        Write-Info "Config:        $ConfigFile (will be preserved)"
    }
    else {
        Write-Info "Config:        not found (will be created)"
    }

    # 4. Backup directory
    if (Test-Path $BackupRoot) {
        $backupCount = (Get-ChildItem -Path $BackupRoot -Directory -Filter "ai-memory.bak.*").Count
        Write-Info "Existing backups: $backupCount in $BackupRoot"
    }

    # 5. Source
    if ($UpdateFromLocal -eq "true") {
        $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
        $projectDir = Split-Path -Parent $scriptPath
        $localSrc = Join-Path $projectDir "plugins\memory\ai-memory"
        if (-not (Test-Path (Join-Path $localSrc "__init__.py"))) {
            Write-Err "Local plugin source not found at $localSrc"
            exit 1
        }
        Write-Info "Source:        $localSrc (local repo)"
    }
    else {
        Write-Info "Source:        $RepoTarballUrl (GitHub)"
    }

    # 6. Hermes CLI
    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if ($hermes) {
        Write-Ok "Hermes CLI found"
    }
    else {
        Write-Warn "Hermes CLI not found — cannot enable plugin automatically."
    }

    # 7. Hermes process
    $hermesProc = Get-Process -Name "hermes*" -ErrorAction SilentlyContinue
    if ($hermesProc) {
        Write-Warn "Hermes process appears to be running."
        Write-Info "You will need to restart Hermes after update."
    }

    # 8. ai-memory server
    Write-Info "Checking ai-memory server at $env:AI_MEMORY_SERVER_URL ..."
    try {
        $response = Invoke-WebRequest -Uri "$env:AI_MEMORY_SERVER_URL/admin/status" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        Write-Ok "ai-memory server is reachable"
    }
    catch {
        Write-Warn "ai-memory server at $env:AI_MEMORY_SERVER_URL is not reachable."
        Write-Info "The update will proceed but the server should be running after restart."
    }

    Write-Host ""
    Write-Host "  All pre-flight checks complete." -ForegroundColor Cyan
}

# --- Main ---
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"
$ConfigFile = Join-Path $HermesHome "ai-memory.json"
$BackupRoot = Join-Path $HermesHome ".ai-memory-backups"
$WrongPluginDir = Join-Path $HermesHome "plugins\memory\ai-memory"

# Set server URL for preflight check
if (-not $env:AI_MEMORY_SERVER_URL) { $env:AI_MEMORY_SERVER_URL = "http://127.0.0.1:49374" }

Write-Host "==> ai-memory Hermes plugin updater" -ForegroundColor Cyan
Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "  *** DRY RUN MODE — no changes will be made ***" -ForegroundColor Yellow
}

# Run pre-flight
Invoke-Preflight

# Source label for display
$sourceLabel = if ($UpdateFromLocal -eq "true") { "local repo" } else { "GitHub ($RepoTarballUrl)" }

# Show planned actions
Write-Host ""
Write-Host "==> Planned actions" -ForegroundColor Cyan
Write-Host ""
Write-Info "1. Backup current install -> $BackupRoot\ai-memory.bak.<timestamp>"
Write-Info "2. Remove current plugin files from $PluginDir"
Write-Info "3. Copy updated files from $sourceLabel -> $PluginDir"
if (Test-Path $ConfigFile) {
    Write-Info "4. Preserve config: $ConfigFile"
}
else {
    Write-Info "4. Create config: $ConfigFile"
}
Write-Info "5. Enable plugin in Hermes (best-effort, if CLI available)"
Write-Info "6. Verify __init__.py exists after update"

# Confirmation
$confirmMsg = @"
This will update the ai-memory plugin:
  From:  $sourceLabel
  To:    $PluginDir

A backup of the current install will be saved to:
$BackupRoot\ai-memory.bak.<timestamp>

Config ($ConfigFile) will be preserved.
"@
if (-not (Confirm-Action $confirmMsg)) { exit 0 }

# --- Update ---
Write-Host ""
Write-Host "==> Updating" -ForegroundColor Cyan

# Detect current install method
$currentMethod = "copy"
$targetInfo = Get-Item $PluginDir -ErrorAction SilentlyContinue
if ($targetInfo -and ($targetInfo.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    $currentMethod = "junction"
}

# Resolve source
$pluginSrc = ""
$downloadDir = $null
if ($UpdateFromLocal -eq "true") {
    $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectDir = Split-Path -Parent $scriptPath
    $pluginSrc = Join-Path $projectDir "plugins\memory\ai-memory"
    if (-not (Test-Path (Join-Path $pluginSrc "__init__.py"))) {
        Write-Err "local plugin source not found at $pluginSrc"
        exit 1
    }
    Write-Info "Source:      $pluginSrc (local repo)"
}
else {
    $downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    Write-Info "Downloading from $RepoTarballUrl ..."
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] Would download from $RepoTarballUrl"
        $pluginSrc = Join-Path $downloadDir "ai-memory-hermes-plugin-main\plugins\memory\ai-memory"
    }
    else {
        $null = New-Item -ItemType Directory -Force -Path $downloadDir
        $tarball = Join-Path $downloadDir "repo.zip"
        Invoke-WebRequest -Uri $RepoTarballUrl -OutFile $tarball -UseBasicParsing

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($tarball, $downloadDir)

        $pluginSrc = Join-Path $downloadDir "ai-memory-hermes-plugin-main\plugins\memory\ai-memory"
        if (-not (Test-Path (Join-Path $pluginSrc "__init__.py"))) {
            Write-Err "downloaded plugin source not found at $pluginSrc"
            Remove-Item -Recurse -Force $downloadDir -ErrorAction SilentlyContinue
            exit 1
        }
    }
}

Write-Info "Target:      $PluginDir"
Write-Info "Method:      $currentMethod"

# Backup current install
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$backupDir = Join-Path $BackupRoot "ai-memory.bak.$timestamp"
Invoke-OrDryRun -Description "Backup $PluginDir -> $backupDir" -Action {
    $null = New-Item -ItemType Directory -Force -Path $BackupRoot
    Copy-Item -Recurse -Force $PluginDir $backupDir
}
Write-Info "Backup:      $backupDir"

# Remove old install
if ($currentMethod -eq "junction") {
    Invoke-OrDryRun -Description "Remove junction $PluginDir" -Action {
        (Get-Item $PluginDir).Delete()
    }
}
else {
    Invoke-OrDryRun -Description "Remove directory $PluginDir" -Action {
        Remove-Item -Recurse -Force $PluginDir
    }
}

# Install updated files
if ($UpdateFromLocal -eq "true" -and $currentMethod -eq "junction") {
    Invoke-OrDryRun -Description "Create junction $PluginDir -> $pluginSrc" -Action {
        New-Item -ItemType Junction -Path $PluginDir -Target $pluginSrc | Out-Null
    }
    Write-Info "Updated:     junction (from local repo)"
}
else {
    Invoke-OrDryRun -Description "Copy updated files to $PluginDir" -Action {
        Copy-Item -Recurse -Force $pluginSrc $PluginDir
    }
    $sourceLabel2 = if ($UpdateFromLocal -eq "true") { "local repo" } else { "downloaded source" }
    Write-Info "Updated:     copy (from $sourceLabel2)"
}

# Preserve config
if (-not $Script:DoDryRun) {
    $backupConfig = Join-Path $backupDir "ai-memory.json"
    if ((Test-Path $backupConfig) -and (-not (Test-Path $ConfigFile))) {
        Copy-Item -Force $backupConfig $ConfigFile
        Write-Info "Config:      restored from backup"
    }
    elseif (Test-Path $ConfigFile) {
        Write-Info "Config:      $ConfigFile (preserved)"
    }
    else {
        $defaultConfig = @{
            server_url = "http://127.0.0.1:49374"
            workspace  = "hermes"
            project    = "hermes-default"
        }
        $defaultConfig | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
        Write-Info "Config:      $ConfigFile (created)"
    }
}
else {
    Write-Info "[DRY RUN] Config would be preserved or created"
}

# Cleanup temp download
if ($downloadDir) {
    Invoke-OrDryRun -Description "Remove temporary download" -Action {
        Remove-Item -Recurse -Force $downloadDir -ErrorAction SilentlyContinue
    }
    Write-Info "Cleanup:     removed temporary download"
}

# List backups
Write-Host ""
Write-Host "  Backups:"
if (Test-Path $BackupRoot) {
    Get-ChildItem -Path $BackupRoot -Directory -Filter "ai-memory.bak.*" | Sort-Object Name | ForEach-Object {
        Write-Info "  - $($_.FullName)"
    }
}

# Best-effort enable
$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($hermes) {
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] Would run: hermes plugins enable ai-memory"
    }
    else {
        try {
            $null = & hermes plugins enable ai-memory
            Write-Info "Hermes:      plugin enabled"
        }
        catch {
            Write-Info "Hermes:      plugin already enabled or could not enable"
        }
    }
}
else {
    Write-Info "Hermes:      CLI not found; skipping enable"
}

# Verify update
if (-not $Script:DoDryRun -and -not (Test-Path (Join-Path $PluginDir "__init__.py"))) {
    Write-Host ""
    Write-Err "update verification failed — $PluginDir\__init__.py is missing."
    Write-Info "             Restore from backup: $backupDir"
    exit 1
}

Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "==> Dry run complete. No changes were made." -ForegroundColor Cyan
    Write-Host "    Re-run without -DryRun to apply."
}
else {
    Write-Host "==> Done. Restart Hermes for the update to take effect." -ForegroundColor Cyan
}
