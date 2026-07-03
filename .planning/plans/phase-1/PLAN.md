# Phase 1: Config — Implementation Plan

> **For agentic workers:** TDD mode is enabled (`workflow.tdd_mode: true`). Follow RED→GREEN→REFACTOR for every code change. Quality gates must pass after plan completion: `ruff check .`, `mypy .`, `pytest --cov` (fail_under 89).

**Goal:** Users can configure the ai-memory plugin connection via JSON file, environment variables, or the Hermes setup wizard — with all four CFG requirements passing.

**Architecture:** Five tasks across two waves. Wave 1 fixes the `api_key` schema bug, enables mypy on plugin code, and cleans up ruff. Wave 2 expands test coverage with roundtrip, corrupt JSON, and extra-keys tests, plus refactors the one test using manual env var save/restore to `monkeypatch`.

**Tech Stack:** Python 3.10+, `pytest`, `monkeypatch`, `ruff`, `mypy`. No new dependencies.

---

## Dependency Analysis

```
Wave 1 (parallel):
  ├─ Task 1: Fix api_key schema in get_config_schema() + TDD  ── touches config.py, test_config.py
  ├─ Task 4: Fix mypy exclude to cover plugin code            ── touches pyproject.toml, conftest.py
  └─ Task 5: Fix ruff import ordering in test_provider.py     ── touches test_provider.py

Wave 2 (after Wave 1):
  ├─ Task 2: Add roundtrip + corrupt JSON + extra-keys tests  ── touches test_config.py only
  └─ Task 3: Refactor test_load_config_file_not_found → monkeypatch ── touches test_config.py only
```

- **Task 2 and 3 depend on Task 1** because Wave 1 updates `test_get_config_schema` assertions that would conflict if done in parallel.
- **Task 4 and 5 are independent** — no file overlap with Task 1 (they touch `pyproject.toml`, `conftest.py`, and `test_provider.py` respectively).
- **No external blockers.** All changes are to existing files with no new dependencies.

---

## Goal-Backward Check

| Requirement | How Phase 1 Satisfies It | Tasks |
|---|---|---|
| **CFG-01** — AiMemoryConfig dataclass | Already implemented (lines 12-18). Tests exist. No changes needed. | ✅ Existing |
| **CFG-02** — `get_config_schema()` returns field descriptors | Fix missing `api_key` field. Add to schema + update test assertion. | Task 1 |
| **CFG-03** — `save_config()` writes validated JSON | Add roundtrip test (save→load→same values). Add corrupt-JSON test. | Task 2 |
| **CFG-04** — `load_config()` reads JSON, falls back to env vars | Add corrupt-JSON fallback test. Refactor manual env var test to monkeypatch. | Tasks 2, 3 |

**Cross-cutting** — mypy and ruff must pass for quality gates:
| Quality Gate | Fix | Tasks |
|---|---|---|
| `mypy .` | Remove `exclude = ["plugins/"]` — currently skips all plugin code | Task 4 |
| `ruff check .` | Fix import sorting in test_provider.py | Task 5 |

---

## Baseline State (before any changes)

```
$ python3 -m pytest tests/test_config.py -v
→ 9 passed (100%)

$ python3 -m pytest tests/ --cov=plugins/memory/ai-memory
→ 40 passed, coverage: 86.34%  ✗ (below fail_under=89)
  config.py: 90% (misses: 58-59, 71-72 — except blocks)
  client.py: 86%
  provider.py: 89%
  __init__.py: 0%

$ python3 -m ruff check .
→ 1 error in test_provider.py (import block unsorted)

$ python3 -m mypy .
→ "Success: no issues found"  — but only checks tests/ (exclude = ["plugins/"] skips config.py, client.py, etc.)
```

---

## Task Breakdown

### Wave 1 — Parallel Tasks

---

### Task 1: Add `api_key` to `get_config_schema()` — TDD

**Type:** TDD (`workflow.tdd_mode: true`)
**Files:**
- Modify: `plugins/memory/ai-memory/config.py` — add `api_key` field descriptor to `get_config_schema()`
- Modify: `tests/test_config.py` — update `test_get_config_schema` to assert `api_key` in keys

**Why:** Pattern mapper identified a bug: `AiMemoryConfig` has `api_key: str` (used by `client.py` line 21 and `load_config` line 76), but `get_config_schema()` omits it. The Hermes setup wizard won't prompt for `api_key` — users who rely on API key auth can't configure it through the wizard.

**Pre-flight check (verify bug exists):**
```bash
python3 -c "from config import get_config_schema; print([k['key'] for k in get_config_schema()])"
# Output: ['server_url', 'auth_token', 'workspace', 'project']
# Note: 'api_key' is missing
```

**RED — Update test (tests/test_config.py, function test_get_config_schema):**

Modify the existing `test_get_config_schema` at line 33 to add the `api_key` assertion:

```python
def test_get_config_schema() -> None:
    schema = get_config_schema()
    keys = {item["key"] for item in schema}
    assert "server_url" in keys
    assert "api_key" in keys       # ← NEW
    assert "auth_token" in keys
    assert "workspace" in keys
    assert "project" in keys
```

```bash
python3 -m pytest tests/test_config.py::test_get_config_schema -v
# Expected: FAIL — AssertionError (api_key not in schema keys)
```

**GREEN — Add field to schema (config.py, function get_config_schema):**

Insert the `api_key` field descriptor at the second position (after `server_url`, before `auth_token`). Follow the same dict shape as existing fields:

```python
def get_config_schema() -> list[dict[str, Any]]:
    return [
        {
            "key": "server_url",
            "description": "ai-memory server URL",
            "default": DEFAULT_SERVER_URL,
            "required": False,
        },
        {
            "key": "api_key",
            "description": "ai-memory API key (alternative to auth_token for legacy auth)",
            "secret": True,
            "required": False,
            "env_var": "AI_MEMORY_API_KEY",
        },
        {
            "key": "auth_token",
            "description": "ai-memory auth token (optional for local mode)",
            "secret": True,
            "required": False,
            "env_var": "AI_MEMORY_AUTH_TOKEN",
        },
        # ... workspace, project unchanged
    ]
```

```bash
python3 -m pytest tests/test_config.py::test_get_config_schema -v
# Expected: PASS
```

**Verify full config suite still passes:**
```bash
python3 -m pytest tests/test_config.py -v
# Expected: 9 passed (all existing tests + updated schema test)
```

**Commit:**
```bash
git add plugins/memory/ai-memory/config.py tests/test_config.py
git commit -m "fix(cfg-02): add api_key to get_config_schema() — TDD

Pattern mapper identified missing api_key field descriptor. The dataclass,
client auth resolution, and load_config env fallback all reference api_key,
but the schema omitted it — meaning the Hermes setup wizard couldn't prompt
for it.

Test written first (RED), schema updated (GREEN).
"
```

---

### Task 4: Fix mypy `exclude` to cover plugin code

**Type:** Standard (config fix)
**Files:**
- Modify: `pyproject.toml` — change `exclude = ["plugins/"]` to `exclude = []`
- Modify: `tests/conftest.py` — add `# type: ignore` to `sys.path.insert` line
- Possibly: add per-file ignores for third-party imports

**Why:** Currently `mypy .` reports "Success: no issues found in 5 source files" — but only because it skips `plugins/`. The plugin code at `plugins/memory/ai-memory/config.py` is never type-checked. This is a known risk (ROADMAP.md item #4, STATE.md RD-04).

**Step 1 — Change pyproject.toml mypy config:**

Edit `pyproject.toml` lines 26-30:
```toml
[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true
exclude = []
```

**Step 2 — Run mypy to see what breaks:**
```bash
python3 -m mypy .
# Expected: errors about unresolved imports for conftest.py's sys.path.insert trick
# and possibly other type errors revealed now that plugins/ is checked
```

**Step 3 — Fix conftest.py (sys.path.insert line at line 11):**

This injection means `from config import AiMemoryConfig` resolves at runtime but mypy can't follow the sys.path modification. Add `# type: ignore`:

```python
sys.path.insert(                                          # type: ignore[import]
    0,
    str(Path(__file__).parent.parent / "plugins/memory/ai-memory"),
)
```

Then on the import lines below (16-18), `config`, `client`, `provider` are now resolvable because that path was added. These should be fine. But `httpx` import on line 8 may need an ignore since `ignore_missing_imports = true` already covers it.

**Step 4 — Run mypy again and fix remaining issues:**
```bash
python3 -m mypy .
# Fix any remaining errors by adding targeted # type: ignore comments
```

**Expected issues:**
- The `sys.path.insert` trick confuses mypy at the import site → `# type: ignore[import]`
- `AiMemoryConfig(**dict_comprehension)` in `load_config` line 78 — mypy strict may flag kwargs from dict → needs `# type: ignore[arg-type]` on that specific call
- Any uncovered issues in client.py/provider.py — fix with minimal targeted ignores

**Step 5 — Verify:**
```bash
python3 -m mypy .
# Expected: Success: no issues found in X source files
# (X should now include files under plugins/memory/ai-memory/)
```

**Step 6 — Verify tests still pass:**
```bash
python3 -m pytest tests/ -v
# Expected: 40 passed
```

**Commit:**
```bash
git add pyproject.toml tests/conftest.py
git commit -m "fix: enable mypy on plugin code by removing exclude filter

Previously exclude=[\"plugins/\"] skipped all type checking for the
plugin. Changed to exclude=[] and added targeted type: ignore comments:
- conftest.py sys.path.insert (mypy can't follow runtime path injection)
- config.py load_config kwargs filter (strict dict-to-kwargs mismatch)
"
```

---

### Task 5: Fix ruff import ordering in test_provider.py

**Type:** Standard (auto-fix)
**Files:**
- Modify: `tests/test_provider.py` — fix import block ordering

**Why:** `ruff check .` currently fails with 1 error in test_provider.py (imports not sorted). This blocks the quality gate.

**Step 1 — Apply auto-fix:**
```bash
python3 -m ruff check --fix .
# Expected: fixes 1 error in test_provider.py
```

**Step 2 — Verify ruff is clean:**
```bash
python3 -m ruff check .
# Expected: no errors
```

**Step 3 — Verify tests still pass:**
```bash
python3 -m pytest tests/ -v
# Expected: 40 passed
```

**Commit:**
```bash
git add tests/test_provider.py
git commit -m "style: fix ruff import ordering in test_provider.py

Auto-fix applied: python3 -m ruff check --fix .
"
```

---

### Wave 2 — After Wave 1 Tasks Complete

---

### Task 2: Add roundtrip, corrupt JSON, and extra-keys tests — TDD

**Type:** TDD (`workflow.tdd_mode: true`)
**Files:**
- Modify: `tests/test_config.py` — add 4 new tests

**Why:** Three coverage gaps exist:
1. **No roundtrip test** (ROADMAP success criterion: "Config round-trips idempotently")
2. **Missing coverage on lines 58-59 and 71-72** — the `except Exception: pass` blocks in `save_config` and `load_config` for corrupt JSON
3. **No test for extra keys in JSON** — the `hasattr` filter at line 78 is untested

**RED — Write 4 new tests (append to test_config.py):**

```python
def test_save_load_roundtrip(tmp_path: Path) -> None:
    """save_config then load_config produces identical values."""
    values = {
        "server_url": "http://roundtrip:49374",
        "auth_token": "roundtrip-token",
        "api_key": "roundtrip-api-key",
        "workspace": "roundtrip-ws",
        "project": "roundtrip-proj",
    }
    save_config(values, str(tmp_path))
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://roundtrip:49374"
    assert cfg.auth_token == "roundtrip-token"
    assert cfg.api_key == "roundtrip-api-key"
    assert cfg.workspace == "roundtrip-ws"
    assert cfg.project == "roundtrip-proj"


def test_load_config_corrupt_json_falls_back(tmp_path: Path) -> None:
    """Corrupt JSON file causes fallback to defaults, not crash."""
    p = tmp_path / "ai-memory.json"
    p.write_text("this is not valid json {{{")
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.auth_token == ""


def test_save_config_corrupt_json_merges(tmp_path: Path) -> None:
    """Corrupt existing JSON is discarded and replaced by fresh save."""
    p = tmp_path / "ai-memory.json"
    p.write_text("{{{garbage}}}")
    save_config({"server_url": "http://fresh:49374"}, str(tmp_path))
    data = json.loads(p.read_text())
    assert data["server_url"] == "http://fresh:49374"
    assert len(data) == 1  # corrupt data was replaced, not merged into


def test_load_config_extra_keys_filtered(tmp_path: Path) -> None:
    """Extra keys in JSON file are stripped — only dataclass fields used."""
    p = tmp_path / "ai-memory.json"
    p.write_text(json.dumps({
        "server_url": "http://filter:49374",
        "unknown_key": "should be ignored",
        "another_unknown": 42,
    }))
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://filter:49374"
    assert not hasattr(cfg, "unknown_key")
```

**Verify all 4 tests fail initially:**
```bash
python3 -m pytest tests/test_config.py::test_save_load_roundtrip \
  tests/test_config.py::test_load_config_corrupt_json_falls_back \
  tests/test_config.py::test_save_config_corrupt_json_merges \
  tests/test_config.py::test_load_config_extra_keys_filtered -v
# Expected: 4 passed (because the implementation already handles these cases)
# Note: The implementation already has the except: pass and hasattr filter.
# The tests validate existing behavior — they should pass immediately.
```

Unlike the usual RED→GREEN, these tests verify existing behavior that is already correct. The value is in coverage and regression protection. If any test fails, it reveals an unexpected implementation issue.

**Step 2 — Verify coverage bump:**
```bash
python3 -m pytest tests/test_config.py --cov=plugins/memory/ai-memory --cov-report=term-missing
# Expected:
#   config.py coverage: 90% → 100%
#   Previously missed lines 58-59 and 71-72 now covered
```

**Step 3 — Verify full suite still passes:**
```bash
python3 -m pytest tests/ -v
# Expected: 44 passed
```

**Commit:**
```bash
git add tests/test_config.py
git commit -m "test(cfg-03,cfg-04): add roundtrip, corrupt JSON, extra-keys tests

- test_save_load_roundtrip: verifies idempotent save→load cycle
- test_load_config_corrupt_json_falls_back: covers except block at lines 71-72
- test_save_config_corrupt_json_merges: covers except block at lines 58-59
- test_load_config_extra_keys_filtered: covers hasattr filter at line 78

Config.py coverage: 90% → 100%
"
```

---

### Task 3: Refactor `test_load_config_file_not_found` to use `monkeypatch`

**Type:** Refactor (standard)
**Files:**
- Modify: `tests/test_config.py` — refactor `test_load_config_file_not_found` (lines 75-86)

**Why:** Pattern mapper flagged this as inconsistent — the test uses manual `os.environ.pop()` + try/finally save/restore, while `test_load_config_falls_back_to_env` uses `monkeypatch`. The manual pattern is fragile (process-global env vars, can leak on exception edge cases). `monkeypatch` is safer and cleaner.

**Step 1 — Replace the test function body:**

Current code (lines 75-86):
```python
def test_load_config_file_not_found(tmp_path: Path) -> None:
    old_url = os.environ.pop("AI_MEMORY_SERVER_URL", None)
    old_token = os.environ.pop("AI_MEMORY_AUTH_TOKEN", None)
    try:
        cfg = load_config(str(tmp_path))
        assert cfg.server_url == "http://127.0.0.1:49374"
        assert cfg.auth_token == ""
    finally:
        if old_url is not None:
            os.environ["AI_MEMORY_SERVER_URL"] = old_url
        if old_token is not None:
            os.environ["AI_MEMORY_AUTH_TOKEN"] = old_token
```

Replace with:
```python
def test_load_config_file_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.auth_token == ""
```

Also check if `import os` at the top of `test_config.py` can be removed now. If `os` is not used anywhere else in the file, remove it to keep imports clean. If other tests still use `os`, leave it.

**Step 2 — Verify test passes:**
```bash
python3 -m pytest tests/test_config.py::test_load_config_file_not_found -v
# Expected: PASS
```

**Step 3 — Verify full config suite:**
```bash
python3 -m pytest tests/test_config.py -v
# Expected: 13 passed (9 original + 4 new from Task 2)
```

**Step 4 — Check if `import os` can be cleaned up:**
```bash
python3 -c "import ast; tree = ast.parse(open('tests/test_config.py').read()); names = [n.name for n in ast.walk(tree) if isinstance(n, ast.Name)]; print('os used' if 'os' in names else 'os unused')"
# If 'os unused', remove 'import os' from test_config.py imports
```

**Commit:**
```bash
git add tests/test_config.py
git commit -m "refactor: use monkeypatch instead of manual os.environ pop in test

test_load_config_file_not_found now uses monkeypatch.delenv() instead of
manual os.environ.pop() + try/finally save/restore. Safer (auto-restores,
scoped to test function) and consistent with the other env var test.
"
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **mypy strict mode reveals many type errors** now that `plugins/` is included | Medium | Medium | Use targeted `# type: ignore` comments per issue rather than broad `ignore_missing_imports` changes. The config module is small (39 lines) — at most 2-3 annotations needed. |
| **Roundtrip test fails** because `save_config` then `load_config` aren't exactly symmetric | Low | Low | Investigate cause: likely a field name mismatch or extra key in the roundtrip. Fix the asymmetry, not the test. |
| **Coverage still below 89%** after Phase 1 (because client.py/provider.py/__init__.py are outside scope) | High | Medium | The 89% threshold is for the **whole project**. Phase 1 only touches config.py — other modules' coverage won't change. Currently 86.34%. Adding ~4% to config.py alone won't cross the threshold. **Mitigation:** Accept that the quality gate may not pass until Phase 3 (provider) adds more tests. If strict pass is required before Phase 2, we need to add tests for other modules too — which would expand this plan. **Recommendation:** Proceed with config-only improvements; the quality gate full pass is a milestone-level gate, not a per-phase gate per the ROADMAP. |
| **Existing tests break** from schema change | Very Low | High | Only `test_get_config_schema` asserts on schema keys — and we're adding, not removing. |
| **Conftest import pattern** doesn't survive mypy strict mode | Medium | Medium | The `sys.path.insert` trick is the main concern. If it can't be cleanly annotated, we may need to switch to relative imports (`from plugins.memory.ai_memory.config import ...`) — but that affects all test files. Start with targeted `# type: ignore`. |
| **Ruff fix reveals other issues** | Low | Low | `--fix` handles the import sort. If it triggers reformatting that breaks something, `ruff format` is deterministic. |

---

## Definition of Done

**Observable success criteria (all must be true):**

- [ ] `python3 -m pytest tests/test_config.py -v` → 13 passed (9 original + 4 new)
- [ ] `python3 -m pytest tests/ -v` → 44 passed
- [ ] `python3 -m ruff check .` → zero errors
- [ ] `python3 -m mypy .` → "Success: no issues found" (now including `plugins/memory/ai-memory/` files)
- [ ] `python3 -c "from config import get_config_schema; assert 'api_key' in {f['key'] for f in get_config_schema()}"` → exits 0
- [ ] `python3 -m pytest tests/test_config.py --cov=plugins/memory/ai-memory --cov-report=term-missing` → config.py coverage 100% (no missing lines)
- [ ] `test_load_config_file_not_found` uses `monkeypatch` parameter (no `os.environ.pop`)
- [ ] All commits reference requirement IDs (CFG-02, CFG-03, CFG-04)

**Requirements coverage:**

| Requirement | Status | Evidence |
|---|---|---|
| CFG-01 — AiMemoryConfig dataclass | ✅ Already satisfied | 2 tests pass, no changes needed |
| CFG-02 — get_config_schema() fields | ✅ Fixed | `api_key` added to schema, test asserts all 5 keys |
| CFG-03 — save_config() writes JSON | ✅ Verified | Roundtrip test proves save→load idempotency |
| CFG-04 — load_config() with env fallback | ✅ Verified | Corrupt JSON, extra keys, env fallback all tested |

---

## Execution Order

```bash
# Wave 1 (can run in parallel — no file conflicts):
#   Task 1: api_key schema fix (TDD)
#   Task 4: mypy exclude fix
#   Task 5: ruff fix

# Wave 2 (after Wave 1):
#   Task 2: roundtrip + corrupt JSON tests (TDD)
#   Task 3: monkeypatch refactor

# Final verification:
python3 -m ruff check . && python3 -m mypy . && python3 -m pytest tests/
```
