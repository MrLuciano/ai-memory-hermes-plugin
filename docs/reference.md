# Reference

## Configuration

### `AiMemoryConfig`

Dataclass in `config.py`. Fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `server_url` | `str` | `http://127.0.0.1:49374` | ai-memory HTTP API endpoint |
| `api_key` | `str` | `""` | API key (Bearer token) |
| `auth_token` | `str` | `""` | Auth token alias |
| `workspace` | `str` | `"hermes"` | ai-memory workspace name |
| `project` | `str` | `"hermes-default"` | ai-memory project name |
| `search_scope` | `str` | `"global"` | `global` (legacy recall) or `project` (isolated recall); other values are rejected |

Precedence: **env vars > file config > defaults**

### Config File Location

`$HERMES_HOME/ai-memory.json`

The file (and `.ai-memory.toml`) is read as UTF-8 with an optional BOM, as PowerShell 5.1 writes.

### Environment Variables

| Variable | Default | Effect |
|---|---|---|
| `AI_MEMORY_SERVER_URL` | `http://127.0.0.1:49374` | server address |
| `AI_MEMORY_API_KEY` | `""` | Bearer token (env-only, never persisted) |
| `AI_MEMORY_AUTH_TOKEN` | `""` | Bearer token alias (env-only, never persisted) |
| `AI_MEMORY_WORKSPACE` | `""` | explicit workspace, outranking marker and derivation |
| `AI_MEMORY_PROJECT` | `""` | explicit project, outranking marker and derivation |
| `AI_MEMORY_CWD` | `""` | session directory, outranking the Hermes `cwd` kwarg and `resolve_agent_cwd()` |
| `AI_MEMORY_SEARCH_SCOPE` | `global` | `global` or `project` |

### Scope Resolution

`initialize()` resolves the session directory first, then each scope field.

**Session directory** (absolute and existing, never `os.getcwd()`):

1. `AI_MEMORY_CWD`
2. the `cwd` kwarg from Hermes (only supplied when `agent.session_cwd` is set)
3. `agent.runtime_cwd.resolve_agent_cwd()` — guarded import, absent when Hermes is not importable

A path must be absolute and existing. An invalid `AI_MEMORY_CWD` fails closed rather than falling through to the kwarg or `resolve_agent_cwd()`, and the plugin never uses `os.getcwd()`.

**Scope** — `config.resolve_scope(cwd, *, explicit_workspace="", explicit_project="")` applies **explicit > marker > derived** per field and returns `workspace`, `project`, `workspace_source`, `project_source` (each `explicit`, `marker`, `derived`, or empty) and `source` (the project's source when a project resolved, else the workspace's). It returns `{}` for an unusable directory.

1. **Explicit** — `ai_memory_workspace` / `project` kwargs, `workspace` / `project` in `ai-memory.json`, or `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`. A non-default programmatic `AiMemoryConfig.project` is treated as explicit for derivation, but never outranks a marker.
2. **Marker** — the nearest `.ai-memory.toml` settings boundary at or above the session directory.
3. **Derived** — when the marker pins `workspace` but no `project`, the project comes from the checkout's git remote (`upstream` first, then `origin`), normalized to the hostless repository path, lowercased, with `/` written as `-` (`git@github.com:acme/movvia.git` → `acme-movvia`; project names never contain `/`). Without a valid remote, `basename(cwd)` is used.

**Marker walk rules:**

- The walk boundary is `$HOME` when the directory is inside it. Outside `$HOME` it stops at the nearest checkout root (a directory containing `.git`, file or directory, including worktrees/submodules); a non-git directory outside `$HOME` checks only itself.
- The boundary is the first marker that declares **more than `[capture]`**, matching upstream's `declares_more_than_capture`. A `[briefing]`-only or otherwise settings-bearing marker is a boundary, so an outer marker's project does not leak through.
- A capture-only marker is transparent. A routes-only marker is also transparent: routes are not settings.
- Markers are read as UTF-8 with an optional BOM; a leading BOM does not hide `workspace`/`project`.

**Authorization.** Writes, mirroring, turn/session hooks and handoff consumption require a non-empty workspace and project, plus one of:

| Project provenance | Workspace provenance | Writes |
|---|---|---|
| `explicit` or `marker` | any | yes |
| `derived` | `explicit` or `marker` | yes |
| `derived` | empty | no (read-only) |
| empty (dataclass default only) | any | no (read-only) |

A project that is only the dataclass default (`hermes-default`), or a `derived` project with no explicit/marker workspace, does not authorize writes. An unusable directory resolves no scope and stays read-only. A repository needs **either** an `.ai-memory.toml` marker pinning `workspace` **or** an explicit `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` pin before the plugin can write; without one it is intentionally read-only.

The documented workspace-only marker (`.ai-memory.toml` requires `workspace`, `project` is optional) therefore authorizes writes via a derived project. Repositories that previously resolved no project now write to the derived one; pages written earlier under `hermes` / `hermes-default` are no longer found by project-scoped recall. See [Migration](../README.md#migration-workspace-only-markers).

`search_scope=global` preserves legacy global search; `search_scope=project` applies the resolved scope to every provider search/prefetch. Unknown scope in project mode returns an error/empty recall, never global results.

**No dynamic directory-scope switching:** the memory-provider contract supplies the session directory at `initialize()`, not the updated live agent cwd. A new initialized provider with the target directory is required; `on_session_switch()` updates the session ID and invalidates recall, but does not re-resolve cwd. See the [Hermes contract](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin).

Legacy-generated default pairs are exempt from explicit file precedence only in project mode and only for the narrow format documented in [Legacy scope defaults](../README.md#legacy-scope-defaults-and-explicit-overrides). `scope_origin=explicit` preserves an intentional default pair; saving nonblank scope values records that metadata. Install/update defaults and blank setup answers do not pin projects. Loading never writes migration changes to the profile.

### Config Schema (for `hermes memory setup`)

| Key | Secret | Env Only | Env Var | Default |
|---|---|---|---|---|
| `server_url` | no | no | — | `http://127.0.0.1:49374` |
| `api_key` | yes | yes | `AI_MEMORY_API_KEY` | `""` |
| `auth_token` | yes | yes | `AI_MEMORY_AUTH_TOKEN` | `""` |
| `workspace` | no | no | `AI_MEMORY_WORKSPACE` | `""` (directory routing) |
| `project` | no | no | `AI_MEMORY_PROJECT` | `""` (directory routing) |
| `search_scope` | no | no | `AI_MEMORY_SEARCH_SCOPE` | `"global"` |

**Env Only** fields are never written to `ai-memory.json`. They must be set via environment variables.

## `AiMemoryClient`

Typed HTTP wrapper in `client.py`. Accepts `AiMemoryConfig`. Persistent `httpx.Client` with connection pooling.

### Methods

#### `search(query, workspace=None, project=None, limit=3) → list[dict]`

**HTTP:** `GET /admin/search?q=<query>&limit=<n>&workspace=<ws>&project=<proj>`  
**Timeout:** 5s (`SEARCH_TIMEOUT`, under Hermes' ~8s prefetch abandonment bound)  
**Raises:** `httpx.HTTPStatusError` on non-2xx

Scope is all-or-nothing: the pair is sent only when both are non-empty, and a lone `workspace` or `project` is rejected upstream with HTTP 400 (`workspace and project must be provided together`). Passing neither searches globally.

Hits upstream are `PageHit { id, path, title, snippet, rank }`; global hits additionally carry `workspace` and `project`. The relevance field is **`rank`** — there is no `score`.

#### `write_page(path, body, tags=None, tier=None, pinned=False, workspace="", project="") → dict`

**HTTP:** `POST /admin/write-page`  
**Timeout:** 10s  
**Raises:** `ValueError` locally when `workspace` or `project` is empty; `httpx.HTTPStatusError` on non-2xx

Both scope fields are required by the server. The plugin fails locally with a clear error rather than sending an incomplete body the server would reject with 422.

Returns `{ "page_id": "...", "path": "...", "checkpoint"?: ..., "manifest_warning"?: ... }`. There is no `ok` field; `page_id` is authoritative.

#### `status() → dict`

**HTTP:** `GET /admin/status`  
**Timeout:** 5s

Returns the server's status report. The lifetime counters are nested under `counts` (`pages_latest`, `pages_all`, `sessions`, `observations`, `evidence_rows`), alongside `version` and `data_dir`.

#### `send_hook(event, session_id, payload=None, workspace=None, project=None, cwd=None, timeout=None) → None`

**HTTP:** `POST /hook?event=<event>&session_id=<sid>&workspace=<ws>&project=<proj>&cwd=<cwd>`  
**Timeout:** `timeout` when given, else `HOOK_TIMEOUT` (0.5s); the provider passes `SESSION_END_TIMEOUT` (10s) for `session-end`  
**Errors:** Swallowed (logged at exception level)

Dropped without a request while the client is paused: after `FAILURE_THRESHOLD` (3) consecutive transport failures it stops calling the server for `COOLDOWN_SECONDS` (60s), and `last_failure()` explains why. A successful request clears that state.

#### `fetch_handoff(agent="hermes", cwd=None, workspace=None, project=None) → str | None`

**HTTP:** `GET /handoff?agent=<agent>&cwd=<cwd>&workspace=<ws>&project=<proj>`  
**Timeout:** 2.0s (`HANDOFF_TIMEOUT`)  
**Returns:** the markdown handoff, or `None` for a blank body

The server returns **HTTP 200 with an empty body** when there is no handoff, so the empty-body path — not only 404 — is the real no-handoff signal. A `403` means a handoff exists but was refused and is raised like any other non-2xx.

The server also accepts `briefing`, `briefing_budget`, `session_id` and the identity fields; this client sends `briefing`/`briefing_budget` when the marker opts into `[briefing] inject_on_session_start`.

## `AiMemoryProvider`

Implements `MemoryProvider` ABC in `provider.py`.

### Properties

- `name → "ai-memory"`

### Methods

- `is_available() → bool` — checks `server_url` is non-empty
- `unavailable_reason() → str` — the missing `server_url`, or the recorded transport failure; `""` while healthy
- `initialize(session_id, **kwargs)` — resolves the session directory and scope, reloads config, fetches the handoff once (skipped in non-primary contexts)
- `get_config_schema() → list[dict]`
- `save_config(values, hermes_home) → list[str]` — returns list of skipped secret keys. Upstream declares `save_config` as `-> None`; this provider returns the skipped list, which is the documented real behaviour here.
- `get_tool_schemas() → list[dict]` — OpenAI function schemas (the `parameters` key)
- `handle_tool_call(name, args) → str` (returns JSON string)
- `system_prompt_block() → str`
- `prefetch(query, *, session_id="") → str` — consumes the newest queued recall for the session+scope (exact-query entry first), else searches; each hit is labelled `title (path): snippet`
- `queue_prefetch(query, *, session_id="")` — background worker; captures client/scope and caches the newest result per `(session_id, search_scope, workspace, project)` plus an exact-query alias; initialization/session switches discard stale results
- `recall_status() → RecallStatus | None` — hit count of the last `prefetch`, `None` when it injected nothing
- `sync_turn(user, assistant, *, session_id="", **kwargs)` — background worker
- `on_session_end(messages, **kwargs)` — background worker; sends the session id, never the transcript
- `on_memory_write(action, target, content, metadata=None)` — mirrors `add` / `replace` asynchronously on a background worker; `remove` is skipped
- `shutdown()` — joins this provider's tracked background workers under a bounded 5s deadline
- `scope_diagnostics() → dict` — local, allowlisted snapshot: `cwd_received`, `cwd_source`, `cwd_normalized`, `search_scope`, `workspace`, `project`, `workspace_source`, `project_source`, `scope_known`, `writes_allowed`, `project_search_allowed`

Background workers use Hermes' `agent.memory_provider.spawn_context_thread` when importable (inheriting contextvars for profile isolation and per-turn secret scope) and fall back to a daemon thread. Threads are tracked so `shutdown()` can join them; Hermes' own drain only covers its manager executor.

## CLI (`register_cli`)

Registered via `register_cli(subparsers)` in `cli.py`.

### Subcommands

#### `hermes ai-memory status`

Checks ai-memory server reachability. Prints the server version and the page / session / observation counts read from `counts`.

#### `hermes ai-memory config`

Displays active config values (secrets show their source: env var or not set).

#### `hermes ai-memory config-set <key> <value>`

Sets a config value. Secrets (`api_key`, `auth_token`) are rejected with instructions to use the corresponding environment variable instead.

#### `hermes ai-memory link`

Creates a symlink `$HERMES_HOME/plugins/ai-memory → <plugin_dir>`.

## `plugin.yaml`

```yaml
name: ai-memory
version: 0.1.4
description: "ai-memory wiki-backed long-term memory provider"
kind: exclusive
python_dependencies:
  - httpx
```

## `register(ctx)`

Entry point in `__init__.py`:

1. Resolves config: file (`$HERMES_HOME/ai-memory.json`) → env var overrides (env wins for secrets)
2. Creates `AiMemoryConfig` with merged values (secrets env-only, never persisted)
3. Instantiates `AiMemoryProvider(config=config)`
4. Calls `ctx.register_memory_provider(provider)`

## Install Scripts

| Platform | Script | Requirements | Behavior |
|---|---|---|---|
| Linux/macOS | `scripts/install.sh` | `curl`, `tar` | Symlinks plugin from local repo; downloads from GitHub when run via `bash <(curl ...)` |
| Windows | `scripts/install.ps1` | PowerShell 5.1+ with .NET | Creates junction from local repo; downloads from GitHub when run via `iex` |
| Linux/macOS | `scripts/uninstall.sh` | `bash` | Removes plugin directory/symlink; disables plugin in Hermes if CLI exists |
| Windows | `scripts/uninstall.ps1` | PowerShell 5.1+ | Removes plugin directory/junction; disables plugin in Hermes if CLI exists |
| Linux/macOS | `scripts/update.sh` | `curl`, `tar` | Downloads latest plugin from GitHub, backs up old install, preserves config |
| Windows | `scripts/update.ps1` | PowerShell 5.1+ with .NET | Downloads latest plugin from GitHub, backs up old install, preserves config |

All scripts run **pre-flight checks** before making changes:

1. Hermes CLI availability (warn if missing)
2. Hermes process status (warn if running — restart needed)
3. ai-memory server reachability (try `/admin/status` endpoint)
4. Existing plugin state (installed? symlink/copy? empty?)
5. Write permissions to `$HERMES_HOME/plugins/`
6. Config file existence and contents
7. Wrong nested path detection (`plugins/memory/ai-memory/`)

### Script Flags

| Flag | Bash | PowerShell | Env var | Description |
|---|---|---|---|---|
| Dry run | `--dry-run` | `-DryRun` | — | Show what would happen without making changes |
| Skip prompts | `--yes` | `-Yes` | `FORCE=true` | Skip confirmation prompts (for CI/automation) |
| Help | `--help` | — | — | Show usage information |

When piped (non-interactive), scripts detect the missing TTY, print a warning, and proceed. Set `FORCE=true` or pass `--yes`/`-Yes` to silence the warning.

### Environment Variables

| Variable | Used By | Description |
|---|---|---|
| `HERMES_HOME` | install/uninstall | Hermes profile directory (default: `~/.hermes` / `%USERPROFILE%\.hermes`) |
| `AI_MEMORY_SERVER_URL` | install | Initial `server_url` written to `ai-memory.json` |
| `REPO_TARBALL_URL` | install | Override the GitHub tarball/zip URL used by the one-liner fallback |
| `REMOVE_CONFIG` | uninstall (bash) | Set to `true` to delete `$HERMES_HOME/ai-memory.json` |
| `FORCE` | all scripts | Set to `true` to skip confirmation prompts (same as `--yes` / `-Yes`) |
| `DRY_RUN` | all scripts | Set to `true` to enable dry-run mode (same as `--dry-run` / `-DryRun`) |

## Quality Gates

| Check | Command | Target |
|---|---|---|
| Lint | `ruff check .` | 0 errors |
| Types | `mypy .` | 0 issues |
| Tests | `pytest -q` | 277 passed, 3 skipped |
| Coverage | `pytest --cov` | configured `fail_under = 89` |
