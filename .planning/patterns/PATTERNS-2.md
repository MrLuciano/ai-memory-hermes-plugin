# Phase 2: Client — Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 4 (client.py, test_client.py, conftest.py, provider.py)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `plugins/memory/ai-memory/client.py` | client | CRUD + event-driven | N/A (primary target) | self |
| `tests/test_client.py` | test | CRUD + event-driven | `test_provider.py` | project-match |
| `tests/conftest.py` | test-utility | config | itself (fixture container) | self |
| `plugins/memory/ai-memory/provider.py` | provider | CRUD + event-driven | (consumer of client.py) | dependency |

---

## Existing Patterns

### 1. `_request` internal transport pattern (client.py lines 26–37)

```python
def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
    url = f"{self._base}{path}"
    headers = {**self._headers, **kwargs.pop("headers", {})}
    if self._transport:
        with httpx.Client(
            transport=self._transport,
            timeout=kwargs.pop("timeout", SEARCH_TIMEOUT),
        ) as c:
            return c.request(method, url, headers=headers, **kwargs)
    timeout = kwargs.pop("timeout", SEARCH_TIMEOUT)
    with httpx.Client(timeout=timeout) as c:
        return c.request(method, url, headers=headers, **kwargs)
```

Key observations:
- `_transport: Any = None` is set as an instance attribute (line 24) — allows test injection of `httpx.MockTransport`
- The `_request` method normalizes URL (`self._base + path`), merges headers, and creates a per-call `httpx.Client`
- Timeout default is `SEARCH_TIMEOUT` (10s) — **every** method either passes explicit timeout or inherits 10s
- `kwargs.pop("timeout", SEARCH_TIMEOUT)` is called in BOTH branches — this is correct (first pop consumes it, second is unreachable when `self._transport` is set) but the duplication is a minor DRY opportunity
- No error handling in `_request` itself — all error handling is in the public methods wrapping it

### 2. Per-method error handling pattern (client.py lines 51–141)

Every public method follows this structure:
```
try:
    r = self._request(method, path, ...)
    r.raise_for_status()
    # parse and return
except Exception:
    log.exception("<method> failed")
    return <fallback value>
```

| Method | Fallback on error | CLI-08 compliance? |
|--------|-------------------|--------------------|
| `search()` | returns `[]` | ❌ Should propagate |
| `write_page()` | returns `{"ok": False, "error": "write failed"}` | ❌ Should propagate |
| `status()` | returns `{"ok": False, "error": "status failed"}` | ❌ Should propagate |
| `send_hook()` | returns `None` (no return value, just logs) | ✅ CLI-07: swallow expected |
| `fetch_handoff()` | returns `None` (except 404 which is intentional) | ❌ Should propagate |

### 3. Auth header construction (client.py lines 20–23)

```python
self._headers: dict[str, str] = {"Content-Type": "application/json"}
token = config.auth_token or config.api_key
if token:
    self._headers["Authorization"] = f"Bearer {token}"
```

- Uses `auth_token` first, falls back to `api_key` — never both
- Stored as instance dict `self._headers`, merged by `_request` per-call
- No token → no `Authorization` header at all (tested by `test_client_no_auth_header_when_no_token`)

### 4. MockTransport test injection pattern (conftest.py lines 36–68 / test_client.py)

```python
# conftest.py — shared fixture
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

Test-writing pattern:
```python
def test_method(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert <assertion about request>
        return httpx.Response(200, json=<expected>)
    client._transport = httpx.MockTransport(handler)
    result = client.method(...)
    assert <assertion about result>
```

Two styles coexist:
1. **Inline handler** (test_client.py, 11 of 12 tests) — per-test `def handler(...)` to assert on request details
2. **Shared handler** (conftest.py `mock_transport`) — centralized routing for provider tests that don't need request inspection

### 5. Timeout constants (client.py lines 11–13)

```python
SEARCH_TIMEOUT = 10.0
HOOK_TIMEOUT = 0.5
WRITE_TIMEOUT = 10.0
```

| Constant | Value | Methods using it | Required by CLI-06 |
|----------|-------|------------------|---------------------|
| `SEARCH_TIMEOUT` | 10.0s | `search()` (explicit), `status()` (default), `fetch_handoff()` (default) | ✅ 10s for admin |
| `HOOK_TIMEOUT` | 0.5s | `send_hook()` (explicit) | ✅ 500ms for hooks |
| `WRITE_TIMEOUT` | 10.0s | `write_page()` (explicit) | ✅ 10s for admin |

Note: `status()` and `fetch_handoff()` rely on the `_request` default of `SEARCH_TIMEOUT` rather than passing the constant explicitly. This works but is inconsistent with `search()` and `write_page()` which pass `timeout=` explicitly. CLI-06 does NOT require a `STATUS_TIMEOUT` or `HANDOFF_TIMEOUT` constant — reuse of `SEARCH_TIMEOUT` is acceptable.

### 6. Provider consumption pattern (provider.py)

```python
# provider._search calls client.search() and wraps result
def _search(self, args: dict[str, Any]) -> dict[str, Any]:
    results = self._client.search(query=query, ...)
    return {"ok": True, "results": results}

# provider._write calls client.write_page() and wraps result
def _write(self, args: dict[str, Any]) -> dict[str, Any]:
    result = self._client.write_page(path=args.get("path", ""), ...)
    if not result.get("ok", True):
        return result
    return {"ok": True, "written": args.get("path")}

# provider._status calls client.status() and returns raw result
def _status(self) -> dict[str, Any]:
    return self._client.status()
```

The provider currently treats all client methods as non-throwing (they all swallow). If Phase 2 makes admin methods propagate, the provider's `_search`, `_write`, `_status` will need to handle exceptions — which is correct per CLI-09 (tool paths propagate exceptions). The exception will fly through `_search` → `handle_tool_call` → up to Hermes, which is the intended user-visible error path.

---

## Requirement Analysis Against Current Code

### CLI-01: `client.search(query, workspace, project, limit)` → `GET /admin/search`

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| HTTP method | `GET` | `GET` | ✅ |
| Path | `/admin/search` | `/admin/search` | ✅ |
| Query params | `?q=<query>&limit=N` + ws/project | `?q=<query>&limit=N` | ✅ |
| Auth | Bearer from config | Bearer auth | ✅ |
| Returns | `list[dict[str, Any]]` | "parsed result list" | ✅ |
| Error behavior | Returns `[]` | **Propagates** | ❌ CLI-08 |
| Timeout | 10s (SEARCH_TIMEOUT) | 10s | ✅ CLI-06 |

**Detail:** `search()` parses response with `data.get("results", data.get("pages", []))` — handles both `results` (search) and `pages` (general list) keys.

### CLI-02: `client.write_page(path, body, tags, tier, pinned)` → `POST /admin/write-page`

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| HTTP method | `POST` | `POST` | ✅ |
| Path | `/admin/write-page` | `/admin/write-page` | ✅ |
| Signature | `(self, path, body, tags, workspace, project)` | `(self, path, body, tags, tier, pinned)` | ❌ Missing `tier`, `pinned` params; has `workspace`/`project` not in spec |
| Error behavior | Returns `{"ok": False, ...}` | **Propagates** | ❌ CLI-08 |
| Timeout | 10s (WRITE_TIMEOUT) | 10s | ✅ CLI-06 |

**Detail:** The current signature has `workspace` and `project` params which are NOT in the CLI-02 spec. These may have been added because the provider passes them. The spec says `tier` and `pinned` but the current implementation doesn't include them in the payload either. The payload currently sends `{path, body, tags?, workspace?, project?}` but should send `{path, body, tags?, tier?, pinned?, workspace?, project?}`.

### CLI-03: `client.status()` → `GET /admin/status`

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| HTTP method | `GET` | `GET` | ✅ |
| Path | `/admin/status` | `/admin/status` | ✅ |
| Signature | `(self)` | `(self)` | ✅ |
| Error behavior | Returns `{"ok": False, ...}` | **Propagates** | ❌ CLI-08 |
| Timeout | 10s (default from `_request`) | 10s | ✅ CLI-06 |

### CLI-04: `client.send_hook(event, session_id, payload, workspace, project)` → `POST /hook`

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| HTTP method | `POST` | `POST` | ✅ |
| Path | `/hook` | `/hook` | ✅ |
| Signature | `(self, event, session_id, payload, workspace, project)` | `(self, messages, event, session_id, session_data)` | ⚠️ Parameter names differ — same concept, `payload` ≈ `messages`/`session_data` |
| Error behavior | Logs, never raises | Logged but not raised | ✅ CLI-07 |
| Timeout | 0.5s (HOOK_TIMEOUT) | 500ms | ✅ CLI-06 |

**Detail:** The spec says `send_hook(messages, event, session_id, session_data)`. The current code has `send_hook(event, session_id, payload, workspace, project)`. The `payload` dict contains what the spec calls `messages` or `session_data`. The parameter ordering differs (event first vs. messages first). The `workspace`/`project` params in current aren't in the spec but are needed by the provider. The current agent param is hardcoded as `"hermes"` (line 102).

### CLI-05: `client.fetch_handoff(workspace, project)` → `GET /handoff`

| Aspect | Current | Required | Gap |
|--------|---------|----------|-----|
| HTTP method | `GET` | `GET` | ✅ |
| Path | `/handoff` | `/handoff` | ✅ |
| Signature | `(self, agent, cwd, workspace, project)` | `(self, workspace, project)` | ⚠️ Has extra `agent` and `cwd` params |
| 404 handling | Returns `None` | Returns `None` on 404 | ✅ |
| Other errors | Returns `None` | **Propagates** | ❌ CLI-08 |
| Returns | `str | None` (summary) | "handoff summary string" | ✅ |
| Timeout | 10s (default from `_request`) | 10s | ✅ CLI-06 |

---

## Gap Analysis: CLI-08 (Error Propagation)

**Status: ❌ CRITICAL — all 4 admin/tool methods incorrectly swallow errors**

CLI-08 requires that HTTP errors on tool/admin paths (search, write_page, status, fetch_handoff) **propagate to the caller** for user visibility. Only `send_hook` should swallow (CLI-07).

### Current `search()` behavior (lines 51–58):

```python
try:
    r = self._request("GET", "/admin/search", params=params, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("results", data.get("pages", []))
except Exception:
    log.exception("search failed")
    return []
```

**What gets swallowed:**
- `httpx.HTTPStatusError` (4xx, 5xx from `raise_for_status()`) → returns `[]`
- `httpx.ConnectError` (server unreachable) → returns `[]`
- `httpx.TimeoutException` (request timed out) → returns `[]`
- `json.JSONDecodeError` (bad response body) → returns `[]`

**What should happen:** All of the above should propagate. The provider's `handle_tool_call` will catch them (or let them propagate further to Hermes for user visibility per CLI-09/PRO-09).

### Current `write_page()` behavior (lines 75–81):

Same pattern — all exceptions swallowed, returns `{"ok": False, "error": "write failed"}`.

### Current `status()` behavior (lines 84–90):

Same pattern — all exceptions swallowed, returns `{"ok": False, "error": "status failed"}`.

### Current `fetch_handoff()` behavior (lines 132–141):

Same pattern — all exceptions swallowed, returns `None`. **EXCEPT the 404 check** (lines 134–136) which is intentional:

```python
r = self._request("GET", "/handoff", ...)
if r.status_code == 404:
    return None
r.raise_for_status()
```

**The 404 check should be preserved** — it's not an error, it's expected behavior (no pending handoff). But a 500 or connection error should propagate.

### Recommended fix for CLI-08

**Strategy: Remove try/except from search, write_page, status. Remove try/except from fetch_handoff but keep 404 handling.**

```python
# search — let exceptions propagate
def search(self, query, ...) -> list[dict[str, Any]]:
    r = self._request("GET", "/admin/search", params=params, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("results", data.get("pages", []))

# write_page — let exceptions propagate
def write_page(self, path, body, ...) -> dict[str, Any]:
    r = self._request("POST", "/admin/write-page", json=payload, timeout=WRITE_TIMEOUT)
    r.raise_for_status()
    return r.json()

# status — let exceptions propagate
def status(self) -> dict[str, Any]:
    r = self._request("GET", "/admin/status", timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    return r.json()

# fetch_handoff — let exceptions propagate, keep 404 handling
def fetch_handoff(self, ...) -> str | None:
    r = self._request("GET", "/handoff", params=params, timeout=SEARCH_TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    return data.get("handoff", {}).get("summary")
```

**Impact on provider.py (Phase 3):**
- `_search()` currently calls `client.search()` and wraps in `{"ok": True, "results": results}` — if `search()` raises, `_search()` will propagate the exception naturally
- `_write()` currently checks `result.get("ok", True)` — with propagation, this check becomes dead code for the error case (exception flies out instead)
- `_status()` currently returns raw result — with propagation, exception flies out instead

This is **correct by design** — CLI-09 says tool paths propagate. The provider `sync_turn`/`on_session_end` daemon threads already have their own `try/except: pass` wrappers that will catch propagated exceptions from `send_hook`. No changes needed there.

### Impact on existing tests

Four tests assert the current swallow behavior and MUST be updated:

| Test | Line | Current assertion | Must change to |
|------|------|-------------------|----------------|
| `test_client_search_handles_http_error` | 31–37 | `assert results == []` | `pytest.raises(httpx.HTTPStatusError)` |
| `test_client_status_handles_error` | 74–80 | `assert result["ok"] is False` | `pytest.raises(httpx.ConnectError)` |
| `test_client_fetch_handoff_returns_none_on_404` | 122–128 | `assert result is None` | ✅ Keep (404 is intentional) |
| (missing) | — | — | New test: fetch_handoff 500 should raise |

---

## Gap Analysis: CLI-06 (Timeout Constants)

**Status: ⚠️ Minor — constants exist but usage is inconsistent**

### Current state

| Constant | Value | Definition line |
|----------|-------|-----------------|
| `SEARCH_TIMEOUT` | `10.0` | line 11 |
| `HOOK_TIMEOUT` | `0.5` | line 12 |
| `WRITE_TIMEOUT` | `10.0` | line 13 |

### Per-method timeout analysis

| Method | Timeout passed | Effective timeout | CLI-06 compliance |
|--------|---------------|-------------------|-------------------|
| `search()` | `timeout=SEARCH_TIMEOUT` (line 52) | 10.0s | ✅ 10s for admin |
| `write_page()` | `timeout=WRITE_TIMEOUT` (line 76) | 10.0s | ✅ 10s for admin |
| `status()` | none (uses _request default) | 10.0s (default=SEARCH_TIMEOUT) | ✅ 10s for admin |
| `send_hook()` | `timeout=HOOK_TIMEOUT` (line 114) | 0.5s | ✅ 500ms for hooks |
| `fetch_handoff()` | none (uses _request default) | 10.0s (default=SEARCH_TIMEOUT) | ✅ 10s for admin |

### Issues found

1. **`status()` and `fetch_handoff()` rely on `_request` default** instead of passing an explicit constant. Works correctly (both get 10s) but inconsistent with `search()` and `write_page()`.

2. **No `STATUS_TIMEOUT` or `HANDOFF_TIMEOUT` constant**: Not required by CLI-06 (which only says "500ms for hooks, 10s for admin"), but adding them would make intentions explicit.

3. **No test enforces timeout values**: There's no test that asserts `search()` uses `SEARCH_TIMEOUT`, `send_hook()` uses `HOOK_TIMEOUT`, etc. This is a TDD gap.

4. **The `_request` default is `SEARCH_TIMEOUT`**, which is the admin timeout. If a new admin method is added and forgets to pass timeout, it gets 10s — correct default. If a new hook-like method is added and forgets, it would get 10s instead of 0.5s — potential bug.

### Recommended fixes

**Low priority — not blocking Phase 2.** The constants exist and all methods get correct timeouts. Recommendations for completeness:

1. Make `status()` and `fetch_handoff()` pass `timeout=SEARCH_TIMEOUT` explicitly for consistency
2. Add tests that verify each method's effective timeout

---

## Gap Analysis: Missing Parameters

### `write_page()` missing `tier` and `pinned` params

CLI-02: `write_page(path, body, tags, tier, pinned)`
Current: `write_page(path, body, tags, workspace, project)`

The `tier` and `pinned` parameters are not in the signature or payload. These are needed for the ai-memory `POST /admin/write-page` API. The current payload also sends `workspace` and `project` which are not in the spec but are needed by the provider.

**Recommended fix:** Add `tier` and `pinned` to both the signature and payload construction. Keep `workspace`/`project` as they're consumed by the provider.

### `fetch_handoff()` has extra params not in spec

CLI-05: `fetch_handoff(workspace, project)`
Current: `fetch_handoff(agent, cwd, workspace, project)`

The `agent` and `cwd` params mirror the ai-memory handoff API parameters. They're useful for multi-agent scenarios but not required by v0.1.0. Keep them (they're optional with defaults) but note the spec doesn't mention them.

### `send_hook()` parameter order differs from spec

CLI-04: `send_hook(messages, event, session_id, session_data)`
Current: `send_hook(event, session_id, payload, workspace, project)`

The current signature matches how the provider calls it (provider passes event first). The spec's parameter ordering (`messages` first) would break the provider. **Recommend keeping the current signature** — changing it is not worth the provider breakage.

---

## Risk Analysis: Provider Impact

Changing error propagation in client.py affects `provider.py` as the main consumer:

```python
# Current: client returns fallback → provider wraps in dict
def _search(self, args):
    results = self._client.search(query, ...)  # never raises
    return {"ok": True, "results": results}

# After: client propagates → exception flies through provider → up to Hermes
def _search(self, args):
    results = self._client.search(query, ...)  # CAN raise httpx.HTTPStatusError
    return {"ok": True, "results": results}  # never reached on error
```

This is **the desired behavior** — the exception becomes visible to the user through Hermes. The provider doesn't need to catch it because:
- `sync_turn` / `on_session_end` (hook paths, CLI-07/PRO-08) use daemon threads with their own `try/except: pass`
- `handle_tool_call` (tool paths, CLI-08/PRO-09) should propagate — that's the point

**However**, `prefetch()` (line 108–112) calls `_search()`:
```python
def prefetch(self, query, ...) -> str | None:
    results = self._search({"query": query, "max_results": 3})
    if results.get("ok") and results.get("results"):
        ...
    return None
```

If `_search()` now raises, `prefetch` will crash. PRO-09 says "Tool paths propagate exceptions" — `prefetch` is a tool path (triggered by `queue_prefetch` which is a daemon thread). Actually, `prefetch` returns `str | None` and is called by `queue_prefetch` which wraps it in a daemon thread with no error handling. So a prefetch failure would crash the daemon thread silently (which is arguably fine — prefetch is best-effort). The `queue_prefetch` method (line 114) doesn't catch exceptions either. This is acceptable per the requirements.

---

## Summary: Concrete Changes Needed

### client.py changes

1. **Remove try/except from `search()`** — let exceptions propagate (CLI-08)
2. **Remove try/except from `write_page()`** — let exceptions propagate (CLI-08)
3. **Remove try/except from `status()`** — let exceptions propagate (CLI-08)
4. **Keep try/except in `send_hook()`** — swallow per CLI-07 (already correct)
5. **Partially remove try/except from `fetch_handoff()`** — let non-404 exceptions propagate, keep 404→None (CLI-08)
6. **Add `tier` and `pinned` params to `write_page()`** — add to signature and payload (CLI-02)
7. **Pass `timeout=SEARCH_TIMEOUT` explicitly from `status()` and `fetch_handoff()`** — consistency (CLI-06)
8. **Remove `log.exception` calls from search, write_page, status, fetch_handoff** — or move logging to before re-raise

### test_client.py changes

The following test assertions change (swallow→propagate):

| # | Test | Change |
|---|------|--------|
| 2 | `test_client_search_handles_http_error` | Rewrite: `pytest.raises(httpx.HTTPStatusError)` instead of `assert results == []` |
| 6 | `test_client_status_handles_error` | Rewrite: `pytest.raises(httpx.ConnectError)` instead of `assert result["ok"] is False` |
| 10 | `test_client_fetch_handoff_returns_none_on_404` | Keep as-is (404 is intentional, not error) |

New tests needed:

| Test | Description |
|------|-------------|
| `test_client_write_page_with_tier_and_pinned` | Verify `tier` and `pinned` params in payload |
| `test_client_search_uses_search_timeout` | Verify search uses 10s timeout |
| `test_client_hook_uses_hook_timeout` | Verify send_hook uses 0.5s timeout |
| `test_client_fetch_handoff_raises_on_500` | Verify 500 from handoff propagates |
| `test_client_status_uses_search_timeout` | Verify status uses 10s timeout |
| `test_client_fetch_handoff_uses_search_timeout` | Verify fetch_handoff uses 10s timeout |

---

## Shared Patterns

### MockTransport test setup

**Source:** `test_client.py` + `conftest.py`

Two patterns coexist — use **inline handler** when testing request details, **shared mock_transport** for higher-level tests:

**Inline (preferred for client unit tests):**
```python
def handler(request: httpx.Request) -> httpx.Response:
    assert <request details>
    return httpx.Response(200, json=<expected>)
client._transport = httpx.MockTransport(handler)
```

**Shared (for provider integration tests):**
```python
@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/admin/search" in request.url.path:
            return httpx.Response(200, json=...)
        ...
    return httpx.MockTransport(handler)
```

### Exception testing pattern for Phase 2

After CLI-08 fix, use this pattern for admin method error tests:
```python
def test_search_raises_on_http_error(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    client._transport = httpx.MockTransport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.search("test query")
```

```python
def test_send_hook_does_not_raise(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    client._transport = httpx.MockTransport(handler)
    client.send_hook("user-prompt", "test-session")  # no raise
```

### Logging pattern

**Source:** `client.py` line 9

```python
log = logging.getLogger("ai-memory")
```

Module-level logger, used as `log.exception("method failed")`. The `log.exception()` call automatically includes the traceback. After CLI-08, `send_hook` will be the only method that logs exceptions (others propagate, so caller can log or not as appropriate).

---

## Concern: CLI-08 & `_request` Pattern Refinement

The `_request` method currently returns `httpx.Response`. All error handling is in the wrapping public methods. After CLI-08:

- `send_hook` (swallow) needs try/except → pattern: `_request` → catch → log
- `search`/`write_page`/`status`/`fetch_handoff` (propagate) → no try/except → `_request` exceptions fly through

This is architecturally clean: `_request` is a thin transport layer, public methods decide error policy.

**One consideration:** `r.json()` could fail on bad JSON even with a 200 response. After CLI-08, this also propagates (correctly — bad server response should be visible to the user). The `log.exception` calls should be removed from the four admin methods since callers can log if they want, and `send_hook` already logs.

---

## No Analog Found

All files have close analogs within the same codebase. No external analogs needed.

| File | Role | Data Flow | Analog | Match |
|------|------|-----------|--------|-------|
| `client.py` | client | CRUD + event-driven | itself | self |
| `test_client.py` | test | CRUD + event-driven | `test_provider.py` | project-match |

## Metadata

**Analog search scope:** `plugins/memory/ai-memory/` and `tests/`
**Files scanned:** 6 (client.py, config.py, provider.py, __init__.py, test_client.py, test_provider.py, conftest.py)
**Pattern extraction date:** 2026-07-03
