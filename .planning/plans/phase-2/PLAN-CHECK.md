# Phase 2 Plan Check — PASS (with issues)

**Phase:** 2 — Client (AiMemoryClient)
**Plan file:** `.planning/plans/phase-2/PLAN.md`
**Requirements:** CLI-01 through CLI-08
**Date:** 2026-07-03

---

## Dimension Results

| Dimension | Result |
|-----------|--------|
| 1. Requirement Coverage | ✅ PASS |
| 2. Task Completeness | ✅ PASS (1 warning) |
| 3. Dependency Correctness | ✅ PASS |
| 4. Key Links Planned | ✅ PASS |
| 5. Scope Sanity | ✅ PASS (1 warning) |
| 6. Verification Derivation | ✅ PASS |
| 7. Context Compliance | ⏭️ SKIPPED (no CONTEXT.md) |
| 7b. Scope Reduction | ⏭️ SKIPPED |
| 7c. Tier Compliance | ⏭️ SKIPPED |
| 8. Nyquist Compliance | ⏭️ SKIPPED (no VALIDATION.md) |
| 9. Cross-Plan Data | ⏭️ SKIPPED (single plan) |
| 10. AGENTS.md Compliance | ✅ PASS |
| 11. Research Resolution | ⏭️ SKIPPED (no RESEARCH.md) |
| 12. Pattern Compliance | ✅ PASS |

---

## Dimension 1: Requirement Coverage ✅

All 8 requirements have explicit coverage:

| Req | Description | Coverage | Tasks |
|-----|-------------|----------|-------|
| CLI-01 | `search()` → `GET /admin/search` | ✅ | Tasks 1, 2 |
| CLI-02 | `write_page()` → `POST /admin/write-page` with `tier`/`pinned` | ✅ | Tasks 2, 3, 4 |
| CLI-03 | `status()` → `GET /admin/status` | ✅ | Task 2 |
| CLI-04 | `send_hook()` → `POST /hook` | ✅ | Existing (verified) |
| CLI-05 | `fetch_handoff()` → `GET /handoff` | ✅ | Tasks 1, 2 |
| CLI-06 | 500ms hook, 10s admin timeout | ✅ | Tasks 3, 4 |
| CLI-07 | Hook errors logged, not raised | ✅ | Existing (verified) |
| CLI-08 | Admin/tool errors propagate | ✅ | Tasks 1, 2 |

**CLI-04 parameter difference acknowledged:** The plan correctly identifies that the current signature `(event, session_id, payload, workspace, project)` differs from the spec `(messages, event, session_id, session_data)`, and correctly defers changing it to avoid breaking the provider. This is a documented deviation, not a gap.

---

## Dimension 2: Task Completeness ✅ (1 warning)

### Task 1 (RED) — ✅ Complete
- **Files:** `tests/test_client.py` — specific file named
- **Action:** 6 detailed steps with code blocks for all 3 test changes
- **Verify:** `pytest` commands with expected outcome for each step
- **Done:** Commit message with requirement ID references

### Task 2 (GREEN) — ✅ Complete
- **Files:** `plugins/memory/ai-memory/client.py` — specific file named
- **Action:** 5 detailed steps showing code before/after for each method
- **Verify:** `pytest` + `ruff` + `mypy` commands with expected counts
- **Done:** Commit message with requirement ID references

### Task 3 (RED) — ❌ Issue (see below)
- **Files:** ✅ `tests/test_client.py`
- **Action:** ✅ 4 detailed steps with code blocks
- **Verify:** ⚠️ Inaccurate expected outcomes (see issue)
- **Done:** ✅ Commit with requirement references

### Task 4 (GREEN) — ✅ Complete
- **Files:** `plugins/memory/ai-memory/client.py`
- **Action:** 2 steps with code blocks (self-correcting — acknowledges timeout changes not needed)
- **Verify:** `pytest` + `ruff` + `mypy` + `--cov` commands
- **Done:** Commit with requirement references

**Issue T-1:** Task 3 Step 5 claims all 3 new tests will FAIL with specific error messages:

> `test_client_search_uses_search_timeout: FAIL — captured_timeout mismatch or spy breaks`
> `test_client_hook_uses_hook_timeout: FAIL — captured_timeout mismatch or spy breaks`
> `test_client_write_page_with_tier_and_pinned: FAIL — "KeyError: 'tier'" or similar`

The `test_client_hook_uses_hook_timeout` test will actually **pass** at this point. `send_hook()` still wraps its `_request` call in a `try/except` (CLI-07 preserved), so the `ConnectError` from the real HTTP attempt (because no transport is set — see BLOCKER below) would be swallowed, the spy's `captured_timeout` would be set to 0.5, and the assertion would pass.

The plan internally acknowledges this (lines 634-655) but the verification step expectations are not updated to match. This is a WARNING because the executor may be confused when the verify output differs from what's documented.

---

## Dimension 3: Dependency Correctness ✅

```
Wave 1: Task 1 (RED) → Task 2 (GREEN)
Wave 2: Task 3 (RED) → Task 4 (GREEN)
Wave 2 depends on Wave 1 (same-file ownership: both modify test_client.py and client.py)
```

- No cycles ✅
- All references valid ✅
- Two-wave separation by concern is well-motivated ✅
- Same-file ownership correctly handled (sequential waves) ✅

---

## Dimension 4: Key Links Planned ✅

| Link | Connection | Status |
|------|-----------|--------|
| Error-propagation tests (Task 1) → code removal (Task 2) | Test→Code wiring | ✅ |
| Timeout tests (Task 3) → timeout params (Task 4) | Test→Code wiring | ✅ |
| Tier/pinned test (Task 3) → tier/pinned params (Task 4) | Test→Code wiring | ✅ |
| Provider tests → client changes | MagicMock isolates provider, no provider changes needed | ✅ Verified |
| send_hook() → send_hook test | Try/except preserved, existing test passes | ✅ |

---

## Dimension 5: Scope Sanity ✅ (1 warning)

**Metrics:**
- Tasks: 4 (2 per wave)
- Files modified: 2 (test_client.py, client.py)
- Dependencies: Sequential within and between waves

**Issue S-1:** 4 tasks is at the warning threshold (target 2-3, warning ≥4). However, the scope is narrow (only 2 files), the tasks are simple (remove try/except, add params), and the RED→GREEN separation per wave justifies the count. Acceptable but noted.

---

## Dimension 6: Verification Derivation ✅

**Truths:** 12 must-have truths are listed, all user- or operator-observable:
- Error behavior truths (T1-T7): observable at the provider/caller boundary ✅
- Tier/pinned parameter (T8): observable via test assertion on POST payload ✅
- Timeout values (T9-T12): slightly implementation-focused ("passes to _request") but support the user-observable CLI-06 requirement ✅

**Artifacts:** test_client.py and client.py — correctly identified as the modified files ✅

**Key links:** Requirement coverage table maps every CLI requirement to specific tasks ✅

**Quality gates:** All expected outcomes are measurable (pytest pass counts, ruff/mypy success, coverage %) ✅

Contingency plan for coverage < 89% is documented (non-transport `_request` path test) ✅

---

## ⚠️ BLOCKER: Task 3 search timeout test missing transport

**Dimension:** task_completeness

**Severity:** BLOCKER

**Description:** The test `test_client_search_uses_search_timeout` as written in Task 3 (lines 417-434) does not set `client._transport`, so the real `_request` method will attempt an actual HTTP connection. After Wave 1 (Task 2), `search()` no longer swallows exceptions. The `ConnectError` from the failed real connection propagates through `search()` (no `try/except` after Task 2), and the test fails with `ConnectError` **before** reaching the `assert captured_timeout == 10.0` assertion.

**Why it's a blocker:** The DoD requires "16 passed" for `test_client.py`, but this test can never pass as written. It will always fail with `ConnectError` because:
1. The `client` fixture (line 12-15 of test_client.py) does NOT set `_transport`
2. The test does NOT set `client._transport`
3. After Task 2 removes the `try/except` from `search()`, the `ConnectError` from the real HTTP attempt propagates to the test runner
4. The `pytest.raises(httpx.ConnectError)` wrapper is absent — this is NOT an expected-failure test

**Fix:** Add transport setup before `client.search("test query")`:

```python
def test_client_search_uses_search_timeout(client: AiMemoryClient) -> None:
    """search() passes SEARCH_TIMEOUT (10s) to _request."""
    captured_timeout: Any = None
    original_request = AiMemoryClient._request

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    def spy(self: AiMemoryClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
        nonlocal captured_timeout
        captured_timeout = kwargs.get("timeout")
        return original_request(self, method, path, **kwargs)

    client._transport = httpx.MockTransport(handler)
    AiMemoryClient._request = spy  # type: ignore[method-assign]
    try:
        client.search("test query")
        assert captured_timeout == 10.0  # SEARCH_TIMEOUT
    finally:
        AiMemoryClient._request = original_request
```

---

## Concern Responses

### Concern 1: Is `tier`/`pinned` in scope or scope creep?

**In scope.** REQUIREMENTS.md CLI-02 explicitly lists: `AiMemoryClient.write_page(path, body, tags, tier, pinned)`. The current implementation is missing these params; adding them fulfills an existing requirement. ✅

### Concern 2: Will provider tests break from error propagation change?

**No.** Verified by reading `test_provider.py` — every test that calls a client method replaces it with `MagicMock` before the call:
- `test_handle_tool_call_search`: `provider._client.search = MagicMock(return_value=[...])`
- `test_handle_tool_call_write`: `provider._client.write_page = MagicMock(return_value={...})`
- `test_handle_tool_call_status`: `provider._client.status = MagicMock(return_value={...})`

MagicMock returns the configured value regardless of the real method's error behavior. The change is transparent. The plan's risk assessment is correct. ✅

### Concern 3: Will 89% coverage hold after removing exception handler lines?

**Risky but manageable.** The plan has a reasonable estimate: removing ~16 lines of error handlers from client.py reduces total line count (those lines no longer count as "missed"), and adding 3+ tests adds coverage for tier/pinned and timeout paths. The contingency plan (non-transport `_request` path test) is well-designed. Recommendation: proceed but monitor coverage closely after Wave 2.

### Concern 4: Is TDD ordering correct (RED first, GREEN second)?

**Mostly correct.** Wave 1 (error propagation) is textbook TDD:
- Task 1 (RED): Tests rewritten to expect propagation → tests fail (code still swallows) ✅
- Task 2 (GREEN): Code changed to propagate → tests pass ✅

Wave 2 (params/timeouts) has a nuance:
- Task 3 (RED): 3 tests added. The `tier`/`pinned` test is a true RED (fails because params don't exist). The 2 timeout tests happen to pass immediately (code already passes correct timeouts). The plan acknowledges this internal inconsistency but chooses to keep the timeout tests as regression coverage. This is acceptable but muddies the RED→GREEN clarity for Wave 2.
- Task 4 (GREEN): Only adds `tier`/`pinned` params (timeout changes not needed). ✅

---

## Goal-Backward Check

**Phase goal:** "The plugin can communicate with an ai-memory server over HTTP for all required operations with appropriate timeout and error handling per endpoint type."

**If all 4 tasks complete (with the BLOCKER fix):**

| Outcome | Status |
|---------|--------|
| `search()` propagates HTTP errors | ✅ Done |
| `write_page()` supports `tier`/`pinned`, propagates errors | ✅ Done |
| `status()` propagates errors | ✅ Done |
| `send_hook()` still swallows errors | ✅ Preserved |
| `fetch_handoff()` returns `None` on 404, propagates on 500 | ✅ Done |
| `search()` uses 10s timeout | ✅ Tested |
| `send_hook()` uses 0.5s timeout | ✅ Tested |
| `write_page()` preserves `workspace`/`project` params | ✅ Preserved |
| `status()` and `fetch_handoff()` pass explicit `SEARCH_TIMEOUT` | ✅ Already correct |
| Existing tests pass (43→46) | ✅ Expected |
| Coverage ≥ 89% | ⚠️ Risk (mitigated) |

**Phase 2 would be done.** The BLOCKER (missing transport in search timeout test) is a fixable bug in the plan's test code, not a scope/design gap.

---

## Summary

```
Dimension 1 (Requirement Coverage):  ✅ PASS
Dimension 2 (Task Completeness):      ✅ PASS (1 warning — inaccurate verify expectations)
Dimension 3 (Dependency Correctness): ✅ PASS
Dimension 4 (Key Links Planned):      ✅ PASS
Dimension 5 (Scope Sanity):          ✅ PASS (1 warning — 4 tasks)
Dimension 6 (Verification Derivation):✅ PASS

BLOCKERS: 1  WARNINGS: 2
```

**1 BLOCKER**: Task 3 `test_client_search_uses_search_timeout` missing `client._transport` setup — test can never pass after Wave 1 removes the try/except from `search()`. Fix: add `client._transport = httpx.MockTransport(handler)`.

**2 WARNINGS:**
1. Task 3 Step 5 verify expectations are inaccurate (claims all 3 tests fail; hook timeout test will actually pass)
2. 4 tasks at warning threshold (acceptable given narrow scope of 2 files)

---

## Recommendation

**CONDITIONAL PASS** — fix the BLOCKER (add transport setup to search timeout test), then proceed to execution. The 2 warnings are noted but do not block execution.
