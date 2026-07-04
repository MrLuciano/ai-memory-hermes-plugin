# Phase 3 Plan Check: AiMemoryProvider

**Phase:** Phase 3 — Provider  
**Plan file:** `.planning/plans/phase-3/PLAN.md`  
**Requirements:** PRO-01 through PRO-09  
**Date:** 2026-07-03  
**Status:** ❌ **ISSUES FOUND — BLOCKER**

---

## Dimensional Results

| Dimension | Result |
|-----------|--------|
| 1. Requirement Coverage | ✅ PASS — All 9 PRO requirements covered |
| 2. Task Completeness | ✅ PASS — All 4 tasks have Files + Action + Verify + Done |
| 3. Dependency Correctness | ✅ PASS — No cycles, valid wave ordering |
| 4. Key Links Planned | ✅ PASS — Tests wired to provider via existing fixture pattern |
| 5. Scope Sanity | ⚠️ WARNING — 4 tasks (borderline), but only 2 files |
| 6. Verification Derivation | ✅ PASS — Truths are user-observable, artifacts map correctly |
| 7. Context Compliance | ⏭️ SKIPPED — No CONTEXT.md for Phase 3 |
| 7c. Architectural Tier Compliance | ⏭️ SKIPPED — No RESEARCH.md |
| 8. Nyquist Compliance | ⏭️ SKIPPED — `nyquist_validation: false` in config |
| 9. Cross-Plan Data Contracts | ✅ PASS — Single plan, no cross-plan data conflicts |
| 10. AGENTS.md Compliance | ✅ PASS — All project conventions respected |
| 11. Research Resolution | ⏭️ SKIPPED — No RESEARCH.md |
| 12. Pattern Compliance | ⚠️ WARNING — Plan deviates from PATTERNS-3.md pattern (see blocker) |

---

## BLOCKER: ABC Import Fallback Has NameError Bug

### Issue

**Task 2, Step 1** (lines 411-419 in PLAN.md) defines the `except ImportError` fallback for the conditional `MemoryProvider` ABC import as:

```python
except ImportError:
    from abc import ABC as MemoryProvider  # type: ignore[assignment]

    class MemoryProvider(ABC):  # type: ignore[no-redef]
        """Local fallback when Hermes is not installed."""
        ...
```

This code **will crash with `NameError: name 'ABC' is not defined`** at runtime. The `from abc import ABC as MemoryProvider` import aliases `ABC` under the name `MemoryProvider` — the original name `ABC` is **not** introduced into the local namespace. The subsequent `class MemoryProvider(ABC):` references `ABC` which doesn't exist.

**Confirmed by direct test:**
```
$ python3 -c "
from abc import ABC as MemoryProvider
class MemoryProvider(ABC): ...
"
ERROR: name 'ABC' is not defined
```

**Impact:** In the test environment (where Hermes Agent is NOT installed — which is the normal case for CI/dev), the `try: from agent.memory_provider import MemoryProvider` will fail with `ImportError`, the `except` block runs, hits `NameError`, and **the entire provider module fails to import**. Every test in `test_provider.py` (and any test importing from `provider`) will crash with `ImportError` wrapping the `NameError`.

### Root Cause

The plan introduced a class-redefinition approach that differs from the verified pattern in PATTERNS-3.md. The PATTERNS-3.md document provides **two correct alternatives**:

**Option A** (from PATTERNS-3.md lines 632-636 — "ABC integration strategy"):
```python
from abc import ABC as _ABC

class MemoryProvider(_ABC):  # type: ignore[no-redef]
    """Local fallback when Hermes is not installed."""
    ...
```

**Option B** (from PATTERNS-3.md lines 698-701 — "Pattern Assignments"):
```python
from abc import ABC as MemoryProvider  # type: ignore[assignment, misc]
```

Both are correct. The plan's version mixes both approaches incorrectly — it aliases as `MemoryProvider` but then tries to reference `ABC` by its original name.

### Fix

Replace the `except ImportError` block in Task 2, Step 1 with either Option A or Option B above. **Option A is preferred** because the empty class body (`...`) provides a clear type-checking target and allows docstrings. If using Option A, add `from abc import ABC as _ABC` and remove the standalone `from abc import ABC as MemoryProvider` line.

```python
except ImportError:
    from abc import ABC as _ABC

    class MemoryProvider(_ABC):  # type: ignore[no-redef]
        """Local fallback when Hermes is not installed.

        All methods have no-op defaults — the real ABC uses @abstractmethod
        for name, is_available, initialize, and get_tool_schemas.
        """
        ...
```

---

## WARNING: Near-Limit Task Count (4 tasks)

### Issue

The plan packs 4 tasks into a single PLAN.md. The 2-3 task target is exceeded, hitting the warning threshold. While only 2 files are modified (mitigating context impact), each task is dense:

| Task | Type | Files | Steps |
|------|------|-------|-------|
| 1 | TDD RED | test_provider.py | 12 steps, 11 test changes |
| 2 | TDD GREEN | provider.py + test_provider.py | 11 steps, 7 code changes |
| 3 | TDD RED | test_provider.py | 10 steps, 8 new tests |
| 4 | TDD GREEN | provider.py + test_provider.py | 5 steps, 1 method rewrite |

**Mitigation:** The plan is well-structured with clear wave boundaries and commit points. The RED→GREEN pairing makes the dependency structure explicit. However, Task 1's 12 steps with 11 test modifications is ambitious — the executor must carefully track which tests are renamed vs removed vs added. Consider whether the pre/post test counts (lines 550-564) are worth verifying before proceeding.

---

## WARNING: Exception-Swallowing Tests Are Vacuously Passing

### Issue

Task 3's `test_sync_turn_swallows_exceptions` and `test_on_session_end_swallows_exceptions` tests cannot actually verify exception swallowing:

```python
def test_sync_turn_swallows_exceptions(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock(side_effect=RuntimeError("boom"))
    provider.sync_turn("user msg", "assistant msg", session_id="sess-1")
    time.sleep(0.05)  # Let daemon thread execute
```

`sync_turn()` spawns a daemon thread and returns immediately. The test only verifies that `sync_turn()` itself doesn't raise — which is guaranteed because the method only creates a `Thread` object and calls `.start()`. The actual exception (from the `MagicMock` side effect in the daemon thread) is swallowed by the `try/except Exception: pass` inside `_do()` — but **this test has no way to observe that**. If the try/except were removed from `_do()`, the test would still pass (the exception would crash the daemon thread silently, and pytest would never know).

The `time.sleep(0.05)` is also fragile — on a slow CI machine, the daemon thread might not execute before the test ends. The test passes either way (thread runs and exception is swallowed, or thread doesn't run at all).

This is an acknowledged limitation in the plan (Risk Assessment: "Daemon thread tests are flaky"). It doesn't block execution but means PRO-08/PRO-09 exception behavior relies on code inspection more than test verification.

**Mitigation in execution:** After Task 2 completes, manually verify that `sync_turn()` and `on_session_end()` still have `try/except Exception: pass` wrapping the `self._client.send_hook()` call. The existing code already has this — the task should preserve it.

---

## WARNING: mypy `exclude` Pattern Skips Plugin Code

### Issue

`pyproject.toml` line 30: `exclude = ["ai-memory"]`

This fnmatch/regex pattern excludes `plugins/memory/ai-memory/provider.py` from mypy type-checking (the path contains "ai-memory"). The plan's final verification step (`mypy .` → "Success: no issues found") will pass **not because the code is correct, but because mypy never inspects it.**

This is a pre-existing issue (not introduced by this plan) and is flagged in ROADMAP.md's risk section: "mypy excludes plugins/ directory in pyproject.toml → Plugin code not type-checked → High." It was supposed to be fixed in Phase 1.

**Impact:** The two `# type: ignore` comments in the conditional ABC import (`assignment`, `no-redef`) may not be tested properly. Additionally, any type errors in the new `initialize()` workspace resolution logic or `handle_tool_call` return type change won't be caught.

**Recommended fix (out of scope for this plan but flagged for Phase 4):** Change `exclude = ["ai-memory"]` to `exclude = []` and add `# type: ignore` comments as needed for third-party modules without stubs.

---

## INFO: "ABC Inheritance Test" Referenced but Not Defined

### Issue

The Task 1 commit message (line 374) mentions "plus ABC inheritance test (PRO-01)" but no such standalone test exists in the plan's 11 task steps. The steps add tests for kwargs absorption, daemon threading, metadata, and signature rewrites — but no explicit `test_provider_inherits_from_memory_provider` or similar.

**Assessment:** This is acceptable because the test fixture `provider()` in `test_provider.py` implicitly validates ABC compliance: if `AiMemoryProvider(MemoryProvider)` has unimplemented abstract methods, Python raises `TypeError` at instantiation time. Since the fixture creates `AiMemoryProvider(config=cfg)`, any abstract method gap would cause an immediate test failure.

The plan correctly acknowledges (in the gap analysis) that explicit `isinstance(provider, MemoryProvider)` is impractical without Hermes installed. The implicit verification via fixture instantiation is sufficient.

**Recommendation:** Remove the "ABC inheritance test" reference from the commit message to avoid confusion, or add it as an inline comment.

---

## Summary

### Issues

```yaml
issues:
  - plan: "PLAN.md"
    dimension: pattern_compliance
    severity: blocker
    description: >
      Task 2 Step 1's except ImportError fallback has a NameError bug:
      'class MemoryProvider(ABC):' references ABC which is not in scope
      (it was aliased as MemoryProvider). Code will crash on import in
      test/CI environments where Hermes Agent is not installed.
    task: 2
    fix_hint: >
      Replace the except block with PATTERNS-3.md's correct pattern:
      'from abc import ABC as _ABC; class MemoryProvider(_ABC): ...'

  - plan: "PLAN.md"
    dimension: scope_sanity
    severity: warning
    description: >
      4 tasks in a single PLAN.md exceeds the 2-3 target threshold.
      Only 2 files modified, but Task 1 has 12 steps with 11 test
      modifications.
    fix_hint: >
      Consider splitting into two plan files if context budget is a
      concern. Acceptable as-is given only 2 files touched.

  - plan: "PLAN.md"
    dimension: task_completeness
    severity: warning
    description: >
      Daemon thread exception-swallowing tests (Task 3 Steps 5-6) are
      vacuously passing — they assert sync_turn/on_session_end don't
      raise (guaranteed, these methods only spawn threads), but can't
      verify the daemon thread's try/except actually catches errors.
    task: 3
    fix_hint: >
      Add threading.Event-based synchronization to confirm the daemon
      thread executed, or accept the limitation and document it in the
      test docstring.

  - plan: "PLAN.md"
    dimension: task_completeness
    severity: info
    description: >
      Task 1 commit message references "ABC inheritance test" but no
      standalone test exists in the plan steps. ABC compliance is
      verified implicitly by the existing test fixture.
    task: 1
    fix_hint: >
      Adjust commit message to not claim an explicit ABC inheritance
      test, or add a 'hasattr(AiMemoryProvider, 'prefetch')' check.
```

### Verdict

**❌ ISSUES FOUND — 1 blocker, 2 warnings, 1 info**

The **blocker** (NameError in ABC import fallback) must be fixed before execution. The plan as written will cause `provider.py` to fail on import in any environment without Hermes Agent installed (CI, dev, test), making the entire test suite unimportable.

The warning-level issues are acceptable for execution but should be noted:
- The 4-task count is at the boundary but manageable with only 2 source files
- The daemon thread tests have inherent limitations that the plan honestly acknowledges

**Fix the import fallback and proceed to execution.**
