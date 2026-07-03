<!-- GSD:project-start source:.planning/PROJECT.md -->
## Project

**ai-memory-hermes-plugin**

A Hermes Agent memory provider plugin backed by ai-memory. Hermes agents get ai-memory as a first-class `MemoryProvider` with automatic prefetch, turn sync, session finalization, and wiki search/write tools.

**Core Value:** Hermes Agent users get ai-memory's zero-friction lifecycle capture, Karpathy-style LLM wiki compilation, and cross-agent handoffs — all as a native Hermes plugin.

### Constraints

- **Tech stack**: Python 3.10+, Hermes Agent, ai-memory server
- **Dependencies**: uv for dev tooling; plugin ships self-contained (dep: httpx)
- **Plugin API**: Must match `agent.memory_provider.MemoryProvider` ABC
- **Compatibility**: Must work with `hermes memory setup` wizard
- **No runtime server**: This is a plugin, not a long-running process
- **TDD mode**: Tests before implementation for each phase
- **Quality gates**: `ruff check .`, `mypy .`, `pytest --cov`
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

### Languages
- Python 3.10+ — plugin implementation

### Runtime
- CPython 3.10+
- Hermes Agent (plugin host)
- ai-memory server (Rust binary, separate process)

### Frameworks
- `httpx` — HTTP client for ai-memory API
- `pytest >=8` — test runner
- `pytest-asyncio` — async test support
- `pytest-cov` — coverage
- `ruff` — linting
- `mypy` — type checking

### Key Dependencies
- `httpx >=0.28` — HTTP communication with ai-memory

### Configuration
- `$HERMES_HOME/ai-memory.json` — saved config per profile
- Environment vars: `AI_MEMORY_SERVER_URL`, `AI_MEMORY_AUTH_TOKEN`, `AI_MEMORY_DATA_DIR`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

### Naming
- `snake_case` for modules, functions, variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Test files prefixed with `test_`
- Private methods prefixed with `_`

### Code Style
- Ruff, line length 100
- Target: Python 3.10+
- Type hints on all function signatures
- `from __future__ import annotations` for PEP 604 syntax

### Import Organization
stdlib → third-party → local

### Error Handling
- Explicit exception types, never bare `except:`
- Hook paths (sync_turn, on_session_end) swallow exceptions gracefully
- Tool paths (search, write) propagate errors for user visibility
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

```
Hermes Agent → MemoryProvider ABC → AiMemoryProvider → AiMemoryClient → HTTP → ai-memory server
```

### Layers
- **AiMemoryProvider** — implements Hermes MemoryProvider ABC
- **AiMemoryClient** — typed HTTP wrapper for ai-memory REST API
- **AiMemoryConfig** — config dataclass + JSON persistence
- **Entry point** — `register(ctx)` → Hermes plugin loader

### Lifecycle
| Hermes hook | ai-memory call | Threading |
|---|---|---|
| `initialize()` | Resolve workspace/project | Sync |
| `prefetch(query)` | `GET /admin/search` | Sync |
| `sync_turn(user, assistant)` | `POST /hook` | Daemon thread |
| `on_session_end(messages)` | `POST /hook?event=session-end` | Daemon thread |
<!-- GSD:architecture-end -->
