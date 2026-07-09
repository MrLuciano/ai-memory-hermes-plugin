# Common Problems

## Server Connection

### "ai-memory server: unreachable"

**Cause:** Hermes cannot connect to the ai-memory HTTP API.

**Check:**
```bash
# Is the server running?
curl http://127.0.0.1:49374/admin/status

# What URL is configured?
hermes memory config
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
hermes memory config
# → api_key:    ****
# → auth_token: ****
```

**Fix:**
- Set the correct key: `export AI_MEMORY_API_KEY=sk-...`
- Or re-run `hermes memory setup`

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
hermes plugins enable ai-memory
```

### Provider shows as "none — built-in only"

**Cause:** The plugin is installed but not active in Hermes. Hermes only adds an external memory provider when `memory.provider` is set to `ai-memory` in `config.yaml`.

**Check:**
```bash
hermes plugins list | grep ai-memory
hermes memory config
# → provider should show ai-memory
cat "$HERMES_HOME/config.yaml" | grep -A2 "memory:"
```

**Fix:**
```bash
hermes plugins enable ai-memory
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
hermes plugins enable ai-memory
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

**Cause:** ai-memory server is slow or unreachable (sync_turn has a 0.5s timeout).

**Check:** Server health, network.

**Note:** `sync_turn` runs on a daemon thread with error swallowing. If the server is slow, the thread may accumulate. The plugin caps at one thread per turn — no queue.

### Memory Not Mirroring

**Cause:** Action is not `"write"` or `"append"` (the only mirrored actions).

The plugin checks `action in ("write", "append")` before mirroring. Other memory actions like `"replace"` or `"delete"` are ignored. This is intentional — only new content is mirrored, modifications/deletions are not.

## Testing

### Tests Fail with Connection Error

The test suite uses `httpx` mock transports and `monkeypatch` — no real network calls. If tests fail with connection errors, check for stale `.pytest_cache` or monkeypatch isolation issues:

```bash
rm -rf .pytest_cache
uv run pytest --cov -v
```

### "Cannot schedule new futures" on Shutdown

This is a known CPython shutdown race with daemon threads. ai-memory plugin uses daemon threads that may fire during interpreter teardown. The error is harmless (logged at debug level). Set `PYTHONWARNINGS=ignore` if it's noisy:

```bash
export PYTHONWARNINGS=ignore
```

## Known Limitations

- **No circuit breaker:** Unlike mem0 plugin, ai-memory does not pause API calls after consecutive failures. The local Rust server is assumed to be reliable.
- **No durable write queue:** Turn sync is fire-and-forget. If the server is down, the turn is lost. ai-memory server handles its own persistence.
- **No multi-turn cadence:** Prefetch fires every turn. The local server response is fast enough that cadence control is unnecessary.
- **Single active provider:** Only one Hermes memory provider can be active at a time, selected via `memory.provider` in config.
