---
phase: 06-code-review
reviewed: 2026-07-03T12:00:00Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - plugins/memory/ai-memory/__init__.py
  - plugins/memory/ai-memory/config.py
  - plugins/memory/ai-memory/client.py
  - plugins/memory/ai-memory/provider.py
  - plugins/memory/ai-memory/cli.py
  - plugins/memory/ai-memory/plugin.yaml
  - tests/conftest.py
  - tests/test_config.py
  - tests/test_client.py
  - tests/test_provider.py
  - tests/test_entry.py
  - tests/test_cli.py
  - pyproject.toml
findings:
  critical: 7
  warning: 8
  info: 6
  total: 21
status: issues_found
---

# Phase 6: Code Review Report — ai-memory-hermes-plugin v0.1.0

**Reviewed:** 2026-07-03T12:00:00Z
**Depth:** deep (cross-file)
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The plugin architecture is well-separated into config, client, provider, CLI, and entry-point layers, with meaningful test coverage across all modules. The threading strategy for hook paths (daemon threads) and the `MemoryProvider` ABC fallback are pragmatic design choices. However, the codebase ships with several correctness bugs and configuration gaps that could cause runtime failures in production:

1. **`is_available()` is a tautology** — always returns True because `server_url` has a non-empty default.
2. **Implicit relative imports break production loading** — `from config import` (no dot-prefix) fails when Hermes loads `__init__.py` as a package member.
3. **Missing runtime dependency** — `httpx` is only in dev-dependencies, not `[project] dependencies`, so `pip install` won't pull it in.
4. **Inconsistent config precedence** — `register()` uses env-over-file ordering; `load_config()` (used by CLI) uses file-over-env ordering.
5. **`on_memory_write` propagates exceptions** — violates the project's own "hook paths swallow" convention.
6. **`plugin.yaml` incomplete** — missing `entry_point` and only declares one of many hooks.
7. **mypy excludes the plugin** — the `exclude = ["ai-memory"]` directive disables type-checking on all plugin source.

Below: every finding organized by severity, each with a specific fix.

---

## Critical Issues

### CR-01: `is_available()` always returns True (logic bug)

**File:** `plugins/memory/ai-memory/provider.py:36-40`
**File:** `plugins/memory/ai-memory/config.py:14`

**Issue:** `AiMemoryProvider.is_available()` checks whether `server_url`, `auth_token`, or `api_key` are truthy. Since `AiMemoryConfig.server_url` defaults to `"http://127.0.0.1:49374"`, the expression `bool(self._config.server_url or ...)` always evaluates to `True` — even when the user has never configured ai-memory and no server is running. This defeats the purpose of `is_available()`, which Hermes uses to decide whether the provider can be enabled.

**Fix:** Either make `is_available()` actually probe the server (e.g., with a lightweight GET), or change the semantics to check that at least one credential is set alongside the server URL (indicating the user has intentionally configured the plugin).

```python
# Option A: lightweight connectivity check
def is_available(self) -> bool:
    try:
        self._client.status()
        return True
    except Exception:
        return False

# Option B: intentionality check (user has set a credential)
def is_available(self) -> bool:
    return bool(self._config.auth_token or self._config.api_key)
```

---

### CR-02: Implicit relative imports break production loading

**File:** `plugins/memory/ai-memory/__init__.py:5-6`

**Issue:** Lines 5-6 use bare module names for local imports:
```python
from config import AiMemoryConfig
from provider import AiMemoryProvider
```
In Python 3, these are implicit relative imports (deprecated and disabled in most contexts). When Hermes loads `plugins/memory/ai-memory/` as a package, Python looks for a top-level `config` or `provider` module on `sys.path` rather than in the package directory — which either fails with `ImportError` or, worse, imports a different `config` module from somewhere else on `sys.path`. Tests pass only because `conftest.py` inserts the directory into `sys.path` — a workaround that masks the bug.

**Fix:** Use explicit relative imports with the dot prefix:

```python
from .config import AiMemoryConfig
from .provider import AiMemoryProvider
```

This also applies to `client.py:7`, `provider.py:7-8`, and `cli.py:7-8` which import from sibling modules using bare names. Every local import should use dot-prefixed relative syntax.

---

### CR-03: Missing runtime dependency (`httpx`)

**File:** `pyproject.toml:6`

**Issue:** `[project] dependencies = []` is empty. The `httpx` package is listed only under `[tool.uv] dev-dependencies` (line 15), which is for development tooling only. When the plugin is installed via `pip install` or when Hermes resolves its `pip_dependencies` from `plugin.yaml`, httpx will NOT be installed, causing an `ImportError` at `from client import AiMemoryClient`.

The `plugin.yaml` declares `pip_dependencies: [httpx]` which suggests Hermes' plugin loader handles installation separately — but the project's own `pyproject.toml` should still declare the runtime dependency correctly for standalone use.

**Fix:** Add httpx to `[project] dependencies`:

```toml
[project]
dependencies = ["httpx>=0.28"]
```

---

### CR-04: `on_memory_write` propagates exceptions (convention violation)

**File:** `plugins/memory/ai-memory/provider.py:164-174`

**Issue:** Per project conventions (`AGENTS.md` line 69): *"Hook paths (sync_turn, on_session_end) swallow exceptions gracefully."* And line 70: *"Tool paths (search, write) propagate errors for user visibility."` The `on_memory_write` method is a hook path but does NOT wrap the `self._client.write_page()` call in a try/except. If the write fails (network error, server down), the exception propagates to Hermes' internal hook dispatcher, potentially crashing or corrupting the agent's turn.

Meanwhile, the sibling hook methods `sync_turn` (line 147) and `on_session_end` (line 162) correctly wrap in `except Exception: pass`.

**Fix:** Wrap the write call in a try/except consistent with other hooks:

```python
def on_memory_write(
    self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None
) -> None:
    if action in ("write", "append"):
        try:
            self._client.write_page(
                path=f"hermes-memory/{target}.md",
                body=content,
                tags=["hermes", "mirror"],
                workspace=self._config.workspace,
                project=self._config.project,
            )
        except Exception:
            log.exception("memory_write hook failed for target=%s", target)
```

---

### CR-05: Inconsistent config precedence between `register()` and `load_config()`

**File:** `plugins/memory/ai-memory/__init__.py:13-33` vs `plugins/memory/ai-memory/config.py:71-85`

**Issue:** The `register()` entry point applies env var overrides AFTER loading file values (lines 26-33), so env vars take precedence over file config. But `config.load_config()` uses `dict.setdefault` to assign env var values (line 81-83), which means file values take precedence over env vars. The two paths produce different final `server_url` / `auth_token` / `api_key` values given the same file + env inputs.

This means CLI commands (`hermes memory status`, `hermes memory config`) may show different effective configuration than what the running provider uses — a confusing and potentially dangerous mismatch.

```python
# __init__.py order (env wins):
#   1. Load config.json (file values)
#   2. Override from env vars → env wins

# load_config() order (file wins):
#   overrides.setdefault("server_url", os.environ.get(...))
#   → setdefault only applies when key NOT already in dict
#   → file values loaded first → file wins
```

**Fix:** Standardise on a single precedence rule — document it in AGENTS.md and implement it identically everywhere. The common convention is env > file > defaults. Update `load_config()`:

```python
def load_config(hermes_home: str) -> AiMemoryConfig:
    p = Path(hermes_home) / "ai-memory.json"
    overrides: dict[str, Any] = {}

    if p.exists():
        try:
            overrides = json.loads(p.read_text())
        except Exception:
            pass

    # Env vars override file values consistently
    env_map = {
        "server_url": "AI_MEMORY_SERVER_URL",
        "auth_token": "AI_MEMORY_AUTH_TOKEN",
        "api_key": "AI_MEMORY_API_KEY",
    }
    for attr, env_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            overrides[attr] = val

    # Defaults only fill in what's still missing
    overrides.setdefault("server_url", DEFAULT_SERVER_URL)

    return AiMemoryConfig(**{k: v for k, v in overrides.items() if hasattr(AiMemoryConfig, k)})
```

---

### CR-06: `plugin.yaml` missing `entry_point` and incomplete hook declarations

**File:** `plugins/memory/ai-memory/plugin.yaml`

**Issue:** Two problems with the manifest:

1. **Missing `entry_point`:** Standard Hermes plugin manifests specify the entry point file (e.g., `entry_point: __init__.py`) so the loader knows which module to import. Without it, the loader may fail to discover the `register()` function.

2. **Incomplete hook declarations:** Only `on_session_end` is listed under `hooks:`, but the provider also implements `initialize`, `prefetch`, `queue_prefetch`, `sync_turn`, `on_memory_write`, `get_tool_schemas`, `handle_tool_call`, `system_prompt_block`, and `shutdown`. If Hermes uses `plugin.yaml` hook declarations for discovery (rather than runtime introspection), the undeclared hooks will never fire.

**Fix:** Add entry_point and declare all implemented hooks:

```yaml
name: ai-memory
version: 0.1.0
description: "ai-memory wiki-backed long-term memory provider"
entry_point: __init__.py
pip_dependencies:
  - httpx
hooks:
  - on_session_end
  - sync_turn
  - on_memory_write
```

(Note: `initialize`, `prefetch`, `get_tool_schemas`, `handle_tool_call` etc. may be auto-discovered by the `MemoryProvider` ABC at registration time — check Hermes documentation to confirm which need explicit declaration.)

---

### CR-07: mypy excludes the entire plugin from type checking

**File:** `pyproject.toml:31`

**Issue:** `exclude = ["ai-memory"]` tells mypy to skip the `plugins/memory/ai-memory/` directory entirely. Combined with `ignore_missing_imports = True` (line 30), this means no plugin source code is ever type-checked — the primary quality gate for type safety is completely disabled for the code that matters most.

**Fix:** Remove the blanket exclusion. If specific imports (e.g., `agent.memory_provider`) are unavailable in CI, handle those with `# type: ignore[import-untyped]` on specific lines (as `provider.py:11` already does) rather than excluding the entire directory.

```toml
[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true
exclude = []   # or remove the line entirely
```

---

## Warnings

### WR-01: Client creates new httpx.Client on every request (no connection pooling)

**File:** `plugins/memory/ai-memory/client.py:30-37`

**Issue:** The `_request` method creates a new `httpx.Client` for EACH HTTP call, then immediately tears it down. This means:
- No connection reuse (TCP handshake + TLS every time)
- No HTTP keep-alive
- Repeated socket overhead

The `_transport` attribute on `self` suggests the original intent was a persistent client, but it's only used for the mock transport path (testing). In production, every call goes through the `else` branch (line 35-37) which creates a fresh client.

**Fix:** Use a long-lived client instance:

```python
class AiMemoryClient:
    def __init__(self, config: AiMemoryConfig) -> None:
        self.config = config
        self._base = config.server_url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = config.auth_token or config.api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(headers=headers)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base}{path}"
        timeout = kwargs.pop("timeout", SEARCH_TIMEOUT)
        return self._client.request(method, url, timeout=timeout, **kwargs)
```

---

### WR-02: `cmd_status` uses private `_client` attribute

**File:** `plugins/memory/ai-memory/cli.py:28`

**Issue:** `provider._client.status()` accesses a private attribute (`_client`). If `AiMemoryProvider`'s internal naming changes, the CLI silently breaks. This is also a layering concern — the CLI should either go through a public API or have its own client instance.

**Fix:** Either expose a public `status()` method on `AiMemoryProvider`, or create a standalone client in the CLI:

```python
def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(args.hermes_home)
    client = AiMemoryClient(config)
    try:
        result = client.status()
        ...
```

---

### WR-03: `cmd_link` misleading "Already linked" message for actual directories

**File:** `plugins/memory/ai-memory/cli.py:50-52`

**Issue:** The condition `os.path.islink(str(target_dir)) or target_dir.exists()` means if someone manually created a regular directory at the target path, the code prints `"Already linked: {target_dir} -> {PLUGIN_DIR}"` — which is false (it's a directory, not a symlink to PLUGIN_DIR). This masks a potential misconfiguration.

**Fix:** Distinguish the two cases:

```python
if target_dir.exists():
    if os.path.islink(str(target_dir)):
        print(f"Already linked: {target_dir} -> {PLUGIN_DIR}")
    else:
        print(f"Target exists but is not a symlink: {target_dir}")
    return
```

---

### WR-04: `cmd_link` dead `FileExistsError` handler

**File:** `plugins/memory/ai-memory/cli.py:57-58`

**Issue:** `FileExistsError` is a subclass of `OSError`. The `except FileExistsError` block on lines 57-58 is unreachable because lines 59-60 (`except OSError`) catches it first. In Python, `except` clauses are checked in order, and OSError matches FileExistsError.

**Fix:** Remove the dead handler:

```python
try:
    os.symlink(str(PLUGIN_DIR), str(target_dir), target_is_directory=True)
    print(f"Linked: {target_dir} -> {PLUGIN_DIR}")
except OSError as e:
    print(f"Failed to link: {e}")
```

Alternatively, order the handlers correctly (specific before general):

```python
try:
    os.symlink(str(PLUGIN_DIR), str(target_dir), target_is_directory=True)
    print(f"Linked: {target_dir} -> {PLUGIN_DIR}")
except FileExistsError:
    print(f"Already linked: {target_dir}")
except OSError as e:
    print(f"Failed to link: {e}")
```

---

### WR-05: Daemon threads access `self._config` without lock (potential data race)

**File:** `plugins/memory/ai-memory/provider.py:134-162`

**Issue:** The `sync_turn` and `on_session_end` methods spawn daemon threads that read `self._config.workspace` and `self._config.project`. While `self._client` is reassigned under `self._lock` in `initialize()`, the daemon threads hold a reference to whichever `self._client` existed when the thread started — but they read `self._config` attributes lazily when the thread actually executes. If `initialize()` is called again (e.g., during a session restart), the daemon threads from the previous session may read stale or concurrently-mutated config values.

In practice, Hermes calls `initialize()` once at session start before any daemon threads spawn, so the race is unlikely. But it's a latent correctness issue.

**Fix:** Capture the config values at thread creation time to avoid lazy reads:

```python
def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
    sid = session_id or self.session_id
    ws = self._config.workspace
    proj = self._config.project

    def _do() -> None:
        try:
            self._client.send_hook(
                event="user-prompt",
                session_id=sid,
                payload={"user": user, "assistant": assistant},
                workspace=ws,
                project=proj,
            )
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()
```

---

### WR-06: Bare `except Exception: pass` in `__init__.py` (violates conventions)

**File:** `plugins/memory/ai-memory/__init__.py:23-24`

**Issue:** The `except Exception: pass` clause on line 23 swallows ALL exceptions from JSON parsing, including `json.JSONDecodeError`, `PermissionError`, `IOError`, etc. While functional for resilience, the project conventions (AGENTS.md line 68) say *"Explicit exception types, never bare except:"*.

**Fix:** Catch specific exceptions:

```python
try:
    with open(config_path) as f:
        overrides = json.load(f)
    for key in ("server_url", "api_key", "auth_token", "workspace", "project"):
        if key in overrides:
            setattr(config, key, overrides[key])
except (json.JSONDecodeError, OSError):
    pass
```

---

### WR-07: `_request` merges headers via mutation, losing caller-supplied headers

**File:** `plugins/memory/ai-memory/client.py:27-28`

**Issue:** `headers = {**self._headers, **kwargs.pop("headers", {})}` works correctly but the pop-from-kwargs pattern is fragile. If the caller of `_request` passes `headers` in kwargs AND also has `headers` in kwarg defaults from a parent call, the pop could silently consume the wrong key.

More concretely, `search()` calls `_request("GET", "/admin/search", params=params, timeout=SEARCH_TIMEOUT)` — no `headers` kwarg, so this is safe. But the pattern is precedent for future callers to get wrong.

**Fix:** Use the `.get()` approach instead of `.pop()` to avoid side effects:

```python
def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
    url = f"{self._base}{path}"
    extra_headers = kwargs.pop("headers", {})
    headers = {**self._headers, **extra_headers}
    ...
```

---

### WR-08: No test verifies `sync_turn` / `on_session_end` actually calls `send_hook`

**File:** `tests/test_provider.py:123-146`

**Issue:** The tests `test_sync_turn_spawns_daemon` and `test_on_session_end_spawns_daemon` do not verify that `send_hook` was actually called — they mock it and then assert `True`. This means a regression where `send_hook` silently stops being called would pass the test suite.

**Fix:** Add a small sleep + verify pattern (or move to an inline synchronous helper for testing):

```python
def test_sync_turn_calls_send_hook(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.sync_turn("user msg", "assistant msg", session_id="sess-1")
    time.sleep(0.05)  # allow daemon thread to execute
    provider._client.send_hook.assert_called_once()
```

---

## Info Items

### IN-01: Missing `__all__` in `__init__.py`

**File:** `plugins/memory/ai-memory/__init__.py`

The entry point only exports `register()` implicitly. Adding `__all__ = ["register"]` clarifies the public API and enables tooling.

---

### IN-02: `conftest.py` uses fragile `sys.path.insert` approach

**File:** `tests/conftest.py:11-14`

Inserting into `sys.path` makes tests dependent on cwd and the conftest running first. Consider using `PYTHONPATH` or a `pytest --rootdir` configuration, or restructure as a proper installable package and use `pip install -e .` in dev.

---

### IN-03: `test_is_available_without_token` masks the `is_available()` bug

**File:** `tests/test_provider.py:31-33`

The test asserts `is_available()` returns True with only defaults — which is the bug. Once CR-01 is fixed, this test must be updated.

---

### IN-04: Missing edge-case tests

Several uncovered edge cases should be added:

- `test_client.py`: What happens when `search()` returns non-dict JSON (e.g., a list)?
- `test_provider.py`: What happens when `_search()` receives empty query string?
- `test_config.py`: What happens when both env var AND file are set (precedence test)?
- `test_entry.py`: What happens when `HERMES_HOME` is not set?

---

### IN-05: `QueuePrefetch` test is a no-op

**File:** `tests/test_provider.py:167-170`

`test_queue_prefetch` mocks `prefetch` after construction but only asserts `True`. Since `queue_prefetch` spawns a thread, the test doesn't verify the thread starts or calls prefetch. Consider testing that `threading.Thread` is called, or verify prefetch is invoked.

---

### IN-06: `_write()` defaults `result.get("ok", True)` — masks API errors

**File:** `plugins/memory/ai-memory/provider.py:198`

```python
if not result.get("ok", True):
```

The `True` default means if the API response doesn't include an `"ok"` field, the write is treated as successful. This could mask a silent failure. Consider `result.get("ok", False)` so only explicit success is treated as success.

---

## Files Not Reviewed (detail)

The following files exist but were out of scope for source-code review:

| File | Reason |
|---|---|
| `uv.lock` | Auto-generated lockfile |
| `.gitignore` | Project boilerplate |
| `AGENTS.md` | Already inspected for conventions |
| `HERMES_MEMORY_PLUGIN_AI-MEMORY.md` | Research/pre-planning doc (still references old `3113` port, `urllib` approach — superseded by implementation) |
| `README.md` | Top-level project readme |
| `plugins/memory/ai-memory/README.md` | Plugin setup readme |
| `.planning/` | Planning artifacts, not shipped |
| `docs/` | Documentation |

---

## Overall Assessment

**Recommendation: MAJOR REVISIONS REQUIRED before shipping v0.1.0.**

The project has a clean architecture and good test structure, but it ships with 7 critical issues that affect correctness in production:

| Priority | Count | Key concerns |
|---|---|---|
| **Critical** | 7 | `is_available()` tautology, broken imports (no relative dot), missing httpx dependency, uncaught hook exception, inconsistent precedence, incomplete plugin manifest, disabled mypy |
| **Warning** | 8 | No connection pooling, private attr access, misleading CLI messages, dead code, potential data race, convention violations |
| **Info** | 6 | Missing `__all__`, missing edge-case tests, fragile test setup |

**Top 3 actions to fix first:**
1. Convert all local imports to explicit relative (`from .foo import Bar`) — blocks production loading
2. Add `httpx>=0.28` to `[project] dependencies` in `pyproject.toml` — blocks runtime
3. Fix `is_available()` — provider health check is currently useless

After these, address the config precedence inconsistency (CR-05), the `on_memory_write` exception swallowing (CR-04), and the `plugin.yaml` completeness (CR-06) before any release.

---

_Reviewed: 2026-07-03T12:00:00Z_
_Reviewer: gsd-code-reviewer (deep)_
_Depth: deep (cross-file analysis)_
