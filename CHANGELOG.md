# Changelog

## [Unreleased]

### Added

- `scripts/update.sh` — updates the plugin from GitHub by default; backs up the old install to `$HERMES_HOME/plugins/ai-memory.bak.<timestamp>`; preserves `ai-memory.json`; supports `UPDATE_FROM_LOCAL=true` and `REPO_TARBALL_URL` overrides.
- `scripts/update.ps1` — Windows equivalent with the same defaults and backup behavior.
- `hermes ai-memory update` CLI command — downloads the latest plugin from GitHub, backs up the old install, and replaces the plugin files.
- `scripts/uninstall.sh` — removes `$HERMES_HOME/plugins/ai-memory`, disables the plugin in Hermes if the CLI is available, and optionally removes `$HERMES_HOME/ai-memory.json` when `REMOVE_CONFIG=true`.
- `scripts/uninstall.ps1` — Windows equivalent; removes `$HERMES_HOME\plugins\ai-memory`, disables the plugin in Hermes if the CLI is available, and optionally removes `$HERMES_HOME\ai-memory.json` with `-RemoveConfig`.

### Fixed

- `scripts/install.sh` one-liner (`bash <(curl -sL ...)`) now works when the script is streamed via process substitution. It falls back to downloading the plugin from GitHub and copying it into `$HERMES_HOME/plugins/ai-memory`.
- `scripts/install.ps1` one-liner (`iex ((Invoke-WebRequest ...).Content)`) now works when the script runs in memory. It falls back to downloading the plugin from GitHub and copying it into `$HERMES_HOME\plugins\ai-memory`.
- `AiMemoryProvider.is_available()` now returns `True` whenever `server_url` is configured, instead of requiring an auth token. Hermes only activates a memory provider when `is_available()` is `True`; requiring auth made the plugin appear inactive for default local installs.
- `plugins/memory/ai-memory/provider.py` — moved `logging.getLogger(__name__)` after imports to resolve ruff `E402` lint errors.
- Plugin submodules (`client.py`, `config.py`, `cli.py`, `provider.py`) now self-register their directory in `sys.path`, so Hermes can pre-load them before `__init__.py` runs without import errors.
- `plugin.yaml` now declares `kind: exclusive` so Hermes treats it explicitly as a memory-provider plugin.

### Documentation

- Updated README, docs/guide.md, docs/reference.md, and docs/common-problems.md to document install/uninstall scripts, fallback behavior, config-removal flags, and the `REPO_TARBALL_URL` override variable.

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

- **Code Review Fixes — Round 1** (2026-07-03):
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

- **Code Review Fixes — Round 2** (2026-07-03):
  - Added `__all__ = ["register"]` to `__init__.py`
  - Documented `sys.path.insert` rationale in both `__init__.py` and `conftest.py`
  - `_write()` now defaults `ok` to `False` instead of `True`
  - `on_memory_write` now logs exception via `log.warning` instead of silent pass
  - `search()` handles non-dict API response gracefully
  - `test_queue_prefetch` verifies `prefetch` is actually called
  - Removed no-op `assert True` from hook error test
  - Added test for env-over-file config precedence
  - Added test for non-dict search response

### Technical

- 76 tests across 5 test files
- 94%+ test coverage
- ruff clean (0 errors)
- mypy clean (0 issues, with documented `ai-memory` exclusion)
- Python 3.10+ with `from __future__ import annotations`
- Dependencies: `httpx>=0.28`
- Dev tooling: pytest, pytest-asyncio, pytest-cov, ruff, mypy, pyyaml
