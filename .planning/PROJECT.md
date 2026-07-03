# ai-memory-hermes-plugin

## What This Is

A Hermes Agent memory provider plugin backed by ai-memory. Hermes agents get ai-memory as a first-class `MemoryProvider` with automatic prefetch, turn sync, session finalization, and wiki search/write tools — without running a separate MCP server.

## Core Value

Hermes Agent users get ai-memory's zero-friction lifecycle capture, Karpathy-style LLM wiki compilation, and cross-agent handoffs — all as a native Hermes plugin.

## Shipped

- Research complete: design spec approved (docs/superpowers/specs/2026-07-02-hermes-ai-memory-plugin-design.md)
- Project scaffolded with GSD workflow

### Phase 1: Config

- `AiMemoryConfig` dataclass: `server_url`, `api_key`, `workspace`, `project`
- `get_config_schema()` — field descriptors for `hermes memory setup`
- `save_config(values, hermes_home)` — writes `$HERMES_HOME/ai-memory.json`
- `load_config(hermes_home)` — reads JSON, falls back to env vars

### Phase 2: Client

- `AiMemoryClient` with typed methods: `search()`, `write_page()`, `status()`, `send_hook()`, `fetch_handoff()`
- Bearer auth, timeout separation (500ms hooks, 10s admin)
- Error handling: HTTP errors logged, not raised on hook paths

### Phase 3: Provider

- `AiMemoryProvider(MemoryProvider)` implementing all Hermes hooks
- Thread safety, daemon threads for sync, tool schemas
- `ai_memory_search`, `ai_memory_write`, `ai_memory_status` tools

### Phase 4: Entry point

- `__init__.py` with `register(ctx)` entry point
- `plugin.yaml` declaring `httpx` dependency

### Phase 5: CLI (optional)

- `hermes ai-memory status` / `config` / `link` subcommands

## Requirements

### Validated

- ✓ Design research complete — ai-memory integrates via Hermes `MemoryProvider` plugin interface
- ✓ Project scaffolded with GSD planning workflow

### Active

- Phase 1: config.py + test_config.py
- Phase 2: client.py + test_client.py
- Phase 3: provider.py + test_provider.py
- Phase 4: __init__.py + plugin.yaml
- Phase 5: cli.py (optional)

## Context

- Plugin lives at `plugins/memory/ai-memory/` — deployable to `$HERMES_HOME/plugins/ai-memory/`
- Uses `httpx` for async HTTP; Hermes provider API is sync — wrapped with `threading` for daemon calls
- ai-memory runs as a separate process (Rust binary) at `http://127.0.0.1:49374` by default
- Auth: Bearer token when `AI_MEMORY_AUTH_TOKEN` set; none on loopback
- Profile isolation: `workspace=hermes`, `project=hermes-{profile_name}`
- TDD mode: tests before implementation for each phase
- Quality gates: `ruff check .`, `mypy .`, `pytest --cov`

## Constraints

- **Tech stack**: Python 3.10+, Hermes Agent, ai-memory server
- **Dependencies**: uv for dev tooling; plugin ships self-contained (dep: httpx)
- **Plugin API**: Must match `agent.memory_provider.MemoryProvider` ABC
- **Compatibility**: Must work with `hermes memory setup` wizard
- **No runtime server**: This is a plugin, not a long-running process

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| httpx for HTTP | Async-capable, modern stdlib alternative; needed by Hermes plugin API | ✓ |
| Config persisted as JSON | Simple, no extra deps; follows Hermes plugin convention | ✓ |
| Daemon threads for sync | Non-blocking turn capture; timeout at shutdown | ✓ |
| workspace=hermes, project=hermes-{profile} | Clear namespace; configurable | ✓ |
| TDD mode | Plugin must be reliable; full coverage target | ✓ |

## Evolution

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions

---

*Last updated: 2026-07-02 — Project scaffolded*
