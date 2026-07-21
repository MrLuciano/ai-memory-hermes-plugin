#!/usr/bin/env bash
# uninstall.sh — Remove the ai-memory Hermes plugin on Linux/macOS
#
# Removes the plugin from $HERMES_HOME/plugins/ai-memory. The ai-memory.json
# config file is kept unless REMOVE_CONFIG=true is set.
#
# Options:
#   --dry-run   Show what would be done without making changes
#   --yes, -y   Skip confirmation prompts
#
# Env vars:
#   FORCE=true       Skip confirmation prompts (same as --yes)
#   REMOVE_CONFIG    Set to "true" to also remove ai-memory.json
#   HERMES_HOME      Hermes profile directory (default: ~/.hermes)
set -euo pipefail

# --- Flag parsing ---
DRY_RUN=false
YES=false
FORCE="${FORCE:-false}"

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --yes|-y)  YES=true ;;
    --help|-h)
      echo "Usage: $0 [--dry-run] [--yes]"
      echo ""
      echo "Options:"
      echo "  --dry-run   Show what would be done without making changes"
      echo "  --yes, -y   Skip confirmation prompts"
      echo ""
      echo "Env vars:"
      echo "  FORCE=true       Skip confirmation prompts"
      echo "  REMOVE_CONFIG    Set to 'true' to also remove ai-memory.json"
      echo "  HERMES_HOME      Hermes profile directory (default: ~/.hermes)"
      exit 0
      ;;
  esac
done

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"
CONFIG_FILE="$HERMES_HOME/ai-memory.json"
REMOVE_CONFIG="${REMOVE_CONFIG:-false}"

# --- Helper functions ---
info()  { echo "  $*"; }
warn()  { echo "  WARNING: $*" >&2; }
err()   { echo "ERROR: $*" >&2; }
ok()    { echo "  OK: $*"; }

run() {
  if [ "$DRY_RUN" = "true" ]; then
    echo "  [DRY RUN] $*"
    return 0
  fi
  "$@"
}

confirm() {
  local msg="$1"
  if [ "$DRY_RUN" = "true" ]; then return 0; fi
  if [ "$YES" = "true" ] || [ "$FORCE" = "true" ]; then return 0; fi
  if [ ! -t 0 ]; then
    echo ""
    echo "  NOTE: non-interactive mode detected (piped input)."
    echo "  To skip this prompt, pass --yes or set FORCE=true."
    echo "  Proceeding with uninstall..."
    return 0
  fi
  echo ""
  echo "$msg"
  read -r -p "  Proceed? [y/N] " answer
  case "$answer" in
    [yY][eE][sS]|[yY]) return 0 ;;
    *) echo "  Aborted."; exit 1 ;;
  esac
}

# --- Pre-flight checks ---
preflight() {
  echo ""
  echo "==> Pre-flight checks"
  echo ""

  # 1. Plugin state
  if [ -L "$PLUGIN_DIR" ]; then
    info "Plugin:       $PLUGIN_DIR (symlink → $(readlink "$PLUGIN_DIR"))"
  elif [ -d "$PLUGIN_DIR" ]; then
    local count
    count=$(find "$PLUGIN_DIR" -maxdepth 1 -type f | wc -l)
    info "Plugin:       $PLUGIN_DIR ($count files)"
  else
    info "Plugin:       not found at $PLUGIN_DIR"
    return
  fi

  # 2. Config file
  if [ -f "$CONFIG_FILE" ]; then
    if [ "$REMOVE_CONFIG" = "true" ]; then
      info "Config:       $CONFIG_FILE (will be removed)"
    else
      info "Config:       $CONFIG_FILE (will be kept)"
    fi
  else
    info "Config:       not found"
  fi

  # 3. Hermes CLI
  if command -v hermes &>/dev/null; then
    ok "Hermes CLI found"
  else
    warn "Hermes CLI not found — cannot disable plugin automatically."
  fi

  # 4. Hermes process
  if pgrep -f "hermes" >/dev/null 2>&1; then
    warn "Hermes process appears to be running."
    info "You will need to restart Hermes after uninstall."
  fi

  # 5. ai-memory server
  local server_url
  if [ -f "$CONFIG_FILE" ]; then
    server_url=$(grep -o '"server_url"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/.*"server_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' || true)
  fi
  server_url="${server_url:-http://127.0.0.1:49374}"
  info "Checking ai-memory server at $server_url ..."
  if curl -sf --connect-timeout 3 "$server_url/admin/status" >/dev/null 2>&1; then
    ok "ai-memory server is reachable — will become unavailable after uninstall"
  else
    info "ai-memory server is not reachable (may already be stopped)"
  fi

  echo ""
  echo "  Checks complete."
}

# --- Main ---
echo "==> ai-memory Hermes plugin uninstaller"
echo ""
if [ "$DRY_RUN" = "true" ]; then
  echo "  *** DRY RUN MODE — no changes will be made ***"
fi

# Run pre-flight
preflight

# Show planned actions
echo ""
echo "==> Planned actions"
echo ""
if [ -L "$PLUGIN_DIR" ]; then
  echo "  1. Remove symlink: $PLUGIN_DIR"
elif [ -d "$PLUGIN_DIR" ]; then
  echo "  1. Remove directory: $PLUGIN_DIR"
else
  echo "  1. (nothing to remove — plugin not found)"
fi

if command -v hermes &>/dev/null; then
  echo "  2. Disable plugin in Hermes (best-effort)"
else
  echo "  2. (Hermes CLI not found — skip disable)"
fi

if [ "$REMOVE_CONFIG" = "true" ] && [ -f "$CONFIG_FILE" ]; then
  echo "  3. Remove config: $CONFIG_FILE"
elif [ -f "$CONFIG_FILE" ]; then
  echo "  3. Config kept: $CONFIG_FILE"
else
  echo "  3. (no config to remove)"
fi

# Confirmation
confirm "This will remove the ai-memory plugin:
  Plugin:   $PLUGIN_DIR
  Config:   $CONFIG_FILE $(if [ "$REMOVE_CONFIG" = "true" ]; then echo "(will be removed)"; else echo "(kept)"; fi)

  The plugin will be disabled in Hermes if the CLI is available."

# --- Uninstall ---
echo ""
echo "==> Uninstalling"

# Remove plugin directory, symlink, or junction
if [ -L "$PLUGIN_DIR" ]; then
  run rm -f "$PLUGIN_DIR"
  info "Removed symlink: $PLUGIN_DIR"
elif [ -d "$PLUGIN_DIR" ]; then
  run rm -rf "$PLUGIN_DIR"
  info "Removed directory: $PLUGIN_DIR"
else
  info "Plugin not found at $PLUGIN_DIR"
fi

# Optionally disable in Hermes (best effort)
if command -v hermes &>/dev/null; then
  if [ "$DRY_RUN" = "true" ]; then
    info "[DRY RUN] Would run: hermes plugins disable ai-memory"
  else
    if hermes plugins disable ai-memory &>/dev/null; then
      info "Disabled plugin in Hermes"
    else
      info "Could not disable plugin in Hermes (it may already be disabled)"
    fi
  fi
else
  info "Hermes CLI not found; skipping disable"
fi

# Remove config only when explicitly requested
if [ "$REMOVE_CONFIG" = "true" ] && [ -f "$CONFIG_FILE" ]; then
  run rm -f "$CONFIG_FILE"
  info "Removed config: $CONFIG_FILE"
elif [ -f "$CONFIG_FILE" ]; then
  info "Config kept: $CONFIG_FILE (set REMOVE_CONFIG=true to remove)"
fi

echo ""
if [ "$DRY_RUN" = "true" ]; then
  echo "==> Dry run complete. No changes were made."
  echo "    Re-run without --dry-run to apply."
else
  echo "==> Done."
fi
