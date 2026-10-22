# Usage Guide

## Installation

### 1. Start ai-memory server

```bash
# Install ai-memory (see https://github.com/akitaonrails/ai-memory)
ai-memory serve

# Default: http://127.0.0.1:49374
```

### 2. Install the plugin

```bash
# Copy into your Hermes profile
cp -r plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"

# Or symlink for development
python -m plugins.memory.ai_memory.cli link
```

**Quick one-liner (Linux/macOS):**

```bash
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)
```

**Using uv pip (pre-installs httpx):**

```bash
uv pip install --system -e /path/to/ai-memory-hermes-plugin
cp -r plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"
```

### 3. Load the plugin

```bash
hermes plugins enable ai-memory
```

This registers the plugin with Hermes; it does **not** activate a memory provider. `plugins.enabled` is unrelated to memory-provider activation, and Hermes skips `exclusive` plugins in the general enabled-check.

### 4. Activate the memory provider

```bash
hermes memory setup
```

The wizard sets `memory.provider: ai-memory` and prompts for server URL, API key (optional), and workspace/project. Leave the scope prompts blank to use directory routing.

### 5. Verify

```bash
hermes ai-memory status
# → ai-memory server: reachable
#   Version:      3.2.0
#   Pages:        42
#   Sessions:     7
#   Observations: 318
```

## Configuration

### Server URL

If ai-memory runs on a different host or port, set:

```bash
export AI_MEMORY_SERVER_URL=http://10.0.0.42:49374
```

Or use the `hermes memory setup` wizard.

### Authentication

Optional Bearer auth via environment variables (secrets are **never written to disk**):

```bash
export AI_MEMORY_API_KEY=sk-...
export AI_MEMORY_AUTH_TOKEN=your-token-here
```

Add to your shell profile for persistence:

```bash
# ~/.bashrc or ~/.zshrc
export AI_MEMORY_API_KEY=sk-...
```

Or via systemd environment:

```ini
[Service]
Environment="AI_MEMORY_API_KEY=sk-..."
```

Verify which source is active:

```bash
hermes ai-memory config
# → auth_token: (set via env: AI_MEMORY_AUTH_TOKEN)
# → api_key:    (not set)
```

**Note:** Attempting `hermes ai-memory config-set auth_token value` will show the env var to use instead — secrets are never persisted to `ai-memory.json`.

### Project Isolation

The provider writes to the resolved project. Reads remain global by default for compatibility; choose `search_scope=project` to restrict searches and recall to that project.

`initialize()` resolves the session directory, then each scope field:

1. **Session directory** — `AI_MEMORY_CWD`, then the Hermes `cwd` kwarg, then `agent.runtime_cwd.resolve_agent_cwd()`. It must be absolute and existing; an invalid `AI_MEMORY_CWD` fails closed, and there is no `os.getcwd()` fallback.
2. **Scope** — precedence is **explicit > marker > derived**:
   - Explicit: `ai_memory_workspace` / `project` kwargs, `workspace` / `project` in `$HERMES_HOME/ai-memory.json`, or `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`.
   - Marker: the nearest `.ai-memory.toml` settings boundary at or above the session directory. A capture-only marker is transparent; the first marker declaring any other setting is the boundary.
   - Derived: a marker that pins `workspace` but no `project` derives the project from the checkout's git remote (`upstream`, else `origin`), normalized to the hostless repository path, lowercased, with `/` written as `-` (project names never contain `/`), or `basename(cwd)` when there is no valid remote.

Writes, mirroring, turn/session hooks and handoff consumption require both fields and authorize a `derived` project only when the workspace is `explicit` or `marker`. A project that is only the dataclass default (`hermes-default`), or a project derived with no explicit/marker workspace, stays read-only. An unusable directory also stays read-only. A repository needs **either** an `.ai-memory.toml` marker pinning `workspace` **or** an explicit `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` pin before the plugin can write memory; without one it is intentionally read-only. The full provenance table is in the [README](../README.md#scope-resolution-and-provenance).

For legacy-generated `hermes` / `hermes-default` pairs, see the deterministic [compatibility rule and explicit opt-out](../README.md#legacy-scope-defaults-and-explicit-overrides). New installers leave scope unset; leave setup scope prompts blank to use markers.

**Migration (0.1.4).** A workspace-only `.ai-memory.toml` now resolves a project instead of failing closed. New memories for such a repository land in the git-remote-derived project (for example `acme-movvia`); pages previously written under `hermes` / `hermes-default` are no longer found by project-scoped recall, though they remain in ai-memory under the old project. Pin the old scope explicitly via `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`, `ai-memory.json`, or the initialization kwargs. `scope_diagnostics()` reports the resolved scope and its provenance.

For a single profile with folder-based memory, set `search_scope` to `project` in `ai-memory.json` (or `AI_MEMORY_SEARCH_SCOPE`) and omit fixed workspace/project overrides. The nearest applicable marker above the absolute, existing session directory wins, including markers within monorepo applications.

With no project marker, no derivable project and no configured project, writes and handoff consumption are blocked. Explicit default-project configuration is still supported. Project-mode recall with unknown scope returns no results rather than falling back to global search.

Folder changes inside an existing session do **not** re-resolve this provider's scope. Start a new provider/session initialized with the target folder; `/new` or `/reset` that only switches the ID does not change folder scope. No process-cwd fallback is used.

## Lifecycle Behavior

### Session Start (`initialize`)

When a new conversation starts, the provider resolves the scope (above) and fetches the previous session's handoff once, so `system_prompt_block()` can surface it. The fetch has a 2.0s timeout. Non-primary contexts (`agent_context` other than `primary`) skip that fetch — accepting a handoff is single-use.

### Before Each Turn (`prefetch`)

The agent calls `prefetch(query, session_id=...)` with the user's message. The provider:

1. Consumes the newest queued recall for the same session and scope, even when the query text changed (Hermes queues with the completed turn's text and prefetches with the next turn's text); an exact-query entry is consumed first when present
2. Otherwise searches the wiki with `GET /admin/search?q=<query>&limit=3`
3. Returns one block per hit, labelled `title (path): snippet` — recall spans every project, so the block names where each fact came from

Search calls time out after 5s, deliberately under Hermes' ~8s prefetch abandonment bound; a slower result would be discarded. `queue_prefetch(query, session_id=...)` runs the search on a tracked background worker right after a turn. The cache keeps the newest queued recall per session+scope plus an exact-query alias, which is what makes the next turn's `prefetch` a cache read.

### After Each Turn (`sync_turn`)

After each user+assistant exchange:

1. Spawns a background worker
2. Sends `POST /hook?event=user-prompt-submit` with `{"session_id", "prompt"}` — the field ai-memory reads — plus the session's `cwd`
3. Swallows errors (logged only)

### Session End (`on_session_end`)

When the conversation ends:

1. Spawns a background worker
2. Sends `POST /hook?event=session-end` with the session id only — the server reads no body field on this event, and posting the transcript risked the 0.5s turn-hook timeout dropping the close
3. Swallows errors (logged only)

Hermes calls `on_session_end` and then immediately `shutdown_all()`, and its own drain cannot see provider threads, so `shutdown()` joins the tracked workers under a bounded 5s deadline.

If a close is ever lost (server down at that moment), `ai-memory finalize-session --agent hermes` posts the same event afterwards.

### Memory Mirroring (`on_memory_write`)

When Hermes writes to built-in `MEMORY.md` or `USER.md`:

1. Mirrors the write asynchronously on a background worker, so the caller's turn is not blocked
2. Path: `hermes-memory/{target}.md`
3. Tags: `hermes`, `mirror`
4. `add` and `replace` are mirrored — a `replace` keeps the superseded entry in the page under `## Substituído`. `remove` is skipped: the wiki keeps the page history rather than a tombstone.

## Using Tools

### `ai_memory_search`

```json
{
  "name": "ai_memory_search",
  "arguments": {
    "query": "project architecture decisions",
    "max_results": 10
  }
}
```

### `ai_memory_write`

```json
{
  "name": "ai_memory_write",
  "arguments": {
    "path": "decisions/auth-flow.md",
    "body": "# Auth Flow\n\nWe use JWT with refresh tokens...",
    "tags": ["auth", "security"]
  }
}
```

### `ai_memory_status`

```json
{
  "name": "ai_memory_status",
  "arguments": {}
}
```

## Development

### Setup

```bash
uv sync
```

### Running Tests

```bash
# Full suite with coverage
uv run pytest --cov

# Single file
uv run pytest tests/test_provider.py -v

# Watch mode (with pytest-watch)
uv run ptw -- --cov
```

### Linting and Typing

```bash
uv run ruff check .
uv run mypy .
```

### Adding a New Tool

1. Add schema to `get_tool_schemas()` in `provider.py`
2. Add handler case in `handle_tool_call()`
3. Add private `_tool_method()` in provider
4. Add client method in `client.py` if needed
5. Write tests in `tests/test_provider.py`

## Integration Patterns

### Multiple Hermes Profiles

Each profile falls back to its own ai-memory project when no marker or configured scope resolves:

```bash
# Profile "work"
hermes --profile work
# → project: hermes-work

# Profile "personal"
hermes --profile personal
# → project: hermes-personal
```

A repository marker or derived git-remote project takes precedence over this profile fallback; explicit config still wins over both.

### Disable Auto-Capture

The plugin has no toggle for auto-capture — it always captures turns. To disable, set the provider to a no-op in Hermes config:

```yaml
memory:
  provider: ""
```

### Custom Handoff Agent

```python
client.fetch_handoff(agent="codex", workspace="hermes", project="my-project")
```

## Deployment

### Install Scripts

Two ready-to-run install scripts are included in the repository:

- `scripts/install.sh` — Linux/macOS (Bash)
- `scripts/install.ps1` — Windows (PowerShell)

Both scripts:
1. Resolve `$HERMES_HOME` (default: `~/.hermes` or `%USERPROFILE%\.hermes`)
2. Run **pre-flight checks** (Hermes CLI, ai-memory server, plugin state, write permissions)
3. Prompt for **confirmation** before making changes
4. Symlink/junction or copy the plugin directory
5. Write an initial `ai-memory.json` config if none exists

#### Flags

| Flag | Bash | PowerShell | Env var | Description |
|---|---|---|---|---|
| Dry run | `--dry-run` | `-DryRun` | — | Show what would happen without making changes |
| Skip prompts | `--yes` | `-Yes` | `FORCE=true` | Skip confirmation (for CI/automation) |

When piped (non-interactive), scripts detect the missing TTY, print a warning, and proceed. Set `FORCE=true` or pass `--yes`/`-Yes` to silence the warning.

### Linux/macOS One-liner

Requires `curl` and `tar`. When run via `curl`, the script downloads the plugin from GitHub and copies it into `$HERMES_HOME/plugins/ai-memory`.

```bash
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)
```

Override the server URL:

```bash
AI_MEMORY_SERVER_URL=http://10.0.0.42:49374 bash <(curl -sL ...)
```

### Windows One-liner

Requires PowerShell 5.1+ with .NET (default on Windows 10/11 and Windows Server 2016+). When run via `iex`, the script downloads the plugin from GitHub and copies it into `$HERMES_HOME\plugins\ai-memory`.

```powershell
powershell -c "iex ((Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.ps1').Content)"
```

### Uninstall

Two uninstall scripts are included:

- `scripts/uninstall.sh` — Linux/macOS
- `scripts/uninstall.ps1` — Windows

Both remove `$HERMES_HOME/plugins/ai-memory` (symlink, junction, or copied directory) and run `hermes plugins disable ai-memory` if the Hermes CLI is available. The `ai-memory.json` config file is kept unless you request removal.

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
# Dry-run:
.\scripts\uninstall.ps1 -DryRun
# Skip prompt:
.\scripts\uninstall.ps1 -Yes
# Also remove config:
.\scripts\uninstall.ps1 -RemoveConfig
```

### Update

Two update scripts are included:

- `scripts/update.sh` — Linux/macOS
- `scripts/update.ps1` — Windows

Both default to downloading the latest plugin from the GitHub `main` branch, back up the existing install to `$HERMES_HOME/.ai-memory-backups/ai-memory.bak.<timestamp>`, replace the plugin files, and preserve `ai-memory.json`. Backups are kept and listed after each run.

Linux/macOS:

```bash
bash scripts/update.sh
# Dry-run (preview only):
bash scripts/update.sh --dry-run
# Skip prompt:
bash scripts/update.sh --yes
```

Override the source tarball:

```bash
REPO_TARBALL_URL=https://example.com/ai-memory.tar.gz bash scripts/update.sh
```

Update from a local clone (preserves a symlink install):

```bash
UPDATE_FROM_LOCAL=true bash scripts/update.sh
```

Windows (PowerShell):

```powershell
.\scripts\update.ps1
# Dry-run:
.\scripts\update.ps1 -DryRun
# Skip prompt:
.\scripts\update.ps1 -Yes
```

```powershell
$env:UPDATE_FROM_LOCAL="true"; .\scripts\update.ps1
```

The `hermes ai-memory update` command performs the same GitHub-based update from inside Hermes.

### uv pip install (from local clone)

If you have the repository cloned and want to install `httpx` into your Hermes environment:

```bash
# Install the project dependency
uv pip install --system -e /path/to/ai-memory-hermes-plugin

# Copy the plugin files
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r /path/to/ai-memory-hermes-plugin/plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"
```

Without the `uv pip install` step, Hermes will still attempt to install `httpx` automatically from `plugin.yaml`'s `pip_dependencies` section — but pre-installing it is faster for repeated deployments.

### Manual Install

```bash
# From the project root
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"
```
