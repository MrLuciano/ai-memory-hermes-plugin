# ai-memory Hermes Memory Provider Plugin

Connects [Hermes Agent](https://github.com/NousResearch/hermes-agent) to [ai-memory](https://github.com/akitaonrails/ai-memory) as a first-class `MemoryProvider` plugin — automatic prefetch, turn sync, session finalization, and wiki search/write tools.

## Features

- **Auto-prefetch** — wiki context injected before every model turn
- **Turn capture** — async daemon-thread sync after each completed turn
- **Session finalization** — `session-end` hook on conversation close
- **Memory mirroring** — built-in `MEMORY.md` writes mirrored to ai-memory wiki
- **Hermes CLI integration** — `hermes memory setup`, `hermes memory status`
- **Per-profile isolation** — project scoped by Hermes profile name
- **3 tool schemas** — `ai_memory_search`, `ai_memory_write`, `ai_memory_status`
- **94% test coverage** — linted with ruff, type-checked with mypy

## Quick Start

```bash
# Quick install via script (Linux/macOS)
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)

# Enable and configure
hermes plugins enable ai-memory
hermes memory setup

# Verify
hermes memory status
```

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
| `config.py` | AiMemoryConfig | Config dataclass + JSON persistence + env-var fallback |
| `cli.py` | CLI | `status`/`config`/`link` subcommands for `hermes memory` |
| `plugin.yaml` | Manifest | Metadata, hooks declaration, pip dependencies |

## Lifecycle

| Hermes hook | ai-memory call | Threading |
|---|---|---|
| `is_available()` | Checks `auth_token` / `api_key` config | Sync |
| `initialize()` | Resolves workspace/project from kwargs | Sync |
| `prefetch(query)` | `GET /admin/search` | Sync |
| `queue_prefetch(query)` | Spawns prefetch thread | Daemon thread |
| `sync_turn(user, assistant)` | `POST /hook?event=user-prompt` | Daemon thread |
| `on_session_end(messages)` | `POST /hook?event=session-end` | Daemon thread |
| `on_memory_write(action, target, content)` | `POST /admin/write-page` | Sync |
| `handle_tool_call(name, args)` | Routes to search/write/status | Sync |

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AI_MEMORY_SERVER_URL` | `http://127.0.0.1:49374` | ai-memory server address |
| `AI_MEMORY_API_KEY` | `""` | API key (sent as Bearer token) |
| `AI_MEMORY_AUTH_TOKEN` | `""` | Auth token (alias for api_key) |

Env vars override file config, which overrides defaults.

### Config File (`$HERMES_HOME/ai-memory.json`)

Written by `hermes memory setup` wizard:

```json
{
  "server_url": "http://127.0.0.1:49374",
  "workspace": "hermes",
  "project": "hermes-default"
}
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
├── test_config.py    # 12 tests
├── test_client.py    # 16 tests
├── test_provider.py  # 29 tests
├── test_entry.py     # 10 tests
└── test_cli.py       # 7 tests
```

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server (HTTP API at port 49374)
- `httpx >= 0.28`

## Deployment

### Install Scripts

| Platform | Script | Method |
|---|---|---|
| Linux/macOS | [`scripts/install.sh`](scripts/install.sh) | Bash — symlinks or copies plugin into `$HERMES_HOME`, writes initial config |
| Windows | [`scripts/install.ps1`](scripts/install.ps1) | PowerShell — creates NTFS junction or copies, writes initial config |

### One-liner (Linux/macOS)

```bash
bash <(curl -sL https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.sh)
```

Set `AI_MEMORY_SERVER_URL` before running to override the default server address:

```bash
AI_MEMORY_SERVER_URL=http://10.0.0.42:49374 bash <(curl -sL ...)
```

### Windows (PowerShell)

```powershell
powershell -c "iex ((Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MrLuciano/ai-memory-hermes-plugin/main/scripts/install.ps1').Content)"
```

With custom server URL:

```powershell
powershell -c "$env:ServerUrl='http://10.0.0.42:49374'; iex ((Invoke-WebRequest -Uri '...').Content)"
```

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
