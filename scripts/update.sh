#!/usr/bin/env bash
# update.sh — Update the ai-memory Hermes plugin on Linux/macOS
#
# Defaults to downloading the latest plugin from GitHub. Set UPDATE_FROM_LOCAL=true
# to update from a cloned repository instead (preserves the symlink install).
#
# Options:
#   --dry-run   Show what would be done without making changes
#   --yes, -y   Skip confirmation prompts
#
# Env vars:
#   FORCE=true            Skip confirmation prompts (same as --yes)
#   UPDATE_FROM_LOCAL     Set to "true" to update from local repo instead of GitHub
#   HERMES_HOME           Hermes profile directory (default: ~/.hermes)
#   AI_MEMORY_SERVER_URL  Server URL for pre-flight check (default: http://127.0.0.1:49374)
#   REPO_TARBALL_URL      Override GitHub tarball URL
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
      echo "  FORCE=true            Skip confirmation prompts"
      echo "  UPDATE_FROM_LOCAL     Set to 'true' to update from local repo"
      echo "  HERMES_HOME           Hermes profile directory (default: ~/.hermes)"
      echo "  AI_MEMORY_SERVER_URL  Server URL for pre-flight check"
      echo "  REPO_TARBALL_URL      Override GitHub tarball URL"
      exit 0
      ;;
  esac
done

AI_MEMORY_SERVER_URL="${AI_MEMORY_SERVER_URL:-http://127.0.0.1:49374}"
REPO_TARBALL_URL="${REPO_TARBALL_URL:-https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.tar.gz}"
UPDATE_FROM_LOCAL="${UPDATE_FROM_LOCAL:-false}"

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ai-memory"
CONFIG_FILE="$HERMES_HOME/ai-memory.json"
BACKUP_ROOT="$HERMES_HOME/.ai-memory-backups"
WRONG_PLUGIN_DIR="$HERMES_HOME/plugins/memory/ai-memory"

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
    echo "  Proceeding with update..."
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
  local checks_passed=true
  echo ""
  echo "==> Pre-flight checks"
  echo ""

  # 1. Plugin state
  if [ ! -e "$PLUGIN_DIR" ]; then
    err "Plugin not installed at $PLUGIN_DIR"
    err "Run scripts/install.sh first."
    exit 1
  fi

  if [ -d "$PLUGIN_DIR" ] && [ ! -f "$PLUGIN_DIR/__init__.py" ]; then
    warn "$PLUGIN_DIR exists but is empty; continuing update."
  fi

  if [ -L "$PLUGIN_DIR" ]; then
    info "Install method: symlink → $(readlink "$PLUGIN_DIR")"
  else
    local count
    count=$(find "$PLUGIN_DIR" -maxdepth 1 -type f | wc -l)
    info "Install method: copy ($count files)"
  fi

  # 2. Wrong path
  if [ -e "$WRONG_PLUGIN_DIR" ]; then
    warn "Found $WRONG_PLUGIN_DIR"
    info "User-installed plugins belong in $PLUGIN_DIR"
  fi

  # 3. Config file
  if [ -f "$CONFIG_FILE" ]; then
    info "Config:        $CONFIG_FILE (will be preserved)"
  else
    info "Config:        not found (will be created)"
  fi

  # 4. Backup directory
  if [ -d "$BACKUP_ROOT" ]; then
    local backup_count
    backup_count=$(find "$BACKUP_ROOT" -maxdepth 1 -name "ai-memory.bak.*" -type d | wc -l)
    info "Existing backups: $backup_count in $BACKUP_ROOT"
  fi

  # 5. Source resolution
  if [ "$UPDATE_FROM_LOCAL" = "true" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    local local_src="$PROJECT_DIR/plugins/memory/ai-memory"
    if [ ! -f "$local_src/__init__.py" ]; then
      err "Local plugin source not found at $local_src"
      exit 1
    fi
    info "Source:        $local_src (local repo)"
  else
    info "Source:        $REPO_TARBALL_URL (GitHub)"
  fi

  # 6. Hermes CLI
  if command -v hermes &>/dev/null; then
    ok "Hermes CLI found"
  else
    warn "Hermes CLI not found — cannot enable plugin automatically."
  fi

  # 7. Hermes process
  if pgrep -f "hermes" >/dev/null 2>&1; then
    warn "Hermes process appears to be running."
    info "You will need to restart Hermes after update."
  fi

  # 8. ai-memory server
  info "Checking ai-memory server at $AI_MEMORY_SERVER_URL ..."
  if curl -sf --connect-timeout 3 "$AI_MEMORY_SERVER_URL/admin/status" >/dev/null 2>&1; then
    ok "ai-memory server is reachable"
  else
    warn "ai-memory server at $AI_MEMORY_SERVER_URL is not reachable."
    info "The update will proceed but the server should be running after restart."
  fi

  echo ""
  echo "  All pre-flight checks complete."
}

# --- Main ---
echo "==> ai-memory Hermes plugin updater"
echo ""
if [ "$DRY_RUN" = "true" ]; then
  echo "  *** DRY RUN MODE — no changes will be made ***"
fi

# Run pre-flight
preflight

# Resolve source (for display in planned actions)
if [ "$UPDATE_FROM_LOCAL" = "true" ]; then
  SOURCE_LABEL="local repo"
else
  SOURCE_LABEL="GitHub ($REPO_TARBALL_URL)"
fi

# Show planned actions
echo ""
echo "==> Planned actions"
echo ""
echo "  1. Backup current install → $BACKUP_ROOT/ai-memory.bak.<timestamp>"
echo "  2. Remove current plugin files from $PLUGIN_DIR"
echo "  3. Copy updated files from $SOURCE_LABEL → $PLUGIN_DIR"
if [ -f "$CONFIG_FILE" ]; then
  echo "  4. Preserve config: $CONFIG_FILE"
else
  echo "  4. Create config: $CONFIG_FILE"
fi
echo "  5. Enable plugin in Hermes (best-effort, if CLI available)"
echo "  6. Verify __init__.py exists after update"

# Confirmation
confirm "This will update the ai-memory plugin:
  From:  $SOURCE_LABEL
  To:    $PLUGIN_DIR

  A backup of the current install will be saved to:
  $BACKUP_ROOT/ai-memory.bak.<timestamp>

  Config ($CONFIG_FILE) will be preserved."

# --- Update ---
echo ""
echo "==> Updating"

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
    err "local plugin source not found at $PLUGIN_SRC"
    exit 1
  fi
  info "Source:      $PLUGIN_SRC (local repo)"
else
  if ! command -v curl &>/dev/null || ! command -v tar &>/dev/null; then
    err "curl and tar are required to download the update."
    exit 1
  fi
  DOWNLOAD_DIR="$(mktemp -d)"
  info "Downloading from $REPO_TARBALL_URL ..."
  if [ "$DRY_RUN" = "true" ]; then
    info "[DRY RUN] Would download from $REPO_TARBALL_URL"
    PLUGIN_SRC="$DOWNLOAD_DIR/plugins/memory/ai-memory"
  else
    curl -fsSL "$REPO_TARBALL_URL" | tar -xz -C "$DOWNLOAD_DIR" --strip-components=1
    PLUGIN_SRC="$DOWNLOAD_DIR/plugins/memory/ai-memory"
    if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
      err "downloaded plugin source not found at $PLUGIN_SRC"
      rm -rf "$DOWNLOAD_DIR"
      exit 1
    fi
  fi
fi

info "Target:      $PLUGIN_DIR"
info "Method:      $CURRENT_METHOD"

# Backup current install
BACKUP_DIR="$BACKUP_ROOT/ai-memory.bak.$(date +%Y%m%d%H%M%S)"
if [ "$DRY_RUN" = "true" ]; then
  info "[DRY RUN] Would backup $PLUGIN_DIR → $BACKUP_DIR"
else
  mkdir -p "$BACKUP_ROOT"
  cp -a "$PLUGIN_DIR" "$BACKUP_DIR"
  info "Backup:      $BACKUP_DIR"
fi

# Remove old install
if [ "$CURRENT_METHOD" = "symlink" ]; then
  run rm -f "$PLUGIN_DIR"
else
  run rm -rf "$PLUGIN_DIR"
fi

# Install updated files
if [ "$UPDATE_FROM_LOCAL" = "true" ] && [ "$CURRENT_METHOD" = "symlink" ] && command -v ln &>/dev/null; then
  run ln -sfn "$PLUGIN_SRC" "$PLUGIN_DIR"
  info "Updated:     symlink (from local repo)"
else
  run cp -r "$PLUGIN_SRC" "$PLUGIN_DIR"
  info "Updated:     copy (from $([ "$UPDATE_FROM_LOCAL" = "true" ] && echo "local repo" || echo "downloaded source"))"
fi

# Preserve config
if [ "$DRY_RUN" != "true" ]; then
  if [ -f "$BACKUP_DIR/ai-memory.json" ] && [ ! -f "$CONFIG_FILE" ]; then
    cp "$BACKUP_DIR/ai-memory.json" "$CONFIG_FILE"
    info "Config:      restored from backup"
  elif [ -f "$CONFIG_FILE" ]; then
    info "Config:      $CONFIG_FILE (preserved)"
  else
    cat > "$CONFIG_FILE" <<EOF
{
  "server_url": "$AI_MEMORY_SERVER_URL",
  "workspace": "hermes",
  "project": "hermes-default"
}
EOF
    info "Config:      $CONFIG_FILE (created)"
  fi
else
  info "[DRY RUN] Config would be preserved or created"
fi

# Cleanup temp download
if [ -n "${DOWNLOAD_DIR:-}" ]; then
  run rm -rf "$DOWNLOAD_DIR"
  info "Cleanup:     removed temporary download"
fi

# List backups
echo ""
echo "  Backups:"
if [ -d "$BACKUP_ROOT" ]; then
  for b in "$BACKUP_ROOT"/ai-memory.bak.*; do
    [ -e "$b" ] || continue
    info "  - $b"
  done
fi

# Best-effort enable
if command -v hermes &>/dev/null; then
  if [ "$DRY_RUN" = "true" ]; then
    info "[DRY RUN] Would run: hermes plugins enable ai-memory"
  else
    if hermes plugins enable ai-memory &>/dev/null; then
      info "Hermes:      plugin enabled"
    else
      info "Hermes:      plugin already enabled or could not enable"
    fi
  fi
else
  info "Hermes:      CLI not found; skipping enable"
fi

# Verify update
if [ "$DRY_RUN" != "true" ] && [ ! -f "$PLUGIN_DIR/__init__.py" ]; then
  echo ""
  err "update verification failed — $PLUGIN_DIR/__init__.py is missing."
  info "             Restore from backup: $BACKUP_DIR"
  exit 1
fi

echo ""
if [ "$DRY_RUN" = "true" ]; then
  echo "==> Dry run complete. No changes were made."
  echo "    Re-run without --dry-run to apply."
else
  echo "==> Done. Restart Hermes for the update to take effect."
fi
