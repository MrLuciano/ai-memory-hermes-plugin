# ROADMAP: ai-memory-hermes-plugin

**Milestone:** v0.1.0 — Core Plugin Implementation
**Created:** 2026-07-03
**Granularity:** Coarse (5 phases)
**Total Requirements:** 27
**Total Tests (scaffolded):** 40 at ~90% coverage

## Milestone Overview

Deliver a complete Hermes Agent memory provider plugin backed by ai-memory. The plugin gives Hermes agents ai-memory's lifecycle capture, LLM wiki compilation, and cross-agent handoffs as a native `MemoryProvider` — no separate MCP server needed.

**Definition of Done:**
- All 27 v0.1.0 requirements implemented and integration-tested
- 3 quality gates passing: `ruff check .`, `mypy .`, `pytest --cov` (fail_under 89)
- Plugin installable via `hermes plugins enable ai-memory`
- CLI subcommands operational: `status`, `config`, `link`
- 40 existing scaffold tests + new TDD tests per phase all green

## Phase Dependency DAG

```
Phase 1 (Config) ──→ Phase 2 (Client) ──→ Phase 3 (Provider) ──→ Phase 4 (Entry Point) ──→ Phase 5 (CLI)
```

Strict sequential chain — each phase builds on the prior. No parallelization.

**Rationale:** Config defines connection parameters. Client wraps HTTP transport. Provider implements the Hermes ABC. Entry Point registers the provider. CLI adds user-facing subcommands on top of a working plugin.

## Phases

- [x] **Phase 1: Config** — AiMemoryConfig dataclass, `get_config_schema()`, `save_config()`, `load_config()` with env var fallback
- [x] **Phase 2: Client** — AiMemoryClient HTTP wrapper for search, write, status, hook, handoff with differentiated timeout/error handling
- [x] **Phase 3: Provider** — AiMemoryProvider implementing Hermes `MemoryProvider` ABC with lifecycle hooks and tool routing
- [ ] **Phase 4: Entry Point** — `__init__.py` + `plugin.yaml` for Hermes plugin loader discovery
- [ ] **Phase 5: CLI** — `hermes ai-memory status/config/link` subcommands

## Phase Details

### Phase 1: Config
**Goal:** Users can configure the ai-memory plugin connection via JSON file, environment variables, or the Hermes setup wizard.
**Depends on:** Nothing (foundation phase)
**Requirements:** CFG-01, CFG-02, CFG-03, CFG-04
**Success Criteria** (what must be TRUE):
1. `AiMemoryConfig` can be created with all default values (zero-arg construction) — no required fields
2. `get_config_schema()` returns field descriptors compatible with the Hermes `memory setup` wizard
3. `save_config()` writes valid JSON to `$HERMES_HOME/ai-memory.json`, merging with any existing data
4. `load_config()` returns a working config from saved JSON, falls back to env vars (`AI_MEMORY_SERVER_URL`, `AI_MEMORY_AUTH_TOKEN`, `AI_MEMORY_DATA_DIR`), falls back to hardcoded defaults
5. Config round-trips idempotently — `save_config()` then `load_config()` produces identical values
**Existing tests:** 9 (`test_config.py`)
**New tests required:** TDD — any gaps discovered during validation
**Plans:** TBD

### Phase 2: Client
**Goal:** The plugin can communicate with an ai-memory server over HTTP for all required operations with appropriate timeout and error handling per endpoint type.
**Depends on:** Phase 1 (Config)
**Requirements:** CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07, CLI-08
**Success Criteria** (what must be TRUE):
1. `client.search()` sends `GET /admin/search?q=<query>&limit=N` with Bearer auth and returns parsed result list
2. `client.write_page()` sends `POST /admin/write-page` with path/body/tags/workspace/project payload
3. `client.status()` sends `GET /admin/status` and returns parsed server health info
4. `client.send_hook()` sends `POST /hook?event=<type>&session_id=<id>` with turn or session-end payload (500ms timeout)
5. `client.fetch_handoff()` sends `GET /handoff` and returns handoff summary string, or `None` on 404
6. HTTP errors on hook paths (`send_hook`) are logged but never raised — agent stays up
7. HTTP errors on admin/tool paths (`search`, `write_page`, `status`, `fetch_handoff`) propagate to caller for user visibility
**Existing tests:** 12 (`test_client.py`)
**New tests required:** TDD — timeout enforcement, error propagation paths, auth header construction
**Plans:** TBD

### Phase 3: Provider
**Goal:** Hermes Agent can use ai-memory as its long-term memory provider through the standard `MemoryProvider` interface for prefetch, turn sync, session finalization, and tool execution.
**Depends on:** Phase 2 (Client)
**Requirements:** PRO-01, PRO-02, PRO-03, PRO-04, PRO-05, PRO-06, PRO-07, PRO-08, PRO-09
**Success Criteria** (what must be TRUE):
1. `AiMemoryProvider` matches the `MemoryProvider` ABC — all abstract methods implemented
2. `initialize()` resolves `workspace` and `project` from kwargs (e.g. `profile`), falls back to config defaults
3. `prefetch(query)` calls `client.search()` and returns concatenated snippets as a single string, or `None` when empty
4. `sync_turn()` spawns a **daemon thread** that calls `client.send_hook()` with user/assistant text
5. `on_session_end()` spawns a **daemon thread** sending `POST /hook?event=session-end` with full message history
6. `get_tool_schemas()` returns tool definitions for `ai_memory_search`, `ai_memory_write`, `ai_memory_status`
7. `handle_tool_call()` routes each tool name to the correct client method and returns structured results
8. Hook paths (`sync_turn`, `on_session_end`) never crash the agent — all exceptions swallowed by daemon thread wrappers
9. Tool paths (`handle_tool_call`, `prefetch`) propagate exceptions for user visibility
**Existing tests:** 19 (`test_provider.py`)
**New tests required:** TDD — integration boundary tests with real client, error propagation verification, threading assertions
**Plans:** TBD
**Risk note:** Highest-risk phase. Hermes `MemoryProvider` ABC API is assumed from design research. If the real Hermes interface differs (method signatures, async patterns, context passing), this phase requires the most rework. Mitigated by early integration spike in Phase 2.

### Phase 4: Entry Point
**Goal:** The Hermes plugin loader can discover, load, and register the ai-memory plugin — making it available via `hermes plugins enable ai-memory`.
**Depends on:** Phase 3 (Provider)
**Requirements:** ENT-01, ENT-02, ENT-03
**Success Criteria** (what must be TRUE):
1. `from plugins.memory.ai_memory import register` succeeds without import errors
2. `register(ctx)` instantiates `AiMemoryProvider` and assigns it to `ctx.agent.memory_provider`
3. `plugin.yaml` declares the `httpx` runtime dependency and the `on_session_end` hook registration
4. Plugin loads without errors via `hermes plugins enable ai-memory` (tested with mock ctx)
5. `hermes memory setup` wizard displays the config fields returned by `get_config_schema()`
**Existing tests:** 0 (new — `test_entry.py` needed)
**New tests required:** 3–5 tests: `register()` wiring, `plugin.yaml` parse validation, plugin lifecycle with mock Hermes context
**Plans:** TBD
**Risk note:** Second-highest risk. The `register(ctx)` API shape and `ctx.agent.memory_provider` attribute path depend on Hermes loader conventions not yet validated. Mitigated by inspecting Hermes plugin examples and existing plugins during Phase 3.

### Phase 5: CLI
**Goal:** Users can inspect and manage the plugin via `hermes ai-memory` CLI subcommands without editing files manually.
**Depends on:** Phase 4 (Entry Point), Phase 1 (Config — for reading saved config)
**Requirements:** CLI-09, CLI-10, CLI-11
**Success Criteria** (what must be TRUE):
1. `hermes ai-memory status` displays connection reachability and wiki page/session statistics
2. `hermes ai-memory config` reads and displays the current saved configuration from `$HERMES_HOME/ai-memory.json`
3. `hermes ai-memory link` creates a symlink from the plugin directory into `$HERMES_HOME/plugins/ai-memory`
4. All subcommands show helpful error messages when the ai-memory server is unreachable or config is missing
**Existing tests:** 0 (new — `test_cli.py` needed)
**New tests required:** 4–6 tests: subcommand argument parsing, output formatting, error cases for missing config/unreachable server
**Plans:** TBD

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hermes `MemoryProvider` ABC API differs from design assumptions | Phase 3 + 4 rework | Medium | Early integration spike in Phase 2; consult real Hermes plugin examples and source |
| ai-memory HTTP API changes between design and implementation | Phase 2 + 3 rework | Low | Pin to ai-memory server v0.x API contract; use httpx for flexible request building |
| mypy excludes `plugins/` directory in `pyproject.toml` | Plugin code not type-checked | High | Fix mypy config in Phase 1: remove blanket exclude or add per-directory override |
| TDD discipline slips under implementation pressure | Coverage drops below 89% | Medium | CI gate enforces `fail_under = 89`; quality gates run after every phase |
| Daemon thread timing makes tests non-deterministic | Flaky CI builds | Medium | Use `threading.Event` for thread lifecycle synchronization in tests; generous timeouts |

## Quality Gate Checklist

After **every** phase completes, verify:

- [ ] `ruff check .` — zero linting errors (line-length 100, target py310)
- [ ] `mypy .` — zero type errors (requires mypy config fix — see note below)
- [ ] `pytest --cov` — all tests pass; coverage >= 89%
- [ ] All new files pass linting (ruff formatting check)
- [ ] Git commit with descriptive message referencing phase number and requirement IDs

**mypy config note:** Current `pyproject.toml` has `exclude = ["plugins/"]` which skips type-checking the plugin code at `plugins/memory/ai-memory/`. This must be addressed in Phase 1 — either remove the blanket exclude and add targeted `# type: ignore` comments, or run mypy on the plugin directory explicitly. Recommended: update `[tool.mypy]` to `exclude = []` and add per-file ignores for third-party modules without stubs.

## Phase Ordering Rationale

**Bottom-up dependency chain — each phase produces a testable artifact:**

1. **Phase 1 — Config first.** No dependencies. Provides the connection parameters every other layer needs. Testable at the unit level (dataclass + file I/O).
2. **Phase 2 — Client second.** Needs config for `server_url` and `auth_token`. Provides HTTP transport. Testable with mock transport (httpx MockTransport) — no real server needed.
3. **Phase 3 — Provider third.** Uses client for all ai-memory calls. Implements the Hermes ABC. The core of the plugin. Testable with mock client + threading assertions.
4. **Phase 4 — Entry Point fourth.** Wraps provider for Hermes plugin loader. Thin integration layer. Testable with mock `ctx` object.
5. **Phase 5 — CLI last.** User-facing subcommands that depend on a fully working plugin and config. Testable with `pytest` CLI runner fixtures.

This ordering ensures no phase is blocked waiting for a downstream dependency, and each phase can be verified independently before the next begins.

## Checkpoint Expectations

| Phase | Entry Gate | Exit Gate | Estimated Test Count |
|-------|-----------|-----------|---------------------|
| 1 — Config | Requirements defined, scaffold in place | 9+ tests green, quality gates pass | 9–11 |
| 2 — Client | Phase 1 complete, config working | 12+ tests green, quality gates pass | 12–15 |
| 3 — Provider | Phase 2 complete, client tested | 19+ tests green, quality gates pass | 19–23 |
| 4 — Entry Point | Phase 3 complete, provider tested | 3–5 new tests green, quality gates pass | 3–5 |
| 5 — CLI | Phase 4 complete, plugin loads | 4–6 new tests green, quality gates pass | 4–6 |

---

*Roadmap created: 2026-07-03 | Milestone: v0.1.0 | Granularity: coarse (5 phases within 3–5 range)*
