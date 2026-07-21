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

### 3. Enable in Hermes

```bash
hermes plugins enable ai-memory
```

### 4. Run setup wizard

```bash
hermes memory setup
```

Prompts for server URL, API key (optional), and workspace/project.

### 5. Verify

```bash
hermes memory status
# → ai-memory server: reachable
#   Pages:    42
#   Sessions: 7
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

Each Hermes profile gets a separate ai-memory project. The project name is derived as `hermes-{profile}`. Override via:

```bash
export AI_MEMORY_PROJECT=my-project
```

Or set `project` in `$HERMES_HOME/ai-memory.json`.

## Lifecycle Behavior

### Session Start (`initialize`)

When a new conversation starts, the provider resolves:
- `workspace` — from kwargs or config (default: `"hermes"`)
- `project` — from kwargs, config, or `"hermes-{profile}"` (default: `"hermes-default"`)

### Before Each Turn (`prefetch`)

The agent calls `prefetch(query)` with the user's message. The provider:
1. Searches ai-memory wiki with `GET /admin/search?q=<query>&limit=3`
2. Returns snippets as a string block
3. Injected into the model's context before the turn

`queue_prefetch(query)` fires the search on a daemon thread for the next turn.

### After Each Turn (`sync_turn`)

After each user+assistant exchange:
1. Spawns a daemon thread
2. Sends `POST /hook?event=user-prompt` with the turn payload
3. Swallows errors (logged only)

### Session End (`on_session_end`)

When the conversation ends:
1. Spawns a daemon thread
2. Sends `POST /hook?event=session-end` with all messages
3. Swallows errors (logged only)

### Memory Mirroring (`on_memory_write`)

When Hermes writes to built-in `MEMORY.md` or `USER.md`:
1. Mirrors content to ai-memory wiki via `POST /admin/write-page`
2. Path: `hermes-memory/{target}.md`
3. Tags: `hermes`, `mirror`

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

Each profile gets its own ai-memory project:

```bash
# Profile "work"
hermes --profile work
# → project: hermes-work

# Profile "personal"
hermes --profile personal
# → project: hermes-personal
```

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
