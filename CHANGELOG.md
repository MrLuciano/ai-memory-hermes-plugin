# Changelog

## [Unreleased]

### Added

- Session-start handoff now forwards the repository marker's `[briefing] inject_on_session_start` opt-in (and optional `max_chars` budget) as `briefing` / `briefing_budget`, so Hermes receives the compiled project brief the official hook clients already get. `config.marker_briefing()` walks from the session `cwd` through capture-only markers and stops at the nearest settings marker, matching ai-memory's own resolution; the provider now passes `cwd` on the handoff fetch. Off unless the repository opts in.
- Optional `search_scope=project` / `AI_MEMORY_SEARCH_SCOPE=project` restricts tools and both recall paths to the resolved workspace/project; global recall remains the default.
- `AiMemoryProvider.scope_diagnostics()` and initialization logs expose local directory/scope state without network calls, credentials, or memory contents.

- `.ai-memory.toml` scope resolution — `config.marker_scope()` walks up from the session's `cwd` (stopping at `$HOME` or the filesystem root) and reads `workspace`/`project` with ai-memory's own line-based parser; a marker that pins no scope key is skipped, matching the server's walk-up.
- `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` env vars, honoured in `load_config()`, in `register()`, and in the scope precedence. Config reads now go through one shared helper, which also stops a `hermes_home`-less call from reading a cwd-relative `ai-memory.json`.
- `config.explicit_scope_keys()` — which scope keys the operator set explicitly, so a configured value beats the repository marker.
- `AiMemoryProvider.recall_status()` — the last `prefetch()`'s hit count, so Hermes can render its recall indicator for ai-memory.
- `AiMemoryProvider.unavailable_reason()` and `AiMemoryClient.last_failure()` — why the provider cannot serve.
- Client pause after repeated failures: `FAILURE_THRESHOLD` (3) consecutive transport failures stop calls for `COOLDOWN_SECONDS` (60s) instead of paying a timeout on every turn; a successful request clears it.
- `SESSION_END_TIMEOUT` (10s) plus optional `cwd` / `timeout` arguments on `AiMemoryClient.send_hook()`.

- `scripts/update.sh` — updates the plugin from GitHub by default; backs up the old install to `$HERMES_HOME/.ai-memory-backups/ai-memory.bak.<timestamp>` (outside the Hermes plugins directory so it is not discovered as a plugin); preserves `ai-memory.json`; supports `UPDATE_FROM_LOCAL=true` and `REPO_TARBALL_URL` overrides.
- `scripts/update.ps1` — Windows equivalent with the same defaults and backup behavior.
- `hermes ai-memory update` CLI command — downloads the latest plugin from GitHub, backs up the old install, and replaces the plugin files.
- `scripts/uninstall.sh` — removes `$HERMES_HOME/plugins/ai-memory`, disables the plugin in Hermes if the CLI is available, and optionally removes `$HERMES_HOME/ai-memory.json` when `REMOVE_CONFIG=true`.
- `scripts/uninstall.ps1` — Windows equivalent; removes `$HERMES_HOME\plugins\ai-memory`, disables the plugin in Hermes if the CLI is available, and optionally removes `$HERMES_HOME\ai-memory.json` with `-RemoveConfig`.
- `hermes ai-memory config-set` CLI command — sets config values; rejects secrets with env-var instructions.
- Config schema now marks `api_key` and `auth_token` as `env_only: true` (env vars only, never persisted to disk).
- `save_config()` now filters secrets before writing to `ai-memory.json` and strips any existing secrets from the file. Returns list of skipped secret keys.
- `cmd_config` shows the source of each secret: `(set via env: AI_MEMORY_AUTH_TOKEN)` or `(not set)`.
- **Pre-flight checks** for all install/uninstall/update scripts: verifies Hermes CLI, Hermes process, ai-memory server reachability, plugin state, write permissions, and wrong-path detection before making any changes.
- **Dry-run mode** (`--dry-run` / `-DryRun`): all scripts show what would happen without making changes.
- **Confirmation prompts**: all scripts prompt before destructive actions. Use `--yes`/`-Yes` or `FORCE=true` to skip (for CI/automation).
- **Non-interactive detection**: when piped, scripts detect missing TTY, print a warning, and proceed. `FORCE=true` silences the warning.

### Fixed

- `Write-Err` in `install.ps1`, `update.ps1` and `uninstall.ps1` now prints its message. An extra pair of braces made it emit a script block, so every error showed the literal text `Write-Host "ERROR: $Msg" -ForegroundColor Red` instead of the error.
- Unknown project scope blocks writes, lifecycle hooks, and handoff consumption; project-mode recall returns no results. Directory routing requires an absolute, existing session directory supplied by Hermes, and does not fall back to the process cwd.
- Background operations capture their client and scope, and obsolete recall workers cannot populate the cache after reinitialization or a session switch.
- New setup/install/update defaults omit fixed workspace/project overrides. In project mode, narrowly matched legacy-generated defaults allow directory routing, while `scope_origin=explicit` preserves an intentional fixed pair.
- Configuration loading is shared by registration, initialization, and the CLI, and accepts UTF-8 BOM files generated by Windows PowerShell.

- `AiMemoryProvider.queue_prefetch()` now accepts the `session_id` keyword Hermes passes (`MemoryManager.queue_prefetch_all`), so the background recall actually runs and the next turn's `prefetch()` is a cache read. Results are cached per `(session_id, query)` and consumed once.
- `AiMemoryProvider.on_memory_write()` now mirrors `add` and `replace` — the actions Hermes announces (its `_MIRRORED_MEMORY_ACTIONS`). The old `write`/`append` gate matched nothing, so no built-in `MEMORY.md` / `USER.md` write was ever mirrored; `write`/`append` stay accepted as synonyms for older callers. A `replace` keeps the superseded entry under `## Substituído`, and `remove` is skipped.
- The tool schemas now use the `parameters` key Hermes normalizes (`MemoryProvider.get_tool_schemas`) instead of `input_schema`, which reached the model as a function with no argument list.
- `initialize()` no longer lets Hermes's `agent_workspace` literal (`"hermes"`) clobber the scope: the checkout's `.ai-memory.toml` is adopted, so Hermes writes the same ai-memory project the other agents in that repository use. An explicit `workspace`/`project` (kwargs, `ai-memory.json`, or `AI_MEMORY_*` env vars) still wins, and a caller reporting no `cwd` keeps the configured scope.
- `initialize()` honours `agent_context`: a cron/subagent run neither writes nor consumes the single-use handoff.
- `on_session_end()` posts the session id instead of the whole transcript (ai-memory reads no body field on `SessionEnd`) and gets `SESSION_END_TIMEOUT` (10s) instead of the 0.5s turn-hook budget, so a slow close no longer loses the session record and its auto handoff.
- Hooks now carry `cwd`, letting the server resolve the session's scope and publish the active project.
- `hermes ai-memory status|config|config-set|link|update` no longer raise `AttributeError`: the host's argparse tree never sets `hermes_home`, so the subcommands resolve it themselves (explicit namespace value, else `get_hermes_home()`, else `HERMES_HOME`/`~/.hermes`). `status` also reads the counters from `counts`, where `/admin/status` nests them, instead of printing `?`.
- `plugin.yaml` declares `python_dependencies` instead of the unknown `pip_dependencies`/`entry_point` keys, and drops the `hooks:` list of ABC method names that no event bus delivers.

- Install/update scripts and `hermes ai-memory update` now detect an empty `$HERMES_HOME/plugins/ai-memory/` directory and re-install instead of treating it as already installed.
- Install/update scripts and CLI command now verify that `__init__.py` exists after install/update and fail loudly if it is missing.
- Install/update scripts now warn if the plugin is found at the wrong nested path `$HERMES_HOME/plugins/memory/ai-memory/`.
- Update backups are now stored in `$HERMES_HOME/.ai-memory-backups/` instead of `$HERMES_HOME/plugins/`, preventing Hermes from discovering backup directories as additional `ai-memory` memory-provider plugins.
- `scripts/install.sh` one-liner (`bash <(curl -sL ...)`) now works when the script is streamed via process substitution. It falls back to downloading the plugin from GitHub and copying it into `$HERMES_HOME/plugins/ai-memory`.
- `scripts/install.ps1` one-liner (`iex ((Invoke-WebRequest ...).Content)`) now works when the script runs in memory. It falls back to downloading the plugin from GitHub and copying it into `$HERMES_HOME\plugins\ai-memory`.
- `AiMemoryProvider.is_available()` now returns `True` whenever `server_url` is configured, instead of requiring an auth token. Hermes only activates a memory provider when `is_available()` is `True`; requiring auth made the plugin appear inactive for default local installs.
- Secrets (`api_key`, `auth_token`) are no longer written to `ai-memory.json`. Existing secrets in the config file are stripped on load. Users must set secrets via environment variables.
- `scripts/update.sh` and `hermes ai-memory update` now strip secrets from backed-up config files when restoring.

### Documentation

- Updated `README.md`, `docs/guide.md`, `docs/reference.md`, and `docs/common-problems.md` for the corrected contracts: background prefetch and its per-session cache, the `add`/`replace` mirroring vocabulary, the minimal `session-end` payload, scope resolution through `.ai-memory.toml`, the `hermes ai-memory …` command names and the `counts` shape of `status`, and the client pause.
- Added a "Scope Resolution" section to `docs/reference.md`.


- Updated README, docs/guide.md, docs/reference.md, and docs/common-problems.md to document install/uninstall scripts, fallback behavior, config-removal flags, the `REPO_TARBALL_URL` override variable, env-only secret handling, and pre-flight/dry-run/confirmation features.

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

- 91 tests across 5 test files
- 94%+ test coverage
- ruff clean (0 errors)
- mypy clean (0 issues, with documented `ai-memory` exclusion)
- Python 3.10+ with `from __future__ import annotations`
- Dependencies: `httpx>=0.28`
- Dev tooling: pytest, pytest-asyncio, pytest-cov, ruff, mypy, pyyaml
