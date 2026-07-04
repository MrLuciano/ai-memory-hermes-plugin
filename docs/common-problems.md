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
