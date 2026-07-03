# ai-memory-hermes-plugin

## What This Is

A Hermes Agent memory provider plugin backed by ai-memory. Hermes agents get ai-memory as a first-class `MemoryProvider` with automatic prefetch, turn sync, session finalization, and wiki search/write tools — without running a separate MCP server.

## Core Value

Hermes Agent users get ai-memory's zero-friction lifecycle capture, Karpathy-style LLM wiki compilation, and cross-agent handoffs — all as a native Hermes plugin.

## Current Milestone: v0.1.0 Core Plugin Implementation

**Goal:** Ship a complete Hermes Agent memory provider plugin backed by ai-memory.

**Target features:**
- **Phase 1** — Config: AiMemoryConfig dataclass, schema, save/load
- **Phase 2** — Client: AiMemoryClient HTTP wrapper with search/write/status/hook/handoff
- **Phase 3** — Provider: AiMemoryProvider with all Hermes lifecycle hooks and tools
- **Phase 4** — Entry point: __init__.py + plugin.yaml for Hermes plugin loader
- **Phase 5** — CLI: hermes ai-memory status/config/link subcommands

## Shipped

- Design research complete (docs/superpowers/specs/)
- Project scaffolded with GSD workflow (ruff/mypy/pytest gates, 40 tests at 90% coverage)

## Requirements

### Validated

- ✓ Design research complete — ai-memory integrates via Hermes `MemoryProvider` plugin interface
- ✓ Project scaffolded with GSD planning workflow

### Active

- [ ] **CFG-01**: AiMemoryConfig dataclass with server_url, api_key, auth_token, workspace, project
- [ ] **CFG-02**: get_config_schema() returns field descriptors for hermes memory setup wizard
- [ ] **CFG-03**: save_config() writes JSON to $HERMES_HOME/ai-memory.json
- [ ] **CFG-04**: load_config() reads JSON, falls back to env vars
- [ ] **CLI-01**: AiMemoryClient.search() sends GET /admin/search with auth and params
- [ ] **CLI-02**: AiMemoryClient.write_page() sends POST /admin/write-page
- [ ] **CLI-03**: AiMemoryClient.status() sends GET /admin/status
- [ ] **CLI-04**: AiMemoryClient.send_hook() sends POST /hook with event/session_id
- [ ] **CLI-05**: AiMemoryClient.fetch_handoff() sends GET /handoff
- [ ] **CLI-06**: Client handles HTTP errors gracefully (logged, not raised on hooks)
- [ ] **PRO-01**: AiMemoryProvider implements MemoryProvider ABC with all lifecycle hooks
- [ ] **PRO-02**: get_tool_schemas() returns ai_memory_search/write/status tool defs
- [ ] **PRO-03**: handle_tool_call() routes to correct client method
- [ ] **PRO-04**: prefetch() calls client.search() and returns concatenated snippets
- [ ] **PRO-05**: sync_turn() spawns daemon thread calling client.send_hook()
- [ ] **PRO-06**: on_session_end() spawns daemon thread sending session-end event
- [ ] **PRO-07**: initialize() resolves workspace/project from kwargs or config
- [ ] **ENT-01**: __init__.py exposes register(ctx) entry point
- [ ] **ENT-02**: plugin.yaml declares httpx dependency and on_session_end hook
- [ ] **CLI-07**: hermes ai-memory status subcommand
- [ ] **CLI-08**: hermes ai-memory config subcommand
- [ ] **CLI-09**: hermes ai-memory link subcommand (symlink to $HERMES_HOME)

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

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-07-02 — Milestone v0.1.0 started*
