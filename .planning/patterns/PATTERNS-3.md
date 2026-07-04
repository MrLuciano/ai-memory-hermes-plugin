# Phase 3: Provider — Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 5 (provider.py, client.py, config.py, __init__.py, test_provider.py, conftest.py)
**Analogs found:** 5 / 5

**Source of truth:** Actual `agent/memory_provider.py` from Hermes Agent main branch (fetched 2026-07-03)

## File Classification

| File | Role | Data Flow | Closest Analog | Match Quality |
|------|------|-----------|----------------|---------------|
| `plugins/memory/ai-memory/provider.py` | provider | CRUD + event-driven | `agent.memory_provider.MemoryProvider` (Hermes ABC) | spec-match |
| `tests/test_provider.py` | test | CRUD + event-driven | `test_client.py` (same-project, same patterns) | project-match |
| `tests/conftest.py` | test-utility | config | itself (fixture container) | self |
| `plugins/memory/ai-memory/__init__.py` | entry-point | n/a | `provider.py` (same package) | package-match |

---

## Hermes `MemoryProvider` ABC — Full Interface Reference

**Source:** `agent/memory_provider.py` (Hermes Agent, main branch)

This is the canonical interface `AiMemoryProvider` must implement. Below is the complete ABC for reference, annotated with whether Phase 2's `AiMemoryProvider` already matches.

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MemoryProvider(ABC):
    """Abstract base class for memory providers."""

    # ── Identity ────────────────────────────────────────────────────────
    @property
    @abstractmethod
    def name(self) -> str:                                       # ✅ Already implemented
        ...

    # ── Core lifecycle (abstract — MUST implement) ─────────────────────
    @abstractmethod
    def is_available(self) -> bool:                              # ✅ Already implemented
        ...

    @abstractmethod
    def initialize(self, session_id: str, **kwargs) -> None:      # ✅ Signature matches
        ...

    @abstractmethod
    def get_tool_schemas(self) -> List[Dict[str, Any]]:           # ✅ Already implemented
        ...

    # ── Core lifecycle (optional with defaults) ──────────────────────────
    def system_prompt_block(self) -> str:                        # ✅ Already implemented
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:      # ❌ Returns str|None instead of str
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:  # ❌ Missing session_id param
        ...

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,         # ❌ Missing messages param
    ) -> None:
        ...

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:  # ❌ Returns Any, not str
        raise NotImplementedError(...)

    def shutdown(self) -> None:                                 # ✅ No-op already matches
        ...

    # ── Optional hooks ──────────────────────────────────────────────────
    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:    # ✅ Signature matches
        ...

    def on_memory_write(                                          # ⚠️ Missing metadata param
        self, action: str, target: str, content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...

    def get_config_schema(self) -> List[Dict[str, Any]]:         # ✅ Already implemented
        return []

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:  # ✅ Already implemented
        ...

    def on_turn_start(self, ...) -> None:                        # 🟡 Not implemented — optional
    def on_session_switch(self, ...) -> None:                     # 🟡 Not implemented — optional
    def on_pre_compress(self, ...) -> str:                       # 🟡 Not implemented — optional
    def on_delegation(self, ...) -> None:                         # 🟡 Not implemented — optional
    def backup_paths(self) -> List[str]:                         # 🟡 Not implemented — optional
```

---

## PRO Requirement Analysis Against Current Provider

### PRO-01: AiMemoryProvider implements MemoryProvider ABC

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Inheritance | `class AiMemoryProvider:` | `class AiMemoryProvider(MemoryProvider):` | ❌ **CRITICAL** — no base class |
| Import path | None | `from agent.memory_provider import MemoryProvider` | ❌ **CRITICAL** — no import |
| Abstract methods | 4 non-abstract versions exist | Must satisfy 4 `@abstractmethod` defs | ✅ Already satisfies (name, is_available, initialize, get_tool_schemas) |

**Detail:** The current class stands alone — it does NOT inherit from the ABC. Adding `(MemoryProvider)` to the class definition and `from agent.memory_provider import MemoryProvider` to the import block satisfies PRO-01. All 4 abstract methods (`name`, `is_available`, `initialize`, `get_tool_schemas`) already exist with matching signatures.

**⚠️ Import availability risk:** `agent.memory_provider` is NOT available at test time (Hermes Agent not installed as a dev dependency). The conftest.py `sys.path.insert` only adds the plugin directory, not Hermes packages. Three resolution strategies:

1. **Add `hermes-agent` as dev dependency in `pyproject.toml`** — most straightforward, but may pull in many transitive deps
2. **Conditional import with fallback mock** — `try: from agent.memory_provider import MemoryProvider; except ImportError: MemoryProvider = object`
3. **Keep ABC inheritance conditional or as a Protocol** — less safe, defeats static checking

**Recommendation:** Strategy 2 (conditional import) — keeps tests hermetic and the plugin self-contained. The conditional import is a single `try/except` block at the top of `provider.py`.

---

### PRO-02: initialize() resolves workspace and project from kwargs

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Session ID | `session_id` from arg | from arg | ✅ |
| hermes_home | From `kwargs.get("hermes_home")` | From kwargs | ✅ |
| server_url | From `kwargs.get("ai_memory_server_url")` | — | ✅ (extra) |
| auth_token | From `kwargs.get("ai_memory_auth_token")` | — | ✅ (extra) |
| profile | From `kwargs.get("profile", "default")` → sets `project` | — | ✅ (extra) |
| **workspace** | **Never resolved from kwargs** | Must resolve from kwargs | ❌ **GAP** |
| **project** | Derived from `profile` kwarg | Must fall back to config | ⚠️ Partial — sets via profile but not from explicit `project` kwarg |

**Current code (provider.py lines 33–54):**
```python
def initialize(self, session_id: str, **kwargs: Any) -> None:
    self.session_id = session_id
    hermes_home = kwargs.get("hermes_home", "")
    self._hermes_home = hermes_home

    with self._lock:
        if hermes_home:
            self._config = load_config(hermes_home)
            self._client = AiMemoryClient(self._config)

        server_url = kwargs.get("ai_memory_server_url", "")
        if server_url:
            self._config.server_url = server_url

        auth_token = kwargs.get("ai_memory_auth_token", "")
        if auth_token:
            self._config.auth_token = auth_token

        profile = kwargs.get("profile", "default")
        self._config.project = f"hermes-{profile}"

        self._client = AiMemoryClient(self._config)
```

**Issues:**
1. `workspace` is never resolved from kwargs — PRO-02 says "resolves workspace and project from kwargs, falls back to config"
2. `project` is always overwritten as `f"hermes-{profile}"` — even if config already has a project set from JSON file. The profile-based scheme should be a fallback, not a hard override.
3. `self._client = AiMemoryClient(self._config)` is called twice with the same config (line 41 inside `if hermes_home:` block, then line 54 unconditionally) — redundant.

**Recommended pattern:**
```python
def initialize(self, session_id: str, **kwargs: Any) -> None:
    self.session_id = session_id
    hermes_home = kwargs.get("hermes_home", "")
    self._hermes_home = hermes_home

    with self._lock:
        if hermes_home:
            self._config = load_config(hermes_home)

        # Apply kwargs overrides
        server_url = kwargs.get("ai_memory_server_url", "")
        if server_url:
            self._config.server_url = server_url

        auth_token = kwargs.get("ai_memory_auth_token", "")
        if auth_token:
            self._config.auth_token = auth_token

        # Resolve workspace from kwargs, fall back to config
        if "ai_memory_workspace" in kwargs:
            self._config.workspace = kwargs["ai_memory_workspace"]
        # Resolve project from kwargs, fall back to profile-derived
        if "ai_memory_project" in kwargs:
            self._config.project = kwargs["ai_memory_project"]
        else:
            profile = kwargs.get("profile", "default")
            self._config.project = f"hermes-{profile}"

        self._client = AiMemoryClient(self._config)
```

---

### PRO-03: prefetch() calls client.search() and returns concatenated snippets

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Calls `client.search()` | ✅ Yes | Yes | ✅ |
| Returns concatenated snippets | ✅ Yes | Yes | ✅ |
| Returns `None` on no results | Returns `None` | Should return `""` | ❌ **MISMATCH with ABC** |
| Return type | `str \| None` | `str` | ❌ **MISMATCH with ABC** |

**Current code (provider.py lines 108–112):**
```python
def prefetch(self, query: str, *, session_id: str = "") -> str | None:
    results = self._search({"query": query, "max_results": 3})
    if results.get("ok") and results.get("results"):
        return "\n\n".join(r.get("snippet", "") for r in results["results"])
    return None
```

**The ABC defines `prefetch() -> str` and returns `""` (empty string) by default.** The current `-> str | None` return is a **runtime risk** — if Hermes calls `.strip()` or `.join()` on the result, `None` crashes. Must return `""` instead.

**Fixed pattern:**
```python
def prefetch(self, query: str, *, session_id: str = "") -> str:
    results = self._search({"query": query, "max_results": 3})
    if results.get("ok") and results.get("results"):
        return "\n\n".join(r.get("snippet", "") for r in results["results"])
    return ""
```

---

### PRO-04: sync_turn() spawns daemon thread calling client.send_hook()

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Daemon thread | ✅ Yes | Yes | ✅ |
| Calls `client.send_hook()` | ✅ Yes | Yes | ✅ |
| User/assistant in payload | ✅ Yes | Yes | ✅ |
| Swallows exceptions | ✅ `try/except: pass` | Yes (PRO-08) | ✅ |
| **Parameter names** | `user`, `assistant` | `user_content`, `assistant_content` | ⚠️ Compatible (not abstract) |
| **Missing `messages` param** | **Not accepted** | ABC has `messages=None` | ❌ **Runtime risk if Hermes passes it** |

**Current code (provider.py lines 117–130):**
```python
def sync_turn(self, user: str, assistant: str, *, session_id: str = "") -> None:
    ...
```

**The ABC signature is:**
```python
def sync_turn(
    self,
    user_content: str,
    assistant_content: str,
    *,
    session_id: str = "",
    messages: Optional[List[Dict[str, Any]]] = None,
) -> None:
```

**Risk:** The `sync_turn` method is NOT abstract in the ABC (it has a default no-op body). However, if Hermes calls `provider.sync_turn(user_content="...", assistant_content="...", messages=[...])`, our current signature would raise `TypeError: sync_turn() got an unexpected keyword argument 'messages'`.

**Two fix options:**
1. **Add `**kwargs` to signature** — absorb all extra kwargs silently (simplest, backward-compatible)
2. **Match ABC signature exactly** — rename params and add `messages=None`

**Recommendation: Option 1** — add `**kwargs: Any` to the end of the signature. This absorbs any future ABC additions without changing param names (which would break existing callers):

```python
def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
```

---

### PRO-05: on_session_end() spawns daemon thread sending session-end event

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Daemon thread | ✅ Yes | Yes | ✅ |
| Calls `client.send_hook()` | ✅ Yes | Yes | ✅ |
| Sends session-end event | ✅ Yes | Yes | ✅ |
| Swallows exceptions | ✅ Yes | Yes (PRO-08) | ✅ |
| Signature | `(self, messages)` | `(self, messages)` | ✅ Matches ABC |
| **Extra `context` kwarg per spec** | **Not accepted** | Spec says `(messages, context)` | ⚠️ Add `**kwargs` to be safe |

**Current code (provider.py lines 132–145):**
```python
def on_session_end(self, messages: list[dict[str, Any]]) -> None:
    ...
```

PRO-05 spec says `on_session_end(messages, context)`. The ABC says `on_session_end(self, messages)`. The spec's `context` param is not in the real ABC — so it's safe to match the ABC: no `context` needed unless Hermes adds it. Adding `**kwargs: Any` for future-proofing is recommended:

```python
def on_session_end(self, messages: list[dict[str, Any]], **kwargs: Any) -> None:
    ...
```

---

### PRO-06: get_tool_schemas() returns tool definitions

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Method exists | ✅ Yes | Yes | ✅ |
| Returns 3 tool schemas | ✅ Yes | Yes | ✅ |
| Contains search/write/status | ✅ Yes | Yes | ✅ |
| ABC is abstract | ✅ Implemented | Abstract | ✅ Meets requirement |

**No changes needed** — already satisfied.

---

### PRO-07: handle_tool_call() routes to correct client method

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| Method exists | ✅ Yes | Yes | ✅ |
| Routes by tool_name | ✅ Yes | Yes | ✅ |
| Returns structured results | ✅ dict[str, Any] | "returns result" | ✅ |
| **ABC return type** | `-> Any` | `-> str` (JSON string) | ⚠️ Should return JSON string |
| **ABC signature** | `(self, tool_name, args, **kwargs)` | `(self, tool_name, args, **kwargs)` | ✅ Signature matches |

**Current code (provider.py lines 96–103):**
```python
def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> Any:
    if tool_name == "ai_memory_search":
        return self._search(args)
    if tool_name == "ai_memory_write":
        return self._write(args)
    if tool_name == "ai_memory_status":
        return self._status()
    raise ValueError(f"Unknown tool: {tool_name}")
```

**ABC signature:** `def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:`

The ABC says `-> str` (return a JSON string). Our implementation returns `dict[str, Any]`. Since `dict` can be JSON-serialized, this is compatible at runtime — Hermes may serialize the dict itself or expect a string. The safest fix is to `json.dumps()` the return value.

**Recommended fix:**
```python
def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
    if tool_name == "ai_memory_search":
        return json.dumps(self._search(args))
    if tool_name == "ai_memory_write":
        return json.dumps(self._write(args))
    if tool_name == "ai_memory_status":
        return json.dumps(self._status())
    raise ValueError(f"Unknown tool: {tool_name}")
```

---

### PRO-08: Hook paths swallow exceptions gracefully

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| `sync_turn` swallows | ✅ `try/except: pass` | Yes | ✅ |
| `on_session_end` swallows | ✅ `try/except: pass` | Yes | ✅ |
| Daemon threads used | ✅ Yes | Yes | ✅ |

**No changes needed** — already satisfied. Best-practice pattern is shown below:

```python
def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
    def _do() -> None:
        try:
            self._client.send_hook(
                event="user-prompt",
                session_id=session_id or self.session_id,
                payload={"user": user, "assistant": assistant},
                workspace=self._config.workspace,
                project=self._config.project,
            )
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()
```

---

### PRO-09: Tool paths propagate exceptions

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| `handle_tool_call` propagates | ✅ No try/except | Yes | ✅ |
| `prefetch` propagates | ✅ No try/except | Yes | ✅ |
| `_search` propagates | ✅ Calls client.search() which raises | Yes (Phase 2 change) | ✅ |
| `_write` propagates | ✅ Calls client.write_page() which raises | Yes (Phase 2 change) | ✅ |
| `_status` propagates | ✅ Calls client.status() which raises | Yes (Phase 2 change) | ✅ |

**Note:** `prefetch()` propagates through `_search()` calling `client.search()` (which now raises after Phase 2 CLI-08 fix). The daemon thread in `queue_prefetch` wraps `prefetch` but has NO error handling — exceptions crash the thread silently. This is **acceptable** per PRO-09 (tool paths propagate) since `queue_prefetch` is best-effort background prefetch.

**No changes needed** — already satisfied.

---

## Test Coverage Gap Analysis

### Current test_provider.py coverage (18 tests)

| Test | Line | Validates | Gap |
|------|------|-----------|-----|
| `test_provider_name` | 22 | `provider.name == "ai-memory"` | ✅ |
| `test_is_available_with_token` | 26 | With auth_token → True | ✅ |
| `test_is_available_without_token` | 30 | Default config → True | ✅ |
| `test_initialize_sets_session_id` | 35 | Session ID + project from profile | ⚠️ Doesn't test workspace resolution |
| `test_get_config_schema` | 41 | Schema has >= 4 fields | ✅ |
| `test_save_config` | 46 | Delegates to config module | ✅ |
| `test_get_tool_schemas` | 53 | 3 tool names present | ✅ |
| `test_handle_tool_call_search` | 61 | Routes search | ✅ |
| `test_handle_tool_call_write` | 68 | Routes write | ✅ |
| `test_handle_tool_call_status` | 78 | Routes status | ✅ |
| `test_handle_tool_call_unknown` | 84 | Raises ValueError | ✅ |
| `test_system_prompt_block` | 89 | Contains "ai-memory" | ✅ |
| `test_prefetch_returns_context` | 94 | Returns snippets | ⚠️ Must change `assert result is not None` → `assert result != ""` |
| `test_prefetch_returns_none_on_no_results` | 108 | Returns None | ❌ **Must change to empty string** `assert result == ""` |
| `test_sync_turn_spawns_daemon` | 114 | No crash | ⚠️ Weak — just asserts `True` |
| `test_on_session_end_spawns_daemon` | 120 | No crash | ⚠️ Weak — just asserts `True` |
| `test_on_memory_write_calls_client` | 126 | Calls client on write action | ✅ |
| `test_on_memory_write_skips_other_actions` | 132 | Skips delete action | ✅ |
| `test_queue_prefetch` | 138 | No crash | ⚠️ Weak — just asserts `True` |

### Missing test coverage for PRO-xx

| PRO | Missing test | Why needed |
|-----|-------------|------------|
| **PRO-01** | `test_provider_inherits_from_memory_provider` | Verifies ABC inheritance — but requires `MemoryProvider` import; test may need conditional skip |
| **PRO-02** | `test_initialize_resolves_workspace_from_kwargs` | Validates workspace kwarg is applied |
| **PRO-02** | `test_initialize_resolves_project_from_kwargs` | Validates project kwarg takes priority over profile |
| **PRO-02** | `test_initialize_falls_back_to_config` | Validates config defaults when kwargs absent |
| **PRO-03** | `test_prefetch_returns_empty_string_on_no_results` | Replaces `test_prefetch_returns_none_on_no_results` |
| **PRO-03** | `test_prefetch_accepts_session_id` | Validates `session_id` kwarg accepted |
| **PRO-03** | `test_prefetch_propagates_client_errors` | Validates PRO-09: errors propagate |
| **PRO-04** | `test_sync_turn_spawns_daemon_thread` | Verify `Thread(daemon=True)` is actually set (not just non-blocking) |
| **PRO-04** | `test_sync_turn_accepts_messages_kwarg` | Validates `**kwargs` absorbs extra params |
| **PRO-05** | `test_on_session_end_accepts_extra_kwargs` | Validates `**kwargs` absorption |
| **PRO-05** | `test_on_session_end_spawns_daemon_thread` | Verify daemon=True |
| **PRO-08** | `test_sync_turn_swallows_exceptions` | Verify hook doesn't crash on error |
| **PRO-08** | `test_on_session_end_swallows_exceptions` | Verify hook doesn't crash on error |
| **PRO-09** | `test_handle_tool_call_propagates_client_error` | Verify tool path raises, not swallows |
| **PRO-09** | `test_prefetch_propagates_search_error` | Verify prefetch raises on client error |

### Thread verification pattern (for PRO-04, PRO-05, PRO-08)

Current tests use weak `assert True` assertions. Better pattern using `threading.Event`:

```python
def test_sync_turn_spawns_daemon_thread(provider: AiMemoryProvider) -> None:
    """Verify sync_turn spawns a daemon thread, not a blocking call."""
    import time
    provider._client.send_hook = MagicMock(side_effect=lambda *a, **kw: time.sleep(0.5))
    start = time.monotonic()
    provider.sync_turn("user msg", "assistant msg", session_id="sess-1")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # Returns immediately (daemon thread spawned)
```

For exception swallowing:
```python
def test_sync_turn_swallows_exceptions(provider: AiMemoryProvider) -> None:
    """Hook paths must never crash the agent."""
    provider._client.send_hook = MagicMock(side_effect=RuntimeError("boom"))
    # Must not raise, even though the client raises
    provider.sync_turn("user", "assistant", session_id="sess-1")
    # Give daemon thread time to execute
    import time
    time.sleep(0.05)
```

---

## All Method Signature Gaps (Provider vs ABC)

| Method | Current Signature | ABC Signature | Impact |
|--------|-------------------|---------------|--------|
| `prefetch` | `(query, *, session_id="") -> str \| None` | `(query, *, session_id="") -> str` | ⚠️ Runtime crash if Hermes expects str |
| `queue_prefetch` | `(query)` | `(query, *, session_id="")` | ⚠️ TypeError if Hermes passes session_id |
| `sync_turn` | `(user, assistant, *, session_id="")` | `(user_content, assistant_content, *, session_id="", messages=None)` | ⚠️ TypeError if Hermes passes `messages=` |
| `handle_tool_call` | `(tool_name, args, **kwargs) -> Any` | `(tool_name, args, **kwargs) -> str` | ⚠️ Hermes may expect JSON string |
| `on_memory_write` | `(action, target, content)` | `(action, target, content, metadata=None)` | ✅ Compatible (optional hook, no crash) |

**All 4 mismatches are fixable by:**
1. Changing `return None` → `return ""` in `prefetch`
2. Adding `**kwargs: Any` to `queue_prefetch`, `sync_turn`, `on_session_end`
3. Adding `import json` and JSON-serializing the return of `handle_tool_call`

---

## conftest.py: Reusable Fixtures for Phase 3

Current fixtures in `conftest.py` (lines 1–87):

```python
# sys.path injection — makes `from provider import AiMemoryProvider` work
sys.path.insert(0, str(Path(__file__).parent.parent / "plugins/memory/ai-memory"))

@pytest.fixture
def config() -> AiMemoryConfig:
    return AiMemoryConfig(server_url="http://localhost:49374", auth_token="test-token",
                          workspace="hermes", project="hermes-test")

@pytest.fixture
def provider(config: AiMemoryConfig) -> AiMemoryProvider:
    return AiMemoryProvider(config=config)

@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/admin/search" in request.url.path:
            return httpx.Response(200, json={"results": [...]})
        ...
    return httpx.MockTransport(handler)

@pytest.fixture
def mock_client(config, mock_transport) -> AiMemoryClient:
    client = AiMemoryClient(config)
    client._transport = mock_transport
    return client
```

**What the fixture set provides:**
- `config` — pre-configured `AiMemoryConfig` with `workspace="hermes"` and `project="hermes-test"`
- `provider` — `AiMemoryProvider` with **real client** (no transport) — client will raise `ConnectError` if actually called
- `mock_transport` — canned HTTP responses for client-level testing
- `mock_client` — client with `_transport` injected — used for client unit tests

**For provider tests that need a working client**, tests currently mock `provider._client.search` or `provider._search` with `MagicMock`. This pattern is sufficient for Phase 3:

```python
# Mock at the _search level (tests prefetch logic, not HTTP)
provider._search = MagicMock(return_value={"ok": True, "results": [...]})

# Mock at the client level (tests handle_tool_call routing)
provider._client.search = MagicMock(return_value=[{"path": "test.md"}])
```

---

## Shared Patterns

### Thread safety: threading.Lock

**Source:** `provider.py` lines 18, 38

```python
self._lock = threading.Lock()
...
with self._lock:
    # mutable state changes
```

The lock protects `_config` and `_client` mutations in `initialize()`. No other provider methods use the lock — all other state reads are effectively single-threaded (Hermes calls lifecycle hooks sequentially per session).

### Daemon thread pattern for hook paths

**Source:** `provider.py` lines 117–145

```python
def sync_turn(self, ...) -> None:
    def _do() -> None:
        try:
            self._client.send_hook(...)
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()
```

All hook methods use this same structure: wrap the actual work in a nested `_do()` function, `try/except: pass` around the client call, and spawn as `daemon=True`. This ensures the agent never blocks on hook writes and never crashes due to hook failures.

### Private underscore methods for tool dispatch

**Source:** `provider.py` lines 160–184

```python
def _search(self, args: dict[str, Any]) -> dict[str, Any]: ...
def _write(self, args: dict[str, Any]) -> dict[str, Any]: ...
def _status(self) -> dict[str, Any]: ...
```

Tool implementation is split into private methods (`_search`, `_write`, `_status`) following the Hermes research doc pattern. These wrap `AiMemoryClient` methods and add result normalization. Public methods call these — `handle_tool_call` dispatches to them, `prefetch` also calls `_search`.

### MagicMock injection for unit tests

**Source:** `test_provider.py` lines 61–66, 94–101

```python
# Client-level mock
provider._client.search = MagicMock(return_value=[{"path": "test.md"}])

# Provider-level mock (bypasses client entirely)
provider._search = MagicMock(return_value={
    "ok": True,
    "results": [{"snippet": "context 1"}],
})
```

Two layering levels for test isolation. Client-level mocks verify the provider-client contract. Provider-level mocks skip the client altogether for pure-logic tests.

---

## Risk Assessment: Hermes ABC Integration

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **`agent.memory_provider` import unavailable at test time** | Tests can't instantiate provider | **High** | Conditional import: `try: from agent.memory_provider import MemoryProvider; except ImportError: MemoryProvider = object` |
| **ABC method signatures differ from assumed (this analysis)** | Additional rework | **Low** (verified against real ABC source) | Already checked against main branch — no surprises expected |
| **Hermes passes kwargs that current signatures reject** | TypeError at runtime | **Medium** | Add `**kwargs: Any` to all lifecycle hooks that may receive extra params |
| **`prefetch` returning `None` instead of `""`** | AttributeError in Hermes | **High** | Fix immediately: `return ""` instead of `return None` |
| **Daemon thread timing in tests** | Flaky CI | **Medium** | Use `time.sleep()` in tests, or avoid timing-sensitive assertions |
| **Mypy fails after adding `MemoryProvider` import** | Quality gate blocks | **High** | Conditional import gets `# type: ignore[unused-import]`; or add `hermes-agent` stubs |

### Recommended ABC integration strategy

**Step 1: Conditional, graceful import in `provider.py`:**
```python
from __future__ import annotations

import json
import threading
from typing import Any

try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    # Hermes Agent not installed (test environment, standalone mode)
    # Provide a minimal fallback for type checking
    from abc import ABC as _ABC

    class MemoryProvider(_ABC):  # type: ignore[no-redef]
        """Local fallback when Hermes is not installed."""
        ...
```

**Step 2: Inherit from `MemoryProvider`:**
```python
class AiMemoryProvider(MemoryProvider):
    ...
```

**Step 3: Fix all 4 signature mismatches** (from gap table above).

**Step 4: Update `pyproject.toml`** — remove `exclude = ["plugins/"]` from mypy config, or at minimum run mypy against the plugin directory explicitly with `mypy plugins/memory/ai-memory/ --ignore-missing-imports`.

---

## Phase 3 Implementation Pattern Summary

### File: `plugins/memory/ai-memory/provider.py`

**Changes needed:**
1. Add `from agent.memory_provider import MemoryProvider` (with conditional fallback)
2. Add `import json` for `handle_tool_call` return serialization
3. Change `class AiMemoryProvider:` to `class AiMemoryProvider(MemoryProvider):`
4. Fix `prefetch()` return: `return ""` instead of `return None`
5. Add `**kwargs: Any` to `sync_turn()` and `queue_prefetch()` signatures
6. Add workspace/project kwarg resolution to `initialize()`
7. Change `handle_tool_call()` return type to `str` and `json.dumps()` the result
8. Add `metadata=None` param to `on_memory_write()`
9. Remove redundant `self._client = AiMemoryClient(self._config)` call in `initialize()`

### File: `tests/test_provider.py`

**Changes needed:**
1. Update `test_prefetch_returns_none_on_no_results` → `test_prefetch_returns_empty_string_on_no_results` (`assert result == ""`)
2. Update `test_prefetch_returns_context` — change `assert result is not None` to `assert result != ""`
3. Add tests for PRO-02: workspace/project kwarg resolution
4. Add tests for PRO-08: exception swallowing in hook paths
5. Add tests for PRO-09: exception propagation in tool paths
6. Add `test_sync_turn_accepts_messages_kwarg` — verify no crash with extra kwargs
7. Strengthen daemon thread tests with timing assertions

### File: `tests/conftest.py`

**No changes needed** — existing `config`, `provider`, `mock_transport`, `mock_client` fixtures are sufficient.

---

## Pattern Assignments

### `plugins/memory/ai-memory/provider.py` (provider, CRUD + event-driven)

**Analog:** `agent/memory_provider.MemoryProvider` (Hermes ABC — fetched 2026-07-03)

**ABC import + conditional fallback pattern:**
```python
from __future__ import annotations

import json
import threading
from typing import Any

try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    from abc import ABC as MemoryProvider  # type: ignore[assignment, misc]
```

**Core class definition pattern:**
```python
class AiMemoryProvider(MemoryProvider):
    def __init__(
        self,
        client: AiMemoryClient | None = None,
        config: AiMemoryConfig | None = None,
    ) -> None:
        self._config = config or AiMemoryConfig()
        self._client = client or AiMemoryClient(self._config)
        self._lock = threading.Lock()
        self.session_id: str = ""
        self._hermes_home: str = ""
```

**Prefetch returning empty string (matches ABC):**
```python
def prefetch(self, query: str, *, session_id: str = "") -> str:
    results = self._search({"query": query, "max_results": 3})
    if results.get("ok") and results.get("results"):
        return "\n\n".join(r.get("snippet", "") for r in results["results"])
    return ""
```

**Handle tool call returning JSON string (matches ABC):**
```python
def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
    if tool_name == "ai_memory_search":
        return json.dumps(self._search(args))
    if tool_name == "ai_memory_write":
        return json.dumps(self._write(args))
    if tool_name == "ai_memory_status":
        return json.dumps(self._status())
    raise ValueError(f"Unknown tool: {tool_name}")
```

**Sync/queue with **kwargs (absorbs ABC extras):**
```python
def queue_prefetch(self, query: str, **kwargs: Any) -> None:
    threading.Thread(target=self.prefetch, args=(query,), daemon=True).start()

def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
    ...

def on_session_end(self, messages: list[dict[str, Any]], **kwargs: Any) -> None:
    ...
```

---

### `tests/test_provider.py` (test, CRUD + event-driven)

**Analog:** `tests/test_client.py` (same-project, same testing conventions)

**Import pattern:**
```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from config import AiMemoryConfig
from provider import AiMemoryProvider
```

**Test pattern — kwargs absorption:**
```python
def test_sync_turn_accepts_extra_kwargs(provider: AiMemoryProvider) -> None:
    """Must not crash when Hermes passes unexpected kwargs."""
    provider._client.send_hook = MagicMock()
    # Hermes may pass context, messages, etc.
    provider.sync_turn("user", "assistant", session_id="sess-1", messages=[], context="test")
    assert True
```

**Test pattern — exception swallowing:**
```python
def test_sync_turn_swallows_exceptions(provider: AiMemoryProvider) -> None:
    """Hook paths must never crash the agent (PRO-08)."""
    provider._client.send_hook = MagicMock(side_effect=RuntimeError("boom"))
    import time
    provider.sync_turn("user msg", "assistant msg", session_id="sess-1")
    time.sleep(0.05)  # Let daemon thread execute
```

**Test pattern — exception propagation:**
```python
def test_handle_tool_call_propagates_client_error(provider: AiMemoryProvider) -> None:
    """Tool paths must propagate exceptions (PRO-09)."""
    provider._client.search = MagicMock(side_effect=RuntimeError("search failed"))
    with pytest.raises(RuntimeError, match="search failed"):
        provider.handle_tool_call("ai_memory_search", {"query": "test"})
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `agent.memory_provider.MemoryProvider` | ABC | n/a | External dependency (Hermes Agent) — not in local codebase, fetched from GitHub |

All other files have close analogs within the codebase or are themselves the target. No external analogs needed beyond the Hermes ABC reference.

---

## Metadata

**Analog search scope:** `plugins/memory/ai-memory/`, `tests/`, and `agent/memory_provider.py` (Hermes Agent GitHub main branch)
**Files scanned:** 8 (provider.py, client.py, config.py, __init__.py, test_provider.py, test_client.py, conftest.py, memory_provider.py from Hermes)
**Pattern extraction date:** 2026-07-03
**Hermes ABC source:** `https://raw.githubusercontent.com/NousResearch/hermes-agent/main/agent/memory_provider.py` (vetted against main branch as of 2026-07-03)
