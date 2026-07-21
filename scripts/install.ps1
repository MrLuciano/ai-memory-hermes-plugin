# install.ps1 — Install ai-memory Hermes plugin on Windows
#
# Works when run:
#   • locally from a cloned repo (scripts\install.ps1)
#   • via the iex one-liner: iex ((Invoke-WebRequest -Uri '.../install.ps1').Content)
#
# Options:
#   -DryRun     Show what would be done without making changes
#   -Yes        Skip confirmation prompts
#
# Env vars:
#   FORCE=true            Skip confirmation prompts (same as -Yes)
#   HERMES_HOME           Hermes profile directory (default: %USERPROFILE%\.hermes)
#   AI_MEMORY_SERVER_URL  Server URL for config (default: http://127.0.0.1:49374)
#   REPO_TARBALL_URL      Override GitHub zip URL
param(
    [string]$ServerUrl = "http://127.0.0.1:49374",
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin installer"

# --- Flag resolution ---
$Script:DoDryRun = $DryRun -or ($env:DRY_RUN -eq "true")
$Script:DoYes = $Yes -or ($env:FORCE -eq "true")

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
    Write-Host "  Proceeding with install..."
    return $true
}

# --- Pre-flight checks ---
function Invoke-Preflight {
    Write-Host ""
    Write-Host "==> Pre-flight checks" -ForegroundColor Cyan
    Write-Host ""

    # 1. HERMES_HOME
    Write-Info "HERMES_HOME:  $HermesHome"
    if (-not (Test-Path $HermesHome)) {
        Write-Warn "$HermesHome does not exist — will be created."
    }

    # 2. Write permissions
    $checkDir = if (Test-Path (Join-Path $HermesHome "plugins")) {
        Join-Path $HermesHome "plugins"
    } else {
        $HermesHome
    }
    try {
        $testFile = Join-Path $checkDir ".ai-memory-write-test"
        New-Item -ItemType File -Path $testFile -Force | Out-Null
        Remove-Item -Force $testFile
        Write-Ok "Write permissions to $checkDir"
    }
    catch {
        Write-Warn "No write permissions to $checkDir — install may fail."
    }

    # 3. Existing plugin
    if (Test-Path (Join-Path $PluginDir "__init__.py")) {
        Write-Warn "Plugin already installed at $PluginDir"
        Write-Info "This will overwrite all plugin files."
        Write-Info "Config ($ConfigFile) will NOT be touched."
    }
    else {
        Write-Ok "No existing plugin at $PluginDir (fresh install)"
    }

    # 4. Hermes CLI
    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if ($hermes) {
        Write-Ok "Hermes CLI found: $($hermes.Source)"
    }
    else {
        Write-Warn "Hermes CLI not found — you will need to enable the plugin manually."
    }

    # 5. Hermes process
    $hermesProc = Get-Process -Name "hermes*" -ErrorAction SilentlyContinue
    if ($hermesProc) {
        Write-Warn "Hermes process appears to be running."
        Write-Info "You will need to restart Hermes after install."
    }

    # 6. ai-memory server
    Write-Info "Checking ai-memory server at $ServerUrl ..."
    try {
        $response = Invoke-WebRequest -Uri "$ServerUrl/admin/status" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        Write-Ok "ai-memory server is reachable"
    }
    catch {
        Write-Warn "ai-memory server at $ServerUrl is not reachable."
        Write-Info "The plugin will install but will not function until the server is running."
    }

    Write-Host ""
    Write-Host "  All pre-flight checks complete." -ForegroundColor Cyan
}

# --- Main ---
Write-Host "==> ai-memory Hermes plugin installer" -ForegroundColor Cyan
Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "  *** DRY RUN MODE — no changes will be made ***" -ForegroundColor Yellow
}

# Locate the script directory
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptPath
$PluginSrc = Join-Path $ProjectDir "plugins\memory\ai-memory"
$DownloadDir = $null

# If the local repo isn't present (e.g. iex one-liner), download from GitHub.
if (-not (Test-Path (Join-Path $PluginSrc "__init__.py"))) {
    $DownloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    Write-Info "Downloading plugin from $RepoTarballUrl ..."
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] Would download from $RepoTarballUrl"
    }
    else {
        $null = New-Item -ItemType Directory -Force -Path $DownloadDir
        $Tarball = Join-Path $DownloadDir "repo.zip"
        Invoke-WebRequest -Uri $RepoTarballUrl -OutFile $Tarball -UseBasicParsing

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($Tarball, $DownloadDir)
    }
    $PluginSrc = Join-Path $DownloadDir "ai-memory-hermes-plugin-main\plugins\memory\ai-memory"

    if (-not (Test-Path (Join-Path $PluginSrc "__init__.py"))) {
        Write-Err "downloaded plugin source not found at $PluginSrc"
        if ($DownloadDir) { Remove-Item -Recurse -Force $DownloadDir -ErrorAction SilentlyContinue }
        exit 1
    }
}

# Resolve HERMES_HOME
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"
$ConfigFile = Join-Path $HermesHome "ai-memory.json"

Write-Host "  Source:      $PluginSrc"
Write-Host "  Target:      $PluginDir"
Write-Host "  Server URL:  $ServerUrl"

# Run pre-flight
Invoke-Preflight

# Show planned actions
Write-Host ""
Write-Host "==> Planned actions" -ForegroundColor Cyan
Write-Host ""
Write-Info "1. Create $HermesHome\plugins\ (if needed)"
if ($DownloadDir) {
    Write-Info "2. Copy plugin files from downloaded source -> $PluginDir"
}
else {
    Write-Info "2. Create junction: $PluginSrc -> $PluginDir"
}
if (-not (Test-Path $ConfigFile)) {
    Write-Info "3. Create config: $ConfigFile"
}
else {
    Write-Info "3. Config: $ConfigFile (already exists, untouched)"
}

# Confirmation
$confirmMsg = @"
This will install the ai-memory plugin to:
  $PluginDir

Config file ($ConfigFile) will not be modified if it already exists.
"@
if (-not (Confirm-Action $confirmMsg)) { exit 0 }

# --- Install ---
Write-Host ""
Write-Host "==> Installing" -ForegroundColor Cyan

# Create target directory
Invoke-OrDryRun -Description "Create $HermesHome\plugins\" -Action {
    $null = New-Item -ItemType Directory -Force -Path (Join-Path $HermesHome "plugins")
}

# Create junction (NTFS symlink) or copy
if ($DownloadDir) {
    # Downloaded source lives in a temp dir; copy it so the plugin survives cleanup.
    Invoke-OrDryRun -Description "Remove and copy plugin to $PluginDir" -Action {
        if (Test-Path $PluginDir) { Remove-Item -Recurse -Force $PluginDir }
        Copy-Item -Recurse -Force $PluginSrc $PluginDir
    }
    Write-Info "Install:     copy (from downloaded source)"
}
elseif ((Get-Command New-Item -ErrorAction SilentlyContinue) -and (Get-PSDrive -PSProvider FileSystem).Count -gt 0) {
    Invoke-OrDryRun -Description "Create junction $PluginDir -> $PluginSrc" -Action {
        if (Test-Path $PluginDir) { Remove-Item -Recurse -Force $PluginDir }
        New-Item -ItemType Junction -Path $PluginDir -Target $PluginSrc | Out-Null
    }
    Write-Info "Install:     junction"
}
else {
    Invoke-OrDryRun -Description "Copy plugin to $PluginDir" -Action {
        Copy-Item -Recurse -Force $PluginSrc $PluginDir
    }
    Write-Info "Install:     copy"
}

# Write initial config if none exists
if (-not (Test-Path $ConfigFile)) {
    if ($Script:DoDryRun) {
        Write-Info "[DRY RUN] Would create $ConfigFile with server_url=$ServerUrl"
    }
    else {
        $Config = @{
            server_url = $ServerUrl
            workspace  = "hermes"
            project    = "hermes-default"
        }
        $Config | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    }
    Write-Info "Config:      $ConfigFile (created)"
}
else {
    Write-Info "Config:      $ConfigFile (exists, untouched)"
}

# Cleanup temp download if used
if ($DownloadDir) {
    Invoke-OrDryRun -Description "Remove temporary download" -Action {
        Remove-Item -Recurse -Force $DownloadDir -ErrorAction SilentlyContinue
    }
    Write-Info "Cleanup:     removed temporary download"
}

# Verify install
if (-not $Script:DoDryRun -and -not (Test-Path (Join-Path $PluginDir "__init__.py"))) {
    Write-Host ""
    Write-Err "install verification failed — $PluginDir\__init__.py is missing."
    exit 1
}

Write-Host ""
if ($Script:DoDryRun) {
    Write-Host "==> Dry run complete. No changes were made." -ForegroundColor Cyan
    Write-Host "    Re-run without -DryRun to apply."
}
else {
    Write-Host "==> Done. Run these commands to enable:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    hermes plugins enable ai-memory"
    Write-Host "    hermes memory setup"
    Write-Host "    hermes memory status"
}
