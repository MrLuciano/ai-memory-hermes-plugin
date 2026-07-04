# Changelog

## [0.1.0] — 2026-07-03

### Added

- **Phase 1 — Config** (REQ-001–REQ-006):
  - `AiMemoryConfig` dataclass with typed fields
  - Config schema for `hermes memory setup` wizard
  - JSON file persistence (`$HERMES_HOME/ai-memory.json`)
  - Env-var fallback (`AI_MEMORY_SERVER_URL`, `AI_MEMORY_API_KEY`, `AI_MEMORY_AUTH_TOKEN`)
  - Extra-key filtering on config load (future-proof)
  - Roundtrip and corrupt-file handling

- **Phase 2 — Client** (REQ-007–REQ-010):
  - `AiMemoryClient` typed HTTP wrapper using `httpx.Client`
  - `search()` — `GET /admin/search` with workspace/project scoping
  - `write_page()` — `POST /admin/write-page` with tier, pinned, tags
  - `status()` — `GET /admin/status`
  - `send_hook()` — `POST /hook` with event/session/payload
  - `fetch_handoff()` — `GET /handoff` with 404 → None fallback
  - Persistent session (connection pooling) + per-request timeouts
  - Auth header injection via Bearer token

- **Phase 3 — Provider** (REQ-011–REQ-019):
  - `AiMemoryProvider` implementing Hermes `MemoryProvider` ABC
  - `is_available()` — checks credentials (not server URL default)
  - `initialize()` — resolves workspace/project from kwargs, reloads config
  - `prefetch()` — synchronous search before each model turn
  - `queue_prefetch()` — daemon-thread background search
  - `sync_turn()` — daemon-thread turn capture (swallows errors)
  - `on_session_end()` — daemon-thread session finalization
  - `on_memory_write()` — mirrors Hermes built-in memory to ai-memory wiki
  - `handle_tool_call()` — dispatches search/write/status
  - `system_prompt_block()` — model context injection
  - Return-type alignment (`str` not `str | None`)
  - Kwargs absorption on all hook methods
  - `metadata` param on `on_memory_write`

- **Phase 4 — Entry Point** (REQ-020–REQ-022):
  - `register()` using `ctx.register_memory_provider(instance)`
  - Config file loading from `$HERMES_HOME` + env-var overrides
  - `sys.path` insertion for Hermes loader compatibility
  - `plugin.yaml` with hooks declaration (`on_session_end`, `sync_turn`, `on_memory_write`)
  - `pip_dependencies` in plugin metadata (`httpx`)

- **Phase 5 — CLI** (REQ-023–REQ-027):
  - `register_cli(subparsers)` — Hermes CLI integration
  - `cmd_status` — server reachability with page/session counts
  - `cmd_config` — config display (secrets masked)
  - `cmd_link` — symlink plugin into Hermes profile
  - Uses `AiMemoryClient` directly (no provider dependency)

- **Code Review Fixes** (2026-07-03):
  - `is_available()` — fixed tautology (was `return True`)
  - Production import loading via `sys.path.insert` in `__init__.py`
  - Unified config precedence: env > file > defaults
  - Thread-safe config capture in daemon thread closures
  - `httpx` declared in `[project] dependencies`
  - `on_memory_write` wrapped in try/except
  - Persistent httpx.Client (connection pooling)
  - CLI uses AiMemoryClient directly instead of provider
  - `plugin.yaml` declares all 3 hooks
  - Bare `except:` → specific exception types
  - `kwargs.pop` → `.get` pattern
  - Test assertions for `send_hook` call chain

### Technical

- 74 tests across 5 test files
- 94.13% test coverage
- ruff clean (0 errors)
- mypy clean (0 issues, with documented `ai-memory` exclusion)
- Python 3.10+ with `from __future__ import annotations`
- Dependencies: `httpx>=0.28`
- Dev tooling: pytest, pytest-asyncio, pytest-cov, ruff, mypy, pyyaml
