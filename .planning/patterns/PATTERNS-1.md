# Phase 1: Config — Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 4 (config.py, test_config.py, conftest.py, pyproject.toml)
**Analogs found:** 4 / 4

## File Classification

| File | Role | Data Flow | Closest Analog | Match Quality |
|------|------|-----------|----------------|---------------|
| `plugins/memory/ai-memory/config.py` | config | request-response | `client.py` (same-package, same import style) | package-match |
| `tests/test_config.py` | test | CRUD | `test_client.py` (same-project, same test patterns) | project-match |
| `tests/conftest.py` | test-utility | config | itself (unique fixture file) | — |
| `pyproject.toml` | config | n/a | standard Python project file | — |

## Pattern Assignments

### `plugins/memory/ai-memory/config.py` (config, request-response)

**Analog:** `plugins/memory/ai-memory/client.py` (same package, same conventions)

**Imports pattern** (config.py lines 1–8):
```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
```

Key observations:
- `from __future__ import annotations` is first — enables PEP 604 syntax (`str | None` instead of `Optional[str]`)
- stdlib imports only (no third-party deps for config — deliberate choice)
- `Path` from `pathlib` for all filesystem operations (consistent pattern: used in both `save_config` and `load_config`)
- No `logging` import — config module doesn't log (only `client.py` and `provider.py` use logging)

**Dataclass pattern** (config.py lines 12–18):
```python
@dataclass
class AiMemoryConfig:
    server_url: str = DEFAULT_SERVER_URL
    api_key: str = ""
    auth_token: str = ""
    workspace: str = "hermes"
    project: str = "hermes-default"
```

Key conventions:
- Default values at class level (not `__init__`)
- `DEFAULT_SERVER_URL` defined as module constant (line 9) — referenced by both `AiMemoryConfig` and `get_config_schema()`
- All fields are `str` — no `Optional[str]` despite env var fallback potentially returning `None`
- `api_key` and `auth_token` are separate (one for legacy API key, one for Bearer token)
- No `hermes_home` or `data_dir` in the dataclass itself — those are `save_config`/`load_config` parameters

**Schema pattern** (config.py lines 21–48):
```python
def get_config_schema() -> list[dict[str, Any]]:
    return [
        {
            "key": "server_url",
            "description": "ai-memory server URL",
            "default": DEFAULT_SERVER_URL,
            "required": False,
        },
        {
            "key": "auth_token",
            "description": "ai-memory auth token (optional for local mode)",
            "secret": True,
            "required": False,
            "env_var": "AI_MEMORY_AUTH_TOKEN",
        },
        {
            "key": "workspace",
            "description": "ai-memory workspace name",
            "default": "hermes",
            "required": False,
        },
        {
            "key": "project",
            "description": "ai-memory project name",
            "default": "hermes-default",
            "required": False,
        },
    ]
```

Pattern structure:
- Each field is a `dict` with `key`, `description`, optional `default`/`secret`/`env_var`/`required`
- `"required": False` on every field — zero-arg construction must work
- `"secret": True` on `auth_token` — marks sensitive field for the setup wizard
- `"env_var"` key on `auth_token` only — links to `AI_MEMORY_AUTH_TOKEN`
- ⚠️ **Missing field: `api_key`** — `AiMemoryConfig` has `api_key: str = ""` but `get_config_schema()` only has 4 fields (server_url, auth_token, workspace, project). The `api_key` field is used by `client.py` (line 21: `token = config.auth_token or config.api_key`) and by `load_config` (line 76: env var `AI_MEMORY_API_KEY`), but is not exposed in the schema. This is a **bug** — the schema should include `api_key` with `env_var: "AI_MEMORY_API_KEY"`.

**Merge-on-save pattern** (config.py lines 51–61):
```python
def save_config(values: dict[str, Any], hermes_home: str) -> None:
    p = Path(hermes_home) / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            pass
    existing.update(values)
    p.write_text(json.dumps(existing, indent=2))
```

Key patterns:
- Accepts `hermes_home: str` (cast to `Path` inside) — flexible for callers passing string paths
- Silently creates parent dirs with `p.parent.mkdir(parents=True, exist_ok=True)`
- Merge strategy: reads existing JSON → `existing.update(values)` — keeps keys not in `values`
- Silent on parse errors: `except Exception: pass` — corrupt JSON is discarded
- Writes with `indent=2` for human readability
- No return value (`-> None`) — fire-and-forget

**Env-fallback pattern** (config.py lines 64–78):
```python
def load_config(hermes_home: str) -> AiMemoryConfig:
    p = Path(hermes_home) / "ai-memory.json"
    overrides: dict[str, Any] = {}

    if p.exists():
        try:
            overrides = json.loads(p.read_text())
        except Exception:
            pass

    overrides.setdefault("server_url", os.environ.get("AI_MEMORY_SERVER_URL", DEFAULT_SERVER_URL))
    overrides.setdefault("auth_token", os.environ.get("AI_MEMORY_AUTH_TOKEN", ""))
    overrides.setdefault("api_key", os.environ.get("AI_MEMORY_API_KEY", ""))

    return AiMemoryConfig(**{k: v for k, v in overrides.items() if hasattr(AiMemoryConfig, k)})
```

Priority chain: file JSON > env var > hardcoded default
- `overrides.setdefault()` ensures file JSON takes priority over env var
- `os.environ.get("VAR", default)` ensures env var takes priority over hardcoded default
- Filter step `hasattr(AiMemoryConfig, k)` strips unknown keys from JSON (tolerates extra keys in saved file)
- ⚠️ **Inconsistency:** The dataclass has `workspace: str = "hermes"` and `project: str = "hermes-default"` as defaults, but `load_config` only has env fallbacks for `server_url`, `auth_token`, and `api_key` — NOT for `workspace` and `project`. If someone sets `AI_MEMORY_WORKSPACE` env var, it would NOT be picked up. Per requirements CFG-04, only `AI_MEMORY_SERVER_URL`, `AI_MEMORY_AUTH_TOKEN`, and `AI_MEMORY_DATA_DIR` are listed as env vars, so this is *by design* — but worth noting.

**Auth header pattern** (for reference — client.py lines 16–24):
```python
def __init__(self, config: AiMemoryConfig) -> None:
    self.config = config
    self._base = config.server_url.rstrip("/")
    self._headers: dict[str, str] = {"Content-Type": "application/json"}
    token = config.auth_token or config.api_key
    if token:
        self._headers["Authorization"] = f"Bearer {token}"
```

This shows how `auth_token` and `api_key` are consumed: `auth_token || api_key`, never both.

---

### `tests/test_config.py` (test, CRUD)

**Analog:** `tests/test_client.py` (same project, same conventions)

**Imports pattern** (test_config.py lines 1–8):
```python
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from config import AiMemoryConfig, get_config_schema, load_config, save_config
```

Key patterns:
- Direct import from `config` (no package prefix) — because `conftest.py` adds `plugins/memory/ai-memory/` to `sys.path` (line 11–14)
- Uses `tmp_path` fixture (pytest built-in) — not the custom `mock_home` from conftest
- Uses `monkeypatch` for env var tests (test_load_config_falls_back_to_env)

**Test pattern — defaults** (lines 11–17):
```python
def test_config_defaults() -> None:
    cfg = AiMemoryConfig()
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.api_key == ""
    assert cfg.auth_token == ""
    assert cfg.workspace == "hermes"
    assert cfg.project == "hermes-default"
```

Tests zero-arg construction — every field has a default.

**Test pattern — custom values** (lines 20–31):
```python
def test_config_custom_values() -> None:
    cfg = AiMemoryConfig(
        server_url="http://custom:49374",
        auth_token="abc123",
        workspace="custom-ws",
        project="custom-proj",
    )
    assert cfg.server_url == "http://custom:49374"
    assert cfg.auth_token == "abc123"
    assert cfg.workspace == "custom-ws"
    assert cfg.project == "custom-proj"
```

Tests positional/named construction. Notable: doesn't test `api_key` custom value (gap).

**Test pattern — schema completeness** (lines 33–39):
```python
def test_get_config_schema() -> None:
    schema = get_config_schema()
    keys = {item["key"] for item in schema}
    assert "server_url" in keys
    assert "auth_token" in keys
    assert "workspace" in keys
    assert "project" in keys
```

Checks that all expected keys are present. ⚠️ **Does NOT assert on `api_key`** — because the schema doesn't include it (the bug mentioned above). Once `api_key` is added to the schema, this test should also assert it.

**Test pattern — save_config creates file** (lines 42–47):
```python
def test_save_config_creates_file(tmp_path: Path) -> None:
    save_config({"server_url": "http://test:49374"}, str(tmp_path))
    p = tmp_path / "ai-memory.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["server_url"] == "http://test:49374"
```

Uses `tmp_path` (pytest Path fixture) — no cleanup needed. Doesn't test parent dir creation (separate test at line 89).

**Test pattern — save_config merges** (lines 50–56):
```python
def test_save_config_merges_existing(tmp_path: Path) -> None:
    p = tmp_path / "ai-memory.json"
    p.write_text(json.dumps({"existing_key": "value"}))
    save_config({"server_url": "http://test:49374"}, str(tmp_path))
    data = json.loads(p.read_text())
    assert data["existing_key"] == "value"
    assert data["server_url"] == "http://test:49374"
```

Proves merge-on-save: pre-writes a file with `existing_key`, calls save_config, verifies both old and new keys survive.

**Test pattern — load_config from file** (lines 59–72):
```python
def test_load_config_from_file(tmp_path: Path) -> None:
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "server_url": "http://file:49374",
        "auth_token": "file-token",
        "workspace": "file-ws",
        "project": "file-proj",
    }))
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://file:49374"
    ...
```

Writes a full config file, loads it, asserts every field matches.

**Test pattern — file not found falls to defaults** (lines 75–86):
```python
def test_load_config_file_not_found(tmp_path: Path) -> None:
    old_url = os.environ.pop("AI_MEMORY_SERVER_URL", None)
    old_token = os.environ.pop("AI_MEMORY_AUTH_TOKEN", None)
    try:
        cfg = load_config(str(tmp_path))
        assert cfg.server_url == "http://127.0.0.1:49374"
        assert cfg.auth_token == ""
    finally:
        if old_url is not None:
            os.environ["AI_MEMORY_SERVER_URL"] = old_url
        if old_token is not None:
            os.environ["AI_MEMORY_AUTH_TOKEN"] = old_token
```

Manual env var save/restore pattern (not using `monkeypatch` — inconsistent with test at line 95). Tests that with no file and no env vars, defaults kick in.

**Test pattern — env fallback** (lines 95–100):
```python
def test_load_config_falls_back_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MEMORY_SERVER_URL", "http://env:49374")
    monkeypatch.setenv("AI_MEMORY_AUTH_TOKEN", "env-token")
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://env:49374"
    assert cfg.auth_token == "env-token"
```

Uses `monkeypatch` fixture (cleaner than manual save/restore at line 75). No file exists → env var takes over → fallback to defaults if no env var.

**Test pattern — parent dir creation** (lines 89–92):
```python
def test_save_config_creates_parent_dirs(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    save_config({"server_url": "http://test:49374"}, str(deep))
    assert (deep / "ai-memory.json").exists()
```

Passes a deep path as `hermes_home` — verifies `mkdir(parents=True)` works.

### `tests/conftest.py` (test-utility, config)

**sys.path injection pattern** (conftest.py lines 1–14):
```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "plugins/memory/ai-memory"),
)
```

All tests import from `config`, `client`, `provider` directly (no `plugins.memory.ai_memory.config`). This means **mypy cannot resolve these imports** — it will report `import "config"` as unresolved unless the config matches. This is a known issue: mypy excludes `plugins/` entirely (see below).

**Core fixtures** (conftest.py lines 21–87):

`mock_home` — returns a tmp dir for config I/O:
```python
@pytest.fixture
def mock_home(tmp_path: Path) -> Path:
    return tmp_path / ".hermes"
```

`config` — returns a pre-configured AiMemoryConfig:
```python
@pytest.fixture
def config() -> AiMemoryConfig:
    return AiMemoryConfig(
        server_url="http://localhost:49374",
        auth_token="test-token",
        workspace="hermes",
        project="hermes-test",
    )
```

`mock_transport` — httpx MockTransport handler returning canned responses:
```python
@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/admin/search" in request.url.path:
            return httpx.Response(200, json={"results": [...]})
        ...
    return httpx.MockTransport(handler)
```

`mock_client` — wraps config + transport:
```python
@pytest.fixture
def mock_client(config: AiMemoryConfig, mock_transport: httpx.MockTransport) -> AiMemoryClient:
    client = AiMemoryClient(config)
    client._transport = mock_transport
    return client
```

`provider` — direct instantiation:
```python
@pytest.fixture
def provider(config: AiMemoryConfig) -> AiMemoryProvider:
    return AiMemoryProvider(config=config)
```

`saved_config` — pre-writes a config file:
```python
@pytest.fixture
def saved_config(mock_home: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "server_url": "http://localhost:49374",
        "auth_token": "saved-token",
        "workspace": "hermes",
        "project": "hermes-custom",
    }
    p = mock_home / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return data
```

Note: `saved_config` fixture is defined but **not used** by `test_config.py`. It's available for client/provider tests.

---

### `pyproject.toml` (config, n/a)

**mypy exclude issue** (lines 26–30):
```toml
[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true
exclude = ["plugins/"]
```

The `exclude = ["plugins/"]` line means **all type checking is skipped** for `plugins/memory/ai-memory/*.py`, `test_config.py` (because its imports resolve via `sys.path` injection in conftest), and all plugin code. This is explicitly flagged in ROADMAP.md (risk #4) and STATE.md (RD-04, open item).

Recommended fix: change to `exclude = []` and add per-file `# type: ignore` for the conftest `sys.path.insert` line and any third-party imports without stubs.

---

## Shared Patterns

### Error handling: silent pass on corrupt JSON

**Source:** `config.py` lines 56–59 (save_config) and lines 70–72 (load_config)

```python
try:
    existing = json.loads(p.read_text())
except Exception:
    pass
```

Both `save_config` and `load_config` silently discard corrupt JSON files. This is intentional — the plugin never crashes because of a corrupt config file. It falls back to defaults/merge. Propagate this pattern to any new file-reading code.

### Path construction: `Path(hermes_home) / "ai-memory.json"`

**Source:** `config.py` lines 52, 65

All config file paths are constructed as `Path(hermes_home) / "ai-memory.json"`. The `hermes_home` parameter is a `str` — cast to `Path` inside the function. Consistent across both `save_config` and `load_config`.

### Dict filtering: `hasattr` guard

**Source:** `config.py` line 78

```python
return AiMemoryConfig(**{k: v for k, v in overrides.items() if hasattr(AiMemoryConfig, k)})
```

Filters out JSON keys that don't correspond to dataclass fields. This tolerates forward-compatibility (extra keys from newer versions) and corrupt data.

### Test isolation: `tmp_path` + `monkeypatch`

**Source:** `test_config.py`

Every test uses `tmp_path` (pytest built-in) for filesystem isolation. Env var tests use either `monkeypatch` (preferred, cleaner) or manual `os.environ.pop`/save-restore. **Prefer `monkeypatch`** for all new tests — it's safer (auto-restores, scoped to test function).

---

## Structural Issues

### 1. Missing `api_key` in schema (BUG)

`get_config_schema()` does NOT include `api_key`, yet:
- `AiMemoryConfig` has `api_key: str = ""`
- `client.py` line 21 uses `config.auth_token or config.api_key`
- `load_config` line 76 reads `os.environ.get("AI_MEMORY_API_KEY", "")`

The schema field should be:
```python
{
    "key": "api_key",
    "description": "ai-memory API key (alternative to auth_token)",
    "secret": True,
    "required": False,
    "env_var": "AI_MEMORY_API_KEY",
}
```

### 2. mypy excludes all plugin code

`pyproject.toml` line 30: `exclude = ["plugins/"]` — this means `mypy .` gives a free pass. Must be fixed in Phase 1. See ROADMAP.md recommendation: `exclude = []` with per-file ignores.

### 3. Inconsistent env var save/restore in tests

`test_load_config_file_not_found` (line 75) uses manual `os.environ.pop()` + try/finally, while `test_load_config_falls_back_to_env` (line 95) uses `monkeypatch`. The manual pattern is fragile (env vars are process-global). New tests should use `monkeypatch`.

### 4. No roundtrip test

There is no test for `save_config()` → `load_config()` roundtrip producing identical values. The ROADMAP success criterion says "Config round-trips idempotently." This is a gap.

---

## Recommendations for Phase 1 Implementation

1. **Fix the `api_key` schema gap** — add it to `get_config_schema()` with `secret: True` and `env_var: "AI_MEMORY_API_KEY"`
2. **Fix mypy exclude** — change to `exclude = []` and add `# type: ignore` on conftest's `sys.path.insert` and on third-party imports
3. **Add roundtrip test** — `save_config()` then `load_config()` should produce same values
4. **Add `workspace`/`project` env var fallback test** — verify they fall back to defaults (currently no env var fallback exists, which is by design but should be tested)
5. **Add `api_key` schema assertion** — update `test_get_config_schema` to assert `api_key` is in keys
6. **Enrich test coverage** for edge cases:
   - Corrupt JSON file (syntax error in file) — should not crash
   - Extra keys in JSON file — should be filtered out
   - Empty `hermes_home` path behavior
   - File with only partial fields (e.g., just `server_url`, no `auth_token`)
7. **Refactor test_load_config_file_not_found** to use `monkeypatch` instead of manual os.environ save/restore

## No Analog Found

| File | Reason |
|------|--------|
| `pyproject.toml` | Standard Python project config — no internal analog needed |

## Metadata

**Analog search scope:** `plugins/memory/ai-memory/` and `tests/`
**Files scanned:** 7 (config.py, client.py, provider.py, __init__.py, test_config.py, test_client.py, test_provider.py, conftest.py, pyproject.toml, plugin.yaml)
**Pattern extraction date:** 2026-07-03
