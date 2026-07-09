# update.ps1 — Update the ai-memory Hermes plugin on Windows
#
# Defaults to downloading the latest plugin from GitHub. Set $env:UPDATE_FROM_LOCAL=true
# to update from a cloned repository instead (preserves the junction install).
param(
    [switch]$FromLocal
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin updater"

$RepoTarballUrl = if ($env:REPO_TARBALL_URL) { $env:REPO_TARBALL_URL } else { "https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.zip" }
$UpdateFromLocal = if ($env:UPDATE_FROM_LOCAL) { $env:UPDATE_FROM_LOCAL } else { $FromLocal.ToString().ToLower() }

$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$PluginDir = Join-Path $HermesHome "plugins\ai-memory"
$ConfigFile = Join-Path $HermesHome "ai-memory.json"
$BackupRoot = Join-Path $HermesHome ".ai-memory-backups"

Write-Host "==> ai-memory Hermes plugin updater" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PluginDir)) {
    Write-Host "ERROR: plugin not installed at $PluginDir" -ForegroundColor Red
    Write-Host "Run scripts\install.ps1 first."
    exit 1
}

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
        Write-Host "ERROR: local plugin source not found at $pluginSrc" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Source:      $pluginSrc (local repo)"
}
else {
    $downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    $null = New-Item -ItemType Directory -Force -Path $downloadDir
    $tarball = Join-Path $downloadDir "repo.zip"

    Write-Host "  Source:      $RepoTarballUrl (downloading...)" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RepoTarballUrl -OutFile $tarball -UseBasicParsing

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($tarball, $downloadDir)

    $pluginSrc = Join-Path $downloadDir "ai-memory-hermes-plugin-main\plugins\memory\ai-memory"
    if (-not (Test-Path (Join-Path $pluginSrc "__init__.py"))) {
        Write-Host "ERROR: downloaded plugin source not found at $pluginSrc" -ForegroundColor Red
        Remove-Item -Recurse -Force $downloadDir -ErrorAction SilentlyContinue
        exit 1
    }
}

Write-Host "  Target:      $PluginDir"
Write-Host "  Method:      $currentMethod"

# Backup current install (outside $HermesHome\plugins so Hermes does not discover it)
$null = New-Item -ItemType Directory -Force -Path $BackupRoot
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$backupDir = Join-Path $BackupRoot "ai-memory.bak.$timestamp"
Copy-Item -Recurse -Force $PluginDir $backupDir
Write-Host "  Backup:      $backupDir"

# Remove old install
if ($currentMethod -eq "junction") {
    (Get-Item $PluginDir).Delete()
}
else {
    Remove-Item -Recurse -Force $PluginDir
}

# Install updated files
if ($UpdateFromLocal -eq "true" -and $currentMethod -eq "junction") {
    New-Item -ItemType Junction -Path $PluginDir -Target $pluginSrc | Out-Null
    Write-Host "  Updated:     junction (from local repo)"
}
else {
    Copy-Item -Recurse -Force $pluginSrc $PluginDir
    $sourceLabel = if ($UpdateFromLocal -eq "true") { "local repo" } else { "downloaded source" }
    Write-Host "  Updated:     copy (from $sourceLabel)"
}

# Preserve config
$backupConfig = Join-Path $backupDir "ai-memory.json"
if ((Test-Path $backupConfig) -and (-not (Test-Path $ConfigFile))) {
    Copy-Item -Force $backupConfig $ConfigFile
    Write-Host "  Config:      restored from backup"
}
elseif (Test-Path $ConfigFile) {
    Write-Host "  Config:      $ConfigFile (preserved)"
}
else {
    $defaultConfig = @{
        server_url = "http://127.0.0.1:49374"
        workspace  = "hermes"
        project    = "hermes-default"
    }
    $defaultConfig | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "  Config:      $ConfigFile (created)"
}

# Cleanup temp download
if ($downloadDir) {
    Remove-Item -Recurse -Force $downloadDir -ErrorAction SilentlyContinue
    Write-Host "  Cleanup:     removed temporary download"
}

# List backups
Write-Host ""
Write-Host "  Backups:"
if (Test-Path $BackupRoot) {
    Get-ChildItem -Path $BackupRoot -Directory -Filter "ai-memory.bak.*" | Sort-Object Name | ForEach-Object {
        Write-Host "    - $($_.FullName)"
    }
}

# Best-effort enable
$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($hermes) {
    try {
        $null = & hermes plugins enable ai-memory
        Write-Host "  Hermes:      plugin enabled"
    }
    catch {
        Write-Host "  Hermes:      plugin already enabled or could not enable"
    }
}
else {
    Write-Host "  Hermes:      CLI not found; skipping enable"
}

Write-Host ""
Write-Host "==> Done. Restart Hermes for the update to take effect." -ForegroundColor Cyan
