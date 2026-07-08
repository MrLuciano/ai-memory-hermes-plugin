# install.ps1 — Install ai-memory Hermes plugin on Windows
#
# Works when run:
#   • locally from a cloned repo (scripts\install.ps1)
#   • via the iex one-liner: iex ((Invoke-WebRequest -Uri '.../install.ps1').Content)
#
# In the one-liner case the script runs in memory, so there is no local repo to
# junction. We fall back to downloading the plugin files from GitHub and copying
# them into $HERMES_HOME\plugins\ai-memory.
param(
    [string]$ServerUrl = "http://127.0.0.1:49374"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ai-memory Hermes plugin installer"

$RepoTarballUrl = if ($env:REPO_TARBALL_URL) { $env:REPO_TARBALL_URL } else { "https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.zip" }

Write-Host "==> ai-memory Hermes plugin installer" -ForegroundColor Cyan
Write-Host ""

# Locate the script directory
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptPath
$PluginSrc = Join-Path $ProjectDir "plugins\memory\ai-memory"
$DownloadDir = $null

# If the local repo isn't present (e.g. iex one-liner), download from GitHub.
if (-not (Test-Path (Join-Path $PluginSrc "__init__.py"))) {
    $DownloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    $null = New-Item -ItemType Directory -Force -Path $DownloadDir
    $Tarball = Join-Path $DownloadDir "repo.zip"

    Write-Host "  Source:      $RepoTarballUrl (downloading...)" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RepoTarballUrl -OutFile $Tarball -UseBasicParsing

    # Extract the zip using .NET (works on Windows PowerShell 5.1 and PowerShell 7+)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Tarball, $DownloadDir)

    $PluginSrc = Join-Path $DownloadDir "ai-memory-hermes-plugin-main\plugins\memory\ai-memory"

    if (-not (Test-Path (Join-Path $PluginSrc "__init__.py"))) {
        Write-Host "ERROR: downloaded plugin source not found at $PluginSrc" -ForegroundColor Red
        Remove-Item -Recurse -Force $DownloadDir -ErrorAction SilentlyContinue
        exit 1
    }
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
if ($DownloadDir) {
    # Downloaded source lives in a temp dir; copy it so the plugin survives cleanup.
    if (Test-Path $PluginDir) {
        Remove-Item -Recurse -Force $PluginDir
    }
    Copy-Item -Recurse -Force $PluginSrc $PluginDir
    Write-Host "  Install:     copy (from downloaded source)"
}
elseif ((Get-Command New-Item -ErrorAction SilentlyContinue) -and (Get-PSDrive -PSProvider FileSystem).Count -gt 0) {
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

# Cleanup temp download if used
if ($DownloadDir) {
    Remove-Item -Recurse -Force $DownloadDir -ErrorAction SilentlyContinue
    Write-Host "  Cleanup:     removed temporary download"
}

Write-Host ""
Write-Host "==> Done. Run these commands to enable:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    hermes plugins enable ai-memory"
Write-Host "    hermes memory setup"
Write-Host "    hermes memory status"
