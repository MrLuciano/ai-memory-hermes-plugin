# Requirements: ai-memory-hermes-plugin

**Defined:** 2026-07-02
**Core Value:** Hermes Agent users get ai-memory's zero-friction lifecycle capture, Karpathy-style LLM wiki compilation, and cross-agent handoffs — all as a native Hermes plugin.

## v0.1.0 Requirements

### Config (Phase 1)

- [ ] **CFG-01**: AiMemoryConfig dataclass with `server_url`, `api_key`, `auth_token`, `workspace`, `project` fields and suitable defaults
- [ ] **CFG-02**: `get_config_schema()` returns field descriptors compatible with `hermes memory setup` wizard
- [ ] **CFG-03**: `save_config(values, hermes_home)` writes validated JSON to `$HERMES_HOME/ai-memory.json`
- [ ] **CFG-04**: `load_config(hermes_home)` reads JSON config, falls back to environment variables (`AI_MEMORY_SERVER_URL`, `AI_MEMORY_AUTH_TOKEN`, `AI_MEMORY_DATA_DIR`)

### Client (Phase 2)

- [ ] **CLI-01**: `AiMemoryClient.search(query, workspace, project, limit)` sends `GET /admin/search` with Bearer auth and query params
- [ ] **CLI-02**: `AiMemoryClient.write_page(path, body, tags, tier, pinned)` sends `POST /admin/write-page`
- [ ] **CLI-03**: `AiMemoryClient.status()` sends `GET /admin/status`
- [ ] **CLI-04**: `AiMemoryClient.send_hook(messages, event, session_id, session_data)` sends `POST /hook` with turn or session-end payload
- [ ] **CLI-05**: `AiMemoryClient.fetch_handoff(workspace, project)` sends `GET /handoff`
- [ ] **CLI-06**: Client uses 500ms default timeout for hooks, 10s for admin endpoints
- [ ] **CLI-07**: HTTP errors on hook paths are logged but not raised (graceful degradation)
- [ ] **CLI-08**: HTTP errors on tool/admin paths propagate to caller for user visibility

### Provider (Phase 3)

- [ ] **PRO-01**: `AiMemoryProvider` implements `agent.memory_provider.MemoryProvider` ABC
- [ ] **PRO-02**: `initialize(**kwargs)` resolves `workspace` and `project` from kwargs, falls back to config
- [ ] **PRO-03**: `prefetch(query, context)` calls `client.search()` and returns concatenated snippet text
- [ ] **PRO-04**: `sync_turn(user_text, assistant_text, context)` spawns daemon thread calling `client.send_hook()`
- [ ] **PRO-05**: `on_session_end(messages, context)` spawns daemon thread sending `POST /hook?event=session-end`
- [ ] **PRO-06**: `get_tool_schemas()` returns tool definitions for `ai_memory_search`, `ai_memory_write`, `ai_memory_status`
- [ ] **PRO-07**: `handle_tool_call(tool_name, args)` routes to the correct client method and returns result
- [ ] **PRO-08**: Hook paths (`sync_turn`, `on_session_end`) swallow exceptions gracefully (daemon threads)
- [ ] **PRO-09**: Tool paths (`handle_tool_call`, `prefetch`) propagate exceptions for user visibility

### Entry Point (Phase 4)

- [ ] **ENT-01**: `__init__.py` exposes `register(ctx)` function compatible with Hermes plugin loader
- [ ] **ENT-02**: `register(ctx)` instantiates `AiMemoryProvider` and assigns to `ctx.agent.memory_provider`
- [ ] **ENT-03**: `plugin.yaml` declares `httpx` runtime dependency and `on_session_end` hook registration

### CLI (Phase 5)

- [ ] **CLI-09**: `hermes ai-memory status` subcommand displays connection status and wiki stats
- [ ] **CLI-10**: `hermes ai-memory config` subcommand reads/displays saved configuration
- [ ] **CLI-11**: `hermes ai-memory link` subcommand symlinks plugin dir into `$HERMES_HOME/plugins/`

## Out of Scope

| Feature | Reason |
|---------|--------|
| Long-running server process | Plugin architecture; ai-memory server runs separately |
| Built-in mock ai-memory server | Users bring their own ai-memory binary |
| Web UI | Hermes Agent handles the UX layer |
| Database migrations | Config is single JSON file |
| Multi-profile support | Single profile per `$HERMES_HOME` in v0.1.0 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 1 | Pending |
| CFG-02 | Phase 1 | Pending |
| CFG-03 | Phase 1 | Pending |
| CFG-04 | Phase 1 | Pending |
| CLI-01 | Phase 2 | Pending |
| CLI-02 | Phase 2 | Pending |
| CLI-03 | Phase 2 | Pending |
| CLI-04 | Phase 2 | Pending |
| CLI-05 | Phase 2 | Pending |
| CLI-06 | Phase 2 | Pending |
| CLI-07 | Phase 2 | Pending |
| CLI-08 | Phase 2 | Pending |
| PRO-01 | Phase 3 | Pending |
| PRO-02 | Phase 3 | Pending |
| PRO-03 | Phase 3 | Pending |
| PRO-04 | Phase 3 | Pending |
| PRO-05 | Phase 3 | Pending |
| PRO-06 | Phase 3 | Pending |
| PRO-07 | Phase 3 | Pending |
| PRO-08 | Phase 3 | Pending |
| PRO-09 | Phase 3 | Pending |
| ENT-01 | Phase 4 | Pending |
| ENT-02 | Phase 4 | Pending |
| ENT-03 | Phase 4 | Pending |
| CLI-09 | Phase 5 | Pending |
| CLI-10 | Phase 5 | Pending |
| CLI-11 | Phase 5 | Pending |

**Coverage:**
- v0.1.0 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-02*
*Last updated: 2026-07-02 after milestone definition*
