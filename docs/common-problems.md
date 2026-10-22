# Common Problems

## Server Connection

### "ai-memory server: unreachable"

**Cause:** Hermes cannot connect to the ai-memory HTTP API.

**Check:**
```bash
# Is the server running?
curl http://127.0.0.1:49374/admin/status

# What URL is configured?
hermes ai-memory config
```

**Fix:**
- Start ai-memory: `ai-memory serve`
- Set the correct URL: `export AI_MEMORY_SERVER_URL=http://host:port`
- Re-run `hermes memory setup`

### Connection Refused

**Cause:** Port not open or server on different host.

**Fix:**
```bash
# Check what's listening
ss -tlnp | grep 49374

# If ai-memory binds to a different port, update config
export AI_MEMORY_SERVER_URL=http://127.0.0.1:3113
```

## Authentication

### 401 Unauthorized

**Cause:** API key or auth token is wrong or missing.

**Check:**
```bash
hermes ai-memory config
# → auth_token: (set via env: AI_MEMORY_AUTH_TOKEN)  ← source shown
# → api_key:    (not set)
```

**Fix:**
- Set the correct key via environment variable:
  ```bash
  export AI_MEMORY_API_KEY=sk-...
  ```
- Add to shell profile for persistence:
  ```bash
  echo 'export AI_MEMORY_API_KEY=sk-...' >> ~/.bashrc
  source ~/.bashrc
  ```
- Or re-run `hermes memory setup`

### Secrets written to ai-memory.json (security concern)

**Cause:** Older plugin versions may have persisted `api_key` or `auth_token` to the config file in plaintext.

**Fix:** The plugin now strips secrets from the JSON file on load. To manually clean up:

```bash
# Check if secrets exist in the config
cat "$HERMES_HOME/ai-memory.json" | grep -E "api_key|auth_token"

# Edit and remove those lines, then set via env vars instead
export AI_MEMORY_API_KEY=sk-...
export AI_MEMORY_AUTH_TOKEN=your-token
```

**Note:** `hermes ai-memory config-set auth_token value` will remind you to use the env var — secrets are never written to disk by the plugin.

## Installation

### Plugin directory exists but is empty

**Cause:** The install or update step did not complete, or the plugin was placed at the wrong path (`$HERMES_HOME/plugins/memory/ai-memory/` instead of `$HERMES_HOME/plugins/ai-memory/`).

**Check:**
```bash
ls "$HERMES_HOME/plugins/ai-memory/"
# Should show: __init__.py plugin.yaml provider.py client.py config.py cli.py README.md

# Wrong nested path that Hermes will not discover:
ls "$HERMES_HOME/plugins/memory/ai-memory/" 2>/dev/null && echo "wrong path exists"
```

**Fix:**
```bash
# Remove the empty/wrong directory and re-install
rm -rf "$HERMES_HOME/plugins/ai-memory"
rm -rf "$HERMES_HOME/plugins/memory/ai-memory"  # if present
bash scripts/install.sh
hermes plugins enable ai-memory   # load the plugin
hermes memory setup               # activate it as the memory provider
```

### Provider shows as "none — built-in only"

**Cause:** The plugin is loaded but not active in Hermes. `hermes plugins enable ai-memory` only makes the plugin available; it does not activate a memory provider. `plugins.enabled` is unrelated to memory-provider activation, and Hermes skips `exclusive` plugins in the general enabled-check. Hermes only adds an external memory provider when `memory.provider` is set to `ai-memory` in `config.yaml`.

**Check:**
```bash
hermes plugins list | grep ai-memory
hermes memory status
# → provider should show ai-memory
cat "$HERMES_HOME/config.yaml" | grep -A2 "memory:"
```

**Fix:**
```bash
hermes memory setup
# or manually set in $HERMES_HOME/config.yaml:
# memory:
#   provider: ai-memory
```

If the plugin still does not appear, run with debug logging to see discovery/loading errors:
```bash
HERMES_PLUGINS_DEBUG=1 hermes memory status
```

### Update does not take effect

**Cause:** Hermes loads plugins at startup. Replacing files on disk does not affect the running process.

**Fix:** Restart Hermes after running `scripts/update.sh`, `scripts/update.ps1`, or `hermes ai-memory update`.

If the update failed midway, restore from the backup created at `$HERMES_HOME/.ai-memory-backups/ai-memory.bak.<timestamp>`:

```bash
rm -rf "$HERMES_HOME/plugins/ai-memory"
cp -r "$HERMES_HOME/.ai-memory-backups/ai-memory.bak.<timestamp>" "$HERMES_HOME/plugins/ai-memory"
```

### Uninstall leaves config behind

**Cause:** The uninstall scripts keep `$HERMES_HOME/ai-memory.json` by default to avoid losing user settings.

**Fix:** Pass the config-removal flag:

```bash
# Linux/macOS
REMOVE_CONFIG=true bash scripts/uninstall.sh
```

```powershell
# Windows
.\scripts\uninstall.ps1 -RemoveConfig
```

### Non-interactive mode warning ("non-interactive mode detected")

**Cause:** The script was piped or run without a TTY (e.g. via `curl | bash`). Scripts detect missing stdin and proceed with a warning.

**Fix:** This is expected behavior. To suppress the warning:

```bash
# Option 1: pass --yes
bash <(curl -sL .../install.sh) --yes

# Option 2: set FORCE=true
FORCE=true bash <(curl -sL .../install.sh)
```

For automation (CI/CD), always use `FORCE=true` or `--yes`/`-Yes`.

### Script prompts for confirmation (CI/automation blocked)

**Cause:** All install/uninstall/update scripts prompt for confirmation by default.

**Fix:** Pass `--yes` (bash) or `-Yes` (PowerShell), or set `FORCE=true`:

```bash
# Linux/macOS
FORCE=true bash scripts/install.sh
# or
bash scripts/install.sh --yes
```

```powershell
# Windows
.\scripts\install.ps1 -Yes
```

### Dry-run shows nothing to do

**Cause:** `--dry-run` / `-DryRun` shows what *would* happen. If the script has nothing to do (e.g. plugin already installed, no changes needed), the output is minimal.

**Fix:** This is expected. The dry-run output is a preview — run without `--dry-run` to apply changes.

### One-liner fails with "plugin source not found"

**Cause:** Older versions of `install.sh` / `install.ps1` assumed they were being run from a cloned repo. When invoked via the curl / `iex` one-liner, the script could not locate the local plugin files.

**Check:**
```bash
# Are you using the latest install script from main?
curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh | head -n 15
```

**Fix:**
- Re-run the current one-liner. The install scripts now detect the missing local source and download the plugin from GitHub automatically.
- If you prefer not to download, clone the repository and run the script locally:
  ```bash
  git clone https://github.com/MrLuciano/ai-memory-hermes-plugin.git
  cd ai-memory-hermes-plugin
  bash scripts/install.sh
  ```

### Plugin Not Found by Hermes

**Cause:** Plugin directory missing or wrong path.

**Check:**
```bash
ls "$HERMES_HOME/plugins/ai-memory/"
# Should show: __init__.py provider.py client.py config.py cli.py plugin.yaml
hermes plugins list | grep ai-memory
```

**Fix:**
```bash
# Symlink manually
mkdir -p "$HERMES_HOME/plugins"
ln -s "$PWD/plugins/memory/ai-memory" "$HERMES_HOME/plugins/ai-memory"
hermes plugins enable ai-memory   # load the plugin
hermes memory setup               # activate it as the memory provider
```

### "No module named 'config'" / ImportError

**Cause:** Python cannot find `config.py` relative to `__init__.py`.

The plugin inserts its directory into `sys.path` at import time, but some Hermes loaders have custom import handling.

**Fix:**
- Ensure `__init__.py` is in the same directory as `config.py`, `provider.py`, `client.py`, `cli.py`
- The `sys.path` insertion at `__init__.py:8-10` handles standard Hermes loading

## Runtime

### Prefetch Returns Empty Results

**Cause:** No matching pages in ai-memory wiki.

**Check:**
```bash
# Direct search
curl "http://127.0.0.1:49374/admin/search?q=test"
```

**Note:** The plugin returns empty string on no results — this is normal. The agent will see no injected context and rely on explicit `ai_memory_search` tool calls.

### Sync Turn Hangs

**Cause:** ai-memory server is slow or unreachable (the turn hook has a 0.5s timeout).

**Check:** Server health, network.

**Note:** `sync_turn` runs on a tracked background worker with error swallowing, so it never blocks the turn. Workers prefer Hermes' context-aware spawner and fall back to a daemon thread; `shutdown()` joins them under a bounded 5s deadline.

### Writes or project recall stopped after 0.1.4

**Cause:** A workspace-only `.ai-memory.toml` now derives its project from the checkout's git remote (or `basename(cwd)`) instead of failing closed. New pages go to the derived project, so pages written earlier under `hermes` / `hermes-default` are no longer returned by project-scoped recall. They still exist in ai-memory under the old project.

**Check:** Inspect the already initialized provider's `scope_diagnostics()`: `workspace`, `project`, `workspace_source`, `project_source`, `cwd_source`.

**Fix:** To keep the old project, pin it explicitly with `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`, `workspace`/`project` in `$HERMES_HOME/ai-memory.json`, or the initialization kwargs. Explicit values outrank marker and derivation.

### Writes disabled although the directory has a marker

**Cause:** Writes need both a non-empty workspace and project, and the project must be `explicit`/`marker`, or `derived` from an `explicit`/`marker` workspace. A project that is only the dataclass default (`hermes-default`), a derived project with no explicit/marker workspace, or an unusable directory stays read-only. Non-primary contexts (cron/subagent) never write.

**Check:** From a normal session startup, read the INFO line containing `ai-memory scope:`, or inspect `scope_diagnostics()` on the initialized provider: `cwd_received`, `cwd_source`, `workspace`, `project`, `workspace_source`, `project_source`, `scope_known`, `writes_allowed`.

**Fix:** Provide an absolute, existing session directory (`AI_MEMORY_CWD` overrides the Hermes `cwd` kwarg and `resolve_agent_cwd()`), or pin `workspace`/`project` explicitly. The plugin never falls back to `os.getcwd()`.

### Memory Not Mirroring

**Cause:** The mirrored actions are `add` and `replace` — what Hermes announces for a built-in `MEMORY.md` / `USER.md` write. `write` and `append` are still accepted as synonyms for older callers.

`remove` is skipped on purpose: the native store owns the deletion, and the mirror keeps the page history instead of writing a tombstone. A `replace` carries the superseded entry in `metadata["previous_content"]` and the page keeps it under `## Substituído`.

### Recall Context Looks Unattributed

**Cause:** Recall spans every project (that is what makes cross-agent recall work), so each injected hit is labelled `<title> (<path>): <snippet>`.

If the hits belong to a project you did not expect, check the resolved scope: a `workspace`/`project` set in `ai-memory.json` or via `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` wins over the checkout's `.ai-memory.toml`, and a marker's pinned project wins over a git-remote-derived one. Use `scope_diagnostics()` to see the value and its provenance.

### Recall misses pages after upgrading

**Cause:** Project-scoped recall follows the resolved project. If a workspace-only marker now derives a different project than the one used before 0.1.4, older pages are still stored under the previous project but are no longer searched.

**Fix:** Pin the old scope explicitly (see [Writes or project recall stopped after 0.1.4](#writes-or-project-recall-stopped-after-014)) or search globally (`search_scope=global`) to confirm the old pages still exist.

## Testing

### Tests Fail with Connection Error

The test suite uses `httpx` mock transports and `monkeypatch` — no real network calls. If tests fail with connection errors, check for stale `.pytest_cache` or monkeypatch isolation issues:

```bash
rm -rf .pytest_cache
uv run pytest --cov -v
```

### "Cannot schedule new futures" on Shutdown

This is a known CPython shutdown race with background threads. The plugin tracks its workers and joins them under a bounded 5s deadline in `shutdown()`, but a worker can still fire during interpreter teardown if that deadline expires or Hermes exits without calling `shutdown()`. The error is harmless (logged at debug level). Set `PYTHONWARNINGS=ignore` if it's noisy:

```bash
export PYTHONWARNINGS=ignore
```

## Known Limitations

- **Pause instead of a full circuit breaker:** after `FAILURE_THRESHOLD` (3) consecutive transport failures the client stops calling the server for `COOLDOWN_SECONDS` (60s) and reports the reason through `unavailable_reason()`. A successful request clears the state immediately.
- **No durable write queue:** Turn sync is fire-and-forget. If the server is down, that turn is lost — ai-memory applies its own durable spool for hooks it does receive.
- **Session end posts no transcript:** ai-memory reads no body field on `session-end`, so the event carries the session id only. Re-close a lost session with `ai-memory finalize-session --agent hermes`.
- **Single active provider:** Only one Hermes memory provider can be active at a time, selected via `memory.provider` in config.
