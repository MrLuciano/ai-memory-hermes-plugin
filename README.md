# ai-memory Hermes Memory Provider Plugin

Connects [Hermes Agent](https://github.com/NousResearch/hermes-agent) to [ai-memory](https://github.com/akitaonrails/ai-memory) as a first-class `MemoryProvider` plugin — automatic prefetch, turn sync, session finalization, and wiki search/write tools.

## Features

- **Background prefetch** — each turn's recall search runs on a tracked background worker after the turn and is injected before the next one
- **Turn capture** — background sync after each completed turn
- **Session finalization** — `session-end` hook on conversation close (the session id only, never the transcript)
- **Memory mirroring** — built-in `MEMORY.md` / `USER.md` writes (`add`, `replace`) mirrored to the ai-memory wiki asynchronously
- **Hermes CLI integration** — `hermes memory setup` plus the plugin's own `hermes ai-memory status | config | config-set | link | update`
- **Scope that matches the other agents** — explicit config, then the nearest `.ai-memory.toml`, then a project derived from the checkout's git remote (or directory name)
- **Safe in non-primary runs** — cron/subagent providers neither write nor consume the single-use handoff
- **3 tool schemas** — `ai_memory_search`, `ai_memory_write`, `ai_memory_status`
- **277 passing tests** (3 skipped) — linted with ruff, type-checked with mypy

## Quick Start

```bash
# Quick install via script (Linux/macOS)
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)

# Load the plugin (registers it with Hermes)
hermes plugins enable ai-memory

# Activate it as the memory provider (sets memory.provider)
hermes memory setup

# Verify
hermes memory status
```

`hermes plugins enable ai-memory` only makes the plugin available; it does not activate a memory provider. `plugins.enabled` is unrelated to memory-provider activation, and Hermes skips `exclusive` plugins in the general enabled-check. Activation is `hermes memory setup` (which sets `memory.provider`) or `memory.provider: ai-memory` in `config.yaml`; the plugin must also be enabled so Hermes loads it at all.

Or download and run `scripts/install.sh` (Linux/macOS) or `scripts/install.ps1` (Windows) from the repository.

## Architecture

```
Hermes Agent → MemoryProvider ABC → AiMemoryProvider → AiMemoryClient → HTTP → ai-memory server
```

| Layer | File | Role |
|---|---|---|
| `__init__.py` | Entry point | `register()` — loads config, creates provider, calls `ctx.register_memory_provider()` |
| `provider.py` | AiMemoryProvider | Implements `MemoryProvider` ABC; lifecycle hooks, tool dispatch |
| `client.py` | AiMemoryClient | Typed HTTP wrapper; search, write page, send hook, fetch handoff |
| `config.py` | AiMemoryConfig | Config dataclass + JSON persistence + env-var fallback + secret filtering |
| `cli.py` | CLI | `status`/`config`/`link` subcommands for `hermes memory` |
| `plugin.yaml` | Manifest | Metadata + `python_dependencies` (Hermes validates but never installs) |

## Lifecycle

| Hermes hook | ai-memory call | Threading |
|---|---|---|
| `is_available()` | Checks `server_url` is configured | Sync |
| `initialize()` | Resolves workspace/project, fetches the handoff once | Sync |
| `prefetch(query, session_id)` | Consumes `queue_prefetch`'s cache, else `GET /admin/search` | Sync |
| `queue_prefetch(query, session_id)` | `GET /admin/search` cached for the next turn | Background worker |
| `recall_status()` | Hit count of the last `prefetch`, for the recall indicator | Sync |
| `sync_turn(user, assistant)` | `POST /hook?event=user-prompt-submit` | Background worker |
| `on_session_end(messages)` | `POST /hook?event=session-end` (session id only) | Background worker |
| `on_memory_write(action, target, content)` | `POST /admin/write-page` for `add` / `replace` | Background worker (async) |
| `handle_tool_call(name, args)` | Routes to search/write/status | Sync |

Background workers prefer Hermes' `agent.memory_provider.spawn_context_thread` (contextvars, profile isolation) and fall back to a daemon thread when Hermes is not importable. Threads are tracked, and `shutdown()` joins them under a bounded 5s deadline so a session-end POST is not killed at process exit.

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AI_MEMORY_SERVER_URL` | `http://127.0.0.1:49374` | ai-memory server address |
| `AI_MEMORY_API_KEY` | `""` | API key (sent as Bearer token) — **env-only, never written to disk** |
| `AI_MEMORY_AUTH_TOKEN` | `""` | Auth token (alias for api_key) — **env-only, never written to disk** |
| `AI_MEMORY_WORKSPACE` | `""` | Workspace name, overriding the file and the `.ai-memory.toml` marker |
| `AI_MEMORY_PROJECT` | `""` | Project name, overriding the file and the `.ai-memory.toml` marker |
| `AI_MEMORY_CWD` | `""` | Session directory, overriding the Hermes `cwd` kwarg and `resolve_agent_cwd()` |
| `AI_MEMORY_SEARCH_SCOPE` | `global` | Search/recall mode: `global` or `project` |

Env vars override file config, which overrides defaults. Secrets (`api_key`, `auth_token`) are **never persisted to `ai-memory.json`** — they must be set via environment variables.

### Config File (`$HERMES_HOME/ai-memory.json`)

Written by `hermes memory setup` wizard. Only non-secret values are stored:

```json
{
  "server_url": "http://127.0.0.1:49374",
  "search_scope": "global"
}
```

`workspace`/`project` overrides set here (except the legacy-generated pair described below), or via `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`, are explicit: they win over the nearest applicable `.ai-memory.toml` at or above the absolute, existing session directory supplied during initialization.

`search_scope` is optional: `global` preserves legacy searches across all projects; `project` restricts search tools and both recall paths to the resolved project. For folder isolation with a single profile, use `{"search_scope": "project"}` and omit fixed workspace/project overrides so the markers can route each new session. A nested marker in `imperio_2026/apps/socorro_financeiro` takes precedence over the root marker.

When the resolved directory is unusable, or neither workspace nor project resolves, project searches return no results and writes (including mirrors, lifecycle hooks and handoff consumption) are blocked. A configured non-default project remains supported. Resolved scope from a previous initialization is never a fallback for the next one.

### Session directory

Hermes only adds `cwd` to the provider initialization kwargs when `agent.session_cwd` is set; the interactive CLI does not set it. The plugin resolves the session directory in this order:

1. `AI_MEMORY_CWD` (explicit override)
2. the `cwd` kwarg from Hermes
3. `agent.runtime_cwd.resolve_agent_cwd()` (guarded import; unavailable when Hermes is not importable)

The directory must be absolute and existing. The plugin never falls back to `os.getcwd()`, and an invalid `AI_MEMORY_CWD` fails closed rather than falling through to another directory. `scope_diagnostics()["cwd_source"]` reports which path was used: `environment`, `kwargs`, `runtime`, or empty when nothing resolved.

### Scope resolution and provenance

`config.resolve_scope(cwd, *, explicit_workspace="", explicit_project="")` resolves each field with precedence **explicit > marker > derived** and returns `workspace`, `project`, `workspace_source` / `project_source` (`explicit`, `marker`, `derived`, or empty) and `source`.

- **Explicit** — `workspace`/`project` in `ai-memory.json`, `AI_MEMORY_WORKSPACE`/`AI_MEMORY_PROJECT`, or initialization kwargs.
- **Marker** — the nearest `.ai-memory.toml` settings boundary at or above the session directory. A capture-only marker is transparent; the first marker that declares any other setting is the boundary, so an outer project does not leak through a `[briefing]`-only or otherwise settings-bearing marker.
- **Derived** — when the marker pins `workspace` but no `project`, the project comes from the checkout's git remote (`upstream`, else `origin`), normalized to the hostless repository path, lowercased, with `/` written as `-` (`git@github.com:acme/movvia.git` → `acme-movvia`; project names never contain `/`). With no valid remote, `basename(cwd)` is used.

Writes, mirroring, turn/session hooks and handoff consumption are authorized only when workspace and project both resolve non-empty and:

| Project provenance | Workspace provenance | Writes |
|---|---|---|
| `explicit` or `marker` | any | yes |
| `derived` | `explicit` or `marker` | yes |
| `derived` | empty | no (read-only) |
| empty (dataclass default only) | any | no (read-only) |

An unusable directory resolves no scope and stays read-only. A project that is only the dataclass default (`hermes-default`) with no provenance does not authorize writes, and neither does a derived project with no explicit/marker workspace. A repository therefore needs **either** an `.ai-memory.toml` marker pinning `workspace` **or** an explicit `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` pin before the plugin can write memory; without one it is intentionally read-only.

### Migration: workspace-only markers

`.ai-memory.toml` marks `workspace` as required and `project` as optional. Before 0.1.4 the plugin required an explicit project, so the documented workspace-only marker silently made the session read-only (recall still worked, so the failure was invisible). The plugin now derives the project, which is a breaking change for existing data:

- New memories for a repository that previously resolved no project now land in the git-remote-derived ai-memory project (for example `acme-movvia`).
- Anything previously written under `hermes` / `hermes-default` for such a repository is no longer found by project-scoped recall. Those pages still exist in ai-memory under the old project.
- Inspect the resolved scope and its provenance with `scope_diagnostics()` (see [Windows directory scope](docs/directory-scope-windows.md)).
- To keep the previous scope, pin it explicitly via `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`, `workspace`/`project` in `$HERMES_HOME/ai-memory.json`, or the initialization kwargs. Explicit values override marker and derivation.

**Changing folders during an existing session does not update this provider's scope.** Start a new provider/session initialized with the target directory; switching the session ID alone is insufficient. The plugin resolves the session directory at initialization (see [Session directory](#session-directory)) and never infers it from `os.getcwd()`. See [Scope Resolution](docs/reference.md#scope-resolution).

### Legacy scope defaults and explicit overrides

New installers/updaters omit fixed workspace/project values. In `hermes memory setup`, leave those prompts blank for directory routing; `search_scope` accepts only `global` or `project`. `hermes ai-memory config` also displays the read policy (not the session-specific TOML resolution).

For old files, a narrow compatibility rule applies **only in project mode** (including `AI_MEMORY_SEARCH_SCOPE=project`): the complete pair `workspace=hermes`, `project=hermes-default`, with no keys other than `server_url`, `workspace`, `project`, `search_scope`, `scope_origin`, is treated as automatic unless `scope_origin=explicit`. Resolution does not rewrite the file. Global mode is unchanged. Single-key overrides, custom values, additional configuration keys, environment variables and initialization kwargs remain explicit.

The old format cannot prove whether an identical pair was installed automatically or typed manually. For an intentional fixed pair, set `hermes ai-memory config-set scope_origin explicit` **before enabling project mode**, or re-save the workspace/project with `config-set`. Saving a nonblank scope via setup/CLI records `scope_origin=explicit`; `automatic` is also accepted, but never demotes customized values. Blank scope inputs remove those file overrides. Invalid origin/policy values are rejected before saving.

For automatic folder routing, set `hermes ai-memory config-set search_scope project` and leave scope overrides unset. Each new provider resolves the intended absolute directory from `AI_MEMORY_CWD`, the Hermes `cwd` kwarg, or `resolve_agent_cwd()`; scope does not change dynamically within an existing provider.

### Secrets & Security

`api_key` and `auth_token` are treated as **env-only secrets**:
- They are **never written** to `ai-memory.json` by `save_config()` or `hermes memory setup`
- If they already exist in the JSON file (e.g. from a previous version), they are **stripped on next load**
- Set them via environment variables and add to your shell profile or systemd environment:

```bash
# Shell profile (~/.bashrc, ~/.zshrc, etc.)
export AI_MEMORY_API_KEY=sk-your-key-here
export AI_MEMORY_AUTH_TOKEN=your-token-here

# Or systemd
Environment="AI_MEMORY_API_KEY=sk-your-key-here"
```

The CLI shows where each secret is sourced from:

```bash
hermes ai-memory config
# → auth_token: (set via env: AI_MEMORY_AUTH_TOKEN)
# → api_key:    (not set)
```

Attempting to write a secret via `hermes ai-memory config-set` shows the env var to use instead:

```bash
hermes ai-memory config-set auth_token my-secret
# → NOT WRITTEN TO DISK: auth_token is a secret — use an environment variable:
#   export AI_MEMORY_AUTH_TOKEN='my-secret'
```

## Tools

| Tool | Description | Parameters |
|---|---|---|
| `ai_memory_search` | Search the wiki | `query` (req), `max_results` (opt, default 5) |
| `ai_memory_write` | Write a new wiki page | `path` (req), `body` (req), `tags` (opt) |
| `ai_memory_status` | Server health check | none |

## Development

```bash
uv sync
uv run ruff check .
uv run mypy .
uv run pytest --cov
```

### Project Structure

```
plugins/memory/ai-memory/
├── __init__.py       # Entry point — register()
├── plugin.yaml       # Hermes manifest
├── provider.py       # AiMemoryProvider
├── client.py         # AiMemoryClient (httpx)
├── config.py         # AiMemoryConfig + persistence
├── cli.py            # CLI subcommands
└── README.md         # In-plugin readme
tests/
├── test_config.py           # 29 tests
├── test_client.py           # 32 tests
├── test_provider.py         # 48 tests
├── test_entry.py            # 14 tests
├── test_cli.py              # 18 tests
├── test_1281_compat.py      # 38 tests
├── test_legacy_scope.py     # 24 tests
├── test_directory_scope.py  # 39 tests
├── test_scope_derivation.py # 29 tests
└── test_cwd_diagnostics.py  # 9 tests
```

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server (HTTP API at port 49374)
- `httpx >= 0.28`

The HTTP contract (routes, event names, the `prompt` body field, markdown handoff, Bearer auth and the `counts` status keys) is verified against ai-memory **3.2.0 (3.x)**.

## Deployment

### Install Scripts

| Platform | Script | Method |
|---|---|---|
| Linux/macOS | [`scripts/install.sh`](scripts/install.sh) | Bash — symlinks or copies plugin into `$HERMES_HOME`, writes initial config |
| Windows | [`scripts/install.ps1`](scripts/install.ps1) | PowerShell — creates NTFS junction or copies, writes initial config |

All scripts support **pre-flight checks**, **dry-run**, and **confirmation prompts**:

| Flag | Bash | PowerShell | Env var | Description |
|---|---|---|---|---|
| Dry run | `--dry-run` | `-DryRun` | — | Show what would happen without making changes |
| Skip prompts | `--yes` | `-Yes` | `FORCE=true` | Skip all confirmation prompts (for CI/automation) |

When piped (non-interactive), scripts detect the missing TTY and proceed with a warning. Set `FORCE=true` or pass `--yes`/`-Yes` to silence the warning.

Pre-flight checks verify: Hermes CLI availability, Hermes process status, ai-memory server reachability, plugin state, write permissions, and existing config.

### One-liner (Linux/macOS)

Requires `curl` and `tar`. The script downloads the plugin from GitHub when run via `curl`, then copies it into `$HERMES_HOME/plugins/ai-memory`.

```bash
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)
```

Preview what the install would do (dry-run):

```bash
bash <(curl -sL .../install.sh) --dry-run
```

Skip confirmation prompts for automation:

```bash
FORCE=true bash <(curl -sL .../install.sh)
```

Set `AI_MEMORY_SERVER_URL` before running to override the default server address:

```bash
AI_MEMORY_SERVER_URL=http://10.0.0.42:49374 bash <(curl -sL ...)
```

### Windows (PowerShell)

Requires PowerShell 5.1+ with .NET (default on Windows 10/11 and Windows Server 2016+). The script downloads the plugin from GitHub when run via `iex`, then copies it into `$HERMES_HOME\plugins\ai-memory`.

```powershell
powershell -c "iex ((Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.ps1').Content)"
```

With custom server URL:

```powershell
powershell -c "$env:ServerUrl='http://10.0.0.42:49374'; iex ((Invoke-WebRequest -Uri '...').Content)"
```

### Uninstall

Removes the plugin from `$HERMES_HOME/plugins/ai-memory` and runs `hermes plugins disable ai-memory` if the Hermes CLI is available. The `ai-memory.json` config file is kept unless you pass the removal flag.

Linux/macOS:

```bash
bash scripts/uninstall.sh
# Dry-run (preview only):
bash scripts/uninstall.sh --dry-run
# Skip prompt:
bash scripts/uninstall.sh --yes
# Also remove config:
REMOVE_CONFIG=true bash scripts/uninstall.sh
```

Windows (PowerShell):

```powershell
.\scripts\uninstall.ps1
# Dry-run (preview only):
.\scripts\uninstall.ps1 -DryRun
# Skip prompt:
.\scripts\uninstall.ps1 -Yes
# Also remove config:
.\scripts\uninstall.ps1 -RemoveConfig
```

### Update

Fetches the latest plugin files from GitHub, backs up the current install to `$HERMES_HOME/.ai-memory-backups/ai-memory.bak.<timestamp>`, replaces the plugin, and preserves `ai-memory.json`.

Linux/macOS:

```bash
bash scripts/update.sh
# Dry-run (preview only):
bash scripts/update.sh --dry-run
# Skip prompt:
bash scripts/update.sh --yes
# Or via one-liner:
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/update.sh)
```

Windows (PowerShell):

```powershell
.\scripts\update.ps1
# Dry-run (preview only):
.\scripts\update.ps1 -DryRun
# Skip prompt:
.\scripts\update.ps1 -Yes
```

Update from a local clone (preserves symlink/junction):

```bash
UPDATE_FROM_LOCAL=true bash scripts/update.sh
```

```powershell
$env:UPDATE_FROM_LOCAL="true"; .\scripts\update.ps1
```

The CLI also provides `hermes ai-memory update`, which downloads and replaces the plugin from GitHub.

### uv pip install (from repo)

If you have `uv` and are deploying from a local clone:

```bash
uv pip install --system -e "$PWD"  # installs httpx dependency
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"
```

More detailed deployment instructions in [docs/guide.md](docs/guide.md#deployment).

## References

- [Hermes Memory Provider Plugin docs](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin)
- [ai-memory repository](https://github.com/akitaonrails/ai-memory)
- [docs/guide.md](docs/guide.md) — usage guide
- [docs/reference.md](docs/reference.md) — full API reference
- [docs/common-problems.md](docs/common-problems.md) — troubleshooting
