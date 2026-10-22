# ai-memory Hermes Memory Provider

Connects Hermes Agent to an ai-memory server for long-term wiki memory.

## Quick Start

```bash
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r * "$HERMES_HOME/plugins/ai-memory/"
hermes plugins enable ai-memory   # load the plugin
hermes memory setup               # activate it (sets memory.provider)
hermes memory status
```

`hermes plugins enable ai-memory` only registers the plugin; activation is `hermes memory setup` (or `memory.provider: ai-memory` in `config.yaml`). `plugins.enabled` is unrelated to memory-provider activation.

## Tools

- `ai_memory_search` — search the wiki
- `ai_memory_write` — write a new page
- `ai_memory_status` — health check

## Docs

Full documentation is at the [project root](../../../README.md), with detailed [usage guide](../../../docs/guide.md), [API reference](../../../docs/reference.md), and [troubleshooting](../../../docs/common-problems.md).

## Search and directory scope

`search_scope` is optional in `$HERMES_HOME/ai-memory.json`:

- `global` (default): preserves legacy global search and recall across projects.
- `project`: restricts tools, synchronous recall and background prefetch to the resolved workspace/project. Unknown scope returns no project results, never a global fallback.

For per-folder routing with one Hermes profile, use `{"search_scope": "project"}` and omit fixed `workspace`/`project` overrides. `AI_MEMORY_SEARCH_SCOPE` also accepts `global` or `project`. Explicit scope kwargs, file config and `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` take precedence over TOML.

At initialization, the plugin resolves the session directory from `AI_MEMORY_CWD`, the Hermes `cwd` kwarg, or `agent.runtime_cwd.resolve_agent_cwd()`. The directory must be absolute and existing; there is no `os.getcwd()` fallback. It then reads the nearest `.ai-memory.toml` settings boundary at or above it. For example, `imperio_2026/apps/socorro_financeiro/src` selects the application's marker rather than `imperio_2026/.ai-memory.toml`. A capture-only marker is transparent; a `[briefing]`-only marker is a boundary, so an outer project cannot leak through.

`.ai-memory.toml` requires `workspace` and treats `project` as optional. When a marker pins only `workspace`, the project is derived from the checkout's git remote (`upstream`, else `origin`) as the hostless repository path, lowercased, with `/` written as `-` (project names never contain `/`), or `basename(cwd)` when there is no valid remote. Writes, lifecycle capture, mirrors and handoff consumption require both fields and authorize a derived project only with an explicit/marker workspace; a project that is only the dataclass default (`hermes-default`) stays read-only. A valid cwd with no marker or derived project means unknown scope unless a project is explicitly configured; a repository needs **either** a marker pinning `workspace` **or** an explicit `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT` pin before memory can be written. An explicitly configured `hermes-default` project remains supported. A custom programmatic `AiMemoryConfig.project` is also retained as a fallback.

**Migration (0.1.4).** Repositories that previously resolved no project now write to the derived project, so pages written earlier under `hermes` / `hermes-default` are no longer found by project-scoped recall; they remain in ai-memory under the old project. Pin the old scope explicitly with `AI_MEMORY_WORKSPACE` / `AI_MEMORY_PROJECT`, `ai-memory.json`, or the initialization kwargs. `scope_diagnostics()` reports the resolved scope and provenance.

Legacy-generated default pairs no longer pin project-mode sessions; an intentional pair is preserved with `scope_origin=explicit`. New installations omit fixed scope, and setup scope prompts default to blank. See the [exact compatibility rule](../../../README.md#legacy-scope-defaults-and-explicit-overrides); indistinguishable hand-written legacy defaults require an explicit opt-out before enabling project mode.

Background workers prefer Hermes' `spawn_context_thread` and fall back to a daemon thread. They snapshot the client, session and scope before dispatch. The recall cache keeps the newest result per session+scope plus an exact-query alias, and initialization/session switches invalidate pending results.

**No dynamic folder-scope switching is supported in an existing session.** Hermes may update its live agent cwd, but the initialized memory provider is not re-initialized. Start a new session/provider initialized with the target folder; an ID-only `/new` or `/reset` on the same provider is not sufficient. The plugin never substitutes `os.getcwd()`. See the [Hermes memory-provider contract](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin).

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server running locally or on LAN
- `httpx`
