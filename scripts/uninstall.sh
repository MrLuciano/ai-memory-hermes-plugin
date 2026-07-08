#!/usr/bin/env bash
# uninstall.sh — Remove the ai-memory Hermes plugin on Linux/macOS
#
# Removes the plugin from $HERMES_HOME/plugins/ai-memory. The ai-memory.json
# config file is kept unless REMOVE_CONFIG=true is set.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"
CONFIG_FILE="$HERMES_HOME/ai-memory.json"
REMOVE_CONFIG="${REMOVE_CONFIG:-false}"

echo "==> ai-memory Hermes plugin uninstaller"
echo ""

# Remove plugin directory, symlink, or junction
if [ -L "$PLUGIN_DIR" ]; then
  rm -f "$PLUGIN_DIR"
  echo "  Removed symlink: $PLUGIN_DIR"
elif [ -d "$PLUGIN_DIR" ]; then
  rm -rf "$PLUGIN_DIR"
  echo "  Removed directory: $PLUGIN_DIR"
else
  echo "  Plugin not found at $PLUGIN_DIR"
fi

# Optionally disable in Hermes (best effort)
if command -v hermes &>/dev/null; then
  if hermes plugins disable ai-memory &>/dev/null; then
    echo "  Disabled plugin in Hermes"
  else
    echo "  Could not disable plugin in Hermes (it may already be disabled)"
  fi
else
  echo "  Hermes CLI not found; skipping disable"
fi

# Remove config only when explicitly requested
if [ "$REMOVE_CONFIG" = "true" ] && [ -f "$CONFIG_FILE" ]; then
  rm -f "$CONFIG_FILE"
  echo "  Removed config: $CONFIG_FILE"
elif [ -f "$CONFIG_FILE" ]; then
  echo "  Config kept: $CONFIG_FILE (set REMOVE_CONFIG=true to remove)"
fi

echo ""
echo "==> Done."
