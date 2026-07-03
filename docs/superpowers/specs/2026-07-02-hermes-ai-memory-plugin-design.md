# ai-memory Hermes Agent Memory Provider Plugin

> Design for a standalone Hermes Agent memory provider plugin backed by ai-memory's hook protocol and admin REST API.

**Status**: Approved for implementation

---

## 1. Problem

Hermes Agent has a built-in `MEMORY.md` / `USER.md` system for cross-session
knowledge, but no integration with [ai-memory](https://github.com/akitaonrails/ai-memory) —
a Rust-based long-term memory server that captures lifecycle events and compiles them
into a durable, git-versioned markdown wiki with FTS5 search.

Users who want ai-memory's zero-friction capture, cross-agent handoffs, and
Karpathy-style LLM wiki must currently choose between:
- Running ai-memory as a separate MCP server (loses Hermes' native tool injection,
  prefetch, and lifecycle integration)
- Running ai-memory alongside a Hermes-native memory provider (duplicated storage)

This plugin bridges the gap: Hermes agents get ai-memory as a first-class
`MemoryProvider` with automatic prefetch, turn sync, and session finalization.

## 2. Solution

A Hermes `MemoryProvider` plugin that speaks ai-memory's HTTP protocol:

- **Hook protocol** (`POST /hook`) for lifecycle capture — sync_turn writes
  observations; on_session_end triggers compilation into wiki pages
- **Admin REST API** (`GET /admin/search`, `POST /admin/write-page`,
  `GET /admin/status`) for agent-facing tools and prefetch
- **Handoff API** (`GET /handoff`) for cross-agent continuation prompts

### 2.1 Architecture

```
┌─────────────────────┐     MemoryProvider ABC      ┌──────────────────────┐
│   Hermes Agent      │◄──────────────────────────►│  AiMemoryProvider     │
│                     │     prefetch / sync_turn    │  provider.py          │
│  MemoryManager      │     on_session_end / tools  │                      │
└─────────────────────┘                             └──────┬───────────────┘
                                                           │ calls
                                                    ┌──────▼───────────────┐
                                                    │  AiMemoryClient      │
                                                    │  client.py           │
                                                    │                      │
                                                    │  httpx (async)       │
                                                    └──────┬───────────────┘
                                                           │ HTTP
                                              ┌────────────▼────────────┐
                                              │  ai-memory server       │
                                              │  (homelab/cloud/LAN)    │
                                              │  port 49374             │
                                              │                         │
                                              │  POST /hook             │
                                              │  GET  /admin/search     │
                                              │  POST /admin/write-page │
                                              │  GET  /admin/status     │
                                              │  GET  /handoff          │
                                              └─────────────────────────┘
```

### 2.2 Lifecycle Mapping

| Hermes hook | ai-memory call | When | Threading |
|---|---|---|---|
| `initialize()` | Resolve workspace/project, store session_id | Agent startup | Sync |
| `system_prompt_block()` | `GET /handoff` → inject as system context | Before first prompt | Sync |
| `prefetch(query)` | `GET /admin/search?q=<query>&limit=3` | Before every LLM call | Sync (fast, <1s) |
| `queue_prefetch(query)` | Same as prefetch, in daemon thread | After each turn | Background |
| `sync_turn(user, assistant)` | `POST /hook?event=user-prompt` + `POST /hook?event=post-tool-use` | After each turn | Daemon thread, 500ms timeout |
| `on_session_end(messages)` | `POST /hook?event=session-end` | Conversation ends | Daemon thread |
| `on_memory_write(...)` | `POST /admin/write-page` | MEMORY.md mirror | Daemon thread |
| `get_tool_schemas()` | Returns 3 tool definitions | After init | Sync |
| `handle_tool_call(name, args)` | Routes to client search/write/status | On tool use | Sync |
| `shutdown()` | Join pending threads (5s timeout) | Process exit | Sync |

### 2.3 API Contract

#### ai-memory endpoints used

| Method | Path | Purpose | Timeout |
|---|---|---|---|
| POST | `/hook?event=...&agent=hermes&workspace=...&project=...` | Ingest lifecycle event | 500ms (fire-and-forget) |
| GET | `/admin/search?q=...&workspace=...&project=...&limit=...` | FTS5 wiki search | 10s |
| POST | `/admin/write-page` | Write wiki page | 10s |
| GET | `/admin/status` | Server health + counts | 10s |
| GET | `/handoff?agent=hermes&cwd=...&workspace=...&project=...` | Fetch pending handoff | 1s |

#### Auth

All requests carry `Authorization: Bearer <token>` when `AI_MEMORY_AUTH_TOKEN`
is set or configured via `hermes memory setup`. Loopback servers use no auth.

#### Profile isolation

Each Hermes profile maps to an ai-memory project:

- `workspace`: `hermes` (configurable)
- `project`: `hermes-{profile_name}` (configurable)

Example: profile `work` → `workspace=hermes`, `project=hermes-work`.

## 3. Project Structure

```
ai-memory-hermes-plugin/
├── pyproject.toml                 # uv project (dev tooling only)
├── uv.lock                        # uv lock file (generated)
├── AGENTS.md                      # Canonical agent instructions
├── plugins/
│   └── memory/
│       └── ai-memory/
│           ├── __init__.py        # register(ctx) entry point
│           ├── plugin.yaml        # Hermes plugin metadata
│           ├── provider.py        # AiMemoryProvider(MemoryProvider)
│           ├── client.py          # AiMemoryClient (HTTP wrapper)
│           ├── config.py          # Config schema + persistence
│           ├── cli.py             # Optional CLI subcommands
│           └── README.md          # Plugin setup instructions
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures (mock server, test config)
│   ├── test_config.py             # Config tests
│   ├── test_client.py             # Client tests (httpx mock transport)
│   └── test_provider.py           # Provider tests (mock client)
└── README.md                      # Project README
```

### 3.1 pyproject.toml

```toml
[project]
name = "ai-memory-hermes-plugin"
version = "0.1.0"
description = "Hermes Agent memory provider backed by ai-memory"
requires-python = ">=3.10"
dependencies = []

[tool.uv]
dev-dependencies = [
    "pytest>=8",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy",
    "httpx",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### 3.2 plugin.yaml

```yaml
name: ai-memory
version: 0.1.0
description: "ai-memory wiki-backed long-term memory provider"
pip_dependencies:
  - httpx
hooks:
  - on_session_end
```

## 4. Implementation Phases

### Phase 1: `config.py` + `test_config.py`

- `AiMemoryConfig` dataclass: `server_url`, `api_key`, `workspace`, `project`
- `get_config_schema()` returns field descriptors for setup wizard
- `save_config(values, hermes_home)` writes JSON to `$HERMES_HOME/ai-memory.json`
- `load_config(hermes_home)` reads JSON, falls back to env vars

### Phase 2: `client.py` + `test_client.py`

- `AiMemoryClient` class with typed methods:
  - `search(query, workspace, project, limit=3) → list[dict]`
  - `write_page(path, body, tags, workspace, project) → dict`
  - `status() → dict`
  - `send_hook(event, session_id, payload, workspace, project) → None`
  - `fetch_handoff(agent, cwd, workspace, project) → str | None`
- Bearer auth via `Authorization: Bearer <token>`
- Timeout handling: 500ms for hooks, 10s for admin/search
- Error handling: HTTP errors → logged, not raised on hook paths

### Phase 3: `provider.py` + `test_provider.py`

- `AiMemoryProvider(MemoryProvider)` implementing all methods from §2.2
- Thread safety: `threading.Lock` for config access, daemon threads for sync
- Tool schemas: `ai_memory_search`, `ai_memory_write`, `ai_memory_status`

### Phase 4: `__init__.py` + `plugin.yaml`

- Minimal `register(ctx)` entry point
- `plugin.yaml` declaring `httpx` dependency

### Phase 5: `cli.py` (optional)

- `hermes ai-memory status` — show connection status
- `hermes ai-memory config` — show current config
- `hermes ai-memory link` — symlink plugin to `$HERMES_HOME/plugins/`

## 5. Testing Strategy

| Test file | What | How |
|---|---|---|
| `test_config.py` | Config save/load/schema | Mock filesystem, verify JSON roundtrip |
| `test_client.py` | HTTP calls | `httpx.MockTransport` — assert URL, method, headers, body; return fixtures |
| `test_provider.py` | Lifecycle hooks | Mock `AiMemoryClient` — assert each ABC method calls correct client method |

All tests use pytest fixtures from `conftest.py`:
- `mock_home(tmp_path)` — temp `$HERMES_HOME`
- `mock_client` — `AiMemoryClient` with `MockTransport`
- `mock_provider(mock_client)` — `AiMemoryProvider` with mock client injected

### Quality Gates

```bash
uv run ruff check .
uv run mypy .
uv run pytest --cov
```

## 6. Deployment

### Development install

```bash
uv sync                              # Install dev deps
ln -s $(pwd)/plugins/memory/ai-memory "$HERMES_HOME/plugins/ai-memory"
```

### User install

```bash
cp -r plugins/memory/ai-memory/ "$HERMES_HOME/plugins/ai-memory/"
hermes plugins list                  # Verify discovery
hermes memory setup                  # Configure server URL + auth token
```

## 7. Success Criteria

- [ ] `hermes plugins list` shows `ai-memory` as available
- [ ] `hermes memory setup` accepts server URL / API key / workspace / project
- [ ] `hermes memory status` reports connected
- [ ] `ai_memory_search` tool returns results from wiki
- [ ] `ai_memory_write` tool creates a new wiki page
- [ ] Conversation turns are captured via hook protocol (verify in ai-memory /web UI)
- [ ] Context is injected before model turn (prefetch called)
- [ ] Session end triggers wiki page synthesis in ai-memory
- [ ] Switching Hermes profiles isolates writes to per-profile ai-memory project
- [ ] All quality gates pass (`ruff check`, `mypy`, `pytest --cov`)
