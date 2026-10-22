# Windows directory scope: diagnosis without memory writes

## Host contract

The locally installed Hermes source was inspected read-only:

- `hermes_cli/main.py:_apply_in_dir` converts `--in` through
  `tools.environments.local._msys_to_windows_path`, validates the directory,
  changes the launch directory, refreshes an inherited `TERMINAL_CWD`, and
  disables restoring the previous session directory.
- `agent/agent_init.py:_memory_provider_init_kwargs` adds `cwd` to the memory
  provider kwargs only when `agent.session_cwd` is set. The interactive CLI
  (`hermes chat`) builds `AIAgent` without it, so `cwd` is normally absent.
- `_init_memory` passes those kwargs to `MemoryManager.initialize_all`, which
  forwards them unchanged except for supplying a missing `hermes_home`.

This is evidence for this installed version and initialization path, not a
captured argument from an earlier session or a guarantee about every Hermes
version.

The plugin therefore resolves the session directory itself when the kwarg is
absent: it imports `agent.runtime_cwd.resolve_agent_cwd()` under a guard (the
plugin still loads without Hermes) and uses the returned directory. This closes
the read-only failure that a missing `cwd` used to cause. No MSYS conversion
was added: the host translates `--in`, and direct `marker_scope('/c/...')` on
native Windows remains unsupported and fails closed. The directory must be a
native absolute, existing path. Do not substitute the process cwd, environment
terminal representation, or `agent_workspace` (which is a workspace name, not a
path).

## Session directory resolution

1. `AI_MEMORY_CWD` — explicit override.
2. The `cwd` kwarg from Hermes.
3. `agent.runtime_cwd.resolve_agent_cwd()` — when Hermes is importable.

The plugin never falls back to `os.getcwd()`.

## Read the actual provider instance

`provider.scope_diagnostics()` returns an allowlisted snapshot, under the
provider lock, without contacting the server or reading/writing memory:

- `cwd_received`: the directory string received at initialization, or empty.
- `cwd_source`: `environment` (`AI_MEMORY_CWD`), `kwargs` (Hermes), `runtime`
  (`resolve_agent_cwd()`), or empty when nothing resolved.
- `cwd_normalized`: native `Path` spelling after validation, or empty if invalid.
  This is not MSYS conversion, symlink canonicalization, or a cwd fallback.
- `search_scope`, `workspace`, `project`.
- `workspace_source` / `project_source`: `explicit`, `marker`, `derived`, or
  empty.
- `scope_known`, `writes_allowed`, `project_search_allowed`.

Inspect this method on the **already initialized instance** in a debugger or
host integration. Do not initialize another live provider just to inspect it:
normal initialization may fetch/consume a handoff when scope is known.
`ai_memory_status` checks the server; it is not this local diagnostic.

Initialization also emits an INFO record on the plugin's `provider` logger,
with the same fields. Path and scope values use `%r`, escaping newlines;
no configuration dump, URL, session transcript, handoff, token or API key is
included. Paths and project names can still identify a checkout, so treat
these logs as local operational metadata. Read the `ai-memory scope:` record
from a normal session startup; no memory-writing prompt is needed. Logging
visibility depends on the host's configured handlers and levels.

An unknown scope still reports the configured/default project name, but
`scope_known=False` and both authorization flags are false. That default name
is **not** evidence of a resolved project or permission to access it.

## Offline regression check

From this repository:

```bash
uv run pytest tests/test_cwd_diagnostics.py tests/test_directory_scope.py tests/test_scope_derivation.py -q
```

Tests use temporary monorepos and fake clients/HTTP transports; the suite
blocks real socket connections and isolates profile/environment scope.
The Windows case uses the native filesystem and confirms that the closest
application marker (`socorro-financeiro`) wins over `imperio_2026` when the
provider actually receives the application directory. Other regressions cover
missing/relative/drive-relative/root-relative directories, files, absent cwd,
`resolve_agent_cwd()`/`AI_MEMORY_CWD` fallbacks, secret-free diagnostics,
marker-walk boundaries, BOM handling, derived projects and reinitialization.
Existing directory-scope tests cover cache isolation, captured asynchronous
context and obsolete workers.

Explicit workspace/project overrides continue to outrank directory markers, and
a marker's pinned project outranks a derived one. Changing a terminal directory
or passing cwd to `on_session_switch` does not reinitialize directory scope: a
new instance/session initialization with the correct cwd is required. No user
config or host installation is changed here.
