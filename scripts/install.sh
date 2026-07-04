#!/usr/bin/env bash
# install.sh — Install ai-memory Hermes plugin on Linux/macOS
set -euo pipefail

AI_MEMORY_SERVER_URL="${AI_MEMORY_SERVER_URL:-http://127.0.0.1:49374}"

echo "==> ai-memory Hermes plugin installer"
echo ""

# Locate this script's directory (works with symlinks)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_SRC="$PROJECT_DIR/plugins/memory/ai-memory"

if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
  echo "ERROR: plugin source not found at $PLUGIN_SRC"
  echo "Run this script from the project root or the scripts/ directory."
  exit 1
fi

# Resolve HERMES_HOME
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"

echo "  Source:      $PLUGIN_SRC"
echo "  Target:      $PLUGIN_DIR"
echo "  Server URL:  $AI_MEMORY_SERVER_URL"

# Symlink or copy
mkdir -p "$HERMES_HOME/plugins"
if command -v ln &>/dev/null; then
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

echo ""
echo "==> Done. Run these commands to enable:"
echo ""
echo "    hermes plugins enable ai-memory"
echo "    hermes memory setup"
echo "    hermes memory status"
