# Phase 4: Entry Point — Implementation Plan

> **For agentic workers:** TDD mode is enabled (`workflow.tdd_mode: true`). Follow RED→GREEN→REFACTOR for every code change. Quality gates must pass after plan completion: `ruff check .`, `mypy .`, `pytest --cov` (fail_under 89). Your starting baseline: 57 tests at 89.91% coverage (0% on `__init__.py` — unaddressed until this phase).

**Goal:** The Hermes plugin loader can discover, load, and register the ai-memory plugin — making it available via `hermes plugins enable ai-memory` and `hermes memory setup`.

**Architecture:** Single sequential TDD wave. Task 1 (RED) writes the test for `register()` against the real Hermes plugin loader API (`ctx.register_memory_provider()`). Task 2 (GREEN) fixes `__init__.py` and verifies `plugin.yaml`.

**Tech Stack:** Python 3.10+, `AiMemoryProvider` (from Phase 3), `AiMemoryConfig` (Phase 1), `YAML` (stdlib — `pyyaml` or manual parse), `pytest`, `ruff`, `mypy`. No new dependencies.

---

## Key Discovery: Real Hermes `register()` API

The Hermes plugin loader (`plugins/memory/__init__.py` in `hermes-agent`) uses a `_ProviderCollector` pattern — **not** `ctx.agent.memory_provider = X`:

```python
# Hermes plugin loader calls:
collector = _ProviderCollector()
mod.register(collector)
# Then reads: collector.provider

# _ProviderCollector has:
class _ProviderCollector:
    def __init__(self):
        self.provider = None
    def register_memory_provider(self, provider):
        self.provider = provider
```

The official `register()` convention (from Hermes built-in `mem0` plugin):

```python
def register(ctx) -> None:
    """Register Mem0 as a memory provider plugin."""
    ctx.register_memory_provider(Mem0MemoryProvider())
```

**Impact:** Our current `__init__.py` stub returns the class instead of calling `ctx.register_memory_provider(instance)`. The fix must align with the real Hermes API. The mock `ctx` in tests must expose `register_memory_provider()`.

---

## Dependency Analysis

```
Wave 1 (sequential — both modify entry point files):
  ├─ Task 1 (TDD RED):    Write test_entry.py with mock ctx, 
  │                        register() protocol test, plugin.yaml validation
  │                        ── creates: tests/test_entry.py
  └─ Task 2 (TDD GREEN):   Fix __init__.py register() to call 
  │                        ctx.register_memory_provider(instance),
  │                        verify plugin.yaml completeness
                           ── modifies: plugins/memory/ai-memory/__init__.py
                               .planning/plans/phase-4/PLAN-CHECK.md
```

**Dependency edges:**
- **Task 2 depends on Task 1** — TDD RED→GREEN. Tests define expected behavior, then implementation satisfies it.
- **No external blockers.** Provider.py, client.py, config.py are all untouched. Conftest.py is untouched.
- **Implicit dependency on Phase 3 (Provider)** — `AiMemoryProvider` must be fully implemented. Phase 3 is complete.

**Why a single TDD wave?** The entry point is a thin layer (~5 lines of production code). Splitting into two waves would add overhead with no benefit.

---

## Goal-Backward Check

### Must-Have Truths (user/operator perspective)

| # | Truth | How Verified | Requirement |
|---|-------|-------------|-------------|
| T1 | `register()` is callable — Hermes loader can find it | `hasattr(mod, "register")` in test | ENT-01 |
| T2 | `register(ctx)` accepts a context object and registers a provider via `ctx.register_memory_provider()` | Mock ctx captures call | ENT-01, ENT-02 |
| T3 | The registered provider is a live `AiMemoryProvider` instance (not a class) | `isinstance(captured, AiMemoryProvider)` | ENT-02 |
| T4 | `plugin.yaml` is valid YAML with expected fields | YAML parse + field assertions | ENT-03 |
| T5 | `plugin.yaml` declares `httpx` as runtime dependency | `pip_dependencies` contains `httpx` | ENT-03 |
| T6 | `plugin.yaml` declares `on_session_end` hook | `hooks` list contains `on_session_end` | ENT-03 |
| T7 | The provider's `get_config_schema()` is accessible after registration | `hasattr(provider, "get_config_schema")` | hermes memory setup |

### Requirement Coverage

| Req | Description | How Satisfied | Tasks |
|-----|-------------|--------------|-------|
| **ENT-01** | `__init__.py` exposes `register(ctx)` compatible with Hermes plugin loader | Function exists at module level, matches Hermes `register(ctx)` signature → `None` | Tasks 1, 2 |
| **ENT-02** | `register(ctx)` instantiates `AiMemoryProvider` and registers it | Calls `ctx.register_memory_provider(AiMemoryProvider())` | Tasks 1, 2 |
| **ENT-03** | `plugin.yaml` declares `httpx` dependency and `on_session_end` hook | YAML verified to contain `pip_dependencies: [httpx]` and `hooks: [on_session_end]` | Task 2 |

---

## Baseline State (before any changes)

```
$ python3 -m pytest tests/ -v
→ 57 passed (100%)

$ python3 -m pytest --cov=plugins/memory/ai-memory
→ 89.91% (fail_under=89 reached)
  __init__.py: 0% (3 lines — not yet exercised by any test)

$ python3 -m ruff check .
→ All checks passed!

$ python3 -m mypy .
→ Success: no issues found in 5 source files
```

**Key insight:** `__init__.py` sits at 0% coverage because no test imports and calls `register()`. Phase 4 tests will bring this to ~100%. The overall project coverage is 89.91% — just 0.91% above the threshold. Adding ~5 passing tests for `__init__.py` will increase coverage; the 3 `__init__.py` lines going from 0% to 100% adds roughly `(3 * 0.9) / (228 + 3 + new_test_code)` — but new test code also adds uncovered statements. The net effect should still be positive.

**Existing `__init__.py` (the problem):**
```python
from provider import AiMemoryProvider

def register(ctx: object) -> type[AiMemoryProvider]:
    return AiMemoryProvider
```

Problems:
1. Returns the **class** instead of calling `ctx.register_memory_provider(instance)` 
2. Return type is `type[AiMemoryProvider]` — Hermes loader ignores return values
3. Never instantiates `AiMemoryProvider`

**Existing `plugin.yaml` (already correct — verify only):**
```yaml
name: ai-memory
version: 0.1.0
description: "ai-memory wiki-backed long-term memory provider"
pip_dependencies:
  - httpx
hooks:
  - on_session_end
```

---

## Task Breakdown

---

### Wave 1 — Entry Point Registration (TDD Cycle)

---

### Task 1 (RED): Write entry point tests with mock ctx

**Type:** TDD (RED)
**Files:**
- Create: `tests/test_entry.py` — 5 new tests for register() protocol, plugin.yaml validation

**Step 1 — Pre-flight verification:**
```bash
python3 -m pytest tests/ -v
# Expected: 57 passed (baseline confirmed)
```

**Step 2 — Create `tests/test_entry.py` with the following content:**

```python
"""Tests for Phase 4 — Entry Point (ENT-01, ENT-02, ENT-03).

Tests the register() function and plugin.yaml metadata.
Uses a mock ctx object matching the Hermes _ProviderCollector API.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
import pytest

sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "plugins/memory/ai-memory"),
)

# Import AFTER sys.path insert
from __init__ import register  # noqa: E402
from provider import AiMemoryProvider  # noqa: E402


class MockCtx:
    """Simulates Hermes _ProviderCollector for register(ctx)."""

    def __init__(self) -> None:
        self.provider: Any = None
        self.tools: list[dict[str, Any]] = []
        self.hooks: list[str] = []

    def register_memory_provider(self, provider: Any) -> None:
        self.provider = provider

    def register_tool(self, *args: Any, **kwargs: Any) -> None:
        self.tools.append(args or kwargs)

    def register_hook(self, *args: Any, **kwargs: Any) -> None:
        self.hooks.append(args[0] if args else "")


def test_register_exists() -> None:
    """ENT-01: register is a callable function at module level."""
    assert callable(register)


def test_register_returns_none() -> None:
    """ENT-01: register() has no return value (Hermes ignores returns)."""
    ctx = MockCtx()
    result = register(ctx)
    assert result is None


def test_register_calls_register_memory_provider() -> None:
    """ENT-02: register(ctx) calls ctx.register_memory_provider()."""
    ctx = MockCtx()
    register(ctx)
    assert ctx.provider is not None


def test_register_passes_ai_memory_provider_instance() -> None:
    """ENT-02: Registered provider is an AiMemoryProvider instance (not a class)."""
    ctx = MockCtx()
    register(ctx)
    assert isinstance(ctx.provider, AiMemoryProvider)


def test_plugin_yaml_has_httpx_dependency() -> None:
    """ENT-03: plugin.yaml declares httpx as a runtime dependency."""
    yaml_path = (
        Path(__file__).parent.parent
        / "plugins/memory/ai-memory"
        / "plugin.yaml"
    )
    assert yaml_path.exists(), "plugin.yaml not found"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    deps = data.get("pip_dependencies", [])
    assert "httpx" in deps, (
        f"Expected httpx in pip_dependencies, got {deps}"
    )


def test_plugin_yaml_has_on_session_end_hook() -> None:
    """ENT-03: plugin.yaml declares on_session_end hook."""
    yaml_path = (
        Path(__file__).parent.parent
        / "plugins/memory/ai-memory"
        / "plugin.yaml"
    )
    assert yaml_path.exists(), "plugin.yaml not found"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    hooks = data.get("hooks", [])
    assert "on_session_end" in hooks, (
        f"Expected on_session_end in hooks, got {hooks}"
    )


def test_registered_provider_has_config_schema() -> None:
    """hermes memory setup: registered provider exposes get_config_schema()."""
    ctx = MockCtx()
    register(ctx)
    assert hasattr(ctx.provider, "get_config_schema")
    schema = ctx.provider.get_config_schema()
    assert isinstance(schema, list)
    assert len(schema) > 0
    keys = [f["key"] for f in schema]
    assert "server_url" in keys
```

**Step 3 — Verify `pyyaml` is available:**
```bash
python3 -c "import yaml; print(yaml.__version__)"
# Expected: version printed (e.g., 6.0)
# If ImportError: pip install pyyaml
```

If `pyyaml` is not installed, either:
- Install it: `pip install pyyaml`
- Or rewrite the YAML tests to use manual parsing (less robust)

**Step 4 — Verify RED (tests fail because __init__.py hasn't been fixed):**
```bash
python3 -m pytest tests/test_entry.py -v
# Expected: 4 of 7 pass, 3 FAIL:
#   test_register_returns_none:     FAIL — currently returns type[AiMemoryProvider]
#   test_register_calls_register_memory_provider:     FAIL — doesn't call it
#   test_register_passes_ai_memory_provider_instance: FAIL — doesn't instantiate
#   test_register_exists:           PASS (function exists)
#   test_plugin_yaml_has_*:         PASS (yaml already correct)
#   test_registered_provider_has_config_schema: FAIL — provider never registered
```

Actually, let me reconsider. The existing `register()`:
```python
def register(ctx: object) -> type[AiMemoryProvider]:
    return AiMemoryProvider
```

1. `test_register_returns_none` — FAILS because it returns `AiMemoryProvider` class
2. `test_register_calls_register_memory_provider` — FAILS because it doesn't call any ctx method
3. `test_register_passes_ai_memory_provider_instance` — FAILS because `ctx.provider is None`
4. `test_register_exists` — PASSES (callable)
5. YAML tests — PASSES (yaml already correct)
6. `test_registered_provider_has_config_schema` — FAILS because `ctx.provider is None`

So 4 FAIL, 3 PASS (the yaml tests + existence).

**Step 5 — Verify unchanged tests still pass:**
```bash
python3 -m pytest tests/ -v --ignore=tests/test_entry.py
# Expected: 57 passed (no regressions)
```

**Commit:**
```bash
git add tests/test_entry.py
git commit -m "test(ent-01,ent-02,ent-03): add entry point tests with mock ctx (RED)

Seven new tests:
- test_register_exists — verify register is callable (ENT-01)
- test_register_returns_none — verify void return (ENT-01)
- test_register_calls_register_memory_provider — calls ctx method (ENT-02)
- test_register_passes_ai_memory_provider_instance — instance check (ENT-02)
- test_plugin_yaml_has_httpx_dependency — yaml deps (ENT-03)
- test_plugin_yaml_has_on_session_end_hook — yaml hooks (ENT-03)
- test_registered_provider_has_config_schema — wizard compat

3 tests pass (yaml + existence), 4 fail until __init__.py is fixed.
Expected RED state for TDD.
"
```

---

### Task 2 (GREEN): Fix `__init__.py` register() and verify plugin.yaml

**Type:** TDD (GREEN)
**Files:**
- Modify: `plugins/memory/ai-memory/__init__.py` — fix register() to use ctx.register_memory_provider()
- Verify: `plugins/memory/ai-memory/plugin.yaml` — confirm correct (no changes needed)

**Step 1 — Fix `plugins/memory/ai-memory/__init__.py`:**

Current content (4 lines):
```python
from provider import AiMemoryProvider


def register(ctx: object) -> type[AiMemoryProvider]:
    return AiMemoryProvider
```

Replace with:
```python
from __future__ import annotations

from typing import Any

from provider import AiMemoryProvider


def register(ctx: Any) -> None:
    """Register AiMemoryProvider with the Hermes plugin loader.

    Called by Hermes plugin loader with a _ProviderCollector ctx.
    Follows the register(ctx) convention from built-in Hermes providers
    (mem0, hindsight, holographic, etc.).
    """
    ctx.register_memory_provider(AiMemoryProvider())
```

Changes:
- Added `from __future__ import annotations` for PEP 604 compat (matching project convention)
- Added `from typing import Any` for the ctx type
- Return type `type[AiMemoryProvider]` → `None`
- Body `return AiMemoryProvider` → `ctx.register_memory_provider(AiMemoryProvider())`
- Added docstring explaining the Hermes convention

**Step 2 — Verify GREEN (all entry point tests pass):**
```bash
python3 -m pytest tests/test_entry.py -v
# Expected: 7 passed
#   test_register_exists:                   PASS
#   test_register_returns_none:             PASS (now returns None)
#   test_register_calls_register_memory_provider: PASS (calls ctx method)
#   test_register_passes_ai_memory_provider_instance: PASS (AiMemoryProvider())
#   test_plugin_yaml_has_httpx_dependency:  PASS
#   test_plugin_yaml_has_on_session_end_hook: PASS
#   test_registered_provider_has_config_schema: PASS
```

**Step 3 — Verify full suite (no regressions):**
```bash
python3 -m pytest tests/ -v
# Expected: 64 passed (57 existing + 7 new entry point tests)
```

**Step 4 — Verify quality gates:**
```bash
python3 -m ruff check .
# Expected: All checks passed

python3 -m mypy .
# Expected: Success: no issues found in 5 source files
# Note: __init__.py now has type annotations — mypy should pass
```

**Step 5 — Verify coverage >= 89%:**
```bash
python3 -m pytest --cov=plugins/memory/ai-memory --cov-report=term-missing
# Expected: total coverage >= 89%
# __init__.py: 0% → ~100% (3 statements now exercised by register() tests)
# Overall: ~90% (slight bump from __init__.py coverage)
```

Coverage calculation:
- Before: 228 total stmts, 23 missed → 89.91%
- After: 228 + 3 new __init__ stmts = 231 total. The 3 __init__ stmts were 3 missed, now 0 missed. So 20 missed / 231 = 91.34%.
- Wait, the existing `__init__.py` already has 3 statements that coverage counts as "3 statements, 3 missed." When we add the import statements (`from __future__ import annotations`, `from typing import Any`), that adds more statements. Let me be more precise:

Current `__init__.py`:
```python
from provider import AiMemoryProvider          # line 1: statement
# (blank line)                                  # line 2: not a statement
# (blank line)                                  # line 3: not a statement
def register(ctx: object) -> type[AiMemoryProvider]:  # line 4: statement (def)
    return AiMemoryProvider                      # line 5: statement
```

Coverage says 3 statements, 3 missed.

New `__init__.py`:
```python
from __future__ import annotations              # line 1: statement
# (blank line)                                  # line 2: not a statement
from typing import Any                          # line 3: statement
# (blank line)                                  # line 4: not a statement
from provider import AiMemoryProvider           # line 5: statement
# (blank line)                                  # line 6: not a statement
# (blank line)                                  # line 7: not a statement
def register(ctx: Any) -> None:                 # line 8: statement (def)
    """Register..."""                           # line 9: not a statement (docstring)
    ctx.register_memory_provider(AiMemoryProvider())  # line 10: statement
```

That's 5 statements (imports, def, return). Once test_entry.py calls `register()`, all 5 get covered → 5 additional covered statements.

New total: 228 + 2 = 230 (net: added 5 __init__ stmts, removed 3 old, = +2)
Actually coverage counts from the actual files. The new file content replaces the old. So:

Old: 228 total, 23 missed → 89.91%
New: 228 - 3 (removed old __init__ stmts) + 5 (new __init__ stmts) + test code stmts = 230 + test code

The test code for `test_entry.py` is ~60 lines with ~20 executable statements. Those test statements will be uncovered (only covered when tests run, and `--cov=plugins/memory/ai-memory` only covers the plugin code, not tests).

So: 228 - 3 + 5 = 230 total plugin statements.
Missed: 23 - 3 (old __init__ missed) + 0 (new __init__ covered) = 20 missed.
Coverage: (230 - 20) / 230 = 91.30%

That's comfortably above 89%. ✅

**Step 6 — Verify plugin.yaml is complete:**

Read and confirm current `plugin.yaml`:
```yaml
name: ai-memory
version: 0.1.0
description: "ai-memory wiki-backed long-term memory provider"
pip_dependencies:
  - httpx
hooks:
  - on_session_end
```

This already satisfies ENT-03 (httpx dependency + on_session_end hook). No changes required. The yaml tests in `test_entry.py` already validate this programmatically.

Optional enhancement: Add `provider_type: memory` for Hermes plugin metadata completeness (the directory at `plugins/memory/ai-memory/` already establishes this by location, but explicit metadata helps). This is **not required** — the loader discovers by directory — but is a good practice.

To keep scope minimal, **no changes to plugin.yaml unless tests reveal an issue.**

**Commit:**
```bash
git add plugins/memory/ai-memory/__init__.py
git commit -m "feat(ent-01,ent-02): fix register() to use ctx.register_memory_provider() (GREEN)

Changes to __init__.py:
- register() now calls ctx.register_memory_provider(AiMemoryProvider())
  instead of returning the class (ENT-01, ENT-02)
- Added from __future__ import annotations for PEP 604 compat
- Added proper type hints (Any for ctx, None return)
- Added docstring explaining Hermes convention

All 64 tests pass (57 existing + 7 new entry point tests).
plugin.yaml verified correct for ENT-03 (no changes needed).
"
```

---

## Optional Enhancement: Add `provider_type: memory` to plugin.yaml

**Not required** but improves Hermes plugin metadata completeness. The Hermes plugin documentation specifies that memory providers at `plugins/memory/<name>/` are auto-discovered by location, but explicit `provider_type: memory` in plugin.yaml provides additional metadata for tooling and documentation.

If you choose to add it:
```yaml
name: ai-memory
version: 0.1.0
description: "ai-memory wiki-backed long-term memory provider"
provider_type: memory
pip_dependencies:
  - httpx
hooks:
  - on_session_end
```

This is a SAFE additive change — no existing behavior depends on the yaml format beyond what ENT-03 requires.

---

## Final Quality Gate Verification

Run after both tasks complete:

```bash
# Full suite
python3 -m pytest tests/ -v
# Expected: 64 passed (57 existing + 7 new)

# Lint
python3 -m ruff check .
# Expected: All checks passed

# Type checking
python3 -m mypy .
# Expected: Success: no issues found

# Coverage
python3 -m pytest --cov=plugins/memory/ai-memory --cov-report=term-missing
# Expected: total coverage >= 89% (estimated ~91%)
# __init__.py: ~100% (3+ statements now exercised)
```

**If coverage drops below 89%:**
The only risk is if `from __future__ import annotations` or `from typing import Any` are counted as uncovered by coverage (they're imports, usually counted as covered when the module is imported). If coverage is below 89% after adding test code, run:

```bash
python3 -m pytest --cov=plugins/memory/ai-memory --cov-report=term-missing
```

Look for the `Missing` column to identify uncovered lines. Most likely cause: the `import yaml` in `test_entry.py` pulls in `pyyaml` which may not be installed in the test environment. If `pyyaml` is missing, the YAML tests will skip (add a `pytest.importorskip("yaml")` guard) and the coverage for plugin code won't be affected.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Actually, the existing code has a bug — task 1 might identify it, but it might not.** | test that would catch it | test might break | Write the test first, then the fix. That's TDD. |
| **plugin.yaml YAML parse test needs pyyaml dependency** | Medium | Low | Add `pytest.importorskip("yaml")` if pyyaml not available, or use manual string parsing. The yaml is simple enough to validate line-by-line. |
| **__init__.py test imports cause circular imports** | Low | Low | Test uses `sys.path.insert` (same pattern as `conftest.py`). Circular imports not possible — `register()` only imports `AiMemoryProvider`, which doesn't import `__init__`. |
| **Coverage threshold** | Low | Low | __init__.py going from 0% to ~100% adds ~2 percentage points. Test code is excluded (--cov=plugins/memory/ai-memory). Estimate: ~91%. |
| **Hermes plugin loader API changes** | Low | Low | Verified against `hermes-agent` main branch code. The `register(ctx)` → `ctx.register_memory_provider()` pattern is documented in the Hermes plugin dev guide. |
| **ENT-02 says "assigns to ctx.agent.memory_provider" but Hermes API uses ctx.register_memory_provider()** | Medium | Low | The requirement was written before the real Hermes API was verified. We follow the real Hermes API. The test validates `register_memory_provider()` call. |

---

## Definition of Done

**All of the following must be true:**

- [ ] `python3 -m pytest tests/test_entry.py -v` → **7 passed**
- [ ] `python3 -m pytest tests/ -v` → all tests pass (64 total: 57 existing + 7 new)
- [ ] `python3 -m ruff check .` → zero errors
- [ ] `python3 -m mypy .` → "Success: no issues found"
- [ ] `python3 -m pytest --cov=plugins/memory/ai-memory` → coverage **>= 89%**
- [ ] `register()` is callable at module level — ENT-01 (tested by `test_register_exists`)
- [ ] `register(ctx)` returns `None` — ENT-01 (tested by `test_register_returns_none`)
- [ ] `register(ctx)` calls `ctx.register_memory_provider()` — ENT-02 (tested by `test_register_calls_register_memory_provider`)
- [ ] The registered object is an `AiMemoryProvider` instance — ENT-02 (tested by `test_register_passes_ai_memory_provider_instance`)
- [ ] `plugin.yaml` contains `httpx` in `pip_dependencies` — ENT-03 (tested by `test_plugin_yaml_has_httpx_dependency`)
- [ ] `plugin.yaml` contains `on_session_end` in `hooks` — ENT-03 (tested by `test_plugin_yaml_has_on_session_end_hook`)
- [ ] Registered provider exposes `get_config_schema()` — hermes memory setup compat (tested by `test_registered_provider_has_config_schema`)
- [ ] All commits reference requirement IDs (ENT-01, ENT-02, ENT-03)

### Requirement Coverage

| Req | Description | Status | Evidence |
|-----|-------------|--------|----------|
| **ENT-01** | `__init__.py` exposes `register(ctx)` compatible with Hermes plugin loader | ✅ Fixed | `def register(ctx: Any) -> None` at module level. 2 tests pass (existence + None return). |
| **ENT-02** | `register(ctx)` instantiates `AiMemoryProvider` and registers it | ✅ Fixed | `ctx.register_memory_provider(AiMemoryProvider())`. 2 tests pass (ctx call + instance check). |
| **ENT-03** | `plugin.yaml` declares `httpx` dependency and `on_session_end` hook | ✅ Verified | Plugin YAML already correct. 2 tests pass (httpx dep + on_session_end hook). |

---

## Execution Order

```bash
# Wave 1 (sequential — RED→GREEN for entry point):
#   Task 1: Write test_entry.py with mock ctx tests (RED)
#   Task 2: Fix __init__.py register() to match Hermes API (GREEN)

# Final verification:
python3 -m ruff check . && python3 -m mypy . && python3 -m pytest tests/ --cov=plugins/memory/ai-memory
```
