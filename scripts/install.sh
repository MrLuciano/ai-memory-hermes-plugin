#!/usr/bin/env bash
# install.sh — Install ai-memory Hermes plugin on Linux/macOS
#
# Works when run:
#   • locally from a cloned repo (scripts/install.sh or ./scripts/install.sh)
#   • via the curl one-liner: bash <(curl -sL .../scripts/install.sh)
#
# In the one-liner case the script is streamed through /dev/fd, so there is no
# local repo to symlink. We fall back to downloading the plugin files from
# GitHub and copying them into $HERMES_HOME/plugins/ai-memory.
set -euo pipefail

AI_MEMORY_SERVER_URL="${AI_MEMORY_SERVER_URL:-http://127.0.0.1:49374}"
REPO_TARBALL_URL="${REPO_TARBALL_URL:-https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.tar.gz}"

echo "==> ai-memory Hermes plugin installer"
echo ""

# Locate this script's directory (works with symlinks)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_SRC="$PROJECT_DIR/plugins/memory/ai-memory"
DOWNLOAD_DIR=""

# If the local repo isn't present (e.g. curl one-liner via process substitution),
# download the plugin source from GitHub.
if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
  if ! command -v curl &>/dev/null || ! command -v tar &>/dev/null; then
    echo "ERROR: plugin source not found locally and curl/tar are required to download it."
    echo "Either clone the repository or install curl and tar, then re-run."
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

# Resolve HERMES_HOME
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"
WRONG_PLUGIN_DIR="$HERMES_HOME/plugins/memory/ai-memory"

echo "  Source:      $PLUGIN_SRC"
echo "  Target:      $PLUGIN_DIR"
echo "  Server URL:  $AI_MEMORY_SERVER_URL"

# Warn if the plugin was previously placed at the wrong nested path
if [ -e "$WRONG_PLUGIN_DIR" ]; then
  echo ""
  echo "  WARNING:     found $WRONG_PLUGIN_DIR"
  echo "               User-installed memory providers belong in $PLUGIN_DIR,"
  echo "               not in plugins/memory/. Remove the nested path and re-run."
fi

# If the target exists but is empty, treat it as not installed
if [ -d "$PLUGIN_DIR" ] && [ ! -f "$PLUGIN_DIR/__init__.py" ]; then
  echo "  Target exists but is empty; removing and re-installing."
  rm -rf "$PLUGIN_DIR"
fi

# Symlink or copy
mkdir -p "$HERMES_HOME/plugins"
if [ -n "$DOWNLOAD_DIR" ]; then
  # Downloaded source lives in a temp dir; copy it so the plugin survives cleanup.
  rm -rf "$PLUGIN_DIR"
  cp -r "$PLUGIN_SRC" "$PLUGIN_DIR"
  echo "  Install:     copy (from downloaded source)"
elif command -v ln &>/dev/null; then
  ln -sfn "$PLUGIN_SRC" "$PLUGIN_DIR"
  echo "  Install:     symlink"
else
  cp -r "$PLUGIN_SRC" "$PLUGIN_DIR"
  echo "  Install:     copy"
fi

# Write initial config if none exists
CONFIG_FILE="$HERMES_HOME/ai-memory.json"
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<EOF
{
  "server_url": "$AI_MEMORY_SERVER_URL",
  "workspace": "hermes",
  "project": "hermes-default"
}
EOF
  echo "  Config:      $CONFIG_FILE (created)"
else
  echo "  Config:      $CONFIG_FILE (exists, untouched)"
fi

# Cleanup temp download if used
if [ -n "$DOWNLOAD_DIR" ]; then
  rm -rf "$DOWNLOAD_DIR"
  echo "  Cleanup:     removed temporary download"
fi

# Verify install
if [ ! -f "$PLUGIN_DIR/__init__.py" ]; then
  echo ""
  echo "ERROR: install verification failed — $PLUGIN_DIR/__init__.py is missing."
  exit 1
fi

echo ""
echo "==> Done. Run these commands to enable:"
echo ""
echo "    hermes plugins enable ai-memory"
echo "    hermes memory setup"
echo "    hermes memory status"
