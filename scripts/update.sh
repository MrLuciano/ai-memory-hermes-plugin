#!/usr/bin/env bash
# update.sh — Update the ai-memory Hermes plugin on Linux/macOS
#
# Defaults to downloading the latest plugin from GitHub. Set UPDATE_FROM_LOCAL=true
# to update from a cloned repository instead (preserves the symlink install).
set -euo pipefail

AI_MEMORY_SERVER_URL="${AI_MEMORY_SERVER_URL:-http://127.0.0.1:49374}"
REPO_TARBALL_URL="${REPO_TARBALL_URL:-https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.tar.gz}"
UPDATE_FROM_LOCAL="${UPDATE_FROM_LOCAL:-false}"

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"
CONFIG_FILE="$HERMES_HOME/ai-memory.json"
BACKUP_ROOT="$HERMES_HOME/.ai-memory-backups"

echo "==> ai-memory Hermes plugin updater"
echo ""

if [ ! -e "$PLUGIN_DIR" ]; then
  echo "ERROR: plugin not installed at $PLUGIN_DIR"
  echo "Run scripts/install.sh first."
  exit 1
fi

# Detect current install method
CURRENT_METHOD="copy"
if [ -L "$PLUGIN_DIR" ]; then
  CURRENT_METHOD="symlink"
fi

# Resolve source
PLUGIN_SRC=""
DOWNLOAD_DIR=""
if [ "$UPDATE_FROM_LOCAL" = "true" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
  PLUGIN_SRC="$PROJECT_DIR/plugins/memory/ai-memory"
  if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
    echo "ERROR: local plugin source not found at $PLUGIN_SRC"
    echo "Run this script from the project root or the scripts/ directory."
    exit 1
  fi
  echo "  Source:      $PLUGIN_SRC (local repo)"
else
  if ! command -v curl &>/dev/null || ! command -v tar &>/dev/null; then
    echo "ERROR: curl and tar are required to download the update."
    exit 1
  fi
  DOWNLOAD_DIR="$(mktemp -d)"
  echo "  Source:      $REPO_TARBALL_URL (downloading...)"
  curl -fsSL "$REPO_TARBALL_URL" | tar -xz -C "$DOWNLOAD_DIR" --strip-components=1
  PLUGIN_SRC="$DOWNLOAD_DIR/plugins/memory/ai-memory"
  if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
    echo "ERROR: downloaded plugin source not found at $PLUGIN_SRC"
    rm -rf "$DOWNLOAD_DIR"
    exit 1
  fi
fi

echo "  Target:      $PLUGIN_DIR"
echo "  Method:      $CURRENT_METHOD"

# Backup current install (outside $HERMES_HOME/plugins so Hermes does not discover it)
mkdir -p "$BACKUP_ROOT"
BACKUP_DIR="$BACKUP_ROOT/ai-memory.bak.$(date +%Y%m%d%H%M%S)"
cp -a "$PLUGIN_DIR" "$BACKUP_DIR"
echo "  Backup:      $BACKUP_DIR"

# Remove old install
if [ "$CURRENT_METHOD" = "symlink" ]; then
  rm -f "$PLUGIN_DIR"
else
  rm -rf "$PLUGIN_DIR"
fi

# Install updated files
if [ "$UPDATE_FROM_LOCAL" = "true" ] && [ "$CURRENT_METHOD" = "symlink" ] && command -v ln &>/dev/null; then
  ln -sfn "$PLUGIN_SRC" "$PLUGIN_DIR"
  echo "  Updated:     symlink (from local repo)"
else
  cp -r "$PLUGIN_SRC" "$PLUGIN_DIR"
  echo "  Updated:     copy (from $([ "$UPDATE_FROM_LOCAL" = "true" ] && echo "local repo" || echo "downloaded source"))"
fi

# Preserve config: if it existed in the backup but is missing now, restore it
if [ -f "$BACKUP_DIR/ai-memory.json" ] && [ ! -f "$CONFIG_FILE" ]; then
  cp "$BACKUP_DIR/ai-memory.json" "$CONFIG_FILE"
  echo "  Config:      restored from backup"
elif [ -f "$CONFIG_FILE" ]; then
  echo "  Config:      $CONFIG_FILE (preserved)"
else
  cat > "$CONFIG_FILE" <<EOF
{
  "server_url": "$AI_MEMORY_SERVER_URL",
  "workspace": "hermes",
  "project": "hermes-default"
}
EOF
  echo "  Config:      $CONFIG_FILE (created)"
fi

# Cleanup temp download
if [ -n "${DOWNLOAD_DIR:-}" ]; then
  rm -rf "$DOWNLOAD_DIR"
  echo "  Cleanup:     removed temporary download"
fi

# List backups (directories and symlinks)
echo ""
echo "  Backups:"
if [ -d "$BACKUP_ROOT" ]; then
  for b in "$BACKUP_ROOT"/ai-memory.bak.*; do
    [ -e "$b" ] || continue
    echo "    - $b"
  done
fi

# Best-effort enable
if command -v hermes &>/dev/null; then
  if hermes plugins enable ai-memory &>/dev/null; then
    echo "  Hermes:      plugin enabled"
  else
    echo "  Hermes:      plugin already enabled or could not enable"
  fi
else
  echo "  Hermes:      CLI not found; skipping enable"
fi

echo ""
echo "==> Done. Restart Hermes for the update to take effect."
